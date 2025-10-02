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

def get_goods_return(api_key):
    url = 'https://seller-analytics-api.wildberries.ru/api/v1/analytics/goods-return'
    start_date = datetime.today() - timedelta(days=30)
    end_date = datetime.today()
    header = {
        'Authorization':api_key
    }

    params = {
        "dateFrom":start_date,
        "dateTo":end_date
    }

    response = requests.get(url, headers=header, params=params)
    if response.status_code == 200:
        return response.json()['report']
    else:
        return f"Ошибка при получении данных {response.status_code}"



def create_data_frame(api_key):
    response = get_goods_return(api_key= api_key)
    print(response)
    if 'Ошибка при получении' in response:
        return 'Данные по API не получили по ошибке. Не удалось создать df'
    else:
        df = pd.DataFrame(response)
        df['update_time'] = datetime.now()
        df.columns = df.columns.str.lower()
        return  df


def save_data(engine, dict_api_and_supplier_name):
    for key, value in dict_api_and_supplier_name.items():
        df = create_data_frame(api_key=value)
        print(f'тут {df}')
        if isinstance(df, pd.DataFrame):
            if df.empty:
                print(f'скип {key}')
                continue
            else:
                df['supplier'] = key
                connect = engine.connect()

                # Отражение метаданных таблиц
                meta = MetaData(schema='reports')
                meta.reflect(bind=engine)
                print(meta.tables.keys())

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
                    index_elements=["srid"],  # Уникальный индекс (конфликт по полю "id")
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
        elif df == 'Данные по API не получили по ошибке. Не удалось создать df':
            print(f'скип {key}')
            continue
        else:
            print(f'Ошибка: неожиданный формат данных {type(df)} для {key}')
            continue





save_data(engine=engine, dict_api_and_supplier_name=dict_api_and_supplier_name)