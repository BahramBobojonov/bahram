#!/usr/bin/env python3

import requests
import pandas as pd
import gspread
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
import time
import numpy as np
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials


engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

query = """
 select * from supplies.vitrina
"""

with engine.begin() as connection:
    result = connection.execute(text(query))
    df_vitrina = pd.DataFrame(result.fetchall(), columns=result.keys())


query = """
 SELECT * FROM supplies.data_to_correct 
"""

with engine.begin() as connection:
    result = connection.execute(text(query))
    data_to_correct = pd.DataFrame(result.fetchall(), columns=result.keys())

df_merge = df_vitrina.merge(data_to_correct, left_on = ['supplier','article'], right_on = ['supplier','purchase_article'], how = 'left')

df_merge = df_merge[df_merge['purchase_article'].isna()][['supplier','article']]

df_merge = df_merge.drop_duplicates()


# Авторизация в Google Sheets
credentials_file = '/home/baakhofficial/wbauto/bahram/cred.json' 
#credentials_file = r"C:\Users\vivar\wb_baah\tasks\files_for_server\cred.json"
spreadsheet_key = "1CqiTBg2pp0JyVk1RCcvvSF_c2s22EmwTCO4yZeobILE"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(credentials_file, scopes=scope)
client = gspread.authorize(creds)

# Открываем таблицу и лист
spreadsheet = client.open_by_key(spreadsheet_key)
worksheet = spreadsheet.worksheet("Корректировка количества после инвентаризации")  # Выбираем нужный лист

# Загружаем текущие данные
existing_data = worksheet.get_all_values()
header = existing_data[0]  # Заголовки
existing_data = existing_data[1:]  # Данные без заголовков

# Преобразуем в DataFrame
df_existing = pd.DataFrame(existing_data, columns=header)

# Подготовка новых данных
df_new = df_merge[["supplier", "article"]].copy()
df_new.columns = ["ИП", "Название"]  # Подгоняем под названия столбцов в Google Sheets
df_new["adjustment_quantity"] = ""  # Заполняем пустыми значениями
df_new["comment"] = ""
df_new["comment_2"] = ""

# Добавляем новые строки в Google Sheets (без перезаписи)
worksheet.append_rows(df_new.values.tolist(), value_input_option="RAW")

print("Данные успешно добавлены!")