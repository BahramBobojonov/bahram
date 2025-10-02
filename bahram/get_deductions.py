#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для выгрузки данных по удержаниям (Deductions) из WB Seller Analytics API.

Поддерживаемые типы удержаний:
1. antifraud-details - Антифрод
2. incorrect-attachments - Неверные вложения
3. goods-labeling - Маркировка товаров
4. characteristics-change - Изменение характеристик

Особенности:
- Единая таблица с типом удержания
- Обработка ошибок с повторными попытками
- Динамическое добавление новых полей из API
- Цикл по всем клиентам из Google Sheets
"""

import sys
import io

# Устанавливаем UTF-8 для консоли Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import requests
import pandas as pd
from sqlalchemy import text, create_engine
from datetime import datetime, timedelta
import time
import gspread
import os
import traceback
import json

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

# PostgreSQL конфигурация
PG_HOST = '94.103.84.245'
PG_PORT = 5432
PG_USER = 'bahram'
PG_PASSWORD = 'Dadajonim99'
PG_DB = 'wb_baah'
PG_SCHEMA = 'reports'
PG_TABLE = 'deductions_data'

# Создание подключения к БД
engine = create_engine(f'postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}')

# Google Sheets setup
cred_path = os.path.join(os.path.dirname(__file__), 'cred.json')
SPREADSHEET_KEY = "15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ"
SHEET_NAME = "Инвесторы"

# Период выгрузки
DAYS_BACK = 31
date_from = (datetime.now() - timedelta(days=DAYS_BACK)).strftime('%Y-%m-%d')
date_to = datetime.now().strftime('%Y-%m-%d')

# Retry настройки
MAX_RETRIES = 3
RETRY_DELAY = 5  # секунд
RATE_LIMIT_DELAY = 2  # секунд между запросами

# ============================================================================
# API ENDPOINTS
# ============================================================================

API_ENDPOINTS = {
    'antifraud-details': {
        'url': 'https://seller-analytics-api.wildberries.ru/api/v1/analytics/antifraud-details',
        'description': 'Самовыкупы'
    },
    'incorrect-attachments': {
        'url': 'https://seller-analytics-api.wildberries.ru/api/v1/analytics/incorrect-attachments',
        'description': 'Подмена товара'
    },
    'goods-labeling': {
        'url': 'https://seller-analytics-api.wildberries.ru/api/v1/analytics/goods-labeling',
        'description': 'Маркировка товаров'
    },
    'characteristics-change': {
        'url': 'https://seller-analytics-api.wildberries.ru/api/v1/analytics/characteristics-change',
        'description': 'Изменение характеристик'
    }
}

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def get_sheet_data_as_dataframe(credentials_file, spreadsheet_key, sheet_name):
    """
    Получает данные из указанного листа Google Sheets и возвращает их в формате DataFrame.
    """
    gc = gspread.service_account(filename=credentials_file)
    worksheet = gc.open_by_key(spreadsheet_key).worksheet(sheet_name)
    data = worksheet.get_all_records(expected_headers=None)
    df = pd.DataFrame(data, dtype=object)
    return df

def create_schema_if_not_exists(engine, schema):
    """Создает схему если её не существует"""
    create_query = text(f'CREATE SCHEMA IF NOT EXISTS {schema}')
    try:
        with engine.connect() as conn:
            conn.execute(create_query)
            conn.commit()
        print(f"✓ Схема {schema} создана/проверена")
        return True
    except Exception as e:
        print(f"✗ Ошибка создания схемы {schema}: {e}")
        return False

def table_exists(engine, schema, table_name):
    """Проверяет существование таблицы"""
    query = text(f"""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = '{schema}' AND table_name = '{table_name}'
        );
    """)
    try:
        result = pd.read_sql(query, engine).iloc[0, 0]
        return bool(result)
    except Exception as e:
        print(f"⚠ Ошибка проверки таблицы: {e}")
        return False

def create_deductions_table(engine, schema, table_name):
    """
    Создает таблицу для хранения данных удержаний.
    Базовые поля + динамические поля из API.
    """
    create_table_query = text(f"""
        CREATE TABLE IF NOT EXISTS {schema}.{table_name} (
            id SERIAL PRIMARY KEY,
            supplier VARCHAR(255) NOT NULL,
            deduction_type VARCHAR(100) NOT NULL,
            deduction_description TEXT,
            update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            date_from VARCHAR(20),
            date_to VARCHAR(20),
            data JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_deductions_supplier ON {schema}.{table_name}(supplier);
        CREATE INDEX IF NOT EXISTS idx_deductions_type ON {schema}.{table_name}(deduction_type);
        CREATE INDEX IF NOT EXISTS idx_deductions_update_time ON {schema}.{table_name}(update_time);
        CREATE INDEX IF NOT EXISTS idx_deductions_data_gin ON {schema}.{table_name} USING GIN (data);
    """)
    
    try:
        with engine.connect() as conn:
            conn.execute(create_table_query)
            conn.commit()
        print(f"✓ Таблица {schema}.{table_name} создана/проверена")
        return True
    except Exception as e:
        print(f"✗ Ошибка создания таблицы: {e}")
        return False

def get_existing_columns(engine, schema, table_name):
    """Получает список существующих колонок в таблице"""
    query = text(f"""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = '{schema}' AND table_name = '{table_name}'
        ORDER BY ordinal_position;
    """)
    
    try:
        result = pd.read_sql(query, engine)
        columns = dict(zip(result['column_name'], result['data_type']))
        return columns
    except Exception as e:
        print(f"⚠ Ошибка получения колонок: {e}")
        return {}

def add_missing_columns(engine, schema, table_name, new_columns):
    """
    Добавляет отсутствующие колонки в таблицу.
    new_columns - словарь {column_name: column_type}
    """
    existing_columns = get_existing_columns(engine, schema, table_name)
    
    if not existing_columns:
        return False
    
    # Системные колонки, которые не добавляем
    system_columns = ['id', 'created_at', 'update_time', 'supplier', 'deduction_type', 
                     'deduction_description', 'date_from', 'date_to', 'data']
    
    added_columns = []
    
    for col_name, col_type in new_columns.items():
        # Пропускаем системные колонки
        if col_name in system_columns:
            continue
            
        # Если колонка уже есть, пропускаем
        if col_name in existing_columns:
            continue
        
        # Определяем тип PostgreSQL (по умолчанию TEXT для гибкости)
        pg_type = col_type if col_type else 'TEXT'
        
        try:
            alter_query = text(f"""
                ALTER TABLE {schema}.{table_name} 
                ADD COLUMN IF NOT EXISTS {col_name} {pg_type};
            """)
            
            with engine.connect() as conn:
                conn.execute(alter_query)
                conn.commit()
            
            added_columns.append(f"{col_name} ({pg_type})")
            
        except Exception as e:
            print(f"  ⚠ Не удалось добавить колонку {col_name}: {e}")
    
    if added_columns:
        print(f"  ✓ Добавлено новых колонок: {len(added_columns)}")
        for col in added_columns:
            print(f"    • {col}")
    
    return len(added_columns) > 0

# ============================================================================
# API ФУНКЦИИ С ОБРАБОТКОЙ ОШИБОК
# ============================================================================

def fetch_deductions_with_retry(api_key, endpoint_key, date_from, date_to, max_retries=MAX_RETRIES):
    """
    Получает данные удержаний с автоматическими повторными попытками при ошибках.
    
    Args:
        api_key: API ключ
        endpoint_key: ключ endpoint из API_ENDPOINTS
        date_from: дата начала
        date_to: дата окончания
        max_retries: максимальное количество попыток
    
    Returns:
        list: список записей или None при ошибке
    """
    endpoint_info = API_ENDPOINTS.get(endpoint_key)
    if not endpoint_info:
        print(f"  ✗ Неизвестный endpoint: {endpoint_key}")
        return None
    
    url = endpoint_info['url']
    headers = {
        'Authorization': api_key,
        'Content-Type': 'application/json'
    }
    
    params = {
        'dateFrom': date_from,
        'dateTo': date_to
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=60)
            
            # Успешный ответ
            if response.status_code == 200:
                data = response.json()
                
                # API может вернуть разные форматы
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    # Иногда данные в ключе 'data' или 'items'
                    if 'data' in data:
                        return data['data']
                    elif 'items' in data:
                        return data['items']
                    else:
                        return [data]  # Оборачиваем в список
                else:
                    return []
            
            # Rate limit - ждем и повторяем
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', RETRY_DELAY))
                print(f"  ⏳ Rate limit. Ожидание {retry_after} сек (попытка {attempt + 1}/{max_retries})")
                time.sleep(retry_after)
                continue
            
            # Unauthorized
            elif response.status_code == 401:
                print(f"  ✗ Ошибка авторизации (401). Проверьте API ключ.")
                return None
            
            # Not Found - возможно метод не доступен для этого аккаунта
            elif response.status_code == 404:
                print(f"  ⚠ Метод не найден (404). Возможно не доступен для этого аккаунта.")
                return []
            
            # Server error - повторяем
            elif response.status_code >= 500:
                print(f"  ⚠ Ошибка сервера ({response.status_code}). Попытка {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    print(f"  ✗ Не удалось получить данные после {max_retries} попыток")
                    return None
            
            # Другие ошибки
            else:
                print(f"  ✗ Ошибка API ({response.status_code}): {response.text[:200]}")
                return None
                
        except requests.exceptions.Timeout:
            print(f"  ⚠ Timeout. Попытка {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY)
                continue
            else:
                print(f"  ✗ Превышено время ожидания после {max_retries} попыток")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"  ⚠ Ошибка запроса: {e}. Попытка {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY)
                continue
            else:
                print(f"  ✗ Ошибка соединения после {max_retries} попыток")
                return None
                
        except Exception as e:
            print(f"  ✗ Неожиданная ошибка: {e}")
            print(f"  Traceback: {traceback.format_exc()}")
            return None
    
    return None

def normalize_and_flatten_data(records, deduction_type):
    """
    Нормализует данные из API и разворачивает вложенные массивы.
    
    Структура ответов API:
    - antifraud-details: {'details': [{...}, {...}]} - массив удержаний за самовыкупы
    - incorrect-attachments: {'report': [{...}, {...}]} - массив удержаний за неверные вложения
    - goods-labeling: {'report': [{...}, {...}]} - массив удержаний за маркировку
    - characteristics-change: {'report': [{...}, {...}]} - массив удержаний за изменение характеристик
    
    Args:
        records: список записей из API (обычно один элемент со вложенным массивом)
        deduction_type: тип удержания
    
    Returns:
        DataFrame с развернутыми данными (каждый элемент массива - отдельная строка)
    """
    if not records:
        return pd.DataFrame()
    
    try:
        # API возвращает один объект с массивом внутри
        if len(records) == 1 and isinstance(records[0], dict):
            record = records[0]
            
            # Определяем ключ с массивом данных
            if 'details' in record:
                array_key = 'details'
            elif 'report' in record:
                array_key = 'report'
            else:
                print(f"  ⚠ Неизвестная структура ответа: {list(record.keys())}")
                return pd.DataFrame()
            
            # Извлекаем массив
            data_array = record.get(array_key, [])
            
            # print(f"  📊 Найдено записей в '{array_key}': {len(data_array)}")
            
            # Если массив пустой, возвращаем пустой DataFrame
            if not data_array:
                # print(f"  ℹ Массив '{array_key}' пустой")
                return pd.DataFrame()
            
            # Разворачиваем массив в DataFrame
            df = pd.DataFrame(data_array)
            
            # Выводим структуру для отладки (раскомментируйте при необходимости)
            # print(f"  📋 Колонки: {list(df.columns)}")
            # if len(df) > 0:
            #     print(f"  📝 Пример: {df.iloc[0].to_dict()}")
            
            # Сохраняем оригинальные данные в JSONB колонку
            df['original_data'] = df.apply(lambda row: row.to_dict(), axis=1)
            
            # Нормализуем колонки - приводим к нижнему регистру и заменяем пробелы
            df.columns = df.columns.str.lower().str.replace(' ', '_').str.replace('-', '_')
            
            return df
        else:
            # Если структура другая (список объектов), обрабатываем как обычно
            df = pd.DataFrame(records)
            df['original_data'] = df.apply(lambda row: row.to_dict(), axis=1)
            df.columns = df.columns.str.lower().str.replace(' ', '_').str.replace('-', '_')
            return df
        
    except Exception as e:
        print(f"  ⚠ Ошибка нормализации данных: {e}")
        print(f"  Traceback: {traceback.format_exc()}")
        return pd.DataFrame()

# ============================================================================
# СОХРАНЕНИЕ В БД
# ============================================================================

def save_deductions_to_db(engine, df, supplier, deduction_type, deduction_description, 
                         date_from, date_to, schema, table_name):
    """
    Сохраняет данные удержаний в PostgreSQL с UPSERT логикой.
    Обновляет существующие записи по ключу (supplier, deduction_type, дата из data).
    
    Args:
        engine: SQLAlchemy engine
        df: DataFrame с данными
        supplier: название компании
        deduction_type: тип удержания
        deduction_description: описание типа удержания
        date_from: дата начала периода
        date_to: дата окончания периода
        schema: схема БД
        table_name: название таблицы
    """
    if df.empty:
        print(f"  ⚠ Нет данных для сохранения")
        return 0
    
    try:
        df_copy = df.copy()
        
        # Добавляем служебные поля
        df_copy['supplier'] = supplier
        df_copy['deduction_type'] = deduction_type
        df_copy['deduction_description'] = deduction_description
        df_copy['update_time'] = datetime.now()
        df_copy['date_from'] = date_from
        df_copy['date_to'] = date_to
        
        # Сохраняем оригинальные данные в JSONB если есть
        # Конвертируем словари в JSON строки для совместимости с psycopg2
        if 'original_data' in df_copy.columns:
            df_copy['data'] = df_copy['original_data'].apply(
                lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, dict) else '{}'
            )
            df_copy = df_copy.drop('original_data', axis=1)
        else:
            df_copy['data'] = df_copy.apply(
                lambda row: json.dumps(row.to_dict(), ensure_ascii=False), axis=1
            )
        
        # Проверяем и добавляем новые колонки с правильными типами
        new_columns = {}
        for col in df_copy.columns:
            if col in ['id', 'created_at', 'update_time', 'supplier', 'deduction_type',
                      'deduction_description', 'date_from', 'date_to', 'data']:
                continue
            
            # Определяем тип на основе названия и содержимого колонки
            if col in ['nmid', 'nm_id']:
                new_columns[col] = 'BIGINT'
            elif col in ['sum', 'amount', 'price', 'cost']:
                new_columns[col] = 'NUMERIC(15, 2)'
            elif col in ['datefrom', 'dateto', 'date_from_detail', 'date_to_detail', 'date']:
                new_columns[col] = 'VARCHAR(20)'
            elif col in ['currency']:
                new_columns[col] = 'VARCHAR(10)'
            else:
                new_columns[col] = 'TEXT'
        
        if new_columns:
            add_missing_columns(engine, schema, table_name, new_columns)
        
        # Удаляем старые записи для этого supplier и deduction_type за этот период
        # Это проще чем делать сложный UPSERT
        delete_query = text(f"""
            DELETE FROM {schema}.{table_name}
            WHERE supplier = :supplier 
            AND deduction_type = :deduction_type
            AND date_from = :date_from
            AND date_to = :date_to
        """)
        
        with engine.begin() as conn:
            result = conn.execute(delete_query, {
                'supplier': supplier,
                'deduction_type': deduction_type,
                'date_from': date_from,
                'date_to': date_to
            })
            deleted_count = result.rowcount
            if deleted_count > 0:
                print(f"  🔄 Удалено старых записей: {deleted_count}")
        
        # Сохраняем новые данные в БД
        df_copy.to_sql(table_name, engine, schema=schema, if_exists='append', 
                      index=False, method='multi')
        
        print(f"  ✓ Сохранено {len(df_copy)} записей")
        return len(df_copy)
        
    except Exception as e:
        print(f"  ✗ Ошибка сохранения в БД: {e}")
        print(f"  Traceback: {traceback.format_exc()}")
        return 0

# ============================================================================
# ОСНОВНАЯ ЛОГИКА
# ============================================================================

def process_all_deductions_for_supplier(api_key, supplier, date_from, date_to):
    """
    Обрабатывает все типы удержаний для одного поставщика.
    
    Args:
        api_key: API ключ
        supplier: название компании
        date_from: дата начала
        date_to: дата окончания
    
    Returns:
        dict: статистика по типам удержаний
    """
    stats = {
        'total_records': 0,
        'by_type': {}
    }
    
    print(f"\n{'='*80}")
    print(f"Обработка поставщика: {supplier}")
    print(f"Период: {date_from} - {date_to}")
    print(f"{'='*80}")
    
    for endpoint_key, endpoint_info in API_ENDPOINTS.items():
        print(f"\n📋 Тип удержания: {endpoint_info['description']} ({endpoint_key})")
        
        # Получаем данные с retry
        records = fetch_deductions_with_retry(api_key, endpoint_key, date_from, date_to)
        
        if records is None:
            print(f"  ✗ Не удалось получить данные")
            stats['by_type'][endpoint_key] = 0
            continue
        
        if not records:
            print(f"  ℹ Данных нет за указанный период")
            stats['by_type'][endpoint_key] = 0
            continue
        
        print(f"  ✓ Получено записей: {len(records)}")
        
        # Нормализуем данные
        df = normalize_and_flatten_data(records, endpoint_key)
        
        if df.empty:
            print(f"  ℹ Нет данных для сохранения (пустой массив)")
            stats['by_type'][endpoint_key] = 0
            continue
        
        # Сохраняем в БД
        saved_count = save_deductions_to_db(
            engine, df, supplier, endpoint_key, 
            endpoint_info['description'], date_from, date_to,
            PG_SCHEMA, PG_TABLE
        )
        
        stats['by_type'][endpoint_key] = saved_count
        stats['total_records'] += saved_count
        
        # Rate limiting между запросами
        time.sleep(RATE_LIMIT_DELAY)
    
    print(f"\n{'='*80}")
    print(f"Итого для {supplier}: {stats['total_records']} записей")
    for deduction_type, count in stats['by_type'].items():
        print(f"  • {API_ENDPOINTS[deduction_type]['description']}: {count}")
    print(f"{'='*80}")
    
    return stats

def main():
    """Главная функция скрипта"""
    
    print("="*80)
    print("ВЫГРУЗКА ДАННЫХ ПО УДЕРЖАНИЯМ WILDBERRIES")
    print("="*80)
    print(f"Дата запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Период выгрузки: {date_from} - {date_to}")
    print(f"База данных: {PG_HOST}:{PG_PORT}/{PG_DB}")
    print(f"Схема.Таблица: {PG_SCHEMA}.{PG_TABLE}")
    print("="*80)
    
    # Инициализация БД
    print("\n📊 ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ")
    print("-"*80)
    
    if not create_schema_if_not_exists(engine, PG_SCHEMA):
        print("⚠ Продолжаем без схемы (может быть ошибка)")
    
    if not create_deductions_table(engine, PG_SCHEMA, PG_TABLE):
        print("⚠ Ошибка создания таблицы")
        return
    
    # Загрузка списка клиентов
    print("\n👥 ЗАГРУЗКА СПИСКА КЛИЕНТОВ")
    print("-"*80)
    
    try:
        df_investors = get_sheet_data_as_dataframe(cred_path, SPREADSHEET_KEY, SHEET_NAME)
        df_investors = df_investors[
            (df_investors['API ключ'] != '') & 
            (df_investors['API ключ'].notna())
        ]
        
        # Исключаем тестовые компании (можно настроить)
        # df_investors = df_investors[
        #     ~df_investors['Имя Юрлица'].isin(['TD', 'ИП Крапивина С.А.'])
        # ]
        
        # Для теста можно раскомментировать:
        # df_investors = df_investors[df_investors['Имя Юрлица'] == 'ИП Баах И.Л.']
        
        dict_api = dict(zip(df_investors['API ключ'], df_investors['Имя Юрлица']))
        print(f"✓ Найдено {len(dict_api)} компаний для обработки")
        
    except Exception as e:
        print(f"✗ Ошибка загрузки клиентов: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return
    
    # Глобальная статистика
    global_stats = {
        'companies_processed': 0,
        'companies_failed': 0,
        'total_records': 0,
        'by_type': {key: 0 for key in API_ENDPOINTS.keys()}
    }
    
    # Обработка каждой компании
    print("\n🔄 НАЧАЛО ОБРАБОТКИ КОМПАНИЙ")
    print("="*80)
    
    for idx, (api_key, supplier) in enumerate(dict_api.items(), 1):
        print(f"\n[{idx}/{len(dict_api)}] Компания: {supplier}")
        
        try:
            stats = process_all_deductions_for_supplier(
                api_key, supplier, date_from, date_to
            )
            
            global_stats['companies_processed'] += 1
            global_stats['total_records'] += stats['total_records']
            
            for deduction_type, count in stats['by_type'].items():
                global_stats['by_type'][deduction_type] += count
            
            print(f"\n✅ Компания {supplier} обработана успешно")
            
        except Exception as e:
            print(f"\n✗ Ошибка обработки компании {supplier}: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            global_stats['companies_failed'] += 1
        
        # Пауза между компаниями
        if idx < len(dict_api):
            print(f"\n⏸ Пауза перед следующей компанией...")
            time.sleep(3)
    
    # Итоговая статистика
    print("\n" + "="*80)
    print("📊 ИТОГОВАЯ СТАТИСТИКА")
    print("="*80)
    print(f"\n🏢 Обработано компаний: {global_stats['companies_processed']}/{len(dict_api)}")
    print(f"❌ Ошибок: {global_stats['companies_failed']}")
    print(f"📊 Всего записей: {global_stats['total_records']}")
    
    print(f"\n📋 По типам удержаний:")
    for deduction_type, count in global_stats['by_type'].items():
        desc = API_ENDPOINTS[deduction_type]['description']
        print(f"  • {desc}: {count}")
    
    print(f"\n💾 Данные сохранены в PostgreSQL:")
    print(f"   База данных: {PG_DB}")
    print(f"   Схема.Таблица: {PG_SCHEMA}.{PG_TABLE}")
    print(f"   Хост: {PG_HOST}")
    
    print("\n" + "="*80)
    print("✅ ПРОЦЕСС ЗАВЕРШЕН!")
    print("="*80)
    print(f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Период обработки: {date_from} - {date_to}")
    print("="*80)

if __name__ == "__main__":
    main()
