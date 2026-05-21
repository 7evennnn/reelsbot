"""
backfill_collections.py
Run this to delete old specific sub-collections and re-categorize
your existing memories into broader categories using Gemini.

Usage:
    python backfill_collections.py YOUR_TELEGRAM_USER_ID
"""

import sys
import os
import json
import re
from google import genai
from google.genai import types
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chromadb
from core.memory import _get_or_create_collection, client

load_dotenv()

# We need the GEMINI_API_KEY
if "GEMINI_API_KEY" not in os.environ:
    print("❌ Error: GEMINI_API_KEY environment variable not set in .env file.")
    sys.exit(1)

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """
You are a categorization assistant for a personal video memory system.
Given a short video memory summary and its existing fine-grained topics, your task is to choose 1 to 3 BROAD, reusable collections (folders) to file it under.

Rules:
- The suggested collections MUST be high-level, broad, reusable categories (usually single words, max 2 words).
- Pick from standard themes rather than inventing highly narrow ones.
- Good examples: cooking, tech, design, productivity, finance, fitness, travel, business, relationships, art, health, gaming.
- Bad examples: "japanese street food tokyo", "warren buffett investing philosophy", "minimalist desk setup ideas".

Output format: Return ONLY a JSON list of strings. Example: ["design", "productivity"]
"""

def reclassify_memory(summary: str, topics: list[str]) -> list[str]:
    prompt = f"""
Summary: {summary}
Existing Topics: {topics}

Return 1-3 broad collections for this memory.
"""
    try:
        response = gemini_client.models.generate_content(
            model=MODEL,
            contents=[SYSTEM_PROMPT, prompt]
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        
        cols = json.loads(raw.strip())
        if isinstance(cols, list):
            # Clean up the responses: lowercase, stripped
            return [str(c).strip().lower() for c in cols if c]
    except Exception as e:
        print(f"  ⚠️ Gemini classification failed: {e}")
    return ["general"]

def backfill_collections(user_id: int):
    # 1. Deleting all sub-collections
    prefix = f"u{user_id}_"
    root_col_name = f"u{user_id}_memories"
    
    print(f"🧹 Deleting existing sub-collections for user {user_id}...")
    all_cols = client.list_collections()
    deleted_count = 0
    for col in all_cols:
        if col.name.startswith(prefix) and col.name != root_col_name:
            print(f"  Deleting collection: {col.name}")
            client.delete_collection(col.name)
            deleted_count += 1
    
    print(f"✅ Deleted {deleted_count} sub-collections.")

    # 2. Retrieve all memories from memories collection
    try:
        root_col = client.get_collection(name=root_col_name)
    except Exception:
        print(f"❌ No memories found for user {user_id}. Send some Reels first!")
        return

    results = root_col.get(include=["metadatas", "documents"])
    ids = results["ids"]
    metadatas = results["metadatas"]
    documents = results["documents"]
    total = len(ids)

    if total == 0:
        print("No memories to backfill.")
        return

    print(f"\n🧠 Found {total} memories. Starting Gemini re-categorization...")

    for i, memory_id in enumerate(ids, 1):
        metadata = metadatas[i - 1]
        document = documents[i - 1]
        
        try:
            analysis = json.loads(metadata.get("full_analysis_json", "{}"))
        except Exception:
            analysis = {}

        summary = analysis.get("summary", "")
        topics = json.loads(metadata.get("topics_json", "[]"))
        old_collections = json.loads(metadata.get("collections_json", "[]"))

        print(f"\n[{i}/{total}] Memory {memory_id[:8]} - Topics: {topics}")
        
        # Call Gemini to get new collections
        new_collections = reclassify_memory(summary, topics)
        print(f"  -> Old Collections: {old_collections}")
        print(f"  -> New Collections: {new_collections}")

        # Update metadata
        metadata["collections_json"] = json.dumps(new_collections)
        
        analysis["suggested_collections"] = new_collections
        metadata["full_analysis_json"] = json.dumps(analysis)

        # Save metadata back to root collection
        root_col.update(ids=[memory_id], metadatas=[metadata])

        # Save to the new sub-collections in ChromaDB
        for col_name in new_collections:
            safe_name = col_name.lower()
            safe_name = re.sub(r'[^a-z0-9._-]', '_', safe_name)  # strip anything invalid
            safe_name = re.sub(r'_+', '_', safe_name)             # collapse runs of underscores
            safe_name = safe_name.strip('_.-')                    # must start/end with alphanumeric
            if len(safe_name) < 3:
                safe_name = f"col_{safe_name}"                    # ChromaDB minimum is 3 chars
            
            try:
                sub_col = _get_or_create_collection(safe_name, user_id)
                sub_col.add(ids=[memory_id], documents=[document], metadatas=[metadata])
            except Exception as e:
                print(f"  ⚠️ Error saving to sub-collection {safe_name}: {e}")

    print(f"\n🎉 Done! Backfilled collections for {total} memories.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backfill_collections.py YOUR_TELEGRAM_USER_ID")
        sys.exit(1)

    backfill_collections(int(sys.argv[1]))