"""
bot.py — ReelsBot
Commands:
  (paste a URL)        → download, analyze, save to your memory
  (URL + a note)       → same but your note is treated as intent
  /reflect             → Gemini reflects on your saves, grouped by time period
  /graph               → interactive HTML memory graph (also saved to data/graphs/)
  /memories            → list recent saves with IDs
  /related <id|topic>  → memories connected to a specific save
  /search <query>      → semantic search your memories
  /todos               → everything you've flagged as something to do
  /collections         → your auto-generated topic folders
  /ask <question>      → search your memory and get a synthesized answer
  /delete <id>         → remove a memory by its 8-char ID
"""
from dotenv import load_dotenv
load_dotenv()


import os
import re
import logging
from datetime import datetime, timezone
from google import genai
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import sys
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from core.digest import send_weekly_digest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.ingest import download_reel, cleanup_video, is_supported_url, get_duration
from core.analyze import analyze_reel
from core.memory import save_memory, search, get_todos, list_collections, get_recent_memories
from core.graph import add_and_link, get_related
from core.visualize import generate_graph
from core.memory import save_memory, search, get_todos, list_collections, get_recent_memories, delete_memory
from core.graph import add_and_link, get_related, remove_node

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
REFLECT_MODEL = "gemini-2.5-flash-lite"
OWNER_USER_ID   = int(os.environ.get("OWNER_USER_ID", 0))
DIGEST_TIMEZONE = os.environ.get("DIGEST_TIMEZONE", "Asia/Kuala_Lumpur")
# ── Guardrails ────────────────────────────────────────────────────────────────
# Message @userinfobot on Telegram to get your ID.
# Empty = open to anyone. Add your ID to lock it down.
ALLOWED_USERS: set[int] = {
    # 123456789,
}

MAX_DURATION_SECONDS = 600
URL_PATTERN = re.compile(r"https?://\S+")


def is_allowed(user_id: int) -> bool:
    return len(ALLOWED_USERS) == 0 or user_id in ALLOWED_USERS


def extract_url_and_note(text: str) -> tuple[str | None, str]:
    match = URL_PATTERN.search(text)
    if not match:
        return None, text.strip()
    url = match.group(0)
    note = text[:match.start()].strip() + " " + text[match.end():].strip()
    return url, note.strip()


def _time_bucket(iso_timestamp: str) -> str:
    """Returns a human period label for a timestamp."""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - dt).days
        if days == 0:
            return "Today"
        elif days <= 7:
            return "This week"
        elif days <= 30:
            return "This month"
        elif days <= 90:
            return "Last 3 months"
        else:
            return "Older"
    except Exception:
        return "Unknown"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("This bot is private.")
        return

    text = update.message.text or ""
    url, user_note = extract_url_and_note(text)

    if not url or not is_supported_url(url):
        await update.message.reply_text(
            "Send me a Reel, TikTok, or YouTube Short URL to save it to memory.\n"
            "Add a note too if you want:\n"
            "`https://instagram.com/reel/xxx I wanna try this`",
            parse_mode="Markdown",
        )
        return

    status_msg = await update.message.reply_text("⏳ Checking video...")

    try:
        duration = get_duration(url)
        if duration > MAX_DURATION_SECONDS:
            await status_msg.edit_text(
                f"❌ Video is {duration // 60}min long — max is {MAX_DURATION_SECONDS // 60}min."
            )
            return
    except Exception:
        pass

    await status_msg.edit_text("⏳ Downloading...")

    try:
        video_path = download_reel(url)
    except Exception as e:
        await status_msg.edit_text(f"❌ Download failed: {e}")
        return

    await status_msg.edit_text("🧠 Analyzing with Gemini...")

    try:
        analysis = analyze_reel(video_path, user_note)
    except Exception as e:
        await status_msg.edit_text(f"❌ Analysis failed: {e}")
        cleanup_video(video_path)
        return

    cleanup_video(video_path)
    memory_id = save_memory(analysis, url, user_id, user_note)
    add_and_link(memory_id, user_id)

    intent = analysis.get("user_intent", {})
    todos = analysis.get("todos", [])
    prefs = analysis.get("preferences_detected", [])
    topics = analysis.get("topics", [])
    priority = analysis.get("memory_priority", "medium")
    collections = analysis.get("suggested_collections", [])
    priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")

    lines = [
        f"✅ *Memory saved* {priority_emoji}", "",
        f"📝 {analysis.get('summary', '')}", "",
        f"🏷️ `{'` `'.join(topics)}`",
    ]
    if intent.get("type") not in (None, "none") and intent.get("description"):
        lines += ["", f"🎯 *Intent:* {intent['description']}"]
    if todos:
        lines += ["", "✅ *Todos added:*"] + [f"  • {t}" for t in todos]
    if prefs:
        lines += ["", "💡 *Preferences noted:*"] + [f"  • {p}" for p in prefs]
    if collections:
        lines += ["", f"📁 Filed under: `{'`, `'.join(collections)}`"]
    lines += ["", f"🆔 `{memory_id[:8]}`"]

    await status_msg.edit_text("\n".join(lines), parse_mode="Markdown")


async def cmd_reflect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    memories = get_recent_memories(user_id, limit=50)
    if not memories:
        await update.message.reply_text("No memories yet — send me some Reels first!")
        return

    await update.message.reply_text("🪞 Reflecting on your saves...")

    # Group memories by time bucket
    buckets: dict[str, list] = {}
    for m in memories:
        bucket = _time_bucket(m.get("created_at", ""))
        buckets.setdefault(bucket, []).append(m)

    # Build a time-structured summary for Gemini
    memory_lines = []
    for bucket in ["Today", "This week", "This month", "Last 3 months", "Older"]:
        items = buckets.get(bucket, [])
        if not items:
            continue
        memory_lines.append(f"\n[{bucket}]")
        for m in items:
            line = f"- {m['summary']}"
            if m["topics"]:
                line += f" [topics: {', '.join(m['topics'][:4])}]"
            if m["todos"]:
                line += f" [todos: {', '.join(m['todos'])}]"
            if m["user_note"]:
                line += f" [they said: \"{m['user_note']}\"]"
            memory_lines.append(line)

    prompt = f"""You are a personal memory assistant for someone who saves short videos (Reels) to remember things they care about.

Here are their saved memories grouped by when they saved them:

{chr(10).join(memory_lines)}

Give a thoughtful, conversational reflection. Because you can see the timeline, cover:
1. **Right now** — what are they clearly into this week/today?
2. **Shifts over time** — has their focus changed compared to earlier saves? What faded, what's new?
3. **Recurring threads** — what keeps showing up across different time periods, even if the topic changes?
4. **Todos or intentions** — what have they said they want to do, and how long ago did they say it?
5. **One nudge** — based on the timeline, something worth acting on or noticing

Write like a smart friend who's been quietly paying attention. Be specific about timing — say "this week" or "a month ago", not vague things like "recently". Don't bullet-point everything."""

    try:
        response = gemini_client.models.generate_content(model=REFLECT_MODEL, contents=[prompt])
        await update.message.reply_text(f"🪞 *Reflection*\n\n{response.text}", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Reflect failed: {e}")


async def cmd_graph(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    await update.message.reply_text("🕸️ Generating your memory graph...")

    try:
        path = generate_graph(user_id)
    except Exception as e:
        await update.message.reply_text(f"❌ Graph generation failed: {e}")
        return

    if not path:
        await update.message.reply_text(
            "Not enough memories to graph yet — save at least 2 Reels and run the backfill script first.\n"
            "`python backfill_graph.py YOUR_ID`",
            parse_mode="Markdown"
        )
        return

    # Send as a file — opens directly in browser
    with open(path, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename="reelsbot_graph.html",
            caption="Open this file in your browser. Hover nodes to preview memories, scroll to zoom, drag to explore. 🟡 = recent · ⚫ = older"
        )


async def cmd_memories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    limit = 10
    if context.args and context.args[0].isdigit():
        limit = min(int(context.args[0]), 50)

    memories = get_recent_memories(user_id, limit=limit)
    if not memories:
        await update.message.reply_text("No memories yet — send me some Reels!")
        return

    lines = [f"🧠 *Your last {len(memories)} memories:*\n"]
    for i, m in enumerate(memories, 1):
        topics = ", ".join(m["topics"][:3]) if m["topics"] else "—"
        summary = m["summary"][:80] + ("..." if len(m["summary"]) > 80 else "")
        age = _time_bucket(m.get("created_at", ""))
        lines += [
            f"*{i}.* {summary}",
            f"   `{m['id'][:8]}` • _{topics}_ • {age}",
            "",
        ]

    lines.append("Use `/related <id>` or `/related <topic>` to explore connections.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_related(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "`/related a4555f96` — by memory ID\n"
            "`/related japanese cooking` — by topic",
            parse_mode="Markdown"
        )
        return

    query = " ".join(context.args).strip()

    if re.fullmatch(r"[0-9a-f]{8}", query):
        short_id = query
    else:
        results = search(query, user_id, n_results=1)
        if not results:
            await update.message.reply_text("No memories found matching that. Try `/memories` to browse.")
            return
        short_id = results[0]["id"][:8]
        await update.message.reply_text(
            f"🔍 Closest match: _{results[0]['summary'][:80]}..._\n`{short_id}`",
            parse_mode="Markdown"
        )

    related = get_related(short_id, user_id)

    if not related:
        await update.message.reply_text(
            "No connections found yet.\n"
            "_(Run `python backfill_graph.py YOUR_ID` to link existing saves)_",
            parse_mode="Markdown"
        )
        return

    lines = [f"🕸️ *Connected to* `{short_id}`:\n"]
    for r in related:
        lines += [f"• {r['summary']}", f"  `{r['id'][:8]}` • strength {r['weight']:.0%}", ""]

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage: `/search minimalist desk setups`", parse_mode="Markdown")
        return

    await update.message.reply_text(f"🔍 Searching for: _{query}_...", parse_mode="Markdown")
    results = search(query, user_id, n_results=5)

    if not results:
        await update.message.reply_text("No memories found yet!")
        return

    lines = [f"🔍 *Top {len(results)} results for '{query}':*\n"]
    for i, r in enumerate(results, 1):
        score_bar = "█" * int(r["relevance_score"] * 10) + "░" * (10 - int(r["relevance_score"] * 10))
        lines += [
            f"*{i}.* {r['summary']}",
            f"`{score_bar}` {r['relevance_score']:.0%}",
            f"[Source]({r['source_url']}) • `{r['id'][:8]}`", "",
        ]

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True)


async def cmd_todos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    todos = get_todos(user_id)
    if not todos:
        await update.message.reply_text("No todos saved yet!")
        return

    lines = ["📋 *Your saved todos:*\n"]
    for entry in todos:
        for todo in entry["todos"]:
            lines += [f"• {todo}", f"  [source]({entry['source_url']})\n"]

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True)


async def cmd_collections(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    cols = [c for c in list_collections(user_id) if c != "memories"]
    if not cols:
        await update.message.reply_text("No collections yet — share some Reels first!")
        return
    await update.message.reply_text(
        "📁 *Your collections:*\n\n" + "\n".join(f"• `{c}`" for c in cols),
        parse_mode="Markdown"
    )

async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    question = " ".join(context.args).strip()
    if not question:
        await update.message.reply_text(
            "Usage: `/ask what do I know about fermentation?`",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(f"🔍 Searching your memory for: _{question}_...", parse_mode="Markdown")
    results = search(question, user_id, n_results=8)

    if not results:
        await update.message.reply_text("No memories found — save some Reels first!")
        return

    memory_lines = []
    for i, r in enumerate(results, 1):
        line = f"[{i}] {r['summary']}"
        if r["topics"]:
            line += f" | topics: {', '.join(r['topics'][:4])}"
        if r["todos"]:
            line += f" | todos: {'; '.join(r['todos'])}"
        if r["user_note"]:
            line += f" | you noted: \"{r['user_note']}\""
        line += f" | saved: {_time_bucket(r['created_at'])}"
        memory_lines.append(line)

    prompt = f"""You are a personal memory assistant. The user saved short videos (Reels/TikToks) to remember things they care about, and now they're asking a question about what they know.

User's question: "{question}"

Relevant memories from their collection:
{chr(10).join(memory_lines)}

Answer based strictly on what's in their memories. Be specific — reference particular saves when useful. If the memories don't clearly answer the question, say so honestly rather than guessing. Write conversationally."""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[prompt]
        )
        await update.message.reply_text(
            f"💬 *{question}*\n\n{response.text}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ask failed: {e}")


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: `/delete a4555f96` — use the 8-char ID from `/memories`",
            parse_mode="Markdown"
        )
        return

    short_id = context.args[0].strip()
    deleted_id = delete_memory(short_id, user_id)

    if not deleted_id:
        await update.message.reply_text(
            f"❌ No memory found with ID `{short_id}`. Check `/memories` for valid IDs.",
            parse_mode="Markdown"
        )
        return

    remove_node(deleted_id, user_id)
    await update.message.reply_text(f"🗑️ Deleted `{short_id}`.", parse_mode="Markdown")



def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN environment variable")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("reflect", cmd_reflect))
    app.add_handler(CommandHandler("graph", cmd_graph))
    app.add_handler(CommandHandler("memories", cmd_memories))
    app.add_handler(CommandHandler("related", cmd_related))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("todos", cmd_todos))
    app.add_handler(CommandHandler("collections", cmd_collections))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("delete", cmd_delete))

    # Weekly digest scheduler
    if OWNER_USER_ID:
        tz = pytz.timezone(DIGEST_TIMEZONE)
        scheduler = AsyncIOScheduler(timezone=tz)

        async def weekly_digest_job():
            await send_weekly_digest(OWNER_USER_ID, gemini_client, REFLECT_MODEL, app.bot)

        scheduler.add_job(
            weekly_digest_job,
            CronTrigger(day_of_week="sun", hour=20, minute=0, timezone=tz),
        )
        scheduler.start()
        print(f"📅 Weekly digest scheduled — Sundays 8pm {DIGEST_TIMEZONE}")
    else:
        print("⚠️  OWNER_USER_ID not set — weekly digest disabled")

    print("🤖 ReelsBot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()