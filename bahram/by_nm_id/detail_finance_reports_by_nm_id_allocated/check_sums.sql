-- Полный SELECT с SUM по всем полям (безопасное приведение типов)
SELECT 
    supplier_name,
    realizationreport_id,
    COUNT(*) as row_count,
    
    -- Количество
    SUM(quantity_sales::numeric) as sum_quantity_sales,
    SUM(quantity_returns::numeric) as sum_quantity_returns,
    SUM(net_quantity::numeric) as sum_net_quantity,
    
    -- Продажи и возвраты
    SUM(prodazha_do_komissii::numeric) as sum_prodazha_do_komissii,
    SUM(vozvrat_do_komissii::numeric) as sum_vozvrat_do_komissii,
    SUM(prodazha_posle_komissii::numeric) as sum_prodazha_posle_komissii,
    SUM(vozvrat_posle_komissii::numeric) as sum_vozvrat_posle_komissii,
    
    -- Комиссии и эквайринг
    SUM(acquiring_fee_sum::numeric) as sum_acquiring_fee_sum,
    SUM(korrektirovka_ekvayringa::numeric) as sum_korrektirovka_ekvayringa,
    SUM(acquiring_fee::numeric) as sum_acquiring_fee,
    SUM(kompensaciya_pri_vozvrate::numeric) as sum_kompensaciya_pri_vozvrate,
    SUM(kompensaciya_uscherba_prodazha::numeric) as sum_kompensaciya_uscherba_prodazha,
    SUM(kompensaciya_uscherba_vozvrat::numeric) as sum_kompensaciya_uscherba_vozvrat,
    SUM(oplata_braka::numeric) as sum_oplata_braka,
    SUM(chastichnaya_kompensaciya_braka::numeric) as sum_chastichnaya_kompensaciya_braka,
    SUM(kompensaciya_braka::numeric) as sum_kompensaciya_braka,
    SUM(kompensaciya_podmenennogo_tovara::numeric) as sum_kompensaciya_podmenennogo_tovara,
    SUM(oplata_poteryannogo_tovara::numeric) as sum_oplata_poteryannogo_tovara,
    SUM(kompensaciya_poteryannogo_tovara::numeric) as sum_kompensaciya_poteryannogo_tovara,
    SUM(oplata_po_itogam_inventarizacii::numeric) as sum_oplata_po_itogam_inventarizacii,
    SUM(avansovaya_oplata_bez_dvizheniya_prodazha::numeric) as sum_avansovaya_oplata_bez_dvizheniya_prodazha,
    SUM(avansovaya_oplata_bez_dvizheniya_vozvrat::numeric) as sum_avansovaya_oplata_bez_dvizheniya_vozvrat,
    SUM(komossia::numeric) as sum_komossia,
    SUM(margin_after_commission::numeric) as sum_margin_after_commission,
    
    -- К перечислению
    SUM(to_transfer_for_goods::numeric) as sum_to_transfer_for_goods,
    SUM(total_to_transfer::numeric) as sum_total_to_transfer,
    
    -- Логистика
    SUM(logistics_count::numeric) as sum_logistics_count,
    SUM(logistics_storno_count::numeric) as sum_logistics_storno_count,
    SUM(correction_count::numeric) as sum_correction_count,
    SUM(logistics_return_positive_total::numeric) as sum_logistics_return_positive_total,
    SUM(logistics_return_positive_count::numeric) as sum_logistics_return_positive_count,
    SUM(bonus_return_total::numeric) as sum_bonus_return_total,
    SUM(bonus_return_count::numeric) as sum_bonus_return_count,
    SUM(logistics_positive_total::numeric) as sum_logistics_positive_total,
    
    -- Выручка
    SUM(net_retail_amount::numeric) as sum_net_retail_amount,
    SUM(net_amount_after_vat::numeric) as sum_net_amount_after_vat,
    SUM(vat_amount::numeric) as sum_vat_amount,
    SUM(tax_to_pay::numeric) as sum_tax_to_pay,
    
    -- Себестоимость
    SUM(cost_price_per_one::numeric) as sum_cost_price_per_one,
    SUM(cost_price_sum::numeric) as sum_cost_price_sum,
    SUM(profit_after_all::numeric) as sum_profit_after_all,
    
    -- Расходы (аллоцированные)
    SUM(storage_fee_total::numeric) as sum_storage_fee_total,
    SUM(total_acceptance::numeric) as sum_total_acceptance,
    SUM(deduction_adv_total::numeric) as sum_deduction_adv_total,
    SUM(deduction_writeoff_total::numeric) as sum_deduction_writeoff_total,
    SUM(deduction_other_total::numeric) as sum_deduction_other_total,
    SUM(logistics_total::numeric) as sum_logistics_total,
    SUM(logistics_total_without_storno::numeric) as sum_logistics_total_without_storno,
    SUM(storno_logistics_total::numeric) as sum_storno_logistics_total,
    SUM(penalties_total::numeric) as sum_penalties_total,
    SUM(additional_payment_total::numeric) as sum_additional_payment_total,
    SUM(additional_payment_correction::numeric) as sum_additional_payment_correction,
    SUM(storage_recalculation_total::numeric) as sum_storage_recalculation_total,
    SUM(storage_correction_total::numeric) as sum_storage_correction_total,
    SUM(acceptance_recalculation_total::numeric) as sum_acceptance_recalculation_total,
    SUM(rebill_logistic_cost::numeric) as sum_rebill_logistic_cost,
    SUM(cashback_discount::numeric) as sum_cashback_discount,
    SUM(ppvz_reward::numeric) as sum_ppvz_reward
    
FROM reports.detail_finance_reports_by_nm_id_allocated
GROUP BY supplier_name, realizationreport_id
ORDER BY supplier_name, realizationreport_id;

