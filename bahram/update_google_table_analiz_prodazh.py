#!/usr/bin/env python3

import requests
import pandas as pd
from gspread_dataframe import set_with_dataframe
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
import time
import numpy as np
import gspread
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')
gc = gspread.service_account(filename='/home/baakhofficial/wbauto/bahram/cred.json')
#gc = gspread.service_account(filename=r"C:\Users\vivar\wb_baah\tasks\files_for_server\cred.json")

# query = """
#  select * from analytics.daily_orders_analyst
# """
# with engine.begin() as connection:
#     result = connection.execute(text(query))
#     df = pd.DataFrame(result.fetchall(), columns=result.keys())


# df = df[['supplier', 'date', 'nm_id', 'orders_count', 'pricewithdisc_sum_orders', 'Количество продаж', 'Количество возвратов',
#        'К перечислению(продажи)', 'К перечислению(возвраты)',
#        'WB реализовал(Продажа)', 'WB реализовал(Возврат)', 'Логистика',
#        'Штрафы', 'Реклама', 'views_sum', 'clicks_sum', 'atbs_sum',
#        'adv_orders_count', 'Платная приемка', 'Платное хранение',
#        'Себестоимость сумма', 'source', 'pricewithdisc_sum_sales',
#        'pricewithdisc_sum_returns', 'cost_price', 'date_update',
#        'Процент комиссии', 'Процент эквайринга', 'Процент SPP',
#        'Скидка WB Wallet', 'Сумма SPP', 'Сумма комиссии', 'Налог', 'margin',
#        'net_profit']]


# df.rename(columns={
#     'orders_count':'Количество заказов',
#     'views_sum':'adv_Количество показов',
#     'clicks_sum':'adv_Количество кликов',
#     'atbs_sum':'adv_Количество добавлений в корзину',
#     'adv_orders_count':'adv_Количество рекламных заказов',
#     'margin':'Маржа',
#     'net_profit':'Прибыль'
# },
# inplace=True)


# df[df.select_dtypes(include=['number']).columns] = df.select_dtypes(include=['number']).fillna(0)
# df['date'] = pd.to_datetime(df['date']).dt.date


# # Открываем Google Таблицу по ключу
spreadsheet = gc.open_by_key("1JeBCJUFMJ6FTWS1SrTDlhYoI9yspJkuF7VEUF1uRtoI")

# # Открываем нужный лист
# worksheet = spreadsheet.worksheet("Анализ продаж")

# # Загружаем DataFrame в Google Таблицу
# set_with_dataframe(worksheet, df)



print(datetime.now())

query = """
WITH calendar AS (
         SELECT generate_series('2024-12-01'::date::timestamp with time zone, CURRENT_DATE::timestamp with time zone, '1 day'::interval) AS date_column
        ), orders_data AS (
         SELECT orders.supplier_name,
            orders.nmid,
            orders.supplierarticle,
            orders.srid,
            orders.pricewithdisc,
            orders.date::date AS date,
            'orders'::text AS source
           FROM reports.orders
          WHERE orders.iscancel IS FALSE AND orders.date::date >= '2024-12-01'::date
        ), fbs_data AS (
         SELECT corrected_fbs_incomes.supplier,
            corrected_fbs_incomes.nmid,
            corrected_fbs_incomes.article,
            corrected_fbs_incomes.rid,
            corrected_fbs_incomes.price / 100 AS pricewithdisc,
            corrected_fbs_incomes.createdat::date AS createdat,
            'supplies'::text AS source
           FROM supplies.corrected_fbs_incomes
          WHERE corrected_fbs_incomes.createdat::date >= '2024-12-01'::date AND corrected_fbs_incomes.correct_supplierstatus <> 'cancel'::text AND corrected_fbs_incomes.wbstatus <> 'canceled_by_client'::text
        ), combined_orders AS (
         SELECT orders_data.supplier_name,
            orders_data.nmid,
            orders_data.supplierarticle,
            orders_data.srid,
            orders_data.pricewithdisc,
            orders_data.date,
            orders_data.source
           FROM orders_data
        UNION
         SELECT fbs_data.supplier,
            fbs_data.nmid,
            fbs_data.article,
            fbs_data.rid,
            fbs_data.pricewithdisc,
            fbs_data.createdat,
            fbs_data.source
           FROM fbs_data
             LEFT JOIN orders_data ON fbs_data.rid = orders_data.srid
          WHERE orders_data.srid IS NULL
        ), aggregated_orders AS (
         SELECT combined_orders.supplier_name,
         combined_orders.supplierarticle,
            combined_orders.nmid,
            combined_orders.date,
            count(DISTINCT combined_orders.srid) AS orders_count,
            sum(combined_orders.pricewithdisc) AS pricewithdisc_sum_orders
           FROM combined_orders
          GROUP BY combined_orders.supplier_name, combined_orders.nmid, combined_orders.date,combined_orders.supplierarticle
        ), sales_data AS (
         SELECT s_1.supplier_name,
            s_1.nmid,
            s_1.supplierarticle,
            s_1.date::date AS date,
            count(DISTINCT s_1.srid) AS sales_count,
            sum(s_1.pricewithdisc) AS pricewithdisc_sum_sales
           FROM reports.sales s_1
             LEFT JOIN reports.sales s2 ON s_1.srid = s2.srid AND s2.saleid ~~ 'R%'::text
          WHERE s2.srid IS NULL AND s_1.date::date >= '2024-12-01'::date
          GROUP BY s_1.supplier_name, s_1.nmid, s_1.supplierarticle, (s_1.date::date)
        ), returns_data AS (
         SELECT sales.supplier_name,
            sales.nmid,
            sales.supplierarticle,
            sales.date::date AS date,
            count(DISTINCT sales.srid) AS returns_count,
            sum(sales.pricewithdisc) AS pricewithdisc_sum_returns
           FROM reports.sales
          WHERE sales.saleid ~~ 'R%'::text AND sales.date::date >= '2024-12-01'::date
          GROUP BY sales.supplier_name, sales.nmid, sales.supplierarticle, (sales.date::date)
        )
 SELECT COALESCE(c.date_column, s.date::timestamp with time zone, r.date::timestamp with time zone)::date AS date,
    COALESCE(o.supplier_name, s.supplier_name, r.supplier_name) AS supplier_name,
    COALESCE(o.supplierarticle, s.supplierarticle, r.supplierarticle) AS supplierarticle,
    COALESCE(o.nmid, s.nmid, r.nmid) AS nmid,
    COALESCE(o.orders_count, 0::bigint) AS orders_count,
    COALESCE(o.pricewithdisc_sum_orders, 0::double precision) AS pricewithdisc_sum_orders,
    COALESCE(s.sales_count, 0::bigint) AS sales_count,
    COALESCE(s.pricewithdisc_sum_sales, 0::double precision) AS pricewithdisc_sum_sales,
    COALESCE(r.returns_count, 0::bigint) AS returns_count,
    COALESCE(r.pricewithdisc_sum_returns, 0::double precision) AS pricewithdisc_sum_returns,
    now()::timestamp without time zone AS date_update
   FROM calendar c
     LEFT JOIN aggregated_orders o ON c.date_column = o.date
     FULL JOIN sales_data s ON c.date_column = s.date AND o.nmid = s.nmid
     FULL JOIN returns_data r ON COALESCE(c.date_column, s.date::timestamp with time zone) = r.date AND COALESCE(o.nmid, s.nmid) = r.nmid
"""
with engine.begin() as connection:
    result = connection.execute(text(query))
    orders_and_sales = pd.DataFrame(result.fetchall(), columns=result.keys())

orders_and_sales['Продажи, шт'] = orders_and_sales['sales_count']-orders_and_sales['returns_count']

orders_and_sales['Продажи, руб'] = orders_and_sales['pricewithdisc_sum_sales']+orders_and_sales['pricewithdisc_sum_returns']

orders_and_sales.rename(columns={'orders_count':'Заказы, шт','pricewithdisc_sum_orders':'Заказы, руб'}, inplace=True)


orders_and_sales = orders_and_sales[['date', 'supplier_name', 'supplierarticle', 'nmid', 'Заказы, шт',
       'Заказы, руб','Продажи, шт', 'Продажи, руб','date_update']]

orders_and_sales['date'] = pd.to_datetime(orders_and_sales['date']).dt.date
orders_and_sales = orders_and_sales.sort_values(by = 'date')
worksheet = spreadsheet.worksheet("Заказы и продажи")
set_with_dataframe(worksheet, orders_and_sales)