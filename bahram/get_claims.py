#!/usr/bin/env python3

import requests
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import time
import gspread
import os
import json
from typing import List, Dict, Any, Optional

# === PostgreSQL setup ===
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

# === Google Sheets setup ===
cred_path = os.path.join(os.path.dirname(__file__), 'cred.json')
gc = gspread.service_account(filename=cred_path)
worksheet = gc.open_by_key("15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ").sheet1
df_keys = pd.DataFrame(worksheet.get_all_records())
df_keys = df_keys[df_keys['API ключ'].notnull() & (df_keys['API ключ'] != '')]

dict_api = dict(zip(df_keys['API ключ'], df_keys['Имя Юрлица']))

print(f"Найдено API ключей: {len(dict_api)}")

def create_claims_table():
    """Создает таблицу для хранения заявок на возврат"""
    create_schema_query = """
    CREATE SCHEMA IF NOT EXISTS reports;
    """
    
    create_table_query = """
    CREATE TABLE IF NOT EXISTS reports.claims (
        id UUID PRIMARY KEY,
        company VARCHAR(255) NOT NULL,
        claim_type INTEGER,
        status INTEGER,
        status_ex INTEGER,
        nm_id BIGINT,
        user_comment TEXT,
        wb_comment TEXT,
        dt TIMESTAMP,
        imt_name TEXT,
        order_dt TIMESTAMP,
        dt_update TIMESTAMP,
        photos TEXT[],
        video_paths TEXT[],
        actions TEXT[],
        price NUMERIC(15, 2),
        currency_code VARCHAR(10),
        srid VARCHAR(255),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE INDEX IF NOT EXISTS idx_claims_company ON reports.claims(company);
    CREATE INDEX IF NOT EXISTS idx_claims_nm_id ON reports.claims(nm_id);
    CREATE INDEX IF NOT EXISTS idx_claims_dt ON reports.claims(dt);
    CREATE INDEX IF NOT EXISTS idx_claims_status ON reports.claims(status);
    CREATE INDEX IF NOT EXISTS idx_claims_srid ON reports.claims(srid);
    """
    
    try:
        with engine.connect() as conn:
            conn.execute(text(create_schema_query))
            conn.execute(text(create_table_query))
            conn.commit()
        print("✓ Таблица reports.claims создана/проверена")
    except Exception as e:
        print(f"Ошибка при создании таблицы: {e}")
        raise

def get_claims(api_key: str, company_name: str, is_archive: bool = False, 
               limit: int = 200, offset: int = 0, nm_id: Optional[int] = None) -> Optional[Dict]:
    """
    Получает заявки на возврат через API Wildberries
    
    Args:
        api_key: API ключ
        company_name: Название компании
        is_archive: Состояние заявки (False - на рассмотрении, True - в архиве)
        limit: Количество заявок в ответе (1-200)
        offset: После какого элемента выдавать данные
        nm_id: Артикул WB (опционально)
    
    Returns:
        Словарь с данными заявок или None при ошибке
    """
    url = "https://returns-api.wildberries.ru/api/v1/claims"
    
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }
    
    params = {
        "is_archive": str(is_archive).lower(),
        "limit": limit,
        "offset": offset
    }
    
    if nm_id:
        params["nm_id"] = nm_id
    
    try:
        print(f"Запрос заявок для {company_name} (архив: {is_archive}, offset: {offset})")
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Получено {len(data.get('claims', []))} заявок для {company_name}")
            return data
        else:
            print(f"✗ Ошибка API для {company_name}: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"✗ Исключение при запросе для {company_name}: {e}")
        return None

def generate_date_periods(start_date: datetime, end_date: datetime, period_days: int = 14) -> List[tuple]:
    """
    Генерирует периоды по 14 дней для получения данных
    
    Args:
        start_date: Начальная дата
        end_date: Конечная дата
        period_days: Количество дней в периоде (по умолчанию 14)
    
    Returns:
        Список кортежей (start_date, end_date) для каждого периода
    """
    periods = []
    current_date = start_date
    
    while current_date < end_date:
        period_end = min(current_date + timedelta(days=period_days), end_date)
        periods.append((current_date, period_end))
        current_date = period_end
    
    return periods

def process_claims_data(claims_data: List[Dict], company_name: str) -> pd.DataFrame:
    """
    Обрабатывает данные заявок и преобразует в DataFrame
    
    Args:
        claims_data: Список заявок из API
        company_name: Название компании
    
    Returns:
        DataFrame с обработанными данными
    """
    if not claims_data:
        return pd.DataFrame()
    
    processed_claims = []
    
    for claim in claims_data:
        processed_claim = {
            'id': claim.get('id'),
            'company': company_name,
            'claim_type': claim.get('claim_type'),
            'status': claim.get('status'),
            'status_ex': claim.get('status_ex'),
            'nm_id': claim.get('nm_id'),
            'user_comment': claim.get('user_comment'),
            'wb_comment': claim.get('wb_comment'),
            'dt': pd.to_datetime(claim.get('dt')) if claim.get('dt') else None,
            'imt_name': claim.get('imt_name'),
            'order_dt': pd.to_datetime(claim.get('order_dt')) if claim.get('order_dt') else None,
            'dt_update': pd.to_datetime(claim.get('dt_update')) if claim.get('dt_update') else None,
            'photos': claim.get('photos', []),
            'video_paths': claim.get('video_paths', []),
            'actions': claim.get('actions', []),
            'price': claim.get('price'),
            'currency_code': claim.get('currency_code'),
            'srid': claim.get('srid')
        }
        processed_claims.append(processed_claim)
    
    return pd.DataFrame(processed_claims)

def upload_claims_to_db(df: pd.DataFrame):
    """
    Загружает данные заявок в базу данных
    
    Args:
        df: DataFrame с данными заявок
    """
    if df.empty:
        print("Нет данных для загрузки")
        return
    
    try:
        # Используем upsert для обновления существующих записей
        with engine.connect() as conn:
            for _, row in df.iterrows():
                # Подготавливаем данные для вставки
                insert_data = {
                    'id': row['id'],
                    'company': row['company'],
                    'claim_type': row['claim_type'],
                    'status': row['status'],
                    'status_ex': row['status_ex'],
                    'nm_id': row['nm_id'],
                    'user_comment': row['user_comment'],
                    'wb_comment': row['wb_comment'],
                    'dt': row['dt'],
                    'imt_name': row['imt_name'],
                    'order_dt': row['order_dt'],
                    'dt_update': row['dt_update'],
                    'photos': row['photos'],
                    'video_paths': row['video_paths'],
                    'actions': row['actions'],
                    'price': row['price'],
                    'currency_code': row['currency_code'],
                    'srid': row['srid'],
                    'updated_at': datetime.now()
                }
                
                # SQL для upsert
                upsert_sql = text("""
                    INSERT INTO reports.claims (
                        id, company, claim_type, status, status_ex, nm_id, user_comment,
                        wb_comment, dt, imt_name, order_dt, dt_update, photos, video_paths,
                        actions, price, currency_code, srid, created_at, updated_at
                    ) VALUES (
                        :id, :company, :claim_type, :status, :status_ex, :nm_id, :user_comment,
                        :wb_comment, :dt, :imt_name, :order_dt, :dt_update, :photos, :video_paths,
                        :actions, :price, :currency_code, :srid, CURRENT_TIMESTAMP, :updated_at
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        company = EXCLUDED.company,
                        claim_type = EXCLUDED.claim_type,
                        status = EXCLUDED.status,
                        status_ex = EXCLUDED.status_ex,
                        nm_id = EXCLUDED.nm_id,
                        user_comment = EXCLUDED.user_comment,
                        wb_comment = EXCLUDED.wb_comment,
                        dt = EXCLUDED.dt,
                        imt_name = EXCLUDED.imt_name,
                        order_dt = EXCLUDED.order_dt,
                        dt_update = EXCLUDED.dt_update,
                        photos = EXCLUDED.photos,
                        video_paths = EXCLUDED.video_paths,
                        actions = EXCLUDED.actions,
                        price = EXCLUDED.price,
                        currency_code = EXCLUDED.currency_code,
                        srid = EXCLUDED.srid,
                        updated_at = EXCLUDED.updated_at
                """)
                
                conn.execute(upsert_sql, insert_data)
            
            conn.commit()
        
        print(f"✓ Загружено {len(df)} заявок в базу данных")
        
    except Exception as e:
        print(f"✗ Ошибка при загрузке в БД: {e}")
        raise

def get_all_claims_for_company(api_key: str, company_name: str, is_archive: bool = False):
    """
    Получает все заявки для компании с пагинацией
    
    Args:
        api_key: API ключ
        company_name: Название компании
        is_archive: Состояние заявки
    """
    print(f"\n{'='*60}")
    print(f"Обработка заявок для: {company_name}")
    print(f"Архив: {is_archive}")
    print(f"{'='*60}")
    
    all_claims = []
    offset = 0
    limit = 200
    
    while True:
        # Получаем заявки с текущим offset
        claims_data = get_claims(api_key, company_name, is_archive, limit, offset)
        
        if not claims_data or 'claims' not in claims_data:
            break
        
        claims = claims_data['claims']
        if not claims:
            break
        
        all_claims.extend(claims)
        print(f"Получено заявок: {len(claims)} (всего: {len(all_claims)})")
        
        # Если получили меньше чем limit, значит это последняя страница
        if len(claims) < limit:
            break
        
        offset += limit
        
        # Пауза между запросами для соблюдения лимитов API
        time.sleep(3)
    
    if all_claims:
        # Обрабатываем и загружаем данные
        df = process_claims_data(all_claims, company_name)
        upload_claims_to_db(df)
        print(f"✓ Всего обработано {len(all_claims)} заявок для {company_name}")
    else:
        print(f"✗ Не найдено заявок для {company_name}")

def get_claims_for_period(api_key: str, company_name: str, start_date: datetime, end_date: datetime):
    """
    Получает заявки за определенный период с разбивкой по 14 дней
    
    Args:
        api_key: API ключ
        company_name: Название компании
        start_date: Начальная дата
        end_date: Конечная дата
    """
    print(f"\n{'='*80}")
    print(f"Обработка компании: {company_name}")
    print(f"Период: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    print(f"{'='*80}")
    
    # Генерируем периоды по 14 дней
    periods = generate_date_periods(start_date, end_date, 14)
    
    print(f"Создано {len(periods)} периодов по 14 дней")
    
    # Обрабатываем каждый период
    for i, (period_start, period_end) in enumerate(periods, 1):
        print(f"\n--- Период {i}/{len(periods)}: {period_start.strftime('%Y-%m-%d')} - {period_end.strftime('%Y-%m-%d')} ---")
        
        try:
            # Получаем заявки на рассмотрении
            get_all_claims_for_company(api_key, company_name, is_archive=False)
            
            # Пауза между запросами
            time.sleep(3)
            
            # Получаем заявки в архиве
            get_all_claims_for_company(api_key, company_name, is_archive=True)
            
            # Пауза между периодами
            time.sleep(3)
            
        except Exception as e:
            print(f"✗ Ошибка в периоде {i} для {company_name}: {e}")
            continue

def main():
    """Основная функция для получения всех заявок за последние 14 дней"""
    print("Начинаем получение заявок на возврат за последние 14 дней...")
    
    # Создаем таблицу если не существует
    create_claims_table()
    
    # Определяем период - последние 14 дней
    end_date = datetime.now()
    start_date = end_date - timedelta(days=14)
    
    print(f"Период получения данных: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    
    # Получаем заявки для каждого API ключа
    for api_key, company_name in dict_api.items():
        try:
            get_claims_for_period(api_key, company_name, start_date, end_date)
            
            # Пауза между компаниями
            time.sleep(5)
            
        except Exception as e:
            print(f"✗ Ошибка при обработке {company_name}: {e}")
            continue
    
    print("\n✓ Получение заявок завершено!")

def main_extended():
    """Расширенная функция для получения заявок за более длительный период"""
    print("Начинаем получение заявок на возврат за расширенный период...")
    
    # Создаем таблицу если не существует
    create_claims_table()
    
    # Определяем период - например, последние 60 дней
    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)
    
    print(f"Расширенный период получения данных: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    
    # Получаем заявки для каждого API ключа
    for api_key, company_name in dict_api.items():
        try:
            get_claims_for_period(api_key, company_name, start_date, end_date)
            
            # Пауза между компаниями
            time.sleep(10)
            
        except Exception as e:
            print(f"✗ Ошибка при обработке {company_name}: {e}")
            continue
    
    print("\n✓ Расширенное получение заявок завершено!")

def main_from_2024():
    """Функция для получения заявок с 1 января 2024 года"""
    print("Начинаем получение заявок на возврат с 1 января 2024 года...")
    
    # Создаем таблицу если не существует
    create_claims_table()
    
    # Определяем период - с 1 января 2024 года до сегодня
    start_date = datetime(2024, 1, 1)
    end_date = datetime.now()
    
    print(f"Период получения данных: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    
    # Получаем заявки для каждого API ключа
    for api_key, company_name in dict_api.items():
        try:
            get_claims_for_period(api_key, company_name, start_date, end_date)
            
            # Пауза между компаниями
            time.sleep(10)
            
        except Exception as e:
            print(f"✗ Ошибка при обработке {company_name}: {e}")
            continue
    
    print("\n✓ Получение заявок с 2024 года завершено!")

if __name__ == "__main__":
    import sys
    
    # Проверяем аргументы командной строки
    if len(sys.argv) > 1:
        if sys.argv[1] == "extended":
            print("Запуск в расширенном режиме (60 дней)")
            main_extended()
        elif sys.argv[1] == "2024":
            print("Запуск с 1 января 2024 года")
            main_from_2024()
        else:
            print("Неизвестный аргумент. Доступные варианты:")
            print("  python get_claims.py          - стандартный режим (14 дней)")
            print("  python get_claims.py extended - расширенный режим (60 дней)")
            print("  python get_claims.py 2024     - с 1 января 2024 года")
    else:
        print("Запуск в стандартном режиме (14 дней)")
        print("Доступные режимы:")
        print("  python get_claims.py extended - расширенный режим (60 дней)")
        print("  python get_claims.py 2024     - с 1 января 2024 года")
        main()
