import asyncio
import logging
import re
import os
import sys
import traceback
from datetime import datetime, timedelta
from typing import Tuple, List, Optional

import pytz
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup,
    InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web  # <--- ЭТО НОВАЯ СТРОКА

from database import db
from excel_helper import ExcelGenerator

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8593813736:AAF0fftkjPXNz2aHVSFzQYGJ0cs7Xxw3PbY"  # Замени на свой токен
MAIN_ADMIN_ID = 429549022  # Замени на свой ID
TIMEZONE = "Asia/Yekaterinburg"
CURRENT_YEAR = 2026
MORNING_REPORT_HOUR = 11
MORNING_REPORT_MINUTE = 0
MIN_HOURS_BETWEEN_RESERVATIONS = 3

# Создаем объекты бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Планировщик для утренних отчетов и уведомлений
scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))

# ========== БАЗА ДАННЫХ ==========
users_db = {}
current_year = CURRENT_YEAR
pending_reservations = {}
pending_deletions = {}
pending_edits = {}

# ========== СОСТОЯНИЯ ==========
class ReservationStates(StatesGroup):
    waiting_for_table_change = State()
    waiting_for_delete_confirmation = State()
    waiting_for_edit_field = State()
    waiting_for_edit_value = State()
    waiting_for_new_admin_id = State()
    waiting_for_admin_to_remove = State()
    waiting_for_search_delete = State()
    waiting_for_search_edit = State()
    waiting_for_waiter_tables = State()
    waiting_for_year = State()

# ========== ФУНКЦИИ ДЛЯ ПАРСИНГА СПИСКА СТОЛОВ ==========

def parse_table_range(range_text: str) -> List[str]:
    """
    Парсит диапазон столов вида '11-15' в список ['11','12','13','14','15']
    """
    if '-' not in range_text:
        return [range_text.strip()]
    
    try:
        start, end = map(int, range_text.split('-'))
        if start > end:
            start, end = end, start
        return [str(i) for i in range(start, end + 1)]
    except ValueError:
        return []

def parse_table_list(text: str) -> List[str]:
    """
    Парсит список столов в различных форматах:
    - "11,12,13,14,15" -> ['11','12','13','14','15']
    - "11-15" -> ['11','12','13','14','15']
    - "11-14, 16" -> ['11','12','13','14','16']
    - "11, 13-15, 17" -> ['11','13','14','15','17']
    """
    if not text or not text.strip():
        return []
    
    # Разделяем по запятым
    parts = [p.strip() for p in text.split(',')]
    
    result = []
    for part in parts:
        if '-' in part:
            # Это диапазон
            result.extend(parse_table_range(part))
        else:
            # Одиночное значение
            if part.isdigit():
                result.append(part)
    
    # Удаляем дубликаты и сортируем
    return sorted(set(result), key=int)

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ЧАСОВЫМ ПОЯСОМ ==========

def get_today_str() -> str:
    """Возвращает сегодняшнюю дату в формате YYYY-MM-DD с учетом часового пояса"""
    tz = pytz.timezone(TIMEZONE)
    today = datetime.now(tz).strftime("%Y-%m-%d")
    print(f"📅 Сегодня по часовому поясу {TIMEZONE}: {today}")
    return today

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ (НОВЫЕ, С БД) ==========

def add_user(user_id: int, username: str, first_name: str, is_admin: int = 0):
    """Добавление пользователя в БД"""
    db.add_user(user_id, username, first_name, is_admin)

def is_admin(user_id: int) -> bool:
    """Проверка на администратора"""
    if user_id == MAIN_ADMIN_ID:
        return True
    user = db.get_user(user_id)
    return user and user.get('is_admin', 0) == 1

def is_main_admin(user_id: int) -> bool:
    """Проверка на главного администратора"""
    return user_id == MAIN_ADMIN_ID

def is_waiter(user_id: int) -> bool:
    """Проверка, является ли пользователь официантом"""
    user = db.get_user(user_id)
    return user and user.get('is_waiter', 0) == 1

def add_admin(user_id: int) -> bool:
    """Добавление администратора"""
    return db.set_admin(user_id, True)

def remove_admin(user_id: int) -> bool:
    """Удаление администратора"""
    if user_id == MAIN_ADMIN_ID:
        return False
    return db.set_admin(user_id, False)

def add_waiter_role(user_id: int) -> bool:
    """Добавление роли официанта"""
    return db.set_waiter(user_id, True)

def remove_waiter_role(user_id: int) -> bool:
    """Удаление роли официанта"""
    return db.set_waiter(user_id, False)

def get_all_users() -> List[int]:
    """Получение всех пользователей"""
    return db.get_all_users()

def get_all_admins() -> List[dict]:
    """Получение списка всех администраторов"""
    return db.get_all_admins(MAIN_ADMIN_ID)    
    if MAIN_ADMIN_ID in users_db:
        admins.append({
            'id': MAIN_ADMIN_ID,
            'name': users_db[MAIN_ADMIN_ID].get('first_name', 'Главный админ'),
            'is_main': True
        })
    
    for user_id, user_data in users_db.items():
        if user_data.get('is_admin') == 1 and user_id != MAIN_ADMIN_ID:
            admins.append({
                'id': user_id,
                'name': user_data.get('first_name', 'Админ'),
                'is_main': False
            })
    
    return admins

async def notify_all_users(text: str, exclude_ids: list = None) -> None:
    """Отправка уведомлений всем"""
    if exclude_ids is None:
        exclude_ids = []
    
    for user_id in get_all_users():
        if user_id in exclude_ids:
            continue
        if is_admin(user_id):
            try:
                await bot.send_message(user_id, text, parse_mode="Markdown")
            except Exception as e:
                logging.error(f"Не удалось отправить пользователю {user_id}: {e}")

# ========== КЛАВИАТУРЫ ==========

def get_main_keyboard(user_id: int = None):
    """Создает клавиатуру с основными кнопками"""
    buttons = []
    
    if user_id and is_waiter(user_id):
        buttons.append([KeyboardButton(text="📋 Мои брони")])
        buttons.append([KeyboardButton(text="📊 Мои столы")])
    
    if user_id and is_admin(user_id):
        if is_waiter(user_id):
            buttons.append([KeyboardButton(text="📋 Все брони")])
        else:
            buttons.append([KeyboardButton(text="📋 Сегодня")])
        buttons.append([KeyboardButton(text="➕ Новая бронь")])
        buttons.append([KeyboardButton(text="🔍 Поиск")])
        buttons.append([KeyboardButton(text="📊 Excel")])
    
    if user_id and is_main_admin(user_id):
        buttons.append([KeyboardButton(text="⚙️ Управление")])
    
    # Если кнопок нет, добавляем базовые
    if not buttons:
        buttons.append([KeyboardButton(text="📋 Сегодня")])
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )
    return keyboard

def get_cancel_keyboard():
    """Клавиатура для отмены действия"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Отменить")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_admin_management_keyboard():
    """Клавиатура для управления персоналом"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить администратора")],
            [KeyboardButton(text="➖ Удалить администратора")],
            [KeyboardButton(text="📋 Список администраторов")],
            [KeyboardButton(text="➕ Добавить официанта")],
            [KeyboardButton(text="➖ Удалить официанта")],
            [KeyboardButton(text="📋 Список официантов")],
            [KeyboardButton(text="📅 Сменить год")],
            [KeyboardButton(text="◀️ Назад в меню")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_reservation_action_keyboard(reservation_id: int):
    """Клавиатура для действий с бронью"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{reservation_id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{reservation_id}")
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_search")]
    ])
    return keyboard

def get_edit_fields_keyboard(reservation_id: int):
    """Клавиатура для выбора поля редактирования"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👤 Имя", callback_data=f"field_name_{reservation_id}"),
            InlineKeyboardButton(text="📞 Телефон", callback_data=f"field_phone_{reservation_id}")
        ],
        [
            InlineKeyboardButton(text="📅 Дата", callback_data=f"field_date_{reservation_id}"),
            InlineKeyboardButton(text="🕐 Время", callback_data=f"field_time_{reservation_id}")
        ],
        [
            InlineKeyboardButton(text="🪑 Стол", callback_data=f"field_table_{reservation_id}"),
            InlineKeyboardButton(text="👥 Гостей", callback_data=f"field_guests_{reservation_id}")
        ],
        [
            InlineKeyboardButton(text="💰 Депозит", callback_data=f"field_deposit_{reservation_id}"),
            InlineKeyboardButton(text="🎉 Повод", callback_data=f"field_occasion_{reservation_id}")
        ],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="back_to_reservation")]
    ])
    return keyboard

# ========== ФУНКЦИЯ ДЛЯ ПАРСИНГА НОМЕРА СТОЛА ==========

def parse_table_number(table_text: str) -> Tuple[str, bool]:
    """Парсит номер стола и определяет, строгий ли выбор"""
    table_text = table_text.strip()
    if table_text.endswith('!'):
        return table_text[:-1], True
    return table_text, False

# ========== ФУНКЦИЯ ДЛЯ ПАРСИНГА ТЕКСТА ==========

def parse_reservation_text(text: str, year: int = None) -> dict:
    """Анализатор текста для извлечения данных брони"""
    global current_year
    if year is None:
        year = current_year
    
    result = {
        'name': '',
        'phone': '',
        'date': '',
        'time': '',
        'guests': 1,
        'deposit': 0,
        'occasion': '',
        'table_number': '',
        'table_strict': False,
        'raw_text': text
    }
    
    original_text = text
    
    # ========== 1. Ищем ТЕЛЕФОН ==========
    phone_patterns = [
        r'\+7[\s\-\(\)]*(\d{3})[\s\-\(\)]*(\d{3})[\s\-\(\)]*(\d{2})[\s\-\(\)]*(\d{2})',
        r'8[\s\-\(\)]*(\d{3})[\s\-\(\)]*(\d{3})[\s\-\(\)]*(\d{2})[\s\-\(\)]*(\d{2})',
        r'(\d{10})',
        r'([78]\d{10})',
        r'(\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})',
    ]
    
    found_phone = None
    phone_match = None
    
    for pattern in phone_patterns:
        phone_match = re.search(pattern, original_text)
        if phone_match:
            raw_phone = re.sub(r'\D', '', phone_match.group(0))
            if len(raw_phone) == 10:
                found_phone = f"+7{raw_phone}"
                break
            elif len(raw_phone) == 11 and raw_phone[0] in '78':
                found_phone = f"+7{raw_phone[1:]}"
                break
    
    if found_phone:
        result['phone'] = found_phone
        original_text = original_text.replace(phone_match.group(0), '')
    
    # ========== 2. Ищем ДАТУ ==========
    date_patterns = [
        r'(\d{1,2})[.\-](\d{1,2})[.\-](\d{2,4})',
        r'(\d{1,2})[.\-](\d{1,2})(?!\d)',
        r'(\d{1,2})/(\d{1,2})',
        r'(\d{1,2})\s+(\d{1,2})(?!\d)',
    ]
    
    found_date = None
    date_text = None
    
    for pattern in date_patterns:
        date_match = re.search(pattern, original_text)
        if date_match:
            groups = date_match.groups()
            if len(groups) >= 2:
                day = int(groups[0])
                month = int(groups[1])
                
                if 1 <= day <= 31 and 1 <= month <= 12:
                    if len(groups) >= 3:
                        year_str = groups[2]
                        if len(year_str) == 2:
                            year_num = 2000 + int(year_str)
                        else:
                            year_num = int(year_str)
                    else:
                        year_num = year
                    
                    found_date = f"{year_num:04d}-{month:02d}-{day:02d}"
                    date_text = date_match.group(0)
                    break
    
    if found_date:
        result['date'] = found_date
        if date_text:
            original_text = original_text.replace(date_text, '')
    
    # ========== 3. Ищем ВРЕМЯ ==========
    time_patterns = [
        r'(\d{1,2}):(\d{2})',
        r'(\d{1,2})\.(\d{2})',
        r'(\d{1,2})\s+(\d{2})(?!\d)',
        r'(\d{1,2})ч(\d{2})',
    ]
    
    found_time = None
    time_text = None
    
    for pattern in time_patterns:
        time_match = re.search(pattern, original_text)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                found_time = f"{hour:02d}:{minute:02d}"
                time_text = time_match.group(0)
                break
    
    if found_time:
        result['time'] = found_time
        if time_text:
            original_text = original_text.replace(time_text, '')
    
    # ========== 4. Ищем НОМЕР СТОЛА ==========
    table_pattern = r'\b(\d+!?)\b'
    table_match = re.search(table_pattern, original_text)
    if table_match:
        table_text = table_match.group(1)
        table_num, is_strict = parse_table_number(table_text)
        result['table_number'] = table_num
        result['table_strict'] = is_strict
        original_text = original_text.replace(table_match.group(0), '')
    
    # ========== 5. Ищем КОЛИЧЕСТВО ЧЕЛОВЕК ==========
    guests_patterns = [
        r'(\d+)\s*(?:чел|человек|персон|гостей|гостя|человека)',
        r'на\s*(\d+)\s*(?:чел|человек)',
    ]
    
    for pattern in guests_patterns:
        guests_match = re.search(pattern, original_text, re.IGNORECASE)
        if guests_match:
            guests = int(guests_match.group(1))
            if 1 <= guests <= 20:
                result['guests'] = guests
                original_text = original_text.replace(guests_match.group(0), '')
                break
    
    # ========== 6. Ищем ДЕПОЗИТ ==========
    deposit_patterns = [
        r'(?:депозит|деп|задаток|предоплата)\s*(\d+)\s*(?:к|к\.|тыс)?',
        r'(?:депозит|деп|задаток|предоплата)\s*(\d+)\s*(?:руб|р|₽|рублей)?',
        r'(\d+)\s*к(?!\w)',
        r'(\d+)\s*(?:тыс|тысяч)',
        r'(\d{5,})',
        r'(\d{4,})\s*(?:руб|р|₽|рублей)',
    ]
    
    for pattern in deposit_patterns:
        deposit_match = re.search(pattern, original_text, re.IGNORECASE)
        if deposit_match:
            deposit_num = int(deposit_match.group(1))
            
            matched_text = deposit_match.group(0).lower()
            if 'к' in matched_text or 'тыс' in matched_text:
                deposit = deposit_num * 1000
                print(f"💰 Распознан депозит с сокращением: {deposit_num}к = {deposit}₽")
            else:
                deposit = deposit_num
                print(f"💰 Распознан депозит: {deposit}₽")
            
            if deposit >= 1000:
                result['deposit'] = deposit
                original_text = original_text.replace(deposit_match.group(0), '')
                break
    
    # ========== 7. Если не нашли гостей, ищем любые подходящие цифры ==========
    if result['guests'] == 1:
        number_matches = re.findall(r'\b(\d+)\b', original_text)
        for num_str in number_matches:
            num = int(num_str)
            if 1 <= num <= 20 and num != result['deposit']:
                result['guests'] = num
                original_text = original_text.replace(num_str, '', 1)
                break
    
    # ========== 8. Ищем ПОВОД ==========
    occasion_keywords = {
        'др': 'День рождения',
        'день рождения': 'День рождения',
        'деньрождения': 'День рождения',
        'годовщина': 'Годовщина',
        'свадьба': 'Свадьба',
        'встреча': 'Встреча',
        'бизнес': 'Бизнес-встреча',
        'обед': 'Обед',
        'ужин': 'Ужин',
        'романтик': 'Романтический ужин',
        'деловой': 'Деловая встреча',
        'семейный': 'Семейный ужин',
        'корпоратив': 'Корпоратив',
        'юбилей': 'Юбилей',
    }
    
    text_lower = original_text.lower()
    for keyword, display in occasion_keywords.items():
        if keyword in text_lower:
            result['occasion'] = display
            original_text = re.sub(keyword, '', original_text, flags=re.IGNORECASE)
            break
    
    # ========== 9. ИЩЕМ ИМЯ ==========
    exclude_words = {
        'др', 'день', 'рождения', 'рожд', 'годовщина', 'свадьба', 'встреча',
        'бизнес', 'обед', 'ужин', 'романтик', 'романтический', 'деловой', 
        'семейный', 'корпоратив', 'юбилей',
        'депозит', 'деп', 'задаток', 'предоплата', 'руб', 'рублей', 'р', '₽',
        'чел', 'человек', 'персон', 'гостей', 'гостя', 'человека',
        'на', 'с', 'со', 'и', 'в', 'во', 'для', 'за', 'по', 'под', 'около',
        'примерно', 'ок', 'при', 'без', 'до', 'после',
        'стол', 'столик', 'номер', 'телефон', 'тел', 'время', 'дата',
        'сегодня', 'завтра', 'вечером', 'днём', 'утром',
        'овек', 'овека', 'guest', 'client', 'gost',
    }
    
    name_text = original_text.strip()
    
    if not name_text:
        result['name'] = 'Гость' if result['phone'] else 'Не указано'
        print(f"📅 Распознанная дата: {result['date']}")
        print(f"🕐 Распознанное время: {result['time']}")
        return result
    
    words = re.findall(r'[а-яА-ЯёЁa-zA-Z-]+', name_text)
    good_words = []
    
    for word in words:
        word_lower = word.lower()
        
        if len(word) < 2:
            continue
        if word_lower in exclude_words:
            continue
        if any(c.isdigit() for c in word):
            continue
        
        occasion_indicators = ['др', 'рожд', 'деньр', 'годовщ', 'свадьб', 'встреч', 
                               'бизн', 'обед', 'ужин', 'роман', 'делов', 'семей',
                               'корпор', 'юбил', 'депоз', 'задат', 'овек']
        if any(ind in word_lower for ind in occasion_indicators):
            continue
        
        if word[0].isupper():
            good_words.append(word)
        elif len(word) > 3 and word_lower not in ['гость', 'клиент']:
            good_words.append(word)
    
    if good_words:
        uppercase_words = [w for w in good_words if w[0].isupper()]
        if uppercase_words:
            result['name'] = ' '.join(uppercase_words[:2])
        else:
            result['name'] = ' '.join(good_words[:2])
    else:
        first_word_match = re.search(r'[а-яА-ЯёЁa-zA-Z-]{2,}', name_text)
        if first_word_match:
            first_word = first_word_match.group()
            result['name'] = first_word if first_word.lower() not in exclude_words else 'Гость'
        else:
            result['name'] = 'Гость'
    
    result['name'] = re.sub(r'[^\w\s-]', '', result['name'])
    result['name'] = re.sub(r'\s+', ' ', result['name']).strip()
    
    print(f"📅 Распознанная дата: {result['date']}")
    print(f"🕐 Распознанное время: {result['time']}")
    print(f"👤 Распознанное имя: {result['name']}")
    
    return result

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ СО СТОЛАМИ ==========

def check_table_availability(table_number: str, date: str, time: str, exclude_reservation_id: int = None) -> dict:
    """Проверяет, свободен ли стол в указанное время"""
    try:
        new_time = datetime.strptime(time, "%H:%M")
    except ValueError:
        return {'available': False, 'conflicts': [], 'table': table_number, 'date': date, 'time': time}
    
    conflicts = []
    all_reservations = db.get_all_reservations()
    
    for res in all_reservations:
        if exclude_reservation_id and res.get('id') == exclude_reservation_id:
            continue
        
        if res.get('date') != date:
            continue
        
        res_table = res.get('table_number')
        if not res_table or res_table == 'Не назначен':
            continue
        
        if res_table == table_number:
            try:
                res_time = datetime.strptime(res.get('time'), "%H:%M")
                time_diff = abs((new_time - res_time).total_seconds() / 3600)
                
                if time_diff < MIN_HOURS_BETWEEN_RESERVATIONS:
                    conflicts.append({
                        'id': res.get('id'),
                        'time': res.get('time'),
                        'name': res.get('name'),
                        'guests': res.get('guests'),
                        'diff_hours': time_diff
                    })
            except (ValueError, TypeError):
                continue
    
    return {
        'available': len(conflicts) == 0,
        'conflicts': conflicts,
        'table': table_number,
        'date': date,
        'time': time
    }

def format_reservation_for_display(res: dict) -> str:
    """Форматирует бронь для отображения"""
    deposit_text = f"💰 Депозит: {res.get('deposit', 0)}₽" if res.get('deposit', 0) > 0 else ""
    occasion_text = f"🎉 {res.get('occasion', '')}" if res.get('occasion') else ""
    table_text = res.get('table_number', 'Не назначен')
    if res.get('table_strict'):
        table_text += " (выбор гостя)"
    
    return (
        f"🆔 #{res.get('id', '?')}\n"
        f"📅 {res.get('date', '?')} | 🕐 {res.get('time', '?')}\n"
        f"👤 {res.get('name', '?')}\n"
        f"📞 {res.get('phone', '?')} | 👥 {res.get('guests', '?')} чел.\n"
        f"🪑 Стол: {table_text}\n"
        f"{occasion_text} {deposit_text}"
    ).strip()

# ========== ХЕНДЛЕРЫ КОМАНД ==========

@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    user = message.from_user
    is_admin_user = 1 if user.id == MAIN_ADMIN_ID else 0
    
    add_user(user.id, user.username, user.first_name, is_admin_user)
    
    if is_admin_user or is_admin(user.id):
        welcome_text = (
            f"👋 Добро пожаловать, {user.first_name}!\n"
            f"📅 Текущий год: **{current_year}**\n\n"
        )
        
        if is_main_admin(user.id):
            welcome_text += "⭐ **Вы главный администратор**\n"
        elif is_admin(user.id):
            welcome_text += "👑 **Вы администратор**\n"
        
        if is_waiter(user.id):
            today = get_today_str()
            tables = db.get_waiter_tables_for_date(user.id, today)
            tables_str = ', '.join(tables) if tables else 'не назначены'
            welcome_text += f"🍽 **Вы официант** (столы на сегодня: {tables_str})\n\n"
        
        welcome_text += "**Как работать:**\n"
        welcome_text += "• Просто напишите данные брони - бот создаст её\n"
        
        await message.answer(
            welcome_text,
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user.id)
        )
    else:
        await message.answer(
            "👋 Добро пожаловать!\n"
            "Вы будете получать уведомления о бронях."
        )

# ========== ОБРАБОТЧИКИ КНОПОК ==========

@dp.message(F.text == "📋 Сегодня")
async def button_today(message: Message):
    """Кнопка показа броней на сегодня"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав.")
        return
    
    reservations = db.get_today_reservations()
    
    if not reservations:
        await message.answer("📭 На сегодня броней нет.")
        return
    
    reservations.sort(key=lambda x: x.get('time', '00:00'))
    
    for r in reservations:
        text = format_reservation_for_display(r)
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=get_reservation_action_keyboard(r['id'])
        )

@dp.message(F.text == "📋 Все брони")
async def button_all_reservations(message: Message):
    """Для админов - показать все брони на сегодня"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав.")
        return
    
    reservations = db.get_today_reservations()
    
    if not reservations:
        await message.answer("📭 На сегодня броней нет.")
        return
    
    reservations.sort(key=lambda x: x.get('time', '00:00'))
    
    for r in reservations:
        text = format_reservation_for_display(r)
        await message.answer(
            text,
            parse_mode="Markdown",
            reply_markup=get_reservation_action_keyboard(r['id'])
        )

@dp.message(F.text == "📋 Мои брони")
async def button_my_reservations(message: Message):
    """Просмотр броней на свои столы"""
    user_id = message.from_user.id
    
    if not is_waiter(user_id):
        await message.answer("❌ Эта функция только для официантов.")
        return
    
    today = get_today_str()
    my_tables = db.get_waiter_tables_for_date(user_id, today)
    
    if not my_tables:
        await message.answer(
            "❌ У вас нет назначенных столов на сегодня.\n"
            "Сначала настройте их в разделе '📊 Мои столы'."
        )
        return
    
    all_reservations = db.get_today_reservations()
    
    my_reservations = []
    for res in all_reservations:
        if res.get('table_number') in my_tables:
            my_reservations.append(res)
    
    if not my_reservations:
        await message.answer("📭 На сегодня нет броней на ваши столы.")
        return
    
    my_reservations.sort(key=lambda x: x.get('time', '00:00'))
    
    for r in my_reservations:
        text = format_reservation_for_display(r)
        await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "➕ Новая бронь")
async def button_new_reservation(message: Message):
    """Кнопка создания новой брони"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав.")
        return
    
    await message.answer(
        "📝 **Создание брони**\n\n"
        "Напишите данные в свободной форме:\n"
        "• Имя\n"
        "• Дату (ДД.ММ)\n"
        "• Время (ЧЧ:ММ)\n"
        "• Номер стола (например 21 или 21!)\n"
        "• Телефон\n"
        "• Количество человек\n"
        "• Повод (если есть)\n"
        "• Депозит (если есть)\n\n"
        "📌 *Пример:*\n"
        "`Андрей 26.02 18:00 21 89126191729 2 др`",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )

@dp.message(F.text == "🔍 Поиск")
async def button_search(message: Message, state: FSMContext):
    """Кнопка поиска"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав.")
        return
    
    await message.answer(
        "🔍 Введите имя или номер телефона для поиска:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(ReservationStates.waiting_for_search_delete)

@dp.message(F.text == "📊 Excel")
async def button_excel(message: Message):
    """Кнопка выгрузки Excel"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав.")
        return
    
    reservations = db.get_today_reservations()
    
    if not reservations:
        await message.answer("📭 На сегодня броней нет.")
        return
    
    today = get_today_str()
    filepath = ExcelGenerator.create_reservation_file(reservations, today)
    db.save_excel_file(f"reservations_{today}.xlsx", today, filepath)
    
    document = FSInputFile(filepath)
    await message.answer_document(
        document,
        caption=f"📊 Брони на {today}",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message(F.text == "📊 Мои столы")
async def button_my_tables(message: Message, state: FSMContext):
    """Кнопка просмотра и редактирования своих столов на сегодня"""
    user_id = message.from_user.id
    
    if not is_waiter(user_id):
        await message.answer("❌ Эта функция только для официантов.")
        return
    
    today = get_today_str()
    current_tables = db.get_waiter_tables_for_date(user_id, today)
    tables_str = ', '.join(current_tables) if current_tables else 'нет столов'
    
    await message.answer(
        f"**🪑 Ваши столы на сегодня ({today})**\n\n"
        f"Текущие столы: {tables_str}\n\n"
        f"Введите номера столов, которые вы обслуживаете СЕГОДНЯ.\n\n"
        f"**Поддерживаемые форматы:**\n"
        f"• Через запятую: `11, 12, 13, 14, 15`\n"
        f"• Диапазоном: `11-15`\n"
        f"• Смешанный: `11-14, 16, 18`\n\n"
        f"Завтра нужно будет ввести заново!",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(ReservationStates.waiting_for_waiter_tables)

@dp.message(F.text == "⚙️ Управление")
async def button_management(message: Message):
    """Кнопка управления"""
    if not is_main_admin(message.from_user.id):
        await message.answer("❌ Только главный администратор может управлять.")
        return
    
    await message.answer(
        "**⚙️ Управление системой**\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=get_admin_management_keyboard()
    )

@dp.message(F.text == "➕ Добавить администратора")
async def button_add_admin(message: Message, state: FSMContext):
    """Кнопка добавления администратора"""
    if not is_main_admin(message.from_user.id):
        await message.answer("❌ Только главный администратор может добавлять админов.")
        return
    
    await message.answer(
        "📝 **Добавление администратора**\n\n"
        "Отправьте ID пользователя.\n\n"
        "Как узнать ID:\n"
        "1. Напишите @userinfobot в Telegram\n"
        "2. Нажмите Start\n"
        "3. Перешлите его сообщение сюда",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(ReservationStates.waiting_for_new_admin_id)
    await state.update_data(adding_role='admin')

@dp.message(F.text == "➕ Добавить официанта")
async def button_add_waiter(message: Message, state: FSMContext):
    """Кнопка добавления официанта"""
    if not is_main_admin(message.from_user.id):
        await message.answer("❌ Только главный администратор может добавлять официантов.")
        return
    
    await message.answer(
        "👤 **Добавление официанта**\n\n"
        "Отправьте ID пользователя.",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(ReservationStates.waiting_for_new_admin_id)
    await state.update_data(adding_role='waiter')

@dp.message(F.text == "➖ Удалить администратора")
async def button_remove_admin(message: Message, state: FSMContext):
    """Кнопка удаления администратора"""
    if not is_main_admin(message.from_user.id):
        await message.answer("❌ Только главный администратор может удалять админов.")
        return
    
    admins = get_all_admins()
    if len(admins) <= 1:
        await message.answer("❌ Нет других администраторов для удаления.")
        return
    
    text = "**📋 Список администраторов:**\n\n"
    for admin in admins:
        if not admin['is_main']:
            text += f"🆔 {admin['id']} | {admin['name']}\n"
    
    text += "\nВведите ID администратора для удаления:"
    
    await message.answer(text, parse_mode="Markdown", reply_markup=get_cancel_keyboard())
    await state.set_state(ReservationStates.waiting_for_admin_to_remove)
    await state.update_data(removing_role='admin')

@dp.message(F.text == "➖ Удалить официанта")
async def button_remove_waiter(message: Message, state: FSMContext):
    """Кнопка удаления официанта"""
    if not is_main_admin(message.from_user.id):
        await message.answer("❌ Только главный администратор может удалять официантов.")
        return
    
    today = get_today_str()
    waiters = db.get_all_waiters_for_date(today)
    
    if not waiters:
        await message.answer("❌ Нет официантов на сегодня.")
        return
    
    text = "**📋 Список официантов на сегодня:**\n\n"
    for w in waiters:
        text += f"🆔 {w['id']} | {w['name']} | Столы: {', '.join(w['tables'])}\n"
    
    text += "\nВведите ID официанта для удаления:"
    
    await message.answer(text, parse_mode="Markdown", reply_markup=get_cancel_keyboard())
    await state.set_state(ReservationStates.waiting_for_admin_to_remove)
    await state.update_data(removing_role='waiter')

@dp.message(F.text == "📋 Список администраторов")
async def button_list_admins(message: Message):
    """Кнопка списка администраторов"""
    if not is_main_admin(message.from_user.id):
        await message.answer("❌ Только главный администратор может просматривать список.")
        return
    
    admins = get_all_admins()
    
    text = "**📋 Список администраторов:**\n\n"
    for admin in admins:
        if admin['is_main']:
            text += f"⭐ {admin['id']} | {admin['name']} (главный)\n"
        else:
            text += f"👤 {admin['id']} | {admin['name']}\n"
    
    await message.answer(text, parse_mode="Markdown", reply_markup=get_admin_management_keyboard())

@dp.message(F.text == "📋 Список официантов")
async def button_list_waiters(message: Message):
    """Кнопка списка официантов"""
    if not is_main_admin(message.from_user.id):
        await message.answer("❌ Только главный администратор может просматривать список.")
        return
    
    today = get_today_str()
    waiters = db.get_all_waiters_for_date(today)
    
    if not waiters:
        await message.answer("📭 Нет официантов на сегодня.")
        return
    
    text = f"**👥 Список официантов на {today}:**\n\n"
    for w in waiters:
        tables_str = ', '.join(w['tables'])
        text += f"👤 {w['name']} (ID: {w['id']})\n"
        text += f"🪑 Столы: {tables_str}\n\n"
    
    await message.answer(text, parse_mode="Markdown", reply_markup=get_admin_management_keyboard())

@dp.message(F.text == "📅 Сменить год")
async def button_change_year(message: Message, state: FSMContext):
    """Кнопка смены года"""
    if not is_main_admin(message.from_user.id):
        await message.answer("❌ Только главный администратор может менять год.")
        return
    
    await message.answer(
        f"📅 **Смена года**\n\n"
        f"Текущий год: {current_year}\n"
        f"Введите новый год (например, 2026):",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(ReservationStates.waiting_for_year)

@dp.message(F.text == "◀️ Назад в меню")
async def button_back_to_main(message: Message):
    """Возврат в главное меню"""
    await message.answer(
        "Главное меню:",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message(F.text == "❌ Отменить")
async def button_cancel(message: Message, state: FSMContext):
    """Кнопка отмены действия"""
    await state.clear()
    user_id = message.from_user.id
    pending_reservations.pop(user_id, None)
    pending_deletions.pop(user_id, None)
    pending_edits.pop(user_id, None)
    
    await message.answer(
        "❌ Действие отменено.",
        reply_markup=get_main_keyboard(user_id)
    )

# ========== ОБРАБОТЧИКИ СОСТОЯНИЙ ==========

@dp.message(ReservationStates.waiting_for_new_admin_id)
async def process_new_admin_id(message: Message, state: FSMContext):
    """Обработка ID нового администратора или официанта"""
    data = await state.get_data()
    adding_role = data.get('adding_role', 'admin')
    
    try:
        text = message.text.strip()
        
        if '#' in text:
            id_match = re.search(r'ID:\s*(\d+)', text)
            if not id_match:
                await message.answer("❌ Не удалось найти ID в сообщении.")
                return
            new_user_id = int(id_match.group(1))
        else:
            new_user_id = int(text)
        
        if new_user_id not in users_db:
            await message.answer(
                f"❌ Пользователь с ID {new_user_id} еще не запускал бота.\n"
                f"Сначала он должен написать /start боту."
            )
            return
        
        if adding_role == 'admin':
            if add_admin(new_user_id):
                user_info = users_db[new_user_id]
                await message.answer(
                    f"✅ Администратор добавлен!\n"
                    f"ID: {new_user_id}\n"
                    f"Имя: {user_info.get('first_name', 'Неизвестно')}",
                    reply_markup=get_admin_management_keyboard()
                )
                
                try:
                    await bot.send_message(
                        new_user_id,
                        "🎉 Вам назначены права администратора!\n"
                        "Нажмите /start для обновления меню."
                    )
                except:
                    pass
            else:
                await message.answer("❌ Не удалось добавить администратора.")
        
               elif adding_role == 'waiter':
            if add_waiter_role(new_user_id):
                user_info = db.get_user(new_user_id)
                name = user_info.get('first_name', 'Неизвестно') if user_info else 'Неизвестно'
                
                try:
                    await bot.send_message(
                        new_user_id,
                        "👏 **Вам назначена роль официанта!**\n\n"
                        "Нажмите /start, затем выберите '📊 Мои столы' чтобы настроить, какие столы вы обслуживаете сегодня.",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Не удалось отправить уведомление официанту {new_user_id}: {e}")
                
                await message.answer(
                    f"✅ Официант добавлен!\n"
                    f"ID: {new_user_id}\n"
                    f"Имя: {name}\n\n"
                    f"Теперь этот пользователь должен настроить свои столы.",
                    reply_markup=get_admin_management_keyboard()
                )
            else:
                await message.answer("❌ Не удалось добавить официанта.")
        
    except ValueError:
        await message.answer("❌ Введите корректный ID (число).")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        await state.clear()

@dp.message(ReservationStates.waiting_for_admin_to_remove)
async def process_remove_user_id(message: Message, state: FSMContext):
    """Обработка удаления администратора или официанта"""
    data = await state.get_data()
    removing_role = data.get('removing_role', 'admin')
    
    try:
        user_id = int(message.text.strip())
        
        if user_id == MAIN_ADMIN_ID:
            await message.answer("❌ Нельзя удалить главного администратора.")
            return
        
        if user_id not in users_db:
            await message.answer(f"❌ Пользователь с ID {user_id} не найден.")
            return
        
        if removing_role == 'admin':
            if remove_admin(user_id):
                await message.answer(
                    f"✅ Администратор удален!",
                    reply_markup=get_admin_management_keyboard()
                )
                
                try:
                    await bot.send_message(
                        user_id,
                        "⚠️ Ваши права администратора были отозваны."
                    )
                except:
                    pass
            else:
                await message.answer("❌ Не удалось удалить администратора.")
        
        elif removing_role == 'waiter':
            today = get_today_str()
            if db.remove_waiter_for_date(user_id, today):
                remove_waiter_role(user_id)
                await message.answer(
                    f"✅ Официант удален с сегодняшнего дня!",
                    reply_markup=get_admin_management_keyboard()
                )
                
                try:
                    await bot.send_message(
                        user_id,
                        "⚠️ Ваши права официанта на сегодня были отозваны."
                    )
                except:
                    pass
            else:
                await message.answer("❌ Не удалось удалить официанта.")
            
    except ValueError:
        await message.answer("❌ Введите корректный ID (число).")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        await state.clear()

@dp.message(ReservationStates.waiting_for_waiter_tables)
async def process_waiter_tables(message: Message, state: FSMContext):
    """Обработка ввода столов официанта на сегодня"""
    user_id = message.from_user.id
    today = get_today_str()
    
    try:
        table_list = parse_table_list(message.text)
        
        if not table_list:
            await message.answer(
                "❌ Не удалось распознать номера столов.\n"
                "Используйте форматы: `11,12,13`, `11-15` или `11-14, 16`"
            )
            return
        
        db.set_waiter_tables_for_date(
            user_id,
            message.from_user.first_name or f"Официант {user_id}",
            table_list,
            today
        )
        
        await message.answer(
            f"✅ Столы на {today} сохранены!\n"
            f"Вы будете получать уведомления для столов: {', '.join(table_list)}\n\n"
            f"Завтра нужно будет настроить заново.",
            reply_markup=get_main_keyboard(user_id)
        )
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        await state.clear()

@dp.message(ReservationStates.waiting_for_year)
async def process_year(message: Message, state: FSMContext):
    """Обработка ввода года"""
    global current_year
    try:
        year = int(message.text.strip())
        if 2020 <= year <= 2030:
            current_year = year
            await message.answer(f"✅ Год установлен: {year}")
        else:
            await message.answer("❌ Год должен быть от 2020 до 2030")
    except ValueError:
        await message.answer("❌ Введите число (например, 2026)")
    finally:
        await state.clear()
        await message.answer(
            "Главное меню:",
            reply_markup=get_main_keyboard(message.from_user.id)
        )

# ========== ОБРАБОТЧИКИ ПОИСКА ==========

@dp.message(ReservationStates.waiting_for_search_delete)
async def process_search(message: Message, state: FSMContext):
    """Обработка поиска"""
    results = db.search_reservations(message.text)
    
    if not results:
        await message.answer("❌ Ничего не найдено.")
    else:
        results.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        for r in results[:10]:
            await message.answer(
                format_reservation_for_display(r),
                parse_mode="Markdown",
                reply_markup=get_reservation_action_keyboard(r['id'])
            )
        
        if len(results) > 10:
            await message.answer(f"... и еще {len(results) - 10} результатов")
    
    await message.answer(
        "Выберите действие:",
        reply_markup=get_main_keyboard(message.from_user.id)
    )
    await state.clear()

# ========== ОБРАБОТЧИКИ ДЕЙСТВИЙ С БРОНЯМИ ==========

@dp.callback_query(lambda c: c.data.startswith('delete_'))
async def process_delete_callback(callback: CallbackQuery):
    """Обработка нажатия на кнопку удаления"""
    reservation_id = int(callback.data.split('_')[1])
    reservation = db.get_reservation_by_id(reservation_id)
    
    if not reservation:
        await callback.answer("❌ Бронь не найдена")
        await callback.message.delete()
        return
    
    pending_deletions[callback.from_user.id] = reservation_id
    
    await callback.message.edit_text(
        f"🗑 **Подтверждение удаления**\n\n"
        f"{format_reservation_for_display(reservation)}\n\n"
        f"❓ Вы уверены, что хотите удалить эту бронь?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data="confirm_delete"),
                InlineKeyboardButton(text="❌ Нет", callback_data="cancel_delete")
            ]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "confirm_delete")
async def process_confirm_delete(callback: CallbackQuery):
    """Подтверждение удаления брони"""
    user_id = callback.from_user.id
    
    if user_id not in pending_deletions:
        await callback.message.edit_text("❌ Ошибка: бронь не найдена")
        return
    
    reservation_id = pending_deletions[user_id]
    reservation = db.get_reservation_by_id(reservation_id)
    
    if db.delete_reservation(reservation_id):
        await callback.message.edit_text(
            f"✅ Бронь #{reservation_id} удалена.",
            parse_mode="Markdown"
        )
        
        today = get_today_str()
        if reservation and reservation.get('date') == today:
            await notify_all_users(
                f"🗑 Бронь #{reservation_id} отменена:\n"
                f"{reservation.get('time')} | {reservation.get('name')} | Стол {reservation.get('table_number', '?')}",
                exclude_ids=[user_id]
            )
    else:
        await callback.message.edit_text("❌ Ошибка при удалении брони")
    
    pending_deletions.pop(user_id, None)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "cancel_delete")
async def process_cancel_delete(callback: CallbackQuery):
    """Отмена удаления"""
    user_id = callback.from_user.id
    if user_id in pending_deletions:
        reservation_id = pending_deletions[user_id]
        reservation = db.get_reservation_by_id(reservation_id)
        
        if reservation:
            await callback.message.edit_text(
                format_reservation_for_display(reservation),
                parse_mode="Markdown",
                reply_markup=get_reservation_action_keyboard(reservation_id)
            )
        pending_deletions.pop(user_id, None)
    
    await callback.answer("❌ Удаление отменено")

@dp.callback_query(lambda c: c.data.startswith('edit_'))
async def process_edit_callback(callback: CallbackQuery):
    """Обработка нажатия на кнопку редактирования"""
    reservation_id = int(callback.data.split('_')[1])
    reservation = db.get_reservation_by_id(reservation_id)
    
    if not reservation:
        await callback.answer("❌ Бронь не найдена")
        await callback.message.delete()
        return
    
    await callback.message.edit_text(
        f"✏️ **Редактирование брони #{reservation_id}**\n\n"
        f"{format_reservation_for_display(reservation)}\n\n"
        f"Выберите поле для редактирования:",
        parse_mode="Markdown",
        reply_markup=get_edit_fields_keyboard(reservation_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('field_'))
async def process_edit_field(callback: CallbackQuery, state: FSMContext):
    """Выбор поля для редактирования"""
    parts = callback.data.split('_')
    field = parts[1]
    reservation_id = int(parts[2])
    
    reservation = db.get_reservation_by_id(reservation_id)
    if not reservation:
        await callback.answer("❌ Бронь не найдена")
        return
    
    field_names = {
        'name': '👤 Имя',
        'phone': '📞 Телефон',
        'date': '📅 Дату',
        'time': '🕐 Время',
        'table': '🪑 Номер стола',
        'guests': '👥 Количество гостей',
        'deposit': '💰 Депозит',
        'occasion': '🎉 Повод'
    }
    
    current_values = {
        'name': reservation.get('name', ''),
        'phone': reservation.get('phone', ''),
        'date': reservation.get('date', ''),
        'time': reservation.get('time', ''),
        'table': reservation.get('table_number', ''),
        'guests': str(reservation.get('guests', '')),
        'deposit': str(reservation.get('deposit', '0')),
        'occasion': reservation.get('occasion', '')
    }
    
    await state.update_data(
        edit_reservation_id=reservation_id,
        edit_field=field
    )
    
    hints = {
        'name': 'Введите новое имя гостя',
        'phone': 'Введите новый номер телефона',
        'date': 'Введите новую дату в формате ДД.ММ',
        'time': 'Введите новое время в формате ЧЧ:ММ',
        'table': 'Введите новый номер стола (можно с !)',
        'guests': 'Введите новое количество гостей (число)',
        'deposit': 'Введите новую сумму депозита (число или 5к)',
        'occasion': 'Введите новый повод (или "нет" чтобы убрать)'
    }
    
    await callback.message.edit_text(
        f"✏️ **Редактирование брони #{reservation_id}**\n\n"
        f"Поле: {field_names.get(field, field)}\n"
        f"Текущее значение: `{current_values.get(field, '')}`\n\n"
        f"{hints.get(field, 'Введите новое значение:')}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Отмена", callback_data=f"edit_{reservation_id}")]
        ])
    )
    
    await state.set_state(ReservationStates.waiting_for_edit_value)
    await callback.answer()

@dp.message(ReservationStates.waiting_for_edit_value)
async def process_edit_value(message: Message, state: FSMContext):
    """Обработка нового значения для редактирования"""
    data = await state.get_data()
    reservation_id = data.get('edit_reservation_id')
    field = data.get('edit_field')
    
    if not reservation_id or not field:
        await message.answer("❌ Ошибка: данные не найдены")
        await state.clear()
        return
    
    reservation = db.get_reservation_by_id(reservation_id)
    if not reservation:
        await message.answer("❌ Бронь не найдена")
        await state.clear()
        return
    
    new_value = message.text.strip()
    valid = True
    error_msg = ""
    
    if field == 'date':
        try:
            date_obj = datetime.strptime(new_value, "%d.%m")
            new_value = f"{current_year:04d}-{date_obj.month:02d}-{date_obj.day:02d}"
        except ValueError:
            valid = False
            error_msg = "❌ Неверный формат даты. Используйте ДД.ММ"
    
    elif field == 'time':
        try:
            time_obj = datetime.strptime(new_value, "%H:%M")
            new_value = f"{time_obj.hour:02d}:{time_obj.minute:02d}"
        except ValueError:
            valid = False
            error_msg = "❌ Неверный формат времени. Используйте ЧЧ:ММ"
    
    elif field == 'table':
        table_match = re.match(r'^(\d+!?)$', new_value)
        if not table_match:
            valid = False
            error_msg = "❌ Неверный формат стола. Используйте число, например 21 или 21!"
        else:
            table_num, is_strict = parse_table_number(new_value)
            new_value = table_num
            availability = check_table_availability(
                table_num,
                reservation.get('date'),
                reservation.get('time'),
                exclude_reservation_id=reservation_id
            )
            if not availability['available']:
                conflict = availability['conflicts'][0]
                valid = False
                error_msg = (
                    f"❌ Стол {table_num} занят!\n"
                    f"В {conflict['time']} бронь на {conflict['name']}\n"
                    f"Введите другой номер стола"
                )
            else:
                await state.update_data(table_strict=is_strict)
    
    elif field == 'guests':
        try:
            guests = int(new_value)
            if guests < 1 or guests > 20:
                valid = False
                error_msg = "❌ Количество гостей должно быть от 1 до 20"
            else:
                new_value = guests
        except ValueError:
            valid = False
            error_msg = "❌ Введите число"
    
    elif field == 'deposit':
        try:
            if 'к' in new_value.lower():
                num_part = re.sub(r'[^\d]', '', new_value)
                if num_part:
                    deposit = int(num_part) * 1000
                    await message.answer(f"💰 Преобразовано: {num_part}к = {deposit}₽")
                else:
                    deposit = 0
            else:
                deposit = int(new_value)
            
            if deposit < 0:
                valid = False
                error_msg = "❌ Депозит не может быть отрицательным"
            elif 0 < deposit < 1000:
                await message.answer(f"⚠️ Внимание: депозит {deposit}₽ меньше 1000₽. Продолжаем...")
                new_value = deposit
            else:
                new_value = deposit
        except ValueError:
            valid = False
            error_msg = "❌ Введите число или сокращение (например 5к, 10к, 20000)"
    
    elif field == 'occasion':
        if new_value.lower() == 'нет':
            new_value = ''
    
    if not valid:
        await message.answer(error_msg)
        return
    
    update_data = {field: new_value}
    if field == 'table':
        update_data['table_strict'] = data.get('table_strict', False)
    
    if db.update_reservation(reservation_id, update_data):
        updated_reservation = db.get_reservation_by_id(reservation_id)
        
        await message.answer(
            f"✅ Бронь #{reservation_id} обновлена!\n\n"
            f"{format_reservation_for_display(updated_reservation)}",
            parse_mode="Markdown"
        )
        
        today = get_today_str()
        if updated_reservation and updated_reservation.get('date') == today:
            await notify_all_users(
                f"✏️ Изменена бронь #{reservation_id}\n"
                f"{format_reservation_for_display(updated_reservation)}",
                exclude_ids=[message.from_user.id]
            )
    else:
        await message.answer("❌ Ошибка при обновлении брони")
    
    await state.clear()
    await message.answer(
        "Выберите действие:",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

# ========== ОБРАБОТЧИКИ ДЛЯ ВОЗВРАТА ==========

@dp.callback_query(lambda c: c.data == "back_to_reservation")
async def back_to_reservation(callback: CallbackQuery):
    """Возврат к просмотру брони"""
    id_match = re.search(r'#(\d+)', callback.message.text)
    if id_match:
        reservation_id = int(id_match.group(1))
        reservation = db.get_reservation_by_id(reservation_id)
        if reservation:
            await callback.message.edit_text(
                format_reservation_for_display(reservation),
                parse_mode="Markdown",
                reply_markup=get_reservation_action_keyboard(reservation_id)
            )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_search")
async def back_to_search(callback: CallbackQuery):
    """Возврат к поиску"""
    await callback.message.edit_text("🔍 Введите имя или номер телефона для поиска:")
    await callback.answer()

# ========== ОСНОВНОЙ ОБРАБОТЧИК ТЕКСТА ==========

@dp.message(ReservationStates.waiting_for_table_change)
async def process_table_change(message: Message, state: FSMContext):
    """Обработка изменения стола при конфликте"""
    user_id = message.from_user.id
    
    if user_id not in pending_reservations:
        await state.clear()
        return
    
    new_table = message.text.strip()
    
    if not new_table.isdigit():
        await message.answer("❌ Номер стола должен быть числом. Попробуйте снова:")
        return
    
    pending = pending_reservations[user_id]
    parsed = pending['parsed']
    
    parsed['table_number'] = new_table
    parsed['table_strict'] = False
    
    availability = check_table_availability(
        parsed['table_number'],
        parsed['date'],
        parsed['time']
    )
    
    if availability['available']:
        reservation_id = db.add_reservation(parsed)
        pending_reservations.pop(user_id, None)
        
        table_text = f"{parsed['table_number']}"
        if parsed['table_strict']:
            table_text += " (выбор гостя)"
        
        reservation_text = (
            f"✅ **Новая бронь #{reservation_id}**\n\n"
            f"📅 Дата: {parsed['date']}\n"
            f"🕐 Время: {parsed['time']}\n"
            f"👤 Имя: {parsed['name']}\n"
            f"📞 Телефон: {parsed['phone']}\n"
            f"👥 Гостей: {parsed['guests']}\n"
            f"🪑 Стол: {table_text}\n"
        )
        
        if parsed['occasion']:
            reservation_text += f"🎉 Повод: {parsed['occasion']}\n"
        if parsed['deposit'] > 0:
            reservation_text += f"💰 Депозит: {parsed['deposit']}₽\n"
        
        await message.answer(reservation_text, parse_mode="Markdown")
        
        today = get_today_str()
        if parsed['date'] == today:
            await notify_all_users(reservation_text, exclude_ids=[user_id])
            
            # Сохраняем в Excel
            try:
                today_reservations = db.get_today_reservations()
                filepath = ExcelGenerator.create_reservation_file(today_reservations, today)
                db.save_excel_file(f"reservations_{today}.xlsx", today, filepath)
            except Exception as e:
                print(f"❌ Ошибка сохранения Excel: {e}")
        
        await state.clear()
        await message.answer(
            "✅ Бронь создана!",
            reply_markup=get_main_keyboard(user_id)
        )
    else:
        conflict = availability['conflicts'][0]
        await message.answer(
            f"⚠️ Стол **{new_table}** тоже занят!\n"
            f"🕐 {conflict['time']} | 👤 {conflict['name']}\n"
            f"👥 {conflict['guests']} чел.\n\n"
            f"Введите другой номер стола:",
            parse_mode="Markdown"
        )

@dp.message(F.text)
async def process_any_text(message: Message, state: FSMContext):
    """Обработка любого текста - пытаемся создать бронь"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    parsed = parse_reservation_text(message.text, current_year)
    
    errors = []
    if not parsed['name'] or parsed['name'] == 'Не указано':
        errors.append("❌ Не удалось определить имя гостя")
    if not parsed['phone']:
        errors.append("❌ Не удалось определить телефон")
    if not parsed['date']:
        errors.append("❌ Не удалось определить дату (формат ДД.ММ)")
    if not parsed['time']:
        errors.append("❌ Не удалось определить время (формат ЧЧ:ММ)")
    if not parsed['table_number']:
        errors.append("❌ Не удалось определить номер стола")
    
    if errors:
        await message.answer(
            "\n".join(errors) + "\n\nПопробуйте еще раз или используйте кнопки.",
            parse_mode="Markdown"
        )
        return
    
    availability = check_table_availability(
        parsed['table_number'],
        parsed['date'],
        parsed['time']
    )
    
    if not availability['available']:
        pending_reservations[user_id] = {
            'parsed': parsed,
            'original_text': message.text
        }
        
        conflict = availability['conflicts'][0]
        
        await message.answer(
            f"⚠️ **Стол {parsed['table_number']} занят!**\n\n"
            f"В это время уже забронировано:\n"
            f"🕐 {conflict['time']} | 👤 {conflict['name']}\n"
            f"👥 {conflict['guests']} чел.\n"
            f"⏱️ Интервал: {conflict['diff_hours']:.1f} ч (минимум {MIN_HOURS_BETWEEN_RESERVATIONS} ч)\n\n"
            f"Введите **другой номер стола** для этой брони:",
            parse_mode="Markdown"
        )
        
        await state.set_state(ReservationStates.waiting_for_table_change)
        return
    
    reservation_id = db.add_reservation(parsed)
    
    table_text = f"{parsed['table_number']}"
    if parsed['table_strict']:
        table_text += " (выбор гостя)"
    
    reservation_text = (
        f"✅ **Новая бронь #{reservation_id}**\n\n"
        f"📅 Дата: {parsed['date']}\n"
        f"🕐 Время: {parsed['time']}\n"
        f"👤 Имя: {parsed['name']}\n"
        f"📞 Телефон: {parsed['phone']}\n"
        f"👥 Гостей: {parsed['guests']}\n"
        f"🪑 Стол: {table_text}\n"
    )
    
    if parsed['occasion']:
        reservation_text += f"🎉 Повод: {parsed['occasion']}\n"
    if parsed['deposit'] > 0:
        reservation_text += f"💰 Депозит: {parsed['deposit']}₽\n"
    
    await message.answer(reservation_text, parse_mode="Markdown")
    
    today = get_today_str()
    if parsed['date'] == today:
        await notify_all_users(reservation_text, exclude_ids=[user_id])
        
        # Сохраняем в Excel
        try:
            today_reservations = db.get_today_reservations()
            filepath = ExcelGenerator.create_reservation_file(today_reservations, today)
            db.save_excel_file(f"reservations_{today}.xlsx", today, filepath)
            print(f"📊 Excel файл сохранен: {filepath}")
        except Exception as e:
            print(f"❌ Ошибка сохранения Excel: {e}")

# ========== КОМАНДЫ ==========

@dp.message(Command("setyear"))
async def cmd_set_year(message: Message):
    """Установка года"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав.")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("❌ Использование: /setyear [год]")
            return
        
        year = int(parts[1])
        if 2020 <= year <= 2030:
            global current_year
            current_year = year
            await message.answer(f"✅ Год установлен: {year}")
        else:
            await message.answer("❌ Год должен быть от 2020 до 2030")
    except ValueError:
        await message.answer("❌ Введите число")

@dp.message(Command("debug"))
async def cmd_debug(message: Message):
    """Отладка - показать все брони"""
    if not is_admin(message.from_user.id):
        return
    
    all_res = db.get_all_reservations()
    today = get_today_str()
    
    text = f"**🔧 Отладка**\n"
    text += f"Сегодня: {today}\n"
    text += f"Всего броней: {len(all_res)}\n\n"
    
    for r in all_res[:20]:  # Ограничим вывод
        text += f"ID {r['id']}: дата={r.get('date')}, имя={r.get('name')}\n"
        if r.get('date') == today:
            text += "  ⬅️ СЕГОДНЯ!\n"
    
    if len(all_res) > 20:
        text += f"\n... и еще {len(all_res) - 20} броней"
    
    await message.answer(text, parse_mode="Markdown")

# ========== УВЕДОМЛЕНИЯ ДЛЯ ОФИЦИАНТОВ ==========

async def send_30min_notifications():
    """Отправка уведомлений за 30 минут до брони"""
    upcoming = db.get_upcoming_reservations(30)
    today = get_today_str()
    
    for res in upcoming:
        table = res.get('table_number')
        if not table:
            continue
        
        waiters = db.get_waiters_for_table_on_date(table, today)
        
        for waiter_id in waiters:
            if db.check_notification_sent(res['id'], waiter_id, '30min'):
                continue
            
            text = (
                f"⏰ **Напоминание: через 30 минут**\n\n"
                f"🪑 Стол {table}\n"
                f"🕐 {res.get('time')} | 👤 {res.get('name')}\n"
                f"👥 {res.get('guests')} чел.\n"
            )
            if res.get('occasion'):
                text += f"🎉 Повод: {res.get('occasion')}\n"
            if res.get('deposit', 0) > 0:
                text += f"💰 Депозит: {res.get('deposit')}₽\n"
            
            try:
                await bot.send_message(waiter_id, text, parse_mode="Markdown")
                db.save_notification(res['id'], waiter_id, '30min')
                print(f"✅ Уведомление за 30 мин отправлено официанту {waiter_id} для стола {table}")
            except Exception as e:
                print(f"❌ Ошибка отправки официанту {waiter_id}: {e}")

async def send_birthday_notifications():
    """Отправка уведомлений через 1 час после брони (для ДР и годовщин)"""
    past = db.get_past_reservations(1)
    today = get_today_str()
    
    for res in past:
        occasion = res.get('occasion', '').lower()
        if 'день рождения' not in occasion and 'годовщина' not in occasion:
            continue
        
        table = res.get('table_number')
        if not table:
            continue
        
        waiters = db.get_waiters_for_table_on_date(table, today)
        
        for waiter_id in waiters:
            if db.check_notification_sent(res['id'], waiter_id, 'birthday'):
                continue
            
            text = (
                f"🎂 **Напоминание: не забудь поздравить!**\n\n"
                f"🪑 Стол {table}\n"
                f"👤 {res.get('name')}\n"
                f"🎉 Повод: {res.get('occasion')}\n\n"
                f"Час назад пришла бронь, не забудь поздравить гостей!"
            )
            
            try:
                await bot.send_message(waiter_id, text, parse_mode="Markdown")
                db.save_notification(res['id'], waiter_id, 'birthday')
                print(f"✅ Поздравительное уведомление отправлено официанту {waiter_id}")
            except Exception as e:
                print(f"❌ Ошибка отправки: {e}")

async def send_deposit_notifications():
    """Отправка уведомлений через 1.5 часа после брони (напоминание о депозите)"""
    past = db.get_past_reservations(1.5)
    today = get_today_str()
    
    for res in past:
        if res.get('deposit', 0) <= 0:
            continue
        
        table = res.get('table_number')
        if not table:
            continue
        
        waiters = db.get_waiters_for_table_on_date(table, today)
        
        for waiter_id in waiters:
            if db.check_notification_sent(res['id'], waiter_id, 'deposit'):
                continue
            
            text = (
                f"💰 **Напоминание о депозите**\n\n"
                f"🪑 Стол {table}\n"
                f"👤 {res.get('name')}\n"
                f"💰 Сумма: {res.get('deposit')}₽\n\n"
                f"Полтора часа назад пришла бронь, не забудь про депозит!"
            )
            
            try:
                await bot.send_message(waiter_id, text, parse_mode="Markdown")
                db.save_notification(res['id'], waiter_id, 'deposit')
                print(f"✅ Напоминание о депозите отправлено официанту {waiter_id}")
            except Exception as e:
                print(f"❌ Ошибка отправки: {e}")

# ========== УТРЕННИЙ ОТЧЕТ ==========
async def send_morning_report():
    """Отправка утреннего отчета"""
    today = get_today_str()
    reservations = db.get_today_reservations()
    
    if not reservations:
        text = f"📋 **Утренний отчет {today}**\n\nНа сегодня броней нет."
    else:
        reservations.sort(key=lambda x: x.get('time', '00:00'))
        text = f"📋 **Утренний отчет {today}**\n\n"
        for r in reservations:
            table_text = r.get('table_number', 'Не назначен')
            if r.get('table_strict'):
                table_text += " (выбор гостя)"
            
            text += (
                f"🕐 {r.get('time')} | 👤 {r.get('name')}\n"
                f"📞 {r.get('phone')} | 👥 {r.get('guests')} чел.\n"
                f"🪑 Стол: {table_text}\n"
            )
            if r.get('deposit', 0) > 0:
                text += f"💰 Депозит: {r.get('deposit')}₽\n"
            if r.get('occasion'):
                text += f"🎉 {r.get('occasion')}\n"
            text += "-----------------\n"
    
    await notify_all_users(text)

# ========== ЗАПУСК ==========
async def on_startup():
    """Действия при запуске"""
    print("🧹 Запуск очистки старых данных...")
    db.cleanup_old_reservations()
    db.cleanup_old_excel_files()
    
    scheduler.add_job(
        send_morning_report,
        'cron',
        hour=MORNING_REPORT_HOUR,
        minute=MORNING_REPORT_MINUTE,
        id='morning_report'
    )
    
    scheduler.add_job(
        send_30min_notifications,
        'interval',
        minutes=1,
        id='30min_notifications'
    )
    
    scheduler.add_job(
        send_birthday_notifications,
        'interval',
        minutes=5,
        id='birthday_notifications'
    )
    
    scheduler.add_job(
        send_deposit_notifications,
        'interval',
        minutes=5,
        id='deposit_notifications'
    )
    
    scheduler.add_job(
        db.cleanup_old_reservations,
        'cron',
        hour=3,
        minute=0,
        id='daily_cleanup'
    )
    
    scheduler.start()
    print(f"✅ Планировщик запущен")
    print(f"✅ Главный администратор ID: {MAIN_ADMIN_ID}")
    print(f"✅ Текущий год: {current_year}")
    print(f"✅ Автоочистка старых броней активирована")

async def main():
    """Главная функция"""
    dp.startup.register(on_startup)
    print("🚀 Бот запускается...")
    await dp.start_polling(bot)

# ========== ЗАПУСК С ВЕБ-СЕРВЕРОМ ==========
from aiohttp import web
import threading
import asyncio

# Простой обработчик для проверки работы
async def healthcheck(request):
    return web.Response(text="✅ Бот работает!", status=200)

async def run_web_server():
    """Запуск веб-сервера для проверки"""
    app = web.Application()
    app.router.add_get('/', healthcheck)
    app.router.add_get('/health', healthcheck)
    
    # Запускаем на всех интерфейсах, порт 10000
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    print("✅ Веб-сервер для проверки запущен на порту 10000")
    print(f"🌐 URL: https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')}")
    
    # Бесконечное ожидание
    await asyncio.Event().wait()

async def main_with_web():
    """Запуск и бота, и веб-сервера"""
    # Запускаем веб-сервер в фоне
    web_task = asyncio.create_task(run_web_server())
    
    # Запускаем бота
    await main()

if __name__ == "__main__":
    try:
        import os
        print("🚀 Запуск бота с веб-сервером...")
        asyncio.run(main_with_web())
    except KeyboardInterrupt:
        print("👋 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        traceback.print_exc()
        sys.exit(1)