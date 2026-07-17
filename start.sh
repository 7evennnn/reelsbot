#!/bin/bash
set -euo pipefail

# Railway needs TWO services from this repo (web + bot). One container cannot
# reliably run both — loading the embedding model twice causes OOM kills.
#   Service "web": APP_ROLE=web
#   Service "bot": APP_ROLE=bot
ROLE="${APP_ROLE:-web}"

echo "[start.sh] APP_ROLE=${ROLE}"

if [ "$ROLE" = "bot" ]; then
  echo "[start.sh] Starting Telegram bot (polling)..."
  exec python3 bot/bot.py
elif [ "$ROLE" = "web" ]; then
  echo "[start.sh] Starting Flask web dashboard..."
  exec python3 web/app.py
else
  echo "[start.sh] Invalid APP_ROLE: $ROLE (expected: web or bot)"
  exit 1
fi