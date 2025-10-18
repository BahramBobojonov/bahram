CREATE OR REPLACE VIEW reports.shk_nm_id_map AS
SELECT DISTINCT shk_id, nm_id, source
FROM (
    SELECT shk_id, nm_id, 'detail_finance_reports' AS source
    FROM reports.detail_finance_reports
    WHERE nm_id != 0
      AND sa_name IS NOT NULL
      AND sa_name != ''
      AND shk_id IS NOT NULL
    
    UNION ALL
    
    SELECT sticker::numeric AS shk_id, nmid AS nm_id, 'orders' AS source
    FROM reports.orders
    WHERE sticker IS NOT NULL
      AND sticker ~ '^[0-9]+$'
    
    UNION ALL
    
    SELECT sticker::bigint AS shk_id, nmid AS nm_id, 'sales' AS source
    FROM reports.sales
    WHERE sticker IS NOT NULL
      AND sticker ~ '^[0-9]+$'
    
    UNION ALL
    
    SELECT shkid AS shk_id, nmid AS nm_id, 'goods_return' AS source
    FROM reports.goods_return
    WHERE shkid IS NOT NULL
    
    UNION ALL
    
      SELECT stickerid::NUMERIC AS shk_id, nmid AS nm_id, 'goods_return_2' AS source
    FROM reports.goods_return
    WHERE stickerid IS NOT NULL
      AND stickerid ~ '^[0-9]+$'

) t;