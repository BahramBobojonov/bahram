#!/usr/bin/env python3

import requests
import pandas as pd
from sqlalchemy import text, create_engine
from datetime import datetime, timedelta
import time
import gspread
import os
import gc
import argparse
from typing import Optional, Dict
import re

# DB engine (повторяет подход проекта)
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

# Настройки
WB_API_LIMIT = int(os.getenv('WB_API_LIMIT', '5000'))
REQUEST_TIMEOUT_CONNECT = int(os.getenv('REQUEST_TIMEOUT_CONNECT', '10'))
REQUEST_TIMEOUT_READ = int(os.getenv('REQUEST_TIMEOUT_READ', '300'))
TO_SQL_CHUNKSIZE = int(os.getenv('TO_SQL_CHUNKSIZE', '1000'))
RATE_LIMIT_SECONDS = int(os.getenv('RATE_LIMIT_SECONDS', '60'))

# Google Sheets
cred_path = os.path.join(os.path.dirname(__file__), 'cred.json')
gs_client = gspread.service_account(filename=cred_path)
worksheet = gs_client.open_by_key("15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ").sheet1

def _normalize_name(value: str) -> str:
    v = (value or "").lower()
    v = re.sub(r"[\s\._\-\u00AB\u00BB\(\)\[\]\{\},]+", "", v)
    return v


def build_api_dict(target_supplier: Optional[str] = None) -> Dict[str, str]:
    df_investors = pd.DataFrame(worksheet.get_all_records())
    df_investors = df_investors[(df_investors['API ключ'] != '') & (df_investors['API ключ'] != None)]
    if target_supplier:
        target_norm = _normalize_name(target_supplier)
        mask = df_investors['Имя Юрлица'].apply(lambda x: target_norm in _normalize_name(str(x)))
        df_investors = df_investors[mask]
    return dict(zip(df_investors['API ключ'], df_investors['Имя Юрлица']))

# Даты по умолчанию (последние 14 дней, можно переопределять через ENV/CLI)
DEFAULT_DAYS = int(os.getenv('WB_DAYS_BACK', '14'))
DEFAULT_START_DATE = (datetime.now() - timedelta(days=DEFAULT_DAYS)).strftime('%Y-%m-%d')
DEFAULT_END_DATE = datetime.today().strftime('%Y-%m-%d')


def fetch_report_chunk_daily(api_key, date_from, date_to, rrdid):
    url = "https://statistics-api.wildberries.ru/api/v5/supplier/reportDetailByPeriod"
    headers = {
        'Authorization': api_key,
        'Content-Type': 'application/json'
    }
    params = {
        'dateFrom': date_from,
        'dateTo': date_to,
        'rrdid': rrdid,
        'limit': WB_API_LIMIT,
        'period': 'daily'
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
        print("API unauthorized (401): обновите токен в кабинете WB. Поставщик будет пропущен.")
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
    df.columns = df.columns.str.lower()
    next_rrdid = data[-1].get('rrd_id', 0) if len(data) == WB_API_LIMIT else 0
    return df, next_rrdid


def schema_exists(engine, schema):
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
    create_schema_if_not_exists(engine, schema)
    df_cols = set(sample_df.columns)
    full_table = f"{schema}.{table_name}"

    if not table_exists(engine, schema, table_name):
        sample_df_empty = sample_df.head(0).copy()
        sample_df_empty['supplier'] = pd.Series(dtype='object')
        sample_df_empty['update_time'] = pd.Series(dtype='object')
        sample_df_empty.to_sql(table_name, engine, schema=schema, if_exists='replace', index=False, method='multi')
        print(f"Created empty table {full_table} with initial columns.")
        return

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
            col_name = f'"{col}"' if ' ' in col or not col[0].isalpha() else col
            alter_query = text(f'ALTER TABLE {full_table} ADD COLUMN IF NOT EXISTS {col_name} TEXT')
            try:
                with engine.connect() as conn:
                    conn.execute(alter_query)
                    conn.commit()
            except Exception as e:
                print(f"Error adding column {col}: {e}")
        print(f"Added new columns to {full_table}: {new_cols}")


def deduplicate_supplier_by_rrd_id(engine, schema, table_name, supplier):
    full_table = f"{schema}.{table_name}"
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
            conn.execute(delete_sql, { 'supplier': supplier })
            conn.commit()
        print(f"Deduplicated by rrd_id at end for {supplier}")
    except Exception as e:
        print(f"Error in final dedup by rrd_id for {supplier}: {e}")


def save_chunk_to_db(df_chunk, supplier, engine, schema, table_name) -> int:
    if not df_chunk.empty:
        df_chunk = df_chunk.copy()
        df_chunk['supplier'] = supplier
        df_chunk['update_time'] = str(datetime.now())
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
            saved = len(df_chunk)
            print(f"Saved {saved} rows for {supplier}")
            return saved
        except Exception as e:
            print(f"Error saving chunk for {supplier}: {e}")
            return 0
        finally:
            del df_chunk
            gc.collect()
    return 0


def count_db_rows(engine, schema, table_name, supplier, date_from, date_to) -> int:
    full_table = f"{schema}.{table_name}"
    query = text(
        f"""
        SELECT COUNT(*)
        FROM {full_table}
        WHERE supplier = :supplier
          AND rr_dt IS NOT NULL
          AND NULLIF(btrim(rr_dt), '') IS NOT NULL
          AND (rr_dt::date BETWEEN :date_from::date AND :date_to::date)
        """
    )
    try:
        with engine.connect() as conn:
            res = conn.execute(query, {
                'supplier': supplier,
                'date_from': date_from,
                'date_to': date_to
            })
            return int(list(res.fetchone() or [0])[0])
    except Exception as e:
        print(f"Error counting DB rows: {e}")
        return -1


def get_detail_fin_report_daily_all_suppliers(dict_api, start_date, end_date):
    schema = 'reports'
    table_name = 'detail_finance_reports_daily'

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Database connection successful.")
    except Exception as e:
        print(f"Database connection failed: {e}. Check credentials/network.")
        return

    # Подготовка списка дней
    try:
        start_dt = datetime.fromisoformat(start_date).date()
        end_dt = datetime.fromisoformat(end_date).date()
    except Exception:
        print("Invalid dates provided, expected YYYY-MM-DD")
        return

    num_days = (end_dt - start_dt).days + 1
    days = [start_dt + timedelta(days=i) for i in range(max(0, num_days))]

    for api_key, supplier in dict_api.items():
        print(f"Processing supplier: {supplier}")
        fetched_rows_total = 0
        saved_rows_total = 0
        table_initialized = False
        first_call_done = False

        for day in days:
            date_str = day.strftime('%Y-%m-%d')
            print(f"  Day {date_str}...")
            rrdid = 0

            # Перед первым запросом следующего дня выдерживаем паузу, если уже были запросы ранее
            if first_call_done:
                time.sleep(RATE_LIMIT_SECONDS)

            try:
                first_df, next_rrdid = fetch_report_chunk_daily(api_key, date_str, date_str, rrdid)
            except MemoryError:
                print(f"MemoryError during first chunk for {supplier} at {date_str}. Consider reducing WB_API_LIMIT.")
                continue

            first_call_done = True

            if first_df is None:
                print(f"    API error at {date_str}, skipping day")
                continue
            if first_df.empty:
                print(f"    No data for {date_str}")
                continue

            if not table_initialized:
                ensure_table_columns(engine, first_df, schema, table_name)
                table_initialized = True

            fetched_rows_total += len(first_df)
            saved_rows_total += save_chunk_to_db(first_df, supplier, engine, schema, table_name)
            time.sleep(RATE_LIMIT_SECONDS)

            rrdid = next_rrdid
            while rrdid != 0:
                try:
                    df_chunk, next_rrdid = fetch_report_chunk_daily(api_key, date_str, date_str, rrdid)
                except MemoryError:
                    print(f"MemoryError on chunk for {supplier} at {date_str}. Reduce WB_API_LIMIT or increase RAM.")
                    break
                if df_chunk is None or df_chunk.empty:
                    break
                fetched_rows_total += len(df_chunk)
                saved_rows_total += save_chunk_to_db(df_chunk, supplier, engine, schema, table_name)
                rrdid = next_rrdid
                time.sleep(RATE_LIMIT_SECONDS)

        deduplicate_supplier_by_rrd_id(engine, schema, table_name, supplier)
        db_rows = count_db_rows(engine, schema, table_name, supplier, start_date, end_date)
        print(f"Completed {supplier}: fetched={fetched_rows_total}, saved={saved_rows_total}, in_db={db_rows}")

    print("All suppliers processed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch WB reportDetailByPeriod (daily) and store to DB")
    parser.add_argument("--supplier", dest="supplier", type=str, default=None, help="Имя Юрлица из Google Sheets для фильтрации (например: 'ИП Баах Р.Н')")
    parser.add_argument("--date-from", dest="date_from", type=str, default=DEFAULT_START_DATE, help="Начальная дата отчёта YYYY-MM-DD")
    parser.add_argument("--date-to", dest="date_to", type=str, default=DEFAULT_END_DATE, help="Конечная дата отчёта YYYY-MM-DD")
    args = parser.parse_args()

    try:
        # Валидация дат
        _ = datetime.fromisoformat(args.date_from)
        _ = datetime.fromisoformat(args.date_to)
    except Exception:
        raise SystemExit("Неверный формат даты. Используйте YYYY-MM-DD")

    api_map = build_api_dict(args.supplier)
    if not api_map:
        # Вывести доступных поставщиков для помощи выбору
        df_all = pd.DataFrame(worksheet.get_all_records())
        suppliers = sorted(set([str(v) for v in df_all.get('Имя Юрлица', []) if v]))
        print("Не найден ни один поставщик по заданным условиям (проверьте имя и таблицу Инвесторы)")
        print(f"Доступные значения 'Имя Юрлица' (частичное совпадение доступно): {suppliers[:50]}")
        raise SystemExit(1)

    print(f"Suppliers to process: {list(api_map.values())}")
    get_detail_fin_report_daily_all_suppliers(api_map, args.date_from, args.date_to)


