CREATE OR REPLACE VIEW reports.vw_pvz_rebill_logistic_detail AS
SELECT
    dfr.supplier,
    dfr.realizationreport_id,
    dfr.date_from,
    dfr.date_to,
    dfr.rr_dt,
    dfr.srid,
    COALESCE(s1.nm_id, s2.nm_id, s3.nm_id, 0) AS nm_id,
    dfr.rebill_logistic_cost::NUMERIC,
    dfr.shk_id, 
    dfr.assembly_id
    --COALESCE(SUM(rebill_logistic_cost::NUMERIC), 0) rebill_logistic_cost
FROM reports.detail_finance_reports dfr
LEFT JOIN (
    SELECT srid, nm_id, source
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (PARTITION BY srid ORDER BY source) AS rn
        FROM reports.srid_nm_id_map
    ) t
    WHERE rn = 1
) s1
ON dfr.srid = s1.srid
LEFT JOIN (
    SELECT shk_id, nm_id, source
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (PARTITION BY shk_id ORDER BY source) AS rn
        FROM reports.shk_nm_id_map
    ) t
    WHERE rn = 1
) s2
ON dfr.shk_id = s2.shk_id
LEFT JOIN (
    SELECT assembly_id, nm_id, source
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (PARTITION BY assembly_id ORDER BY source) AS rn
        FROM reports.assembly_nm_id_map
    ) t
    WHERE rn = 1
) s3
ON dfr.assembly_id = s3.assembly_id
WHERE dfr.supplier_oper_name = 'Возмещение издержек по перевозке/по складским операциям с товаром'
  AND dfr.date_from::date >= '2025-03-01'
--GROUP BY 1,2,3,4,5,6;