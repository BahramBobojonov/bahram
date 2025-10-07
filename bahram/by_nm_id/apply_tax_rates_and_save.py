#!/usr/bin/env python3

import os
import pandas as pd
from sqlalchemy import create_engine, text
import gspread


# DB connection (reuse pattern from existing scripts)
ENGINE = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

# Google Sheets
SHEET_KEY = "15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ"


def get_gs_client():
    """Authorize gspread using service account located at bahram/cred.json."""
    # cred.json расположен в каталоге bahram; текущий файл лежит в bahram/by_nm_id
    cred_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cred.json')
    return gspread.service_account(filename=cred_path)


def load_rates_dataframe():
    """Load VAT and tax rates per supplier (ИП) from Google Sheet.

    Expected columns: 'ИП', 'НДС', 'Налоговая ставка'. Empty/NULL VAT -> 0.
    Percent values like 20 or '20%' are converted to fractions (0.2).
    """
    gc = get_gs_client()
    worksheet = gc.open_by_key(SHEET_KEY).sheet1
    df = pd.DataFrame(worksheet.get_all_records())

    # Normalize column names expected in RU
    required_cols = ['Имя Юрлица', 'НДС', 'Налоговая ставка']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"В Google Sheet отсутствует столбец: {col}")

    df = df[['Имя Юрлица', 'НДС', 'Налоговая ставка']].copy()

    # Clean and convert to numeric
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
        # Convert percentage to fraction if looks like percent (e.g., 20 or 20.0)
        if num > 1.0:
            num = num / 100.0
        return num

    df['НДС'] = df['НДС'].apply(lambda x: to_fraction(x, default_zero=True))  # NULL -> 0
    df['Налоговая ставка'] = df['Налоговая ставка'].apply(lambda x: to_fraction(x, default_zero=False))

    # Fill missing tax rate with 0 if not provided
    df['Налоговая ставка'] = df['Налоговая ставка'].fillna(0.0)

    # Drop rows without supplier name
    df = df[df['Имя Юрлица'].astype(str).str.strip() != '']
    return df


def read_finance_sql() -> str:
    """Read base SQL from v_finance_summary_by_nmid.sql and return its text."""
    sql_path = os.path.join(os.path.dirname(__file__), 'v_finance_summary_by_nmid.sql')
    with open(sql_path, 'r', encoding='utf-8') as f:
        return f.read()


def read_result_sql() -> str:
    """Read result SQL from v_finance_summary_by_nmid_result.sql and return its text."""
    sql_path = os.path.join(os.path.dirname(__file__), 'v_finance_summary_by_nmid_result.sql')
    with open(sql_path, 'r', encoding='utf-8') as f:
        return f.read()


def ensure_target_table(create_select_sql: str) -> None:
    """Create target table reports.mv_detail_finance_reports_v1 based on select structure if it doesn't exist."""
    create_sql = text(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'reports' AND table_name = 'mv_detail_finance_reports_v1'
            ) THEN
                EXECUTE 'CREATE TABLE reports.mv_detail_finance_reports_v1 AS (' || $q${create_select_sql}$q$ || ') WITH NO DATA';
            END IF;
        END$$;
        """
    )
    with ENGINE.begin() as conn:
        conn.execute(create_sql)


def ensure_final_table(create_select_sql: str) -> None:
    """Create target table reports.detail_finance_reports_bu_nm_id based on select structure if it doesn't exist."""
    create_sql = text(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'reports' AND table_name = 'detail_finance_reports_bu_nm_id'
            ) THEN
                EXECUTE 'CREATE TABLE reports.detail_finance_reports_bu_nm_id AS (' || $q${create_select_sql}$q$ || ') WITH NO DATA';
            END IF;
        END$$;
        """
    )
    with ENGINE.begin() as conn:
        conn.execute(create_sql)


def main():
    base_sql = read_finance_sql()

    # Append supplier filter to the WHERE clause
    # Original contains: WHERE date_from::date >= '2025-08-25'
    supplier_filtered_sql = base_sql.replace(
        "WHERE date_from::date >= '2025-08-25'",
        "WHERE date_from::date >= '2025-08-25' AND supplier = :supplier"
    )

    # Prepare CREATE TABLE ... AS (select) WITH NO DATA
    # We must have a standalone SELECT; base_sql already starts with SELECT ... FROM ... ORDER BY ...
    # Remove ORDER BY for CTAS structure consistency
    select_for_create = supplier_filtered_sql.rsplit('ORDER BY', 1)[0].strip()
    # Replace bind params for CTAS so statement is self-contained
    select_for_create = (
        select_for_create
        .replace(':vat_rate', '0')
        .replace(':tax_rate', '0')
        .replace(':supplier', "''")
    )

    ensure_target_table(select_for_create)

    df_rates = load_rates_dataframe()

    insert_sql = text(
        f"""
        INSERT INTO reports.mv_detail_finance_reports_v1
        {supplier_filtered_sql}
        """
    )

    with ENGINE.begin() as conn:
        for _, row in df_rates.iterrows():
            supplier = str(row['Имя Юрлица']).strip()
            vat_rate = float(row['НДС']) if row['НДС'] is not None else 0.0
            tax_rate = float(row['Налоговая ставка']) if row['Налоговая ставка'] is not None else 0.0

            params = {
                'supplier': supplier,
                'vat_rate': vat_rate,
                'tax_rate': tax_rate,
            }
            conn.execute(insert_sql, params)

    # Stage 2: build final aggregated table from result SQL, filtered by supplier and parameterized rates
    result_sql = read_result_sql()

    # Add supplier filter: if there's already WHERE, append AND; otherwise add WHERE
    trimmed_result_sql = result_sql.strip().rstrip(';')
    if 'WHERE' in trimmed_result_sql.upper():
        supplier_filtered_result_sql = trimmed_result_sql + " AND a.supplier_name = :supplier"
    else:
        supplier_filtered_result_sql = trimmed_result_sql + " WHERE a.supplier_name = :supplier"

    # Prepare CTAS SELECT for the final table (no params, no ORDER BY, no supplier filter)
    # For CTAS we remove params and supplier binding to make it standalone
    select_for_final_create = trimmed_result_sql
    # Remove any ORDER BY if present
    if 'ORDER BY' in select_for_final_create.upper():
        select_for_final_create = select_for_final_create.rsplit('ORDER BY', 1)[0].strip()
    select_for_final_create = (
        select_for_final_create
        .replace(':vat_rate', '0')
        .replace(':tax_rate', '0')
        .replace(':supplier', "''")
    )

    ensure_final_table(select_for_final_create)

    insert_final_sql = text(
        f"""
        INSERT INTO reports.detail_finance_reports_bu_nm_id
        {supplier_filtered_result_sql}
        """
    )

    # Fill final table per supplier with respective rates
    with ENGINE.begin() as conn:
        for _, row in df_rates.iterrows():
            supplier = str(row['Имя Юрлица']).strip()
            vat_rate = float(row['НДС']) if row['НДС'] is not None else 0.0
            tax_rate = float(row['Налоговая ставка']) if row['Налоговая ставка'] is not None else 0.0

            params = {
                'supplier': supplier,
                'vat_rate': vat_rate,
                'tax_rate': tax_rate,
            }
            conn.execute(insert_final_sql, params)


if __name__ == "__main__":
    main()


