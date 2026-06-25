#!/bin/bash
# Start the Telegram bot in the background
python3 bot/bot.py &

# Start the Flask web dashboard in the foreground
python3 web/app.py