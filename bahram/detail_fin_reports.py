#!/usr/bin/env python3

import requests
import pandas as pd
from sqlalchemy import text, create_engine
from datetime import datetime, timedelta
import time
import gspread
import os
import gc

# For local testing; switch to remote for prod server: 'postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah'
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

# Tunables (can be overridden via env)
WB_API_LIMIT = int(os.getenv('WB_API_LIMIT', '5000'))  # smaller chunks to reduce memory
REQUEST_TIMEOUT_CONNECT = int(os.getenv('REQUEST_TIMEOUT_CONNECT', '10'))
REQUEST_TIMEOUT_READ = int(os.getenv('REQUEST_TIMEOUT_READ', '300'))
TO_SQL_CHUNKSIZE = int(os.getenv('TO_SQL_CHUNKSIZE', '1000'))
RATE_LIMIT_SECONDS = int(os.getenv('RATE_LIMIT_SECONDS', '60'))

# Google Sheets setup - relative path for server compatibility
cred_path = os.path.join(os.path.dirname(__file__), 'cred.json')
gs_client = gspread.service_account(filename=cred_path)
worksheet = gs_client.open_by_key("15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ").sheet1
df_investors = pd.DataFrame(worksheet.get_all_records())
df_investors = df_investors[(df_investors['API ключ'] != '') & (df_investors['API ключ'] != None)]

dict_api = dict(zip(df_investors['API ключ'], df_investors['Имя Юрлица']))

# Configurable dates - for testing, use small period; for full, '2024-01-29'
start_date = (datetime.now() - timedelta(days=628)).strftime('%Y-%m-%d')  # Last 14 days as requested
end_date = datetime.today().strftime('%Y-%m-%d')

def fetch_report_chunk(api_key, date_from, date_to, rrdid):
    """
    Fetch a single chunk of the report.
    """
    url = "https://statistics-api.wildberries.ru/api/v5/supplier/reportDetailByPeriod"
    headers = {
        'Authorization': api_key,
        'Content-Type': 'application/json'
    }
    params = {
        'dateFrom': date_from,
        'dateTo': date_to,
        'rrdid': rrdid,
        'limit': WB_API_LIMIT
    }
    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=(REQUEST_TIMEOUT_CONNECT, REQUEST_TIMEOUT_READ)
        )
    except requests.RequestException as e:
        print(f"HTTP error for key {api_key[:10]}...: {e}. Skipping chunk.")
        return None, 0

    if response.status_code == 401:
        print("API unauthorized (401): access token expired; обновите токен в кабинете WB. Поставщик будет пропущен.")
        return None, 0

    if response.status_code != 200:
        print(f"API request failed for key {api_key[:10]}... with status {response.status_code}: {response.text[:200]}.")
        return None, 0

    try:
        data = response.json()
    except ValueError as e:
        print(f"Failed to parse JSON for key {api_key[:10]}...: {e}")
        return None, 0
    if not data:
        return pd.DataFrame(), 0
    df = pd.DataFrame(data)
    df.columns = df.columns.str.lower()  # Normalize to lowercase
    next_rrdid = data[-1].get('rrd_id', 0) if len(data) == WB_API_LIMIT else 0
    return df, next_rrdid

def schema_exists(engine, schema):
    """
    Check if schema exists.
    """
    query = text(f"""
        SELECT EXISTS (
            SELECT FROM information_schema.schemata 
            WHERE schema_name = '{schema}'
        );
    """)
    try:
        result = pd.read_sql(query, engine).iloc[0, 0]
        return bool(result)
    except Exception as e:
        print(f"Error checking schema existence: {e}")
        return False

def create_schema_if_not_exists(engine, schema):
    """
    Create schema if it doesn't exist.
    """
    if not schema_exists(engine, schema):
        create_query = text(f'CREATE SCHEMA IF NOT EXISTS {schema}')
        try:
            with engine.connect() as conn:
                conn.execute(create_query)
                conn.commit()
            print(f"Created schema {schema}.")
        except Exception as e:
            print(f"Error creating schema {schema}: {e}")

def table_exists(engine, schema, table_name):
    """
    Check if table exists in the specified schema.
    """
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
        print(f"Error checking table existence: {e}")
        return False

def ensure_table_columns(engine, sample_df, schema, table_name):
    """
    Dynamically add missing columns to the table to handle new API fields.
    Uses TEXT type for flexibility; creates schema and table if they don't exist.
    """
    # Ensure schema exists
    create_schema_if_not_exists(engine, schema)
    
    df_cols = set(sample_df.columns)
    
    full_table = f"{schema}.{table_name}"
    
    if not table_exists(engine, schema, table_name):
        # Create empty table with correct columns only (no data to avoid duplication/memory spike)
        sample_df_empty = sample_df.head(0).copy()
        sample_df_empty['supplier'] = pd.Series(dtype='object')
        sample_df_empty['update_time'] = pd.Series(dtype='object')
        sample_df_empty.to_sql(table_name, engine, schema=schema, if_exists='replace', index=False, method='multi')
        print(f"Created empty table {full_table} with initial columns.")
        return
    
    # Get existing table columns
    query = text(f"""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = '{schema}' AND table_name = '{table_name}'
    """)
    try:
        existing_cols = pd.read_sql(query, engine)['column_name'].tolist()
    except Exception as e:
        print(f"Error fetching existing columns: {e}")
        return
    existing_set = set(existing_cols)
    new_cols = df_cols - existing_set
    if new_cols:
        for col in new_cols:
            col_name = f'"{col}"' if ' ' in col or not col[0].isalpha() else col  # Quote if needed
            alter_query = text(f'ALTER TABLE {full_table} ADD COLUMN IF NOT EXISTS {col_name} TEXT')
            try:
                with engine.connect() as conn:
                    conn.execute(alter_query)
                    conn.commit()
            except Exception as e:
                print(f"Error adding column {col}: {e}")
        print(f"Added new columns to {full_table}: {new_cols}")

def count_supplier_rows_in_db(engine, schema, table_name, supplier, start_date, end_date):
    """
    Подсчитывает количество уникальных строк по rrd_id для поставщика в БД за указанный период.
    """
    full_table = f"{schema}.{table_name}"
    count_query = text(f"""
        SELECT COUNT(DISTINCT rrd_id) as unique_count,
               COUNT(*) as total_count
        FROM {full_table}
        WHERE supplier = :supplier
          AND rrd_id IS NOT NULL
          AND NULLIF(btrim(rrd_id::text), '') IS NOT NULL
          AND date_trunc('day', CAST(rr_dt AS timestamp)) >= CAST(:start_date AS date)
          AND date_trunc('day', CAST(rr_dt AS timestamp)) <= CAST(:end_date AS date)
    """)
    try:
        with engine.connect() as conn:
            result = conn.execute(count_query, {
                'supplier': supplier,
                'start_date': start_date,
                'end_date': end_date
            })
            row = result.fetchone()
            return row[0], row[1]  # unique_count, total_count
    except Exception as e:
        print(f"Error counting rows for {supplier}: {e}")
        return 0, 0

def deduplicate_supplier_by_rrd_id(engine, schema, table_name, supplier):
    """
    Финальная дедупликация: для заданного поставщика удаляем дубли по rrd_id,
    оставляя запись с максимальным update_time. Пустые/NULL rrd_id игнорируются.
    Возвращает количество удаленных строк.
    """
    full_table = f"{schema}.{table_name}"
    # Удаляем все строки, которые не первые в разбиении по (supplier, rrd_id)
    # Оставляем наиболее свежую по update_time (TEXT в формате ISO, сравнение лексикографическое подходит)
    delete_sql = text(
        f"""
        WITH marked AS (
          SELECT ctid,
                 row_number() OVER (
                   PARTITION BY supplier, NULLIF(btrim(rrd_id::text), '')
                   ORDER BY (update_time::timestamp) DESC
                 ) AS rn
          FROM {full_table}
          WHERE supplier = :supplier
            AND rrd_id IS NOT NULL
            AND NULLIF(btrim(rrd_id::text), '') IS NOT NULL
        )
        DELETE FROM {full_table} t
        USING marked d
        WHERE t.ctid = d.ctid AND d.rn > 1;
        """
    )
    try:
        with engine.connect() as conn:
            result = conn.execute(delete_sql, { 'supplier': supplier })
            deleted_count = result.rowcount
            conn.commit()
        print(f"Deduplicated by rrd_id for {supplier}: удалено {deleted_count} дублей")
        return deleted_count
    except Exception as e:
        print(f"Error in final dedup by rrd_id for {supplier}: {e}")
        return 0

def save_chunk_to_db(df_chunk, supplier, engine, schema, table_name):
    """
    Append a chunk of data to the database with supplier and update_time.
    """
    if not df_chunk.empty:
        df_chunk = df_chunk.copy()
        df_chunk['supplier'] = supplier
        df_chunk['update_time'] = str(datetime.now())  # String for TEXT
        try:
            df_chunk.to_sql(
                table_name,
                engine,
                schema=schema,
                if_exists='append',
                index=False,
                method='multi',
                chunksize=TO_SQL_CHUNKSIZE
            )
            print(f"Saved {len(df_chunk)} rows for {supplier}")
        except Exception as e:
            print(f"Error saving chunk for {supplier}: {e}")
        finally:
            # Free memory promptly
            del df_chunk
            gc.collect()

def get_detail_fin_report_all_suppliers(dict_api, start_date, end_date):
    """
    Fetch and save reports for all suppliers in chunks to minimize memory usage.
    Handles pagination with rrdid and dynamic schema updates.
    """
    schema = 'reports'
    table_name = 'detail_finance_reports'
    
    # Test DB connection first
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Database connection successful.")
    except Exception as e:
        print(f"Database connection failed: {e}. Check credentials/network.")
        return
    
    for api_key, supplier in dict_api.items():
        print(f"\n{'='*80}")
        print(f"Processing supplier: {supplier}")
        print(f"{'='*80}")
        rrdid = 0
        sample_df = None
        total_rows_from_api = 0
        unique_rrd_ids_from_api = set()
        
        # First, try to fetch a sample chunk to get columns
        try:
            first_df, next_rrdid = fetch_report_chunk(api_key, start_date, end_date, rrdid)
        except MemoryError:
            print(f"MemoryError during first chunk for {supplier}. Consider reducing WB_API_LIMIT.")
            continue
        if first_df is None or first_df.empty:
            print(f"No data or API error for {supplier}")
            continue
        
        sample_df = first_df
        ensure_table_columns(engine, sample_df, schema, table_name)
        save_chunk_to_db(first_df, supplier, engine, schema, table_name)
        
        # Собираем статистику по API данным
        total_rows_from_api += len(first_df)
        if 'rrd_id' in first_df.columns:
            unique_rrd_ids_from_api.update(first_df['rrd_id'].dropna().astype(str).str.strip().tolist())
        
        # Continue with remaining chunks
        rrdid = next_rrdid
        while rrdid != 0:
            try:
                df_chunk, next_rrdid = fetch_report_chunk(api_key, start_date, end_date, rrdid)
            except MemoryError:
                print(f"MemoryError on chunk for {supplier}. Reduce WB_API_LIMIT or increase RAM.")
                break
            if df_chunk is None or df_chunk.empty:
                break
            save_chunk_to_db(df_chunk, supplier, engine, schema, table_name)
            
            # Собираем статистику
            total_rows_from_api += len(df_chunk)
            if 'rrd_id' in df_chunk.columns:
                unique_rrd_ids_from_api.update(df_chunk['rrd_id'].dropna().astype(str).str.strip().tolist())
            
            rrdid = next_rrdid
            time.sleep(RATE_LIMIT_SECONDS)  # Rate limit
        
        # Финальная дедупликация после вставки всех чанков поставщика
        deleted_count = deduplicate_supplier_by_rrd_id(engine, schema, table_name, supplier)
        
        # Проверка: считаем строки в БД после дедупликации
        unique_in_db, total_in_db = count_supplier_rows_in_db(engine, schema, table_name, supplier, start_date, end_date)
        
        # Выводим отчет
        print(f"\n{'-'*80}")
        print(f"ОТЧЕТ ДЛЯ ПОСТАВЩИКА: {supplier}")
        print(f"{'-'*80}")
        print(f"📊 Данные полученные из API:")
        print(f"   • Всего строк получено: {total_rows_from_api}")
        print(f"   • Уникальных rrd_id: {len(unique_rrd_ids_from_api)}")
        print(f"\n💾 Данные в БД после дедупликации:")
        print(f"   • Всего строк в БД: {total_in_db}")
        print(f"   • Уникальных rrd_id в БД: {unique_in_db}")
        print(f"   • Удалено дублей: {deleted_count}")
        print(f"\n✅ Проверка целостности:")
        
        # Расчет разницы
        diff_unique = len(unique_rrd_ids_from_api) - unique_in_db
        match_status = "✅ СОВПАДАЕТ" if diff_unique == 0 else f"⚠️ РАСХОЖДЕНИЕ: {abs(diff_unique)} записей"
        
        print(f"   • Уникальные rrd_id (API vs БД): {match_status}")
        
        if diff_unique != 0:
            print(f"   ⚠️ ВНИМАНИЕ: Количество уникальных записей не совпадает!")
            print(f"      API: {len(unique_rrd_ids_from_api)} | БД: {unique_in_db} | Разница: {diff_unique}")
        
        print(f"{'-'*80}\n")
    
    print("\n" + "="*80)
    print("All suppliers processed.")
    print("="*80)

if __name__ == "__main__":
    get_detail_fin_report_all_suppliers(dict_api, start_date, end_date)
