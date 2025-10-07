CREATE OR REPLACE VIEW reports.v_acceptance_by_nm_id AS
WITH
latest_acceptance AS (
    SELECT *
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY supplier, shkcreatedate, incomeid, nmid, gicreatedate
                   ORDER BY update_time DESC
               ) AS rn
        FROM reports.acceptance
    ) t
    WHERE rn = 1
),
dfr_agg AS (
    SELECT supplier, date_from::date, date_to::date, MIN(realizationreport_id) AS realizationreport_id
    FROM reports.detail_finance_reports
    WHERE report_type = 1
    GROUP BY supplier, date_from::date, date_to::date
),
detail_agg AS (
    SELECT
        supplier,
        rr_dt::date,
        nm_id,
        date_from::date,
        date_to::date,
        SUM(acceptance) AS total_acceptance,
        MIN(realizationreport_id) AS realizationreport_id
    FROM reports.detail_finance_reports
    WHERE acceptance <> 0
      AND nm_id <> 0
    GROUP BY supplier, rr_dt, nm_id, date_from, date_to
),
acceptance_agg AS (
    SELECT
        la.supplier,
        la.shkcreatedate::date AS rr_dt,
        la.nmid AS nm_id,  -- привели к единому имени
        date_trunc('week', la.shkcreatedate::date)::date AS date_from,
        (date_trunc('week', la.shkcreatedate::date) + interval '6 days')::date AS date_to,
        SUM(COALESCE(NULLIF(la.total::text, 'NaN')::numeric, 0)) AS total_acceptance,
        dfr_agg.realizationreport_id
    FROM latest_acceptance la
    JOIN dfr_agg
      ON la.supplier = dfr_agg.supplier
     AND date_trunc('week', la.shkcreatedate::date)::date = dfr_agg.date_from
     AND (date_trunc('week', la.shkcreatedate::date) + interval '6 days')::date = dfr_agg.date_to
    WHERE la.shkcreatedate::date >= DATE '2025-08-01'
    GROUP BY la.supplier, rr_dt, la.nmid, date_from, date_to, dfr_agg.realizationreport_id
)
SELECT * FROM detail_agg
UNION ALL
SELECT * FROM acceptance_agg
ORDER BY supplier, date_from;


-- CREATE OR REPLACE VIEW reports.v_acceptance_by_nm_id AS
-- WITH
-- -- 1. Платная приемка (агрегируем сразу по nmid + supplier + report_date)
-- cte_acceptance AS (
--     SELECT
--         a.nmid,
--         a.supplier,
--         a.shkcreatedate::date AS report_date,
--         SUM(COALESCE(NULLIF(a.total::text, 'NaN')::numeric, 0)) AS total_acceptance
--     FROM reports.acceptance a
--     WHERE a.shkcreatedate::date >= DATE '2025-08-01'
--     GROUP BY a.nmid, a.supplier, a.shkcreatedate::date
-- ),

-- -- 2. FBS корректировки (report_date берется из dfr.sale_dt)
-- cte_corrected_fbs AS (
--     SELECT
--         fi.nmid,
--         dfr.supplier,
--         dfr.date_from::date AS report_date,
--         SUM(COALESCE(NULLIF(fi.scanprice::text, 'NaN')::numeric, 0)) AS total_fbs_correction
--     FROM reports.detail_finance_reports dfr
--     JOIN supplies.fbs_incomes fi
--         ON dfr.srid = fi.rid
--     WHERE dfr.acceptance != 0
--     GROUP BY fi.nmid, dfr.supplier, dfr.date_from::date
-- ),
-- -- 3. Объединяем источники
-- cte_union AS (
--     SELECT
--         nmid,
--         supplier,
--         report_date,
--         total_acceptance,
--         0::numeric AS total_fbs_correction
--     FROM cte_acceptance
--     UNION ALL
--     SELECT
--         nmid,
--         supplier,
--         report_date,
--         0::numeric AS total_acceptance,
--         total_fbs_correction
--     FROM cte_corrected_fbs
-- ),

-- -- 4. Финальный расчет по каждой строке
-- cte_total AS (
--     SELECT
--         nmid,
--         supplier,
--         report_date,
--         SUM(total_acceptance) AS total_acceptance,
--         SUM(total_fbs_correction) AS total_fbs_correction,
--         SUM(total_acceptance) + SUM(total_fbs_correction) AS total_combined,
--         CASE
--             WHEN SUM(total_acceptance) <> 0 AND SUM(total_fbs_correction) = 0 THEN 'ФБО или корректировка платной приемки'
--             WHEN SUM(total_acceptance) = 0 AND SUM(total_fbs_correction) <> 0 THEN 'ФБС платная приемка'
--             WHEN SUM(total_acceptance) <> 0 AND SUM(total_fbs_correction) <> 0 THEN 'ФБС и ФБО платная приемка'
--             ELSE 'Нет данных по платной приемке'
--         END AS source_type
--     FROM cte_union
--     GROUP BY nmid, supplier, report_date
-- )

-- SELECT *
-- FROM cte_total;




-- -- БЛОК для проверки агрегированных сумм
-- WITH summary_agg AS (
--     SELECT 
--         afr.realizationreport_id,
--         afr.supplier_name,
--         afr.date_from::date AS date_from,
--         afr.date_to::date AS date_to,
--         SUM(v.total_combined) AS total_by_nmid
--     FROM reports.aggregated_finance_report afr
--     JOIN reports.v_acceptance_fbs_summary v
--       ON afr.supplier_name = v.supplier
--      AND v.report_date::date BETWEEN afr.date_from::date AND afr.date_to::date
--     WHERE afr.acceptance_total IS NOT NULL
--       AND afr.acceptance_total != 0
--     GROUP BY afr.realizationreport_id, afr.supplier_name, afr.date_from::date, afr.date_to::date
-- )
-- SELECT 
--     afr.supplier_name,
--     afr.realizationreport_id,
--     afr.report_date::date AS report_date,
--     afr.date_from::date AS date_from,
--     afr.date_to::date AS date_to,
--     afr.acceptance_total,
--     COALESCE(sa.total_by_nmid, 0) AS sum_by_nmid,
--     afr.acceptance_total - COALESCE(sa.total_by_nmid, 0) AS diff
-- FROM reports.aggregated_finance_report afr
-- LEFT JOIN summary_agg sa
--     ON afr.realizationreport_id = sa.realizationreport_id
-- ORDER BY afr.supplier_name, afr.report_date