CREATE OR REPLACE VIEW reports.v_acquiring_fee AS
SELECT
    supplier,
    realizationreport_id,
    date_from,
    date_to,
    rr_dt,
    nm_id,
    COALESCE(
        SUM(acquiring_fee::NUMERIC) FILTER (WHERE lower(doc_type_name) = 'продажа'), 0
    ) -
    COALESCE(
        SUM(acquiring_fee::NUMERIC) FILTER (WHERE lower(doc_type_name) = 'возврат'), 0
    ) AS acquiring_fee
FROM reports.detail_finance_reports
WHERE acquiring_fee::NUMERIC <> 0
  AND payment_processing = 'Перевыставление эквайринга'
GROUP BY
    supplier,
    realizationreport_id,
    date_from,
    date_to,
    rr_dt,
    nm_id;