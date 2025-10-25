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
    #df = df[df['Имя Юрлица'] != 'ИП Астахова А.А.']
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


def save_to_table(df, table_name, schema='reports', if_exists='append', chunksize=1000):
    """
    Сохраняет DataFrame в таблицу PostgreSQL порциями
    
    Args:
        df: DataFrame для сохранения
        table_name: Имя таблицы
        schema: Схема БД (по умолчанию 'reports')
        if_exists: Режим записи ('append', 'replace', 'fail')
        chunksize: Размер порции для вставки
    """
    try:
        # Защита от превышения лимита параметров в PostgreSQL (65535)
        # При method='multi' количество биндов = chunksize * num_columns
        # Вычисляем безопасный размер порции динамически с запасом
        num_columns = len(df.columns)
        if num_columns <= 0:
            logger.info(f"⚠ Пропуск сохранения в {schema}.{table_name}: пустой DataFrame")
            return

        POSTGRES_PARAM_LIMIT = 65535
        SAFETY_MARGIN = 0.95  # небольшой запас, чтобы не упираться в лимит
        max_params = int(POSTGRES_PARAM_LIMIT * SAFETY_MARGIN)
        max_chunk_by_params = max(1, max_params // max(1, num_columns))

        effective_chunksize = min(chunksize, max_chunk_by_params)

        if effective_chunksize < chunksize:
            logger.info(
                f"🔧 chunksize уменьшен с {chunksize} до {effective_chunksize} (столбцов: {num_columns}, лимит биндов ~{max_params})"
            )

        # Приводим столбцы DataFrame к схеме целевой таблицы, чтобы избежать UndefinedColumn
        # Используем отдельное подключение для чтения схемы
        table_columns = []
        with ENGINE.connect() as conn:
            try:
                result = conn.execute(text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = :schema AND table_name = :table
                    ORDER BY ordinal_position
                    """
                ), {"schema": schema, "table": table_name})
                table_columns = [row[0] for row in result.fetchall()]
                conn.commit()  # Явно коммитим, чтобы закрыть транзакцию
            except Exception as e:
                conn.rollback()  # Откатываем при ошибке
                raise

        # Если режим append и таблица существует - выравниваем столбцы
        if if_exists == 'append' and table_columns:
            # Оставляем только существующие в БД столбцы
            df_aligned = df.copy()
            df_aligned = df_aligned[[col for col in df_aligned.columns if col in table_columns]]

            # Добавляем недостающие столбцы как NULL
            for col in table_columns:
                if col not in df_aligned.columns:
                    df_aligned[col] = None

            # Упорядочиваем столбцы по порядку в таблице
            df_aligned = df_aligned[table_columns]
        else:
            # Для replace или если таблицы нет - используем DataFrame как есть
            df_aligned = df.copy()

        # Используем отдельное подключение для записи
        with ENGINE.connect() as conn:
            try:
                df_aligned.to_sql(
                    name=table_name,
                    con=conn,
                    schema=schema,
                    if_exists=if_exists,
                    index=False,
                    method='multi',
                    chunksize=effective_chunksize
                )
                conn.commit()  # Явно коммитим
                logger.info(f"✅ Данные сохранены в {schema}.{table_name}: {len(df_aligned)} строк")
            except Exception as e:
                conn.rollback()  # Откатываем при ошибке
                raise
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
    all_results_1 = []
    for idx, row in df_rates.iterrows():
        supplier_name = row['Имя Юрлица']
        vat_rate = row['НДС']
        tax_rate = row['Налоговая ставка']
        
        logger.info(f"\n🔄 Обработка: {supplier_name} (НДС={vat_rate*100:.1f}%, Налог={tax_rate*100:.1f}%)")
        
        # Добавляем фильтр по supplier к запросу (после WHERE, до GROUP BY)
        sql_filtered = sql_query_1.replace(
            "FROM reports.detail_finance_reports\nWHERE",
            f"FROM reports.detail_finance_reports\nWHERE supplier = '{supplier_name}' AND"
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
    
    # Очищаем таблицу один раз в начале
    logger.info("\n💾 Очистка таблицы reports.detail_finance_reports_by_nm_id...")
    try:
        with ENGINE.connect() as conn:
            conn.execute(text("TRUNCATE TABLE reports.detail_finance_reports_by_nm_id"))
            conn.commit()
        logger.info("✅ Таблица очищена через TRUNCATE")
    except Exception as e:
        logger.warning(f"⚠ Ошибка при очистке таблицы: {e}")
    
    total_rows_saved = 0
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
                # Конвертируем все числовые колонки в правильные типы
                numeric_columns = [col for col in df_result.columns if col not in ['supplier_name', 'supplier', 'realizationreport_id', 'date_from', 'date_to', 'rr_dt']]
                for col in numeric_columns:
                    try:
                        df_result[col] = pd.to_numeric(df_result[col], errors='coerce')
                    except:
                        pass
                
                # Сохраняем данные сразу порциями
                save_to_table(df_result, 'detail_finance_reports_by_nm_id', schema='reports', if_exists='append', chunksize=500)
                total_rows_saved += len(df_result)
                logger.info(f"  ✓ Сохранено {len(df_result)} строк для {supplier_name}")
            else:
                logger.warning(f"  ⚠ Нет данных для {supplier_name}")
                
        except Exception as e:
            logger.error(f"  ✗ Ошибка для {supplier_name}: {e}")
            continue
    
    if total_rows_saved > 0:
        logger.info(f"\n✅ Всего сохранено {total_rows_saved} строк в detail_finance_reports_by_nm_id")
    else:
        logger.warning("\n⚠ Нет данных для сохранения на шаге 2")
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ СКРИПТ ЗАВЕРШЕН УСПЕШНО")
    logger.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise

