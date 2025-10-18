#!/usr/bin/env python3

import requests
import pandas as pd
from sqlalchemy import create_engine, MetaData
from sqlalchemy.dialects.postgresql import insert
import datetime
import time
import gspread
import json

# Настройка подключения
credentials_file = '/home/baakhofficial/wbauto/bahram/cred.json'
spreadsheet_key = "15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ"
sheet_name = "Инвесторы"
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

print(f"Начало выполнения скрипта: {datetime.datetime.now()}")


def get_sheet_data_as_dataframe(credentials_file, spreadsheet_key, sheet_name):
    """
    Получает данные из указанного листа Google Sheets и возвращает их в формате DataFrame.
    """
    gc = gspread.service_account(filename=credentials_file)
    worksheet = gc.open_by_key(spreadsheet_key).worksheet(sheet_name)
    data = worksheet.get_all_records(expected_headers=None)
    df = pd.DataFrame(data, dtype=object)
    return df


def get_cards_from_api(api_key, supplier_name):
    """
    Получает список карточек товаров через API Wildberries.
    """
    headers = {'Authorization': api_key}
    
    # Первый запрос для получения карточек
    response = requests.post(
        'https://content-api.wildberries.ru/content/v2/get/cards/list',
        headers=headers,
        json={
            "settings": {
                "cursor": {'limit': 100},
                'filter': {'withPhoto': -1},
                'sort': {"ascending": False}
            }
        }
    )
    
    if response.status_code != 200:
        print(f"Ошибка запроса для {supplier_name}: {response.status_code}")
        return None
    
    jdata = json.loads(response.text)
    
    if jdata['cursor']['total'] == 0:
        print(f"Карточек нет для {supplier_name}")
        return None
    
    all_cards = jdata['cards']
    print(f"Первый запрос для {supplier_name}: получено {len(all_cards)} карточек")
    
    # Пагинация - получаем все карточки
    while jdata['cursor']['total'] != 0:
        response = requests.post(
            'https://content-api.wildberries.ru/content/v2/get/cards/list',
            headers=headers,
            json={
                "settings": {
                    "cursor": {
                        'limit': 100,
                        'updatedAt': jdata['cursor']['updatedAt'],
                        'nmID': jdata['cursor']['nmID']
                    },
                    'filter': {'withPhoto': -1},
                    'sort': {"ascending": False}
                }
            }
        )
        
        if response.status_code != 200:
            print(f"Ошибка запроса пагинации для {supplier_name}: {response.status_code}")
            break
        
        jdata = json.loads(response.text)
        
        if jdata['cursor']['total'] == 0:
            break
        
        all_cards.extend(jdata['cards'])
        print(f"Получено еще {len(jdata['cards'])} карточек для {supplier_name}")
        time.sleep(0.5)  # Задержка между запросами
    
    print(f"Всего выгружено {len(all_cards)} карточек для {supplier_name}")
    return all_cards


def flatten_card_data(cards, supplier_name):
    """
    Преобразует вложенную структуру карточек в плоский DataFrame.
    """
    flattened_data = []
    
    for card in cards:
        # Базовая информация карточки
        base_info = {
            'supplier_name': supplier_name,
            'nm_id': card.get('nmID'),
            'imtid': card.get('imtID'),
            'nm_uuid': card.get('nmUUID'),
            'subject_id': card.get('subjectID'),
            'subject_name': card.get('subjectName'),
            'vendor_code': card.get('vendorCode'),
            'brand': card.get('brand'),
            'title': card.get('title'),
            'description': card.get('description'),
            'video': card.get('video'),
            'created_at': card.get('createdAt'),
            'updated_at': card.get('updatedAt'),
            'update_time': datetime.datetime.now()
        }
        
        # Обработка размеров (sizes)
        sizes = card.get('sizes', [])
        if sizes:
            for size in sizes:
                size_info = base_info.copy()
                size_info.update({
                    'chrt_id': size.get('chrtID'),
                    'tech_size': size.get('techSize'),
                    'sku_id': size.get('skus', [None])[0] if size.get('skus') else None,
                    'price': size.get('price'),
                    'discount_price': size.get('discountedPrice'),
                    'wbsize': size.get('wbSize')
                })
                flattened_data.append(size_info)
        else:
            # Если нет размеров, добавляем базовую информацию
            flattened_data.append(base_info)
    
    return pd.DataFrame(flattened_data)


def upload_to_database(engine, df, table_name='products_card', schema='products'):
    """
    Загружает данные в базу данных с удалением старых данных и вставкой новых.
    """
    if df.empty:
        print("DataFrame пустой, загрузка пропущена")
        return
    
    import psycopg2
    from psycopg2 import sql
    
    # Параметры подключения
    db_params = {
        'dbname': 'wb_baah',
        'user': 'bahram',
        'password': 'Dadajonim99',
        'host': '94.103.84.245',
        'port': '5432',
    }
    
    try:
        # Подключаемся к базе данных
        connection = psycopg2.connect(**db_params)
        cursor = connection.cursor()
        
        # Удаляем старую таблицу если существует
        cursor.execute(f"DROP TABLE IF EXISTS {schema}.{table_name} CASCADE")
        print(f"Старая таблица {schema}.{table_name} удалена (если существовала)")
        
        connection.commit()
        cursor.close()
        connection.close()
        
        # Создаём таблицу заново и загружаем данные
        df.to_sql(table_name, engine, schema=schema, if_exists='replace', index=False)
        
        # Создаем индексы для оптимизации
        connection = psycopg2.connect(**db_params)
        cursor = connection.cursor()
        
        # Индекс на nm_id для быстрого поиска
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_nm_id 
            ON {schema}.{table_name}(nm_id)
        """)
        
        # Индекс на supplier_name для фильтрации по поставщикам
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_supplier 
            ON {schema}.{table_name}(supplier_name)
        """)
        
        # Индекс на update_time для поиска последних обновлений
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_update_time 
            ON {schema}.{table_name}(update_time)
        """)
        
        connection.commit()
        cursor.close()
        connection.close()
        
        print(f"Данные успешно загружены в {schema}.{table_name}: {len(df)} записей")
        print(f"Индексы созданы успешно")
        
    except Exception as e:
        print(f"Ошибка при загрузке данных: {str(e)}")
        if connection:
            connection.rollback()
        raise


# Основная логика
def main():
    # Получаем API ключи из Google Sheets
    df = get_sheet_data_as_dataframe(credentials_file, spreadsheet_key, sheet_name)
    
    # Фильтруем только записи с API стандартным ключом
    df = df[(df['API стандартный'] != '') & (df['API стандартный'] != None)]
    
    if df.empty:
        print("Нет доступных API ключей")
        return
    
    print(f"Найдено {len(df)} поставщиков с API ключами")
    
    all_cards_df = pd.DataFrame()
    
    # Проходим по каждому поставщику
    for index, row in df.iterrows():
        api_key = row['API стандартный']
        supplier_name = row['Имя Юрлица']
        
        print(f"\n{'='*60}")
        print(f"Обработка поставщика: {supplier_name}")
        print(f"{'='*60}")
        
        try:
            # Получаем карточки товаров
            cards = get_cards_from_api(api_key, supplier_name)
            
            if cards is None or len(cards) == 0:
                print(f"Нет карточек для {supplier_name}")
                continue
            
            # Преобразуем в DataFrame
            df_cards = flatten_card_data(cards, supplier_name)
            
            if not df_cards.empty:
                all_cards_df = pd.concat([all_cards_df, df_cards], ignore_index=True)
                print(f"Добавлено {len(df_cards)} записей для {supplier_name}")
            
            # Задержка между поставщиками
            time.sleep(2)
            
        except Exception as e:
            print(f"Ошибка при обработке {supplier_name}: {str(e)}")
            continue
    
    # Загружаем все данные в базу
    if not all_cards_df.empty:
        print(f"\n{'='*60}")
        print(f"Загрузка данных в базу данных...")
        print(f"Всего записей: {len(all_cards_df)}")
        print(f"{'='*60}")
        
        upload_to_database(engine, all_cards_df)
        
        print(f"\nСкрипт завершен успешно: {datetime.datetime.now()}")
        print(f"Всего обработано карточек: {len(all_cards_df)}")
    else:
        print("\nНет данных для загрузки")


if __name__ == "__main__":
    main()

