
CREATE OR REPLACE VIEW reports.v_deduction_by_nm_id AS 
-- Первый запрос: COUNT(*) = 1
SELECT 
    r.realizationreport_id,
    r.date_from,
    r.date_to,
    r.sale_dt,
    r.supplier,
    r.deduction::numeric AS deduction,
    u.company,
    u.cost::numeric AS cost,
    u.cnt AS upd_count,
    u.upd_number,
    a.updsum,
    a.updtime::date AS updtime,
    a.advertid,
    awn.nm_ids,
    awn.nm_count,
    TRIM(awn.nm_id) AS nm_id,
    CASE 
        WHEN awn.nm_count > 0 THEN a.updsum::numeric / awn.nm_count
        ELSE a.updsum::numeric
    END AS updsum_per_item
FROM reports.detail_finance_reports r
LEFT JOIN (
    SELECT 
        company,
        cost::numeric,
        COUNT(*) AS cnt,
        MIN(upd_number) AS upd_number
    FROM documents.upd_items
    WHERE report_type = 'upd'
      AND LOWER(COALESCE(item_name, '')) LIKE '%продвижение%'
      AND LOWER(COALESCE(item_name, '')) LIKE '%оказание услуг%'
    GROUP BY company, cost
    HAVING COUNT(*) = 1
) u 
    ON LOWER(COALESCE(r.supplier, '')) = LOWER(COALESCE(u.company, ''))
    AND ABS(r.deduction::numeric - u.cost::numeric) < 0.01
LEFT JOIN analytics.adv_upd a
    ON a.updnum::text = u.upd_number::text
    AND LOWER(COALESCE(a.supplier, '')) = LOWER(COALESCE(u.company, ''))
    AND a.paymenttype = 'Баланс'
LEFT JOIN (
    SELECT 
        advertid, 
        nm_ids,
        array_length(string_to_array(nm_ids, ','), 1) AS nm_count,
        unnest(string_to_array(nm_ids, ',')) AS nm_id
    FROM (
        SELECT DISTINCT advertid, nm_ids 
        FROM analytics.adv_upd_with_nm_id
    ) t
) awn
    ON awn.advertid = a.advertid
WHERE LOWER(COALESCE(r.bonus_type_name, '')) LIKE '%продвижение%'
  AND LOWER(COALESCE(r.bonus_type_name, '')) LIKE '%оказание услуг%'
  AND r.date_from::date >= DATE '2025-03-01'

UNION ALL

-- Второй запрос: COUNT(*) > 1
SELECT 
    r.realizationreport_id,
    r.date_from,
    r.date_to,
    r.sale_dt,
    r.supplier,
    r.deduction::numeric AS deduction,
    u.company,
    u.cost::numeric AS cost,
    NULL::integer AS upd_count,
    u.upd_number,
    a.updsum,
    a.updtime::date AS updtime,
    a.advertid,
    awn.nm_ids,
    awn.nm_count,
    TRIM(awn.nm_id) AS nm_id,
    CASE 
        WHEN awn.nm_count > 0 THEN a.updsum::numeric / awn.nm_count
        ELSE a.updsum::numeric
    END AS updsum_per_item
FROM reports.detail_finance_reports r
JOIN LATERAL (
    SELECT 
        di.upd_number,
        di.company,
        di.cost::numeric
    FROM documents.upd_items di
    INNER JOIN (
        SELECT 
            company,
            cost::numeric
        FROM documents.upd_items
        WHERE report_type = 'upd'
          AND LOWER(COALESCE(item_name, '')) LIKE '%продвижение%'
          AND LOWER(COALESCE(item_name, '')) LIKE '%оказание услуг%'
        GROUP BY company, cost
        HAVING COUNT(*) > 1
    ) mu 
        ON LOWER(COALESCE(di.company, '')) = LOWER(COALESCE(mu.company, ''))
       AND di.cost::numeric = mu.cost
    WHERE di.report_type = 'upd'
      AND LOWER(COALESCE(di.item_name, '')) LIKE '%продвижение%'
      AND LOWER(COALESCE(di.item_name, '')) LIKE '%оказание услуг%'
      AND LOWER(COALESCE(di.company, '')) = LOWER(COALESCE(r.supplier, ''))
      AND ABS(r.deduction::numeric - di.cost::numeric) < 0.01
    ORDER BY ABS(di.creation_time::date - r.date_to::date)
    LIMIT 1
) u ON TRUE
LEFT JOIN analytics.adv_upd a
    ON a.updnum::text = u.upd_number::text
    AND LOWER(COALESCE(a.supplier, '')) = LOWER(COALESCE(u.company, ''))
    AND a.paymenttype = 'Баланс'
LEFT JOIN (
    SELECT 
        advertid, 
        nm_ids,
        array_length(string_to_array(nm_ids, ','), 1) AS nm_count,
        unnest(string_to_array(nm_ids, ',')) AS nm_id
    FROM (
        SELECT DISTINCT advertid, nm_ids 
        FROM analytics.adv_upd_with_nm_id
    ) t
) awn
    ON awn.advertid = a.advertid
WHERE LOWER(COALESCE(r.bonus_type_name, '')) LIKE '%продвижение%'
  AND LOWER(COALESCE(r.bonus_type_name, '')) LIKE '%оказание услуг%'
  AND r.date_from::date >= DATE '2025-03-01';


-- WITH campaign_nm_counts AS (
--     SELECT
--         advertid,
--         supplier,
--         nm_ids,
--         CARDINALITY(regexp_split_to_array(nm_ids, '\s*,\s*')) AS nm_count
--     FROM analytics.vw_adv_upd_joined
-- ),
-- adv_upd_grouped AS (
--     SELECT
--         updnum,
--         updtime::date AS updtime,
--         advertid,
--         supplier,
--         SUM(updsum) AS total_updsum
--     FROM analytics.adv_upd
--     GROUP BY updnum, updtime::date, advertid, supplier
-- ),
-- adv_upd_with_nm AS (
--     SELECT DISTINCT
--         aug.updnum,
--         aug.updtime,
--         aug.total_updsum AS updsum,
--         aug.advertid,
--         aug.supplier,
--         cnc.nm_count,
--         cnc.nm_ids
--     FROM adv_upd_grouped aug
--     LEFT JOIN campaign_nm_counts cnc
--         ON aug.advertid = cnc.advertid
--         AND COALESCE(aug.supplier, '') = COALESCE(cnc.supplier, '')
-- ),
-- deduction_calculation AS (
--     SELECT DISTINCT
--         COALESCE(u.company, r.supplier, awn.supplier) AS supplier,
--         r.realizationreport_id,
--         awn.advertid AS campaign_id,
--         COALESCE(u.upd_number, awn.updnum::text) AS reklama,
--         r.date_from,
--         r.date_to,
--         awn.updtime AS sale_dt,
--         awn.updsum AS total_cost,
--         awn.nm_count,
--         awn.nm_ids,
--         awn.updsum::numeric / NULLIF(awn.nm_count, 0) AS deduction
--     FROM documents.upd_items u
--     FULL JOIN reports.detail_finance_reports r
--         ON COALESCE(u.company, '') = COALESCE(r.supplier, '')
--         --AND COALESCE(u.item_name, '') = COALESCE(r.bonus_type_name, '')
--         AND COALESCE(u.cost, 0) = COALESCE(r.deduction::numeric, 0)
--     LEFT JOIN adv_upd_with_nm awn
--         ON u.upd_number::text = awn.updnum::text
-- WHERE LOWER(COALESCE(u.item_name, r.bonus_type_name)) LIKE '%продвижение%'
--   AND LOWER(COALESCE(u.item_name, r.bonus_type_name)) LIKE '%оказание услуг%'
--       AND ( r.date_from::date >= DATE '2025-03-01')
--       AND r.deduction::NUMERIC <> 0
-- ),
-- nm_id_expanded AS (
--     SELECT 
--         dc.supplier,
--         dc.realizationreport_id,
--         TRIM(unnest(string_to_array(dc.nm_ids, ','))) AS nm_id,
--         dc.campaign_id,
--         dc.deduction,
--         dc.reklama,
--         dc.date_from,
--         dc.date_to,
--         dc.sale_dt
--     FROM deduction_calculation dc
--     WHERE dc.nm_ids IS NOT NULL
-- )
-- SELECT 
--     nm_id,
--     supplier,
--     realizationreport_id,
--     campaign_id AS "ID кампании",
--     deduction,
--     reklama AS "Реклама",
--     date_from,
--     date_to,
--     sale_dt
-- FROM nm_id_expanded
-- ORDER BY supplier, campaign_id, nm_id;


