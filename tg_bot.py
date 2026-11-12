import os
import uuid
import asyncio
import html
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web
from ai_core import (
    ask_gyert,
    speech_to_text,
    text_to_speech,
    clear_history,
    CONFERENCE_TRIGGER,
    CONFERENCE_SPEECH,
    CONFERENCE_LEGAL,
)

load_dotenv(encoding="utf-8-sig")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🧹 Очистить память", callback_data="clear_mem")
    builder.adjust(1)
    return builder.as_markup()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Приветствую! Я <b>GyertAI</b> — интеллектуальное ядро экосистемы Gyert "
        "и умной станции <b>GyertStation</b>.\n\n"
        "Пиши мне любые задачи или отправляй голосовые сообщения — я отвечу голосом "
        "в стиле Джарвиса!",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(F.data == "clear_mem")
async def cb_clear(callback: types.CallbackQuery):
    clear_history(f"tg_{callback.message.chat.id}")
    await callback.answer("Память диалога очищена!")
    await callback.message.answer("🧹 Память сброшена. Готов к новым задачам!")

# Секретная активация речи на конференции: только точное сообщение,
# с полным совпадением регистра, пробелов и написания.
@dp.message(F.text == CONFERENCE_TRIGGER)
async def handle_conference_speech(message: types.Message):
    chat_id = message.chat.id
    await bot.send_chat_action(chat_id=chat_id, action="record_voice")

    # Показываем речь вместе с юридической информацией (она только в тексте,
    # озвучивается же исключительно сама речь).
    display_text = f"{html.escape(CONFERENCE_SPEECH)}\n\n<i>{html.escape(CONFERENCE_LEGAL)}</i>"
    await message.answer(display_text, parse_mode="HTML")

    os.makedirs("temp_audio", exist_ok=True)
    out_mp3 = os.path.join("temp_audio", f"conference_{uuid.uuid4()}.mp3")
    try:
        await text_to_speech(CONFERENCE_SPEECH, out_mp3)
        await message.answer_audio(
            types.FSInputFile(out_mp3), title="GyertAI — Речь для конференции"
        )
    except Exception as e:
        await message.answer(f"⚠️ Не удалось озвучить речь: {e}")
    finally:
        if os.path.exists(out_mp3):
            os.remove(out_mp3)

# /tts <текст> — озвучить произвольный текст голосом Джарвиса, без обращения к ИИ
@dp.message(Command("tts"))
async def cmd_tts(message: types.Message):
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.answer(
            "Напишите текст после команды, например:\n"
            "<code>/tts Добрый день, я GyertAI</code>",
            parse_mode="HTML",
        )
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="record_voice")
    os.makedirs("temp_audio", exist_ok=True)
    out_mp3 = os.path.join("temp_audio", f"tts_{uuid.uuid4()}.mp3")
    try:
        await text_to_speech(text, out_mp3)
        await message.answer_audio(types.FSInputFile(out_mp3), title="GyertAI — озвучка")
    except Exception as e:
        await message.answer(f"⚠️ Не удалось озвучить текст: {e}")
    finally:
        if os.path.exists(out_mp3):
            os.remove(out_mp3)

@dp.message(F.text)
async def handle_text(message: types.Message):
    chat_id = message.chat.id
    await bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        reply = await ask_gyert(f"tg_{chat_id}", message.text)
        await message.answer(reply, reply_markup=get_main_keyboard())
    except Exception as e:
        await message.answer(f"⚠️ Ошибка ядра: {e}")
        return

    # Озвучиваем ответ голосом Джарвиса и присылаем его аудиосообщением
    os.makedirs("temp_audio", exist_ok=True)
    out_mp3 = os.path.join("temp_audio", f"out_{uuid.uuid4()}.mp3")
    try:
        await bot.send_chat_action(chat_id=chat_id, action="record_voice")
        await text_to_speech(reply, out_mp3)
        await message.answer_audio(types.FSInputFile(out_mp3), title="GyertAI")
    except Exception as e:
        await message.answer(f"⚠️ Не удалось озвучить ответ: {e}")
    finally:
        if os.path.exists(out_mp3):
            os.remove(out_mp3)

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    chat_id = message.chat.id
    await bot.send_chat_action(chat_id=chat_id, action="typing")
    os.makedirs("temp_audio", exist_ok=True)
    in_ogg = os.path.join("temp_audio", f"in_{uuid.uuid4()}.ogg")
    out_mp3 = os.path.join("temp_audio", f"out_{uuid.uuid4()}.mp3")

    try:
        await bot.download(file=message.voice.file_id, destination=in_ogg)
        user_text = await speech_to_text(in_ogg)
        reply = await ask_gyert(f"tg_{chat_id}", user_text)

        await message.answer(
            f"🤖 <b>GyertAI:</b> {html.escape(reply)}",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )

        await bot.send_chat_action(chat_id=chat_id, action="record_voice")
        await text_to_speech(reply, out_mp3)
        await message.answer_audio(types.FSInputFile(out_mp3), title="GyertAI Voice")
    except Exception as e:
        await message.answer(f"⚠️ Ошибка голоса: {e}")
    finally:
        for f in (in_ogg, out_mp3):
            if os.path.exists(f):
                os.remove(f)

async def handle_web(request):
    return web.Response(text="GyertAI Telegram Bot is Live!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(start_web_server())
    print("🤖 Telegram-бот GyertAI успешно запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
