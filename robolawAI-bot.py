import os
import logging
import asyncio
import requests
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from openai import OpenAI

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Загружаем переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOTHUB_API_KEY = os.getenv("BOTHUB_API_KEY")  # Bothub API Key
LAWYER_PHONE = "+7(999)916-04-83"

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
    model="gpt-4o-mini-2024-07-18",
    messages=[{"role": "user", "content": "Say this is a test"}],
    stream=True,
)

for chunk in stream:
    part = chunk.to_dict()['choices'][0]['delta'].get('content', None)
    if part:  # Если получен контент, печатаем его
        print(part)

        # Проверяем структуру ответа
        if hasattr(chat_completion, "choices") and len(chat_completion.choices) > 0:
            return chat_completion.choices[0].message.content
        else:
            return "Извините, произошла ошибка при обработке ответа от ИИ."
    
    except Exception as e:
        logging.error(f"Ошибка при запросе к Bothub API: {e}")
        return "Извините, произошла ошибка при обработке ответа от ИИ."

# Обработчик команды /start
@router.message(CommandStart())
async def send_welcome(message: Message):
    user_question_count[message.from_user.id] = 0
    await message.answer(
        "Привет! Я Робот-Юрист, задайте мне свой юридический вопрос (Вы можете задать до 3 вопросов)."
    )

# Обработчик текстовых сообщений
@router.message(F.text)
async def handle_question(message: Message):
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

    user_question_count[user_id] += 1  # Увеличиваем счетчик вопросов

    await message.answer(f"{answer}\n\nХотите узнать больше? Позвоните юристу по номеру: {LAWYER_PHONE}")

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())