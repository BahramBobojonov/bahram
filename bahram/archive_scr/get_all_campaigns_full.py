#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для получения ВСЕХ кампаний за период с 1 марта 2025 года
Разбивает запросы на циклы по 31 день (максимум для API)
"""

import requests
import time
import json
from datetime import datetime, timedelta, date
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

# Путь к файлу с учетными данными
credentials_file = '/home/baakhofficial/wbauto/bahram/cred.json'

def get_api_keys(credentials_file):
    """Получение API ключей из Google Sheets"""
    print("📋 Загружаем API ключи из Google Sheets...")
    
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
    client = gspread.authorize(creds)
    
    sheet = client.open_by_key('15thyGyoR3qUud50Z1L7nwaN6aNob6rqwF4qA4w1UfnQ')
    worksheet = sheet.sheet1
    
    data = worksheet.get_all_records()
    
    dict_api_and_supplier_name = {}
    for row in data:
        company_name = row.get('Имя Юрлица')
        api_key = row.get('API ключ')
        
        if company_name and api_key:
            dict_api_and_supplier_name[api_key] = company_name
    
    print(f"✅ Загружено {len(dict_api_and_supplier_name)} API ключей")
    return dict_api_and_supplier_name


def generate_date_ranges(start_date, end_date, max_days=31):
    """
    Генерирует список периодов по max_days дней
    
    Args:
        start_date: начальная дата (date object)
        end_date: конечная дата (date object)
        max_days: максимальное количество дней в периоде
    
    Returns:
        list: список кортежей (from_date, to_date)
    """
    periods = []
    current_start = start_date
    
    while current_start <= end_date:
        current_end = min(current_start + timedelta(days=max_days-1), end_date)
        periods.append((current_start, current_end))
        current_start = current_end + timedelta(days=1)
    
    return periods


def get_upd_data(api_key, from_date, to_date, company_name, max_retries=5):
    """
    Получение данных о затратах на кампании за период
    """
    url = "https://advert-api.wildberries.ru/adv/v1/upd"
    headers = {"Authorization": api_key}
    params = {
        "from": from_date,
        "to": to_date
    }
    
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return data
            elif response.status_code == 401:
                print(f"[{company_name}] ❌ Ошибка авторизации (401)")
                return None
            elif response.status_code == 429:
                wait_time = 60 + (attempt * 30)
                print(f"[{company_name}] ⚠️ Превышен лимит запросов (429), ждём {wait_time} секунд...")
                time.sleep(wait_time)
                continue
            else:
                print(f"[{company_name}] ❌ Ошибка {response.status_code}: {response.text}")
                time.sleep(10)
                continue
                
        except requests.exceptions.RequestException as e:
            print(f"[{company_name}] ❌ Ошибка запроса: {e}")
            if attempt < max_retries:
                time.sleep(10)
                continue
            return None
    
    return None


def extract_campaigns_from_upd(upd_data):
    """
    Извлекает уникальные кампании из данных upd
    """
    campaigns = {}
    
    for record in upd_data:
        advert_id = record.get('advertId')
        advert_status = record.get('advertStatus')
        camp_name = record.get('campName', 'Без названия')
        advert_type = record.get('advertType')
        payment_type = record.get('paymentType', '')
        
        if advert_id is not None:
            if advert_id not in campaigns:
                campaigns[advert_id] = {
                    'status': advert_status,
                    'name': camp_name,
                    'type': advert_type,
                    'payment_type': payment_type
                }
            else:
                # Обновляем если новый статус более актуален
                current_status = campaigns[advert_id]['status']
                if current_status is None or (advert_status is not None and advert_status > current_status):
                    campaigns[advert_id]['status'] = advert_status
                    campaigns[advert_id]['name'] = camp_name
                    campaigns[advert_id]['type'] = advert_type
                    campaigns[advert_id]['payment_type'] = payment_type
    
    return campaigns


def get_all_campaigns_for_period(api_keys_dict, start_date, end_date):
    """
    Получает все кампании для всех компаний за указанный период
    Разбивает на периоды по 31 день
    """
    print(f"\n📅 ОБЩИЙ ПЕРИОД: {start_date} - {end_date}")
    
    # Генерируем периоды
    periods = generate_date_ranges(start_date, end_date, max_days=31)
    print(f"📊 Разбито на {len(periods)} периодов по 31 день\n")
    
    all_companies_campaigns = {}
    
    for idx, (api_key, company_name) in enumerate(api_keys_dict.items(), 1):
        print(f"\n{'='*60}")
        print(f"🏢 Компания {idx}/{len(api_keys_dict)}: {company_name}")
        print(f"{'='*60}")
        
        company_campaigns = {}
        
        # Проходим по всем периодам
        for period_idx, (period_start, period_end) in enumerate(periods, 1):
            print(f"\n  📅 Период {period_idx}/{len(periods)}: {period_start} - {period_end}")
            
            # Получаем данные upd
            upd_data = get_upd_data(api_key, str(period_start), str(period_end), company_name)
            
            if upd_data:
                print(f"  ✅ Получено {len(upd_data)} записей UPD")
                
                # Извлекаем кампании
                period_campaigns = extract_campaigns_from_upd(upd_data)
                
                # Объединяем с уже найденными кампаниями
                for camp_id, camp_info in period_campaigns.items():
                    if camp_id not in company_campaigns:
                        company_campaigns[camp_id] = camp_info
                    else:
                        # Обновляем если новая информация более актуальна
                        if camp_info['status'] and camp_info['status'] > company_campaigns[camp_id]['status']:
                            company_campaigns[camp_id] = camp_info
                
                print(f"  📊 Уникальных кампаний найдено за период: {len(period_campaigns)}")
                print(f"  📊 Всего уникальных кампаний для компании: {len(company_campaigns)}")
            else:
                print(f"  ❌ Не удалось получить данные")
            
            # Пауза между запросами (лимит 1 запрос в секунду)
            time.sleep(1.5)
        
        all_companies_campaigns[company_name] = company_campaigns
        
        # Статистика по компании
        if company_campaigns:
            status_names = {
                -1: "Удалена", 4: "Готова к запуску", 7: "Завершена",
                8: "Отменена", 9: "Активна", 11: "На паузе"
            }
            
            status_groups = {}
            for camp_id, camp_info in company_campaigns.items():
                status = camp_info['status']
                if status not in status_groups:
                    status_groups[status] = []
                status_groups[status].append(camp_id)
            
            print(f"\n  📊 ИТОГО по компании {company_name}:")
            print(f"  ✅ Всего уникальных кампаний: {len(company_campaigns)}")
            for status, camp_list in sorted(status_groups.items()):
                status_name = status_names.get(status, f"Неизвестный ({status})")
                print(f"     - Статус {status} ({status_name}): {len(camp_list)} кампаний")
        
        # Пауза между компаниями
        if idx < len(api_keys_dict):
            print(f"\n  ⏳ Пауза 3 секунды перед следующей компанией...")
            time.sleep(3)
    
    return all_companies_campaigns


def get_promotion_adverts(api_key, campaign_ids, company_name, max_retries=5):
    """
    Получение детальной информации о кампаниях типов 4-8 через promotion API (POST)
    """
    url = "https://advert-api.wildberries.ru/adv/v1/promotion/adverts"
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }
    
    if len(campaign_ids) > 50:
        campaign_ids = campaign_ids[:50]
    
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(url, headers=headers, json=campaign_ids, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return data if isinstance(data, list) else []
            elif response.status_code == 401:
                return []
            elif response.status_code == 429:
                wait_time = 60 + (attempt * 30)
                time.sleep(wait_time)
                continue
            else:
                time.sleep(10)
                continue
                
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                time.sleep(10)
                continue
            return []
    
    return []


def get_auction_adverts(api_key, campaign_ids, company_name, max_retries=5):
    """
    Получение детальной информации о кампаниях типа 9 через auction API (GET)
    """
    url = "https://advert-api.wildberries.ru/adv/v0/auction/adverts"
    headers = {"Authorization": api_key}
    
    if len(campaign_ids) > 50:
        campaign_ids = campaign_ids[:50]
    
    params = {"ids": ",".join(map(str, campaign_ids))}
    
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                adverts = data.get('adverts', []) if isinstance(data, dict) else []
                return adverts
            elif response.status_code == 401:
                return []
            elif response.status_code == 429:
                wait_time = 60 + (attempt * 30)
                time.sleep(wait_time)
                continue
            else:
                time.sleep(10)
                continue
                
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                time.sleep(10)
                continue
            return []
    
    return []


def get_all_campaign_details(api_keys_dict, all_campaigns):
    """
    Получает детальную информацию для всех кампаний через соответствующие API
    - Тип 9: auction API
    - Типы 4-8: promotion API
    """
    print("\n" + "="*60)
    print("📡 ПОЛУЧЕНИЕ ДЕТАЛЬНОЙ ИНФОРМАЦИИ О КАМПАНИЯХ")
    print("="*60)
    
    all_details = []
    api_key_by_company = {v: k for k, v in api_keys_dict.items()}
    
    for company_name, campaigns in all_campaigns.items():
        if not campaigns:
            continue
        
        api_key = api_key_by_company.get(company_name)
        if not api_key:
            continue
        
        print(f"\n{'='*60}")
        print(f"🏢 Компания: {company_name}")
        print(f"📊 Кампаний: {len(campaigns)}")
        print(f"{'='*60}")
        
        # Разделяем кампании по типам
        type_9_campaigns = []  # Для auction API
        other_type_campaigns = []  # Для promotion API (типы 4-8)
        
        for camp_id, camp_info in campaigns.items():
            camp_type = camp_info.get('type')
            if camp_type == 9:
                type_9_campaigns.append(camp_id)
            else:
                other_type_campaigns.append(camp_id)
        
        print(f"  Тип 9 (ручные ставки): {len(type_9_campaigns)} кампаний")
        print(f"  Типы 4-8 (авто): {len(other_type_campaigns)} кампаний")
        
        batch_size = 50
        found_campaign_ids = set()
        
        # 1. Обрабатываем кампании типа 9 через auction API
        if type_9_campaigns:
            print(f"\n📡 Обработка типа 9 через AUCTION API...")
            for i in range(0, len(type_9_campaigns), batch_size):
                batch = type_9_campaigns[i:i+batch_size]
                
                adverts = get_auction_adverts(api_key, batch, company_name)
                print(f"  ✅ Пачка {i//batch_size + 1}: получено {len(adverts)}/{len(batch)}")
                
                for advert in adverts:
                    campaign_id = advert.get('id')
                    campaign_info = campaigns.get(campaign_id, {})
                    found_campaign_ids.add(campaign_id)
                    
                    # Извлекаем nm_id
                    nm_settings = advert.get('nm_settings', [])
                    nm_ids = [nm.get('nm_id') for nm in nm_settings if nm.get('nm_id')]
                    
                    # Ставки
                    bids_list = []
                    for nm in nm_settings:
                        nm_bids = nm.get('bids', {})
                        if nm_bids:
                            bids_list.append({
                                'nm_id': nm.get('nm_id'),
                                'search': nm_bids.get('search'),
                                'recommendations': nm_bids.get('recommendations')
                            })
                    
                    detail = {
                        'Компания': company_name,
                        'ID кампании': campaign_id,
                        'Название кампании': campaign_info.get('name', 'Без названия'),
                        'Статус': campaign_info.get('status'),
                        'Тип кампании': campaign_info.get('type'),
                        'Источник списания': campaign_info.get('payment_type', ''),
                        'Артикулы WB (nm_id)': ', '.join(map(str, nm_ids)) if nm_ids else '',
                        'Количество артикулов': len(nm_ids),
                        'Ставки по артикулам': json.dumps(bids_list, ensure_ascii=False) if bids_list else '',
                        'API метод': 'auction/adverts (тип 9)'
                    }
                    
                    all_details.append(detail)
                
                time.sleep(0.3)
        
        # 2. Обрабатываем кампании типов 4-8 через promotion API
        if other_type_campaigns:
            print(f"\n📡 Обработка типов 4-8 через PROMOTION API...")
            for i in range(0, len(other_type_campaigns), batch_size):
                batch = other_type_campaigns[i:i+batch_size]
                
                adverts = get_promotion_adverts(api_key, batch, company_name)
                print(f"  ✅ Пачка {i//batch_size + 1}: получено {len(adverts)}/{len(batch)}")
                
                for advert in adverts:
                    campaign_id = advert.get('advertId')
                    campaign_info = campaigns.get(campaign_id, {})
                    found_campaign_ids.add(campaign_id)
                    
                    # Извлекаем nm_id в зависимости от типа
                    nm_ids = []
                    bids_list = []
                    
                    # Для типа 8 - autoParams
                    if 'autoParams' in advert:
                        auto_params = advert.get('autoParams', {})
                        nm_ids = auto_params.get('nms', [])
                        
                        # Ставки из nmCPM
                        nm_cpm_list = auto_params.get('nmCPM', [])
                        for nm_cpm in nm_cpm_list:
                            bids_list.append({
                                'nm_id': nm_cpm.get('nm'),
                                'cpm': nm_cpm.get('cpm')
                            })
                    
                    # Для типов 4-7 - params
                    elif 'params' in advert:
                        params = advert.get('params', [])
                        for param in params:
                            if 'nms' in param:
                                nm_ids.extend(param.get('nms', []))
                            if 'nm' in param:
                                nm_ids.append(param.get('nm'))
                    
                    detail = {
                        'Компания': company_name,
                        'ID кампании': campaign_id,
                        'Название кампании': campaign_info.get('name', advert.get('name', 'Без названия')),
                        'Статус': campaign_info.get('status', advert.get('status')),
                        'Тип кампании': campaign_info.get('type', advert.get('type')),
                        'Источник списания': campaign_info.get('payment_type', advert.get('paymentType', '')),
                        'Артикулы WB (nm_id)': ', '.join(map(str, nm_ids)) if nm_ids else '',
                        'Количество артикулов': len(nm_ids),
                        'Ставки по артикулам': json.dumps(bids_list, ensure_ascii=False) if bids_list else '',
                        'API метод': f'promotion/adverts (тип {advert.get("type")})'
                    }
                    
                    all_details.append(detail)
                
                time.sleep(0.3)
        
        # 3. Добавляем кампании, не найденные ни в одном API
        all_campaign_ids = type_9_campaigns + other_type_campaigns
        not_found = set(all_campaign_ids) - found_campaign_ids
        if not_found:
            print(f"\n⚠️ Не найдено ни в одном API: {len(not_found)} кампаний")
            for campaign_id in not_found:
                campaign_info = campaigns.get(campaign_id, {})
                detail = {
                    'Компания': company_name,
                    'ID кампании': campaign_id,
                    'Название кампании': campaign_info.get('name', 'Без названия'),
                    'Статус': campaign_info.get('status'),
                    'Тип кампании': campaign_info.get('type'),
                    'Источник списания': campaign_info.get('payment_type', ''),
                    'Артикулы WB (nm_id)': 'Недоступно',
                    'Количество артикулов': 0,
                    'Ставки по артикулам': '',
                    'API метод': 'НЕ НАЙДЕНО'
                }
                all_details.append(detail)
        
        print(f"\n✅ Обработано: {len([d for d in all_details if d['Компания'] == company_name])} записей")
        time.sleep(2)
    
    return all_details


def save_to_excel(details, filename='all_campaigns_full.xlsx'):
    """Сохраняет данные в Excel"""
    filepath = f'/home/baakhofficial/wbauto/bahram/{filename}'
    
    if not details:
        print("⚠️ Нет данных для сохранения")
        return
    
    print(f"\n💾 Сохранение {len(details)} записей в Excel...")
    
    df = pd.DataFrame(details)
    
    status_names = {
        -1: "Удалена", 4: "Готова к запуску", 7: "Завершена",
        8: "Отменена", 9: "Активна", 11: "На паузе"
    }
    
    df['Статус (название)'] = df['Статус'].map(status_names)
    df = df.sort_values(['Компания', 'ID кампании'])
    
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Все кампании', index=False)
        worksheet = writer.sheets['Все кампании']
        
        # Форматирование
        header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
        header_font = Font(bold=True, color='FFFFFF')
        
        for cell in worksheet[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # Автоширина
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 80)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    print(f"✅ Данные сохранены в {filepath}")
    print(f"📊 Записей: {len(df)}")
    print(f"🏢 Компаний: {df['Компания'].nunique()}")


def main():
    print("="*60)
    print("🚀 ЗАПУСК ПОЛНОГО СБОРА ДАННЫХ ПО КАМПАНИЯМ")
    print("="*60)
    
    # Получаем API ключи
    api_keys_dict = get_api_keys(credentials_file)
    
    # Определяем период
    start_date = date(2025, 3, 1)  # 1 марта 2025
    end_date = datetime.now().date()  # Сегодня
    
    # Получаем все кампании за весь период
    all_campaigns = get_all_campaigns_for_period(api_keys_dict, start_date, end_date)
    
    # Получаем детальную информацию
    campaign_details = get_all_campaign_details(api_keys_dict, all_campaigns)
    
    # Сохраняем в Excel
    save_to_excel(campaign_details)
    
    # Итоговая статистика
    print("\n" + "="*60)
    print("📊 ИТОГОВАЯ СТАТИСТИКА")
    print("="*60)
    
    total_campaigns = sum(len(camps) for camps in all_campaigns.values())
    
    # Подсчет по методам API
    auction_count = len([d for d in campaign_details if 'auction/adverts' in d.get('API метод', '')])
    promotion_count = len([d for d in campaign_details if 'promotion/adverts' in d.get('API метод', '')])
    not_found = len([d for d in campaign_details if d.get('API метод') == 'НЕ НАЙДЕНО'])
    
    # Подсчет артикулов
    total_nmids = sum(d.get('Количество артикулов', 0) for d in campaign_details if d.get('Количество артикулов', 0) > 0)
    
    print(f"🏢 Обработано компаний: {len(all_campaigns)}")
    print(f"📊 Всего уникальных кампаний: {total_campaigns}")
    print(f"\n📡 По методам API:")
    print(f"  ✅ Через auction API (тип 9): {auction_count} кампаний")
    print(f"  ✅ Через promotion API (типы 4-8): {promotion_count} кампаний")
    print(f"  ❌ Не найдено: {not_found} кампаний")
    print(f"\n📦 Всего артикулов (nm_id): {total_nmids}")
    
    print("\n✅ Скрипт завершён успешно!")


if __name__ == "__main__":
    main()

