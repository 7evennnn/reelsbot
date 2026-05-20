"""
visualize.py — Interactive memory graph for ReelsBot

Generates a pyvis HTML file saved to data/graphs/u{user_id}_graph.html
Open it directly from your project folder, or receive it via /graph in Telegram.

Node color = recency (bright gold = today, fades to grey over time)
Node size  = number of connections (more linked = bigger)
Edge width = similarity strength
Hover any node to see the memory summary + date
"""

import os
import json
from datetime import datetime, timezone
from pyvis.network import Network

GRAPH_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "graphs")
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "chroma")
os.makedirs(GRAPH_DIR, exist_ok=True)


def _days_ago(iso_timestamp: str) -> float:
    dt = datetime.fromisoformat(iso_timestamp)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    return delta.total_seconds() / 86400


def _recency_color(days: float) -> str:
    """
    Maps age in days to a hex color.
    0 days  → #FFD700 (bright gold)
    7 days  → #FF8C00 (orange)
    30 days → #CC5500 (burnt orange)
    90 days → #666666 (grey)
    180d+   → #333333 (dark grey)
    """
    if days < 1:
        return "#FFD700"
    elif days < 7:
        t = (days - 1) / 6
        r = int(255 - t * (255 - 255))
        g = int(215 - t * (215 - 140))
        b = int(0)
        return f"#{r:02x}{g:02x}{b:02x}"
    elif days < 30:
        t = (days - 7) / 23
        r = int(255 - t * (255 - 204))
        g = int(140 - t * (140 - 85))
        b = int(0)
        return f"#{r:02x}{g:02x}{b:02x}"
    elif days < 90:
        t = (days - 30) / 60
        r = int(204 - t * (204 - 120))
        g = int(85 - t * (85 - 120))
        b = int(0 + t * 120)
        return f"#{r:02x}{g:02x}{b:02x}"
    elif days < 180:
        t = (days - 90) / 90
        v = int(120 - t * (120 - 51))
        return f"#{v:02x}{v:02x}{v:02x}"
    else:
        return "#333333"


def _recency_label(days: float) -> str:
    if days < 1:
        return "today"
    elif days < 2:
        return "yesterday"
    elif days < 7:
        return f"{int(days)}d ago"
    elif days < 30:
        return f"{int(days / 7)}w ago"
    elif days < 365:
        return f"{int(days / 30)}mo ago"
    else:
        return f"{days / 365:.1f}y ago"


def generate_graph(user_id: int) -> str | None:
    """
    Generate an interactive HTML graph for the user's memories.
    Returns the path to the HTML file, or None if not enough data.
    """
    import chromadb
    from chromadb.utils import embedding_functions
    import networkx as nx
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from core.graph import _load_graph

    # Load the NetworkX graph
    graph = _load_graph(user_id)
    if graph.number_of_nodes() < 2:
        return None

    # Load memory metadata from ChromaDB
    from chromadb.utils import embedding_functions
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    try:
        col = client.get_collection(name=f"u{user_id}_memories", embedding_function=ef)
        results = col.get(include=["metadatas"])
    except Exception:
        return None

    # Build a lookup: memory_id → {summary, created_at, topics}
    memory_info = {}
    for i, meta in enumerate(results["metadatas"]):
        mem_id = results["ids"][i]
        analysis = json.loads(meta["full_analysis_json"])
        memory_info[mem_id] = {
            "summary": analysis.get("summary", ""),
            "topics": analysis.get("topics", []),
            "created_at": meta.get("created_at", ""),
        }

    # Build pyvis network
    net = Network(
        height="100vh",
        width="100%",
        bgcolor="#111111",
        font_color="#eeeeee",
        select_menu=False,
    )

    net.set_options("""
    {
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -80,
          "centralGravity": 0.01,
          "springLength": 120,
          "springConstant": 0.06
        },
        "maxVelocity": 50,
        "solver": "forceAtlas2Based",
        "stabilization": { "iterations": 150 }
      },
      "edges": {
        "smooth": { "type": "continuous" },
        "color": { "inherit": false }
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 100
      }
    }
    """)

    # Add nodes
    for node_id in graph.nodes():
        info = memory_info.get(node_id, {})
        summary = info.get("summary", "Unknown memory")
        topics = info.get("topics", [])
        created_at = info.get("created_at", "")

        days = _days_ago(created_at) if created_at else 999
        color = _recency_color(days)
        age_label = _recency_label(days)

        # Size by degree (more connections = bigger node)
        degree = graph.degree(node_id)
        size = 12 + (degree * 6)

        # Truncate summary for tooltip
        short_summary = summary[:120] + "..." if len(summary) > 120 else summary
        topics_str = ", ".join(topics[:4]) if topics else "—"

        tooltip = (
            f"<b>{age_label}</b><br>"
            f"{short_summary}<br><br>"
            f"<i>Topics: {topics_str}</i><br>"
            f"<code>{node_id[:8]}</code>"
        )

        net.add_node(
            node_id,
            label=node_id[:8],
            title=tooltip,
            color={
                "background": color,
                "border": "#ffffff22",
                "highlight": {"background": "#ffffff", "border": "#ffffff"},
                "hover": {"background": "#ffffff", "border": "#ffffff"},
            },
            size=size,
            font={"size": 9, "color": "#cccccc"},
        )

    # Add edges
    for u, v, data in graph.edges(data=True):
        weight = data.get("weight", 0.5)
        width = weight * 4
        opacity_hex = format(int(weight * 200), "02x")
        net.add_edge(
            u, v,
            width=width,
            color=f"#aaaaaa{opacity_hex}",
            title=f"Similarity: {weight:.0%}",
        )

    # Save
    output_path = os.path.join(GRAPH_DIR, f"u{user_id}_graph.html")
    net.save_graph(output_path)
    _inject_legend(output_path)
    return output_path


def _inject_legend(html_path: str):
    """Injects a recency legend and title into the generated HTML."""
    legend_html = """
    <style>
      #reelsbot-legend {
        position: fixed; top: 16px; left: 16px;
        background: #1a1a1a; border: 1px solid #333;
        border-radius: 8px; padding: 12px 16px;
        font-family: sans-serif; font-size: 12px; color: #ccc;
        z-index: 9999; pointer-events: none;
      }
      #reelsbot-legend h3 { margin: 0 0 8px 0; font-size: 13px; color: #fff; }
      .legend-row { display: flex; align-items: center; gap: 8px; margin: 4px 0; }
      .legend-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
      #reelsbot-tip {
        position: fixed; bottom: 16px; left: 16px;
        background: #1a1a1a; border: 1px solid #333;
        border-radius: 8px; padding: 10px 14px;
        font-family: sans-serif; font-size: 11px; color: #888;
        z-index: 9999; pointer-events: none;
      }
    </style>
    <div id="reelsbot-legend">
      <h3>🧠 ReelsBot Memory Graph</h3>
      <div class="legend-row"><div class="legend-dot" style="background:#FFD700"></div> Today</div>
      <div class="legend-row"><div class="legend-dot" style="background:#FF8C00"></div> This week</div>
      <div class="legend-row"><div class="legend-dot" style="background:#CC5500"></div> This month</div>
      <div class="legend-row"><div class="legend-dot" style="background:#888"></div> Older</div>
      <div class="legend-row"><div class="legend-dot" style="background:#333"></div> Long ago</div>
      <br>
      <div style="color:#777; font-size:11px">Node size = connections<br>Edge brightness = similarity</div>
    </div>
    <div id="reelsbot-tip">Hover a node to preview · Scroll to zoom · Drag to explore</div>
    """

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("</body>", legend_html + "\n</body>")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
