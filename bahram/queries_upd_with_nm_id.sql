-- ============================================================================
-- SQL ЗАПРОСЫ ДЛЯ РАБОТЫ С analytics.adv_upd_with_nm_id
-- Таблица содержит все записи UPD с добавленными nm_id (LEFT JOIN)
-- ============================================================================

-- 1. ПРОВЕРКА ЗАГРУЖЕННЫХ ДАННЫХ
-- ============================================================================

-- Общая статистика по таблице
SELECT 
    COUNT(*) as total_records,
    COUNT(DISTINCT supplier) as unique_suppliers,
    COUNT(DISTINCT advertid) as unique_campaigns,
    COUNT(DISTINCT nm_id) as unique_nm_ids,
    COUNT(CASE WHEN nm_id IS NOT NULL THEN 1 END) as records_with_nm_id,
    COUNT(CASE WHEN nm_id IS NULL THEN 1 END) as records_without_nm_id,
    MIN(updtime) as earliest_date,
    MAX(updtime) as latest_date,
    SUM(updsum) as total_sum
FROM analytics.adv_upd_with_nm_id;


-- Статистика по компаниям
SELECT 
    supplier,
    COUNT(*) as total_records,
    COUNT(DISTINCT advertid) as campaigns_count,
    COUNT(DISTINCT nm_id) as unique_nm_ids,
    SUM(updsum) as total_deductions,
    MIN(updtime) as first_date,
    MAX(updtime) as last_date
FROM analytics.adv_upd_with_nm_id
GROUP BY supplier
ORDER BY total_deductions DESC;


-- 2. АНАЛИЗ ПО АРТИКУЛАМ (NM_ID)
-- ============================================================================

-- Топ артикулов по сумме списаний
SELECT 
    nm_id,
    supplier,
    COUNT(*) as deduction_count,
    SUM(updsum) as total_deductions,
    AVG(updsum) as avg_deduction,
    MIN(updtime) as first_deduction,
    MAX(updtime) as last_deduction,
    COUNT(DISTINCT advertid) as campaigns_count,
    STRING_AGG(DISTINCT campname, ', ') as campaign_names
FROM analytics.adv_upd_with_nm_id
WHERE nm_id IS NOT NULL
GROUP BY nm_id, supplier
ORDER BY total_deductions DESC
LIMIT 100;


-- Динамика списаний по артикулу
SELECT 
    DATE(updtime) as deduction_date,
    nm_id,
    supplier,
    COUNT(*) as records_count,
    SUM(updsum) as daily_deductions,
    STRING_AGG(DISTINCT campname, ', ') as campaigns
FROM analytics.adv_upd_with_nm_id
WHERE nm_id = 123456789  -- ЗАМЕНИТЕ НА НУЖНЫЙ nm_id
GROUP BY DATE(updtime), nm_id, supplier
ORDER BY deduction_date DESC;


-- 3. АНАЛИЗ ПО КАМПАНИЯМ
-- ============================================================================

-- Детальная информация по кампаниям с артикулами
SELECT 
    advertid,
    campname,
    supplier,
    adverttype,
    paymenttype,
    COUNT(*) as total_records,
    COUNT(DISTINCT nm_id) as unique_nm_ids,
    COUNT(CASE WHEN nm_id IS NOT NULL THEN 1 END) as records_with_nm,
    SUM(updsum) as total_deductions,
    MIN(updtime) as first_deduction,
    MAX(updtime) as last_deduction
FROM analytics.adv_upd_with_nm_id
GROUP BY advertid, campname, supplier, adverttype, paymenttype
ORDER BY total_deductions DESC;


-- Кампании БЕЗ артикулов (проблемные)
SELECT 
    advertid,
    campname,
    supplier,
    adverttype,
    advertstatus,
    COUNT(*) as records_count,
    SUM(updsum) as total_sum
FROM analytics.adv_upd_with_nm_id
WHERE nm_id IS NULL
GROUP BY advertid, campname, supplier, adverttype, advertstatus
ORDER BY total_sum DESC;


-- 4. ДЕТАЛЬНЫЙ РАЗБОР СПИСАНИЙ
-- ============================================================================

-- Все списания с полной информацией (последние 1000)
SELECT 
    updnum,
    updtime,
    updsum,
    advertid,
    campname,
    adverttype,
    advertstatus,
    paymenttype,
    nm_id,
    supplier,
    loaded_at
FROM analytics.adv_upd_with_nm_id
ORDER BY updtime DESC
LIMIT 1000;


-- Списания по конкретной кампании со всеми артикулами
SELECT 
    updnum,
    updtime,
    updsum,
    nm_id,
    campname,
    paymenttype
FROM analytics.adv_upd_with_nm_id
WHERE advertid = 12345  -- ЗАМЕНИТЕ НА ID КАМПАНИИ
ORDER BY updtime DESC, nm_id;


-- 5. СРАВНЕНИЕ С ИСХОДНОЙ ТАБЛИЦЕЙ analytics.adv_upd
-- ============================================================================

-- Сравнение количества записей (должно быть больше или равно)
SELECT 
    'adv_upd' as table_name,
    COUNT(*) as records_count,
    SUM(updsum) as total_sum
FROM analytics.adv_upd
UNION ALL
SELECT 
    'adv_upd_with_nm_id' as table_name,
    COUNT(DISTINCT (updnum, updtime, advertid, supplier)) as records_count,
    SUM(updsum) as total_sum
FROM analytics.adv_upd_with_nm_id;


-- Проверка: суммы должны совпадать при группировке
WITH original AS (
    SELECT 
        advertid,
        supplier,
        SUM(updsum) as total_sum_original
    FROM analytics.adv_upd
    GROUP BY advertid, supplier
),
with_nm AS (
    SELECT 
        advertid,
        supplier,
        SUM(updsum) as total_sum_with_nm
    FROM analytics.adv_upd_with_nm_id
    GROUP BY advertid, supplier
)
SELECT 
    COALESCE(o.advertid, w.advertid) as advertid,
    COALESCE(o.supplier, w.supplier) as supplier,
    o.total_sum_original,
    w.total_sum_with_nm,
    CASE 
        WHEN ABS(COALESCE(o.total_sum_original, 0) - COALESCE(w.total_sum_with_nm, 0)) < 0.01 
        THEN '✓ OK' 
        ELSE '✗ MISMATCH' 
    END as status
FROM original o
FULL OUTER JOIN with_nm w 
    ON o.advertid = w.advertid 
    AND o.supplier = w.supplier
ORDER BY status, advertid;


-- 6. РАСЧЕТ СПИСАНИЙ НА АРТИКУЛ (КАК В deduction_by_nm_id)
-- ============================================================================

-- Вариант 1: Деление поровну между артикулами в записи UPD
WITH nm_counts AS (
    -- Считаем сколько артикулов в каждой записи UPD
    SELECT 
        updnum,
        updtime,
        advertid,
        supplier,
        updsum,
        campname,
        paymenttype,
        COUNT(*) OVER (PARTITION BY updnum, updtime, advertid, supplier) as nm_count
    FROM analytics.adv_upd_with_nm_id
    WHERE nm_id IS NOT NULL
)
SELECT 
    u.nm_id,
    u.supplier,
    u.advertid,
    u.campname,
    COUNT(*) as upd_records_count,
    SUM(nc.updsum / nc.nm_count) as deduction_per_nm_id,
    MIN(u.updtime) as first_deduction,
    MAX(u.updtime) as last_deduction
FROM analytics.adv_upd_with_nm_id u
JOIN nm_counts nc 
    ON u.updnum = nc.updnum 
    AND u.updtime = nc.updtime 
    AND u.advertid = nc.advertid 
    AND u.supplier = nc.supplier
WHERE u.nm_id IS NOT NULL
GROUP BY u.nm_id, u.supplier, u.advertid, u.campname
ORDER BY deduction_per_nm_id DESC;


-- Вариант 2: Простое суммирование (без деления)
-- Каждая запись UPD умножается на количество артикулов
SELECT 
    nm_id,
    supplier,
    COUNT(DISTINCT advertid) as campaigns_count,
    COUNT(*) as records_count,
    SUM(updsum) as total_deductions,
    AVG(updsum) as avg_deduction_per_record
FROM analytics.adv_upd_with_nm_id
WHERE nm_id IS NOT NULL
GROUP BY nm_id, supplier
ORDER BY total_deductions DESC;


-- 7. АНАЛИЗ ПО ТИПАМ КАМПАНИЙ
-- ============================================================================

-- Статистика по типам кампаний
SELECT 
    adverttype,
    CASE 
        WHEN adverttype = 4 THEN 'Автоматическая (каталог)'
        WHEN adverttype = 5 THEN 'Автоматическая (карточка товара)'
        WHEN adverttype = 6 THEN 'Автоматическая (поиск)'
        WHEN adverttype = 7 THEN 'Автоматическая (поиск + каталог)'
        WHEN adverttype = 8 THEN 'Автоматическая (аукцион)'
        WHEN adverttype = 9 THEN 'Ручные ставки'
        ELSE 'Неизвестный тип'
    END as type_name,
    COUNT(DISTINCT advertid) as campaigns_count,
    COUNT(*) as records_count,
    COUNT(DISTINCT nm_id) as unique_nm_ids,
    SUM(updsum) as total_deductions,
    AVG(updsum) as avg_deduction
FROM analytics.adv_upd_with_nm_id
GROUP BY adverttype
ORDER BY adverttype;


-- 8. АНАЛИЗ ПО ИСТОЧНИКАМ СПИСАНИЯ
-- ============================================================================

-- Статистика по источникам списания
SELECT 
    paymenttype,
    COUNT(DISTINCT advertid) as campaigns_count,
    COUNT(*) as records_count,
    COUNT(DISTINCT nm_id) as unique_nm_ids,
    SUM(updsum) as total_deductions,
    AVG(updsum) as avg_deduction
FROM analytics.adv_upd_with_nm_id
GROUP BY paymenttype
ORDER BY total_deductions DESC;


-- 9. ВРЕМЕННОЙ АНАЛИЗ
-- ============================================================================

-- Динамика списаний по дням
SELECT 
    DATE(updtime) as deduction_date,
    COUNT(*) as records_count,
    COUNT(DISTINCT advertid) as campaigns_count,
    COUNT(DISTINCT nm_id) as unique_nm_ids,
    SUM(updsum) as daily_deductions
FROM analytics.adv_upd_with_nm_id
GROUP BY DATE(updtime)
ORDER BY deduction_date DESC;


-- Динамика по неделям
SELECT 
    DATE_TRUNC('week', updtime) as week_start,
    COUNT(*) as records_count,
    COUNT(DISTINCT advertid) as campaigns_count,
    COUNT(DISTINCT nm_id) as unique_nm_ids,
    SUM(updsum) as weekly_deductions
FROM analytics.adv_upd_with_nm_id
GROUP BY DATE_TRUNC('week', updtime)
ORDER BY week_start DESC;


-- 10. ЭКСПОРТ ДЛЯ АНАЛИЗА
-- ============================================================================

-- Полная таблица для экспорта в Excel/CSV
SELECT 
    updnum as "Номер УПД",
    updtime as "Дата и время",
    updsum as "Сумма списания",
    advertid as "ID кампании",
    campname as "Название кампании",
    adverttype as "Тип кампании",
    paymenttype as "Источник списания",
    advertstatus as "Статус",
    nm_id as "Артикул WB",
    supplier as "Юр. лицо",
    loaded_at as "Дата загрузки"
FROM analytics.adv_upd_with_nm_id
ORDER BY updtime DESC;

