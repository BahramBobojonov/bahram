#!/usr/bin/env python3

import pandas as pd
import numpy as np

def analyze_duplicates_before_merge():
    """
    Анализ дублей во втором файле перед мерджем
    """
    print("=== АНАЛИЗ ДУБЛЕЙ ВО ВТОРОМ ФАЙЛЕ ===")
    
    # Загружаем второй файл
    df_srid_nm = pd.read_csv('srid_nm_id.csv')
    
    print(f"Всего записей во втором файле: {len(df_srid_nm):,}")
    print(f"Уникальных srid: {df_srid_nm['srid'].nunique():,}")
    print(f"Дублей srid: {len(df_srid_nm) - df_srid_nm['srid'].nunique():,}")
    
    # Анализ дублей по srid
    srid_counts = df_srid_nm['srid'].value_counts()
    duplicates = srid_counts[srid_counts > 1]
    
    print(f"\nSrid с дублями: {len(duplicates):,}")
    print(f"Максимальное количество дублей для одного srid: {duplicates.max()}")
    print(f"Среднее количество дублей: {duplicates.mean():.2f}")
    
    # Показываем примеры дублей
    print(f"\nПримеры дублей (первые 5):")
    for srid, count in duplicates.head().items():
        print(f"  {srid}: {count} раз")
        example_rows = df_srid_nm[df_srid_nm['srid'] == srid][['srid', 'nm_id']].head(3)
        print(f"    Примеры nm_id: {example_rows['nm_id'].tolist()}")
    
    return df_srid_nm, duplicates

def handle_duplicates_strategy(df_srid_nm, duplicates):
    """
    Стратегия обработки дублей: берем первое вхождение каждого srid
    """
    print(f"\n=== СТРАТЕГИЯ ОБРАБОТКИ ДУБЛЕЙ ===")
    print("Стратегия: берем первое вхождение каждого srid (drop_duplicates)")
    
    # Удаляем дубли, оставляя первое вхождение
    df_srid_nm_unique = df_srid_nm.drop_duplicates(subset=['srid'], keep='first')
    
    print(f"Записей после удаления дублей: {len(df_srid_nm_unique):,}")
    print(f"Удалено дублей: {len(df_srid_nm) - len(df_srid_nm_unique):,}")
    
    return df_srid_nm_unique

def perform_merge():
    """
    Выполнение left merge между файлами
    """
    print("\n=== ЗАГРУЗКА ФАЙЛОВ ===")
    
    # Загружаем первый файл (расходы с nm_id = 0)
    df_expenses = pd.read_excel('ppvz_reward_nm_id_0.xlsx')
    print(f"Загружен файл расходов: {len(df_expenses):,} записей")
    
    # Загружаем и обрабатываем второй файл
    df_srid_nm, duplicates = analyze_duplicates_before_merge()
    df_srid_nm_unique = handle_duplicates_strategy(df_srid_nm, duplicates)
    
    print(f"\n=== ВЫПОЛНЕНИЕ LEFT MERGE ===")
    print(f"Записей в первом файле: {len(df_expenses):,}")
    print(f"Записей во втором файле (после удаления дублей): {len(df_srid_nm_unique):,}")
    
    # Выполняем left merge
    df_merged = df_expenses.merge(
        df_srid_nm_unique, 
        on='srid', 
        how='left',
        suffixes=('_original', '_new')
    )
    
    print(f"Записей после merge: {len(df_merged):,}")
    
    # Анализ результатов merge
    print(f"\n=== АНАЛИЗ РЕЗУЛЬТАТОВ MERGE ===")
    
    # Сколько записей получили новые nm_id
    matched_count = df_merged['nm_id_new'].notna().sum()
    unmatched_count = df_merged['nm_id_new'].isna().sum()
    
    print(f"Записей с найденными nm_id: {matched_count:,} ({matched_count/len(df_merged)*100:.1f}%)")
    print(f"Записей без найденных nm_id: {unmatched_count:,} ({unmatched_count/len(df_merged)*100:.1f}%)")
    
    # Показываем примеры
    print(f"\nПримеры успешных совпадений:")
    matched_examples = df_merged[df_merged['nm_id_new'].notna()][['srid', 'nm_id_original', 'nm_id_new', 'ppvz_reward']].head()
    print(matched_examples)
    
    print(f"\nПримеры неудачных совпадений:")
    unmatched_examples = df_merged[df_merged['nm_id_new'].isna()][['srid', 'nm_id_original', 'ppvz_reward']].head()
    print(unmatched_examples)
    
    return df_merged, matched_count, unmatched_count

def create_final_dataset(df_merged):
    """
    Создание финального датасета с обновленными nm_id
    """
    print(f"\n=== СОЗДАНИЕ ФИНАЛЬНОГО ДАТАСЕТА ===")
    
    # Создаем копию для финального датасета
    df_final = df_merged.copy()
    
    # Заменяем nm_id = 0 на новые значения где они найдены
    df_final['nm_id_final'] = df_final['nm_id_original']
    df_final.loc[df_final['nm_id_new'].notna(), 'nm_id_final'] = df_final.loc[df_final['nm_id_new'].notna(), 'nm_id_new']
    
    # Удаляем служебные колонки
    df_final = df_final.drop(['nm_id_original', 'nm_id_new'], axis=1)
    df_final = df_final.rename(columns={'nm_id_final': 'nm_id'})
    
    # Статистика по финальному датасету
    zero_nm_count = (df_final['nm_id'] == 0).sum()
    non_zero_nm_count = (df_final['nm_id'] != 0).sum()
    
    print(f"Финальный датасет:")
    print(f"  Всего записей: {len(df_final):,}")
    print(f"  Записей с nm_id = 0: {zero_nm_count:,} ({zero_nm_count/len(df_final)*100:.1f}%)")
    print(f"  Записей с nm_id != 0: {non_zero_nm_count:,} ({non_zero_nm_count/len(df_final)*100:.1f}%)")
    
    return df_final

def main():
    """
    Основная функция
    """
    print("=== MERGE NM_ID СКРИПТ ===")
    print("Задача: заменить nm_id = 0 на реальные номера номенклатур")
    
    try:
        # Выполняем merge
        df_merged, matched_count, unmatched_count = perform_merge()
        
        # Создаем финальный датасет
        df_final = create_final_dataset(df_merged)
        
        # Сохраняем результаты
        print(f"\n=== СОХРАНЕНИЕ РЕЗУЛЬТАТОВ ===")
        
        # Сохраняем полный результат merge
        df_merged.to_excel('merge_result_full.xlsx', index=False)
        print(f"✓ Полный результат merge сохранен в: merge_result_full.xlsx")
        
        # Сохраняем финальный датасет
        df_final.to_excel('expenses_with_real_nm_id.xlsx', index=False)
        print(f"✓ Финальный датасет сохранен в: expenses_with_real_nm_id.xlsx")
        
        # Сохраняем только успешно обновленные записи
        df_updated = df_final[df_final['nm_id'] != 0]
        if len(df_updated) > 0:
            df_updated.to_excel('expenses_updated_nm_id.xlsx', index=False)
            print(f"✓ Обновленные записи сохранены в: expenses_updated_nm_id.xlsx ({len(df_updated):,} записей)")
        
        # Сохраняем неудачные совпадения
        df_failed = df_final[df_final['nm_id'] == 0]
        if len(df_failed) > 0:
            df_failed.to_excel('expenses_failed_nm_id.xlsx', index=False)
            print(f"✓ Неудачные совпадения сохранены в: expenses_failed_nm_id.xlsx ({len(df_failed):,} записей)")
        
        print(f"\n=== ИТОГОВАЯ СТАТИСТИКА ===")
        print(f"Исходных записей: {len(df_merged):,}")
        print(f"Успешно обновлено: {matched_count:,} ({matched_count/len(df_merged)*100:.1f}%)")
        print(f"Не удалось обновить: {unmatched_count:,} ({unmatched_count/len(df_merged)*100:.1f}%)")
        
    except Exception as e:
        print(f"✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

