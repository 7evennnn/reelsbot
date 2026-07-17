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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    PreCheckoutQueryHandler,
)
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.digest import send_weekly_digest
from apscheduler.schedulers.background import BackgroundScheduler as AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from core.ingest import download_reel, cleanup_video, is_supported_url, get_duration
from core.analyze import analyze_reel
from core.memory import save_memory, search, get_todos, list_collections, get_recent_memories, delete_memory
from core.graph import add_and_link, get_related, remove_node
from core.visualize import generate_graph
from core.auth import generate_login_token

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
REFLECT_MODEL = "gemini-2.5-flash-lite"
OWNER_USER_ID   = int(os.environ.get("OWNER_USER_ID", 0))
DIGEST_TIMEZONE = os.environ.get("DIGEST_TIMEZONE", "Asia/Kuala_Lumpur")
MODE = os.environ.get("MODE", "standalone")
PAYMENT_PROVIDER_TOKEN = os.environ.get("PAYMENT_PROVIDER_TOKEN", "")

try:
    from core.db import has_quota, increment_processed, add_credits, get_or_create_user, has_ask_quota, increment_asks
except ImportError:
    pass
# ── Guardrails ────────────────────────────────────────────────────────────────
# Message @userinfobot on Telegram to get your ID.
# Empty = open to anyone. Add your ID to lock it down.
ALLOWED_USERS: set[int] = {
    # 123456789,
}

MAX_DURATION_SECONDS = 600
URL_PATTERN = re.compile(r"https?://\S+")

def get_local_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # doesn't send data, just finds outbound interface
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

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

    if MODE == "saas":
        if not has_quota(user_id):
            await update.message.reply_text(
                "⚠️ **Quota Exceeded.**\n\n"
                "You have used up your free/paid Reels.\n"
                "Please use `/upgrade` to purchase an additional 50 Reels.",
                parse_mode="Markdown"
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
    if MODE == "saas":
        increment_processed(user_id)

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

    if MODE == "saas":
        if not has_ask_quota(user_id):
            await update.message.reply_text(
                "⚠️ **Ask Quota Exceeded.**\n\n"
                "You have used up your free/paid Ask requests.\n"
                "Please use `/upgrade` to purchase more credits.",
                parse_mode="Markdown"
            )
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
        if MODE == "saas":
            increment_asks(user_id)
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


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    help_text = (
        "🧠 *ReelsBot — Your Personal Video Brain*\n\n"
        "Here are the commands you can run:\n\n"
        "🔗 *Save a Reel* — Just paste the Reel/Shorts/TikTok URL (e.g. `https://instagram.com/reel/...`)\n"
        "💬 *Save with Context* — Paste the URL and add context (e.g. `https://instagram.com/reel/... check out this setup!`)\n\n"
        "🤖 *AI Actions:*\n"
        "• `/ask <question>` — Search memories & get synthesized answer\n"
        "• `/reflect` — Gemini reflects on your saved saves\n"
        "• `/graph` — Generates interactive memory knowledge graph html\n\n"
        "🔍 *Browsing & Managing:*\n"
        "• `/memories [limit]` — List recent saved memories (default 10)\n"
        "• `/search <query>` — Semantic search across your saves\n"
        "• `/related <id|topic>` — Find connected memories\n"
        "• `/todos` — List all extracted todo tasks\n"
        "• `/collections` — Show automatically generated folders\n"
        "• `/login` — Get magic link to web dashboard\n"
        "• `/delete <id>` — Delete a memory by its 8-char ID\n"
        "• `/help` — Show this message"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def cmd_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    token = generate_login_token(user_id)

    base_url = os.environ.get("BASE_URL", f"http://{get_local_ip()}:5000").rstrip("/")
    login_url = f"{base_url}/login?token={token}"

    await update.message.reply_text(
        f"🔑 ReelsBot Web Login\n\n"
        f"Open this link to access your memories dashboard.\n"
        f"Valid for 15 minutes, one-time use only:\n\n"
        f"{login_url}",
        disable_web_page_preview=True,
    )



async def _post_init(application):
    """Ensure polling mode and log which bot account we connected as."""
    await application.bot.delete_webhook(drop_pending_updates=True)
    me = await application.bot.get_me()
    logger.info("Telegram bot ready — polling as @%s (id=%s)", me.username, me.id)


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled bot error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            f"Something went wrong: {context.error}"
        )


async def cmd_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if MODE != "saas":
        await update.message.reply_text("SaaS mode is not enabled. Enjoy unlimited use!")
        return

    user_id = update.effective_user.id
    user = get_or_create_user(user_id)
    
    await update.message.reply_text(
        f"📊 **Usage Stats**\n"
        f"Processed Reels: {user['processed_reels']} / {user['total_allowed_reels']} Reels\n"
        f"Used Ask Credits: {user['processed_asks']} / {user['total_allowed_asks']} Asks\n\n"
        "Click the button below to add 50 more Reels and 10 Ask credits to your account for $3.00.",
        parse_mode="Markdown"
    )

    chat_id = update.message.chat_id
    title = "ReelsBot 50-Reel Top-up"
    description = "Unlock 50 more high-intelligence video analyses."
    payload = "reelsbot_topup_50"
    currency = "USD"
    price = 300 # $3.00

    if PAYMENT_PROVIDER_TOKEN:
        prices = [LabeledPrice("Top-up Pack", price)]
        await context.bot.send_invoice(
            chat_id, title, description, payload, PAYMENT_PROVIDER_TOKEN, currency, prices
        )
    else:
        # Telegram Stars pricing format (currency XTR)
        # Note: 1 Star is approx 0.02 USD. 3 USD = 150 Stars
        prices = [LabeledPrice("Top-up Pack", 150)]
        await context.bot.send_invoice(
            chat_id, title, description, payload, "", "XTR", prices
        )


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if query.invoice_payload != "reelsbot_topup_50":
        await query.answer(ok=False, error_message="Something went wrong...")
    else:
        await query.answer(ok=True)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    amount = update.message.successful_payment.total_amount / 100.0
    
    # Add 50 reels and 10 asks
    add_credits(user_id, 50, amount, amount_asks=10, tier_name='premium')
    
    await update.message.reply_text(
        "✅ **Payment Received!**\n\n"
        "Thank you! 50 Reels and 10 Ask credits have been added to your account.\n"
        "You can continue sending videos and asking questions.",
        parse_mode="Markdown"
    )


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN environment variable")

    app = (
        ApplicationBuilder()
        .token(token)
        .post_init(_post_init)
        .build()
    )
    app.add_error_handler(_on_error)
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
    app.add_handler(CommandHandler("login", cmd_login))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("upgrade", cmd_upgrade))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

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
        print(f"[Weekly] Weekly digest scheduled — Sundays 8pm {DIGEST_TIMEZONE}")
    else:
        print("⚠️  OWNER_USER_ID not set — weekly digest disabled")

    logger.info("ReelsBot starting polling loop...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()