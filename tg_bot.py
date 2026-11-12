import os
import re
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
import accounts

load_dotenv(encoding="utf-8-sig")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Диалог создания аккаунта: chat_id -> {"step": "login"|"password"|"promo", ...}
AWAITING = {}

def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Аккаунт", callback_data="acc_show")
    builder.button(text="🧹 Очистить память", callback_data="clear_mem")
    builder.adjust(1)
    return builder.as_markup()

def _chat_id(event):
    chat = getattr(event, "chat", None)
    if chat is None:
        chat = getattr(getattr(event, "message", None), "chat", None)
    return getattr(chat, "id", None)

def remember_user(event):
    """Запоминает связку юзернейм -> чат: по ней сайт отправляет код подтверждения."""
    username = getattr(event.from_user, "username", None)
    chat_id = _chat_id(event)
    if username and chat_id is not None:
        accounts.link_telegram(username, chat_id)
    return username

def user_identity(message: types.Message):
    """Ключ для дневного лимита: аккаунт, если он создан, иначе сам чат."""
    username = remember_user(message)
    return accounts.resolve_identity(username, f"tg{_chat_id(message)}")

async def check_limit(message: types.Message) -> bool:
    """Списывает запрос и, если бесплатный лимит кончился, просит оформить подписку."""
    allowed, left = accounts.consume_request(user_identity(message))
    if allowed:
        return True
    await message.answer(
        f"⛔ Бесплатный лимит — {accounts.FREE_DAILY_LIMIT} запросов в день — исчерпан.\n\n"
        "Оформите подписку в разделе «👤 Аккаунт»:\n"
        "• неделя — 1.5 GRAM\n"
        "• месяц — 4 GRAM\n\n"
        "Или активируйте промокод там же.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )
    return False

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    remember_user(message)
    await message.answer(
        "👋 Приветствую! Я <b>GyertAI</b> — интеллектуальное ядро экосистемы Gyert "
        "и умной станции <b>GyertStation</b>.\n\n"
        "Пиши мне любые задачи или отправляй голосовые сообщения — я отвечу голосом "
        "в стиле Джарвиса!\n\n"
        f"Без подписки доступно {accounts.FREE_DAILY_LIMIT} запросов в день. "
        "Создать аккаунт, активировать промокод или оформить подписку — в разделе "
        "«👤 Аккаунт».",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(F.data == "clear_mem")
async def cb_clear(callback: types.CallbackQuery):
    clear_history(f"tg_{callback.message.chat.id}")
    await callback.answer("Память диалога очищена!")
    await callback.message.answer("🧹 Память сброшена. Готов к новым задачам!")

# --- Раздел «Аккаунт» ---------------------------------------------------------

def account_keyboard(state):
    builder = InlineKeyboardBuilder()
    if state and state["login"]:
        builder.button(text="💳 Неделя — 1.5 GRAM", callback_data="acc_buy_week")
        builder.button(text="💳 Месяц — 4 GRAM", callback_data="acc_buy_month")
        builder.button(text="🔑 Ввести промокод", callback_data="acc_promo")
    else:
        builder.button(text="✨ Создать аккаунт", callback_data="acc_create")
    builder.adjust(1)
    return builder.as_markup()

def account_text(state, username):
    if not state or not state["login"]:
        return (
            "👤 <b>Аккаунт GyertAI</b>\n\n"
            "Аккаунт создаётся по вашему юзернейму в Telegram: придумываете логин и пароль — "
            "и входите с ними на сайте.\n\n"
            f"Без подписки доступно {accounts.FREE_DAILY_LIMIT} запросов в день."
        )
    if state["subscribed"]:
        status = f"активна до {state['until']}"
    else:
        status = "не оформлена"
    promo = state["promo_used"] or "—"
    return (
        "👤 <b>Аккаунт GyertAI</b>\n\n"
        f"Telegram: @{username or '—'}\n"
        f"Логин: <b>{html.escape(state['login'])}</b>\n"
        f"Подписка: {status}\n"
        f"Промокод: {promo}\n\n"
        f"Бесплатный лимит: {accounts.FREE_DAILY_LIMIT} запросов в день."
    )

async def show_account(event):
    """Показывает карточку аккаунта. event — Message или CallbackQuery."""
    username = accounts.normalize_username(getattr(event.from_user, "username", "") or "")
    state = accounts.account_state(username) if username else None
    text = account_text(state, username)
    markup = account_keyboard(state)
    if isinstance(event, types.CallbackQuery):
        await event.message.answer(text, parse_mode="HTML", reply_markup=markup)
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=markup)

@dp.message(Command("account"))
async def cmd_account(message: types.Message):
    remember_user(message)
    await show_account(message)

@dp.callback_query(F.data == "acc_show")
async def cb_account(callback: types.CallbackQuery):
    remember_user(callback)
    await callback.answer()
    await show_account(callback)

@dp.callback_query(F.data == "acc_create")
async def cb_account_create(callback: types.CallbackQuery):
    username = remember_user(callback)
    await callback.answer()
    if not username:
        await callback.message.answer(
            "Сначала задайте юзернейм в настройках Telegram — он нужен для входа на сайте."
        )
        return
    AWAITING[_chat_id(callback)] = {"step": "login", "login": None}
    await callback.message.answer(
        "Придумайте логин для входа на сайте: 3–32 символа, латиница, цифры "
        "и подчёркивание.\n\nДля отмены напишите «отмена»."
    )

@dp.callback_query(F.data == "acc_promo")
async def cb_account_promo(callback: types.CallbackQuery):
    remember_user(callback)
    await callback.answer()
    AWAITING[_chat_id(callback)] = {"step": "promo"}
    await callback.message.answer("Введите промокод. Для отмены напишите «отмена».")

@dp.callback_query(F.data.in_({"acc_buy_week", "acc_buy_month"}))
async def cb_account_buy(callback: types.CallbackQuery):
    username = accounts.normalize_username(remember_user(callback) or "")
    await callback.answer()
    plan = "week" if callback.data == "acc_buy_week" else "month"
    days, price = accounts.PLANS[plan]
    ok, result = await asyncio.to_thread(accounts.create_invoice, username, plan)
    if not ok:
        await callback.message.answer(f"⚠️ {result}")
        return
    builder = InlineKeyboardBuilder()
    builder.button(text=f"Оплатить {price} GRAM", url=result)
    await callback.message.answer(
        f"💳 Счёт на <b>{price} GRAM</b> — подписка на {days} дней создан.\n"
        "Оплатите по кнопке ниже, подписка включится автоматически.",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )

def in_account_dialog(message: types.Message) -> bool:
    return _chat_id(message) in AWAITING

@dp.message(F.text, in_account_dialog)
async def handle_account_input(message: types.Message):
    state = AWAITING[_chat_id(message)]
    text = (message.text or "").strip()

    if text.lower() in {"отмена", "cancel", "/cancel"}:
        AWAITING.pop(_chat_id(message), None)
        await message.answer("Хорошо, отменил.")
        return

    if state["step"] == "promo":
        username = remember_user(message)
        ok, result = accounts.redeem_promo(username or "", text)
        AWAITING.pop(_chat_id(message), None)
        await message.answer(result, reply_markup=get_main_keyboard())
        return

    if state["step"] == "login":
        if not re.match(r"^[A-Za-z0-9_]{3,32}$", text):
            await message.answer("Логин: 3–32 символа, только латиница, цифры и подчёркивание.")
            return
        if accounts.login_taken(text):
            await message.answer("Такой логин уже занят, придумайте другой.")
            return
        state["login"] = text
        state["step"] = "password"
        await message.answer("Теперь придумайте пароль (не короче 6 символов).")
        return

    username = remember_user(message)
    ok, result = accounts.create_account(username or "", state["login"], text)
    AWAITING.pop(_chat_id(message), None)
    if ok:
        await message.answer(
            f"✅ {result}\n\nЛогин: <b>{html.escape(state['login'])}</b>\n"
            "С этими данными можно войти на сайте GyertAI.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )
    else:
        await message.answer(f"⚠️ {result}")

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
    if not await check_limit(message):
        return
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
    if not await check_limit(message):
        return
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
