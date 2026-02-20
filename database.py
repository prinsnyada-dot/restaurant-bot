import sqlite3
import json
from datetime import datetime, timedelta
import pytz
import os

class Database:
    def __init__(self, db_name="restaurant.db"):
        self.db_name = db_name
        self.init_db()
        # При запуске проверяем и удаляем старые брони
        self.cleanup_old_reservations()
    
    def init_db(self):
        """Создание таблиц при первом запуске"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            # Таблица с бронями
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    date TEXT NOT NULL
                )
            ''')
            
            # Индекс для быстрого поиска по дате
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_reservations_date 
                ON reservations(date)
            ''')
            
            # ТАБЛИЦА ДЛЯ ПОЛЬЗОВАТЕЛЕЙ (НОВАЯ)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    is_admin INTEGER DEFAULT 0,
                    is_waiter INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            ''')
            
            # Таблица для официантов и их столов (с датой)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS waiters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    tables TEXT NOT NULL,
                    date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, date)
                )
            ''')
            
            # Индекс для быстрого поиска по дате
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_waiters_date 
                ON waiters(date)
            ''')
            
            # Таблица для отслеживания отправленных уведомлений
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reservation_id INTEGER NOT NULL,
                    waiter_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    FOREIGN KEY (reservation_id) REFERENCES reservations(id)
                )
            ''')
            
            # Таблица для хранения Excel файлов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS excel_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    filepath TEXT NOT NULL
                )
            ''')
            
            conn.commit()
    
    def cleanup_old_reservations(self):
        """Удаление броней старше 2 месяцев"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                
                # Вычисляем дату 2 месяца назад
                two_months_ago = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
                
                # Получаем список удаляемых броней для лога
                cursor.execute('''
                    SELECT id, data FROM reservations 
                    WHERE date < ?
                ''', (two_months_ago,))
                
                old_reservations = cursor.fetchall()
                
                if old_reservations:
                    print(f"🧹 Найдено {len(old_reservations)} броней старше 2 месяцев")
                    
                    # Удаляем связанные уведомления
                    for res in old_reservations:
                        cursor.execute('''
                            DELETE FROM notifications WHERE reservation_id = ?
                        ''', (res[0],))
                    
                    # Удаляем старые брони
                    cursor.execute('''
                        DELETE FROM reservations WHERE date < ?
                    ''', (two_months_ago,))
                    
                    conn.commit()
                    print(f"✅ Удалено {len(old_reservations)} старых броней")
                    
        except Exception as e:
            print(f"❌ Ошибка при удалении старых броней: {e}")
    
    def cleanup_old_excel_files(self):
        """Удаление старых Excel файлов (старше 2 месяцев)"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                
                two_months_ago = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
                
                # Получаем список старых файлов
                cursor.execute('''
                    SELECT filepath FROM excel_files WHERE date < ?
                ''', (two_months_ago,))
                
                old_files = cursor.fetchall()
                
                # Удаляем физические файлы
                for file in old_files:
                    filepath = file[0]
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        print(f"🗑 Удален старый Excel файл: {filepath}")
                
                # Удаляем записи из БД
                cursor.execute('''
                    DELETE FROM excel_files WHERE date < ?
                ''', (two_months_ago,))
                
                conn.commit()
                
        except Exception as e:
            print(f"❌ Ошибка при удалении старых Excel файлов: {e}")
    
    # ====== МЕТОДЫ ДЛЯ БРОНЕЙ ======
    
    def add_reservation(self, reservation_data):
        """Добавление брони"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            created_at = datetime.now().isoformat()
            data_json = json.dumps(reservation_data, ensure_ascii=False)
            date = reservation_data.get('date', '')
            
            cursor.execute(
                'INSERT INTO reservations (data, created_at, date) VALUES (?, ?, ?)',
                (data_json, created_at, date)
            )
            conn.commit()
            return cursor.lastrowid
    
    def get_all_reservations(self):
        """Получение всех броней"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, data, created_at FROM reservations ORDER BY date DESC, id DESC')
            rows = cursor.fetchall()
            
            reservations = []
            for row in rows:
                res_data = json.loads(row[1])
                res_data['id'] = row[0]
                reservations.append(res_data)
            return reservations
    
    def get_today_reservations(self):
        """Получение броней на сегодня с учетом часового пояса"""
        tz = pytz.timezone("Asia/Yekaterinburg")
        today = datetime.now(tz).strftime("%Y-%m-%d")
        print(f"🔍 Запрос броней на дату: {today}")
        
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, data FROM reservations WHERE date = ?', (today,))
            rows = cursor.fetchall()
            
            today_reservations = []
            for row in rows:
                res_data = json.loads(row[1])
                res_data['id'] = row[0]
                today_reservations.append(res_data)
            
            print(f"✅ Найдено броней на сегодня: {len(today_reservations)}")
            return today_reservations
    
    def get_reservations_by_date(self, date):
        """Получение броней по конкретной дате"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, data FROM reservations WHERE date = ? ORDER BY data->>"$.time"', (date,))
            rows = cursor.fetchall()
            
            date_reservations = []
            for row in rows:
                res_data = json.loads(row[1])
                res_data['id'] = row[0]
                date_reservations.append(res_data)
            
            return date_reservations
    
    def search_reservations(self, search_term):
        """Поиск броней"""
        all_res = self.get_all_reservations()
        results = []
        search_term_lower = search_term.lower()
        
        for r in all_res:
            if (search_term_lower in r.get('name', '').lower() or 
                search_term in r.get('phone', '') or
                search_term_lower in r.get('occasion', '').lower()):
                results.append(r)
        return results
    
    def get_reservation_by_id(self, reservation_id):
        """Получение брони по ID"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT data FROM reservations WHERE id = ?', (reservation_id,))
            row = cursor.fetchone()
            if row:
                res_data = json.loads(row[0])
                res_data['id'] = reservation_id
                return res_data
            return None
    
    def update_reservation(self, reservation_id, updated_data):
        """Обновление брони"""
        current = self.get_reservation_by_id(reservation_id)
        if not current:
            return False
        
        current.update(updated_data)
        
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            save_data = current.copy()
            if 'id' in save_data:
                del save_data['id']
            
            data_json = json.dumps(save_data, ensure_ascii=False)
            cursor.execute(
                'UPDATE reservations SET data = ? WHERE id = ?',
                (data_json, reservation_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_reservation(self, reservation_id):
        """Удаление брони"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            # Удаляем связанные уведомления
            cursor.execute('DELETE FROM notifications WHERE reservation_id = ?', (reservation_id,))
            # Удаляем саму бронь
            cursor.execute('DELETE FROM reservations WHERE id = ?', (reservation_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    # ====== МЕТОДЫ ДЛЯ ОФИЦИАНТОВ (С ДАТАМИ) ======
    
    def set_waiter_tables_for_date(self, user_id: int, name: str, tables: list, date: str = None):
        """Установка столов для официанта на конкретную дату"""
        if date is None:
            tz = pytz.timezone("Asia/Yekaterinburg")
            date = datetime.now(tz).strftime("%Y-%m-%d")
        
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            created_at = datetime.now().isoformat()
            tables_json = json.dumps(tables, ensure_ascii=False)
            
            cursor.execute('''
                INSERT OR REPLACE INTO waiters (user_id, name, tables, date, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, name, tables_json, date, created_at))
            conn.commit()
            print(f"👤 Официант {user_id} назначен на столы {tables} на дату {date}")
    
    def get_waiter_tables_for_date(self, user_id: int, date: str = None) -> list:
        """Получение списка столов официанта на конкретную дату"""
        if date is None:
            tz = pytz.timezone("Asia/Yekaterinburg")
            date = datetime.now(tz).strftime("%Y-%m-%d")
        
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT tables FROM waiters 
                WHERE user_id = ? AND date = ?
            ''', (user_id, date))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return []
    
    def get_waiters_for_table_on_date(self, table_number: str, date: str = None) -> list:
        """Получение всех официантов, обслуживающих стол в конкретную дату"""
        if date is None:
            tz = pytz.timezone("Asia/Yekaterinburg")
            date = datetime.now(tz).strftime("%Y-%m-%d")
        
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, tables FROM waiters 
                WHERE date = ?
            ''', (date,))
            rows = cursor.fetchall()
            
            waiters = []
            for row in rows:
                tables = json.loads(row[1])
                if table_number in tables:
                    waiters.append(row[0])
            return waiters
    
    def get_all_waiters_for_date(self, date: str = None) -> list:
        """Получение всех официантов на конкретную дату"""
        if date is None:
            tz = pytz.timezone("Asia/Yekaterinburg")
            date = datetime.now(tz).strftime("%Y-%m-%d")
        
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, name, tables FROM waiters 
                WHERE date = ?
                ORDER BY name
            ''', (date,))
            rows = cursor.fetchall()
            
            waiters = []
            for row in rows:
                waiters.append({
                    'id': row[0],
                    'name': row[1],
                    'tables': json.loads(row[2])
                })
            return waiters
    
    def remove_waiter_for_date(self, user_id: int, date: str = None):
        """Удаление официанта на конкретную дату"""
        if date is None:
            tz = pytz.timezone("Asia/Yekaterinburg")
            date = datetime.now(tz).strftime("%Y-%m-%d")
        
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM waiters WHERE user_id = ? AND date = ?
            ''', (user_id, date))
            conn.commit()
            return cursor.rowcount > 0
    
    # ====== МЕТОДЫ ДЛЯ УВЕДОМЛЕНИЙ ======
    
    def save_notification(self, reservation_id: int, waiter_id: int, notif_type: str):
        """Сохранение информации об отправленном уведомлении"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            sent_at = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO notifications (reservation_id, waiter_id, type, sent_at)
                VALUES (?, ?, ?, ?)
            ''', (reservation_id, waiter_id, notif_type, sent_at))
            conn.commit()
    
    def check_notification_sent(self, reservation_id: int, waiter_id: int, notif_type: str) -> bool:
        """Проверка, отправлялось ли уже такое уведомление"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id FROM notifications 
                WHERE reservation_id = ? AND waiter_id = ? AND type = ?
            ''', (reservation_id, waiter_id, notif_type))
            return cursor.fetchone() is not None
    
    def get_upcoming_reservations(self, minutes: int = 30) -> list:
        """Получение броней, которые наступят через указанное количество минут"""
        tz = pytz.timezone("Asia/Yekaterinburg")
        now = datetime.now(tz)
        target_time = now + timedelta(minutes=minutes)
        
        target_date = target_time.strftime("%Y-%m-%d")
        target_time_str = target_time.strftime("%H:%M")
        
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, data FROM reservations 
                WHERE date = ? AND data LIKE ?
            ''', (target_date, f'%"time": "{target_time_str}"%'))
            
            rows = cursor.fetchall()
            upcoming = []
            for row in rows:
                res_data = json.loads(row[1])
                res_data['id'] = row[0]
                upcoming.append(res_data)
            
            return upcoming
    
    def get_past_reservations(self, hours: float) -> list:
        """Получение броней, которые были указанное количество часов назад"""
        tz = pytz.timezone("Asia/Yekaterinburg")
        now = datetime.now(tz)
        past_time = now - timedelta(hours=hours)
        
        past_date = past_time.strftime("%Y-%m-%d")
        past_time_str = past_time.strftime("%H:%M")
        
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, data FROM reservations 
                WHERE date = ? AND data LIKE ?
            ''', (past_date, f'%"time": "{past_time_str}"%'))
            
            rows = cursor.fetchall()
            past = []
            for row in rows:
                res_data = json.loads(row[1])
                res_data['id'] = row[0]
                past.append(res_data)
            
            return past
    
    # ====== МЕТОДЫ ДЛЯ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ ======
    
    def add_user(self, user_id: int, username: str, first_name: str, is_admin: int = 0):
        """Добавление или обновление пользователя"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            created_at = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, is_admin, is_waiter, created_at)
                VALUES (?, ?, ?, ?, COALESCE((SELECT is_waiter FROM users WHERE user_id = ?), 0), ?)
            ''', (user_id, username, first_name, is_admin, user_id, created_at))
            conn.commit()
    
    def get_user(self, user_id: int) -> dict:
        """Получение данных пользователя"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    'user_id': row[0],
                    'username': row[1],
                    'first_name': row[2],
                    'is_admin': row[3],
                    'is_waiter': row[4],
                    'created_at': row[5]
                }
            return None
    
    def set_admin(self, user_id: int, is_admin: bool):
        """Установка прав администратора"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET is_admin = ? WHERE user_id = ?
            ''', (1 if is_admin else 0, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def set_waiter(self, user_id: int, is_waiter: bool):
        """Установка прав официанта"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET is_waiter = ? WHERE user_id = ?
            ''', (1 if is_waiter else 0, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_all_users(self) -> list:
        """Получение всех пользователей"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users')
            return [row[0] for row in cursor.fetchall()]
    
    def get_all_admins(self, main_admin_id: int) -> list:
        """Получение всех администраторов"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, first_name FROM users WHERE is_admin = 1')
            admins = []
            for row in cursor.fetchall():
                admins.append({
                    'id': row[0],
                    'name': row[1],
                    'is_main': (row[0] == main_admin_id)
                })
            return admins
    
    def get_all_waiters(self) -> list:
        """Получение всех официантов"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, first_name FROM users WHERE is_waiter = 1')
            rows = cursor.fetchall()
            return [{'id': row[0], 'name': row[1]} for row in rows]
    
    # ====== МЕТОДЫ ДЛЯ EXCEL ФАЙЛОВ ======
    
    def save_excel_file(self, filename: str, date: str, filepath: str):
        """Сохранение информации об Excel файле"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            created_at = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO excel_files (filename, date, created_at, filepath)
                VALUES (?, ?, ?, ?)
            ''', (filename, date, created_at, filepath))
            conn.commit()
    
    def get_excel_files_by_date(self, date: str) -> list:
        """Получение всех Excel файлов за дату"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT filename, filepath, created_at FROM excel_files 
                WHERE date = ?
                ORDER BY created_at DESC
            ''', (date,))
            
            return cursor.fetchall()

# Создаем глобальный экземпляр базы данных
db = Database()