#!/bin/bash

BOT_TOKEN="8130004725:AAGZIwLuaVv2sZHsECfaMWxxE0s7coAT1Cw"
CHAT_ID="427881502"
FAIL_FLAG="/tmp/cron_failures.flag"

if [ -z "$1" ]; then
  /usr/bin/curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
    -d chat_id=$CHAT_ID \
    -d text="❌ Враппер запущен без указания скрипта!"
  exit 1
fi

SCRIPT=$1
SCRIPT_NAME=$(basename "$SCRIPT")
MONITOR_DIR="/tmp/cron_monitor"
cd "$(dirname "$SCRIPT")" || exit 1

# Создаем директорию для мониторинга, если её нет
mkdir -p "$MONITOR_DIR"

# Обновляем файл последнего запуска для мониторинга
echo "$(date +%s)" > "$MONITOR_DIR/${SCRIPT_NAME}.last_run"

# Функция для проверки времени отправки ежедневного отчёта (16:00)
check_daily_report_time() {
  local last_report_file="/tmp/last_daily_report.date"
  local current_date=$(date '+%Y-%m-%d')
  local current_hour=$(date '+%H')
  
  # Если файл с последней датой отчёта не существует, создаём его
  if [ ! -f "$last_report_file" ]; then
    echo "$current_date" > "$last_report_file"
    # Если сейчас 16:00 или позже, отправляем отчёт
    if [ "$current_hour" -ge 16 ]; then
      return 0  # Отправляем отчёт
    else
      return 1  # Не отправляем отчёт
    fi
  fi
  
  # Читаем дату последнего отчёта
  local last_date=$(cat "$last_report_file" 2>/dev/null || echo "")
  
  # Если дата изменилась и сейчас 16:00 или позже, обновляем файл и отправляем отчёт
  if [ "$last_date" != "$current_date" ] && [ "$current_hour" -ge 16 ]; then
    echo "$current_date" > "$last_report_file"
    return 0  # Отправляем отчёт
  else
    return 1  # Не отправляем отчёт
  fi
}

# Функция для добавления успешного скрипта в список
add_successful_script() {
  local script_name="$1"
  local success_file="/tmp/successful_scripts_24h.txt"
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  
  # Добавляем скрипт с полной датой и временем выполнения в файл
  echo "$script_name ($timestamp)" >> "$success_file"
}

# Функция для отправки ежедневного отчёта об успешных скриптах
send_daily_success_report() {
  local success_file="/tmp/successful_scripts_24h.txt"
  
  if [ -f "$success_file" ] && [ -s "$success_file" ]; then
    local script_count=$(wc -l < "$success_file")
    local scripts_list=$(cat "$success_file" | tr '\n' '\n' | head -20)  # Ограничиваем до 20 скриптов
    
    local current_time=$(date '+%H:%M:%S')
    local message="✅ Ежедневный отчёт об успешных скриптах%0A%0A🕐 Время отправки: $current_time%0A📊 Всего успешно выполнено за последние 24 часа: $script_count скриптов%0A%0A📝 Список скриптов:%0A$scripts_list"
    
    if [ $script_count -gt 20 ]; then
      message="${message}%0A%0A... и ещё $((script_count - 20)) скриптов"
    fi
    
    /usr/bin/curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
      -d chat_id=$CHAT_ID \
      -d text="$message"
    
    # Очищаем файл после отправки отчёта
    rm -f "$success_file"
  fi
}

# ====== Запуск скрипта и ловим stderr ======
START_TIME=$(date)
ERR_MSG=$(/usr/bin/python3 "$SCRIPT" 2>&1)
STATUS=$?
END_TIME=$(date)

if [ $STATUS -ne 0 ]; then
  # ставим флаг падения для дневного отчёта
  touch "$FAIL_FLAG"

  # отправляем Telegram сообщение с текстом ошибки (каждый раз при неуспешном выполнении)
  /usr/bin/curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
    -d chat_id=$CHAT_ID \
    -d text="❌ Скрипт $SCRIPT_NAME упал с кодом $STATUS%0A%0A🕐 Время: $START_TIME%0A%0A$(echo "$ERR_MSG" | head -n 20 | sed 's/"/\\"/g')"
else
  # Добавляем успешный скрипт в список для ежедневного отчёта
  add_successful_script "$SCRIPT_NAME"
  
  # Проверяем, нужно ли отправить ежедневный отчёт об успешных скриптах
  if check_daily_report_time; then
    send_daily_success_report
  fi
fi
