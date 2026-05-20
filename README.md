# ReelsBot — Reel Memory Agent

Share a Reel → AI watches it → extracts knowledge, preferences, and todos → searchable forever.

## Setup

```bash
pip install -r requirements.txt
```

### Environment variables
```env
GEMINI_API_KEY=your-key-from-aistudio.google.com
TELEGRAM_BOT_TOKEN=your-token-from-@BotFather
```

### Run
```bash
python bot/bot.py
```

---

## Commands

| Action | What to send |
|---|---|
| Save a Reel | Paste the URL |
| Save with context | `https://instagram.com/reel/xxx I want this desk setup` |
| Ask a question | `/ask what do I know about fermentation?` |
| Search memories | `/search minimal workspace` |
| Reflect on saves | `/reflect` |
| Visual memory graph | `/graph` |
| List recent saves | `/memories` |
| List recent saves (custom) | `/memories 20` |
| Find connected memories | `/related a4555f96` or `/related japanese cooking` |
| See your todos | `/todos` |
| List collections | `/collections` |
| Delete a memory | `/delete a4555f96` |

---

## Models

| Task | Model |
|---|---|
| Video analysis (URL paste) | Gemini 2.5 Flash |
| `/ask` and `/reflect` synthesis | Gemini 2.5 Flash-Lite |
| `/reflect` final reflection | Gemini 2.5 Pro |

---

## Project structure

```
reelsbot/
├── bot/
│   └── bot.py                  # Telegram bot — all commands, guardrails, routing
├── core/
│   ├── analyze.py              # Sends video to Gemini, returns structured JSON memory
│   ├── ingest.py               # Downloads video via yt-dlp, duration check
│   ├── memory.py               # ChromaDB read/write, namespaced by user_id
│   ├── graph.py                # NetworkX graph — links memories by semantic similarity
│   └── visualize.py            # Pyvis HTML graph generator with recency colour coding
├── data/
│   ├── videos/                 # Temp folder — videos deleted after analysis
│   ├── chroma/                 # Persistent vector DB (do NOT delete)
│   └── graphs/                 # Generated HTML graphs + NetworkX JSON files
├── backfill_graph.py           # One-time script to link all existing memories into graph
├── CHANGELOG.md                # Full history of every change made to the project
├── requirements.txt
├── .env
└── .gitignore
```

---

## Getting API keys

- **Gemini API key** — [aistudio.google.com](https://aistudio.google.com) → Get API Key
- **Telegram bot token** — Message `@BotFather` on Telegram → `/newbot`
- **Your Telegram user ID** — Message `@userinfobot` on Telegram

---

## Locking down to specific users

In `bot/bot.py`, add your Telegram ID to `ALLOWED_USERS`:

```python
ALLOWED_USERS: set[int] = {
    123456789,  # your ID from @userinfobot
}
```

Leave it empty to allow anyone (dev mode).

---

## Backfilling the graph

If you saved memories before the graph module was added, run once:

```bash
python backfill_graph.py YOUR_TELEGRAM_USER_ID
```

Your user ID appears in the terminal as `user=XXXXXXX` when you save a memory.

---

## Instagram note

Instagram throttles anonymous downloads. If yt-dlp fails on private content, run:

```bash
yt-dlp --cookies-from-browser chrome <url>
```

Then add `"--cookies-from-browser", "chrome"` to the cmd list in `core/ingest.py`.
