CREATE OR REPLACE VIEW products.v_single_cost_price AS
SELECT 
    ip,
    legal_entity,
    is_ours,
    nm_id,
    article,
    COUNT(Себестоимость) AS count_price_sum,
    SUM(Себестоимость) AS cost_price_sum
FROM products.sebestoimost
GROUP BY 
    ip,
    legal_entity,
    is_ours,
    nm_id,
    article
HAVING COUNT(Себестоимость) = 1;