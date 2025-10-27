-- Цель

-- Объединить корректные суммы из UPD-документов (vw_upd_with_nm_id)
-- с дневной разбивкой продаж из финансовых отчетов (detail_finance_reports)
-- для получения достоверной дневной динамики продаж по каждому nm_id и отчету (realizationreport_id).

-- Проблема, которую решает

-- vw_upd_with_nm_id содержит точные суммы (amount_sum) и количество (quantity_sum),
-- но нет разбивки по дням.

-- detail_finance_reports содержит продажи по дням (sale_dt),
-- но суммы там искажены из-за особенностей отчетов Wildberries (сторно, логистика и т.п.).

-- Итоговые значения (SUM(amount_sum) и SUM(quantity_sales))
-- по отчету совпадают между источниками, что позволяет использовать sum_per_order
-- из UPD как достоверную цену за единицу и корректно распределять суммы по дням.

-- для проверки количества
-- потом нужно будет настроить алерт если diff <> 0 

-- скрпипт для проверки количества
WITH upd AS (
    SELECT 
        redemption_number,
        nm_id,
        date,
        SUM(quantity_sum) AS total_quantity_upd
    FROM reports.vw_upd_with_nm_id
    WHERE date>= '2025-03-01'
    --redemption_number = '480331732'
    GROUP BY 1,2,3
),
fin AS (
    SELECT 
        realizationreport_id::text AS redemption_number,  -- <- привели к тексту
        nm_id,
        date_from::date,
        SUM(
            CASE
                WHEN doc_type_name = 'Продажа'
                     AND supplier_oper_name = 'Продажа'
                THEN quantity::numeric
                ELSE 0
            END
        ) AS total_quantity_fin
    FROM reports.detail_finance_reports
    WHERE report_type = 2
    AND date_from::date>='2025-03-01'
      --AND realizationreport_id = 480331732  -- <- числовое сравнение, без кавычек
    GROUP BY 1,2,3
)
SELECT 
    COALESCE(u.redemption_number, f.redemption_number) AS redemption_number,
    COALESCE(u.nm_id, f.nm_id) AS nm_id,
    COALESCE(u.date, f.date_from) AS date_from,
    u.total_quantity_upd,
    f.total_quantity_fin,
    (COALESCE(u.total_quantity_upd,0) - COALESCE(f.total_quantity_fin,0)) AS diff
FROM upd u
FULL JOIN fin f
    ON u.nm_id = f.nm_id
   AND u.redemption_number = f.redemption_number
ORDER BY nm_id;

-- скрипт для создания вюшки с разбивкой по дням

CREATE OR REPLACE VIEW reports.vw_vikupi_sales_by_day AS
WITH upd AS (
    SELECT 
        nm_id,
        redemption_number,
        SUM(quantity_sum) AS total_quantity,
        SUM(amount_sum) AS total_amount,
        SUM(amount_sum) / NULLIF(SUM(quantity_sum), 0) AS sum_per_order
    FROM reports.vw_upd_with_nm_id
    WHERE date >= '2025-03-01'
    GROUP BY 1,2
),
sales_by_day AS (
    SELECT 
        sale_dt::date AS sale_date,
        nm_id,
        realizationreport_id::text AS redemption_number,
        date_from::date AS date_from,
        date_to::date AS date_to,
        supplier,
        SUM(
            CASE
                WHEN doc_type_name = 'Продажа'
                     AND supplier_oper_name = 'Продажа'
                THEN quantity::numeric
                ELSE 0
            END
        ) AS quantity_sales
    FROM reports.detail_finance_reports
    WHERE report_type = 2
      AND date_from::date >= '2025-03-01'
    GROUP BY 1,2,3,4,5,6
)
SELECT 
    s.sale_date,
    s.date_from,
    s.date_to,
    s.supplier,
    s.nm_id,
    s.redemption_number,
    s.quantity_sales,
    u.sum_per_order,
    ROUND(s.quantity_sales * u.sum_per_order, 2) AS amount_day
FROM sales_by_day s
LEFT JOIN upd u
    ON s.nm_id = u.nm_id
   AND s.redemption_number = u.redemption_number;

