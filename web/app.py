"""
app.py — ReelsBot web frontend
Run with: python web/app.py
Access at: http://localhost:5000
On your phone: http://[your-laptop-ip]:5000
"""

import os
import sys
import json
import re

from flask import Flask, render_template, jsonify, send_file
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from core.memory import get_recent_memories, list_collections

app = Flask(__name__)

OWNER_USER_ID = int(os.environ.get("OWNER_USER_ID", 0))
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "chroma")
GRAPH_DIR  = os.path.join(os.path.dirname(__file__), "..", "data", "graphs")


def _get_chroma_col(name: str):
    import chromadb
    from chromadb.utils import embedding_functions
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    return client.get_collection(name=name, embedding_function=ef)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/memories")
def api_memories():
    """All memories with source_url, collections, and priority attached."""
    memories = get_recent_memories(OWNER_USER_ID, limit=500)

    # Fetch full metadata from ChromaDB to get source_url, collections, priority
    try:
        col = _get_chroma_col(f"u{OWNER_USER_ID}_memories")
        results = col.get(include=["metadatas"])
        meta_map = {
            results["ids"][i]: meta
            for i, meta in enumerate(results["metadatas"])
        }
        for m in memories:
            meta = meta_map.get(m["id"], {})
            m["source_url"]  = meta.get("source_url", "")
            m["collections"] = json.loads(meta.get("collections_json", "[]"))
            m["priority"]    = meta.get("priority", "medium")
    except Exception:
        for m in memories:
            m.setdefault("source_url", "")
            m.setdefault("collections", [])
            m.setdefault("priority", "medium")

    return jsonify(memories)


@app.route("/api/collections")
def api_collections():
    """All collection names (excluding the root memories collection)."""
    cols = sorted(c for c in list_collections(OWNER_USER_ID) if c != "memories")
    return jsonify(cols)


@app.route("/api/graph")
def api_graph():
    """Serve the pre-generated pyvis graph HTML."""
    graph_path = os.path.join(GRAPH_DIR, f"u{OWNER_USER_ID}_graph.html")

    if not os.path.exists(graph_path):
        try:
            from core.visualize import generate_graph
            graph_path = generate_graph(OWNER_USER_ID)
        except Exception:
            pass

    if graph_path and os.path.exists(graph_path):
        return send_file(graph_path)

    return "No graph yet — save at least 2 Reels first.", 404


if __name__ == "__main__":
    if not OWNER_USER_ID:
        print("⚠️  Add OWNER_USER_ID=your_telegram_id to your .env file")
        raise SystemExit(1)

    import socket
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "your-laptop-ip"

    print(f"🌐 ReelsBot web UI")
    print(f"   Local:  http://localhost:5000")
    print(f"   Phone:  http://{local_ip}:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)