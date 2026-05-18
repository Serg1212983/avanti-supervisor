import os
import logging
import requests
import json
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import anthropic

TELEGRAM_TOKEN = "8608440555:AAGBRdr8IA2iB9sLCEJFnPDBtRMeSlfkFLU"
OWNER_CHAT_ID = 6854020655
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

SYSTEM_PROMPT = """Ти — AI Супервайзер і особистий асистент Сергія. Власник бізнесу AVANTI Cosmetics.
Відповідай українською мовою. Коротко і по суті. Без зайвих слів.

БІЗНЕС: Дистрибуція косметики, Закарпаття, ФОП Сергій
ОБОРОТ: 1 млн+ грн/місяць. МАРЖА: 18.6% ціль 30%.
БОРГ: 400 000 грн до грудня 2026.
ОБОРОТНІ КОШТИ: 100-120 000 грн

КЛІЄНТИ (22, Закарпаття):
Немеш, ФОП Петрище, Рущак, Лендел, Білак, Костак, Козушко,
Цибарь, Крьока, Папарига, Гоєр, Думен, Морозько, Сятиня,
Сабов, Кричфалушій, Прислупська, Худенко, Іжакевич,
ФОП Бісун, ФОП Холод, ФОП Копос

ЗНИЖКИ (Клуб партнерів AVANTI):
ACTIVE 20к+: 10/9%, SPECIAL 50к+: 14/10%
VIP 100к+: 23/12%, LIMITED 150к+: 25/14%, EXCLUSIVE 200к+: 27/16%

ПОРТФЕЛЬ (24 марки):
Нігті: PNB, Siller, Adore
Волосся: ECHOSline, EMMEBI ITALIA, MAIS, Apriori, AG Skin, Bbcos,
C:EHKO, Daeng Gi Meo Ri, Deeply, GK Hair, Mielle, Meloni,
MoroccanOil, Palco, RR Line, Hedonic, Robeauty, Dermaskill
Обличчя: Bourjois, Lumene, Max Factor
Кандидати: Hypertine Beauty Surf

СТРАТЕГІЯ:
- Ціль: 1.5 млн → 2 млн грн/місяць
- Червень 2026: інтернет-магазин Wize Wase (таємно від B2B клієнтів)
- Нові ТМ: ексклюзивні імпортери, маржа 30%+, середній+ сегмент
- Масштабування по Україні

ОСОБИСТИЙ РОЗПОРЯДОК СЕРГІЯ:
- 12:00 — спорт (30-40 хвилин)
- 12:45 — їжа
- Решта часу — робота вдома (не виходить через судовий процес)

ФУНКЦІЇ АСИСТЕНТА:
Якщо Сергій просить нагадати щось — запиши і скажи що запам'ятав.
Якщо питає про план на день/тиждень — відповідай з урахуванням розпорядку.
Якщо просить скласти графік — допоможи структурувати задачі по часу.
Якщо питання про бізнес — думай в категоріях кас, маржі, клієнтів.
Завжди будь проактивним — якщо бачиш важливе питання яке варто вирішити, запропонуй сам."""

conversation_history = []
reminders = []

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_claude_response(user_message):
    global conversation_history
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    conversation_history.append({"role": "user", "content": user_message})
    if len(conversation_history) > 30:
        conversation_history = conversation_history[-30:]
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=conversation_history
        )
        assistant_message = response.content[0].text
        conversation_history.append({"role": "assistant", "content": assistant_message})
        return assistant_message
    except Exception as e:
        return f"Помилка Claude: {str(e)}"


def transcribe_voice(file_path):
    """Перетворює голосове повідомлення в текст через OpenAI Whisper"""
    try:
        with open(file_path, 'rb') as audio_file:
            headers = {"Authorization": f"Bearer {OPENAI_KEY}"}
            files = {"file": ("voice.ogg", audio_file, "audio/ogg")}
            data = {"model": "whisper-1", "language": "uk"}
            resp = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data,
                timeout=30
            )
            result = resp.json()
            if "text" in result:
                return result["text"]
            else:
                return None
    except Exception as e:
        logger.error(f"Whisper error: {e}")
        return None


def get_agent1_response():
    """Агент №1 - тренди та нові ТМ"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1200,
            messages=[{
                "role": "user",
                "content": """Ти аналітик косметичного ринку України.

Дай мені:

🔥 ТРЕНДИ ТИЖНЯ (3 пункти)
Що зараз популярно в косметиці в Україні та світі (манікюр, волосся, обличчя).
Звідки йде тренд (Корея, Захід, тощо) і чому це важливо для дистриб'ютора.

🏆 НОВІ ТМ — КАНДИДАТИ (3-4 марки)
Торгові марки яких НЕМАЄ в цьому списку:
PNB, Siller, Adore, ECHOSline, EMMEBI ITALIA, MAIS, Apriori, AG Skin, Bbcos, C:EHKO, Daeng Gi Meo Ri, Deeply, GK Hair, Mielle, Meloni, MoroccanOil, Palco, RR Line, Hedonic, Robeauty, Dermaskill, Bourjois, Lumene, Max Factor.

Критерії відбору:
- Середній або вище середнього ціновий сегмент
- Є ексклюзивний імпортер в Україні який працює через дистриб'юторів
- Потенційна маржинальність 30%+
- Схожі за рівнем на: R-Line, ECHOSline, Meloni

Для кожної ТМ: назва, категорія, чому підходить, де шукати контакт імпортера.

💡 РЕКОМЕНДАЦІЯ
Що зробити цього місяця щоб наблизитись до обороту 1.5 млн грн/міс.

Відповідай українською мовою."""
            }]
        )
        return response.content[0].text
    except Exception as e:
        return f"Помилка агента: {str(e)}"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    response = get_claude_response(update.message.text)
    await update.message.reply_text(response)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка голосових повідомлень"""
    if update.effective_user.id != OWNER_CHAT_ID:
        return

    await update.message.reply_text("🎤 Слухаю... розпізнаю голос")

    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        file_path = f"/tmp/voice_{voice.file_id}.ogg"
        await file.download_to_drive(file_path)

        if not OPENAI_KEY:
            await update.message.reply_text("❌ OpenAI ключ не налаштований для голосу")
            return

        text = transcribe_voice(file_path)

        if text:
            await update.message.reply_text(f"🎤 Розпізнано: _{text}_", parse_mode="Markdown")
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            response = get_claude_response(text)
            await update.message.reply_text(response)
        else:
            await update.message.reply_text("❌ Не вдалось розпізнати голос. Спробуй ще раз або напиши текстом.")

        try:
            os.remove(file_path)
        except:
            pass

    except Exception as e:
        await update.message.reply_text(f"❌ Помилка обробки голосу: {str(e)}")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await update.message.reply_text(
        "AVANTI Supervisor активовано! 🚀\n\n"
        "Я твій бізнес-супервайзер і особистий асистент.\n\n"
        "🎤 Можеш надсилати голосові повідомлення!\n\n"
        "Команди:\n"
        "/status — статус бізнесу\n"
        "/digest — ранковий дайджест\n"
        "/plan — план на сьогодні\n"
        "/agent1 — запустити аналітика\n"
        "/remind — додати нагадування\n"
        "/reset — очистити пам'ять"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    response = get_claude_response("Дай короткий статус бізнесу AVANTI на сьогодні. 5-7 пунктів максимум.")
    await update.message.reply_text(response)


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    now = datetime.now()
    response = get_claude_response(
        f"Ранковий дайджест на {now.strftime('%d.%m.%Y')}. "
        f"Структура: 🔴 Термінове | 🟡 Важливе | 🟢 На контролі. "
        f"Врахуй розпорядок дня: 12:00 спорт, 12:45 їжа."
    )
    await update.message.reply_text(f"🌅 Дайджест {now.strftime('%d.%m')}\n\n{response}")


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    now = datetime.now()
    response = get_claude_response(
        f"Склади план на сьогодні {now.strftime('%A %d.%m.%Y')}. "
        f"Враховуй: 12:00 спорт, 12:45 їжа. "
        f"Розстав задачі по часових блоках: ранок, до спорту, після їжі, вечір. "
        f"Питай що є пріоритетним якщо не знаєш."
    )
    await update.message.reply_text(f"📅 План на сьогодні\n\n{response}")


async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    args = context.args
    if not args:
        await update.message.reply_text(
            "Напиши що нагадати, наприклад:\n"
            "/remind зателефонувати в PUMB о 15:00\n"
            "/remind зустріч з постачальником в п'ятницю о 11:00"
        )
        return
    reminder_text = " ".join(args)
    reminders.append({
        "text": reminder_text,
        "created": datetime.now().strftime("%d.%m %H:%M")
    })
    await update.message.reply_text(
        f"✅ Записав нагадування:\n_{reminder_text}_\n\n"
        f"Всього нагадувань: {len(reminders)}",
        parse_mode="Markdown"
    )


async def cmd_reminders_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    if not reminders:
        await update.message.reply_text("📋 Немає активних нагадувань")
        return
    text = "📋 Активні нагадування:\n\n"
    for i, r in enumerate(reminders, 1):
        text += f"{i}. {r['text']}\n   _(додано {r['created']})_\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_agent1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await update.message.reply_text("🔍 Агент №1 запущено. Аналізую ринок... зачекай 60 секунд")
    text = get_agent1_response()
    now = datetime.now()
    await update.message.reply_text(f"🤖 Агент №1 — {now.strftime('%d.%m.%Y')}\n\n{text}")


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    global conversation_history
    conversation_history = []
    await update.message.reply_text("🔄 Пам'ять очищена.")


async def send_morning_digest(context: ContextTypes.DEFAULT_TYPE):
    """Автоматичний ранковий дайджест о 8:30 Київ (5:30 UTC)"""
    now = datetime.now()
    response = get_claude_response(
        f"Ранковий автодайджест {now.strftime('%d.%m.%Y')}. "
        f"Коротко — що сьогодні критично для AVANTI? "
        f"Структура: 🔴 Термінове | 🟡 Важливе | 🟢 На контролі. "
        f"Нагадай про 12:00 спорт і 12:45 їжа. Максимум 150 слів."
    )
    await context.bot.send_message(
        chat_id=OWNER_CHAT_ID,
        text=f"🌅 Доброго ранку! Дайджест {now.strftime('%d.%m')}\n\n{response}"
    )


async def send_sport_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Нагадування о 12:00 — спорт"""
    await context.bot.send_message(
        chat_id=OWNER_CHAT_ID,
        text="💪 12:00 — Час спорту!\n\nВідклади роботу на 30-40 хвилин. Здоров'я важливіше."
    )


async def send_food_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Нагадування о 12:45 — їжа"""
    await context.bot.send_message(
        chat_id=OWNER_CHAT_ID,
        text="🍽️ 12:45 — Час їжі!\n\nПообідай спокійно перед тим як повертатись до роботи."
    )


async def send_weekly_trends(context: ContextTypes.DEFAULT_TYPE):
    """Щопонеділка о 9:00 Київ (6:00 UTC) — тренди тижня"""
    now = datetime.now()
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{
                "role": "user",
                "content": "Дай мені топ-3 тренди в косметиці (манікюр, волосся, обличчя) які зараз актуальні в Україні та світі. Для кожного: назва тренду, звідки прийшов, чому важливо знати дистриб'ютору. Відповідай українською, коротко."
            }]
        )
        text = response.content[0].text
        await context.bot.send_message(
            chat_id=OWNER_CHAT_ID,
            text=f"🔍 Тренди тижня — {now.strftime('%d.%m.%Y')}\n\n{text}"
        )
    except Exception as e:
        logger.error(f"Weekly trends error: {e}")


async def send_monthly_brands(context: ContextTypes.DEFAULT_TYPE):
    """1-го числа кожного місяця о 9:00 — нові ТМ"""
    now = datetime.now()
    text = get_agent1_response()
    await context.bot.send_message(
        chat_id=OWNER_CHAT_ID,
        text=f"🏆 Нові ТМ — шортліст {now.strftime('%B %Y')}\n\n{text}"
    )


def main():
    if not ANTHROPIC_KEY:
        print("ПОМИЛКА: Встановіть ANTHROPIC_API_KEY")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Команди
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("remind", cmd_remind))
    app.add_handler(CommandHandler("reminders", cmd_reminders_list))
    app.add_handler(CommandHandler("agent1", cmd_agent1))
    app.add_handler(CommandHandler("reset", cmd_reset))

    # Голосові повідомлення
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Текстові повідомлення
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Автоматичні розсилки
    job_queue = app.job_queue

    # Ранковий дайджест о 8:30 Київ = 5:30 UTC
    job_queue.run_daily(send_morning_digest, time=datetime.strptime("05:30", "%H:%M").time())

    # Нагадування спорт о 12:00 Київ = 9:00 UTC
    job_queue.run_daily(send_sport_reminder, time=datetime.strptime("09:00", "%H:%M").time())

    # Нагадування їжа о 12:45 Київ = 9:45 UTC
    job_queue.run_daily(send_food_reminder, time=datetime.strptime("09:45", "%H:%M").time())

    # Тренди щопонеділка о 9:00 Київ = 6:00 UTC
    job_queue.run_daily(
        send_weekly_trends,
        time=datetime.strptime("06:00", "%H:%M").time(),
        days=(1,)  # 1 = понеділок
    )

    # Нові ТМ 1-го числа кожного місяця о 9:00 Київ = 6:00 UTC
    job_queue.run_monthly(
        send_monthly_brands,
        when=datetime.strptime("06:00", "%H:%M").time(),
        day=1
    )

    print("AVANTI Supervisor запущений!")
    print("Голосові повідомлення: ✅")
    print("Ранковий дайджест: 8:30 Київ")
    print("Спорт нагадування: 12:00 Київ")
    print("Їжа нагадування: 12:45 Київ")
    print("Тренди: щопонеділка 9:00 Київ")
    print("Нові ТМ: 1-го числа кожного місяця 9:00 Київ")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
