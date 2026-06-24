import os
import logging
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

BOT_TOKEN        = os.environ.get("BOT_TOKEN")
BITRIX_WEBHOOK   = os.environ.get("BITRIX_WEBHOOK")
OWNER_CHAT_ID    = os.environ.get("OWNER_CHAT_ID", "7674074787")
SI_LOGIN         = os.environ.get("SI_LOGIN")
SI_PASSWORD      = os.environ.get("SI_PASSWORD")
SYRVE_URL        = os.environ.get("SYRVE_URL", "https://puzzle-restaurant.syrve.app")
SYRVE_LOGIN      = os.environ.get("SYRVE_LOGIN", "Gufron")
SYRVE_PASSWORD   = os.environ.get("SYRVE_PASSWORD")
SYRVE_STORE_ID   = int(os.environ.get("SYRVE_STORE_ID", "18023"))

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
SI_API       = "https://server.serviceinspector.ru/api/0"

USERS = {
    "1": "Гуфрон Рустамов", "7": "Хабиб Кенджабаев",
    "23": "Назира Рустамова", "35": "Дилафрузхон Кенджабаева",
    "67": "Наимджон Косимов", "93": "Мичгона Урунова",
    "121": "Олимджон Хомидов", "123": "Акмал Акбаров",
    "147": "Набихон Мухитдинов", "2551": "Дилшод Абдуллоев",
    "7735": "Аъзамчон Точибоев", "8621": "Шерафкан Азиззода",
}

# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────

def send_message(chat_id, text, parse_mode="HTML"):
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Send message error: {e}")

# ─────────────────────────────────────────────
# SYRVE AUTH
# ─────────────────────────────────────────────

_syrve_token        = None
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
            _syrve_token        = token
            _syrve_token_expiry = datetime.now() + timedelta(minutes=18)
            logging.info("Syrve token obtained successfully")
            return token
        logging.error(f"Syrve login failed: {data}")
        return None
    except Exception as e:
        logging.error(f"Syrve auth error: {e}")
        return None

def syrve_headers():
    token = syrve_get_token()
    if not token:
        return None
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def fmt_date(d):
    """datetime → 'Mon Jun 23 2026'"""
    return d.strftime("%a %b %d %Y")

def parse_series(data):
    """Извлекаем метрики из widgetData.series (dict или list)"""
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
            series = wd.get("series", {})
            if isinstance(series, dict):
                for code, vals in series.items():
                    if isinstance(vals, list) and vals:
                        total = sum(v for v in vals if isinstance(v, (int, float)))
                        metrics.setdefault(code, 0)
                        metrics[code] += total
            for tile in (wd.get("tiles") or []):
                if not isinstance(tile, dict):
                    continue
                code = tile.get("metricCode", "")
                val  = tile.get("currentPeriodValue") or tile.get("value")
                if code and val is not None:
                    metrics[code] = val
    return metrics

# ─────────────────────────────────────────────
# SYRVE: КОММЕРЧЕСКИЙ ОТЧЁТ (/puzzle)
# ─────────────────────────────────────────────

def get_syrve_commercial(date=None):
    if not SYRVE_PASSWORD:
        return "❌ Syrve: пароль не настроен"

    hdrs = syrve_headers()
    if not hdrs:
        return "❌ Syrve: не удалось получить токен"

    today     = date or datetime.now().strftime("%Y-%m-%d")
    dt        = datetime.strptime(today, "%Y-%m-%d")
    yesterday = (dt - timedelta(days=1)).strftime("%Y-%m-%d")

    report  = f"🍽 <b>Puzzle Restaurant — Коммерция</b>\n"
    report += f"📅 {today}\n"
    report += "━━━━━━━━━━━━━━━━\n"

    # 1. Executive dashboard (выручка, средний чек)
    try:
        r = requests.post(
            f"{SYRVE_URL}/api/kpi/dashboard/data",
            json={
                "dateFromCurrent":  fmt_date(dt),
                "dateToCurrent":    fmt_date(dt),
                "dateFromPrevious": fmt_date(dt - timedelta(days=1)),
                "dateToPrevious":   fmt_date(dt - timedelta(days=1)),
                "storeIds":         [SYRVE_STORE_ID],
                "dashboardId":      0,
                "dashboardType":    "executive"
            },
            headers=hdrs, timeout=20
        )
        metrics = parse_series(r.json())
        rev     = metrics.get("REV_NET") or metrics.get("REVENUE")
        avg     = metrics.get("AVG_CHECK")
        orders  = metrics.get("ORDERS_COUNT") or metrics.get("CHECKS_COUNT")
        guests  = metrics.get("GUESTS_COUNT")

        if rev:
            report += f"💰 <b>Выручка:</b> {float(rev):.2f} AED\n"
        if orders:
            report += f"🧾 <b>Чеков:</b> {int(float(orders))}\n"
        if avg:
            report += f"📈 <b>Средний чек:</b> {float(avg):.2f} AED\n"
        if guests:
            report += f"👥 <b>Гостей:</b> {int(float(guests))}\n"
    except Exception as e:
        report += f"⚠️ Выручка: {e}\n"

    # 2. P&L (себестоимость, валовая прибыль)
    try:
        r = requests.post(
            f"{SYRVE_URL}/api/kpi/dashboard/data",
            json={
                "dateFromCurrent":  fmt_date(dt),
                "dateToCurrent":    fmt_date(dt),
                "dateFromPrevious": fmt_date(dt - timedelta(days=1)),
                "dateToPrevious":   fmt_date(dt - timedelta(days=1)),
                "storeIds":         [SYRVE_STORE_ID],
                "dashboardId":      "281546",
                "dashboardType":    "executive"
            },
            headers=hdrs, timeout=20
        )
        pl = parse_series(r.json())
        cost  = pl.get("COST_PRICE") or pl.get("COST")
        gross = pl.get("GROSS_PROFIT") or pl.get("GROSS")
        disc  = pl.get("DISCOUNT") or pl.get("DISCOUNTS_SUM")

        report += "\n<b>📊 P&L:</b>\n"
        if cost:
            report += f"🏭 Себестоимость: {float(cost):.2f} AED\n"
        if gross:
            report += f"📈 Валовая прибыль: {float(gross):.2f} AED\n"
        if disc:
            report += f"🏷 Скидки: {float(disc):.2f} AED\n"
    except Exception as e:
        logging.error(f"P&L error: {e}")

    # 3. Топ-3 блюда
    try:
        r = requests.post(
            f"{SYRVE_URL}/api/report/product-mix",
            json={
                "dateFrom": fmt_date(dt),
                "dateTo":   fmt_date(dt),
                "mode":     "TOTAL_BY_PERIODS",
                "storeIds": [SYRVE_STORE_ID]
            },
            headers=hdrs, timeout=20
        )
        pm_data = r.json()
        products = []
        if isinstance(pm_data, dict):
            for item in (pm_data.get("items") or pm_data.get("products") or pm_data.get("data") or []):
                if isinstance(item, dict):
                    name = item.get("name") or item.get("productName") or item.get("dish")
                    qty  = item.get("quantity") or item.get("count") or item.get("sold") or 0
                    summ = item.get("sum") or item.get("revenue") or item.get("amount") or 0
                    if name:
                        products.append({"name": name, "qty": float(qty), "sum": float(summ)})
        elif isinstance(pm_data, list):
            for item in pm_data:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("productName")
                    qty  = item.get("quantity") or item.get("count") or 0
                    summ = item.get("sum") or item.get("revenue") or 0
                    if name:
                        products.append({"name": name, "qty": float(qty), "sum": float(summ)})

        if products:
            top3 = sorted(products, key=lambda x: x["sum"], reverse=True)[:3]
            report += "\n🏆 <b>Топ-3 блюда:</b>\n"
            for i, p in enumerate(top3, 1):
                report += f"{i}. {p['name']} — {int(p['qty'])} шт / {p['sum']:.2f} AED\n"
        else:
            logging.info(f"Product-mix raw: {str(pm_data)[:300]}")
    except Exception as e:
        logging.error(f"Product-mix error: {e}")

    return report

# ─────────────────────────────────────────────
# SYRVE: БУХГАЛТЕРСКИЙ ОТЧЁТ (/puzzle_fin)
# ─────────────────────────────────────────────

def get_syrve_finance(date=None):
    if not SYRVE_PASSWORD:
        return "❌ Syrve: пароль не настроен"

    hdrs = syrve_headers()
    if not hdrs:
        return "❌ Syrve: не удалось получить токен"

    today = date or datetime.now().strftime("%Y-%m-%d")
    dt    = datetime.strptime(today, "%Y-%m-%d")

    # Даты в формате для documents API
    date_from = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    date_to   = today

    report  = f"📒 <b>Puzzle Restaurant — Бухгалтерия</b>\n"
    report += f"📅 {today}\n"
    report += "━━━━━━━━━━━━━━━━\n"

    # 1. Кассовые смены
    try:
        r = requests.get(
            f"{SYRVE_URL}/api/cash/eod/status",
            headers=hdrs, timeout=10
        )
        eod = r.json()
        if isinstance(eod, dict):
            status  = eod.get("status", "—")
            closed  = eod.get("closedAt") or eod.get("closeDate") or "—"
            by_whom = eod.get("closedBy") or eod.get("user") or "—"
            report += f"🏦 <b>Закрытие дня:</b> {status}\n"
            if closed != "—":
                report += f"   🕐 Закрыто: {closed}\n"
            if by_whom != "—":
                report += f"   👤 Кем: {by_whom}\n"
        elif isinstance(eod, list) and eod:
            report += f"🏦 <b>Кассовых смен закрыто:</b> {len(eod)}\n"
            total_cash = sum(float(s.get("cashRevenue", 0) or 0) for s in eod if isinstance(s, dict))
            total_card = sum(float(s.get("cardRevenue", 0) or 0) for s in eod if isinstance(s, dict))
            if total_cash or total_card:
                report += f"   💵 Наличные: {total_cash:.2f} AED\n"
                report += f"   💳 Карта: {total_card:.2f} AED\n"
                report += f"   💰 Итого: {total_cash + total_card:.2f} AED\n"
    except Exception as e:
        report += f"⚠️ Смены: {e}\n"

    # 2. Активные смены
    try:
        r = requests.get(
            f"{SYRVE_URL}/api/cash/shift/active",
            headers=hdrs, timeout=10
        )
        shifts = r.json()
        if isinstance(shifts, list):
            report += f"\n💵 <b>Активных смен:</b> {len(shifts)}\n"
            for s in shifts[:3]:
                if isinstance(s, dict):
                    num  = s.get("number") or s.get("id", "—")
                    cash = float(s.get("cashRevenue", 0) or 0)
                    card = float(s.get("cardRevenue", 0) or 0)
                    report += f"   Смена #{num}: 💵{cash:.0f} + 💳{card:.0f} AED\n"
        elif isinstance(shifts, dict):
            cash = float(shifts.get("cashRevenue", 0) or 0)
            card = float(shifts.get("cardRevenue", 0) or 0)
            report += f"\n💵 <b>Текущая смена:</b> {cash:.2f} + {card:.2f} AED\n"
    except Exception as e:
        report += f"⚠️ Активные смены: {e}\n"

    # 3. Документы (приходные накладные, акты приготовления)
    try:
        r = requests.get(
            f"{SYRVE_URL}/api/documents/list",
            params={"dateFrom": date_from, "dateTo": date_to, "store": SYRVE_STORE_ID},
            headers=hdrs, timeout=15
        )
        docs = r.json()
        doc_list = docs if isinstance(docs, list) else (docs.get("items") or docs.get("documents") or [])

        # Фильтруем по типам
        incoming    = [d for d in doc_list if isinstance(d, dict) and "накладная" in str(d.get("type", "")).lower() or "INCOMING" in str(d.get("type", "")).upper() or "IncomingInvoice" in str(d.get("documentType", ""))]
        production  = [d for d in doc_list if isinstance(d, dict) and ("приготовл" in str(d.get("type", "")).lower() or "ProductionDocument" in str(d.get("documentType", "")) or "приготов" in str(d.get("typeName", "")).lower())]
        all_types   = {}
        for d in doc_list:
            if isinstance(d, dict):
                t = d.get("type") or d.get("documentType") or d.get("typeName") or "Unknown"
                all_types[t] = all_types.get(t, 0) + 1

        report += f"\n📄 <b>Документы за {date_from} — {date_to}:</b>\n"
        if all_types:
            for t, cnt in sorted(all_types.items(), key=lambda x: -x[1])[:6]:
                report += f"   • {t}: {cnt} шт\n"
        else:
            report += "   Нет документов\n"

    except Exception as e:
        report += f"⚠️ Документы: {e}\n"

    # 4. Инвентаризация
    try:
        r = requests.get(
            f"{SYRVE_URL}/api/inventory/count/list/active",
            headers=hdrs, timeout=10
        )
        inv = r.json()
        inv_list = inv if isinstance(inv, list) else (inv.get("items") or [])
        report += f"\n📦 <b>Инвентаризация:</b>\n"
        if inv_list:
            report += f"   Активных заданий: {len(inv_list)}\n"
            for item in inv_list[:3]:
                if isinstance(item, dict):
                    name   = item.get("name") or item.get("storeName") or "—"
                    status = item.get("status") or item.get("state") or "—"
                    report += f"   • {name}: {status}\n"
        else:
            report += "   Активных заданий нет\n"
    except Exception as e:
        report += f"⚠️ Инвентаризация: {e}\n"

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
            params={"access_token": token, "org_id": org_id,
                    "from_date": today, "to_date": today}, timeout=15)
        audits = r.json()
        if not audits:
            return "📋 <b>Service Inspector:</b> Проверок за сегодня нет"

        # Группируем по сотруднику
        by_employee = {}
        for a in audits:
            emp  = a.get("inspectorName", "—")
            name = a.get("name", "")
            obj  = a.get("selectedInspectObjectName", "")
            res  = a.get("result", 0)
            key  = (emp, name, obj)
            existing = by_employee.get(key)
            if not existing or res > existing.get("result", 0):
                by_employee[key] = a

        report  = "📋 <b>KPI — Service Inspector</b>\n"
        report += f"📅 {today}\n"
        report += "━━━━━━━━━━━━━━━━\n"

        # Группируем по сотруднику для сводки
        emp_stats = {}
        for (emp, name, obj), a in by_employee.items():
            if emp not in emp_stats:
                emp_stats[emp] = {"results": [], "checklists": []}
            emp_stats[emp]["results"].append(a.get("result", 0))
            emp_stats[emp]["checklists"].append(name)

        for emp, stats in sorted(emp_stats.items()):
            avg = sum(stats["results"]) / len(stats["results"]) if stats["results"] else 0
            cnt = len(stats["results"])
            emoji = "🟢" if avg >= 80 else ("🟡" if avg >= 60 else "🔴")
            report += f"{emoji} <b>{emp}</b>\n"
            report += f"   📊 Выполнение: {avg:.1f}% | Чек-листов: {cnt}\n"
            for cl in stats["checklists"][:2]:
                report += f"   • {cl}\n"
            report += "\n"

        total = len(by_employee)
        avg_all = sum(a.get("result", 0) for a in by_employee.values()) / total if total else 0
        report += f"━━━━━━━━━━━━━━━━\n"
        report += f"📊 Проверок: {total} | Средний балл: {avg_all:.1f}%"
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
    footer = "\n━━━━━━━━━━━━━━━━\n💡 /puzzle — Puzzle | /puzzle_fin — Бухгалтерия"
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
            f"/report — дашборд TajBurger\n"
            f"/tasks — задачи Bitrix24\n"
            f"/kpi — KPI Service Inspector\n"
            f"/puzzle — 🇦🇪 Коммерция Puzzle\n"
            f"/puzzle_fin — 🇦🇪 Бухгалтерия Puzzle\n"
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
        send_message(chat_id, "⏳ Загружаю коммерцию Puzzle Restaurant...")
        send_message(chat_id, get_syrve_commercial())
    elif text == "/puzzle_fin":
        send_message(chat_id, "⏳ Загружаю бухгалтерию Puzzle Restaurant...")
        send_message(chat_id, get_syrve_finance())
    elif text == "/help":
        send_message(chat_id,
            "📋 <b>Команды:</b>\n\n"
            "/report — полный дашборд TajBurger\n"
            "/tasks — задачи по сотрудникам\n"
            "/kpi — результаты проверок\n"
            "/puzzle — коммерция Puzzle 🇦🇪\n"
            "/puzzle_fin — бухгалтерия Puzzle 🇦🇪\n"
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
    send_message(OWNER_CHAT_ID, get_syrve_commercial())
    return jsonify({"ok": True})

@app.route("/send_puzzle_fin", methods=["GET"])
def send_puzzle_fin():
    send_message(OWNER_CHAT_ID, get_syrve_finance())
    return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "TajBurger Bot running 🍔"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
