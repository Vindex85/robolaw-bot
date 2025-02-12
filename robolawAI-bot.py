import logging
import os
import requests
import asyncio
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart

# Загружаем переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOTHUB_API_KEY = os.getenv("BOTHUB_API_KEY")  # Новый ключ API для Bothub
ADMIN_IDS = {308383825, 321005569}
LAWYER_PHONE = "+7(999)916-04-83"

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Создание бота и диспетчера
bot = Bot(token=TELEGRAM_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

dp.include_router(router)

# Хранилище количества вопросов
user_question_count = {}

# Функция получения списка моделей
def get_models():
    url = "https://bothub.chat/api/v2/model/list?children=1"
    headers = {
        'Authorization': f'Bearer {BOTHUB_API_KEY}',
        'Content-Type': 'application/json'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        models = response.json()
        print("Models:", models)  # Логируем модели
        return models
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при получении моделей: {e}")
        return []

# Функция запроса к Bothub API с использованием GPT-3.5-turbo
def get_gpt_response(prompt):
    # Получаем список доступных моделей
    models = get_models()
    if not models:
        return "Извините, не удалось получить доступные модели."

    # Находим модель GPT-3.5-turbo
    gpt_model = next((model for model in models if model.get('name') == 'gpt-3.5-turbo'), None)
    
    if not gpt_model:
        return "Извините, нужная модель не найдена."

    headers = {
        "Authorization": f"Bearer {BOTHUB_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "messages": [{"role": "user", "content": prompt}],
        "model": "gpt-3.5-turbo"
    }

    try:
        response = requests.post(
            "https://bothub.chat/api/v2/openai/v1/chat/completions",  # URL для отправки запроса
            headers=headers,
            json=data
        )

        # Логируем ответ
        print("Status Code:", response.status_code)
        print("Response Body:", response.text)

        if response.status_code != 200:
            return "Извините, произошла ошибка при обработке запроса к ИИ."

        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"Ошибка при запросе к Bothub API: {e}")
        return "Извините, произошла ошибка при обработке ответа от ИИ."

# Обработчик команды /start
@router.message(CommandStart())
async def send_welcome(message: Message):
    user_question_count[message.from_user.id] = 0
    await message.answer("Привет! Я Робот-Юрист, задайте мне свой юридический вопрос (Вы можете задать до 3 вопросов).")

# Обработчик текстовых сообщений
@router.message(F.text)
async def handle_question(message: Message):
    user_id = message.from_user.id
    
    if user_id not in user_question_count:
        user_question_count[user_id] = 0
    
    if user_question_count[user_id] >= 3:
        await message.answer(f"Вы достигли лимита в 3 вопроса. Если хотите узнать больше, позвоните юристу по номеру: {LAWYER_PHONE}")
        return
    
    question = message.text
    answer = get_gpt_response(question)
    
    user_question_count[user_id] += 1
    await message.answer(f"{answer}\n\nЕсли хотите узнать больше, позвоните юристу по номеру: {LAWYER_PHONE}")

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
