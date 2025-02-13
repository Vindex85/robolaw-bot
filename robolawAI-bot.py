import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import Message, Update
from aiogram.fsm.storage.memory import MemoryStorage
from quart import Quart, request
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Загружаем переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOTHUB_API_KEY = os.getenv("BOTHUB_API_KEY")
LAWYER_PHONE = "+7(999)916-04-83"
ADMIN_IDS = [308383825, 321005569]
PORT = int(os.getenv("PORT", 10000))  # Render требует порт выше 10000

if not TELEGRAM_BOT_TOKEN or not BOTHUB_API_KEY:
    raise ValueError("Ошибка: TELEGRAM_BOT_TOKEN или BOTHUB_API_KEY не найдены в .env")

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Инициализация диспетчера и роутера
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)  

# Инициализация Quart
app = Quart(__name__)

# Счетчик вопросов
user_question_count = {}

# API-клиент OpenAI (Bothub)
client = OpenAI(
    api_key=BOTHUB_API_KEY,
    base_url="https://bothub.chat/api/v2/openai/v1"
)

# Функция для запроса к Bothub API
def get_ai_response(prompt):
    try:
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        response = ""
        for chunk in stream:
            part = chunk.to_dict()['choices'][0]['delta'].get('content', None)
            if part:
                response += part
        return response if response else "Ошибка ИИ."
    except Exception as e:
        logging.error(f"Ошибка запроса к Bothub API: {e}")
        return "Произошла ошибка при обработке ответа."

# Отправка сообщений администраторам
async def notify_admins(message: Message):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"Новый вопрос от @{message.from_user.username} (ID: {message.from_user.id}):\n\n{message.text}")
        except Exception as e:
            logging.error(f"Ошибка при отправке админу {admin_id}: {e}")

# Обработчик команды /start
@router.message(CommandStart())
async def send_welcome(message: Message):
    user_question_count[message.from_user.id] = 0
    await message.answer("Привет! Я Робот-Юрист, задайте мне свой юридический вопрос.")

# Обработчик текстовых сообщений
@router.message()
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
    answer = get_ai_response(message.text)
    await notify_admins(message)
    user_question_count[user_id] += 1
    await message.answer(f"{answer}\n\nХотите узнать больше? Позвоните юристу по номеру: {LAWYER_PHONE}")

# Webhook-обработчик Quart
@app.route("/webhook", methods=["POST"])
async def webhook():
    try:
        data = await request.get_json()  # Получаем данные от Telegram
        update = Update(**data)  # Создаём объект Update

        # Новый способ обработки обновлений в aiogram 3.x
        await dp.process_update(update)

        return "OK", 200
    except Exception as e:
        logging.error(f"Ошибка в webhook: {e}")
        return "Internal Server Error", 500

# Функция для установки Webhook
async def on_startup():
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'your-app.onrender.com')}/webhook"
    await bot.set_webhook(webhook_url)
    logging.info(f"✅ Webhook установлен на {webhook_url}")

# Запуск приложения
if __name__ == "__main__":
    logging.info("🚀 Запуск бота...")
    asyncio.run(on_startup())  # Асинхронная установка Webhook
    app.run(host="0.0.0.0", port=PORT)  # Используем порт из Render
