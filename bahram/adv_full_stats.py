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

# Для тестирования можно ограничить количество компаний (закомментируйте следующие 3 строки для полного запуска)
# test_companies = ["ИП Баах Р.Н."]
# dict_api = {k: v for k, v in dict_api.items() if v in test_companies}
# print(f"🧪 ТЕСТОВЫЙ РЕЖИМ: обрабатываем только {len(dict_api)} компаний")

# === Параметры дат ===
end_date = datetime.now().date()
begin_date = datetime(2025, 10, 1).date()  # 1 марта 2025 года

print(f"📅 Общий период запроса: {begin_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
print(f"🏢 Всего компаний для обработки: {len(dict_api)}")

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
print(f"📊 Создано {len(date_periods)} периодов по 31 дню:")
for i, (start, end) in enumerate(date_periods, 1):
    print(f"  📅 Период {i}: {start} - {end}")

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
def get_campaigns_with_statuses(api_key, company_name, start_date=None, end_date=None):
    """
    Получение списка кампаний со статусами через метод /adv/v1/upd
    Возвращает словарь {campaign_id: {'status': status, 'name': name}}
    
    Метод поддерживает максимум 31 день за запрос, поэтому разбиваем на периоды
    """
    url = "https://advert-api.wildberries.ru/adv/v1/upd"
    headers = {"Authorization": api_key}
    
    # Если даты не указаны, берём последние 31 день
    if end_date is None:
        end_date = datetime.now().date()
    if start_date is None:
        start_date = end_date - timedelta(days=31)
    
    # Генерируем периоды по 31 день
    all_campaigns = {}
    current_start = start_date
    period_num = 0
    
    print(f"[{company_name}] 📅 Запрашиваем список кампаний через /adv/v1/upd за период {start_date} - {end_date}...")
    
    while current_start < end_date:
        current_end = min(current_start + timedelta(days=30), end_date)  # 31 день = start + 30 дней
        period_num += 1
        
        params = {
            "from": str(current_start),
            "to": str(current_end)
        }
        
        print(f"[{company_name}]   📆 Период {period_num}: {current_start} - {current_end}")
        
        for attempt in range(5):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"[{company_name}]     ✅ Получено {len(data)} записей")
                    
                    # Извлекаем уникальные кампании с их статусами
                    for record in data:
                        advert_id = record.get('advertId')
                        advert_status = record.get('advertStatus')
                        camp_name = record.get('campName', 'Без названия')
                        
                        if advert_id is not None:
                            # Обновляем только если новый статус более актуален
                            if advert_id not in all_campaigns:
                                all_campaigns[advert_id] = {
                                    'status': advert_status,
                                    'name': camp_name
                                }
                            else:
                                current_status = all_campaigns[advert_id]['status']
                                if current_status is None or (advert_status is not None and advert_status > current_status):
                                    all_campaigns[advert_id]['status'] = advert_status
                                    all_campaigns[advert_id]['name'] = camp_name
                    
                    # Пауза между запросами (лимит: 1 запрос в секунду)
                    time.sleep(2)
                    break  # Успешно получили данные, переходим к следующему периоду
                    
                elif resp.status_code == 401:
                    print(f"[{company_name}]     ❌ Ошибка авторизации (401)")
                    return {}
                elif resp.status_code == 429:
                    wait_time = 60 + (attempt * 30)
                    print(f"[{company_name}]     ⚠️ Ошибка 429, попытка {attempt+1}/5, ожидание {wait_time} сек")
                    time.sleep(wait_time)
                else:
                    print(f"[{company_name}]     ❌ Ошибка {resp.status_code}, попытка {attempt+1}/5")
                    time.sleep(30)
                    
            except Exception as e:
                print(f"[{company_name}]     ❌ Исключение: {e}, попытка {attempt+1}/5")
                time.sleep(30)
        
        # Переходим к следующему периоду
        current_start = current_end + timedelta(days=1)
    
    print(f"[{company_name}] ✅ Всего найдено {len(all_campaigns)} уникальных кампаний за весь период")
    return all_campaigns

def get_fullstats(api_key, ids, company_name, begin_date_str, end_date_str):
    """Получение полной статистики по кампаниям"""
    url = "https://advert-api.wildberries.ru/adv/v3/fullstats"
    headers = {"Authorization": api_key}
    params = {
        "ids": ",".join(map(str, ids)),
        "beginDate": begin_date_str,
        "endDate": end_date_str
    }
    
    for attempt in range(10):  # УВЕЛИЧЕНО: 10 попыток вместо 5
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=60)
            if resp.status_code == 200:
                print(f"[{company_name}] ✅ Получена статистика для {len(ids)} кампаний за период {begin_date_str} - {end_date_str}")
                return resp.json()
            elif resp.status_code == 429:
                # Обработка ошибки "too many requests"
                # Агрессивное увеличение: 3, 5, 7, 9, 11, 13, 15, 17, 19, 21 минут
                wait_time = 180 + (attempt * 120)  # 3 минуты + по 2 минуты за каждую попытку
                print(f"[{company_name}] ⚠️ Ошибка 429, попытка {attempt+1}/10, ожидание {wait_time} сек ({wait_time//60} мин)")
                time.sleep(wait_time)
            elif resp.status_code == 400:
                # Обработка ошибки 400
                error_text = resp.text
                print(f"[{company_name}] Ошибка 400")
                print(f"[{company_name}] Ответ: {error_text[:300]}")
                
                # Проверяем тип ошибки
                if "there are no statistics for this advertising period" in error_text.lower():
                    # Нет статистики за этот период - это нормально, кампании могли не быть активны
                    print(f"[{company_name}] ℹ️ Нет статистики за период {begin_date_str} - {end_date_str} (кампании неактивны)")
                    return []  # Возвращаем пустой список, это не ошибка
                
                elif "invalid advert status id" in error_text.lower():
                    # Неправильный статус кампании - это реальная ошибка
                    print(f"[{company_name}] ⚠️ Обнаружена кампания с неподходящим статусом")
                    
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
                                elif single_resp.status_code == 400 and "there are no statistics" in single_resp.text.lower():
                                    # Нет статистики - нормально
                                    print(f"[{company_name}] ℹ️ Кампания {single_id}: нет статистики за период")
                                else:
                                    print(f"[{company_name}] ✗ Кампания {single_id}: ошибка {single_resp.status_code}")
                            except Exception as e:
                                print(f"[{company_name}] ✗ Кампания {single_id}: исключение {e}")
                        
                        # КРИТИЧНО: пауза 2 минуты между запросами отдельных кампаний
                        wait_time = 120  # 2 минуты
                        print(f"⏰ [{company_name}] Ожидание {wait_time} сек между запросами отдельных кампаний...")
                        time.sleep(wait_time)
                    
                    if individual_results:
                        print(f"[{company_name}] Получена статистика для {len(individual_results)} кампаний из {len(ids)}")
                        return individual_results
                
                return []  # возвращаем пустой список если ничего не получилось
            else:
                print(f"[{company_name}] ❌ Ошибка запроса fullstats: {resp.status_code}, попытка {attempt+1}/10")
                print(f"[{company_name}] Ответ: {resp.text[:200]}")
                time.sleep(60)  # пауза 1 минута перед повтором
        except Exception as e:
            print(f"[{company_name}] ❌ Исключение при запросе fullstats: {e}, попытка {attempt+1}/10")
            time.sleep(60)
    
    print(f"[{company_name}] ❌ КРИТИЧНО: Не удалось получить данные после 10 попыток для периода {begin_date_str} - {end_date_str}")
    print(f"[{company_name}] 📝 ТРЕБУЕТСЯ ПОВТОРНЫЙ ЗАПУСК для периода: {begin_date_str} - {end_date_str}")
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
print(f"\n{'='*60}")
print(f"🚀 НАЧАЛО ОБРАБОТКИ {len(dict_api)} КОМПАНИЙ")
print(f"{'='*60}\n")

total_records_uploaded = 0
total_companies_processed = 0
successful_companies = 0
failed_periods = []  # Список пропущенных периодов для повторного запуска

for api_key, company_name in dict_api.items():
    print(f"\n{'='*60}")
    print(f"🏢 Обрабатываем компанию: {company_name}")
    print(f"🔑 API ключ: {api_key[:10]}...{api_key[-4:]}")
    print(f"{'='*60}")
    
    # Получаем список кампаний со статусами через /adv/v1/upd за весь период
    print(f"[{company_name}] Начинаем получение списка кампаний...")
    campaigns_dict = get_campaigns_with_statuses(api_key, company_name, start_date=begin_date, end_date=end_date)
    print(f"[{company_name}] Завершено получение списка кампаний")
    
    if not campaigns_dict:
        print(f"[{company_name}] Не найдено кампаний, пропускаем")
        continue
    
    # Фильтруем кампании по статусам 7, 9, 11 (для fullstats)
    valid_statuses = [7, 9, 11]
    campaign_ids = []
    filtered_out_campaigns_local = []
    
    status_names = {
        -1: "Удалена",
        4: "Готова к запуску",
        7: "Завершена",
        8: "Отменена",
        9: "Активна",
        11: "На паузе"
    }
    
    for camp_id, camp_info in campaigns_dict.items():
        status = camp_info['status']
        name = camp_info['name']
        
        if status in valid_statuses:
            campaign_ids.append(camp_id)
        else:
            status_name = status_names.get(status, f"Неизвестный ({status})")
            filtered_out_campaigns_local.append({
                'id': camp_id,
                'status': status,
                'status_name': status_name,
                'name': name
            })
            all_filtered_campaigns.append({
                'company': company_name,
                'id': camp_id,
                'status': status,
                'status_name': status_name,
                'name': name
            })
    
    print(f"[{company_name}] Найдено {len(campaigns_dict)} кампаний, из них:")
    print(f"  ✅ {len(campaign_ids)} подходят для fullstats (статусы 7, 9, 11):")
    for camp_id in campaign_ids[:10]:  # Показываем первые 10
        camp_info = campaigns_dict[camp_id]
        status_name = status_names.get(camp_info['status'], f"Статус {camp_info['status']}")
        print(f"    - ID {camp_id}: {status_name} - {camp_info['name']}")
    if len(campaign_ids) > 10:
        print(f"    ... и ещё {len(campaign_ids) - 10} кампаний")
    
    if filtered_out_campaigns_local:
        print(f"  ❌ {len(filtered_out_campaigns_local)} отфильтровано (другие статусы):")
        for fc in filtered_out_campaigns_local[:5]:  # Показываем первые 5
            print(f"    - ID {fc['id']}: статус {fc['status']} ({fc['status_name']}) - {fc['name']}")
        if len(filtered_out_campaigns_local) > 5:
            print(f"    ... и ещё {len(filtered_out_campaigns_local) - 5} кампаний")
    
    if not campaign_ids:
        print(f"[{company_name}] Нет кампаний с подходящими статусами, пропускаем")
        continue
    
    # Пауза после запроса upd (лимит: 1 запрос в секунду)
    print(f"[{company_name}] ⏳ Пауза 5 секунд после запроса списка кампаний...")
    time.sleep(5)
    
    # Массив для накопления данных текущей компании
    company_data = []
    company_failed_periods = []  # Пропущенные периоды для ЭТОЙ компании
    
    # Обрабатываем каждый период по 31 дню
    for period_num, (period_start, period_end) in enumerate(date_periods, 1):
        print(f"\n📅 [{company_name}] Период {period_num}/{len(date_periods)}: {period_start} - {period_end}")
        
        # Разбиваем на пачки по 100 ID (лимит API)
        batch_size = 100
        total_batches = (len(campaign_ids) - 1) // batch_size + 1
        
        for i in range(0, len(campaign_ids), batch_size):
            batch_ids = campaign_ids[i:i+batch_size]
            batch_num = i // batch_size + 1
            
            print(f"📊 [{company_name}] Период {period_num}, партия {batch_num}/{total_batches} ({len(batch_ids)} кампаний)")
            
            # Получаем статистику для текущего периода
            stats = get_fullstats(api_key, batch_ids, company_name, period_start, period_end)
            
            if not stats:
                # Если данные не получены, логируем период для повторного запуска
                period_info = {
                    'company': company_name,
                    'api_key': api_key[-4:],
                    'period_start': period_start,
                    'period_end': period_end,
                    'batch_num': batch_num,
                    'campaign_ids': batch_ids
                }
                failed_periods.append(period_info)
                company_failed_periods.append(period_info)  # Добавляем в список пропущенных для текущей компании
                print(f"⚠️ [{company_name}] Период {period_start} - {period_end} (партия {batch_num}) добавлен в список для повторного запуска")
            
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
            
            # Ждем перед следующим запросом (лимит API: 3 запроса/мин, интервал 20 сек)
            # Делаем паузу после КАЖДОГО запроса для соблюдения лимитов
            wait_time = 180  # 3 минуты для максимальной надёжности
            print(f"⏰ [{company_name}] Ожидание {wait_time} сек (3 мин) для соблюдения лимитов API...")
            time.sleep(wait_time)
    
    # ====== ПОВТОРНЫЙ ЗАПУСК ДЛЯ ПРОПУЩЕННЫХ ПЕРИОДОВ ======
    if company_failed_periods:
        print(f"\n{'='*60}")
        print(f"🔄 ПОВТОРНЫЙ ЗАПУСК ДЛЯ ПРОПУЩЕННЫХ ПЕРИОДОВ")
        print(f"{'='*60}")
        print(f"[{company_name}] Обнаружено {len(company_failed_periods)} пропущенных периодов")
        print(f"[{company_name}] Запускаем повторную обработку...")
        
        retry_success_count = 0
        remaining_failed = []
        
        for retry_num, period_info in enumerate(company_failed_periods, 1):
            period_start = period_info['period_start']
            period_end = period_info['period_end']
            batch_ids = period_info['campaign_ids']
            batch_num = period_info['batch_num']
            
            print(f"\n🔄 [{company_name}] Повторная попытка {retry_num}/{len(company_failed_periods)}")
            print(f"   Период: {period_start} - {period_end} (партия {batch_num})")
            
            # Повторный запрос статистики
            stats = get_fullstats(api_key, batch_ids, company_name, period_start, period_end)
            
            if stats:
                # Парсим данные
                df_stats = parse_fullstats_detailed(stats, company_name)
                
                if not df_stats.empty:
                    df_stats["company"] = company_name
                    df_stats["api_key_last4"] = api_key[-4:]
                    company_data.append(df_stats)
                    retry_success_count += 1
                    print(f"✅ [{company_name}] Период {period_start} - {period_end} успешно получен при повторе!")
                else:
                    print(f"⚠️ [{company_name}] Пустой DataFrame после парсинга")
                    remaining_failed.append(period_info)
            else:
                print(f"❌ [{company_name}] Период {period_start} - {period_end} не удалось получить и при повторе")
                remaining_failed.append(period_info)
            
            # Пауза между повторными запросами
            if retry_num < len(company_failed_periods):
                wait_time = 180  # 3 минуты
                print(f"⏰ [{company_name}] Ожидание {wait_time} сек перед следующим повтором...")
                time.sleep(wait_time)
        
        print(f"\n{'='*60}")
        print(f"📊 ИТОГИ ПОВТОРНОЙ ОБРАБОТКИ для {company_name}")
        print(f"{'='*60}")
        print(f"✅ Успешно получено при повторе: {retry_success_count}/{len(company_failed_periods)}")
        print(f"❌ Всё ещё не получено: {len(remaining_failed)}")
        
        # Обновляем список пропущенных периодов (удаляем успешные)
        for period_info in company_failed_periods:
            if period_info not in remaining_failed:
                failed_periods.remove(period_info)
    
    # Загружаем данные текущей компании в PostgreSQL сразу после обработки
    if company_data:
        print(f"\n💾 [{company_name}] Загрузка данных в PostgreSQL...")
        company_df = pd.concat(company_data, ignore_index=True)
        
        try:
            uploaded = upload_to_postgres(company_df, table_name='adv_fullstats', schema='reports', chunk_size=500)
            total_records_uploaded += uploaded
            total_companies_processed += 1
            successful_companies += 1
            print(f"✅ [{company_name}] Загружено {uploaded:,} записей")
            
            # Освобождаем память
            del company_df
            del company_data
            
        except Exception as e:
            print(f"❌ [{company_name}] Ошибка загрузки: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"⚠️ [{company_name}] Нет данных для загрузки")
    
    # Пауза между компаниями для соблюдения лимитов API
    print(f"⏰ Пауза 10 сек перед следующей компанией...")
    time.sleep(10)

# === Итоговая сводка ===
print(f"\n{'='*60}")
print("📊 ИТОГОВАЯ СВОДКА")
print(f"{'='*60}")

if total_companies_processed > 0:
    print(f"\n✅ Компаний успешно обработано: {successful_companies}")
    print(f"❌ Компаний с ошибками: {len(dict_api) - successful_companies}")
    print(f"📊 Всего загружено записей: {total_records_uploaded:,}")
    if successful_companies > 0:
        print(f"📈 Среднее записей на компанию: {total_records_uploaded // successful_companies:,}")
    print(f"📅 Период обработки: {begin_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    print(f"📊 Количество периодов: {len(date_periods)}")
    
    # Выводим информацию о пропущенных периодах
    if failed_periods:
        print(f"\n⚠️ ВНИМАНИЕ: Пропущено периодов: {len(failed_periods)}")
        print("📝 Список пропущенных периодов:")
        for fp in failed_periods:
            print(f"  - {fp['company']}: {fp['period_start']} - {fp['period_end']} (партия {fp['batch_num']})")
        
        # Сохраняем в файл для повторного запуска
        import json
        failed_log_path = '/home/baakhofficial/wbauto/failed_periods.json'
        with open(failed_log_path, 'w', encoding='utf-8') as f:
            json.dump(failed_periods, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Пропущенные периоды сохранены в: {failed_log_path}")
        print("📌 Запустите скрипт повторно для получения пропущенных данных")
    else:
        print(f"\n✅ Все периоды обработаны успешно!")
else:
    print("\n⚠️ Нет данных для сохранения")

print(f"\n{'='*60}")
print("🎉 ОБРАБОТКА ЗАВЕРШЕНА")
print(f"{'='*60}\n")
