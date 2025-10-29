#!/usr/bin/env python3
import os
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine, text


DB_URL = os.getenv(
    "DB_URL",
    "postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah",
)

OUTPUT_DIR = "/home/baakhofficial/wbauto/@adhoc"
OUTPUT_XLSX = os.path.join(
    OUTPUT_DIR,
    f"detail_finance_reports_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
)

SUPPLIER = "ИП Мелешкова О.В"
DATE_FROM = "2025-07-01"

SQL_QUERY = text(
    """
    SELECT realizationreport_id, date_from, date_to, create_dt, currency_name, suppliercontract_code, rrd_id, gi_id, dlv_prc, fix_tariff_date_from, fix_tariff_date_to, subject_name, nm_id, brand_name, sa_name, ts_name, barcode, doc_type_name, quantity, retail_price, retail_amount, sale_percent, commission_percent, office_name, supplier_oper_name, order_dt, sale_dt, rr_dt, shk_id, retail_price_withdisc_rub, delivery_amount, return_amount, delivery_rub, gi_box_type_name, product_discount_for_report, supplier_promo, rid, ppvz_spp_prc, ppvz_kvw_prc_base, ppvz_kvw_prc, sup_rating_prc_up, is_kgvp_v2, ppvz_sales_commission, ppvz_for_pay, ppvz_reward, acquiring_fee, acquiring_percent, payment_processing, acquiring_bank, ppvz_vw, ppvz_vw_nds, ppvz_office_name, ppvz_office_id, ppvz_supplier_id, ppvz_supplier_name, ppvz_inn, declaration_number, bonus_type_name, sticker_id, site_country, srv_dbs, penalty, additional_payment, rebill_logistic_cost, storage_fee, deduction, acceptance, assembly_id, srid, report_type, is_legal_entity, trbx_id, rebill_logistic_org, supplier, update_time, kiz, is_srv_dbs, cashback_commission_change, installment_cofinancing_amount, cashback_amount, order_uid, cashback_discount, wibes_wb_discount_percent
    FROM reports.detail_finance_reports
    WHERE supplier = :supplier
      AND date_from::date >= :date_from
    """
)


def coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    # Дата/время
    date_cols = [
        "date_from",
        "date_to",
        "create_dt",
        "fix_tariff_date_from",
        "fix_tariff_date_to",
        "rr_dt",
    ]
    datetime_cols = [
        "order_dt",
        "sale_dt",
        "update_time",
    ]

    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    for col in datetime_cols:
        if col in df.columns:
            series = pd.to_datetime(df[col], errors="coerce", utc=False)
            # Удаляем таймзону для совместимости с Excel
            try:
                if pd.api.types.is_datetime64tz_dtype(series):
                    series = series.dt.tz_convert(None)
            except Exception:
                pass
            df[col] = series

    # Целочисленные (nullable Int64)
    int_cols = [
        "realizationreport_id",
        "rrd_id",
        "gi_id",
        "quantity",
        "delivery_amount",
        "return_amount",
        "shk_id",
        "ppvz_office_id",
        "ppvz_supplier_id",
        "assembly_id",
        "report_type",
        "nm_id",
    ]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Вещественные
    float_cols = [
        "dlv_prc",
        "retail_price",
        "retail_amount",
        "sale_percent",
        "commission_percent",
        "retail_price_withdisc_rub",
        "delivery_rub",
        "product_discount_for_report",
        "supplier_promo",
        "ppvz_spp_prc",
        "ppvz_kvw_prc_base",
        "ppvz_kvw_prc",
        "sup_rating_prc_up",
        "is_kgvp_v2",
        "ppvz_sales_commission",
        "ppvz_for_pay",
        "ppvz_reward",
        "acquiring_fee",
        "acquiring_percent",
        "ppvz_vw",
        "ppvz_vw_nds",
        "penalty",
        "additional_payment",
        "rebill_logistic_cost",
        "storage_fee",
        "deduction",
        "acceptance",
        "cashback_commission_change",
        "installment_cofinancing_amount",
        "cashback_amount",
        "cashback_discount",
        "wibes_wb_discount_percent",
    ]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Булевы
    bool_cols = [
        "srv_dbs",
        "is_legal_entity",
        "is_srv_dbs",
    ]
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].map({True: True, False: False, 1: True, 0: False, "t": True, "f": False}).astype("boolean")

    # Остальные как строки
    # Набор полей, которые должны быть строками (если присутствуют)
    str_cols = [
        "currency_name",
        "suppliercontract_code",
        "subject_name",
        "brand_name",
        "sa_name",
        "ts_name",
        "barcode",
        "doc_type_name",
        "office_name",
        "supplier_oper_name",
        "gi_box_type_name",
        "payment_processing",
        "acquiring_bank",
        "ppvz_office_name",
        "ppvz_supplier_name",
        "ppvz_inn",
        "declaration_number",
        "bonus_type_name",
        "sticker_id",
        "site_country",
        "srid",
        "trbx_id",
        "rebill_logistic_org",
        "supplier",
        "kiz",
        "order_uid",
        "rid",
    ]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype("string")

    return df


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        df = pd.read_sql_query(SQL_QUERY, con=conn, params={"supplier": SUPPLIER, "date_from": DATE_FROM})

    # Переименование колонок на русские названия согласно документации
    rename_map = {
        "realizationreport_id": "Номер отчёта",
        "date_from": "Дата начала отчётного периода",
        "date_to": "Дата конца отчётного периода",
        "create_dt": "Дата формирования отчёта",
        "currency_name": "Валюта отчёта",
        "suppliercontract_code": "Договор",
        "rrd_id": "Номер строки",
        "gi_id": "Номер поставки",
        "dlv_prc": "Фиксированный коэффициент склада по поставке",
        "fix_tariff_date_from": "Дата начала действия фиксации",
        "fix_tariff_date_to": "Дата конца действия фиксации",
        "subject_name": "Предмет",
        "nm_id": "Артикул WB",
        "brand_name": "Бренд",
        "sa_name": "Артикул продавца",
        "ts_name": "Размер",
        "barcode": "Баркод",
        "doc_type_name": "Тип документа",
        "quantity": "Количество",
        "retail_price": "Цена розничная",
        "retail_amount": "Вайлдберриз реализовал Товар (Пр)",
        "sale_percent": "Согласованный продуктовый дисконт, %",
        "commission_percent": "Размер кВВ, %",
        "office_name": "Склад",
        "supplier_oper_name": "Обоснование для оплаты",
        "order_dt": "Дата заказа",
        "sale_dt": "Дата продажи",
        "rr_dt": "Дата операции",
        "shk_id": "Штрихкод",
        "retail_price_withdisc_rub": "Цена розничная с учётом согласованной скидки",
        "delivery_amount": "Количество доставок",
        "return_amount": "Количество возврата",
        "delivery_rub": "Услуги по доставке товара покупателю",
        "gi_box_type_name": "Тип коробов",
        "product_discount_for_report": "Итоговая согласованная скидка, %",
        "supplier_promo": "Промокод, %",
        "ppvz_spp_prc": "Скидка постоянного Покупателя (СПП), %",
        "ppvz_kvw_prc_base": "Размер кВВ без НДС, % базовый",
        "ppvz_kvw_prc": "Итоговый кВВ без НДС, %",
        "sup_rating_prc_up": "Размер снижения кВВ из-за рейтинга, %",
        "is_kgvp_v2": "Размер снижения кВВ из-за акции, %",
        "ppvz_sales_commission": "Вознаграждение с продаж до вычета услуг поверенного, без НДС",
        "ppvz_for_pay": "К перечислению продавцу за реализованный товар",
        "ppvz_reward": "Возмещение за выдачу и возврат товаров на ПВЗ",
        "acquiring_fee": "Эквайринг/Комиссии за организацию платежей",
        "acquiring_percent": "Размер комиссии за эквайринг/Комиссии за организацию платежей, %",
        "payment_processing": "Тип платежа за Эквайринг/Комиссии за организацию платежей",
        "acquiring_bank": "Наименование банка-эквайера",
        "ppvz_vw": "Вознаграждение Вайлдберриз (ВВ), без НДС",
        "ppvz_vw_nds": "НДС с вознаграждения Вайлдберриз",
        "ppvz_office_name": "Наименование офиса доставки",
        "ppvz_office_id": "Номер офиса доставки",
        "ppvz_supplier_id": "Номер партнёра",
        "ppvz_supplier_name": "Партнёр",
        "ppvz_inn": "ИНН партнёра",
        "declaration_number": "Номер таможенной декларации",
        "bonus_type_name": "Виды логистики, штрафов и корректировок ВВ",
        "sticker_id": "Цифровое значение стикера",
        "site_country": "Страна продажи",
        "srv_dbs": "Признак услуги платной доставки",
        "penalty": "Общая сумма штрафов",
        "additional_payment": "Корректировка Вознаграждения Вайлдберриз (ВВ)",
        "rebill_logistic_cost": "Возмещение издержек по перевозке/по складским операциям с товаром",
        "rebill_logistic_org": "Организатор перевозки",
        "storage_fee": "Хранение",
        "deduction": "Удержания",
        "acceptance": "Платная приёмка",
        "assembly_id": "Номер сборочного задания",
        "kiz": "Код маркировки",
        "srid": "Уникальный ID заказа",
        "report_type": "Тип отчёта",
        "is_legal_entity": "Признак B2B-продажи",
        "trbx_id": "Номер короба для платной приёмки",
        "supplier": "Поставщик",
        "update_time": "Время обновления",
        "is_srv_dbs": "Признак услуги DBS",
        "cashback_commission_change": "Стоимость участия в программе лояльности",
        "installment_cofinancing_amount": "Скидка по программе софинансирования",
        "cashback_amount": "Сумма, удержанная за начисленные баллы программы лояльности",
        "order_uid": "ID транзакции",
        "cashback_discount": "Компенсация скидки по программе лояльности",
        "wibes_wb_discount_percent": "Скидка Wibes, %",
        "rid": "Номер заказа",
    }
    df.rename(columns=rename_map, inplace=True)

    df = coerce_types(df)

    # Сохранение в Excel
    df.to_excel(OUTPUT_XLSX, index=False)
    print(f"Saved: {OUTPUT_XLSX}")


if __name__ == "__main__":
    main()


