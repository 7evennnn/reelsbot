"""
digest.py — Weekly PDF digest for ReelsBot
Called every Sunday at 8pm by APScheduler in bot.py.
Generates a PDF report and sends it via Telegram.
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DIGEST_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "digests")
os.makedirs(DIGEST_DIR, exist_ok=True)

# Colors
C_BG     = HexColor("#0f0f0f")
C_ACCENT = HexColor("#FFD700")
C_TEXT   = HexColor("#eeeeee")
C_SUB    = HexColor("#666666")
C_DIM    = HexColor("#333333")


def _safe(text: str) -> str:
    """Escape XML special chars for ReportLab paragraphs."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def get_week_memories(user_id: int) -> list[dict]:
    """Return all memories saved in the past 7 days, newest first."""
    from core.memory import get_recent_memories
    all_memories = get_recent_memories(user_id, limit=500)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    result = []
    for m in all_memories:
        try:
            dt = datetime.fromisoformat(m["created_at"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                result.append(m)
        except Exception:
            pass
    return result


def _generate_reflection(memories: list[dict], gemini_client, model: str) -> str:
    """Ask Gemini for a weekly reflection. Returns plain prose."""
    if not memories:
        return (
            "Quiet week — hopefully that means you've been cutting down on the reels "
            "and actually doing the things you've been saving. Sometimes the best week "
            "is the one where you act on what you already know."
        )

    lines = []
    for m in memories:
        line = f"- {m['summary']}"
        if m.get("topics"):
            line += f" [topics: {', '.join(m['topics'][:4])}]"
        if m.get("todos"):
            line += f" [todos: {', '.join(m['todos'])}]"
        if m.get("user_note"):
            line += f" [you noted: \"{m['user_note']}\"]"
        lines.append(line)

    prompt = f"""You're writing the weekly digest for someone's personal Reel memory system. They saved {len(memories)} video{'s' if len(memories) != 1 else ''} this week.

Here's what they saved:
{chr(10).join(lines)}

Write a short, warm weekly reflection in plain prose — 3 to 4 paragraphs. Cover:
1. The main themes of their week — what kept showing up?
2. Any todos or intentions they flagged — new directions or building on existing saves?
3. One observation connecting dots they might not have noticed themselves
4. One specific nudge — something worth acting on this week based on what they saved

No headers. No bullet points. No bold text. No markdown formatting of any kind. Write like a smart friend who's been quietly paying attention — specific and conversational, not generic."""

    response = gemini_client.models.generate_content(model=model, contents=[prompt])
    return response.text.strip()


def _build_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DigestTitle", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=26,
            textColor=C_ACCENT, spaceAfter=2*mm, alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "DigestSubtitle", parent=base["Normal"],
            fontName="Helvetica", fontSize=11,
            textColor=C_SUB, spaceAfter=6*mm,
        ),
        "section": ParagraphStyle(
            "DigestSection", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=9,
            textColor=C_ACCENT, spaceBefore=6*mm, spaceAfter=3*mm,
            leading=14,
        ),
        "body": ParagraphStyle(
            "DigestBody", parent=base["Normal"],
            fontName="Helvetica", fontSize=10,
            textColor=C_TEXT, leading=17, spaceAfter=4*mm,
        ),
        "card_summary": ParagraphStyle(
            "DigestCardSummary", parent=base["Normal"],
            fontName="Helvetica", fontSize=9,
            textColor=C_TEXT, leading=14, spaceAfter=1*mm,
        ),
        "card_meta": ParagraphStyle(
            "DigestCardMeta", parent=base["Normal"],
            fontName="Helvetica", fontSize=8,
            textColor=C_SUB, spaceAfter=4*mm,
        ),
        "footer": ParagraphStyle(
            "DigestFooter", parent=base["Normal"],
            fontName="Helvetica", fontSize=8,
            textColor=C_DIM, spaceAfter=0,
        ),
    }


def _dark_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(C_BG)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.restoreState()


def build_pdf(user_id: int, memories: list[dict], reflection: str, week_label: str) -> str:
    """Build and save the digest PDF. Returns the file path."""
    output_path = os.path.join(
        DIGEST_DIR,
        f"u{user_id}_digest_{datetime.now().strftime('%Y%m%d')}.pdf"
    )

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        rightMargin=22*mm, leftMargin=22*mm,
        topMargin=22*mm, bottomMargin=22*mm,
    )

    S = _build_styles()
    story = []

    # ── Cover ─────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("ReelsBot", S["title"]))
    story.append(Paragraph(f"Weekly Digest · {week_label}", S["subtitle"]))
    count_text = (
        f"{len(memories)} save{'s' if len(memories) != 1 else ''} this week"
        if memories else "Nothing saved this week"
    )
    story.append(Paragraph(count_text, S["card_meta"]))
    story.append(HRFlowable(
        width="100%", thickness=0.5, color=C_DIM, spaceAfter=8*mm
    ))

    # ── Reflection ────────────────────────────────────────────────────────────
    story.append(Paragraph("THIS WEEK", S["section"]))
    for para in reflection.split("\n\n"):
        para = para.strip()
        if para:
            story.append(Paragraph(_safe(para), S["body"]))

    # ── Memory list ───────────────────────────────────────────────────────────
    if memories:
        story.append(HRFlowable(
            width="100%", thickness=0.5, color=C_DIM,
            spaceBefore=4*mm, spaceAfter=6*mm
        ))
        story.append(Paragraph("SAVED THIS WEEK", S["section"]))

        for m in memories:
            summary = m.get("summary", "")
            topics = m.get("topics", [])
            try:
                dt = datetime.fromisoformat(m["created_at"])
                time_str = dt.strftime("%a %d %b, %I:%M %p")
            except Exception:
                time_str = ""

            story.append(Paragraph(_safe(summary), S["card_summary"]))
            meta_parts = []
            if topics:
                meta_parts.append("  ·  ".join(topics[:4]))
            if time_str:
                meta_parts.append(time_str)
            if meta_parts:
                story.append(Paragraph("  ·  ".join(meta_parts), S["card_meta"]))
            else:
                story.append(Spacer(1, 2*mm))

        # ── Todos ─────────────────────────────────────────────────────────────
        all_todos = []
        for m in memories:
            for t in m.get("todos", []):
                if t not in all_todos:
                    all_todos.append(t)

        if all_todos:
            story.append(HRFlowable(
                width="100%", thickness=0.5, color=C_DIM,
                spaceBefore=4*mm, spaceAfter=6*mm
            ))
            story.append(Paragraph("TODOS ADDED THIS WEEK", S["section"]))
            for todo in all_todos:
                story.append(Paragraph(f"· {_safe(todo)}", S["body"]))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 8*mm))
    story.append(HRFlowable(
        width="100%", thickness=0.5, color=C_DIM, spaceAfter=4*mm
    ))
    story.append(Paragraph(
        f"Generated {datetime.now().strftime('%d %B %Y, %I:%M %p')}  ·  ReelsBot",
        S["footer"]
    ))

    doc.build(story, onFirstPage=_dark_page, onLaterPages=_dark_page)
    return output_path


async def send_weekly_digest(user_id: int, gemini_client, model: str, bot):
    """Full pipeline — called by APScheduler every Sunday at 8pm."""
    print(f"[digest] Running weekly digest for user {user_id}...")

    try:
        memories = get_week_memories(user_id)

        today = datetime.now()
        week_start = today - timedelta(days=7)
        week_label = f"{week_start.strftime('%d %b')} – {today.strftime('%d %b %Y')}"

        reflection = _generate_reflection(memories, gemini_client, model)
        pdf_path = build_pdf(user_id, memories, reflection, week_label)

        if memories:
            caption = f"📋 Your weekly digest — {len(memories)} save{'s' if len(memories) != 1 else ''} this week."
        else:
            caption = "📋 Weekly digest — quiet week this time."

        with open(pdf_path, "rb") as f:
            await bot.send_document(
                chat_id=user_id,
                document=f,
                filename=f"reelsbot_digest_{today.strftime('%Y%m%d')}.pdf",
                caption=caption,
            )
        print(f"[digest] Sent to {user_id}")

    except Exception as e:
        print(f"[digest] Failed: {e}")
        try:
            await bot.send_message(chat_id=user_id, text=f"❌ Weekly digest failed: {e}")
        except Exception:
            pass
