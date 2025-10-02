#!/usr/bin/env python3

import datetime
import requests
import json
import gspread
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy import insert, MetaData
from sqlalchemy.dialects.postgresql import insert



dateFrom = "2010-01-01"
dateFrom = datetime.datetime.strptime(dateFrom,"%Y-%m-%d")



engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')



def upload_orders_to_db(engine, df):
    connect = engine.connect()
    meta = MetaData(schema='supplies')
    meta.reflect(bind=engine)
    print(meta.tables.keys())
    table = meta.tables['supplies.fbo_incomes']

    # Convert DataFrame to list of dictionaries for inserting
    insrt_vals = df.to_dict(orient='records')

    chunk_size = 1000  # Chunk size for batching the insert operation
    insrt_stmnt = insert(table)

    # Define the ON CONFLICT DO UPDATE logic
    do_update_stmt = insrt_stmnt.on_conflict_do_update(
        index_elements=["nmid", "incomeid", "barcode"],  # Unique constraint based on nmid, incomeid, barcode
        set_={  # Fields to be updated in case of conflict
            "number": insrt_stmnt.excluded.number,
            "date": insrt_stmnt.excluded.date,
            "lastchangedate": insrt_stmnt.excluded.lastchangedate,
            "supplierarticle": insrt_stmnt.excluded.supplierarticle,
            "techsize": insrt_stmnt.excluded.techsize,
            "quantity": insrt_stmnt.excluded.quantity,
            "totalprice": insrt_stmnt.excluded.totalprice,
            "warehousename": insrt_stmnt.excluded.warehousename,
            "status": insrt_stmnt.excluded.status,
            "supplier": insrt_stmnt.excluded.supplier,
            "dateclose": insrt_stmnt.excluded.dateclose,
            "update_time": insrt_stmnt.excluded.update_time
        }
    )

    # Perform the insertion/update in chunks
    with engine.begin() as connection:
        for i in range(0, len(insrt_vals), chunk_size):
            chunk = insrt_vals[i:i + chunk_size]
            chunk_stmt = do_update_stmt.values(chunk)  # Insert/update the current chunk
            connection.execute(chunk_stmt)

    print("Data uploaded successfully")


gc = gspread.service_account(filename='/home/baakhofficial/wbauto/bahram/cred.json')

#gc = gspread.service_account(filename='cred.json')
worksheet = gc.open_by_key("15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ").sheet1
# Перенесем в Пандас поскольку так тупо проще работать
df_investors = pd.DataFrame(worksheet.get_all_records())
df_investors = df_investors[(df_investors['API ключ'] != '')&(df_investors['API ключ'] != None)]
#df_investors  = df_investors[df_investors['Имя Юрлица']=='ИП Баах И.Л.']
df_report_full = pd.DataFrame()
for i in range(len(df_investors)):
    df_report = pd.DataFrame()
    legal_entity = df_investors.iloc[i]['Имя Юрлица']
    print('Starts',legal_entity)
    api_stat_token = df_investors.iloc[i]['API ключ']
    # Authorization parameter
    headers = {
        'Authorization': api_stat_token}
    response = requests.get('https://statistics-api.wildberries.ru/api/v1/supplier/incomes',
                            headers=headers,
                            params={"dateFrom":dateFrom.date()})
    if response.status_code!=200:
        print('Ошибка запроса', response.status_code)
    else:
        print(response.status_code)
        print(response.json())
        if response.text != '[]':
            jdata = json.loads(response.text)
            df_report = pd.concat((pd.json_normalize(d) for d in jdata),axis=0)
            df_report['supplier'] = legal_entity
            #df_report.to_excel(r"C:\Users\vivar\OneDrive\Рабочий стол\Для инвентаризацииc.xlsx")
            df_report_full = pd.concat([df_report_full,df_report])
        print('Finished')

df_report_full['date'] = pd.to_datetime(df_report_full['date']).dt.strftime('%Y-%m-%d')


df_report_full.columns = df_report_full.columns.str.lower()
df_report_full['number'] = df_report_full['number'].replace('',None).astype('float')
condition1 = (df_report_full['supplier'] == 'TD') & (df_report_full['date'] >= '2024-01-01')
condition2 = (df_report_full['supplier'] == 'ИП Крапивина С.А.') & (df_report_full['date'] >= '2024-03-25')

# Исключение записей, которые удовлетворяют любому из условий
df_report_full = df_report_full[~(condition1 | condition2)]
from datetime import datetime
df_report_full['update_time'] = datetime.now()
df_report_full['incomeid'] = df_report_full['incomeid'].astype('int')
df_report_full['number'] = df_report_full['number'].astype('float')
df_report_full['quantity'] = df_report_full['quantity'].astype('float')
df_report_full['totalprice'] = df_report_full['totalprice'].astype('float')
df_report_full['nmid'] = df_report_full['nmid'].astype('int')
#df_report_full.to_excel(r"C:\Users\vivar\OneDrive\Рабочий стол\Для инвентаризации.xlsx")
upload_orders_to_db(engine=engine, df = df_report_full)

