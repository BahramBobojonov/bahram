#!/usr/bin/env python3

import gspread
import requests
import pandas as pd
from datetime import datetime, timedelta
import time
from sqlalchemy import create_engine, text

# Database connection
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

# Dates for last 60 days (will be split into cycles of 31 days max)
date_from = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
date_to = datetime.now().strftime('%Y-%m-%d')

#credentials_file = '/home/baakhofficial/wbauto/bahram/cred.json'
credentials_file = r"cred.json"
spreadsheet_key = "15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ"
sheet_name = "Инвесторы"  # Укажите имя листа

def split_date_range(start_date_str, end_date_str, max_days=31):
    """
    Разбивает период на циклы по максимум max_days дней.
    :param start_date_str: Начальная дата в формате 'YYYY-MM-DD'
    :param end_date_str: Конечная дата в формате 'YYYY-MM-DD'
    :param max_days: Максимальное количество дней в одном цикле (по умолчанию 31)
    :return: Список кортежей (start_date, end_date) для каждого цикла
    """
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    
    cycles = []
    current_start = start_date
    
    while current_start < end_date:
        # Вычисляем конец текущего цикла
        current_end = min(current_start + timedelta(days=max_days-1), end_date)
        
        cycles.append((
            current_start.strftime('%Y-%m-%d'),
            current_end.strftime('%Y-%m-%d')
        ))
        
        # Переходим к следующему циклу
        current_start = current_end + timedelta(days=1)
    
    return cycles

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

def fetch_data_for_period(api_key, start_date, end_date):
    """
    Получает данные за указанный период, разбивая его на циклы по 31 день.
    :param api_key: API ключ
    :param start_date: Начальная дата в формате 'YYYY-MM-DD'
    :param end_date: Конечная дата в формате 'YYYY-MM-DD'
    :return: Список всех данных за период
    """
    url = "https://advert-api.wildberries.ru/adv/v1/upd"
    headers = {'Authorization': api_key}
    
    # Разбиваем период на циклы по 31 день
    cycles = split_date_range(start_date, end_date, max_days=31)
    all_data = []
    
    print(f"Обрабатываем период {start_date} - {end_date} в {len(cycles)} циклах")
    
    for i, (cycle_start, cycle_end) in enumerate(cycles, 1):
        print(f"Цикл {i}/{len(cycles)}: {cycle_start} - {cycle_end}")
        
        params = {'from': cycle_start, 'to': cycle_end}
        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            cycle_data = response.json()
            all_data.extend(cycle_data)
            print(f"Получено {len(cycle_data)} записей за цикл {i}")
        elif response.status_code == 401:
            print("Ошибка: неверный API-ключ или доступ запрещен.")
            return None
        elif response.status_code == 429:
            print("Превышен лимит запросов. Ожидание 5 секунд...")
            time.sleep(5)
            # Повторяем запрос
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                cycle_data = response.json()
                all_data.extend(cycle_data)
                print(f"Получено {len(cycle_data)} записей за цикл {i} (повторный запрос)")
            else:
                print(f"Ошибка при повторном запросе: {response.status_code} - {response.text}")
                return None
        else:
            print(f"Ошибка в цикле {i}: {response.status_code} - {response.text}")
            return None
        
        # Соблюдаем лимит запросов (1 запрос в секунду)
        if i < len(cycles):  # Не ждем после последнего цикла
            time.sleep(1)
    
    print(f"Всего получено {len(all_data)} записей за весь период")
    return all_data

def get_column_type(col):
    if col in ['updnum', 'advertid', 'adverttype', 'advertstatus', 'updsum']:
        return 'integer'
    elif col == 'updtime':
        return 'timestamp without time zone'
    elif col in ['campname', 'paymenttype', 'supplier']:
        return 'varchar(500)'
    else:
        return 'text'

def ensure_schema(engine, schema):
    create_schema_query = text(f"CREATE SCHEMA IF NOT EXISTS {schema};")
    with engine.begin() as conn:
        conn.execute(create_schema_query)
    print(f"Schema {schema} ensured")

def create_table_if_not_exists(engine, schema, table_name):
    create_query = text(f"""
        CREATE TABLE IF NOT EXISTS {schema}.{table_name} (
            updnum INTEGER,
            updtime TIMESTAMP WITHOUT TIME ZONE,
            updsum INTEGER,
            advertid INTEGER,
            campname VARCHAR(500),
            adverttype INTEGER,
            paymenttype VARCHAR(500),
            advertstatus INTEGER,
            supplier VARCHAR(500)
        );
    """)
    with engine.begin() as conn:
        conn.execute(create_query)
    print(f"Table {schema}.{table_name} created if not exists")

def ensure_columns(engine, schema, table_name, columns):
    core_columns = ['updnum', 'updtime', 'updsum', 'advertid', 'campname', 'adverttype', 'paymenttype', 'advertstatus', 'supplier']
    for col in columns:
        if col not in core_columns:
            dtype = get_column_type(col)
            alter_query = text(f"""
                ALTER TABLE {schema}.{table_name}
                ADD COLUMN IF NOT EXISTS "{col}" {dtype};
            """)
            with engine.begin() as conn:
                conn.execute(alter_query)
            print(f"Added new column {col} with type {dtype}")

def rename_legacy_columns(engine, schema, table_name):
    renames = {
        'updtim': 'updtime',
        'camp_name': 'campname',
        'advert_type': 'adverttype',
        'payment_type': 'paymenttype',
        'advert_status': 'advertstatus',
    }
    for old_col, new_col in renames.items():
        try:
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE {schema}.{table_name} RENAME COLUMN "{old_col}" TO "{new_col}";'))
            print(f"Renamed column {old_col} to {new_col}")
        except Exception as e:
            # Skip if column does not exist
            if 'does not exist' in str(e).lower():
                continue
            print(f"Error renaming column {old_col} to {new_col}: {e}")

def deduplicate_table(engine, schema, table_name):
    # Поля для дедупликации
    dedup_columns = ['updnum', 'updtime', 'updsum', 'advertid', 'campname', 'paymenttype', 'adverttype', 'supplier']
    
    dedup_sql = text(f"""
    CREATE TEMP TABLE tmp_dedup AS
    SELECT DISTINCT ON ({', '.join(dedup_columns)})
        *
    FROM {schema}.{table_name}
    ORDER BY {', '.join(dedup_columns)}, updtime DESC;
    
    TRUNCATE TABLE {schema}.{table_name};
    
    INSERT INTO {schema}.{table_name}
    SELECT * FROM tmp_dedup;
    
    DROP TABLE tmp_dedup;
    """)
    with engine.begin() as conn:
        conn.execute(dedup_sql)
    print(f"Deduplicated {schema}.{table_name} by columns: {', '.join(dedup_columns)}")

# Get API keys from sheet
df = get_sheet_data_as_dataframe(credentials_file, spreadsheet_key, sheet_name)
df = df[(df['API ключ'] != '') & (df['API ключ'] != None) & ~((df['Имя Юрлица'] == 'TD') | (df['Имя Юрлица'] == 'ИП Крапивина С.А.'))]

#df = df[df['Имя Юрлица']=='ИП Баах И.Л.']
dict_api = dict(zip(df['API ключ'], df['Имя Юрлица']))

# Ensure schema and create table if not exists
ensure_schema(engine, 'analytics')
create_table_if_not_exists(engine, 'analytics', 'adv_upd')
rename_legacy_columns(engine, 'analytics', 'adv_upd')

# Note: No deletion of old data - only adding new data

# Flag to ensure columns only once
has_ensured = False

# Process each company
for api_key, company_name in dict_api.items():
    print(f"\n=== Обработка компании: {company_name} (API Key: {api_key[:10]}...) ===")
    data = fetch_data_for_period(api_key, date_from, date_to)

    if data:
        for item in data:
            item['supplier'] = company_name
        temp_df = pd.DataFrame(data)

        # Process updTime
        if 'updTime' in temp_df.columns:
            temp_df['updTime'] = temp_df['updTime'].astype(str).str[:19]
            temp_df['updTime'] = pd.to_datetime(temp_df['updTime'], errors='coerce')

        # Lowercase column names
        temp_df.columns = temp_df.columns.str.lower()

        # Ensure table has all columns (dynamic) on first successful fetch
        if not has_ensured and len(temp_df) > 0:
            ensure_columns(engine, 'analytics', 'adv_upd', temp_df.columns.tolist())
            has_ensured = True

        # Insert data (low memory: per company)
        temp_df.to_sql(
            name='adv_upd',
            con=engine,
            schema='analytics',
            if_exists='append',
            index=False,
            method='multi',
            chunksize=1000
        )
        print(f"Вставлено {len(data)} записей для {company_name}")
    else:
        print(f"Данные не получены для {company_name}")

    print(f"Завершена обработка компании: {company_name}")
    time.sleep(2)  # Дополнительная пауза между компаниями

deduplicate_table(engine, 'analytics', 'adv_upd')
print(f"\n=== Процесс завершен успешно ===")
print(f"Обработан период: {date_from} - {date_to}")
print(f"Количество компаний: {len(dict_api)}")
print("Все данные сохранены в таблице analytics.adv_upd")