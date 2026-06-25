# 🧠 ReelsBot — Your Personal Video Memory Brain

> **YC Product Statement:** We help content consumers turn saved short-form videos (Reels, TikToks, Shorts) into a structured personal knowledge engine. ReelsBot automatically transcribes, indexes, and semantically links your saves via a Telegram bot and interactive web dashboard so you never lose the value of what you scroll.

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

## 📖 The Story of ReelsBot

### 💡 Inspiration
We found ourselves constantly saving reels about coding tips, productivity hacks, and recipes, only to realize that Instagram's "Saved" folder is a graveyard. It's unsearchable and offers zero actionability. We wanted to build a bridge between our passive scrolling habits and our active workspace—allowing us to simply drop a link and have an AI extract, connect, and remember the value for us.

### 🏗️ How We Built It
We structured ReelsBot to be mobile-first (via Telegram) and desktop-optimized (via Flask):
1. **Ingestion & Multimodal Analysis:** When a URL is shared, the backend downloads the video. We pass the raw video to Gemini 2.5 Flash, prompting it to watch, transcribe, and return a structured JSON memory containing key takeaways, actionable todos, and suggested collections.
2. **Vector and Graph Databases:** The summary and tags are converted to vector embeddings and stored in ChromaDB. Simultaneously, we add the memory to a NetworkX graph, drawing edges to other memories if their cosine similarity exceeds a specific threshold.
3. **Interactive Dashboard:** We built a Flask web dashboard that renders the user's memories, filters them by priority/intent, and loads an interactive knowledge graph mapping out their brain.

### 🚧 Challenges We Ran Into
*   **Multimodal Audio-Visual Ingestion:** Downloading and handling large video payloads on low-bandwidth connections was a bottleneck. We implemented strict duration limits and local cleanup protocols to keep the server lean.
*   **Unicode Encoding on Windows Consoles:** Emojis and special characters in logs caused crash loops. We solved this by forcing UTF-8 output encoding across the runtime.
*   **HTML Escaping in Interactive Tooltips:** Pyvis's default string tooltips printed raw HTML tags like `<b>` instead of rendering them. We wrote a custom post-processing script to intercept the generated HTML and dynamically parse tooltip titles into browser-native HTML DOM elements before initializing the network.

### 🏆 Accomplishments We're Proud Of
*   **Real Multimodal Gemini Leverage:** Instead of just sending a transcript to an LLM, our pipeline feeds the actual visual video frames and audio to Gemini 2.5 Flash, allowing it to capture code snippets on-screen or visual details that transcripts miss.
*   **Zero-friction Login:** The `/login` command in Telegram uses a 15-minute, single-use cryptographically signed magic link to securely sign users into the web dashboard without needing passwords.
*   **Visualizing Thought:** Seeing our randomly saved reels organize themselves into beautiful, interconnected gold nodes on the interactive memory graph.

### 🎓 What We Learned
*   **RAG is more than text search:** Combining vector-based semantic retrieval (ChromaDB) with graph-based relational structures (NetworkX) creates a significantly more intuitive search experience than vector retrieval alone.
*   **Designing for constraints:** When you only have 2 hours left before a submission, prioritizing the core user flow (dropping a link -> seeing it on the graph) keeps the scope clean.

### 🚀 What's Next for ReelsBot
*   **Audio Briefings (ElevenLabs):** Send a daily or weekly brief using custom synthesized audio summaries of what you saved.
*   **Browser Extensions:** Auto-capture shared links from Instagram/TikTok directly from the desktop browser.
*   **Collaborative Vaults:** Shared memory graphs for teams to build collective research spaces.

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
