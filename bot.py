import asyncio
import aiosqlite
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import logging

# --- НАСТРОЙКИ ЛОГИРОВАНИЯ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- КОНФИГ (ОБЯЗАТЕЛЬНО ИЗМЕНИ!) ---
BOT_TOKEN = "7862932345:AAFGRUkr1psowir4zBPk6Ne8c8Ne1v08tgM"  # ⚠️ Вставь токен от @BotFather
ADMIN_ID = 1284961976  # ⚠️ Твой личный ID (узнай у @userinfobot)
ADMIN_CHAT_ID = -1003309304447  # ⚠️ ID группы (узнай у @getmyid_bot, добавь в группу!)

# --- ИНИЦИАЛИЗАЦИЯ ---
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
DB_FILE = "users.db"

# --- FSM ---
class Form(StatesGroup):
    name = State()
    geo = State()
    url = State()
    phone = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS completed_users (
                id INTEGER PRIMARY KEY,
                name TEXT,
                geo TEXT,
                url TEXT,
                username TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS incomplete_users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                phone TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def save_completed_user(user_id, name, geo, url, username, phone):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR REPLACE INTO completed_users (id, name, geo, url, username, phone) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name, geo, url, username, phone)
        )
        await db.execute("DELETE FROM incomplete_users WHERE id = ?", (user_id,))
        await db.commit()
        logging.info(f"✅ Пользователь {user_id} сохранен в завершенные")

async def save_incomplete_user(user_id, username, phone=None):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO incomplete_users (id, username, phone) VALUES (?, ?, ?)",
            (user_id, username, phone)
        )
        await db.commit()
        logging.info(f"⏳ Пользователь {user_id} сохранен в незавершенные")

async def get_completed_users(limit=10, offset=0):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM completed_users ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
        ) as cursor:
            return await cursor.fetchall()

async def get_incomplete_users(limit=10, offset=0):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM incomplete_users ORDER BY started_at DESC LIMIT ? OFFSET ?", (limit, offset)
        ) as cursor:
            return await cursor.fetchall()

async def get_completed_count():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT COUNT(*) FROM completed_users") as cursor:
            return (await cursor.fetchone())[0]

async def get_incomplete_count():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT COUNT(*) FROM incomplete_users") as cursor:
            return (await cursor.fetchone())[0]

# --- КЛАВИАТУРЫ ---
def geo_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Москва")],
            [KeyboardButton(text="Санкт-Петербург")],
            [KeyboardButton(text="Другой")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def contact_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить заявку", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def admin_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Завершенные заявки", callback_data="admin_completed")],
        [InlineKeyboardButton(text="⏳ Незавершенные", callback_data="admin_incomplete")]
    ])

def pagination_keyboard(current_offset, limit, total, callback_prefix):
    keyboard = []
    if current_offset > 0:
        keyboard.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{callback_prefix}_{current_offset - limit}"))
    if current_offset + limit < total:
        keyboard.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"{callback_prefix}_{current_offset + limit}"))
    return InlineKeyboardMarkup(inline_keyboard=[keyboard]) if keyboard else None

# --- ОБРАБОТЧИКИ ---
@dp.message(F.text == "/start")
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    
    user = message.from_user
    username = user.username or "-"
    await save_incomplete_user(user.id, username)
    
    await message.answer("Привет! Как тебя зовут?")
    await state.set_state(Form.name)

@dp.message(Form.name)
async def ask_geo(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Выбери свой город:", reply_markup=geo_keyboard())
    await state.set_state(Form.geo)

@dp.message(Form.geo)
async def ask_url(message: Message, state: FSMContext):
    await state.update_data(geo=message.text)
    await message.answer("Пришли ссылку на сайт, который надо исправить:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Form.url)

@dp.message(Form.url)
async def ask_phone(message: Message, state: FSMContext):
    await state.update_data(url=message.text)
    await message.answer("Теперь нажми кнопку ниже, чтобы оставить заявку:", reply_markup=contact_keyboard())
    await state.set_state(Form.phone)

@dp.message(Form.phone, F.contact)
async def finish(message: Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    data = await state.get_data()

    user = message.from_user
    username = user.username or "-"
    phone = data["phone"]

    # === ШАГ 1: Проверяем, дошли ли до сюда ===
    print(f"DEBUG: Готовим заявку от {user.id}")
    
    try:
        await save_completed_user(user.id, data["name"], data["geo"], data["url"], username, phone)
        print("DEBUG: Пользователь сохранен в БД")
    except Exception as e:
        print(f"ERROR: Не сохранил в БД: {e}")
        await message.answer("Ошибка при сохранении. Попробуйте позже.")
        return

    # === ШАГ 2: Готовим текст ===
    notification_text = (
        f"📩 <b>НОВАЯ ЗАЯВКА</b>\n\n"
        f"👤 <b>Имя:</b> {data['name']}\n"
        f"🌍 <b>Гео:</b> {data['geo']}\n"
        f"🔗 <b>Сайт:</b> {data['url']}\n"
        f"📱 <b>Telegram:</b> @{username}\n"
        f"☎️ <b>Телефон:</b> {phone}"
    )
    print(f"DEBUG: Текст готов. Отправляем в группу {ADMIN_CHAT_ID}")

    # === ШАГ 3: Пытаемся отправить в группу ===
    try:
        await bot.send_message(ADMIN_CHAT_ID, notification_text)
        print("✅ УСПЕХ: Сообщение отправлено в группу")
    except Exception as e:
        print(f"❌ ОШИБКА группы: {e}")
        # Отправляем тебе в личку резервное сообщение
        await bot.send_message(ADMIN_ID, f"⚠️ Группа недоступна: {e}\n\n{notification_text}")
        print("DEBUG: Отправил резервное сообщение в личку")

    # === ШАГ 4: Завершаем ===
    await message.answer("Спасибо! Я передал твою заявку. Скоро свяжусь.", reply_markup=types.ReplyKeyboardRemove())
    await state.clear()
    print("DEBUG: Финиш")

# === АДМИН-КОМАНДА ТОЛЬКО ДЛЯ ТЕБЯ ===
@dp.message(F.text == "/admin")
async def admin_command(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет доступа к админ-панели.")
        return
    
    await message.answer("Админ-панель:", reply_markup=admin_menu_keyboard())

@dp.callback_query(F.data.startswith("admin_"))
async def admin_menu(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа")
        return
    
    action = callback.data.split("_")[1]
    
    if action == "completed":
        await show_completed(callback, offset=0)
    elif action == "incomplete":
        await show_incomplete(callback, offset=0)

async def show_completed(callback, offset=0):
    limit = 10
    users = await get_completed_users(limit=limit, offset=offset)
    total = await get_completed_count()
    
    if not users:
        await callback.answer("Завершенных заявок нет")
        return
    
    text = f"📋 <b>Завершенные заявки (всего: {total})</b>\n\n"
    
    for user in users:
        date = datetime.fromisoformat(user["created_at"]).strftime("%d.%m.%Y %H:%M")
        contact = f"@{user['username']}" if user['username'] != "-" else user['phone']
        text += f"📅 {date} | 📞 {contact}\n"
    
    keyboard = pagination_keyboard(offset, limit, total, "completed")
    await callback.message.edit_text(text, reply_markup=keyboard)

async def show_incomplete(callback, offset=0):
    limit = 10
    users = await get_incomplete_users(limit=limit, offset=offset)
    total = await get_incomplete_count()
    
    if not users:
        await callback.answer("Незавершенных заявок нет")
        return
    
    text = f"⏳ <b>Незавершенные заявки (всего: {total})</b>\n\n"
    
    for user in users:
        date = datetime.fromisoformat(user["started_at"]).strftime("%d.%m.%Y %H:%M")
        contact = f"@{user['username']}" if user['username'] != "-" else (user['phone'] or "-")
        text += f"📅 {date} | 📞 {contact}\n"
    
    keyboard = pagination_keyboard(offset, limit, total, "incomplete")
    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith(("completed_", "incomplete_")))
async def paginate(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа")
        return
    
    parts = callback.data.split("_")
    offset = int(parts[1])
    prefix = parts[0]
    
    if prefix == "completed":
        await show_completed(callback, offset)
    else:
        await show_incomplete(callback, offset)

# --- ЗАПУСК ---
async def main():
    await init_db()
    logging.info("=== БОТ ЗАПУЩЕН ===")
    logging.info(f"Admin ID: {ADMIN_ID}")
    logging.info(f"Admin Chat ID: {ADMIN_CHAT_ID}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())