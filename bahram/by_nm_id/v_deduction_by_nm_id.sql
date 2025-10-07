-- ОСНОВНОЙ ЗАПРОС: Расчет deduction с разбивкой по nm_id
-- Делит updsum поровну между всеми товарами в кампании
CREATE OR REPLACE VIEW reports.v_deduction_by_nm_id AS
WITH adv_campaigns AS (
    -- Получаем уникальные комбинации advertid и nm_id
    SELECT DISTINCT advertid, nm_id, supplier
    FROM analytics.adv_fullstats
),
campaign_nm_counts AS (
    -- Считаем количество nm_id для каждой кампании и поставщика
    SELECT 
        advertid,
        supplier,
        COUNT(DISTINCT nm_id) as nm_count,
        STRING_AGG(DISTINCT nm_id::text, ', ' ORDER BY nm_id::text) as nm_ids
    FROM adv_campaigns
    GROUP BY advertid, supplier
),
-- Группируем и суммируем updsum по updnum, т.к. один УПД может иметь несколько списаний
adv_upd_grouped AS (
    SELECT 
        a.updnum,
        MAX(a.updtime) as updtime,  -- Берем последнее время списания
        SUM(a.updsum) as total_updsum,  -- СУММИРУЕМ все списания по одному УПД
        MAX(a.advertid) as advertid,
        MAX(a.supplier) as supplier
    FROM analytics.adv_upd a
    WHERE a.paymenttype = 'Баланс'
    GROUP BY a.updnum
),
adv_upd_with_nm AS (
    SELECT DISTINCT
        aug.updnum,
        aug.updtime,
        aug.total_updsum as updsum,
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
        -- Объединяем supplier из всех источников
        COALESCE(u.company, r.supplier, awn.supplier) AS supplier,
        -- Реализационный отчет из финотчетов
        r.realizationreport_id,
        -- ID кампании из adv_upd
        awn.advertid AS campaign_id,
        -- Номер документа (реклама) из разных источников
        COALESCE(u.upd_number, awn.updnum::text) AS reklama,
        -- Даты из финотчетов
        r.date_from,
        r.date_to,
        -- Дата списания из adv_upd
        awn.updtime AS sale_dt,
        -- Общая сумма расходов из adv_upd
        awn.updsum AS total_cost,
        -- Количество nm_id для кампании
        awn.nm_count,
        -- Строка с nm_id
        awn.nm_ids,
        -- Делим общую сумму на количество nm_id для избежания задвоения (с точностью)
        awn.updsum::numeric / NULLIF(awn.nm_count, 0) AS deduction
    FROM documents.upd_items u
    FULL JOIN reports.detail_finance_reports r
        ON COALESCE(u.company, '') = COALESCE(r.supplier, '')
        AND COALESCE(u.item_name, '') = COALESCE(r.bonus_type_name, '')
        AND COALESCE(u.COST, 0) = COALESCE(r.deduction::numeric, 0)
    LEFT JOIN adv_upd_with_nm awn
        ON u.upd_number::text = awn.updnum::text
    WHERE COALESCE(u.item_name, r.bonus_type_name) = 'Оказание услуг «ВБ.Продвижение»'
      AND (r.date_from IS NULL OR r.date_from::date >= DATE '2025-08-25')
),
nm_id_expanded AS (
    -- Разворачиваем nm_id из строки в отдельные строки
    SELECT 
        dc.supplier,
        dc.realizationreport_id,
        TRIM(unnest(string_to_array(dc.nm_ids, ','))) as nm_id,
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

