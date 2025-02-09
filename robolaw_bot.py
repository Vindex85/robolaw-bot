import logging
import sqlite3
import time
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext

# Логирование
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = "7768038184:AAGWYf4G5cnteBnTIzGpOSFUZUSDwvigLW8"

# ID администраторов (юристов)
ADMIN_IDS = [321005569, 308383825]  # Замените на список ID админов

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

# Список готовых вопросов и ответов
FAQ = {
      "Как составить договор?": "✅ Включите в договор:\n- Стороны\n- Предмет\n- Цена\n- Сроки\n- Ответственность сторон\nЛучше проконсультироваться с юристом.",
      "Что делать при увольнении?": "✅ Проверьте, соответствует ли увольнение Трудовому кодексу. Можно обжаловать в суде или подать жалобу в инспекцию труда.",
      "Как оспорить штраф?": "✅ Подайте жалобу в ГИБДД или суд в течение 10 дней с момента получения штрафа.",
      "Какие права есть у арендатора?": "✅ Арендатор имеет право на:\n- Своевременное устранение неисправностей\n- Возврат депозита\n- Защиту от незаконного выселения.",
      "Как вернуть некачественный товар?": "✅ Вы можете вернуть товар в течение 14 дней. Если обнаружен брак – можно требовать возврат денег или обмен."
}

# Команда /start
async def start(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("💬 Задать вопрос юристу", callback_data="ask_lawyer")],
        [InlineKeyboardButton("📌 Популярные вопросы", callback_data="faq")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Привет! Я бот-юрист 🤖. Чем могу помочь?", reply_markup=reply_markup)

# Обработка кнопок
async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "ask_lawyer":
        await query.message.reply_text("✏️ Напишите свой вопрос, и юрист ответит вам в ближайшее время.")
    
    elif query.data == "faq":
        keyboard = [[InlineKeyboardButton(q, callback_data=q)] for q in FAQ.keys()]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("📌 Выберите популярный вопрос:", reply_markup=reply_markup)
    
    elif query.data in FAQ:
        await query.message.reply_text(f"💡 *Ответ:*\n{FAQ[query.data]}", parse_mode="Markdown")

# Обработка новых вопросов
async def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    user_name = update.message.from_user.first_name
    question = update.message.text
    message_id = update.message.message_id
    timestamp = int(time.time())

    if user_id in ADMIN_IDS:
        logging.info(f"🛑 Юрист {user_name} ({user_id}) написал: '{question}'. Игнорируем как новый вопрос.")
        return

    logging.info(f"📩 Новый вопрос от {user_name} (ID: {user_id}), message_id: {message_id}")

    with db_lock:
        cursor.execute("INSERT INTO questions (user_id, message_id, question, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
                       (user_id, message_id, question, timestamp))
        conn.commit()

    await context.bot.send_message(
        chat_id=ADMIN_IDS[0],  
        text=f"📩 *Новый вопрос от {user_name} (ID: {user_id})*\n\n❓ {question}\n\n"
             f"📌 Ответьте на это сообщение кнопкой 'Ответить', чтобы я отправил ответ пользователю.",
        parse_mode="Markdown"
    )

    await update.message.reply_text("✅ Ваш вопрос отправлен юристу. Ожидайте ответа.")

# Обработка ответов юриста
async def reply_to_user(update: Update, context: CallbackContext) -> None:
    """Юрист отвечает на вопрос пользователя"""
    
    user_id = update.message.from_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ У вас нет прав для выполнения этой команды.")
        return

    if update.message.reply_to_message:
        reply_text = update.message.text
        replied_message_id = update.message.reply_to_message.message_id

        logging.info(f"🔍 Юрист отвечает на сообщение ID: {replied_message_id}. Проверяем в БД...")

        with db_lock:
            cursor.execute("SELECT user_id FROM questions WHERE message_id = ?", (replied_message_id,))
            result = cursor.fetchone()

        if not result:
            logging.warning(f"⚠️ message_id={replied_message_id} НЕ НАЙДЕН в БД. Ищем по user_id...")
            
            with db_lock:
                cursor.execute("SELECT user_id, message_id FROM questions WHERE status = 'pending' ORDER BY created_at DESC LIMIT 1")
                result = cursor.fetchone()

        if result:
            recipient_id, original_message_id = result
            logging.info(f"✅ Найден user_id: {recipient_id}. Отправляем ответ...")

            with db_lock:
                cursor.execute("UPDATE questions SET answer = ?, status = 'answered' WHERE user_id = ? AND message_id = ?", 
                               (reply_text, recipient_id, original_message_id))
                conn.commit()

            await context.bot.send_message(chat_id=recipient_id, text=f"📩 Ответ юриста:\n\n💬 {reply_text}")
            await update.message.reply_text("✅ Ответ отправлен пользователю.")
        else:
            logging.error(f"⚠️ Ошибка: не удалось найти ID пользователя для ответа!")
            await update.message.reply_text("⚠️ Ошибка: не удалось найти пользователя для этого вопроса.")
    else:
        await update.message.reply_text("⚠️ Используйте 'Ответить' на вопрос пользователя, чтобы отправить ответ!")

# Запуск бота
def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.REPLY & filters.TEXT, reply_to_user))

    application.run_polling()

if __name__ == "__main__":
    main()
