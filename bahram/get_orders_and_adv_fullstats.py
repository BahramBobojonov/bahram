#!/usr/bin/env python3

import requests
import gspread
from datetime import datetime, timedelta
import time
import json
import pandas as pd
from sqlalchemy import create_engine


print(datetime.now())
credentials_file = '/home/baakhofficial/wbauto/bahram/cred.json'
#credentials_file = 'cred.json'
spreadsheet_key = "15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ"
sheet_name = "Инвесторы"  # Укажите имя листа
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')





today = datetime.now()
#today = today - timedelta(hours=2)############
#today#####################
start_of_last_30_days = today - timedelta(days=7)
start_of_last_30_days = start_of_last_30_days.strftime('%Y-%m-%d')
end_of_last_30_days = today.strftime('%Y-%m-%d')
request_date =today.strftime('%Y-%m-%d')

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

def get_nomenclature_list(url, headers, supplier):
    import pandas as pd
    import requests

    df_all_nms = pd.DataFrame()  # Итоговый DataFrame
    cursor = {
        "limit": 100  # Начальный лимит
    }
    try:
        while True:
            # Формируем тело запроса
            data = {
                "settings": {
                    "cursor": cursor,
                    "filter": {
                        "withPhoto": -1
                    }
                }
            }

            # Выполняем запрос
            response = requests.post(url, headers=headers, json=data)

            # Проверяем успешность запроса
            if response.status_code != 200:
                print(f"Ошибка {response.status_code}: {response.text}")
                break

            # Извлекаем данные из ответа
            response_data = response.json()
            if "cards" not in response_data:
                print("Некорректный формат ответа от API")
                break

            # Создаем DataFrame из полученных данных
            df = pd.DataFrame(response_data["cards"], dtype=object)
            if not df.empty:
                df['supplier'] = supplier  # Добавляем колонку поставщика
                df_all_nms = pd.concat([df_all_nms, df], ignore_index=True)

            # Проверяем, достигнут ли конец данных
            if len(response_data["cards"]) < cursor["limit"]:
                break

            # Обновляем курсор
            last_item = response_data["cards"][-1]
            cursor["updatedAt"] = last_item["updatedAt"]
            cursor["nmID"] = last_item["nmID"]
    except requests.exceptions.RequestException as e:
        # Обработка сетевых ошибок
        print(f"Ошибка при выполнении запроса: {e}")
    except ValueError as e:
        # Обработка ошибок парсинга JSON
        print(f"Ошибка обработки данных: {e}")
    except Exception as e:
        # Обработка других непредвиденных ошибок
        print(f"Непредвиденная ошибка: {e}")


    return df_all_nms if not df_all_nms.empty else None

def fetch_wildberries_data(api_key,start_of_last_30_days,end_of_last_30_days):
    """
    Функция для получения данных по одному API-ключу.
    :param api_key: API ключ для авторизации
    :param ip_name: Название юридического лица (используется для метки в данных)
    :return: DataFrame с данными
    """

    # URL и заголовки
    url = "https://advert-api.wildberries.ru/adv/v1/upd"
    headers = {'Authorization': api_key}
    params = {'from': start_of_last_30_days, 'to': end_of_last_30_days}

    # Отправка запроса
    response = requests.get(url, headers=headers, params=params)

    # Проверка статуса ответа
    if response.status_code == 200:
        try:
            data = response.json()
            if isinstance(data, list):  # Проверка, что данные в формате списка
                df = pd.DataFrame(data, dtype=object)
                return df
            else:
                print(f"Неожиданный формат данных: {data}")
        except ValueError as e:
            print(f"Ошибка при обработке JSON: {e}")
    elif response.status_code == 401:
        print(f"Ошибка 401: Неверный API-ключ или недостаточно прав доступа.")
    else:
        print(f"Ошибка {response.status_code} при загрузке данных за период с {params['from']} по {params['to']}")

    # Возвращаем None в случае ошибки
    time.sleep(1)  # Задержка между запросами для предотвращения перегрузки сервера
    return None

df_investors = get_sheet_data_as_dataframe(credentials_file, spreadsheet_key, sheet_name)
df_investors = df_investors[(df_investors['API ключ'] != '')&(df_investors['API ключ'] != None)&~((df_investors['Имя Юрлица'] == 'TD') | (df_investors['Имя Юрлица'] == 'ИП Крапивина С.А.'))]
print(df_investors)
#df_investors = df_investors.head(2)#######################

individual_entrepreneurs = [
    #"ИП Шестаков В.Ю.",
    "ИП Мелешков А.Г.",
    "ИП Баах И.Л.",
    #"ИП Стрижакова Я.В.",
    #"ИП Куксенко",
    "ИП Баах Р.Н.",
    "ИП Радченко",
    "ИП Барышева Анастасия Михайловна",
    "ИП Астахова А.А.",
    #"ИП Крапивина С.А.",
    "ИП Мелешков С.Г.",
    "ИП Дедерер М.А.",
    "ИП Мелешкова О.В.",
    "ИП Сергеев М.Э.",
    "ИП Солоджук Е.Г.",
    "ИП Кобрина"
]





df_investors = df_investors[df_investors['Имя Юрлица'].isin(individual_entrepreneurs)]

print(df_investors)



df_all = pd.DataFrame()
for index, row in df_investors.iterrows():
    url = 'https://content-api.wildberries.ru/content/v2/get/cards/list'
    api_key = row['API ключ']  # API-ключ поставщика
    supplier = row['Имя Юрлица']  # Имя юрлица поставщика

    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }

    # Запуск функции для текущего поставщика
    try:
        df_supplier = get_nomenclature_list(url, headers=headers, supplier=supplier)
        if df_supplier.empty:
            print(f"Пустой DataFrame для поставщика {supplier}. Пропуск.")
        else:
            df_all = pd.concat([df_all, df_supplier], ignore_index=True)
    except Exception as e:
        print(f"Ошибка при обработке поставщика {supplier}: {e}")

df_all = df_all.drop_duplicates(subset='nmID')
print(f"Собрано {len(df_all)} номенклатур.")
columns = [
    "nmID",
    "subjectName",
    "vendorCode",
    "brand",
    "title",
    "createdAt",
    "updatedAt",
    "supplier",
    "tags"
]
df_all = df_all[columns]
df_all['tags'] = df_all['tags'].astype('str')
#df_all.columns = df_all.columns.str.lower()
df_all.rename(columns = {'nmID':'nm_id'})
df_all['update_date'] = datetime.now()
df_all.to_sql('products_card', engine, schema='products',if_exists='replace', index=False)

print(df_all.columns)
df_investors = df_investors.merge(df_all[['nmID','vendorCode','title','subjectName','supplier']], left_on = 'Имя Юрлица', right_on ='supplier', how ='left')


URL = "https://seller-analytics-api.wildberries.ru/api/v2/nm-report/detail/history"
final_df = pd.DataFrame()
def get_data(api_key, nm_ids, begin_date, end_date):
    payload = {
        "nmIDs": nm_ids,  # Укажите артикулы WB, максимум 20
        "period": {
            "begin": begin_date,  # Дата начала периода (формат ГГГГ-ММ-ДД)
            "end": end_date  # Дата конца периода (формат ГГГГ-ММ-ДД)
        },
        "timezone": "Europe/Moscow",  # Временная зона (опционально)
        "aggregationLevel": "day"  # Уровень агрегации (day или week, опционально)
    }
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        return response.json().get("data", [])  # Возвращаем только поле "data"
    except requests.exceptions.RequestException as e:
        print(f"Ошибка для API ключа {api_key} и nmIDs {nm_ids}: {e}")
        return []


today = datetime.now()
#today = today - timedelta(hours=2)############
#today#################

begin_date = today - timedelta(days=7)#####################
end_date = today

begin_date = begin_date.strftime('%Y-%m-%d')
end_date = end_date.strftime('%Y-%m-%d')

result_df = pd.DataFrame()

for api_key in df_investors["API ключ"].unique():
    # Фильтруем nmID для текущего API_KEY
    nm_ids = df_investors[df_investors["API ключ"] == api_key]["nmID"].tolist()

    # Разбиваем nm_ids на группы по 20
    for i in range(0, len(nm_ids), 20):
        chunk = nm_ids[i:i + 20]
        print(f"Запрос для API ключа {api_key} и nmIDs {chunk}")

        # Получаем данные
        data = get_data(api_key, chunk, begin_date, end_date)
        if data:
            all_list = pd.DataFrame()
            for i in data:
                all_ip_data = pd.DataFrame()
                for day in i['history']:
                    day['nm'] = i['nmID']
                    day['imtName'] = i['imtName']
                    day['vendorCode'] = i['vendorCode']
                    supplier = \
                    df_investors[(df_investors["API ключ"] == api_key) & (df_investors["nmID"] == i['nmID'])][
                        "supplier"].values[0]  # Извлекаем значение supplier
                    title = df_investors[(df_investors["API ключ"] == api_key) & (df_investors["nmID"] == i['nmID'])][
                        "title"].values[0]
                    subjectName = \
                    df_investors[(df_investors["API ключ"] == api_key) & (df_investors["nmID"] == i['nmID'])][
                        "subjectName"].values[0]
                    day['supplier'] = supplier
                    day['subjectName'] = title
                    df = pd.DataFrame([day])
                    all_ip_data = pd.concat([df, all_ip_data], ignore_index=True)
                all_list = pd.concat([all_list, all_ip_data], ignore_index=True)
            result_df = pd.concat([result_df, all_list], ignore_index=True)
        time.sleep(15)

result_df.columns = result_df.columns.str.lower()
result_df.rename(columns ={
    "nm":'nm_id',
    "dt":"order_date",
    "vendorCode":'supplier_article',
    "imtName":'article',
}, inplace=True)
#result_df.to_excel('all_orders_data.xlsx', index = False)
print(result_df.dtypes)
result_df['order_date'] =pd.to_datetime(result_df['order_date'])
from sqlalchemy import create_engine, MetaData, insert
from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.dialects.postgresql import insert

# Подключение к базе данных
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')
connect = engine.connect()

# Отражение метаданных таблиц
meta = MetaData(schema='analytics')
meta.reflect(bind=engine)
print(meta.tables.keys())

# Получение таблицы
table = meta.tables['analytics.detail_orders']

# Формирование списка данных для вставки
insrt_vals = result_df.to_dict(orient='records')

# Размер чанка (например, 1000 строк)
chunk_size = 1000

# Подготовка INSERT-запроса
insrt_stmnt = insert(table)

# Добавление "ON CONFLICT DO UPDATE" для PostgreSQL
do_update_stmt = insrt_stmnt.on_conflict_do_update(
    index_elements=["order_date", "nm_id", "supplier"],  # Уникальный индекс (конфликт по полям индекса)
    set_={  # Указываем, какие поля будут обновляться
        "opencardcount": insrt_stmnt.excluded.opencardcount,
        "addtocartcount": insrt_stmnt.excluded.addtocartcount,
        "addtocartconversion": insrt_stmnt.excluded.addtocartconversion,
        "orderscount": insrt_stmnt.excluded.orderscount,
        "orderssumrub": insrt_stmnt.excluded.orderssumrub,
        "carttoorderconversion": insrt_stmnt.excluded.carttoorderconversion,
        "buyoutscount": insrt_stmnt.excluded.buyoutscount,
        "buyoutssumrub": insrt_stmnt.excluded.buyoutssumrub,
        "buyoutpercent": insrt_stmnt.excluded.buyoutpercent,
        "imtname": insrt_stmnt.excluded.imtname,
        "vendorcode": insrt_stmnt.excluded.vendorcode,
        "subjectname": insrt_stmnt.excluded.subjectname
    }
)

# Вставка данных чанками
with engine.begin() as connection:
    for i in range(0, len(insrt_vals), chunk_size):
        chunk = insrt_vals[i:i + chunk_size]
        chunk_stmt = do_update_stmt.values(chunk)  # Вставляем текущий чанк
        connection.execute(chunk_stmt)


df_investors = df_investors.drop_duplicates(subset =['API ключ','Имя Юрлица'])

all_advert_data = pd.DataFrame()
all_camp_data = []

# URL для API-запросов
url = "https://advert-api.wildberries.ru/adv/v2/fullstats"

# Основной цикл по каждому продавцу
for ipx, row in df_investors.iterrows():
    api_key = row['API ключ']
    supplier_name = row['Имя Юрлица']
    print(f"Получение данных для поставщика: {supplier_name}")

    # Получаем данные с помощью первой функции (функция fetch_wildberries_data предполагается заранее определённой)
    df = fetch_wildberries_data(api_key, start_of_last_30_days=start_of_last_30_days, end_of_last_30_days=end_of_last_30_days)
    if df.empty:
        print("Получен пустой DataFrame. Выход из цикла.")
        break

    df['supplier'] = supplier_name  # Добавляем поле с названием поставщика
    all_advert_data = pd.concat([all_advert_data, df], ignore_index=True)  # Объединяем данные
    print(df.columns)

    if 'advertId' not in df.columns or df['advertId'].isna().any():
        print(f"Пропуск данных для {supplier_name}: отсутствуют advertId или есть пустые значения")
        continue

    # Получаем уникальные ID кампаний и ключи для заголовка API
    campaign_ids = list(df['advertId'].unique())
    headers = {"Authorization": api_key}

    # Создаем параметры запросов для каждой кампании
    params = [{"id": c, "interval": {"begin": start_of_last_30_days, "end": end_of_last_30_days}} for c in campaign_ids]

    counter = 0  # Счетчик для отслеживания количества запросов
    # Цикл по каждой кампании текущего поставщика
    for param in params:
        try:
            # Запрос данных для кампании
            response = requests.post(url, json=[param], headers=headers)
            response.raise_for_status()
            data = response.json()

            # Проверка на пустой ответ
            if not data:
                print(f"Пустой ответ для ID {param['id']} поставщика {supplier_name}")
                continue

            # Обработка и сохранение данных в общий список all_camp_data
            for c in data:
                for d in c['days']:
                    for a in d['apps']:
                        for nm in a['nm']:
                            # Добавляем необходимые поля
                            nm['appType'] = a['appType']
                            nm['date'] = d['date']
                            nm['advertId'] = c['advertId']
                            nm['supplier'] = supplier_name  # Добавляем поле поставщика
                            all_camp_data.append(nm)

        except requests.exceptions.RequestException as e:
            print(f"Ошибка для ID {param['id']} поставщика {supplier_name}: {e}")

        # Увеличиваем счетчик запросов
        counter += 1
        #if counter == 1:##########################
            #break#####################################
        print(f"Запросов выполнено: {counter}")

        # Задержка между запросами
        time.sleep(60)

# Создаем DataFrame из собранных данных всех кампаний
df_all_success = pd.DataFrame(all_camp_data)
df_all_success['date'] = df_all_success['date'].str.split('T').str[0]

df_all_success['date'] = df_all_success['date'].fillna(' ')
df_all_success['name'] = df_all_success['name'].fillna(' ')
df_all_success['supplier'] = df_all_success['supplier'].fillna(' ')
df_all_success = df_all_success.fillna(0)

data_types = {
    'views': 'int64',
    'clicks': 'int64',
    'ctr': 'float',
    'cpc': 'float',
    'sum': 'int64',
    'atbs': 'int64',
    'orders': 'int64',
    'cr': 'float',
    'shks': 'int64',
    'sum_price': 'int64',
    'name': 'object',
    'nmId': 'int64',
    'appType': 'int64',
    'date': 'object',
    'advertId': 'int64',
    'supplier': 'object'
}

df_all_success = df_all_success.astype(data_types)
df_all_success['cr'] = df_all_success['cr'].astype('float')
df_all_success.columns = df_all_success.columns.str.lower()
df_all_success.rename(columns ={
    'nmid':'nm_id',
    'date':'adv_date',
},inplace=True)
df_all_success['adv_date'] =pd.to_datetime(df_all_success['adv_date'])
#df_all_success.to_excel('all_data.xlsx')
print(datetime.now())

meta = MetaData(schema='analytics')
meta.reflect(bind=engine)
print(meta.tables.keys())

# Получение таблицы
table = meta.tables['analytics.adv_fullstats']

# Формирование списка данных для вставки
insrt_vals = df_all_success.to_dict(orient='records')

# Размер чанка (например, 1000 строк)
chunk_size = 1000

# Подготовка INSERT-запроса
insrt_stmnt = insert(table)

# Добавление "ON CONFLICT DO UPDATE" для PostgreSQL
do_update_stmt = insrt_stmnt.on_conflict_do_update(
    index_elements=["supplier", "advertid", "adv_date", "nm_id", "apptype"],  # Уникальный индекс (конфликт по полям индекса)
    set_={  # Указываем, какие поля будут обновляться
        "views": insrt_stmnt.excluded.views,
        "clicks": insrt_stmnt.excluded.clicks,
        "ctr": insrt_stmnt.excluded.ctr,
        "cpc": insrt_stmnt.excluded.cpc,
        "sum": insrt_stmnt.excluded.sum,
        "atbs": insrt_stmnt.excluded.atbs,
        "orders": insrt_stmnt.excluded.orders,
        "cr": insrt_stmnt.excluded.cr,
        "shks": insrt_stmnt.excluded.shks,
        "sum_price": insrt_stmnt.excluded.sum_price,
        "name": insrt_stmnt.excluded.name,
    }
)

# Вставка данных чанками
with engine.begin() as connection:
    for i in range(0, len(insrt_vals), chunk_size):
        chunk = insrt_vals[i:i + chunk_size]
        chunk_stmt = do_update_stmt.values(chunk)  # Вставляем текущий чанк
        connection.execute(chunk_stmt)  # Выполнение запроса