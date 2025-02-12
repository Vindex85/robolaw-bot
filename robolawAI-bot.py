from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
import asyncio
import logging
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOTHUB_API_KEY = os.getenv("BOTHUB_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()

client = OpenAI(
    api_key=BOTHUB_API_KEY,
    base_url='https://bothub.chat/api/v2/openai/v1'
)

user_question_count = {}
MAX_QUESTIONS = 3

def get_ai_response(prompt):
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "Ты - юридический помощник. Всегда отвечай на русском языке."},
                {"role": "user", "content": prompt}
            ],
            model="gpt-4o-mini-2024-07-18",
        )

        logging.info(f"Ответ от API: {chat_completion}")

        if hasattr(chat_completion, "choices") and len(chat_completion.choices) > 0:
            return chat_completion.choices[0].message.content
        else:
            return "Извините, произошла ошибка при обработке ответа от ИИ."

    except Exception as e:
        logging.error(f"Ошибка при запросе к Bothub API: {e}")
        return "Извините, произошла ошибка при обработке ответа от ИИ."

@dp.message(Command("start"))
async def start_command(message: Message):
    user_question_count[message.from_user.id] = 0
    await message.answer("Привет! Я Робот-Юрист, задайте мне свой юридический вопрос (Вы можете задать до 3 вопросов).")

@dp.message()
async def handle_question(message: Message):
    user_id = message.from_user.id
    if user_id not in user_question_count:
        user_question_count[user_id] = 0

    if user_question_count[user_id] >= MAX_QUESTIONS:
        await message.answer("Вы исчерпали лимит вопросов. Если хотите узнать больше, позвоните юристу по номеру: +7(999)916-04-83")
        return

    question = message.text
    answer = get_ai_response(question)

    user_question_count[user_id] += 1  # Увеличиваем счетчик вопросов

    await message.answer(f"{answer}\n\nХотите узнать больше? Позвоните юристу по номеру: {LAWYER_PHONE}")

async def main():
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
