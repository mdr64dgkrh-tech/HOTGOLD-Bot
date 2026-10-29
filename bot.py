import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           LabeledPrice, Message, PreCheckoutQuery)

BOT_TOKEN = os.environ["BOT_TOKEN"]          # токен от @BotFather
ADMIN_ID = int(os.environ["ADMIN_ID"])       # твой Telegram ID: сюда придут оплаченные заказы

# Каждый пакет = свой постоянный код (тот же, что показывает сайт). Gold -> Stars.
CODES = {
    "HG-1000": {"gold": 1000, "stars": 999},
    "HG-3000": {"gold": 3000, "stars": 1599},
    "HG-6000": {"gold": 6000, "stars": 2999},
    "HG-9000": {"gold": 9000, "stars": 3999},
}

class Order(StatesGroup):
    code = State()
    game_id = State()

dp = Dispatcher(storage=MemoryStorage())
fmt = lambda n: f"{n:,}".replace(",", " ")


@dp.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.set_state(Order.code)
    await m.answer("Здравствуйте, спасибо что выбрали наш магазин! "
                   "Пожалуйста, введите код, который вы получили на сайте после выбора пакета.")


@dp.message(Order.code, F.text)
async def got_code(m: Message, state: FSMContext):
    code = m.text.strip().upper()
    pkg = CODES.get(code)
    if not pkg:
        await m.answer("Код не найден. Проверьте его и отправьте ещё раз.")
        return
    await state.update_data(code=code)
    await state.set_state(Order.game_id)
    await m.answer(f"Сумма Gold — {fmt(pkg['gold'])}, итого с вас {fmt(pkg['stars'])} Stars ★.\n\n"
                   "Отправьте ваш игровой ID, чтобы мы знали, куда зачислить Gold.")


@dp.message(Order.game_id, F.text)
async def got_game_id(m: Message, state: FSMContext):
    game_id = m.text.strip()
    if not (3 <= len(game_id) <= 32) or " " in game_id:
        await m.answer("Игровой ID выглядит некорректно. Отправьте его ещё раз.")
        return
    data = await state.get_data()
    pkg = CODES[data["code"]]
    await state.update_data(game_id=game_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"Оплатить {fmt(pkg['stars'])} ★", callback_data="pay")]])
    await m.answer(f"Заказ: {fmt(pkg['gold'])} Gold\nИгровой ID: {game_id}\n"
                   f"К оплате: {fmt(pkg['stars'])} Stars ★", reply_markup=kb)


@dp.callback_query(F.data == "pay")
async def pay(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "code" not in data or "game_id" not in data:
        await c.answer("Начните заново: /start", show_alert=True)
        return
    pkg = CODES[data["code"]]
    await c.message.answer_invoice(
        title=f"{fmt(pkg['gold'])} Gold",
        description=f"Игровая валюта Gold для ID {data['game_id']}",
        payload=f"{data['code']}|{data['game_id']}",
        currency="XTR",                      # Telegram Stars; provider_token не нужен
        prices=[LabeledPrice(label=f"{fmt(pkg['gold'])} Gold", amount=pkg["stars"])],
    )
    await c.answer()


@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    code = q.invoice_payload.split("|")[0]
    ok = code in CODES and CODES[code]["stars"] == q.total_amount
    await q.answer(ok=ok, error_message=None if ok else "Ошибка заказа, начните заново: /start")


@dp.message(F.successful_payment)
async def paid(m: Message, state: FSMContext, bot: Bot):
    sp = m.successful_payment
    code, game_id = sp.invoice_payload.split("|", 1)
    pkg = CODES[code]
    await state.clear()
    await m.answer(f"Оплата прошла успешно ✅\n{fmt(pkg['gold'])} Gold будут отправлены на ID {game_id}. "
                   "Спасибо за покупку! Чтобы сделать новый заказ, нажмите /start.")
    u = m.from_user
    await bot.send_message(
        ADMIN_ID,
        f"💰 Новый оплаченный заказ\nGold: {fmt(pkg['gold'])}\nStars: {fmt(pkg['stars'])}\n"
        f"Игровой ID: {game_id}\nПокупатель: {u.full_name} (@{u.username}, id {u.id})\n"
        f"charge_id: {sp.telegram_payment_charge_id}")


async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(Bot(BOT_TOKEN))

if __name__ == "__main__":
    asyncio.run(main())
