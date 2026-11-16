"""Аккаунты GyertAI: регистрация через Telegram, подписка, промокоды и дневной лимит.

Данные лежат в общей с проектом базе gyert_memory.db, но в отдельных таблицах.
Модуль намеренно не зависит от aiogram и FastAPI: и бот, и сайт используют его
функции напрямую.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")

DB_PATH = "gyert_memory.db"

FREE_DAILY_LIMIT = 20            # бесплатных запросов в день
CODE_TTL = 10 * 60               # сколько живёт 6-значный код подтверждения


def _load_promo_codes() -> dict:
    """Промокоды читаем из .env, чтобы они не лежали в открытом виде в репозитории.

    Формат переменной PROMO_CODES: "КОД_1:дней,КОД_2:дней".
    """
    codes = {}
    for item in (os.environ.get("PROMO_CODES") or "").split(","):
        code, _, days = item.partition(":")
        code = code.strip()
        if not code:
            continue
        try:
            days = int(days.strip())
        except ValueError:
            continue
        if days > 0:
            codes[code.upper()] = days
    return codes


PROMO_CODES = _load_promo_codes()   # промокод -> дней бесплатного доступа
PLANS = {                        # тариф -> (дней подписки, цена в GRAM)
    "week": (7, "1.5"),
    "month": (30, "4"),
}
STARS_PLANS = {                  # тариф -> цена в звёздах Telegram
    "week": 100,
    "month": 250,
}

XROCKET_CURRENCY = os.environ.get("XROCKET_CURRENCY", "GRAM")
XROCKET_INVOICES_URL = os.environ.get(
    "XROCKET_INVOICES_URL", "https://pay.api.xrocket.exchange/api/v1/invoices"
)
XROCKET_API_TOKEN = os.environ.get("XROCKET_API_TOKEN")
XROCKET_WEBHOOK_SECRET = os.environ.get("XROCKET_WEBHOOK_SECRET")
# Основной бот GyertAI: в нём идёт диалог, от него приходит подтверждение оплаты.
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# Отдельный бот, который присылает только коды подтверждения.
VERIFY_BOT_TOKEN = os.environ.get("VERIFY_BOT_TOKEN") or BOT_TOKEN
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

_LOGIN_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")

# timeout=10 — база общая с ai_core, поэтому ждём освобождения блокировки дольше.
conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
conn.row_factory = sqlite3.Row
conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,      -- telegram-юзернейм в нижнем регистре, без @
        chat_id TEXT,                   -- id чата в основном боте GyertAI
        verify_chat_id TEXT,            -- id чата в боте подтверждений (для кодов)
        login TEXT UNIQUE,
        password_hash TEXT,
        salt TEXT,
        subscription_until INTEGER DEFAULT 0,
        promo_used TEXT,
        created_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS login_codes (
        username TEXT PRIMARY KEY,
        code TEXT,
        expires_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS usage (
        identity TEXT,
        day TEXT,
        count INTEGER,
        PRIMARY KEY (identity, day)
    );
    CREATE TABLE IF NOT EXISTS invoices (
        invoice_id TEXT PRIMARY KEY,
        username TEXT,
        plan TEXT,
        paid INTEGER DEFAULT 0,
        created_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS auth_tokens (
        token TEXT PRIMARY KEY,
        username TEXT,
        created_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS webhook_events (
        event_id TEXT PRIMARY KEY,
        received_at INTEGER
    );
""")
# Для баз, созданных до появления бота подтверждений, добавляем колонку на месте.
try:
    conn.execute("ALTER TABLE users ADD COLUMN verify_chat_id TEXT")
except sqlite3.OperationalError:
    pass
conn.commit()


def normalize_username(username: str) -> str:
    return (username or "").strip().lstrip("@").lower()


def _now() -> int:
    return int(time.time())


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120000).hex()


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M")


# --- Telegram -----------------------------------------------------------------

def link_telegram(username: str, chat_id: str):
    """Запоминает, какому юзернейму принадлежит чат: по этому адресу уходит код."""
    username = normalize_username(username)
    if not username:
        return
    conn.execute(
        "INSERT INTO users (username, chat_id, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT(username) DO UPDATE SET chat_id=excluded.chat_id",
        (username, str(chat_id), _now()),
    )
    conn.commit()


def send_telegram_message(chat_id: str, text: str, token: str = None) -> bool:
    token = token or BOT_TOKEN
    if not token or not chat_id:
        return False
    payload = json.dumps({"chat_id": str(chat_id), "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15):
            return True
    except (urllib.error.URLError, OSError):
        return False


def chat_id_of(username: str):
    row = conn.execute(
        "SELECT chat_id FROM users WHERE username = ?", (normalize_username(username),)
    ).fetchone()
    return row["chat_id"] if row and row["chat_id"] else None


def link_verify_chat(username: str, chat_id: str):
    """Запоминает чат в боте подтверждений: туда уходит код для входа на сайте."""
    username = normalize_username(username)
    if not username:
        return
    conn.execute(
        "INSERT INTO users (username, verify_chat_id, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT(username) DO UPDATE SET verify_chat_id=excluded.verify_chat_id",
        (username, str(chat_id), _now()),
    )
    conn.commit()


def verify_chat_id_of(username: str):
    row = conn.execute(
        "SELECT verify_chat_id FROM users WHERE username = ?", (normalize_username(username),)
    ).fetchone()
    return row["verify_chat_id"] if row and row["verify_chat_id"] else None


def telegram_user_from_init_data(init_data: str):
    """Проверяет подпись Telegram WebApp и возвращает данные пользователя.

    Telegram подписывает initData ключом, производным от токена бота: если подпись
    сходится, данные не подделаны и мини-приложению можно доверять.
    """
    if not init_data or not BOT_TOKEN:
        return None
    try:
        pairs = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    except ValueError:
        return None
    received_hash = pairs.pop("hash", "")
    if not received_hash:
        return None

    check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        return None
    try:
        return json.loads(pairs.get("user") or "{}") or None
    except ValueError:
        return None


# --- Регистрация и вход -------------------------------------------------------

def send_login_code(username: str):
    """Создаёт 6-значный код и отправляет его через бота подтверждений."""
    username = normalize_username(username)
    if not username:
        return False, "Укажите юзернейм из Telegram (например, @elisey)."

    chat_id = verify_chat_id_of(username)
    if not chat_id:
        return False, ("Не нашли этот юзернейм. Напишите любое сообщение нашему боту "
                       "подтверждений в Telegram — и повторите попытку.")

    code = f"{secrets.randbelow(1000000):06d}"
    conn.execute(
        "INSERT INTO login_codes (username, code, expires_at) VALUES (?, ?, ?) "
        "ON CONFLICT(username) DO UPDATE SET code=excluded.code, expires_at=excluded.expires_at",
        (username, code, _now() + CODE_TTL),
    )
    conn.commit()

    if not send_telegram_message(
        chat_id,
        f"🔐 Код подтверждения GyertAI: <b>{code}</b>\nОн действует 10 минут.",
        token=VERIFY_BOT_TOKEN,
    ):
        return False, "Не удалось отправить код в Telegram. Проверьте, что бот не заблокирован."
    return True, "Код отправлен в Telegram."


def check_login_code(username: str, code: str) -> bool:
    row = conn.execute(
        "SELECT code, expires_at FROM login_codes WHERE username = ?",
        (normalize_username(username),),
    ).fetchone()
    if not row or row["expires_at"] < _now():
        return False
    return hmac.compare_digest(str(row["code"]), (code or "").strip())


def login_taken(login: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM users WHERE login = ?", ((login or "").strip(),)
    ).fetchone())


def create_account(username: str, login: str, password: str):
    """Создаёт аккаунт: логин с паролем для юзернейма из Telegram."""
    username = normalize_username(username)
    login = (login or "").strip()

    if not _LOGIN_RE.match(login):
        return False, "Логин: 3–32 символа, только латиница, цифры и подчёркивание."
    if len(password or "") < 6:
        return False, "Пароль должен быть не короче 6 символов."
    if login_taken(login):
        return False, "Такой логин уже занят."
    if not conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        return False, "Сначала напишите нашему боту в Telegram и повторите попытку."
    if has_account(username):
        return False, "У этого Telegram-аккаунта уже есть аккаунт GyertAI."

    salt = secrets.token_hex(16)
    conn.execute(
        "UPDATE users SET login = ?, password_hash = ?, salt = ? WHERE username = ?",
        (login, _hash_password(password, salt), salt, username),
    )
    conn.execute("DELETE FROM login_codes WHERE username = ?", (username,))
    conn.commit()
    return True, "Аккаунт создан."


def register(username: str, code: str, login: str, password: str):
    """Регистрация с сайта: сначала проверяется 6-значный код из Telegram."""
    if not check_login_code(username, code):
        return False, "Неверный или просроченный код подтверждения."
    return create_account(username, login, password)


def authenticate(login: str, password: str):
    row = conn.execute(
        "SELECT username, password_hash, salt FROM users WHERE login = ?",
        ((login or "").strip(),),
    ).fetchone()
    if not row or not row["password_hash"]:
        return None
    if hmac.compare_digest(row["password_hash"], _hash_password(password or "", row["salt"])):
        return row["username"]
    return None


def issue_token(username: str) -> str:
    token = secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO auth_tokens (token, username, created_at) VALUES (?, ?, ?)",
        (token, username, _now()),
    )
    conn.commit()
    return token


def username_by_token(token: str):
    if not token:
        return None
    row = conn.execute(
        "SELECT username FROM auth_tokens WHERE token = ?", (token,)
    ).fetchone()
    return row["username"] if row else None


def drop_token(token: str):
    if token:
        conn.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
        conn.commit()


# --- Состояние аккаунта и лимиты ---------------------------------------------

def has_account(username: str) -> bool:
    row = conn.execute(
        "SELECT login FROM users WHERE username = ?", (normalize_username(username),)
    ).fetchone()
    return bool(row and row["login"])


def subscription_until(username: str) -> int:
    row = conn.execute(
        "SELECT subscription_until FROM users WHERE username = ?",
        (normalize_username(username),),
    ).fetchone()
    return row["subscription_until"] if row else 0


def is_subscribed(username: str) -> bool:
    return subscription_until(username) > _now()


def grant_subscription(username: str, days: int) -> int:
    """Продлевает подписку и возвращает новую дату окончания."""
    username = normalize_username(username)
    base = max(subscription_until(username), _now())
    until = int(base + timedelta(days=days).total_seconds())
    conn.execute("UPDATE users SET subscription_until = ? WHERE username = ?", (until, username))
    conn.commit()
    return until


def redeem_promo(username: str, promo: str):
    username = normalize_username(username)
    promo = (promo or "").strip().upper()
    row = conn.execute(
        "SELECT promo_used FROM users WHERE username = ?", (username,)
    ).fetchone()
    if not row:
        return False, "Аккаунт не найден."
    if not has_account(username):
        return False, "Сначала создайте аккаунт в разделе «Аккаунт»."
    if row["promo_used"]:
        return False, f"Промокод {row['promo_used']} уже активирован на этом аккаунте."
    if promo not in PROMO_CODES:
        return False, "Такого промокода нет."

    days = PROMO_CODES[promo]
    until = grant_subscription(username, days)
    conn.execute("UPDATE users SET promo_used = ? WHERE username = ?", (promo, username))
    conn.commit()
    return True, f"Промокод активирован: доступ открыт до {_iso(until)}."


def resolve_identity(username, fallback_id: str) -> str:
    """Ключ, по которому считается дневной лимит: аккаунт, если он есть, иначе гость."""
    username = normalize_username(username or "")
    if username and has_account(username):
        return f"user:{username}"
    return f"guest:{fallback_id}"


def consume_request(identity: str):
    """Списывает один запрос. Возвращает (разрешено, осталось)."""
    if identity.startswith("user:") and is_subscribed(identity.split(":", 1)[1]):
        return True, -1

    day = _today()
    row = conn.execute(
        "SELECT count FROM usage WHERE identity = ? AND day = ?", (identity, day)
    ).fetchone()
    used = row["count"] if row else 0
    if used >= FREE_DAILY_LIMIT:
        return False, 0

    conn.execute(
        "INSERT INTO usage (identity, day, count) VALUES (?, ?, 1) "
        "ON CONFLICT(identity, day) DO UPDATE SET count = count + 1",
        (identity, day),
    )
    conn.commit()
    return True, FREE_DAILY_LIMIT - used - 1


def account_state(username: str):
    """Краткая карточка аккаунта для бота и сайта."""
    username = normalize_username(username)
    row = conn.execute(
        "SELECT login, subscription_until, promo_used FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not row:
        return None
    until = row["subscription_until"] or 0
    return {
        "username": username,
        "login": row["login"],
        "subscribed": until > _now(),
        "until": _iso(until) if until > _now() else None,
        "promo_used": row["promo_used"],
    }


# --- Оплата через xRocket ------------------------------------------------------

def create_invoice(username: str, plan: str, base_url: str = ""):
    """Создаёт счёт в xRocket и возвращает ссылку на оплату."""
    username = normalize_username(username)
    if plan not in PLANS:
        return False, "Неизвестный тариф."
    if not XROCKET_API_TOKEN:
        return False, "Оплата временно недоступна: не настроен ключ xRocket."
    if not has_account(username):
        return False, "Сначала создайте аккаунт."

    days, price = PLANS[plan]
    base = (base_url or PUBLIC_BASE_URL).rstrip("/")
    client_invoice_id = f"gyert-{plan}-{username}-{_now()}"

    payload = {
        "priceAmount": price,
        "priceCurrency": XROCKET_CURRENCY,
        "description": f"GyertAI — подписка на {'неделю' if plan == 'week' else 'месяц'}",
        "clientInvoiceId": client_invoice_id,
        "expiresIn": 24 * 60 * 60 * 1000,
        "isFeePaidByUser": True,
        "customer": {"telegramUsername": username},
        "payload": {"username": username, "plan": plan},
    }
    if base:
        payload["callback"] = {"callbackUrl": f"{base}/api/xrocket/webhook"}

    req = urllib.request.Request(
        XROCKET_INVOICES_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {XROCKET_API_TOKEN}",
            "Content-Type": "application/json",
            # Cloudflare перед API отклоняет запросы со стандартным
            # User-Agent Python (ошибка 1010), поэтому представляемся как программа.
            "User-Agent": "GyertAI/1.0 (+https://gyertai.onrender.com)",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return False, f"xRocket отклонил запрос ({e.code}): {e.read().decode(errors='ignore')[:200]}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, f"Не удалось связаться с xRocket: {e}"

    link = (data.get("links") or {}).get("telegramBotLink")
    invoice_id = str(data.get("id") or client_invoice_id)
    conn.execute(
        "INSERT INTO invoices (invoice_id, username, plan, created_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(invoice_id) DO NOTHING",
        (client_invoice_id, username, plan, _now()),
    )
    conn.execute(
        "INSERT INTO invoices (invoice_id, username, plan, created_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(invoice_id) DO NOTHING",
        (invoice_id, username, plan, _now()),
    )
    conn.commit()

    if not link:
        return False, "xRocket не вернул ссылку на оплату."
    return True, link


# --- Оплата звёздами Telegram -------------------------------------------------

TELEGRAM_API_URL = "https://api.telegram.org"


def _telegram_api(method: str, payload: dict, token: str = None):
    """Вызывает метод Bot API и возвращает (ok, результат или текст ошибки)."""
    token = token or BOT_TOKEN
    if not token:
        return False, "Не настроен токен бота."
    req = urllib.request.Request(
        f"{TELEGRAM_API_URL}/bot{token}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return False, f"Telegram отклонил запрос ({e.code}): {e.read().decode(errors='ignore')[:200]}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, f"Не удалось связаться с Telegram: {e}"
    if not data.get("ok"):
        return False, data.get("description") or "Telegram вернул ошибку."
    return True, data.get("result")


def stars_payload(plan: str, username: str) -> str:
    """Метка платежа: по ней после оплаты восстанавливается тариф и аккаунт."""
    return f"stars:{plan}:{normalize_username(username)}:{_now()}"


def create_stars_invoice_link(plan: str, username: str):
    """Создаёт ссылку на оплату подписки звёздами Telegram (валюта XTR)."""
    username = normalize_username(username)
    if plan not in STARS_PLANS:
        return False, "Неизвестный тариф."
    if not has_account(username):
        return False, "Сначала создайте аккаунт."
    if not BOT_TOKEN:
        return False, "Оплата временно недоступна: не настроен токен бота."

    title = f"GyertAI — подписка на {'неделю' if plan == 'week' else 'месяц'}"
    ok, result = _telegram_api("createInvoiceLink", {
        "title": title,
        "description": f"Подписка GyertAI на {PLANS[plan][0]} дней без дневного лимита.",
        "payload": stars_payload(plan, username),
        "currency": "XTR",
        "prices": [{"label": title, "amount": STARS_PLANS[plan]}],
    })
    if not ok:
        return False, result
    if not isinstance(result, str):
        return False, "Telegram не вернул ссылку на оплату."
    return True, result


def apply_stars_payment(payload: str):
    """Начисляет подписку после успешной оплаты звёздами. Возвращает (ok, текст)."""
    parts = (payload or "").split(":")
    if len(parts) < 3 or parts[0] != "stars":
        return False, "Неизвестный платёж."
    plan = parts[1]
    username = normalize_username(parts[2])
    if plan not in PLANS:
        return False, "Неизвестный тариф."
    if not has_account(username):
        return False, "Аккаунт не найден."
    until = grant_subscription(username, PLANS[plan][0])
    return True, f"{PLANS[plan][0]} дней подписки до {_iso(until)}"


def verify_webhook(raw_body: bytes, signature: str, version: str, timestamp: str) -> bool:
    """Проверяет подпись вебхука: HMAC-SHA256 по строке "{timestamp}.{тело запроса}"."""
    if not XROCKET_WEBHOOK_SECRET or not signature or not timestamp:
        return False
    if version != "v1":
        return False
    try:
        if abs(int(time.time() * 1000) - int(timestamp)) > 5 * 60 * 1000:
            return False
    except ValueError:
        return False

    expected = hmac.new(
        XROCKET_WEBHOOK_SECRET.encode(),
        f"{timestamp}.".encode() + raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def apply_webhook(raw_body: bytes, headers: dict):
    """Обрабатывает событие об оплате. Возвращает (http-код, пояснение)."""
    if not verify_webhook(
        raw_body,
        headers.get("signature", ""),
        headers.get("signature-version", ""),
        headers.get("signature-timestamp", ""),
    ):
        return 401, "invalid signature"

    try:
        event = json.loads(raw_body.decode())
    except (ValueError, UnicodeDecodeError):
        return 400, "invalid json"

    event_id = str(event.get("id") or "")
    if event_id:
        if conn.execute("SELECT 1 FROM webhook_events WHERE event_id = ?", (event_id,)).fetchone():
            return 200, "duplicate"
        conn.execute(
            "INSERT INTO webhook_events (event_id, received_at) VALUES (?, ?)",
            (event_id, _now()),
        )
        conn.commit()

    if event.get("type") != "invoice":
        return 200, "ignored"

    data = (event.get("data") or {})
    if data.get("event") != "invoice_status_changed":
        return 200, "ignored"

    invoice = data.get("invoice") or {}
    if invoice.get("status") != "paid":
        return 200, "not paid"

    payload = (invoice.get("callback") or {}).get("payload") or {}
    username = normalize_username(payload.get("username") or "")
    plan = payload.get("plan") or ""

    # Если в payload ничего не пришло, восстанавливаем тариф по номеру счёта.
    if plan not in PLANS or not username:
        row = conn.execute(
            "SELECT username, plan FROM invoices WHERE invoice_id = ?",
            (str(invoice.get("clientInvoiceId") or invoice.get("id") or ""),),
        ).fetchone()
        if row:
            username = username or row["username"]
            plan = plan or row["plan"]

    if plan not in PLANS or not username:
        return 200, "unknown invoice"

    row = conn.execute(
        "SELECT paid FROM invoices WHERE invoice_id = ?",
        (str(invoice.get("clientInvoiceId") or invoice.get("id") or ""),),
    ).fetchone()
    if row and row["paid"]:
        return 200, "already credited"

    days = PLANS[plan][0]
    until = grant_subscription(username, days)
    conn.execute(
        "UPDATE invoices SET paid = 1 WHERE invoice_id IN (?, ?)",
        (str(invoice.get("id") or ""), str(invoice.get("clientInvoiceId") or "")),
    )
    conn.commit()

    chat_id = chat_id_of(username)
    if chat_id:
        send_telegram_message(
            chat_id,
            f"✅ Оплата получена! Подписка GyertAI активна до {_iso(until)}.",
        )
    return 200, f"credited {days} days to {username}"
