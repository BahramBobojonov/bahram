-- Создание таблиц для хранения результатов расчета deduction

-- Удаляем таблицы если существуют (для пересоздания)
DROP TABLE IF EXISTS analytics.deduction_by_nm_id CASCADE;
DROP TABLE IF EXISTS analytics.deduction_validation CASCADE;

-- ТАБЛИЦА 1: Основной расчет - deduction с разбивкой по товарам
CREATE TABLE analytics.deduction_by_nm_id (
    id SERIAL PRIMARY KEY,
    nm_id VARCHAR(50) NOT NULL,
    supplier VARCHAR(500),
    realizationreport_id BIGINT,
    campaign_id INTEGER,
    deduction NUMERIC(15, 2),
    reklama VARCHAR(50),
    date_from DATE,
    date_to DATE,
    sale_dt TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для быстрого поиска
CREATE INDEX idx_deduction_nm_id ON analytics.deduction_by_nm_id(nm_id);
CREATE INDEX idx_deduction_supplier ON analytics.deduction_by_nm_id(supplier);
CREATE INDEX idx_deduction_report ON analytics.deduction_by_nm_id(realizationreport_id);
CREATE INDEX idx_deduction_campaign ON analytics.deduction_by_nm_id(campaign_id);
CREATE INDEX idx_deduction_reklama ON analytics.deduction_by_nm_id(reklama);
CREATE INDEX idx_deduction_created_at ON analytics.deduction_by_nm_id(created_at);

-- Комментарии к таблице и колонкам
COMMENT ON TABLE analytics.deduction_by_nm_id IS 'Расчет deduction с разбивкой по товарам (nm_id). Сумма делится поровну между всеми товарами в кампании.';
COMMENT ON COLUMN analytics.deduction_by_nm_id.nm_id IS 'Артикул товара';
COMMENT ON COLUMN analytics.deduction_by_nm_id.supplier IS 'Поставщик (юр.лицо)';
COMMENT ON COLUMN analytics.deduction_by_nm_id.realizationreport_id IS 'Номер реализационного отчета';
COMMENT ON COLUMN analytics.deduction_by_nm_id.campaign_id IS 'ID рекламной кампании';
COMMENT ON COLUMN analytics.deduction_by_nm_id.deduction IS 'Сумма списания на данный товар (разделенная поровну)';
COMMENT ON COLUMN analytics.deduction_by_nm_id.reklama IS 'Номер документа УПД';
COMMENT ON COLUMN analytics.deduction_by_nm_id.date_from IS 'Дата начала периода отчета';
COMMENT ON COLUMN analytics.deduction_by_nm_id.date_to IS 'Дата конца периода отчета';
COMMENT ON COLUMN analytics.deduction_by_nm_id.sale_dt IS 'Дата списания средств';
COMMENT ON COLUMN analytics.deduction_by_nm_id.created_at IS 'Дата создания записи';
COMMENT ON COLUMN analytics.deduction_by_nm_id.updated_at IS 'Дата последнего обновления';

-- ТАБЛИЦА 2: Валидация - проверка корректности разбивки
CREATE TABLE analytics.deduction_validation (
    id SERIAL PRIMARY KEY,
    realizationreport_id BIGINT,
    reklama TEXT,
    supplier VARCHAR(500),
    date_from DATE,
    date_to DATE,
    upd_count INTEGER,
    nm_count INTEGER,
    original_sum NUMERIC(15, 2),
    sum_after_split NUMERIC(15, 2),
    difference NUMERIC(15, 2),
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для быстрого поиска
CREATE INDEX idx_validation_report ON analytics.deduction_validation(realizationreport_id);
CREATE INDEX idx_validation_reklama ON analytics.deduction_validation(reklama);
CREATE INDEX idx_validation_supplier ON analytics.deduction_validation(supplier);
CREATE INDEX idx_validation_status ON analytics.deduction_validation(status);
CREATE INDEX idx_validation_created_at ON analytics.deduction_validation(created_at);

-- Комментарии к таблице и колонкам
COMMENT ON TABLE analytics.deduction_validation IS 'Валидация корректности разбивки deduction. Сравнивает исходные суммы с суммами после разбивки на товары. Группировка по realizationreport_id + supplier.';
COMMENT ON COLUMN analytics.deduction_validation.realizationreport_id IS 'Номер реализационного отчета';
COMMENT ON COLUMN analytics.deduction_validation.reklama IS 'Список номеров УПД (может быть несколько через запятую)';
COMMENT ON COLUMN analytics.deduction_validation.supplier IS 'Поставщик (юр.лицо)';
COMMENT ON COLUMN analytics.deduction_validation.date_from IS 'Дата начала периода отчета';
COMMENT ON COLUMN analytics.deduction_validation.date_to IS 'Дата конца периода отчета';
COMMENT ON COLUMN analytics.deduction_validation.upd_count IS 'Количество УПД в отчете';
COMMENT ON COLUMN analytics.deduction_validation.nm_count IS 'Количество товаров после разбивки';
COMMENT ON COLUMN analytics.deduction_validation.original_sum IS 'Исходная ОБЩАЯ сумма из detail_finance_reports по отчету';
COMMENT ON COLUMN analytics.deduction_validation.sum_after_split IS 'Сумма после разбивки на товары (агрегированная по отчету)';
COMMENT ON COLUMN analytics.deduction_validation.difference IS 'Разница между исходной суммой и суммой после разбивки';
COMMENT ON COLUMN analytics.deduction_validation.status IS 'Статус проверки: OK, ОШИБКА, НЕТ_В_ИСТОЧНИКЕ, НЕТ_ПОСЛЕ_РАЗБИВКИ';
COMMENT ON COLUMN analytics.deduction_validation.created_at IS 'Дата создания записи';
COMMENT ON COLUMN analytics.deduction_validation.updated_at IS 'Дата последнего обновления';

-- Создаем представление для быстрого просмотра проблемных записей
CREATE OR REPLACE VIEW analytics.deduction_errors AS
SELECT 
    realizationreport_id,
    reklama AS "Номера УПД",
    supplier AS "Поставщик",
    date_from AS "Дата начала",
    date_to AS "Дата конца",
    upd_count AS "Кол-во УПД",
    nm_count AS "Кол-во товаров",
    original_sum AS "Исходная сумма",
    sum_after_split AS "Сумма после разбивки",
    difference AS "Разница",
    status AS "Статус",
    created_at AS "Дата проверки"
FROM analytics.deduction_validation
WHERE status != 'OK'
ORDER BY ABS(difference) DESC NULLS LAST;

COMMENT ON VIEW analytics.deduction_errors IS 'Представление для быстрого просмотра проблемных записей (статус != OK)';

-- Вывод информации о созданных объектах
SELECT 'Таблицы успешно созданы!' as message;
SELECT 'analytics.deduction_by_nm_id' as table_name, count(*) as rows FROM analytics.deduction_by_nm_id
UNION ALL
SELECT 'analytics.deduction_validation' as table_name, count(*) as rows FROM analytics.deduction_validation;

