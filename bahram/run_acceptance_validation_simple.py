#!/usr/bin/env python3
"""
Упрощенный скрипт для проверки корректности разбивки платной приемки по nm_id
"""

import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import logging
import sys
import os

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('acceptance_validation.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Подключение к базе данных
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

def run_acceptance_validation(date_from, date_to):
    """
    Запускает валидацию данных по платной приемке
    
    Args:
        date_from (str): Дата начала периода в формате 'YYYY-MM-DD'
        date_to (str): Дата окончания периода в формате 'YYYY-MM-DD'
    
    Returns:
        tuple: (df_main, df_summary) - основные данные и сводная статистика
    """
    try:
        logger.info(f"🔍 Запуск валидации платной приемки за период {date_from} - {date_to}")
        
        # Основной SQL запрос с подстановкой дат
        sql_query = f"""
        WITH cte_acceptance AS (
            SELECT 
                sum(t.acceptance_sum) AS acceptance_sum,
                t.nmid,
                t.supplier,
                t.date
            FROM (
                -- Данные из reports.acceptance
                SELECT 
                    a.supplier,
                    a.nmid,
                    a."shkcreatedate"::date AS date,
                    sum(a.total) AS acceptance_sum
                FROM reports.acceptance a
                WHERE a."shkcreatedate"::date >= '{date_from}'::date
                GROUP BY a.nmid, a."shkcreatedate", a.supplier
                HAVING sum(a.total) > 0::double precision
                
                UNION ALL
                
                -- Данные из supplies.corrected_fbs_incomes
                SELECT 
                    cfi.supplier,
                    cfi.nmid,
                    cfi.createdat::date AS date,
                    sum(cfi.scanprice) AS acceptance_sum
                FROM supplies.corrected_fbs_incomes cfi
                WHERE cfi.createdat::date >= '{date_from}'::date
                    AND cfi.scanprice >= 0::double precision 
                    AND cfi.scanprice IS NOT NULL 
                    AND cfi.scanprice <> 'NaN'::double precision
                GROUP BY cfi.nmid, cfi.createdat, cfi.supplier
                HAVING sum(cfi.scanprice) > 0::double precision
            ) t
            WHERE t.date >= '{date_from}'::date
                AND t.date <= '{date_to}'::date
            GROUP BY t.nmid, t.supplier, t.date
        ),
        
        cte_detail_reports AS (
            SELECT 
                supplier,
                realizationreport_id,
                nm_id,
                date_from,
                date_to,
                SUM(acceptance::numeric) AS acceptance_from_detail,
                COUNT(*) AS record_count
            FROM reports.detail_finance_reports
            WHERE date_from::date >= '{date_from}'::date
                AND date_to::date <= '{date_to}'::date
                AND acceptance::numeric != 0
            GROUP BY supplier, realizationreport_id, nm_id, date_from, date_to
        ),
        
        cte_aggregated AS (
            SELECT 
                supplier_name,
                realizationreport_id,
                date_from,
                date_to,
                acceptance_total,
                report_date
            FROM reports.aggregated_finance_report
            WHERE report_date >= '{date_from}'::date
                AND report_date <= '{date_to}'::date
        ),
        
        main_comparison AS (
            SELECT 
                COALESCE(a.supplier, dr.supplier, agg.supplier_name) AS supplier_name,
                COALESCE(dr.realizationreport_id, agg.realizationreport_id) AS realizationreport_id,
                COALESCE(dr.date_from, agg.date_from) AS date_from,
                COALESCE(dr.date_to, agg.date_to) AS date_to,
                COALESCE(dr.nm_id, a.nmid) AS nm_id,
                
                COALESCE(a.acceptance_sum, 0) AS acceptance_corrected,
                COALESCE(dr.acceptance_from_detail, 0) AS acceptance_from_detail,
                COALESCE(agg.acceptance_total, 0) AS acceptance_aggregated,
                
                CASE 
                    WHEN COALESCE(a.acceptance_sum, 0) = COALESCE(dr.acceptance_from_detail, 0) 
                        AND COALESCE(dr.acceptance_from_detail, 0) = COALESCE(agg.acceptance_total, 0)
                    THEN 'OK'
                    WHEN COALESCE(a.acceptance_sum, 0) != COALESCE(dr.acceptance_from_detail, 0)
                    THEN 'MISMATCH_DETAIL'
                    WHEN COALESCE(dr.acceptance_from_detail, 0) != COALESCE(agg.acceptance_total, 0)
                    THEN 'MISMATCH_AGGREGATED'
                    ELSE 'PARTIAL_MISMATCH'
                END AS validation_status,
                
                COALESCE(a.acceptance_sum, 0) - COALESCE(dr.acceptance_from_detail, 0) AS diff_corrected_vs_detail,
                COALESCE(dr.acceptance_from_detail, 0) - COALESCE(agg.acceptance_total, 0) AS diff_detail_vs_aggregated,
                
                dr.record_count,
                agg.report_date
                
            FROM cte_acceptance a
            FULL OUTER JOIN cte_detail_reports dr 
                ON a.nmid = dr.nm_id 
                AND a.supplier = dr.supplier
                AND a.date = dr.date_from::date
            FULL OUTER JOIN cte_aggregated agg
                ON dr.supplier = agg.supplier_name
                AND dr.realizationreport_id = agg.realizationreport_id
                AND dr.date_from = agg.date_from
                AND dr.date_to = agg.date_to
        )
        
        SELECT 
            supplier_name,
            realizationreport_id,
            date_from,
            date_to,
            nm_id,
            acceptance_corrected,
            acceptance_from_detail,
            acceptance_aggregated,
            validation_status,
            diff_corrected_vs_detail,
            diff_detail_vs_aggregated,
            record_count,
            report_date,
            
            CASE 
                WHEN validation_status = 'OK' THEN '✅ Корректно'
                WHEN validation_status = 'MISMATCH_DETAIL' THEN '⚠️ Несоответствие в детализации'
                WHEN validation_status = 'MISMATCH_AGGREGATED' THEN '⚠️ Несоответствие в агрегации'
                ELSE '❌ Частичное несоответствие'
            END AS status_description,
            
            CASE 
                WHEN ABS(diff_corrected_vs_detail) > 0 THEN 1
                WHEN ABS(diff_detail_vs_aggregated) > 0 THEN 2
                ELSE 3
            END AS fix_priority

        FROM main_comparison
        WHERE (acceptance_corrected != 0 OR acceptance_from_detail != 0 OR acceptance_aggregated != 0)
        ORDER BY 
            fix_priority ASC,
            ABS(diff_corrected_vs_detail) DESC,
            ABS(diff_detail_vs_aggregated) DESC,
            supplier_name,
            realizationreport_id,
            nm_id
        """
        
        with engine.connect() as conn:
            logger.info("📊 Выполнение основного запроса валидации...")
            df_main = pd.read_sql(sql_query, conn)
            
            # Сводная статистика
            logger.info("📈 Получение сводной статистики...")
            summary_query = f"""
            WITH summary_stats AS (
                SELECT 
                    COUNT(*) AS total_records,
                    COUNT(CASE WHEN validation_status = 'OK' THEN 1 END) AS correct_records,
                    COUNT(CASE WHEN validation_status != 'OK' THEN 1 END) AS incorrect_records,
                    SUM(acceptance_corrected) AS total_acceptance_corrected,
                    SUM(acceptance_from_detail) AS total_acceptance_detail,
                    SUM(acceptance_aggregated) AS total_acceptance_aggregated,
                    SUM(ABS(diff_corrected_vs_detail)) AS total_diff_corrected_detail,
                    SUM(ABS(diff_detail_vs_aggregated)) AS total_diff_detail_aggregated
                FROM ({sql_query}) main_data
            )
            SELECT 
                'СВОДНАЯ СТАТИСТИКА' AS report_type,
                total_records,
                correct_records,
                incorrect_records,
                ROUND((correct_records::numeric / NULLIF(total_records, 0) * 100), 2) AS accuracy_percent,
                total_acceptance_corrected,
                total_acceptance_detail,
                total_acceptance_aggregated,
                total_diff_corrected_detail,
                total_diff_detail_aggregated,
                CASE 
                    WHEN total_diff_corrected_detail = 0 AND total_diff_detail_aggregated = 0 
                    THEN '✅ Все данные корректны'
                    ELSE '⚠️ Требуется исправление'
                END AS overall_status
            FROM summary_stats
            """
            
            df_summary = pd.read_sql(summary_query, conn)
            
        logger.info(f"✅ Валидация завершена. Получено {len(df_main)} записей")
        return df_main, df_summary
        
    except Exception as e:
        logger.error(f"❌ Ошибка при выполнении валидации: {e}")
        raise

def analyze_results(df_main, df_summary):
    """
    Анализирует результаты валидации и выводит отчет
    """
    logger.info("📋 АНАЛИЗ РЕЗУЛЬТАТОВ ВАЛИДАЦИИ")
    logger.info("=" * 80)
    
    # Выводим сводную статистику
    if not df_summary.empty:
        summary_row = df_summary.iloc[0]
        logger.info(f"📊 СВОДНАЯ СТАТИСТИКА:")
        logger.info(f"   Всего записей: {summary_row['total_records']}")
        logger.info(f"   Корректных записей: {summary_row['correct_records']}")
        logger.info(f"   Некорректных записей: {summary_row['incorrect_records']}")
        logger.info(f"   Точность: {summary_row['accuracy_percent']}%")
        logger.info(f"   Общий статус: {summary_row['overall_status']}")
        logger.info("")
    
    # Анализируем несоответствия
    incorrect_records = df_main[df_main['validation_status'] != 'OK']
    
    if len(incorrect_records) > 0:
        logger.warning(f"⚠️ НАЙДЕНО {len(incorrect_records)} НЕСООТВЕТСТВИЙ:")
        logger.info("")
        
        # Группируем по типу несоответствия
        status_counts = incorrect_records['validation_status'].value_counts()
        for status, count in status_counts.items():
            logger.warning(f"   {status}: {count} записей")
        
        logger.info("")
        
        # Топ-10 самых больших расхождений
        logger.info("🔍 ТОП-10 САМЫХ БОЛЬШИХ РАСХОЖДЕНИЙ:")
        top_discrepancies = incorrect_records.nlargest(10, 'diff_corrected_vs_detail')
        
        for idx, row in top_discrepancies.iterrows():
            logger.warning(f"   {row['supplier_name']} | {row['nm_id']} | "
                          f"Расхождение: {row['diff_corrected_vs_detail']:.2f} | "
                          f"Статус: {row['status_description']}")
        
        logger.info("")
        
        # Анализ по поставщикам
        logger.info("🏢 АНАЛИЗ ПО ПОСТАВЩИКАМ:")
        supplier_stats = incorrect_records.groupby('supplier_name').agg({
            'validation_status': 'count',
            'diff_corrected_vs_detail': ['sum', 'mean'],
            'diff_detail_vs_aggregated': ['sum', 'mean']
        }).round(2)
        
        for supplier in supplier_stats.index:
            count = supplier_stats.loc[supplier, ('validation_status', 'count')]
            diff_sum = supplier_stats.loc[supplier, ('diff_corrected_vs_detail', 'sum')]
            logger.warning(f"   {supplier}: {count} несоответствий, "
                          f"суммарное расхождение: {diff_sum:.2f}")
        
    else:
        logger.info("✅ Все данные корректны! Несоответствий не найдено.")

def save_results_to_excel(df_main, df_summary, date_from, date_to):
    """
    Сохраняет результаты в Excel файл
    """
    try:
        filename = f"acceptance_validation_{date_from}_to_{date_to}.xlsx"
        
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            # Основные данные
            df_main.to_excel(writer, sheet_name='Validation_Results', index=False)
            
            # Сводная статистика
            df_summary.to_excel(writer, sheet_name='Summary', index=False)
            
            # Только несоответствия
            incorrect_records = df_main[df_main['validation_status'] != 'OK']
            if len(incorrect_records) > 0:
                incorrect_records.to_excel(writer, sheet_name='Discrepancies', index=False)
        
        logger.info(f"💾 Результаты сохранены в файл: {filename}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении результатов: {e}")

def main():
    """Основная функция"""
    try:
        # Параметры по умолчанию
        date_from = '2024-12-01'
        date_to = '2024-12-31'
        
        # Можно передать параметры через командную строку
        if len(sys.argv) >= 3:
            date_from = sys.argv[1]
            date_to = sys.argv[2]
        
        logger.info("🚀 ЗАПУСК СКРИПТА ВАЛИДАЦИИ ПЛАТНОЙ ПРИЕМКИ")
        logger.info(f"📅 Период: {date_from} - {date_to}")
        logger.info("=" * 80)
        
        # Запускаем валидацию
        df_main, df_summary = run_acceptance_validation(date_from, date_to)
        
        # Анализируем результаты
        analyze_results(df_main, df_summary)
        
        # Сохраняем результаты
        save_results_to_excel(df_main, df_summary, date_from, date_to)
        
        logger.info("✅ СКРИПТ ЗАВЕРШЕН УСПЕШНО")
        
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
