"""
memory.py
ChromaDB-backed long-term memory for ReelsBot.
Every collection is namespaced per user — no data leaks between users.
"""

import chromadb
from chromadb.utils import embedding_functions
import json
import os
import uuid
from datetime import datetime
import re

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "chroma")

ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2",
    model_kwargs={"device": "cpu"} # Ensure it doesn't try to look for a GPU
)

client = chromadb.PersistentClient(path=CHROMA_DIR)


def _get_or_create_collection(name: str, user_id: int):
    """All collections are prefixed with the user's Telegram ID."""
    namespaced = f"u{user_id}_{name}"
    return client.get_or_create_collection(
        name=namespaced,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def save_memory(analysis: dict, source_url: str, user_id: int, user_note: str = "") -> str:
    memory_id = uuid.uuid4().hex

    # in save_memory(), replace the embed_text_parts block with:
    topics_str = " ".join(analysis.get("topics", []))
    embed_text_parts = [
        topics_str,                                    # topics first, weighted by repetition
        topics_str,                                    # repeat once so they anchor the vector
        analysis.get("summary", ""),
        " ".join(analysis.get("todos", [])),
        " ".join(analysis.get("preferences_detected", [])),
    ]
    if user_note:
        embed_text_parts.append(f"User note: {user_note}")

    embed_text = " | ".join(p for p in embed_text_parts if p)

    metadata = {
        "source_url": source_url,
        "user_note": user_note,
        "intent_type": analysis.get("user_intent", {}).get("type", "none"),
        "intent_desc": analysis.get("user_intent", {}).get("description") or "",
        "priority": analysis.get("memory_priority", "medium"),
        "topics_json": json.dumps(analysis.get("topics", [])),
        "todos_json": json.dumps(analysis.get("todos", [])),
        "prefs_json": json.dumps(analysis.get("preferences_detected", [])),
        "collections_json": json.dumps(analysis.get("suggested_collections", [])),
        "full_analysis_json": json.dumps(analysis),
        "created_at": datetime.utcnow().isoformat(),
    }

    main_col = _get_or_create_collection("memories", user_id)
    main_col.add(ids=[memory_id], documents=[embed_text], metadatas=[metadata])

    for col_name in analysis.get("suggested_collections", []):
        safe_name = col_name.lower()
        safe_name = re.sub(r'[^a-z0-9._-]', '_', safe_name)  # strip anything invalid
        safe_name = re.sub(r'_+', '_', safe_name)             # collapse runs of underscores
        safe_name = safe_name.strip('_.-')                    # must start/end with alphanumeric
        if len(safe_name) < 3:
            safe_name = f"col_{safe_name}"                    # ChromaDB minimum is 3 chars
        try:
            col = _get_or_create_collection(safe_name, user_id)
            col.add(ids=[memory_id], documents=[embed_text], metadatas=[metadata])
        except Exception as e:
            print(f"[memory] Error saving to sub-collection {safe_name}: {e}")

    print(f"[memory] user={user_id} saved {memory_id} → {analysis.get('suggested_collections', [])}")
    return memory_id


def search(query: str, user_id: int, collection: str = "memories", n_results: int = 5) -> list[dict]:
    col = _get_or_create_collection(collection, user_id)

    if col.count() == 0:
        return []

    results = col.query(
        query_texts=[query],
        n_results=min(n_results, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    memories = []
    for i, meta in enumerate(results["metadatas"][0]):
        memories.append({
            "id": results["ids"][0][i],
            "relevance_score": round(1 - results["distances"][0][i], 3),
            "summary": json.loads(meta["full_analysis_json"]).get("summary", ""),
            "source_url": meta["source_url"],
            "user_note": meta["user_note"],
            "intent": {"type": meta["intent_type"], "description": meta["intent_desc"]},
            "topics": json.loads(meta["topics_json"]),
            "todos": json.loads(meta["todos_json"]),
            "preferences": json.loads(meta["prefs_json"]),
            "priority": meta["priority"],
            "created_at": meta["created_at"],
        })

    return memories


def get_todos(user_id: int) -> list[dict]:
    col = _get_or_create_collection("memories", user_id)
    results = col.get(where={"intent_type": {"$in": ["todo", "interest"]}})

    todos = []
    for i, meta in enumerate(results["metadatas"]):
        items = json.loads(meta.get("todos_json", "[]"))
        if items:
            todos.append({
                "id": results["ids"][i],
                "todos": items,
                "source_url": meta["source_url"],
                "created_at": meta["created_at"],
            })
    return todos


def get_recent_memories(user_id: int, limit: int = 30) -> list[dict]:
    """Fetch the most recent N memories — used by /reflect."""
    col = _get_or_create_collection("memories", user_id)
    if col.count() == 0:
        return []

    results = col.get(include=["metadatas"])
    memories = []
    for i, meta in enumerate(results["metadatas"]):
        analysis = json.loads(meta["full_analysis_json"])
        memories.append({
            "summary": analysis.get("summary", ""),
            "topics": analysis.get("topics", []),
            "todos": analysis.get("todos", []),
            "preferences": analysis.get("preferences_detected", []),
            "user_note": meta.get("user_note", ""),
            "created_at": meta["created_at"],
        })

    memories_with_ids = []
    for meta, mem_id in zip(results["metadatas"], results["ids"]):
        analysis = json.loads(meta["full_analysis_json"])
        memories_with_ids.append({
            "id": mem_id,
            "summary": analysis.get("summary", ""),
            "topics": analysis.get("topics", []),
            "todos": analysis.get("todos", []),
            "preferences": analysis.get("preferences_detected", []),
            "user_note": meta.get("user_note", ""),
            "created_at": meta["created_at"],
        })
    memories_with_ids.sort(key=lambda m: m["created_at"], reverse=True)
    return memories_with_ids[:limit]


def list_collections(user_id: int) -> list[str]:
    prefix = f"u{user_id}_"
    all_cols = [c.name for c in client.list_collections()]
    # Return only this user's collections, with the prefix stripped
    return [name[len(prefix):] for name in all_cols if name.startswith(prefix)]


def delete_memory(short_or_full_id: str, user_id: int) -> str | None:
    """
    Delete a memory by 8-char short ID or full UUID.
    Returns the full ID if deleted, None if not found.
    """
    col = _get_or_create_collection("memories", user_id)

    # Resolve short ID → full ID
    if len(short_or_full_id) <= 8:
        results = col.get(include=["metadatas"])
        full_id = next((mid for mid in results["ids"] if mid.startswith(short_or_full_id)), None)
        if not full_id:
            return None
    else:
        full_id = short_or_full_id

    # Get sub-collections before deleting
    try:
        result = col.get(ids=[full_id], include=["metadatas"])
        if not result["ids"]:
            return None
        collections = json.loads(result["metadatas"][0].get("collections_json", "[]"))
    except Exception:
        return None

    # Delete from main collection
    col.delete(ids=[full_id])

    # Delete from sub-collections
    for col_name in collections:
        safe_name = re.sub(r'[^a-z0-9._-]', '_', col_name.lower().replace(" ", "_"))
        safe_name = re.sub(r'_+', '_', safe_name).strip('_.-')
        if len(safe_name) < 3:
            safe_name = f"col_{safe_name}"
        try:
            sub_col = _get_or_create_collection(safe_name, user_id)
            sub_col.delete(ids=[full_id])
        except Exception:
            pass

    return full_id