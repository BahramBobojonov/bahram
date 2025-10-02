#!/usr/bin/env python3

import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import gspread
import os
import json
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Float, DateTime, BigInteger, text
from sqlalchemy.dialects.postgresql import insert

# === PostgreSQL setup ===
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

# === Google Sheets setup ===
cred_path = os.path.join(os.path.dirname(__file__), 'cred.json')
gc = gspread.service_account(filename=cred_path)
worksheet = gc.open_by_key("15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ").sheet1
df_keys = pd.DataFrame(worksheet.get_all_records())
df_keys = df_keys[df_keys['API ключ'].notnull() & (df_keys['API ключ'] != '')]

dict_api = dict(zip(df_keys['API ключ'], df_keys['Имя Юрлица']))

# === Параметры дат ===
end_date = datetime.now().date()
begin_date = end_date - timedelta(days=30)
begin_date_str = begin_date.strftime('%Y-%m-%d')
end_date_str = end_date.strftime('%Y-%m-%d')

print(f"Период запроса: {begin_date_str} - {end_date_str}")

# === Функция для загрузки данных в PostgreSQL ===
def upload_to_postgres(df, table_name='adv_fullstats', schema='reports', chunk_size=1000):
    """
    Оптимизированная загрузка данных в PostgreSQL с UPSERT логикой
    
    Args:
        df: DataFrame с данными
        table_name: название таблицы
        schema: схема БД
        chunk_size: размер батча для вставки
    """
    if df.empty:
        print(f"[PostgreSQL] Нет данных для загрузки в {schema}.{table_name}")
        return
    
    # Подготовка данных
    df_upload = df.copy()
    
    # Переименовываем колонки для БД (lowercase, snake_case)
    column_mapping = {
        'advertId': 'advertid',
        'nmId': 'nm_id',
        'appType': 'apptype',
        'company': 'supplier'
    }
    df_upload.rename(columns=column_mapping, inplace=True)
    
    # Убираем колонку api_key_last4 (не нужна в БД)
    if 'api_key_last4' in df_upload.columns:
        df_upload = df_upload.drop(columns=['api_key_last4'])
    
    # Преобразуем дату
    if 'date' in df_upload.columns:
        df_upload['adv_date'] = pd.to_datetime(df_upload['date']).dt.date
        df_upload = df_upload.drop(columns=['date'])
    
    # Заменяем NaN на None для корректной вставки в PostgreSQL
    df_upload = df_upload.where(pd.notnull(df_upload), None)
    
    # Проверяем существование таблицы и создаем если нужно
    table_exists = False
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = '{schema}' 
                AND table_name = '{table_name}'
            )
        """))
        table_exists = result.fetchone()[0]
    
    if not table_exists:
        # Создаем таблицу со всеми колонками через pandas
        print(f"[PostgreSQL] Создаем новую таблицу {schema}.{table_name}")
        df_upload.to_sql(table_name, engine, schema=schema, if_exists='replace', index=False)
        
        # Создаем уникальный индекс
        with engine.begin() as conn:
            conn.execute(text(f"""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_{table_name}_unique 
                ON {schema}.{table_name} (supplier, advertid, adv_date, nm_id, apptype)
            """))
        print(f"[PostgreSQL] Создан уникальный индекс на (supplier, advertid, adv_date, nm_id, apptype)")
    else:
        print(f"[PostgreSQL] Используем существующую таблицу {schema}.{table_name}")
        
        # Проверяем и добавляем новые колонки, если они появились в API
        with engine.connect() as conn:
            # Получаем список существующих колонок
            result = conn.execute(text(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = '{schema}' 
                AND table_name = '{table_name}'
            """))
            existing_columns = {row[0] for row in result.fetchall()}
            
            # Находим новые колонки
            new_columns = set(df_upload.columns) - existing_columns
            
            if new_columns:
                print(f"[PostgreSQL] Обнаружены новые колонки из API: {len(new_columns)}")
                
                # Добавляем каждую новую колонку
                with engine.begin() as conn_alter:
                    for col in new_columns:
                        # Определяем тип данных на основе первого не-NULL значения
                        sample_value = df_upload[col].dropna().iloc[0] if not df_upload[col].dropna().empty else None
                        
                        if sample_value is None:
                            col_type = 'TEXT'
                        elif isinstance(sample_value, (int, pd.Int64Dtype)):
                            col_type = 'BIGINT'
                        elif isinstance(sample_value, float):
                            col_type = 'DOUBLE PRECISION'
                        elif isinstance(sample_value, bool):
                            col_type = 'BOOLEAN'
                        else:
                            col_type = 'TEXT'
                        
                        try:
                            conn_alter.execute(text(f"""
                                ALTER TABLE {schema}.{table_name} 
                                ADD COLUMN IF NOT EXISTS "{col}" {col_type}
                            """))
                            print(f"[PostgreSQL]   + Добавлена колонка: {col} ({col_type})")
                        except Exception as e:
                            print(f"[PostgreSQL]   ! Ошибка добавления колонки {col}: {e}")
                
                print(f"[PostgreSQL] ✓ Схема таблицы обновлена")
    
    # Получаем метаданные таблицы
    metadata = MetaData(schema=schema)
    metadata.reflect(bind=engine, only=[table_name])
    table = metadata.tables[f'{schema}.{table_name}']
    
    # Подготовка данных для вставки
    records = df_upload.to_dict(orient='records')
    
    # Определяем колонки для обновления (все кроме ключевых)
    key_columns = ['supplier', 'advertid', 'adv_date', 'nm_id', 'apptype']
    
    # Получаем список колонок которые действительно есть в таблице
    table_columns = [col.name for col in table.columns]
    update_columns = [col for col in table_columns if col not in key_columns]
    
    # Вставка данных батчами с UPSERT
    with engine.begin() as connection:
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i + chunk_size]
            
            # Создаем INSERT statement
            stmt = insert(table).values(chunk)
            
            # Создаем ON CONFLICT DO UPDATE только для существующих колонок
            update_dict = {col: stmt.excluded[col] for col in update_columns}
            
            do_update_stmt = stmt.on_conflict_do_update(
                index_elements=key_columns,
                set_=update_dict
            )
            
            # Выполняем запрос
            result = connection.execute(do_update_stmt)
            
            batch_num = (i // chunk_size) + 1
            total_batches = (len(records) - 1) // chunk_size + 1
            
            print(f"[PostgreSQL] Обработан батч {batch_num}/{total_batches} ({len(chunk)} записей)")
    
    print(f"[PostgreSQL] ✓ Загружено {len(records)} записей в {schema}.{table_name}")
    return len(records)

# === Функции для API ===
def get_campaigns(api_key, company_name):
    """Получение списка рекламных кампаний"""
    url = "https://advert-api.wildberries.ru/adv/v1/promotion/count"
    headers = {"Authorization": api_key}
    for attempt in range(5):  # попытки при ошибке
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                print(f"[{company_name}] Получен ответ от promotion/count")
                return data.get('adverts', [])
            else:
                print(f"[{company_name}] Ошибка запроса campaigns: {resp.status_code}, повтор через 2 сек")
                time.sleep(2)
        except Exception as e:
            print(f"[{company_name}] Исключение при запросе campaigns: {e}, попытка {attempt+1}/5")
            time.sleep(2)
    return []

def get_fullstats(api_key, ids, company_name):
    """Получение полной статистики по кампаниям"""
    url = "https://advert-api.wildberries.ru/adv/v3/fullstats"
    headers = {"Authorization": api_key}
    params = {
        "ids": ",".join(map(str, ids)),
        "beginDate": begin_date_str,
        "endDate": end_date_str
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        if resp.status_code == 200:
            print(f"[{company_name}] Получена статистика для {len(ids)} кампаний")
            return resp.json()
        else:
            print(f"[{company_name}] Ошибка запроса fullstats: {resp.status_code}")
            print(f"[{company_name}] Ответ: {resp.text[:200]}")
            return []
    except Exception as e:
        print(f"[{company_name}] Исключение при запросе fullstats: {e}")
        return []

# === Парсинг JSON структурированно ===
def parse_fullstats_detailed(data, company_name):
    """
    Детальный парсинг данных fullstats с сохранением связей между уровнями.
    Структура: campaign -> days -> apps -> nms (номенклатура)
    """
    all_records = []
    
    if not data:
        print(f"[{company_name}] Нет данных для парсинга")
        return pd.DataFrame()
    
    for campaign in data:
        # Базовые данные кампании (верхний уровень)
        campaign_id = campaign.get('advertId')
        campaign_base = {
            'advertId': campaign_id,
            'atbs': campaign.get('atbs'),
            'canceled': campaign.get('canceled'),
            'clicks': campaign.get('clicks'),
            'cpc': campaign.get('cpc'),
            'cr': campaign.get('cr'),
            'ctr': campaign.get('ctr'),
            'frq': campaign.get('frq'),
            'orders': campaign.get('orders'),
            'shks': campaign.get('shks'),
            'sum': campaign.get('sum'),
            'sum_price': campaign.get('sum_price'),
            'views': campaign.get('views')
        }
        
        # Обрабатываем дни (days)
        days = campaign.get('days', [])
        if not days:
            # Если нет дней, сохраняем хотя бы данные кампании
            all_records.append(campaign_base)
            continue
            
        for day in days:
            day_data = campaign_base.copy()
            day_data['date'] = day.get('date')
            day_data['day_atbs'] = day.get('atbs')
            day_data['day_canceled'] = day.get('canceled')
            day_data['day_clicks'] = day.get('clicks')
            day_data['day_cpc'] = day.get('cpc')
            day_data['day_cr'] = day.get('cr')
            day_data['day_ctr'] = day.get('ctr')
            day_data['day_orders'] = day.get('orders')
            day_data['day_shks'] = day.get('shks')
            day_data['day_sum'] = day.get('sum')
            day_data['day_sum_price'] = day.get('sum_price')
            day_data['day_views'] = day.get('views')
            
            # Обрабатываем приложения (apps)
            apps = day.get('apps', [])
            if not apps:
                # Если нет приложений, сохраняем данные дня
                all_records.append(day_data)
                continue
                
            for app in apps:
                app_data = day_data.copy()
                app_data['appType'] = app.get('appType')
                app_data['app_atbs'] = app.get('atbs')
                app_data['app_canceled'] = app.get('canceled')
                app_data['app_clicks'] = app.get('clicks')
                app_data['app_cpc'] = app.get('cpc')
                app_data['app_cr'] = app.get('cr')
                app_data['app_ctr'] = app.get('ctr')
                app_data['app_frq'] = app.get('frq')
                app_data['app_orders'] = app.get('orders')
                app_data['app_shks'] = app.get('shks')
                app_data['app_sum'] = app.get('sum')
                app_data['app_sum_price'] = app.get('sum_price')
                app_data['app_views'] = app.get('views')
                
                # Обрабатываем номенклатуру (nms) - ИСПРАВЛЕНО: было nm, стало nms
                nms = app.get('nms', [])
                if not nms:
                    # Если нет номенклатуры, сохраняем данные приложения
                    all_records.append(app_data)
                    continue
                    
                for nm in nms:
                    nm_data = app_data.copy()
                    nm_data['nmId'] = nm.get('nmId')
                    nm_data['name'] = nm.get('name')
                    nm_data['nm_atbs'] = nm.get('atbs')
                    nm_data['nm_canceled'] = nm.get('canceled')
                    nm_data['nm_clicks'] = nm.get('clicks')
                    nm_data['nm_cpc'] = nm.get('cpc')
                    nm_data['nm_cr'] = nm.get('cr')
                    nm_data['nm_ctr'] = nm.get('ctr')
                    nm_data['nm_frq'] = nm.get('frq')
                    nm_data['nm_orders'] = nm.get('orders')
                    nm_data['nm_shks'] = nm.get('shks')
                    nm_data['nm_sum'] = nm.get('sum')
                    nm_data['nm_sum_price'] = nm.get('sum_price')
                    nm_data['nm_views'] = nm.get('views')
                    
                    all_records.append(nm_data)
    
    df = pd.DataFrame(all_records)
    print(f"[{company_name}] Создан DataFrame с {len(df)} строками и {len(df.columns)} колонками")
    return df

# === Основной цикл ===
print(f"\n=== Начало обработки {len(dict_api)} компаний ===\n")

total_records_uploaded = 0
total_companies_processed = 0

for api_key, company_name in dict_api.items():
    print(f"\n{'='*60}")
    print(f"Обрабатываем компанию: {company_name}")
    print(f"{'='*60}")
    
    # Получаем список кампаний
    campaigns = get_campaigns(api_key, company_name)
    
    if not campaigns:
        print(f"[{company_name}] Не найдено кампаний, пропускаем")
        continue
    
    # Извлекаем ID кампаний
    campaign_ids = []
    for c in campaigns:
        advert_list = c.get("advert_list", [])
        for adv in advert_list:
            adv_id = adv.get("advertId")
            if adv_id:
                campaign_ids.append(adv_id)
    
    print(f"[{company_name}] Найдено {len(campaign_ids)} кампаний")
    
    if not campaign_ids:
        continue
    
    # Массив для накопления данных текущей компании
    company_data = []
    
    # Разбиваем на пачки по 100 ID (лимит API)
    batch_size = 100
    total_batches = (len(campaign_ids) - 1) // batch_size + 1
    
    for i in range(0, len(campaign_ids), batch_size):
        batch_ids = campaign_ids[i:i+batch_size]
        batch_num = i // batch_size + 1
        
        print(f"[{company_name}] Обрабатываем партию {batch_num}/{total_batches} ({len(batch_ids)} кампаний)")
        
        # Получаем статистику
        stats = get_fullstats(api_key, batch_ids, company_name)
        
        if stats:
            # Парсим данные детально
            df_stats = parse_fullstats_detailed(stats, company_name)
            
            if not df_stats.empty:
                df_stats["company"] = company_name
                df_stats["api_key_last4"] = api_key[-4:]
                company_data.append(df_stats)
            else:
                print(f"[{company_name}] Пустой DataFrame после парсинга")
        
        # Ждем перед следующим запросом (лимит: 1 запрос/мин для fullstats)
        if batch_num < total_batches:
            print(f"[{company_name}] Ожидание 60 сек перед следующим запросом...")
            time.sleep(60)
    
    # Загружаем данные текущей компании в PostgreSQL сразу после обработки
    if company_data:
        print(f"\n[{company_name}] Загрузка данных в PostgreSQL...")
        company_df = pd.concat(company_data, ignore_index=True)
        
        try:
            uploaded = upload_to_postgres(company_df, table_name='adv_fullstats', schema='reports', chunk_size=500)
            total_records_uploaded += uploaded
            total_companies_processed += 1
            print(f"[{company_name}] ✓ Загружено {uploaded} записей")
            
            # Освобождаем память
            del company_df
            del company_data
            
        except Exception as e:
            print(f"[{company_name}] ✗ Ошибка загрузки: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"[{company_name}] Нет данных для загрузки")

# === Итоговая сводка ===
print(f"\n{'='*60}")
print("ИТОГОВАЯ СВОДКА")
print(f"{'='*60}")

if total_companies_processed > 0:
    print(f"\n✓ Компаний обработано: {total_companies_processed}")
    print(f"✓ Всего загружено записей: {total_records_uploaded:,}")
    print(f"✓ Среднее записей на компанию: {total_records_uploaded // total_companies_processed:,}")
else:
    print("\n⚠️ Нет данных для сохранения")

print(f"\n{'='*60}")
print("✅ ОБРАБОТКА ЗАВЕРШЕНА")
print(f"{'='*60}\n")
