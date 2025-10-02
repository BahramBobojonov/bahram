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
spreadsheet_key = "15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ"
sheet_name = "Инвесторы"  # Укажите имя листа
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

today = datetime.date.today()
dates_last_30_days = [today - datetime.timedelta(days=i) for i in range(5)]
formatted_dates = [date.strftime('%Y-%m-%d') for date in dates_last_30_days]


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

def get_orders(api_key, date_from, flag: 0, supplier_name= None):
    url = 'https://statistics-api.wildberries.ru/api/v1/supplier/sales'
    headers = {
        'Authorization': api_key
    }

    params ={
        "dateFrom": date_from,
        "flag": flag
    }

    response = requests.get(url, headers=headers, params=params)
    print(f"{supplier_name} {response.status_code}")
    if response.status_code == 200:
        result = requests.get(url, headers=headers, params=params).json()
        if result:
            for item in result:
                item['supplier_name'] = supplier_name
            return result
        else:
            print(f"Empty response received for supplier {supplier_name}")
            return None
    else:
        print(f"Request failed with status code {response.status_code} for supplier {supplier_name}")
        return None


def upload_sales_to_db(engine, df):
    connect = engine.connect()
    meta = MetaData(schema='reports')
    meta.reflect(bind=engine)
    print(meta.tables.keys())
    table = meta.tables['reports.sales']

    insrt_vals = df.to_dict(orient='records')

    chunk_size = 1000
    insrt_stmnt = insert(table)
    do_update_stmt = insrt_stmnt.on_conflict_do_update(
        index_elements=["srid", "saleid"],  # Unique index (conflict based on indexed fields)
        set_={
            "date": insrt_stmnt.excluded.date,
            "lastchangedate": insrt_stmnt.excluded.lastchangedate,
            "warehousename": insrt_stmnt.excluded.warehousename,
            "warehousetype": insrt_stmnt.excluded.warehousetype,
            "countryname": insrt_stmnt.excluded.countryname,
            "oblastokrugname": insrt_stmnt.excluded.oblastokrugname,
            "regionname": insrt_stmnt.excluded.regionname,
            "supplierarticle": insrt_stmnt.excluded.supplierarticle,
            "nmid": insrt_stmnt.excluded.nmid,
            "barcode": insrt_stmnt.excluded.barcode,
            "category": insrt_stmnt.excluded.category,
            "subject": insrt_stmnt.excluded.subject,
            "brand": insrt_stmnt.excluded.brand,
            "techsize": insrt_stmnt.excluded.techsize,
            "incomeid": insrt_stmnt.excluded.incomeid,
            "issupply": insrt_stmnt.excluded.issupply,
            "isrealization": insrt_stmnt.excluded.isrealization,
            "totalprice": insrt_stmnt.excluded.totalprice,
            "discountpercent": insrt_stmnt.excluded.discountpercent,
            "spp": insrt_stmnt.excluded.spp,
            "paymentsaleamount": insrt_stmnt.excluded.paymentsaleamount,
            "forpay": insrt_stmnt.excluded.forpay,
            "finishedprice": insrt_stmnt.excluded.finishedprice,
            "pricewithdisc": insrt_stmnt.excluded.pricewithdisc,
            # "saleid": insrt_stmnt.excluded.saleid,
            "ordertype": insrt_stmnt.excluded.ordertype,
            "sticker": insrt_stmnt.excluded.sticker,
            "gnumber": insrt_stmnt.excluded.gnumber,
            "supplier_name": insrt_stmnt.excluded.supplier_name
        }
    )
    with engine.begin() as connection:
        for i in range(0, len(insrt_vals), chunk_size):
            chunk = insrt_vals[i:i + chunk_size]
            chunk_stmt = do_update_stmt.values(chunk)  # Вставляем текущий чанк
            connection.execute(chunk_stmt)
    return print("Data uploaded successfully")

df = get_sheet_data_as_dataframe(credentials_file, spreadsheet_key, sheet_name)
df = df[(df['API ключ'] != '')&(df['API ключ'] != None)&~((df['Имя Юрлица'] == 'TD') | (df['Имя Юрлица'] == 'ИП Крапивина С.А.'))]

print(df)
dict_api = dict(zip(df['API ключ'], df['Имя Юрлица']))


for date in formatted_dates:
    for api_key, supplier_name in dict_api.items():
        res = get_orders(api_key=api_key, date_from=date, flag=1, supplier_name=supplier_name)
        if res is not None and len(res) > 0:  # Проверка, что результат не пустой
            df = pd.DataFrame(res)
            df.columns = df.columns.str.lower()
            print(date)
            upload_sales_to_db(engine, df)
            del df
        else:
            print(f"Warning: No results for supplier {supplier_name} on date {date}")
    print(f"Processed date: {date}")
    time.sleep(60)





