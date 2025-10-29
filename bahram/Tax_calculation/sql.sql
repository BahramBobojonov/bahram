WITH base_calculations AS (
	SELECT *, 
			(net_retail_amount::numeric - total_to_transfer::NUMERIC+cashback_discount::numeric) AS itogo_zachteno_iz_stoimosti_realizovannogo_tovara,
			(deduction_adv_total::NUMERIC+deduction_writeoff_total::NUMERIC+deduction_other_total::NUMERIC) AS prochie_uderzhaniya,
			(ppvz_reward::NUMERIC + rebill_logistic_cost::numeric) AS vozmeshenie_rashodov_poverennogo,
			(net_retail_amount::numeric - total_to_transfer::NUMERIC+cashback_discount::NUMERIC-deduction_adv_total::NUMERIC-deduction_writeoff_total::NUMERIC-deduction_other_total::NUMERIC - ppvz_reward::NUMERIC - rebill_logistic_cost::NUMERIC-penalties_total::NUMERIC -acquiring_fee) AS summa_voznagrazhdeniya_wb_s_nds,
			-- Расчет суммы без НДС (в зависимости от даты: 20% до 2026-01-01, 22% после)
			(net_retail_amount::numeric - total_to_transfer::NUMERIC+cashback_discount::NUMERIC-deduction_adv_total::NUMERIC-deduction_writeoff_total::NUMERIC-deduction_other_total::NUMERIC - ppvz_reward::NUMERIC - rebill_logistic_cost::NUMERIC-penalties_total::NUMERIC -acquiring_fee) / 
				CASE 
					WHEN date_from::date >= '2026-01-01' THEN 1.22
					ELSE 1.20
				END AS summa_bez_nds,
			-- Расчет суммы НДС
			(net_retail_amount::numeric - total_to_transfer::NUMERIC+cashback_discount::NUMERIC-deduction_adv_total::NUMERIC-deduction_writeoff_total::NUMERIC-deduction_other_total::NUMERIC - ppvz_reward::NUMERIC - rebill_logistic_cost::NUMERIC-penalties_total::NUMERIC -acquiring_fee) - 
			(net_retail_amount::numeric - total_to_transfer::NUMERIC+cashback_discount::NUMERIC-deduction_adv_total::NUMERIC-deduction_writeoff_total::NUMERIC-deduction_other_total::NUMERIC - ppvz_reward::NUMERIC - rebill_logistic_cost::NUMERIC-penalties_total::NUMERIC -acquiring_fee) / 
				CASE 
					WHEN date_from::date >= '2026-01-01' THEN 1.22
					ELSE 1.20
				END AS summa_nds
	FROM reports.detail_finance_reports_by_nm_id_allocated
	WHERE realizationreport_id = 318998774
)
SELECT *,
		-- Сумма summa_bez_nds по всему отчету
		SUM(summa_bez_nds) OVER (PARTITION BY realizationreport_id) AS total_summa_bez_nds_po_otchetu,
		-- Расчет налоговой базы в зависимости от знака total_summa_bez_nds
		CASE 
			WHEN SUM(summa_bez_nds) OVER (PARTITION BY realizationreport_id) < 0 THEN
				-- Если отрицательная
				net_retail_amount::numeric - summa_bez_nds - summa_nds + 
				COALESCE(kompensaciya_pri_vozvrate::numeric, 0) + 
				COALESCE(kompensaciya_uscherba_prodazha::numeric, 0) - 
				COALESCE(kompensaciya_uscherba_vozvrat::numeric, 0) + 
				COALESCE(additional_payment_total::numeric, 0)
			ELSE
				-- Если положительная
				net_retail_amount::numeric + 
				COALESCE(kompensaciya_pri_vozvrate::numeric, 0) + 
				COALESCE(kompensaciya_uscherba_prodazha::numeric, 0) - 
				COALESCE(kompensaciya_uscherba_vozvrat::numeric, 0) + 
				COALESCE(additional_payment_total::numeric, 0)
		END AS nalogovaya_baza
FROM base_calculations