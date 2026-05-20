"""
analyze.py
Sends a downloaded Reel + optional user note to Gemini and returns
a structured memory object. Uses the new google-genai SDK.
"""

import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """
You are analyzing a video that a user has shared with their personal AI memory system.
You will receive:
  1. The video itself
  2. (Optionally) a user note typed alongside the share — treat this as a voice annotation

Your job is to extract a structured memory from this. Return ONLY valid JSON matching this schema:

{
  "summary": "2-3 sentence factual summary of what the video is about",
  "topics": ["list", "of", "topic", "tags"],
  "user_intent": {
    "type": "interest | todo | knowledge | person | place | product | none",
    "description": "What the user wants to remember or do — null if no intent signal"
  },
  "preferences_detected": [
    "any style, aesthetic, or taste preferences the user expressed or the content implies they'd want remembered"
  ],
  "todos": [
    "any tasks, things to try, places to go, things to buy the user mentioned or implied"
  ],
  "knowledge": "key factual content in the video worth remembering (how-to steps, facts, tips)",
  "memory_priority": "high | medium | low",
  "suggested_collections": ["1 to 3 broad single-word or two-word folder names"]
}

Rules:
- If the user said something like "remember I like this" / "keep in mind" / "I gotta do this" → high priority, capture it verbatim in the relevant field
- If it's just a passive share with no note → infer intent from content, set priority accordingly
- topics should be specific: not just "food" but "Japanese street food", "ramen preparation"
- Be concise. The summary will be embedded for semantic search so make it rich with keywords.
- suggested_collections must be BROAD reusable categories — single words strongly preferred.
  Good examples: business, cooking, fitness, travel, tech, design, finance, productivity, health, investing
  Bad examples: "warren buffett investing philosophy", "japanese street food tokyo", "minimalist desk setup ideas"
  Use at most 2 collections per memory. Pick from existing broad themes rather than inventing new narrow ones.
"""


def analyze_reel(video_path: str, user_note: str = "") -> dict:
    """
    Upload video to Gemini, run structured analysis, return parsed dict.

    Args:
        video_path: Local path to the downloaded video file
        user_note: Any text the user typed alongside the link (can be empty)

    Returns:
        Parsed memory dict
    """
    print(f"[analyze] Uploading {video_path} to Gemini...")

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    ext = os.path.splitext(video_path)[1].lower()
    mime_map = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}
    mime_type = mime_map.get(ext, "video/mp4")

    user_message = SYSTEM_PROMPT
    if user_note.strip():
        user_message += f"\n\nUser's annotation when sharing this: \"{user_note.strip()}\""
    else:
        user_message += "\n\nNo user annotation — infer intent from content only."

    print("[analyze] Sending to Gemini for analysis...")

    import time

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=[
                    types.Part.from_bytes(data=video_bytes, mime_type=mime_type),
                    user_message,
                ],
            )
            break
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                wait = 45
                print(f"[analyze] Rate limited, retrying in {wait}s... (attempt {attempt + 1}/3)")
                time.sleep(wait)
            else:
                raise

    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw.strip())