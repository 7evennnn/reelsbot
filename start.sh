#!/bin/bash
# Start the Telegram bot in the background
python bot/bot.py &

# Start the Flask web dashboard in the foreground
python web/app.py