import os
import uuid
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web
from ai_core import (
    ask_gyert, speech_to_text, text_to_speech, clear_history,
    is_conference_trigger, CONFERENCE_FULL_TEXT, CONFERENCE_SPEECH_AUDIO
)

load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🧹 Очистить память", callback_data="clear_mem")
    return builder.as_markup()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Приветствую! Я **GyertAI** — полноценный искусственный интеллект нового поколения.\n\n"
        "Задавайте любые вопросы текстом или отправляйте голосовые сообщения — я отвечу вам.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(F.data == "clear_mem")
async def cb_clear(callback: types.CallbackQuery):
    clear_history(f"tg_{callback.message.chat.id}")
    await callback.answer("Память диалога очищена!")
    await callback.message.answer("🧹 Память сброшена. Готов к новым задачам!")

@dp.message(F.text)
async def handle_text(message: types.Message):
    chat_id = message.chat.id
    user_text = message.text

    # Строгая проверка точной фразы для конференции СМТЛ
    if is_conference_trigger(user_text):
        await bot.send_chat_action(chat_id=chat_id, action="record_voice")
        await message.answer(CONFERENCE_FULL_TEXT)
        
        os.makedirs("temp_audio", exist_ok=True)
        out_mp3 = os.path.join("temp_audio", f"conf_{uuid.uuid4()}.mp3")
        try:
            # Озвучиваем строго речь без юридической приписки
            await text_to_speech(CONFERENCE_SPEECH_AUDIO, out_mp3)
            await message.answer_audio(types.FSInputFile(out_mp3), title="GyertAI — Приветствие")
        finally:
            if os.path.exists(out_mp3):
                os.remove(out_mp3)
        return

    # Обычный режим работы ИИ во всех остальных случаях
    await bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        reply = await ask_gyert(f"tg_{chat_id}", user_text)
        await message.answer(reply, reply_markup=get_main_keyboard())
    except Exception as e:
        await message.answer(f"⚠️ Ошибка ядра: {e}")

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
        
        if is_conference_trigger(user_text):
            await message.answer(CONFERENCE_FULL_TEXT)
            await bot.send_chat_action(chat_id=chat_id, action="record_voice")
            await text_to_speech(CONFERENCE_SPEECH_AUDIO, out_mp3)
            await message.answer_audio(types.FSInputFile(out_mp3), title="GyertAI — Приветствие")
            return

        reply = await ask_gyert(f"tg_{chat_id}", user_text)
        await message.answer(reply, reply_markup=get_main_keyboard())
        
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
    print("🤖 Telegram-бот GyertAI обновлён и запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
