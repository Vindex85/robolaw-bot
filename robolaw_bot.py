import os
import psycopg2
from psycopg2.extras import DictCursor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler

# Подключение к PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")

conn = psycopg2.connect(DATABASE_URL, sslmode="require")
cur = conn.cursor(cursor_factory=DictCursor)

# Создание таблиц, если их нет
def create_tables():
    with conn:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                question TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS answers (
                id SERIAL PRIMARY KEY,
                question_id INT REFERENCES questions(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                answer TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS statistics (
                user_id BIGINT PRIMARY KEY,
                questions_asked INT DEFAULT 0,
                answers_given INT DEFAULT 0
            );
        """)

create_tables()

# Часто задаваемые вопросы (FAQ)
FAQ = {
     "Как составить договор?": "✅ Включите в договор:\n- Стороны\n- Предмет\n- Цена\n- Сроки\n- Ответственность сторон\nЛучше проконсультироваться с юристом.",
    "Что делать при увольнении?": "✅ Проверьте, соответствует ли увольнение Трудовому кодексу. Можно обжаловать в суде или подать жалобу в инспекцию труда.",
    "Как оспорить штраф?": "✅ Подайте жалобу в ГИБДД или суд в течение 10 дней с момента получения штрафа.",
    "Какие права есть у арендатора?": "✅ Арендатор имеет право на:\n- Своевременное устранение неисправностей\n- Возврат депозита\n- Защиту от незаконного выселения.",
    "Как вернуть некачественный товар?": "✅ Вы можете вернуть товар в течение 14 дней. Если обнаружен брак – можно требовать возврат денег или обмен.",
    "Как задать вопрос?": "✅ Просто отправьте сообщение, и юрист вам ответит.",
    "Сколько стоит консультация?": "✅ Первая консультация бесплатна, дальнейшие услуги обсуждаются с юристом.",
    "Как долго ждать ответа?": "✅ Ответ поступит в течение нескольких часов, в зависимости от загруженности юристов."
}

# Функция для сохранения вопросов
def save_question(user_id, message_id, question_text):
    with conn:
        cur.execute("""
            INSERT INTO questions (user_id, message_id, question)
            VALUES (%s, %s, %s);
        """, (user_id, message_id, question_text))

    update_statistics(user_id, is_question=True)

# Функция для сохранения ответов
def save_answer(question_id, user_id, answer_text):
    with conn:
        cur.execute("""
            INSERT INTO answers (question_id, user_id, answer)
            VALUES (%s, %s, %s);
        """, (question_id, user_id, answer_text))

    update_statistics(user_id, is_question=False)

# Обновление статистики
def update_statistics(user_id, is_question=True):
    with conn:
        if is_question:
            cur.execute("""
                INSERT INTO statistics (user_id, questions_asked)
                VALUES (%s, 1)
                ON CONFLICT (user_id) DO UPDATE
                SET questions_asked = statistics.questions_asked + 1;
            """, (user_id,))
        else:
            cur.execute("""
                INSERT INTO statistics (user_id, answers_given)
                VALUES (%s, 1)
                ON CONFLICT (user_id) DO UPDATE
                SET answers_given = statistics.answers_given + 1;
            """, (user_id,))

# Обработчик команды /stats
async def show_stats(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    cur.execute("SELECT questions_asked, answers_given FROM statistics WHERE user_id = %s", (user_id,))
    stats = cur.fetchone()

    if stats:
        await update.message.reply_text(
            f"📊 Ваша статистика:\n"
            f"❓ Вопросов задано: {stats['questions_asked']}\n"
            f"💬 Ответов дано: {stats['answers_given']}"
        )
    else:
        await update.message.reply_text("📊 У вас пока нет статистики.")

# Обработчик команды /faq
async def show_faq(update: Update, context: CallbackContext):
    keyboard = [[InlineKeyboardButton(q, callback_data=q)] for q in FAQ.keys()]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите вопрос:", reply_markup=reply_markup)

# Обработчик кнопок FAQ
async def faq_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    answer = FAQ.get(query.data, "Ответ не найден.")
    await query.message.reply_text(f"❓ {query.data}\n\n💡 {answer}")

# Основной код бота
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
application = Application.builder().token(TOKEN).build()

application.add_handler(CommandHandler("stats", show_stats))
application.add_handler(CommandHandler("faq", show_faq))
application.add_handler(CallbackQueryHandler(faq_callback))

print("Бот запущен...")
application.run_polling()
