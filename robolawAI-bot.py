from dotenv import load_dotenv
import os
import logging
import asyncio
import asyncpg
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, Update, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from openai import OpenAI
from quart import Quart, request

load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Загружаем переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOTHUB_API_KEY = os.getenv("BOTHUB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://robolaw-bot.onrender.com/webhook")
PORT = int(os.getenv("PORT", 10000))
LAWYER_PHONE = "+79999160483"
ADMIN_IDS = [int(admin_id) for admin_id in os.getenv("ADMIN_IDS", "308383825,321005569").split(",")]

if not TELEGRAM_BOT_TOKEN or not BOTHUB_API_KEY or not DATABASE_URL:
    raise ValueError("Ошибка: TELEGRAM_BOT_TOKEN, BOTHUB_API_KEY или DATABASE_URL не найдены в .env")

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Инициализация OpenAI-клиента через Bothub API
client = OpenAI(
    api_key=BOTHUB_API_KEY,
    base_url="https://bothub.chat/api/v2/openai/v1"
)

# Функции для работы с PostgreSQL
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS user_limits (
            user_id BIGINT PRIMARY KEY,
            question_count INTEGER DEFAULT 0
        )
    ''')
    await conn.close()

async def get_user_question_count(user_id):
    conn = await asyncpg.connect(DATABASE_URL)
    count = await conn.fetchval('SELECT question_count FROM user_limits WHERE user_id = $1', user_id)
    await conn.close()
    return count if count is not None else 0

async def set_user_question_count(user_id, count):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        'INSERT INTO user_limits (user_id, question_count) VALUES ($1, $2) '
        'ON CONFLICT (user_id) DO UPDATE SET question_count = $2',
        user_id, count
    )
    await conn.close()

# Функция запроса к Bothub API с учётом контекста
def get_ai_response(messages):
    try:
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
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

# Функция отправки вопроса админам
async def notify_admins(user_id, username, phone_number, question):
    for admin_id in ADMIN_IDS:
        try:
            phone_info = f"Телефон: {phone_number}" if phone_number else "Телефон: не указан"
            await bot.send_message(
                admin_id,
                f"Новый вопрос от пользователя:\n"
                f"ID: {user_id}\n"
                f"Ник: @{username if username else 'нет ника'}\n"
                f"{phone_info}\n"
                f"Вопрос: {question}"
            )
        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения админу {admin_id}: {e}")

# Обработчик команды /start
@router.message(CommandStart())
async def send_welcome(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await set_user_question_count(user_id, 0)
    await state.clear()  # Очищаем контекст при старте
    await message.answer("Привет! Я Робот-Юрист. Задайте мне свой юридический вопрос.")

# Обработчик команды /help
@router.message(Command("help"))
async def send_help(message: Message):
    await message.answer(
        "Я — Робот-Юрист. Задавайте юридические вопросы, и я отвечу профессионально. "
        f"Лимит — 3 вопроса. Для сложных случаев звоните: {LAWYER_PHONE}"
    )

# Обработчик текстовых сообщений
@router.message(F.text)
async def handle_question(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not message.text.strip():
        await message.answer("Пожалуйста, задайте вопрос текстом.")
        return

    count = await get_user_question_count(user_id)
    if count >= 3:
        await message.answer(f"Лимит 3 вопроса достигнут. Если хотите узнать больше, позвоните или напишите юристу: {LAWYER_PHONE}")
        return

    await message.answer("Ваш вопрос обрабатывается...")

    question = message.text
    username = message.from_user.username
    phone_number = message.from_user.phone_number if hasattr(message.from_user, 'phone_number') else None
    logging.info(f"User {user_id} asked: {question}")

    await notify_admins(user_id, username, phone_number, question)

    # Получаем текущий контекст из состояния
    data = await state.get_data()
    history = data.get("history", [
        {"role": "system", "content": "Ты — юридический консультант. Отвечай кратко, чётко и профессионально. Давай только общую информацию, если нет конкретных деталей, и напоминай, что это не заменяет консультацию юриста."}
    ])

    # Добавляем новый вопрос в историю
    history.append({"role": "user", "content": question})
    answer = get_ai_response(history)
    history.append({"role": "assistant", "content": answer})

    # Сохраняем обновлённую историю
    await state.set_data({"history": history})
    logging.info(f"Response to {user_id}: {answer}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Задать ещё вопрос", callback_data="ask_again")],
        [InlineKeyboardButton(text="Уточнить", callback_data="clarify")],
    ])
    
    await message.answer(
        f"{answer}\n\nХотите узнать больше? Позвоните юристу по номеру: {LAWYER_PHONE}",
        reply_markup=keyboard
    )
    await set_user_question_count(user_id, count + 1)

# Обработчик "Задать ещё вопрос"
@router.callback_query(F.data == "ask_again")
async def process_ask_again(callback: CallbackQuery, state: FSMContext):
    await state.clear()  # Очищаем историю для нового вопроса
    await callback.message.edit_text("Задайте новый вопрос:")
    await callback.answer()

# Обработчик "Уточнить"
@router.callback_query(F.data == "clarify")
async def process_clarify(callback: CallbackQuery):
    await callback.message.edit_text("Пожалуйста, уточните ваш вопрос:")
    await callback.answer()

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

# Установка Webhook с явным указанием типов обновлений
async def set_webhook():
    await bot.set_webhook(WEBHOOK_URL, allowed_updates=["message", "callback_query"])

# Запуск бота с Webhook
async def main():
    await init_db()
    await set_webhook()
    logging.info(f"✅ Webhook установлен на {WEBHOOK_URL}")
    await app.run_task(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    asyncio.run(main())