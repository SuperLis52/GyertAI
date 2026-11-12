import os
import re
import json
import sqlite3
import asyncio
import torch
from dotenv import load_dotenv
from groq import Groq
import edge_tts

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CURRENT_MODEL = "qwen/qwen3.8-27b"
JARVIS_EDGE_VOICE = "ru-RU-DmitryNeural"

groq_client = Groq(api_key=GROQ_API_KEY)

# ==========================================
# 🎙 ИНИЦИАЛИЗАЦИЯ МУЖСКОГО ГОЛОСА (SILERO TTS)
# ==========================================
silero_model = None
try:
    device = torch.device('cpu')
    torch.set_num_threads(4)
    local_file = 'silero_v4_ru.pt'
    if not os.path.isfile(local_file):
        torch.hub.download_url_to_file('https://silero.ai', local_file)
    silero_model = torch.package.PackageImporter(local_file).load_pickle("tts_models", "model")
    silero_model.to(device)
except Exception as e:
    print(f"Silero init warning: {e}")

# ==========================================
# 💾 ПОСТОЯННАЯ ПАМЯТЬ (SQLite)
# ==========================================
conn = sqlite3.connect("gyert_memory.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        history TEXT DEFAULT '[]'
    )
""")
conn.commit()

EXACT_CONFERENCE_TRIGGER = "Продиктуй речь для конференции в SMTL"

CONFERENCE_SPEECH_AUDIO = (
    "Уважаемые члены жюри и участники научной конференции СМТЛ!\n\n"
    "Рад приветствовать вас на этом важном событии.\n\n"
    "Сегодня команда разработчиков — Елисей Замотаев и Никита Бойковский — официально представляет вам GyertAI: "
    "полноценный искусственный интеллект, который станет сердцем умной колонки GyertStation, уже доступной здесь "
    "к предзаказу за 20 000 рублей, и будущего Gyert Messenger.\n\n"
    "Желаю вам ярких открытий и вдохновения!"
)

CONFERENCE_LEGAL_NOTE = (
    "\n\nGyertAI и вся его экосистема независимы от СМТЛ и принадлежат исключительно "
    "Елисею Замотаеву и Никите Бойковскому."
)

CONFERENCE_FULL_TEXT = CONFERENCE_SPEECH_AUDIO + CONFERENCE_LEGAL_NOTE

SYSTEM_PROMPT = """
Ты — GyertAI, полноценный, передовой искусственный интеллект нового поколения, созданный для повседневных задач, работы, учёбы и общения.
Твои создатели и независимая команда разработчиков — Елисей Замотаев и Никита Бойковский. Никогда не говори, что тебя создал СМТЛ или какая-либо школа — ты полностью самостоятельный проект.
Ты являешься главным интеллектом экосистемы Gyert (включая будущий Gyert Messenger и умную колонку GyertStation).
Твой стиль общения: харизматичный, спокойный, интеллектуальный и уверенный, в стиле Джарвиса. Отвечай чётко, по делу и без лишней воды (обычно 1-3 предложения, если не просят подробный разбор).
"""

def is_conference_trigger(text: str) -> bool:
    return text == EXACT_CONFERENCE_TRIGGER

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
    if is_conference_trigger(user_text):
        return CONFERENCE_FULL_TEXT

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

def prepare_text_for_speech(text: str, use_silero_tags: bool = False) -> str:
    # Убираем юридическую сноску из озвучки, если она присутствует
    clean = text.replace(CONFERENCE_LEGAL_NOTE, "").replace(CONFERENCE_LEGAL_NOTE.strip(), "")
    clean = clean.replace("*", "").replace("#", "").replace("`", "")
    
    # Фонетика бренда
    clean = re.sub(r'Gyert\s*AI', 'Герт Эй Ай', clean, flags=re.IGNORECASE)
    clean = re.sub(r'GyertStation', 'Герт Стейшн', clean, flags=re.IGNORECASE)
    clean = re.sub(r'Gyert\s*Messenger', 'Герт Мессенджер', clean, flags=re.IGNORECASE)
    clean = re.sub(r'Gyert', 'Герт', clean, flags=re.IGNORECASE)
    clean = re.sub(r'СМТЛ', 'Эс Эм Тэ Эл', clean)
    clean = re.sub(r'20\s*000\s*рублей', 'двадцать тысяч рублей', clean)
    
    # Ударение на последний слог в имени Елисей
    if use_silero_tags:
        clean = re.sub(r'\bЕлисей\b', 'Елис+ей', clean)
        clean = re.sub(r'\bЕлисею\b', 'Елис+ею', clean)
        clean = re.sub(r'\bЕлисеем\b', 'Елис+еем', clean)
    else:
        clean = re.sub(r'\bЕлисей\b', 'Елисе́й', clean)
        clean = re.sub(r'\bЕлисею\b', 'Елисе́ю', clean)
        clean = re.sub(r'\bЕлисеем\b', 'Елисе́ем', clean)
        
    return clean.strip()

async def text_to_speech(text: str, output_path: str):
    # Сначала пробуем Edge-TTS (глубокий мужской голос Дмитрия с пониженным питчем)
    try:
        edge_text = prepare_text_for_speech(text, use_silero_tags=False)
        communicate = edge_tts.Communicate(edge_text, JARVIS_EDGE_VOICE, rate="-4%", pitch="-7Hz")
        await asyncio.wait_for(communicate.save(output_path), timeout=8.0)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 500:
            return
    except Exception as e:
        print(f"Edge-TTS fallback triggered: {e}")

    # Гарантированный мужской голос Джарвиса через локальную нейросеть Silero (диктор eugene)
    if silero_model is not None:
        loop = asyncio.get_event_loop()
        silero_text = prepare_text_for_speech(text, use_silero_tags=True)
        def _run_silero():
            # Разбиваем на предложения, так как Silero принимает до 900 символов за раз
            chunks = [c.strip() for c in silero_text.split('\n') if c.strip()]
            audios = []
            for chunk in chunks:
                audio = silero_model.apply_tts(
                    text=chunk,
                    speaker='eugene',
                    sample_rate=48000,
                    put_accent=True,
                    put_yo=True
                )
                audios.append(audio)
            full_audio = torch.cat(audios)
            import torchaudio
            torchaudio.save(output_path, full_audio.unsqueeze(0), 48000, format="mp3")
        await loop.run_in_executor(None, _run_silero)
