-- ПРОВЕРОЧНЫЙ ЗАПРОС: Валидация корректности разбивки
-- Сравнивает агрегированные данные из analytics.deduction_by_nm_id
-- с исходными данными из reports.detail_finance_reports
-- ГРУППИРОВКА ПО realizationreport_id + supplier (один отчет может содержать несколько УПД)

WITH 
-- Агрегируем данные из основной таблицы (результат расчета) по отчету
result_aggregated AS (
    SELECT 
        realizationreport_id,
        supplier,
        COUNT(DISTINCT reklama) as upd_count,
        COUNT(DISTINCT nm_id) as nm_count,
        STRING_AGG(DISTINCT reklama, ', ' ORDER BY reklama) as reklama_list,
        ROUND(SUM(deduction)::numeric, 2) as sum_after_split
    FROM analytics.deduction_by_nm_id
    WHERE realizationreport_id IS NOT NULL
    GROUP BY realizationreport_id, supplier
),
-- Исходные данные из detail_finance_reports - тоже группируем по отчету
source_data AS (
    SELECT 
        realizationreport_id, 
        supplier,
        MIN(date_from) as date_from,
        MIN(date_to) as date_to,
        COUNT(*) as records_count,
        SUM(deduction::numeric) as original_deduction
    FROM reports.detail_finance_reports
    WHERE bonus_type_name = 'Оказание услуг «ВБ.Продвижение»'
      AND date_from::date >= DATE '2025-09-01'
    GROUP BY realizationreport_id, supplier
),
-- Данные которые есть после разбивки но нет в источнике
orphan_records AS (
    SELECT 
        NULL::bigint as realizationreport_id,
        supplier,
        COUNT(DISTINCT reklama) as upd_count,
        COUNT(DISTINCT nm_id) as nm_count,
        STRING_AGG(DISTINCT reklama, ', ' ORDER BY reklama) as reklama_list,
        ROUND(SUM(deduction)::numeric, 2) as sum_after_split
    FROM analytics.deduction_by_nm_id
    WHERE realizationreport_id IS NULL
    GROUP BY supplier
)
-- СРАВНЕНИЕ: Исходные суммы VS Суммы после разбивки
SELECT 
    COALESCE(sd.realizationreport_id, ra.realizationreport_id, orph.realizationreport_id) as realizationreport_id,
    COALESCE(ra.reklama_list, orph.reklama_list) as "Номера УПД",
    COALESCE(sd.supplier, ra.supplier, orph.supplier) as supplier,
    sd.date_from as "Дата начала",
    sd.date_to as "Дата конца",
    COALESCE(ra.upd_count, orph.upd_count) as "Кол-во УПД",
    COALESCE(ra.nm_count, orph.nm_count) as "Кол-во товаров",
    sd.original_deduction as "Исходная сумма",
    COALESCE(ra.sum_after_split, orph.sum_after_split) as "Сумма после разбивки",
    ROUND((COALESCE(ra.sum_after_split, orph.sum_after_split, 0) - COALESCE(sd.original_deduction, 0))::numeric, 2) as "Разница",
    CASE 
        -- Если нет в источнике (detail_finance_reports)
        WHEN sd.original_deduction IS NULL AND (ra.sum_after_split IS NOT NULL OR orph.sum_after_split IS NOT NULL) THEN 'НЕТ_В_ИСТОЧНИКЕ'
        -- Если нет после разбивки (в deduction_by_nm_id)
        WHEN sd.original_deduction IS NOT NULL AND ra.sum_after_split IS NULL AND orph.sum_after_split IS NULL THEN 'НЕТ_ПОСЛЕ_РАЗБИВКИ'
        -- Если разница меньше или равна 1 копейке - считаем OK (погрешность округления)
        WHEN ABS(COALESCE(ra.sum_after_split, orph.sum_after_split, 0) - COALESCE(sd.original_deduction, 0)) <= 0.01 THEN 'OK'
        -- Иначе ошибка
        ELSE 'ОШИБКА'
    END as "Статус"
FROM source_data sd
FULL JOIN result_aggregated ra
    ON sd.realizationreport_id = ra.realizationreport_id
    AND COALESCE(sd.supplier, '') = COALESCE(ra.supplier, '')
FULL JOIN orphan_records orph
    ON COALESCE(sd.supplier, '') = COALESCE(orph.supplier, '')
    AND sd.realizationreport_id IS NULL
    AND ra.realizationreport_id IS NULL
ORDER BY 
    CASE 
        -- Сначала настоящие ошибки (большая разница)
        WHEN ABS(COALESCE(ra.sum_after_split, orph.sum_after_split, 0) - COALESCE(sd.original_deduction, 0)) > 0.01 
             AND sd.original_deduction IS NOT NULL 
             AND (ra.sum_after_split IS NOT NULL OR orph.sum_after_split IS NOT NULL) THEN 1 
        -- Потом записи, которых нет в источнике или после разбивки
        WHEN sd.original_deduction IS NULL OR (ra.sum_after_split IS NULL AND orph.sum_after_split IS NULL) THEN 2
        -- В конце OK записи
        ELSE 3 
    END,
    ABS(COALESCE(ra.sum_after_split, orph.sum_after_split, 0) - COALESCE(sd.original_deduction, 0)) DESC NULLS LAST,
    realizationreport_id;
