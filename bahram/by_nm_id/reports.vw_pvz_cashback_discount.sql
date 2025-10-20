CREATE OR REPLACE VIEW reports.vw_pvz_cashback_discount AS
SELECT 
    supplier,
    realizationreport_id,
    date_from,
    date_to,
    rr_dt,
    nm_id,
    COALESCE(
        SUM(cashback_discount::NUMERIC) FILTER (WHERE lower(doc_type_name) = 'продажа'), 0
    ) -
    COALESCE(
        SUM(cashback_discount::NUMERIC) FILTER (WHERE lower(doc_type_name) = 'возврат'), 0
    ) AS cashback_discount
FROM reports.detail_finance_reports 
WHERE supplier_oper_name = 'Компенсация скидки по программе лояльности'
  AND cashback_discount::NUMERIC != 0
GROUP BY 
    supplier,
    realizationreport_id,
    date_from,
    date_to,
    rr_dt,
    nm_id;
