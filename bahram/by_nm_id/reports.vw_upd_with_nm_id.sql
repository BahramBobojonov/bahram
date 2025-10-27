CREATE OR REPLACE VIEW reports.vw_upd_with_nm_id AS
WITH upd AS (
    SELECT 
        LOWER(company) AS company,
        redemption_number,
        LOWER(item_name) AS item_name,
        LOWER(article) AS article,
        to_date(date, 'DD.MM.YYYY') AS date,
        SUM(amount) AS amount_sum,
        SUM(quantity) AS quantity_sum
    FROM documents.upd_items
    WHERE redemption_number IS NOT NULL
    GROUP BY 1,2,3,4,5
),
prod AS (
    SELECT 
        LOWER(supplier_name) AS supplier_name,
        LOWER(vendor_code) AS vendor_code,
        LOWER(title) AS title,
        MAX(nm_id) AS nm_id
    FROM products.products_card
    GROUP BY 1,2,3
    HAVING COUNT(DISTINCT nm_id) = 1
),
fin AS (
    SELECT 
        LOWER(supplier) AS supplier,
        LOWER(sa_name) AS sa_name,
        MAX(nm_id) AS nm_id
    FROM reports.detail_finance_reports
    WHERE nm_id <> 0
      AND sa_name <> ''
    GROUP BY 1,2
    HAVING COUNT(DISTINCT nm_id) = 1
),
ord AS (
    SELECT 
        LOWER(RTRIM(supplier_name)) AS supplier_name,
        LOWER(RTRIM(supplierarticle)) AS supplierarticle,
        MAX(nmid) AS nm_id
    FROM reports.orders
    GROUP BY 1,2
    HAVING COUNT(DISTINCT nmid) = 1
)
SELECT
    u.company,
    u.redemption_number,
    u.item_name,
    u.article,
    u.date,
    u.amount_sum,
    u.quantity_sum,
        CASE 
        WHEN COALESCE(u.quantity_sum, 0) = 0 THEN NULL
        ELSE u.amount_sum / u.quantity_sum
    END AS price_per_unit,
    COALESCE(p.nm_id, f.nm_id, o.nm_id) AS nm_id
FROM upd u
LEFT JOIN prod p
    ON u.article = p.vendor_code
    AND u.company=p.supplier_name
LEFT JOIN fin f
    ON u.company = f.supplier
   AND u.article = f.sa_name
LEFT JOIN ord o
    ON u.company = o.supplier_name
   AND u.article = o.supplierarticle;