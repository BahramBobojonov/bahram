#!/usr/bin/env python3

import datetime
import requests
import json
import pandas as pd
import gspread
import time

dateTo=datetime.datetime.today()
dateTo=datetime.datetime(dateTo.year,dateTo.month,dateTo.day)+datetime.timedelta(days=1)
amount_of_months_to_upload=3
dates=[dateTo]
for month_number in range(1,amount_of_months_to_upload+1):
    dates.append(dateTo-datetime.timedelta(days=month_number*29))
dates.sort()
#dates=[date.date() for date in dates]
start_date=dates[0]
dates=[datetime.datetime.timestamp(date) for date in dates]


#gc = gspread.service_account(filename='/home/baakhofficial/wbauto/bahram/cred.json')
worksheet = gc.open_by_key("15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ").sheet1
df_investors = pd.DataFrame(worksheet.get_all_records())
df_investors = df_investors[(df_investors['API стандартный'] != '')&(df_investors['API стандартный'] != None)]

df_report_full = pd.DataFrame()
for i in range(len(df_investors)):
    print('Starts',df_investors.iloc[i]['Имя Юрлица'])
    df_full = pd.DataFrame()
    api_stat_token = df_investors.iloc[i]['API стандартный']
    # Authorization parameter
    for month_number in range(amount_of_months_to_upload):
        #time.sleep(1)
        print("Месяц №",month_number+1)
        dateFrom=dates[month_number]
        dateTo=dates[month_number+1]
        headers = {
            'Authorization': api_stat_token}
        response = requests.get('https://suppliers-api.wildberries.ru/api/v3/orders',
                                headers=headers,
                                params={"dateFrom":int(dateFrom),"dateTo":int(dateTo), 'limit':1000, 'next':0})


        if response.status_code!=200:
            print('Ошибка запроса', response.status_code)
        else:
            jdata = json.loads(response.text)
            df_report = pd.DataFrame(jdata['orders'])
            if len(df_report)>0:
                #Join a status
                order_list = df_report[df_report['deliveryType'] == 'fbs']['id'].to_list()
                # Server request
                response = requests.post('https://suppliers-api.wildberries.ru/api/v3/orders/status',
                                        headers=headers,
                                        json={'orders': order_list})

                if response.status_code != 200:
                    print('Ошибка запроса', response.status_code)
                else:
                    stat_jdata = json.loads(response.text)
                    if len(stat_jdata['orders']) > 0:
                        df_statuses = pd.DataFrame(stat_jdata['orders'])
                        df_full = df_report.merge(right=df_statuses,how='inner',on='id')
                    else:
                        print("Запрос вернул пустую строку")


                while len(jdata['orders']) != 0:
                    response = requests.get('https://suppliers-api.wildberries.ru/api/v3/orders',
                                        headers=headers,
                                        params={"dateFrom":int(dateFrom),"dateTo":int(dateTo), 'limit':1000, 'next':jdata['next']})
                    jdata = json.loads(response.text)
                    df_report = pd.DataFrame(jdata['orders'])
                    if len(df_report) > 0:
                        # Join a status
                        order_list = df_report[df_report['deliveryType'] == 'fbs']['id'].to_list()
                        response = requests.post('https://suppliers-api.wildberries.ru/api/v3/orders/status',
                                                headers=headers,
                                                json={'orders': order_list})
                        if response.status_code != 200:
                            print('Ошибка запроса', response.status_code)
                        else:
                            stat_jdata = json.loads(response.text)
                            if len(stat_jdata['orders'])>0:
                                df_statuses = pd.DataFrame(stat_jdata['orders'])
                                df_full = pd.concat([df_full,df_report.merge(right=df_statuses,how='inner',on='id')])
                            else:
                                print("Запрос вернул пустую строку")


                df_full['legal_entity'] = df_investors.iloc[i]['Имя Юрлица']
                if len(df_full)>0:
                    df_report_full = pd.concat([df_report_full,df_full])
                print('Finished')
            else:
                print("Empty month")



df_report_full['createdAt'] = pd.to_datetime(df_report_full['createdAt']).apply(lambda x: x + datetime.timedelta(hours=3)).dt.strftime('%Y-%m-%d')
df_report_full["quantity"]=1
df_grouped_full = df_report_full.groupby(by=['createdAt','legal_entity','deliveryType','article','nmId','supplierStatus','wbStatus'], as_index=False)['quantity'].sum(numeric_only=True)



df_grouped_full.rename(columns = {'createdAt':'Дата','legal_entity':'ИП',
                                  'deliveryType':'Тип Поставки','article':'Артикул',
                                  'nmId':'Номер товара','supplierStatus':'Статус поставщика',
                                  'wbStatus':'Статус WB','quantity':'Количество'}
                       , inplace = True)
df_grouped_full['Дата'] = pd.to_datetime(df_grouped_full['Дата'])
df_grouped_full['Update Time'] = datetime.datetime.now()
df_grouped_full['Update Time'] = df_grouped_full['Update Time'].astype('str')

key = '1CqiTBg2pp0JyVk1RCcvvSF_c2s22EmwTCO4yZeobILE'
rec_wsh = gc.open_by_key(key).get_worksheet(1)
df_gdata = pd.DataFrame(rec_wsh.get_all_records())
df_gdata['Дата'] = pd.to_datetime(df_gdata['Дата'])

df_gdata=df_gdata[df_gdata["Дата"]<start_date]

result=pd.concat([df_gdata,df_grouped_full])
result['Дата'] = result['Дата'].astype('str')
result['Номер товара'] = result['Номер товара'].astype('str')

result['ID'] = result['ИП'] + " "+ result['Номер товара']

gc = gspread.service_account(filename='/home/baakhofficial/wbauto/bahram/cred.json')

# Открываем таблицу
spreadsheet = gc.open("OnlyWBaakh Траты, Закупы, Логистика")

# Выбираем лист "Сборочные задания"
wks = spreadsheet.worksheet("Товары")

all_data_from_tovari = pd.DataFrame(wks.get_all_records(expected_headers= None))
all_data_from_tovari = all_data_from_tovari[['ID', 'CID']]
all_data_from_tovari = all_data_from_tovari.drop_duplicates()
result.drop(columns='CID', inplace = True)
result = result.merge(all_data_from_tovari, on ='ID', how= 'left')
result['СтатусWB'] = result['Статус WB']
result['Кол-во'] = result['Количество']
result = result[['Дата', 'ИП', 'Тип Поставки', 'Артикул', 'Номер товара',
       'Статус поставщика', 'Статус WB', 'Количество', 'Update Time', 'ID','CID',
       'СтатусWB', 'Кол-во']]
result = result.fillna('')
print(result.dtypes)
rec_wsh.clear()
rec_wsh.update([result.columns.values.tolist()] + result.values.tolist())
print('Данные успешно обновлены')
