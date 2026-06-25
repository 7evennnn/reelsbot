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
from datetime import timedelta

from flask import Flask, render_template, jsonify, send_file, session, redirect, url_for, request
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from core.memory import get_recent_memories, list_collections

app = Flask(__name__)

# Cryptographically sign sessions. Fallback to a random key if not configured in .env
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "reelsbot-signed-session-cookie-key-928374")
app.permanent_session_lifetime = timedelta(days=30)

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
    # Render index.html. The frontend will inspect if we are logged in or not
    user_id = session.get("user_id")
    return render_template("index.html", authenticated=bool(user_id), user_id=user_id)


@app.route("/login")
def login():
    token = request.args.get("token")
    if not token:
        return render_template("index.html", authenticated=False, error="No login token provided. Please request a new link via /login in your Telegram bot.")
    
    from core.auth import verify_login_token
    user_id = verify_login_token(token)
    if not user_id:
        return render_template("index.html", authenticated=False, error="This magic link is invalid or has expired. Please run /login in your Telegram bot to generate a new one.")
        
    session["user_id"] = user_id
    session.permanent = True
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("index"))


@app.route("/api/user")
def api_user():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"authenticated": False})
    return jsonify({"authenticated": True, "user_id": user_id})


@app.route("/api/memories")
def api_memories():
    """All memories for the currently authenticated user."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    memories = get_recent_memories(user_id, limit=500)

    # Fetch full metadata from ChromaDB to get source_url, collections, priority
    try:
        col = _get_chroma_col(f"u{user_id}_memories")
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
    """All collections names for the currently authenticated user."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    cols = sorted(c for c in list_collections(user_id) if c != "memories")
    return jsonify(cols)


@app.route("/api/graph")
def api_graph():
    """Serve the user-specific pre-generated pyvis graph HTML."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    graph_path = os.path.join(GRAPH_DIR, f"u{user_id}_graph.html")

    if not os.path.exists(graph_path):
        try:
            from core.visualize import generate_graph
            graph_path = generate_graph(user_id)
        except Exception:
            pass

    if graph_path and os.path.exists(graph_path):
        return send_file(graph_path)

    return "No graph yet — save at least 2 Reels first.", 404


if __name__ == "__main__":
    # Railway provides the PORT environment variable. 
    # Default to 5000 for local development.
    port = int(os.environ.get("PORT", 5000))
    
    # Binding to 0.0.0.0 is required for the app to be reachable 
    # outside the container.
    app.run(host="0.0.0.0", port=port)