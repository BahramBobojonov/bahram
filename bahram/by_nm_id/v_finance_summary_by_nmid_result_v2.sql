-- ШАГ 1: Создаем временную таблицу со всеми уникальными ключами
WITH all_keys AS (
  -- Ключи из основной таблицы
  SELECT DISTINCT
    supplier AS supplier_name,
    realizationreport_id,
    nm_id::bigint,
    date_from::date,
    date_to::date,
    rr_dt::date
  FROM reports.v_storage_fee_by_nmid
  WHERE realizationreport_id IS NOT NULL
  
  UNION DISTINCT
  
  SELECT DISTINCT
    supplier AS supplier_name,
    realizationreport_id,
    nmid::bigint,
    date_from::date,
    date_to::date,
    date::date AS rr_dt
  FROM reports.v_storage_fee_by_nmid
  WHERE realizationreport_id IS NOT NULL
  
  UNION DISTINCT
  
  SELECT DISTINCT
    supplier AS supplier_name,
    realizationreport_id,
    nmid::bigint,
    date_from::date,
    date_to::date,
    rr_dt::date
  FROM reports.v_acceptance_by_nm_id
  
  UNION DISTINCT
  
  SELECT DISTINCT
    supplier AS supplier_name,
    realizationreport_id,
    nm_id::bigint,
    date_from::date,
    date_to::date,
    updtime::date AS rr_dt
  FROM reports.v_deduction_by_nm_id
  
  UNION DISTINCT
  
  SELECT DISTINCT
    supplier AS supplier_name,
    realizationreport_id,
    nm_id::bigint,
    date_from::date,
    date_to::date,
    rr_dt::date
  FROM reports.vw_pvz_rebill_logistic
  
  UNION DISTINCT
  
  SELECT DISTINCT
    supplier AS supplier_name,
    realizationreport_id,
    product_id::bigint,
    date_from::date,
    date_to::date,
    rr_dt::date
  FROM reports.v_bonus_review_deductions
),
-- ШАГ 2: LEFT JOIN всех данных к ключам
result_data AS (
SELECT 
  all_keys.supplier_name,
  all_keys.realizationreport_id,
  all_keys.nm_id,
  all_keys.date_from,
  all_keys.date_to,
  all_keys.rr_dt,
  
  CASE WHEN COALESCE(b.storage_fee_total::numeric, 0) <> 0 THEN b.storage_fee_total::numeric ELSE 0 END AS storage_fee_total,
  COALESCE(c.total_acceptance, 0) AS total_acceptance,
  COALESCE(d.sum_deduction, 0) AS deduction_adv_total,
  COALESCE(f.total_deduction, 0) AS deduction_writeoff_total,
  COALESCE(a.quantity_sales, 0) AS quantity_sales,
  COALESCE(a.quantity_returns, 0) AS quantity_returns,
  COALESCE(a.net_quantity, 0) AS net_quantity,
  COALESCE(a.prodazha_do_komissii, 0) AS prodazha_do_комиссии,
  COALESCE(a.vozvrat_do_komissii, 0) AS vozvrat_do_комиссии,
  COALESCE(a.prodazha_posle_komissii, 0) AS prodazha_posle_komиссии,
  COALESCE(a.vozvrat_posle_komissii, 0) AS vozvrat_posle_komиссии,
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
  COALESCE(a.oplata_po_itogam_inventarizacii, 0) AS oplata_po_itogam_inventarии,
  COALESCE(a.avansovaya_oplata_bez_dvizheniya_prodazha, 0) AS avansovaya_oplata_bez_dvizheniya_prodazha,
  COALESCE(a.avansovaya_oplata_bez_dvizheniya_vozvrat, 0) AS avansovaya_oplata_bez_dvizheniya_vozvrat,
  COALESCE(a.komossia, 0) AS komossia,
  COALESCE(a.margin_after_commission, 0) AS margin_after_commission,
  COALESCE(a.to_transfer_for_goods, 0) AS to_transfer_for_goods,

  COALESCE(a.logistics_total, 0) AS logistics_total_without_storno,
  COALESCE(storno_logistics.delivery_rub, 0) AS storno_logistics_total,
  COALESCE(a.logistics_total,0) + COALESCE(storno_logistics.delivery_rub, 0) AS logistics_total,

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
  COALESCE(additional_payment_correction.additional_payment_correction, 0) AS additional_payment_correction,

  (
    COALESCE(a.to_transfer_for_goods::numeric, 0)
  )
  - (COALESCE(a.logistics_total::numeric, 0) + COALESCE(storno_logistics.delivery_rub::numeric, 0))
  - COALESCE(a.penalties_total::numeric, 0)
  - COALESCE(a.additional_payment_total::numeric, 0)
  - CASE WHEN COALESCE(b.storage_fee_total::numeric, 0) <> 0 THEN b.storage_fee_total::numeric ELSE 0 END
  - COALESCE(c.total_acceptance::numeric, 0)
  - COALESCE(d.sum_deduction::numeric, 0)
  - COALESCE(f.total_deduction::numeric, 0)
  - COALESCE(a.deduction_other_total::numeric, 0)
  - COALESCE(additional_payment_correction.additional_payment_correction::numeric, 0)
  AS total_to_transfer,

  COALESCE(a.net_retail_amount, 0) AS net_retail_amount,
  COALESCE(cp.cost_price_sum, 0) AS cost_price_per_one,
  (COALESCE(a.quantity_sales, 0) * COALESCE(cp.cost_price_sum, 0)) AS cost_price_sum

FROM all_keys
LEFT JOIN reports.mv_detail_finance_reports_v1 a
  ON all_keys.rr_dt = a.rr_dt::date
 AND all_keys.nm_id = a.nm_id::bigint
 AND all_keys.realizationreport_id = a.realizationreport_id
 AND all_keys.date_from = a.date_from::date
 AND all_keys.date_to = a.date_to::date
LEFT JOIN (
  SELECT 
    date::date,
    supplier,
    nmid::bigint,
    date_from::date,
    date_to::date,
    SUM(total_warehouseprice)::numeric AS storage_fee_total,
    realizationreport_id
  FROM reports.v_storage_fee_by_nmid
  WHERE realizationreport_id IS NOT null
  GROUP BY 1,2,3,4,5,7
) b
  ON all_keys.rr_dt = b.date::date
 AND all_keys.nm_id = b.nmid::bigint
 AND all_keys.realizationreport_id = b.realizationreport_id
 AND all_keys.date_from = b.date_from::date
 AND all_keys.date_to = b.date_to::date
LEFT JOIN (
  SELECT 
    supplier,
    rr_dt::date,
    nmid::bigint AS nm_id,
    date_from::date,
    date_to::date,
    realizationreport_id,
    SUM(total_acceptance) AS total_acceptance
  FROM reports.v_acceptance_by_nm_id
  GROUP BY 1,2,3,4,5,6
) c
  ON all_keys.rr_dt = c.rr_dt::date
 AND all_keys.nm_id = c.nm_id::bigint
 AND all_keys.realizationreport_id = c.realizationreport_id
 AND all_keys.date_from = c.date_from::date
 AND all_keys.date_to = c.date_to::date
LEFT JOIN (
  SELECT 
    nm_id::bigint,
    updtime::date,
    date_from::date,
    date_to::date,
    realizationreport_id,
    supplier,
    SUM(updsum_per_item::numeric) AS sum_deduction
  FROM reports.v_deduction_by_nm_id
  GROUP BY 1,2,3,4,5,6
) d
  ON all_keys.rr_dt = d.updtime::date
 AND all_keys.nm_id = d.nm_id::bigint
 AND all_keys.realizationreport_id = d.realizationreport_id
 AND all_keys.date_from = d.date_from::date
 AND all_keys.date_to = d.date_to::date
LEFT JOIN reports.vw_pvz_rebill_logistic logistic
  ON all_keys.rr_dt = logistic.rr_dt::date
 AND all_keys.nm_id = logistic.nm_id::bigint
 AND all_keys.realizationreport_id = logistic.realizationreport_id
 AND all_keys.date_from = logistic.date_from::date
 AND all_keys.date_to = logistic.date_to::date
LEFT JOIN reports.v_bonus_review_deductions f
  ON all_keys.rr_dt = f.rr_dt::date
 AND all_keys.nm_id = f.product_id::bigint
 AND all_keys.realizationreport_id = f.realizationreport_id
 AND all_keys.date_from = f.date_from::date
 AND all_keys.date_to = f.date_to::date
LEFT JOIN reports.vw_pvz_refund_reward pvz
  ON all_keys.supplier_name = pvz.supplier
 AND all_keys.realizationreport_id = pvz.realizationreport_id
 AND all_keys.nm_id = pvz.nm_id::bigint
 AND all_keys.rr_dt = pvz.rr_dt::date
 AND all_keys.date_from = pvz.date_from::date
 AND all_keys.date_to = pvz.date_to::date
LEFT JOIN reports.v_acquiring_fee fee
  ON all_keys.supplier_name = fee.supplier
 AND all_keys.realizationreport_id = fee.realizationreport_id
 AND all_keys.nm_id = fee.nm_id::bigint
 AND all_keys.rr_dt = fee.rr_dt::date
 AND all_keys.date_from = fee.date_from::date
 AND all_keys.date_to = fee.date_to::date
LEFT JOIN reports.vw_pvz_cashback_discount cashback
  ON all_keys.supplier_name = cashback.supplier
 AND all_keys.realizationreport_id = cashback.realizationreport_id
 AND all_keys.nm_id = cashback.nm_id::bigint
 AND all_keys.rr_dt = cashback.rr_dt::date
 AND all_keys.date_from = cashback.date_from::date
 AND all_keys.date_to = cashback.date_to::date
LEFT JOIN (
  SELECT 
    supplier,
    realizationreport_id,
    nm_id::bigint,
    rr_dt::date AS rr_dt,
    date_from::date,
    date_to::date,
    SUM(delivery_rub) AS delivery_rub
  FROM reports.vw_storno_logistics_nm_id
  GROUP BY 1,2,3,4,5,6
) storno_logistics
  ON all_keys.supplier_name = storno_logistics.supplier
 AND all_keys.realizationreport_id = storno_logistics.realizationreport_id
 AND all_keys.nm_id = storno_logistics.nm_id::bigint
 AND all_keys.rr_dt = storno_logistics.rr_dt::date
 AND all_keys.date_from = storno_logistics.date_from::date
 AND all_keys.date_to = storno_logistics.date_to::date
LEFT JOIN reports.additional_payment_correction additional_payment_correction
  ON all_keys.supplier_name = additional_payment_correction.supplier
 AND all_keys.realizationreport_id = additional_payment_correction.realizationreport_id
 AND all_keys.nm_id = additional_payment_correction.nm_id::bigint
 AND all_keys.rr_dt = additional_payment_correction.rr_dt::date
 AND all_keys.date_from = additional_payment_correction.date_from::date
 AND all_keys.date_to = additional_payment_correction.date_to::date
LEFT JOIN products.v_single_cost_price cp
  ON a.supplier_name = cp.legal_entity
 AND a.nm_id::bigint = cp.nm_id::bigint
)

SELECT * FROM result_data;
