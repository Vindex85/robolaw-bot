import sqlite3
import time
import threading
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, CallbackContext
)

# Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Токен бота (замени на свой токен!)
TOKEN = "ТВОЙ_ТОКЕН_ОТ_BOTFATHER"

# ID администраторов (укажи свой ID и ID юриста)
ADMIN_IDS = {321005569, 308383825}  # Можно добавить несколько ID через запятую

# Подключение к базе SQLite
conn = sqlite3.connect("law_bot.db", check_same_thread=False)
cursor = conn.cursor()
db_lock = threading.Lock()

# Создание таблицы вопросов
with db_lock:
    cursor.execute('''CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        question TEXT,
        answer TEXT,
        status TEXT DEFAULT 'pending',
        created_at INTEGER,
        message_id INTEGER
    )''')
    conn.commit()

# Часто задаваемые вопросы
faq = {
    "Как составить договор?": "Основные условия: стороны, предмет, цена, сроки, ответственность. Лучше проконсультироваться с юристом.",
    "Что делать при увольнении?": "Проверьте, соответствует ли увольнение Трудовому кодексу. Можно обжаловать в суде или подать жалобу в инспекцию труда.",
    "Как оспорить штраф?": "Подайте жалобу в ГИБДД или суд в течение 10 дней с момента получения штрафа. Обоснуйте свою позицию доказательствами.",
    "Какие права есть у арендатора?": "Арендатор имеет право на своевременное устранение неисправностей, возврат депозита и защиту от незаконного выселения.",
    "Как вернуть некачественный товар?": "Потребитель может вернуть товар в течение 14 дней или потребовать возврата денег при выявлении дефектов."
}

# Функция /start
async def start(update: Update, context: CallbackContext) -> None:
    keyboard = [[InlineKeyboardButton(q, callback_data=q)] for q in faq.keys()]
    keyboard.append([InlineKeyboardButton("💬 Задать вопрос юристу", callback_data="ask_lawyer")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Привет! Я бот-юрист 🤖. Выберите вопрос или задайте свой:", reply_markup=reply_markup)

# Функция обработки кнопок
async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "ask_lawyer":
        await query.message.reply_text("✏️ Напишите свой вопрос, и юрист ответит вам в ближайшее время.")
        return
    
    response = faq.get(query.data, "Извините, ответа на этот вопрос пока нет.")
    await query.edit_message_text(text=f"❓ {query.data}\n\n💡 {response}")

# Функция получения вопросов
async def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    question = update.message.text
    message_id = update.message.message_id
    timestamp = int(time.time())

    with db_lock:
        cursor.execute("INSERT INTO questions (user_id, message_id, question, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
                       (user_id, message_id, question, timestamp))
        conn.commit()

    # Отправка вопроса юристу
    for admin_id in ADMIN_IDS:
        await context.bot.send_message(
            chat_id=admin_id,
            text=f"📩 *Новый вопрос от пользователя (ID: {user_id})*\n\n❓ {question}\n\nОтветьте на это сообщение, и я отправлю ответ пользователю.",
            parse_mode="Markdown"
        )

    await update.message.reply_text("✅ Ваш вопрос отправлен юристу. Ожидайте ответа.")

# Функция ответа юриста
async def reply_to_user(update: Update, context: CallbackContext) -> None:
    if update.message.from_user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ У вас нет прав для выполнения этой команды.")
        return

    if update.message.reply_to_message:
        answer_text = update.message.text
        replied_message = update.message.reply_to_message.text

        with db_lock:
            cursor.execute("SELECT user_id FROM questions WHERE question = ? AND status='pending'", (replied_message,))
            user_id = cursor.fetchone()

        if user_id:
            user_id = user_id[0]

            with db_lock:
                cursor.execute("UPDATE questions SET answer = ?, status = 'answered' WHERE user_id = ? AND question = ?",
                               (answer_text, user_id, replied_message))
                conn.commit()

            await context.bot.send_message(chat_id=user_id, text=f"📩 Ответ юриста:\n\n💬 {answer_text}")
            await update.message.reply_text("✅ Ответ отправлен пользователю.")
        else:
            await update.message.reply_text("⚠️ Ошибка: не удалось найти пользователя.")
    else:
        await update.message.reply_text("⚠️ Отвечайте на сообщение с вопросом пользователя!")

# Функция вывода статистики
async def stats(update: Update, context: CallbackContext) -> None:
    if update.message.from_user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ У вас нет прав для просмотра статистики.")
        return

    with db_lock:
        cursor.execute("SELECT COUNT(*) FROM questions WHERE status='pending'")
        pending_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM questions WHERE status='answered'")
        answered_count = cursor.fetchone()[0]

    stats_message = (
        f"📊 **Статистика**:\n\n"
        f"📝 **Неотвеченных вопросов**: {pending_count}\n"
        f"✅ **Отвеченных вопросов**: {answered_count}\n"
    )

    await update.message.reply_text(stats_message)

# Запуск бота
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.REPLY & filters.TEXT, reply_to_user))

    print("✅ Бот запущен! Ожидание команд...")
    app.run_polling()

if __name__ == "__main__":
    main()
