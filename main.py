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


# ============================================================
# АГЕНТ №4 — КОНТЕНТ + SMM (Instagram AVANTI)
# ============================================================

# 15 топових позицій з цінами
INSTAGRAM_POSTS = [
    {"brand": "Deeply", "name": "Шампунь нормалізуючий", "vol": "250мл", "salon": 158, "partner": 141, "rrc": 280, "no_price": True},
    {"brand": "Deeply", "name": "Маска відновлююча", "vol": "300мл", "salon": 248, "partner": 220, "rrc": 440, "no_price": True},
    {"brand": "Deeply", "name": "Кондиціонер розгладжуючий", "vol": "250мл", "salon": 208, "partner": 185, "rrc": 311, "no_price": True},
    {"brand": "Deeply", "name": "Спрей термозахист 10в1", "vol": "200мл", "salon": 267, "partner": 238, "rrc": 420, "no_price": True},
    {"brand": "RR Line", "name": "Маска Macadamia Star", "vol": "500мл", "salon": 283, "partner": 264, "rrc": 385, "no_price": False},
    {"brand": "RR Line", "name": "Флюїд Macadamia Star", "vol": "100мл", "salon": 590, "partner": 551, "rrc": 802, "no_price": False},
    {"brand": "MoroccanOil", "name": "Treatment олія", "vol": "50мл", "salon": 851, "partner": 795, "rrc": 1190, "no_price": False},
    {"brand": "EMMEBI ITALIA", "name": "Nutry Care маска", "vol": "200мл", "salon": 523, "partner": 488, "rrc": 713, "no_price": False},
    {"brand": "EMMEBI ITALIA", "name": "Gate 03 крем вирівнюючий", "vol": "200мл", "salon": 671, "partner": 627, "rrc": 917, "no_price": False},
    {"brand": "ECHOSline", "name": "Vegan Balance шампунь", "vol": "300мл", "salon": 289, "partner": 270, "rrc": 449, "no_price": False},
    {"brand": "ECHOSline", "name": "Vegan Hydrating маска", "vol": "300мл", "salon": 230, "partner": 214, "rrc": 357, "no_price": False},
    {"brand": "Bbcos", "name": "Keratin фарба без аміаку", "vol": "100мл", "salon": 352, "partner": 328, "rrc": 553, "no_price": False},
    {"brand": "C:EHKO", "name": "Лак фіксація Діамант (3)", "vol": "400мл", "salon": 410, "partner": 383, "rrc": 740, "no_price": True},
    {"brand": "Dermaskill", "name": "Only One Cream 3в1", "vol": "50мл", "salon": 1378, "partner": 1286, "rrc": 1950, "no_price": False},
    {"brand": "PNB", "name": "Гель-лак в асортименті", "vol": "8мл", "salon": 135, "partner": 109, "rrc": 196, "no_price": False},
]

AGENT4_SYSTEM = """Ти — AI Агент №4 AVANTI Cosmetics. Спеціаліст з контенту та SMM.
Твоє завдання: генерувати тексти для Instagram постів в B2B сегменті.
Цільова аудиторія: власники салонів, магазинів косметики, майстри манікюру та перукарі.
Ціль акаунту: залучення нових B2B партнерів по Закарпаттю та Україні.
Стиль: професійний, лаконічний, з акцентом на вигоду для бізнесу клієнта.
Мова: українська.
Завжди закінчуй: "📋 Прайс і умови → посилання в профілі | ✈️ @avanti_cosmetics_ua"
Максимум 150 слів."""


def get_agent4_post(post_idx: int) -> str:
    """Генерує текст Instagram поста для позиції по індексу."""
    post = INSTAGRAM_POSTS[post_idx % len(INSTAGRAM_POSTS)]
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    if post["no_price"]:
        price_info = "Ціни — за запитом (надаємо прайс)"
        price_block = ""
    else:
        price_info = f"Ціна салону: {post['salon']} ₴ | Ціна партнера: {post['partner']} ₴ | РРЦ: {post['rrc']} ₴"
        price_block = f"\n💅 Салон: {post['salon']} ₴\n🏪 Партнер: {post['partner']} ₴"

    prompt = f"""Напиши текст для Instagram поста про продукт:
Бренд: {post['brand']}
Продукт: {post['name']} {post['vol']}
{price_info}

Структура:
1. Емоційний заголовок 1 рядок
2. Опис продукту та його переваг для бізнесу (2-3 речення)
3. Для кого підходить (салон/майстер/магазин)
{price_block}
4. Заклик до дії + хештеги (5-7 хештегів)"""

    try:
        r = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=400,
            system=AGENT4_SYSTEM,
            messages=[{"role": "user", "content": prompt}]
        )
        return r.content[0].text
    except Exception as e:
        return f"❌ Помилка генерації: {e}"


def get_agent4_strategy() -> str:
    """Генерує стратегічний контент-план на тиждень."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    now = kyiv_time()
    try:
        r = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=500,
            system=AGENT4_SYSTEM,
            messages=[{"role": "user", "content": f"""Контент-план для Instagram @avanti__cosmetics на тиждень ({now.strftime('%d.%m.%Y')}).
Ціль: залучення B2B клієнтів (салони, магазини, майстри) по Закарпаттю.
Готуємось до таргетованої реклами після 10 червня.
Запропонуй 3 пости на тиждень: ПН, СР, ПТ.
Для кожного: тема, тип контенту, короткий опис."""}]
        )
        return r.content[0].text
    except Exception as e:
        return f"❌ Помилка: {e}"


# Лічильник постів (зберігається між запусками через БД)
def get_post_counter() -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS agent4_state (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("SELECT value FROM agent4_state WHERE key='post_counter'")
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else 0


def increment_post_counter():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS agent4_state (key TEXT PRIMARY KEY, value TEXT)")
    counter = get_post_counter() + 1
    c.execute("INSERT OR REPLACE INTO agent4_state (key, value) VALUES ('post_counter', ?)", (str(counter),))
    conn.commit()
    conn.close()
    return counter


async def auto_agent4_post(context: ContextTypes.DEFAULT_TYPE):
    """Автоматична генерація тексту поста ПН/СР/ПТ о 9:00 Київ."""
    now = kyiv_time()
    counter = get_post_counter()
    post = INSTAGRAM_POSTS[counter % len(INSTAGRAM_POSTS)]
    post_text = get_agent4_post(counter)
    increment_post_counter()

    msg = f"""✨ Агент №4 — Контент Instagram
📅 {now.strftime('%d.%m.%Y')} | Пост #{counter + 1}/15

🏷️ {post['brand']} — {post['name']} {post['vol']}

━━━━━━━━━━━━━━━━━━━━
{post_text}
━━━━━━━━━━━━━━━━━━━━

📸 Додай фото продукту і публікуй в @avanti__cosmetics"""

    await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=msg)


async def auto_agent4_weekly(context: ContextTypes.DEFAULT_TYPE):
    """Щотижневий контент-план у неділю о 20:00 Київ."""
    now = kyiv_time()
    plan = get_agent4_strategy()
    await context.bot.send_message(
        chat_id=OWNER_CHAT_ID,
        text=f"📊 Агент №4 — Контент-план на тиждень\n📅 {now.strftime('%d.%m.%Y')}\n\n{plan}"
    )


async def cmd_agent4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /agent4 — генерує наступний пост вручну."""
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await update.message.reply_text("✨ Агент №4 генерує пост... зачекай")
    counter = get_post_counter()
    post = INSTAGRAM_POSTS[counter % len(INSTAGRAM_POSTS)]
    post_text = get_agent4_post(counter)
    increment_post_counter()
    now = kyiv_time()

    msg = f"""✨ Агент №4 — Instagram пост #{counter + 1}/15
📅 {now.strftime('%d.%m.%Y')}

🏷️ {post['brand']} — {post['name']} {post['vol']}

━━━━━━━━━━━━━━━━━━━━
{post_text}
━━━━━━━━━━━━━━━━━━━━

📸 Додай фото і публікуй в @avanti__cosmetics
📋 Залишилось постів: {15 - (counter + 1) % 15}"""

    await update.message.reply_text(msg)


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
    app.add_handler(CommandHandler("agent4", cmd_agent4))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    jq = app.job_queue
    # Існуючі задачі
    jq.run_daily(auto_digest, time=datetime.strptime("05:30", "%H:%M").time())
    jq.run_daily(auto_sport,  time=datetime.strptime("09:00", "%H:%M").time())
    jq.run_daily(auto_food,   time=datetime.strptime("09:45", "%H:%M").time())
    jq.run_daily(auto_trends, time=datetime.strptime("06:00", "%H:%M").time(), days=(1,))
    jq.run_monthly(auto_brands, when=datetime.strptime("06:00", "%H:%M").time(), day=1)
    # Агент №4 — Instagram пости ПН/СР/ПТ о 9:00 Київ (6:00 UTC)
    jq.run_daily(auto_agent4_post, time=datetime.strptime("06:00", "%H:%M").time(), days=(1, 3, 5))
    # Контент-план щонеділі о 20:00 Київ (17:00 UTC)
    jq.run_daily(auto_agent4_weekly, time=datetime.strptime("17:00", "%H:%M").time(), days=(0,))

    print("🚀 AVANTI Supervisor запущений!")
    print("📊 БД: нагадування і задачі зберігаються постійно")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
