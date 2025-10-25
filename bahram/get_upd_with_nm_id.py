#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для получения данных UPD с добавлением информации о номенклатурах (nm_id)
- Получает ВСЕ записи из UPD API (все поля)
- Делает LEFT JOIN с данными по номенклатурам из детальных API (promotion/auction)
- Загружает результат в БД в схему analytics.adv_upd_with_nm_id
"""

import requests
import time
import json
from datetime import datetime, timedelta, date
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from sqlalchemy import create_engine, text
import traceback

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

# PostgreSQL конфигурация
PG_HOST = '94.103.84.245'
PG_PORT = 5432
PG_USER = 'bahram'
PG_PASSWORD = 'Dadajonim99'
PG_DB = 'wb_baah'

# Путь к файлу с учетными данными
CREDENTIALS_FILE = '/home/baakhofficial/wbauto/bahram/cred.json'
SPREADSHEET_KEY = '15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ'

# Создание подключения к БД
engine = create_engine(f'postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}')

# ============================================================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С API И БД
# ============================================================================

def get_api_keys(credentials_file):
    """Получение API ключей из Google Sheets"""
    print("📋 Загружаем API ключи из Google Sheets...")
    
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
    client = gspread.authorize(creds)
    
    sheet = client.open_by_key(SPREADSHEET_KEY)
    worksheet = sheet.sheet1
    
    data = worksheet.get_all_records()
    
    dict_api_and_supplier_name = {}
    for row in data:
        company_name = row.get('Имя Юрлица')
        api_key = row.get('API ключ')
        
        if company_name and api_key:
            dict_api_and_supplier_name[api_key] = company_name
    
    print(f"✅ Загружено {len(dict_api_and_supplier_name)} API ключей")
    return dict_api_and_supplier_name


def generate_date_ranges(start_date, end_date, max_days=31):
    """
    Генерирует список периодов по max_days дней
    """
    periods = []
    current_start = start_date
    
    while current_start <= end_date:
        current_end = min(current_start + timedelta(days=max_days-1), end_date)
        periods.append((current_start, current_end))
        current_start = current_end + timedelta(days=1)
    
    return periods


def get_upd_data(api_key, from_date, to_date, company_name, max_retries=5):
    """
    Получение данных о затратах на кампании за период (UPD API)
    Возвращает список всех записей со ВСЕМИ полями
    """
    url = "https://advert-api.wildberries.ru/adv/v1/upd"
    headers = {"Authorization": api_key}
    params = {
        "from": from_date,
        "to": to_date
    }
    
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                print(f"  ✅ Получено {len(data)} записей UPD")
                return data
            elif response.status_code == 401:
                print(f"  ❌ Ошибка авторизации (401)")
                return None
            elif response.status_code == 429:
                wait_time = 60 + (attempt * 30)
                print(f"  ⚠️ Превышен лимит запросов (429), попытка {attempt}/{max_retries}, ждём {wait_time} секунд...")
                time.sleep(wait_time)
                continue
            elif response.status_code == 400:
                print(f"  ⚠️ Ошибка 400 (Bad Request): {response.text[:200]}")
                # Может быть нет данных за этот период
                return []
            elif response.status_code >= 500:
                print(f"  ⚠️ Ошибка сервера {response.status_code}, попытка {attempt}/{max_retries}")
                time.sleep(10)
                continue
            else:
                print(f"  ❌ Ошибка {response.status_code}: {response.text[:200]}")
                if attempt < max_retries:
                    time.sleep(10)
                    continue
                return None
                
        except requests.exceptions.Timeout:
            print(f"  ⚠️ Таймаут запроса, попытка {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(10)
                continue
            return None
        except requests.exceptions.ConnectionError as e:
            print(f"  ⚠️ Ошибка соединения: {e}, попытка {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(15)
                continue
            return None
        except requests.exceptions.RequestException as e:
            print(f"  ❌ Ошибка запроса: {e}, попытка {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(10)
                continue
            return None
        except Exception as e:
            print(f"  ❌ Неожиданная ошибка: {e}, попытка {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(10)
                continue
            return None
    
    print(f"  ❌ Не удалось получить данные после {max_retries} попыток")
    return None


def get_promotion_adverts(api_key, campaign_ids, company_name, max_retries=5):
    """
    Получение детальной информации о кампаниях типов 4-8 через promotion API (POST)
    Возвращает словарь {campaign_id: [список nm_id]}
    """
    url = "https://advert-api.wildberries.ru/adv/v1/promotion/adverts"
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }
    
    if len(campaign_ids) > 50:
        campaign_ids = campaign_ids[:50]
    
    # Конвертируем numpy.int64 в Python int для JSON сериализации
    campaign_ids = [int(cid) for cid in campaign_ids]
    
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(url, headers=headers, json=campaign_ids, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return data if isinstance(data, list) else []
            elif response.status_code == 401:
                print(f"  ⚠️ Promotion API: Ошибка авторизации (401)")
                return []
            elif response.status_code == 400:
                print(f"  ⚠️ Promotion API: Bad Request (400): {response.text[:200]}")
                return []
            elif response.status_code == 429:
                wait_time = 60 + (attempt * 30)
                print(f"  ⚠️ Promotion API: Превышен лимит (429), попытка {attempt}/{max_retries}, ждём {wait_time} сек")
                time.sleep(wait_time)
                continue
            elif response.status_code >= 500:
                print(f"  ⚠️ Promotion API: Ошибка сервера {response.status_code}, попытка {attempt}/{max_retries}")
                time.sleep(10)
                continue
            else:
                print(f"  ⚠️ Promotion API: Ошибка {response.status_code}: {response.text[:200]}")
                if attempt < max_retries:
                    time.sleep(10)
                    continue
                return []
                
        except requests.exceptions.Timeout:
            print(f"  ⚠️ Promotion API: Таймаут, попытка {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(10)
                continue
            return []
        except requests.exceptions.RequestException as e:
            print(f"  ⚠️ Promotion API: Ошибка запроса: {e}, попытка {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(10)
                continue
            return []
        except Exception as e:
            print(f"  ❌ Promotion API: Неожиданная ошибка: {e}, попытка {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(10)
                continue
            return []
    
    print(f"  ❌ Promotion API: Не удалось получить данные после {max_retries} попыток")
    return []


def get_auction_adverts(api_key, campaign_ids, company_name, max_retries=5):
    """
    Получение детальной информации о кампаниях типа 9 через auction API (GET)
    Возвращает словарь {campaign_id: [список nm_id]}
    """
    url = "https://advert-api.wildberries.ru/adv/v0/auction/adverts"
    headers = {"Authorization": api_key}
    
    if len(campaign_ids) > 50:
        campaign_ids = campaign_ids[:50]
    
    # Конвертируем numpy.int64 в Python int
    campaign_ids = [int(cid) for cid in campaign_ids]
    params = {"ids": ",".join(map(str, campaign_ids))}
    
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                adverts = data.get('adverts', []) if isinstance(data, dict) else []
                return adverts
            elif response.status_code == 401:
                print(f"  ⚠️ Auction API: Ошибка авторизации (401)")
                return []
            elif response.status_code == 400:
                print(f"  ⚠️ Auction API: Bad Request (400): {response.text[:200]}")
                return []
            elif response.status_code == 429:
                wait_time = 60 + (attempt * 30)
                print(f"  ⚠️ Auction API: Превышен лимит (429), попытка {attempt}/{max_retries}, ждём {wait_time} сек")
                time.sleep(wait_time)
                continue
            elif response.status_code >= 500:
                print(f"  ⚠️ Auction API: Ошибка сервера {response.status_code}, попытка {attempt}/{max_retries}")
                time.sleep(10)
                continue
            else:
                print(f"  ⚠️ Auction API: Ошибка {response.status_code}: {response.text[:200]}")
                if attempt < max_retries:
                    time.sleep(10)
                    continue
                return []
                
        except requests.exceptions.Timeout:
            print(f"  ⚠️ Auction API: Таймаут, попытка {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(10)
                continue
            return []
        except requests.exceptions.RequestException as e:
            print(f"  ⚠️ Auction API: Ошибка запроса: {e}, попытка {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(10)
                continue
            return []
        except Exception as e:
            print(f"  ❌ Auction API: Неожиданная ошибка: {e}, попытка {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(10)
                continue
            return []
    
    print(f"  ❌ Auction API: Не удалось получить данные после {max_retries} попыток")
    return []


def extract_nm_ids_from_campaign_details(api_key, campaign_ids_by_type, company_name):
    """
    Получает список nm_id для кампаний, разделённых по типам
    
    Args:
        api_key: API ключ
        campaign_ids_by_type: словарь {campaign_id: type}
        company_name: название компании
    
    Returns:
        словарь {campaign_id: [nm_id1, nm_id2, ...]}
    """
    campaign_nm_mapping = {}
    
    # Разделяем кампании по типам
    type_9_campaigns = [cid for cid, ctype in campaign_ids_by_type.items() if ctype == 9]
    other_type_campaigns = [cid for cid, ctype in campaign_ids_by_type.items() if ctype != 9]
    
    batch_size = 50
    
    # 1. Обрабатываем кампании типа 9 через auction API
    if type_9_campaigns:
        print(f"  📡 Получение nm_id для {len(type_9_campaigns)} кампаний типа 9 (auction API)...")
        for i in range(0, len(type_9_campaigns), batch_size):
            batch = type_9_campaigns[i:i+batch_size]
            
            adverts = get_auction_adverts(api_key, batch, company_name)
            
            for advert in adverts:
                campaign_id = advert.get('id')
                nm_settings = advert.get('nm_settings', [])
                nm_ids = [nm.get('nm_id') for nm in nm_settings if nm.get('nm_id')]
                
                if campaign_id and nm_ids:
                    campaign_nm_mapping[campaign_id] = nm_ids
            
            time.sleep(0.3)
    
    # 2. Обрабатываем кампании типов 4-8 через promotion API
    if other_type_campaigns:
        print(f"  📡 Получение nm_id для {len(other_type_campaigns)} кампаний типов 4-8 (promotion API)...")
        for i in range(0, len(other_type_campaigns), batch_size):
            batch = other_type_campaigns[i:i+batch_size]
            
            adverts = get_promotion_adverts(api_key, batch, company_name)
            
            for advert in adverts:
                campaign_id = advert.get('advertId')
                nm_ids = []
                
                # Для типа 8 - autoParams
                if 'autoParams' in advert:
                    auto_params = advert.get('autoParams', {})
                    nm_ids = auto_params.get('nms', [])
                
                # Для типов 4-7 - params
                elif 'params' in advert:
                    params = advert.get('params', [])
                    for param in params:
                        if 'nms' in param:
                            nm_ids.extend(param.get('nms', []))
                        if 'nm' in param:
                            nm_ids.append(param.get('nm'))
                
                if campaign_id and nm_ids:
                    campaign_nm_mapping[campaign_id] = nm_ids
            
            time.sleep(0.3)
    
    print(f"  ✅ Найдены nm_id для {len(campaign_nm_mapping)} кампаний")
    return campaign_nm_mapping


def process_company_data(api_key, company_name, start_date, end_date):
    """
    Обрабатывает данные одной компании:
    1. Получает все записи UPD
    2. Получает nm_id для каждой кампании
    3. Делает left join
    
    Returns:
        DataFrame с объединёнными данными
    """
    print(f"\n{'='*60}")
    print(f"🏢 Компания: {company_name}")
    print(f"{'='*60}")
    
    # Генерируем периоды
    periods = generate_date_ranges(start_date, end_date, max_days=31)
    print(f"📊 Разбито на {len(periods)} периодов по 31 день")
    
    all_upd_records = []
    
    # Получаем все записи UPD
    for period_idx, (period_start, period_end) in enumerate(periods, 1):
        print(f"\n  📅 Период {period_idx}/{len(periods)}: {period_start} - {period_end}")
        
        upd_data = get_upd_data(api_key, str(period_start), str(period_end), company_name)
        
        if upd_data is not None:
            if len(upd_data) > 0:
                # Добавляем название компании к каждой записи
                for record in upd_data:
                    record['supplier'] = company_name
                
                all_upd_records.extend(upd_data)
            else:
                print(f"  ℹ️ Нет данных за этот период")
        else:
            print(f"  ❌ Ошибка получения данных")
        
        time.sleep(1.5)
    
    if not all_upd_records:
        print(f"⚠️ Нет данных UPD для компании {company_name}")
        return pd.DataFrame()
    
    print(f"\n📊 Всего записей UPD: {len(all_upd_records)}")
    
    # Создаём DataFrame из UPD
    df_upd = pd.DataFrame(all_upd_records)
    
    # Нормализуем названия колонок (lowercase)
    df_upd.columns = df_upd.columns.str.lower()
    
    # Извлекаем уникальные кампании с их типами
    campaign_ids_by_type = {}
    if 'advertid' in df_upd.columns and 'adverttype' in df_upd.columns:
        unique_campaigns = df_upd[['advertid', 'adverttype']].drop_duplicates()
        for _, row in unique_campaigns.iterrows():
            # Конвертируем numpy типы в Python типы
            adv_id = int(row['advertid']) if pd.notna(row['advertid']) else None
            adv_type = int(row['adverttype']) if pd.notna(row['adverttype']) else None
            
            if adv_id is not None and adv_type is not None:
                campaign_ids_by_type[adv_id] = adv_type
    
    print(f"📊 Уникальных кампаний: {len(campaign_ids_by_type)}")
    
    # Получаем nm_id для кампаний
    if campaign_ids_by_type:
        campaign_nm_mapping = extract_nm_ids_from_campaign_details(
            api_key, 
            campaign_ids_by_type, 
            company_name
        )
        
        # Добавляем nm_ids как строку (разделенную запятыми) БЕЗ JOIN
        # Каждая запись UPD остаётся одной строкой
        def get_nm_ids_for_campaign(advertid):
            if advertid in campaign_nm_mapping:
                nm_ids = campaign_nm_mapping[advertid]
                if nm_ids:
                    # Конвертируем в строку, разделенную запятыми
                    return ', '.join(map(str, nm_ids))
            return None
        
        def get_nm_ids_count(advertid):
            if advertid in campaign_nm_mapping:
                nm_ids = campaign_nm_mapping[advertid]
                return len(nm_ids) if nm_ids else 0
            return 0
        
        df_upd['nm_ids'] = df_upd['advertid'].apply(get_nm_ids_for_campaign)
        df_upd['nm_ids_count'] = df_upd['advertid'].apply(get_nm_ids_count)
        
        found_count = df_upd['nm_ids'].notna().sum()
        total_nm_ids = df_upd['nm_ids_count'].sum()
        
        print(f"✅ Добавлены nm_ids: {found_count}/{len(df_upd)} записей имеют артикулы ({total_nm_ids} всего)")
    else:
        df_upd['nm_ids'] = None
        df_upd['nm_ids_count'] = 0
        print(f"⚠️ Нет информации о кампаниях")
    
    # Добавляем timestamp обработки
    df_upd['loaded_at'] = datetime.now()
    
    return df_upd


def ensure_schema_and_table(engine):
    """
    Создаёт схему analytics и таблицу adv_upd_with_nm_id если их нет
    """
    print("\n💾 Подготовка схемы и таблицы в БД...")
    
    with engine.begin() as conn:
        # Создаём схему
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS analytics"))
        
        # Создаём таблицу БЕЗ id (основные поля, остальные добавятся динамически)
        create_table_sql = text("""
        CREATE TABLE IF NOT EXISTS analytics.adv_upd_with_nm_id (
            updnum INTEGER,
            updtime TIMESTAMP,
            updsum INTEGER,
            advertid INTEGER,
            campname VARCHAR(500),
            adverttype INTEGER,
            paymenttype VARCHAR(500),
            advertstatus INTEGER,
            supplier VARCHAR(500),
            nm_ids TEXT,
            nm_ids_count INTEGER,
            loaded_at TIMESTAMP
        )
        """)
        
        conn.execute(create_table_sql)
        
        # Создаём индексы
        conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_upd_nm_advertid 
        ON analytics.adv_upd_with_nm_id(advertid)
        """))
        
        conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_upd_nm_supplier 
        ON analytics.adv_upd_with_nm_id(supplier)
        """))
        
        conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_upd_nm_updtime 
        ON analytics.adv_upd_with_nm_id(updtime)
        """))
        
        conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_upd_nm_unique_key 
        ON analytics.adv_upd_with_nm_id(updnum, advertid, supplier)
        """))
    
    print("✅ Схема и таблица готовы")


def ensure_columns_exist(engine, df):
    """
    Проверяет и добавляет новые колонки в таблицу если они есть в DataFrame
    """
    existing_columns = set()
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'analytics' 
            AND table_name = 'adv_upd_with_nm_id'
        """))
        existing_columns = {row[0] for row in result.fetchall()}
    
    new_columns = set(df.columns) - existing_columns
    
    if new_columns:
        print(f"📊 Найдены новые колонки: {len(new_columns)}")
        
        with engine.begin() as conn:
            for col in new_columns:
                # Определяем тип данных
                sample_val = df[col].dropna().iloc[0] if not df[col].dropna().empty else None
                
                if sample_val is None:
                    col_type = 'TEXT'
                elif isinstance(sample_val, (int, pd.Int64Dtype)):
                    col_type = 'BIGINT'
                elif isinstance(sample_val, float):
                    col_type = 'DOUBLE PRECISION'
                elif isinstance(sample_val, (datetime, pd.Timestamp)):
                    col_type = 'TIMESTAMP'
                else:
                    col_type = 'TEXT'
                
                try:
                    conn.execute(text(f"""
                        ALTER TABLE analytics.adv_upd_with_nm_id 
                        ADD COLUMN IF NOT EXISTS "{col}" {col_type}
                    """))
                    print(f"  + Добавлена колонка: {col} ({col_type})")
                except Exception as e:
                    print(f"  ! Ошибка добавления колонки {col}: {e}")


def upload_to_database(engine, df):
    """
    Загружает данные в БД
    """
    if df.empty:
        print("⚠️ Нет данных для загрузки")
        return
    
    print(f"\n💾 Загрузка {len(df)} записей в БД...")
    
    # Проверяем и добавляем новые колонки
    ensure_columns_exist(engine, df)
    
    # Загружаем данные порциями
    chunk_size = 1000
    total_chunks = (len(df) - 1) // chunk_size + 1
    
    for i in range(0, len(df), chunk_size):
        chunk = df.iloc[i:i+chunk_size]
        chunk_num = (i // chunk_size) + 1
        
        try:
            chunk.to_sql(
                name='adv_upd_with_nm_id',
                con=engine,
                schema='analytics',
                if_exists='append',
                index=False,
                method='multi',
                chunksize=500
            )
            print(f"  ✅ Загружен чанк {chunk_num}/{total_chunks} ({len(chunk)} записей)")
        except Exception as e:
            print(f"  ❌ Ошибка загрузки чанка {chunk_num}: {e}")
            traceback.print_exc()
    
    print(f"✅ Загрузка завершена")


def deduplicate_table(engine):
    """
    Удаляет дубликаты из таблицы по ключевым полям
    Уникальность: updnum + advertid + supplier
    """
    print("\n🧹 Дедупликация таблицы...")
    
    dedup_sql = text("""
    CREATE TEMP TABLE tmp_unique AS
    SELECT DISTINCT ON (updnum, advertid, supplier)
        *
    FROM analytics.adv_upd_with_nm_id
    ORDER BY updnum, advertid, supplier, loaded_at DESC;
    
    TRUNCATE TABLE analytics.adv_upd_with_nm_id;
    
    INSERT INTO analytics.adv_upd_with_nm_id
    SELECT * FROM tmp_unique;
    
    DROP TABLE tmp_unique;
    """)
    
    try:
        with engine.begin() as conn:
            conn.execute(dedup_sql)
            
            # Подсчитываем количество записей после дедупликации
            result = conn.execute(text("SELECT COUNT(*) FROM analytics.adv_upd_with_nm_id"))
            count = result.scalar()
            print(f"✅ Дедупликация завершена (ключ: updnum + advertid + supplier)")
            print(f"✅ Осталось {count:,} уникальных записей")
    except Exception as e:
        print(f"⚠️ Ошибка дедупликации: {e}")
        traceback.print_exc()


# ============================================================================
# ОСНОВНАЯ ЛОГИКА
# ============================================================================

def main():
    print("="*60)
    print("🚀 ЗАГРУЗКА UPD С НОМЕНКЛАТУРАМИ В БД")
    print("="*60)
    
    # Получаем API ключи
    api_keys_dict = get_api_keys(CREDENTIALS_FILE)
    
    # Определяем период
    start_date = date(2025, 3, 1)  # 1 марта 2025
    end_date = datetime.now().date()  # Сегодня
    
    print(f"\n📅 ПЕРИОД: {start_date} - {end_date}")
    print(f"🏢 КОМПАНИЙ: {len(api_keys_dict)}\n")
    
    # Подготовка БД
    ensure_schema_and_table(engine)
    
    # Обрабатываем каждую компанию
    total_records = 0
    successful_companies = 0
    
    for idx, (api_key, company_name) in enumerate(api_keys_dict.items(), 1):
        print(f"\n{'='*60}")
        print(f"Компания {idx}/{len(api_keys_dict)}: {company_name}")
        print(f"{'='*60}")
        
        try:
            # Получаем и обрабатываем данные
            df_company = process_company_data(api_key, company_name, start_date, end_date)
            
            if not df_company.empty:
                # Загружаем в БД
                upload_to_database(engine, df_company)
                
                total_records += len(df_company)
                successful_companies += 1
                
                print(f"✅ Компания {company_name}: {len(df_company)} записей загружено")
            else:
                print(f"⚠️ Компания {company_name}: нет данных")
        
        except Exception as e:
            print(f"❌ Ошибка обработки компании {company_name}: {e}")
            traceback.print_exc()
        
        # Пауза между компаниями
        if idx < len(api_keys_dict):
            print(f"\n⏳ Пауза 3 секунды...")
            time.sleep(3)
    
    # Дедупликация
    deduplicate_table(engine)
    
    # Итоговая статистика
    print("\n" + "="*60)
    print("📊 ИТОГОВАЯ СТАТИСТИКА")
    print("="*60)
    print(f"🏢 Обработано компаний: {len(api_keys_dict)}")
    print(f"✅ Успешно: {successful_companies}")
    print(f"❌ С ошибками: {len(api_keys_dict) - successful_companies}")
    print(f"📊 Всего записей загружено: {total_records:,}")
    print(f"💾 Таблица: analytics.adv_upd_with_nm_id")
    print("="*60)
    
    print("\n✅ Скрипт завершён успешно!")


if __name__ == "__main__":
    main()

