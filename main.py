import os
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import anthropic

TELEGRAM_TOKEN = "8608440555:AAGBRdr8IA2iB9sLCEJFnPDBtRMeSlfkFLU"
OWNER_CHAT_ID = 6854020655
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

SYSTEM_PROMPT = """Ти — AI Супервайзер бізнесу AVANTI Cosmetics.
Спілкуєшся тільки з власником. Відповідай українською, коротко і по суті.

БІЗНЕС: Дистрибуція косметики, Закарпаття
ОБОРОТ: 1 млн+ грн/місяць
МАРЖА: 18.6% → ціль 30%
БОРГ: 400 000 грн → закрити до грудня 2026
ОБОРОТНІ КОШТИ: 100-120 000 грн

КЛІЄНТИ (22, Закарпаття):
Немеш, ФОП Петрище, Рущак, Лендел, Білак, Костак, Козушко,
Цибарь, Крьока, Папарига, Гоєр, Думен, Морозько, Сятиня,
Сабов, Кричфалушій, Прислупська, Худенко, Іжакевич,
ФОП Бісун, ФОП Холод, ФОП Копос

ЗНИЖКИ (Клуб партнерів AVANTI):
ACTIVE 20к+ : 10% / 9%
SPECIAL 50к+: 14% / 10%
VIP 100к+: 23% / 12%
LIMITED 150к+: 25% / 14%
EXCLUSIVE 200к+: 27% / 16%

ПОРТФЕЛЬ (24 марки):
Нігті: PNB, Siller, Adore
Волосся: ECHOSline, EMMEBI ITALIA, MAIS, Apriori, AG Skin, Bbcos, C:EHKO, Daeng Gi Meo Ri, Deeply, GK Hair, Mielle, Meloni, MoroccanOil, Palco, RR Line, Hedonic, Robeauty, Dermaskill
Обличчя/макіяж: Bourjois, Lumene, Max Factor
Нові кандидати: Hypertine (Beauty Surf)
СТРАТЕГІЯ:
- Ціль: 1.5 млн потім 2 млн грн/місяць
- Червень 2026: інтернет-магазин Wize Wase (таємно від B2B клієнтів)
- Липень 2026: сайт AVANTI
- Масштабування по Україні через регіональних менеджерів
- Нові ТМ: тільки українські імпортери з ексклюзивом, маржа 30%+
"""

conversation_history = []
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
def get_claude_response(user_message: str) -> str:
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
        logger.error(f"Claude API error: {e}")
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
        "Знаю твій бізнес повністю.\n"
        "Питай будь-що.\n\n"
        "/status — статус бізнесу\n"
        "/digest — ранковий дайджест\n"
        "/reset — очистити пам'ять"
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
    response = get_claude_response("Ранковий дайджест. Структура: Термінове / Важливе / На контролі")
    await update.message.reply_text(response)

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    global conversation_history
    conversation_history = []
    await update.message.reply_text("Пам'ять очищена.")
async def cmd_agent1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_CHAT_ID:
        return
    await update.message.reply_text("🤖 Агент №1 запущено. Зачекай 60 секунд...")
    try:
       import requests
        headers = {
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "Ти експерт косметичного ринку України. Відповідай українською."},
                {"role": "user", "content": "Знайди 3 тренди в косметиці України зараз. Запропонуй 2-3 нові ТМ середнього+ сегменту яких немає в списку: PNB, Siller, Adore, ECHOSline, EMMEBI ITALIA, MAIS, Apriori, AG Skin, Bbcos, C:EHKO, Daeng Gi Meo Ri, Deeply, GK Hair, Mielle, Meloni, MoroccanOil, Palco, RR Line, Hedonic, Robeauty, Dermaskill, Bourjois, Lumene, Max Factor."}
            ],
            "max_tokens": 1000
        }
        resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data, timeout=60)
        text = resp.json()["choices"][0]["message"]["content"]
        await update.message.reply_text(f"🤖 Агент №1\n\n{text}")
    except Exception as e:
        await update.message.reply_text(f"Помилка: {str(e)}")
def main():
    if not ANTHROPIC_KEY:
        print("ПОМИЛКА: Встановіть ANTHROPIC_API_KEY")
        return
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
    import threading
    import schedule
    import time

    def run_agent1_weekly():
        import asyncio
        from agent1 import run_agent1
        asyncio.run(run_agent1())

    def scheduler_thread():
        schedule.every().monday.at("09:00").do(run_agent1_weekly)
        while True:
            schedule.run_pending()
            time.sleep(60)

    t = threading.Thread(target=scheduler_thread, daemon=True)
    t.start()
    main()
