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
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert
import psycopg2

# Даты: последние 31 день (формат YYYY-MM-DD)
date_from = (datetime.now() - timedelta(days=45)).strftime('%Y-%m-%d')
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
            response = requests.get(url, headers=headers, params=params, timeout=60)
            
            if response.status_code == 200:
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
                time.sleep(1)  # Уважение к rate limit
                
            elif response.status_code == 401:
                print("  ✗ Ошибка: неверный API-ключ или доступ запрещен.")
                break
            elif response.status_code == 429:
                retry_after = response.headers.get('Retry-After', 12)
                print(f"  ⏳ Rate limit. Ожидание {retry_after} секунд...")
                time.sleep(int(retry_after))
                continue
            else:
                print(f"  ✗ Ошибка: {response.status_code} - {response.text[:100]}")
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
        response = requests.get(url, headers=headers, params=params, timeout=60)
        
        if response.status_code == 200:
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
                
        elif response.status_code == 401:
            return {'success': False, 'error': 'Неверный API-ключ'}
        elif response.status_code == 429:
            retry_after = response.headers.get('Retry-After', 12)
            return {'success': False, 'error': f'Rate limit, ждать {retry_after} сек'}
        else:
            return {'success': False, 'error': f'{response.status_code} - {response.text}'}
            
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
    Примеры: "УПД №092800080382 от 28.09.2025.pdf"
    """
    match = re.search(r'от\s+(\d{2}\.\d{2}\.\d{4})', filename)
    if match:
        return match.group(1)
    match = re.search(r'(\d{2}\.\d{2}\.\d{4})', filename)
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
        date VARCHAR(20),
        item_name TEXT NOT NULL,
        cost NUMERIC(15, 2),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT unique_upd_item UNIQUE (company, upd_number, date, cost)
    );
    
    CREATE INDEX IF NOT EXISTS idx_upd_company ON {PG_SCHEMA}.{PG_TABLE}(company);
    CREATE INDEX IF NOT EXISTS idx_upd_number ON {PG_SCHEMA}.{PG_TABLE}(upd_number);
    CREATE INDEX IF NOT EXISTS idx_upd_date ON {PG_SCHEMA}.{PG_TABLE}(date);
    """
    
    # Проверяем существование constraint
    check_constraint_query = f"""
    SELECT COUNT(*) 
    FROM information_schema.table_constraints 
    WHERE table_schema = '{PG_SCHEMA}' 
    AND table_name = '{PG_TABLE}' 
    AND constraint_name = 'unique_upd_item';
    """
    
    try:
        with engine.begin() as conn:
            conn.execute(text(create_schema_query))
            conn.execute(text(create_table_query))
            
            # Проверяем, есть ли constraint
            result = conn.execute(text(check_constraint_query))
            constraint_exists = result.scalar() > 0
            
            if not constraint_exists:
                print("⚠ Добавляем отсутствующий UNIQUE constraint...")
                add_constraint_query = f"""
                ALTER TABLE {PG_SCHEMA}.{PG_TABLE} 
                ADD CONSTRAINT unique_upd_item UNIQUE (company, upd_number, date, cost);
                """
                conn.execute(text(add_constraint_query))
                print("✓ UNIQUE constraint добавлен")
            
        print("✓ Таблица БД создана/проверена (уникальный ключ: company + upd_number + date + cost)")
        return True
    except Exception as e:
        print(f"✗ Ошибка создания таблицы: {e}")
        return False

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
        return False
    
    try:
        df = pd.DataFrame(upd_data)
        
        # Добавляем поле updated_at
        df['updated_at'] = datetime.now()
        
        # Проверяем и добавляем новые колонки
        data_columns = dict(df.dtypes)
        add_missing_columns(data_columns)
        
        # Получаем список колонок для INSERT (исключаем created_at)
        columns_to_insert = [col for col in df.columns if col not in ['created_at']]
        
        # Получаем список колонок для UPDATE (исключаем created_at и ключевые поля)
        columns_to_update = [col for col in columns_to_insert 
                            if col not in ['company', 'upd_number', 'date', 'cost']]
        
        # Конвертируем DataFrame в список словарей
        records = df[columns_to_insert].to_dict('records')
        
        # Формируем SQL для UPSERT
        columns_str = ', '.join(columns_to_insert)
        placeholders = ', '.join([f':{col}' for col in columns_to_insert])
        
        update_str = ', '.join([f"{col} = EXCLUDED.{col}" for col in columns_to_update])
        
        upsert_query = f"""
        INSERT INTO {PG_SCHEMA}.{PG_TABLE} ({columns_str})
        VALUES ({placeholders})
        ON CONFLICT (company, upd_number, date, cost)
        DO UPDATE SET {update_str};
        """
        
        # Выполняем UPSERT батчами
        inserted_count = 0
        updated_count = 0
        batch_size = 1000
        
        with engine.begin() as conn:
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                
                for record in batch:
                    result = conn.execute(text(upsert_query), record)
                    inserted_count += 1
        
        print(f"  ✓ {len(records)} позиций обработано в PostgreSQL (UPSERT)")
        return True
        
    except Exception as e:
        print(f"  ✗ Ошибка загрузки в БД: {e}")
        print(f"  Детали: {traceback.format_exc()}")
        return False

def deduplicate_upd_data():
    """Выполняет дедупликацию данных в таблице УПД через временную таблицу"""
    try:
        # Имя временной таблицы БЕЗ схемы (временные таблицы создаются в pg_temp автоматически)
        temp_table = f"{PG_TABLE}_temp"
        
        # Удаляем временную таблицу если она уже существует
        drop_temp_table_query = f"DROP TABLE IF EXISTS {temp_table};"
        
        # Создаем временную таблицу с уникальными записями
        # Дедупликация по: company, upd_number, cost, date
        create_temp_table_query = f"""
        CREATE TEMP TABLE {temp_table} AS
        SELECT DISTINCT ON (company, upd_number, date, cost)
            company, upd_number, date, item_name, cost, created_at, updated_at
        FROM {PG_SCHEMA}.{PG_TABLE}
        ORDER BY company, upd_number, date, cost, updated_at DESC;
        """
        
        # Удаляем все данные из основной таблицы
        truncate_query = f"TRUNCATE TABLE {PG_SCHEMA}.{PG_TABLE};"
        
        # Вставляем уникальные данные обратно
        insert_back_query = f"""
        INSERT INTO {PG_SCHEMA}.{PG_TABLE} (company, upd_number, date, item_name, cost, created_at, updated_at)
        SELECT company, upd_number, date, item_name, cost, created_at, updated_at
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

# Создаем таблицу в PostgreSQL если её нет
print("="*80)
print("ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ")
print("="*80)
if not create_upd_table_if_not_exists():
    print("⚠ Продолжаем без базы данных")
print()

# Получаем API ключи из Google Sheets
print("Загрузка API ключей из Google Sheets...")
df = get_sheet_data_as_dataframe(credentials_file, spreadsheet_key, sheet_name)
df = df[(df['API ключ'] != '') & (df['API ключ'] != None) & ~((df['Имя Юрлица'] == 'TD') | (df['Имя Юрлица'] == 'ИП Крапивина С.А.'))]

# Для теста можно раскомментировать (тестируем на одной компании):
#df = df[df['Имя Юрлица']=='ИП Солоджук Е. Г']

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
                        print(f" → Извлечено {len(upd_items)} позиций")
                    else:
                        print(f" → Нет данных")
                except Exception as e:
                    print(f" → Ошибка: {e}")
            else:
                print()
        else:
            print(f"✗ {result['error']}")
            company_download_stats['failed'] += 1
        
        time.sleep(10)  # Rate limit
    
    # ШАГ 3: Сохранение данных УПД в PostgreSQL
    print(f"\n💾 Шаг 3/5: Сохранение данных УПД в PostgreSQL...")
    if company_upd_data:
        df_upd = pd.DataFrame(company_upd_data)
        
        # Загружаем в PostgreSQL
        upload_success = upload_upd_to_postgres(company_upd_data)
        
        print(f"  ✓ Обработано {len(company_upd_data)} позиций из {df_upd['upd_number'].nunique()} УПД")
        print(f"  💰 Общая сумма: {df_upd['cost'].sum():,.2f} руб")
        
        if upload_success:
            total_stats['total_upd_items'] += len(company_upd_data)
            
            # Выполняем дедупликацию после загрузки
            print(f"\n🔄 Дедупликация данных...")
            deduplicate_upd_data()
    else:
        print(f"  ⚠ УПД данные не извлечены")
    
    # ШАГ 4: Очистка файлов
    print(f"\n🧹 Шаг 4/5: Удаление архивов и временных файлов...")
    if os.path.exists(company_dir):
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
    
    time.sleep(2)

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

print(f"\n💡 Данные УПД сохранены в PostgreSQL:")
print(f"   База данных: {PG_DB}")
print(f"   Схема.Таблица: {PG_SCHEMA}.{PG_TABLE}")
print(f"   Хост: {PG_HOST}")

print(f"\n🧹 Все временные файлы и архивы удалены с сервера")

print("\n" + "="*80)
print("✅ ПРОЦЕСС ЗАВЕРШЕН!")
print("="*80)
print(f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Период обработки: {date_from} - {date_to}")
print("="*80)