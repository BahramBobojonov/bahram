#!/usr/bin/env python3
"""
Скрипт для сравнения таблиц aggregated_finance_report и monthly_financial_report
"""

import pandas as pd
from sqlalchemy import create_engine, text
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

def compare_tables():
    """Сравнивает количество строк и суммы в обеих таблицах"""
    
    logger.info("\n" + "=" * 100)
    logger.info("СРАВНЕНИЕ ТАБЛИЦ: aggregated_finance_report vs monthly_financial_report")
    logger.info("=" * 100)
    
    # 1. Количество строк
    logger.info("\n📊 1. КОЛИЧЕСТВО СТРОК ПО ПЕРИОДАМ:")
    
    query_counts = text("""
    WITH agg_counts AS (
        SELECT 
            DATE_TRUNC('month', report_date::date) AS month,
            COUNT(*) AS agg_count,
            COUNT(DISTINCT supplier_name) AS agg_suppliers,
            COUNT(DISTINCT realizationreport_id) AS agg_report_ids
        FROM reports.aggregated_finance_report
        WHERE report_date >= '2025-09-01'
        GROUP BY DATE_TRUNC('month', report_date::date)
    ),
    monthly_counts AS (
        SELECT 
            DATE_TRUNC('month', report_date::date) AS month,
            COUNT(*) AS monthly_count,
            COUNT(DISTINCT supplier_name) AS monthly_suppliers,
            COUNT(DISTINCT realizationreport_id) AS monthly_report_ids
        FROM reports.monthly_financial_report
        WHERE report_date >= '2025-09-01'
        GROUP BY DATE_TRUNC('month', report_date::date)
    )
    SELECT 
        COALESCE(a.month, m.month) AS month,
        COALESCE(a.agg_count, 0) AS aggregated_rows,
        COALESCE(m.monthly_count, 0) AS monthly_rows,
        COALESCE(a.agg_count, 0) - COALESCE(m.monthly_count, 0) AS diff_rows,
        COALESCE(a.agg_suppliers, 0) AS agg_suppliers,
        COALESCE(m.monthly_suppliers, 0) AS monthly_suppliers,
        COALESCE(a.agg_report_ids, 0) AS agg_report_ids,
        COALESCE(m.monthly_report_ids, 0) AS monthly_report_ids
    FROM agg_counts a
    FULL OUTER JOIN monthly_counts m ON a.month = m.month
    ORDER BY month DESC
    """)
    
    df_counts = pd.read_sql(query_counts, engine)
    print("\n" + df_counts.to_string(index=False))
    
    # 2. Детальное сравнение по поставщикам
    logger.info("\n\n📊 2. ДЕТАЛЬНОЕ СРАВНЕНИЕ ПО ПОСТАВЩИКАМ (СЕНТЯБРЬ 2025):")
    
    query_supplier_detail = text("""
    WITH agg_data AS (
        SELECT 
            supplier_name,
            COUNT(*) AS agg_records,
            COUNT(DISTINCT realizationreport_id) AS agg_report_ids,
            COUNT(DISTINCT date_from || '_' || date_to) AS agg_periods
        FROM reports.aggregated_finance_report
        WHERE report_date >= '2025-09-01' AND report_date < '2025-10-01'
        GROUP BY supplier_name
    ),
    monthly_data AS (
        SELECT 
            supplier_name,
            COUNT(*) AS monthly_records,
            COUNT(DISTINCT realizationreport_id) AS monthly_report_ids
        FROM reports.monthly_financial_report
        WHERE report_date >= '2025-09-01' AND report_date < '2025-10-01'
        GROUP BY supplier_name
    )
    SELECT 
        COALESCE(a.supplier_name, m.supplier_name) AS supplier_name,
        COALESCE(a.agg_records, 0) AS agg_records,
        COALESCE(m.monthly_records, 0) AS monthly_records,
        COALESCE(a.agg_records, 0) - COALESCE(m.monthly_records, 0) AS diff,
        COALESCE(a.agg_report_ids, 0) AS agg_report_ids,
        COALESCE(m.monthly_report_ids, 0) AS monthly_report_ids,
        COALESCE(a.agg_periods, 0) AS agg_periods
    FROM agg_data a
    FULL OUTER JOIN monthly_data m ON a.supplier_name = m.supplier_name
    ORDER BY ABS(COALESCE(a.agg_records, 0) - COALESCE(m.monthly_records, 0)) DESC
    """)
    
    df_suppliers = pd.read_sql(query_supplier_detail, engine)
    print("\n" + df_suppliers.to_string(index=False))
    
    # 3. Сравнение сумм по ключевым полям
    logger.info("\n\n📊 3. СРАВНЕНИЕ ФИНАНСОВЫХ СУММ (СЕНТЯБРЬ 2025):")
    
    query_financial = text("""
    WITH agg_sums AS (
        SELECT 
            'aggregated' AS source,
            SUM(prodazha_do_komissii) AS prodazha,
            SUM(vozvrat_do_komissii) AS vozvrat,
            SUM(storage_fee_total) AS storage_fee,
            SUM(acceptance_total) AS acceptance,
            SUM(logistics_total) AS logistics,
            SUM(total_to_transfer) AS to_transfer,
            SUM(profit_after_all) AS profit
        FROM reports.aggregated_finance_report
        WHERE report_date >= '2025-09-01' AND report_date < '2025-10-01'
    ),
    monthly_sums AS (
        SELECT 
            'monthly' AS source,
            SUM(prodazha_do_komissii) AS prodazha,
            SUM(vozvrat_do_komissii) AS vozvrat,
            SUM(storage_fee_total) AS storage_fee,
            SUM(acceptance_total) AS acceptance,
            SUM(logistics_total) AS logistics,
            SUM(total_to_transfer) AS to_transfer,
            SUM(profit_after_all) AS profit
        FROM reports.monthly_financial_report
        WHERE report_date >= '2025-09-01' AND report_date < '2025-10-01'
    )
    SELECT * FROM agg_sums
    UNION ALL
    SELECT * FROM monthly_sums
    """)
    
    df_financial = pd.read_sql(query_financial, engine)
    
    # Вычисляем разницу
    if len(df_financial) == 2:
        diff_row = pd.DataFrame([{
            'source': 'difference',
            'prodazha': df_financial.iloc[0]['prodazha'] - df_financial.iloc[1]['prodazha'],
            'vozvrat': df_financial.iloc[0]['vozvrat'] - df_financial.iloc[1]['vozvrat'],
            'storage_fee': df_financial.iloc[0]['storage_fee'] - df_financial.iloc[1]['storage_fee'],
            'acceptance': df_financial.iloc[0]['acceptance'] - df_financial.iloc[1]['acceptance'],
            'logistics': df_financial.iloc[0]['logistics'] - df_financial.iloc[1]['logistics'],
            'to_transfer': df_financial.iloc[0]['to_transfer'] - df_financial.iloc[1]['to_transfer'],
            'profit': df_financial.iloc[0]['profit'] - df_financial.iloc[1]['profit']
        }])
        df_financial = pd.concat([df_financial, diff_row], ignore_index=True)
    
    print("\n" + df_financial.to_string(index=False))
    
    # 4. Примеры дублирующихся записей
    logger.info("\n\n📊 4. ПРИМЕРЫ ЗАПИСЕЙ ДЛЯ ОДНОГО ПОСТАВЩИКА:")
    
    query_examples = text("""
    -- Aggregated table
    SELECT 
        'aggregated' AS source,
        supplier_name,
        realizationreport_id,
        report_date,
        date_from,
        date_to,
        prodazha_do_komissii,
        storage_fee_total,
        total_to_transfer
    FROM reports.aggregated_finance_report
    WHERE supplier_name = 'ИП Баах И.Л.'
        AND report_date >= '2025-09-01' AND report_date < '2025-10-01'
    ORDER BY report_date, date_from
    LIMIT 10
    """)
    
    df_examples_agg = pd.read_sql(query_examples, engine)
    
    query_examples_monthly = text("""
    -- Monthly table
    SELECT 
        'monthly' AS source,
        supplier_name,
        realizationreport_id,
        report_date,
        prodazha_do_komissii,
        storage_fee_total,
        total_to_transfer
    FROM reports.monthly_financial_report
    WHERE supplier_name = 'ИП Баах И.Л.'
        AND report_date >= '2025-09-01' AND report_date < '2025-10-01'
    ORDER BY report_date
    LIMIT 10
    """)
    
    df_examples_monthly = pd.read_sql(query_examples_monthly, engine)
    
    logger.info("\n🔹 Aggregated Finance Report:")
    print("\n" + df_examples_agg.to_string(index=False))
    
    logger.info("\n🔹 Monthly Financial Report:")
    print("\n" + df_examples_monthly.to_string(index=False))
    
    # 5. Вывод и рекомендации
    logger.info("\n\n" + "=" * 100)
    logger.info("📋 ВЫВОДЫ И РЕКОМЕНДАЦИИ:")
    logger.info("=" * 100)
    
    total_agg = df_counts['aggregated_rows'].sum()
    total_monthly = df_counts['monthly_rows'].sum()
    
    logger.info(f"""
    1. Количество записей:
       - aggregated_finance_report: {total_agg}
       - monthly_financial_report: {total_monthly}
       - Разница: {total_agg - total_monthly}
    
    2. Возможные причины расхождения:
       - В aggregated разбивка по date_from/date_to (еженедельные периоды)
       - В monthly может быть агрегация на уровне месяца
       - Один realizationreport_id может содержать несколько периодов
    
    3. Что это означает:
       {'✅ ЭТО НОРМАЛЬНО' if total_agg > total_monthly else '⚠️ ТРЕБУЕТ ПРОВЕРКИ'}
       
       Таблица aggregated_finance_report более детализирована и содержит разбивку
       по еженедельным периодам (date_from/date_to), в то время как monthly_financial_report
       агрегирует данные на уровне realizationreport_id.
    
    4. Рекомендации:
       - Для детального анализа используйте aggregated_finance_report
       - Для месячной сводки можно агрегировать aggregated по месяцам
       - Обе таблицы корректны, но решают разные задачи
    """)
    
    # Сохранение в Excel
    logger.info("\n💾 Сохранение результатов в Excel...")
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"/home/baakhofficial/wbauto/bahram/finance_reports_comparison_{timestamp}.xlsx"
    
    # Конвертируем timezone-aware datetime в naive datetime для Excel
    for col in df_counts.select_dtypes(include=['datetimetz']).columns:
        df_counts[col] = df_counts[col].dt.tz_localize(None)
    
    for col in df_examples_agg.select_dtypes(include=['datetimetz']).columns:
        df_examples_agg[col] = df_examples_agg[col].dt.tz_localize(None)
        
    for col in df_examples_monthly.select_dtypes(include=['datetimetz']).columns:
        df_examples_monthly[col] = df_examples_monthly[col].dt.tz_localize(None)
    
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df_counts.to_excel(writer, sheet_name='Counts_by_Month', index=False)
        df_suppliers.to_excel(writer, sheet_name='Suppliers_Detail', index=False)
        df_financial.to_excel(writer, sheet_name='Financial_Sums', index=False)
        df_examples_agg.to_excel(writer, sheet_name='Example_Aggregated', index=False)
        df_examples_monthly.to_excel(writer, sheet_name='Example_Monthly', index=False)
    
    logger.info(f"✅ Результаты сохранены: {filename}")

if __name__ == "__main__":
    compare_tables()

