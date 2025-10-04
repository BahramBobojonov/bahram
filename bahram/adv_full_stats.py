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

# ТЕСТОВЫЙ РЕЖИМ: работаем только с ИП Баах Р.Н.
test_company = "ИП Баах Р.Н."
dict_api = {k: v for k, v in dict_api.items() if v == test_company}
print(f"ТЕСТОВЫЙ РЕЖИМ: обрабатываем только компанию '{test_company}'")
print(f"Найдено API ключей для тестирования: {len(dict_api)}")

# === Параметры дат ===
end_date = datetime.now().date()
begin_date = end_date - timedelta(days=60)

print(f"Общий период запроса: {begin_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")

def generate_date_periods(start_date, end_date, period_days=31):
    """
    Генерирует список периодов по period_days дней для обхода ограничений API
    
    Args:
        start_date: начальная дата
        end_date: конечная дата  
        period_days: максимальное количество дней в периоде (по умолчанию 31)
    
    Returns:
        List of tuples: [(begin_date_str, end_date_str), ...]
    """
    periods = []
    current_start = start_date
    
    while current_start <= end_date:
        # Вычисляем конец текущего периода
        current_end = min(current_start + timedelta(days=period_days - 1), end_date)
        
        periods.append((
            current_start.strftime('%Y-%m-%d'),
            current_end.strftime('%Y-%m-%d')
        ))
        
        # Переходим к следующему периоду
        current_start = current_end + timedelta(days=1)
    
    return periods

# Генерируем периоды по 31 дню
date_periods = generate_date_periods(begin_date, end_date, 31)
print(f"Создано {len(date_periods)} периодов по 31 дню:")
for i, (start, end) in enumerate(date_periods, 1):
    print(f"  Период {i}: {start} - {end}")

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
    print(f"[{company_name}] Запрашиваем список кампаний...")
    
    for attempt in range(5):  # попытки при ошибке
        try:
            print(f"[{company_name}] Попытка {attempt+1}/5 запроса campaigns...")
            resp = requests.get(url, headers=headers, timeout=30)
            print(f"[{company_name}] Получен ответ: {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                print(f"[{company_name}] Получен ответ от promotion/count")
                return data.get('adverts', [])
            elif resp.status_code == 429:
                # Обработка ошибки "too many requests"
                wait_time = 60 + (attempt * 30)  # увеличиваем время ожидания с каждой попыткой
                print(f"[{company_name}] Ошибка 429 (too many requests), попытка {attempt+1}/5, ожидание {wait_time} сек")
                time.sleep(wait_time)
            else:
                print(f"[{company_name}] Ошибка запроса campaigns: {resp.status_code}, попытка {attempt+1}/5")
                time.sleep(5)  # увеличиваем паузу
        except Exception as e:
            print(f"[{company_name}] Исключение при запросе campaigns: {e}, попытка {attempt+1}/5")
            time.sleep(5)
    
    print(f"[{company_name}] Не удалось получить список кампаний после 5 попыток")
    return []

def get_fullstats(api_key, ids, company_name, begin_date_str, end_date_str):
    """Получение полной статистики по кампаниям"""
    url = "https://advert-api.wildberries.ru/adv/v3/fullstats"
    headers = {"Authorization": api_key}
    params = {
        "ids": ",".join(map(str, ids)),
        "beginDate": begin_date_str,
        "endDate": end_date_str
    }
    
    for attempt in range(5):  # попытки при ошибке
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=60)
            if resp.status_code == 200:
                print(f"[{company_name}] Получена статистика для {len(ids)} кампаний за период {begin_date_str} - {end_date_str}")
                return resp.json()
            elif resp.status_code == 429:
                # Обработка ошибки "too many requests"
                wait_time = 60 + (attempt * 30)  # увеличиваем время ожидания с каждой попыткой
                print(f"[{company_name}] Ошибка 429 (too many requests), попытка {attempt+1}/5, ожидание {wait_time} сек")
                time.sleep(wait_time)
            elif resp.status_code == 400:
                # Обработка ошибки "invalid advert status id" 
                print(f"[{company_name}] Ошибка 400 (invalid advert status)")
                print(f"[{company_name}] Ответ: {resp.text[:300]}")
                
                # Попробуем запросить статистику для каждой кампании отдельно
                if len(ids) > 1:
                    print(f"[{company_name}] Пробуем запросить статистику для каждой кампании отдельно...")
                    individual_results = []
                    for single_id in ids:
                        try:
                            single_resp = requests.get(url, headers=headers, params={
                                "ids": str(single_id),
                                "beginDate": begin_date_str,
                                "endDate": end_date_str
                            }, timeout=60)
                            if single_resp.status_code == 200:
                                individual_results.extend(single_resp.json())
                                print(f"[{company_name}] ✓ Получена статистика для кампании {single_id}")
                            else:
                                print(f"[{company_name}] ✗ Кампания {single_id}: ошибка {single_resp.status_code}")
                        except Exception as e:
                            print(f"[{company_name}] ✗ Кампания {single_id}: исключение {e}")
                        time.sleep(1)  # небольшая пауза между запросами
                    
                    if individual_results:
                        print(f"[{company_name}] Получена статистика для {len(individual_results)} кампаний из {len(ids)}")
                        return individual_results
                
                return []  # возвращаем пустой список если ничего не получилось
            else:
                print(f"[{company_name}] Ошибка запроса fullstats: {resp.status_code}, попытка {attempt+1}/5")
                print(f"[{company_name}] Ответ: {resp.text[:200]}")
                time.sleep(5)  # небольшая пауза перед повтором
        except Exception as e:
            print(f"[{company_name}] Исключение при запросе fullstats: {e}, попытка {attempt+1}/5")
            time.sleep(5)
    
    print(f"[{company_name}] Не удалось получить данные после 5 попыток")
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
    print(f"API ключ: {api_key[:10]}...{api_key[-4:]}")
    print(f"{'='*60}")
    
    # Получаем список кампаний
    print(f"[{company_name}] Начинаем получение списка кампаний...")
    campaigns = get_campaigns(api_key, company_name)
    print(f"[{company_name}] Завершено получение списка кампаний")
    
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
    
    # Примечание: API promotion/count не возвращает статус кампаний
    # Будем пробовать запрашивать статистику для всех кампаний
    # и обрабатывать ошибки 400 индивидуально
    print(f"[{company_name}] Попробуем запросить статистику для всех {len(campaign_ids)} кампаний")
    
    # Массив для накопления данных текущей компании
    company_data = []
    
    # Обрабатываем каждый период по 31 дню
    for period_num, (period_start, period_end) in enumerate(date_periods, 1):
        print(f"\n[{company_name}] Период {period_num}/{len(date_periods)}: {period_start} - {period_end}")
        
        # Разбиваем на пачки по 100 ID (лимит API)
        batch_size = 100
        total_batches = (len(campaign_ids) - 1) // batch_size + 1
        
        for i in range(0, len(campaign_ids), batch_size):
            batch_ids = campaign_ids[i:i+batch_size]
            batch_num = i // batch_size + 1
            
            print(f"[{company_name}] Период {period_num}, партия {batch_num}/{total_batches} ({len(batch_ids)} кампаний)")
            
            # Получаем статистику для текущего периода
            stats = get_fullstats(api_key, batch_ids, company_name, period_start, period_end)
            
            if stats:
                # Парсим данные детально
                df_stats = parse_fullstats_detailed(stats, company_name)
                
                if not df_stats.empty:
                    df_stats["company"] = company_name
                    df_stats["api_key_last4"] = api_key[-4:]
                    company_data.append(df_stats)
                else:
                    print(f"[{company_name}] Пустой DataFrame после парсинга")
            else:
                # Если не удалось получить данные (возможно из-за 429), увеличиваем паузу
                print(f"[{company_name}] Данные не получены, увеличиваем паузу до 120 сек...")
                time.sleep(120)
            
            # Ждем перед следующим запросом (лимит: 1 запрос/мин для fullstats)
            if batch_num < total_batches:
                print(f"[{company_name}] Ожидание 60 сек перед следующим запросом...")
                time.sleep(60)
        
        # Небольшая пауза между периодами
        if period_num < len(date_periods):
            print(f"[{company_name}] Пауза 5 сек перед следующим периодом...")
            time.sleep(5)
    
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
