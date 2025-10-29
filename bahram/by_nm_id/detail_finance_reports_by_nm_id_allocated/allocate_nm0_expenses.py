#!/usr/bin/env python3
"""
Распределение расходов по строкам с nm_id = 0 пропорционально дневной выручке
для каждой пары (realizationreport_id, supplier) и дня rr_dt.

Источник: reports.detail_finance_reports_by_nm_id
Результат: reports.detail_finance_reports_by_nm_id_allocated

Логика:
- Для каждой группы (supplier, realizationreport_id, rr_dt):
  - Считаем суммы по расходным колонкам у nm_id = 0 (нераспределённые)
  - Считаем дневную выручку по номенклатурам с revenue > 0 (по умолчанию net_retail_amount)
  - Если сумма выручки > 0: распределяем суммы nm_id=0 пропорционально доле выручки
    и прибавляем к строкам nm_id > 0. В строке nm_id = 0 делаем *_after = 0
  - Иначе: оставляем все как есть

Также создаются колонки <name>_before и <name>_after для каждой распределяемой
расходной колонки. Исходные значения не изменяются.
"""

import os
from datetime import datetime
from typing import List

import pandas as pd
from sqlalchemy import create_engine, text


# Подключение к PostgreSQL (как в execute_finance_reports_with_rates.py)
ENGINE = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')


def read_source_table() -> pd.DataFrame:
    query = """
        SELECT *
        FROM reports.detail_finance_reports_by_nm_id
    """
    with ENGINE.connect() as conn:
        df = pd.read_sql(text(query), conn)
    return df


def get_expense_columns(candidate_columns: List[str]) -> List[str]:
    """
    Фиксированный список расходных колонок, подлежащих распределению.
    Пересекаем с фактически доступными в таблице.
    """
    known_expense_cols = [
        'storage_fee_total',
        'total_acceptance',
        'deduction_adv_total',
        'deduction_writeoff_total',
        'logistics_total',
        'logistics_total_without_storno',
        'storno_logistics_total',
        'penalties_total',
        'additional_payment_total',
        'storage_recalculation_total',
        'storage_correction_total',
        'acceptance_recalculation_total',
        'deduction_other_total',
        'acquiring_fee',
        'rebill_logistic_cost',
        'cashback_discount',
        'additional_payment_correction',
        'ppvz_reward',
    ]
    present = [c for c in known_expense_cols if c in candidate_columns]
    return present


def ensure_numeric(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    for c in columns:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df


def allocate_expenses(df: pd.DataFrame,
                      revenue_col: str = 'net_retail_amount',
                      nm_id_col: str = 'nm_id',
                      supplier_col: str = 'supplier_name',
                      report_col: str = 'realizationreport_id',
                      date_col: str = 'rr_dt') -> pd.DataFrame:
    if supplier_col not in df.columns and 'supplier' in df.columns:
        df = df.rename(columns={'supplier': supplier_col})

    # Список распределяемых колонок
    expense_cols = get_expense_columns(df.columns.tolist())

    # Если нет ни одной колонки для распределения — возвращаем как есть
    if not expense_cols:
        return df.copy()

    # Создаём только *_after на базе исходных значений
    for col in expense_cols:
        df[f'{col}_after'] = pd.to_numeric(df[col], errors='coerce')

    # Безопасные типы
    numeric_cols = expense_cols + [f'{c}_after' for c in expense_cols] + [revenue_col]
    df = ensure_numeric(df, [c for c in numeric_cols if c in df.columns])

    # Обязательные ключи
    key_cols = [supplier_col, report_col, date_col]
    for k in [supplier_col, report_col]:
        if k not in df.columns:
            raise ValueError(f'Нет обязательной колонки для группировки: {k}')

    # Подготовим флаги и суммы по группам
    df['_is_nm0'] = (df[nm_id_col].fillna(0).astype('int64') == 0)
    df['_rev_pos'] = df[revenue_col].fillna(0).clip(lower=0)

    # 1) Суммы расходов nm_id=0 по всему отчёту (supplier, report) — без привязки к дате
    report_key = [supplier_col, report_col]
    nm0_sum_report = (
        df[df['_is_nm0']]
        .groupby(report_key)[expense_cols]
        .sum()
        .rename(columns={c: f'{c}__nm0_sum_report' for c in expense_cols})
    )

    # 2) Сумма положительной выручки по всему отчёту среди nm_id>0 (для долей)
    rev_sum_report = (
        df[~df['_is_nm0']]
        .groupby(report_key)['_rev_pos']
        .sum()
        .rename('rev_pos_sum_report')
    )

    # Присоединяем агрегаты к каждой строке отчёта
    df = df.merge(nm0_sum_report, on=report_key, how='left')
    df = df.merge(rev_sum_report, on=report_key, how='left')

    # Заполняем NaN нулями
    for c in [f'{col}__nm0_sum_report' for col in expense_cols]:
        if c in df.columns:
            df[c] = df[c].fillna(0)
    df['rev_pos_sum_report'] = df['rev_pos_sum_report'].fillna(0)

    # Распределение: каждая строка nm_id>0 получает долю total_nm0_report * (row_rev_pos / rev_pos_sum_report)
    can_allocate_mask = (~df['_is_nm0']) & (df['rev_pos_sum_report'] > 0)
    row_share_report = pd.Series(0.0, index=df.index)
    row_share_report.loc[can_allocate_mask] = (df.loc[can_allocate_mask, '_rev_pos'] / df.loc[can_allocate_mask, 'rev_pos_sum_report']).fillna(0)

    for col in expense_cols:
        total_nm0_report_col = f'{col}__nm0_sum_report'
        add_amount = row_share_report * df[total_nm0_report_col]
        df.loc[can_allocate_mask, f'{col}_after'] = (df.loc[can_allocate_mask, f'{col}_after'] + add_amount.loc[can_allocate_mask])
        # В строках nm_id=0 зануляем после распределения, если в отчёте есть положительная выручка
        zero_mask = df['_is_nm0'] & (df['rev_pos_sum_report'] > 0)
        df.loc[zero_mask, f'{col}_after'] = 0

    # Удалим служебные столбцы
    # Удалим служебные и исходные расходные столбцы (оставляем только *_after)
    drop_cols = ['_is_nm0', '_rev_pos'] + [f'{c}__nm0_sum_report' for c in expense_cols] + ['rev_pos_sum_report'] + expense_cols
    df = df.drop(columns=[c for c in drop_cols if c in df.columns])

    return df


def compute_total_to_transfer_after(df: pd.DataFrame) -> pd.DataFrame:
    """
    Пересчитать total_to_transfer_after по формуле из v_finance_summary_by_nmid_result.sql,
    используя *_after колонки. to_transfer_for_goods остаётся исходным.

    total_to_transfer_after =
        to_transfer_for_goods
        - logistics_total_after
        - penalties_total_after
        - additional_payment_total_after
        - storage_fee_total_after
        - total_acceptance_after
        - deduction_adv_total_after
        - deduction_writeoff_total_after
        - deduction_other_total_after
        - additional_payment_correction_after
    """
    # не сохраняем before-колонки

    # гарантируем числовые типы
    numeric_needed = [
        'to_transfer_for_goods',
        'logistics_total_after',
        'penalties_total_after',
        'additional_payment_total_after',
        'storage_fee_total_after',
        'total_acceptance_after',
        'deduction_adv_total_after',
        'deduction_writeoff_total_after',
        'deduction_other_total_after',
        'additional_payment_correction_after',
    ]
    for c in numeric_needed + ['to_transfer_for_goods']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')

    def v(col: str) -> pd.Series:
        return df[col] if col in df.columns else 0

    df['total_to_transfer_after'] = (
        pd.to_numeric(df.get('to_transfer_for_goods', 0), errors='coerce').fillna(0)
        - v('logistics_total_after').fillna(0)
        - v('penalties_total_after').fillna(0)
        - v('additional_payment_total_after').fillna(0)
        - v('storage_fee_total_after').fillna(0)
        - v('total_acceptance_after').fillna(0)
        - v('deduction_adv_total_after').fillna(0)
        - v('deduction_writeoff_total_after').fillna(0)
        - v('deduction_other_total_after').fillna(0)
        - v('additional_payment_correction_after').fillna(0)
    )

    return df


def finalize_schema_with_after(df: pd.DataFrame) -> pd.DataFrame:
    """
    Приводит результат к исходной схеме:
    - Для всех известных расходных колонок, если есть `<col>_after`,
      создаёт/заменяет колонку `<col>` значениями из `<col>_after`.
    - Удаляет колонки `*_after`.
    - Если есть `total_to_transfer_after`, переименовывает в `total_to_transfer`.
    """
    expense_cols_all = [
        'storage_fee_total','total_acceptance','deduction_adv_total','deduction_writeoff_total',
        'logistics_total','logistics_total_without_storno','storno_logistics_total','penalties_total',
        'additional_payment_total','storage_recalculation_total','storage_correction_total',
        'acceptance_recalculation_total','deduction_other_total','acquiring_fee','rebill_logistic_cost',
        'cashback_discount','additional_payment_correction','ppvz_reward'
    ]

    df_out = df.copy()

    for col in expense_cols_all:
        after_col = f'{col}_after'
        if after_col in df_out.columns:
            df_out[col] = pd.to_numeric(df_out[after_col], errors='coerce')

    # Переименование total_to_transfer_after -> total_to_transfer
    if 'total_to_transfer_after' in df_out.columns:
        df_out['total_to_transfer'] = pd.to_numeric(df_out['total_to_transfer_after'], errors='coerce')

    # Удаляем все *_after
    after_cols_present = [c for c in df_out.columns if c.endswith('_after')]
    df_out = df_out.drop(columns=after_cols_present)

    return df_out


def save_to_db(df: pd.DataFrame, table: str = 'detail_finance_reports_by_nm_id_allocated', schema: str = 'reports') -> None:
    # Приводим имена столбцов к нижнему регистру для совместимости
    df_to_save = df.copy()
    df_to_save.columns = [str(c) for c in df_to_save.columns]
    with ENGINE.connect() as conn:
        df_to_save.to_sql(name=table, con=conn, schema=schema, if_exists='replace', index=False, method='multi', chunksize=1000)


def save_to_excel(df: pd.DataFrame, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = os.path.join(out_dir, f'allocated_preview_{ts}.xlsx')

    # Вкладка 1: детальные строки, вкладка 2: сверка по поставщику и отчёту
    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        # Выгружаем итоговую схему (после finalize)
        df.to_excel(writer, index=False, sheet_name='detail')

        supplier_col = 'supplier_name' if 'supplier_name' in df.columns else ('supplier' if 'supplier' in df.columns else 'supplier_name')
        group_cols = [supplier_col, 'realizationreport_id'] if 'realizationreport_id' in df.columns else [supplier_col]

        # Суммируем ключевые расходы и total_to_transfer в финальной схеме
        expense_cols_for_sum = [
            'storage_fee_total','total_acceptance','deduction_adv_total','deduction_writeoff_total',
            'logistics_total','logistics_total_without_storno','storno_logistics_total','penalties_total',
            'additional_payment_total','storage_recalculation_total','storage_correction_total',
            'acceptance_recalculation_total','deduction_other_total','acquiring_fee','rebill_logistic_cost',
            'cashback_discount','additional_payment_correction','ppvz_reward','total_to_transfer'
        ]
        cols_to_sum = [c for c in expense_cols_for_sum if c in df.columns]
        summary = df.groupby(group_cols, dropna=False)[cols_to_sum].sum(min_count=1).reset_index()

        summary.to_excel(writer, index=False, sheet_name='reconciliation')

    return out_path


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    print('Чтение исходной таблицы...')
    src = read_source_table()

    # Явно приводим идентификаторы
    id_like_cols = ['nm_id', 'realizationreport_id']
    for c in id_like_cols:
        if c in src.columns:
            src[c] = pd.to_numeric(src[c], errors='ignore')

    print('Распределение расходов...')
    allocated = allocate_expenses(src, revenue_col='net_retail_amount')
    print('Пересчёт total_to_transfer_after...')
    allocated = compute_total_to_transfer_after(allocated)

    print('Приведение схемы к исходной (замена *_after -> оригинальные имена)...')
    allocated = finalize_schema_with_after(allocated)

    print('Запись результата в БД...')
    save_to_db(allocated)

    print('Экспорт в Excel для проверки...')
    xlsx_path = save_to_excel(allocated, base_dir)
    print(f'Excel сохранён: {xlsx_path}')


if __name__ == '__main__':
    main()


