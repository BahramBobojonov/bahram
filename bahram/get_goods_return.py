#!/usr/bin/env python3

import requests
import pandas as pd
from sqlalchemy import text
from datetime import datetime, timedelta
from sqlalchemy import create_engine
import time
import gspread
from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.dialects.postgresql import insert
import logging
import json

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

gc = gspread.service_account(filename='/home/baakhofficial/wbauto/bahram/cred.json')
#gc = gspread.service_account(filename=r"C:\Users\vivar\wb_baah\tasks\files_for_server\cred.json")
worksheet = gc.open_by_key("15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ").sheet1
# Перенесем в Пандас поскольку так тупо проще работать
df_investors = pd.DataFrame(worksheet.get_all_records())
df_investors = df_investors[(df_investors['API ключ'] != '')&(df_investors['API ключ'] != None)]
#df_investors = df_investors.head(2)
dict_api_and_supplier_name = dict(zip(df_investors['Имя Юрлица'], df_investors['API ключ']))
print(dict_api_and_supplier_name)
api_key ='eyJhbGciOiJFUzI1NiIsImtpZCI6IjIwMjQxMTE4djEiLCJ0eXAiOiJKV1QifQ.eyJlbnQiOjEsImV4cCI6MTc0OTE1OTA0NiwiaWQiOiIwMTkzOTYyOC01NjgyLTczYzEtOGEzNC00OWVmNjNkYjIwYjEiLCJpaWQiOjI3Nzg3NDUxLCJvaWQiOjEyOTgwNiwicyI6NzkzNCwic2lkIjoiZmJkMjY3NjItNDE2NC00ZTUxLWJjODktZjIzZWY3MzhlOTBiIiwidCI6ZmFsc2UsInVpZCI6Mjc3ODc0NTF9.haxwKVnVJj7JarXas18uuk-q3kOlLWxQbX0ZffBfksNYUhvUtUQM90HbGxTwSfbvPC1v871Wl0zR-lLEElyy8w'


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

def get_goods_return(api_key, start_date, end_date):
    url = 'https://seller-analytics-api.wildberries.ru/api/v1/analytics/goods-return'
    header = {
        'Authorization':api_key
    }

    params = {
        "dateFrom":start_date.strftime('%Y-%m-%d'),
        "dateTo":end_date.strftime('%Y-%m-%d')
    }

    response = make_request_with_retry(url, header, params=params, max_retries=15, initial_delay=10)
    if response and response.status_code == 200:
        return response.json()['report']
    else:
        return f"Ошибка при получении данных {response.status_code if response else 'Нет ответа'}"



def create_data_frame(api_key, start_date, end_date):
    response = get_goods_return(api_key=api_key, start_date=start_date, end_date=end_date)
    logger.info(f"Получены данные за период {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}: {len(response) if isinstance(response, list) else 'ошибка'}")
    if 'Ошибка при получении' in str(response):
        return 'Данные по API не получили по ошибке. Не удалось создать df'
    else:
        df = pd.DataFrame(response)
        df['update_time'] = datetime.now()
        df.columns = df.columns.str.lower()
        return df


def generate_date_ranges(start_date, end_date, days_per_cycle=31):
    """
    Генерирует диапазоны дат по 31 дню для обхода ограничений API
    """
    date_ranges = []
    current_start = start_date
    
    while current_start <= end_date:
        current_end = min(current_start + timedelta(days=days_per_cycle - 1), end_date)
        date_ranges.append((current_start, current_end))
        current_start = current_end + timedelta(days=1)
    
    return date_ranges

def save_data(engine, dict_api_and_supplier_name):
    # Устанавливаем даты для получения данных с 1 марта 2025 года
    start_date = datetime(2025, 3, 1)  # 1 марта 2025 года
    end_date = datetime.today()  # До сегодняшнего дня
    
    logger.info(f"Начинаем получение данных с {start_date.strftime('%Y-%m-%d')} по {end_date.strftime('%Y-%m-%d')}")
    
    # Генерируем диапазоны дат по 31 дню
    date_ranges = generate_date_ranges(start_date, end_date)
    logger.info(f"Создано {len(date_ranges)} циклов по 31 дню")
    
    success_count = 0
    error_count = 0
    auth_error_count = 0
    
    for idx, (key, value) in enumerate(dict_api_and_supplier_name.items()):
        logger.info(f"\nОбрабатываем поставщика: {key}")
        
        all_dataframes = []  # Список для сбора всех DataFrame
        auth_error_occurred = False
        
        # Обрабатываем каждый диапазон дат
        for i, (cycle_start, cycle_end) in enumerate(date_ranges, 1):
            logger.info(f"Цикл {i}/{len(date_ranges)}: {cycle_start.strftime('%Y-%m-%d')} - {cycle_end.strftime('%Y-%m-%d')}")
            
            df = create_data_frame(api_key=value, start_date=cycle_start, end_date=cycle_end)
            
            if isinstance(df, pd.DataFrame):
                if not df.empty:
                    df['supplier'] = key
                    all_dataframes.append(df)
                    logger.info(f"Получено {len(df)} записей за этот период")
                else:
                    logger.info(f"Нет данных за период {cycle_start.strftime('%Y-%m-%d')} - {cycle_end.strftime('%Y-%m-%d')}")
            elif df == 'Данные по API не получили по ошибке. Не удалось создать df':
                logger.error(f'Ошибка API для периода {cycle_start.strftime("%Y-%m-%d")} - {cycle_end.strftime("%Y-%m-%d")}')
                # Если в первом цикле нет данных - скорее всего ошибка авторизации
                if i == 1:
                    logger.warning(f"Первый запрос для {key} не дал данных. Возможна ошибка авторизации. Пропускаем остальные периоды.")
                    auth_error_occurred = True
                    auth_error_count += 1
                    break
                continue
            else:
                logger.error(f'Неожиданный формат данных {type(df)} для периода {cycle_start.strftime("%Y-%m-%d")} - {cycle_end.strftime("%Y-%m-%d")}')
                continue
            
            # Адаптивная пауза с учетом burst лимита API
            if i < len(date_ranges) and not auth_error_occurred:  # Не ждем после последнего цикла
                if i % 3 == 0:
                    # После каждых 3 циклов - длинная пауза для восстановления burst лимита
                    logger.info(f"Пауза 120 секунд для соблюдения лимитов API (цикл {i})")
                    time.sleep(120)
                else:
                    # Между циклами внутри burst - средняя пауза
                    time.sleep(15)
        
        # Объединяем все DataFrame в один (только если не было ошибки авторизации)
        if all_dataframes and not auth_error_occurred:
            try:
                combined_df = pd.concat(all_dataframes, ignore_index=True)
                logger.info(f"Всего получено {len(combined_df)} записей для поставщика {key}")
                
                # Сохраняем данные в базу
                save_to_database(engine, combined_df, key)
                success_count += 1
            except Exception as e:
                logger.error(f"Ошибка при объединении данных для {key}: {e}")
                error_count += 1
        elif auth_error_occurred:
            logger.warning(f"Пропущен {key} из-за ошибки авторизации")
        else:
            logger.warning(f"Нет данных для поставщика {key}")
            error_count += 1
        
        # Пауза между обработкой разных поставщиков
        if idx < len(dict_api_and_supplier_name) - 1:  # Не ждем после последнего поставщика
            logger.info(f"Пауза 30 секунд перед обработкой следующего поставщика...")
            time.sleep(30)
    
    logger.info(f"Обработка завершена. Успешно: {success_count}, Ошибок: {error_count}, Ошибок авторизации: {auth_error_count}")

def save_to_database(engine, df, supplier_name):
    """
    Сохраняет DataFrame в базу данных
    """
    try:
        connect = engine.connect()

        # Отражение метаданных таблиц
        meta = MetaData(schema='reports')
        meta.reflect(bind=engine)
        logger.info(f"Доступные таблицы: {list(meta.tables.keys())}")

        # Получение таблицы
        table = meta.tables['reports.goods_return']

        # Формирование списка данных для вставки
        insrt_vals = df.to_dict(orient='records')

        # Размер чанка (например, 1000 строк)
        chunk_size = 1000

        # Подготовка INSERT-запроса
        insrt_stmnt = insert(table)

        # Добавление "ON CONFLICT DO UPDATE" для PostgreSQL
        do_update_stmt = insrt_stmnt.on_conflict_do_update(
            index_elements=["srid"],  # Уникальный индекс (конфликт по полю "srid")
            set_={  # Указываем, какие поля будут обновляться
                "status": insrt_stmnt.excluded.status,
                "barcode": insrt_stmnt.excluded.barcode,
                "brand": insrt_stmnt.excluded.brand,
                "dstofficeaddress": insrt_stmnt.excluded.dstofficeaddress,
                "dstofficeid": insrt_stmnt.excluded.dstofficeid,
                "isstatusactive": insrt_stmnt.excluded.isstatusactive,
                "nmid": insrt_stmnt.excluded.nmid,
                "orderdt": insrt_stmnt.excluded.orderdt,
                "returntype": insrt_stmnt.excluded.returntype,
                "shkid": insrt_stmnt.excluded.shkid,
                "srid": insrt_stmnt.excluded.srid,
                "update_time": insrt_stmnt.excluded.update_time,
                "stickerid": insrt_stmnt.excluded.stickerid,
                "subjectname": insrt_stmnt.excluded.subjectname,
                "techsize": insrt_stmnt.excluded.techsize,
                "supplier": insrt_stmnt.excluded.supplier,
                "orderid": insrt_stmnt.excluded.orderid,
                "readytoreturndt": insrt_stmnt.excluded.readytoreturndt,
                "reason": insrt_stmnt.excluded.reason,
                "expireddt": insrt_stmnt.excluded.expireddt,
                "completeddt": insrt_stmnt.excluded.completeddt
            }
        )

        # Вставка данных чанками
        with engine.begin() as connection:
            for i in range(0, len(insrt_vals), chunk_size):
                chunk = insrt_vals[i:i + chunk_size]
                chunk_stmt = do_update_stmt.values(chunk)  # Вставляем текущий чанк
                connection.execute(chunk_stmt)  # Выполнение запроса
        
        logger.info(f"Данные для поставщика {supplier_name} успешно сохранены в базу данных")
        
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных для поставщика {supplier_name}: {str(e)}")
    finally:
        if 'connect' in locals():
            connect.close()





if __name__ == "__main__":
    # Запуск обновления данных о возвратах товаров с 1 марта 2025 года
    logger.info("=" * 80)
    logger.info(f"Запуск обновления данных о возвратах товаров")
    logger.info(f"Период: с 1 марта 2025 года до {datetime.today().strftime('%Y-%m-%d')}")
    logger.info("=" * 80)
    
    try:
        save_data(engine=engine, dict_api_and_supplier_name=dict_api_and_supplier_name)
        logger.info("Скрипт завершен успешно")
    except Exception as e:
        logger.error(f"Критическая ошибка при выполнении скрипта: {e}", exc_info=True)
        raise