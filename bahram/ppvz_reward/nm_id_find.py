#!/usr/bin/env python3

import pandas as pd
from sqlalchemy import create_engine, text

# PostgreSQL конфигурация
PG_HOST = '94.103.84.245'
PG_PORT = 5432
PG_USER = 'bahram'
PG_PASSWORD = 'Dadajonim99'
PG_DB = 'wb_baah'

# Создание подключения к БД
engine = create_engine(f'postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}')

def get_ppvz_reward_data():
    """
    Получает данные из таблицы detail_finance_reports
    где ppvz_reward не равен 0 и nm_id = 0
    """
    
    query = """
    SELECT 
        nm_id,
        quantity,
        return_amount,
        ppvz_reward::numeric, 
        retail_amount,  
        realizationreport_id, 
        date_from, 
        date_to,
        doc_type_name,
        supplier_oper_name, 
        supplier, 
        srid,
        shk_id 
    FROM reports.detail_finance_reports
    WHERE ppvz_reward::NUMERIC != 0
    AND nm_id = 0
    """
    
    try:
        print("Подключение к базе данных...")
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
        
        print(f"✓ Успешно загружено записей: {len(df):,}")
        print(f"✓ Колонок: {len(df.columns)}")
        print(f"\nПервые 5 строк:")
        print(df.head())
        print(f"\nИнформация о данных:")
        print(df.info())
        
        return df
        
    except Exception as e:
        print(f"✗ Ошибка при загрузке данных: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_srid_nm_id_data():
    """
    Получает пары srid, nm_id из таблицы detail_finance_reports
    где nm_id != 0 и sa_name не пустое/не NULL
    """

    query = """
    SELECT 
        srid,
        nm_id
    FROM reports.detail_finance_reports
    WHERE nm_id != 0
      AND sa_name IS NOT NULL
      AND sa_name != ''
    """

    try:
        print("\nПодключение к базе данных для получения srid, nm_id...")
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn)

        print(f"✓ Успешно загружено записей (srid, nm_id): {len(df):,}")
        if len(df) > 0:
            print("\nПервые 5 строк (srid, nm_id):")
            print(df.head())
        return df

    except Exception as e:
        print(f"✗ Ошибка при загрузке srid, nm_id: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # Выполнение запроса
    df = get_ppvz_reward_data()
    
    if df is not None and len(df) > 0:
        # Сохранение в Excel для анализа
        output_file = 'ppvz_reward_nm_id_0.xlsx'
        df.to_excel(output_file, index=False)
        print(f"\n✓ Данные сохранены в файл: {output_file}")
    else:
        print("\n⚠ Данных не найдено или произошла ошибка")

    # Выполнение второго запроса (srid, nm_id)
    df_srid_nm = get_srid_nm_id_data()

    if df_srid_nm is not None and len(df_srid_nm) > 0:
        # Для больших данных используем CSV вместо Excel
        if len(df_srid_nm) > 1000000:
            output_file_2 = 'srid_nm_id.csv'
            df_srid_nm.to_csv(output_file_2, index=False)
            print(f"\n✓ Данные (srid, nm_id) сохранены в файл: {output_file_2} (CSV формат для больших данных)")
        else:
            output_file_2 = 'srid_nm_id.xlsx'
            df_srid_nm.to_excel(output_file_2, index=False)
            print(f"\n✓ Данные (srid, nm_id) сохранены в файл: {output_file_2}")
    else:
        print("\n⚠ Данных (srid, nm_id) не найдено или произошла ошибка")

