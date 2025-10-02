#!/usr/bin/env python3

import datetime
import requests
import json
from IPython.display import clear_output
import pandas as pd
import gspread
import time
dateFrom = "2024-05-28"
dateFrom = datetime.datetime.strptime(dateFrom,"%Y-%m-%d")
#dateFrom = datetime.datetime.timestamp(dateFrom)


gc = gspread.service_account(filename='/home/baakhofficial/wbauto/bahram/cred.json')
worksheet = gc.open_by_key("15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ").sheet1
# Перенесем в Пандас поскольку так тупо проще работать
df_investors = pd.DataFrame(worksheet.get_all_records())
df_investors = df_investors[(df_investors['API ключ'] != '')&(df_investors['API ключ'] != None)]

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
            df_report['legal_entity'] = legal_entity
            df_report_full = pd.concat([df_report_full,df_report])
        print('Finished')
#df_report_full.to_excel('df_report_full.xlsx', index = False)
df_report_full['date'] = pd.to_datetime(df_report_full['date']).dt.strftime('%Y-%m-%d')
df_report_full = df_report_full[['date','legal_entity','nmId','warehouseName','quantity','status']]

key = '1CqiTBg2pp0JyVk1RCcvvSF_c2s22EmwTCO4yZeobILE'
rec_wsh = gc.open_by_key(key).get_worksheet(3)
df_gdata = pd.DataFrame(rec_wsh.get_all_records())
df_gdata=df_gdata[['Дата', "Юрлицо", "ID","Номер склада", "Количество", "Статус", "Дата обновления"]]

def datetime_to_excel_serial_date(date):
    excel_base_date = datetime.datetime(1899, 12, 30)  # Excel's base date is December 30, 1899
    delta = date - excel_base_date
    excel_serial_date = delta.days + delta.seconds / (24 * 60 * 60)  # Include fraction of a day
    return excel_serial_date

df_report_full.rename(columns = {'date':'Дата','legal_entity':'Юрлицо','nmId':'ID','warehouseName':'Номер склада',
                                 'quantity':'Количество','status':'Статус'}
                       , inplace = True)

df_report_full['Дата обновления'] = datetime.datetime.now()
df_report_full['Дата обновления'] = df_report_full['Дата обновления'].astype('str')

df_report_full['Дата'] = pd.to_datetime(df_report_full['Дата'])
df_report_full=df_report_full.sort_values(by=['Дата', 'Юрлицо'],ascending=True)
df_gdata['Дата'] = pd.to_datetime(df_gdata['Дата'])
df_report_full['Дата'] = df_report_full['Дата'].apply(datetime_to_excel_serial_date)
df_gdata['Дата'] = df_gdata['Дата'].apply(datetime_to_excel_serial_date)
start_date=min(df_report_full["Дата"])
df_gdata=df_gdata[df_gdata["Дата"]<start_date]
result=pd.concat([df_gdata,df_report_full])
result = result.fillna('')


rec_wsh.batch_clear(["A:G"])
rec_wsh.update([result.columns.values.tolist()] + result.values.tolist())
rec_wsh.format('A',{'numberFormat':{'type':'DATE'}})

print("Данные успешно обновлены")