#!/usr/bin/env python3

import requests
import pandas as pd
import gspread
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text, inspect
import time
import logging
import os

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

# Определяем путь к cred.json в зависимости от ОС
cred_path = '/home/baakhofficial/wbauto/bahram/cred.json' if os.name != 'nt' else os.path.join(os.path.dirname(__file__), 'cred.json')
gc = gspread.service_account(filename=cred_path)
worksheet = gc.open_by_key("15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ").sheet1

# Перенесем в Пандас поскольку так тупо проще работать
df_investors = pd.DataFrame(worksheet.get_all_records())
df_investors = df_investors[(df_investors['API ключ'] != '')&(df_investors['API ключ'] != None)]
dict_api = dict(zip(df_investors['API ключ'], df_investors['Имя Юрлица']))

start_date = (datetime.today() - timedelta(days=45)).strftime('%Y-%m-%d')
end_date = datetime.today().strftime('%Y-%m-%d')


def ensure_table_columns(engine, schema, table_name, df):
    """
    Проверяет наличие всех столбцов из DataFrame в таблице PostgreSQL.
    Автоматически создает недостающие столбцы.
    
    :param engine: SQLAlchemy Engine
    :param schema: Схема базы данных
    :param table_name: Имя таблицы
    :param df: DataFrame с данными для вставки
    """
    inspector = inspect(engine)
    
    # Проверяем существование таблицы
    if not inspector.has_table(table_name, schema=schema):
        logger.info(f"Таблица {schema}.{table_name} не существует, будет создана автоматически")
        return
    
    # Получаем существующие столбцы
    existing_columns = {col['name'].lower() for col in inspector.get_columns(table_name, schema=schema)}
    
    # Получаем столбцы из DataFrame
    df_columns = set(df.columns.str.lower())
    
    # Находим недостающие столбцы
    missing_columns = df_columns - existing_columns
    
    if missing_columns:
        logger.info(f"Найдены новые столбцы: {missing_columns}")
        
        # Определяем типы данных для новых столбцов
        type_mapping = {
            'int64': 'BIGINT',
            'float64': 'DOUBLE PRECISION',
            'object': 'TEXT',
            'datetime64[ns]': 'TIMESTAMP',
            'bool': 'BOOLEAN'
        }
        
        with engine.begin() as connection:
            for column in missing_columns:
                # Определяем тип данных столбца
                dtype = str(df[column].dtype)
                pg_type = type_mapping.get(dtype, 'TEXT')
                
                # Создаем SQL запрос для добавления столбца
                alter_query = f'ALTER TABLE {schema}.{table_name} ADD COLUMN IF NOT EXISTS "{column}" {pg_type};'
                
                try:
                    connection.execute(text(alter_query))
                    logger.info(f"Добавлен столбец '{column}' типа {pg_type} в таблицу {schema}.{table_name}")
                except Exception as e:
                    logger.error(f"Ошибка при добавлении столбца '{column}': {e}")
                    raise


def make_request_with_retry(url, headers, params=None, max_retries=5, initial_delay=8):
    """
    Выполняет запрос с повторными попытками при ошибках 429 и 5xx.
    
    :param url: URL для запроса
    :param headers: Заголовки запроса
    :param params: Параметры запроса
    :param max_retries: Максимальное количество повторных попыток
    :param initial_delay: Начальная задержка в секундах (увеличена для избежания 429)
    :return: Response объект или None при неудаче
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=90)
            
            # Успешный ответ
            if response.status_code == 200:
                return response
            
            # Ошибка 429 (Too Many Requests) - нужно повторить с задержкой
            if response.status_code == 429:
                # Экспоненциальная задержка с увеличенной базой: 8, 16, 32, 64, 128 секунд
                delay = initial_delay * (2 ** attempt)
                logger.warning(f"⚠️ Ошибка 429 (Too Many Requests). Повторная попытка {attempt + 1}/{max_retries} через {delay} сек.")
                time.sleep(delay)
                continue
            
            # Ошибки 5xx (серверные ошибки) - можно повторить
            if 500 <= response.status_code < 600:
                delay = initial_delay * (2 ** attempt)
                logger.warning(f"Серверная ошибка {response.status_code}. Повторная попытка {attempt + 1}/{max_retries} через {delay} сек.")
                time.sleep(delay)
                continue
            
            # Другие ошибки (401, 403, 404 и т.д.) - не повторяем
            return response
            
        except requests.exceptions.RequestException as e:
            delay = initial_delay * (2 ** attempt)
            logger.error(f"Ошибка сети при запросе: {e}. Повторная попытка {attempt + 1}/{max_retries} через {delay} сек.")
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                logger.error(f"Исчерпаны все попытки запроса к {url}")
                return None
    
    logger.error(f"Не удалось выполнить запрос после {max_retries} попыток")
    return None


def check_task_status(api_key, task_id, max_attempts=60, delay=8):
    """
    Проверяет статус задачи через polling.
    
    Лимиты API: 1 запрос каждые 5 секунд
    
    :param api_key: API ключ
    :param task_id: ID задачи
    :param max_attempts: Максимальное количество попыток (по умолчанию 60 = 8 минут)
    :param delay: Задержка между попытками в секундах (8 сек с запасом для избежания 429)
    :return: True если задача готова, False если нет
    """
    status_url = f"https://seller-analytics-api.wildberries.ru/api/v1/acceptance_report/tasks/{task_id}/status"
    headers = {'Authorization': api_key}
    
    for attempt in range(max_attempts):
        try:
            response = make_request_with_retry(status_url, headers, max_retries=3, initial_delay=8)
            
            if response and response.status_code == 200:
                status_data = response.json()
                status = status_data.get('data', {}).get('status', '')
                
                if status == 'done':
                    logger.info(f"Задача {task_id} завершена успешно")
                    return True
                elif status == 'error':
                    logger.error(f"Задача {task_id} завершилась с ошибкой")
                    return False
                else:
                    logger.info(f"Задача {task_id} в статусе: {status}. Попытка {attempt + 1}/{max_attempts}")
            elif response and response.status_code == 404:
                logger.warning(f"Задача {task_id} не найдена (404)")
                return False
            
            # Не ждем после последней попытки
            if attempt < max_attempts - 1:
                time.sleep(delay)
            
        except Exception as e:
            logger.error(f"Ошибка при проверке статуса задачи {task_id}: {e}")
            if attempt < max_attempts - 1:
                time.sleep(delay)
    
    logger.warning(f"Превышено время ожидания для задачи {task_id}")
    return False


def get_acceptance_report(api_key, date_from, date_to, supplier):
    """
    Получает отчет приемки через новый асинхронный API.
    
    :param api_key: API ключ
    :param date_from: Дата начала периода
    :param date_to: Дата окончания периода
    :param supplier: Название поставщика
    :return: DataFrame с данными или None
    """
    try:
        # Шаг 1: Создание задачи на генерацию отчета
        url = 'https://seller-analytics-api.wildberries.ru/api/v1/acceptance_report'
        
        headers = {
            'Authorization': api_key,
            'Content-Type': 'application/json'
        }
        
        params = {
            'dateFrom': date_from,
            'dateTo': date_to
        }
        
        logger.info(f"[{supplier}] Создание задачи для периода {date_from} - {date_to}")
        response = make_request_with_retry(url, headers, params=params, max_retries=5, initial_delay=8)
        
        if not response or response.status_code != 200:
            logger.error(f"[{supplier}] Ошибка создания задачи: {response.status_code if response else 'Нет ответа'}")
            if response:
                logger.error(f"[{supplier}] Ответ: {response.text}")
            return None
        
        # Получаем task_id
        task_id = response.json().get('data', {}).get('taskId')
        if not task_id:
            logger.error(f"[{supplier}] Не получен task_id из ответа API")
            return None
            
        logger.info(f"[{supplier}] Создана задача {task_id}")
        
        # Шаг 2: Проверка статуса задачи (polling)
        # Лимит API: 1 запрос каждые 5 секунд, ждем до 8 минут с увеличенными таймаутами
        if not check_task_status(api_key, task_id, max_attempts=60, delay=8):
            logger.error(f"[{supplier}] Задача {task_id} не завершилась успешно")
            return None
        
        # Шаг 3: Загрузка готового отчета
        download_url = f"https://seller-analytics-api.wildberries.ru/api/v1/acceptance_report/tasks/{task_id}/download"
        headers = {'Authorization': api_key}
        
        logger.info(f"[{supplier}] Загрузка данных задачи {task_id}")
        response_data = make_request_with_retry(download_url, headers, max_retries=5, initial_delay=8)
        
        if not response_data or response_data.status_code != 200:
            logger.error(f"[{supplier}] Ошибка загрузки данных: {response_data.status_code if response_data else 'Нет ответа'}")
            if response_data:
                logger.error(f"[{supplier}] Ответ: {response_data.text}")
            return None
        
        # Шаг 4: Обработка данных
        data = response_data.json()
        
        # API может вернуть данные в разных форматах
        if isinstance(data, dict):
            # Если ответ содержит обертку, ищем данные внутри
            report_data = data.get('report', data.get('data', []))
        else:
            report_data = data
        
        if not report_data or len(report_data) == 0:
            logger.warning(f"[{supplier}] Нет данных за период {date_from} - {date_to}")
            return None
        
        df = pd.DataFrame(report_data)
        logger.info(f"[{supplier}] 📥 Получено {len(df)} записей за период {date_from} - {date_to}")
        
        # Проверяем структуру данных
        logger.info(f"[{supplier}] 📋 Столбцы в ответе API: {', '.join(df.columns.tolist())}")
        
        return df
        
    except Exception as e:
        logger.error(f"[{supplier}] Непредвиденная ошибка при получении отчета: {e}", exc_info=True)
        return None


def get_acceptance_reports_by_all_ip(dict_api, start_date, end_date):
    """
    Получает отчеты приемки для всех поставщиков и загружает в PostgreSQL.
    Обрабатывает каждого клиента отдельно с разбиением на периоды по 31 день.
    
    :param dict_api: Словарь {API ключ: Название поставщика}
    :param start_date: Дата начала периода (строка в формате ГГГГ-ММ-ДД)
    :param end_date: Дата окончания периода (строка в формате ГГГГ-ММ-ДД)
    :return: None
    """
    success_count = 0
    error_count = 0
    total_records = 0
    
    # Преобразуем строки в datetime объекты
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Вычисляем количество дней
    total_days = (end_dt - start_dt).days + 1
    
    logger.info("=" * 80)
    logger.info(f"Начало обработки {len(dict_api)} поставщиков")
    logger.info(f"Период: {start_date} - {end_date} ({total_days} дней)")
    logger.info("=" * 80)
    
    for api, supplier in dict_api.items():
        logger.info(f"\n{'='*60}")
        logger.info(f"Обработка поставщика: {supplier}")
        logger.info(f"{'='*60}")
        
        try:
            all_dataframes = []
            
            # Разбиваем период на циклы по 31 день (максимум для API)
            current_start = start_dt
            cycle_count = 0
            
            while current_start <= end_dt:
                # Определяем конец текущего цикла (максимум 31 день)
                current_end = min(current_start + timedelta(days=30), end_dt)
                
                period_start_str = current_start.strftime('%Y-%m-%d')
                period_end_str = current_end.strftime('%Y-%m-%d')
                
                logger.info(f"[{supplier}] Запрос данных за период {period_start_str} - {period_end_str}")
                
                # Получаем данные для текущего поставщика за текущий период
                df_period = get_acceptance_report(
                    api_key=api, 
                    date_from=period_start_str, 
                    date_to=period_end_str, 
                    supplier=supplier
                )
                
                if df_period is not None and not df_period.empty:
                    all_dataframes.append(df_period)
                    logger.info(f"[{supplier}] Получено {len(df_period)} записей за период")
                
                # Переходим к следующему периоду
                current_start = current_end + timedelta(days=1)
                cycle_count += 1
                
                # Пауза для соблюдения лимитов API (1 запрос/минуту) с запасом
                if current_start <= end_dt:  # Не ждем после последнего цикла
                    logger.info(f"[{supplier}] Пауза 75 секунд для соблюдения лимитов API (с запасом против 429)")
                    time.sleep(75)
            
            # Объединяем все данные за все периоды
            if all_dataframes:
                df_combined = pd.concat(all_dataframes, ignore_index=True)
                records_from_api = len(df_combined)
                logger.info(f"[{supplier}] 📥 Получено из API: {records_from_api} записей")
                
                # Добавляем метаданные
                df_combined['supplier'] = supplier
                df_combined['update_time'] = datetime.now()
                
                # Нормализуем названия столбцов
                df_combined.columns = df_combined.columns.str.lower()
                
                # Заменяем пустые строки на None
                df_combined = df_combined.replace('', None)
                
                # Проверяем количество уникальных записей по ключевым полям
                key_columns = ['shkcreatedate', 'incomeid', 'nmid', 'gicreatedate']
                # Проверяем какие из ключевых колонок есть в данных
                available_keys = [col for col in key_columns if col in df_combined.columns]
                if available_keys:
                    unique_records = df_combined.drop_duplicates(subset=available_keys).shape[0]
                    duplicates_in_api = records_from_api - unique_records
                    if duplicates_in_api > 0:
                        logger.warning(f"[{supplier}] ⚠️ В данных из API найдено {duplicates_in_api} дубликатов (по ключевым полям)")
                    logger.info(f"[{supplier}] 🔑 Уникальных записей по ключевым полям: {unique_records}")
                
                # Проверяем и создаем недостающие столбцы
                ensure_table_columns(engine, 'reports', 'acceptance', df_combined)
                
                # Подсчитываем записи в БД для этого поставщика ДО загрузки
                try:
                    with engine.begin() as connection:
                        count_query = text(f"SELECT COUNT(*) FROM reports.acceptance WHERE supplier = :supplier")
                        result = connection.execute(count_query, {"supplier": supplier})
                        count_before_load = result.fetchone()[0]
                        logger.info(f"[{supplier}] 📊 Записей в БД ДО загрузки: {count_before_load}")
                except Exception as e:
                    logger.warning(f"[{supplier}] Не удалось подсчитать записи до загрузки: {e}")
                    count_before_load = 0
                
                # Загружаем данные в PostgreSQL
                df_combined.to_sql(name='acceptance', con=engine, schema='reports', if_exists='append', index=False)
                logger.info(f"[{supplier}] ✅ Загружено {len(df_combined)} записей в БД")
                
                # Подсчитываем записи в БД для этого поставщика ПОСЛЕ загрузки
                try:
                    with engine.begin() as connection:
                        result = connection.execute(count_query, {"supplier": supplier})
                        count_after_load = result.fetchone()[0]
                        logger.info(f"[{supplier}] 📊 Записей в БД ПОСЛЕ загрузки: {count_after_load}")
                        added_records = count_after_load - count_before_load
                        if added_records == records_from_api:
                            logger.info(f"[{supplier}] ✅ Все записи загружены корректно ({added_records} = {records_from_api})")
                        else:
                            logger.warning(f"[{supplier}] ⚠️ Расхождение: загружено {added_records}, ожидалось {records_from_api}")
                except Exception as e:
                    logger.warning(f"[{supplier}] Не удалось подсчитать записи после загрузки: {e}")
                
                total_records += len(df_combined)
                success_count += 1
                
                # Освобождаем память
                del df_combined, all_dataframes
            else:
                logger.warning(f"[{supplier}] Нет данных для загрузки за весь период")
                
        except Exception as e:
            logger.error(f"[{supplier}] ✗ Ошибка при обработке: {e}", exc_info=True)
            error_count += 1
            continue
    
    # Очистка старых записей после успешной загрузки
    if success_count > 0:
        logger.info("\n" + "=" * 80)
        logger.info("НАЧАЛО ДЕДУПЛИКАЦИИ")
        logger.info("=" * 80)
        delete_old_acceptance_records(engine)
        
        # Подсчитываем записи по каждому поставщику ПОСЛЕ дедупликации
        logger.info("\n" + "=" * 80)
        logger.info("КОЛИЧЕСТВО ЗАПИСЕЙ ПО ПОСТАВЩИКАМ ПОСЛЕ ДЕДУПЛИКАЦИИ")
        logger.info("=" * 80)
        try:
            with engine.begin() as connection:
                supplier_count_query = """
                SELECT supplier, COUNT(*) as records_count
                FROM reports.acceptance
                GROUP BY supplier
                ORDER BY records_count DESC
                """
                result = connection.execute(text(supplier_count_query))
                total_after_dedup = 0
                for row in result:
                    supplier_name = row[0]
                    records_count = row[1]
                    logger.info(f"  [{supplier_name}]: {records_count} записей")
                    total_after_dedup += records_count
                logger.info(f"\n📊 ВСЕГО записей в БД после дедупликации: {total_after_dedup}")
        except Exception as e:
            logger.warning(f"Не удалось получить статистику по поставщикам: {e}")
    
    # Итоговая статистика
    logger.info("\n" + "=" * 80)
    logger.info("ИТОГОВАЯ СТАТИСТИКА")
    logger.info("=" * 80)
    logger.info(f"✓ Успешно обработано: {success_count} поставщиков")
    logger.info(f"✗ Ошибок: {error_count}")
    logger.info(f"✓ Всего получено из API: {total_records} записей")
    if success_count > 0:
        logger.info(f"✓ Среднее записей на поставщика (из API): {total_records // success_count}")
    logger.info("=" * 80)


def delete_old_acceptance_records(engine):
    """
    Удаляет дубликаты из таблицы reports.acceptance, оставляя только последнюю запись 
    для каждого уникального набора данных (по полю update_time).
    
    ВАЖНО: В ключ дедупликации включены все критичные поля:
    - supplier - Поставщик
    - shkcreatedate - Дата приёмки
    - incomeid - Номер поставки
    - nmid - Артикул WB
    - gicreatedate - Дата создания поставки
    
    Все эти поля вместе формируют уникальную запись о приёмке товара.
    Исторические данные сохраняются - удаляются ТОЛЬКО дубликаты с более ранним update_time.

    :param engine: Экземпляр SQLAlchemy Engine для подключения к базе данных.
    """
    try:
        with engine.begin() as connection:
            # Подсчитываем количество записей ДО дедупликации
            count_before_query = "SELECT COUNT(*) as total FROM reports.acceptance"
            result_before = connection.execute(text(count_before_query))
            count_before = result_before.fetchone()[0]
            logger.info(f"📊 Записей в БД ДО дедупликации: {count_before}")
            
            # Подсчитываем количество дубликатов, которые будут удалены
            duplicates_query = """
            WITH ranked_records AS (
                SELECT ctid,
                       ROW_NUMBER() OVER (
                           PARTITION BY supplier, shkcreatedate, incomeid, nmid, gicreatedate
                           ORDER BY update_time DESC
                       ) AS rn
                FROM reports.acceptance
            )
            SELECT COUNT(*) as duplicates
            FROM ranked_records 
            WHERE rn > 1
            """
            result_dup = connection.execute(text(duplicates_query))
            duplicates_count = result_dup.fetchone()[0]
            logger.info(f"🔍 Найдено дубликатов для удаления: {duplicates_count}")
            
            # Выполняем дедупликацию
            query = """
            WITH ranked_records AS (
                SELECT ctid,
                       ROW_NUMBER() OVER (
                           PARTITION BY supplier, shkcreatedate, incomeid, nmid, gicreatedate
                           ORDER BY update_time DESC
                       ) AS rn
                FROM reports.acceptance
            )
            DELETE FROM reports.acceptance
            WHERE ctid IN (
                SELECT ctid 
                FROM ranked_records 
                WHERE rn > 1
            );
            """
            
            logger.info("Выполняется SQL запрос на удаление дубликатов...")
            result = connection.execute(text(query))
            deleted_rows = result.rowcount
            logger.info(f"✓ Удалено {deleted_rows} дублированных записей")
            
            # Подсчитываем количество записей ПОСЛЕ дедупликации
            result_after = connection.execute(text(count_before_query))
            count_after = result_after.fetchone()[0]
            logger.info(f"📊 Записей в БД ПОСЛЕ дедупликации: {count_after}")
            
            # Проверяем корректность дедупликации
            expected_after = count_before - deleted_rows
            if count_after == expected_after:
                logger.info(f"✅ Дедупликация выполнена корректно: {count_before} - {deleted_rows} = {count_after}")
            else:
                logger.warning(f"⚠️ Несоответствие: ожидалось {expected_after}, получилось {count_after}")
                
    except Exception as e:
        logger.error(f"Ошибка при дедупликации записей: {e}")
        # Не прерываем выполнение, т.к. данные уже загружены


if __name__ == "__main__":
    try:
        get_acceptance_reports_by_all_ip(dict_api, start_date, end_date)
        logger.info("\n✅ Скрипт завершен успешно")
    except Exception as e:
        logger.error(f"\n❌ Критическая ошибка при выполнении скрипта: {e}", exc_info=True)
        raise