from dotenv import load_dotenv
import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, Update
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from openai import OpenAI
from quart import Quart, request

load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Загружаем переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOTHUB_API_KEY = os.getenv("BOTHUB_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-app-name.onrender.com/webhook")
PORT = int(os.getenv("PORT", 10000))
LAWYER_PHONE = "+7(999)916-04-83"
ADMIN_IDS = [308383825, 321005569]

if not TELEGRAM_BOT_TOKEN or not BOTHUB_API_KEY:
    raise ValueError("Ошибка: TELEGRAM_BOT_TOKEN или BOTHUB_API_KEY не найдены в .env")

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Лимит вопросов на одного пользователя
user_question_count = {}

# Инициализация OpenAI-клиента через Bothub API
client = OpenAI(
    api_key=BOTHUB_API_KEY,
    base_url="https://bothub.chat/api/v2/openai/v1"
)

# Функция запроса к Bothub API
def get_ai_response(prompt):
    try:
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты — юридический консультант. Отвечай кратко, чётко и профессионально. Давай только общую информацию, если нет конкретных деталей, и напоминай, что это не заменяет консультацию юриста."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            max_tokens=300,
            top_p=0.9,
            stream=True,
        )

        response = ""
        for chunk in stream:
            part = chunk.to_dict()['choices'][0]['delta'].get('content', None)
            if part:
                response += part
        return response if response else "Извините, не удалось получить ответ от ИИ."
    except Exception as e:
        logging.error(f"Ошибка при запросе к Bothub API: {e}")
        return "Извините, произошла ошибка при обработке ответа от ИИ."

# Обработчик команды /start
@router.message(CommandStart())
async def send_welcome(message: Message):
    user_question_count[message.from_user.id] = 0
    await message.answer("Привет! Я Робот-Юрист, задайте мне свой юридический вопрос.")

# Обработчик текстовых сообщений
@router.message(F.text)
async def handle_question(message: Message):
    await message.answer("Ваш вопрос обрабатывается...")
    user_id = message.from_user.id
    if user_id not in user_question_count:
        user_question_count[user_id] = 0
    if user_question_count[user_id] >= 3:
        await message.answer(
            f"Вы достигли лимита в 3 вопроса. Если хотите узнать больше, позвоните юристу по номеру: {LAWYER_PHONE}"
        )
        return
    question = message.text
    answer = get_ai_response(question)
    await message.answer(f"{answer}\n\nХотите узнать больше? Позвоните юристу по номеру: {LAWYER_PHONE}")

# Настройка веб-сервера на Quart для обработки вебхуков
app = Quart(__name__)

@app.route("/ping", methods=["GET"])
async def ping():
    return {"status": "pong"}, 200

@app.route("/webhook", methods=["POST"])
async def webhook():
    try:
        update = Update.model_validate(await request.json)
        await dp.feed_update(bot, update)
        return "OK", 200
    except Exception as e:
        logging.error(f"Ошибка в webhook: {e}")
        return "Error", 500

# Установка Webhook
async def set_webhook():
    await bot.set_webhook(WEBHOOK_URL)

# Запуск бота с Webhook
async def main():
    await set_webhook()
    logging.info(f"✅ Webhook установлен на {WEBHOOK_URL}")
    await app.run_task(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    asyncio.run(main())
