#!/usr/bin/env python3

import gspread
import requests
import pandas as pd
from datetime import datetime, timedelta
import time
from sqlalchemy import create_engine, text

# Database connection
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

# Dates for last 31 days (API max interval)
date_from = (datetime.now() - timedelta(days=31)).strftime('%Y-%m-%d')
date_to = datetime.now().strftime('%Y-%m-%d')

#credentials_file = '/home/baakhofficial/wbauto/bahram/cred.json'
credentials_file = r"cred.json"
spreadsheet_key = "15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ"
sheet_name = "Инвесторы"  # Укажите имя листа

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

def fetch_data(api_key, start_date, end_date):
    url = "https://advert-api.wildberries.ru/adv/v1/upd"
    headers = {'Authorization': api_key}
    params = {'from': start_date, 'to': end_date}
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        return response.json()
    elif response.status_code == 401:
        print("Ошибка: неверный API-ключ или доступ запрещен.")
        return None
    else:
        print(f"Ошибка: {response.status_code} - {response.text}")
        return None

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
    dedup_sql = text(f"""
    CREATE TEMP TABLE tmp_dedup AS
    SELECT DISTINCT * FROM {schema}.{table_name};
    TRUNCATE TABLE {schema}.{table_name};
    INSERT INTO {schema}.{table_name}
    SELECT * FROM tmp_dedup;
    DROP TABLE tmp_dedup;
    """)
    with engine.begin() as conn:
        conn.execute(dedup_sql)
    print(f"Deduplicated {schema}.{table_name} by all columns")

# Get API keys from sheet
df = get_sheet_data_as_dataframe(credentials_file, spreadsheet_key, sheet_name)
df = df[(df['API ключ'] != '') & (df['API ключ'] != None) & ~((df['Имя Юрлица'] == 'TD') | (df['Имя Юрлица'] == 'ИП Крапивина С.А.'))]

#df = df[df['Имя Юрлица']=='ИП Баах И.Л.']
dict_api = dict(zip(df['API ключ'], df['Имя Юрлица']))

# Ensure schema and create table if not exists
ensure_schema(engine, 'analytics')
create_table_if_not_exists(engine, 'analytics', 'adv_upd')
rename_legacy_columns(engine, 'analytics', 'adv_upd')

# Delete old data for the period
delete_query = f"""
DELETE FROM analytics.adv_upd
WHERE updtime >= '{date_from}'
"""
try:
    with engine.begin() as connection:
        connection.execute(text(delete_query))
    print(f"Deleted old data from {date_from}")
except Exception as e:
    if "does not exist" in str(e):
        print("Table does not exist, skipping delete")
    else:
        print(f"Error during delete: {e}")

# Flag to ensure columns only once
has_ensured = False

# Process each company
for api_key, company_name in dict_api.items():
    print(f"Processing company: {company_name} (API Key: {api_key[:10]}...)")
    data = fetch_data(api_key, date_from, date_to)

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
        print(f"Inserted {len(data)} records for {company_name}")
    else:
        print(f"No data fetched for {company_name}")

    time.sleep(1)  # Rate limit respect

deduplicate_table(engine, 'analytics', 'adv_upd')
print("Process completed successfully")