"""
backfill_graph.py
Run this ONCE to build graph edges for all your existing memories.
After this, new saves are linked automatically.

Usage:
    python backfill_graph.py YOUR_TELEGRAM_USER_ID
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from core.graph import add_and_link
import chromadb

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "data", "chroma")

def backfill(user_id: int):
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection_name = f"u{user_id}_memories"

    try:
        col = client.get_collection(name=collection_name)
    except Exception:
        print(f"No memories found for user {user_id}. Send some Reels first!")
        return

    results = col.get(include=["metadatas"])
    ids = results["ids"]
    total = len(ids)

    if total == 0:
        print("No memories to backfill.")
        return

    print(f"Found {total} memories. Building graph links...\n")

    for i, memory_id in enumerate(ids, 1):
        print(f"[{i}/{total}] Linking {memory_id[:8]}...")
        add_and_link(memory_id, user_id)

    print(f"\nDone! Graph built for {total} memories.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backfill_graph.py YOUR_TELEGRAM_USER_ID")
        print("Your ID appears in the terminal as 'user=XXXXXXX' when you save a memory.")
        sys.exit(1)

    backfill(int(sys.argv[1]))
