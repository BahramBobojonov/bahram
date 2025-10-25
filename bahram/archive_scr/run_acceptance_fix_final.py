#!/usr/bin/env python3
"""
Итоговый скрипт для исправления несоответствий в данных платной приемки
"""

import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
import logging
import sys
import os

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('acceptance_fix_final.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Подключение к базе данных
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

def get_discrepancies_to_fix(date_from, date_to):
    """
    Получает список несоответствий для исправления
    """
    try:
        logger.info("🔍 Получение списка несоответствий для исправления...")
        
        query = f"""
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
        )
        SELECT 
            dr.supplier,
            dr.realizationreport_id,
            dr.nm_id,
            dr.date_from,
            dr.date_to,
            COALESCE(a.acceptance_sum, 0) AS correct_acceptance,
            dr.acceptance_from_detail AS current_acceptance,
            COALESCE(a.acceptance_sum, 0) - dr.acceptance_from_detail AS difference,
            dr.record_count
        FROM cte_detail_reports dr
        LEFT JOIN cte_acceptance a 
            ON a.nmid = dr.nm_id 
            AND a.supplier = dr.supplier
            AND a.date = dr.date_from::date
        WHERE COALESCE(a.acceptance_sum, 0) != dr.acceptance_from_detail
            AND ABS(COALESCE(a.acceptance_sum, 0) - dr.acceptance_from_detail) > 0.01
        ORDER BY ABS(COALESCE(a.acceptance_sum, 0) - dr.acceptance_from_detail) DESC
        """
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
        
        logger.info(f"📊 Найдено {len(df)} несоответствий для исправления")
        return df
        
    except Exception as e:
        logger.error(f"❌ Ошибка при получении несоответствий: {e}")
        raise

def fix_detail_finance_reports(df_discrepancies, dry_run=True):
    """
    Исправляет данные в reports.detail_finance_reports
    """
    try:
        logger.info(f"🔧 {'СИМУЛЯЦИЯ' if dry_run else 'ИСПРАВЛЕНИЕ'} данных в detail_finance_reports")
        
        if len(df_discrepancies) == 0:
            logger.info("✅ Несоответствий для исправления не найдено")
            return
        
        total_fixed = 0
        total_difference = 0
        
        for idx, row in df_discrepancies.iterrows():
            supplier = row['supplier']
            realizationreport_id = row['realizationreport_id']
            nm_id = row['nm_id']
            date_from = row['date_from']
            date_to = row['date_to']
            correct_acceptance = row['correct_acceptance']
            current_acceptance = row['current_acceptance']
            difference = row['difference']
            record_count = row['record_count']
            
            logger.info(f"📝 {supplier} | {nm_id} | {date_from}-{date_to}")
            logger.info(f"   Текущее значение: {current_acceptance:.2f}")
            logger.info(f"   Корректное значение: {correct_acceptance:.2f}")
            logger.info(f"   Разница: {difference:.2f}")
            logger.info(f"   Записей в детализации: {record_count}")
            
            if not dry_run:
                # Выполняем исправление
                update_query = text("""
                UPDATE reports.detail_finance_reports 
                SET acceptance = :correct_acceptance,
                    update_time = CURRENT_TIMESTAMP
                WHERE supplier = :supplier
                    AND realizationreport_id = :realizationreport_id
                    AND nm_id = :nm_id
                    AND date_from = :date_from
                    AND date_to = :date_to
                """)
                
                with engine.begin() as conn:
                    result = conn.execute(update_query, {
                        'correct_acceptance': correct_acceptance,
                        'supplier': supplier,
                        'realizationreport_id': realizationreport_id,
                        'nm_id': nm_id,
                        'date_from': date_from,
                        'date_to': date_to
                    })
                    
                    logger.info(f"   ✅ Обновлено записей: {result.rowcount}")
                    total_fixed += result.rowcount
                    total_difference += abs(difference)
            else:
                logger.info(f"   🔍 Будет обновлено записей: {record_count}")
                total_fixed += record_count
                total_difference += abs(difference)
            
            logger.info("")
        
        logger.info(f"📊 ИТОГО:")
        logger.info(f"   {'Будет обновлено' if dry_run else 'Обновлено'} записей: {total_fixed}")
        logger.info(f"   {'Будет исправлено' if dry_run else 'Исправлено'} расхождений: {total_difference:.2f}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при исправлении данных: {e}")
        raise

def recalculate_aggregated_report(date_from, date_to, dry_run=True):
    """
    Пересчитывает данные в reports.aggregated_finance_report
    """
    try:
        logger.info(f"🔄 {'СИМУЛЯЦИЯ' if dry_run else 'ПЕРЕСЧЕТ'} aggregated_finance_report")
        
        # Загружаем основной скрипт для пересчета
        script_path = os.path.join(os.path.dirname(__file__), 'main_fin_report_script.sql')
        
        if not os.path.exists(script_path):
            logger.error(f"❌ Файл {script_path} не найден")
            return
        
        with open(script_path, 'r', encoding='utf-8') as f:
            sql_query = f.read()
        
        # Параметры для пересчета
        params = {
            'date_from': date_from,
            'date_to': date_to,
            'vat_rate': 0.2,  # 20% НДС
            'tax_rate': 0.05  # 5% налог
        }
        
        if not dry_run:
            logger.info("📊 Выполнение пересчета aggregated_finance_report...")
            
            with engine.begin() as conn:
                # Удаляем старые записи за период
                delete_query = text(f"""
                DELETE FROM reports.aggregated_finance_report 
                WHERE report_date >= '{date_from}'::date 
                    AND report_date <= '{date_to}'::date
                """)
                
                delete_result = conn.execute(delete_query)
                
                logger.info(f"🗑️ Удалено старых записей: {delete_result.rowcount}")
                
                # Вставляем новые данные
                insert_result = conn.execute(text(sql_query), params)
                logger.info(f"✅ Вставлено новых записей: {insert_result.rowcount}")
        else:
            logger.info("🔍 Будет выполнено:")
            logger.info("   1. Удаление старых записей за период")
            logger.info("   2. Пересчет и вставка новых данных")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при пересчете aggregated_finance_report: {e}")
        raise

def main():
    """Основная функция"""
    try:
        # Параметры по умолчанию
        date_from = '2024-12-01'
        date_to = '2024-12-31'
        dry_run = True  # По умолчанию только симуляция
        
        # Парсинг аргументов командной строки
        if len(sys.argv) >= 3:
            date_from = sys.argv[1]
            date_to = sys.argv[2]
        
        if len(sys.argv) >= 4 and sys.argv[3].lower() == '--execute':
            dry_run = False
        
        logger.info("🚀 ЗАПУСК СКРИПТА ИСПРАВЛЕНИЯ ПЛАТНОЙ ПРИЕМКИ")
        logger.info(f"📅 Период: {date_from} - {date_to}")
        logger.info(f"🔧 Режим: {'СИМУЛЯЦИЯ' if dry_run else 'ВЫПОЛНЕНИЕ'}")
        logger.info("=" * 80)
        
        # Получаем несоответствия
        df_discrepancies = get_discrepancies_to_fix(date_from, date_to)
        
        if len(df_discrepancies) > 0:
            # Исправляем данные в detail_finance_reports
            fix_detail_finance_reports(df_discrepancies, dry_run)
            
            # Пересчитываем aggregated_finance_report
            recalculate_aggregated_report(date_from, date_to, dry_run)
            
            if dry_run:
                logger.info("")
                logger.info("💡 Для выполнения исправлений запустите скрипт с флагом --execute")
                logger.info("   Пример: python run_acceptance_fix_final.py 2024-12-01 2024-12-31 --execute")
        else:
            logger.info("✅ Несоответствий для исправления не найдено")
        
        logger.info("✅ СКРИПТ ЗАВЕРШЕН УСПЕШНО")
        
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
