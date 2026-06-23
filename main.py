import os
import logging
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
BITRIX_WEBHOOK = os.environ.get("BITRIX_WEBHOOK")
OWNER_CHAT_ID = os.environ.get("OWNER_CHAT_ID", "7674074787")
SI_LOGIN = os.environ.get("SI_LOGIN")
SI_PASSWORD = os.environ.get("SI_PASSWORD")
SYRVE_URL = os.environ.get("SYRVE_URL", "https://puzzle-restaurant.syrve.app")
SYRVE_LOGIN = os.environ.get("SYRVE_LOGIN", "Gufron")
SYRVE_PASSWORD = os.environ.get("SYRVE_PASSWORD")
SYRVE_STORE_ID = int(os.environ.get("SYRVE_STORE_ID", "18023"))

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
SI_API = "https://server.serviceinspector.ru/api/0"

USERS = {
    "1": "Гуфрон Рустамов", "7": "Хабиб Кенджабаев",
    "23": "Назира Рустамова", "35": "Дилафрузхон Кенджабаева",
    "67": "Наимджон Косимов", "93": "Мичгона Урунова",
    "121": "Олимджон Хомидов", "123": "Акмал Акбаров",
    "147": "Набихон Мухитдинов", "2551": "Дилшод Абдуллоев",
    "7735": "Аъзамчон Точибоев", "8621": "Шерафкан Азиззода",
}

def send_message(chat_id, text, parse_mode="HTML"):
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Send message error: {e}")

# ─────────────────────────────────────────────
# SYRVE
# ─────────────────────────────────────────────

_syrve_token = None
_syrve_token_expiry = None

def syrve_get_token():
    global _syrve_token, _syrve_token_expiry
    if _syrve_token and _syrve_token_expiry and datetime.now() < _syrve_token_expiry:
        return _syrve_token
    try:
        r = requests.post(
            f"{SYRVE_URL}/api/auth/login",
            json={"login": SYRVE_LOGIN, "password": SYRVE_PASSWORD},
            timeout=10
        )
        data = r.json()
        token = data.get("token")
        if token:
            _syrve_token = token
            _syrve_token_expiry = datetime.now() + timedelta(minutes=18)
            logging.info("Syrve token obtained successfully")
            return token
        logging.error(f"Syrve login failed: {data}")
        return None
    except Exception as e:
        logging.error(f"Syrve auth error: {e}")
        return None

def get_syrve_report(date=None):
    if not SYRVE_PASSWORD:
        return "❌ Syrve: пароль не настроен (SYRVE_PASSWORD)"

    token = syrve_get_token()
    if not token:
        return "❌ Syrve: не удалось получить токен"

    today = date or datetime.now().strftime("%Y-%m-%d")
    dt = datetime.strptime(today, "%Y-%m-%d")
    yesterday = (dt - timedelta(days=1)).strftime("%Y-%m-%d")

    # Форматы дат для API
    def fmt(d):
        return datetime.strptime(d, "%Y-%m-%d").strftime("%a %b %d %Y")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        r = requests.post(
            f"{SYRVE_URL}/api/kpi/dashboard/data",
            json={
                "dateFromCurrent": fmt(today),
                "dateToCurrent": fmt(today),
                "dateFromPrevious": fmt(yesterday),
                "dateToPrevious": fmt(yesterday),
                "storeIds": [SYRVE_STORE_ID],
                "dashboardId": 0,
                "dashboardType": "executive"
            },
            headers=headers,
            timeout=20
        )
        data = r.json()
    except Exception as e:
        logging.error(f"Syrve dashboard error: {e}")
        return f"❌ Ошибка запроса Syrve: {str(e)}"

    # Парсим данные
    report = f"🍽 <b>Puzzle Restaurant</b>\n"
    report += f"📅 {today}\n"
    report += "━━━━━━━━━━━━━━━━\n"

    try:
        metrics = {}
        rows = data.get("rows", []) if isinstance(data, dict) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            for cell in row.get("cells", []):
                if not isinstance(cell, dict):
                    continue
                wd = cell.get("widgetData", {})
                if not isinstance(wd, dict):
                    continue
                for tile in (wd.get("tiles") or []):
                    if not isinstance(tile, dict):
                        continue
                    code = tile.get("metricCode", "")
                    val = tile.get("currentPeriodValue") or tile.get("value")
                    if code and val is not None:
                        metrics[code] = val
                for m in (wd.get("metrics") or []):
                    if not isinstance(m, dict):
                        continue
                    code = m.get("metricCode", "")
                    val = m.get("currentPeriodValue") or m.get("value")
                    if code and val is not None:
                        metrics[code] = val
                for s in (wd.get("series") or []):
                    if not isinstance(s, dict):
                        continue
                    code = s.get("metricCode", "")
                    vals = s.get("data") or []
                    if code and vals:
                        total = sum(v for v in vals if isinstance(v, (int, float)))
                        if total:
                            metrics.setdefault(code, total)

        rev    = metrics.get("REV_NET") or metrics.get("NET_REVENUE") or metrics.get("REVENUE")
        orders = metrics.get("ORDERS_COUNT") or metrics.get("CHECKS_COUNT")
        avg    = metrics.get("AVG_CHECK") or metrics.get("AVG_REVENUE")
        guests = metrics.get("GUESTS_COUNT")

        if any(v is not None for v in [rev, orders, avg, guests]):
            if rev is not None:
                report += f"💰 <b>Выручка:</b> {float(rev):.2f} AED\n"
            if orders is not None:
                report += f"🧾 <b>Чеков:</b> {int(float(orders))}\n"
            if avg is not None:
                report += f"📈 <b>Средний чек:</b> {float(avg):.2f} AED\n"
            if guests is not None:
                report += f"👥 <b>Гостей:</b> {int(float(guests))}\n"
        else:
            report += f"<i>Данные за {today} ещё не поступили</i>\n"
            if metrics:
                report += f"<i>Метрики: {', '.join(list(metrics.keys())[:5])}</i>\n"
            logging.info(f"Syrve metrics: {metrics}")

    except Exception as e:
        logging.error(f"Syrve parse error: {e}")
        report += f"\n⚠️ Ошибка парсинга: {str(e)}\n"

    return report

# ─────────────────────────────────────────────
# SERVICE INSPECTOR
# ─────────────────────────────────────────────

def get_si_token():
    try:
        r = requests.get(f"{SI_API}/auth/access_token",
            params={"user_login": SI_LOGIN, "user_secret": SI_PASSWORD}, timeout=10)
        data = r.json()
        return data.get("accessToken"), data.get("organizationInfo", {}).get("id")
    except Exception as e:
        logging.error(f"SI auth error: {e}")
        return None, None

def get_si_report():
    token, org_id = get_si_token()
    if not token:
        return "❌ Не удалось подключиться к Service Inspector"

    today = datetime.now().strftime("%d.%m.%Y")
    try:
        r = requests.get(f"{SI_API}/inspector/get_processed_audits",
            params={
                "access_token": token, "org_id": org_id,
                "from_date": today, "to_date": today
            }, timeout=15)
        audits = r.json()
        if not audits:
            return "📋 <b>Service Inspector:</b> Проверок за сегодня нет"

        grouped = {}
        for a in audits:
            key = (a.get("name", ""), a.get("selectedInspectObjectName", ""))
            existing = grouped.get(key)
            if not existing or a.get("result", 0) > existing.get("result", 0):
                grouped[key] = a

        report  = "📋 <b>KPI — Service Inspector</b>\n"
        report += f"📅 {datetime.now().strftime('%d.%m.%Y')}\n"
        report += "━━━━━━━━━━━━━━━━\n"

        total = len(grouped)
        avg   = sum(a.get("result", 0) for a in grouped.values()) / total if total else 0

        for (name, obj), a in sorted(grouped.items()):
            result    = a.get("result", 0)
            inspector = a.get("inspectorName", "—")
            closed    = "✅" if a.get("isClosed") else "🔄"
            emoji     = "🟢" if result >= 80 else ("🟡" if result >= 60 else "🔴")
            report += f"{closed} {emoji} <b>{name}</b>\n"
            report += f"   📍 {obj} | 👤 {inspector}\n"
            report += f"   📊 Результат: {result:.1f}%\n\n"

        report += f"━━━━━━━━━━━━━━━━\n"
        report += f"📊 Проверок: {total} | Средний балл: {avg:.1f}%"
        return report
    except Exception as e:
        return f"❌ Ошибка SI: {str(e)}"

# ─────────────────────────────────────────────
# BITRIX24
# ─────────────────────────────────────────────

def get_bitrix_tasks():
    try:
        r = requests.get(f"{BITRIX_WEBHOOK}tasks.task.list.json", params={
            "filter[STATUS]": "2",
            "select[]": ["ID", "TITLE", "RESPONSIBLE_ID", "DEADLINE"],
            "order[RESPONSIBLE_ID]": "ASC"
        }, timeout=10)
        tasks = r.json().get("result", {}).get("tasks", [])

        today = datetime.now().strftime("%Y-%m-%d")
        r2 = requests.get(f"{BITRIX_WEBHOOK}tasks.task.list.json", params={
            "filter[STATUS]": "5",
            "filter[>=CLOSED_DATE]": today + "T00:00:00",
            "select[]": ["ID", "TITLE", "RESPONSIBLE_ID"],
        }, timeout=10)
        done = r2.json().get("result", {}).get("tasks", [])

        active_by = {}
        done_by   = {}
        for t in tasks:
            uid  = str(t.get("responsibleId", ""))
            name = USERS.get(uid, f"ID {uid}")
            active_by.setdefault(name, []).append(t.get("title", ""))
        for t in done:
            uid  = str(t.get("responsibleId", ""))
            name = USERS.get(uid, f"ID {uid}")
            done_by.setdefault(name, []).append(t.get("title", ""))

        report  = "📌 <b>Задачи — Bitrix24</b>\n"
        report += "━━━━━━━━━━━━━━━━\n"
        all_names = set(list(active_by.keys()) + list(done_by.keys()))
        if not all_names:
            report += "✅ Нет активных задач\n"
        else:
            for name in sorted(all_names):
                active     = active_by.get(name, [])
                done_count = len(done_by.get(name, []))
                report += f"👤 <b>{name}</b>\n"
                report += f"   ✅ Выполнено: {done_count} | 🔄 В работе: {len(active)}\n"
                for t in active[:2]:
                    report += f"   • {t[:45]}\n"
                report += "\n"
        report += f"📊 Итого: активных {len(tasks)} | выполнено {len(done)}"
        return report
    except Exception as e:
        return f"❌ Ошибка Bitrix: {str(e)}"

# ─────────────────────────────────────────────
# ОБЩИЙ ОТЧЁТ
# ─────────────────────────────────────────────

def get_full_report():
    now    = datetime.now().strftime("%d.%m.%Y %H:%M")
    header = f"🍔 <b>TajBurger Dashboard</b>\n🕐 {now}\n\n"
    tasks  = get_bitrix_tasks()
    si     = get_si_report()
    footer = "\n━━━━━━━━━━━━━━━━\n💡 /report — обновить | /puzzle — Puzzle"
    return header + tasks + "\n\n" + si + footer

# ─────────────────────────────────────────────
# WEBHOOK / ROUTES
# ─────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return jsonify({"ok": True})
    message    = data.get("message", {})
    chat_id    = message.get("chat", {}).get("id")
    text       = message.get("text", "")
    first_name = message.get("from", {}).get("first_name", "")
    if not chat_id:
        return jsonify({"ok": True})

    if text == "/start":
        send_message(chat_id,
            f"👋 Привет, {first_name}!\n\n"
            f"🍔 <b>TajBurger Task Dashboard</b>\n\n"
            f"Команды:\n"
            f"/report — полный отчёт TajBurger\n"
            f"/tasks — задачи Bitrix24\n"
            f"/kpi — KPI Service Inspector\n"
            f"/puzzle — продажи Puzzle Restaurant 🇦🇪\n"
            f"/help — помощь")
    elif text == "/report":
        send_message(chat_id, "⏳ Загружаю данные...")
        send_message(chat_id, get_full_report())
    elif text == "/tasks":
        send_message(chat_id, "⏳ Загружаю задачи...")
        send_message(chat_id, get_bitrix_tasks())
    elif text == "/kpi":
        send_message(chat_id, "⏳ Загружаю KPI...")
        send_message(chat_id, get_si_report())
    elif text == "/puzzle":
        send_message(chat_id, "⏳ Загружаю данные Puzzle Restaurant...")
        send_message(chat_id, get_syrve_report())
    elif text == "/help":
        send_message(chat_id,
            "📋 <b>Команды:</b>\n\n"
            "/report — полный дашборд TajBurger\n"
            "/tasks — задачи по сотрудникам\n"
            "/kpi — результаты проверок\n"
            "/puzzle — продажи Puzzle Restaurant 🇦🇪\n"
            "/start — начало работы")
    else:
        send_message(chat_id, "Используй /report для получения отчёта 📊")
    return jsonify({"ok": True})

@app.route("/send_report", methods=["GET"])
def send_daily_report():
    send_message(OWNER_CHAT_ID, get_full_report())
    return jsonify({"ok": True})

@app.route("/send_puzzle_report", methods=["GET"])
def send_puzzle_report():
    send_message(OWNER_CHAT_ID, get_syrve_report())
    return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "TajBurger Bot running 🍔"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
