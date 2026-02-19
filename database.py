import sqlite3
import json
from datetime import datetime
import pytz  

class Database:
    def __init__(self, db_name="restaurant.db"):
        self.db_name = db_name
        self.init_db()
    
    def init_db(self):
        """Создание таблицы при первом запуске"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            ''')
            conn.commit()
    
    def add_reservation(self, reservation_data):
        """Добавление брони"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            created_at = datetime.now().isoformat()
            # Преобразуем словарь в JSON строку для хранения
            data_json = json.dumps(reservation_data, ensure_ascii=False)
            cursor.execute(
                'INSERT INTO reservations (data, created_at) VALUES (?, ?)',
                (data_json, created_at)
            )
            conn.commit()
            return cursor.lastrowid
    
    def get_all_reservations(self):
        """Получение всех броней"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, data, created_at FROM reservations ORDER BY id')
            rows = cursor.fetchall()
            
            reservations = []
            for row in rows:
                res_data = json.loads(row[1])
                res_data['id'] = row[0]  # Добавляем ID из базы
                reservations.append(res_data)
            return reservations
    
  def get_today_reservations(self):
    """Получение броней на сегодня с учетом часового пояса"""
    # Получаем сегодняшнюю дату с учетом часового пояса
    tz = pytz.timezone("Asia/Yekaterinburg")
    today = datetime.now(tz).strftime("%Y-%m-%d")
    print(f"🔍 Запрос броней на дату: {today}")
    
    with sqlite3.connect(self.db_name) as conn:
        cursor = conn.cursor()
        # Ищем брони, где дата совпадает с сегодняшней
        cursor.execute('SELECT id, data FROM reservations')
        rows = cursor.fetchall()
        
        today_reservations = []
        for row in rows:
            res_data = json.loads(row[1])
            res_data['id'] = row[0]
            
            print(f"  Проверка брони #{row[0]}: дата в базе = {res_data.get('date')}")
            
            if res_data.get('date') == today:
                today_reservations.append(res_data)
        
        print(f"✅ Найдено броней на сегодня: {len(today_reservations)}")
        return today_reservations
    
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
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            data_json = json.dumps(updated_data, ensure_ascii=False)
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
            cursor.execute('DELETE FROM reservations WHERE id = ?', (reservation_id,))
            conn.commit()
            return cursor.rowcount > 0

# Создаем глобальный экземпляр базы данных
db = Database()