import os
import asyncio
from datetime import datetime
from telegram import Bot
from openai import OpenAI

TELEGRAM_TOKEN = "8608440555:AAGBRdr8IA2iB9sLCEJFnPDBtRMeSlfkFLU"
OWNER_CHAT_ID = 6854020655
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

SEARCH_PROMPT = """Ти — AI агент для бізнесу AVANTI Cosmetics (дистрибуція косметики, Закарпаття, Україна).

ТВОЯ ЗАДАЧА: Знайди актуальну інформацію по двох напрямках.

НАПРЯМОК 1 — ТРЕНДИ КОСМЕТИКИ:
Що зараз популярно в Instagram, TikTok серед косметики:
- Манікюр, нігті, гель-лаки
- Догляд за волоссям, укладки
- Догляд за обличчям, сироватки
Фокус: Україна + Польща + Корея + Захід

НАПРЯМОК 2 — НОВІ ТОРГОВІ МАРКИ:
Шукай українських імпортерів або виробників косметики які:
- Мають ЕКСКЛЮЗИВ на ринку України
- Працюють ЧЕРЕЗ ДИСТРИБ'ЮТОРІВ (не напряму в магазини)
- Середній і вище середнього ціновий сегмент
- НЕ дешева косметика
- Схожі на: R-Line, ECHOSline, Meloni, DEEPLY, DAENG GI MEO RI, 
- Можуть дати оборот 200-300 тис грн/місяць

ПОТОЧНИЙ ПОРТФЕЛЬ (не пропонуй ці марки):
PNB, Siller, Adore, ECHOSline, EMMEBI ITALIA, MAIS, Apriori, AG Skin, 
Bbcos, C:ehko, Daeng gi meo ri, Deeply, GK Hair, Mielle, Meloni, 
MoroccanOil, Palco, RR Line, Hedonic, Robeauty, Dermaskill, Bourjois, Lumene, Maxfactor


ФОРМАТ ВІДПОВІДІ (українською):
🔥 ТРЕНДИ ТИЖНЯ
1. [тренд] — [пояснення чому актуально]
2. [тренд] — [пояснення]
3. [тренд] — [пояснення]

🏆 КАНДИДАТИ НА НОВІ ТМ
1. [назва ТМ] — [чому підходить, де знайти контакт]
2. [назва ТМ] — [чому підходить]
3. [назва ТМ] — [чому підходить]

💡 РЕКОМЕНДАЦІЯ
[Що конкретно зробити цього тижня для досягнення обороту 1.5 млн грн/міс]"""


async def run_agent1():
    client = OpenAI(api_key=OPENAI_KEY)
    bot = Bot(token=TELEGRAM_TOKEN)

    now = datetime.now()
    print(f"Агент №1 запущено: {now.strftime('%d.%m.%Y %H:%M')}")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ти експерт з косметичного ринку України. Відповідай українською мовою."},
                {"role": "user", "content": SEARCH_PROMPT}
            ],
            max_tokens=1500,
            temperature=0.7
        )

        result = response.choices[0].message.content

        message = (
            f"🤖 *АГЕНТ №1 — Щотижневий звіт*\n"
            f"_{now.strftime('%d.%m.%Y')}_\n\n"
            f"{result}"
        )

        await bot.send_message(
            chat_id=OWNER_CHAT_ID,
            text=message,
            parse_mode="Markdown"
        )

        print("Звіт надіслано успішно!")

    except Exception as e:
        print(f"Помилка: {e}")
        await bot.send_message(
            chat_id=OWNER_CHAT_ID,
            text=f"❌ Агент №1 помилка: {str(e)}"
        )

if __name__ == "__main__":
    asyncio.run(run_agent1())
  
