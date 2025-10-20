WITH campaign_nm_counts AS (
    SELECT
        advertid,
        supplier,
        nm_ids,
        CARDINALITY(regexp_split_to_array(nm_ids, '\s*,\s*')) AS nm_count
    FROM analytics.vw_adv_upd_joined
),
adv_upd_grouped AS (
    SELECT
        updnum,
        updtime::date AS updtime,
        advertid,
        supplier,
        SUM(updsum) AS total_updsum
    FROM analytics.adv_upd
    GROUP BY updnum, updtime::date, advertid, supplier
),
adv_upd_with_nm AS (
    SELECT DISTINCT
        aug.updnum,
        aug.updtime,
        aug.total_updsum AS updsum,
        aug.advertid,
        aug.supplier,
        cnc.nm_count,
        cnc.nm_ids
    FROM adv_upd_grouped aug
    LEFT JOIN campaign_nm_counts cnc
        ON aug.advertid = cnc.advertid
        AND COALESCE(aug.supplier, '') = COALESCE(cnc.supplier, '')
),
deduction_calculation AS (
    SELECT DISTINCT
        COALESCE(u.company, r.supplier, awn.supplier) AS supplier,
        r.realizationreport_id,
        awn.advertid AS campaign_id,
        COALESCE(u.upd_number, awn.updnum::text) AS reklama,
        r.date_from,
        r.date_to,
        awn.updtime AS sale_dt,
        awn.updsum AS total_cost,
        awn.nm_count,
        awn.nm_ids,
        awn.updsum::numeric / NULLIF(awn.nm_count, 0) AS deduction
    FROM documents.upd_items u
    FULL JOIN reports.detail_finance_reports r
        ON COALESCE(u.company, '') = COALESCE(r.supplier, '')
        AND COALESCE(u.item_name, '') = COALESCE(r.bonus_type_name, '')
        AND COALESCE(u.cost, 0) = COALESCE(r.deduction::numeric, 0)
    LEFT JOIN adv_upd_with_nm awn
        ON u.upd_number::text = awn.updnum::text
WHERE LOWER(COALESCE(u.item_name, r.bonus_type_name)) LIKE '%продвижение%'
  AND LOWER(COALESCE(u.item_name, r.bonus_type_name)) LIKE '%оказание услуг%'
      AND (r.date_from IS NULL OR r.date_from::date >= DATE '2025-03-01')
),
nm_id_expanded AS (
    SELECT 
        dc.supplier,
        dc.realizationreport_id,
        TRIM(unnest(string_to_array(dc.nm_ids, ','))) AS nm_id,
        dc.campaign_id,
        dc.deduction,
        dc.reklama,
        dc.date_from,
        dc.date_to,
        dc.sale_dt
    FROM deduction_calculation dc
    WHERE dc.nm_ids IS NOT NULL
)
SELECT 
    nm_id,
    supplier,
    realizationreport_id,
    campaign_id AS "ID кампании",
    deduction,
    reklama AS "Реклама",
    date_from,
    date_to,
    sale_dt
FROM nm_id_expanded
ORDER BY supplier, campaign_id, nm_id;
