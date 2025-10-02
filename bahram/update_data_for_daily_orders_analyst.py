#!/usr/bin/env python3

import pandas as pd
from sqlalchemy import text
from sqlalchemy import create_engine


engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')



query = """
REFRESH MATERIALIZED VIEW reports.daily_product_summary_mv
"""
with engine.begin() as connection:
    connection.execute(text(query))



query = """
REFRESH MATERIALIZED VIEW reports.daily_product_summary_mv_step_2
"""
with engine.begin() as connection:
    connection.execute(text(query))
