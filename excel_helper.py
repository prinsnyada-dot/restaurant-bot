import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
import datetime
import os
from typing import List, Tuple, Dict

class ExcelGenerator:
    """Класс для создания Excel таблиц с бронями"""
    
    @staticmethod
    def create_reservation_file(reservations: List[Dict], date: str) -> str:
        """
        Создает Excel файл с бронями на указанную дату
        reservations: список словарей с данными броней
        date: дата в формате YYYY-MM-DD
        Возвращает путь к созданному файлу
        """
        # Создаем новую книгу Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Брони {date}"
        
        # Заголовки столбцов
        headers = [
            "ID", "Дата", "Стол", "Имя гостя", "Телефон", 
            "Повод", "Время", "Гостей", "Депозит (₽)"
        ]
        
        # Форматирование заголовков
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        
        # Применяем форматирование к заголовкам
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.value = header
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
        
        # Заполняем данными
        border = Border(
            left=Side(style='thin'), 
            right=Side(style='thin'),
            top=Side(style='thin'), 
            bottom=Side(style='thin')
        )
        
        for row_num, res in enumerate(reservations, 2):
            # Получаем данные из словаря по ключам
            row_data = [
                res.get('id', ''),                    # ID
                res.get('date', ''),                   # Дата
                res.get('table_number', 'Не назначен'), # Стол
                res.get('name', ''),                    # Имя
                res.get('phone', ''),                   # Телефон
                res.get('occasion', '-'),                # Повод
                res.get('time', ''),                     # Время
                res.get('guests', ''),                   # Гости
                res.get('deposit', 0)                    # Депозит
            ]
            
            for col_num, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_num, column=col_num)
                cell.value = value
                cell.border = border
                
                # Форматирование депозита
                if col_num == 9 and value and int(value) > 0:
                    cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                elif col_num == 9 and value and int(value) == 0:
                    cell.fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
        
        # Автоматическая ширина колонок
        for col in range(1, len(headers) + 1):
            max_length = 0
            column_letter = get_column_letter(col)
            for row in range(1, len(reservations) + 2):
                cell = ws[f"{column_letter}{row}"]
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 30)  # Не шире 30 символов
            ws.column_dimensions[column_letter].width = adjusted_width
        
        # Сохраняем файл
        timestamp = datetime.datetime.now().strftime('%H%M%S')
        filename = f"reservations_{date}_{timestamp}.xlsx"
        filepath = os.path.join("excel_files", filename)
        
        # Создаем папку, если её нет
        os.makedirs("excel_files", exist_ok=True)
        
        wb.save(filepath)
        print(f"✅ Excel файл сохранен: {filepath}")
        return filepath
    
    @staticmethod
    def create_reservation_file_simple(reservations: List[Dict], date: str) -> str:
        """
        Упрощенная версия для отладки - создает текстовый файл
        """
        filename = f"reservations_{date}.txt"
        os.makedirs("excel_files", exist_ok=True)
        filepath = os.path.join("excel_files", filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"Брони на {date}\n")
            f.write("="*60 + "\n\n")
            
            for r in sorted(reservations, key=lambda x: x.get('time', '00:00')):
                f.write(f"ID: {r.get('id')}\n")
                f.write(f"Время: {r.get('time')}\n")
                f.write(f"Имя: {r.get('name')}\n")
                f.write(f"Телефон: {r.get('phone')}\n")
                f.write(f"Гостей: {r.get('guests')}\n")
                
                table = r.get('table_number', '')
                if table:
                    strict = " (выбор гостя)" if r.get('table_strict') else ""
                    f.write(f"Стол: {table}{strict}\n")
                
                if r.get('occasion'):
                    f.write(f"Повод: {r.get('occasion')}\n")
                if r.get('deposit', 0) > 0:
                    f.write(f"Депозит: {r.get('deposit')}₽\n")
                f.write("-"*40 + "\n")
        
        return filepath