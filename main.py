import os
import logging
import requests
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
BITRIX_WEBHOOK = os.environ.get("BITRIX_WEBHOOK")
OWNER_CHAT_ID = os.environ.get("OWNER_CHAT_ID", "7674074787")
SI_LOGIN = os.environ.get("SI_LOGIN")
SI_PASSWORD = os.environ.get("SI_PASSWORD")
SYRVE_URL = os.environ.get("SYRVE_URL", "https://puzzle-restaurant.syrve.app")
SYRVE_API_KEY = os.environ.get("SYRVE_API_KEY")

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

def syrve_get_token():
    try:
        r = requests.post(
            f"{SYRVE_URL}/api/1/access_token",
            json={"apiLogin": SYRVE_API_KEY},
            timeout=10
        )
        data = r.json()
        token = data.get("token")
        if not token:
            logging.error(f"Syrve token error: {data}")
        return token
    except Exception as e:
        logging.error(f"Syrve auth error: {e}")
        return None

def syrve_get_org_id(token):
    try:
        r = requests.post(
            f"{SYRVE_URL}/api/1/organizations",
            json={"returnAdditionalInfo": False},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        orgs = r.json().get("organizations", [])
        return orgs[0]["id"] if orgs else None
    except Exception as e:
        logging.error(f"Syrve org error: {e}")
        return None

def get_syrve_report(date=None):
    if not SYRVE_API_KEY:
        return "❌ Syrve: API ключ не настроен"

    token = syrve_get_token()
    if not token:
        return "❌ Syrve: не удалось получить токен"

    org_id = syrve_get_org_id(token)
    if not org_id:
        return "❌ Syrve: не удалось получить ID организации"

    today = date or datetime.now().strftime("%Y-%m-%d")
    date_from = f"{today} 00:00:00"
    date_to   = f"{today} 23:59:59"
    headers   = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # — Продажи (OLAP) —
    total_revenue = 0
    total_orders  = 0
    dishes = []
    try:
        r = requests.post(
            f"{SYRVE_URL}/api/1/reports/olap",
            json={
                "organizationId": org_id,
                "settings": {
                    "queryFilter": {
                        "dateFrom": date_from,
                        "dateTo":   date_to,
                        "openDateFrom": date_from,
                        "openDateTo":   date_to
                    },
                    "groupByRowFields": ["DishName"],
                    "aggregateFields": ["DishAmountInt", "DishSumInt"]
                }
            },
            headers=headers,
            timeout=15
        )
        rows = r.json().get("data", [])
        for row in rows:
            total_revenue += row.get("DishSumInt", 0)
            total_orders  += row.get("DishAmountInt", 0)
            dishes.append({
                "name": row.get("DishName", ""),
                "qty":  row.get("DishAmountInt", 0),
                "sum":  row.get("DishSumInt", 0)
            })
    except Exception as e:
        logging.error(f"Syrve OLAP error: {e}")

    # — Кассовые сессии —
    cash_income = 0
    card_income = 0
    try:
        r = requests.post(
            f"{SYRVE_URL}/api/1/cash_shifts",
            json={
                "organizationIds": [org_id],
                "openDateFrom": f"{today}T00:00:00",
                "openDateTo":   f"{today}T23:59:59"
            },
            headers=headers,
            timeout=15
        )
        shifts = r.json().get("cashShifts", [])
        for shift in shifts:
            cash_income += shift.get("cashIn", 0)
            card_income += shift.get("cardIn", 0)
    except Exception as e:
        logging.error(f"Syrve cash_shifts error: {e}")

    # — Формируем отчёт —
    avg_check = round(total_revenue / total_orders, 2) if total_orders > 0 else 0
    top5 = sorted(dishes, key=lambda x: x["sum"], reverse=True)[:5]

    report  = f"🍽 <b>Puzzle Restaurant — Продажи</b>\n"
    report += f"📅 {today}\n"
    report += "━━━━━━━━━━━━━━━━\n"
    report += f"💰 Выручка: <b>{total_revenue:.2f} AED</b>\n"
    report += f"🧾 Чеков: <b>{total_orders}</b>\n"
    report += f"📈 Средний чек: <b>{avg_check} AED</b>\n\n"
    report += f"💵 Наличные: {cash_income:.2f} AED\n"
    report += f"💳 Карта: {card_income:.2f} AED\n\n"

    if top5:
        report += "🏆 <b>Топ-5 блюд:</b>\n"
        for i, d in enumerate(top5, 1):
            report += f"{i}. {d['name']} — {d['qty']} шт / {d['sum']:.2f} AED\n"

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
    footer = "\n━━━━━━━━━━━━━━━━\n💡 /report — обновить отчёт"
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
            f"/report — полный отчёт (TajBurger)\n"
            f"/tasks — только задачи Bitrix24\n"
            f"/kpi — только KPI Service Inspector\n"
            f"/puzzle — продажи Puzzle Restaurant\n"
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
