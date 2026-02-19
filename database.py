import sqlite3
import datetime
from typing import List, Tuple, Optional

class Database:
    """Класс для работы с базой данных"""
    
    def __init__(self, db_name="restaurant.db"):
        self.db_name = db_name
        self.init_db()
    
    def init_db(self):
        """Создание таблиц при первом запуске"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            # Таблица с бронями
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,           -- Дата брони (ГГГГ-ММ-ДД)
                    table_number TEXT,             -- Номер стола (может быть пустым)
                    guest_name TEXT NOT NULL,       -- Имя гостя
                    phone TEXT NOT NULL,            -- Телефон
                    occasion TEXT,                  -- Повод посещения
                    time TEXT NOT NULL,             -- Время
                    guests_count INTEGER NOT NULL,   -- Количество гостей
                    deposit INTEGER DEFAULT 0,       -- Депозит (рубли)
                    created_at TEXT NOT NULL         -- Когда создана бронь
                )
            ''')
            
            # Таблица с пользователями бота
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    is_admin INTEGER DEFAULT 0,      -- 0 - обычный, 1 - администратор
                    created_at TEXT NOT NULL
                )
            ''')
            
            conn.commit()
    
    def add_reservation(self, date: str, table_number: str, guest_name: str, 
                       phone: str, occasion: str, time: str, guests_count: int) -> int:
        """Добавление новой брони"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            created_at = datetime.datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO reservations 
                (date, table_number, guest_name, phone, occasion, time, guests_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (date, table_number, guest_name, phone, occasion, time, guests_count, created_at))
            
            conn.commit()
            return cursor.lastrowid
    
    def update_table_number(self, reservation_id: int, new_table_number: str):
        """Обновление номера стола"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE reservations 
                SET table_number = ? 
                WHERE id = ?
            ''', (new_table_number, reservation_id))
            conn.commit()
    
    def update_deposit(self, reservation_id: int, deposit: int):
        """Обновление суммы депозита"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE reservations 
                SET deposit = ? 
                WHERE id = ?
            ''', (deposit, reservation_id))
            conn.commit()
    
    def get_today_reservations(self) -> List[Tuple]:
        """Получение броней на сегодня"""
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        return self.get_reservations_by_date(today)
    
    def get_reservations_by_date(self, date: str) -> List[Tuple]:
        """Получение броней на конкретную дату"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM reservations 
                WHERE date = ? 
                ORDER BY time
            ''', (date,))
            return cursor.fetchall()
    
    def search_reservations(self, search_term: str) -> List[Tuple]:
        """Поиск броней по имени или телефону"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            # Ищем по частичному совпадению (SQL-инъекции защищены параметрами)
            cursor.execute('''
                SELECT * FROM reservations 
                WHERE guest_name LIKE ? OR phone LIKE ?
                ORDER BY date DESC, time
            ''', (f'%{search_term}%', f'%{search_term}%'))
            return cursor.fetchall()
    
    def add_user(self, user_id: int, username: str, first_name: str, is_admin: int = 0):
        """Добавление пользователя бота"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            created_at = datetime.datetime.now().isoformat()
            
            cursor.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, username, first_name, is_admin, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, is_admin, created_at))
            
            conn.commit()
    
    def get_all_users(self, only_admins: bool = False) -> List[Tuple]:
        """Получение всех пользователей"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            if only_admins:
                cursor.execute('SELECT user_id FROM users WHERE is_admin = 1')
            else:
                cursor.execute('SELECT user_id FROM users')
            return [row[0] for row in cursor.fetchall()]
    
    def is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result and result[0] == 1

# Создаем глобальный объект базы данных
db = Database()