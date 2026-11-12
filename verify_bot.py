"""Отдельный Telegram-бот, который присылает только коды подтверждения.

Диалог с GyertAI ведёт основной бот, а коды — этот: пользователь один раз пишет
сюда, чтобы бот получил право отправлять ему сообщения, а сайт затем находит
человека по юзернейму.
"""
import asyncio
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from dotenv import load_dotenv

import accounts

load_dotenv(encoding="utf-8-sig")

TOKEN = os.environ.get("VERIFY_BOT_TOKEN")
bot = Bot(token=TOKEN) if TOKEN else None
dp = Dispatcher()


def remember(message: types.Message):
    username = getattr(message.from_user, "username", None)
    if username:
        accounts.link_verify_chat(username, message.chat.id)


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    remember(message)
    await message.answer(
        "🔐 Это бот подтверждений <b>GyertAI</b>.\n\n"
        "Сюда будут приходить коды для входа в аккаунт на сайте. "
        "Убедитесь, что в настройках Telegram задан юзернейм (@имя) — по нему "
        "сайт вас находит.",
        parse_mode="HTML",
    )


@dp.message(F.text)
async def handle_text(message: types.Message):
    remember(message)
    await message.answer(
        "Готово! Возвращайтесь на сайт GyertAI и нажмите «Получить код в Telegram» ещё раз."
    )


async def start_verify_bot():
    if bot is None:
        print("⚠️ VERIFY_BOT_TOKEN не задан — бот подтверждений не запущен.")
        return
    await bot.delete_webhook(drop_pending_updates=True)
    print("🔐 Бот подтверждений GyertAI запущен!")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(start_verify_bot())
