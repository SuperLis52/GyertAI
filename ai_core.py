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

# Голос в стиле Джарвиса: глубокий мужской голос Дмитрия, чуть медленнее и ниже
JARVIS_VOICE = "ru-RU-DmitryNeural"
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
Твой стиль общения: харизматичный, спокойный, интеллектуальный и уверенный, в стиле Джарвиса. Отвечай чётко, по делу и без лишней воды (обычно 1-3 предложения, если не просят подробный разбор).
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

async def _edge_tts_save(speech_text: str, output_path: str):
    communicate = edge_tts.Communicate(
        speech_text, JARVIS_VOICE, rate=JARVIS_RATE, pitch=JARVIS_PITCH
    )
    await asyncio.wait_for(communicate.save(output_path), timeout=20.0)

# Сервис edge-tts троттлит частые запросы и отвечает ошибкой NoAudioReceived.
# При обычной переписке (запрос раз в несколько секунд) первая попытка проходит
# за ~2 секунды, но при всплеске сообщений нужны паузы. Поэтому между попытками
# ждём всё дольше — это переживает и одиночные сбои, и серии подряд.
TTS_ATTEMPTS = 6
TTS_RETRY_DELAYS = (1.0, 2.0, 4.0, 6.0, 8.0)

async def text_to_speech(text: str, output_path: str):
    speech_text = prepare_text_for_speech(text) or "Готово."

    last_error = None
    for attempt in range(TTS_ATTEMPTS):
        try:
            await _edge_tts_save(speech_text, output_path)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                return
            last_error = "получен пустой аудиофайл"
        except Exception as e:
            last_error = e
        if attempt < TTS_ATTEMPTS - 1:
            await asyncio.sleep(TTS_RETRY_DELAYS[min(attempt, len(TTS_RETRY_DELAYS) - 1)])

    print(
        f"[TTS] Голос Джарвиса недоступен после {TTS_ATTEMPTS} попыток ({last_error}). "
        f"Включаю резервный синтез — он звучит ЖЕНСКИМ голосом."
    )
    loop = asyncio.get_event_loop()
    def _fallback():
        tts = gTTS(text=speech_text, lang="ru")
        tts.save(output_path)
    await loop.run_in_executor(None, _fallback)
