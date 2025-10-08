#!/usr/bin/env python3
import os
from datetime import datetime
import gspread
import pandas as pd
from gspread_dataframe import get_as_dataframe
from sqlalchemy import create_engine
import psycopg2

GOOGLE_SHEET_ID = "1SAU8CxTbhWP-eY5DRmazfGQ7TbQCMr9RiAhAEo_jLD4"
SECOND_SHEET_ID = "1Kt-EfIrLIOKcttybdpYgAK3Z20daRIaIJCs3vI30QTM"

# PostgreSQL конфигурация
PG_HOST = '94.103.84.245'
PG_PORT = 5432
PG_USER = 'bahram'
PG_PASSWORD = 'Dadajonim99'
PG_DB = 'wb_baah'
PG_SCHEMA = 'products'
PG_TABLE = 'sebestoimost'

# Создание подключения к БД
engine = create_engine(f'postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}')

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    return df.rename(columns={c: str(c).strip() for c in df.columns})

def _normalize_key(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace("\u00A0", " ", regex=False)
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
        .str.upper()
    )

def read_sheet_df(sheet_id: str, worksheet_title: str = None) -> pd.DataFrame:
    gc = gspread.service_account(filename="/home/baakhofficial/wbauto/bahram/cred.json")
    spreadsheet = gc.open_by_key(sheet_id)
    ws = spreadsheet.worksheet(worksheet_title) if worksheet_title else spreadsheet.worksheets()[0]
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0)
    if df is not None:
        df = df.dropna(how="all").dropna(axis=1, how="all")
    else:
        df = pd.DataFrame()
    return _normalize_columns(df)

def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = os.path.dirname(__file__)

    # 1) Получить данные → DF
    base_df = read_sheet_df(GOOGLE_SHEET_ID)
    tovary_df = read_sheet_df(SECOND_SHEET_ID, "Товары")

    # 2) В «Товары»: удалить дубли по паре «Юрлицо» + «Код товара»
    if "Юрлицо" in tovary_df.columns and "Код товара" in tovary_df.columns:
        tovary_df = tovary_df.drop_duplicates(subset=["Юрлицо", "Код товара"], keep="first")

    # 3) LEFT MERGE по двум полям:
    # слева:  «Юрлицо», «Артикул»
    # справа: «Юрлицо», «Название в закупе»
    if (
        "Юрлицо" in base_df.columns
        and "Артикул" in base_df.columns
        and "Юрлицо" in tovary_df.columns
        and "Название в закупе" in tovary_df.columns
    ):
        left = base_df.copy()
        right = tovary_df.copy()
        # нормализуем оба компонента составного ключа
        left["__lk1"] = _normalize_key(left["Юрлицо"])
        left["__lk2"] = _normalize_key(left["Артикул"])
        right["__rk1"] = _normalize_key(right["Юрлицо"])
        right["__rk2"] = _normalize_key(right["Название в закупе"])
        merged = left.merge(
            right,
            left_on=["__lk1", "__lk2"],
            right_on=["__rk1", "__rk2"],
            how="left",
            suffixes=("", "_tovary"),
        ).drop(columns=["__lk1", "__lk2", "__rk1", "__rk2"], errors="ignore")
    else:
        merged = base_df

    # 3.1) Переименование столбцов на английские названия
    rename_columns_map = {
        # базовые поля
        "ИП": "ip",
        "Юрлицо": "legal_entity",
        "Артикул": "article",
        "Название в закупе": "purchase_article",
        "Код товара": "nm_id",
        "Название": "name",
        "Категория": "category",
        "Ссылка": "wb_link",
        "Наш не наш": "is_ours",
        # поля из правой таблицы с возможными суффиксами
        "Юрлицо_tovary": "legal_entity_tovary",
        "Название в закупе_tovary": "purchase_article_tovary",
        "Код товара_tovary": "nm_id_tovary",
        "Название_tovary": "name_tovary",
        "Категория_tovary": "category_tovary",
        "Ссылка_tovary": "wb_link_tovary",
        "Наш не наш_tovary": "is_ours_tovary",
    }
    merged = merged.rename(columns=rename_columns_map)

    # 4) Добавить метаданные и отправить в PostgreSQL
    merged['update_time'] = datetime.now()
    merged['source'] = 'google_sheets_merge'
    
    try:
        # Отправка в PostgreSQL схему products
        merged.to_sql(
            PG_TABLE, 
            engine, 
            schema=PG_SCHEMA, 
            if_exists='replace', 
            index=False,
            method='multi'
        )
        print(f"✅ Данные успешно отправлены в PostgreSQL: {PG_SCHEMA}.{PG_TABLE}")
        print(f"📊 Количество записей: {len(merged)}")
        
        # Очистка старых записей (оставляем только последнюю загрузку)
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text(f"""
                DELETE FROM {PG_SCHEMA}.{PG_TABLE} 
                WHERE update_time < (
                    SELECT MAX(update_time) 
                    FROM {PG_SCHEMA}.{PG_TABLE}
                )
            """))
            conn.commit()
        print("🧹 Старые записи очищены")
        
    except Exception as e:
        print(f"❌ Ошибка при отправке в PostgreSQL: {e}")
        raise e

if __name__ == "__main__":
    main()
