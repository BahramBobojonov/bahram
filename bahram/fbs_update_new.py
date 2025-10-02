#!/usr/bin/env python3


import requests
import gspread
from datetime import timedelta
import time
from datetime import datetime
import pandas as pd
import logging
import os

gc = gspread.service_account(filename='/home/baakhofficial/wbauto/bahram/cred.json')
#gc = gspread.service_account(filename=r"C:\Users\vivar\wb_baah\tasks\files_for_server\cred.json")
worksheet = gc.open_by_key("15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ").sheet1
# Перенесем в Пандас поскольку так тупо проще работать
df_investors = pd.DataFrame(worksheet.get_all_records())
df_investors = df_investors[(df_investors['API ключ'] != '') & (df_investors['API ключ'] != None)]
print(df_investors['Имя Юрлица'].unique())
#df_investors = df_investors[df_investors['Имя Юрлица'].isin(['ИП Баах Р.Н.'])]


api_keys = df_investors['API ключ'].unique()
print(api_keys)
# Конфигурация URL
orders_url = "https://marketplace-api.wildberries.ru/api/v3/orders"
statuses_url = "https://marketplace-api.wildberries.ru/api/v3/orders/status"


# Функция для генерации дат
def generate_date_ranges(start_date, end_date, delta_days=30):
    while start_date < end_date:
        next_date = start_date + timedelta(days=delta_days)
        yield start_date, min(next_date, end_date)
        start_date = next_date


# Дата начала (1 января 2023 года) и дата окончания (текущая дата)
start_date = datetime(2024, 1, 1)
end_date = datetime.now()

# DataFrames для хранения данных
all_orders_data = []
all_statuses_data = []

# Итерация по API-ключам
for api_key in api_keys:
    print(f"Начинаю обработку для API-ключа: {api_key}")

    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }

    # Итерация по периодам
    for period_start, period_end in generate_date_ranges(start_date, end_date):
        print(f"Обрабатываю период с {period_start.date()} по {period_end.date()}...")

        next_page = 0  # Инициализация пагинации
        while True:
            try:
                # Параметры запроса
                params = {
                    "limit": 1000,  # Максимальный размер страницы
                    "next": next_page,  # Текущая страница
                    "dateFrom": int(period_start.timestamp()),  # Начало периода
                    "dateTo": int(period_end.timestamp())  # Конец периода
                }

                # Запрос к API для получения заказов
                response = requests.get(orders_url, headers=headers, params=params)
                response.raise_for_status()

                try:
                    data = response.json()
                except ValueError:
                    print("Ответ от сервера не является валидным JSON.")
                    break

                # Проверка наличия данных
                if not data.get("orders"):
                    print("Данные закончились.")
                    break

                # Преобразование данных в DataFrame и добавление к orders_data
                orders = data["orders"]
                for order in orders:
                    order["api_key"] = api_key  # Добавляем поле API-ключа
                all_orders_data.extend(orders)

                # Получение ID заказов
                order_ids = [order["id"] for order in orders]
                payload = {"orders": order_ids}

                # Запрос для получения статусов
                status_response = requests.post(statuses_url, json=payload, headers=headers)
                status_response.raise_for_status()

                try:
                    status_data = status_response.json()
                except ValueError:
                    print("Ответ от сервера по статусам не является валидным JSON.")
                    break

                if status_data.get('orders'):
                    for status in status_data["orders"]:
                        status["api_key"] = api_key  # Добавляем поле API-ключа
                    all_statuses_data.extend(status_data["orders"])

                # Вывод информации о текущей итерации
                print(f"Обработано {len(orders)} сборочных заданий. Всего заказов: {len(all_orders_data)}.")
                print(
                    f"Обработано {len(status_data['orders']) if status_data.get('orders') else 0} статусов. Всего статусов: {len(all_statuses_data)}.")

                # Обновление параметра пагинации
                next_page = data.get("next")
                if not next_page:
                    break

                # Опциональная задержка между запросами
                time.sleep(1)

            except requests.exceptions.RequestException as e:
                print(f"Произошла ошибка: {e}")
                break

# Преобразование собранных данных в DataFrame
orders_df = pd.DataFrame(all_orders_data)
statuses_df = pd.DataFrame(all_statuses_data)

df_merge = orders_df.merge(statuses_df, on=['id', 'api_key'], how='left')
df_merge = df_merge.merge(df_investors[['API ключ', 'Имя Юрлица']], left_on='api_key', right_on='API ключ', how='left')
df_merge.drop(columns=['api_key', 'API ключ'], inplace=True)
df_merge.loc[(df_merge['wbStatus'].isin(['declined_by_client', 'canceled_by_client'])) & (
            df_merge['supplierStatus'] == 'new'), 'supplierStatus'] = 'cancel'

df_merge['scanPrice'] = df_merge['scanPrice'].astype('float')
df_merge['scanPrice'] = df_merge['scanPrice'] / 100

df_merge['isZeroOrder'] = df_merge['isZeroOrder'].astype('str')
df_merge['update_time'] = datetime.now()

df_merge.columns = df_merge.columns.str.lower()
df_merge.rename(columns={'имя юрлица': 'supplier'}, inplace=True)
df_merge['address'] = df_merge['address'].astype('str')
df_merge['offices'] = df_merge['offices'].astype('str')
df_merge['skus'] = df_merge['skus'].astype('str')
df_merge['options'] = df_merge['options'].astype('str')
df_merge['createdat'] = pd.to_datetime(df_merge['createdat'])

condition1 = (df_merge['supplier'] == 'TD') & (df_merge['createdat'] >= '2024-01-01')
condition2 = (df_merge['supplier'] == 'ИП Крапивина С.А.') & (df_merge['createdat'] >= '2024-03-25')

# Исключение записей, которые удовлетворяют любому из условий
df_merge = df_merge[~(condition1 | condition2)]
#df_merge.to_csv('double_сборочных_заданий.csv', sep=';', index = False)
df_merge = df_merge.drop_duplicates(subset ='id')
from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.dialects.postgresql import insert

#Создание соединения с базой данных
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')
connect = engine.connect()

# Отражение метаданных таблиц
meta = MetaData(schema='supplies')
meta.reflect(bind=engine)
print(meta.tables.keys())

# Получение таблицы
table = meta.tables['supplies.fbs_incomes']

# Формирование списка данных для вставки
insrt_vals = df_merge.to_dict(orient='records')

# Размер чанка (например, 1000 строк)
chunk_size = 1000

# Подготовка INSERT-запроса
insrt_stmnt = insert(table)

# Добавление "ON CONFLICT DO UPDATE" для PostgreSQL
do_update_stmt = insrt_stmnt.on_conflict_do_update(
    index_elements=["id"],  # Уникальный индекс (конфликт по полю "id")
    set_={  # Указываем, какие поля будут обновляться
        "wbstatus": insrt_stmnt.excluded.wbstatus,  # Обновление столбца wbstatus
        "supplierstatus": insrt_stmnt.excluded.supplierstatus,
        "update_time":  insrt_stmnt.excluded.update_time,# Обновление столбца supplierstatus
        "scanprice":  insrt_stmnt.excluded.scanprice# Обновление столбца supplierstatus
    }
)

# Вставка данных чанками
with engine.begin() as connection:
    for i in range(0, len(insrt_vals), chunk_size):
        chunk = insrt_vals[i:i + chunk_size]
        chunk_stmt = do_update_stmt.values(chunk)  # Вставляем текущий чанк
        connection.execute(chunk_stmt)  # Выполнение запроса