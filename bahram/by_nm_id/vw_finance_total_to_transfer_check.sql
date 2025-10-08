
CREATE OR REPLACE VIEW reports.vw_finance_total_to_transfer_check AS
WITH base AS (
    SELECT 
        supplier AS supplier_name,
        realizationreport_id,
        create_dt::date AS report_date,
        date_from::date,
        date_to::date,
        report_type,

        (
            -- К перечислению за товар
            SUM(CASE WHEN doc_type_name = 'Продажа' THEN ppvz_for_pay::numeric ELSE 0 END)
            - SUM(CASE WHEN doc_type_name = 'Возврат' THEN ppvz_for_pay::numeric ELSE 0 END)
        )
        -- Логистика
        - SUM(
            CASE 
                WHEN supplier_oper_name = 'Логистика' THEN delivery_rub::numeric
                WHEN supplier_oper_name = 'Логистика сторно' THEN -delivery_rub::numeric
                WHEN supplier_oper_name = 'Коррекция логистики' THEN delivery_rub::numeric
                ELSE 0
            END
        )
        -- Штрафы
        - SUM(
            CASE 
                WHEN supplier_oper_name IN ('Штраф', 'Штрафы и доплаты') THEN penalty::numeric
                ELSE 0
            END
        )
        -- Доплаты
        - SUM(
            CASE 
                WHEN supplier_oper_name = 'Доплаты' THEN additional_payment::numeric
                ELSE 0
            END
        )
        -- Хранение
        - SUM(storage_fee::numeric)
        -- Приемка
        - SUM(acceptance::numeric)
        -- Вычеты / deduction
        - SUM(deduction::numeric)
        AS total_to_transfer

    FROM reports.detail_finance_reports
    WHERE create_dt::date >= '2025-09-01'
    GROUP BY supplier, realizationreport_id, create_dt::date, date_from::date, date_to::date, report_type
),
upd_items_weekly AS (
    SELECT 
        report_number,
        amount
    FROM documents.upd_items
    WHERE item_name = 'Итого к перечислению Продавцу за текущий период с учетом Вознаграждений и возвратов Товаров'
      AND report_type = 'weekly_sales'
),
redemption_totals AS (
    SELECT 
        redemption_number,
        SUM(amount) AS redemption_total,
        company
    FROM documents.upd_items
    WHERE redemption_number IS NOT NULL
    GROUP BY redemption_number, company
),
nmid_totals AS (
    SELECT 
        realizationreport_id,
        SUM(total_to_transfer) AS total_to_transfer_by_nmid
    FROM reports.detail_finance_reports_by_nm_id
    GROUP BY realizationreport_id
),
final AS (
    SELECT
        b.*,
        COALESCE(
            ui.amount,
            CASE 
                WHEN r.redemption_total IS NOT NULL THEN r.redemption_total
                ELSE NULL
            END
        ) AS total_to_transfer_from_documents,

        CASE 
            WHEN ABS(
                b.total_to_transfer - COALESCE(
                    ui.amount,
                    CASE 
                        WHEN r.redemption_total IS NOT NULL THEN r.redemption_total
                        ELSE NULL
                    END
                )
            ) <= 5 THEN true
            ELSE false
        END AS is_equal,

        nmid.total_to_transfer_by_nmid,
        CASE 
            WHEN ABS(b.total_to_transfer - COALESCE(nmid.total_to_transfer_by_nmid, 0)) <= 5 THEN true
            ELSE false
        END AS is_equal_nmid

    FROM base b
    LEFT JOIN upd_items_weekly ui
        ON b.realizationreport_id::text = ui.report_number
    LEFT JOIN redemption_totals r
        ON b.realizationreport_id::text = r.redemption_number
    LEFT JOIN nmid_totals nmid
        ON b.realizationreport_id = nmid.realizationreport_id
)
SELECT *
FROM final
ORDER BY supplier_name, date_from, date_to
