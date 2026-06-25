#!/bin/bash
set -euo pipefail

# Choose process role per service/container.
# APP_ROLE=web (default) or APP_ROLE=bot
ROLE="${APP_ROLE:-web}"

if [ "$ROLE" = "bot" ]; then
  exec python3 bot/bot.py
elif [ "$ROLE" = "web" ]; then
  exec python3 web/app.py
else
  echo "Invalid APP_ROLE: $ROLE (expected: web or bot)"
  exit 1
fi