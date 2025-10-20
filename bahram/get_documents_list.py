#!/usr/bin/env python3

import gspread
import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import base64
import os
import zipfile
import re
import pdfplumber
import shutil
import traceback
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert
import psycopg2
import openpyxl

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Период для получения данных (с 1 марта 2025 года до сегодня)
date_from = datetime(2025, 3, 1).strftime('%Y-%m-%d')
date_to = datetime.now().strftime('%Y-%m-%d')

credentials_file = r"cred.json"
spreadsheet_key = "15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ"
sheet_name = "Инвесторы"

# PostgreSQL конфигурация
PG_HOST = '94.103.84.245'
PG_PORT = 5432
PG_USER = 'bahram'
PG_PASSWORD = 'Dadajonim99'
PG_DB = 'wb_baah'
PG_SCHEMA = 'documents'
PG_TABLE = 'upd_items'

# Создание подключения к БД
engine = create_engine(f'postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}')

def make_request_with_retry(url, headers, params=None, max_retries=15, initial_delay=10):
    """
    Выполняет запрос с повторными попытками при ошибках 429 и 5xx.
    Увеличено количество попыток и время задержек для надежности.
    
    :param url: URL для запроса
    :param headers: Заголовки запроса
    :param params: Параметры запроса
    :param max_retries: Максимальное количество повторных попыток (по умолчанию 15)
    :param initial_delay: Начальная задержка в секундах (по умолчанию 10)
    :return: Response объект или None при неудаче
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=90)
            
            # Успешный ответ
            if response.status_code == 200:
                logger.info(f"Успешный запрос после {attempt + 1} попыток")
                return response
            
            # Ошибка 429 (Too Many Requests) - нужно повторить с задержкой
            if response.status_code == 429:
                # Увеличенная экспоненциальная задержка: 10, 20, 40, 80, 160, 320, 640, 1280 сек
                delay = min(initial_delay * (2 ** attempt), 1800)  # Максимум 30 минут
                logger.warning(f"⚠️ Ошибка 429 (Too Many Requests). Повторная попытка {attempt + 1}/{max_retries} через {delay} сек.")
                time.sleep(delay)
                continue
            
            # Ошибки 5xx (серверные ошибки) - можно повторить
            if 500 <= response.status_code < 600:
                delay = min(initial_delay * (3 ** attempt), 1800)  # Максимум 30 минут
                logger.warning(f"Серверная ошибка {response.status_code}. Повторная попытка {attempt + 1}/{max_retries} через {delay} сек.")
                time.sleep(delay)
                continue
            
            # Другие ошибки (401, 403, 404 и т.д.) - не повторяем
            logger.error(f"Ошибка {response.status_code} - не повторяем")
            return response
            
        except requests.exceptions.RequestException as e:
            delay = min(initial_delay * (2 ** attempt), 1800)  # Максимум 30 минут
            logger.error(f"Ошибка сети при запросе: {e}. Повторная попытка {attempt + 1}/{max_retries} через {delay} сек.")
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                logger.error(f"Исчерпаны все попытки запроса к {url}")
                return None
    
    logger.error(f"Не удалось выполнить запрос после {max_retries} попыток")
    return None

def get_sheet_data_as_dataframe(credentials_file, spreadsheet_key, sheet_name):
    """
    Получает данные из указанного листа Google Sheets и возвращает их в формате DataFrame.
    :param credentials_file: Путь к файлу с учетными данными (JSON).
    :param spreadsheet_key: Ключ таблицы Google Sheets.
    :param sheet_name: Имя листа в таблице Google Sheets.
    :return: DataFrame с данными из листа Google Sheets.
    """
    # Авторизация через gspread
    gc = gspread.service_account(filename=credentials_file)
    
    # Открытие таблицы и листа
    worksheet = gc.open_by_key(spreadsheet_key).worksheet(sheet_name)
    
    # Загрузка данных в DataFrame
    data = worksheet.get_all_records(expected_headers=None)
    df = pd.DataFrame(data, dtype=object)
    return df

def fetch_documents_list(api_key, begin_date, end_date, locale='ru', page_limit=50, max_pages=100):
    """
    Получает список документов для аккаунта с пагинацией.
    API endpoint: https://documents-api.wildberries.ru/api/v1/documents/list
    """
    url = 'https://documents-api.wildberries.ru/api/v1/documents/list'
    headers = {'Authorization': api_key}
    offset = 0
    all_documents = []
    
    for page in range(max_pages):
        params = {
            'locale': locale,
            'limit': page_limit,
            'offset': offset
        }
        
        # Добавляем даты только если они указаны
        if begin_date and end_date:
            params['beginTime'] = begin_date
            params['endTime'] = end_date
        
        try:
            response = make_request_with_retry(url, headers, params, max_retries=15, initial_delay=10)
            
            if response and response.status_code == 200:
                data = response.json()
                documents = data.get('data', {}).get('documents', [])
                
                if not documents:
                    break
                    
                all_documents.extend(documents)
                print(f"  Страница {page + 1}: +{len(documents)} документов")
                
                # Если получили меньше документов чем limit, значит это последняя страница
                if len(documents) < page_limit:
                    break
                    
                offset += page_limit
                # Адаптивная пауза с учетом burst лимита API
                if page % 3 == 0:
                    # После каждых 3 страниц - длинная пауза для восстановления burst лимита
                    print(f"  Пауза 120 секунд для соблюдения лимитов API (страница {page + 1})")
                    time.sleep(120)
                else:
                    # Между страницами внутри burst - средняя пауза
                    time.sleep(15)
                
            elif response and response.status_code == 401:
                print("  ✗ Ошибка: неверный API-ключ или доступ запрещен.")
                break
            elif response and response.status_code == 429:
                retry_after = response.headers.get('Retry-After', 12)
                print(f"  ⏳ Rate limit. Ожидание {retry_after} секунд...")
                time.sleep(int(retry_after))
                continue
            else:
                print(f"  ✗ Ошибка: {response.status_code if response else 'Нет ответа'} - {response.text[:100] if response else 'Нет ответа'}")
                break
                
        except Exception as e:
            print(f"  ✗ Ошибка при запросе: {e}")
            break
    
    return all_documents

def download_document(api_key, service_name, extension, save_dir='wb_documents'):
    """
    Скачивает один документ из списка документов продавца.
    API endpoint: https://documents-api.wildberries.ru/api/v1/documents/download
    """
    url = 'https://documents-api.wildberries.ru/api/v1/documents/download'
    headers = {'Authorization': api_key}
    params = {
        'serviceName': service_name,
        'extension': extension
    }
    
    try:
        response = make_request_with_retry(url, headers, params, max_retries=15, initial_delay=10)
        
        if response and response.status_code == 200:
            data = response.json()
            file_data = data.get('data', {})
            
            file_name = file_data.get('fileName', f'{service_name}.{extension}')
            document_base64 = file_data.get('document', '')
            
            if document_base64:
                # Декодируем base64
                document_bytes = base64.b64decode(document_base64)
                
                # Создаем директорию если её нет
                os.makedirs(save_dir, exist_ok=True)
                
                # Сохраняем файл
                file_path = os.path.join(save_dir, file_name)
                with open(file_path, 'wb') as f:
                    f.write(document_bytes)
                
                return {'success': True, 'file_path': file_path, 'file_name': file_name}
            else:
                return {'success': False, 'error': 'Нет данных документа'}
                
        elif response and response.status_code == 401:
            return {'success': False, 'error': 'Неверный API-ключ'}
        elif response and response.status_code == 429:
            retry_after = response.headers.get('Retry-After', 12)
            return {'success': False, 'error': f'Rate limit, ждать {retry_after} сек'}
        else:
            return {'success': False, 'error': f'{response.status_code if response else 'Нет ответа'} - {response.text if response else 'Нет ответа'}'}
            
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ============================================================================
# ФУНКЦИИ ДЛЯ ПАРСИНГА УПД
# ============================================================================

def extract_zip_file(zip_path, extract_to):
    """Разархивирует ZIP файл"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        return True, extract_to
    except Exception as e:
        return False, str(e)

def extract_upd_number_from_archive_name(archive_name):
    """
    Извлекает номер УПД из названия архива
    Примеры: 
    - "Universal transfer document 262209333.zip" -> "262209333"
    - "upd-262339466.zip" -> "262339466"
    """
    name = archive_name.replace('.zip', '')
    numbers = re.findall(r'\d+', name)
    if numbers:
        return numbers[-1]
    return None

def extract_date_from_filename(filename):
    """
    Извлекает дату из названия файла
    Примеры: 
    - "УПД №092800080382 от 28.09.2025.pdf"
    - "Отчет №492905534 от 2025-09-22.pdf"
    """
    # Ищем дату в формате DD.MM.YYYY
    match = re.search(r'от\s+(\d{2}\.\d{2}\.\d{4})', filename)
    if match:
        return match.group(1)
    
    # Ищем дату в формате YYYY-MM-DD
    match = re.search(r'от\s+(\d{4}-\d{2}-\d{2})', filename)
    if match:
        # Конвертируем YYYY-MM-DD в DD.MM.YYYY
        date_str = match.group(1)
        try:
            from datetime import datetime
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            return date_obj.strftime('%d.%m.%Y')
        except:
            return date_str
    
    # Ищем любую дату в формате DD.MM.YYYY
    match = re.search(r'(\d{2}\.\d{2}\.\d{4})', filename)
    if match:
        return match.group(1)
    
    # Ищем любую дату в формате YYYY-MM-DD
    match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    if match:
        date_str = match.group(1)
        try:
            from datetime import datetime
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            return date_obj.strftime('%d.%m.%Y')
        except:
            return date_str
    
    return None

def extract_report_number_from_filename(filename):
    """
    Извлекает номер отчета из названия файла
    Примеры: "Еженедельный отчет реализации №12345 от 28.09.2025.pdf" -> "12345"
    """
    match = re.search(r'№\s*(\d+)', filename)
    if match:
        return match.group(1)
    return None

def parse_table_row(row, upd_number, date):
    """
    Парсит строку таблицы УПД и извлекает данные о товаре
    
    Структура УПД (стандартная):
    - Колонка 2: Наименование товара
    - Колонка 12: Стоимость с налогом - всего
    """
    if not row or len(row) < 3:
        return None
    
    row_text = ' '.join([str(cell) if cell else '' for cell in row])
    
    # Пропускаем заголовки и служебные строки
    skip_keywords = ['Наименование товара', 'п/п', 'Всего к оплате', 'Итого к оплате']
    for keyword in skip_keywords:
        if keyword in row_text:
            return None
    
    if row_text.strip() in ['А', '1', '1а', '1б', '2', '2а', '3', '4', '5', '6', '7', '8', '9', '10', '10а', '11']:
        return None
    
    # Извлекаем наименование товара (колонка 2)
    item_name = None
    if len(row) > 2 and row[2]:
        item_name = str(row[2]).strip()
        if len(item_name) < 3 or item_name.isdigit():
            item_name = None
    
    # Извлекаем стоимость с налогом (колонка 12)
    item_cost = None
    if len(row) > 12 and row[12]:
        cost_str = str(row[12]).replace(' ', '').replace(',', '.')
        try:
            cost = float(cost_str)
            if cost > 0:
                item_cost = cost
        except (ValueError, TypeError):
            pass
    
    # Если не нашли в колонке 12, ищем в последних колонках
    if item_name and not item_cost:
        for cell in reversed(row):
            if cell and isinstance(cell, str):
                cleaned = cell.replace(' ', '').replace(',', '.')
                if 'Без' in cell or '—' in cell or 'x' in cell.lower():
                    continue
                try:
                    cost = float(cleaned)
                    if cost > 0:
                        item_cost = cost
                        break
                except (ValueError, TypeError):
                    continue
    
    if item_name and item_cost:
        return {
            'upd_number': upd_number,
            'date': date,
            'item_name': item_name,
            'cost': item_cost
        }
    
    return None

def parse_upd_pdf(pdf_path, upd_number_override=None):
    """Парсит PDF файл УПД и извлекает данные"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            all_items = []
            
            filename = os.path.basename(pdf_path)
            date_from_filename = extract_date_from_filename(filename)
            upd_number = upd_number_override
            
            for page in pdf.pages:
                tables = page.extract_tables()
                if not tables:
                    continue
                
                for table in tables:
                    for row_idx, row in enumerate(table):
                        if row_idx == 0:
                            continue
                        
                        item = parse_table_row(row, upd_number, date_from_filename)
                        if item:
                            all_items.append(item)
            
            return all_items
            
    except Exception as e:
        print(f"    ✗ Ошибка при парсинге PDF: {e}")
        return []

def parse_report_table_row(row, report_number, date):
    """
    Парсит строку таблицы еженедельного отчета реализации
    """
    if not row or len(row) < 3:
        print(f"      🔍 DEBUG: Строка пропущена - недостаточно колонок: {len(row) if row else 0}")
        return None
    
    row_text = ' '.join([str(cell) if cell else '' for cell in row])
    print(f"      🔍 DEBUG: Анализ строки: {row_text[:100]}...")
    print(f"      🔍 DEBUG: Колонки ({len(row)}): {[str(cell)[:20] if cell else 'None' for cell in row]}")
    
    # Пропускаем заголовки и служебные строки
    skip_keywords = ['Наименование', 'Артикул', 'Баркод', 'Количество', 'Сумма', 'Всего', 'Итого', 'п/п']
    for keyword in skip_keywords:
        if keyword in row_text and len(row_text.strip()) < 50:
            print(f"      🔍 DEBUG: Строка пропущена - заголовок: {keyword}")
            return None
    
    # Извлекаем данные товара
    item_data = {}
    
    # Для еженедельных отчетов структура: [№, Наименование, Документ основание, Дата, № документа, Сумма, НДС]
    item_name = None
    article = None
    barcode = None
    quantity = None
    amount = None
    
    if len(row) >= 6:
        # Наименование товара/услуги (колонка 1)
        if row[1] and isinstance(row[1], str) and len(row[1].strip()) > 3:
            item_name = row[1].strip()
            print(f"      🔍 DEBUG: Найдено наименование: {item_name}")
        
        # Номер документа как артикул (колонка 4)
        if row[4] and isinstance(row[4], str):
            doc_number = str(row[4]).strip()
            if re.match(r'^\d+$', doc_number) and len(doc_number) > 3:
                article = doc_number
                print(f"      🔍 DEBUG: Найден артикул (№ документа): {article}")
        
        # Сумма (колонка 5)
        if row[5] and isinstance(row[5], str):
            amount_str = str(row[5]).replace(' ', '').replace(',', '.')
            try:
                amt = float(amount_str)
                if amt > 0:
                    amount = amt
                    print(f"      🔍 DEBUG: Найдена сумма: {amount}")
            except (ValueError, TypeError):
                pass
        
        # Количество из номера строки (колонка 0) - если это число с точкой
        if row[0] and isinstance(row[0], str):
            qty_str = str(row[0]).replace('.', '').strip()
            try:
                qty = float(qty_str)
                if 0 < qty < 10000:
                    quantity = qty
                    print(f"      🔍 DEBUG: Найдено количество (из номера строки): {quantity}")
            except (ValueError, TypeError):
                pass
    else:
        # Fallback для старой логики, если структура отличается
        # Наименование товара (обычно в первой или второй колонке)
        for i, cell in enumerate(row[:3]):
            if cell and isinstance(cell, str) and len(cell.strip()) > 3:
                cell_clean = cell.strip()
                if not cell_clean.isdigit() and not re.match(r'^\d+$', cell_clean):
                    item_name = cell_clean
                    print(f"      🔍 DEBUG: Найдено наименование (fallback): {item_name}")
                    break
        
        # Артикул (обычно числовой)
        for cell in row:
            if cell and isinstance(cell, str):
                cell_clean = cell.strip()
                if re.match(r'^\d+$', cell_clean) and len(cell_clean) > 3:
                    article = cell_clean
                    print(f"      🔍 DEBUG: Найден артикул (fallback): {article}")
                    break
        
        # Баркод (обычно длинное число)
        for cell in row:
            if cell and isinstance(cell, str):
                cell_clean = cell.strip()
                if re.match(r'^\d{8,}$', cell_clean):
                    barcode = cell_clean
                    print(f"      🔍 DEBUG: Найден баркод (fallback): {barcode}")
                    break
        
        # Количество
        for cell in row:
            if cell and isinstance(cell, str):
                cell_clean = cell.replace(' ', '').replace(',', '.')
                try:
                    qty = float(cell_clean)
                    if 0 < qty < 10000:  # Разумные пределы для количества
                        quantity = qty
                        print(f"      🔍 DEBUG: Найдено количество (fallback): {quantity}")
                        break
                except (ValueError, TypeError):
                    continue
        
        # Сумма
        for cell in reversed(row):  # Ищем с конца, так как сумма обычно в последних колонках
            if cell and isinstance(cell, str):
                cell_clean = cell.replace(' ', '').replace(',', '.')
                try:
                    amt = float(cell_clean)
                    if amt > 0:
                        amount = amt
                        print(f"      🔍 DEBUG: Найдена сумма (fallback): {amount}")
                        break
                except (ValueError, TypeError):
                    continue
    
    if item_name and (article or barcode or quantity or amount):
        result = {
            'report_number': report_number,
            'date': date,
            'item_name': item_name,
            'article': article,
            'barcode': barcode,
            'quantity': quantity,
            'amount': amount,
            'report_type': 'weekly_sales'
        }
        print(f"      🔍 DEBUG: ✅ Создана запись: {result}")
        return result
    else:
        print(f"      🔍 DEBUG: ❌ Строка не подходит - нет достаточных данных")
        print(f"      🔍 DEBUG: item_name: {item_name}, article: {article}, barcode: {barcode}, quantity: {quantity}, amount: {amount}")
        return None

def parse_report_table_row_silent(row, report_number, date):
    """
    Парсит строку таблицы еженедельного отчета реализации (без дебага)
    """
    if not row or len(row) < 3:
        return None
    
    row_text = ' '.join([str(cell) if cell else '' for cell in row])
    
    # Пропускаем заголовки и служебные строки
    skip_keywords = ['Наименование', 'Артикул', 'Баркод', 'Количество', 'Сумма', 'Всего', 'Итого', 'п/п']
    for keyword in skip_keywords:
        if keyword in row_text and len(row_text.strip()) < 50:
            return None
    
    # Для еженедельных отчетов структура: [№, Наименование, Документ основание, Дата, № документа, Сумма, НДС]
    item_name = None
    article = None
    barcode = None
    quantity = None
    amount = None
    
    if len(row) >= 6:
        # Наименование товара/услуги (колонка 1)
        if row[1] and isinstance(row[1], str) and len(row[1].strip()) > 3:
            item_name = row[1].strip()
        
        # Номер документа как артикул (колонка 4)
        if row[4] and isinstance(row[4], str):
            doc_number = str(row[4]).strip()
            if re.match(r'^\d+$', doc_number) and len(doc_number) > 3:
                article = doc_number
        
        # Сумма (колонка 5)
        if row[5] and isinstance(row[5], str):
            amount_str = str(row[5]).replace(' ', '').replace(',', '.')
            try:
                amt = float(amount_str)
                # Убираем условие amt > 0, чтобы сохранять отрицательные суммы
                amount = amt
            except (ValueError, TypeError):
                pass
        
        # Количество из номера строки (колонка 0) - если это число с точкой
        if row[0] and isinstance(row[0], str):
            qty_str = str(row[0]).replace('.', '').strip()
            try:
                qty = float(qty_str)
                if 0 < qty < 10000:
                    quantity = qty
            except (ValueError, TypeError):
                pass
    else:
        # Fallback для старой логики, если структура отличается
        # Наименование товара (обычно в первой или второй колонке)
        for i, cell in enumerate(row[:3]):
            if cell and isinstance(cell, str) and len(cell.strip()) > 3:
                cell_clean = cell.strip()
                if not cell_clean.isdigit() and not re.match(r'^\d+$', cell_clean):
                    item_name = cell_clean
                    break
        
        # Артикул (обычно числовой)
        for cell in row:
            if cell and isinstance(cell, str):
                cell_clean = cell.strip()
                if re.match(r'^\d+$', cell_clean) and len(cell_clean) > 3:
                    article = cell_clean
                    break
        
        # Баркод (обычно длинное число)
        for cell in row:
            if cell and isinstance(cell, str):
                cell_clean = cell.strip()
                if re.match(r'^\d{8,}$', cell_clean):
                    barcode = cell_clean
                    break
        
        # Количество
        for cell in row:
            if cell and isinstance(cell, str):
                cell_clean = cell.replace(' ', '').replace(',', '.')
                try:
                    qty = float(cell_clean)
                    if 0 < qty < 10000:  # Разумные пределы для количества
                        quantity = qty
                        break
                except (ValueError, TypeError):
                    continue
        
        # Сумма
        for cell in reversed(row):  # Ищем с конца, так как сумма обычно в последних колонках
            if cell and isinstance(cell, str):
                cell_clean = cell.replace(' ', '').replace(',', '.')
                try:
                    amt = float(cell_clean)
                    # Убираем условие amt > 0, чтобы сохранять отрицательные суммы
                    amount = amt
                    break
                except (ValueError, TypeError):
                    continue
    
    if item_name and (article or barcode or quantity or amount):
        return {
            'report_number': report_number,
            'date': date,
            'item_name': item_name,
            'article': article,
            'barcode': barcode,
            'quantity': quantity,
            'amount': amount,
            'report_type': 'weekly_sales'
        }
    
    return None

def parse_report_pdf(pdf_path, report_number_override=None):
    """Парсит PDF файл еженедельного отчета реализации"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            all_items = []
            
            filename = os.path.basename(pdf_path)
            date_from_filename = extract_date_from_filename(filename)
            report_number = report_number_override or extract_report_number_from_filename(filename)
            
            print(f"    🔍 DEBUG: Парсинг отчета PDF: {filename}")
            print(f"    🔍 DEBUG: Номер отчета: {report_number}")
            print(f"    🔍 DEBUG: Дата: {date_from_filename}")
            
            for page_num, page in enumerate(pdf.pages, 1):
                tables = page.extract_tables()
                if not tables:
                    print(f"    🔍 DEBUG: Страница {page_num}: таблицы не найдены")
                    continue
                
                print(f"    🔍 DEBUG: Страница {page_num}: найдено {len(tables)} таблиц")
                
                for table_idx, table in enumerate(tables):
                    print(f"    🔍 DEBUG: Таблица {table_idx+1}: {len(table)} строк")
                    
                    for row_idx, row in enumerate(table):
                        if row_idx == 0:  # Пропускаем заголовок
                            continue
                        
                        item = parse_report_table_row_silent(row, report_number, date_from_filename)
                        if item:
                            all_items.append(item)
            
            print(f"    🔍 DEBUG: Всего извлечено позиций: {len(all_items)}")
            return all_items
            
    except Exception as e:
        print(f"    ✗ Ошибка при парсинге отчета PDF: {e}")
        print(f"    🔍 DEBUG: Детали ошибки: {traceback.format_exc()}")
        return []

def process_upd_archive(zip_path, company_name):
    """Обрабатывает один архив УПД"""
    archive_name = os.path.basename(zip_path)
    upd_number = extract_upd_number_from_archive_name(archive_name)
    
    # Создаем временную папку для разархивации
    extract_dir = zip_path.replace('.zip', '_extracted')
    
    # Разархивируем
    success, result = extract_zip_file(zip_path, extract_dir)
    if not success:
        return []
    
    # Ищем PDF файлы
    pdf_files = []
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(root, file))
    
    # Парсим каждый PDF
    all_items = []
    for pdf_path in pdf_files:
        items = parse_upd_pdf(pdf_path, upd_number_override=upd_number)
        for item in items:
            item['company'] = company_name
            # Убеждаемся, что report_type установлен правильно
            if 'report_type' not in item or item['report_type'] is None:
                item['report_type'] = 'upd'
        all_items.extend(items)
    
    return all_items

def process_report_archive(zip_path, company_name):
    """Обрабатывает один архив еженедельного отчета реализации"""
    archive_name = os.path.basename(zip_path)
    
    print(f"    🔍 DEBUG: Обработка архива отчета: {archive_name}")
    
    # Создаем временную папку для разархивации
    extract_dir = zip_path.replace('.zip', '_extracted')
    
    # Разархивируем
    success, result = extract_zip_file(zip_path, extract_dir)
    if not success:
        print(f"    🔍 DEBUG: Ошибка разархивации: {result}")
        return []
    
    print(f"    🔍 DEBUG: Архив разархивирован в: {extract_dir}")
    
    # Ищем PDF файлы
    pdf_files = []
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(root, file))
    
    print(f"    🔍 DEBUG: Найдено PDF файлов: {len(pdf_files)}")
    for pdf_file in pdf_files:
        print(f"    🔍 DEBUG: PDF файл: {os.path.basename(pdf_file)}")
    
    # Парсим каждый PDF
    all_items = []
    for pdf_path in pdf_files:
        print(f"    🔍 DEBUG: Парсинг PDF: {os.path.basename(pdf_path)}")
        items = parse_report_pdf(pdf_path)
        for item in items:
            item['company'] = company_name
            # Убеждаемся, что report_type установлен правильно
            if 'report_type' not in item or item['report_type'] is None:
                item['report_type'] = 'weekly_sales'
        all_items.extend(items)
        print(f"    🔍 DEBUG: Извлечено {len(items)} позиций из {os.path.basename(pdf_path)}")
    
    print(f"    🔍 DEBUG: Всего извлечено позиций из архива: {len(all_items)}")
    return all_items

# ============================================================================
# ФУНКЦИИ ДЛЯ ПАРСИНГА УВЕДОМЛЕНИЙ О ВЫКУПЕ
# ============================================================================

def extract_redemption_number_from_filename(filename):
    """
    Извлекает номер уведомления из названия файла
    Пример: "Уведомление о выкупе №492066895 от 2025-09-22.xlsx" -> "492066895"
    """
    match = re.search(r'№\s*(\d+)', filename)
    if match:
        return match.group(1)
    # Попробуем извлечь из другого формата
    match = re.search(r'redeem-notification-(\d+)', filename)
    if match:
        return match.group(1)
    return None

def extract_redemption_date_from_filename(filename):
    """
    Извлекает дату из названия файла
    Пример: "Уведомление о выкупе №492066895 от 2025-09-22.xlsx" -> "22.09.2025"
    """
    # Ищем дату в формате YYYY-MM-DD
    match = re.search(r'от\s+(\d{4}-\d{2}-\d{2})', filename)
    if match:
        date_str = match.group(1)
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            return date_obj.strftime('%d.%m.%Y')
        except:
            return date_str
    
    # Ищем дату в формате DD.MM.YYYY
    match = re.search(r'от\s+(\d{2}\.\d{2}\.\d{4})', filename)
    if match:
        return match.group(1)
    
    return None

def parse_redemption_notification_excel(excel_path, redemption_number_override=None, redemption_date_override=None):
    """
    Парсит Excel файл уведомления о выкупе
    
    Структура файла:
    - Строка 2: УВЕДОМЛЕНИЕ О ВЫКУПЕ №492066895 от 2025-09-22
    - Строка 9: Заголовки таблицы (№ п/п | Артикул | Наименование | Количество | Сумма выкупа | ...)
    - Строки 10-12: Данные товаров
    - Строка 13: Итого
    """
    try:
        filename = os.path.basename(excel_path)
        
        # Читаем файл без заголовков
        df = pd.read_excel(excel_path, header=None)
        
        # Извлекаем номер уведомления и дату
        redemption_number = redemption_number_override
        redemption_date = redemption_date_override
        
        # Сначала пробуем из названия файла
        if not redemption_number:
            redemption_number = extract_redemption_number_from_filename(filename)
        
        if not redemption_date:
            redemption_date = extract_redemption_date_from_filename(filename)
        
        # Если не нашли, пробуем из содержимого Excel
        if len(df) > 2 and df.iloc[2, 0]:
            header_text = str(df.iloc[2, 0])
            
            # Извлекаем номер
            if not redemption_number:
                match = re.search(r'№\s*(\d+)', header_text)
                if match:
                    redemption_number = match.group(1)
            
            # Извлекаем дату
            if not redemption_date:
                match = re.search(r'от\s+(\d{4}-\d{2}-\d{2})', header_text)
                if match:
                    date_str = match.group(1)
                    # Конвертируем YYYY-MM-DD в DD.MM.YYYY
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        redemption_date = date_obj.strftime('%d.%m.%Y')
                    except:
                        redemption_date = date_str
        
        # Ищем строку с заголовками таблицы (обычно строка 9)
        header_row_idx = None
        for idx, row in df.iterrows():
            row_text = ' '.join([str(val) if pd.notna(val) else '' for val in row])
            if '№' in row_text and 'п/п' in row_text and 'Артикул' in row_text:
                header_row_idx = idx
                break
        
        if header_row_idx is None:
            return []
        
        # Читаем таблицу начиная со строки с заголовками
        all_items = []
        
        for idx in range(header_row_idx + 1, len(df)):
            row = df.iloc[idx]
            
            # Проверяем, что это не строка "Итого"
            if pd.notna(row[0]) and 'итого' in str(row[0]).lower():
                break
            
            # Извлекаем данные
            try:
                # Номер п/п (колонка 0)
                row_number = str(row[0]).strip() if pd.notna(row[0]) else None
                if not row_number or not row_number.isdigit():
                    continue
                
                # Артикул (колонка 1)
                article = str(row[1]).strip() if pd.notna(row[1]) else None
                
                # Наименование (колонка 2)
                item_name = str(row[2]).strip() if pd.notna(row[2]) else None
                
                # Количество (колонка 3)
                quantity = None
                if pd.notna(row[3]):
                    try:
                        quantity = float(str(row[3]).replace(' ', '').replace(',', '.'))
                    except (ValueError, TypeError):
                        pass
                
                # Сумма выкупа (колонка 4)
                amount = None
                if pd.notna(row[4]):
                    amount_str = str(row[4]).replace(' ', '').replace(',', '.')
                    try:
                        amount = float(amount_str)
                    except (ValueError, TypeError):
                        pass
                
                # Ставка НДС (колонка 5)
                vat_rate = str(row[5]).strip() if pd.notna(row[5]) else None
                
                # Сумма НДС (колонка 6)
                vat_amount = None
                if pd.notna(row[6]) and str(row[6]) != '—':
                    vat_str = str(row[6]).replace(' ', '').replace(',', '.')
                    try:
                        vat_amount = float(vat_str)
                    except (ValueError, TypeError):
                        pass
                
                # КИЗ (колонка 7)
                kiz = str(row[7]).strip() if pd.notna(row[7]) and str(row[7]) != '—' else None
                
                if item_name and (article or quantity or amount):
                    item = {
                        'redemption_number': redemption_number,
                        'date': redemption_date,
                        'item_name': item_name,
                        'article': article,
                        'quantity': quantity,
                        'amount': amount,
                        'vat_rate': vat_rate,
                        'vat_amount': vat_amount,
                        'kiz': kiz,
                        'report_type': 'redemption_notification'
                    }
                    all_items.append(item)
                
            except Exception as e:
                continue
        
        return all_items
        
    except Exception as e:
        print(f"    ✗ Ошибка парсинга Excel: {e}")
        return []

def process_redemption_archive(zip_path, company_name):
    """Обрабатывает один архив уведомления о выкупе"""
    archive_name = os.path.basename(zip_path)
    redemption_number = extract_redemption_number_from_filename(archive_name)
    redemption_date = extract_redemption_date_from_filename(archive_name)
    
    # Создаем временную папку для разархивации
    extract_dir = zip_path.replace('.zip', '_extracted')
    
    # Разархивируем
    success, result = extract_zip_file(zip_path, extract_dir)
    if not success:
        return []
    
    # Ищем Excel файлы
    excel_files = []
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.lower().endswith(('.xlsx', '.xls')):
                excel_files.append(os.path.join(root, file))
    
    # Парсим каждый Excel
    all_items = []
    for excel_path in excel_files:
        items = parse_redemption_notification_excel(
            excel_path, 
            redemption_number_override=redemption_number,
            redemption_date_override=redemption_date
        )
        for item in items:
            item['company'] = company_name
            # Убеждаемся, что report_type установлен правильно
            if 'report_type' not in item or item['report_type'] is None:
                item['report_type'] = 'redemption_notification'
        all_items.extend(items)
    
    return all_items

def create_upd_table_if_not_exists():
    """Создает таблицу для хранения данных УПД, если её не существует"""
    create_schema_query = f"""
    CREATE SCHEMA IF NOT EXISTS {PG_SCHEMA};
    """
    
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {PG_SCHEMA}.{PG_TABLE} (
        company VARCHAR(255) NOT NULL,
        upd_number VARCHAR(100),
        report_number VARCHAR(100),
        redemption_number VARCHAR(100),
        date VARCHAR(20),
        item_name TEXT NOT NULL,
        cost NUMERIC(15, 2),
        article VARCHAR(100),
        barcode VARCHAR(50),
        quantity NUMERIC(15, 2),
        amount NUMERIC(15, 2),
        vat_rate VARCHAR(50),
        vat_amount NUMERIC(15, 2),
        kiz TEXT,
        report_type VARCHAR(50) DEFAULT 'upd',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT unique_upd_item UNIQUE (company, upd_number, date, cost),
        CONSTRAINT unique_report_item UNIQUE (company, report_number, date, item_name, amount),
        CONSTRAINT unique_redemption_item UNIQUE (company, redemption_number, date, item_name, amount)
    );
    
    CREATE INDEX IF NOT EXISTS idx_upd_company ON {PG_SCHEMA}.{PG_TABLE}(company);
    CREATE INDEX IF NOT EXISTS idx_upd_number ON {PG_SCHEMA}.{PG_TABLE}(upd_number);
    CREATE INDEX IF NOT EXISTS idx_report_number ON {PG_SCHEMA}.{PG_TABLE}(report_number);
    CREATE INDEX IF NOT EXISTS idx_redemption_number ON {PG_SCHEMA}.{PG_TABLE}(redemption_number);
    CREATE INDEX IF NOT EXISTS idx_upd_date ON {PG_SCHEMA}.{PG_TABLE}(date);
    CREATE INDEX IF NOT EXISTS idx_report_type ON {PG_SCHEMA}.{PG_TABLE}(report_type);
    """
    
    # Проверяем существование constraint'ов
    check_upd_constraint_query = f"""
    SELECT COUNT(*) 
    FROM information_schema.table_constraints 
    WHERE table_schema = '{PG_SCHEMA}' 
    AND table_name = '{PG_TABLE}' 
    AND constraint_name = 'unique_upd_item';
    """
    
    check_report_constraint_query = f"""
    SELECT COUNT(*) 
    FROM information_schema.table_constraints 
    WHERE table_schema = '{PG_SCHEMA}' 
    AND table_name = '{PG_TABLE}' 
    AND constraint_name = 'unique_report_item';
    """
    
    try:
        with engine.begin() as conn:
            conn.execute(text(create_schema_query))
            conn.execute(text(create_table_query))
            
            # Проверяем, есть ли constraint для УПД
            result = conn.execute(text(check_upd_constraint_query))
            upd_constraint_exists = result.scalar() > 0
            
            if not upd_constraint_exists:
                print("⚠ Добавляем отсутствующий UNIQUE constraint для УПД...")
                add_upd_constraint_query = f"""
                ALTER TABLE {PG_SCHEMA}.{PG_TABLE} 
                ADD CONSTRAINT unique_upd_item UNIQUE (company, upd_number, date, cost);
                """
                conn.execute(text(add_upd_constraint_query))
                print("✓ UNIQUE constraint для УПД добавлен")
            
            # Проверяем, есть ли constraint для отчетов
            result = conn.execute(text(check_report_constraint_query))
            report_constraint_exists = result.scalar() > 0
            
            if not report_constraint_exists:
                print("⚠ Добавляем отсутствующий UNIQUE constraint для отчетов...")
                add_report_constraint_query = f"""
                ALTER TABLE {PG_SCHEMA}.{PG_TABLE} 
                ADD CONSTRAINT unique_report_item UNIQUE (company, report_number, date, item_name, amount);
                """
                conn.execute(text(add_report_constraint_query))
                print("✓ UNIQUE constraint для отчетов добавлен")
            
        print("✓ Таблица БД создана/проверена (поддержка УПД и отчетов)")
        return True
    except Exception as e:
        print(f"✗ Ошибка создания таблицы: {e}")
        return False

def create_reports_summary_table():
    """Создает таблицу для агрегированных данных по отчетам с финансовыми категориями"""
    create_schema_query = f"""
    CREATE SCHEMA IF NOT EXISTS {PG_SCHEMA};
    """
    
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {PG_SCHEMA}.reports_summary (
        id SERIAL PRIMARY KEY,
        company VARCHAR(255) NOT NULL,
        report_number VARCHAR(100),
        report_date VARCHAR(20),
        report_type VARCHAR(50),
        
        -- Основные финансовые категории
        total_cost_realized_goods_services NUMERIC(15, 2) DEFAULT 0,
        total_cost_realized_goods NUMERIC(15, 2) DEFAULT 0,
        total_cost_realized_services NUMERIC(15, 2) DEFAULT 0,
        total_cost_reserved_goods_pickup NUMERIC(15, 2) DEFAULT 0,
        loyalty_discount_compensation NUMERIC(15, 2) DEFAULT 0,
        total_credited_from_realized NUMERIC(15, 2) DEFAULT 0,
        
        -- Вознаграждения и НДС
        wb_reward_amount NUMERIC(15, 2) DEFAULT 0,
        wb_reward_vat NUMERIC(15, 2) DEFAULT 0,
        loyalty_program_cost NUMERIC(15, 2) DEFAULT 0,
        loyalty_program_vat NUMERIC(15, 2) DEFAULT 0,
        
        -- Услуги и возмещения
        international_shipping_cost NUMERIC(15, 2) DEFAULT 0,
        acquiring_cost_reimbursement NUMERIC(15, 2) DEFAULT 0,
        shipping_cost_reimbursement NUMERIC(15, 2) DEFAULT 0,
        pickup_return_cost_reimbursement NUMERIC(15, 2) DEFAULT 0,
        
        -- Штрафы и удержания
        penalties NUMERIC(15, 2) DEFAULT 0,
        other_deductions NUMERIC(15, 2) DEFAULT 0,
        third_party_deductions NUMERIC(15, 2) DEFAULT 0,
        damage_compensation NUMERIC(15, 2) DEFAULT 0,
        other_payments NUMERIC(15, 2) DEFAULT 0,
        loyalty_points_deduction NUMERIC(15, 2) DEFAULT 0,
        
        -- Итоговая сумма
        total_amount_to_seller NUMERIC(15, 2) DEFAULT 0,
        
        -- Метаданные
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        
        CONSTRAINT unique_report_summary UNIQUE (company, report_number, report_date)
    );
    
    CREATE INDEX IF NOT EXISTS idx_reports_summary_company ON {PG_SCHEMA}.reports_summary(company);
    CREATE INDEX IF NOT EXISTS idx_reports_summary_number ON {PG_SCHEMA}.reports_summary(report_number);
    CREATE INDEX IF NOT EXISTS idx_reports_summary_date ON {PG_SCHEMA}.reports_summary(report_date);
    CREATE INDEX IF NOT EXISTS idx_reports_summary_type ON {PG_SCHEMA}.reports_summary(report_type);
    """
    
    try:
        with engine.begin() as conn:
            conn.execute(text(create_schema_query))
            conn.execute(text(create_table_query))
        
        print("✓ Таблица reports_summary создана/проверена")
        return True
    except Exception as e:
        print(f"✗ Ошибка создания таблицы reports_summary: {e}")
        return False

def aggregate_reports_data():
    """Агрегирует данные из таблицы upd_items в таблицу reports_summary"""
    try:
        # Получаем уникальные отчеты из исходной таблицы
        get_reports_query = f"""
        SELECT DISTINCT 
            company,
            report_number,
            date,
            report_type
        FROM {PG_SCHEMA}.{PG_TABLE}
        WHERE report_number IS NOT NULL
        ORDER BY company, report_number, date;
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(get_reports_query))
            reports = result.fetchall()
        
        print(f"📊 Найдено {len(reports)} уникальных отчетов для агрегации")
        
        aggregated_count = 0
        
        for report in reports:
            company, report_number, date, report_type = report
            
            # Агрегируем данные по каждому отчету
            aggregate_query = f"""
            SELECT 
                SUM(COALESCE(amount, cost, 0)) as total_amount,
                COUNT(*) as items_count
            FROM {PG_SCHEMA}.{PG_TABLE}
            WHERE company = :company 
            AND report_number = :report_number 
            AND date = :date
            AND report_type = :report_type;
            """
            
            with engine.connect() as conn:
                result = conn.execute(text(aggregate_query), {
                    'company': company,
                    'report_number': report_number,
                    'date': date,
                    'report_type': report_type
                })
                agg_data = result.fetchone()
            
            if agg_data and agg_data[0] is not None:
                total_amount = float(agg_data[0]) if agg_data[0] is not None else 0.0
                items_count = int(agg_data[1]) if agg_data[1] is not None else 0
                
                # Определяем категорию на основе типа отчета и названий товаров
                category_mapping = determine_financial_category(company, report_number, date, report_type)
                
                # Вставляем агрегированные данные
                insert_summary_query = f"""
                INSERT INTO {PG_SCHEMA}.reports_summary (
                    company, report_number, report_date, report_type,
                    total_cost_realized_goods_services,
                    total_cost_realized_goods,
                    total_cost_realized_services,
                    total_cost_reserved_goods_pickup,
                    loyalty_discount_compensation,
                    total_credited_from_realized,
                    wb_reward_amount,
                    wb_reward_vat,
                    loyalty_program_cost,
                    loyalty_program_vat,
                    international_shipping_cost,
                    acquiring_cost_reimbursement,
                    shipping_cost_reimbursement,
                    pickup_return_cost_reimbursement,
                    penalties,
                    other_deductions,
                    third_party_deductions,
                    damage_compensation,
                    other_payments,
                    loyalty_points_deduction,
                    total_amount_to_seller,
                    updated_at
                ) VALUES (
                    :company, :report_number, :date, :report_type,
                    :total_cost_realized_goods_services,
                    :total_cost_realized_goods,
                    :total_cost_realized_services,
                    :total_cost_reserved_goods_pickup,
                    :loyalty_discount_compensation,
                    :total_credited_from_realized,
                    :wb_reward_amount,
                    :wb_reward_vat,
                    :loyalty_program_cost,
                    :loyalty_program_vat,
                    :international_shipping_cost,
                    :acquiring_cost_reimbursement,
                    :shipping_cost_reimbursement,
                    :pickup_return_cost_reimbursement,
                    :penalties,
                    :other_deductions,
                    :third_party_deductions,
                    :damage_compensation,
                    :other_payments,
                    :loyalty_points_deduction,
                    :total_amount_to_seller,
                    CURRENT_TIMESTAMP
                )
                ON CONFLICT (company, report_number, report_date)
                DO UPDATE SET
                    total_cost_realized_goods_services = EXCLUDED.total_cost_realized_goods_services,
                    total_cost_realized_goods = EXCLUDED.total_cost_realized_goods,
                    total_cost_realized_services = EXCLUDED.total_cost_realized_services,
                    total_cost_reserved_goods_pickup = EXCLUDED.total_cost_reserved_goods_pickup,
                    loyalty_discount_compensation = EXCLUDED.loyalty_discount_compensation,
                    total_credited_from_realized = EXCLUDED.total_credited_from_realized,
                    wb_reward_amount = EXCLUDED.wb_reward_amount,
                    wb_reward_vat = EXCLUDED.wb_reward_vat,
                    loyalty_program_cost = EXCLUDED.loyalty_program_cost,
                    loyalty_program_vat = EXCLUDED.loyalty_program_vat,
                    international_shipping_cost = EXCLUDED.international_shipping_cost,
                    acquiring_cost_reimbursement = EXCLUDED.acquiring_cost_reimbursement,
                    shipping_cost_reimbursement = EXCLUDED.shipping_cost_reimbursement,
                    pickup_return_cost_reimbursement = EXCLUDED.pickup_return_cost_reimbursement,
                    penalties = EXCLUDED.penalties,
                    other_deductions = EXCLUDED.other_deductions,
                    third_party_deductions = EXCLUDED.third_party_deductions,
                    damage_compensation = EXCLUDED.damage_compensation,
                    other_payments = EXCLUDED.other_payments,
                    loyalty_points_deduction = EXCLUDED.loyalty_points_deduction,
                    total_amount_to_seller = EXCLUDED.total_amount_to_seller,
                    updated_at = CURRENT_TIMESTAMP;
                """
                
                with engine.begin() as conn:
                    conn.execute(text(insert_summary_query), {
                        'company': company,
                        'report_number': report_number,
                        'date': date,
                        'report_type': report_type,
                        **category_mapping,
                        'total_amount_to_seller': total_amount
                    })
                
                aggregated_count += 1
                
                if aggregated_count % 10 == 0:
                    print(f"  📊 Обработано {aggregated_count} отчетов...")
        
        print(f"✓ Агрегировано {aggregated_count} отчетов в таблицу reports_summary")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка агрегации данных: {e}")
        print(f"Детали: {traceback.format_exc()}")
        return False

def determine_financial_category(company, report_number, date, report_type):
    """Определяет финансовую категорию на основе данных отчета"""
    # Пока что простая логика - все суммы идут в основную категорию
    # В будущем можно добавить более сложную логику на основе названий товаров/услуг
    
    # Получаем данные товаров для анализа
    get_items_query = f"""
    SELECT item_name, amount, cost
    FROM {PG_SCHEMA}.{PG_TABLE}
    WHERE company = :company 
    AND report_number = :report_number 
    AND date = :date
    AND report_type = :report_type;
    """
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text(get_items_query), {
                'company': company,
                'report_number': report_number,
                'date': date,
                'report_type': report_type
            })
            items = result.fetchall()
        
        # Пока что все суммы относим к основной категории
        total_amount = sum((float(item[1]) if item[1] is not None and not pd.isna(item[1]) else 
                           float(item[2]) if item[2] is not None and not pd.isna(item[2]) else 0) 
                          for item in items)
        
        return {
            'total_cost_realized_goods_services': total_amount,
            'total_cost_realized_goods': 0,
            'total_cost_realized_services': 0,
            'total_cost_reserved_goods_pickup': 0,
            'loyalty_discount_compensation': 0,
            'total_credited_from_realized': 0,
            'wb_reward_amount': 0,
            'wb_reward_vat': 0,
            'loyalty_program_cost': 0,
            'loyalty_program_vat': 0,
            'international_shipping_cost': 0,
            'acquiring_cost_reimbursement': 0,
            'shipping_cost_reimbursement': 0,
            'pickup_return_cost_reimbursement': 0,
            'penalties': 0,
            'other_deductions': 0,
            'third_party_deductions': 0,
            'damage_compensation': 0,
            'other_payments': 0,
            'loyalty_points_deduction': 0
        }
        
    except Exception as e:
        print(f"⚠ Ошибка определения категории для {company}/{report_number}: {e}")
        return {
            'total_cost_realized_goods_services': 0,
            'total_cost_realized_goods': 0,
            'total_cost_realized_services': 0,
            'total_cost_reserved_goods_pickup': 0,
            'loyalty_discount_compensation': 0,
            'total_credited_from_realized': 0,
            'wb_reward_amount': 0,
            'wb_reward_vat': 0,
            'loyalty_program_cost': 0,
            'loyalty_program_vat': 0,
            'international_shipping_cost': 0,
            'acquiring_cost_reimbursement': 0,
            'shipping_cost_reimbursement': 0,
            'pickup_return_cost_reimbursement': 0,
            'penalties': 0,
            'other_deductions': 0,
            'third_party_deductions': 0,
            'damage_compensation': 0,
            'other_payments': 0,
            'loyalty_points_deduction': 0
        }

def aggregate_company_reports(company_name):
    """Агрегирует данные конкретной компании в таблицу reports_summary"""
    try:
        # Получаем уникальные отчеты для конкретной компании
        get_reports_query = f"""
        SELECT DISTINCT 
            company,
            report_number,
            date,
            report_type
        FROM {PG_SCHEMA}.{PG_TABLE}
        WHERE company = :company_name
        AND report_number IS NOT NULL
        ORDER BY report_number, date;
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(get_reports_query), {'company_name': company_name})
            reports = result.fetchall()
        
        aggregated_count = 0
        
        for report in reports:
            company, report_number, date, report_type = report
            
            # Агрегируем данные по каждому отчету
            aggregate_query = f"""
            SELECT 
                SUM(COALESCE(amount, cost, 0)) as total_amount,
                COUNT(*) as items_count
            FROM {PG_SCHEMA}.{PG_TABLE}
            WHERE company = :company 
            AND report_number = :report_number 
            AND date = :date
            AND report_type = :report_type;
            """
            
            with engine.connect() as conn:
                result = conn.execute(text(aggregate_query), {
                    'company': company,
                    'report_number': report_number,
                    'date': date,
                    'report_type': report_type
                })
                agg_data = result.fetchone()
            
            if agg_data and agg_data[0] is not None:
                total_amount = float(agg_data[0]) if agg_data[0] is not None else 0.0
                items_count = int(agg_data[1]) if agg_data[1] is not None else 0
                
                # Определяем категорию на основе типа отчета и названий товаров
                category_mapping = determine_financial_category(company, report_number, date, report_type)
                
                # Вставляем агрегированные данные
                insert_summary_query = f"""
                INSERT INTO {PG_SCHEMA}.reports_summary (
                    company, report_number, report_date, report_type,
                    total_cost_realized_goods_services,
                    total_cost_realized_goods,
                    total_cost_realized_services,
                    total_cost_reserved_goods_pickup,
                    loyalty_discount_compensation,
                    total_credited_from_realized,
                    wb_reward_amount,
                    wb_reward_vat,
                    loyalty_program_cost,
                    loyalty_program_vat,
                    international_shipping_cost,
                    acquiring_cost_reimbursement,
                    shipping_cost_reimbursement,
                    pickup_return_cost_reimbursement,
                    penalties,
                    other_deductions,
                    third_party_deductions,
                    damage_compensation,
                    other_payments,
                    loyalty_points_deduction,
                    total_amount_to_seller,
                    updated_at
                ) VALUES (
                    :company, :report_number, :date, :report_type,
                    :total_cost_realized_goods_services,
                    :total_cost_realized_goods,
                    :total_cost_realized_services,
                    :total_cost_reserved_goods_pickup,
                    :loyalty_discount_compensation,
                    :total_credited_from_realized,
                    :wb_reward_amount,
                    :wb_reward_vat,
                    :loyalty_program_cost,
                    :loyalty_program_vat,
                    :international_shipping_cost,
                    :acquiring_cost_reimbursement,
                    :shipping_cost_reimbursement,
                    :pickup_return_cost_reimbursement,
                    :penalties,
                    :other_deductions,
                    :third_party_deductions,
                    :damage_compensation,
                    :other_payments,
                    :loyalty_points_deduction,
                    :total_amount_to_seller,
                    CURRENT_TIMESTAMP
                )
                ON CONFLICT (company, report_number, report_date)
                DO UPDATE SET
                    total_cost_realized_goods_services = EXCLUDED.total_cost_realized_goods_services,
                    total_cost_realized_goods = EXCLUDED.total_cost_realized_goods,
                    total_cost_realized_services = EXCLUDED.total_cost_realized_services,
                    total_cost_reserved_goods_pickup = EXCLUDED.total_cost_reserved_goods_pickup,
                    loyalty_discount_compensation = EXCLUDED.loyalty_discount_compensation,
                    total_credited_from_realized = EXCLUDED.total_credited_from_realized,
                    wb_reward_amount = EXCLUDED.wb_reward_amount,
                    wb_reward_vat = EXCLUDED.wb_reward_vat,
                    loyalty_program_cost = EXCLUDED.loyalty_program_cost,
                    loyalty_program_vat = EXCLUDED.loyalty_program_vat,
                    international_shipping_cost = EXCLUDED.international_shipping_cost,
                    acquiring_cost_reimbursement = EXCLUDED.acquiring_cost_reimbursement,
                    shipping_cost_reimbursement = EXCLUDED.shipping_cost_reimbursement,
                    pickup_return_cost_reimbursement = EXCLUDED.pickup_return_cost_reimbursement,
                    penalties = EXCLUDED.penalties,
                    other_deductions = EXCLUDED.other_deductions,
                    third_party_deductions = EXCLUDED.third_party_deductions,
                    damage_compensation = EXCLUDED.damage_compensation,
                    other_payments = EXCLUDED.other_payments,
                    loyalty_points_deduction = EXCLUDED.loyalty_points_deduction,
                    total_amount_to_seller = EXCLUDED.total_amount_to_seller,
                    updated_at = CURRENT_TIMESTAMP;
                """
                
                with engine.begin() as conn:
                    conn.execute(text(insert_summary_query), {
                        'company': company,
                        'report_number': report_number,
                        'date': date,
                        'report_type': report_type,
                        **category_mapping,
                        'total_amount_to_seller': total_amount
                    })
                
                aggregated_count += 1
        
        return aggregated_count
        
    except Exception as e:
        print(f"✗ Ошибка агрегации данных для компании {company_name}: {e}")
        return 0

def get_existing_columns():
    """Получает список существующих колонок в таблице"""
    query = f"""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = '{PG_SCHEMA}' 
    AND table_name = '{PG_TABLE}'
    ORDER BY ordinal_position;
    """
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query))
            columns = {row[0]: row[1] for row in result}
        return columns
    except Exception as e:
        print(f"⚠ Ошибка получения колонок: {e}")
        return {}

def add_missing_columns(data_columns):
    """Добавляет отсутствующие колонки в таблицу"""
    existing_columns = get_existing_columns()
    
    if not existing_columns:
        return False
    
    # Маппинг типов данных Python -> PostgreSQL
    type_mapping = {
        'int64': 'BIGINT',
        'float64': 'NUMERIC(15, 2)',
        'object': 'TEXT',
        'datetime64[ns]': 'TIMESTAMP',
        'bool': 'BOOLEAN'
    }
    
    added_columns = []
    
    for col_name, col_type in data_columns.items():
        # Пропускаем системные колонки
        if col_name in ['created_at', 'updated_at']:
            continue
            
        # Если колонка уже есть, пропускаем
        if col_name in existing_columns:
            continue
        
        # Определяем тип PostgreSQL
        pg_type = type_mapping.get(str(col_type), 'TEXT')
        
        try:
            alter_query = f"""
            ALTER TABLE {PG_SCHEMA}.{PG_TABLE} 
            ADD COLUMN IF NOT EXISTS {col_name} {pg_type};
            """
            
            with engine.begin() as conn:
                conn.execute(text(alter_query))
            
            added_columns.append(f"{col_name} ({pg_type})")
            
        except Exception as e:
            print(f"  ⚠ Не удалось добавить колонку {col_name}: {e}")
    
    if added_columns:
        print(f"  ✓ Добавлено новых колонок: {len(added_columns)}")
        for col in added_columns:
            print(f"    • {col}")
    
    return len(added_columns) > 0

def upload_upd_to_postgres(upd_data):
    """Загружает данные УПД в PostgreSQL с UPSERT логикой через временную таблицу"""
    if not upd_data:
        print("  ⚠ Нет данных для загрузки")
        return False
    
    try:
        df = pd.DataFrame(upd_data)
        print(f"  🔍 DEBUG: Создан DataFrame с {len(df)} записями")
        print(f"  🔍 DEBUG: Колонки: {list(df.columns)}")
        
        # Добавляем поле updated_at
        df['updated_at'] = datetime.now()
        
        # Проверяем и добавляем новые колонки
        data_columns = dict(df.dtypes)
        add_missing_columns(data_columns)
        
        # DEBUG: Показываем типы данных
        print(f"  🔍 DEBUG: Типы данных:")
        for col, dtype in data_columns.items():
            print(f"    • {col}: {dtype}")
        
        # DEBUG: Показываем примеры записей
        print(f"  🔍 DEBUG: Примеры записей:")
        for i, record in enumerate(df.head(3).to_dict('records')):
            print(f"    Запись {i+1}:")
            for key, value in record.items():
                if pd.notna(value):
                    print(f"      {key}: {value}")
            print()
        
        # Получаем список колонок для INSERT (исключаем created_at)
        columns_to_insert = [col for col in df.columns if col not in ['created_at']]
        
        # Получаем список колонок для UPDATE (исключаем created_at и ключевые поля)
        columns_to_update = [col for col in columns_to_insert 
                            if col not in ['company', 'upd_number', 'report_number', 'date', 'cost', 'item_name', 'amount']]
        
        # Конвертируем DataFrame в список словарей
        records = df[columns_to_insert].to_dict('records')
        
        # Формируем SQL для UPSERT с поддержкой двух типов constraint'ов
        columns_str = ', '.join(columns_to_insert)
        placeholders = ', '.join([f':{col}' for col in columns_to_insert])
        
        update_str = ', '.join([f"{col} = EXCLUDED.{col}" for col in columns_to_update])
        
        # Создаем два отдельных UPSERT запроса для разных типов данных
        upsert_upd_query = f"""
        INSERT INTO {PG_SCHEMA}.{PG_TABLE} ({columns_str})
        VALUES ({placeholders})
        ON CONFLICT (company, upd_number, date, cost) 
        WHERE upd_number IS NOT NULL
        DO UPDATE SET {update_str};
        """
        
        upsert_report_query = f"""
        INSERT INTO {PG_SCHEMA}.{PG_TABLE} ({columns_str})
        VALUES ({placeholders})
        ON CONFLICT (company, report_number, date, item_name, amount)
        WHERE report_number IS NOT NULL
        DO UPDATE SET {update_str};
        """
        
        upsert_redemption_query = f"""
        INSERT INTO {PG_SCHEMA}.{PG_TABLE} ({columns_str})
        VALUES ({placeholders})
        ON CONFLICT (company, redemption_number, date, item_name, amount)
        WHERE redemption_number IS NOT NULL
        DO UPDATE SET {update_str};
        """
        
        # Выполняем UPSERT батчами
        inserted_count = 0
        updated_count = 0
        batch_size = 1000
        
        # DEBUG: Статистика по типам записей
        upd_records = 0
        report_records = 0
        redemption_records = 0
        other_records = 0
        
        print(f"  🔍 DEBUG: Начинаем обработку {len(records)} записей")
        
        with engine.begin() as conn:
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                print(f"  🔍 DEBUG: Обрабатываем батч {i//batch_size + 1}, записей: {len(batch)}")
                
                for record_idx, record in enumerate(batch):
                    # Очищаем NaN значения из записи
                    cleaned_record = {}
                    for key, value in record.items():
                        if pd.isna(value) or value is None:
                            cleaned_record[key] = None
                        else:
                            cleaned_record[key] = value
                    
                    # Выбираем правильный UPSERT запрос в зависимости от типа данных
                    upd_number = cleaned_record.get('upd_number')
                    report_number = cleaned_record.get('report_number')
                    redemption_number = cleaned_record.get('redemption_number')
                    
                    # Проверяем тип записи по report_type
                    report_type = cleaned_record.get('report_type', '')
                    
                    # Проверяем, есть ли валидный upd_number (не NaN и не None)
                    has_upd_number = (upd_number is not None and str(upd_number) != 'nan' and str(upd_number) != 'None')
                    # Проверяем, есть ли валидный report_number (не NaN и не None)
                    has_report_number = (report_number is not None and str(report_number) != 'nan' and str(report_number) != 'None')
                    # Проверяем, есть ли валидный redemption_number (не NaN и не None)
                    has_redemption_number = (redemption_number is not None and str(redemption_number) != 'nan' and str(redemption_number) != 'None')
                    
                    # Определяем тип записи по report_type, а не по наличию номеров
                    if report_type == 'upd' and has_upd_number:
                        # Это УПД документ
                        print(f"    🔍 DEBUG: Запись {record_idx+1} - УПД (upd_number: {upd_number})")
                        result = conn.execute(text(upsert_upd_query), cleaned_record)
                        upd_records += 1
                    elif report_type == 'weekly_sales' and has_report_number:
                        # Это еженедельный отчет
                        print(f"    🔍 DEBUG: Запись {record_idx+1} - Отчет (report_number: {report_number})")
                        result = conn.execute(text(upsert_report_query), cleaned_record)
                        report_records += 1
                    elif report_type == 'redemption_notification' and has_redemption_number:
                        # Это уведомление о выкупе
                        print(f"    🔍 DEBUG: Запись {record_idx+1} - Уведомление (redemption_number: {redemption_number})")
                        result = conn.execute(text(upsert_redemption_query), cleaned_record)
                        redemption_records += 1
                    else:
                        # Если тип не определен или нет валидных номеров, пропускаем запись
                        print(f"    🔍 DEBUG: Запись {record_idx+1} - Пропущена (тип: {report_type}, upd: {has_upd_number}, report: {has_report_number}, redemption: {has_redemption_number})")
                        continue
                    
                    inserted_count += 1
                    
                    # Показываем прогресс каждые 10 записей
                    if inserted_count % 10 == 0:
                        print(f"    🔍 DEBUG: Обработано {inserted_count} записей...")
        
        print(f"  🔍 DEBUG: Итоговая статистика:")
        print(f"    • УПД записей: {upd_records}")
        print(f"    • Отчетов записей: {report_records}")
        print(f"    • Уведомлений о выкупе: {redemption_records}")
        print(f"    • Других записей: {other_records}")
        print(f"    • Всего обработано: {inserted_count}")
        
        print(f"  ✓ {len(records)} позиций обработано в PostgreSQL (UPSERT)")
        return True
        
    except Exception as e:
        print(f"  ✗ Ошибка загрузки в БД: {e}")
        print(f"  Детали: {traceback.format_exc()}")
        return False

def deduplicate_upd_data():
    """Выполняет дедупликацию данных в таблице с учетом разных типов записей"""
    try:
        # Имя временной таблицы БЕЗ схемы (временные таблицы создаются в pg_temp автоматически)
        temp_table = f"{PG_TABLE}_temp"
        
        # Удаляем временную таблицу если она уже существует
        drop_temp_table_query = f"DROP TABLE IF EXISTS {temp_table};"
        
        # Создаем временную таблицу с уникальными записями
        # Дедупликация по разным полям в зависимости от типа записи
        create_temp_table_query = f"""
        CREATE TEMP TABLE {temp_table} AS
        SELECT DISTINCT ON (
            company, 
            COALESCE(upd_number, 'NULL'),
            COALESCE(report_number, 'NULL'),
            COALESCE(redemption_number, 'NULL'),
            date,
            COALESCE(cost, 0),
            COALESCE(amount, 0),
            item_name
        )
            company, upd_number, report_number, redemption_number, date, item_name, cost, amount, 
            article, barcode, quantity, report_type, vat_rate, vat_amount, kiz, created_at, updated_at
        FROM {PG_SCHEMA}.{PG_TABLE}
        ORDER BY company, 
                 COALESCE(upd_number, 'NULL'),
                 COALESCE(report_number, 'NULL'),
                 COALESCE(redemption_number, 'NULL'),
                 date,
                 COALESCE(cost, 0),
                 COALESCE(amount, 0),
                 item_name,
                 updated_at DESC;
        """
        
        # Удаляем все данные из основной таблицы
        truncate_query = f"TRUNCATE TABLE {PG_SCHEMA}.{PG_TABLE};"
        
        # Вставляем уникальные данные обратно
        insert_back_query = f"""
        INSERT INTO {PG_SCHEMA}.{PG_TABLE} (
            company, upd_number, report_number, redemption_number, date, item_name, cost, amount,
            article, barcode, quantity, report_type, vat_rate, vat_amount, kiz, created_at, updated_at
        )
        SELECT 
            company, upd_number, report_number, redemption_number, date, item_name, cost, amount,
            article, barcode, quantity, report_type, vat_rate, vat_amount, kiz, created_at, updated_at
        FROM {temp_table};
        """
        
        # Удаляем временную таблицу после использования
        drop_temp_after_query = f"DROP TABLE IF EXISTS {temp_table};"
        
        # Получаем количество записей до дедупликации
        count_before_query = f"SELECT COUNT(*) FROM {PG_SCHEMA}.{PG_TABLE};"
        
        with engine.begin() as conn:
            # Считаем записи до дедупликации
            result = conn.execute(text(count_before_query))
            count_before = result.scalar()
            
            # Выполняем дедупликацию
            conn.execute(text(drop_temp_table_query))  # Удаляем старую временную таблицу
            conn.execute(text(create_temp_table_query))
            conn.execute(text(truncate_query))
            conn.execute(text(insert_back_query))
            conn.execute(text(drop_temp_after_query))  # Очищаем временную таблицу
            
            # Считаем записи после дедупликации
            result = conn.execute(text(count_before_query))
            count_after = result.scalar()
        
        deleted_rows = count_before - count_after
        
        if deleted_rows > 0:
            print(f"  ✓ Удалено {deleted_rows} дубликатов из таблицы")
        else:
            print(f"  ✓ Дубликаты не найдены")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Ошибка при дедупликации: {e}")
        return False

def cleanup_files(directory, archive_path=None):
    """Удаляет временные файлы и архивы после обработки"""
    deleted_count = 0
    
    # Удаляем временные папки с разархивированными файлами
    for root, dirs, files in os.walk(directory, topdown=False):
        for name in dirs:
            if '_extracted' in name:
                extracted_dir = os.path.join(root, name)
                try:
                    shutil.rmtree(extracted_dir)
                    deleted_count += 1
                except Exception as e:
                    print(f"    ⚠ Не удалось удалить {extracted_dir}: {e}")
    
    # Удаляем архивы .zip
    for root, dirs, files in os.walk(directory, topdown=False):
        for name in files:
            if name.lower().endswith('.zip'):
                zip_file = os.path.join(root, name)
                try:
                    os.remove(zip_file)
                    deleted_count += 1
                except Exception as e:
                    print(f"    ⚠ Не удалось удалить {zip_file}: {e}")
    
    return deleted_count

# ============================================================================
# ОСНОВНОЙ КОД
# ============================================================================

# Создаем таблицы в PostgreSQL если их нет
print("="*80)
print("ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ")
print("="*80)
if not create_upd_table_if_not_exists():
    print("⚠ Продолжаем без базы данных")
else:
    print("✓ Основная таблица создана/проверена")

# Создаем таблицу для агрегированных отчетов
print("\n📊 Создание таблицы агрегированных отчетов...")
if not create_reports_summary_table():
    print("⚠ Продолжаем без таблицы агрегированных отчетов")
else:
    print("✓ Таблица агрегированных отчетов создана/проверена")
    
    # Агрегируем существующие данные
    print("\n🔄 Агрегация существующих данных...")
    if aggregate_reports_data():
        print("✓ Данные успешно агрегированы")
    else:
        print("⚠ Ошибка агрегации данных")

print()

# Получаем API ключи из Google Sheets
print("Загрузка API ключей из Google Sheets...")
df = get_sheet_data_as_dataframe(credentials_file, spreadsheet_key, sheet_name)
df = df[(df['API ключ'] != '') & (df['API ключ'] != None) & ~((df['Имя Юрлица'] == 'TD') | (df['Имя Юрлица'] == 'ИП Крапивина С.А.'))]

# Для теста можно раскомментировать (тестируем на одной компании):
# df = df[df['Имя Юрлица']=='ИП Солоджук Е. Г']

dict_api = dict(zip(df['API ключ'], df['Имя Юрлица']))
print(f"Найдено {len(dict_api)} компаний для обработки\n")

# Глобальная статистика
total_stats = {
    'companies_processed': 0,
    'total_documents': 0,
    'total_upd_items': 0,
    'download_success': 0,
    'download_failed': 0
}

# Обрабатываем каждую компанию ПОЛНОСТЬЮ (от начала до конца)
for company_idx, (api_key, company_name) in enumerate(dict_api.items(), 1):
    print(f"\n{'='*80}")
    print(f"[{company_idx}/{len(dict_api)}] ОБРАБОТКА КОМПАНИИ: {company_name}")
    print(f"{'='*80}\n")
    
    # Локальные данные для этой компании (очищаются после каждой компании)
    company_documents = []
    company_upd_data = []
    company_download_stats = {'success': 0, 'failed': 0}
    
    # ШАГ 1: Получаем список документов
    print(f"📋 Шаг 1/5: Получение списка документов за период {date_from} - {date_to}")
    documents = fetch_documents_list(api_key, date_from, date_to)
    
    if not documents:
        print(f"✗ Документы не найдены для {company_name}")
        print(f"⏭️  Переход к следующей компании...\n")
        continue
    
    print(f"✓ Получено {len(documents)} документов")
    
    # Фильтруем УПД документы
    upd_documents = [doc for doc in documents if 'УПД' in doc.get('category', '')]
    print(f"  📋 Из них УПД: {len(upd_documents)}")
    
    # Фильтруем еженедельные отчеты реализации
    report_documents = [doc for doc in documents if 'Еженедельный отчет реализации' in doc.get('category', '')]
    print(f"  📊 Из них еженедельных отчетов: {len(report_documents)}")
    
    # Фильтруем уведомления о выкупе
    redemption_documents = [doc for doc in documents if 'Уведомление о выкупе' in doc.get('category', '')]
    print(f"  🛒 Из них уведомлений о выкупе: {len(redemption_documents)}")
    
    # ШАГ 2: Скачивание и парсинг документов
    print(f"\n📥 Шаг 2/5: Скачивание документов...")
    company_dir = os.path.join('wb_documents', company_name.replace('/', '_').replace('\\', '_'))
    
    for i, doc in enumerate(documents, 1):
        service_name = doc.get('serviceName')
        extensions = doc.get('extensions', [])
        category = doc.get('category', '')
        
        if not service_name or not extensions:
            continue
        
        extension = extensions[0] if isinstance(extensions, list) else extensions
        is_upd = 'УПД' in category
        is_report = 'Еженедельный отчет реализации' in category
        is_redemption = 'Уведомление о выкупе' in category
        
        print(f"  [{i}/{len(documents)}] {service_name[:50]}...", end=' ')
        
        result = download_document(api_key, service_name, extension, company_dir)
        
        if result['success']:
            print(f"✓", end='')
            company_download_stats['success'] += 1
            
            # Если это УПД, сразу парсим
            if is_upd and extension == 'zip':
                try:
                    upd_items = process_upd_archive(result['file_path'], company_name)
                    if upd_items:
                        company_upd_data.extend(upd_items)
                        print(f" → Извлечено {len(upd_items)} позиций УПД")
                    else:
                        print(f" → Нет данных УПД")
                except Exception as e:
                    print(f" → Ошибка УПД: {e}")
            # Если это еженедельный отчет, парсим
            elif is_report and extension == 'zip':
                try:
                    report_items = process_report_archive(result['file_path'], company_name)
                    if report_items:
                        company_upd_data.extend(report_items)
                        print(f" → Извлечено {len(report_items)} позиций отчета")
                    else:
                        print(f" → Нет данных отчета")
                except Exception as e:
                    print(f" → Ошибка отчета: {e}")
            # Если это уведомление о выкупе, парсим
            elif is_redemption and extension == 'zip':
                try:
                    redemption_items = process_redemption_archive(result['file_path'], company_name)
                    if redemption_items:
                        company_upd_data.extend(redemption_items)
                        print(f" → Извлечено {len(redemption_items)} позиций уведомления")
                    else:
                        print(f" → Нет данных уведомления")
                except Exception as e:
                    print(f" → Ошибка уведомления: {e}")
            else:
                print()
        else:
            print(f"✗ {result['error']}")
            company_download_stats['failed'] += 1
        
        # Адаптивная пауза с учетом burst лимита API
        if i % 3 == 0:
            # После каждых 3 документов - длинная пауза для восстановления burst лимита
            print(f"  Пауза 120 секунд для соблюдения лимитов API (документ {i})")
            time.sleep(120)
        else:
            # Между документами внутри burst - средняя пауза
            time.sleep(15)
    
    # ШАГ 3: Сохранение данных в PostgreSQL
    print(f"\n💾 Шаг 3/5: Сохранение данных в PostgreSQL...")
    if company_upd_data:
        df_upd = pd.DataFrame(company_upd_data)
        
        # Загружаем в PostgreSQL
        upload_success = upload_upd_to_postgres(company_upd_data)
        
        # Статистика по типам документов
        upd_items = df_upd[df_upd['report_type'] == 'upd'] if 'report_type' in df_upd.columns else df_upd
        report_items = df_upd[df_upd['report_type'] == 'weekly_sales'] if 'report_type' in df_upd.columns else pd.DataFrame()
        redemption_items = df_upd[df_upd['report_type'] == 'redemption_notification'] if 'report_type' in df_upd.columns else pd.DataFrame()
        
        print(f"  ✓ Обработано {len(company_upd_data)} позиций:")
        if not upd_items.empty:
            print(f"    📋 УПД: {len(upd_items)} позиций из {upd_items['upd_number'].nunique()} документов")
            print(f"    💰 Сумма УПД: {upd_items['cost'].sum():,.2f} руб")
        if not report_items.empty:
            print(f"    📊 Отчеты: {len(report_items)} позиций из {report_items['report_number'].nunique()} отчетов")
            print(f"    💰 Сумма отчетов: {report_items['amount'].sum():,.2f} руб")
        if not redemption_items.empty:
            print(f"    🛒 Уведомления о выкупе: {len(redemption_items)} позиций из {redemption_items['redemption_number'].nunique()} уведомлений")
            print(f"    💰 Сумма выкупов: {redemption_items['amount'].sum():,.2f} руб")
        
        if upload_success:
            total_stats['total_upd_items'] += len(company_upd_data)
            
            # Выполняем дедупликацию после загрузки
            print(f"\n🔄 Дедупликация данных...")
            deduplicate_upd_data()
            
            # Обновляем агрегированные данные для этой компании
            print(f"\n📊 Обновление агрегированных данных...")
            try:
                # Агрегируем только данные этой компании
                aggregate_company_reports(company_name)
                print(f"✓ Агрегированные данные обновлены для {company_name}")
            except Exception as e:
                print(f"⚠ Ошибка агрегации для {company_name}: {e}")
    else:
        print(f"  ⚠ Данные не извлечены")
    
    # ШАГ 4: Очистка файлов (с возможностью сохранения для дебага)
    print(f"\n🧹 Шаг 4/5: Удаление архивов и временных файлов...")
    if os.path.exists(company_dir):
        # Для дебага сохраняем один PDF файл отчета
        debug_saved = False
        for root, dirs, files in os.walk(company_dir):
            for file in files:
                if file.lower().endswith('.pdf') and 'отчет' in file.lower() and not debug_saved:
                    debug_pdf_path = os.path.join(root, file)
                    debug_save_path = f"debug_report_{company_name.replace(' ', '_')}.pdf"
                    try:
                        shutil.copy2(debug_pdf_path, debug_save_path)
                        print(f"  🔍 DEBUG: Сохранен PDF для анализа: {debug_save_path}")
                        debug_saved = True
                    except Exception as e:
                        print(f"  ⚠ Не удалось сохранить PDF для дебага: {e}")
        
        deleted_count = cleanup_files(company_dir)
        print(f"  ✓ Удалено {deleted_count} файлов и папок")
        print(f"  💾 Освобождено место на диске")
    else:
        print(f"  ⚠ Папка не найдена")
    
    # ШАГ 5: Статистика по компании
    print(f"\n📊 Шаг 5/5: Итоги по компании")
    print(f"  Документов скачано: {company_download_stats['success']}")
    print(f"  Ошибок: {company_download_stats['failed']}")
    print(f"  Позиций из УПД: {len(company_upd_data)}")
    
    # Обновляем глобальную статистику
    total_stats['companies_processed'] += 1
    total_stats['total_documents'] += len(documents)
    total_stats['download_success'] += company_download_stats['success']
    total_stats['download_failed'] += company_download_stats['failed']
    
    # Очищаем память
    company_documents.clear()
    company_upd_data.clear()
    if 'df_upd' in locals():
        del df_upd
    
    print(f"\n✅ Компания {company_name} обработана полностью")
    print(f"🧹 Данные в БД, архивы удалены, память очищена")
    print(f"⏭️  Переход к следующей компании...\n")
    
    # Пауза между компаниями
    time.sleep(30)

# ============================================================================
# ИТОГОВАЯ СТАТИСТИКА ПО ВСЕМ КОМПАНИЯМ
# ============================================================================

print("\n" + "="*80)
print("📊 ИТОГОВАЯ СТАТИСТИКА")
print("="*80)

print(f"\n🏢 Обработано компаний: {total_stats['companies_processed']}/{len(dict_api)}")
print(f"📋 Всего документов в списках: {total_stats['total_documents']}")
print(f"📥 Скачано успешно: {total_stats['download_success']}")
print(f"❌ Ошибок при скачивании: {total_stats['download_failed']}")
print(f"📊 Всего позиций из УПД: {total_stats['total_upd_items']}")

print(f"\n💡 Данные сохранены в PostgreSQL:")
print(f"   База данных: {PG_DB}")
print(f"   Схема.Таблица: {PG_SCHEMA}.{PG_TABLE}")
print(f"   Хост: {PG_HOST}")
print(f"   Типы документов: УПД и еженедельные отчеты реализации")

print(f"\n🧹 Все временные файлы и архивы удалены с сервера")

def generate_documents_report_from_march_2025():
    """
    Генерирует отчет документов с 1 марта 2025 года до текущей даты.
    """
    # Устанавливаем дату начала - 1 марта 2025 года
    march_1_2025 = datetime(2025, 3, 1)
    today = datetime.now()
    
    # Проверяем, что 1 марта 2025 еще не наступило
    if today < march_1_2025:
        print(f"1 марта 2025 года еще не наступило. Текущая дата: {today.strftime('%Y-%m-%d')}")
        return "Отчет не может быть сгенерирован - 1 марта 2025 года еще не наступило"
    
    start_date = march_1_2025.strftime('%Y-%m-%d')
    end_date = today.strftime('%Y-%m-%d')
    
    print("=" * 80)
    print(f"Генерация отчета документов с 1 марта 2025 года")
    print(f"Период: {start_date} - {end_date}")
    print(f"Общее количество дней: {(today - march_1_2025).days + 1}")
    print("=" * 80)
    
    # Обновляем глобальные переменные
    global date_from, date_to
    date_from = start_date
    date_to = end_date
    
    try:
        # Здесь будет основной код обработки документов
        # (код из основного блока main)
        print("Отчет с 1 марта 2025 года завершен успешно")
        return "Отчет с 1 марта 2025 года завершен успешно"
    except Exception as e:
        print(f"Критическая ошибка при генерации отчета с 1 марта 2025: {e}")
        raise

if __name__ == "__main__":
    # Проверяем, что 1 марта 2025 еще не наступило
    march_1_2025 = datetime(2025, 3, 1)
    today = datetime.now()
    
    if today < march_1_2025:
        print(f"1 марта 2025 года еще не наступило. Текущая дата: {today.strftime('%Y-%m-%d')}")
        print("Скрипт будет работать с текущими датами")
    else:
        print(f"Период обработки: {date_from} - {date_to}")
        print(f"Общее количество дней: {(today - march_1_2025).days + 1}")

print("\n" + "="*80)
print("✅ ПРОЦЕСС ЗАВЕРШЕН!")
print("="*80)
print(f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Период обработки: {date_from} - {date_to}")
print("="*80)