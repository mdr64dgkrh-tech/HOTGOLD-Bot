import asyncio
import logging
import os
import re

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.getenv("ADMIN_ID", "7170883398"))

# Gold -> Telegram Stars
PACKAGES = {
    "HG-1000": {"gold": 1000, "stars": 999},
    "HG-3000": {"gold": 3000, "stars": 1599},
    "HG-6000": {"gold": 6000, "stars": 2999},
    "HG-9000": {"gold": 9000, "stars": 3999},
    "HG-16000": {"gold": 16000, "stars": 5999},
}

GAME_ID_PATTERN = re.compile(r"[0-9]{8,9}\Z")
DELIVERY_NOTICE = (
    "Gold будет зачислена на аккаунт не сразу, но в течении 78 часов. "
    "Если после истечения данного срока gold не поступит на ваш аккаунт, "
    "то обратитесь в поддержку. Она есть в шапке бота"
)


class Order(StatesGroup):
    game_id = State()
    confirmation = State()


dp = Dispatcher(storage=MemoryStorage())


def fmt(number: int) -> str:
    return f"{number:,}".replace(",", " ")


def packages_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for code, package in PACKAGES.items():
        rows.append([
            InlineKeyboardButton(
                text=f"{fmt(package['gold'])} Gold — {fmt(package['stars'])} ⭐",
                callback_data=f"package:{code}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Здравствуйте, спасибо что выбрали наш магазин! "
        "Выберите пожалуйста пакет, который бы вы хотели приобрести.",
        reply_markup=packages_keyboard(),
    )


@dp.callback_query(F.data.startswith("package:"))
async def choose_package(callback: CallbackQuery, state: FSMContext):
    code = callback.data.split(":", 1)[1]
    package = PACKAGES.get(code)
    if package is None:
        await callback.answer("Пакет не найден. Нажмите /start.", show_alert=True)
        return

    await state.clear()
    await state.update_data(code=code)
    await state.set_state(Order.game_id)
    await callback.answer(
        f"{fmt(package['gold'])} Gold — {fmt(package['stars'])} Stars ⭐",
        show_alert=True,
    )
    if callback.message:
        await callback.message.answer(
            f"Вы выбрали пакет: {fmt(package['gold'])} Gold.\n\n"
            "Отправьте ваш игровой ID (только 8 или 9 цифр)."
        )


@dp.message(Order.game_id, F.text)
async def get_game_id(message: Message, state: FSMContext):
    game_id = message.text
    if GAME_ID_PATTERN.fullmatch(game_id) is None:
        await message.answer("<b>ID введен неверно</b>", parse_mode=ParseMode.HTML)
        return

    await state.update_data(game_id=game_id)
    await state.set_state(Order.confirmation)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="Далее", callback_data="order:next")
        ]]
    )
    await message.answer(DELIVERY_NOTICE, reply_markup=keyboard)


@dp.callback_query(F.data == "order:next")
async def show_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    code = data.get("code")
    game_id = data.get("game_id")
    package = PACKAGES.get(code)
    if package is None or not game_id or GAME_ID_PATTERN.fullmatch(game_id) is None:
        await callback.answer("Заказ не найден. Начните заново: /start", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=f"Оплатить {fmt(package['stars'])} ⭐",
                callback_data="pay",
            )
        ]]
    )
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"Ваш заказ:\n"
            f"Gold: {fmt(package['gold'])}\n"
            f"Игровой ID: {game_id}\n"
            f"К оплате: {fmt(package['stars'])} Stars ⭐",
            reply_markup=keyboard,
        )


@dp.callback_query(F.data == "pay")
async def pay(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    code = data.get("code")
    game_id = data.get("game_id")
    package = PACKAGES.get(code)
    if package is None or not game_id or GAME_ID_PATTERN.fullmatch(game_id) is None:
        await callback.answer("Начните заново: /start", show_alert=True)
        return

    if callback.message:
        await callback.message.answer_invoice(
            title=f"{fmt(package['gold'])} Gold",
            description=f"Игровая валюта Gold для ID {game_id}",
            payload=f"{code}|{game_id}",
            currency="XTR",
            prices=[LabeledPrice(label=f"{fmt(package['gold'])} Gold", amount=package["stars"])],
        )
    await callback.answer()


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    parts = query.invoice_payload.split("|", 1)
    if len(parts) == 2:
        code, game_id = parts
        package = PACKAGES.get(code)
        valid = (
            package is not None
            and GAME_ID_PATTERN.fullmatch(game_id) is not None
            and query.currency == "XTR"
            and package["stars"] == query.total_amount
        )
    else:
        valid = False

    await query.answer(
        ok=valid,
        error_message=None if valid else "Ошибка заказа. Начните заново: /start",
    )


@dp.message(F.successful_payment)
async def paid(message: Message, state: FSMContext, bot: Bot):
    payment = message.successful_payment
    parts = payment.invoice_payload.split("|", 1)
    if len(parts) != 2:
        await message.answer("Платёж получен, но данные заказа нужно проверить через поддержку.")
        return

    code, game_id = parts
    package = PACKAGES.get(code)
    if package is None:
        await message.answer("Платёж получен, но пакет не распознан. Обратитесь в поддержку.")
        return

    await state.clear()
    await message.answer(
        f"Оплата прошла успешно ✅\n"
        f"{fmt(package['gold'])} Gold будут отправлены на ID {game_id}.\n"
        "Спасибо за покупку! Чтобы сделать новый заказ, нажмите /start."
    )

    buyer = message.from_user
    await bot.send_message(
        ADMIN_ID,
        f"💰 Новый оплаченный заказ\n"
        f"Gold: {fmt(package['gold'])}\n"
        f"Stars: {fmt(package['stars'])}\n"
        f"Игровой ID: {game_id}\n"
        f"Покупатель: {buyer.full_name} (@{buyer.username}, id {buyer.id})\n"
        f"charge_id: {payment.telegram_payment_charge_id}",
    )


async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(BOT_TOKEN)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
