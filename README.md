# 🧠 ReelsBot — Your Personal Video Memory Brain

> **Don't want to self-host or set up API keys?** [Try the official hosted ReelsBot on Telegram!](https://t.me/Reeeeeelssssbot) (First 50 reels free, top-up packs available).

### TL;DR
ReelsBot turns the black box of saved short-form videos (Reels, TikToks, Shorts) into a searchable, interactive personal knowledge graph. Send any video link to the Telegram bot, and it transcribes, vectorizes, and maps it using Gemini and local embeddings so you can query or reflect on your video library instantly.

---

## 📖 Product Concept

### 🧑‍💻 What it does
We all save educational videos, recipes, tutorials, or ideas on Instagram, TikTok, or YouTube Shorts, but they disappear into a saved folder we never look at again. A black hole, if you will.
ReelsBot watches these videos for you, summarizes them, extracts todos, and puts them on an interactive concept map. You can search your library, ask questions of your memories (e.g., "/ask what were those desk setups I saved?"), or get automated weekly reflections.

### How it works
ReelsBot processes short-form video payloads through a multimodal pipeline:
1. **Multimodal Analysis:** Gemini API (2.5 Flash) ingests raw video assets via `yt-dlp` to extract structural summaries, user intent, suggested collections, and priority queues.
2. **Dense Vector Indexing:** ChromaDB stores namespaced document embeddings locally via `sentence-transformers` for semantic querying and contextual RAG.
3. **Topological Similarity Mapping:** A NetworkX graph calculates cosine similarity matrices between saved items, outputting interactive graph maps rendered using PyVis.

---

## 🛠️ Built With

*   **Languages:** Python
*   **APIs:** Google GenAI SDK (Gemini 2.5 Flash & Flash-Lite)
*   **Vector Engine:** ChromaDB (Local namespaced indexes)
*   **Similarity Embeddings:** SentenceTransformers (`all-MiniLM-L6-v2` locally)
*   **Graph Engine:** NetworkX & Pyvis (Interactive HTML network visualizations)
*   **Web Ingress & Dashboard:** Flask
*   **Interfaces:** Telegram Bot API
*   **Worker dependencies:** `yt-dlp` and `ffmpeg`

---

## ⚙️ Setup

### Installation
```bash
pip install -r requirements.txt
```

### Environment variables
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=your-key-from-aistudio.google.com
TELEGRAM_BOT_TOKEN=your-token-from-@BotFather
OWNER_USER_ID=your-telegram-id-from-@userinfobot
BASE_URL=http://localhost:5000
```

### Run Locally
```bash
# Navigate to the folder
cd reelsbot 

# Start Telegram bot
python bot/bot.py

# Start Web dashboard
python web/app.py
```

### Deploy on Railway

Use **two services** from the same repo. Each service runs one process (start command: `bash start.sh`).

| Service | `APP_ROLE` | What it does |
|---|---|---|
| **web** | `web` | Flask dashboard (default if `APP_ROLE` is unset) |
| **bot** | `bot` | Telegram bot — **required for bot replies** |

Shared variables on both services: `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `OWNER_USER_ID`, `BASE_URL`, `HF_HOME=/app/data/hf_cache`, `FLASK_SECRET_KEY`.

Mount a persistent volume at `/app/data` on **both** services so ChromaDB and the HF model cache survive restarts.

**Verify the bot service logs contain:**
```
[start.sh] APP_ROLE=bot
Telegram bot ready — polling as @YourBotName
ReelsBot starting polling loop...
```

If you only see Flask/Werkzeug logs, the bot is not running — add a second service with `APP_ROLE=bot`.

**Common gotcha:** Do not run the bot locally and on Railway at the same time with the same token; only one process can poll Telegram updates.

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
