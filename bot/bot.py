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
import sqlite3
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
        return {"text": t, "callback_data": d}
    return {"inline_keyboard": [[btn(t, d) for t, d in row] for row in buttons]}


def notify_admins(text, photo=None):
    for a in ADMIN_IDS:
        if photo:
            tg("sendPhoto", chat_id=a, photo=photo, caption=text[:1024], parse_mode="HTML")
        else:
            send(a, text)


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
        CREATE TABLE IF NOT EXISTS reminders(
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, order_id TEXT, target TEXT,
            label TEXT, lang TEXT, sent7 INTEGER DEFAULT 0, sent1 INTEGER DEFAULT 0);
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
    if c.get("text"):
        lines.append(f"💌 Открытка: «{esc(c['text'])}»")
    else:
        lines.append("💌 Открытка: без открытки")
    if (o.get("sender") or {}).get("anonymous"):
        lines.append("🤫 Анонимно: не подписывать от кого")
    if o.get("occasion"):
        lines.append(f"🎉 Повод: {esc(OCCASIONS.get(o['occasion'], o['occasion']))}")
    if o.get("kindness"):
        lines.append("🤍 + Букет добра: мини-букет для вручения незнакомцу")
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
        "hello": "Привет! Это May Flowers 🌸 Цветы с доставкой по Еревану от партнёрских студий.\n\nНажмите «Открыть магазин», выберите букет и оформите заказ. Здесь же я пришлю фото вашего букета перед доставкой.",
        "open": "🌸 Открыть магазин",
        "soon": "Магазин скоро откроется.",
        "received": "Заказ {id} принят ✅\nИщем студию, которая соберёт ваш букет. Напишу, как только начнут.",
        "accepted": "Студия начала собирать ваш букет по заказу {id} 💐",
        "built": "Ваш букет готов! Вот он 👇\nЗаказ {id}, скоро передадим курьеру.",
        "courier": "Курьер уже везёт букет по заказу {id} 🚗",
        "delivered": "Букет по заказу {id} доставлен 🌸 Спасибо, что дарите добро!",
        "cancelled": "Заказ {id} отменён. Менеджер свяжется с вами.",
        "none": "У вас пока нет заказов.",
        "r7": "Через неделю повод, на который вы год назад дарили цветы: {label}. Подобрать букет заранее?",
        "r1": "Завтра {label}! Ещё успеем доставить букет.",
        "again": "💐 Выбрать букет",
    },
    "en": {
        "hello": "Hi! This is May Flowers 🌸 Flower delivery across Yerevan from partner studios.\n\nTap “Open shop”, pick a bouquet and place an order. I will send you a photo of your bouquet here before delivery.",
        "open": "🌸 Open shop",
        "soon": "The shop opens soon.",
        "received": "Order {id} received ✅\nWe are finding a studio for your bouquet. I will write as soon as they start.",
        "accepted": "A studio has started your bouquet for order {id} 💐",
        "built": "Your bouquet is ready! Here it is 👇\nOrder {id}, handing it to the courier soon.",
        "courier": "The courier is on the way with order {id} 🚗",
        "delivered": "Order {id} delivered 🌸 Thank you for giving kindness!",
        "cancelled": "Order {id} was cancelled. A manager will contact you.",
        "none": "You have no orders yet.",
        "r7": "In a week, the occasion you sent flowers for last year: {label}. Pick a bouquet in advance?",
        "r1": "Tomorrow: {label}! There is still time to deliver flowers.",
        "again": "💐 Pick a bouquet",
    },
    "hy": {
        "hello": "Բարև։ Սա May Flowers-ն է 🌸 Ծաղիկների առաքում Երևանով գործընկեր ստուդիաներից։\n\nՍեղմեք «Բացել խանութը», ընտրեք ծաղկեփունջ և պատվիրեք։ Այստեղ կուղարկեմ ձեր ծաղկեփնջի լուսանկարը առաքումից առաջ։",
        "open": "🌸 Բացել խանութը",
        "soon": "Խանութը շուտով կբացվի։",
        "received": "Պատվեր {id}-ն ընդունված է ✅\nՓնտրում ենք ստուդիա։ Կգրեմ, հենց սկսեն։",
        "accepted": "Ստուդիան սկսեց հավաքել ձեր ծաղկեփունջը, պատվեր {id} 💐",
        "built": "Ձեր ծաղկեփունջը պատրաստ է։ Ահա այն 👇\nՊատվեր {id}",
        "courier": "Առաքիչը ճանապարհին է, պատվեր {id} 🚗",
        "delivered": "Պատվեր {id}-ն առաքված է 🌸 Շնորհակալություն բարության համար։",
        "cancelled": "Պատվեր {id}-ն չեղարկված է։ Մենեջերը կկապվի ձեզ հետ։",
        "none": "Դեռ պատվերներ չունեք։",
        "r7": "Մեկ շաբաթից առիթ, որի համար անցյալ տարի ծաղիկներ եք նվիրել՝ {label}։ Ընտրե՞նք ծաղկեփունջ նախապես։",
        "r1": "Վաղը՝ {label}։ Դեռ կհասցնենք առաքել։",
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
                    o = {"lang": r["lang"]}
                    if days <= 7 and days > 1 and not r["sent7"]:
                        send(r["chat_id"], esc(CLIENT[r["lang"]]["r7"].format(label=r["label"])), shop_button(o, "again"))
                        q("UPDATE reminders SET sent7=1 WHERE id=?", (r["id"],))
                    elif days <= 1 and days >= 0 and not r["sent1"]:
                        send(r["chat_id"], esc(CLIENT[r["lang"]]["r1"].format(label=r["label"])), shop_button(o, "again"))
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
    notify_admins(f"🆕 Новый заказ {src}\n\n" + admin_text(o, "new"))
    if client_chat:
        notify_client(oid, "received")
        if o.get("remind"):
            add_reminder(o, client_chat)
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
                      f"или перезапустите раздачу: /retry {esc(order_id)}")
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

    if cmd == "/start":
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
            send(chat, "Вы админ May Flowers.\n\n" + HELP_ADMIN)
        elif studio_by_chat(chat):
            send(chat, HELP_STUDIO)
        else:
            client_hello(chat, m)
        return

    if is_admin(uid):
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
    "ru": [["💐 Каталог", "📦 Мои заказы"], ["🤍 Букет добра", "📞 Связаться"], ["ℹ️ Как это работает"]],
    "en": [["💐 Catalog", "📦 My orders"], ["🤍 Kindness bouquet", "📞 Contact us"], ["ℹ️ How it works"]],
    "hy": [["💐 Կատալոգ", "📦 Իմ պատվերները"], ["🤍 Բարության ծաղկեփունջ", "📞 Կապ"], ["ℹ️ Ինչպես է աշխատում"]],
}
MENU_ACTIONS = ["catalog", "orders", "kind", "contact", "how"]
CL = {
    "ru": {
        "menu_hint": "Меню внизу 👇",
        "pick": "Выберите повод:",
        "cats": {"all": "Все букеты", "bd": "День рождения", "love": "Любовь", "thanks": "Спасибо",
                 "mom": "Маме", "sorry": "Извинение", "premium": "Премиум"},
        "order": "🛒 Заказать", "back": "↩️ Поводы", "empty": "Тут пока пусто.",
        "how": "Как это работает:\n\n1. Выберите букет в каталоге или в магазине.\n2. Укажите адрес, дату и время, текст открытки.\n3. Студия-партнёр соберёт букет, и я пришлю вам его фото до доставки.\n4. Курьер привезёт цветы по Еревану, от 60 минут.",
        "kind": "🤍 Букет добра\n\nДобавьте к любому заказу мини-букет за $15. Маис или наша команда вручит его незнакомому человеку на улицах Еревана от вашего имени, а вы получите видео вручения.\n\nОтметить можно при оформлении заказа.",
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
        "how": "How it works:\n\n1. Pick a bouquet in the catalog or the shop.\n2. Enter the address, date, time and card text.\n3. A partner studio builds the bouquet and I send you a photo before delivery.\n4. A courier delivers across Yerevan, from 60 minutes.",
        "kind": "🤍 Kindness bouquet\n\nAdd a mini bouquet to any order for $15. Mais or our team hands it to a stranger on the streets of Yerevan on your behalf, and you get the video.\n\nTick it at checkout.",
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
        "how": "Ինչպես է աշխատում՝\n\n1. Ընտրեք ծաղկեփունջ կատալոգում կամ խանութում։\n2. Նշեք հասցեն, ամսաթիվը, ժամը և բացիկի տեքստը։\n3. Գործընկեր ստուդիան կհավաքի ծաղկեփունջը, և ես կուղարկեմ լուսանկարը առաքումից առաջ։\n4. Առաքիչը կբերի Երևանով մեկ՝ 60 րոպեից։",
        "kind": "🤍 Բարության ծաղկեփունջ\n\nԱվելացրեք ցանկացած պատվերին մինի ծաղկեփունջ $15-ով։ Մաիսը կամ մեր թիմը այն կհանձնի անծանոթ մարդու Երևանի փողոցներում ձեր անունից, իսկ դուք կստանաք տեսանյութը։\n\nՆշեք պատվիրելիս։",
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
        txt = L["contact"] + ("\n" + L["contact_direct"].format(c=MANAGER_CONTACT) if MANAGER_CONTACT else "")
        send(chat, esc(txt))


def client_free_text(chat, m, text):
    frm = m.get("from") or {}
    name = " ".join(x for x in [frm.get("first_name"), frm.get("last_name")] if x) or "клиент"
    user = f" @{esc(frm['username'])}" if frm.get("username") else ""
    notify_admins(f"💬 Сообщение от {esc(name)}{user} (ID <code>{chat}</code>):\n{esc(text[:3000])}\n\n"
                  f"Ответить: <code>/reply {chat} </code>текст")
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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Intake-Key, X-Telegram-Init-Data")
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
        self.reply(200, {"ok": True, "id": oid})

    def log_message(self, fmt, *args):
        log.info("http %s", fmt % args)


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
