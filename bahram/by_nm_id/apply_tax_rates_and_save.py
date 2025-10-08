#!/usr/bin/env python3

import os
import pandas as pd
from sqlalchemy import create_engine, text
import gspread


# DB connection (reuse pattern from existing scripts)
ENGINE = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

# Google Sheets
SHEET_KEY = "15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ"


def get_gs_client():
    """Authorize gspread using service account located at bahram/cred.json."""
    # cred.json расположен в каталоге bahram; текущий файл лежит в bahram/by_nm_id
    cred_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cred.json')
    return gspread.service_account(filename=cred_path)


def load_rates_dataframe():
    """Load VAT and tax rates per supplier (ИП) from Google Sheet.

    Expected columns: 'ИП', 'НДС', 'Налоговая ставка'. Empty/NULL VAT -> 0.
    Percent values like 20 or '20%' are converted to fractions (0.2).
    """
    gc = get_gs_client()
    worksheet = gc.open_by_key(SHEET_KEY).sheet1
    df = pd.DataFrame(worksheet.get_all_records())

    # Normalize column names expected in RU
    required_cols = ['Имя Юрлица', 'НДС', 'Налоговая ставка']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"В Google Sheet отсутствует столбец: {col}")

    df = df[['Имя Юрлица', 'НДС', 'Налоговая ставка']].copy()

    # Clean and convert to numeric
    def to_fraction(val, default_zero=False):
        if val is None or (isinstance(val, str) and val.strip() == ''):
            return 0.0 if default_zero else None
        if isinstance(val, str):
            v = val.replace('%', '').replace(',', '.').strip()
        else:
            v = val
        try:
            num = float(v)
        except Exception:
            return 0.0 if default_zero else None
        # Convert percentage to fraction if looks like percent (e.g., 20 or 20.0)
        if num > 1.0:
            num = num / 100.0
        return num

    df['НДС'] = df['НДС'].apply(lambda x: to_fraction(x, default_zero=True))  # NULL -> 0
    df['Налоговая ставка'] = df['Налоговая ставка'].apply(lambda x: to_fraction(x, default_zero=False))

    # Fill missing tax rate with 0 if not provided
    df['Налоговая ставка'] = df['Налоговая ставка'].fillna(0.0)

    # Drop rows without supplier name
    df = df[df['Имя Юрлица'].astype(str).str.strip() != '']
    return df

