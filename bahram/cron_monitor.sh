#!/bin/bash

BOT_TOKEN="8130004725:AAGZIwLuaVv2sZHsECfaMWxxE0s7coAT1Cw"
CHAT_ID="427881502"
MONITOR_DIR="/tmp/cron_monitor"

# Создаем директорию для мониторинга, если её нет
mkdir -p "$MONITOR_DIR"

# Функция для отправки уведомления в Telegram
send_telegram() {
  local message="$1"
  /usr/bin/curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
    -d chat_id=$CHAT_ID \
    -d text="$message"
}

# Функция для проверки расписания cron
check_cron_schedule() {
  local script_name="$1"
  local cron_schedule="$2"
  local tolerance_minutes="$3"  # Допустимая задержка в минутах
  
  local monitor_file="$MONITOR_DIR/${script_name}.last_run"
  local current_time=$(date +%s)
  local tolerance_seconds=$((tolerance_minutes * 60))
  
  # Парсим расписание cron
  local minute=$(echo "$cron_schedule" | awk '{print $1}')
  local hour=$(echo "$cron_schedule" | awk '{print $2}')
  local day=$(echo "$cron_schedule" | awk '{print $3}')
  local month=$(echo "$cron_schedule" | awk '{print $4}')
  local weekday=$(echo "$cron_schedule" | awk '{print $5}')
  
  # Проверяем, должен ли скрипт запускаться сейчас
  local should_run=false
  
  # Простая проверка для минутных задач (* * * * *)
  if [[ "$minute" == "*" && "$hour" == "*" && "$day" == "*" && "$month" == "*" && "$weekday" == "*" ]]; then
    should_run=true
  # Проверка для задач каждые N минут (*/N * * * *)
  elif [[ "$minute" =~ ^\*/[0-9]+$ ]]; then
    local interval=$(echo "$minute" | cut -d'/' -f2)
    local current_minute=$(date +%M)
    if [ $((current_minute % interval)) -eq 0 ]; then
      should_run=true
    fi
  # Проверка для часовых задач (0 * * * *)
  elif [[ "$minute" == "0" && "$hour" == "*" ]]; then
    local current_minute=$(date +%M)
    if [ "$current_minute" == "00" ]; then
      should_run=true
    fi
  # Проверка для ежедневных задач (0 0 * * *)
  elif [[ "$minute" == "0" && "$hour" == "0" ]]; then
    local current_minute=$(date +%M)
    local current_hour=$(date +%H)
    if [ "$current_minute" == "00" ] && [ "$current_hour" == "00" ]; then
      should_run=true
    fi
  fi
  
  if [ "$should_run" = true ]; then
    # Проверяем, когда скрипт последний раз запускался
    if [ -f "$monitor_file" ]; then
      local last_run=$(cat "$monitor_file" 2>/dev/null || echo "0")
      local time_diff=$((current_time - last_run))
      
      # Если прошло больше времени, чем допустимо + толерантность
      if [ $time_diff -gt $tolerance_seconds ]; then
        send_telegram "⚠️ Скрипт $script_name не запускался по расписанию!%0A%0A📅 Расписание: $cron_schedule%0A⏰ Последний запуск: $(date -d @$last_run)%0A🕐 Текущее время: $(date)%0A⏱️ Задержка: $((time_diff / 60)) минут"
        return 1
      fi
    else
      # Если файл не существует, создаем его
      echo "$current_time" > "$monitor_file"
    fi
  fi
  
  return 0
}

# Список скриптов для мониторинга с их расписанием и толерантностью
declare -A scripts=(
  ["products.py"]="* * * * * 5"           # каждую минуту, толерантность 5 минут
  ["upload_to_bd.py"]="* * * * * 5"       # каждую минуту, толерантность 5 минут
  ["fbs_update_new.py"]="0 * * * * 10"    # каждый час, толерантность 10 минут
  ["get_orders.py"]="30 * * * * 10"        # каждый час в :30, толерантность 10 минут
  ["detail_orders.py"]="40 * * * * 10"     # каждый час в :40, толерантность 10 минут
  ["report_paid_storage.py"]="35 * * * * 10" # каждый час в :35, толерантность 10 минут
  ["reports_acceptace.py"]="30 * * * * 10"  # каждый час в :30, толерантность 10 минут
  ["profit_report.py"]="43 * * * * 10"     # каждый час в :43, толерантность 10 минут
  ["add_new_nms_to_corrected_list.py"]="*/5 * * * * 10" # каждые 5 минут, толерантность 10 минут
  ["get_goods_return.py"]="23 * * * * 10"  # каждый час в :23, толерантность 10 минут
  ["update_data_for_daily_orders_analyst.py"]="0 * * * * 10" # каждый час, толерантность 10 минут
  ["update_google_table_analiz_prodazh.py"]="5 * * * * 10" # каждый час в :05, толерантность 10 минут
  ["adv_upd_sum.py"]="40 */4 * * * 15"     # каждые 4 часа в :40, толерантность 15 минут
  ["articles_export.py"]="0 0 * * * 30"   # каждый день в 00:00, толерантность 30 минут
  ["fbo_update_new.py"]="0 1 * * * 30"    # каждый день в 01:00, толерантность 30 минут
  ["adv_full_stats.py"]="20 */4 * * * 15" # каждые 4 часа в :20, толерантность 15 минут
  ["detail_fin_reports.py"]="0 12 * * * 30" # каждый день в 12:00, толерантность 30 минут
  ["get_deductions.py"]="0 18 * * * 30"   # каждый день в 18:00, толерантность 30 минут
  ["get_documents_list.py"]="0 20 * * * 30" # каждый день в 20:00, толерантность 30 минут
)

# Проверяем каждый скрипт
for script in "${!scripts[@]}"; do
  schedule_info="${scripts[$script]}"
  cron_schedule=$(echo "$schedule_info" | awk '{print $1, $2, $3, $4, $5}')
  tolerance=$(echo "$schedule_info" | awk '{print $6}')
  
  check_cron_schedule "$script" "$cron_schedule" "$tolerance"
done
