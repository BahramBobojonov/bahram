SELECT 
    supplier AS supplier_name,
    realizationreport_id,
    COALESCE(MAX(create_dt::date), date_from::date) AS report_date,
    date_from,
    date_to,
    SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_price_withdisc_rub::numeric ELSE 0 END) AS prodazha_do_komissii,
    SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_price_withdisc_rub::numeric ELSE 0 END) AS vozvrat_do_komissii,
    SUM(CASE WHEN doc_type_name = 'Продажа' THEN ppvz_for_pay::numeric ELSE 0 END) AS prodazha_posle_komissii,
    SUM(CASE WHEN doc_type_name = 'Возврат' THEN ppvz_for_pay::numeric ELSE 0 END) AS vozvrat_posle_komissii,
    SUM(acquiring_fee::numeric) AS acquiring_fee_sum,
    SUM(CASE WHEN supplier_oper_name = 'Корректировка эквайринга' THEN ppvz_for_pay::numeric ELSE 0 END) AS korrektirovka_ekvayringa,
    SUM(CASE WHEN supplier_oper_name = 'Добровольная компенсация при возврате' THEN ppvz_for_pay::numeric ELSE 0 END) AS kompensaciya_pri_vozvrate,
    SUM(
        CASE 
            WHEN doc_type_name = 'Продажа' 
             AND supplier_oper_name = 'Компенсация ущерба' 
            THEN ppvz_for_pay::numeric 
            ELSE 0 
        END
    ) AS kompensaciya_uscherba_prodazha,
    SUM(
        CASE 
            WHEN doc_type_name = 'Возврат' 
             AND supplier_oper_name = 'Компенсация ущерба' 
            THEN ppvz_for_pay::numeric 
            ELSE 0 
        END
    ) AS kompensaciya_uscherba_vozvrat,
    SUM(CASE WHEN supplier_oper_name = 'Оплата брака' THEN ppvz_for_pay::numeric ELSE 0 END) AS oplata_braka,
    SUM(CASE WHEN supplier_oper_name = 'Частичная компенсация брака' THEN ppvz_for_pay::numeric ELSE 0 END) AS chastichnaya_kompensaciya_braka,
    SUM(CASE WHEN supplier_oper_name = 'Компенсация брака' THEN ppvz_for_pay::numeric ELSE 0 END) AS kompensaciya_braka,
    SUM(CASE WHEN supplier_oper_name = 'Компенсация подмененного товара' THEN ppvz_for_pay::numeric ELSE 0 END) AS kompensaciya_podmenennogo_tovara,
    SUM(CASE WHEN supplier_oper_name = 'Оплата потерянного товара' THEN ppvz_for_pay::numeric ELSE 0 END) AS oplata_poteryannogo_tovara,
    SUM(CASE WHEN supplier_oper_name = 'Компенсация потерянного товара' THEN ppvz_for_pay::numeric ELSE 0 END) AS kompensaciya_poteryannogo_tovara,
    SUM(CASE WHEN supplier_oper_name = 'Оплата по итогам инвентаризации' THEN ppvz_for_pay::numeric ELSE 0 END) AS oplata_po_itogam_inventarizacii,
    SUM(
        CASE 
            WHEN doc_type_name = 'Продажа' 
             AND supplier_oper_name = 'Авансовая оплата за товар без движения' 
            THEN ppvz_for_pay::numeric 
            ELSE 0 
        END
    ) AS avansovaya_oplata_bez_dvizheniya_prodazha,
    SUM(
        CASE 
            WHEN doc_type_name = 'Возврат' 
             AND supplier_oper_name = 'Авансовая оплата за товар без движения' 
            THEN ppvz_for_pay::numeric 
            ELSE 0 
        END
    ) AS avansovaya_oplata_bez_dvizheniya_vozvrat,
    (SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_price_withdisc_rub::numeric ELSE 0 END) - 
    SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_price_withdisc_rub::numeric ELSE 0 END))- (
    SUM(CASE WHEN doc_type_name = 'Продажа' THEN ppvz_for_pay::numeric ELSE 0 END) -
    SUM(CASE WHEN doc_type_name = 'Возврат' THEN ppvz_for_pay::numeric ELSE 0 END)) AS komossia,
    
CASE 
    WHEN (SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_price_withdisc_rub::numeric ELSE 0 END)
          - SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_price_withdisc_rub::numeric ELSE 0 END)) != 0 
    THEN
        (
          SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_price_withdisc_rub::numeric ELSE 0 END)
          - SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_price_withdisc_rub::numeric ELSE 0 END)
          - (
              SUM(CASE WHEN doc_type_name = 'Продажа' THEN ppvz_for_pay::numeric ELSE 0 END)
              - SUM(CASE WHEN doc_type_name = 'Возврат' THEN ppvz_for_pay::numeric ELSE 0 END)
            )
        )
        /
        (
          SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_price_withdisc_rub::numeric ELSE 0 END)
          - SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_price_withdisc_rub::numeric ELSE 0 END)
        )
    ELSE 0
END AS margin_after_commission,
(
    SUM(CASE WHEN doc_type_name = 'Продажа' THEN ppvz_for_pay::numeric ELSE 0 END) -
    SUM(CASE WHEN doc_type_name = 'Возврат' THEN ppvz_for_pay::numeric ELSE 0 END)) AS to_transfer_for_goods,
    SUM(
        CASE 
            WHEN supplier_oper_name = 'Логистика' THEN delivery_rub::numeric
            WHEN supplier_oper_name = 'Логистика сторно' THEN -delivery_rub::numeric
            WHEN supplier_oper_name = 'Коррекция логистики' THEN delivery_rub::numeric
            ELSE 0
        END
    ) AS logistics_total,
    
    COUNT(
        CASE 
            WHEN supplier_oper_name = 'Логистика' THEN 1
        END
    ) AS logistics_count,
    
    COUNT(
        CASE 
            WHEN supplier_oper_name = 'Логистика сторно' THEN 1
        END
    ) AS logistics_storno_count,
    
    COUNT(
        CASE 
            WHEN supplier_oper_name = 'Коррекция логистики' THEN 1
        END
    ) AS correction_count,
    
    SUM(
        CASE 
            WHEN supplier_oper_name = 'Логистика' AND return_amount::numeric > 0
            THEN delivery_rub::numeric
            ELSE 0
        END
    ) AS logistics_return_positive_total,
    
    COUNT(
        CASE 
            WHEN supplier_oper_name = 'Логистика' AND return_amount::numeric > 0
            THEN 1
        END
    ) AS logistics_return_positive_count,
    
    SUM(
        CASE 
            WHEN doc_type_name = 'Логистика' AND bonus_type_name = 'Возврат брака (К продавцу)' 
            THEN delivery_rub::numeric
            ELSE 0
        END
    ) AS bonus_return_total,
    
    COUNT(
        CASE 
            WHEN doc_type_name = 'Логистика' AND bonus_type_name = 'Возврат брака (К продавцу)' 
            THEN 1
        END
    ) AS bonus_return_count,
        SUM(
        CASE 
            WHEN supplier_oper_name = 'Логистика' AND delivery_amount::numeric > 0
            THEN delivery_rub::numeric
            ELSE 0
        END
    ) AS logistics_positive_total,
        SUM(
        CASE 
            WHEN supplier_oper_name = 'Штраф' THEN penalty::numeric
            WHEN supplier_oper_name = 'Штрафы и доплаты' THEN penalty::numeric
            ELSE 0
        END
    ) AS penalties_total,
        SUM(
        CASE 
            WHEN supplier_oper_name = 'Доплаты' THEN additional_payment::numeric
            ELSE 0
        END
    ) AS additional_payment_total,
    SUM(storage_fee::numeric) AS storage_fee_total,
        SUM(
        CASE 
            WHEN supplier_oper_name = 'Пересчет хранения' THEN storage_fee::numeric
            ELSE 0
        END
    ) AS storage_recalculation_total,
        SUM(
        CASE 
            WHEN supplier_oper_name = 'Корректировка хранения' THEN storage_fee::numeric
            ELSE 0
        END
    ) AS storage_correction_total,
        SUM(acceptance::numeric) AS acceptance_total,
                SUM(
        CASE 
            WHEN supplier_oper_name = 'Пересчет платной приемки' THEN acceptance::numeric
            ELSE 0
        END
    ) AS acceptance_recalculation_total,
    SUM(deduction::numeric) AS deduction_total,
        SUM(
        CASE 
            WHEN deduction::numeric < 0 THEN deduction::numeric
            ELSE 0
        END
    ) AS deduction_negative_total,
        SUM(
        CASE 
            WHEN deduction::numeric > 0 THEN deduction::numeric
            ELSE 0
        END
    ) AS deduction_positive_total,
        SUM(
        CASE 
            WHEN bonus_type_name LIKE 'Списание за отзыв%' THEN deduction::numeric
            ELSE 0
        END
    ) AS deduction_writeoff_total,
            SUM(
        CASE 
            WHEN bonus_type_name LIKE '%Продвижение%' THEN deduction::numeric
            ELSE 0
        END
    ) AS deduction_adv_total,
SUM(
    CASE 
        WHEN bonus_type_name NOT LIKE '%Продвижение%' 
         AND bonus_type_name NOT LIKE 'Списание за отзыв%' 
        THEN deduction::numeric
        ELSE 0
    END
) AS deduction_other_total,
(
    -- К перечислению за товар
    SUM(CASE WHEN doc_type_name = 'Продажа' THEN ppvz_for_pay::numeric ELSE 0 END) -
    SUM(CASE WHEN doc_type_name = 'Возврат' THEN ppvz_for_pay::numeric ELSE 0 END)
)
-
-- Логистика
SUM(
    CASE 
        WHEN supplier_oper_name = 'Логистика' THEN delivery_rub::numeric
        WHEN supplier_oper_name = 'Логистика сторно' THEN -delivery_rub::numeric
        WHEN supplier_oper_name = 'Коррекция логистики' THEN delivery_rub::numeric
        ELSE 0
    END
)
-
-- Штрафы
SUM(
    CASE 
        WHEN supplier_oper_name = 'Штраф' THEN penalty::numeric
        WHEN supplier_oper_name = 'Штрафы и доплаты' THEN penalty::numeric
        ELSE 0
    END
)
-
-- Доплаты
SUM(
    CASE 
        WHEN supplier_oper_name = 'Доплаты' THEN additional_payment::numeric
        ELSE 0
    END
)
-
-- Хранение
SUM(storage_fee::numeric)
-
-- Приемка
SUM(acceptance::numeric)
-
-- Вычеты / deduction
SUM(deduction::numeric)
AS total_to_transfer,
SUM(
        CASE 
            WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric
            ELSE 0
        END
    )
    -
    SUM(
        CASE 
            WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric
            ELSE 0
        END
    ) AS net_retail_amount,
    
(
    -- Чистая сумма продаж минус возвраты
    SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END)
    - SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)
)
-
(
    -- Вычет НДС
    (
        SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END)
        - SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)
    ) * :vat_rate / (1 + :vat_rate)
) AS net_amount_after_vat,
(
    (
        SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END)
        - SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)
    )
    -
    (
        SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END)
        - SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)
    ) * :vat_rate / (1 + :vat_rate)
) * :tax_rate AS tax_to_pay,
    (
        SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END)
        - SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)
    ) * :vat_rate / (1 + :vat_rate) AS vat_amount,
    CASE 
    WHEN 
        (SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_price_withdisc_rub::numeric ELSE 0 END)
        - SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_price_withdisc_rub::numeric ELSE 0 END)) > 0
    THEN
        (
            -- К перечислению за товар минус логистика, штрафы, доплаты, хранение, приемка и вычеты
            (
                SUM(CASE WHEN doc_type_name = 'Продажа' THEN ppvz_for_pay::numeric ELSE 0 END)
                - SUM(CASE WHEN doc_type_name = 'Возврат' THEN ppvz_for_pay::numeric ELSE 0 END)
            )
            -
            SUM(
                CASE 
                    WHEN supplier_oper_name = 'Логистика' THEN delivery_rub::numeric
                    WHEN supplier_oper_name = 'Логистика сторно' THEN -delivery_rub::numeric
                    WHEN supplier_oper_name = 'Коррекция логистики' THEN delivery_rub::numeric
                    ELSE 0
                END
            )
            -
            SUM(
                CASE 
                    WHEN supplier_oper_name = 'Штраф' THEN penalty::numeric
                    WHEN supplier_oper_name = 'Штрафы и доплаты' THEN penalty::numeric
                    ELSE 0
                END
            )
            -
            SUM(
                CASE 
                    WHEN supplier_oper_name = 'Доплаты' THEN additional_payment::numeric
                    ELSE 0
                END
            )
            -
            SUM(storage_fee::numeric)
            -
            SUM(acceptance::numeric)
            -
            SUM(deduction::numeric)
        )
        -
        -- Вычитаем налог к уплате и НДС
        (
            (
                SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END)
                - SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)
            )
            -
            (
                SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END)
                - SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)
            ) * :vat_rate / (1 + :vat_rate)
        ) * :tax_rate
        -
        (
            SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END)
            - SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)
        ) * :vat_rate / (1 + :vat_rate)
    ELSE 0
END AS profit_after_all
FROM reports.detail_finance_reports
GROUP BY supplier, realizationreport_id, date_from, date_to
ORDER BY supplier, date_from, date_to;
