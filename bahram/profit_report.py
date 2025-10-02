#!/usr/bin/env python3

import gspread
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
# Параметры подключения к БД
db_url = 'postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah'
engine = create_engine(db_url)

# SQL-запрос
query = "SELECT * FROM reports.profit_report"

# Чтение данных из БД
try:
    with engine.connect() as connection:
        df = pd.read_sql_query(text(query), con=connection)
        print("Данные успешно получены из базы данных.")
except Exception as e:
    print(f"Ошибка при получении данных из БД: {e}")
    exit()

df['update_time'] = datetime.now()
df = df.astype('str')

try:
    # Указываем путь к JSON-файлу с учетными данными
    #credentials_path = "C:\\Users\\vivar\\PycharmProjects\\wb_baah\\cred.json"
    credentials_path = "/home/baakhofficial/wbauto/bahram/cred.json"


    # Аутентификация и открытие Google Sheets
    gc = gspread.service_account(filename=credentials_path)
    sheet = gc.open_by_key("107voGB48RRtNvZHELLMguzh7h7qvdP8kJDlDlkfeYhs")
    worksheet = sheet.worksheet("Лист1")

    print("Успешное подключение к Google Sheets.")

    # Очистка текущего содержимого листа перед записью новых данных
    worksheet.clear()

    # Формирование данных для записи
    data_to_update = [df.columns.tolist()] + df.values.tolist()

    # Обновляем все данные на листе в одном запросе
    worksheet.update("A1", data_to_update)

    print("Данные успешно загружены в Google Sheets.")
except Exception as e:
    print(f"Ошибка при работе с Google Sheets: {e}")
