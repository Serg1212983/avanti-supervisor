import os
import logging
import requests
import threading
import time
import re
import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import anthropic

TELEGRAM_TOKEN = "8608440555:AAGBRdr8IA2iB9sLCEJFnPDBtRMeSlfkFLU"
OWNER_CHAT_ID = 6854020655
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
DB_PATH = "/app/avanti.db"

SYSTEM_PROMPT = """Ти — AI Супервайзер і особистий асистент Сергія. Власник бізнесу AVANTI Cosmetics.
Відповідай українською мовою. Коротко і по суті.

БІЗНЕС: Дистрибуція косметики, Закарпаття, ФОП Сергій
ОБОРОТ: 1 млн+ грн/місяць. МАРЖА: 18.6% ціль 30%.
БОРГ: 400 000 грн до грудня 2026.
ОБОРОТНІ КОШТИ: 100-120 000 грн

КЛІЄНТИ (22, Закарпаття):
Немеш, ФОП Петрище, Рущак, Лендел, Білак, Костак, Козушко,
Цибарь, Крьока, Папарига, Гоєр, Думен, Морозько, Сятиня,
Сабов, Кричфалушій, Прислупська, Худенко, Іжакевич,
ФОП Бісун, ФОП Холод, ФОП Копос

ЗНИЖКИ: ACTIVE 20к+ 10/9%, SPECIAL 50к+ 14/10%, VIP 100к+ 23/12%, LIMITED 150к+ 25/14%, EXCLUSIVE 200к+ 27/16%

ПОРТФЕЛЬ (24 марки):
Нігті: PNB, Siller, Adore
Волосся: ECHOSline, EMMEBI ITALIA, MAIS, Apriori, AG Skin, Bbcos,
C:EHKO, Daeng Gi Meo Ri, Deeply, GK Hair, Mielle, Meloni,
MoroccanOil, Palco, RR Line, Hedonic, Robeauty, Dermaskill
Обличчя: Bourjois, Lumene, Max Factor
Кандидати: Hypertine Beauty Surf

СТРАТЕГІЯ: Ціль 1.5 млн → 2 млн грн/місяць. Червень 2026 Wize Wase B2C.
РОЗПОРЯДОК: 12:00 спорт, 12:45 їжа. Сергій не виходить з дому.

ВАЖЛИВО ПРО НАГАДУВАННЯ:
Якщо Сергій каже "нагадай", "нагадати", "нагади" з часом — система автоматично збереже нагадування.
ЗАВЖДИ відповідай: "✅ Записав нагадування: [задача] о [час]"
НІКОЛИ не кажи що не можеш надіслати нагадування — система це робить автоматично."""

conversation_history = []
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def kyiv_time():
    return datetime.utcnow() + timedelta(hours=3)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT NOT NULL,
        remind_time TEXT NOT NULL,
        remind_date TEXT NOT NULL,
        done INTEGER DEFAULT 0,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT NOT NULL,
        done INTEGER DEFAULT 0,
        created_at TEXT,
        due_date TEXT
    )""")
    conn.commit()
    conn.close()


def db_add_reminder(text, rtime, rdate):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO reminders (text, remind_time, remind_date, created_at) VALUES (?,?,?,?)",
              (text, rtime, rdate, kyiv_time().strftime("%d.%m %H:%M")))
    conn.commit()
    conn.close()


def db_get_active_reminders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, text, remind_time, remind_date FROM reminders WHERE done=0 ORDER BY remind_date, remind_time")
    rows = c.fetchall()
    conn.close()
    return rows


def db_mark_done(rid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE reminders SET done=1 WHERE id=?", (rid,))
    conn.commit()
    conn.close()


def db_add_task(text, due_date=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO tasks (text, created_at, due_date) VALUES (?,?,?)",
              (text, kyiv_time().strftime("%d.%m %H:%M"), due_date))
    conn.commit()
    conn.close()


def db_get_tasks():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, text, due_date FROM tasks WHERE done=0 ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return rows


def db_done_task(tid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE tasks SET done=1 WHERE id=?", (tid,))
    conn.commit()
    conn.close()


def parse_time(text):
    patterns = [
        r'о\s*(\d{1,2})[:\.](\d{2})',
        r'(\d{1,2})[:\.](\d{2})',
        r'о\s*(\d{1,2})\s*год',
        r'\b(\d{1,2}):(\d{2})\b',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            g = m.groups()
            h = int(g[0])
            mn = int(g[1]) if len(g) > 1 and g[1] else 0
            if 0 <= h <= 23 and 0 <= mn <= 59:
                return h, mn
    return None, None


def get_claude_response(user_message):
    global conversation_history
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    now = kyiv_time()
    conversation_history.append({
        "role": "user",
        "content": f"[Київ {now.strftime('%H:%M %d.%m.%Y')}] {user_message}"
    })
    if len(conversation_history) > 30:
        conversation_history = conversation_history[-30:]
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=conversation_history
        )
        reply = response.content[0].text
        conversation_history.append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        return f"Помилка: {str(e)}"


def transcribe_voice(file_path):
    try:
        with open(file_path, 'rb') as f:
            resp = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {OPENAI_KEY}"},
                files={"file": ("voice.ogg", f, "audio/ogg")},
                data={"model": "whisper-1", "language": "uk"},
                timeout=30
            )
            return resp.json().get("text")
    except Exception as e:
        logger.error(f"Whisper: {e}")
        return None


def get_agent1_response():
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    try:
        r = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1200,
            messages=[{"role": "user", "content": """Ти аналітик косметичного ринку України.

🔥 ТРЕНДИ ТИЖНЯ (3 пункти) — що популярно в косметиці UA+світ.

🏆 НОВІ ТМ КАНДИДАТИ (3-4 марки) — яких НЕМАЄ в списку:
PNB, Siller, Adore, ECHOSline, EMMEBI ITALIA, MAIS, Apriori, AG Skin, Bbcos, C:EHKO, Daeng Gi Meo Ri, Deeply, GK Hair, Mielle, Meloni, MoroccanOil, Palco, RR Line, Hedonic, Robeauty, Dermaskill, Bourjois, Lumene, Max Factor.
Критерії: середній+ сегмент, ексклюзивний імпортер в Україні, маржа 30%+.

💡 РЕКОМЕНДАЦІЯ для 1.5 млн грн/міс.
Українською."""}]
        )
        return r.content[0].text
    except Exception as e:
        return f"Помилка: {str(e)}"


def process_reminder(text):
    """Перевіряє чи є в тексті нагадування і зберігає в БД"""
    kws = ["нагадай", "нагадати", "нагади", "нагадування"]
    if not any(k in text.lower() for k in kws):
        return False, None, None

    h, mn = parse_time(text)
    if h is None:
        return False, None, None

    now = kyiv_time()
    rt = f"{h:02d}:{mn:02d}"
    rd = now.strftime("%d.%m")
    label = "сьогодні"

    if h < now.hour or (h == now.hour and mn <= now.minute):
        rd = (now + timedelta(days=1)).strftime("%d.%m")
        label = "завтра"

    db_add_reminder(text, rt, rd)
    return True, rt, label


def reminder_checker():
    """Перевіряє нагадування кожну хвилину"""
    while True:
        try:
            now = kyiv_time()
            ct = f"{now.hour:02d}:{now.minute:02d}"
            cd = now.strftime("%d.%m")
            rows = db_get_active_reminders()
            for rid, rtext, rtime, rdate in rows:
                if rtime == ct and rdate == cd:
                    db_mark_done(rid)
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                        json={
                            "chat_id": OWNER_CHAT_ID,
                            "text": f"🔔 НАГАДУВАННЯ!\n\n📝 {rtext}\n⏰ {rtime}"
                        },
                        timeout=10
                    )
                    logger.info(f"Reminder sent: {rtext} at {rtime}")
        except Exception as e:
            logger.error(f"Reminder checker: {e}")
        time.sleep(60)


async def process_text(text, update, context):
    """Обробляє текст — і голосовий і текстовий"""
    # Перевіряємо нагадування
    is_reminder, rt, label = process_reminder(text)
    if is_reminder:
        await update.message.reply_text(f"✅ Нагадування записано!\n⏰ {label} о {rt}\n📝 {text}")
        return

    # Перевіряємо задачі
    task_kws = ["задача:", "завдання:", "зробити:", "todo:"]
    if any(k in text.lower() for k in task_kws):
        db_add_task(text)
        await update.message.reply_text(f"✅ Задачу записано:\n📋 {text}")
        return

    # Звичайна відповідь
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    response = get_claude_response(text)
    await update.message.reply_text(response)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await process_text(update.message.text, update, context)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await update.message.reply_text("🎤 Розпізнаю...")
    try:
        file = await context.bot.get_file(update.message.voice.file_id)
        path = f"/tmp/v_{update.message.voice.file_id}.ogg"
        await file.download_to_drive(path)
        if not OPENAI_KEY:
            await update.message.reply_text("❌ OPENAI_API_KEY не налаштований")
            return
        text = transcribe_voice(path)
        try:
            os.remove(path)
        except:
            pass
        if text:
            await update.message.reply_text(f"🎤 _{text}_", parse_mode="Markdown")
            await process_text(text, update, context)
        else:
            await update.message.reply_text("❌ Не вдалось розпізнати. Спробуй ще раз.")
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)}")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    now = kyiv_time()
    await update.message.reply_text(
        f"AVANTI Supervisor 🚀\n"
        f"Зараз: {now.strftime('%H:%M %d.%m.%Y')} Київ\n\n"
        f"🎤 Говори голосом!\n"
        f"🔔 'Нагадай о 15:00 зателефонувати' — збережу і нагадаю точно\n"
        f"📋 'Задача: зробити щось' — запишу в список\n\n"
        f"Авто щодня:\n"
        f"• 8:30 — ранковий дайджест\n"
        f"• 12:00 — нагадування спорт\n"
        f"• 12:45 — нагадування їжа\n\n"
        f"Авто тижневе:\n"
        f"• Пн 9:00 — тренди косметики\n"
        f"• 1-го числа — нові ТМ кандидати\n\n"
        f"Команди: /status /digest /plan /reminders /tasks /agent1"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text(get_claude_response("Статус бізнесу AVANTI сьогодні. 5-7 пунктів."))


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    now = kyiv_time()
    r = get_claude_response("Ранковий дайджест. 🔴 Термінове | 🟡 Важливе | 🟢 На контролі")
    await update.message.reply_text(f"🌅 {now.strftime('%d.%m')}\n\n{r}")


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    now = kyiv_time()
    rems = db_get_active_reminders()
    tasks = db_get_tasks()
    context_text = ""
    if rems:
        context_text += "\nНагадування: " + ", ".join([f"{r[2]} — {r[1][:40]}" for r in rems])
    if tasks:
        context_text += "\nЗадачі: " + ", ".join([t[1][:40] for t in tasks[:5]])
    r = get_claude_response(f"План на сьогодні по часових блоках. 12:00 спорт, 12:45 їжа.{context_text}")
    await update.message.reply_text(f"📅 {now.strftime('%d.%m')}\n\n{r}")


async def cmd_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    rows = db_get_active_reminders()
    if not rows:
        await update.message.reply_text("📋 Немає активних нагадувань")
        return
    text = f"🔔 Нагадувань: {len(rows)}\n\n"
    for rid, rtext, rtime, rdate in rows:
        text += f"⏰ {rtime} ({rdate})\n📝 {rtext[:60]}\n\n"
    await update.message.reply_text(text)


async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    rows = db_get_tasks()
    if not rows:
        await update.message.reply_text("📋 Немає активних задач\n\nДодай: 'Задача: зробити щось'")
        return
    text = f"📋 Задач: {len(rows)}\n\n"
    for tid, ttext, tdue in rows:
        due = f" ({tdue})" if tdue else ""
        text += f"• [{tid}] {ttext[:60]}{due}\n"
    text += "\nЩоб закрити задачу: /done [номер]"
    await update.message.reply_text(text)


async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Вкажи номер: /done 1")
        return
    try:
        tid = int(args[0])
        db_done_task(tid)
        await update.message.reply_text(f"✅ Задача #{tid} виконана!")
    except:
        await update.message.reply_text("Невірний номер")


async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Приклад: /remind о 15:00 зателефонувати Рущаку")
        return
    text = " ".join(args)
    is_reminder, rt, label = process_reminder("нагадай " + text)
    if is_reminder:
        await update.message.reply_text(f"✅ {label} о {rt}\n📝 {text}")
    else:
        await update.message.reply_text("Не знайшов час. Вкажи наприклад: о 15:00")


async def cmd_agent1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await update.message.reply_text("🔍 Аналізую... зачекай 60 секунд")
    now = kyiv_time()
    await update.message.reply_text(f"🤖 Агент №1 — {now.strftime('%d.%m.%Y')}\n\n{get_agent1_response()}")


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    global conversation_history
    conversation_history = []
    await update.message.reply_text("🔄 Пам'ять очищена.")


async def auto_digest(context: ContextTypes.DEFAULT_TYPE):
    now = kyiv_time()
    rems = db_get_active_reminders()
    rn = f"\n🔔 Нагадувань сьогодні: {len(rems)}" if rems else ""
    r = get_claude_response("Ранковий дайджест. 🔴 Термінове | 🟡 Важливе | 🟢 На контролі. Максимум 150 слів.")
    await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=f"🌅 Доброго ранку! {now.strftime('%d.%m')}{rn}\n\n{r}")


async def auto_sport(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=OWNER_CHAT_ID, text="💪 12:00 — Час спорту! 30-40 хвилин.")


async def auto_food(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=OWNER_CHAT_ID, text="🍽️ 12:45 — Час їжі!")


async def auto_trends(context: ContextTypes.DEFAULT_TYPE):
    now = kyiv_time()
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    try:
        r = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=700,
            messages=[{"role": "user", "content": "Топ-3 тренди в косметиці України зараз (манікюр/волосся/обличчя). Для кожного: назва, звідки, чому важливо дистриб'ютору. Українською, коротко."}]
        )
        await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=f"🔍 Тренди — {now.strftime('%d.%m')}\n\n{r.content[0].text}")
    except Exception as e:
        logger.error(f"Trends: {e}")


async def auto_brands(context: ContextTypes.DEFAULT_TYPE):
    now = kyiv_time()
    await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=f"🏆 Нові ТМ — {now.strftime('%B %Y')}\n\n{get_agent1_response()}")


def main():
    if not ANTHROPIC_KEY:
        print("ПОМИЛКА: ANTHROPIC_API_KEY")
        return

    init_db()
    print("✅ База даних ініціалізована")

    t = threading.Thread(target=reminder_checker, daemon=True)
    t.start()
    print("✅ Нагадування активні (перевірка щохвилини)")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("remind", cmd_remind))
    app.add_handler(CommandHandler("reminders", cmd_reminders))
    app.add_handler(CommandHandler("tasks", cmd_tasks))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("agent1", cmd_agent1))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    jq = app.job_queue
    jq.run_daily(auto_digest, time=datetime.strptime("05:30", "%H:%M").time())
    jq.run_daily(auto_sport,  time=datetime.strptime("09:00", "%H:%M").time())
    jq.run_daily(auto_food,   time=datetime.strptime("09:45", "%H:%M").time())
    jq.run_daily(auto_trends, time=datetime.strptime("06:00", "%H:%M").time(), days=(1,))
    jq.run_monthly(auto_brands, when=datetime.strptime("06:00", "%H:%M").time(), day=1)

    print("🚀 AVANTI Supervisor запущений!")
    print("📊 БД: нагадування і задачі зберігаються постійно")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
