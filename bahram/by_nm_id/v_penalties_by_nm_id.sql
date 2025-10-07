CREATE OR REPLACE VIEW reports.v_penalties_by_nm_id AS
SELECT 
    realizationreport_id,
    date_from::date AS date_from,
    date_to::date AS date_to,
    nm_id,
    rr_dt::date AS rr_date,
    bonus_type_name,
    SUM(penalty::numeric) AS total_penalty
FROM reports.detail_finance_reports
WHERE penalty IS NOT NULL
  AND penalty != '0'
  AND penalty::numeric != 0
  AND date_from::date >= DATE '2025-08-25'
GROUP BY 
    realizationreport_id,
    date_from::date,
    date_to::date,
    nm_id,
    rr_dt::date,
    bonus_type_name;
