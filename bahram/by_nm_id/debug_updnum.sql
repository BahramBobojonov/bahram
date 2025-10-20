-- Проверка этапов запроса для updnum: 265522014, 264473543, 255704444, 0 по ИП Баах Р.Н.

\echo '=== ЭТАП 0: Исходные данные из analytics.adv_upd ==='
SELECT 
    updnum, 
    updtime::date, 
    advertid, 
    supplier, 
    updsum,
    COUNT(*) as records_count
FROM analytics.adv_upd 
WHERE supplier LIKE '%Баах%' 
  AND updnum IN (265522014, 264473543, 255704444, 0)
GROUP BY updnum, updtime::date, advertid, supplier, updsum
ORDER BY updnum;

\echo ''
\echo '=== ЭТАП 1: После adv_upd_grouped (группировка) ==='
WITH adv_upd_grouped AS (
    SELECT
        updnum,
        updtime::date AS updtime,
        advertid,
        supplier,
        SUM(updsum) AS total_updsum
    FROM analytics.adv_upd
    GROUP BY updnum, updtime::date, advertid, supplier
)
SELECT 
    updnum,
    updtime,
    advertid,
    supplier,
    total_updsum
FROM adv_upd_grouped
WHERE supplier LIKE '%Баах%' 
  AND updnum IN (265522014, 264473543, 255704444, 0)
ORDER BY updnum;

\echo ''
\echo '=== ЭТАП 2: После adv_upd_with_nm (JOIN с campaign_nm_counts) ==='
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
)
SELECT 
    updnum,
    updtime,
    advertid,
    supplier,
    updsum,
    nm_count,
    LEFT(nm_ids, 100) as nm_ids_preview
FROM adv_upd_with_nm
WHERE supplier LIKE '%Баах%' 
  AND updnum IN (265522014, 264473543, 255704444, 0)
ORDER BY updnum;

\echo ''
\echo '=== ЭТАП 3: Проверка данных в documents.upd_items ==='
SELECT 
    upd_number,
    company,
    item_name,
    cost,
    COUNT(*) as records_count
FROM documents.upd_items
WHERE company LIKE '%Баах%' 
  AND upd_number IN ('265522014', '264473543', '255704444', '0')
  AND item_name = 'Оказание услуг «ВБ.Продвижение»'
GROUP BY upd_number, company, item_name, cost
ORDER BY upd_number;

\echo ''
\echo '=== ЭТАП 4: После deduction_calculation (с FULL JOIN) ==='
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
    WHERE COALESCE(u.item_name, r.bonus_type_name) = 'Оказание услуг «ВБ.Продвижение»'
      AND (r.date_from IS NULL OR r.date_from::date >= DATE '2025-03-01')
)
SELECT 
    supplier,
    reklama,
    campaign_id,
    sale_dt,
    total_cost,
    nm_count,
    LEFT(nm_ids, 100) as nm_ids_preview,
    deduction,
    realizationreport_id,
    date_from,
    date_to
FROM deduction_calculation
WHERE supplier LIKE '%Баах%' 
  AND reklama IN ('265522014', '264473543', '255704444', '0')
ORDER BY reklama;

\echo ''
\echo '=== ЭТАП 5: Финальный результат (с фильтром WHERE dc.nm_ids IS NOT NULL) ==='
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
    WHERE COALESCE(u.item_name, r.bonus_type_name) = 'Оказание услуг «ВБ.Продвижение»'
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
WHERE supplier LIKE '%Баах%' 
  AND reklama IN ('265522014', '264473543', '255704444', '0')
ORDER BY supplier, campaign_id, nm_id;

