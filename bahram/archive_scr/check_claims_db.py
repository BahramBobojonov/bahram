#!/usr/bin/env python3

"""
Скрипт для проверки данных в таблице reports.claims
"""

import pandas as pd
from sqlalchemy import create_engine, text

# === PostgreSQL setup ===
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

def check_claims_data():
    """Проверяет данные в таблице reports.claims"""
    
    print("Проверка данных в таблице reports.claims")
    print("=" * 50)
    
    try:
        # Общая статистика
        with engine.connect() as conn:
            # Количество записей
            result = conn.execute(text("SELECT COUNT(*) as total FROM reports.claims"))
            total_count = result.fetchone()[0]
            print(f"Общее количество заявок: {total_count}")
            
            # Статистика по компаниям
            result = conn.execute(text("""
                SELECT company, COUNT(*) as count 
                FROM reports.claims 
                GROUP BY company 
                ORDER BY count DESC
            """))
            companies = result.fetchall()
            print(f"\nСтатистика по компаниям:")
            for company, count in companies:
                print(f"  {company}: {count} заявок")
            
            # Статистика по статусам
            result = conn.execute(text("""
                SELECT status, COUNT(*) as count 
                FROM reports.claims 
                GROUP BY status 
                ORDER BY status
            """))
            statuses = result.fetchall()
            print(f"\nСтатистика по статусам:")
            for status, count in statuses:
                status_name = {0: "на рассмотрении", 1: "отказ", 2: "одобрено"}.get(status, f"статус {status}")
                print(f"  {status_name}: {count} заявок")
            
            # Последние заявки
            result = conn.execute(text("""
                SELECT company, dt, status, nm_id, user_comment 
                FROM reports.claims 
                ORDER BY dt DESC 
                LIMIT 5
            """))
            recent_claims = result.fetchall()
            print(f"\nПоследние 5 заявок:")
            for claim in recent_claims:
                company, dt, status, nm_id, comment = claim
                status_name = {0: "на рассмотрении", 1: "отказ", 2: "одобрено"}.get(status, f"статус {status}")
                comment_short = comment[:50] + "..." if comment and len(comment) > 50 else comment or "Нет комментария"
                print(f"  {company} | {dt} | {status_name} | NM: {nm_id} | {comment_short}")
            
            # Проверка структуры таблицы
            result = conn.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = 'reports' AND table_name = 'claims'
                ORDER BY ordinal_position
            """))
            columns = result.fetchall()
            print(f"\nСтруктура таблицы reports.claims:")
            for col_name, data_type in columns:
                print(f"  {col_name}: {data_type}")
                
    except Exception as e:
        print(f"Ошибка при проверке данных: {e}")

if __name__ == "__main__":
    check_claims_data()
