#!/usr/bin/env python3
"""
Скрипт для проверки корректности разбивки платной приемки по nm_id
и сравнения данных между разными источниками
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

def load_sql_query():
    """Загружает SQL запрос из файла"""
    try:
        script_path = os.path.join(os.path.dirname(__file__), 'acceptance_validation_script.sql')
        with open(script_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Ошибка загрузки SQL файла: {e}")
        raise

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
        
        # Загружаем SQL запрос
        sql_query = load_sql_query()
        
        # Подготавливаем параметры
        params = {
            'date_from': date_from,
            'date_to': date_to
        }
        
        with engine.connect() as conn:
            # Выполняем основной запрос
            logger.info("📊 Выполнение основного запроса валидации...")
            df_main = pd.read_sql(text(sql_query), conn, params=params)
            
            # Выполняем запрос сводной статистики
            logger.info("📈 Получение сводной статистики...")
            summary_query = sql_query.split('-- Дополнительный запрос для сводной статистики')[1]
            df_summary = pd.read_sql(text(summary_query), conn, params=params)
            
        logger.info(f"✅ Валидация завершена. Получено {len(df_main)} записей")
        return df_main, df_summary
        
    except Exception as e:
        logger.error(f"❌ Ошибка при выполнении валидации: {e}")
        raise

def analyze_results(df_main, df_summary):
    """
    Анализирует результаты валидации и выводит отчет
    
    Args:
        df_main (pd.DataFrame): Основные данные валидации
        df_summary (pd.DataFrame): Сводная статистика
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

def fix_discrepancies(df_main):
    """
    Предлагает исправления для найденных несоответствий
    
    Args:
        df_main (pd.DataFrame): Основные данные валидации
    """
    incorrect_records = df_main[df_main['validation_status'] != 'OK']
    
    if len(incorrect_records) == 0:
        logger.info("✅ Исправления не требуются - все данные корректны")
        return
    
    logger.info("🔧 ПРЕДЛОЖЕНИЯ ПО ИСПРАВЛЕНИЮ:")
    logger.info("=" * 80)
    
    # Группируем по приоритету исправления
    priority_groups = incorrect_records.groupby('fix_priority')
    
    for priority, group in priority_groups:
        logger.info(f"🎯 ПРИОРИТЕТ {priority}:")
        
        if priority == 1:
            logger.info("   Несоответствие между корректными данными и детализацией")
            logger.info("   Рекомендация: Обновить данные в reports.detail_finance_reports")
            
        elif priority == 2:
            logger.info("   Несоответствие между детализацией и агрегацией")
            logger.info("   Рекомендация: Пересчитать reports.aggregated_finance_report")
            
        else:
            logger.info("   Частичные несоответствия")
            logger.info("   Рекомендация: Проверить данные вручную")
        
        logger.info(f"   Записей для исправления: {len(group)}")
        logger.info("")

def save_results_to_excel(df_main, df_summary, date_from, date_to):
    """
    Сохраняет результаты в Excel файл
    
    Args:
        df_main (pd.DataFrame): Основные данные валидации
        df_summary (pd.DataFrame): Сводная статистика
        date_from (str): Дата начала периода
        date_to (str): Дата окончания периода
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
        
        # Предлагаем исправления
        fix_discrepancies(df_main)
        
        # Сохраняем результаты
        save_results_to_excel(df_main, df_summary, date_from, date_to)
        
        logger.info("✅ СКРИПТ ЗАВЕРШЕН УСПЕШНО")
        
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
