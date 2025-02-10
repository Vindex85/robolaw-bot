import logging
import os
import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes
)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
print(f"TELEGRAM_TOKEN: {TELEGRAM_TOKEN}")  # Отладочный вывод
if not TELEGRAM_TOKEN:
    print("Ошибка: TELEGRAM_TOKEN не задан.")

# SQLAlchemy для работы с БД
from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================================================
# Настройка подключения к базе данных
# Если переменная окружения DATABASE_URL не задана, используется SQLite (для тестирования)
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///db.sqlite3")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модели базы данных

class FAQ(Base):
    __tablename__ = 'faqs'
    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)

class UserQuestion(Base):
    __tablename__ = 'user_questions'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, nullable=False)
    question_text = Column(Text, nullable=False)
    answer_text = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class EventLog(Base):
    __tablename__ = 'event_logs'
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(50), nullable=False)  # например: "start", "faq_access", "user_question", "admin_answer"
    user_id = Column(BigInteger, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

# Создаем таблицы, если их нет
Base.metadata.create_all(bind=engine)

# Функция инициализации FAQ (если таблица пуста, добавляем 5 вопросов)
def init_faqs():
    db = SessionLocal()
    if db.query(FAQ).count() == 0:
        faqs = [
            FAQ(
                question="Как составить договор?",
                answer="✅ Включите в договор:\n- Стороны\n- Предмет\n- Цена\n- Сроки\n- Ответственность сторон\nЛучше проконсультироваться с юристом."
            ),
            FAQ(
                question="Что делать при увольнении?",
                answer="✅ Проверьте, соответствует ли увольнение Трудовому кодексу. Можно обжаловать в суде или подать жалобу в инспекцию труда."
            ),
            FAQ(
                question="Как оспорить штраф?",
                answer="✅ Подайте жалобу в ГИБДД или суд в течение 10 дней с момента получения штрафа."
            ),
            FAQ(
                question="Как вернуть некачественный товар?",
                answer="✅ Вы можете вернуть товар в течение 14 дней. Если обнаружен брак – можно требовать возврат денег или обмен."
            ),
            FAQ(
                question="Как задать вопрос?",
                answer="✅ Введите команду /start и выберите «Задать вопрос»."
            ),
        ]
        db.add_all(faqs)
        db.commit()
    db.close()

init_faqs()

# ============================================================================
# Список администраторов (замените примерное значение на реальные Telegram-ID)
ADMIN_IDS = [308383825, 321005569]

# Состояния для ConversationHandler
USER_QUESTION = 1
ADMIN_SELECT_QUESTION = 2
ADMIN_ENTER_ANSWER = 3

# ============================================================================
# Обработчик команды /start: отправляет сообщение с кнопками (FAQ и "Задать вопрос")
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Логируем событие запуска бота
    db = SessionLocal()
    db.add(EventLog(event_type="start", user_id=user.id))
    db.commit()
    db.close()
    
    keyboard = [
        [InlineKeyboardButton("FAQ", callback_data="show_faq")],
        [InlineKeyboardButton("Задать вопрос", callback_data="ask_question")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Отправляем приветственное сообщение с inline‑клавиатурой
    await update.message.reply_text(
        "Добро пожаловать! Я робот-юрист!\nВыберите опцию:",
        reply_markup=reply_markup
    )

# ============================================================================
# Универсальный обработчик callback-запросов (для кнопок FAQ, задать вопрос, навигации)
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    db = SessionLocal()

    if data == "show_faq":
        # Логируем событие просмотра FAQ
        db.add(EventLog(event_type="faq_access", user_id=query.from_user.id))
        db.commit()
        # Получаем список FAQ из БД
        faqs = db.query(FAQ).all()
        keyboard = []
        for faq in faqs:
            keyboard.append([InlineKeyboardButton(faq.question, callback_data=f"faq_{faq.id}")])
        keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_start")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите вопрос:", reply_markup=reply_markup)
    elif data.startswith("faq_"):
        # Если нажата кнопка с конкретным FAQ (например, faq_3)
        faq_id = int(data.split("_")[1])
        faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
        if faq:
            text = f"Вопрос: {faq.question}\n\nОтвет: {faq.answer}"
            await query.edit_message_text(text)
    elif data == "ask_question":
        # Запускаем разговор для ввода вопроса
        await query.edit_message_text("Пожалуйста, введите ваш вопрос:")
        db.close()
        return USER_QUESTION  # переключаемся в состояние ожидания вопроса
    elif data == "back_to_start":
        # Возврат к начальному меню
        keyboard = [
            [InlineKeyboardButton("FAQ", callback_data="show_faq")],
            [InlineKeyboardButton("Задать вопрос", callback_data="ask_question")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Добро пожаловать в юридический чат-бот!\nВыберите опцию:", reply_markup=reply_markup)
    db.close()
    return ConversationHandler.END

# ============================================================================
# Обработка текста, введённого пользователем в ходе разговора (задание вопроса)
async def receive_user_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    question_text = update.message.text
    db = SessionLocal()
    new_question = UserQuestion(user_id=user.id, question_text=question_text)
    db.add(new_question)
    db.commit()
    # Логируем событие вопроса пользователя
    db.add(EventLog(event_type="user_question", user_id=user.id))
    db.commit()
    db.close()
    await update.message.reply_text("Ваш вопрос отправлен. Ожидайте ответа от юриста.")
    return ConversationHandler.END

# Функция для отмены разговора
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

# ============================================================================
# Команда для администраторов: выводит список новых (неотвеченных) вопросов
async def list_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return
    db = SessionLocal()
    questions = db.query(UserQuestion).filter(UserQuestion.answer_text == None).all()
    if not questions:
        await update.message.reply_text("Нет новых вопросов.")
    else:
        message = "Новые вопросы:\n"
        for q in questions:
            message += f"ID: {q.id} | Вопрос: {q.question_text}\n"
        await update.message.reply_text(message)
    db.close()

# ============================================================================
# Администраторский разговор для ответа на вопрос пользователя.
# Шаг 1: команда /answer – ввод ID вопроса
async def admin_answer_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return ConversationHandler.END
    await update.message.reply_text("Введите ID вопроса, на который хотите ответить:")
    return ADMIN_SELECT_QUESTION

# Шаг 2: получение ID вопроса и запрос ответа
async def admin_select_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        question_id = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректный числовой ID вопроса:")
        return ADMIN_SELECT_QUESTION
    db = SessionLocal()
    question = db.query(UserQuestion).filter(UserQuestion.id == question_id).first()
    if not question:
        await update.message.reply_text("Вопрос с таким ID не найден. Попробуйте еще раз:")
        db.close()
        return ADMIN_SELECT_QUESTION
    context.user_data["question_id"] = question_id
    await update.message.reply_text(f"Вопрос: {question.question_text}\nВведите ваш ответ:")
    db.close()
    return ADMIN_ENTER_ANSWER

# Шаг 3: получение ответа и отправка его пользователю
async def admin_enter_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer_text = update.message.text
    question_id = context.user_data.get("question_id")
    db = SessionLocal()
    question = db.query(UserQuestion).filter(UserQuestion.id == question_id).first()
    if question:
        question.answer_text = answer_text
        db.commit()
        # Отправляем ответ пользователю (если бот может написать пользователю)
        try:
            await context.bot.send_message(
                chat_id=question.user_id,
                text=f"На ваш вопрос:\n{question.question_text}\n\nдан ответ:\n{answer_text}"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения пользователю {question.user_id}: {e}")
        db.add(EventLog(event_type="admin_answer", user_id=update.effective_user.id))
        db.commit()
        await update.message.reply_text("Ответ отправлен пользователю.")
    else:
        await update.message.reply_text("Ошибка: вопрос не найден.")
    db.close()
    return ConversationHandler.END

# ============================================================================
# Команда для просмотра статистики (только для администраторов)
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return
    db = SessionLocal()
    start_count = db.query(EventLog).filter(EventLog.event_type == "start").count()
    faq_count = db.query(EventLog).filter(EventLog.event_type == "faq_access").count()
    user_questions_count = db.query(UserQuestion).count()
    answered_questions_count = db.query(UserQuestion).filter(UserQuestion.answer_text != None).count()
    admin_answers_count = db.query(EventLog).filter(EventLog.event_type == "admin_answer").count()
    message = (
        f"Статистика:\n"
        f"Запусков бота (/start): {start_count}\n"
        f"Просмотров FAQ: {faq_count}\n"
        f"Всего вопросов пользователей: {user_questions_count}\n"
        f"Ответов юристов: {answered_questions_count}\n"
        f"Действий админов (ответов): {admin_answers_count}"
    )
    await update.message.reply_text(message)
    db.close()

# ============================================================================
# Основная функция запуска бота
def main():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        logger.error("TELEGRAM_TOKEN не задан в переменных окружения.")
        return

    application = Application.builder().token(token).build()
    
    # Обработчик команды /start
    application.add_handler(CommandHandler("start", start))
    
    # ConversationHandler для процесса "Задать вопрос"
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^ask_question$")],
        states={
            USER_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_question)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(conv_handler)
    
    # Обработчик для всех callback‑запросов (FAQ, навигация и т.д.)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Команда для админов: просмотр списка новых вопросов
    application.add_handler(CommandHandler("questions", list_questions))
    
    # ConversationHandler для ответа на вопрос (команда /answer)
    admin_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("answer", admin_answer_start)],
        states={
            ADMIN_SELECT_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_select_question)],
            ADMIN_ENTER_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_enter_answer)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(admin_conv_handler)
    
    # Команда для просмотра статистики (только для админов)
    application.add_handler(CommandHandler("stats", stats))
    
    # Запуск бота (на Render можно использовать webhook‑подход, здесь — polling для простоты)
    def main():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        logger.error("TELEGRAM_TOKEN не задан в переменных окружения.")
        return

    application = Application.builder().token(token).build()
    
    # Обработчик команды /start
    application.add_handler(CommandHandler("start", start))
    
    # ConversationHandler для процесса "Задать вопрос"
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^ask_question$")],
        states={USER_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_question)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(conv_handler)
    
    # Обработчик для всех callback-запросов (FAQ, навигация и т.д.)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Команда для админов: просмотр списка новых вопросов
    application.add_handler(CommandHandler("questions", list_questions))
    
    # ConversationHandler для ответа на вопрос (команда /answer)
    admin_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("answer", admin_answer_start)],
        states={
            ADMIN_SELECT_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_select_question)],
            ADMIN_ENTER_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_enter_answer)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(admin_conv_handler)
    
    # Команда для просмотра статистики (только для админов)
    application.add_handler(CommandHandler("stats", stats))
    
    # Устанавливаем webhook
    webhook_url = f"https://robolaw-bot.onrender.com/{TELEGRAM_TOKEN}"
    application.bot.set_webhook(webhook_url)
    
    # Запускаем webhook-сервер
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8443)),
        url_path=TELEGRAM_TOKEN
    )

if __name__ == '__main__':
    main()


if __name__ == '__main__':
    main()
