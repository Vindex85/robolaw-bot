import sqlite3
import time
import threading
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext

# Логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ID администраторов (список)
ADMIN_IDS = {321005569, 308383825}  # Укажи нужные ID админов

# Подключение к базе данных
conn = sqlite3.connect("law_bot.db", check_same_thread=False)
cursor = conn.cursor()
db_lock = threading.Lock()

# Создание таблицы, если её нет
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

# Готовые вопросы-ответы
faq = {
    "Как составить договор?": "✅ Включите в договор:\n- Стороны\n- Предмет\n- Цена\n- Сроки\n- Ответственность сторон\nЛучше проконсультироваться с юристом.",
    "Что делать при увольнении?": "✅ Проверьте, соответствует ли увольнение Трудовому кодексу. Можно обжаловать в суде или подать жалобу в инспекцию труда.",
    "Как оспорить штраф?": "✅ Подайте жалобу в ГИБДД или суд в течение 10 дней с момента получения штрафа.",
    "Какие права есть у арендатора?": "✅ Арендатор имеет право на:\n- Своевременное устранение неисправностей\n- Возврат депозита\n- Защиту от незаконного выселения.",
    "Как вернуть некачественный товар?": "✅ Вы можете вернуть товар в течение 14 дней. Если обнаружен брак – можно требовать возврат денег или обмен.",
}

# Команда /start
def start(update: Update, context: CallbackContext) -> None:
    keyboard = [[InlineKeyboardButton(q, callback_data=q)] for q in faq.keys()]
    keyboard.append([InlineKeyboardButton("💬 Задать вопрос юристу", callback_data="ask_lawyer")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Привет! Я бот-юрист 🤖. Выберите вопрос или задайте свой:", reply_markup=reply_markup)

# Обработка кнопок (исправлено)
def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query

    try:
        query.answer()  # Подтверждаем, что бот обработал нажатие
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при query.answer(): {e}")

    if query.data == "ask_lawyer":
        query.message.reply_text("✏️ Напишите свой вопрос, и юрист ответит вам в ближайшее время.")
        return
    
    response = faq.get(query.data, "❌ Извините, ответа на этот вопрос пока нет.")
    
    try:
        query.message.reply_text(f"❓ {query.data}\n\n💡 {response}")
    except Exception as e:
        logger.error(f"Ошибка при отправке ответа на кнопку {query.data}: {e}")

# Обработка сообщений пользователей
def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    user_name = update.message.from_user.first_name
    question = update.message.text
    message_id = update.message.message_id
    timestamp = int(time.time())

    # Если юрист отвечает через "Ответить", передаем в reply_to_user()
    if update.message.reply_to_message and user_id in ADMIN_IDS:
        logger.info(f"🔹 Юрист {user_name} ({user_id}) отвечает на вопрос. Передаем в reply_to_user().")
        reply_to_user(update, context)
        return

    # Если юрист пишет без ответа → игнорируем
    if user_id in ADMIN_IDS:
        logger.info(f"🔹 Юрист {user_name} ({user_id}) написал без ответа: {question}. Игнорируем.")
        return

    try:
        with db_lock:
            cursor.execute("INSERT INTO questions (user_id, message_id, question, status, created_at) VALUES (?, ?, ?, 'pending', ?)", 
                           (user_id, message_id, question, timestamp))
            conn.commit()

        # Отправка вопроса админам
        for admin_id in ADMIN_IDS:
            try:
                context.bot.send_message(
                    chat_id=admin_id,
                    text=f"📩 *Новый вопрос от {user_name} (ID: {user_id})*\n\n❓ {question}\n\nОтветьте на это сообщение, и я отправлю ответ пользователю.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения админу {admin_id}: {e}")

        update.message.reply_text("✅ Ваш вопрос отправлен юристу. Ожидайте ответа.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении вопроса: {e}")
        update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")

# Обработка ответов юриста
def reply_to_user(update: Update, context: CallbackContext) -> None:
    if update.message.from_user.id not in ADMIN_IDS:
        update.message.reply_text("⚠️ У вас нет прав для выполнения этой команды.")
        return

    if not update.message.reply_to_message:
        update.message.reply_text("⚠️ Отвечайте на сообщение с вопросом пользователя!")
        return

    text = update.message.text
    message_id = update.message.reply_to_message.message_id

    logger.info(f"🔍 Юрист отвечает на сообщение ID: {message_id}, ищем user_id в БД...")

    extracted_user_id = None
    with db_lock:
        cursor.execute("SELECT user_id FROM questions WHERE message_id = ?", (message_id,))
        result = cursor.fetchone()
        if result:
            extracted_user_id = result[0]

    if not extracted_user_id:
        logger.warning(f"⚠️ Не найден message_id={message_id} в БД! Ищем по user_id...")
        with db_lock:
            cursor.execute("SELECT user_id FROM questions WHERE status='pending' ORDER BY created_at DESC LIMIT 1")
            result = cursor.fetchone()
            if result:
                extracted_user_id = result[0]
                logger.info(f"✅ Найден user_id={extracted_user_id} по статусу 'pending'.")

    if not extracted_user_id:
        update.message.reply_text("⚠️ Ошибка: не удалось определить пользователя.")
        logger.error(f"❌ Не удалось извлечь ID пользователя. message_id={message_id}")
        return

    try:
        with db_lock:
            cursor.execute("UPDATE questions SET answer = ?, status = 'answered' WHERE user_id = ? AND status='pending'", 
                           (text, extracted_user_id))
            conn.commit()

            context.bot.send_message(chat_id=extracted_user_id, text=f"📩 Ответ юриста:\n\n💬 {text}")
            update.message.reply_text("✅ Ответ отправлен пользователю.")
            logger.info(f"✅ Ответ отправлен пользователю {extracted_user_id}: {text}")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при обработке ответа: {e}")
        update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")

# Команда /stats (только для админов)
def stats(update: Update, context: CallbackContext) -> None:
    if update.message.from_user.id not in ADMIN_IDS:
        update.message.reply_text("⚠️ У вас нет доступа к статистике.")
        return

    with db_lock:
        cursor.execute("SELECT COUNT(*) FROM questions WHERE status='pending'")
        pending = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM questions WHERE status='answered'")
        answered = cursor.fetchone()[0]

    update.message.reply_text(f"📊 **Статистика**:\n✅ Отвеченные: {answered}\n⏳ Ожидают ответа: {pending}")

# Запуск бота
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("stats", stats))
    dp.add_handler(CallbackQueryHandler(button))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(MessageHandler(Filters.reply & Filters.text, reply_to_user))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()