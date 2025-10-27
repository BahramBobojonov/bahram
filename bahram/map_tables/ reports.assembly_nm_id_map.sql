-- reports.assembly_nm_id_map исходный текст

CREATE MATERIALIZED VIEW reports.assembly_nm_id_map
TABLESPACE pg_default
AS SELECT DISTINCT t.assembly_id,
    t.nm_id,
    t.source
   FROM ( SELECT dfr.assembly_id,
            dfr.nm_id,
            'detail_finance_reports'::text AS source
           FROM reports.detail_finance_reports dfr
          WHERE dfr.nm_id <> 0 AND dfr.sa_name IS NOT NULL AND dfr.sa_name <> ''::text AND dfr.assembly_id IS NOT NULL AND dfr.assembly_id <> 0
        UNION ALL
         SELECT fbs.id AS assembly_id,
            fbs.nmid AS nm_id,
            'fbs_incomes'::text AS source
           FROM supplies.fbs_incomes fbs
          WHERE fbs.id IS NOT NULL AND fbs.id <> 0) t
WITH DATA;