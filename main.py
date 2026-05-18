import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import anthropic

TELEGRAM_TOKEN = "8608440555:AAGBRdr8IA2iB9sLCEJFnPDBtRMeSlfkFLU"
OWNER_CHAT_ID = 6854020655
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

SYSTEM_PROMPT = """Ти AI Супервайзер AVANTI Cosmetics. Відповідай українською коротко.
Власник: Сергій, ФОП, Закарпаття.
Оборот: 1млн+ грн/міс. Маржа: 18.6% ціль 30%.
Борг: 400000 грн до грудня 2026.
Клієнти 22: Немеш, ФОП Петрище, Рущак, Лендел, Білак, Костак, Козушко, Цибарь, Крьока, Папарига, Гоєр, Думен, Морозько, Сятиня, Сабов, Кричфалушій, Прислупська, Худенко, Іжакевич, ФОП Бісун, ФОП Холод, ФОП Копос.
Знижки: ACTIVE 20к 10/9%, SPECIAL 50к 14/10%, VIP 100к 23/12%, LIMITED 150к 25/14%, EXCLUSIVE 200к 27/16%.
Портфель 24 марки: PNB, Siller, Adore, ECHOSline, EMMEBI ITALIA, MAIS, Apriori, AG Skin, Bbcos, C:EHKO, Daeng Gi Meo Ri, Deeply, GK Hair, Mielle, Meloni, MoroccanOil, Palco, RR Line, Hedonic, Robeauty, Dermaskill, Bourjois, Lumene, Max Factor.
Нові кандидати: Hypertine Beauty Surf.
Стратегія: ціль 1.5млн потім 2млн грн/міс. Червень 2026 магазин Wize Wase таємно. Нові ТМ тільки ексклюзивні імпортери маржа 30 плюс."""

conversation_history = []
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_claude_response(user_message):
    global conversation_history
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    conversation_history.append({"role": "user", "content": user_message})
    if len(conversation_history) > 20:
        conversation_history = conversation_history[-20:]
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


def get_agent1_response():
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": "Знайди 3 актуальних тренди в косметиці України зараз. Запропонуй 2-3 нові торгові марки середнього+ сегменту яких немає в списку: PNB, Siller, Adore, ECHOSline, EMMEBI ITALIA, MAIS, Apriori, AG Skin, Bbcos, C:EHKO, Daeng Gi Meo Ri, Deeply, GK Hair, Mielle, Meloni, MoroccanOil, Palco, RR Line, Hedonic, Robeauty, Dermaskill, Bourjois, Lumene, Max Factor. Марки мають мати ексклюзивного імпортера в Україні який працює через дистрибюторів."
            }]
        )
        return response.content[0].text
    except Exception as e:
        return f"Помилка: {str(e)}"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        await update.message.reply_text("Доступ заборонено.")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    response = get_claude_response(update.message.text)
    await update.message.reply_text(response)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await update.message.reply_text(
        "AVANTI Supervisor активовано!\n\n"
        "/status — статус бізнесу\n"
        "/digest — ранковий дайджест\n"
        "/agent1 — пошук нових ТМ і тренди\n"
        "/reset — очистити память"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    response = get_claude_response("Дай короткий статус бізнесу AVANTI на сьогодні. 5-7 пунктів.")
    await update.message.reply_text(response)


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    response = get_claude_response("Ранковий дайджест. Термінове / Важливе / На контролі")
    await update.message.reply_text(response)


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    global conversation_history
    conversation_history = []
    await update.message.reply_text("Память очищена.")


async def cmd_agent1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await update.message.reply_text("Агент №1 запущено. Зачекай 60 секунд...")
    text = get_agent1_response()
    await update.message.reply_text(f"Агент №1\n\n{text}")


def main():
    if not ANTHROPIC_KEY:
        print("ПОМИЛКА: Встановіть ANTHROPIC_API_KEY")
        return

    import threading
    import schedule
    import time

    def weekly_agent1():
        import asyncio
        from telegram import Bot
        bot = Bot(token=TELEGRAM_TOKEN)
        text = get_agent1_response()
        message = f"🤖 Агент №1 — Щотижневий звіт\n\n{text}"
        asyncio.run(bot.send_message(chat_id=OWNER_CHAT_ID, text=message))
        print("Щотижневий звіт надіслано!")

    def run_scheduler():
        schedule.every().monday.at("06:00").do(weekly_agent1)
        while True:
            schedule.run_pending()
            time.sleep(60)

    t = threading.Thread(target=run_scheduler, daemon=True)
    t.start()
    print("Планувальник запущено - звіт щопонеділка о 9:00")

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("agent1", cmd_agent1))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущений!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
