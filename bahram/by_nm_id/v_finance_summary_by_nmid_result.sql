SELECT 
  COALESCE(a.supplier_name, b.supplier, c.supplier, d.supplier, f.supplier) AS supplier_name,
  COALESCE(a.realizationreport_id, b.realizationreport_id, c.realizationreport_id, d.realizationreport_id, f.realizationreport_id) AS realizationreport_id,
  COALESCE(a.nm_id, b.nmid::bigint, c.nm_id, d.nm_id, f.product_id::bigint) AS nm_id,
  COALESCE(a.date_from, b.date_from, c.date_from, d.date_from, f.date_from) AS date_from,
  COALESCE(a.date_to, b.date_to, c.date_to, d.date_to, f.date_to) AS date_to,
  COALESCE(a.rr_dt, b.date, c.rr_dt, d.sale_dt, f.rr_dt) AS rr_dt,
  CASE 
    WHEN COALESCE(a.nm_id, b.nmid::bigint, c.nm_id, d.nm_id, f.product_id::bigint, 0) = 0 THEN 0
    WHEN COALESCE(a.storage_fee_total::numeric, 0) <> 0 THEN a.storage_fee_total::numeric
    WHEN COALESCE(b.storage_fee_total::numeric, 0) <> 0 THEN b.storage_fee_total::numeric
    ELSE 0
  END AS storage_fee_total,
  COALESCE(c.total_acceptance, 0) AS total_acceptance,
  COALESCE(d.sum_deduction, 0) AS deduction_adv_total,
  COALESCE(f.total_deduction, 0) AS deduction_writeoff_total,
  COALESCE(a.quantity_sales, 0) AS quantity_sales,
  COALESCE(a.quantity_returns, 0) AS quantity_returns,
  COALESCE(a.net_quantity, 0) AS net_quantity,
  COALESCE(a.prodazha_do_komissii, 0) AS prodazha_do_komissii,
  COALESCE(a.vozvrat_do_komissii, 0) AS vozvrat_do_komissii,
  COALESCE(a.prodazha_posle_komissii, 0) AS prodazha_posle_komissii,
  COALESCE(a.vozvrat_posle_komissii, 0) AS vozvrat_posle_komissii,
  COALESCE(a.acquiring_fee_sum, 0) AS acquiring_fee_sum,
  COALESCE(a.korrektirovka_ekvayringa, 0) AS korrektirovka_ekvayringa,
  COALESCE(a.kompensaciya_pri_vozvrate, 0) AS kompensaciya_pri_vozvrate,
  COALESCE(a.kompensaciya_uscherba_prodazha, 0) AS kompensaciya_uscherba_prodazha,
  COALESCE(a.kompensaciya_uscherba_vozvrat, 0) AS kompensaciya_uscherba_vozvrat,
  COALESCE(a.oplata_braka, 0) AS oplata_braka,
  COALESCE(a.chastichnaya_kompensaciya_braka, 0) AS chastichnaya_kompensaciya_braka,
  COALESCE(a.kompensaciya_braka, 0) AS kompensaciya_braka,
  COALESCE(a.kompensaciya_podmenennogo_tovara, 0) AS kompensaciya_podmenennogo_tovara,
  COALESCE(a.oplata_poteryannogo_tovara, 0) AS oplata_poteryannogo_tovara,
  COALESCE(a.kompensaciya_poteryannogo_tovara, 0) AS kompensaciya_poteryannogo_tovara,
  COALESCE(a.oplata_po_itogam_inventarizacii, 0) AS oplata_po_itogam_inventarizacii,
  COALESCE(a.avansovaya_oplata_bez_dvizheniya_prodazha, 0) AS avansovaya_oplata_bez_dvizheniya_prodazha,
  COALESCE(a.avansovaya_oplata_bez_dvizheniya_vozvrat, 0) AS avansovaya_oplata_bez_dvizheniya_vozvrat,
  COALESCE(a.komossia, 0) AS komossia,
  COALESCE(a.margin_after_commission, 0) AS margin_after_commission,
  COALESCE(a.to_transfer_for_goods, 0) AS to_transfer_for_goods,
  COALESCE(a.logistics_total, 0) AS logistics_total,
  COALESCE(a.logistics_count, 0) AS logistics_count,
  COALESCE(a.logistics_storno_count, 0) AS logistics_storno_count,
  COALESCE(a.correction_count, 0) AS correction_count,
  COALESCE(a.logistics_return_positive_total, 0) AS logistics_return_positive_total,
  COALESCE(a.logistics_return_positive_count, 0) AS logistics_return_positive_count,
  COALESCE(a.bonus_return_total, 0) AS bonus_return_total,
  COALESCE(a.bonus_return_count, 0) AS bonus_return_count,
  COALESCE(a.logistics_positive_total, 0) AS logistics_positive_total,
  COALESCE(a.penalties_total, 0) AS penalties_total,
  COALESCE(a.additional_payment_total, 0) AS additional_payment_total,
  COALESCE(a.storage_recalculation_total, 0) AS storage_recalculation_total,
  COALESCE(a.storage_correction_total, 0) AS storage_correction_total,
  COALESCE(a.acceptance_recalculation_total, 0) AS acceptance_recalculation_total,
  COALESCE(a.deduction_other_total, 0) AS deduction_other_total,
  COALESCE(pvz.ppvz_reward, 0) AS ppvz_reward,
  COALESCE(fee.acquiring_fee, 0) AS acquiring_fee,
  COALESCE(logistic.rebill_logistic_cost, 0) AS rebill_logistic_cost,
  COALESCE(cashback.cashback_discount, 0) AS cashback_discount,
  (
  COALESCE(a.to_transfer_for_goods::numeric, 0)
)
-
  COALESCE(a.logistics_total::numeric, 0)
-
  COALESCE(a.penalties_total::numeric, 0)
-
  COALESCE(a.additional_payment_total::numeric, 0)
-
CASE 
    WHEN COALESCE(a.nm_id, b.nmid::bigint, c.nm_id, d.nm_id, f.product_id::bigint, 0) = 0 THEN 0
    WHEN COALESCE(a.storage_fee_total::numeric, 0) <> 0 THEN a.storage_fee_total::numeric
    WHEN COALESCE(b.storage_fee_total::numeric, 0) <> 0 THEN b.storage_fee_total::numeric
    ELSE 0
END
-
COALESCE(c.total_acceptance::numeric, 0)
-
COALESCE(d.sum_deduction::numeric, 0)   -- deduction_adv_total
-
COALESCE(f.total_deduction::numeric, 0) -- deduction_writeoff_total
-
COALESCE(a.deduction_other_total::numeric, 0) -- deduction_other_total
AS total_to_transfer,
  COALESCE(a.net_retail_amount, 0) AS net_retail_amount
  ,(
      COALESCE(a.net_retail_amount, 0)
    - (  COALESCE(a.net_retail_amount, 0) * CAST(:vat_rate AS numeric) / (1 + CAST(:vat_rate AS numeric)))
) AS net_amount_after_vat,
(  COALESCE(a.net_retail_amount, 0) * CAST(:vat_rate AS numeric) / (1 + CAST(:vat_rate AS numeric))) AS vat_amount,
((  COALESCE(a.net_retail_amount, 0) - (  COALESCE(a.net_retail_amount, 0) * CAST(:vat_rate AS numeric) / (1 + CAST(:vat_rate AS numeric))))
 * CAST(:tax_rate AS numeric)) AS tax_to_pay,
 COALESCE(cp.cost_price_sum, 0) AS cost_price_per_one,
 (COALESCE(a.quantity_sales, 0) * COALESCE(cp.cost_price_sum, 0)) AS cost_price_sum,
 ((
  COALESCE(a.to_transfer_for_goods::numeric, 0)
)
-
  COALESCE(a.logistics_total::numeric, 0)
-
  COALESCE(a.penalties_total::numeric, 0)
-
  COALESCE(a.additional_payment_total::numeric, 0)
-
CASE 
    WHEN COALESCE(a.nm_id, b.nmid::bigint, c.nm_id, d.nm_id, f.product_id::bigint, 0) = 0 THEN 0
    WHEN COALESCE(a.storage_fee_total::numeric, 0) <> 0 THEN a.storage_fee_total::numeric
    WHEN COALESCE(b.storage_fee_total::numeric, 0) <> 0 THEN b.storage_fee_total::numeric
    ELSE 0
END
-
COALESCE(c.total_acceptance::numeric, 0)
-
COALESCE(d.sum_deduction::numeric, 0)   -- deduction_adv_total
-
COALESCE(f.total_deduction::numeric, 0) -- deduction_writeoff_total
-
COALESCE(a.deduction_other_total::numeric, 0)
)
--
- (  COALESCE(a.net_retail_amount, 0) * CAST(:vat_rate AS numeric) / (1 + CAST(:vat_rate AS numeric)))  -- vat_amount
- ((COALESCE(a.net_retail_amount, 0) 
     - (COALESCE(a.net_retail_amount, 0) * CAST(:vat_rate AS numeric) / (1 + CAST(:vat_rate AS numeric))))
   * CAST(:tax_rate AS numeric))
- (COALESCE(a.quantity_sales, 0) * COALESCE(cp.cost_price_sum, 0)) AS profit_after_all  -- tax_amoun
FROM reports.mv_detail_finance_reports_v1 a
FULL JOIN reports.v_storage_fee_by_nmid b
  ON a.rr_dt = b.date
 AND a.nm_id = b.nmid::bigint
 and a.realizationreport_id = b.realizationreport_id
FULL JOIN reports.v_acceptance_by_nm_id c
  ON COALESCE(a.rr_dt, b.date) = c.rr_dt
 AND COALESCE(a.nm_id, b.nmid::bigint) = c.nm_id
 and COALESCE(a.realizationreport_id, b.realizationreport_id) = c.realizationreport_id
FULL JOIN (
  SELECT 
    nm_id::bigint, 
    sale_dt::date, 
    date_from::date, 
    date_to::date, 
    realizationreport_id, 
    supplier, 
    SUM(deduction) AS sum_deduction
  FROM reports.v_deduction_by_nm_id
  GROUP BY nm_id::bigint, sale_dt::date, date_from::date, date_to::date, realizationreport_id, supplier
) d
  ON COALESCE(a.rr_dt, b.date, c.rr_dt) = d.sale_dt
 AND COALESCE(a.nm_id, b.nmid::bigint, c.nm_id) = d.nm_id
 and COALESCE(a.realizationreport_id, b.realizationreport_id, c.realizationreport_id) = d.realizationreport_id
FULL JOIN reports.v_bonus_review_deductions f
  ON COALESCE(a.rr_dt, b.date, c.rr_dt, d.sale_dt) = f.rr_dt
 AND COALESCE(a.nm_id, b.nmid::bigint, c.nm_id, d.nm_id) = f.product_id::bigint
 and COALESCE(a.realizationreport_id, b.realizationreport_id, c.realizationreport_id, d.realizationreport_id) = f.realizationreport_id
  LEFT JOIN reports.vw_pvz_refund_reward pvz
  ON COALESCE(a.supplier_name, b.supplier, c.supplier, d.supplier, f.supplier) = pvz.supplier
 AND COALESCE(a.realizationreport_id, b.realizationreport_id, c.realizationreport_id, d.realizationreport_id, f.realizationreport_id) = pvz.realizationreport_id
 AND COALESCE(a.nm_id, b.nmid::bigint, c.nm_id, d.nm_id, f.product_id::bigint) = pvz.nm_id
 AND COALESCE(a.rr_dt, b.date, c.rr_dt, d.sale_dt, f.rr_dt) = pvz.rr_dt::date
 AND COALESCE(a.date_from, b.date_from, c.date_from, d.date_from, f.date_from) = pvz.date_from::date
 AND COALESCE(a.date_to, b.date_to, c.date_to, d.date_to, f.date_to) = pvz.date_to::date
  LEFT JOIN reports.v_acquiring_fee fee
  ON COALESCE(a.supplier_name, b.supplier, c.supplier, d.supplier, f.supplier) = fee.supplier
 AND COALESCE(a.realizationreport_id, b.realizationreport_id, c.realizationreport_id, d.realizationreport_id, f.realizationreport_id) = fee.realizationreport_id
 AND COALESCE(a.nm_id, b.nmid::bigint, c.nm_id, d.nm_id, f.product_id::bigint) = fee.nm_id
 AND COALESCE(a.rr_dt, b.date, c.rr_dt, d.sale_dt, f.rr_dt) = fee.rr_dt::date
 AND COALESCE(a.date_from, b.date_from, c.date_from, d.date_from, f.date_from) = fee.date_from::date
 AND COALESCE(a.date_to, b.date_to, c.date_to, d.date_to, f.date_to) = fee.date_to::date
  LEFT JOIN reports.vw_pvz_rebill_logistic logistic
  ON COALESCE(a.supplier_name, b.supplier, c.supplier, d.supplier, f.supplier) = logistic.supplier
 AND COALESCE(a.realizationreport_id, b.realizationreport_id, c.realizationreport_id, d.realizationreport_id, f.realizationreport_id) = logistic.realizationreport_id
 AND COALESCE(a.nm_id, b.nmid::bigint, c.nm_id, d.nm_id, f.product_id::bigint) = logistic.nm_id
 AND COALESCE(a.rr_dt, b.date, c.rr_dt, d.sale_dt, f.rr_dt) = logistic.rr_dt::date
 AND COALESCE(a.date_from, b.date_from, c.date_from, d.date_from, f.date_from) = logistic.date_from::date
 AND COALESCE(a.date_to, b.date_to, c.date_to, d.date_to, f.date_to) = logistic.date_to::date
  LEFT JOIN reports.vw_pvz_cashback_discount cashback
  ON COALESCE(a.supplier_name, b.supplier, c.supplier, d.supplier, f.supplier) = cashback.supplier
 AND COALESCE(a.realizationreport_id, b.realizationreport_id, c.realizationreport_id, d.realizationreport_id, f.realizationreport_id) = cashback.realizationreport_id
 AND COALESCE(a.nm_id, b.nmid::bigint, c.nm_id, d.nm_id, f.product_id::bigint) = cashback.nm_id
 AND COALESCE(a.rr_dt, b.date, c.rr_dt, d.sale_dt, f.rr_dt) = cashback.rr_dt::date
 AND COALESCE(a.date_from, b.date_from, c.date_from, d.date_from, f.date_from) = cashback.date_from::date
 AND COALESCE(a.date_to, b.date_to, c.date_to, d.date_to, f.date_to) = cashback.date_to::date
 LEFT JOIN products.v_single_cost_price cp
  ON a.supplier_name = cp.legal_entity
 AND a.nm_id = cp.nm_id
 
 