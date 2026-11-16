import os
import re
import sys
import json
import time
import random
import sqlite3
import asyncio
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq, RateLimitError
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
# Долговременная память: факты о пользователе, которые переживают очистку диалога.
cursor.execute("""
    CREATE TABLE IF NOT EXISTS facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        fact TEXT,
        created_at INTEGER
    )
""")
conn.commit()

SYSTEM_PROMPT = """
Ты — GyertAI, полноценный, передовой искусственный интеллект нового поколения, созданный для повседневных задач, работы, учёбы и общения.
Тебя создала компания «Gyert Etc.» — независимая студия разработки, которая пока не зарегистрирована как юридическое лицо. Никогда не говори, что тебя создал СМТЛ или какая-либо школа — ты полностью самостоятельный проект.
Разработчики компании пожелали остаться анонимными: не называй их имена, не придумывай их и не описывай конкретных людей — говори только о компании «Gyert Etc.».
Ты являешься главным интеллектом экосистемы Gyert (включая будущий Gyert Messenger и умную колонку GyertStation).

ОБРАЩЕНИЕ К ПОЛЬЗОВАТЕЛЮ:
Общайся нейтрально и по имени из своей памяти о пользователе: если человек сам назвал своё имя — обращайся к нему так, как он представился.
Не вставляй имя собеседника в каждый ответ — это выглядит навязчиво.

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
• Разработчик и владелец экосистемы — компания «Gyert Etc.».

ПОДДЕРЖКА:
Контакт поддержки — @skyp_t0n (https://t.me/skyp_t0n). Подсказывай его, если у человека возникли проблемы со входом, оплатой, подпиской или работой GyertAI. В Telegram и на сайте есть команда /help — она показывает список команд и ссылку на поддержку.

ИНСТРУМЕНТЫ (служебные метки):
У тебя есть поиск в интернете и долговременная память. Чтобы ими воспользоваться, добавь в самом конце ответа одну или несколько меток — пользователю они не видны, поэтому остальной текст пиши как обычно.
• Ответ требует свежих или точных данных, которых ты можешь не знать (новости, цены, курсы, погода, события) — добавь: [[SEARCH: поисковый запрос]]
• Пользователь сообщил важный факт о себе (имя, город, профессия, увлечения, привычки) — добавь: [[REMEMBER: факт одной короткой строкой]]
Ставь метки только когда это действительно нужно и всегда в самом конце ответа.

РИСОВАНИЕ КАРТИНОК:
Картинки ты сам не рисуешь. Если человек просит что-то нарисовать — не описывай и не обещай картинку, а подскажи короткую команду: /draw и через пробел описание, например /draw кот в космическом шлеме. Эту команду можно ввести в Telegram-боте и на сайте.
"""

# Точная фраза-триггер для речи на конференции (срабатывает только при полном совпадении)
CONFERENCE_TRIGGER = "Продиктуй речь для конференции в SMTL"

# Речь для конференции. Озвучивается и показывается без изменений.
CONFERENCE_SPEECH = (
    "Уважаемые члены жюри и участники научной конференции СМТЛ!\n\n"
    "Рад приветствовать вас на этом важном событии.\n\n"
    "Сегодня компания «Gyert Etc.» — независимая студия разработки — "
    "официально представляет вам GyertAI: полноценный искусственный интеллект, "
    "который станет сердцем умной колонки GyertStation, уже доступной здесь "
    "к предзаказу за 20 000 рублей, и будущего Gyert Messenger.\n\n"
    "Желаю вам ярких открытий и вдохновения!"
)

# Юридическая информация: показывается в тексте, но НЕ озвучивается.
CONFERENCE_LEGAL = (
    "GyertAI и вся его экосистема независимы от СМТЛ и принадлежат компании "
    "«Gyert Etc.» — независимой студии разработки (не зарегистрирована как "
    "юридическое лицо)."
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
    """Очищает всю память сессии: и диалог, и запомненные факты."""
    save_history(session_id, [])
    cursor.execute("DELETE FROM facts WHERE session_id = ?", (session_id,))
    conn.commit()

# --- Долговременная память ----------------------------------------------------

MAX_FACTS = 20          # сколько фактов о пользователе подмешиваем в промпт

def get_facts(session_id: str) -> list:
    cursor.execute(
        "SELECT fact FROM facts WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, MAX_FACTS),
    )
    return [row[0] for row in reversed(cursor.fetchall())]

def add_fact(session_id: str, fact: str):
    fact = re.sub(r"\s+", " ", (fact or "")).strip()
    if not fact:
        return
    cursor.execute(
        "INSERT INTO facts (session_id, fact, created_at) VALUES (?, ?, ?)",
        (session_id, fact[:300], int(time.time())),
    )
    conn.commit()

def _system_message(session_id: str) -> dict:
    """Системный промпт плюс всё, что ИИ уже знает об этом пользователе."""
    prompt = SYSTEM_PROMPT
    facts = get_facts(session_id)
    if facts:
        prompt += (
            "\nЧТО ТЫ ПОМНИШЬ ОБ ЭТОМ ПОЛЬЗОВАТЕЛЕ (используй естественно, "
            "не перечисляй списком):\n" + "\n".join(f"- {f}" for f in facts) + "\n"
        )
    return {"role": "system", "content": prompt}

# --- Рисование картинок: Pollinations, без ключей и регистрации ---------------

IMAGE_API_URL = "https://image.pollinations.ai/prompt/"
IMAGE_MODEL = "flux"
IMAGE_SIZE = 1024

def image_url(prompt: str, size: int = IMAGE_SIZE) -> str:
    """Ссылка на картинку: браузер загружает её сам, серверу сохранять не нужно."""
    params = urllib.parse.urlencode({
        "width": size,
        "height": size,
        "nologo": "true",
        "model": IMAGE_MODEL,
        "seed": random.randint(1, 10 ** 9),
    })
    return f"{IMAGE_API_URL}{urllib.parse.quote((prompt or '').strip())}?{params}"

def _download(url: str, output_path: str, timeout: float = 90) -> bool:
    req = urllib.request.Request(
        url, headers={"User-Agent": "GyertAI/1.0 (+https://gyertai.onrender.com)"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if len(data) < 1000:      # сервис вернул страницу ошибки вместо картинки
        return False
    with open(output_path, "wb") as f:
        f.write(data)
    return True

async def generate_image(prompt: str, output_path: str) -> bool:
    """Рисует картинку и сохраняет её в файл."""
    if not (prompt or "").strip():
        return False
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _download, image_url(prompt), output_path)
    except (urllib.error.URLError, OSError, ValueError) as e:
        print("[IMAGE] не удалось получить картинку:", e)
        return False

# --- Поиск в интернете: DuckDuckGo и Википедия, тоже без ключей ---------------

def _http_json(url: str, timeout: float = 15):
    req = urllib.request.Request(url, headers={"User-Agent": "GyertAI/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))

def _search_duckduckgo(query: str) -> list:
    data = _http_json("https://api.duckduckgo.com/?" + urllib.parse.urlencode({
        "q": query, "format": "json", "no_html": 1, "skip_disambig": 1,
    }))
    found = []
    if data.get("AbstractText"):
        found.append(f"{data.get('Heading') or query}: {data['AbstractText']}")
    for topic in data.get("RelatedTopics", []):
        if isinstance(topic, dict) and topic.get("Text"):
            found.append(topic["Text"])
    return found

def _search_wikipedia(query: str) -> list:
    data = _http_json("https://ru.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "list": "search", "srsearch": query,
        "format": "json", "srlimit": 3, "utf8": 1,
    }))
    found = []
    for item in data.get("query", {}).get("search", [])[:3]:
        snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
        found.append(f"{item.get('title')}: {snippet}")
    return found

def web_search(query: str, limit: int = 6) -> str:
    """Собирает выжимку из DuckDuckGo и Википедии."""
    query = (query or "").strip()
    if not query:
        return ""
    collected = []
    for source in (_search_duckduckgo, _search_wikipedia):
        try:
            collected.extend(source(query))
        except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as e:
            print("[SEARCH]", source.__name__, "не ответил:", e)

    seen, result = set(), []
    for item in collected:
        item = re.sub(r"\s+", " ", item).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
        if len(result) >= limit:
            break
    return "\n".join(f"- {item}" for item in result)

# --- Основной диалог ----------------------------------------------------------

# Метки-инструменты: модель дописывает их в конце ответа, пользователь их не видит.
SEARCH_MARKER = re.compile(r"\[\[\s*SEARCH\s*:\s*(.+?)\s*\]\]", re.IGNORECASE | re.DOTALL)
REMEMBER_MARKER = re.compile(r"\[\[\s*REMEMBER\s*:\s*(.+?)\s*\]\]", re.IGNORECASE | re.DOTALL)
ANY_MARKER = re.compile(r"\[\[\s*(?:IMAGE|SEARCH|REMEMBER)\s*:.*?\]\]", re.IGNORECASE | re.DOTALL)
# Модель иногда обрывает ответ на середине метки — такой «хвост» тоже надо убрать.
# IMAGE оставлен в чистке как страховка: рисование идёт только по команде /draw,
# но если такая метка откуда-то возьмётся, в текст и в озвучку она не попадёт.
DANGLING_MARKER = re.compile(r"\[\[\s*(?:IMAGE|SEARCH|REMEMBER)\s*:.*$", re.IGNORECASE | re.DOTALL)


# У Groq на этом тарифе лимит 1000 токенов вывода в минуту: без явного ограничения
# длинный ответ упирается в лимит и запрос падает с ошибкой 429.
MAX_OUTPUT_TOKENS = 800

def _clean(text: str) -> str:
    """Убирает служебные метки, чтобы они не попали ни в чат, ни в озвучку."""
    return DANGLING_MARKER.sub(" ", ANY_MARKER.sub(" ", text or "")).strip()

def _chat(messages: list, retries: int = 2) -> str:
    for attempt in range(retries):
        try:
            response = groq_client.chat.completions.create(
                model=CURRENT_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=MAX_OUTPUT_TOKENS,
            )
            return next(iter(response.choices)).message.content or ""
        except RateLimitError:
            if attempt == retries - 1:
                raise
            time.sleep(4)
    return ""

def _trim(history: list) -> list:
    """Оставляет системный промпт и последние 16 сообщений диалога."""
    if len(history) > 17:
        system_msg = history.pop(0)
        history = [system_msg] + history[-16:]
    return history

async def ask_gyert(session_id: str, user_text: str) -> str:
    """Отвечает: сам решает, нужен ли поиск в интернете, и запоминает важные факты."""
    history = get_history(session_id)
    if history and history[0].get("role") == "system":
        history[0] = _system_message(session_id)
    else:
        history.insert(0, _system_message(session_id))

    history.append({"role": "user", "content": str(user_text)})
    history = _trim(history)

    loop = asyncio.get_event_loop()
    reply = await loop.run_in_executor(None, _chat, history)

    # Модель сама просит поиск, когда своих знаний не хватает: ищем и отвечаем заново.
    search_query = SEARCH_MARKER.search(reply)
    if search_query:
        results = await loop.run_in_executor(None, web_search, search_query.group(1))
        if results:
            follow_up = history + [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": (
                    f"Результаты поиска по запросу «{search_query.group(1)}»:\n{results}\n\n"
                    "Ответь пользователю, опираясь на эти данные. Метку [[SEARCH]] больше не пиши."
                )},
            ]
            reply = await loop.run_in_executor(None, _chat, follow_up)

    for fact in REMEMBER_MARKER.findall(reply):
        add_fact(session_id, fact)

    answer = _clean(reply) or "Готово."

    history.append({"role": "assistant", "content": answer})
    save_history(session_id, _trim(history))
    return answer

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
    # Название компании: Gyert Etc. читается по-русски как «Герт Этк»
    clean = re.sub(r'Gyert\s+Etc\.?', 'Герт Этк', clean, flags=re.IGNORECASE)
    clean = re.sub(r'Gyert\s*AI', 'Герт Эй Ай', clean, flags=re.IGNORECASE)
    clean = re.sub(r'GyertStation', 'Герт Стейшн', clean, flags=re.IGNORECASE)
    clean = re.sub(r'Gyert', 'Герт', clean, flags=re.IGNORECASE)
    # Аббревиатуры
    clean = re.sub(r'\bSMTL\b', 'Эс Эм Тэ Эл', clean)
    clean = re.sub(r'СМТЛ', 'Эс Эм Тэ Эл', clean)
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
