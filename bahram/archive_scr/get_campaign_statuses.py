#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для получения статусов кампаний через метод /adv/v1/upd
Получаем данные за последний месяц чтобы собрать актуальные статусы всех кампаний
"""

import requests
import time
import json
from datetime import datetime, timedelta
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


def get_upd_data(api_key, from_date, to_date, company_name, max_retries=5):
    """
    Получение данных о затратах на кампании за период
    Возвращает список кампаний с их статусами
    """
    url = "https://advert-api.wildberries.ru/adv/v1/upd"
    headers = {"Authorization": api_key}
    params = {
        "from": from_date,
        "to": to_date
    }
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[{company_name}] Попытка {attempt}/{max_retries} запроса upd для периода {from_date} - {to_date}...")
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                print(f"[{company_name}] ✅ Получено {len(data)} записей")
                return data
            elif response.status_code == 401:
                print(f"[{company_name}] ❌ Ошибка авторизации (401)")
                return None
            elif response.status_code == 429:
                wait_time = 60 + (attempt * 30)  # 60, 90, 120, 150, 180 секунд
                print(f"[{company_name}] ⚠️ Превышен лимит запросов (429), ждём {wait_time} секунд...")
                time.sleep(wait_time)
                continue
            else:
                print(f"[{company_name}] ❌ Ошибка {response.status_code}: {response.text}")
                time.sleep(30)
                continue
                
        except requests.exceptions.RequestException as e:
            print(f"[{company_name}] ❌ Ошибка запроса: {e}")
            if attempt < max_retries:
                time.sleep(30)
                continue
            return None
    
    return None


def extract_campaign_statuses(upd_data):
    """
    Извлекает уникальные кампании и их статусы из данных upd
    Возвращает словарь {campaign_id: {'status': status, 'name': name, 'type': type, 'payment_type': payment_type}}
    """
    campaigns = {}
    
    for record in upd_data:
        advert_id = record.get('advertId')
        advert_status = record.get('advertStatus')
        camp_name = record.get('campName', 'Без названия')
        advert_type = record.get('advertType')
        payment_type = record.get('paymentType', '')
        
        if advert_id is not None:
            # Если кампания уже есть, обновляем только если новый статус "лучше"
            # (приоритет активным статусам)
            if advert_id not in campaigns:
                campaigns[advert_id] = {
                    'status': advert_status,
                    'name': camp_name,
                    'type': advert_type,
                    'payment_type': payment_type
                }
            else:
                # Обновляем если текущий статус None или новый статус более актуален
                current_status = campaigns[advert_id]['status']
                if current_status is None or (advert_status is not None and advert_status > current_status):
                    campaigns[advert_id]['status'] = advert_status
                    campaigns[advert_id]['name'] = camp_name
                    campaigns[advert_id]['type'] = advert_type
                    campaigns[advert_id]['payment_type'] = payment_type
    
    return campaigns


def get_all_campaigns_with_statuses(api_keys_dict, days_back=31):
    """
    Получает статусы всех кампаний для всех компаний
    
    Args:
        api_keys_dict: словарь {api_key: company_name}
        days_back: количество дней назад для запроса (по умолчанию 31)
    
    Returns:
        dict: {company_name: {campaign_id: {status, name, type}}}
    """
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days_back)
    
    print(f"\n📅 Период запроса: {start_date} - {end_date}")
    print(f"🏢 Всего компаний: {len(api_keys_dict)}\n")
    
    all_companies_campaigns = {}
    
    for idx, (api_key, company_name) in enumerate(api_keys_dict.items(), 1):
        print(f"\n{'='*60}")
        print(f"🏢 Компания {idx}/{len(api_keys_dict)}: {company_name}")
        print(f"{'='*60}")
        
        # Получаем данные upd
        upd_data = get_upd_data(api_key, str(start_date), str(end_date), company_name)
        
        if upd_data:
            # Извлекаем статусы кампаний
            campaigns = extract_campaign_statuses(upd_data)
            all_companies_campaigns[company_name] = campaigns
            
            print(f"\n[{company_name}] 📊 Найдено {len(campaigns)} уникальных кампаний:")
            
            # Группируем по статусам
            status_groups = {}
            for camp_id, camp_info in campaigns.items():
                status = camp_info['status']
                if status not in status_groups:
                    status_groups[status] = []
                status_groups[status].append((camp_id, camp_info['name']))
            
            # Названия статусов
            status_names = {
                -1: "Удалена",
                4: "Готова к запуску",
                7: "Завершена",
                8: "Отменена",
                9: "Активна",
                11: "На паузе"
            }
            
            for status, camp_list in sorted(status_groups.items()):
                status_name = status_names.get(status, f"Неизвестный ({status})")
                print(f"  📍 Статус {status} ({status_name}): {len(camp_list)} кампаний")
                for camp_id, camp_name in camp_list[:3]:  # Показываем первые 3
                    print(f"    - ID {camp_id}: {camp_name}")
                if len(camp_list) > 3:
                    print(f"    ... и ещё {len(camp_list) - 3} кампаний")
            
        else:
            print(f"[{company_name}] ❌ Не удалось получить данные")
            all_companies_campaigns[company_name] = {}
        
        # Пауза между компаниями (лимит 1 запрос в секунду)
        if idx < len(api_keys_dict):
            print(f"\n⏳ Пауза 5 секунд перед следующей компанией...")
            time.sleep(5)
    
    return all_companies_campaigns


def get_cpm_cpc_adverts(api_key, campaign_ids, company_name, adv_type='cpm', max_retries=5):
    """
    Получение детальной информации о CPM/CPC кампаниях
    Метод /adv/v0/cpm/list или /adv/v0/cpc/list
    
    Args:
        api_key: API ключ
        campaign_ids: список ID кампаний
        company_name: название компании
        adv_type: тип кампании ('cpm' или 'cpc')
        max_retries: максимальное количество попыток
    
    Returns:
        list: список кампаний с детальной информацией
    """
    url = f"https://advert-api.wildberries.ru/adv/v0/{adv_type}/list"
    headers = {"Authorization": api_key}
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[{company_name}] Запрос {adv_type}/list (попытка {attempt}/{max_retries})...")
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                adverts = data if isinstance(data, list) else []
                
                # Фильтруем только нужные кампании
                filtered = [adv for adv in adverts if adv.get('advertId') in campaign_ids]
                print(f"[{company_name}] ✅ Получено {len(filtered)} из {len(campaign_ids)} кампаний")
                return filtered
            elif response.status_code == 401:
                print(f"[{company_name}] ❌ Ошибка авторизации (401)")
                return []
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
            return []
    
    return []


def get_auction_adverts(api_key, campaign_ids, company_name, max_retries=5):
    """
    Получение детальной информации о кампаниях с ручной ставкой
    Метод /adv/v0/auction/adverts
    
    Args:
        api_key: API ключ
        campaign_ids: список ID кампаний (максимум 50)
        company_name: название компании
        max_retries: максимальное количество попыток
    
    Returns:
        list: список кампаний с детальной информацией
    """
    url = "https://advert-api.wildberries.ru/adv/v0/auction/adverts"
    headers = {"Authorization": api_key}
    
    # Ограничиваем до 50 ID
    if len(campaign_ids) > 50:
        campaign_ids = campaign_ids[:50]
    
    params = {
        "ids": ",".join(map(str, campaign_ids))
    }
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[{company_name}] Запрос auction/adverts для {len(campaign_ids)} кампаний (попытка {attempt}/{max_retries})...")
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                adverts = data.get('adverts', []) if isinstance(data, dict) else []
                print(f"[{company_name}] ✅ Получено {len(adverts)} записей")
                return adverts
            elif response.status_code == 401:
                print(f"[{company_name}] ❌ Ошибка авторизации (401)")
                return []
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
            return []
    
    return []


def get_all_auction_details(api_keys_dict, all_campaigns):
    """
    Получает детальную информацию для всех кампаний через auction API
    
    Args:
        api_keys_dict: словарь {api_key: company_name}
        all_campaigns: словарь {company_name: {campaign_id: {status, name, type, payment_type}}}
    
    Returns:
        list: список словарей с детальной информацией о кампаниях
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
            print(f"[{company_name}] ⚠️ API ключ не найден, пропускаем...")
            continue
        
        print(f"\n{'='*60}")
        print(f"🏢 Компания: {company_name}")
        print(f"📊 Кампаний из UPD: {len(campaigns)}")
        print(f"{'='*60}")
        
        # Разбиваем на пачки по 50 ID (лимит API)
        campaign_ids = list(campaigns.keys())
        batch_size = 50
        
        # Словарь для отслеживания найденных кампаний
        found_campaign_ids = set()
        
        for i in range(0, len(campaign_ids), batch_size):
            batch = campaign_ids[i:i+batch_size]
            print(f"\n📦 Обработка пачки {i//batch_size + 1} ({len(batch)} кампаний)...")
            
            # Получаем данные
            adverts = get_auction_adverts(api_key, batch, company_name)
            
            # Обрабатываем результаты
            for advert in adverts:
                campaign_id = advert.get('id')
                campaign_info = campaigns.get(campaign_id, {})
                found_campaign_ids.add(campaign_id)
                
                # Базовая информация
                detail = {
                    'Компания': company_name,
                    'ID кампании': campaign_id,
                    'Название кампании': campaign_info.get('name', 'Без названия'),
                    'Статус': campaign_info.get('status'),
                    'Тип кампании': campaign_info.get('type'),
                    'Источник списания (UPD)': campaign_info.get('payment_type', ''),
                }
                
                # Настройки кампании
                settings = advert.get('settings', {})
                detail['Статус (auction)'] = settings.get('status')
                
                # Временные метки
                timestamps = settings.get('timestamps', {})
                detail['Дата создания'] = timestamps.get('created')
                detail['Дата начала'] = timestamps.get('started')
                detail['Дата окончания'] = timestamps.get('finished')
                
                # Тип ставки
                detail['Тип ставки'] = settings.get('bid_type')
                
                # Предмет
                subject = advert.get('subject', {})
                detail['ID предмета'] = subject.get('id')
                detail['Название предмета'] = subject.get('name')
                
                # Ставки
                bids = advert.get('bids', {})
                detail['Ставка в поиске'] = bids.get('search')
                detail['Ставка в рекомендациях'] = bids.get('recommendations')
                
                # Товары (nm_id)
                nm_settings = advert.get('nm_settings', [])
                nm_ids = []
                for nm in nm_settings:
                    nm_id = nm.get('nm_id')
                    if nm_id:
                        nm_ids.append(nm_id)
                
                detail['Артикулы WB (nm_id)'] = ', '.join(map(str, nm_ids)) if nm_ids else ''
                detail['Количество артикулов'] = len(nm_ids)
                detail['API метод'] = 'auction/adverts'
                
                all_details.append(detail)
            
            # Пауза 200 мс между запросами (лимит 5 запросов в секунду)
            if i + batch_size < len(campaign_ids):
                time.sleep(0.2)
        
        # Добавляем кампании, которые не вернулись из auction API (автоматические кампании)
        not_found = set(campaign_ids) - found_campaign_ids
        if not_found:
            print(f"\n⚠️ Кампаний не найдено в auction API: {len(not_found)}")
            print(f"   Пытаемся получить через CPM/CPC API...")
            
            # Пробуем получить через CPM API
            not_found_list = list(not_found)
            cpm_adverts = get_cpm_cpc_adverts(api_key, not_found_list, company_name, 'cpm')
            time.sleep(0.5)
            
            # Пробуем получить через CPC API
            cpc_adverts = get_cpm_cpc_adverts(api_key, not_found_list, company_name, 'cpc')
            time.sleep(0.5)
            
            # Объединяем результаты
            all_cpm_cpc = cpm_adverts + cpc_adverts
            found_via_cpm_cpc = set()
            
            # Обрабатываем найденные кампании
            for advert in all_cpm_cpc:
                campaign_id = advert.get('advertId')
                if campaign_id not in not_found:
                    continue
                    
                found_via_cpm_cpc.add(campaign_id)
                campaign_info = campaigns.get(campaign_id, {})
                
                # Базовая информация
                detail = {
                    'Компания': company_name,
                    'ID кампании': campaign_id,
                    'Название кампании': advert.get('name', campaign_info.get('name', 'Без названия')),
                    'Статус': advert.get('status', campaign_info.get('status')),
                    'Тип кампании': advert.get('type', campaign_info.get('type')),
                    'Источник списания (UPD)': campaign_info.get('payment_type', ''),
                }
                
                # Даты
                detail['Дата создания'] = advert.get('createTime')
                detail['Дата начала'] = advert.get('startTime')
                detail['Дата окончания'] = advert.get('endTime')
                
                # Тип ставки
                detail['Тип ставки'] = 'Автоматическая (CPM/CPC)'
                
                # Предмет
                detail['ID предмета'] = None
                detail['Название предмета'] = None
                
                # Ставки (если есть)
                detail['Ставка в поиске'] = advert.get('cpm')
                detail['Ставка в рекомендациях'] = None
                
                # Товары (nm_id) - для CPM/CPC кампаний
                nm_ids = []
                
                # Проверяем разные варианты структуры данных
                if 'nms' in advert and isinstance(advert['nms'], list):
                    nm_ids = advert['nms']
                elif 'params' in advert and isinstance(advert['params'], list):
                    for param in advert['params']:
                        if 'nms' in param and isinstance(param['nms'], list):
                            nm_ids.extend(param['nms'])
                
                detail['Артикулы WB (nm_id)'] = ', '.join(map(str, nm_ids)) if nm_ids else 'Не указано'
                detail['Количество артикулов'] = len(nm_ids)
                detail['API метод'] = 'cpm/list или cpc/list'
                detail['Статус (auction)'] = None
                
                all_details.append(detail)
            
            # Для кампаний, которые не нашлись нигде
            still_not_found = not_found - found_via_cpm_cpc
            if still_not_found:
                print(f"   ❌ Не найдено ни в одном API: {len(still_not_found)} кампаний")
                
                for campaign_id in still_not_found:
                    campaign_info = campaigns.get(campaign_id, {})
                    detail = {
                        'Компания': company_name,
                        'ID кампании': campaign_id,
                        'Название кампании': campaign_info.get('name', 'Без названия'),
                        'Статус': campaign_info.get('status'),
                        'Тип кампании': campaign_info.get('type'),
                        'Источник списания (UPD)': campaign_info.get('payment_type', ''),
                        'Статус (auction)': None,
                        'Дата создания': None,
                        'Дата начала': None,
                        'Дата окончания': None,
                        'Тип ставки': 'Неизвестный тип',
                        'ID предмета': None,
                        'Название предмета': None,
                        'Ставка в поиске': None,
                        'Ставка в рекомендациях': None,
                        'Артикулы WB (nm_id)': 'Недоступно',
                        'Количество артикулов': 0,
                        'API метод': 'НЕ НАЙДЕНО',
                    }
                    all_details.append(detail)
        
        company_details = [d for d in all_details if d['Компания'] == company_name]
        print(f"\n[{company_name}] ✅ Всего записей: {len(company_details)}")
        print(f"   - Через auction API: {len([d for d in company_details if d.get('API метод') == 'auction/adverts'])}")
        print(f"   - Через CPM/CPC API: {len([d for d in company_details if d.get('API метод') == 'cpm/list или cpc/list'])}")
        print(f"   - Не найдено ни в одном API: {len([d for d in company_details if d.get('API метод') == 'НЕ НАЙДЕНО'])}")
        
        # Пауза между компаниями
        print(f"⏳ Пауза 2 секунды перед следующей компанией...")
        time.sleep(2)
    
    return all_details


def save_to_excel(details, filename='campaign_details.xlsx'):
    """
    Сохраняет детальную информацию в Excel файл
    
    Args:
        details: список словарей с информацией о кампаниях
        filename: имя файла
    """
    filepath = f'/home/baakhofficial/wbauto/bahram/{filename}'
    
    if not details:
        print("⚠️ Нет данных для сохранения в Excel")
        return
    
    print(f"\n💾 Сохранение {len(details)} записей в Excel...")
    
    # Создаем DataFrame
    df = pd.DataFrame(details)
    
    # Названия статусов
    status_names = {
        -1: "Удалена",
        4: "Готова к запуску",
        7: "Завершена",
        8: "Отменена",
        9: "Активна",
        11: "На паузе"
    }
    
    # Добавляем расшифровку статусов
    df['Статус (название)'] = df['Статус'].map(status_names)
    
    # Сортируем по компании и ID кампании
    df = df.sort_values(['Компания', 'ID кампании'])
    
    # Переупорядочиваем колонки
    columns_order = [
        'Компания',
        'ID кампании',
        'Название кампании',
        'Статус',
        'Статус (название)',
        'Тип кампании',
        'Источник списания (UPD)',
        'API метод',
        'Тип ставки',
        'Ставка в поиске',
        'Ставка в рекомендациях',
        'Артикулы WB (nm_id)',
        'Количество артикулов',
        'ID предмета',
        'Название предмета',
        'Дата создания',
        'Дата начала',
        'Дата окончания',
        'Статус (auction)'
    ]
    
    # Используем только те колонки, которые есть в df
    columns_order = [col for col in columns_order if col in df.columns]
    df = df[columns_order]
    
    # Сохраняем в Excel
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Кампании', index=False)
        
        # Получаем workbook и worksheet для форматирования
        worksheet = writer.sheets['Кампании']
        
        # Форматируем заголовки
        header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
        header_font = Font(bold=True, color='FFFFFF')
        
        for cell in worksheet[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # Автоширина колонок
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    print(f"✅ Данные сохранены в {filepath}")
    print(f"📊 Записей: {len(df)}")
    print(f"🏢 Компаний: {df['Компания'].nunique()}")


def save_to_json(data, filename='campaign_statuses.json'):
    """Сохраняет данные в JSON файл"""
    filepath = f'/home/baakhofficial/wbauto/bahram/{filename}'
    
    # Конвертируем для JSON (int ключи -> str)
    json_data = {}
    for company, campaigns in data.items():
        json_data[company] = {
            str(camp_id): info for camp_id, info in campaigns.items()
        }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Данные сохранены в {filepath}")


def main():
    print("="*60)
    print("🚀 ЗАПУСК СКРИПТА ПОЛУЧЕНИЯ СТАТУСОВ КАМПАНИЙ")
    print("="*60)
    
    # Получаем API ключи
    api_keys_dict = get_api_keys(credentials_file)
    
    # Получаем статусы всех кампаний
    all_campaigns = get_all_campaigns_with_statuses(api_keys_dict, days_back=31)
    
    # Сохраняем в JSON
    save_to_json(all_campaigns)
    
    # Получаем детальную информацию через auction API
    campaign_details = get_all_auction_details(api_keys_dict, all_campaigns)
    
    # Сохраняем в Excel
    save_to_excel(campaign_details)
    
    # Итоговая статистика
    print("\n" + "="*60)
    print("📊 ИТОГОВАЯ СТАТИСТИКА")
    print("="*60)
    
    total_campaigns = sum(len(camps) for camps in all_campaigns.values())
    total_valid = sum(
        len([c for c, info in camps.items() if info['status'] in [7, 9, 11]])
        for camps in all_campaigns.values()
    )
    
    # Считаем статистику по методам получения данных
    auction_found = len([d for d in campaign_details if d.get('API метод') == 'auction/adverts'])
    cpm_cpc_found = len([d for d in campaign_details if d.get('API метод') == 'cpm/list или cpc/list'])
    not_found = len([d for d in campaign_details if d.get('API метод') == 'НЕ НАЙДЕНО'])
    
    print(f"🏢 Обработано компаний: {len(all_campaigns)}")
    print(f"📊 Всего уникальных кампаний из UPD: {total_campaigns}")
    print(f"✅ Кампаний для fullstats (7,9,11): {total_valid}")
    print(f"❌ Кампаний с другими статусами: {total_campaigns - total_valid}")
    print(f"\n📋 Детальных записей получено: {len(campaign_details)}")
    print(f"   ✅ Через auction API (ручные ставки): {auction_found}")
    print(f"   ✅ Через CPM/CPC API (авто ставки): {cpm_cpc_found}")
    print(f"   ❌ Не найдено ни в одном API: {not_found}")
    print(f"\n✅ Всего с nm_id: {auction_found + cpm_cpc_found}")
    
    if not_found > 0:
        print(f"\n⚠️  ВНИМАНИЕ: {not_found} кампаний не найдены ни в одном API")
        print(f"   Для них nm_id недоступны")
    
    print("\n✅ Скрипт завершён успешно!")


if __name__ == "__main__":
    main()

