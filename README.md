# OpenClaw — Reel Memory Agent

Share a Reel → AI watches it → extracts knowledge, preferences, and todos → searchable forever.

## Setup

```bash
pip install -r requirements.txt
```

### Environment variables
```bash
export GEMINI_API_KEY="your-key-from-aistudio.google.com"
export TELEGRAM_BOT_TOKEN="your-token-from-@BotFather"
```

### Run
```bash
python bot/bot.py
```

## Usage in Telegram

| Action | What to send |
|---|---|
| Save a Reel | Just paste the URL |
| Save with context | `https://instagram.com/reel/xxx I want this desk setup` |
| Search memories | `/search minimal workspace` |
| See your todos | `/todos` |
| List collections | `/collections` |

## Getting a Telegram Bot Token
1. Open Telegram, message `@BotFather`
2. `/newbot` → follow prompts
3. Copy the token

## Instagram note
Instagram throttles anonymous downloads. If yt-dlp fails on private/logged-in content, run:
```bash
yt-dlp --cookies-from-browser chrome <url>
```
Then add `"--cookies-from-browser", "chrome"` to the cmd list in `core/ingest.py`.

## Project structure
```
openclaw/
├── bot/
│   └── bot.py          # Telegram interface
├── core/
│   ├── analyze.py      # Gemini multimodal analysis
│   ├── ingest.py       # yt-dlp video download
│   └── memory.py       # ChromaDB storage + search
├── data/
│   ├── videos/         # Temp video storage (auto-cleaned)
│   └── chroma/         # Persistent vector DB
└── requirements.txt
```
