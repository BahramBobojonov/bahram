#!/usr/bin/env python3
"""
Скрипт для генерации отчета о платном хранении с 1 марта 2025 года.
Использует циклы по 8 дней для соблюдения лимитов API Wildberries.
"""

import sys
import os
from datetime import datetime

# Добавляем путь к модулю report_paid_storage
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from report_paid_storage import generate_report_from_march_2025

if __name__ == "__main__":
    print("=" * 80)
    print("ГЕНЕРАЦИЯ ОТЧЕТА О ПЛАТНОМ ХРАНЕНИИ С 1 МАРТА 2025 ГОДА")
    print("=" * 80)
    print(f"Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    try:
        result = generate_report_from_march_2025()
        print(f"\nРезультат: {result}")
        print("\n✅ Отчет успешно сгенерирован!")
        
    except Exception as e:
        print(f"\n❌ Ошибка при генерации отчета: {e}")
        sys.exit(1)
