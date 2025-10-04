#!/usr/bin/env python3

import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import os
import gspread

# Подключение к базе данных
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

# Google Sheets setup
cred_path = os.path.join(os.path.dirname(__file__), 'cred.json')
gs_client = gspread.service_account(filename=cred_path)
worksheet = gs_client.open_by_key("15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ").worksheet("Инвесторы")
df_investors = pd.DataFrame(worksheet.get_all_records())

# Получаем данные о налоговых ставках для каждого ИП
df_investors = df_investors[(df_investors['Имя Юрлица'] != '') & (df_investors['Имя Юрлица'].notnull())]

# Обрабатываем налоговые ставки, заменяя пустые значения на 0
tax_rates_raw = dict(zip(df_investors['Имя Юрлица'], df_investors['Налоговая ставка']))
tax_rates = {}
for supplier, rate in tax_rates_raw.items():
    if pd.isna(rate) or rate == '' or rate is None:
        tax_rates[supplier] = 0.0  # Пустые значения = 0
    else:
        try:
            tax_rates[supplier] = float(rate) / 100  # Конвертируем в десятичную дробь
        except (ValueError, TypeError):
            tax_rates[supplier] = 0.0  # Ошибка = 0

# Обрабатываем НДС, заменяя пустые значения на 0
vat_rates_raw = dict(zip(df_investors['Имя Юрлица'], df_investors['НДС']))
vat_rates = {}
for supplier, rate in vat_rates_raw.items():
    if pd.isna(rate) or rate == '' or rate is None:
        vat_rates[supplier] = 0.0  # Пустые значения = 0
    else:
        try:
            vat_rates[supplier] = float(rate) / 100  # Конвертируем в десятичную дробь
        except (ValueError, TypeError):
            vat_rates[supplier] = 0.0  # Ошибка = 0

print(f"Загружены налоговые ставки для {len(tax_rates)} поставщиков")

def get_last_month_dates():
    """
    Получает даты начала и конца последнего месяца
    """
    today = datetime.now()
    # Первый день текущего месяца
    first_day_current_month = today.replace(day=1)
    # Последний день предыдущего месяца
    last_day_previous_month = first_day_current_month - timedelta(days=1)
    # Первый день предыдущего месяца
    first_day_previous_month = last_day_previous_month.replace(day=1)
    
    return first_day_previous_month.strftime('%Y-%m-%d'), last_day_previous_month.strftime('%Y-%m-%d')

def create_monthly_report_table():
    """
    Создает таблицу для хранения месячных отчетов
    """
    create_table_query = text("""
    CREATE TABLE IF NOT EXISTS reports.monthly_financial_report (
        supplier_name VARCHAR(255) NOT NULL,
        realizationreport_id DOUBLE PRECISION NOT NULL,
        report_date DATE NOT NULL,
        prodazha_do_komissii NUMERIC(15,2),
        vozvrat_do_komissii NUMERIC(15,2),
        prodazha_posle_komissii NUMERIC(15,2),
        vozvrat_posle_komissii NUMERIC(15,2),
        acquiring_fee_sum NUMERIC(15,2),
        komossia NUMERIC(15,2),
        margin_after_commission NUMERIC(15,4),
        k_perecheisleniyu_za_tovar NUMERIC(15,2),
        logistics_total NUMERIC(15,2),
        penalties_total NUMERIC(15,2),
        additional_payment_total NUMERIC(15,2),
        storage_fee_total NUMERIC(15,2),
        acceptance_total NUMERIC(15,2),
        deduction_total NUMERIC(15,2),
        total_to_transfer NUMERIC(15,2),
        net_retail_amount NUMERIC(15,2),
        net_amount_after_vat NUMERIC(15,2),
        tax_to_pay NUMERIC(15,2),
        vat_amount NUMERIC(15,2),
        profit_after_all NUMERIC(15,2),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(supplier_name, realizationreport_id, report_date)
    );
    """)
    
    with engine.connect() as conn:
        conn.execute(create_table_query)
        conn.commit()
    print("✓ Таблица monthly_financial_report создана/проверена")

def get_simple_report_query(date_from, date_to, supplier_name, vat_rate, tax_rate):
    """
    Возвращает SQL-запрос с группировкой по поставщику и номеру отчета
    """
    query = f"""
    SELECT 
        supplier AS supplier_name,
        realizationreport_id,
        MAX(create_dt::date) AS report_date,
        SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_price_withdisc_rub::numeric ELSE 0 END) AS prodazha_do_komissii,
        SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_price_withdisc_rub::numeric ELSE 0 END) AS vozvrat_do_komissii,
        SUM(CASE WHEN doc_type_name = 'Продажа' THEN ppvz_for_pay::numeric ELSE 0 END) AS prodazha_posle_komissii,
        SUM(CASE WHEN doc_type_name = 'Возврат' THEN ppvz_for_pay::numeric ELSE 0 END) AS vozvrat_posle_komissii,
        SUM(acquiring_fee::numeric) AS acquiring_fee_sum,
        SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_price_withdisc_rub::numeric ELSE 0 END) - 
        SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_price_withdisc_rub::numeric ELSE 0 END) - 
        (SUM(CASE WHEN doc_type_name = 'Продажа' THEN ppvz_for_pay::numeric ELSE 0 END) - 
         SUM(CASE WHEN doc_type_name = 'Возврат' THEN ppvz_for_pay::numeric ELSE 0 END)) AS komossia,
        
        CASE 
            WHEN SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_price_withdisc_rub::numeric ELSE 0 END) - 
                 SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_price_withdisc_rub::numeric ELSE 0 END) > 0 THEN
                (SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_price_withdisc_rub::numeric ELSE 0 END) - 
                 SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_price_withdisc_rub::numeric ELSE 0 END) - 
                 (SUM(CASE WHEN doc_type_name = 'Продажа' THEN ppvz_for_pay::numeric ELSE 0 END) - 
                  SUM(CASE WHEN doc_type_name = 'Возврат' THEN ppvz_for_pay::numeric ELSE 0 END))) / 
                (SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_price_withdisc_rub::numeric ELSE 0 END) - 
                 SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_price_withdisc_rub::numeric ELSE 0 END))
            ELSE 0
        END AS margin_after_commission,
        
        SUM(CASE WHEN doc_type_name = 'Продажа' THEN ppvz_for_pay::numeric ELSE 0 END) - 
        SUM(CASE WHEN doc_type_name = 'Возврат' THEN ppvz_for_pay::numeric ELSE 0 END) AS k_perecheisleniyu_za_tovar,
        
        SUM(
            CASE 
                WHEN supplier_oper_name = 'Логистика' THEN delivery_rub::numeric
                WHEN supplier_oper_name = 'Логистика сторно' THEN -delivery_rub::numeric
                WHEN supplier_oper_name = 'Коррекция логистики' THEN delivery_rub::numeric
                ELSE 0
            END
        ) AS logistics_total,
        
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
        SUM(acceptance::numeric) AS acceptance_total,
        SUM(deduction::numeric) AS deduction_total,
        
        SUM(CASE WHEN doc_type_name = 'Продажа' THEN ppvz_for_pay::numeric ELSE 0 END) - 
        SUM(CASE WHEN doc_type_name = 'Возврат' THEN ppvz_for_pay::numeric ELSE 0 END) - 
        SUM(
            CASE 
                WHEN supplier_oper_name = 'Логистика' THEN delivery_rub::numeric
                WHEN supplier_oper_name = 'Логистика сторно' THEN -delivery_rub::numeric
                WHEN supplier_oper_name = 'Коррекция логистики' THEN delivery_rub::numeric
                ELSE 0
            END
        ) - 
        SUM(
            CASE 
                WHEN supplier_oper_name = 'Штраф' THEN penalty::numeric
                WHEN supplier_oper_name = 'Штрафы и доплаты' THEN penalty::numeric
                ELSE 0
            END
        ) - 
        SUM(
            CASE 
                WHEN supplier_oper_name = 'Доплаты' THEN additional_payment::numeric
                ELSE 0
            END
        ) - 
        SUM(storage_fee::numeric) - 
        SUM(acceptance::numeric) - 
        SUM(deduction::numeric) AS total_to_transfer,
        
        SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END) - 
        SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END) AS net_retail_amount,
        
        CASE 
            WHEN SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END) - 
                 SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END) > 0 THEN
                SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END) - 
                SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END) - 
                (SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END) - 
                 SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)) * {vat_rate} / (1 + {vat_rate})
            ELSE SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END) - 
                 SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)
        END AS net_amount_after_vat,
        
        CASE 
            WHEN SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END) - 
                 SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END) > 0 THEN
                ((SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END) - 
                  SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)) - 
                 (SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END) - 
                  SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)) * {vat_rate} / (1 + {vat_rate})) * {tax_rate}
            ELSE 0
        END AS tax_to_pay,
        
        CASE 
            WHEN SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END) - 
                 SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END) > 0 THEN
                (SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END) - 
                 SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)) * {vat_rate} / (1 + {vat_rate})
            ELSE 0
        END AS vat_amount,
        
        CASE 
            WHEN SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_price_withdisc_rub::numeric ELSE 0 END) - 
                 SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_price_withdisc_rub::numeric ELSE 0 END) > 0 THEN
                SUM(CASE WHEN doc_type_name = 'Продажа' THEN ppvz_for_pay::numeric ELSE 0 END) - 
                SUM(CASE WHEN doc_type_name = 'Возврат' THEN ppvz_for_pay::numeric ELSE 0 END) - 
                SUM(
                    CASE 
                        WHEN supplier_oper_name = 'Логистика' THEN delivery_rub::numeric
                        WHEN supplier_oper_name = 'Логистика сторно' THEN -delivery_rub::numeric
                        WHEN supplier_oper_name = 'Коррекция логистики' THEN delivery_rub::numeric
                        ELSE 0
                    END
                ) - 
                SUM(
                    CASE 
                        WHEN supplier_oper_name = 'Штраф' THEN penalty::numeric
                        WHEN supplier_oper_name = 'Штрафы и доплаты' THEN penalty::numeric
                        ELSE 0
                    END
                ) - 
                SUM(
                    CASE 
                        WHEN supplier_oper_name = 'Доплаты' THEN additional_payment::numeric
                        ELSE 0
                    END
                ) - 
                SUM(storage_fee::numeric) - 
                SUM(acceptance::numeric) - 
                SUM(deduction::numeric) -
                CASE 
                    WHEN SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END) - 
                         SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END) > 0 THEN
                        ((SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END) - 
                          SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)) - 
                         (SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END) - 
                          SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)) * {vat_rate} / (1 + {vat_rate})) * {tax_rate}
                    ELSE 0
                END -
                CASE 
                    WHEN SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END) - 
                         SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END) > 0 THEN
                        (SUM(CASE WHEN doc_type_name = 'Продажа' THEN retail_amount::numeric ELSE 0 END) - 
                         SUM(CASE WHEN doc_type_name = 'Возврат' THEN retail_amount::numeric ELSE 0 END)) * {vat_rate} / (1 + {vat_rate})
                    ELSE 0
                END
            ELSE 0
        END AS profit_after_all
        
    FROM reports.detail_finance_reports
    WHERE date_from >= '{date_from}' AND date_from <= '{date_to}'
    AND supplier = '{supplier_name}'
    GROUP BY supplier, realizationreport_id
    """
    return query

def run_simple_monthly_report():
    """
    Основная функция для выполнения упрощенного месячного отчета
    """
    print("=" * 80)
    print("ЗАПУСК УПРОЩЕННОГО МЕСЯЧНОГО ФИНАНСОВОГО ОТЧЕТА")
    print("=" * 80)
    
    # Получаем даты последнего месяца
    date_from, date_to = get_last_month_dates()
    print(f"📅 Период отчета: {date_from} - {date_to}")
    
    # Создаем таблицу для хранения отчетов
    create_monthly_report_table()
    
    all_results = []
    
    # Обрабатываем каждого поставщика отдельно
    for supplier_name in tax_rates.keys():
        print(f"\n🔄 Обработка поставщика: {supplier_name}")
        
        # Получаем налоговые ставки для данного поставщика
        supplier_tax_rate = tax_rates.get(supplier_name, 0.06)  # По умолчанию 6%
        supplier_vat_rate = vat_rates.get(supplier_name, 0.2)   # По умолчанию 20%
        
        print(f"   Налоговая ставка: {supplier_tax_rate}")
        print(f"   НДС: {supplier_vat_rate}")
        
        # Получаем SQL-запрос для данного поставщика
        query = get_simple_report_query(date_from, date_to, supplier_name, supplier_vat_rate, supplier_tax_rate)
        
        try:
            # Выполняем запрос
            result_df = pd.read_sql(query, engine)
            
            if not result_df.empty and result_df.iloc[0]['prodazha_do_komissii'] is not None:
                all_results.append(result_df)
                total_sales = result_df['prodazha_do_komissii'].sum()
                print(f"   ✅ Получено {len(result_df)} отчетов")
                print(f"   💰 Общие продажи до комиссии: {total_sales:,.2f}")
            else:
                print(f"   ⚠️  Нет данных за указанный период")
                
        except Exception as e:
            print(f"   ❌ Ошибка для поставщика {supplier_name}: {e}")
            continue
    
    if not all_results:
        print("⚠️  Нет данных ни для одного поставщика за указанный период")
        return
    
    # Объединяем все результаты
    final_result = pd.concat(all_results, ignore_index=True)
    print(f"\n✅ Общий итог: {len(final_result)} записей для {len(all_results)} поставщиков")
    
    # Сохраняем результат в таблицу с обновлением существующих записей
    print("💾 Сохранение данных в таблицу...")
    
    # Сначала удаляем существующие записи за этот период
    delete_query = text(f"""
        DELETE FROM reports.monthly_financial_report 
        WHERE report_date >= '{date_from}' AND report_date <= '{date_to}'
    """)
    
    with engine.connect() as conn:
        conn.execute(delete_query)
        conn.commit()
    
    # Затем вставляем новые данные
    final_result.to_sql(
        'monthly_financial_report',
        engine,
        schema='reports',
        if_exists='append',
        index=False,
        method='multi'
    )
    
    print("✅ Данные успешно сохранены в таблицу reports.monthly_financial_report")
    
    # Выводим краткую сводку по всем поставщикам
    print("\n📊 КРАТКАЯ СВОДКА ПО ПОСТАВЩИКАМ:")
    print("-" * 80)
    
    # Группируем данные по поставщикам для сводки
    supplier_summary = final_result.groupby('supplier_name').agg({
        'prodazha_do_komissii': 'sum',
        'vozvrat_do_komissii': 'sum',
        'komossia': 'sum',
        'total_to_transfer': 'sum',
        'profit_after_all': 'sum'
    }).reset_index()
    
    for _, row in supplier_summary.iterrows():
        supplier = row['supplier_name']
        print(f"\n{supplier}:")
        print(f"  Продажи до комиссии: {row['prodazha_do_komissii']:,.2f}")
        print(f"  Возвраты до комиссии: {row['vozvrat_do_komissii']:,.2f}")
        print(f"  Комиссия: {row['komossia']:,.2f}")
        print(f"  К перечислению: {row['total_to_transfer']:,.2f}")
        print(f"  Прибыль после всех вычетов: {row['profit_after_all']:,.2f}")
    
    # Общая сводка
    print(f"\n📈 ОБЩИЕ ИТОГИ:")
    print("-" * 50)
    print(f"Общие продажи до комиссии: {final_result['prodazha_do_komissii'].sum():,.2f}")
    print(f"Общие возвраты до комиссии: {final_result['vozvrat_do_komissii'].sum():,.2f}")
    print(f"Общая комиссия: {final_result['komossia'].sum():,.2f}")
    print(f"Общая сумма к перечислению: {final_result['total_to_transfer'].sum():,.2f}")
    print(f"Общая прибыль: {final_result['profit_after_all'].sum():,.2f}")
    print(f"Всего отчетов обработано: {len(final_result)}")
    
    print("=" * 80)
    print("ОТЧЕТ ЗАВЕРШЕН")
    print("=" * 80)

if __name__ == "__main__":
    run_simple_monthly_report()
