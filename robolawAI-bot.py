from dotenv import load_dotenv
import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from openai import OpenAI

load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Загружаем переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOTHUB_API_KEY = os.getenv("BOTHUB_API_KEY")  # Bothub API Key
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
        # Синхронный запрос для генерации текста с потоком
        stream = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )

        response = ""
        # Потоковая обработка данных
        for chunk in stream:
            part = chunk.to_dict()['choices'][0]['delta'].get('content', None)
            if part:
                response += part
        return response if response else "Извините, не удалось получить ответ от ИИ."

    except Exception as e:
        logging.error(f"Ошибка при запросе к Bothub API: {e}")
        return "Извините, произошла ошибка при обработке ответа от ИИ."

# Функция отправки сообщений администраторам
async def notify_admins(message: Message):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"Новый вопрос от пользователя @{message.from_user.username} (ID: {message.from_user.id}):\n\n{message.text}")
        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения админу {admin_id}: {e}")

# Обработчик команды /start
@router.message(CommandStart())
async def send_welcome(message: Message):
    user_question_count[message.from_user.id] = 0
    await message.answer(
        "Привет! Я Робот-Юрист, задайте мне свой юридический вопрос."
    )

# Обработчик текстовых сообщений
@router.message(F.text)
async def handle_question(message: Message):
    await message.answer("Ваш вопрос обрабатывается...")
    user_id = message.from_user.id

    # Проверяем, не превышен ли лимит вопросов
    if user_id not in user_question_count:
        user_question_count[user_id] = 0

    if user_question_count[user_id] >= 3:
        await message.answer(
            f"Вы достигли лимита в 3 вопроса. Если хотите узнать больше, позвоните юристу по номеру: {LAWYER_PHONE}"
        )
        return

    # Отправляем вопрос ИИ
    question = message.text
    answer = get_ai_response(question)

    # Уведомляем администраторов
    await notify_admins(message)

    user_question_count[user_id] += 1  # Увеличиваем счетчик вопросов

    await message.answer(f"{answer}\n\nХотите узнать больше? Позвоните юристу по номеру: {LAWYER_PHONE}")

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())