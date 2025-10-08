#!/usr/bin/env python3
"""
Скрипт для выполнения SQL запросов по финансовым отчетам с параметрами НДС и налогов
для каждого ИП из Google Sheet.

1. Загружает НДС и налоговые ставки для каждого ИП из Google Sheet
2. Выполняет v_finance_summary_by_nmid.sql для каждого supplier и сохраняет в reports.mv_detail_finance_reports_v1
3. Выполняет v_finance_summary_by_nmid_result.sql для каждого supplier и сохраняет в reports.detail_finance_reports_by_nm_id
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text
import gspread
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Параметры подключения
ENGINE = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')
SHEET_KEY = "15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ"

# Пути к SQL файлам
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_FILE_1 = os.path.join(SCRIPT_DIR, 'v_finance_summary_by_nmid.sql')
SQL_FILE_2 = os.path.join(SCRIPT_DIR, 'v_finance_summary_by_nmid_result.sql')


def get_gs_client():
    """Авторизация в Google Sheets"""
    cred_path = os.path.join(os.path.dirname(SCRIPT_DIR), 'cred.json')
    return gspread.service_account(filename=cred_path)


def load_rates_dataframe():
    """
    Загружает НДС и налоговые ставки для каждого ИП из Google Sheet.
    
    Ожидаемые колонки: 'Имя Юрлица', 'НДС', 'Налоговая ставка'
    Пустые значения НДС заменяются на 0.
    Процентные значения типа 20 или '20%' конвертируются в дроби (0.2).
    
    Returns:
        DataFrame с колонками: Имя Юрлица, НДС, Налоговая ставка
    """
    gc = get_gs_client()
    worksheet = gc.open_by_key(SHEET_KEY).sheet1
    df = pd.DataFrame(worksheet.get_all_records())
    
    # Проверяем наличие необходимых колонок
    required_cols = ['Имя Юрлица', 'НДС', 'Налоговая ставка']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"В Google Sheet отсутствует столбец: {col}")
    
    df = df[required_cols].copy()
    
    # Функция для конвертации процентов в дробные значения
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
        # Конвертируем процент в дробь, если число >= 1 (например, 1 -> 0.01, 6 -> 0.06, 20 -> 0.2)
        if num >= 1.0:
            num = num / 100.0
        return num
    
    df['НДС'] = df['НДС'].apply(lambda x: to_fraction(x, default_zero=True))
    df['Налоговая ставка'] = df['Налоговая ставка'].apply(lambda x: to_fraction(x, default_zero=False))
    df['Налоговая ставка'] = df['Налоговая ставка'].fillna(0.0)
    
    # Убираем строки без имени юрлица
    df = df[df['Имя Юрлица'].astype(str).str.strip() != '']
    
    logger.info(f"✅ Загружено {len(df)} записей с налоговыми ставками из Google Sheet")
    return df


def load_sql_file(file_path):
    """Загружает SQL запрос из файла"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            sql_query = f.read()
        logger.info(f"✅ SQL запрос загружен из файла: {file_path}")
        return sql_query
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке SQL файла {file_path}: {e}")
        raise


def execute_sql_with_params(sql_query, vat_rate, tax_rate, supplier_name):
    """
    Выполняет SQL запрос с подстановкой параметров НДС и налога
    
    Args:
        sql_query: SQL запрос с параметрами :vat_rate и :tax_rate
        vat_rate: Ставка НДС (в дробном виде, например 0.2 для 20%)
        tax_rate: Налоговая ставка (в дробном виде, например 0.06 для 6%)
        supplier_name: Имя поставщика для логирования
        
    Returns:
        DataFrame с результатами запроса
    """
    try:
        with ENGINE.connect() as conn:
            result = conn.execute(
                text(sql_query),
                {"vat_rate": vat_rate, "tax_rate": tax_rate}
            )
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
        
        logger.info(f"✅ Запрос выполнен для {supplier_name}: получено {len(df)} строк")
        return df
    except Exception as e:
        logger.error(f"❌ Ошибка при выполнении запроса для {supplier_name}: {e}")
        raise


def save_to_table(df, table_name, schema='reports', if_exists='append'):
    """
    Сохраняет DataFrame в таблицу PostgreSQL
    
    Args:
        df: DataFrame для сохранения
        table_name: Имя таблицы
        schema: Схема БД (по умолчанию 'reports')
        if_exists: Режим записи ('append', 'replace', 'fail')
    """
    try:
        df.to_sql(
            name=table_name,
            con=ENGINE,
            schema=schema,
            if_exists=if_exists,
            index=False,
            method='multi'
        )
        logger.info(f"✅ Данные сохранены в {schema}.{table_name}: {len(df)} строк")
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении в {schema}.{table_name}: {e}")
        raise


def main():
    """Основная функция"""
    logger.info("=" * 80)
    logger.info("НАЧАЛО ВЫПОЛНЕНИЯ СКРИПТА")
    logger.info("=" * 80)
    
    # Загружаем налоговые ставки из Google Sheet
    logger.info("\n📊 Загрузка налоговых ставок из Google Sheet...")
    df_rates = load_rates_dataframe()
    
    logger.info(f"\n📋 Список ИП и их ставки:")
    for idx, row in df_rates.iterrows():
        logger.info(f"  - {row['Имя Юрлица']}: НДС={row['НДС']*100:.1f}%, Налог={row['Налоговая ставка']*100:.1f}%")
    
    # Загружаем SQL запросы
    logger.info("\n📄 Загрузка SQL запросов...")
    sql_query_1 = load_sql_file(SQL_FILE_1)
    sql_query_2 = load_sql_file(SQL_FILE_2)
    
    # ШАГ 1: Выполнение первого запроса и сохранение в mv_detail_finance_reports_v1
    logger.info("\n" + "=" * 80)
    logger.info("ШАГ 1: Выполнение v_finance_summary_by_nmid.sql")
    logger.info("=" * 80)
    logger.info("\n⚠️ ВАЖНО: Запрос использует фиксированные параметры НДС и налога.")
    logger.info("⚠️ Для правильной работы нужно добавить колонки vat_rate и tax_rate в исходные данные.")
    
    # Добавляем фильтр WHERE к первому SQL запросу
    sql_with_filter_1 = sql_query_1.replace(
        "FROM reports.detail_finance_reports",
        f"FROM reports.detail_finance_reports WHERE supplier IN ({','.join([repr(s) for s in df_rates['Имя Юрлица'].tolist()])})"
    )
    
    all_results_1 = []
    for idx, row in df_rates.iterrows():
        supplier_name = row['Имя Юрлица']
        vat_rate = row['НДС']
        tax_rate = row['Налоговая ставка']
        
        logger.info(f"\n🔄 Обработка: {supplier_name} (НДС={vat_rate*100:.1f}%, Налог={tax_rate*100:.1f}%)")
        
        # Добавляем фильтр по supplier к запросу (после WHERE, до GROUP BY)
        sql_filtered = sql_query_1.replace(
            "WHERE date_from::date >= '2025-08-25'",
            f"WHERE date_from::date >= '2025-08-25' AND supplier = '{supplier_name}'"
        )
        
        try:
            df_result = execute_sql_with_params(sql_filtered, vat_rate, tax_rate, supplier_name)
            
            if len(df_result) > 0:
                all_results_1.append(df_result)
                logger.info(f"  ✓ Добавлено {len(df_result)} строк для {supplier_name}")
            else:
                logger.warning(f"  ⚠ Нет данных для {supplier_name}")
                
        except Exception as e:
            logger.error(f"  ✗ Ошибка для {supplier_name}: {e}")
            continue
    
    # Сохраняем результаты первого запроса
    if all_results_1:
        logger.info(f"\n💾 Сохранение результатов в reports.mv_detail_finance_reports_v1...")
        df_final_1 = pd.concat(all_results_1, ignore_index=True)
        
        # Конвертируем все числовые колонки в правильные типы
        numeric_columns = [col for col in df_final_1.columns if col not in ['supplier_name', 'supplier', 'realizationreport_id', 'date_from', 'date_to', 'rr_dt']]
        for col in numeric_columns:
            try:
                df_final_1[col] = pd.to_numeric(df_final_1[col], errors='coerce')
            except:
                pass
        
        # Очищаем таблицу перед записью
        save_to_table(df_final_1, 'mv_detail_finance_reports_v1', schema='reports', if_exists='replace')
        logger.info(f"✅ Всего сохранено {len(df_final_1)} строк")
    else:
        logger.warning("⚠ Нет данных для сохранения на шаге 1")
    
    # ШАГ 2: Выполнение второго запроса и сохранение в detail_finance_reports_by_nm_id
    logger.info("\n" + "=" * 80)
    logger.info("ШАГ 2: Выполнение v_finance_summary_by_nmid_result.sql")
    logger.info("=" * 80)
    
    all_results_2 = []
    for idx, row in df_rates.iterrows():
        supplier_name = row['Имя Юрлица']
        vat_rate = row['НДС']
        tax_rate = row['Налоговая ставка']
        
        logger.info(f"\n🔄 Обработка: {supplier_name} (НДС={vat_rate*100:.1f}%, Налог={tax_rate*100:.1f}%)")
        
        # Добавляем фильтр по supplier к запросу
        sql_filtered = sql_query_2 + f"\nWHERE COALESCE(a.supplier_name, b.supplier, c.supplier, d.supplier, f.supplier) = '{supplier_name}'"
        
        try:
            df_result = execute_sql_with_params(sql_filtered, vat_rate, tax_rate, supplier_name)
            
            if len(df_result) > 0:
                all_results_2.append(df_result)
                logger.info(f"  ✓ Добавлено {len(df_result)} строк для {supplier_name}")
            else:
                logger.warning(f"  ⚠ Нет данных для {supplier_name}")
                
        except Exception as e:
            logger.error(f"  ✗ Ошибка для {supplier_name}: {e}")
            continue
    
    # Сохраняем результаты второго запроса
    if all_results_2:
        logger.info(f"\n💾 Сохранение результатов в reports.detail_finance_reports_by_nm_id...")
        df_final_2 = pd.concat(all_results_2, ignore_index=True)
        
        # Конвертируем все числовые колонки в правильные типы
        numeric_columns = [col for col in df_final_2.columns if col not in ['supplier_name', 'supplier', 'realizationreport_id', 'date_from', 'date_to', 'rr_dt']]
        for col in numeric_columns:
            try:
                df_final_2[col] = pd.to_numeric(df_final_2[col], errors='coerce')
            except:
                pass
        
        # Очищаем таблицу перед записью
        save_to_table(df_final_2, 'detail_finance_reports_by_nm_id', schema='reports', if_exists='replace')
        logger.info(f"✅ Всего сохранено {len(df_final_2)} строк")
    else:
        logger.warning("⚠ Нет данных для сохранения на шаге 2")
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ СКРИПТ ЗАВЕРШЕН УСПЕШНО")
    logger.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise

