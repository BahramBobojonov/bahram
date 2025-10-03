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
cd "$(dirname "$SCRIPT")" || exit 1

# ====== Запуск скрипта и ловим stderr ======
ERR_MSG=$(/usr/bin/python3 "$SCRIPT" 2>&1)
STATUS=$?

if [ $STATUS -ne 0 ]; then
  # ставим флаг падения для дневного отчёта
  touch "$FAIL_FLAG"

  # отправляем Telegram сообщение с текстом ошибки (ограничиваем первые 4000 символов, чтобы не было проблем)
  /usr/bin/curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
    -d chat_id=$CHAT_ID \
    -d text="❌ Скрипт $SCRIPT упал с кодом $STATUS на $(date)%0A%0A$(echo "$ERR_MSG" | head -n 20 | sed 's/"/\\"/g')"
fi
