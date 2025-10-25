#!/usr/bin/env python3

import requests
import pandas as pd
import gspread
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text, inspect
import time
import logging
import json

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


# Период для получения данных (с 1 марта 2025 года до сегодня)
start_date = datetime(2025, 10, 1).strftime('%Y-%m-%d')
end_date = datetime.now().strftime('%Y-%m-%d')


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


def make_request_with_retry(url, headers, params=None, max_retries=15, initial_delay=10):
    """
    Выполняет запрос с повторными попытками при ошибках 429 и 5xx.
    Увеличено количество попыток и время задержек для надежности.
    
    :param url: URL для запроса
    :param headers: Заголовки запроса
    :param params: Параметры запроса
    :param max_retries: Максимальное количество повторных попыток (по умолчанию 15)
    :param initial_delay: Начальная задержка в секундах (по умолчанию 10)
    :return: Response объект или None при неудаче
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params)
            
            # Успешный ответ
            if response.status_code == 200:
                logger.info(f"Успешный запрос после {attempt + 1} попыток")
                return response
            
            # Ошибка 429 (Too Many Requests) - нужно повторить с задержкой
            if response.status_code == 429:
                # Увеличенная экспоненциальная задержка: 10, 20, 40, 80, 160, 320, 640, 1280 сек
                delay = min(initial_delay * (2 ** attempt), 1800)  # Максимум 30 минут
                logger.warning(f"Ошибка 429 (Too Many Requests). Повторная попытка {attempt + 1}/{max_retries} через {delay} сек.")
                time.sleep(delay)
                continue
            
            # Ошибки 5xx (серверные ошибки) - можно повторить
            if 500 <= response.status_code < 600:
                delay = min(initial_delay * (3 ** attempt), 1800)  # Максимум 30 минут
                logger.warning(f"Серверная ошибка {response.status_code}. Повторная попытка {attempt + 1}/{max_retries} через {delay} сек.")
                time.sleep(delay)
                continue
            # Другие ошибки (401, 403, 404 и т.д.) - не повторяем
            logger.error(f"Ошибка {response.status_code} - не повторяем")
            return response
            
        except requests.exceptions.RequestException as e:
            delay = min(initial_delay * (2 ** attempt), 1800)  # Максимум 30 минут
            logger.error(f"Ошибка сети при запросе: {e}. Повторная попытка {attempt + 1}/{max_retries} через {delay} сек.")
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                logger.error(f"Исчерпаны все попытки запроса к {url}")
                return None
    
    logger.error(f"Не удалось выполнить запрос после {max_retries} попыток")
    return None


def check_task_status(api_key, task_id, max_attempts=50, delay=15):
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
            response = make_request_with_retry(status_url, headers, max_retries=10, initial_delay=5)
            
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


def get_paid_storage_data_for_supplier(ip, api_key, start_date, end_date):
    """
    Получает данные о платном хранении для одного поставщика за указанный период.
    
    :param ip: Имя поставщика
    :param api_key: API ключ
    :param start_date: Дата начала периода
    :param end_date: Дата окончания периода
    :return: DataFrame с данными или None при ошибке
    """
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

        response = make_request_with_retry(url, headers, params=params, max_retries=15, initial_delay=10)

        if not response or response.status_code != 200:
            logger.error(f"Ошибка создания задачи: {response.status_code if response else 'Нет ответа'} для {ip}")
            if response:
                logger.error(f"Ответ: {response.text}")
            return None
        
        task_id = response.json()['data']['taskId']
        logger.info(f"Создана задача {task_id} для {ip} за период {start_date} - {end_date}")
        
        # Шаг 2: Проверка статуса задачи
        if not check_task_status(api_key, task_id, max_attempts=50, delay=15):
            logger.error(f"Задача {task_id} не завершилась успешно для {ip}")
            return None
        
        # Шаг 3: Загрузка готового отчета
        download_url = f"https://seller-analytics-api.wildberries.ru/api/v1/paid_storage/tasks/{task_id}/download"
        headers = {'Authorization': api_key}
        
        response_data = make_request_with_retry(download_url, headers, max_retries=15, initial_delay=10)

        if not response_data or response_data.status_code != 200:
            logger.error(f"Ошибка загрузки данных: {response_data.status_code if response_data else 'Нет ответа'} для {ip}")
            if response_data:
                logger.error(f"Ответ: {response_data.text}")
            return None
        
        # Шаг 4: Обработка данных
        data = response_data.json()
        
        if not data or len(data) == 0:
            logger.warning(f"Нет данных для {ip} за период {start_date} - {end_date}")
            return None
        
        df = pd.DataFrame(data)
        df['supplier'] = ip
        df.columns = df.columns.str.lower()
        df = df.replace('', None)
        df['update_time'] = datetime.now()
        
        logger.info(f"Получено {len(df)} записей для {ip} за период {start_date} - {end_date}")
        return df
        
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при обработке {ip}: {e}", exc_info=True)
        return None


def get_paid_storage_data(start_date, end_date):
    """
    Получает данные о платном хранении через API Wildberries с циклами по 8 дней.
    Оптимизированная версия с проверкой статуса задачи и динамическим управлением схемой БД.
    Пропускает ИП с ошибками авторизации после первой неудачной попытки.
    
    :param start_date: Дата начала периода
    :param end_date: Дата окончания периода
    :return: Сообщение о результате
    """
    success_count = 0
    error_count = 0
    auth_error_count = 0
    
    # Преобразуем строки в datetime объекты
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Вычисляем количество дней
    total_days = (end_dt - start_dt).days + 1
    logger.info(f"Общий период: {total_days} дней")
    
    for idx, row in df_investors.iterrows():
        ip = row['Имя Юрлица']
        api_key = row['API ключ']
        
        logger.info(f"Обработка данных для {ip}")
        
        all_dataframes = []
        auth_error_occurred = False
        
        # Разбиваем период на циклы по 8 дней
        current_start = start_dt
        cycle_count = 0
        while current_start <= end_dt and not auth_error_occurred:
            # Определяем конец текущего цикла (максимум 8 дней)
            current_end = min(current_start + timedelta(days=7), end_dt)
            
            period_start_str = current_start.strftime('%Y-%m-%d')
            period_end_str = current_end.strftime('%Y-%m-%d')
            
            logger.info(f"Запрос данных для {ip} за период {period_start_str} - {period_end_str}")
            
            # Получаем данные за текущий период
            df_period = get_paid_storage_data_for_supplier(ip, api_key, period_start_str, period_end_str)
            
            if df_period is not None:
                all_dataframes.append(df_period)
            else:
                # Проверяем, была ли это ошибка авторизации
                # Если в первом цикле нет данных и нет ответа - скорее всего ошибка авторизации
                if cycle_count == 0:
                    logger.warning(f"Первый запрос для {ip} не дал данных. Возможна ошибка авторизации. Пропускаем остальные периоды.")
                    auth_error_occurred = True
                    auth_error_count += 1
                    break
            
            # Переходим к следующему периоду
            current_start = current_end + timedelta(days=1)
            cycle_count += 1
            
            # Адаптивная пауза с учетом burst лимита API (3 запроса быстро, потом 120 сек)
            # Лимит API: 1 запрос/минуту, всплеск 5 запросов - увеличиваем паузы
            if current_start <= end_dt and not auth_error_occurred:  # Не ждем после последнего цикла
                if cycle_count % 3 == 0:
                    # После каждых 3 циклов - длинная пауза для восстановления burst лимита
                    logger.info(f"Пауза 120 секунд для соблюдения лимитов API (цикл {cycle_count})")
                    time.sleep(120)
                else:
                    # Между циклами внутри burst - средняя пауза
                    time.sleep(15)
        
        # Объединяем все данные за все периоды (только если не было ошибки авторизации)
        if all_dataframes and not auth_error_occurred:
            try:
                df_combined = pd.concat(all_dataframes, ignore_index=True)
                
                # Шаг 5: Проверка и создание недостающих столбцов
                ensure_table_columns(engine, 'reports', 'paid_storage', df_combined)
                
                # Шаг 6: Удаление существующих данных для этого ИП за период ПЕРЕД загрузкой новых
                delete_paid_storage_for_period(engine, ip, start_date, end_date)
                
                # Шаг 7: Загрузка новых данных в БД
                df_combined.to_sql(name='paid_storage', con=engine, schema='reports', if_exists='append', index=False)
                logger.info(f"Загружено {len(df_combined)} записей для {ip} за весь период")
                
                success_count += 1
                
            except Exception as e:
                logger.error(f"Ошибка при объединении данных для {ip}: {e}", exc_info=True)
                error_count += 1
        elif auth_error_occurred:
            logger.warning(f"Пропущен {ip} из-за ошибки авторизации")
        else:
            logger.warning(f"Не получено данных для {ip} за весь период")
            error_count += 1
        
        # Пауза между обработкой разных ИП для снижения нагрузки на API
        if idx < len(df_investors) - 1:  # Не ждем после последнего ИП
            logger.info(f"Пауза 30 секунд перед обработкой следующего ИП...")
            time.sleep(30)
    
    logger.info(f"Обработка завершена. Успешно: {success_count}, Ошибок: {error_count}, Ошибок авторизации: {auth_error_count}")
    return f"Данные успешно обновлены. Успешно: {success_count}, Ошибок: {error_count}, Ошибок авторизации: {auth_error_count}"


def save_raw_api_response_to_excel(start_date, end_date, supplier_name="Баах Р"):
    """
    Сохраняет оригинальный ответ API в Excel файл без обработок и преобразований.
    Тестовая функция для конкретного поставщика.
    
    :param start_date: Дата начала периода
    :param end_date: Дата окончания периода
    :param supplier_name: Имя поставщика для фильтрации
    :return: Путь к созданному Excel файлу
    """
    logger.info(f"Поиск данных для поставщика: {supplier_name}")
    
    # Находим данные для указанного поставщика
    supplier_data = df_investors[df_investors['Имя Юрлица'].str.contains(supplier_name, case=False, na=False)]
    
    if supplier_data.empty:
        logger.error(f"Поставщик '{supplier_name}' не найден в таблице инвесторов")
        return None
    
    supplier_row = supplier_data.iloc[0]
    ip = supplier_row['Имя Юрлица']
    api_key = supplier_row['API ключ']
    
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

        response = make_request_with_retry(url, headers, params=params, max_retries=15, initial_delay=10)

        if not response or response.status_code != 200:
            logger.error(f"Ошибка создания задачи: {response.status_code if response else 'Нет ответа'} для {ip}")
            if response:
                logger.error(f"Ответ: {response.text}")
            return None
        
        task_id = response.json()['data']['taskId']
        logger.info(f"Создана задача {task_id} для {ip}")
        
        # Шаг 2: Проверка статуса задачи
        if not check_task_status(api_key, task_id, max_attempts=50, delay=15):
            logger.error(f"Задача {task_id} не завершилась успешно для {ip}")
            return None
        
        # Шаг 3: Загрузка готового отчета
        download_url = f"https://seller-analytics-api.wildberries.ru/api/v1/paid_storage/tasks/{task_id}/download"
        headers = {'Authorization': api_key}
        
        response_data = make_request_with_retry(download_url, headers, max_retries=15, initial_delay=10)

        if not response_data or response_data.status_code != 200:
            logger.error(f"Ошибка загрузки данных: {response_data.status_code if response_data else 'Нет ответа'} для {ip}")
            if response_data:
                logger.error(f"Ответ: {response_data.text}")
            return None
        
        # Шаг 4: Сохранение оригинального ответа в Excel
        raw_data = response_data.json()
        
        if not raw_data or len(raw_data) == 0:
            logger.warning(f"Нет данных для {ip} за период {start_date} - {end_date}")
            return None
        
        # Создаем DataFrame из оригинальных данных
        df_raw = pd.DataFrame(raw_data)
        
        # Генерируем имя файла с временной меткой
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"raw_paid_storage_{supplier_name.replace(' ', '_')}_{start_date}_{end_date}_{timestamp}.xlsx"
        filepath = f"/home/baakhofficial/wbauto/bahram/{filename}"
        
        # Сохраняем в Excel с несколькими листами
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Лист 1: Оригинальные данные
            df_raw.to_excel(writer, sheet_name='Raw_Data', index=False)
            
            # Лист 2: Метаданные запроса
            metadata = {
                'supplier': [ip],
                'api_key': [api_key[:10] + '...' if len(api_key) > 10 else api_key],  # Маскируем ключ
                'start_date': [start_date],
                'end_date': [end_date],
                'task_id': [task_id],
                'download_time': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
                'total_records': [len(raw_data)]
            }
            df_metadata = pd.DataFrame(metadata)
            df_metadata.to_excel(writer, sheet_name='Metadata', index=False)
            
            # Лист 3: Структура данных (информация о столбцах)
            columns_info = {
                'column_name': df_raw.columns.tolist(),
                'data_type': [str(df_raw[col].dtype) for col in df_raw.columns],
                'non_null_count': [df_raw[col].count() for col in df_raw.columns],
                'null_count': [df_raw[col].isnull().sum() for col in df_raw.columns]
            }
            df_columns_info = pd.DataFrame(columns_info)
            df_columns_info.to_excel(writer, sheet_name='Columns_Info', index=False)
        
        logger.info(f"Оригинальные данные сохранены в файл: {filepath}")
        logger.info(f"Всего записей: {len(raw_data)}")
        logger.info(f"Столбцов: {len(df_raw.columns)}")
        
        return filepath
        
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных для {ip}: {e}", exc_info=True)
        return None


def delete_paid_storage_for_period(engine, supplier, date_start, date_end):
    """
    Удаляет существующие записи из таблицы reports.paid_storage для конкретного ИП за указанный период.
    
    Эта функция вызывается ПЕРЕД загрузкой новых данных, чтобы избежать дубликатов.
    Вместо сложной дедупликации просто удаляем старые данные и загружаем свежие.
    
    :param engine: Экземпляр SQLAlchemy Engine для подключения к базе данных
    :param supplier: Имя компании (ИП) для удаления данных. Если None, удаляется вся таблица за период
    :param date_start: Начальная дата периода (формат YYYY-MM-DD)
    :param date_end: Конечная дата периода (формат YYYY-MM-DD)
    """
    if supplier:
        query = """
        DELETE FROM reports.paid_storage
        WHERE supplier = :supplier
          AND date >= :date_start
          AND date <= :date_end
        """
        params = {'supplier': supplier, 'date_start': date_start, 'date_end': date_end}
    else:
        query = """
        DELETE FROM reports.paid_storage
        WHERE date >= :date_start
          AND date <= :date_end
        """
        params = {'date_start': date_start, 'date_end': date_end}

    try:
        with engine.begin() as connection:
            logger.info(f"Удаление существующих данных для {supplier} за период {date_start} - {date_end}")
            result = connection.execute(text(query), params)
            deleted_rows = result.rowcount
            logger.info(f"Удалено {deleted_rows} записей для {supplier} за период {date_start} - {date_end}")
            return deleted_rows
                
    except Exception as e:
        logger.error(f"Ошибка при удалении данных для {supplier}: {e}")
        raise


def get_paid_storage_for_single_supplier(supplier_name, start_date, end_date):
    """
    Получает данные о платном хранении для одного конкретного ИП за указанный период.
    
    :param supplier_name: Имя ИП (например, "ИП Астахова А.А.")
    :param start_date: Дата начала периода (формат YYYY-MM-DD)
    :param end_date: Дата окончания периода (формат YYYY-MM-DD)
    :return: Сообщение о результате
    """
    logger.info("=" * 80)
    logger.info(f"Запуск обновления для {supplier_name}")
    logger.info(f"Период: {start_date} - {end_date}")
    logger.info("=" * 80)
    
    # Находим данные для указанного поставщика
    supplier_data = df_investors[df_investors['Имя Юрлица'].str.contains(supplier_name, case=False, na=False)]
    
    if supplier_data.empty:
        error_msg = f"ИП '{supplier_name}' не найден в таблице инвесторов"
        logger.error(error_msg)
        return error_msg
    
    supplier_row = supplier_data.iloc[0]
    ip = supplier_row['Имя Юрлица']
    api_key = supplier_row['API ключ']
    
    logger.info(f"Найден ИП: {ip}")
    
    # Преобразуем строки в datetime объекты
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Вычисляем количество дней
    total_days = (end_dt - start_dt).days + 1
    logger.info(f"Общий период: {total_days} дней")
    
    all_dataframes = []
    auth_error_occurred = False
    
    # Разбиваем период на циклы по 8 дней
    current_start = start_dt
    cycle_count = 0
    while current_start <= end_dt and not auth_error_occurred:
        # Определяем конец текущего цикла (максимум 8 дней)
        current_end = min(current_start + timedelta(days=7), end_dt)
        
        period_start_str = current_start.strftime('%Y-%m-%d')
        period_end_str = current_end.strftime('%Y-%m-%d')
        
        logger.info(f"Запрос данных для {ip} за период {period_start_str} - {period_end_str}")
        
        # Получаем данные за текущий период
        df_period = get_paid_storage_data_for_supplier(ip, api_key, period_start_str, period_end_str)
        
        if df_period is not None:
            all_dataframes.append(df_period)
        else:
            # Проверяем, была ли это ошибка авторизации
            if cycle_count == 0:
                logger.warning(f"Первый запрос для {ip} не дал данных. Возможна ошибка авторизации.")
                auth_error_occurred = True
                return f"Ошибка получения данных для {ip} - возможна проблема с авторизацией"
        
        # Переходим к следующему периоду
        current_start = current_end + timedelta(days=1)
        cycle_count += 1
        
        # Пауза между циклами
        if current_start <= end_dt and not auth_error_occurred:
            if cycle_count % 3 == 0:
                logger.info(f"Пауза 120 секунд для соблюдения лимитов API (цикл {cycle_count})")
                time.sleep(120)
            else:
                time.sleep(15)
    
    # Объединяем все данные за все периоды
    if all_dataframes and not auth_error_occurred:
        try:
            df_combined = pd.concat(all_dataframes, ignore_index=True)
            
            # Проверка и создание недостающих столбцов
            ensure_table_columns(engine, 'reports', 'paid_storage', df_combined)
            
            # Удаление существующих данных для этого ИП за период ПЕРЕД загрузкой новых
            delete_paid_storage_for_period(engine, ip, start_date, end_date)
            
            # Загрузка новых данных в БД
            df_combined.to_sql(name='paid_storage', con=engine, schema='reports', if_exists='append', index=False)
            logger.info(f"✅ Загружено {len(df_combined)} записей для {ip} за весь период")
            
            success_msg = f"✅ Данные успешно обновлены для {ip}. Загружено {len(df_combined)} записей"
            logger.info(success_msg)
            return success_msg
            
        except Exception as e:
            error_msg = f"❌ Ошибка при обработке данных для {ip}: {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg
    else:
        error_msg = f"❌ Не получено данных для {ip} за период {start_date} - {end_date}"
        logger.warning(error_msg)
        return error_msg


def generate_report_from_march_2025():
    """
    Генерирует отчет о платном хранении с 1 марта 2025 года до текущей даты.
    Использует циклы по 8 дней для соблюдения лимитов API.
    """
    # Устанавливаем дату начала - 1 марта 2025 года
    march_1_2025 = datetime(2025, 3, 1)
    today = datetime.today()
    
    # Проверяем, что 1 марта 2025 еще не наступило
    if today < march_1_2025:
        logger.warning(f"1 марта 2025 года еще не наступило. Текущая дата: {today.strftime('%Y-%m-%d')}")
        return "Отчет не может быть сгенерирован - 1 марта 2025 года еще не наступило"
    
    start_date = march_1_2025.strftime('%Y-%m-%d')
    end_date = today.strftime('%Y-%m-%d')
    
    logger.info("=" * 80)
    logger.info(f"Генерация отчета о платном хранении с 1 марта 2025 года")
    logger.info(f"Период: {start_date} - {end_date}")
    logger.info(f"Общее количество дней: {(today - march_1_2025).days + 1}")
    logger.info("=" * 80)
    
    try:
        result = get_paid_storage_data(start_date, end_date)
        logger.info(result)
        logger.info("Отчет с 1 марта 2025 года завершен успешно")
        return result
    except Exception as e:
        logger.error(f"Критическая ошибка при генерации отчета с 1 марта 2025: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    # Запуск обычного обновления (45 дней назад до сегодня)
    logger.info("=" * 80)
    logger.info(f"Запуск обновления данных о платном хранении")
    logger.info(f"Период: {start_date} - {end_date}")
    logger.info(f"Общее количество дней: {(datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days + 1}")
    logger.info("=" * 80)
    
    try:
        result = get_paid_storage_data(start_date, end_date)
        logger.info(result)
        logger.info("Скрипт завершен успешно")
    except Exception as e:
        logger.error(f"Критическая ошибка при выполнении скрипта: {e}", exc_info=True)
        raise



