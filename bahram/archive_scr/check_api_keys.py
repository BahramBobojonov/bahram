#!/usr/bin/env python3

import gspread
import pandas as pd
import os
import requests

# === Google Sheets setup ===
cred_path = os.path.join(os.path.dirname(__file__), 'cred.json')
gc = gspread.service_account(filename=cred_path)
worksheet = gc.open_by_key("15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ").sheet1
df_keys = pd.DataFrame(worksheet.get_all_records())
df_keys = df_keys[df_keys['API ключ'].notnull() & (df_keys['API ключ'] != '')]

print("Доступные API ключи:")
for i, (api_key, company) in enumerate(zip(df_keys['API ключ'], df_keys['Имя Юрлица'])):
    print(f"{i+1}. {company}: {api_key[:20]}...")

print(f"\nВсего ключей: {len(df_keys)}")

# Тестируем каждый ключ
print("\nТестирование API ключей...")
for i, (api_key, company) in enumerate(zip(df_keys['API ключ'], df_keys['Имя Юрлица'])):
    print(f"\n{i+1}. Тестируем {company}...")
    
    url = "https://returns-api.wildberries.ru/api/v1/claims"
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }
    params = {
        "is_archive": "false",
        "limit": 1,
        "offset": 0
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Успешно! Заявок: {data.get('total', 0)}")
        else:
            print(f"   ✗ Ошибка {response.status_code}: {response.text[:100]}...")
    except Exception as e:
        print(f"   ✗ Исключение: {e}")
