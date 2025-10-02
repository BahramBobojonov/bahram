#!/usr/bin/env python3

import requests
import pandas as pd
import gspread
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text, inspect
import time
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

# Определяем путь к cred.json в зависимости от ОС
import os
cred_path = '/home/baakhofficial/wbauto/bahram/cred.json' if os.name != 'nt' else 'cred.json'
gc = gspread.service_account(filename=cred_path)
worksheet = gc.open_by_key("15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ").sheet1
# Перенесем в Пандас поскольку так тупо проще работать
df_investors = pd.DataFrame(worksheet.get_all_records())
df_investors = df_investors[(df_investors['API ключ'] != '')&(df_investors['API ключ'] != None)]


start_date = (datetime.today() - timedelta(days=8)).strftime('%Y-%m-%d')
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


def make_request_with_retry(url, headers, params=None, max_retries=5, initial_delay=5):
    """
    Выполняет запрос с повторными попытками при ошибках 429 и 5xx.
    
    :param url: URL для запроса
    :param headers: Заголовки запроса
    :param params: Параметры запроса
    :param max_retries: Максимальное количество повторных попыток
    :param initial_delay: Начальная задержка в секундах
    :return: Response объект или None при неудаче
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params)
            
            # Успешный ответ
            if response.status_code == 200:
                return response
            
            # Ошибка 429 (Too Many Requests) - нужно повторить с задержкой
            if response.status_code == 429:
                # Экспоненциальная задержка: 5, 10, 20, 40, 80 секунд
                delay = initial_delay * (2 ** attempt)
                logger.warning(f"Ошибка 429 (Too Many Requests). Повторная попытка {attempt + 1}/{max_retries} через {delay} сек.")
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


def check_task_status(api_key, task_id, max_attempts=20, delay=10):
    """
    Проверяет статус задачи через polling.
    
    :param api_key: API ключ
    :param task_id: ID задачи
    :param max_attempts: Максимальное количество попыток
    :param delay: Задержка между попытками в секундах
    :return: True если задача готова, False если нет
    """
    status_url = f"https://seller-analytics-api.wildberries.ru/api/v1/paid_storage/tasks/{task_id}/status"
    headers = {'Authorization': api_key}
    
    for attempt in range(max_attempts):
        try:
            response = make_request_with_retry(status_url, headers, max_retries=3, initial_delay=3)
            
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
            
            time.sleep(delay)
            
        except Exception as e:
            logger.error(f"Ошибка при проверке статуса задачи {task_id}: {e}")
            time.sleep(delay)
    
    logger.warning(f"Превышено время ожидания для задачи {task_id}")
    return False


def get_paid_storage_data(start_date, end_date):
    """
    Получает данные о платном хранении через API Wildberries.
    Оптимизированная версия с проверкой статуса задачи и динамическим управлением схемой БД.
    
    :param start_date: Дата начала периода
    :param end_date: Дата окончания периода
    :return: Сообщение о результате
    """
    success_count = 0
    error_count = 0
    
    for idx, row in df_investors.iterrows():
        ip = row['Имя Юрлица']
        api_key = row['API ключ']
        
        logger.info(f"Обработка данных для {ip}")
        
        try:
            # Шаг 1: Создание задачи на генерацию отчета
            url = "https://seller-analytics-api.wildberries.ru/api/v1/paid_storage"
            headers = {
                'Authorization': api_key,
                'Content-Type': 'application/json'
            }
            params = {
                'dateFrom': start_date,
                'dateTo': end_date
            }

            response = make_request_with_retry(url, headers, params=params, max_retries=5, initial_delay=5)

            if not response or response.status_code != 200:
                logger.error(f"Ошибка создания задачи: {response.status_code if response else 'Нет ответа'} для {ip}")
                if response:
                    logger.error(f"Ответ: {response.text}")
                error_count += 1
                continue
            
            task_id = response.json()['data']['taskId']
            logger.info(f"Создана задача {task_id} для {ip}")
            
            # Шаг 2: Проверка статуса задачи (polling вместо фиксированного ожидания)
            if not check_task_status(api_key, task_id, max_attempts=30, delay=5):
                logger.error(f"Задача {task_id} не завершилась успешно для {ip}")
                error_count += 1
                continue
            
            # Шаг 3: Загрузка готового отчета
            download_url = f"https://seller-analytics-api.wildberries.ru/api/v1/paid_storage/tasks/{task_id}/download"
            headers = {'Authorization': api_key}
            
            response_data = make_request_with_retry(download_url, headers, max_retries=5, initial_delay=5)

            if not response_data or response_data.status_code != 200:
                logger.error(f"Ошибка загрузки данных: {response_data.status_code if response_data else 'Нет ответа'} для {ip}")
                if response_data:
                    logger.error(f"Ответ: {response_data.text}")
                error_count += 1
                continue
            
            # Шаг 4: Обработка данных
            data = response_data.json()
            
            if not data or len(data) == 0:
                logger.warning(f"Нет данных для {ip} за период {start_date} - {end_date}")
                continue
            
            df = pd.DataFrame(data)
            df['supplier'] = ip
            df.columns = df.columns.str.lower()
            df = df.replace('', None)
            df['update_time'] = datetime.now()
            
            # Шаг 5: Проверка и создание недостающих столбцов
            ensure_table_columns(engine, 'reports', 'paid_storage', df)
            
            # Шаг 6: Загрузка данных в БД
            df.to_sql(name='paid_storage', con=engine, schema='reports', if_exists='append', index=False)
            logger.info(f"Загружено {len(df)} записей для {ip}")
            
            success_count += 1
            
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при обработке {ip}: {e}", exc_info=True)
            error_count += 1
            continue
    
    # Очистка старых записей после успешной загрузки
    if success_count > 0:
        logger.info("Начинаем удаление устаревших записей...")
        delete_old_paid_storage_records(engine)
    
    logger.info(f"Обработка завершена. Успешно: {success_count}, Ошибок: {error_count}")
    return f"Данные успешно обновлены. Успешно: {success_count}, Ошибок: {error_count}"


def delete_old_paid_storage_records(engine):
    """
    Удаляет старые записи из таблицы reports.paid_storage, оставляя только последнюю запись для каждого поставщика и даты.
    Оптимизированная версия с использованием CTE и window functions.

    :param engine: Экземпляр SQLAlchemy Engine для подключения к базе данных.
    """
    query = """
    WITH ranked_records AS (
        SELECT ctid,
               ROW_NUMBER() OVER (
                   PARTITION BY supplier, date 
                   ORDER BY update_time DESC
               ) AS rn
        FROM reports.paid_storage
    )
    DELETE FROM reports.paid_storage
    WHERE ctid IN (
        SELECT ctid 
        FROM ranked_records 
        WHERE rn > 1
    );
    """

    try:
        with engine.begin() as connection:
            logger.info("Выполняется SQL запрос на удаление дубликатов...")
            result = connection.execute(text(query))
            deleted_rows = result.rowcount
            logger.info(f"Удалено {deleted_rows} устаревших записей из таблицы paid_storage")
    except Exception as e:
        logger.error(f"Ошибка при удалении старых записей: {e}")
        raise


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info(f"Запуск обновления данных о платном хранении")
    logger.info(f"Период: {start_date} - {end_date}")
    logger.info("=" * 80)
    
    try:
        result = get_paid_storage_data(start_date, end_date)
        logger.info(result)
        logger.info("Скрипт завершен успешно")
    except Exception as e:
        logger.error(f"Критическая ошибка при выполнении скрипта: {e}", exc_info=True)
        raise



