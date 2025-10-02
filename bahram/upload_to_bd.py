#!/usr/bin/env python3


import requests
import pandas as pd
from sqlalchemy import create_engine, MetaData
from sqlalchemy.dialects.postgresql import insert
import datetime
import time
import gspread 

credentials_file = '/home/baakhofficial/wbauto/bahram/cred.json' 
#credentials_file = 'cred.json'
spreadsheet_key = "1CqiTBg2pp0JyVk1RCcvvSF_c2s22EmwTCO4yZeobILE"
sheet_name = "Корректировка количества после инвентаризации"  # Укажите имя листа
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

def get_sheet_data_as_dataframe(credentials_file, spreadsheet_key, sheet_name):
    """
    Получает данные из указанного листа Google Sheets и возвращает их в формате DataFrame.
    :param credentials_file: Путь к файлу с учетными данными (JSON).
    :param spreadsheet_key: Ключ таблицы Google Sheets.
    :param sheet_name: Имя листа в таблице Google Sheets.
    :return: DataFrame с данными из листа Google Sheets.

    """
    # Авторизация через gspread
    gc = gspread.service_account(filename=credentials_file)

    # Открытие таблицы и листа
    worksheet = gc.open_by_key(spreadsheet_key).worksheet(sheet_name)

    # Загрузка данных в DataFrame
    data = worksheet.get_all_records(expected_headers=None)
    df = pd.DataFrame(data, dtype=object)
    return df

def upload_orders_to_db(engine, df):
    connect = engine.connect()
    meta = MetaData(schema='supplies')
    meta.reflect(bind=engine)
    print(meta.tables.keys())
    table = meta.tables['supplies.data_to_correct']

    insrt_vals = df.to_dict(orient='records')

    chunk_size = 1000
    insrt_stmnt = insert(table)
    do_update_stmt = insrt_stmnt.on_conflict_do_update(
        index_elements=["supplier", "purchase_article"],  # Уникальный индекс (конфликт по полям индекса)
        set_={  # Указываем, какие поля будут обновляться
            "adjustment_quantity": insrt_stmnt.excluded.adjustment_quantity,
            "comment": insrt_stmnt.excluded.comment,
            "comment_2": insrt_stmnt.excluded.comment_2
        }
    )
    with engine.begin() as connection:
        for i in range(0, len(insrt_vals), chunk_size):
            chunk = insrt_vals[i:i + chunk_size]
            chunk_stmt = do_update_stmt.values(chunk)  # Вставляем текущий чанк
            connection.execute(chunk_stmt)
    return print("Data uploaded successfully")

import numpy as np
df = get_sheet_data_as_dataframe(credentials_file, spreadsheet_key, sheet_name)
print((df.dtypes))
df['adjustment_quantity'] = df['adjustment_quantity'].replace('', np.nan)
df.rename(columns={'ИП':"supplier",
                   "Название":'purchase_article'}, inplace=True)

df['supplier'] = df['supplier'].fillna('no_data')
df['purchase_article'] = df['purchase_article'].fillna('no_data')
df['adjustment_quantity'] = df['adjustment_quantity'].astype('float')
df['adjustment_quantity'] = df['adjustment_quantity'].fillna(0)
df = df[['supplier','purchase_article','adjustment_quantity','comment','comment_2']]
print(df.columns)
print(df)
upload_orders_to_db(engine, df)