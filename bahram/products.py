#!/usr/bin/env python3

import datetime
import requests
import json
from IPython.display import clear_output
import pandas as pd
import gspread
import time
from sqlalchemy import text
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine
import psycopg2
# Укажите параметры подключения
print(datetime.now())
db_params = {
    'dbname': 'wb_baah',
    'user': 'bahram',
    'password': 'Dadajonim99',
    'host': '94.103.84.245',  # Например, 'localhost' или IP-адрес сервера
    'port': '5432',  # Обычно 5432 для PostgreSQL
}

engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

#gc = gspread.service_account(filename='cred.json')
gc = gspread.service_account(filename='/home/baakhofficial/wbauto/bahram/cred.json')
key = '1Kt-EfIrLIOKcttybdpYgAK3Z20daRIaIJCs3vI30QTM'
rec_wsh = gc.open_by_key(key).worksheet("Товары")
df_gdata = pd.DataFrame(rec_wsh.get_all_records())
df_gdata = df_gdata[df_gdata['ID'] != '']

df_gdata.rename(columns={
     "Код товара":'nm_id',
     "Юрлицо":'supplier',
     "Название":'article',
     "Категория":'category',
     'Ссылка':'wb_link',
     'Название в закупе':'purchase_article',
     'Наш не наш':'is_ours'
 },inplace=True)


df_gdata.drop(columns=['ID','CID'], inplace=True)

df_gdata['nm_id'] = df_gdata['nm_id'].astype('int')
df_gdata['update_time'] = datetime.now()

#df_gdata.to_excel('data_products.xlsx')
df_gdata.to_sql('products', engine, schema='products',if_exists='append', index=False)
query = """
DELETE FROM products.products
WHERE update_time < (
    SELECT MAX(update_time)
    FROM products.products
);
"""

try:
    # Подключение к базе данных
    connection = psycopg2.connect(**db_params)
    cursor = connection.cursor()

    # Выполнение запроса
    cursor.execute(query)

    # Зафиксировать изменения
    connection.commit()

    print("Запрос выполнен успешно!")

except Exception as e:
    print("Произошла ошибка:", e)
    if connection:
        connection.rollback()  # Отмена изменений в случае ошибки
finally:
    if cursor:
        cursor.close()
    if connection:
        connection.close()

expected_headers = ['Дата', 'Кому', 'Товар', 'Стоимость закупа','Количество', 'Ставка Фуллфилмент','Сумма','Стоимость закупа для инвестора', 'Сумма закупа для инвестора']


rec_wsh = gc.open_by_key(key).worksheet("Закупы")
data = rec_wsh.get('A1:J')

purchases = pd.DataFrame(data[1:], columns=data[0])
# Заменяем запятые на точки в строках числовых столбцов
float_columns = [
    'Стоимость закупа', 'Количество', 'Ставка Фуллфилмент',
    'Сумма', 'Сумма ФФ', 'Стоимость закупа для инвестора', 'Сумма закупа для инвестора'
]

# Заменяем запятые на точки и приводим к типу float
for col in float_columns:
    purchases[col] = purchases[col].apply(lambda x: str(x).replace(' ', '').replace(' ', '').replace(',', '.') if isinstance(x, str) else x)
    purchases[col] = pd.to_numeric(purchases[col])  # Преобразуем в float

# Удаляем строки, где поле 'Кому' пустое
purchases = purchases[(purchases['Кому'] != '')|(purchases['Товар']!='')]

# Переименовываем столбцы
purchases.rename(columns={
    "Дата": 'create_date',
    "Кому": 'supplier',
    "Товар": 'article',
    "Стоимость закупа": 'price',
    'Количество': 'quantity',
    'Ставка Фуллфилмент': 'fulfillment',
    'Сумма': 'total_amount',
    'Сумма ФФ': 'fulfillment_amount',
    'Количество': 'quantity',
    'Стоимость закупа для инвестора': 'price_for_investor',
    'Сумма закупа для инвестора': 'total_amount_for_investor',
    '': 'comment'
}, inplace=True)

# Добавляем время обновления
purchases['update_time'] = datetime.now()
#purchases.to_excel('data.xlsx')

purchases.to_sql('purchases', engine, schema='products', if_exists='append', index=False)



# SQL-запрос
query = """
DELETE FROM products.purchases
WHERE update_time < (
    SELECT MAX(update_time)
    FROM products.purchases
);
"""

try:
    # Подключение к базе данных
    connection = psycopg2.connect(**db_params)
    cursor = connection.cursor()

    # Выполнение запроса
    cursor.execute(query)

    # Зафиксировать изменения
    connection.commit()

    print("purchases Запрос выполнен успешно!")

except Exception as e:
    print("Произошла ошибка:", e)
    if connection:
        connection.rollback()  # Отмена изменений в случае ошибки
finally:
    if cursor:
        cursor.close()
    if connection:
        connection.close()
