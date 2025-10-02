#!/usr/bin/env python3
import datetime
import requests
import json
from IPython.display import clear_output
import pandas as pd
import gspread
import time

gc = gspread.service_account(filename = '/home/baakhofficial/wbauto/bahram/cred.json')
worksheet = gc.open_by_key("15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ").sheet1
# Перенесем в Пандас поскольку так тупо проще работать
df_investors = pd.DataFrame(worksheet.get_all_records())
df_investors = df_investors[(df_investors['API стандартный'] != '')&(df_investors['API стандартный'] != None)]
print(df_investors)

df_report_full = pd.DataFrame()
for i in range(len(df_investors)):
    len_kt = 0
    print('Starts',df_investors.iloc[i]['Имя Юрлица'])
    api_stat_token = df_investors.iloc[i]['API стандартный']
    legal_entity = df_investors.iloc[i]['Имя Юрлица']
    # Authorization parameter
    headers = {
        'Authorization': api_stat_token}
    response = requests.post('https://content-api.wildberries.ru/content/v2/get/cards/list',
                            headers=headers,
                            json={"settings":{"cursor":{'limit':int(100)},'filter':{'withPhoto':int(-1)},'sort':{"ascending":False}}})
    if response.status_code!=200:
        print('Ошибка запроса', response.status_code)
    else:
        jdata = json.loads(response.text)


        if jdata['cursor']['total'] != 0:
            df_report = pd.DataFrame(jdata['cards'])

            while jdata['cursor']['total'] != 0:

                response = requests.post('https://content-api.wildberries.ru/content/v2/get/cards/list',
                                        headers=headers,
                                        json={"settings":{"cursor":{'limit':int(100),'updatedAt': jdata['cursor']['updatedAt'], 'nmID': jdata['cursor']['nmID']},'filter':{'withPhoto':int(-1)},'sort':{"ascending":False}}})
                if response.status_code != 200:
                    print('Ошибка запроса', response.status_code)
                else:
                    jdata = json.loads(response.text)
                    if jdata['cursor']['total'] == 0:
                        continue

                    df_report = pd.concat([df_report,pd.DataFrame(jdata['cards'])])

            print('Выгружено',len(df_report),'карточек из основного пула')
            df_report['legalEntity'] = legal_entity
            df_report_full = pd.concat([df_report_full,df_report])
        else:
            print('Карточек нет')

    # Now getting everything from a trash
    response = requests.post('https://content-api.wildberries.ru/content/v2/get/cards/trash',
                        headers=headers,
                        json= {"settings": {"cursor": {"limit": 100},'sort':{"ascending":False}}}
                             )
    response = requests.post('https://content-api.wildberries.ru/content/v2/get/cards/trash',
                             headers=headers,
                             json={"settings": {"cursor": {"limit": 100}, 'sort': {"ascending": False}}}
                             )
    if response.status_code != 200:
        print('Ошибка запроса', response.status_code)
    else:
        jdata = json.loads(response.text)
        print((jdata))
        print(type(jdata))
        print(jdata['cards'])
        print(len(jdata['cards']))
        if len(jdata['cards']) != 0:

            df_report = pd.DataFrame(jdata['cards'])

            while jdata['cursor']['total'] != 0:
                response = requests.post('https://content-api.wildberries.ru/content/v2/get/cards/trash',
                                         headers=headers,
                                         json={"settings": {
                                             "cursor": {'limit': int(100), 'trashedAt': jdata['cursor']['trashedAt'],
                                                        'nmID': jdata['cursor']['nmID']},
                                             'sort': {"ascending": False}}})
                jdata = json.loads(response.text)
                if len(jdata['cards']) == 0:
                    continue

                df_report = pd.concat([df_report, pd.DataFrame(jdata['cards'])])
            print(len(df_report), "товаров выгружено из мусора")
            df_report['legalEntity'] = legal_entity
            df_report_full = pd.concat([df_report_full, df_report])
        else:
            print('Мусора нет')
    
df_report_full = df_report_full[['nmID','legalEntity','vendorCode']].sort_values(by='nmID') 
print(df_report_full.dtypes)

print(df_report_full)
key = '1Kt-EfIrLIOKcttybdpYgAK3Z20daRIaIJCs3vI30QTM'
rec_wsh = gc.open_by_key(key).get_worksheet(0)
df_gdata = pd.DataFrame(rec_wsh.get_all_records())
print(df_gdata)
df_gdata = df_gdata[df_gdata['Код товара'] != ''].iloc[:,0:4]
print(df_gdata.dtypes)
df_replacement = pd.merge(df_report_full, df_gdata, indicator=True,
                    left_on=['nmID'],
                    right_on=['Код товара'], how='outer').query('_merge=="left_only"').drop('_merge', axis=1).iloc[:,0:4]


row_num = len(df_gdata) + 2
df_replacement = df_replacement[['nmID', 'legalEntity', 'vendorCode']]  # Порядок нужных столбцов
df_replacement = df_replacement.fillna('')

for index, row in df_replacement.iterrows():
    # Записываем значения в соответствующие столбцы (начиная с текущей строки row_num)
    rec_wsh.update_cell(row_num, 2, str(row['nmID']))  # Столбец 'nmID' записывается во 2-й столбец
    rec_wsh.update_cell(row_num, 3, str(row['legalEntity']))  # Столбец 'legalEntity' — в 3-й
    rec_wsh.update_cell(row_num, 4, str(row['vendorCode']))  # Столбец 'vendorCode' — в 4-й
    row_num += 1  # Переходим к следующей строке
    print(str(datetime.datetime.now()))  # Печатаем текущее время
    time.sleep(5)  # Пауза в 5 секунд, чтобы избежать превышения лимитов API