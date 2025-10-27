-- reports.srid_nm_id_map исходный текст

CREATE MATERIALIZED VIEW reports.srid_nm_id_map
TABLESPACE pg_default
AS SELECT DISTINCT t.srid,
    t.nm_id,
    t.source
   FROM ( SELECT detail_finance_reports.srid,
            detail_finance_reports.nm_id,
            'detail_finance_reports'::text AS source
           FROM reports.detail_finance_reports
          WHERE detail_finance_reports.nm_id <> 0 AND detail_finance_reports.sa_name IS NOT NULL AND detail_finance_reports.sa_name <> ''::text
        UNION ALL
         SELECT fbs_incomes.rid AS srid,
            fbs_incomes.nmid AS nm_id,
            'fbs_incomes'::text AS source
           FROM supplies.fbs_incomes
        UNION ALL
         SELECT orders.srid,
            orders.nmid AS nm_id,
            'orders'::text AS source
           FROM reports.orders
        UNION ALL
         SELECT sales.srid,
            sales.nmid AS nm_id,
            'sales'::text AS source
           FROM reports.sales
        UNION ALL
         SELECT goods_return.srid,
            goods_return.nmid AS nm_id,
            'goods_return'::text AS source
           FROM reports.goods_return) t
WITH DATA;