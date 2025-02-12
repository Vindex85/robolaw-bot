import asyncio
import logging
import asyncpg
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.filters import Command
from openai import OpenAI
from dotenv import load_dotenv

# Настройки
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_IDS = {308383825, 321005569}  # ID администраторов
LAWYER_PHONE = "+7(999)916-04-83"

# Инициализация бота и базы данных
bot = Bot(token=TOKEN)
dp = Dispatcher()
client = OpenAI(api_key=OPENAI_API_KEY)

async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            question_count INT DEFAULT 0
        );
    ''')
    await conn.close()

async def get_question_count(user_id: int):
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow("SELECT question_count FROM users WHERE user_id = $1", user_id)
    await conn.close()
    return row["question_count"] if row else 0

async def update_question_count(user_id: int):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        INSERT INTO users (user_id, question_count) 
        VALUES ($1, 1) 
        ON CONFLICT (user_id) DO UPDATE 
        SET question_count = users.question_count + 1;
    ''', user_id)
    await conn.close()

async def get_ai_response(question: str):
    response = client.completions.create(
        model="gpt-4",
        prompt=f"Юридический вопрос: {question}\nОтвет:",
        max_tokens=200
    )
    return response.choices[0].text.strip()

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("Привет! Я юридический бот. Задайте мне ваш вопрос.")

@dp.message()
async def handle_question(message: Message):
    user_id = message.from_user.id
    question_count = await get_question_count(user_id)

    if question_count >= 3:
        await message.answer(f"Если хотите узнать больше, позвоните юристу по номеру: {LAWYER_PHONE}")
        return

    answer = await get_ai_response(message.text)
    await update_question_count(user_id)
    await message.answer(f"{answer}\n\nЕсли хотите узнать больше, позвоните юристу по номеру: {LAWYER_PHONE}")

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Здесь вызываем start_polling без использования asyncio.run(), так как aiogram сам управляет циклом событий
<<<<<<< HEAD
    asyncio.run(main())
=======
    asyncio.run(main())
>>>>>>> e85b2e1bfebe99538d6acce0eb88551b45d869f0
