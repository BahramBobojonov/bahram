#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для выгрузки данных по удержаниям (Deductions) из WB Seller Analytics API.

Поддерживаемые типы удержаний:
1. antifraud-details - Самовыкупы (еженедельные отчеты по средам)
2. incorrect-attachments - Подмена товара (максимум 31 день)
3. goods-labeling - Маркировка товаров (максимум 31 день)
4. characteristics-change - Изменение характеристик (максимум 31 день)
5. warehouse-measurements - Занижение габаритов упаковки (с пагинацией, максимум 31 день)

Особенности:
- Единая таблица с типом удержания
- Обработка ошибок с повторными попытками (до 15 попыток)
- Динамическое добавление новых полей из API
- Цикл по всем клиентам из Google Sheets
- Специальная обработка для каждого типа удержаний:
  * antifraud-details: использует параметр 'date', работает по неделям
  * warehouse-measurements: пагинация с параметрами tab, limit, offset
  * остальные: стандартные параметры dateFrom/dateTo
- Адаптивные паузы для соблюдения лимитов API
- Циклы по 31 день для соблюдения ограничений API
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

# Период выгрузки (с 1 марта 2025)
march_1_2025 = datetime(2025, 3, 1)
today = datetime.now()

# Проверяем, что 1 марта 2025 уже наступило
if today < march_1_2025:
    print(f"⚠ 1 марта 2025 года еще не наступило. Текущая дата: {today.strftime('%Y-%m-%d')}")
    print("⚠ Используем период с 1 января 2025")
    date_from = '2025-01-01'
else:
    date_from = march_1_2025.strftime('%Y-%m-%d')

date_to = today.strftime('%Y-%m-%d')

# Retry настройки (как в report_paid_storage.py)
MAX_RETRIES = 15
RETRY_DELAY = 10  # секунд
RATE_LIMIT_DELAY = 5  # секунд между запросами
BURST_PAUSE = 120  # секунд после каждых 3 запросов
CYCLE_PAUSE = 15  # секунд между циклами
SUPPLIER_PAUSE = 30  # секунд между поставщиками

# ============================================================================
# API ENDPOINTS
# ============================================================================

API_ENDPOINTS = {
    'antifraud-details': {
        'url': 'https://seller-analytics-api.wildberries.ru/api/v1/analytics/antifraud-details',
        'description': 'Самовыкупы',
        'type': 'antifraud',
        'param_type': 'date',  # Использует параметр 'date' вместо 'dateFrom/dateTo'
        'max_days': None,  # Нет ограничения по дням, но данные еженедельные
        'rate_limit': {'period': 100, 'limit': 10, 'interval': 10, 'burst': 10}  # 100 минут, 10 запросов, 10 минут, 10 всплеск
    },
    'incorrect-attachments': {
        'url': 'https://seller-analytics-api.wildberries.ru/api/v1/analytics/incorrect-attachments',
        'description': 'Подмена товара',
        'type': 'standard',
        'param_type': 'dateRange',  # Использует dateFrom/dateTo
        'max_days': 31,
        'rate_limit': {'period': 1, 'limit': 1, 'interval': 1, 'burst': 10}  # 1 минута, 1 запрос, 1 минута, 10 всплеск
    },
    'goods-labeling': {
        'url': 'https://seller-analytics-api.wildberries.ru/api/v1/analytics/goods-labeling',
        'description': 'Маркировка товаров',
        'type': 'standard',
        'param_type': 'dateRange',  # Использует dateFrom/dateTo
        'max_days': 31,
        'rate_limit': {'period': 10, 'limit': 10, 'interval': 1, 'burst': 10}  # 10 минут, 10 запросов, 1 минута, 10 всплеск
    },
    'characteristics-change': {
        'url': 'https://seller-analytics-api.wildberries.ru/api/v1/analytics/characteristics-change',
        'description': 'Изменение характеристик',
        'type': 'standard',
        'param_type': 'dateRange',  # Использует dateFrom/dateTo
        'max_days': 31,
        'rate_limit': {'period': 10, 'limit': 10, 'interval': 1, 'burst': 10}  # 10 минут, 10 запросов, 1 минута, 10 всплеск
    },
    'warehouse-measurements': {
        'url': 'https://seller-analytics-api.wildberries.ru/api/v1/analytics/warehouse-measurements',
        'description': 'Занижение габаритов упаковки',
        'type': 'pagination',
        'param_type': 'dateRange',  # Использует dateFrom/dateTo
        'max_days': 31,
        'tabs': ['penalty', 'measurement'],
        'rate_limit': {'period': 1, 'limit': 5, 'interval': 12, 'burst': 1}  # 1 минута, 5 запросов, 12 секунд, 1 всплеск
    }
}

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def split_date_range_into_cycles(start_date, end_date, max_days=31):
    """
    Разбивает период на циклы по max_days дней для соблюдения лимитов API.
    
    Args:
        start_date: дата начала (строка 'YYYY-MM-DD')
        end_date: дата окончания (строка 'YYYY-MM-DD')
        max_days: максимальное количество дней в цикле (по умолчанию 31)
    
    Returns:
        list: список кортежей (start, end) для каждого цикла
    """
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    cycles = []
    current_start = start_dt
    
    while current_start <= end_dt:
        # Определяем конец текущего цикла (максимум max_days дней)
        current_end = min(current_start + timedelta(days=max_days-1), end_dt)
        
        cycles.append((
            current_start.strftime('%Y-%m-%d'),
            current_end.strftime('%Y-%m-%d')
        ))
        
        # Переходим к следующему циклу
        current_start = current_end + timedelta(days=1)
    
    return cycles

def get_cycles_for_endpoint(endpoint_key, start_date, end_date):
    """
    Получает циклы для конкретного endpoint с учетом его ограничений.
    
    Args:
        endpoint_key: ключ endpoint из API_ENDPOINTS
        start_date: дата начала
        end_date: дата окончания
    
    Returns:
        list: список кортежей (start, end) для каждого цикла
    """
    endpoint_info = API_ENDPOINTS.get(endpoint_key)
    if not endpoint_info:
        return [(start_date, end_date)]
    
    # Для antifraud-details не используем циклы, так как он работает по неделям
    if endpoint_info.get('type') == 'antifraud':
        return [(start_date, end_date)]
    
    # Для остальных методов используем max_days из конфигурации
    max_days = endpoint_info.get('max_days', 31)
    return split_date_range_into_cycles(start_date, end_date, max_days)

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
    Улучшенная версия с экспоненциальными задержками как в report_paid_storage.py
    
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
    
    # Специальная обработка для warehouse-measurements
    if endpoint_info.get('type') == 'pagination':
        return fetch_warehouse_measurements_with_pagination(api_key, endpoint_key, date_from, date_to, max_retries)
    
    # Специальная обработка для antifraud-details (использует параметр 'date')
    if endpoint_info.get('type') == 'antifraud':
        return fetch_antifraud_details(api_key, endpoint_key, date_from, date_to, max_retries)
    
    # Стандартные параметры для остальных методов (используем ISO формат)
    params = {
        'dateFrom': f"{date_from}T00:00:00.000Z",
        'dateTo': f"{date_to}T23:59:59.999Z"
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
            
            # Rate limit - ждем и повторяем с экспоненциальной задержкой
            elif response.status_code == 429:
                delay = min(RETRY_DELAY * (2 ** attempt), 1800)  # Максимум 30 минут
                print(f"  ⏳ Rate limit. Ожидание {delay} сек (попытка {attempt + 1}/{max_retries})")
                time.sleep(delay)
                continue
            
            # Unauthorized
            elif response.status_code == 401:
                print(f"  ✗ Ошибка авторизации (401). Проверьте API ключ.")
                return None
            
            # Not Found - возможно метод не доступен для этого аккаунта
            elif response.status_code == 404:
                print(f"  ⚠ Метод не найден (404). Возможно не доступен для этого аккаунта.")
                return []
            
            # Server error - повторяем с экспоненциальной задержкой
            elif 500 <= response.status_code < 600:
                delay = min(RETRY_DELAY * (3 ** attempt), 1800)  # Максимум 30 минут
                print(f"  ⚠ Ошибка сервера ({response.status_code}). Ожидание {delay} сек (попытка {attempt + 1}/{max_retries})")
                time.sleep(delay)
                continue
            
            # Другие ошибки (403 и т.д.) - не повторяем
            else:
                print(f"  ✗ Ошибка API ({response.status_code}): {response.text[:200]}")
                return None
                
        except requests.exceptions.Timeout:
            delay = min(RETRY_DELAY * (2 ** attempt), 1800)  # Максимум 30 минут
            print(f"  ⚠ Timeout. Ожидание {delay} сек (попытка {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(delay)
                continue
            else:
                print(f"  ✗ Превышено время ожидания после {max_retries} попыток")
                return None
                
        except requests.exceptions.RequestException as e:
            delay = min(RETRY_DELAY * (2 ** attempt), 1800)  # Максимум 30 минут
            print(f"  ⚠ Ошибка запроса: {e}. Ожидание {delay} сек (попытка {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(delay)
                continue
            else:
                print(f"  ✗ Ошибка соединения после {max_retries} попыток")
                return None
                
        except Exception as e:
            print(f"  ✗ Неожиданная ошибка: {e}")
            print(f"  Traceback: {traceback.format_exc()}")
            return None
    
    print(f"  ✗ Не удалось получить данные после {max_retries} попыток")
    return None

def fetch_antifraud_details(api_key, endpoint_key, date_from, date_to, max_retries=MAX_RETRIES):
    """
    Получает данные antifraud-details с специальной обработкой.
    Этот метод использует параметр 'date' вместо 'dateFrom/dateTo' и работает с еженедельными отчетами.
    
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
    
    all_records = []
    
    # Для antifraud-details нужно запрашивать данные по неделям
    # Отчеты формируются каждую среду, поэтому запрашиваем данные по средам
    start_dt = datetime.strptime(date_from, '%Y-%m-%d')
    end_dt = datetime.strptime(date_to, '%Y-%m-%d')
    
    # Находим все среды в диапазоне
    wednesdays = []
    current_date = start_dt
    while current_date <= end_dt:
        # Находим следующую среду
        days_ahead = 2 - current_date.weekday()  # 2 = среда (0=понедельник)
        if days_ahead <= 0:  # Если сегодня среда или уже прошла
            days_ahead += 7
        next_wednesday = current_date + timedelta(days=days_ahead)
        
        if next_wednesday <= end_dt:
            wednesdays.append(next_wednesday.strftime('%Y-%m-%d'))
            current_date = next_wednesday + timedelta(days=1)
        else:
            break
    
    print(f"  📅 Найдено {len(wednesdays)} сред для запроса данных")
    
    # Запрашиваем данные за каждую среду
    for wednesday in wednesdays:
        print(f"  📊 Запрос данных за среду: {wednesday}")
        
        params = {'date': wednesday}
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=60)
                
                # Успешный ответ
                if response.status_code == 200:
                    data = response.json()
                    
                    # API возвращает данные в ключе 'details'
                    if 'details' in data and data['details']:
                        records = data['details']
                        all_records.extend(records)
                        print(f"    ✓ Получено {len(records)} записей за {wednesday}")
                    else:
                        print(f"    ℹ Нет данных за {wednesday}")
                    
                    break  # Успешный запрос, выходим из цикла попыток
                
                # Rate limit - ждем и повторяем с экспоненциальной задержкой
                elif response.status_code == 429:
                    delay = min(RETRY_DELAY * (2 ** attempt), 1800)  # Максимум 30 минут
                    print(f"    ⏳ Rate limit. Ожидание {delay} сек (попытка {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                
                # Unauthorized
                elif response.status_code == 401:
                    print(f"    ✗ Ошибка авторизации (401). Проверьте API ключ.")
                    return None
                
                # Not Found - возможно метод не доступен для этого аккаунта
                elif response.status_code == 404:
                    print(f"    ⚠ Метод не найден (404). Возможно не доступен для этого аккаунта.")
                    return []
                
                # Server error - повторяем с экспоненциальной задержкой
                elif 500 <= response.status_code < 600:
                    delay = min(RETRY_DELAY * (3 ** attempt), 1800)  # Максимум 30 минут
                    print(f"    ⚠ Ошибка сервера ({response.status_code}). Ожидание {delay} сек (попытка {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                
                # Другие ошибки (400, 403 и т.д.) - не повторяем
                else:
                    print(f"    ✗ Ошибка API ({response.status_code}): {response.text[:200]}")
                    break  # Не повторяем для 400 ошибок
                    
            except requests.exceptions.Timeout:
                delay = min(RETRY_DELAY * (2 ** attempt), 1800)  # Максимум 30 минут
                print(f"    ⚠ Timeout. Ожидание {delay} сек (попытка {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    continue
                else:
                    print(f"    ✗ Превышено время ожидания после {max_retries} попыток")
                    break
                    
            except requests.exceptions.RequestException as e:
                delay = min(RETRY_DELAY * (2 ** attempt), 1800)  # Максимум 30 минут
                print(f"    ⚠ Ошибка запроса: {e}. Ожидание {delay} сек (попытка {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    continue
                else:
                    print(f"    ✗ Ошибка соединения после {max_retries} попыток")
                    break
                    
            except Exception as e:
                print(f"    ✗ Неожиданная ошибка: {e}")
                print(f"    Traceback: {traceback.format_exc()}")
                break
        
        # Пауза между запросами (antifraud имеет лимит 10 запросов в 100 минут)
        if wednesday != wednesdays[-1]:  # Не ждем после последнего запроса
            print(f"    ⏸ Пауза 10 минут для соблюдения лимитов API")
            time.sleep(600)  # 10 минут
    
    print(f"  ✓ Всего получено записей antifraud: {len(all_records)}")
    return all_records

def fetch_warehouse_measurements_with_pagination(api_key, endpoint_key, date_from, date_to, max_retries=MAX_RETRIES):
    """
    Получает данные warehouse-measurements с поддержкой пагинации.
    Обрабатывает оба типа отчетов: penalty и measurement.
    
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
    
    all_records = []
    
    # Обрабатываем каждый тип отчета (penalty и measurement)
    for tab in endpoint_info.get('tabs', ['penalty']):
        print(f"  📊 Получение данных для вкладки: {tab}")
        
        offset = 0
        limit = 1000  # Максимальный лимит согласно API
        has_more_data = True
        page_count = 0
        
        while has_more_data:
            page_count += 1
            # Исправляем параметры согласно документации API
            # Пробуем разные форматы дат
            params = {
                'dateFrom': f"{date_from}T00:00:00.000Z",  # ISO 8601 формат
                'dateTo': f"{date_to}T23:59:59.999Z",      # ISO 8601 формат
                'tab': tab,
                'limit': limit,
                'offset': offset
            }
            
            print(f"    📄 Страница {page_count} (offset: {offset}, limit: {limit})")
            print(f"    📅 Параметры: dateFrom={params['dateFrom']}, dateTo={params['dateTo']}")
            
            for attempt in range(max_retries):
                try:
                    response = requests.get(url, headers=headers, params=params, timeout=60)
                    
                    # Успешный ответ
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Извлекаем данные из ответа
                        if 'data' in data and 'reports' in data['data']:
                            reports = data['data']['reports']
                            total_count = data['data'].get('totalCount', 0)
                            
                            if reports:
                                # Добавляем информацию о типе отчета к каждой записи
                                for report in reports:
                                    report['tab_type'] = tab
                                    report['endpoint_type'] = endpoint_key
                                
                                all_records.extend(reports)
                                print(f"    ✓ Получено {len(reports)} записей (всего: {total_count})")
                                
                                # Проверяем, есть ли еще данные
                                if len(reports) < limit or offset + len(reports) >= total_count:
                                    has_more_data = False
                                    print(f"    ✅ Пагинация завершена для вкладки {tab}")
                                else:
                                    offset += len(reports)
                                    print(f"    ⏭ Переход к следующей странице (новый offset: {offset})")
                                    time.sleep(RATE_LIMIT_DELAY)  # Пауза между запросами
                            else:
                                has_more_data = False
                        else:
                            print(f"    ℹ Нет данных для вкладки {tab}")
                            has_more_data = False
                        
                        break  # Успешный запрос, выходим из цикла попыток
                    
                    # Rate limit - ждем и повторяем с экспоненциальной задержкой
                    elif response.status_code == 429:
                        delay = min(RETRY_DELAY * (2 ** attempt), 1800)  # Максимум 30 минут
                        print(f"    ⏳ Rate limit. Ожидание {delay} сек (попытка {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        continue
                    
                    # Unauthorized
                    elif response.status_code == 401:
                        print(f"    ✗ Ошибка авторизации (401). Проверьте API ключ.")
                        return None
                    
                    # Not Found - возможно метод не доступен для этого аккаунта
                    elif response.status_code == 404:
                        print(f"    ⚠ Метод не найден (404). Возможно не доступен для этого аккаунта.")
                        return []
                    
                    # Server error - повторяем с экспоненциальной задержкой
                    elif 500 <= response.status_code < 600:
                        delay = min(RETRY_DELAY * (3 ** attempt), 1800)  # Максимум 30 минут
                        print(f"    ⚠ Ошибка сервера ({response.status_code}). Ожидание {delay} сек (попытка {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                        continue
                    
                    # Другие ошибки (403 и т.д.) - не повторяем
                    else:
                        print(f"    ✗ Ошибка API ({response.status_code}): {response.text[:200]}")
                        return None
                        
                except requests.exceptions.Timeout:
                    delay = min(RETRY_DELAY * (2 ** attempt), 1800)  # Максимум 30 минут
                    print(f"    ⚠ Timeout. Ожидание {delay} сек (попытка {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        continue
                    else:
                        print(f"    ✗ Превышено время ожидания после {max_retries} попыток")
                        return None
                        
                except requests.exceptions.RequestException as e:
                    delay = min(RETRY_DELAY * (2 ** attempt), 1800)  # Максимум 30 минут
                    print(f"    ⚠ Ошибка запроса: {e}. Ожидание {delay} сек (попытка {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        continue
                    else:
                        print(f"    ✗ Ошибка соединения после {max_retries} попыток")
                        return None
                        
                except Exception as e:
                    print(f"    ✗ Неожиданная ошибка: {e}")
                    print(f"    Traceback: {traceback.format_exc()}")
                    return None
            
            # Если не удалось получить данные после всех попыток
            if attempt == max_retries - 1:
                print(f"    ✗ Не удалось получить данные для вкладки {tab}")
                break
        
        # Пауза между разными типами отчетов
        if tab != endpoint_info.get('tabs', ['penalty'])[-1]:
            time.sleep(RATE_LIMIT_DELAY)
    
    print(f"  ✓ Всего получено записей: {len(all_records)}")
    return all_records

def normalize_and_flatten_data(records, deduction_type):
    """
    Нормализует данные из API и разворачивает вложенные массивы.
    
    Структура ответов API:
    - antifraud-details: {'details': [{...}, {...}]} - массив удержаний за самовыкупы
    - incorrect-attachments: {'report': [{...}, {...}]} - массив удержаний за неверные вложения
    - goods-labeling: {'report': [{...}, {...}]} - массив удержаний за маркировку
    - characteristics-change: {'report': [{...}, {...}]} - массив удержаний за изменение характеристик
    - warehouse-measurements: [{'nmId': ..., 'dimId': ..., ...}, ...] - массив удержаний за габариты
    
    Args:
        records: список записей из API (обычно один элемент со вложенным массивом)
        deduction_type: тип удержания
    
    Returns:
        DataFrame с развернутыми данными (каждый элемент массива - отдельная строка)
    """
    if not records:
        return pd.DataFrame()
    
    try:
        # Специальная обработка для warehouse-measurements
        if deduction_type == 'warehouse-measurements':
            # Для warehouse-measurements records уже является списком объектов
            if isinstance(records, list) and len(records) > 0:
                df = pd.DataFrame(records)
                
                # Сохраняем оригинальные данные в JSONB колонку
                df['original_data'] = df.apply(lambda row: row.to_dict(), axis=1)
                
                # Нормализуем колонки - приводим к нижнему регистру и заменяем пробелы
                df.columns = df.columns.str.lower().str.replace(' ', '_').str.replace('-', '_')
                
                return df
            else:
                return pd.DataFrame()
        
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
            if col in ['nmid', 'nm_id', 'dimid', 'dim_id']:
                new_columns[col] = 'BIGINT'
            elif col in ['sum', 'amount', 'price', 'cost', 'prcover', 'volume', 'volumesup', 
                        'reversalamount', 'penaltyamount']:
                new_columns[col] = 'NUMERIC(15, 2)'
            elif col in ['datefrom', 'dateto', 'date_from_detail', 'date_to_detail', 'date', 
                        'dtbonus', 'isvaliddt']:
                new_columns[col] = 'VARCHAR(20)'
            elif col in ['currency', 'subject']:
                new_columns[col] = 'VARCHAR(255)'
            elif col in ['width', 'length', 'height', 'widthsup', 'lengthsup', 'heightsup']:
                new_columns[col] = 'INTEGER'
            elif col in ['isvalid']:
                new_columns[col] = 'BOOLEAN'
            elif col in ['photourls', 'tab_type', 'endpoint_type']:
                new_columns[col] = 'TEXT'
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
    Обрабатывает все типы удержаний для одного поставщика с циклами по 31 день.
    
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
        'by_type': {},
        'cycles_processed': 0,
        'cycles_failed': 0
    }
    
    print(f"\n{'='*80}")
    print(f"Обработка поставщика: {supplier}")
    print(f"Период: {date_from} - {date_to}")
    print(f"{'='*80}")
    
    # Обрабатываем каждый тип удержаний отдельно с учетом их особенностей
    for endpoint_key, endpoint_info in API_ENDPOINTS.items():
        print(f"\n📋 {endpoint_info['description']} ({endpoint_key})")
        
        # Получаем циклы для конкретного endpoint
        cycles = get_cycles_for_endpoint(endpoint_key, date_from, date_to)
        print(f"  📅 Циклов для {endpoint_info['description']}: {len(cycles)}")
        
        endpoint_stats = {
            'total_records': 0,
            'cycles_processed': 0,
            'cycles_failed': 0
        }
        
        # Обрабатываем каждый цикл для данного endpoint
        for cycle_idx, (cycle_start, cycle_end) in enumerate(cycles, 1):
            if len(cycles) > 1:
                print(f"  🔄 Цикл {cycle_idx}/{len(cycles)}: {cycle_start} - {cycle_end}")
            
            # Получаем данные с retry
            records = fetch_deductions_with_retry(api_key, endpoint_key, cycle_start, cycle_end)
            
            if records is None:
                print(f"    ✗ Не удалось получить данные")
                endpoint_stats['cycles_failed'] += 1
                continue
            
            if not records:
                print(f"    ℹ Данных нет за период {cycle_start} - {cycle_end}")
                endpoint_stats['cycles_failed'] += 1
                continue
            
            print(f"    ✓ Получено записей: {len(records)}")
            
            # Нормализуем данные
            df = normalize_and_flatten_data(records, endpoint_key)
            
            if df.empty:
                print(f"    ℹ Нет данных для сохранения (пустой массив)")
                endpoint_stats['cycles_failed'] += 1
                continue
            
            # Сохраняем в БД
            saved_count = save_deductions_to_db(
                engine, df, supplier, endpoint_key, 
                endpoint_info['description'], cycle_start, cycle_end,
                PG_SCHEMA, PG_TABLE
            )
            
            endpoint_stats['total_records'] += saved_count
            endpoint_stats['cycles_processed'] += 1
            
            # Пауза между циклами (кроме последнего)
            if cycle_idx < len(cycles):
                print(f"    ⏸ Пауза {CYCLE_PAUSE} сек перед следующим циклом...")
                time.sleep(CYCLE_PAUSE)
        
        # Обновляем общую статистику
        stats['total_records'] += endpoint_stats['total_records']
        stats['by_type'][endpoint_key] = endpoint_stats['total_records']
        stats['cycles_processed'] += endpoint_stats['cycles_processed']
        stats['cycles_failed'] += endpoint_stats['cycles_failed']
        
        print(f"  ✅ {endpoint_info['description']}: {endpoint_stats['total_records']} записей")
        
        # Адаптивные паузы между endpoint'ами
        if endpoint_key != list(API_ENDPOINTS.keys())[-1]:  # Не последний endpoint
            if len(stats['by_type']) % 3 == 0:
                print(f"  ⏸ Пауза {BURST_PAUSE} сек для соблюдения лимитов API")
                time.sleep(BURST_PAUSE)
            else:
                time.sleep(CYCLE_PAUSE)
    
    print(f"\n{'='*80}")
    print(f"Итого для {supplier}: {stats['total_records']} записей")
    print(f"Циклов обработано: {stats['cycles_processed']}")
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
    print(f"Настройки retry: {MAX_RETRIES} попыток, задержки до 30 мин")
    
    # Показываем информацию о циклах
    cycles = split_date_range_into_cycles(date_from, date_to, max_days=31)
    total_days = (datetime.strptime(date_to, '%Y-%m-%d') - datetime.strptime(date_from, '%Y-%m-%d')).days + 1
    print(f"Циклы: {len(cycles)} циклов по 31 день (всего {total_days} дней)")
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
        'auth_errors': 0,
        'total_records': 0,
        'total_cycles': 0,
        'cycles_processed': 0,
        'cycles_failed': 0,
        'by_type': {key: 0 for key in API_ENDPOINTS.keys()}
    }
    
    # Подсчитываем общее количество циклов
    total_cycles = 0
    for api_key, supplier in dict_api.items():
        cycles = split_date_range_into_cycles(date_from, date_to, max_days=31)
        total_cycles += len(cycles)
    global_stats['total_cycles'] = total_cycles
    
    # Обработка каждой компании
    print("\n🔄 НАЧАЛО ОБРАБОТКИ КОМПАНИЙ")
    print("="*80)
    
    for idx, (api_key, supplier) in enumerate(dict_api.items(), 1):
        print(f"\n[{idx}/{len(dict_api)}] Компания: {supplier}")
        
        try:
            stats = process_all_deductions_for_supplier(
                api_key, supplier, date_from, date_to
            )
            
            # Обновляем статистику циклов
            global_stats['cycles_processed'] += stats.get('cycles_processed', 0)
            global_stats['cycles_failed'] += stats.get('cycles_failed', 0)
            
            # Проверяем, была ли ошибка авторизации (если все типы удержаний вернули 0 записей)
            if stats['total_records'] == 0 and all(count == 0 for count in stats['by_type'].values()):
                print(f"\n⚠ Возможна ошибка авторизации для {supplier} - нет данных по всем типам удержаний")
                global_stats['auth_errors'] += 1
            else:
                global_stats['companies_processed'] += 1
                global_stats['total_records'] += stats['total_records']
                
                for deduction_type, count in stats['by_type'].items():
                    global_stats['by_type'][deduction_type] += count
                
                print(f"\n✅ Компания {supplier} обработана успешно")
            
        except Exception as e:
            print(f"\n✗ Ошибка обработки компании {supplier}: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            global_stats['companies_failed'] += 1
        
        # Пауза между компаниями (как в report_paid_storage.py)
        if idx < len(dict_api):
            print(f"\n⏸ Пауза {SUPPLIER_PAUSE} сек перед следующей компанией...")
            time.sleep(SUPPLIER_PAUSE)
    
    # Итоговая статистика
    print("\n" + "="*80)
    print("📊 ИТОГОВАЯ СТАТИСТИКА")
    print("="*80)
    print(f"\n🏢 Обработано компаний: {global_stats['companies_processed']}/{len(dict_api)}")
    print(f"❌ Ошибок: {global_stats['companies_failed']}")
    print(f"🔐 Ошибок авторизации: {global_stats['auth_errors']}")
    print(f"📊 Всего записей: {global_stats['total_records']}")
    print(f"🔄 Циклов обработано: {global_stats['cycles_processed']}/{global_stats['total_cycles']}")
    print(f"⚠ Циклов без данных: {global_stats['cycles_failed']}")
    
    print(f"\n📋 По типам удержаний:")
    for deduction_type, count in global_stats['by_type'].items():
        desc = API_ENDPOINTS[deduction_type]['description']
        print(f"  • {desc}: {count}")
    
    print(f"\n💾 Данные сохранены в PostgreSQL:")
    print(f"   База данных: {PG_DB}")
    print(f"   Схема.Таблица: {PG_SCHEMA}.{PG_TABLE}")
    print(f"   Хост: {PG_HOST}")
    
    # Дополнительная статистика по циклам
    if global_stats['total_cycles'] > 0:
        cycle_success_rate = (global_stats['cycles_processed'] / global_stats['total_cycles']) * 100
        print(f"\n📈 Эффективность циклов: {cycle_success_rate:.1f}%")
    
    print("\n" + "="*80)
    print("✅ ПРОЦЕСС ЗАВЕРШЕН!")
    print("="*80)
    print(f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Период обработки: {date_from} - {date_to}")
    print(f"Всего циклов: {global_stats['total_cycles']}")
    print("="*80)

def test_warehouse_measurements():
    """
    Тестовая функция для проверки warehouse-measurements только для ИП Баах Р
    """
    print("="*80)
    print("ТЕСТОВЫЙ РЕЖИМ: WAREHOUSE-MEASUREMENTS ДЛЯ ИП БААХ Р")
    print("="*80)
    
    # Инициализация БД
    print("\n📊 ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ")
    print("-"*80)
    
    if not create_schema_if_not_exists(engine, PG_SCHEMA):
        print("⚠ Продолжаем без схемы (может быть ошибка)")
    
    if not create_deductions_table(engine, PG_SCHEMA, PG_TABLE):
        print("⚠ Ошибка создания таблицы")
        return
    
    # Загрузка данных для ИП Баах Р
    print("\n👤 ЗАГРУЗКА ДАННЫХ ДЛЯ ИП БААХ Р")
    print("-"*80)
    
    try:
        df_investors = get_sheet_data_as_dataframe(cred_path, SPREADSHEET_KEY, SHEET_NAME)
        df_investors = df_investors[
            (df_investors['API ключ'] != '') & 
            (df_investors['API ключ'].notna())
        ]
        
        # Фильтруем только ИП Баах Р
        df_baah = df_investors[df_investors['Имя Юрлица'].str.contains('Баах', case=False, na=False)]
        
        if df_baah.empty:
            print("✗ ИП Баах Р не найден в таблице")
            return
        
        supplier = df_baah.iloc[0]['Имя Юрлица']
        api_key = df_baah.iloc[0]['API ключ']
        
        print(f"✓ Найден поставщик: {supplier}")
        
    except Exception as e:
        print(f"✗ Ошибка загрузки данных: {e}")
        return
    
    # Тестируем только warehouse-measurements с коротким периодом
    test_date_from = '2025-10-01'  # Короткий период для теста
    test_date_to = '2025-10-20'
    
    print(f"\n🧪 ТЕСТИРОВАНИЕ WAREHOUSE-MEASUREMENTS")
    print(f"Поставщик: {supplier}")
    print(f"Период: {test_date_from} - {test_date_to}")
    print("="*80)
    
    try:
        # Получаем данные
        records = fetch_warehouse_measurements_with_pagination(api_key, 'warehouse-measurements', test_date_from, test_date_to)
        
        if records is None:
            print("✗ Не удалось получить данные")
            return
        
        if not records:
            print("ℹ Нет данных за указанный период")
            return
        
        print(f"✓ Получено записей: {len(records)}")
        
        # Нормализуем данные
        df = normalize_and_flatten_data(records, 'warehouse-measurements')
        
        if df.empty:
            print("ℹ Нет данных для сохранения")
            return
        
        print(f"✓ Данные нормализованы: {len(df)} строк, {len(df.columns)} колонок")
        print(f"📋 Колонки: {list(df.columns)}")
        
        # Сохраняем в БД
        saved_count = save_deductions_to_db(
            engine, df, supplier, 'warehouse-measurements', 
            'Занижение габаритов упаковки', test_date_from, test_date_to,
            PG_SCHEMA, PG_TABLE
        )
        
        print(f"✓ Сохранено в БД: {saved_count} записей")
        
    except Exception as e:
        print(f"✗ Ошибка тестирования: {e}")
        print(f"Traceback: {traceback.format_exc()}")
    
    print("\n" + "="*80)
    print("✅ ТЕСТ ЗАВЕРШЕН!")
    print("="*80)

if __name__ == "__main__":
    # Раскомментируйте нужную функцию для запуска
    main()
    # test_warehouse_measurements()  # Раскомментируйте для тестирования
