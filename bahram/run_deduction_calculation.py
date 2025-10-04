#!/usr/bin/env python3
"""
Автоматизированный расчет deduction с разбивкой по товарам
Запускает основной запрос и проверочный запрос для валидации результатов
Сохраняет результаты в базу данных и Excel файлы
"""

import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
import os

# Параметры подключения к базе данных
DB_CONFIG = {
    'user': 'bahram',
    'password': 'Dadajonim99',
    'host': '94.103.84.245',
    'port': '5432',
    'database': 'wb_baah'
}

# Создание подключения
engine = create_engine(
    f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
)

# Пути к SQL файлам
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_SQL = os.path.join(SCRIPT_DIR, 'deduction_by_nm_id_main.sql')
VALIDATION_SQL = os.path.join(SCRIPT_DIR, 'deduction_validation.sql')
CREATE_TABLES_SQL = os.path.join(SCRIPT_DIR, 'create_deduction_tables.sql')

# Названия таблиц в БД
MAIN_TABLE = 'analytics.deduction_by_nm_id'
VALIDATION_TABLE = 'analytics.deduction_validation'


def load_sql_file(file_path):
    """Загружает SQL запрос из файла"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def create_tables_if_not_exist(engine):
    """
    Создает таблицы в БД если они не существуют
    
    Args:
        engine: SQLAlchemy engine
    """
    print("=" * 80)
    print("СОЗДАНИЕ/ПРОВЕРКА ТАБЛИЦ В БД")
    print("=" * 80)
    
    try:
        sql_create = load_sql_file(CREATE_TABLES_SQL)
        
        with engine.begin() as conn:
            conn.execute(text(sql_create))
        
        print(f"✅ Таблицы созданы/проверены:")
        print(f"   - {MAIN_TABLE}")
        print(f"   - {VALIDATION_TABLE}")
        print()
        
    except Exception as e:
        print(f"⚠️ Ошибка при создании таблиц: {str(e)}")
        print("Продолжаем выполнение...")
        print()


def save_to_database(df, table_name, engine, if_exists='replace'):
    """
    Сохраняет DataFrame в таблицу БД
    
    Args:
        df: DataFrame для сохранения
        table_name: имя таблицы (с схемой)
        engine: SQLAlchemy engine
        if_exists: 'replace', 'append', 'fail'
    """
    schema, table = table_name.split('.')
    
    # Подготовка данных для сохранения
    df_to_save = df.copy()
    
    # Переименовываем колонки для соответствия БД
    column_mapping = {
        'ID кампании': 'campaign_id',
        'Реклама': 'reklama',
        'Номера УПД': 'reklama',
        'Номер рекламы': 'reklama',
        'Дата начала': 'date_from',
        'Дата конца': 'date_to',
        'Кол-во УПД': 'upd_count',
        'Кол-во товаров': 'nm_count',
        'Исходная сумма': 'original_sum',
        'Сумма после разбивки': 'sum_after_split',
        'Разница': 'difference',
        'Статус': 'status'
    }
    
    df_to_save.rename(columns=column_mapping, inplace=True)
    
    # Удаляем старые данные если replace
    if if_exists == 'replace':
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {table_name}"))
    
    # Сохраняем в БД
    df_to_save.to_sql(
        name=table,
        schema=schema,
        con=engine,
        if_exists='append',
        index=False,
        method='multi',
        chunksize=1000
    )


def run_main_calculation(engine, save_to_db=True):
    """
    Запускает основной расчет deduction с разбивкой по товарам
    
    Args:
        engine: SQLAlchemy engine
        save_to_db: сохранять ли результат в БД
    
    Returns:
        DataFrame с результатами расчета
    """
    print("=" * 80)
    print("ОСНОВНОЙ РАСЧЕТ: Deduction с разбивкой по товарам")
    print("=" * 80)
    
    sql_query = load_sql_file(MAIN_SQL)
    
    print("⏳ Выполнение запроса...")
    start_time = datetime.now()
    
    df_result = pd.read_sql(sql_query, engine)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    print(f"✅ Запрос выполнен за {elapsed:.2f} сек")
    print(f"📊 Получено строк: {len(df_result)}")
    print(f"📦 Уникальных товаров (nm_id): {df_result['nm_id'].nunique()}")
    print(f"🏢 Поставщиков: {df_result['supplier'].nunique()}")
    print(f"💰 Общая сумма deduction: {df_result['deduction'].sum():.2f}")
    
    # Сохранение в БД
    if save_to_db and len(df_result) > 0:
        print(f"⏳ Сохранение в БД: {MAIN_TABLE}...")
        save_to_database(df_result, MAIN_TABLE, engine, if_exists='replace')
        print(f"✅ Сохранено {len(df_result)} записей в БД")
    
    print("\n📋 Первые 5 строк результата:")
    print(df_result.head().to_string())
    print()
    
    return df_result


def run_validation(engine, save_to_db=True):
    """
    Запускает проверочный запрос для валидации корректности разбивки
    Проверяет данные из analytics.deduction_by_nm_id против reports.detail_finance_reports
    
    Args:
        engine: SQLAlchemy engine
        save_to_db: сохранять ли результат в БД
    
    Returns:
        DataFrame с результатами валидации
    """
    print("=" * 80)
    print("ПРОВЕРКА: Валидация корректности разбивки")
    print("=" * 80)
    print("📊 Источник данных: analytics.deduction_by_nm_id (уже сохраненные результаты)")
    print("🔍 Сравнение с: reports.detail_finance_reports")
    print()
    
    sql_query = load_sql_file(VALIDATION_SQL)
    
    print("⏳ Выполнение проверочного запроса...")
    start_time = datetime.now()
    
    df_validation = pd.read_sql(sql_query, engine)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    print(f"✅ Проверка завершена за {elapsed:.2f} сек")
    print(f"📊 Проверено записей: {len(df_validation)}")
    
    # Сохранение в БД
    if save_to_db and len(df_validation) > 0:
        print(f"⏳ Сохранение в БД: {VALIDATION_TABLE}...")
        save_to_database(df_validation, VALIDATION_TABLE, engine, if_exists='replace')
        print(f"✅ Сохранено {len(df_validation)} записей в БД")
    
    # Статистика по статусам
    status_counts = df_validation['Статус'].value_counts()
    
    print("\n📈 СТАТИСТИКА ПО СТАТУСАМ:")
    print("-" * 50)
    for status, count in status_counts.items():
        emoji = "✅" if status == "OK" else "⚠️" if "НЕТ" in status else "❌"
        print(f"{emoji} {status}: {count}")
    
    # Показываем проблемные записи
    errors = df_validation[df_validation['Статус'] == 'ОШИБКА']
    if len(errors) > 0:
        print(f"\n❌ НАЙДЕНЫ ОШИБКИ ({len(errors)} записей):")
        print("-" * 50)
        print(errors.to_string())
    else:
        print("\n✅ ОШИБОК НЕ НАЙДЕНО! Все суммы совпадают.")
    
    # Записи без источника
    missing_source = df_validation[df_validation['Статус'] == 'НЕТ_В_ИСТОЧНИКЕ']
    if len(missing_source) > 0:
        print(f"\n⚠️ Записи без источника ({len(missing_source)}):")
        print("-" * 50)
        cols_to_show = []
        if 'realizationreport_id' in missing_source.columns:
            cols_to_show.append('realizationreport_id')
        if 'Номера УПД' in missing_source.columns:
            cols_to_show.append('Номера УПД')
        if 'supplier' in missing_source.columns:
            cols_to_show.append('supplier')
        if 'Сумма после разбивки' in missing_source.columns:
            cols_to_show.append('Сумма после разбивки')
        print(missing_source[cols_to_show].to_string())
    
    print()
    return df_validation


def main():
    """Главная функция для запуска расчетов"""
    print("\n" + "=" * 80)
    print("АВТОМАТИЗИРОВАННЫЙ РАСЧЕТ DEDUCTION ПО ТОВАРАМ")
    print(f"Дата запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80 + "\n")
    
    try:
        # 0. Создание/проверка таблиц в БД
        create_tables_if_not_exist(engine)
        
        # 1. Основной расчет
        df_main = run_main_calculation(engine, save_to_db=True)
        
        # 2. Валидация результатов
        df_validation = run_validation(engine, save_to_db=True)
        
        # 3. Итоговая сводка
        print("=" * 80)
        print("ИТОГОВАЯ СВОДКА")
        print("=" * 80)
        
        errors_count = len(df_validation[df_validation['Статус'] == 'ОШИБКА'])
        ok_count = len(df_validation[df_validation['Статус'] == 'OK'])
        total = len(df_validation)
        
        if errors_count == 0:
            print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО!")
            print(f"✅ Корректных записей: {ok_count} из {total}")
        else:
            print(f"⚠️ ВНИМАНИЕ! Обнаружены ошибки: {errors_count} из {total}")
            print(f"✅ Корректных записей: {ok_count} из {total}")
            print(f"❌ Процент ошибок: {(errors_count/total*100):.2f}%")
        
        print("\n💾 РЕЗУЛЬТАТЫ СОХРАНЕНЫ В БД:")
        print(f"   - Таблица с расчетом: {MAIN_TABLE}")
        print(f"     Записей: {len(df_main)}")
        print(f"   - Таблица валидации: {VALIDATION_TABLE}")
        print(f"     Записей: {len(df_validation)}")
        
        print("\n💡 Для просмотра результатов используйте:")
        print(f"   SELECT * FROM {MAIN_TABLE} LIMIT 10;")
        print(f"   SELECT * FROM {VALIDATION_TABLE} WHERE status != 'OK';")
        print(f"   SELECT * FROM analytics.deduction_errors;  -- представление с ошибками")
        
        print("=" * 80 + "\n")
        
        return df_main, df_validation
        
    except Exception as e:
        print(f"\n❌ ОШИБКА: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

