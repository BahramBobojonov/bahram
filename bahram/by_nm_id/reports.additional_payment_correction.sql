CREATE OR REPLACE VIEW reports.additional_payment_correction AS 
WITH srid_map AS (
         SELECT srid_nm_id_map.srid,
            max(srid_nm_id_map.nm_id) AS nm_id
           FROM reports.srid_nm_id_map
          GROUP BY srid_nm_id_map.srid
         HAVING count(DISTINCT srid_nm_id_map.nm_id) = 1
        ), assembly_map AS (
         SELECT assembly_nm_id_map.assembly_id,
            max(assembly_nm_id_map.nm_id) AS nm_id
           FROM reports.assembly_nm_id_map
          GROUP BY assembly_nm_id_map.assembly_id
         HAVING count(DISTINCT assembly_nm_id_map.nm_id) = 1
        ), shk_map AS (
         SELECT shk_nm_id_map.shk_id,
            max(shk_nm_id_map.nm_id) AS nm_id
           FROM reports.shk_nm_id_map
          GROUP BY shk_nm_id_map.shk_id
         HAVING count(DISTINCT shk_nm_id_map.nm_id) = 1
        ), joined AS (
         SELECT dfr.rr_dt::date AS rr_dt, 
            dfr.realizationreport_id,
            dfr.date_from::date AS date_from,
            dfr.date_to::date AS date_to,
            dfr.supplier,
               dfr.additional_payment::numeric AS additional_payment_correction,
            COALESCE(NULLIF(dfr.nm_id, 0), sm.nm_id, am.nm_id, shkm.nm_id) AS nm_id_final
           FROM reports.detail_finance_reports dfr
             LEFT JOIN srid_map sm ON dfr.srid = sm.srid
             LEFT JOIN assembly_map am ON dfr.assembly_id = am.assembly_id
             LEFT JOIN shk_map shkm ON dfr.shk_id::numeric = shkm.shk_id
          WHERE  supplier_oper_name = 'Корректировка' AND dfr.date_from::date >= '2025-03-01'::date
        )
 SELECT COALESCE(joined.nm_id_final, 0::bigint) AS nm_id,
    joined.rr_dt,
    joined.realizationreport_id,
    joined.date_from,
    joined.date_to,
    joined.supplier,
    sum(joined.additional_payment_correction) AS additional_payment_correction
   FROM joined
   GROUP BY 
COALESCE(joined.nm_id_final, 0::bigint),
    joined.rr_dt,
    joined.realizationreport_id,
    joined.date_from,
    joined.date_to,
    joined.supplier