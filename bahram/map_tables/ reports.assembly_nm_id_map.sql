CREATE OR REPLACE VIEW reports.assembly_nm_id_map AS
SELECT DISTINCT assembly_id, nm_id, source
FROM (
    SELECT assembly_id, nm_id, 'detail_finance_reports' AS source
    FROM reports.detail_finance_reports
    WHERE nm_id != 0
      AND sa_name IS NOT NULL
      AND sa_name != ''
      AND assembly_id IS NOT NULL
      AND assembly_id <> 0
    
    UNION ALL
    
    SELECT id AS assembly_id, nmid AS nm_id, 'fbs_incomes' AS source
    FROM supplies.fbs_incomes
    WHERE id IS NOT NULL
      AND id <> 0
) t;