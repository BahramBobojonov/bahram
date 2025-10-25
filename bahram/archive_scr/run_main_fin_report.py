#!/usr/bin/env python3
"""
Скрипт для запуска main_fin_report_script.sql и загрузки результатов в таблицу
"""

import pandas as pd
from sqlalchemy import create_engine, text
import logging
from datetime import datetime
import gspread

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Подключение к базе данных
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

# Получаем данные о поставщиках из Google Sheets
import os
cred_path = '/home/baakhofficial/wbauto/bahram/cred.json' if os.name != 'nt' else 'cred.json'
gc = gspread.service_account(filename=cred_path)
worksheet = gc.open_by_key("15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ").sheet1
df_investors = pd.DataFrame(worksheet.get_all_records())
df_investors = df_investors[(df_investors['API ключ'] != '') & (df_investors['API ключ'] != None)]


def load_sql_query():
    """Загружает SQL запрос из файла"""
    sql_file = '/home/baakhofficial/wbauto/bahram/main_fin_report_script.sql'
    
    try:
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_query = f.read()
        
        logger.info(f"✅ SQL запрос загружен из файла: {sql_file}")
        return sql_query
        
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке SQL файла: {e}")
        raise


def create_aggregated_report_table():
    """Создает таблицу для агрегированных данных"""
    
    create_table_query = text("""
    CREATE TABLE IF NOT EXISTS reports.aggregated_finance_report (
        supplier_name VARCHAR(255) NOT NULL,
        realizationreport_id DOUBLE PRECISION NOT NULL,
        report_date DATE,
        date_from TEXT,
        date_to TEXT,
        prodazha_do_komissii NUMERIC(15,2),
        vozvrat_do_komissii NUMERIC(15,2),
        prodazha_posle_komissii NUMERIC(15,2),
        vozvrat_posle_komissii NUMERIC(15,2),
        acquiring_fee_sum NUMERIC(15,2),
        korrektirovka_ekvayringa NUMERIC(15,2),
        kompensaciya_pri_vozvrate NUMERIC(15,2),
        kompensaciya_uscherba_prodazha NUMERIC(15,2),
        kompensaciya_uscherba_vozvrat NUMERIC(15,2),
        oplata_braka NUMERIC(15,2),
        chastichnaya_kompensaciya_braka NUMERIC(15,2),
        kompensaciya_braka NUMERIC(15,2),
        kompensaciya_podmenennogo_tovara NUMERIC(15,2),
        oplata_poteryannogo_tovara NUMERIC(15,2),
        kompensaciya_poteryannogo_tovara NUMERIC(15,2),
        oplata_po_itogam_inventarizacii NUMERIC(15,2),
        avansovaya_oplata_bez_dvizheniya_prodazha NUMERIC(15,2),
        avansovaya_oplata_bez_dvizheniya_vozvrat NUMERIC(15,2),
        komossia NUMERIC(15,2),
        margin_after_commission NUMERIC(15,4),
        k_perecheisleniyu_za_tovar NUMERIC(15,2),
        logistics_total NUMERIC(15,2),
        logistics_count INTEGER,
        logistics_storno_count INTEGER,
        correction_count INTEGER,
        logistics_return_positive_total NUMERIC(15,2),
        logistics_return_positive_count INTEGER,
        bonus_return_total NUMERIC(15,2),
        bonus_return_count INTEGER,
        logistics_positive_total NUMERIC(15,2),
        penalties_total NUMERIC(15,2),
        additional_payment_total NUMERIC(15,2),
        storage_fee_total NUMERIC(15,2),
        storage_recalculation_total NUMERIC(15,2),
        storage_correction_total NUMERIC(15,2),
        acceptance_total NUMERIC(15,2),
        acceptance_recalculation_total NUMERIC(15,2),
        deduction_total NUMERIC(15,2),
        deduction_negative_total NUMERIC(15,2),
        deduction_positive_total NUMERIC(15,2),
        deduction_writeoff_total NUMERIC(15,2),
        deduction_adv_total NUMERIC(15,2),
        deduction_other_total NUMERIC(15,2),
        total_to_transfer NUMERIC(15,2),
        net_retail_amount NUMERIC(15,2),
        net_amount_after_vat NUMERIC(15,2),
        tax_to_pay NUMERIC(15,2),
        vat_amount NUMERIC(15,2),
        profit_after_all NUMERIC(15,2),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(supplier_name, realizationreport_id, date_from, date_to)
    );
    
    CREATE INDEX IF NOT EXISTS idx_agg_supplier ON reports.aggregated_finance_report(supplier_name);
    CREATE INDEX IF NOT EXISTS idx_agg_dates ON reports.aggregated_finance_report(date_from, date_to);
    CREATE INDEX IF NOT EXISTS idx_agg_report_id ON reports.aggregated_finance_report(realizationreport_id);
    """)
    
    try:
        with engine.connect() as conn:
            conn.execute(create_table_query)
            conn.commit()
        
        logger.info("✅ Таблица aggregated_finance_report создана/проверена")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при создании таблицы: {e}")
        raise


def run_aggregated_report(supplier_filter=None):
    """
    Запускает агрегированный отчёт для всех или конкретных поставщиков
    
    :param supplier_filter: Список имён поставщиков для фильтрации (опционально)
    """
    
    logger.info("\n" + "=" * 80)
    logger.info("ЗАПУСК АГРЕГИРОВАННОГО ФИНАНСОВОГО ОТЧЁТА")
    logger.info("=" * 80)
    
    # Загружаем SQL запрос
    sql_query = load_sql_query()
    
    # Не создаём таблицу программно - pandas создаст её автоматически из DataFrame с правильными типами
    # create_aggregated_report_table()
    
    all_results = []
    success_count = 0
    error_count = 0
    
    # Обрабатываем каждого поставщика
    for idx, row in df_investors.iterrows():
        supplier_name = row['Имя Юрлица']
        
        # Фильтрация если указана
        if supplier_filter and supplier_name not in supplier_filter:
            continue
        
        # Получаем ставки НДС и налога для поставщика
        supplier_vat_rate = float(row.get('Ставка НДС', 0.2))  # По умолчанию 20%
        supplier_tax_rate = float(row.get('Ставка налога', 0.06))  # По умолчанию 6%
        
        logger.info(f"\n📊 Обработка поставщика: {supplier_name}")
        logger.info(f"   НДС: {supplier_vat_rate*100}%, Налог: {supplier_tax_rate*100}%")
        
        try:
            # Добавляем WHERE для фильтрации по поставщику
            supplier_sql = sql_query.replace(
                "FROM reports.detail_finance_reports",
                f"FROM reports.detail_finance_reports WHERE supplier = '{supplier_name}'"
            )
            
            # Выполняем запрос с параметрами
            result_df = pd.read_sql(
                text(supplier_sql), 
                engine,
                params={
                    'vat_rate': supplier_vat_rate,
                    'tax_rate': supplier_tax_rate
                }
            )
            
            if not result_df.empty:
                all_results.append(result_df)
                logger.info(f"   ✅ Получено {len(result_df)} записей")
                success_count += 1
            else:
                logger.warning(f"   ⚠️ Нет данных")
                
        except Exception as e:
            logger.error(f"   ❌ Ошибка: {e}")
            error_count += 1
            continue
    
    if not all_results:
        logger.warning("⚠️ Нет данных ни для одного поставщика")
        return None
    
    # Объединяем все результаты
    final_result = pd.concat(all_results, ignore_index=True)
    logger.info(f"\n✅ Итого: {len(final_result)} записей для {success_count} поставщиков")
    
    # Сохраняем в таблицу
    logger.info("\n💾 Сохранение данных в таблицу...")
    
    try:
        # Проверяем существование таблицы и удаляем старые записи
        suppliers_list = "', '".join(final_result['supplier_name'].unique())
        
        with engine.connect() as conn:
            # Проверяем существование таблицы
            check_table = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'reports' 
                    AND table_name = 'aggregated_finance_report'
                )
            """)
            table_exists = conn.execute(check_table).scalar()
            
            if table_exists:
                # Удаляем старые записи для обновляемых поставщиков
                delete_query = text(f"""
                    DELETE FROM reports.aggregated_finance_report 
                    WHERE supplier_name IN ('{suppliers_list}')
                """)
                result = conn.execute(delete_query)
                deleted_count = result.rowcount
                conn.commit()
                logger.info(f"   Удалено {deleted_count} старых записей")
            else:
                logger.info(f"   Таблица не существует, будет создана автоматически")
        
        # Вставляем новые данные
        final_result.to_sql(
            'aggregated_finance_report',
            engine,
            schema='reports',
            if_exists='append',
            index=False,
            method='multi'
        )
        
        logger.info(f"   ✅ Загружено {len(final_result)} новых записей")
        
        # Выводим сводку
        logger.info("\n📊 СВОДКА ПО ПОСТАВЩИКАМ:")
        summary = final_result.groupby('supplier_name').agg({
            'prodazha_do_komissii': 'sum',
            'storage_fee_total': 'sum',
            'total_to_transfer': 'sum',
            'profit_after_all': 'sum'
        }).reset_index()
        
        print("\n" + "=" * 120)
        print(summary.to_string(index=False))
        print("=" * 120)
        
        return final_result
        
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении данных: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("СКРИПТ АГРЕГИРОВАННОГО ФИНАНСОВОГО ОТЧЁТА")
    logger.info("Дата: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    logger.info("=" * 80)
    
    try:
        # Запускаем для всех поставщиков
        # Можно указать конкретных: supplier_filter=['ИП Баах Р.Н.', 'ИП Астахова А.А.']
        df_result = run_aggregated_report()
        
        if df_result is not None:
            logger.info("\n✅ ОТЧЁТ УСПЕШНО СФОРМИРОВАН И ЗАГРУЖЕН В БД")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        raise

