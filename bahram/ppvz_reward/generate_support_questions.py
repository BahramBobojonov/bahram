#!/usr/bin/env python3

import pandas as pd
import os
from datetime import datetime

def load_failed_data():
    """
    Загружает данные о неудачных совпадениях
    """
    df_failed = pd.read_excel('expenses_failed_nm_id.xlsx')
    print(f"Загружено неудачных записей: {len(df_failed)}")
    return df_failed

def group_by_suppliers(df_failed):
    """
    Группирует данные по ИП (один файл на ИП)
    """
    print("\n=== ГРУППИРОВКА ДАННЫХ ПО ИП ===")
    
    # Группируем по ИП
    grouped = df_failed.groupby('supplier').agg({
        'srid': ['count', 'nunique', list],
        'ppvz_reward': ['sum', 'count'],
        'realizationreport_id': ['nunique', list],
        'date_from': ['min', 'max'],
        'doc_type_name': lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 'Неизвестно',
        'supplier_oper_name': lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 'Неизвестно'
    }).reset_index()
    
    # Упрощаем названия колонок
    grouped.columns = [
        'supplier', 'total_records', 'unique_srid_count', 'srid_list',
        'total_ppvz_reward', 'ppvz_records_count', 'unique_reports_count', 'reports_list',
        'date_from_min', 'date_from_max', 'doc_type_name', 'supplier_oper_name'
    ]
    
    print(f"Создано групп по ИП: {len(grouped)}")
    
    # Показываем статистику
    print(f"\nСтатистика по ИП:")
    for _, row in grouped.iterrows():
        print(f"  {row['supplier']}: {row['total_records']} записей, {row['unique_srid_count']} srid, {row['unique_reports_count']} отчетов, {row['total_ppvz_reward']:.2f} руб.")
    
    return grouped

def generate_support_question_by_supplier(group_data):
    """
    Генерирует вопрос для поддержки WB по ИП с перечислением всех srid
    """
    supplier = group_data['supplier']
    total_records = group_data['total_records']
    unique_srid_count = group_data['unique_srid_count']
    srid_list = group_data['srid_list']
    total_ppvz_reward = group_data['total_ppvz_reward']
    unique_reports_count = group_data['unique_reports_count']
    reports_list = group_data['reports_list']
    date_from_min = group_data['date_from_min']
    date_from_max = group_data['date_from_max']
    
    # Формируем список отчетов
    reports_text = ', '.join([str(r) for r in reports_list])
    
    # Формируем список srid (первые 50 для краткости)
    srid_sample = srid_list[:50]
    srid_text = '\n'.join([f'"{srid}"' for srid in srid_sample])
    if len(srid_list) > 50:
        srid_text += f'\n... и еще {len(srid_list) - 50} srid'
    
    question = f"""Здравствуйте! Проблема с API статистики WB.

ИП: {supplier}
Период: {date_from_min} - {date_from_max}
Отчетов: {unique_reports_count}
Записей с nm_id=0: {total_records}
Уникальных srid: {unique_srid_count}
Сумма PPVZ Reward: {total_ppvz_reward:.2f} руб.

Отчеты: {reports_text}

API: https://statistics-api.wildberries.ru/api/v5/supplier/reportDetailByPeriod

Проблема: есть расходы PPVZ Reward, но нет nm_id. По srid не находим номенклатуру в тех же отчетах.

SRID без nm_id:
{srid_text}

Вопрос: почему nm_id=0? Как получить правильные nm_id через API?

{supplier}"""
    
    return question

def create_questions_directory():
    """
    Создает директорию для вопросов
    """
    questions_dir = 'support_questions'
    if not os.path.exists(questions_dir):
        os.makedirs(questions_dir)
        print(f"Создана директория: {questions_dir}")
    return questions_dir

def generate_all_questions():
    """
    Генерирует все вопросы для поддержки (по одному файлу на ИП)
    """
    print("=== ГЕНЕРАЦИЯ ВОПРОСОВ ДЛЯ ПОДДЕРЖКИ WB (ПО ИП) ===")
    
    # Загружаем данные
    df_failed = load_failed_data()
    
    # Группируем по ИП
    grouped = group_by_suppliers(df_failed)
    
    # Создаем директорию для вопросов
    questions_dir = create_questions_directory()
    
    print(f"\n=== СОЗДАНИЕ ФАЙЛОВ ВОПРОСОВ ===")
    
    # Генерируем вопрос для каждого ИП
    for idx, (_, group_data) in enumerate(grouped.iterrows(), 1):
        supplier = group_data['supplier']
        
        # Создаем безопасное имя файла
        safe_supplier = supplier.replace(' ', '_').replace('.', '').replace(',', '')
        filename = f"question_{safe_supplier}.txt"
        filepath = os.path.join(questions_dir, filename)
        
        # Генерируем вопрос
        question = generate_support_question_by_supplier(group_data)
        
        # Сохраняем в файл
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(question)
        
        print(f"✓ Создан файл {idx}/{len(grouped)}: {filename}")
    
    print(f"\n=== ИТОГОВАЯ СТАТИСТИКА ===")
    print(f"Всего создано файлов вопросов: {len(grouped)}")
    print(f"Директория с файлами: {questions_dir}/")
    
    # Создаем сводный файл
    summary_file = os.path.join(questions_dir, 'SUMMARY.txt')
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write("СВОДКА ПО ВОПРОСАМ В ПОДДЕРЖКУ WB (ПО ИП)\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Дата создания: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
        f.write(f"Всего файлов вопросов: {len(grouped)}\n\n")
        
        f.write("СПИСОК ФАЙЛОВ:\n")
        f.write("-" * 30 + "\n")
        for idx, (_, group_data) in enumerate(grouped.iterrows(), 1):
            supplier = group_data['supplier']
            total_records = group_data['total_records']
            unique_srid_count = group_data['unique_srid_count']
            unique_reports_count = group_data['unique_reports_count']
            total_ppvz_reward = group_data['total_ppvz_reward']
            
            f.write(f"{idx:2d}. {supplier}\n")
            f.write(f"    Записей: {total_records}, Srid: {unique_srid_count}, Отчетов: {unique_reports_count}\n")
            f.write(f"    Сумма: {total_ppvz_reward:.2f} руб.\n")
            f.write(f"    Файл: question_{supplier.replace(' ', '_').replace('.', '').replace(',', '')}.txt\n\n")
    
    print(f"✓ Создан сводный файл: {summary_file}")
    
    return grouped

def main():
    """
    Основная функция
    """
    try:
        grouped = generate_all_questions()
        
        print(f"\n=== ГОТОВО! ===")
        print(f"Все файлы с вопросами созданы в директории 'support_questions/'")
        print(f"Каждый файл содержит готовый текст для копирования в чат поддержки WB")
        print(f"Сводная информация находится в файле SUMMARY.txt")
        
    except Exception as e:
        print(f"✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
