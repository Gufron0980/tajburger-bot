import os
import logging
import requests
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8220859604:AAFwAQKB-ycu4-anSdBi8cJjlKaN_Q5juGQ")
BITRIX_WEBHOOK = os.environ.get("BITRIX_WEBHOOK", "https://tajburger.bitrix24.ru/rest/1/upszyza4hn7zmsl1/")
OWNER_CHAT_ID = os.environ.get("OWNER_CHAT_ID", "7674074787")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Список сотрудников
USERS = {
    "1": "Гуфрон Рустамов",
    "7": "Хабиб Кенджабаев",
    "23": "Назира Рустамова",
    "35": "Дилафрузхон Кенджабаева",
    "67": "Наимджон Косимов",
    "93": "Мичгона Урунова",
    "121": "Олимджон Хомидов",
    "123": "Акмал Акбаров",
    "147": "Набихон Мухитдинов",
    "2551": "Дилшод Абдуллоев",
    "7735": "Аъзамчон Точибоев",
    "8621": "Шерафкан Азиззода",
}

def send_message(chat_id, text, parse_mode="HTML"):
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    requests.post(url, json=payload)

def get_tasks_report():
    """Получить отчёт по задачам из Bitrix24"""
    try:
        # Активные задачи
        r = requests.get(f"{BITRIX_WEBHOOK}tasks.task.list.json", params={
            "filter[STATUS]": "2",
            "select[]": ["ID", "TITLE", "STATUS", "RESPONSIBLE_ID", "DEADLINE"],
            "order[RESPONSIBLE_ID]": "ASC"
        })
        data = r.json()
        tasks = data.get("result", {}).get("tasks", [])

        # Завершённые за сегодня
        today = datetime.now().strftime("%Y-%m-%d")
        r2 = requests.get(f"{BITRIX_WEBHOOK}tasks.task.list.json", params={
            "filter[STATUS]": "5",
            "filter[>=CLOSED_DATE]": today + "T00:00:00",
            "select[]": ["ID", "TITLE", "RESPONSIBLE_ID", "CLOSED_DATE"],
        })
        data2 = r2.json()
        done_tasks = data2.get("result", {}).get("tasks", [])

        # Группировка по сотрудникам
        active_by_user = {}
        done_by_user = {}

        for t in tasks:
            uid = str(t.get("responsibleId", ""))
            name = USERS.get(uid, f"Сотрудник {uid}")
            active_by_user.setdefault(name, []).append(t.get("title", ""))

        for t in done_tasks:
            uid = str(t.get("responsibleId", ""))
            name = USERS.get(uid, f"Сотрудник {uid}")
            done_by_user.setdefault(name, []).append(t.get("title", ""))

        # Формируем отчёт
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        report = f"📊 <b>Ежедневный отчёт TajBurger</b>\n"
        report += f"🕐 {now}\n"
        report += "━━━━━━━━━━━━━━━━\n\n"

        all_names = set(list(active_by_user.keys()) + list(done_by_user.keys()))

        if not all_names:
            report += "✅ Нет активных задач\n"
        else:
            for name in sorted(all_names):
                active = active_by_user.get(name, [])
                done = done_by_user.get(name, [])
                report += f"👤 <b>{name}</b>\n"
                report += f"   ✅ Выполнено сегодня: {len(done)}\n"
                report += f"   🔄 В работе: {len(active)}\n"
                if active:
                    for t in active[:3]:
                        report += f"   • {t[:50]}\n"
                report += "\n"

        report += "━━━━━━━━━━━━━━━━\n"
        report += f"📌 Итого активных: {len(tasks)} | Выполнено: {len(done_tasks)}"
        return report

    except Exception as e:
        return f"❌ Ошибка получения данных: {str(e)}"


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return jsonify({"ok": True})

    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    first_name = message.get("from", {}).get("first_name", "")

    if not chat_id:
        return jsonify({"ok": True})

    if text == "/start":
        send_message(chat_id,
            f"👋 Привет, {first_name}!\n\n"
            f"Я бот TajBurger Task Dashboard.\n\n"
            f"Команды:\n"
            f"/report — отчёт по задачам\n"
            f"/help — помощь"
        )

    elif text == "/report":
        send_message(chat_id, "⏳ Загружаю данные из Bitrix24...")
        report = get_tasks_report()
        send_message(chat_id, report)

    elif text == "/help":
        send_message(chat_id,
            "📋 <b>Доступные команды:</b>\n\n"
            "/report — ежедневный отчёт по задачам сотрудников\n"
            "/start — начать работу\n"
            "/help — эта справка"
        )

    else:
        send_message(chat_id,
            f"Привет! Используй /report для получения отчёта по задачам."
        )

    return jsonify({"ok": True})


@app.route("/send_report", methods=["GET"])
def send_daily_report():
    """Эндпоинт для ежедневной отправки отчёта"""
    report = get_tasks_report()
    send_message(OWNER_CHAT_ID, report)
    return jsonify({"ok": True, "message": "Report sent"})


@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "TajBurger Bot is running! 🍔"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
