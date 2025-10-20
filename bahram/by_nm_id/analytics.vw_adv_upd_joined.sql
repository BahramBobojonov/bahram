CREATE OR REPLACE VIEW analytics.vw_adv_upd_joined AS
SELECT 
    a.*,
    v.nm_ids,
    v.nm_ids_count
FROM analytics.adv_upd a
LEFT JOIN (
    SELECT DISTINCT advertid, nm_ids, nm_ids_count
    FROM analytics.adv_upd_with_nm_id
) v
ON a.advertid = v.advertid;