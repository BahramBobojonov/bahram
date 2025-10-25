#!/usr/bin/env python3

"""
Скрипт для мониторинга прогресса загрузки заявок
"""

import time
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime

# === PostgreSQL setup ===
engine = create_engine('postgresql://bahram:Dadajonim99@94.103.84.245:5432/wb_baah')

def monitor_progress():
    """Мониторит прогресс загрузки заявок"""
    
    print("Мониторинг загрузки заявок на возврат")
    print("=" * 50)
    
    try:
        with engine.connect() as conn:
            # Общая статистика
            result = conn.execute(text("SELECT COUNT(*) as total FROM reports.claims"))
            total_count = result.fetchone()[0]
            
            # Статистика по компаниям
            result = conn.execute(text("""
                SELECT company, COUNT(*) as count 
                FROM reports.claims 
                GROUP BY company 
                ORDER BY count DESC
            """))
            companies = result.fetchall()
            
            # Статистика по датам
            result = conn.execute(text("""
                SELECT DATE(dt) as date, COUNT(*) as count 
                FROM reports.claims 
                WHERE dt IS NOT NULL
                GROUP BY DATE(dt) 
                ORDER BY date DESC 
                LIMIT 10
            """))
            dates = result.fetchall()
            
            print(f"Общее количество заявок: {total_count}")
            print(f"Время проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            print(f"\nСтатистика по компаниям:")
            for company, count in companies:
                print(f"  {company}: {count} заявок")
            
            print(f"\nПоследние 10 дней с заявками:")
            for date, count in dates:
                print(f"  {date}: {count} заявок")
            
            # Проверяем, есть ли процесс загрузки
            import subprocess
            try:
                result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
                if 'get_claims.py' in result.stdout:
                    print(f"\n✓ Процесс загрузки активен")
                else:
                    print(f"\n✗ Процесс загрузки не найден")
            except:
                print(f"\n? Не удалось проверить процесс загрузки")
                
    except Exception as e:
        print(f"Ошибка при мониторинге: {e}")

if __name__ == "__main__":
    monitor_progress()
