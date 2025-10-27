CREATE OR REPLACE VIEW reports.vw_storno_logistics_nm_id AS
WITH srid_map AS (
    SELECT srid, MAX(nm_id) AS nm_id 
    FROM reports.srid_nm_id_map
    GROUP BY 1
    HAVING COUNT(DISTINCT nm_id) = 1
),
assembly_map AS (
    SELECT assembly_id, MAX(nm_id) AS nm_id 
    FROM reports.assembly_nm_id_map
    GROUP BY 1
    HAVING COUNT(DISTINCT nm_id) = 1
),
shk_map AS (
    SELECT shk_id, MAX(nm_id) AS nm_id 
    FROM reports.shk_nm_id_map
    GROUP BY 1
    HAVING COUNT(DISTINCT nm_id) = 1
),
joined AS (
    SELECT
        dfr.rr_dt::date AS rr_dt,
        dfr.realizationreport_id,
        dfr.date_from,
        dfr.date_to,
        dfr.supplier,
        dfr.delivery_rub::NUMERIC AS delivery_rub,
        COALESCE(
            NULLIF(dfr.nm_id, 0),
            sm.nm_id,
            am.nm_id,
            shkm.nm_id
        ) AS nm_id_final
    FROM reports.detail_finance_reports dfr
    LEFT JOIN srid_map sm ON dfr.srid = sm.srid
    LEFT JOIN assembly_map am ON dfr.assembly_id = am.assembly_id
    LEFT JOIN shk_map shkm ON dfr.shk_id = shkm.shk_id
    WHERE dfr.supplier_oper_name = 'Сторно логистики'
      AND dfr.date_from::date >= DATE '2025-03-01'
      AND dfr.delivery_rub::NUMERIC <> 0
)
SELECT *
FROM joined
