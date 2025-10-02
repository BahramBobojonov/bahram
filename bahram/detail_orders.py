#!/usr/bin/env python3

import requests
import gspread
from datetime import datetime, timedelta
import time
import json
import pandas as pd
from sqlalchemy import create_engine, MetaData
from sqlalchemy.dialects.postgresql import insert

today = datetime.now()


begin_date = today - timedelta(days=7)#####################
end_date = today

begin_date = begin_date.strftime('%Y-%m-%d')
end_date = end_date.strftime('%Y-%m-%d')
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


def get_nomenclature_list(api_key, supplier):
    url = 'https://content-api.wildberries.ru/content/v2/get/cards/list'
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }

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


def chunk_list(lst, chunk_size):
    """
    Разделяет список на чанки указанного размера.
    """
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


def get_data(api_key, nm_ids, begin_date, end_date):
    url = 'https://seller-analytics-api.wildberries.ru/api/v2/nm-report/detail/history'
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }

    all_data = []

    # Разделяем список nm_ids на чанки по 20
    for chunk in chunk_list(nm_ids, 20):
        print(chunk)
        payload = {
            "nmIDs": chunk,  # Указываем текущий чанк
            "period": {
                "begin": begin_date,  # Дата начала периода
                "end": end_date  # Дата конца периода
            },
            "timezone": "Europe/Moscow",  # Временная зона
            "aggregationLevel": "day"  # Уровень агрегации
        }

        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            # Добавляем данные из ответа в общий список
            all_data.extend(response.json().get("data", []))
            time.sleep(10)
        except requests.exceptions.RequestException as e:
            print(f"Ошибка для API ключа {api_key} и nmIDs {chunk}: {e}")

    return all_data

def get_history_info(result_data, supplier_name):
    all_data_from_history = []  # Создаем список вне цикла
    for item in result_data:
        for history_entry in item['history']:
            # Добавляем поля из основного элемента
            history_entry['nmID'] = item['nmID']
            history_entry['imtName'] = item['imtName']
            history_entry['vendorCode'] = item['vendorCode']
            history_entry['supplier'] = supplier_name
            # Добавляем обработанную запись в общий список
            all_data_from_history.append(history_entry)
    return all_data_from_history


def prepared_data_for_bd(df):
    df.columns = df.columns.str.lower()
    df.rename(columns={
        "nmid": 'nm_id',
        "dt": "order_date",
        "vendorCode": 'supplier_article',
        "imtName": 'article',
    }, inplace=True)

    df['order_date'] = pd.to_datetime(df['order_date'])
    return df


def upload_data_to_db(engine, df):
    connect = engine.connect()
    # Отражение метаданных таблиц
    meta = MetaData(schema='analytics')
    meta.reflect(bind=engine)
    print(meta.tables.keys())

    # Получение таблицы
    table = meta.tables['analytics.detail_orders']

    # Формирование списка данных для вставки
    insrt_vals = df.to_dict(orient='records')

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

    return print("Data uploaded successfully")


print(datetime.now())
credentials_file = '/home/baakhofficial/wbauto/bahram/cred.json'
#credentials_file = 'cred.json'
spreadsheet_key = "15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ"
sheet_name = "Инвесторы"  # Укажите имя листа
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')


df_investors = get_sheet_data_as_dataframe(credentials_file, spreadsheet_key, sheet_name)
df_investors = df_investors[(df_investors['API ключ'] != '')&(df_investors['API ключ'] != None)&~((df_investors['Имя Юрлица'] == 'TD') | (df_investors['Имя Юрлица'] == 'ИП Крапивина С.А.'))]
print(df_investors)

df_all = pd.DataFrame()
all_result = []
for index, row in df_investors.iterrows():

    api_key = row['API ключ']  # API-ключ поставщика
    supplier = row['Имя Юрлица']  # Имя юрлица поставщика
    try:
        df_supplier = get_nomenclature_list(api_key=api_key, supplier=supplier)
        if df_supplier.empty:
            print(f"Пустой DataFrame для поставщика {supplier}. Пропуск.")
        else:
            nmids = df_supplier['nmID'].unique().tolist()
            result = get_data(api_key, nm_ids=nmids, begin_date=begin_date, end_date=end_date)
            print(len(result))
            if not result:
                print(f"Пустой результат get_data для {supplier}. Пропуск.")
                continue

            nm_data = get_history_info(result, supplier_name=supplier)
            if not nm_data:
                print(f"Пустая история для {supplier}. Пропуск.")
                continue
            #print(f"nm_data для {supplier}: {nm_data}")
            df = pd.DataFrame(nm_data)  # Убрали [0], так как nm_data - это список словарей
            if df.empty:
                print(f"Пустой DataFrame из nm_data для {supplier}. Пропуск.")
                continue
            df = prepared_data_for_bd(df)
            print(df.columns)
            upload_data_to_db(engine=engine, df=df)
        df_all = pd.concat([df_all, df_supplier], ignore_index=True)
    except Exception as e:
        print(f"Ошибка при обработке поставщика {supplier}: {e}")
