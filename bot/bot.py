"""
May Flowers — бот магазина: клиенты (мини-апка), студии-партнёры и админы.

Что делает:
  * принимает заказы с сайта (POST /api/orders) и раздаёт их студиям в Telegram;
  * студия жмёт «Принять» или «Не можем»; если не ответила за ACCEPT_TIMEOUT секунд,
    заявка уходит следующей студии;
  * после принятия студия видит контакты получателя и ведёт заказ по статусам:
    фото готового букета -> передан курьеру -> доставлен;
  * админы (вы) получают каждый заказ и каждое изменение статуса.

Зависимостей нет: только стандартная библиотека Python 3.9+.
Запуск:  BOT_TOKEN=... ADMIN_IDS=123456 INTAKE_KEY=секрет python3 bot.py
"""

import hashlib
import hmac
import html
import json
import logging
import os
import secrets
import shutil
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date as Date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------- настройки

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x]
INTAKE_KEY = os.environ.get("INTAKE_KEY", "")
PORT = int(os.environ.get("PORT", "8080"))
BIND_HOST = os.environ.get("BIND_HOST", "0.0.0.0")  # на сервере за Caddy: 127.0.0.1
ACCEPT_TIMEOUT = int(os.environ.get("ACCEPT_TIMEOUT", "600"))  # секунд на «Принять»
PAYOUT_SHARE = float(os.environ.get("PAYOUT_SHARE", "0.7"))  # доля студии, если сайт не прислал сумму
DB_PATH = os.environ.get("DB_PATH", "mayflowers.db")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
API_BASE = os.environ.get("TELEGRAM_API", "https://api.telegram.org")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")  # адрес сайта (мини-апки), https://...
TZ_OFFSET = float(os.environ.get("TZ_OFFSET", "4"))  # часовой пояс для напоминаний, Ереван = +4
REMIND_HOUR = int(os.environ.get("REMIND_HOUR", "11"))  # во сколько слать напоминания
INIT_MAX_AGE = 86400  # подпись мини-апки действительна сутки
MANAGER_CONTACT = os.environ.get("MANAGER_CONTACT", "")  # например @mayflowers_manager или +374 ...
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")  # ключ Claude API: включает умного помощника
AI_MODEL = os.environ.get("AI_MODEL", "claude-haiku-5-5")
AI_USER_DAILY = int(os.environ.get("AI_USER_DAILY", "40"))     # ответов ИИ одному клиенту в сутки
AI_DAILY_CAP = int(os.environ.get("AI_DAILY_CAP", "3000"))     # всего ответов ИИ в сутки, защита баланса
HUMAN_HOURS = float(os.environ.get("HUMAN_HOURS", "6"))        # сколько часов диалог ведёт человек после «Позвать человека»
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "cards")  # кеш записей для открыток
CARD_REPLY_MAX = 6_000_000  # байт на голосовой ответ из браузера
CARD_UPLOAD_MAX = 40_000_000  # байт на поздравление, записанное прямо на сайте (до 60 с видео)
CATALOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mayflowers")

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
OCCASIONS = {"bd": "День рождения", "love": "Любовь", "thanks": "Спасибо",
             "mom": "Маме", "sorry": "Извинение"}

STATUS_TEXT = {
    "new": "Новый",
    "offered": "Ждёт ответа студии",
    "accepted": "Принят студией, собирают",
    "built": "Собран, фото отправлено",
    "courier": "У курьера",
    "delivered": "Доставлен",
    "unassigned": "Никто не принял",
    "cancelled": "Отменён",
}

# ---------------------------------------------------------------- Telegram API


def tg(method, **params):
    """Вызов Bot API. Возвращает result или None при ошибке."""
    url = f"{API_BASE}/bot{BOT_TOKEN}/{method}"
    data = json.dumps({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    timeout = params.get("timeout", 0) + 15
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = {"ok": False, "description": str(e)}
    except Exception as e:  # сеть, таймаут
        log.warning("telegram %s failed: %s", method, e)
        return None
    if not body.get("ok"):
        desc = body.get("description", "")
        if "message is not modified" not in desc:
            log.warning("telegram %s error: %s", method, desc)
        return None
    return body.get("result")


def send(chat_id, text, buttons=None):
    return tg("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
              disable_web_page_preview=True, reply_markup=kb(buttons))


def edit(chat_id, message_id, text, buttons=None):
    return tg("editMessageText", chat_id=chat_id, message_id=message_id, text=text,
              parse_mode="HTML", disable_web_page_preview=True, reply_markup=kb(buttons))


def kb(buttons):
    if buttons is None:
        return None
    def btn(t, d):
        if d.startswith("webapp:"):
            return {"text": t, "web_app": {"url": d[7:]}}
        if d.startswith("url:"):
            return {"text": t, "url": d[4:]}
        return {"text": t, "callback_data": d}
    return {"inline_keyboard": [[btn(t, d) for t, d in row] for row in buttons]}


def notify_admins(text, photo=None, buttons=None):
    for a in ADMIN_IDS:
        if photo:
            tg("sendPhoto", chat_id=a, photo=photo, caption=text[:1024], parse_mode="HTML", reply_markup=kb(buttons))
        else:
            send(a, text, buttons)


def tg_upload(method, field, filename, data, content_type, **params):
    """Вызов Bot API с загрузкой файла (multipart/form-data)."""
    boundary = "----mf" + secrets.token_hex(12)
    parts = []
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
                 f'Content-Type: {content_type}\r\n\r\n'.encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(f"{API_BASE}/bot{BOT_TOKEN}/{method}", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = {"ok": False, "description": str(e)}
    except Exception as e:
        log.warning("telegram %s upload failed: %s", method, e)
        return None
    if not body.get("ok"):
        log.warning("telegram %s upload error: %s", method, body.get("description", ""))
        return None
    return body.get("result")


# ---------------------------------------------------------------- база

DB_LOCK = threading.RLock()
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row


def q(sql, args=(), one=False):
    with DB_LOCK:
        cur = db.execute(sql, args)
        db.commit()
        rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def init_db():
    with DB_LOCK:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS studios(
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER UNIQUE, name TEXT,
            active INTEGER DEFAULT 1, priority INTEGER DEFAULT 100,
            last_assigned REAL DEFAULT 0, joined_at REAL);
        CREATE TABLE IF NOT EXISTS invites(code TEXT PRIMARY KEY, name TEXT, created REAL, used INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS orders(
            id TEXT PRIMARY KEY, payload TEXT, status TEXT, studio_id INTEGER,
            created REAL, photo TEXT, msg_id INTEGER);
        CREATE TABLE IF NOT EXISTS offers(
            order_id TEXT, studio_id INTEGER, status TEXT, offered REAL, msg_id INTEGER,
            PRIMARY KEY(order_id, studio_id));
        CREATE TABLE IF NOT EXISTS waiting_photo(chat_id INTEGER PRIMARY KEY, order_id TEXT);
        CREATE TABLE IF NOT EXISTS cards(
            token TEXT PRIMARY KEY, order_id TEXT UNIQUE, rec_code TEXT UNIQUE, client_chat INTEGER,
            kind TEXT, file_id TEXT, created REAL, recorded REAL, opened REAL, replies INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS waiting_card(chat_id INTEGER PRIMARY KEY, token TEXT);
        CREATE TABLE IF NOT EXISTS ai_msgs(id INTEGER PRIMARY KEY AUTOINCREMENT, chat INTEGER, role TEXT, content TEXT, ts REAL);
        CREATE TABLE IF NOT EXISTS ai_usage(day TEXT, chat INTEGER, n INTEGER DEFAULT 0, PRIMARY KEY(day, chat));
        CREATE TABLE IF NOT EXISTS human_mode(chat INTEGER PRIMARY KEY, until REAL);
        CREATE TABLE IF NOT EXISTS rem_links(code TEXT PRIMARY KEY, order_id TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS vip_requests(
            id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT, client_chat INTEGER, created REAL);
        CREATE TABLE IF NOT EXISTS reminders(
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, order_id TEXT, target TEXT,
            label TEXT, lang TEXT, sent7 INTEGER DEFAULT 0, sent1 INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS order_codes(order_id TEXT PRIMARY KEY, code TEXT);
        """)
        cols = [r[1] for r in db.execute("PRAGMA table_info(orders)")]
        if "client_chat" not in cols:
            db.execute("ALTER TABLE orders ADD COLUMN client_chat INTEGER")
        db.commit()


# ---------------------------------------------------------------- тексты заявки

def esc(s):
    return html.escape(str(s or ""))


def money(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "—"
    return f"${x:,.0f}".replace(",", " ")


def when_text(d):
    date = d.get("date", "")
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        date = f"{dt.day} {MONTHS[dt.month - 1]}"
    except ValueError:
        pass
    win = d.get("window") or ""
    if win == "asap":
        win = "как можно скорее (≈60 мин)"
    elif win == "exact":
        win = "ровно к " + (d.get("exact_time") or "?")
    return f"{date}, {win}".strip(", ")


def payout(o):
    if o.get("payout_usd") is not None:
        return o["payout_usd"]
    goods = sum(float(i.get("price_usd", 0)) * int(i.get("qty", 1)) for i in o.get("items", []))
    return round(goods * PAYOUT_SHARE)


def order_text(o, full=False, status=None, studio_name=None):
    """full=False: то, что студия видит до принятия (без телефонов)."""
    lines = [f"🌸 <b>Заявка {esc(o['id'])}</b>" + (" · <i>ТЕСТ</i>" if o.get("test") else "")]
    if status:
        lines.append(f"Статус: <b>{esc(STATUS_TEXT.get(status, status))}</b>"
                     + (f" · {esc(studio_name)}" if studio_name else ""))
    lines.append("")
    for i in o.get("items", []):
        lines.append(f"💐 <b>{esc(i.get('name'))}</b> × {int(i.get('qty', 1))}")
        if i.get("composition"):
            lines.append(f"     {esc(i['composition'])}")
    w = o.get("wrapping") or {}
    wrap = ", ".join(x for x in [w.get("paper"), w.get("ribbon")] if x)
    lines.append(f"🎀 Оформление: {esc(wrap or 'фирменное May Flowers')}")
    c = o.get("card") or {}
    if c.get("type") == "media":
        lines.append("🎙 Открытка: аудио/видео-поздравление. QR-код пришлю после принятия заказа: "
                     "распечатайте и вложите в букет")
    elif c.get("text"):
        lines.append(f"💌 Открытка: «{esc(c['text'])}»")
    else:
        lines.append("💌 Открытка: без открытки")
    if (o.get("sender") or {}).get("anonymous"):
        lines.append("🤫 Анонимно: не подписывать от кого")
    if o.get("occasion"):
        lines.append(f"🎉 Повод: {esc(OCCASIONS.get(o['occasion'], o['occasion']))}")
    if o.get("kindness"):
        lines.append("🤍 <b>БУКЕТ В ДОБРЫЕ РУКИ</b>: подарить случайному прохожему на улице и снять видео вручения")
    if o.get("comment"):
        lines.append(f"📝 Комментарий: {esc(o['comment'])}")
    lines.append("")
    lines.append(f"🕒 Когда: <b>{esc(when_text(o.get('delivery') or {}))}</b>")
    r = o.get("recipient") or {}
    lines.append(f"📍 Адрес: {esc(r.get('address'))}")
    if full:
        lines.append(f"👤 Получатель: {esc(r.get('name'))}, <code>{esc(r.get('phone'))}</code>")
    lines.append("")
    lines.append(f"💰 Выплата студии: <b>{money(payout(o))}</b>")
    if not full and status in (None, "offered"):
        lines.append(f"⏳ Ответьте в течение {ACCEPT_TIMEOUT // 60} мин, иначе заявка уйдёт другой студии.")
    return "\n".join(lines)


def admin_text(o, status, studio_name=None):
    s = o.get("sender") or {}
    pay = o.get("payment") or {}
    extra = [
        "",
        f"🙋 Заказчик: {esc(s.get('name'))}, <code>{esc(s.get('phone'))}</code>"
        + (f" · Telegram @{esc(o['tg_username'])}" if o.get("tg_username") else ""),
        f"💳 Оплата: {esc(pay.get('method') or '—')} · {esc(pay.get('status') or '—')} · итого {money(o.get('total_usd'))}",
    ]
    return order_text(o, full=True, status=status, studio_name=studio_name) + "\n" + "\n".join(extra)


def studio_buttons(order_id, status):
    if status == "accepted":
        return [[("📸 Букет готов — отправить фото", f"photo:{order_id}")]]
    if status == "built":
        return [[("🚗 Передан курьеру", f"st:{order_id}:courier")]]
    if status == "courier":
        return [[("✅ Доставлен", f"st:{order_id}:delivered")]]
    return []


# ---------------------------------------------------------------- клиенты (мини-апка)

CLIENT = {
    "ru": {
        "hello": "Привет! Это May Flowers 🌸 Доставка цветов и не только от Маиса Варданяна.\n\nНажмите «Открыть магазин», выберите букет и оформите заказ. Здесь же я пришлю фото вашего букета перед доставкой.",
        "open": "🌸 Открыть магазин",
        "soon": "Магазин скоро откроется.",
        "received": "Заказ {id} принят ✅\nФлорист скоро возьмётся за ваш букет. Напишу, как только начнём.",
        "accepted": "Начали собирать ваш букет по заказу {id} 💐",
        "built": "Ваш букет готов! Вот он 👇\nЗаказ {id}, скоро передадим курьеру.",
        "courier": "Курьер уже везёт букет по заказу {id} 🚗",
        "delivered": "Букет по заказу {id} доставлен 🌸 Спасибо, что дарите добро!",
        "cancelled": "Заказ {id} отменён. Менеджер свяжется с вами.",
        "none": "У вас пока нет заказов.",
        "r7": "Через 3 дня, {date}, — {label}. Год назад в этот день вы заказывали букет «{bouquet}» {who}. Подобрать букет заранее?",
        "r1": "Завтра, {date}, — {label}. Ещё успеем собрать и доставить букет {who} 🌸",
        "same": "🔁 Повторить тот же букет",
        "rem_on": "Готово 🔔 Напомню о дне «{label}» за 3 дня и накануне, каждый год.",
        "again": "💐 Выбрать букет",
    },
    "en": {
        "hello": "Hi! This is May Flowers 🌸 Flowers and more, delivered by Mais Vardanyan.\n\nTap “Open shop”, pick a bouquet and place an order. I will send you a photo of your bouquet here before delivery.",
        "open": "🌸 Open shop",
        "soon": "The shop opens soon.",
        "received": "Order {id} received ✅\nA florist will pick up your bouquet shortly. I will write as soon as we start.",
        "accepted": "We have started your bouquet for order {id} 💐",
        "built": "Your bouquet is ready! Here it is 👇\nOrder {id}, handing it to the courier soon.",
        "courier": "The courier is on the way with order {id} 🚗",
        "delivered": "Order {id} delivered 🌸 Thank you for giving kindness!",
        "cancelled": "Order {id} was cancelled. A manager will contact you.",
        "none": "You have no orders yet.",
        "r7": "In 3 days, {date}: {label}. A year ago you ordered the “{bouquet}” bouquet for {who} on this day. Pick a bouquet in advance?",
        "r1": "Tomorrow, {date}: {label}. There is still time to build and deliver flowers for {who} 🌸",
        "same": "🔁 Same bouquet again",
        "rem_on": "Done 🔔 I will remind you about “{label}” 3 days before and the day before, every year.",
        "again": "💐 Pick a bouquet",
    },
    "hy": {
        "hello": "Բարև։ Սա May Flowers-ն է 🌸 Ծաղիկների և ոչ միայն առաքում Մաիս Վարդանյանից։\n\nՍեղմեք «Բացել խանութը», ընտրեք ծաղկեփունջ և պատվիրեք։ Այստեղ կուղարկեմ ձեր ծաղկեփնջի լուսանկարը առաքումից առաջ։",
        "open": "🌸 Բացել խանութը",
        "soon": "Խանութը շուտով կբացվի։",
        "received": "Պատվեր {id}-ն ընդունված է ✅\nԾաղկավաճառը շուտով կսկսի ձեր ծաղկեփունջը։ Կգրեմ, հենց սկսենք։",
        "accepted": "Սկսեցինք հավաքել ձեր ծաղկեփունջը, պատվեր {id} 💐",
        "built": "Ձեր ծաղկեփունջը պատրաստ է։ Ահա այն 👇\nՊատվեր {id}",
        "courier": "Առաքիչը ճանապարհին է, պատվեր {id} 🚗",
        "delivered": "Պատվեր {id}-ն առաքված է 🌸 Շնորհակալություն բարության համար։",
        "cancelled": "Պատվեր {id}-ն չեղարկված է։ Մենեջերը կկապվի ձեզ հետ։",
        "none": "Դեռ պատվերներ չունեք։",
        "r7": "3 օրից՝ {date}, {label}։ Անցյալ տարի այս օրը դուք պատվիրել էիք «{bouquet}» ծաղկեփունջը {who}-ի համար։ Ընտրե՞նք ծաղկեփունջ նախապես։",
        "r1": "Վաղը՝ {date}, {label}։ Դեռ կհասցնենք հավաքել և առաքել ծաղկեփունջը {who}-ի համար 🌸",
        "same": "🔁 Կրկնել նույն ծաղկեփունջը",
        "rem_on": "Պատրաստ է 🔔 Կհիշեցնեմ «{label}» օրվա մասին 3 օր առաջ և նախորդ օրը, ամեն տարի։",
        "again": "💐 Ընտրել ծաղկեփունջ",
    },
}
OCC_LABEL = {
    "ru": {"bd": "день рождения", "love": "важный день", "thanks": "повод сказать спасибо",
           "mom": "праздник", "sorry": "особый день"},
    "en": {"bd": "birthday", "love": "special day", "thanks": "thank-you day",
           "mom": "celebration", "sorry": "special day"},
    "hy": {"bd": "ծննդյան օր", "love": "կարևոր օր", "thanks": "շնորհակալության առիթ",
           "mom": "տոն", "sorry": "հատուկ օր"},
}


def lang_of(o):
    lg = (o.get("lang") or "ru")[:2]
    return lg if lg in CLIENT else "ru"


def ct(o, key, **kw):
    return CLIENT[lang_of(o)][key].format(id=o.get("id", ""), **kw)


def shop_button(o=None, key="open"):
    if not WEBAPP_URL:
        return None
    return [[(CLIENT[lang_of(o or {})][key], "webapp:" + WEBAPP_URL)]]


def notify_client(order_id, key, photo=None):
    row, o = get_order(order_id)
    if not row or not row["client_chat"]:
        return
    if photo:
        tg("sendPhoto", chat_id=row["client_chat"], photo=photo, caption=ct(o, key))
    else:
        send(row["client_chat"], esc(ct(o, key)))


def verify_init_data(init_data):
    """Проверка подписи Telegram Mini App. Возвращает пользователя или None."""
    try:
        pairs = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    got = pairs.pop("hash", None)
    if not got:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, got):
        return None
    try:
        if time.time() - int(pairs.get("auth_date", "0")) > INIT_MAX_AGE:
            return None
        return json.loads(pairs.get("user", "{}"))
    except (ValueError, TypeError):
        return None


def next_occurrence(iso, today):
    """Ближайшая будущая годовщина даты (без учёта самой даты заказа)."""
    try:
        d = datetime.strptime(iso, "%Y-%m-%d").date()
    except ValueError:
        return None
    year = max(today.year, d.year + 1)
    for y in (year, year + 1):
        try:
            cand = d.replace(year=y)
        except ValueError:  # 29 февраля
            cand = Date(y, 2, 28)
        if cand > today:
            return cand
    return None


def add_reminder(o, chat_id):
    today = local_now().date()
    target = next_occurrence((o.get("delivery") or {}).get("date", ""), today)
    if not target:
        return
    who = (o.get("recipient") or {}).get("name") or "❤"
    lg = lang_of(o)
    label = OCC_LABEL[lg].get(o.get("occasion") or "bd", OCC_LABEL[lg]["bd"]) + " — " + who
    q("INSERT INTO reminders(chat_id,order_id,target,label,lang) VALUES(?,?,?,?,?)",
      (chat_id, o["id"], target.isoformat(), label, lg))


REMIND_DAYS = int(os.environ.get("REMIND_DAYS", "3"))  # за сколько дней до годовщины первое напоминание
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
             "October", "November", "December"]


def day_text(d, lg):
    if lg == "en":
        return f"{MONTHS_EN[d.month - 1]} {d.day}"
    if lg == "hy":
        return f"{d.day:02d}.{d.month:02d}"
    return f"{d.day} {MONTHS[d.month - 1]}"


def reminder_message(r, key, target):
    """Текст напоминания и кнопки: повторить тот же букет или выбрать другой."""
    lg = r["lang"] if r["lang"] in CLIENT else "ru"
    _, o = get_order(r["order_id"])
    o = o or {}
    items = o.get("items") or [{}]
    bouquet = items[0].get("name") or "—"
    sku = items[0].get("sku")
    who = (o.get("recipient") or {}).get("name") or "❤"
    label = r["label"].split(" — ")[0]
    text = esc(CLIENT[lg][key].format(date=day_text(target, lg), label=label, bouquet=bouquet, who=who_for(who, lg)))
    rows = []
    if WEBAPP_URL:
        if sku:
            rows.append([(CLIENT[lg]["same"], "webapp:" + shop_url(add=sku))])
        rows.append([(CLIENT[lg]["again"], "webapp:" + shop_url())])
    return text, rows or None


def who_for(name, lg):
    """«для мамы»: простое склонение частых слов, остальное как есть."""
    if lg != "ru":
        return name or "❤"
    if not name or name == "❤":
        return ""
    forms = {"мама": "мамы", "папа": "папы", "бабушка": "бабушки", "сестра": "сестры", "жена": "жены",
             "подруга": "подруги", "дочка": "дочки", "дочь": "дочери", "брат": "брата", "муж": "мужа", "сын": "сына"}
    f = forms.get(name.lower())
    return f"для {f}" if f else f"(получатель — {name})"


def remind_link_for(order_id):
    """Ссылка для заказа с сайта: человек открывает бота, и напоминания привязываются к его Telegram."""
    code = secrets.token_urlsafe(9)
    q("INSERT INTO rem_links(code,order_id,created) VALUES(?,?,?)", (code, order_id, time.time()))
    return f"https://t.me/{BOT_USERNAME}?start=rem_{code}"


def remind_start(chat, m, code):
    r = q("SELECT * FROM rem_links WHERE code=?", (code,), one=True)
    lg = user_lang(m.get("from") or {})
    if not r:
        send(chat, esc(CARD_TX.get(lg, CARD_TX["ru"])["bad"]))
        return
    row, o = get_order(r["order_id"])
    if not row:
        send(chat, esc(CARD_TX.get(lg, CARD_TX["ru"])["bad"]))
        return
    q("UPDATE orders SET client_chat=COALESCE(client_chat, ?) WHERE id=?", (chat, r["order_id"]))
    if not q("SELECT 1 FROM reminders WHERE order_id=? AND chat_id=?", (r["order_id"], chat), one=True):
        add_reminder(o, chat)
    rem = q("SELECT label FROM reminders WHERE order_id=? AND chat_id=?", (r["order_id"], chat), one=True)
    label = (rem["label"] if rem else "").split(" — ")[0] or "—"
    send(chat, esc(CLIENT[lang_of(o)]["rem_on"].format(label=label)))


def local_now():
    return datetime.utcnow() + timedelta(hours=TZ_OFFSET)


def reminder_loop():
    while True:
        try:
            now = local_now()
            if now.hour >= REMIND_HOUR:
                today = now.date()
                for r in q("SELECT * FROM reminders"):
                    target = datetime.strptime(r["target"], "%Y-%m-%d").date()
                    days = (target - today).days
                    if days <= REMIND_DAYS and days > 1 and not r["sent7"]:
                        text, rows = reminder_message(r, "r7", target)
                        send(r["chat_id"], text, rows)
                        q("UPDATE reminders SET sent7=1 WHERE id=?", (r["id"],))
                    elif days <= 1 and days >= 0 and not r["sent1"]:
                        text, rows = reminder_message(r, "r1", target)
                        send(r["chat_id"], text, rows)
                        q("UPDATE reminders SET sent1=1, sent7=1 WHERE id=?", (r["id"],))
                    elif days < 0:
                        nxt = next_occurrence(r["target"], today)
                        q("UPDATE reminders SET target=?, sent7=0, sent1=0 WHERE id=?", (nxt.isoformat(), r["id"]))
        except Exception:
            log.exception("reminder loop")
        time.sleep(int(os.environ.get("REMIND_EVERY", "900")))


# ---------------------------------------------------------------- логика заказов

def get_order(order_id):
    row = q("SELECT * FROM orders WHERE id=?", (order_id,), one=True)
    if not row:
        return None, None
    return row, json.loads(row["payload"])


def studio_by_chat(chat_id):
    return q("SELECT * FROM studios WHERE chat_id=?", (chat_id,), one=True)


def create_order(o, client_chat=None):
    oid = str(o.get("id") or "").strip()[:40]
    if not oid or q("SELECT 1 FROM orders WHERE id=?", (oid,), one=True):
        n = q("SELECT COUNT(*) AS n FROM orders", one=True)["n"]
        oid = f"MF-{2001 + n}"
        while q("SELECT 1 FROM orders WHERE id=?", (oid,), one=True):
            n += 1
            oid = f"MF-{2001 + n}"
    o["id"] = oid
    q("INSERT INTO orders(id,payload,status,created,client_chat) VALUES(?,?,?,?,?)",
      (oid, json.dumps(o, ensure_ascii=False), "new", time.time(), client_chat))
    src = "из мини-апки" if client_chat else "с сайта"
    notify_admins(f"🆕 Новый заказ {src}\n\n" + admin_text(o, "new"), buttons=[[("📂 Открыть заказ", f"adm:o:{oid}")]])
    if client_chat:
        notify_client(oid, "received")
        if o.get("remind"):
            add_reminder(o, client_chat)
    if (o.get("card") or {}).get("type") == "media":
        make_card(oid, o, client_chat)
    dispatch(oid)
    return oid


def dispatch(order_id):
    """Предложить заявку следующей свободной студии."""
    row, o = get_order(order_id)
    if not row or row["status"] not in ("new", "offered", "unassigned"):
        return
    tried = {r["studio_id"] for r in q("SELECT studio_id FROM offers WHERE order_id=?", (order_id,))}
    studios = [s for s in q("SELECT * FROM studios WHERE active=1 ORDER BY priority, last_assigned")
               if s["id"] not in tried]
    if not studios:
        q("UPDATE orders SET status='unassigned' WHERE id=?", (order_id,))
        notify_admins(f"⚠️ Заявку <b>{esc(order_id)}</b> не принял никто. Свяжитесь со студиями вручную "
                      f"или раздайте заново.",
                      buttons=[[("🔁 Раздать заново", f"adm:retry:{order_id}"), ("❌ Отменить", f"adm:cx:{order_id}")]])
        return
    s = studios[0]
    photo = next((i.get("image_url") for i in o.get("items", []) if str(i.get("image_url", "")).startswith("http")), None)
    if photo:
        tg("sendPhoto", chat_id=s["chat_id"], photo=photo, caption=f"Референс к заявке {o['id']}")
    msg = send(s["chat_id"], order_text(o, full=False, status="offered"),
               [[("✅ Принять", f"acc:{order_id}"), ("❌ Не можем", f"dec:{order_id}")]])
    q("INSERT OR REPLACE INTO offers(order_id,studio_id,status,offered,msg_id) VALUES(?,?,?,?,?)",
      (order_id, s["id"], "pending", time.time(), msg["message_id"] if msg else None))
    q("UPDATE orders SET status='offered' WHERE id=?", (order_id,))
    log.info("order %s offered to studio %s", order_id, s["name"])


def close_offer(offer, text):
    s = q("SELECT * FROM studios WHERE id=?", (offer["studio_id"],), one=True)
    if s and offer["msg_id"]:
        edit(s["chat_id"], offer["msg_id"], text)


def expire_loop():
    while True:
        time.sleep(15)
        try:
            limit = time.time() - ACCEPT_TIMEOUT
            for off in q("SELECT * FROM offers WHERE status='pending' AND offered<?", (limit,)):
                q("UPDATE offers SET status='expired' WHERE order_id=? AND studio_id=?",
                  (off["order_id"], off["studio_id"]))
                close_offer(off, f"⌛ Время на ответ вышло. Заявка {esc(off['order_id'])} передана другой студии.")
                dispatch(off["order_id"])
        except Exception:
            log.exception("expire loop")


def set_status(order_id, status, studio):
    row, o = get_order(order_id)
    if not row or row["studio_id"] != studio["id"]:
        return False
    q("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    if row["msg_id"]:
        edit(studio["chat_id"], row["msg_id"], order_text(o, full=True, status=status),
             studio_buttons(order_id, status))
    notify_admins(f"🔄 {esc(order_id)}: <b>{esc(STATUS_TEXT[status])}</b> · {esc(studio['name'])}")
    if status in ("built", "courier", "delivered"):
        notify_client(order_id, status, photo=row["photo"] if status == "built" else None)
    return True


# ---------------------------------------------------------------- обработка апдейтов

HELP_ADMIN = (
    "<b>Команды админа</b>\n"
    "/invite Название студии — ссылка-приглашение для студии\n"
    "/studios — список студий\n"
    "/pause ID, /resume ID — выключить или включить студию\n"
    "/priority ID число — порядок раздачи (меньше = раньше)\n"
    "/remove ID — удалить студию\n"
    "/orders — последние заказы\n"
    "/order ID — заказ целиком\n"
    "/retry ID — заново раздать заказ всем студиям\n"
    "/cancel ID — отменить заказ\n"
    "/test — тестовый заказ\n"
    "/myid — ваш Telegram ID\n"
    "/reply ID текст — ответить клиенту (ID приходит вместе с его сообщением)\n"
    "/menu — показать меню клиента (проверить, как его видят люди)"
)
HELP_STUDIO = (
    "Сюда приходят заявки May Flowers.\n"
    "• «✅ Принять» — берёте заказ, после этого увидите контакты получателя.\n"
    f"• Не ответили за {ACCEPT_TIMEOUT // 60} мин — заявка уйдёт другой студии.\n"
    "• Когда букет готов, нажмите «📸 Букет готов» и пришлите фото.\n"
    "/active — ваши текущие заказы"
)


def is_admin(uid):
    return uid in ADMIN_IDS


def handle_message(m):
    chat = m["chat"]["id"]
    uid = m.get("from", {}).get("id")
    text = (m.get("text") or "").strip()
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0].lower()
    arg = arg.strip()

    # фото готового букета
    if m.get("photo"):
        w = q("SELECT * FROM waiting_photo WHERE chat_id=?", (chat,), one=True)
        s = studio_by_chat(chat)
        if not w or not s:
            if s:
                send(chat, "Фото получено, но я не жду фото ни по одному заказу.")
            return
        file_id = m["photo"][-1]["file_id"]
        q("UPDATE orders SET photo=? WHERE id=?", (file_id, w["order_id"]))
        q("DELETE FROM waiting_photo WHERE chat_id=?", (chat,))
        set_status(w["order_id"], "built", s)
        notify_admins(f"📸 {esc(w['order_id'])}: букет собран · {esc(s['name'])}", photo=file_id)
        send(chat, "Спасибо! Фото отправлено. Когда отдадите курьеру, нажмите кнопку в заявке.")
        return

    if cmd == "/myid":
        send(chat, f"Ваш Telegram ID: <code>{uid}</code>")
        return

    # запись для аудио/видео-открытки
    media = m.get("voice") or m.get("video_note") or m.get("video") or m.get("audio")
    if media and not studio_by_chat(chat):
        if card_media_in(chat, m, media):
            return

    if cmd == "/start":
        if arg.startswith("rec_"):
            card_start(chat, m, arg[4:])
            return
        if arg.startswith("rem_"):
            remind_start(chat, m, arg[4:])
            return
        if arg:
            inv = q("SELECT * FROM invites WHERE code=? AND used=0", (arg,), one=True)
            if not inv:
                send(chat, "Ссылка-приглашение недействительна. Попросите новую у менеджера May Flowers.")
                return
            if studio_by_chat(chat):
                send(chat, "Эта студия уже подключена.\n\n" + HELP_STUDIO)
                return
            q("INSERT INTO studios(chat_id,name,joined_at) VALUES(?,?,?)", (chat, inv["name"], time.time()))
            q("UPDATE invites SET used=1 WHERE code=?", (arg,))
            send(chat, f"Студия «{esc(inv['name'])}» подключена к May Flowers 🌸\n\n" + HELP_STUDIO)
            notify_admins(f"✅ Подключилась студия «{esc(inv['name'])}»")
            return
        if is_admin(uid):
            admin_home(chat)
        elif studio_by_chat(chat):
            send(chat, HELP_STUDIO)
        else:
            client_hello(chat, m)
        return

    if is_admin(uid):
        if text in ADMIN_BUTTONS:
            admin_button(chat, ADMIN_BUTTONS[text])
            return
        st = ADMIN_STATE.pop(chat, None)
        if st and text and not text.startswith("/"):
            admin_state_input(chat, st, text)
            return
        if handle_admin(chat, cmd, arg):
            return

    action = client_button(text)
    if action and not studio_by_chat(chat):
        client_action(chat, m, action)
        return

    s = studio_by_chat(chat)
    if s and cmd == "/active":
        rows = q("SELECT * FROM orders WHERE studio_id=? AND status IN ('accepted','built','courier') "
                 "ORDER BY created DESC", (s["id"],))
        if not rows:
            send(chat, "Активных заказов нет.")
        for r in rows:
            o = json.loads(r["payload"])
            msg = send(chat, order_text(o, full=True, status=r["status"]), studio_buttons(r["id"], r["status"]))
            if msg:
                q("UPDATE orders SET msg_id=? WHERE id=?", (msg["message_id"], r["id"]))
        return
    if s:
        send(chat, HELP_STUDIO)
    elif is_admin(uid):
        send(chat, HELP_ADMIN)
    elif cmd == "/orders":
        client_action(chat, m, "orders")
    elif cmd == "/catalog":
        client_action(chat, m, "catalog")
    elif text and not text.startswith("/"):
        client_free_text(chat, m, text)
    else:
        client_hello(chat, m)


# ---------------------------------------------------------------- меню и каталог для клиентов

MENU = {
    "ru": [["💐 Каталог", "📦 Мои заказы"], ["🤍 В добрые руки", "📞 Связаться"], ["ℹ️ Как это работает"]],
    "en": [["💐 Catalog", "📦 My orders"], ["🤍 Kind hands", "📞 Contact us"], ["ℹ️ How it works"]],
    "hy": [["💐 Կատալոգ", "📦 Իմ պատվերները"], ["🤍 Բարի ձեռքեր", "📞 Կապ"], ["ℹ️ Ինչպես է աշխատում"]],
}
MENU_ACTIONS = ["catalog", "orders", "kind", "contact", "how"]
CL = {
    "ru": {
        "menu_hint": "Меню внизу 👇",
        "pick": "Выберите повод:",
        "cats": {"all": "Все букеты", "bd": "День рождения", "love": "Любовь", "thanks": "Спасибо",
                 "mom": "Маме", "sorry": "Извинение", "premium": "Премиум"},
        "order": "🛒 Заказать", "back": "↩️ Поводы", "empty": "Тут пока пусто.",
        "how": "Как это работает:\n\n1. Выберите букет в каталоге или в магазине.\n2. Укажите адрес, дату и время, текст открытки.\n3. Мы соберём букет, и я пришлю вам его фото до доставки.\n4. Курьер привезёт цветы по Еревану, от 60 минут.",
        "kind": "🤍 Букет в добрые руки\n\nВыберите любой букет, и мы подарим его случайному прохожему на улицах Еревана. В открытке будет ваше имя, а вам придёт видео вручения.\n\nПри оформлении заказа выберите «Кому: В добрые руки».",
        "contact": "Напишите вопрос прямо сюда, менеджер ответит в этом чате.",
        "contact_direct": "Или напрямую: {c}",
        "sent": "Передал менеджеру, ответим здесь же 🌸",
        "cab": "📦 Открыть кабинет",
        "manager": "💬 Менеджер May Flowers:",
    },
    "en": {
        "menu_hint": "Menu is below 👇",
        "pick": "Choose an occasion:",
        "cats": {"all": "All bouquets", "bd": "Birthday", "love": "Love", "thanks": "Thank you",
                 "mom": "For mom", "sorry": "Sorry", "premium": "Premium"},
        "order": "🛒 Order", "back": "↩️ Occasions", "empty": "Nothing here yet.",
        "how": "How it works:\n\n1. Pick a bouquet in the catalog or the shop.\n2. Enter the address, date, time and card text.\n3. We build the bouquet and I send you a photo before delivery.\n4. A courier delivers across Yerevan, from 60 minutes.",
        "kind": "🤍 A bouquet into kind hands\n\nPick any bouquet and we will give it to a random passer-by on the streets of Yerevan. Your name goes on the card, and you get the video of the moment.\n\nAt checkout choose “For: Kind hands”.",
        "contact": "Write your question right here, a manager will reply in this chat.",
        "contact_direct": "Or directly: {c}",
        "sent": "Sent to a manager, we will reply here 🌸",
        "cab": "📦 Open my account",
        "manager": "💬 May Flowers manager:",
    },
    "hy": {
        "menu_hint": "Մենյուն ներքևում է 👇",
        "pick": "Ընտրեք առիթը՝",
        "cats": {"all": "Բոլոր ծաղկեփնջերը", "bd": "Ծննդյան օր", "love": "Սեր", "thanks": "Շնորհակալություն",
                 "mom": "Մայրիկին", "sorry": "Ներողություն", "premium": "Պրեմիում"},
        "order": "🛒 Պատվիրել", "back": "↩️ Առիթներ", "empty": "Այստեղ դեռ դատարկ է։",
        "how": "Ինչպես է աշխատում՝\n\n1. Ընտրեք ծաղկեփունջ կատալոգում կամ խանութում։\n2. Նշեք հասցեն, ամսաթիվը, ժամը և բացիկի տեքստը։\n3. Մենք կհավաքենք ծաղկեփունջը, և ես կուղարկեմ լուսանկարը առաքումից առաջ։\n4. Առաքիչը կբերի Երևանով մեկ՝ 60 րոպեից։",
        "kind": "🤍 Ծաղկեփունջ բարի ձեռքերին\n\nԸնտրեք ցանկացած ծաղկեփունջ, և մենք այն կնվիրենք պատահական անցորդի Երևանի փողոցներում: Բացիկին կլինի ձեր անունը, իսկ դուք կստանաք հանձնման տեսանյութը:\n\nՊատվիրելիս ընտրեք «Ում՝ Բարի ձեռքերին»:",
        "contact": "Գրեք ձեր հարցն այստեղ, մենեջերը կպատասխանի այս չատում։",
        "contact_direct": "Կամ ուղղակի՝ {c}",
        "sent": "Փոխանցեցի մենեջերին, կպատասխանենք այստեղ 🌸",
        "cab": "📦 Բացել կաբինետը",
        "manager": "💬 May Flowers մենեջեր՝",
    },
}
CAT_ORDER = ["all", "bd", "love", "thanks", "mom", "sorry", "premium"]
CATALOG = {"rate_amd": 390, "items": []}


def load_catalog():
    """Каталог берём с сайта (catalog.json рядом с index.html), иначе из файла рядом с ботом."""
    global CATALOG
    if WEBAPP_URL:
        try:
            with urllib.request.urlopen(urllib.parse.urljoin(WEBAPP_URL, "catalog.json"), timeout=15) as r:
                data = json.loads(r.read().decode())
            if data.get("items"):
                CATALOG = data
                return
        except Exception as e:
            log.warning("catalog from site failed: %s", e)
    try:
        with open(CATALOG_FILE, encoding="utf-8") as f:
            CATALOG = json.load(f)
    except (OSError, ValueError) as e:
        log.warning("catalog file failed: %s", e)


def catalog_loop():
    while True:
        time.sleep(900)
        load_catalog()


def user_lang(frm):
    return lang_of({"lang": (frm or {}).get("language_code")})


def shop_url(**params):
    if not WEBAPP_URL:
        return ""
    if not params:
        return WEBAPP_URL
    return WEBAPP_URL + ("&" if "?" in WEBAPP_URL else "?") + urllib.parse.urlencode(params)


def menu_markup(lg):
    return {"keyboard": [[{"text": t} for t in row] for row in MENU[lg]], "resize_keyboard": True, "is_persistent": True}


def client_button(text):
    for lg, rows in MENU.items():
        flat = [t for row in rows for t in row]
        if text in flat:
            return MENU_ACTIONS[flat.index(text)]
    return None


def client_hello(chat, m):
    lg = user_lang(m.get("from"))
    if WEBAPP_URL:
        send(chat, esc(CLIENT[lg]["hello"]), [[(CLIENT[lg]["open"], "webapp:" + shop_url())]])
    else:
        send(chat, esc(CLIENT[lg]["soon"]))
    tg("sendMessage", chat_id=chat, text=CL[lg]["menu_hint"], reply_markup=menu_markup(lg))


def client_action(chat, m, action):
    lg = user_lang(m.get("from"))
    L = CL[lg]
    if action == "catalog":
        send(chat, L["pick"], cat_menu(lg))
    elif action == "orders":
        rows = q("SELECT * FROM orders WHERE client_chat=? ORDER BY created DESC LIMIT 10", (chat,))
        btn = [[(L["cab"], "webapp:" + shop_url(v="cabinet"))]] if WEBAPP_URL else None
        if not rows:
            send(chat, esc(CLIENT[lg]["none"]), [[(CLIENT[lg]["open"], "webapp:" + shop_url())]] if WEBAPP_URL else None)
        else:
            send(chat, "\n".join(f"{esc(r['id'])} · {esc(STATUS_TEXT.get(r['status'], r['status']))}" for r in rows), btn)
    elif action == "how":
        send(chat, esc(L["how"]), [[(CLIENT[lg]["open"], "webapp:" + shop_url())]] if WEBAPP_URL else None)
    elif action == "kind":
        send(chat, esc(L["kind"]), [[(CLIENT[lg]["open"], "webapp:" + shop_url())]] if WEBAPP_URL else None)
    elif action == "contact":
        set_human(chat, True)
        txt = L["contact"] + ("\n" + L["contact_direct"].format(c=MANAGER_CONTACT) if MANAGER_CONTACT else "")
        send(chat, esc(txt))


def client_free_text(chat, m, text):
    if ANTHROPIC_API_KEY and not human_active(chat):
        if ai_chat(chat, m, text):
            return
    forward_to_human(chat, m, text)


def forward_to_human(chat, m, text):
    frm = m.get("from") or {}
    name = " ".join(x for x in [frm.get("first_name"), frm.get("last_name")] if x) or "клиент"
    user = f" @{esc(frm['username'])}" if frm.get("username") else ""
    notify_admins(f"💬 Сообщение от {esc(name)}{user}:\n{esc(text[:3000])}",
                  buttons=[[("✍️ Ответить", f"adm:rp:{chat}")]])
    send(chat, esc(CL[user_lang(frm)]["sent"]))


def cat_items(cat):
    items = CATALOG.get("items", [])
    if cat == "premium":
        items = [i for i in items if i.get("usd", 0) >= 150]
    elif cat != "all":
        items = [i for i in items if cat in i.get("occ", [])]
    return sorted(items, key=lambda i: i.get("usd", 0))


def cat_menu(lg):
    labels = CL[lg]["cats"]
    rows, row = [], []
    for c in CAT_ORDER:
        row.append((labels[c], f"cat:{c}:0"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


def card(lg, cat, idx):
    items = cat_items(cat)
    if not items:
        return None
    idx %= len(items)
    it = items[idx]
    name = it["n"].get(lg) or it["n"]["ru"]
    comp = it["k"].get(lg) or it["k"]["ru"]
    amd = round(it["usd"] * CATALOG.get("rate_amd", 390) / 100) * 100
    amd_txt = f"{amd:,}".replace(",", "\u00a0")
    caption = (f"<b>{esc(name)}</b>\n{esc(comp)}\n\n<b>${it['usd']}</b> · {amd_txt} ֏"
               + f"\n\n{esc(CL[lg]['cats'][cat])} · {idx + 1} / {len(items)}")
    nav = [("◀️", f"cat:{cat}:{idx - 1}"), (f"{idx + 1}/{len(items)}", "cat:noop"), ("▶️", f"cat:{cat}:{idx + 1}")]
    rows = [nav]
    if WEBAPP_URL:
        rows.append([(CL[lg]["order"], "webapp:" + shop_url(add=it["id"]))])
    rows.append([(CL[lg]["back"], "cat:menu")])
    photo = urllib.parse.urljoin(WEBAPP_URL, it["img"]) if WEBAPP_URL else None
    return photo, caption, rows


def catalog_callback(cb, answer):
    chat = cb["message"]["chat"]["id"]
    mid = cb["message"]["message_id"]
    lg = user_lang(cb.get("from"))
    parts = cb.get("data", "").split(":")
    if parts[1] == "noop":
        answer()
        return
    if parts[1] == "menu":
        if cb["message"].get("photo"):
            tg("deleteMessage", chat_id=chat, message_id=mid)
            send(chat, CL[lg]["pick"], cat_menu(lg))
        else:
            edit(chat, mid, CL[lg]["pick"], cat_menu(lg))
        answer()
        return
    cat = parts[1] if parts[1] in CAT_ORDER else "all"
    idx = int(parts[2]) if len(parts) > 2 and parts[2].lstrip("-").isdigit() else 0
    c = card(lg, cat, idx)
    if not c:
        answer(CL[lg]["empty"])
        return
    photo, caption, rows = c
    if cb["message"].get("photo") and photo:
        tg("editMessageMedia", chat_id=chat, message_id=mid,
           media={"type": "photo", "media": photo, "caption": caption, "parse_mode": "HTML"}, reply_markup=kb(rows))
    else:
        if photo:
            tg("deleteMessage", chat_id=chat, message_id=mid)
            tg("sendPhoto", chat_id=chat, photo=photo, caption=caption, parse_mode="HTML", reply_markup=kb(rows))
        else:
            edit(chat, mid, caption, rows)
    answer()


# ---------------------------------------------------------------- админка на кнопках

ADMIN_KB = [["📋 Заказы", "🏪 Студии"], ["➕ Пригласить студию", "🧪 Тестовый заказ"], ["👀 Меню клиента", "❓ Помощь"]]
ADMIN_BUTTONS = {"📋 Заказы": "orders", "🏪 Студии": "studios", "➕ Пригласить студию": "invite",
                 "🧪 Тестовый заказ": "test", "👀 Меню клиента": "client", "❓ Помощь": "help", "⚙️ Админка": "home"}
ADMIN_STATE = {}  # chat_id -> ("invite",) или ("reply", client_chat)
ADMIN_HELP = (
    "<b>Как пользоваться</b>\n\n"
    "📋 <b>Заказы</b> — последние заказы. Нажмите на заказ: увидите всё по нему, фото букета, "
    "можно раздать заново или отменить.\n"
    "🏪 <b>Студии</b> — список студий. Нажмите на студию: пауза, порядок раздачи, удаление.\n"
    "➕ <b>Пригласить студию</b> — бот спросит название и даст одноразовую ссылку для флориста.\n"
    "🧪 <b>Тестовый заказ</b> — проверить, как заявка уходит студиям.\n"
    "👀 <b>Меню клиента</b> — посмотреть бота глазами покупателя (вернуться: «⚙️ Админка»).\n\n"
    "Когда клиент пишет в бот, вам приходит его сообщение с кнопкой «✍️ Ответить»."
)


def admin_markup():
    return {"keyboard": [[{"text": t} for t in row] for row in ADMIN_KB], "resize_keyboard": True, "is_persistent": True}


def admin_home(chat):
    tg("sendMessage", chat_id=chat, parse_mode="HTML", reply_markup=admin_markup(),
       text="⚙️ <b>Админка May Flowers</b>\nВыберите раздел на кнопках внизу.")


def admin_button(chat, action):
    ADMIN_STATE.pop(chat, None)
    if action == "home":
        admin_home(chat)
    elif action == "orders":
        admin_orders(chat)
    elif action == "studios":
        admin_studios(chat)
    elif action == "invite":
        ADMIN_STATE[chat] = ("invite",)
        send(chat, "Напишите название студии одним сообщением, например «Цветы на Абовяна».", [[("Отмена", "adm:x")]])
    elif action == "test":
        handle_admin(chat, "/test", "")
    elif action == "client":
        rows = [[{"text": t} for t in row] for row in MENU["ru"]] + [[{"text": "⚙️ Админка"}]]
        tg("sendMessage", chat_id=chat, text="Так меню видят клиенты. Вернуться: «⚙️ Админка».",
           reply_markup={"keyboard": rows, "resize_keyboard": True, "is_persistent": True})
    elif action == "help":
        send(chat, ADMIN_HELP)


def admin_state_input(chat, st, text):
    if st[0] == "invite":
        handle_admin(chat, "/invite", text.strip())
    elif st[0] == "reply":
        r = send(st[1], esc(CL["ru"]["manager"]) + "\n" + esc(text.strip()))
        send(chat, "Ответ отправлен ✅" if r else "Не доставлено: клиент мог заблокировать бота.")


def orders_view():
    rows = q("SELECT id, status FROM orders ORDER BY created DESC LIMIT 15")
    if not rows:
        return "Заказов пока нет.", [[("🧪 Создать тестовый заказ", "adm:test")]]
    return ("<b>Последние заказы</b>\nНажмите на заказ, чтобы открыть.",
            [[(f"{r['id']} · {STATUS_TEXT.get(r['status'], r['status'])}", f"adm:o:{r['id']}")] for r in rows])


def admin_orders(chat, mid=None):
    text, rows = orders_view()
    edit(chat, mid, text, rows) if mid else send(chat, text, rows)


def order_view(order_id):
    row, o = get_order(order_id)
    if not row:
        return "Заказ не найден.", [[("↩️ К заказам", "adm:orders")]]
    st = q("SELECT name FROM studios WHERE id=?", (row["studio_id"],), one=True)
    rows = []
    if row["status"] in ("new", "offered", "unassigned"):
        rows.append([("🔁 Раздать заново", f"adm:retry:{order_id}")])
    if row["photo"]:
        rows.append([("📸 Фото букета", f"adm:ph:{order_id}")])
    if row["status"] not in ("cancelled", "delivered"):
        rows.append([("❌ Отменить заказ", f"adm:cx:{order_id}")])
    rows.append([("↩️ К заказам", "adm:orders")])
    return admin_text(o, row["status"], st["name"] if st else None), rows


def studios_view():
    rows = q("SELECT * FROM studios ORDER BY priority, id")
    btns = [[(f"{'✅' if r['active'] else '⏸'} {r['name']}", f"adm:s:{r['id']}")] for r in rows]
    btns.append([("➕ Пригласить студию", "adm:inv")])
    if not rows:
        return "Студий пока нет. Пригласите первую 👇", btns
    return "<b>Студии</b>\nСверху вниз — порядок, в котором студии получают заявки. Нажмите на студию.", btns


def admin_studios(chat, mid=None):
    text, rows = studios_view()
    edit(chat, mid, text, rows) if mid else send(chat, text, rows)


def studio_view(sid):
    r = q("SELECT * FROM studios WHERE id=?", (sid,), one=True)
    if not r:
        return "Студия не найдена.", [[("↩️ К студиям", "adm:studios")]]
    done = q("SELECT COUNT(*) AS n FROM orders WHERE studio_id=? AND status='delivered'", (sid,), one=True)["n"]
    active = q("SELECT COUNT(*) AS n FROM orders WHERE studio_id=? AND status IN ('accepted','built','courier')",
               (sid,), one=True)["n"]
    joined = datetime.fromtimestamp(r["joined_at"] or 0).strftime("%d.%m.%Y")
    text = (f"🏪 <b>{esc(r['name'])}</b>\n"
            f"Статус: {'✅ получает заявки' if r['active'] else '⏸ на паузе'}\n"
            f"Подключена: {joined}\nДоставлено заказов: {done}\nСейчас в работе: {active}")
    rows = [[("⏸ Поставить на паузу", f"adm:sp:{sid}") if r["active"] else ("▶️ Включить", f"adm:sr:{sid}")],
            [("⬆️ Получать раньше", f"adm:up:{sid}"), ("⬇️ Получать позже", f"adm:dn:{sid}")],
            [("🗑 Удалить студию", f"adm:sd:{sid}")],
            [("↩️ К студиям", "adm:studios")]]
    return text, rows


def admin_callback(cb, answer):
    chat = cb["message"]["chat"]["id"]
    mid = cb["message"]["message_id"]
    parts = cb.get("data", "").split(":")
    act = parts[1] if len(parts) > 1 else ""
    arg = ":".join(parts[2:])

    def show(view):
        text, rows = view
        if cb["message"].get("photo"):
            send(chat, text, rows)
        else:
            edit(chat, mid, text, rows)

    if act == "x":
        ADMIN_STATE.pop(chat, None)
        edit(chat, mid, "Отменено.")
    elif act == "orders":
        show(orders_view())
    elif act == "o":
        show(order_view(arg))
    elif act == "retry":
        handle_admin(chat, "/retry", arg)
        show(order_view(arg))
    elif act == "cx":
        show((f"Отменить заказ <b>{esc(arg)}</b>? Студия получит сообщение «не собирайте».",
              [[("Да, отменить", f"adm:cxy:{arg}"), ("Нет", f"adm:o:{arg}")]]))
    elif act == "cxy":
        handle_admin(chat, "/cancel", arg)
        show(order_view(arg))
    elif act == "ph":
        row, _ = get_order(arg)
        if row and row["photo"]:
            tg("sendPhoto", chat_id=chat, photo=row["photo"], caption=f"Фото букета {arg}")
    elif act == "test":
        handle_admin(chat, "/test", "")
    elif act == "studios":
        show(studios_view())
    elif act == "inv":
        ADMIN_STATE[chat] = ("invite",)
        send(chat, "Напишите название студии одним сообщением, например «Цветы на Абовяна».", [[("Отмена", "adm:x")]])
    elif act == "s":
        show(studio_view(int(arg)))
    elif act in ("sp", "sr"):
        q("UPDATE studios SET active=? WHERE id=?", (0 if act == "sp" else 1, int(arg)))
        show(studio_view(int(arg)))
    elif act in ("up", "dn"):
        sid = int(arg)
        order = [r["id"] for r in q("SELECT id FROM studios ORDER BY priority, id")]
        if sid in order:
            i = order.index(sid)
            j = i - 1 if act == "up" else i + 1
            if 0 <= j < len(order):
                order[i], order[j] = order[j], order[i]
            for n, x in enumerate(order):
                q("UPDATE studios SET priority=? WHERE id=?", ((n + 1) * 10, x))
            answer(f"Теперь {order.index(sid) + 1}-я по очереди")
        show(studio_view(sid))
        return
    elif act == "sd":
        r = q("SELECT name FROM studios WHERE id=?", (int(arg),), one=True)
        show((f"Удалить студию «{esc(r['name'] if r else '?')}»? Новые заявки ей приходить перестанут.",
              [[("Да, удалить", f"adm:sdy:{arg}"), ("Нет", f"adm:s:{arg}")]]))
    elif act == "sdy":
        q("DELETE FROM studios WHERE id=?", (int(arg),))
        show(studios_view())
    elif act == "rp":
        ADMIN_STATE[chat] = ("reply", int(arg))
        send(chat, "Напишите ответ клиенту одним сообщением.", [[("Отмена", "adm:x")]])
    answer()


def handle_admin(chat, cmd, arg):
    if cmd == "/help":
        send(chat, HELP_ADMIN)
    elif cmd == "/invite":
        if not arg:
            send(chat, "Напишите так: /invite Название студии")
            return True
        code = secrets.token_urlsafe(9)
        q("INSERT INTO invites(code,name,created) VALUES(?,?,?)", (code, arg[:80], time.time()))
        link = f"https://t.me/{BOT_USERNAME}?start={code}"
        send(chat, f"Приглашение для «{esc(arg)}». Отправьте студии эту ссылку, она одноразовая:\n{link}")
    elif cmd == "/studios":
        rows = q("SELECT * FROM studios ORDER BY priority, id")
        if not rows:
            send(chat, "Студий пока нет. Пригласите: /invite Название")
        else:
            send(chat, "\n".join(
                f"{r['id']}. {esc(r['name'])} · {'✅ активна' if r['active'] else '⏸ на паузе'} · приоритет {r['priority']}"
                for r in rows))
    elif cmd in ("/pause", "/resume", "/remove", "/priority"):
        parts = arg.split()
        if not parts or not parts[0].isdigit():
            send(chat, f"Напишите так: {cmd} ID" + (" число" if cmd == "/priority" else ""))
            return True
        sid = int(parts[0])
        if cmd == "/pause":
            q("UPDATE studios SET active=0 WHERE id=?", (sid,))
        elif cmd == "/resume":
            q("UPDATE studios SET active=1 WHERE id=?", (sid,))
        elif cmd == "/remove":
            q("DELETE FROM studios WHERE id=?", (sid,))
        elif cmd == "/priority" and len(parts) > 1 and parts[1].lstrip("-").isdigit():
            q("UPDATE studios SET priority=? WHERE id=?", (int(parts[1]), sid))
        send(chat, "Готово. /studios")
    elif cmd == "/orders":
        rows = q("SELECT o.*, s.name AS sname FROM orders o LEFT JOIN studios s ON s.id=o.studio_id "
                 "ORDER BY created DESC LIMIT 15")
        if not rows:
            send(chat, "Заказов пока нет. Проверьте бота: /test")
        else:
            send(chat, "\n".join(
                f"{esc(r['id'])} · {esc(STATUS_TEXT.get(r['status'], r['status']))}"
                + (f" · {esc(r['sname'])}" if r["sname"] else "") for r in rows))
    elif cmd == "/order":
        row, o = get_order(arg)
        if not row:
            send(chat, "Нет такого заказа.")
        else:
            s = q("SELECT name FROM studios WHERE id=?", (row["studio_id"],), one=True)
            send(chat, admin_text(o, row["status"], s["name"] if s else None))
            if row["photo"]:
                tg("sendPhoto", chat_id=chat, photo=row["photo"], caption=f"Фото {o['id']}")
    elif cmd == "/retry":
        row, _ = get_order(arg)
        if not row:
            send(chat, "Нет такого заказа.")
        elif row["status"] not in ("unassigned", "offered", "new"):
            send(chat, "Этот заказ уже принят студией.")
        else:
            for off in q("SELECT * FROM offers WHERE order_id=? AND status='pending'", (arg,)):
                close_offer(off, f"Заявка {esc(arg)} больше не актуальна.")
            q("DELETE FROM offers WHERE order_id=?", (arg,))
            q("UPDATE orders SET status='new' WHERE id=?", (arg,))
            dispatch(arg)
            send(chat, f"Раздача {esc(arg)} запущена заново.")
    elif cmd == "/cancel":
        row, o = get_order(arg)
        if not row:
            send(chat, "Нет такого заказа.")
        else:
            q("UPDATE orders SET status='cancelled' WHERE id=?", (arg,))
            for off in q("SELECT * FROM offers WHERE order_id=? AND status='pending'", (arg,)):
                close_offer(off, f"Заявка {esc(arg)} отменена.")
            q("UPDATE offers SET status='closed' WHERE order_id=?", (arg,))
            if row["studio_id"]:
                s = q("SELECT * FROM studios WHERE id=?", (row["studio_id"],), one=True)
                if s:
                    send(s["chat_id"], f"❌ Заказ {esc(arg)} отменён. Не собирайте его.")
            notify_client(arg, "cancelled")
            send(chat, f"Заказ {esc(arg)} отменён.")
    elif cmd == "/reply":
        target, _, msg = arg.partition(" ")
        if not target.lstrip("-").isdigit() or not msg.strip():
            send(chat, "Напишите так: /reply ID текст")
            return True
        lg = "ru"
        r = send(int(target), esc(CL[lg]["manager"]) + "\n" + esc(msg.strip()))
        send(chat, "Отправлено ✅" if r else "Не доставлено: клиент мог заблокировать бота.")
    elif cmd == "/menu":
        tg("sendMessage", chat_id=chat, text=CL["ru"]["menu_hint"], reply_markup=menu_markup("ru"))
    elif cmd == "/test":
        create_order(sample_order())
        send(chat, "Тестовый заказ создан и отправлен студиям.")
    else:
        return False
    return True


def handle_callback(cb):
    chat = cb["message"]["chat"]["id"]
    data = cb.get("data", "")
    s = studio_by_chat(chat)

    def answer(text=""):
        tg("answerCallbackQuery", callback_query_id=cb["id"], text=text)

    if data.startswith("cat:"):
        catalog_callback(cb, answer)
        return
    if data.startswith("ai:") and not s:
        ai_callback(cb, data[3:], answer)
        return
    if data.startswith("adm:"):
        if is_admin((cb.get("from") or {}).get("id")):
            admin_callback(cb, answer)
        else:
            answer()
        return
    if not s:
        answer()
        return
    kind, _, rest = data.partition(":")
    order_id = rest.split(":")[0]
    row, o = get_order(order_id)
    if not row:
        answer("Заказ не найден")
        return

    if kind in ("acc", "dec"):
        off = q("SELECT * FROM offers WHERE order_id=? AND studio_id=?", (order_id, s["id"]), one=True)
        if not off or off["status"] != "pending":
            answer("Заявка уже недоступна")
            edit(chat, cb["message"]["message_id"], f"Заявка {esc(order_id)} уже недоступна.")
            return
        if kind == "dec":
            q("UPDATE offers SET status='declined' WHERE order_id=? AND studio_id=?", (order_id, s["id"]))
            edit(chat, off["msg_id"], f"Вы отказались от заявки {esc(order_id)}. Передаём другой студии.")
            notify_admins(f"↪️ {esc(order_id)}: «{esc(s['name'])}» отказалась")
            answer("Передаём другой студии")
            dispatch(order_id)
            return
        # принять: только если заказ ещё свободен
        with DB_LOCK:
            fresh = q("SELECT status FROM orders WHERE id=?", (order_id,), one=True)
            if fresh["status"] != "offered":
                answer("Заявку уже взяли")
                return
            q("UPDATE offers SET status='accepted' WHERE order_id=? AND studio_id=?", (order_id, s["id"]))
            q("UPDATE orders SET status='accepted', studio_id=?, msg_id=? WHERE id=?",
              (s["id"], off["msg_id"], order_id))
            q("UPDATE studios SET last_assigned=? WHERE id=?", (time.time(), s["id"]))
        edit(chat, off["msg_id"], order_text(o, full=True, status="accepted"), studio_buttons(order_id, "accepted"))
        notify_admins(f"✅ {esc(order_id)} принят · {esc(s['name'])}")
        notify_client(order_id, "accepted")
        send_card_qr(chat, order_id)
        answer("Заказ ваш!")
        return

    if row["studio_id"] != s["id"]:
        answer("Это не ваш заказ")
        return
    if kind == "photo":
        q("INSERT OR REPLACE INTO waiting_photo(chat_id,order_id) VALUES(?,?)", (chat, order_id))
        send(chat, f"Пришлите одно фото готового букета по заказу {esc(order_id)}.")
        answer()
        return
    if kind == "st":
        new = rest.split(":")[1] if ":" in rest else ""
        allowed = {"built": "courier", "courier": "delivered"}
        if allowed.get(row["status"]) != new:
            answer("Сначала предыдущий шаг")
            return
        set_status(order_id, new, s)
        answer(STATUS_TEXT[new])


def poll_loop():
    offset = 0
    while True:
        updates = tg("getUpdates", offset=offset, timeout=25, allowed_updates=["message", "callback_query"])
        if updates is None:
            time.sleep(3)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            try:
                if "message" in u:
                    handle_message(u["message"])
                elif "callback_query" in u:
                    handle_callback(u["callback_query"])
            except Exception:
                log.exception("update failed")


# ---------------------------------------------------------------- приём заказов с сайта

def validate(o):
    if not isinstance(o, dict):
        return "заказ должен быть объектом JSON"
    items = o.get("items")
    if not isinstance(items, list) or not items:
        return "нет букетов в items"
    r = o.get("recipient") or {}
    if not r.get("phone") or not r.get("address"):
        return "нужны recipient.phone и recipient.address"
    if not (o.get("delivery") or {}).get("date"):
        return "нужна delivery.date"
    return None


class Intake(BaseHTTPRequestHandler):
    def cors(self):
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Intake-Key, X-Telegram-Init-Data, X-Order-Id, X-Manage, X-Card-Kind")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Max-Age", "600")

    def reply(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.end_headers()

    def tg_user(self):
        """Telegram ID клиента по подписи мини-апки, или None (ответ 401 уже отправлен)."""
        user = verify_init_data(self.headers.get("X-Telegram-Init-Data") or "")
        if not user or not user.get("id"):
            self.reply(401, {"ok": False, "error": "нужна подпись Telegram"})
            return None
        return int(user["id"])

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            self.reply(200, {"ok": True})
        elif path.startswith("/api/card/"):
            self.card_get(path[len("/api/card/"):])
        elif path == "/api/me":
            uid = self.tg_user()
            if uid is not None:
                self.reply(200, cabinet(uid))
        elif path.startswith("/api/photo/"):
            uid = self.tg_user()
            if uid is None:
                return
            oid = urllib.parse.unquote(path[len("/api/photo/"):])
            row = q("SELECT photo, client_chat FROM orders WHERE id=?", (oid,), one=True)
            if not row or row["client_chat"] != uid or not row["photo"]:
                self.reply(404, {"ok": False})
                return
            data = download_photo(row["photo"])
            if not data:
                self.reply(502, {"ok": False, "error": "Telegram не отдал фото"})
                return
            self.send_response(200)
            self.cors()
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "private, max-age=86400")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.reply(404, {"ok": False})

    def do_POST(self):
        p = self.path.split("?")[0]
        if p.startswith("/api/card/") and p.endswith("/reply"):
            self.card_reply(p[len("/api/card/"):-len("/reply")])
            return
        if p == "/api/card/upload":
            self.card_upload()
            return
        if p in ("/api/card/add", "/api/card/state"):
            self.card_manage(p.endswith("/add"))
            return
        if p == "/api/ai":
            self.ai_request()
            return
        if p == "/api/vip":
            self.vip_request()
            return
        if self.path == "/api/reminders/delete":
            uid = self.tg_user()
            if uid is None:
                return
            try:
                rid = int(json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}").get("id"))
            except (ValueError, TypeError, AttributeError):
                self.reply(400, {"ok": False, "error": "нужен id"})
                return
            q("DELETE FROM reminders WHERE id=? AND chat_id=?", (rid, uid))
            self.reply(200, {"ok": True})
            return
        if self.path != "/api/orders":
            self.reply(404, {"ok": False, "error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 64_000:
            self.reply(413, {"ok": False, "error": "пустой или слишком большой запрос"})
            return
        try:
            o = json.loads(self.rfile.read(length).decode())
        except Exception:
            self.reply(400, {"ok": False, "error": "битый JSON"})
            return
        client_chat = None
        init = self.headers.get("X-Telegram-Init-Data")
        if init:
            user = verify_init_data(init)
            if not user or not user.get("id"):
                self.reply(401, {"ok": False, "error": "подпись Telegram не прошла проверку"})
                return
            client_chat = int(user["id"])
            if isinstance(o, dict):
                o["tg_username"] = user.get("username") or ""
        else:
            key = self.headers.get("X-Intake-Key") or (o.get("key") if isinstance(o, dict) else None)
            if not INTAKE_KEY or not secrets.compare_digest(str(key or ""), INTAKE_KEY):
                self.reply(401, {"ok": False, "error": "неверный ключ"})
                return
        err = validate(o)
        if err:
            self.reply(422, {"ok": False, "error": err})
            return
        o.pop("key", None)
        oid = create_order(o, client_chat)
        resp = {"ok": True, "id": oid}
        c = q("SELECT rec_code FROM cards WHERE order_id=?", (oid,), one=True)
        if c and not client_chat:
            resp["record_link"] = f"https://t.me/{BOT_USERNAME}?start=rec_{c['rec_code']}"
        if o.get("remind") and not client_chat:
            resp["remind_link"] = remind_link_for(oid)
        if not client_chat:
            # секрет заказа для кабинета на сайте: по нему клиент потом добавляет или меняет открытку
            code = secrets.token_urlsafe(12)
            q("INSERT OR REPLACE INTO order_codes(order_id,code) VALUES(?,?)", (oid, code))
            resp["manage"] = code
        self.reply(200, resp)

    # ---- умный помощник для сайта и мини-апки: подбор букетов (ключ Claude живёт только здесь)
    def ai_request(self):
        if not ANTHROPIC_API_KEY:
            self.reply(503, {"ok": False, "error": "ИИ выключен"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 4_000:
            self.reply(413, {"ok": False})
            return
        try:
            v = json.loads(self.rfile.read(length).decode())
            text = str(v.get("q") or "").strip()[:600]
            lg = str(v.get("lang") or "ru")[:2]
        except Exception:
            self.reply(400, {"ok": False})
            return
        init = self.headers.get("X-Telegram-Init-Data")
        if init:
            if not verify_init_data(init):
                self.reply(401, {"ok": False})
                return
        elif not INTAKE_KEY or not secrets.compare_digest(str(self.headers.get("X-Intake-Key") or ""), INTAKE_KEY):
            self.reply(401, {"ok": False})
            return
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        if not text or not hits_allowed("ai:" + ip, 15, 600) or not ai_budget(0):
            self.reply(429, {"ok": False, "error": "слишком много запросов"})
            return
        r = ai_pick(text, lg)
        if r is None:
            self.reply(502, {"ok": False})
            return
        self.reply(200, dict(ok=True, **r))

    # ---- «Маис лично»: заявка на премиум-вручение, только админам
    def vip_request(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 8_000:
            self.reply(413, {"ok": False, "error": "пустой или слишком большой запрос"})
            return
        try:
            v = json.loads(self.rfile.read(length).decode())
            assert isinstance(v, dict)
        except Exception:
            self.reply(400, {"ok": False, "error": "битый JSON"})
            return
        chat, uname = None, ""
        init = self.headers.get("X-Telegram-Init-Data")
        if init:
            user = verify_init_data(init)
            if not user or not user.get("id"):
                self.reply(401, {"ok": False, "error": "подпись Telegram не прошла проверку"})
                return
            chat, uname = int(user["id"]), user.get("username") or ""
        else:
            key = self.headers.get("X-Intake-Key") or ""
            if not INTAKE_KEY or not secrets.compare_digest(str(key), INTAKE_KEY):
                self.reply(401, {"ok": False, "error": "неверный ключ"})
                return
        f = {k: str(v.get(k) or "").strip()[:500] for k in ("name", "phone", "recipient", "date", "comment", "lang")}
        if not f["name"] or not f["phone"] or not f["recipient"]:
            self.reply(422, {"ok": False, "error": "нужны имя, телефон и кого поздравляем"})
            return
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        if not reply_allowed("vip:" + ip):
            self.reply(429, {"ok": False, "error": "слишком много заявок"})
            return
        q("INSERT INTO vip_requests(payload,client_chat,created) VALUES(?,?,?)",
          (json.dumps(f, ensure_ascii=False), chat, time.time()))
        when = when_text({"date": f["date"]}) if f["date"] else ""
        notify_admins("👑 <b>Заявка: Маис лично</b> (от $" + esc(v.get("price_from_usd") or 1000) + ")\n\n"
                      f"🙋 {esc(f['name'])}, <code>{esc(f['phone'])}</code>"
                      + (f" · Telegram @{esc(uname)}" if uname else "") + "\n"
                      f"🎁 Кого поздравляем: {esc(f['recipient'])}\n"
                      + (f"📅 Желаемая дата: {esc(when)}\n" if when else "")
                      + (f"📝 {esc(f['comment'])}\n" if f["comment"] else "")
                      + "\nСвяжитесь с клиентом в течение дня и согласуйте дату с Маисом.")
        self.reply(200, {"ok": True})

    # ---- аудио/видео-открытка по QR: доступ даёт только длинный случайный токен
    def card_get(self, rest):
        token, _, sub = rest.partition("/")
        c = card_by_token(urllib.parse.unquote(token))
        if not c:
            self.reply(404, {"ok": False})
            return
        _, o = get_order(c["order_id"])
        o = o or {}
        if sub == "":
            snd = o.get("sender") or {}
            self.reply(200, {"ok": True, "status": "ready" if c["file_id"] else "pending",
                             "from": "" if snd.get("anonymous") else (snd.get("name") or ""),
                             "kind": c["kind"] or "", "lang": lang_of(o)})
            return
        if sub != "media" or not c["file_id"]:
            self.reply(404, {"ok": False})
            return
        path, ctype = card_media_file(c)
        if not path:
            self.reply(502, {"ok": False, "error": "Telegram не отдал запись"})
            return
        preview = "preview=1" in (self.path.split("?", 1)[1] if "?" in self.path else "")
        if not c["opened"] and not preview:
            q("UPDATE cards SET opened=? WHERE token=?", (time.time(), c["token"]))
            if c["client_chat"]:
                send(c["client_chat"], esc(card_tx(o, "opened")))
            notify_admins(f"💌 {esc(c['order_id'])}: получатель открыл аудио/видео-открытку")
        size = os.path.getsize(path)
        start, end = 0, size - 1
        rng = self.headers.get("Range") or ""
        partial = rng.startswith("bytes=")
        if partial:
            a, _, b = rng[6:].split(",")[0].partition("-")
            try:
                if a:
                    start, end = int(a), (int(b) if b else size - 1)
                else:
                    start, end = max(0, size - int(b)), size - 1
            except ValueError:
                partial = False
                start, end = 0, size - 1
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.cors()
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        self.send_response(206 if partial else 200)
        self.cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "private, max-age=3600")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(65536, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def card_manage(self, add):
        """Кабинет: узнать состояние открытки (state) или добавить её к заказу (add).
        Доступ: подпись Telegram владельца заказа или секрет заказа с сайта (manage)."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(n, 4096)) or b"{}") if n else {}
            oid = str(body.get("order_id") or "")[:40]
        except (ValueError, TypeError, AttributeError):
            self.reply(400, {"ok": False, "error": "bad json"})
            return
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        if not hits_allowed("cardm:" + ip, 30, 600):
            self.reply(429, {"ok": False, "error": "слишком часто"})
            return
        row, uid = self.order_owner(oid, body.get("manage"))
        if not row:
            return
        if add:
            err, c = card_add(oid, uid)
            if err:
                self.reply(409 if err == "late" else 404, {"ok": False, "error": err})
                return
        else:
            c = q("SELECT * FROM cards WHERE order_id=?", (oid,), one=True)
        self.reply(200, {"ok": True, "status": row["status"], "media": card_info(c)})

    def order_owner(self, oid, manage):
        """Проверить, что запрос от владельца заказа. (строка заказа, telegram id) или (None, None) — ответ уже отправлен."""
        row = q("SELECT status, client_chat FROM orders WHERE id=?", (oid,), one=True) if oid else None
        uid = None
        if self.headers.get("X-Telegram-Init-Data"):
            uid = self.tg_user()
            if uid is None:
                return None, None
            ok = bool(row) and row["client_chat"] == uid
        else:
            code = q("SELECT code FROM order_codes WHERE order_id=?", (oid,), one=True) if oid else None
            ok = bool(row and code) and secrets.compare_digest(str(manage or ""), code["code"])
        if not ok:
            self.reply(404, {"ok": False, "error": "not_found"})
            return None, None
        return row, uid

    def card_upload(self):
        """Поздравление, записанное прямо на сайте: голос или видео из браузера."""
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        length = int(self.headers.get("Content-Length") or 0)
        if not hits_allowed("cardu:" + ip, 12, 3600):
            self.reply(429, {"ok": False, "error": "слишком часто"})
            return
        if length <= 1000 or length > CARD_UPLOAD_MAX:
            self.reply(413, {"ok": False, "error": "too_big" if length > CARD_UPLOAD_MAX else "empty"})
            return
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        kind = "video" if (self.headers.get("X-Card-Kind") or "") == "video" else "voice"
        if not ctype.startswith(("audio/", "video/")):
            self.reply(415, {"ok": False, "error": "нужна аудио- или видеозапись"})
            return
        oid = urllib.parse.unquote(self.headers.get("X-Order-Id") or "")[:40]
        row, uid = self.order_owner(oid, urllib.parse.unquote(self.headers.get("X-Manage") or ""))
        if not row:
            return
        data = self.rfile.read(length)
        err, c = card_add(oid, uid)
        if err:
            self.reply(409 if err == "late" else 404, {"ok": False, "error": err})
            return
        processing = card_save_upload(c, data, ctype, kind)
        if processing is None:
            self.reply(422, {"ok": False, "error": "запись не читается"})
            return
        c = q("SELECT * FROM cards WHERE order_id=?", (oid,), one=True)
        self.reply(200, {"ok": True, "processing": processing, "media": card_info(c)})

    def card_reply(self, token):
        c = card_by_token(urllib.parse.unquote(token))
        if not c:
            self.reply(404, {"ok": False})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > CARD_REPLY_MAX:
            self.reply(413, {"ok": False, "error": "пустая или слишком длинная запись"})
            return
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        if not reply_allowed(ip) or (c["replies"] or 0) >= 5:
            self.reply(429, {"ok": False, "error": "слишком много ответов"})
            return
        data = self.rfile.read(length)
        ctype = (self.headers.get("Content-Type") or "audio/webm").split(";")[0]
        if not ctype.startswith(("audio/", "video/")):
            self.reply(415, {"ok": False, "error": "нужна аудиозапись"})
            return
        if not deliver_card_reply(c, data, ctype):
            self.reply(502, {"ok": False, "error": "не удалось передать ответ"})
            return
        q("UPDATE cards SET replies=COALESCE(replies,0)+1 WHERE token=?", (c["token"],))
        self.reply(200, {"ok": True})

    def log_message(self, fmt, *args):
        log.info("http %s", fmt % args)


# ---------------------------------------------------------------- аудио/видео-открытка по QR

CARD_TX = {
    "ru": {"ask": "🎙 Запишите поздравление для открытки к заказу {id}: голосовое, кружок или видео, прямо сюда в чат. "
                  "На открытке будет QR-код, получатель наведёт камеру и услышит вас.",
           "saved": "Сохранил ✅ Получатель увидит это поздравление по QR-коду на открытке.\n"
                    "Хотите перезаписать — просто пришлите новое до доставки.",
           "late": "Букет уже доставлен, поздравление менять нельзя.",
           "busy": "Эта ссылка уже привязана к другому аккаунту Telegram.",
           "bad": "Ссылка для записи не найдена. Напишите нам, поможем.",
           "big": "Видео слишком большое (больше 20 МБ). Запишите покороче или кружком.",
           "listen": "▶️ Как это увидит получатель",
           "opened": "💌 Получатель открыл ваше поздравление 🤍",
           "reply": "💌 Ответ на ваше поздравление (заказ {id})"},
    "en": {"ask": "🎙 Record a greeting for the card in order {id}: a voice message, a video note or a video, right here. "
                  "The card gets a QR code, the recipient points the camera and hears you.",
           "saved": "Saved ✅ The recipient will open this greeting from the QR code on the card.\n"
                    "Want to redo it? Just send a new one before delivery.",
           "late": "The bouquet is already delivered, the greeting can no longer be changed.",
           "busy": "This link is already tied to another Telegram account.",
           "bad": "Recording link not found. Message us and we will help.",
           "big": "The video is too large (over 20 MB). Record a shorter one or a video note.",
           "listen": "▶️ See it as the recipient",
           "opened": "💌 The recipient opened your greeting 🤍",
           "reply": "💌 A reply to your greeting (order {id})"},
    "hy": {"ask": "🎙 Ձայնագրեք շնորհավորանք {id} պատվերի բացիկի համար՝ ձայնային, շրջանակ կամ տեսանյութ, հենց այստեղ: "
                  "Բացիկին կլինի QR կոդ, ստացողը կուղղի տեսախցիկը և կլսի ձեզ:",
           "saved": "Պահպանված է ✅ Ստացողը կտեսնի շնորհավորանքը բացիկի QR կոդով:\n"
                    "Ուզում եք նորից ձայնագրել, պարզապես ուղարկեք նորը մինչև առաքումը:",
           "late": "Ծաղկեփունջն արդեն առաքված է, շնորհավորանքը փոխել հնարավոր չէ:",
           "busy": "Այս հղումն արդեն կապված է այլ Telegram հաշվի հետ:",
           "bad": "Ձայնագրման հղումը չի գտնվել: Գրեք մեզ, կօգնենք:",
           "big": "Տեսանյութը չափազանց մեծ է (20 ՄԲ-ից ավելի): Ձայնագրեք ավելի կարճ կամ շրջանակով:",
           "listen": "▶️ Ինչպես կտեսնի ստացողը",
           "opened": "💌 Ստացողը բացեց ձեր շնորհավորանքը 🤍",
           "reply": "💌 Պատասխան ձեր շնորհավորանքին ({id} պատվեր)"},
}
REPLY_HITS = {}


def card_tx(o, key):
    return CARD_TX[lang_of(o)][key].format(id=o.get("id", ""))


def card_url(token):
    base = (WEBAPP_URL or "").split("?")[0].rstrip("/")
    return f"{base}/card.html?c={token}"


def card_by_token(token):
    if not token or len(token) > 64:
        return None
    return q("SELECT * FROM cards WHERE token=?", (token,), one=True)


def make_card(order_id, o, client_chat):
    token, rec = secrets.token_urlsafe(16), secrets.token_urlsafe(9)
    q("INSERT OR IGNORE INTO cards(token,order_id,rec_code,client_chat,created) VALUES(?,?,?,?,?)",
      (token, order_id, rec, client_chat, time.time()))
    if client_chat:
        q("INSERT OR REPLACE INTO waiting_card(chat_id,token) VALUES(?,?)", (client_chat, token))
        send(client_chat, esc(card_tx(o, "ask")))
    notify_admins(f"🎙 {esc(order_id)}: заказ с аудио/видео-открыткой\n{esc(card_url(token))}")


def card_add(order_id, client_chat=None):
    """Аудио/видео-открытка к уже оформленному заказу (из личного кабинета).
    Возвращает (код ошибки или None, данные карточки)."""
    row, o = get_order(order_id)
    if not row:
        return "not_found", None
    if row["status"] in ("delivered", "cancelled"):
        return "late", None
    c = q("SELECT * FROM cards WHERE order_id=?", (order_id,), one=True)
    if not c:
        token, rec = secrets.token_urlsafe(16), secrets.token_urlsafe(9)
        q("INSERT OR IGNORE INTO cards(token,order_id,rec_code,client_chat,created) VALUES(?,?,?,?,?)",
          (token, order_id, rec, client_chat or row["client_chat"], time.time()))
        card = dict(o.get("card") or {})
        old = card.get("text") if card.get("type") == "text" else ""
        o["card"] = {"type": "media", "text": old or "🎙 Аудио/видео-открытка (добавлена из кабинета)"}
        q("UPDATE orders SET payload=? WHERE id=?", (json.dumps(o, ensure_ascii=False), order_id))
        notify_admins(f"🎙 {esc(order_id)}: клиент добавил аудио/видео-открытку из кабинета\n{esc(card_url(token))}")
        if row["studio_id"] and row["status"] not in ("new", "offered", "unassigned"):
            st = q("SELECT chat_id FROM studios WHERE id=?", (row["studio_id"],), one=True)
            if st:
                send(st["chat_id"], f"🎙 К заказу {esc(order_id)} клиент добавил аудио/видео-поздравление. "
                                    "Распечатайте QR-код ниже и вложите в букет."
                                    + (f"\n💌 Текст открытки остаётся: «{esc(old)}»" if old else ""))
                send_card_qr(st["chat_id"], order_id)
        c = q("SELECT * FROM cards WHERE order_id=?", (order_id,), one=True)
    return None, c


def card_info(c):
    """Состояние открытки для кабинета."""
    if not c:
        return None
    return {"recorded": bool(c["file_id"]), "kind": c["kind"] or "", "processing": c["token"] in CARD_PROCESSING,
            "listen": card_url(c["token"]) + "&me=1" if c["file_id"] else "",
            "record_link": f"https://t.me/{BOT_USERNAME}?start=rec_{c['rec_code']}"}


def card_start(chat, m, rec):
    c = q("SELECT * FROM cards WHERE rec_code=?", (rec,), one=True)
    lg = user_lang(m.get("from") or {})
    if not c:
        send(chat, esc(CARD_TX.get(lg, CARD_TX["ru"])["bad"]))
        return
    _, o = get_order(c["order_id"])
    o = o or {"lang": lg}
    if c["client_chat"] and c["client_chat"] != chat:
        send(chat, esc(card_tx(o, "busy")))
        return
    q("UPDATE cards SET client_chat=? WHERE token=?", (chat, c["token"]))
    q("UPDATE orders SET client_chat=COALESCE(client_chat, ?) WHERE id=?", (chat, c["order_id"]))
    q("INSERT OR REPLACE INTO waiting_card(chat_id,token) VALUES(?,?)", (chat, c["token"]))
    if o.get("remind") and o.get("id") and not q("SELECT 1 FROM reminders WHERE order_id=?", (o["id"],), one=True):
        add_reminder(o, chat)
    send(chat, esc(card_tx(o, "ask")))


def card_media_in(chat, m, media):
    """Голосовое, кружок или видео от клиента, который записывает открытку. True, если обработали."""
    w = q("SELECT * FROM waiting_card WHERE chat_id=?", (chat,), one=True)
    if not w:
        return False
    c = card_by_token(w["token"])
    if not c:
        return False
    row, o = get_order(c["order_id"])
    o = o or {}
    if row and row["status"] in ("delivered", "cancelled"):
        q("DELETE FROM waiting_card WHERE chat_id=?", (chat,))
        send(chat, esc(card_tx(o, "late")))
        return True
    if (media.get("file_size") or 0) > 20_000_000:
        send(chat, esc(card_tx(o, "big")))
        return True
    kind = "voice" if (m.get("voice") or m.get("audio")) else ("video_note" if m.get("video_note") else "video")
    q("UPDATE cards SET file_id=?, kind=?, recorded=? WHERE token=?",
      (media["file_id"], kind, time.time(), c["token"]))
    send(chat, esc(card_tx(o, "saved")), [[(card_tx(o, "listen"), "url:" + card_url(c["token"]) + "&me=1")]])
    notify_admins(f"🎙 {esc(c['order_id'])}: клиент записал поздравление ({kind})")
    return True


def qr_png(text):
    try:
        import io
        import qrcode
        img = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=4)
        img.add_data(text)
        img.make(fit=True)
        buf = io.BytesIO()
        img.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        log.warning("QR не сгенерирован: %s", e)
        return None


def send_card_qr(chat, order_id):
    c = q("SELECT * FROM cards WHERE order_id=?", (order_id,), one=True)
    if not c:
        return
    url = card_url(c["token"])
    caption = (f"🎙 QR-код для открытки к заказу {order_id}.\n"
               "Распечатайте (примерно 3×3 см) и вложите в букет вместе с открыткой. "
               "Подпись рядом: «Наведите камеру — здесь поздравление для вас».")
    png = qr_png(url)
    if png and tg_upload("sendPhoto", "photo", f"qr-{order_id}.png", png, "image/png",
                         chat_id=chat, caption=caption):
        if png:
            tg_upload("sendDocument", "document", f"qr-{order_id}.png", png, "image/png",
                      chat_id=chat, caption="Файл для печати без сжатия")
        return
    send(chat, esc(caption) + f"\n\nСсылка для QR-кода: {esc(url)}")


def _download_tg(file_id):
    f = tg("getFile", file_id=file_id)
    if not f or not f.get("file_path"):
        return None
    try:
        with urllib.request.urlopen(f"{API_BASE}/file/bot{BOT_TOKEN}/{f['file_path']}", timeout=60) as r:
            return r.read()
    except Exception as e:
        log.warning("file download failed: %s", e)
        return None


def _ffmpeg(args, data, timeout=120):
    if not shutil.which("ffmpeg"):
        return None
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", *args, "pipe:1"],
                           input=data, capture_output=True, timeout=timeout)
        return r.stdout if r.returncode == 0 and r.stdout else None
    except Exception as e:
        log.warning("ffmpeg failed: %s", e)
        return None


def _ffmpeg_file(args, data, suffix, timeout=120):
    """ffmpeg во временный файл: нужен для +faststart, через pipe он не работает."""
    if not shutil.which("ffmpeg"):
        return None
    import tempfile
    fd, out = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", "pipe:0", *args, out],
                           input=data, capture_output=True, timeout=timeout)
        if r.returncode == 0 and os.path.getsize(out) > 0:
            with open(out, "rb") as f:
                return f.read()
    except Exception as e:
        log.warning("ffmpeg failed: %s", e)
    finally:
        try:
            os.remove(out)
        except OSError:
            pass
    return None


CARD_PROCESSING = set()


def _ffmpeg_path(src, args, dst, timeout=300):
    """ffmpeg с файла на файл: MP4 с iPhone нельзя читать из pipe, у него индекс в конце."""
    if not shutil.which("ffmpeg"):
        return False
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, *args, dst],
                           capture_output=True, timeout=timeout)
        return r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0
    except Exception as e:
        log.warning("ffmpeg failed: %s", e)
        return False


def card_save_upload(c, data, ctype, kind):
    """Сохранить запись с сайта и перекодировать в формат, который играет и iPhone, и Android.
    Голос — сразу (секунды). Видео — в фоне, пока идёт перекодировка, открытка ждёт.
    True — видео обрабатывается, False — готово, None — запись не читается."""
    os.makedirs(MEDIA_DIR, exist_ok=True)
    stamp = secrets.token_hex(4)
    ext = {"audio/mp4": "m4a", "video/mp4": "mp4", "audio/ogg": "ogg", "audio/mpeg": "mp3"}.get(ctype, "webm")
    raw = os.path.join(MEDIA_DIR, f"{c['token']}-raw{stamp}.{ext}")
    with open(raw, "wb") as f:
        f.write(data)

    def finish(out):
        prev = q("SELECT file_id FROM cards WHERE token=?", (c["token"],), one=True)
        q("UPDATE cards SET file_id=?, kind=?, recorded=? WHERE token=?", ("local:" + out, kind, time.time(), c["token"]))
        if prev and (prev["file_id"] or "").startswith("local:") and prev["file_id"][6:] != out:
            _rm(prev["file_id"][6:])  # прошлая запись с сайта больше не нужна
        _, o = get_order(c["order_id"])
        notify_admins(f"🎙 {esc(c['order_id'])}: клиент записал поздравление на сайте ({kind})")
        if c["client_chat"]:
            send(c["client_chat"], esc(card_tx(o or {}, "saved")), [[(card_tx(o or {}, "listen"), "url:" + card_url(c["token"]) + "&me=1")]])

    if kind == "voice":
        out = os.path.join(MEDIA_DIR, f"{c['token']}-web{stamp}.m4a")
        ok = _ffmpeg_path(raw, ["-vn", "-t", "62", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart"], out, 120)
        if not ok:
            if ext != "m4a":  # без перекодировки годится только M4A (его пишет Safari)
                _rm(raw)
                return None
            out = raw
        else:
            _rm(raw)
        finish(out)
        return False

    out = os.path.join(MEDIA_DIR, f"{c['token']}-web{stamp}.mp4")

    def work():
        try:
            ok = _ffmpeg_path(raw, ["-t", "62", "-vf", "scale='min(720,iw)':-2,format=yuv420p", "-c:v", "libx264",
                                    "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "96k",
                                    "-movflags", "+faststart"], out, 600)
            if ok:
                _rm(raw)
                finish(out)
            else:
                log.warning("видео-открытка %s не перекодировалась", c["order_id"])
                _rm(raw)
                notify_admins(f"⚠️ {esc(c['order_id'])}: видео-поздравление с сайта не удалось обработать")
        finally:
            CARD_PROCESSING.discard(c["token"])

    CARD_PROCESSING.add(c["token"])
    threading.Thread(target=work, daemon=True).start()
    return True


def _rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


def card_media_file(c):
    """Путь к записи на диске (скачивает из Telegram при первом запросе) и её Content-Type.
    Голосовые Telegram (OGG/Opus) перекодируются в M4A, их играет и iPhone."""
    os.makedirs(MEDIA_DIR, exist_ok=True)
    if c["file_id"].startswith("local:"):
        path = c["file_id"][6:]
        if not os.path.exists(path):
            return None, None
        return path, {"m4a": "audio/mp4", "mp4": "video/mp4", "ogg": "audio/ogg"}.get(path.rsplit(".", 1)[-1], "application/octet-stream")
    tag = hashlib.sha1(c["file_id"].encode()).hexdigest()[:10]
    voice = c["kind"] == "voice"
    for ext, ctype in ((("m4a", "audio/mp4"), ("ogg", "audio/ogg")) if voice else (("mp4", "video/mp4"),)):
        path = os.path.join(MEDIA_DIR, f"{c['token']}-{tag}.{ext}")
        if os.path.exists(path):
            return path, ctype
    data = _download_tg(c["file_id"])
    if not data:
        return None, None
    if voice:
        m4a = _ffmpeg_file(["-vn", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart"], data, ".m4a")
        ext, ctype, out = ("m4a", "audio/mp4", m4a) if m4a else ("ogg", "audio/ogg", data)
    else:
        ext, ctype, out = "mp4", "video/mp4", data
    path = os.path.join(MEDIA_DIR, f"{c['token']}-{tag}.{ext}")
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(out)
    os.replace(tmp, path)
    return path, ctype


def hits_allowed(key, limit, window):
    now = time.time()
    hits = [t for t in REPLY_HITS.get(key, []) if now - t < window]
    if len(hits) >= limit:
        REPLY_HITS[key] = hits
        return False
    hits.append(now)
    REPLY_HITS[key] = hits
    return True


def reply_allowed(ip):
    return hits_allowed(ip, 5, 600)


def deliver_card_reply(c, data, ctype):
    _, o = get_order(c["order_id"])
    o = o or {}
    caption = card_tx(o, "reply")
    targets = [c["client_chat"]] if c["client_chat"] else ADMIN_IDS
    ogg = _ffmpeg(["-vn", "-c:a", "libopus", "-b:a", "48k", "-f", "ogg"], data)
    ok = False
    for chat in targets:
        if ogg:
            r = tg_upload("sendVoice", "voice", "reply.ogg", ogg, "audio/ogg", chat_id=chat, caption=caption)
        else:
            ext = "mp4" if "mp4" in ctype else ("ogg" if "ogg" in ctype else "webm")
            r = tg_upload("sendDocument", "document", f"reply.{ext}", data, ctype, chat_id=chat, caption=caption)
        ok = ok or bool(r)
    if c["client_chat"]:
        notify_admins(f"💌 {esc(c['order_id'])}: получатель ответил голосом на открытку")
    return ok


# ---------------------------------------------------------------- умный помощник (Claude API)

AI_TX = {
    "ru": {"human": "👩 Позвать человека", "bot": "🤖 Вернуть помощника", "order": "🛒 Заказать",
           "handoff": "Передал вопрос менеджеру, он ответит здесь же 🌸",
           "back": "Снова на связи помощник 🤖 Пишите, что ищете: кому, повод, бюджет.",
           "busy": "Помощник сейчас перегружен, передал ваш вопрос менеджеру 🌸",
           "card": "💌 Текст для открытки"},
    "en": {"human": "👩 Talk to a person", "bot": "🤖 Back to the assistant", "order": "🛒 Order",
           "handoff": "I passed your question to a manager, they will reply right here 🌸",
           "back": "The assistant is back 🤖 Tell me who it is for, the occasion and your budget.",
           "busy": "The assistant is busy right now, I passed your question to a manager 🌸",
           "card": "💌 Card text"},
    "hy": {"human": "👩 Կանչել մարդու", "bot": "🤖 Վերադարձնել օգնականին", "order": "🛒 Պատվիրել",
           "handoff": "Հարցը փոխանցեցի մենեջերին, նա կպատասխանի այստեղ 🌸",
           "back": "Օգնականը կրկին կապի մեջ է 🤖 Գրեք՝ ում համար, առիթը և բյուջեն:",
           "busy": "Օգնականն այժմ ծանրաբեռնված է, հարցը փոխանցեցի մենեջերին 🌸",
           "card": "💌 Բացիկի տեքստ"},
}
LANG_NAME = {"ru": "русском", "en": "английском", "hy": "армянском"}


def ai_catalog():
    rate = CATALOG.get("rate_amd", 390)
    rows = []
    for i in CATALOG.get("items", []):
        rows.append({"id": i["id"], "name": i["n"].get("ru"), "name_en": i["n"].get("en"), "name_hy": i["n"].get("hy"),
                     "composition": i["k"].get("ru"), "usd": i["usd"],
                     "amd": round(i["usd"] * rate / 100) * 100, "occasions": i.get("occ", [])})
    return json.dumps(rows, ensure_ascii=False)


def ai_system():
    return (
        "Ты — консультант цветочного сервиса MayFlowers by Mais в Ереване. Это доставка цветов и не только "
        "от блогера Маиса Варданяна, который дарит цветы незнакомым людям. Слоган: «Дари добро. Дари цветы.»\n"
        "Правила:\n"
        "- Советуй только букеты из каталога ниже, по их id. Цены бери только из каталога, ничего не выдумывай.\n"
        "- Никогда не упоминай студии, партнёров, подрядчиков или флористов со стороны. Для клиента всё делает MayFlowers.\n"
        "- Доставка по Еревану $3: соберём за час или привезём к точному времени. Фото готового букета приходит до доставки.\n"
        "- Дополнительно есть: «Букет в добрые руки» (букет дарим случайному прохожему от имени клиента и присылаем видео), "
        "аудио или видео поздравление по QR-коду на открытке, «Маис лично» (Маис сам привозит букет, от $1000, по заявке на сайте), "
        "особые большие букеты от $500 через менеджера.\n"
        "- Отвечай тепло и коротко, 1–3 предложения, без списков и markdown. Пиши на языке клиента. "
        "Говори только о букетах, которые предлагаешь; неподходящие не упоминай.\n"
        "- Не обсуждай темы, не связанные с цветами, подарками и заказом: вежливо верни разговор к цветам.\n"
        "- Поставь human=true, если клиент просит человека или менеджера, жалуется, спрашивает про уже оформленный заказ, "
        "оплату, возврат, корпоративный или нестандартный заказ, или ты не можешь помочь.\n"
        "Каталог (JSON):\n" + ai_catalog()
    )


def ai_call(system, messages, max_tokens=1000):
    # thinking выключен: для консультаций он не нужен, а ответ без него быстрее и не обрезается по max_tokens
    body = {"model": AI_MODEL, "max_tokens": max_tokens, "thinking": {"type": "disabled"},
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.loads(r.read().decode())
        if d.get("stop_reason") == "max_tokens":
            log.warning("claude api: ответ обрезан по max_tokens")
        return "".join(c.get("text", "") for c in d.get("content", []) if c.get("type") == "text")
    except urllib.error.HTTPError as e:
        try:
            log.warning("claude api %s: %s", e.code, e.read().decode()[:300])
        except Exception:
            log.warning("claude api %s", e.code)
    except Exception as e:
        log.warning("claude api failed: %s", e)
    return None


def ai_json(text):
    if not text:
        return None
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        return json.loads(text[a:b + 1])
    except ValueError:
        return None


def ai_budget(chat):
    """True и +1 к счётчику, если не превышены лимиты на клиента и на сутки."""
    day = local_now().strftime("%Y-%m-%d")
    total = q("SELECT COALESCE(SUM(n),0) AS n FROM ai_usage WHERE day=?", (day,), one=True)["n"]
    mine = q("SELECT n FROM ai_usage WHERE day=? AND chat=?", (day, chat), one=True)
    if total >= AI_DAILY_CAP or (chat and mine and mine["n"] >= AI_USER_DAILY):
        return False
    q("INSERT INTO ai_usage(day,chat,n) VALUES(?,?,1) ON CONFLICT(day,chat) DO UPDATE SET n=n+1", (day, chat))
    return True


def valid_ids():
    return {i["id"] for i in CATALOG.get("items", [])}


def ai_pick(text, lg):
    """Один запрос с сайта: до 3 букетов, короткий ответ и текст открытки."""
    lg = lg if lg in LANG_NAME else "ru"
    prompt = (f"Покупатель на сайте написал:\n\"\"\"{text}\"\"\"\n\nПодбери до 3 букетов из каталога по поводу, получателю, "
              f"вкусам и бюджету; бюджет не превышай. Пиши на {LANG_NAME[lg]} языке.\n"
              'Ответь только JSON: {"reply":"1–2 предложения","picks":[{"id":число,"why":"до 15 слов"}],'
              '"card":"текст открытки 1–2 предложения или пустая строка"}')
    d = ai_json(ai_call(ai_system(), [{"role": "user", "content": prompt}]))
    if d is None:
        return None
    ok = valid_ids()
    picks = [{"id": int(x.get("id")), "why": str(x.get("why") or "")[:200]}
             for x in (d.get("picks") or []) if isinstance(x, dict) and str(x.get("id", "")).isdigit() and int(x["id"]) in ok][:3]
    return {"reply": str(d.get("reply") or "")[:600], "picks": picks, "card": str(d.get("card") or "")[:300]}


def human_active(chat):
    r = q("SELECT until FROM human_mode WHERE chat=?", (chat,), one=True)
    return bool(r and r["until"] > time.time())


def set_human(chat, on):
    if on:
        q("INSERT OR REPLACE INTO human_mode(chat,until) VALUES(?,?)", (chat, time.time() + HUMAN_HOURS * 3600))
    else:
        q("DELETE FROM human_mode WHERE chat=?", (chat,))


def ai_chat(chat, m, text):
    """Диалог с клиентом в боте. False — не получилось, тогда сообщение уйдёт человеку."""
    lg = user_lang(m.get("from"))
    T = AI_TX[lg]
    if not ai_budget(chat):
        return False
    tg("sendChatAction", chat_id=chat, action="typing")
    q("INSERT INTO ai_msgs(chat,role,content,ts) VALUES(?,?,?,?)", (chat, "user", text[:2000], time.time()))
    hist = list(reversed(q("SELECT role, content FROM ai_msgs WHERE chat=? AND ts>? ORDER BY id DESC LIMIT 12",
                           (chat, time.time() - 86400 * 2))))
    msgs = []
    for h in hist:
        if msgs and msgs[-1]["role"] == h["role"]:
            msgs[-1]["content"] += "\n" + h["content"]
        else:
            msgs.append({"role": h["role"], "content": h["content"]})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    msgs[-1]["content"] += ("\n\n[Ответь только JSON: {\"reply\":\"ответ клиенту на " + LANG_NAME[lg] + " языке\","
                            "\"picks\":[id букетов, до 3, только если уместно показать букеты],"
                            "\"card\":\"текст открытки, если клиент просил, иначе пусто\",\"human\":true|false}]")
    d = ai_json(ai_call(ai_system(), msgs))
    if d is None:
        return False
    reply = str(d.get("reply") or "").strip()[:1500]
    ok = valid_ids()
    picks = [int(x) for x in (d.get("picks") or []) if str(x).isdigit() and int(x) in ok][:3]
    q("INSERT INTO ai_msgs(chat,role,content,ts) VALUES(?,?,?,?)",
      (chat, "assistant", json.dumps({"reply": reply, "picks": picks}, ensure_ascii=False), time.time()))
    if d.get("human"):
        send(chat, esc(reply) if reply else esc(T["handoff"]))
        handoff(chat, m, text)
        return True
    items = {i["id"]: i for i in CATALOG.get("items", [])}
    rate = CATALOG.get("rate_amd", 390)
    for pid in picks:
        it = items[pid]
        amd = f"{round(it['usd'] * rate / 100) * 100:,}".replace(",", "\u00a0")
        cap = f"<b>{esc(it['n'].get(lg) or it['n']['ru'])}</b>\n{esc(it['k'].get(lg) or it['k']['ru'])}\n\n<b>${it['usd']}</b> · {amd} ֏"
        rows = [[(T["order"], "webapp:" + shop_url(add=pid))]] if WEBAPP_URL else None
        if WEBAPP_URL:
            tg("sendPhoto", chat_id=chat, photo=urllib.parse.urljoin(WEBAPP_URL, it["img"]), caption=cap,
               parse_mode="HTML", reply_markup=kb(rows))
        else:
            send(chat, cap)
    card_txt = str(d.get("card") or "").strip()[:400]
    out = esc(reply or "🌸") + (f"\n\n{esc(T['card'])}: «{esc(card_txt)}»" if card_txt else "")
    send(chat, out, [[(T["human"], "ai:human")]])
    return True


def handoff(chat, m, text):
    """Передать диалог человеку: ИИ молчит HUMAN_HOURS часов, сообщения идут админам."""
    lg = user_lang(m.get("from") if m else {})
    set_human(chat, True)
    frm = (m or {}).get("from") or {}
    name = " ".join(x for x in [frm.get("first_name"), frm.get("last_name")] if x) or "клиент"
    user = f" @{esc(frm['username'])}" if frm.get("username") else ""
    last = q("SELECT role, content FROM ai_msgs WHERE chat=? ORDER BY id DESC LIMIT 6", (chat,))
    lines = []
    for r in reversed(last):
        c = r["content"]
        if r["role"] == "assistant":
            try:
                c = json.loads(c).get("reply", c)
            except ValueError:
                pass
        lines.append(("👤 " if r["role"] == "user" else "🤖 ") + esc(str(c)[:400]))
    notify_admins(f"🙋 {esc(name)}{user} просит человека\n\n" + ("\n".join(lines) or esc(text[:1000])),
                  buttons=[[("✍️ Ответить", f"adm:rp:{chat}")]])
    send(chat, esc(AI_TX[lg]["handoff"]), [[(AI_TX[lg]["bot"], "ai:bot")]])


def ai_callback(cb, act, answer):
    chat = cb["message"]["chat"]["id"]
    lg = user_lang(cb.get("from"))
    if act == "human":
        handoff(chat, {"from": cb.get("from") or {}}, "")
    elif act == "bot":
        set_human(chat, False)
        send(chat, esc(AI_TX[lg]["back"]))
    answer()


def cabinet(uid):
    """Всё для личного кабинета клиента в мини-апке."""
    orders, people = [], {}
    for r in q("SELECT * FROM orders WHERE client_chat=? ORDER BY created DESC LIMIT 50", (uid,)):
        o = json.loads(r["payload"])
        rec = o.get("recipient") or {}
        orders.append({
            "id": r["id"], "status": r["status"], "created": int(r["created"]),
            "items": [{"sku": i.get("sku"), "name": i.get("name"), "qty": i.get("qty", 1),
                       "price_usd": i.get("price_usd")} for i in o.get("items", [])],
            "total_usd": o.get("total_usd"), "delivery": o.get("delivery") or {},
            "recipient": {"name": rec.get("name"), "address": rec.get("address"), "phone": rec.get("phone")},
            "occasion": o.get("occasion"), "card": o.get("card") or {}, "kindness": bool(o.get("kindness")),
            "has_photo": bool(r["photo"]),
            "media": card_info(q("SELECT * FROM cards WHERE order_id=?", (r["id"],), one=True)),
        })
        key = (rec.get("name"), rec.get("phone"), rec.get("address"))
        if rec.get("phone") and key not in people:
            people[key] = {"name": rec.get("name"), "phone": rec.get("phone"), "address": rec.get("address")}
    rem = [{"id": r["id"], "target": r["target"], "label": r["label"]}
           for r in q("SELECT * FROM reminders WHERE chat_id=? ORDER BY target", (uid,))]
    return {"ok": True, "orders": orders, "reminders": rem, "recipients": list(people.values())}


def download_photo(file_id):
    f = tg("getFile", file_id=file_id)
    if not f or not f.get("file_path"):
        return None
    try:
        with urllib.request.urlopen(f"{API_BASE}/file/bot{BOT_TOKEN}/{f['file_path']}", timeout=20) as r:
            return r.read()
    except Exception as e:
        log.warning("photo download failed: %s", e)
        return None


def sample_order():
    return {
        "test": True,
        "items": [{"name": "Пионовое облако", "qty": 1, "price_usd": 110,
                   "composition": "Пионы, пионовидные розы, гортензия"}],
        "total_usd": 113, "payout_usd": 77,
        "delivery": {"date": datetime.now().strftime("%Y-%m-%d"), "window": "14:00–16:00"},
        "recipient": {"name": "Анна", "phone": "+374 00 000000", "address": "Ереван, ул. Абовяна 1 (тест)"},
        "sender": {"name": "Тест", "phone": "+374 00 000001", "anonymous": False},
        "occasion": "mom",
        "card": {"type": "text", "text": "Мама, с праздником! Это тестовый заказ."},
        "wrapping": {"paper": "Фирменный крафт May Flowers", "ribbon": "Розовая атласная лента"},
        "kindness": True,
        "comment": "Тестовый заказ, не собирать",
        "payment": {"method": "test", "status": "test"},
    }


# ---------------------------------------------------------------- запуск

BOT_USERNAME = "bot"


def main():
    global BOT_USERNAME
    if not BOT_TOKEN:
        raise SystemExit("Нет BOT_TOKEN. Получите токен у @BotFather и передайте BOT_TOKEN=...")
    if not ADMIN_IDS:
        log.warning("ADMIN_IDS пуст: никто не сможет приглашать студии. Узнать свой ID: напишите боту /myid")
    if not INTAKE_KEY:
        log.warning("INTAKE_KEY пуст: приём заказов с сайта выключен")
    init_db()
    me = tg("getMe")
    if not me:
        raise SystemExit("Telegram не принял токен или недоступен")
    BOT_USERNAME = me["username"]
    tg("deleteWebhook")
    load_catalog()
    log.info("каталог: %s букетов", len(CATALOG.get("items", [])))
    threading.Thread(target=catalog_loop, daemon=True).start()
    tg("setMyCommands", commands=[
        {"command": "start", "description": "Начать"},
        {"command": "catalog", "description": "Каталог букетов"},
        {"command": "orders", "description": "Мои заказы"},
    ])
    if WEBAPP_URL:
        tg("setChatMenuButton", menu_button={"type": "web_app", "text": "Магазин", "web_app": {"url": WEBAPP_URL}})
    else:
        log.warning("WEBAPP_URL пуст: у клиентов не будет кнопки магазина")
    threading.Thread(target=expire_loop, daemon=True).start()
    threading.Thread(target=reminder_loop, daemon=True).start()
    server = ThreadingHTTPServer((BIND_HOST, PORT), Intake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("@%s запущен, приём заказов на :%s/api/orders", BOT_USERNAME, PORT)
    poll_loop()


if __name__ == "__main__":
    main()
