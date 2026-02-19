import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
import datetime
import os
from typing import List, Tuple

class ExcelGenerator:
    """Класс для создания Excel таблиц с бронями"""
    
    @staticmethod
    def create_reservation_file(reservations: List[Tuple], date: str) -> str:
        """
        Создает Excel файл с бронями на указанную дату
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
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin')
        )
        
        for row_num, res in enumerate(reservations, 2):
            # res содержит: id, date, table_number, guest_name, phone, 
            # occasion, time, guests_count, deposit, created_at
            row_data = [
                res[0],  # ID
                res[1],  # Дата
                res[2] if res[2] else "Не назначен",  # Стол
                res[3],  # Имя
                res[4],  # Телефон
                res[5] if res[5] else "-",  # Повод
                res[6],  # Время
                res[7],  # Гости
                res[8] if len(res) > 8 else 0  # Депозит
            ]
            
            for col_num, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_num, column=col_num)
                cell.value = value
                cell.border = border
                if col_num == 9 and value > 0:  # Депозит > 0 - выделяем зеленым
                    cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                elif col_num == 9 and value == 0:  # Нет депозита - серым
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
        filename = f"reservations_{date}_{datetime.datetime.now().strftime('%H%M%S')}.xlsx"
        filepath = os.path.join("excel_files", filename)
        
        # Создаем папку, если её нет
        os.makedirs("excel_files", exist_ok=True)
        
        wb.save(filepath)
        return filepath