CREATE MATERIALIZED VIEW reports.shk_nm_id_map
TABLESPACE pg_default
AS SELECT DISTINCT t.shk_id,
    t.nm_id,
    t.source
   FROM ( SELECT detail_finance_reports.shk_id,
            detail_finance_reports.nm_id,
            'detail_finance_reports'::text AS source
           FROM reports.detail_finance_reports
          WHERE detail_finance_reports.nm_id <> 0 AND detail_finance_reports.sa_name IS NOT NULL AND detail_finance_reports.sa_name <> ''::text AND detail_finance_reports.shk_id IS NOT NULL
        UNION ALL
         SELECT orders.sticker::numeric AS shk_id,
            orders.nmid AS nm_id,
            'orders'::text AS source
           FROM reports.orders
          WHERE orders.sticker IS NOT NULL AND orders.sticker ~ '^[0-9]+$'::text
        UNION ALL
         SELECT sales.sticker::bigint AS shk_id,
            sales.nmid AS nm_id,
            'sales'::text AS source
           FROM reports.sales
          WHERE sales.sticker IS NOT NULL AND sales.sticker ~ '^[0-9]+$'::text
        UNION ALL
         SELECT goods_return.shkid AS shk_id,
            goods_return.nmid AS nm_id,
            'goods_return'::text AS source
           FROM reports.goods_return
          WHERE goods_return.shkid IS NOT NULL
        UNION ALL
         SELECT goods_return.stickerid::numeric AS shk_id,
            goods_return.nmid AS nm_id,
            'goods_return_2'::text AS source
           FROM reports.goods_return
          WHERE goods_return.stickerid IS NOT NULL AND goods_return.stickerid ~ '^[0-9]+$'::text) t
WITH DATA;