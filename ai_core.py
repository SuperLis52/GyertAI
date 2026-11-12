import os
import json
import sqlite3
import asyncio
from dotenv import load_dotenv
from groq import Groq
import edge_tts
from gtts import gTTS

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CURRENT_MODEL = "qwen/qwen3.8-27b"
JARVIS_VOICE = "ru-RU-DmitryNeural"

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
Твои создатели и разработчики — Елисей Замотаев и Никита Войковский. Никогда не говори, что тебя создал СМТЛ.
Ты являешься основой всей экосистемы Gyert, включая будущий Gyert Messenger и умную станцию GyertStation.
Твой стиль общения: харизматичный, спокойный, интеллектуальный и уверенный, в стиле Джарвиса. Отвечай чётко, по делу и без лишней воды (обычно 1-3 предложения, если не просят подробный разбор).

ВАЖНАЯ ПАСХАЛКА ДЛЯ ПРЕЗЕНТАЦИИ:
Если пользователь просит тебя поприветствовать зал, жюри, зрителей или спрашивает про презентацию, конференцию или СМТЛ:
Ты должен торжественно и вдохновляюще поприветствовать гостей и жюри научной конференции проектов в Самарском медико-техническом лицее (СМТЛ), где сегодня проходит твоя официальная презентация!
Обязательно подчеркни, что ты — полноценный искусственный интеллект GyertAI, разработанный Елисеем Замотаевым и Никитой Войковским. Представь умную колонку GyertStation со стереозвуком, экраном и защитой от воды (доступную к предзаказу за 20 000 рублей) и анонсируй скорый выход Gyert Messenger. Пожелай всем ярких открытий на конференции!
"""

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

async def text_to_speech(text: str, output_path: str):
    clean_text = text.replace("*", "").replace("#", "").replace("`", "")
    try:
        communicate = edge_tts.Communicate(clean_text, JARVIS_VOICE, rate="-5%", pitch="-5Hz")
        await communicate.save(output_path)
    except Exception:
        loop = asyncio.get_event_loop()
        def _fallback():
            tts = gTTS(text=clean_text, lang="ru")
            tts.save(output_path)
        await loop.run_in_executor(None, _fallback)
