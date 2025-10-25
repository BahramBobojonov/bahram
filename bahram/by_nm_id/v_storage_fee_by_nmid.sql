-- ============================================================================
-- ФИНАЛЬНЫЙ SQL: Разбивка storage_fee по номенклатурам (nm_id)
-- ============================================================================
CREATE OR REPLACE VIEW reports.v_storage_fee_by_nmid AS 
SELECT * FROM reports.v_storage_fee_by_nmid_step_0
UNION ALL
SELECT
        sale_dt::date AS date,
        supplier,
        nm_id AS nmid,
        date_from::date,
        date_to::date,
        SUM(storage_fee::numeric) AS total_warehouseprice,
        realizationreport_id
    FROM reports.detail_finance_reports
    WHERE storage_fee::numeric <> 0
      AND nm_id <> 0
     AND date_from::date>='2025-03-01'
    AND  report_type = 1
    GROUP BY 1,2,3,4,5,7


    CREATE OR REPLACE VIEW reports.v_storage_fee_by_nmid_step_0 AS
WITH storage_weekly AS (
    SELECT
        date::date,
        supplier,
        NMID,
        date_trunc('week', date::timestamp)::date AS date_from,
        (date_trunc('week', date::timestamp)::date + INTERVAL '6 days')::date AS date_to,
        SUM(warehouseprice) AS total_warehouseprice
    FROM reports.paid_storage
    GROUP BY 1, 2, 3, 4
),
finance_reports AS (
    SELECT
        supplier,
        date_from::date AS date_from,
        date_to::date AS date_to,
        MIN(realizationreport_id) AS realizationreport_id
    FROM reports.detail_finance_reports
    WHERE report_type = 1
    GROUP BY supplier, date_from::date, date_to::date
)
SELECT
    s.date,
    s.supplier,
    s.NMID,
    s.date_from,
    s.date_to,
    s.total_warehouseprice,
    f.realizationreport_id
FROM storage_weekly s
LEFT JOIN finance_reports f
    ON LOWER(COALESCE(s.supplier, '')) = LOWER(COALESCE(f.supplier, ''))
    AND s.date_from = f.date_from
    AND s.date_to = f.date_to;









-- ============================================================================
-- CREATE OR REPLACE VIEW reports.v_storage_fee_by_nmid AS
-- WITH storage_weekly AS (
--     SELECT
--         date::date,
--         supplier,
--         NMID,
--         date_trunc('week', date::timestamp)::date AS date_from,
--         (date_trunc('week', date::timestamp)::date + INTERVAL '6 days')::date AS date_to,
--         SUM(warehouseprice) AS total_warehouseprice
--     FROM reports.paid_storage
--     GROUP BY 1, 2, 3, 4
-- ),
-- finance_reports AS (
--     SELECT
--         supplier,
--         date_from::date AS date_from,
--         date_to::date AS date_to,
--         MIN(realizationreport_id) AS realizationreport_id
--     FROM reports.detail_finance_reports
--     WHERE report_type = 1
--     GROUP BY supplier, date_from::date, date_to::date
-- )
-- SELECT
--     s.date,
--     s.supplier,
--     s.NMID,
--     s.date_from,
--     s.date_to,
--     s.total_warehouseprice,
--     f.realizationreport_id
-- FROM storage_weekly s
-- LEFT JOIN finance_reports f
--     ON LOWER(COALESCE(s.supplier, '')) = LOWER(COALESCE(f.supplier, ''))
--     AND s.date_from = f.date_from
--     AND s.date_to = f.date_to;
-- CREATE OR REPLACE VIEW reports.v_storage_fee_by_nmid AS
-- WITH latest_ps AS (
--     SELECT *
--     FROM (
--         SELECT *,
--                ROW_NUMBER() OVER (
--                    PARTITION BY supplier, date, giid, chrtid, barcode, nmid, warehouse, officeid, calctype
--                    ORDER BY update_time DESC
--                ) AS rn
--         FROM reports.paid_storage
--     ) t
--     WHERE rn = 1
-- ),
-- dfr_agg AS (
--     SELECT supplier, date_from::date, date_to::date, MIN(realizationreport_id) AS realizationreport_id
--     FROM reports.detail_finance_reports
--     WHERE report_type = 1
--     GROUP BY supplier, date_from::date, date_to::date
-- )
-- SELECT
--     ps.date,
--     ps.nmid,
--     ps.supplier,
--     date_trunc('week', ps.date)::date AS date_from,
--     (date_trunc('week', ps.date) + interval '6 days')::date AS date_to,
--     SUM(ps.warehouseprice) AS storage_fee_total,
--     dfr_agg.realizationreport_id
-- FROM latest_ps ps
-- JOIN dfr_agg
--     ON ps.supplier = dfr_agg.supplier
--     AND date_trunc('week', ps.date)::date = dfr_agg.date_from
--     AND (date_trunc('week', ps.date) + interval '6 days')::date = dfr_agg.date_to
-- WHERE ps.date::date >= '2025-08-25'
-- GROUP BY ps.date, ps.nmid, ps.supplier, date_from, date_to, dfr_agg.realizationreport_id;


-- CREATE OR REPLACE VIEW reports.v_storage_fee_by_nmid AS
-- WITH aggregated_periods AS (
--     -- Берём уникальные периоды (БЕЗ realizationreport_id чтобы избежать дублей)
--     SELECT DISTINCT
--         supplier_name,
--         date_from::date AS period_start,
--         date_to::date AS period_end
--     FROM reports.aggregated_finance_report
--     WHERE storage_fee_total != 0
--         AND report_date >= '2025-09-01'  -- ← Можно изменить период
-- ),

-- storage_by_nmid AS (
--     -- Разбивка по nm_id для каждого периода
--     SELECT 
--         ap.supplier_name,
--         ap.period_start,
--         ap.period_end,
        
--         ps.nmid AS nm_id,
--         MAX(ps.chrtid) AS chrtid,  -- Берём любое значение (они одинаковые для nmid)
--         MAX(ps.barcode) AS barcode,
        
--         -- Статистика по номенклатуре
--         COUNT(DISTINCT ps.date::date) AS days_stored,
--         COUNT(DISTINCT ps.officeid) AS warehouses_count,
--         COUNT(DISTINCT ps.calctype) AS calc_types_count,
        
--         -- Стоимость хранения
--         SUM(COALESCE(ps.warehouseprice, 0)) AS storage_fee_by_nmid,
--         AVG(COALESCE(ps.warehouseprice, 0)) AS avg_daily_fee,
--         MIN(ps.date::date) AS first_storage_date,
--         MAX(ps.date::date) AS last_storage_date,
        
--         -- Детали тарификации
--         STRING_AGG(DISTINCT ps.warehouse, ', ') AS warehouses,
--         STRING_AGG(DISTINCT ps.calctype, '; ') AS calc_types
        
--     FROM aggregated_periods ap
--     INNER JOIN reports.paid_storage ps
--         ON ap.supplier_name = ps.supplier
--         AND ps.date::date >= ap.period_start
--         AND ps.date::date <= ap.period_end
--     WHERE ps.warehouseprice IS NOT NULL
--     GROUP BY 
--         ap.supplier_name,
--         ap.period_start,
--         ap.period_end,
--         ps.nmid
-- )

-- -- ФИНАЛЬНЫЙ РЕЗУЛЬТАТ
-- SELECT 
--     supplier_name AS Поставщик,
--     period_start AS Период_начало,
--     period_end AS Период_конец,
    
--     nm_id AS Номенклатура,
--     chrtid AS ID_характеристики,
--     barcode AS Штрих_код,
    
--     ROUND(storage_fee_by_nmid::numeric, 2) AS Стоимость_хранения,
--     days_stored AS Дней_хранения,
--     ROUND(avg_daily_fee::numeric, 2) AS Средняя_стоимость_день,
    
--     warehouses_count AS Количество_складов,
--     calc_types_count AS Количество_тарифов,
    
--     warehouses AS Склады,
--     calc_types AS Типы_тарификации,
    
--     first_storage_date AS Первая_дата,
--     last_storage_date AS Последняя_дата

-- FROM storage_by_nmid
-- ORDER BY 
--     supplier_name, 
--     period_start, 
--     storage_fee_by_nmid DESC;


-- ============================================================================
-- ДОПОЛНИТЕЛЬНЫЙ ЗАПРОС: Итоги по периодам для сверки
-- ============================================================================

-- Раскомментируйте для проверки общих сумм:
/*
WITH aggregated_periods AS (
    SELECT 
        supplier_name,
        date_from::date AS period_start,
        date_to::date AS period_end,
        realizationreport_id,
        SUM(storage_fee_total) AS total_from_aggregated
    FROM reports.aggregated_finance_report
    WHERE storage_fee_total != 0 AND report_date >= '2025-09-01'
    GROUP BY supplier_name, date_from, date_to, realizationreport_id
),
storage_by_period AS (
    SELECT 
        ap.supplier_name,
        ap.period_start,
        ap.period_end,
        ap.realizationreport_id,
        ap.total_from_aggregated,
        SUM(COALESCE(ps.warehouseprice, 0)) AS total_from_paid_storage,
        COUNT(DISTINCT ps.nmid) AS unique_nm_count
    FROM aggregated_periods ap
    LEFT JOIN reports.paid_storage ps
        ON ap.supplier_name = ps.supplier
        AND ps.date::date >= ap.period_start
        AND ps.date::date <= ap.period_end
    WHERE ps.warehouseprice IS NOT NULL
    GROUP BY 
        ap.supplier_name,
        ap.period_start,
        ap.period_end,
        ap.realizationreport_id,
        ap.total_from_aggregated
)
SELECT 
    supplier_name,
    period_start,
    period_end,
    realizationreport_id,
    unique_nm_count AS Количество_номенклатур,
    ROUND(total_from_aggregated::numeric, 2) AS Сумма_aggregated,
    ROUND(total_from_paid_storage::numeric, 2) AS Сумма_по_nm_id,
    ROUND((total_from_aggregated - total_from_paid_storage)::numeric, 2) AS Разница,
    CASE 
        WHEN ABS(total_from_aggregated - total_from_paid_storage) < 0.01 THEN 'СОВПАДАЕТ ✓'
        WHEN ABS(total_from_aggregated - total_from_paid_storage) < 1 THEN 'Округление'
        ELSE 'Проверить ⚠'
    END AS Статус
FROM storage_by_period
ORDER BY supplier_name, period_start;
*/


-- ============================================================================
-- ПРИМЕР ИСПОЛЬЗОВАНИЯ В PYTHON
-- ============================================================================
/*
import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine('postgresql://user:pass@host:port/dbname')

# Читаем SQL из файла
with open('storage_fee_by_nmid.sql', 'r', encoding='utf-8') as f:
    query = f.read().split('-- ДОПОЛНИТЕЛЬНЫЙ ЗАПРОС')[0]  # Берём только основной запрос

# Выполняем запрос
df = pd.read_sql(text(query), engine)

# Сохраняем в Excel
df.to_excel('storage_fee_by_nmid.xlsx', index=False)
print(f"Получено {len(df)} записей по {df['Номенклатура'].nunique()} номенклатурам")
*/

