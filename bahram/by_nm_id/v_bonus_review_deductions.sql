-- reports.v_bonus_review_deductions исходный текст

CREATE OR REPLACE VIEW reports.v_bonus_review_deductions
AS SELECT detail_finance_reports.realizationreport_id,
    detail_finance_reports.date_from::date AS date_from,
    detail_finance_reports.date_to::date AS date_to,
    detail_finance_reports.supplier,
    regexp_replace(detail_finance_reports.bonus_type_name, '.*товар[[:space:]]+([0-9]+).*'::text, '\1'::text) AS product_id,
    sum(COALESCE(NULLIF(detail_finance_reports.deduction, 'NaN'::text)::numeric, 0::numeric)) AS total_deduction
   FROM reports.detail_finance_reports
  WHERE detail_finance_reports.bonus_type_name ~~* '%отзыв%'::text AND detail_finance_reports.date_from >= '2025-08-25'::text
  GROUP BY detail_finance_reports.realizationreport_id, (detail_finance_reports.date_from::date), (detail_finance_reports.date_to::date), detail_finance_reports.supplier, (regexp_replace(detail_finance_reports.bonus_type_name, '.*товар[[:space:]]+([0-9]+).*'::text, '\1'::text));