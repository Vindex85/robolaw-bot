import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage

# Переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HF_API_KEY = os.getenv("HF_API_KEY")  # API-ключ Hugging Face
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_IDS = {308383825, 321005569}
LAWYER_PHONE = "+7(999)916-04-83"

# Создание экземпляра бота и диспетчера
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Подключение к базе данных PostgreSQL
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    return conn

# Функция для отправки запроса к DeepSeek R1 (Hugging Face)
def get_dialogpt_response(question: str):
    url = "https://api-inference.huggingface.co/models/deepseek-ai/DeepSeek-R1"  # URL для модели DialoGPT

    headers = {
        "Authorization": f"Bearer {HF_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "inputs": question
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Проверка на ошибки
        data = response.json()
        return data[0]["generated_text"]
    except requests.exceptions.RequestException as e:
        return f"Ошибка при запросе к DeepSeek R1: {str(e)}"

# Функция для сохранения статистики вопросов
async def log_question(user_id: int, question: str, answer: str):
    conn = await init_db()
    await conn.execute('''
        INSERT INTO questions(user_id, question, answer) VALUES($1, $2, $3)
    ''', user_id, question, answer)
    await conn.close()

# Функция для получения и обновления количества вопросов пользователя
async def get_question_count(user_id: int):
    conn = await init_db()
    row = await conn.fetchrow('''
        SELECT question_count FROM users WHERE user_id = $1
    ''', user_id)
    
    if row:
        count = row['question_count']
    else:
        await conn.execute('''
            INSERT INTO users(user_id, question_count) VALUES($1, 0)
        ''', user_id)
        count = 0

    await conn.close()
    return count

async def update_question_count(user_id: int, count: int):
    conn = await init_db()
    await conn.execute('''
        UPDATE users SET question_count = $1 WHERE user_id = $2
    ''', count, user_id)
    await conn.close()

# Обработчик команды /start
@dp.message_handler(commands=["start"])
async def send_welcome(message: Message):
    await message.answer("Привет! Я Робот-Юрист, задайте мне свой юридический вопрос (Вы можете задать до 3 вопросов).")

# Обработчик текстовых сообщений
@dp.message_handler()
async def handle_question(message: Message):
    user_id = message.from_user.id
    question = message.text

    # Получаем количество вопросов пользователя
    count = await get_question_count(user_id)

    # Проверяем, не достиг ли пользователь лимита
    if count >= 3:
        await message.answer(f"Вы достигли лимита в 3 вопроса. Если хотите узнать больше, позвоните юристу по номеру: {LAWYER_PHONE}")
        return

    # Генерация ответа с помощью DeepSeek
    answer = get_deepseek_response(question)

    # Логируем вопрос и ответ в базу данных
    await log_question(user_id, question, answer)

    # Обновляем счётчик вопросов пользователя
    await update_question_count(user_id, count + 1)

    # Отправляем ответ
    await message.answer(f"{answer}\n\nЕсли хотите узнать больше, позвоните юристу по номеру: {LAWYER_PHONE}")

# Запуск бота
if __name__ == '__main__':
    dp.run_polling()
