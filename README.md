# 🧠 ReelsBot — Your Personal Video Memory Brain

> **Product Statement:** We help content consumers turn saved short-form videos (Reels, TikToks, Shorts) into a structured personal knowledge engine. ReelsBot automatically transcribes, indexes, and semantically links your saves via a Telegram bot and interactive web dashboard so you never lose the value of what you scroll.

---

## 📖 Layman's vs. Judge's Pitch

### 🧑‍💻 Layman's Explanation (What it does)
We all save educational videos, recipe hacks, and tech tutorials on Instagram, TikTok, or YouTube Shorts, but they disappear into a black box we never open again. ReelsBot is a Telegram bot that watches these videos for you, summarizes them, extracts a list of things to do (todos), and places them on an interactive knowledge map that you can search or ask questions to.

### ⚖️ Judge's Pitch (How it works & technical leverage)
ReelsBot leverages Gemini's multimodal audio-visual understanding to parse, transcribe, and structure raw short-form video content shared via social media. The data is processed through a dual pipeline:
1. **ChromaDB Vector Store** for dense semantic search and RAG-based (Retrieval-Augmented Generation) Q&A.
2. **NetworkX Topological Graph** using sentence-transformers to calculate cosine similarity between memories, mapping them into an interactive HTML visualization.

This goes beyond a simple LLM wrapper: it builds a stateful, namespaced memory graph that updates incrementally as the user interacts with the bot, turning passive scrolling into an structured, queryable knowledge engine.

---

## 🛠️ Built With

*   **Languages:** Python (Core logic & backend)
*   **APIs:** Google Gemini API (Gemini 2.5 Flash for multimodal video analysis, Gemini 2.5 Flash-Lite for semantic Q&A, Gemini 2.5 Pro for timeline reflections)
*   **Databases:** ChromaDB (Vector database for local semantic indexing)
*   **Embeddings:** SentenceTransformers (`all-MiniLM-L6-v2` for generating dense vector representations locally)
*   **Graph Engine:** NetworkX (Topological structure) & Pyvis (Interactive HTML network visualization)
*   **Web Framework:** Flask (Dashboard and serving the knowledge map)
*   **Interfaces:** Telegram Bot API (via `python-telegram-bot`)
*   **Media Processing:** `yt-dlp` (For video ingestion and downloading)
*   **Deployment:** Railway (Cloud hosting)

---

## ⚙️ Setup

```bash
pip install -r requirements.txt
```

### Environment variables
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=your-key-from-aistudio.google.com
TELEGRAM_BOT_TOKEN=your-token-from-@BotFather
OWNER_USER_ID=your-telegram-id-from-@userinfobot
BASE_URL=https://your-railway-url.up.railway.app
```

### Run Locally
```bash
# Start Telegram bot
python bot/bot.py

# Start Web dashboard
python web/app.py
```

---

## 🕹️ Commands

| Action | What to send / Command |
|---|---|
| **Save a Reel** | Paste the URL |
| **Save with context** | `[URL] I want this desk setup` |
| **Ask a question** | `/ask what do I know about fermentation?` |
| **Search memories** | `/search minimal workspace` |
| **Reflect on saves** | `/reflect` |
| **Visual memory graph** | `/graph` |
| **List recent saves** | `/memories` |
| **Find connected memories** | `/related <id>` or `/related <topic>` |
| **See your todos** | `/todos` |
| **List collections** | `/collections` |
| **Web Dashboard login** | `/login` |
| **Delete a memory** | `/delete <id>` |
| **Help menu** | `/help` |

---

## 📁 Project Structure

```
reelsbot/
├── bot/
│   └── bot.py                  # Telegram bot — commands, routing, and scheduler
├── core/
│   ├── analyze.py              # Sends video to Gemini, returns structured JSON memory
│   ├── ingest.py               # Downloads video via yt-dlp, duration check
│   ├── memory.py               # ChromaDB vector index read/write
│   ├── graph.py                # NetworkX graph builder
│   └── visualize.py            # Pyvis HTML graph generator with premium styles
├── data/
│   ├── chroma/                 # Persistent vector DB
│   └── graphs/                 # Generated HTML graphs
├── web/
│   ├── app.py                  # Flask web dashboard backend
│   └── templates/
│       └── index.html          # Premium dashboard frontend UI
├── requirements.txt
├── .env
└── .gitignore
```
