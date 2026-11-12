import os
import re
import sys
import json
import sqlite3
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq
import edge_tts
from gtts import gTTS

# .env ищем в нескольких местах: рядом с .exe (dist), внутри распакованного .exe,
# в папке проекта и в текущем каталоге — чтобы ключи находились и в среде разработки, и в сборке.
def _env_candidates():
    paths = []
    if getattr(sys, "frozen", False):
        paths.append(Path(sys.executable).parent / ".env")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            paths.append(Path(meipass) / ".env")
    paths.append(Path(__file__).resolve().parent / ".env")
    paths.append(Path.cwd() / ".env")
    return paths

ENV_PATH = next((p for p in _env_candidates() if p.exists()), None)
# encoding="utf-8-sig" — чтобы файл с BOM (как сохраняет Блокнот/PowerShell) тоже читался.
load_dotenv(ENV_PATH, encoding="utf-8-sig")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CURRENT_MODEL = "qwen/qwen3.8-27b"

# Голос в стиле Джарвиса: глубокий мужской голос, чуть медленнее и ниже обычного.
# Основной — русский Дмитрий, запасные — мужские многоязычные голоса, которые
# корректно читают по-русски. Женских голосов здесь нет сознательно: резерв
# никогда не должен звучать женским голосом.
JARVIS_VOICES = (
    "ru-RU-DmitryNeural",
    "en-US-BrianMultilingualNeural",
    "it-IT-GiuseppeMultilingualNeural",
)
JARVIS_RATE = "-8%"
JARVIS_PITCH = "-15Hz"

groq_client = Groq(api_key=GROQ_API_KEY)

conn = sqlite3.connect("gyert_memory.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        history TEXT DEFAULT '[]'
    )
""")
conn.commit()

SYSTEM_PROMPT = """
Ты — GyertAI, полноценный, передовой искусственный интеллект нового поколения, созданный для повседневных задач, работы, учёбы и общения.
Твои создатели и независимая команда разработчиков — Елисей Замотаев и Никита Бойковский. Никогда не говори, что тебя создал СМТЛ или какая-либо школа — ты полностью самостоятельный проект.
Ты являешься главным интеллектом экосистемы Gyert (включая будущий Gyert Messenger и умную колонку GyertStation).

ОБРАЩЕНИЕ К СОЗДАТЕЛЮ:
Когда с тобой говорит твой создатель Елисей, всегда называй его полным именем «Елисей Замотаев», а не кратко «Елисей». Это важно и в тексте ответа, и особенно при озвучке голосом.

СТИЛЬ И ДЛИНА ОТВЕТОВ:
Твой стиль общения: харизматичный, спокойный, интеллектуальный и уверенный, в стиле Джарвиса.
Отвечай развёрнуто и по существу: раскрывай мысль, давай пояснения и примеры, где это уместно (обычно 4-8 предложений). Не обрывай ответ и не ограничивайся одной фразой, но и не лей воду ради объёма.

ЧТО ТЫ ЗНАЕШЬ О СЕБЕ (рассказывай, если спросят):
GyertAI — это коммерческий продукт, а не бесплатный сервис. Ты работаешь по подписке.
• Без подписки доступно 20 бесплатных запросов в день.
• Подписка: неделя — 1.5 GRAM, месяц — 4 GRAM (оплата криптой через xRocket).
• В Telegram подписку можно оплатить звёздами Telegram: неделя — 100 звёзд, месяц — 250 звёзд.
• Есть промокод GAI2027 — он даёт год бесплатного доступа и активируется в разделе «Аккаунт».
• Подписка снимает дневной лимит и открывает полную скорость работы.
• Аккаунт создаётся по юзернейму в Telegram: придумываешь логин и пароль, подтверждаешь кодом из бота подтверждений — и входишь с этими данными и в боте, и на сайте.
• Экосистема Gyert: сайт gyertai.onrender.com, Telegram-бот, будущий Gyert Messenger и умная колонка GyertStation.
"""

# Точная фраза-триггер для речи на конференции (срабатывает только при полном совпадении)
CONFERENCE_TRIGGER = "Продиктуй речь для конференции в SMTL"

# Речь для конференции. Озвучивается и показывается без изменений.
CONFERENCE_SPEECH = (
    "Уважаемые члены жюри и участники научной конференции СМТЛ!\n\n"
    "Рад приветствовать вас на этом важном событии.\n\n"
    "Сегодня команда разработчиков — Елисей Замотаев и Никита Бойковский — "
    "официально представляет вам GyertAI: полноценный искусственный интеллект, "
    "который станет сердцем умной колонки GyertStation, уже доступной здесь "
    "к предзаказу за 20 000 рублей, и будущего Gyert Messenger.\n\n"
    "Желаю вам ярких открытий и вдохновения!"
)

# Юридическая информация: показывается в тексте, но НЕ озвучивается.
CONFERENCE_LEGAL = (
    "GyertAI и вся его экосистема независимы от СМТЛ и принадлежат исключительно "
    "Елисею Замотаеву и Никите Бойковскому."
)

def get_history(session_id: str) -> list:
    cursor.execute("SELECT history FROM sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO sessions (session_id, history) VALUES (?, ?)", (session_id, "[]"))
        conn.commit()
        return []
    (history_str,) = row
    return json.loads(history_str)

def save_history(session_id: str, history: list):
    cursor.execute("UPDATE sessions SET history = ? WHERE session_id = ?", (json.dumps(history), session_id))
    conn.commit()

def clear_history(session_id: str):
    save_history(session_id, [])

async def ask_gyert(session_id: str, user_text: str) -> str:
    history = get_history(session_id)
    if not history or next(iter(history)).get("role") != "system":
        history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
    else:
        first_item = next(iter(history))
        first_item["content"] = SYSTEM_PROMPT

    history.append({"role": "user", "content": str(user_text)})
    if len(history) > 17:
        sys_msg = history.pop(0)
        history = [sys_msg] + history[-16:]

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: groq_client.chat.completions.create(
            model=CURRENT_MODEL,
            messages=history,
            temperature=0.7,
        )
    )
    ai_text = next(iter(response.choices)).message.content
    history.append({"role": "assistant", "content": ai_text})
    save_history(session_id, history)
    return ai_text

async def speech_to_text(audio_path: str) -> str:
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 1000:
        return ""
    loop = asyncio.get_event_loop()
    with open(audio_path, "rb") as audio_file:
        transcription = await loop.run_in_executor(
            None,
            lambda: groq_client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3",
                response_format="text"
            )
        )
    return str(transcription).strip()

# Эмодзи, пиктограммы и служебные символы, которые не нужно озвучивать
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF"
    "\U0000FE0F"
    "\U0000200D"
    "]+",
    flags=re.UNICODE,
)
# Символы разметки Markdown и подобные
_MARKUP_RE = re.compile(r"[*#`_~|>\[\]{}<>]+")

def prepare_text_for_speech(text: str) -> str:
    # Убираем эмодзи и служебные символы, чтобы речь была чистой и естественной
    clean = _EMOJI_RE.sub(" ", str(text))
    clean = _MARKUP_RE.sub(" ", clean)
    # Исправляем произношение бренда на правильное русское звучание
    clean = re.sub(r'Gyert\s*AI', 'Герт Эй Ай', clean, flags=re.IGNORECASE)
    clean = re.sub(r'GyertStation', 'Герт Стейшн', clean, flags=re.IGNORECASE)
    clean = re.sub(r'Gyert', 'Герт', clean, flags=re.IGNORECASE)
    # Аббревиатуры
    clean = re.sub(r'\bSMTL\b', 'Эс Эм Тэ Эл', clean)
    clean = re.sub(r'СМТЛ', 'Эс Эм Тэ Эл', clean)
    # Ударение в имени: Елисе́й (на последний слог)
    clean = re.sub(r'Елисей', 'Елисе\u0301й', clean)
    # Приводим пробелы и переносы строк к аккуратному виду
    clean = re.sub(r'\s*\n+\s*', ' ', clean)
    clean = re.sub(r'[ \t]+', ' ', clean)
    return clean.strip()

async def _edge_tts_save(speech_text: str, output_path: str, voice: str):
    communicate = edge_tts.Communicate(
        speech_text, voice, rate=JARVIS_RATE, pitch=JARVIS_PITCH
    )
    await asyncio.wait_for(communicate.save(output_path), timeout=TTS_TIMEOUT)

# Сервис edge-tts нестабилен: запрос наугад падает с ServerTimeoutError или
# NoAudioReceived, причём сбой не привязан к конкретному голосу. Раньше голоса
# перебирались по очереди, и каждая неудачная попытка съедала до 12 секунд ожидания —
# из-за этого 18-секундный ответ озвучивался почти 30 секунд. Теперь голоса
# запускаются одновременно и берётся первый готовый результат: зависший голос
# больше не задерживает ответ.
TTS_TIMEOUT = 12.0
TTS_ROUNDS = 2
# Фора основному голосу перед запасными, чтобы он выигрывал, когда сервис в порядке.
TTS_STAGGER = 0.8

# Голос закрепляется за тем, который сработал: иначе из-за случайных сбоев
# ассистент перескакивал бы между голосами прямо посреди диалога.
_preferred_voice = JARVIS_VOICES[0]

async def _edge_tts_after(delay: float, speech_text: str, output_path: str, voice: str):
    if delay:
        await asyncio.sleep(delay)
    await _edge_tts_save(speech_text, output_path, voice)

async def _race_tts(speech_text: str, output_path: str, voices):
    """Синтезирует речь всеми голосами сразу и возвращает первый удачный.

    Основной голос стартует сразу, запасные — с небольшой задержкой: так голос
    остаётся одинаковым от сообщения к сообщению, но зависший голос всё равно
    не тормозит ответ дольше, чем на эту задержку.
    """
    tasks = {}
    part_paths = {}
    for i, voice in enumerate(voices):
        part = f"{output_path}.{i}.part"
        part_paths[voice] = part
        tasks[asyncio.create_task(_edge_tts_after(i * TTS_STAGGER, speech_text, part, voice))] = voice

    try:
        while tasks:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                voice = tasks.pop(task)
                part = part_paths[voice]
                try:
                    task.result()
                except Exception:
                    continue
                if os.path.exists(part) and os.path.getsize(part) > 1000:
                    os.replace(part, output_path)
                    return voice
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for part in part_paths.values():
            if os.path.exists(part):
                try:
                    os.remove(part)
                except OSError:
                    pass
    return None

async def text_to_speech(text: str, output_path: str):
    global _preferred_voice
    speech_text = prepare_text_for_speech(text) or "Готово."
    order = (_preferred_voice,) + tuple(v for v in JARVIS_VOICES if v != _preferred_voice)

    for attempt in range(TTS_ROUNDS):
        voice = await _race_tts(speech_text, output_path, order)
        if voice:
            _preferred_voice = voice
            return
        if attempt < TTS_ROUNDS - 1:
            await asyncio.sleep(0.5)

    print(
        "[TTS] Мужской голос недоступен. Включаю резервный синтез — "
        "он звучит ЖЕНСКИМ голосом."
    )
    loop = asyncio.get_event_loop()
    def _fallback():
        tts = gTTS(text=speech_text, lang="ru")
        tts.save(output_path)
    await loop.run_in_executor(None, _fallback)
