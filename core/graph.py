"""
graph.py — NetworkX second brain layer for ReelsBot

Every time a memory is saved, this module:
  1. Finds the 3 most semantically similar existing memories (via ChromaDB)
  2. Creates edges between them weighted by similarity score
  3. Persists the graph to disk as JSON

/related <id> traverses this graph to show connected memories.
As the graph grows, /reflect can use it to find non-obvious clusters.
"""

import os
import json
import networkx as nx
from typing import Optional

GRAPH_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "graphs")
os.makedirs(GRAPH_DIR, exist_ok=True)

# Minimum similarity to create an edge — raise this to be more selective
SIMILARITY_THRESHOLD = 0.4
# How many neighbours to link each new memory to
TOP_K_LINKS = 30


def _graph_path(user_id: int) -> str:
    return os.path.join(GRAPH_DIR, f"u{user_id}.json")


def _load_graph(user_id: int) -> nx.Graph:
    path = _graph_path(user_id)
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        return nx.node_link_graph(data)
    return nx.Graph()


def _save_graph(graph: nx.Graph, user_id: int):
    path = _graph_path(user_id)
    with open(path, "w") as f:
        json.dump(nx.node_link_data(graph), f)


def add_and_link(memory_id: str, user_id: int):
    """
    Add a new memory node to the graph and link it to its closest neighbours.
    Called immediately after save_memory() in bot.py.
    """
    # Import here to avoid circular imports
    from core.memory import search, get_recent_memories

    graph = _load_graph(user_id)
    graph.add_node(memory_id)

    # Get all existing memories to find neighbours
    # We use the memory's own summary as the search query
    from chromadb.utils import embedding_functions
    import chromadb

    CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "chroma")
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

    collection_name = f"u{user_id}_memories"
    try:
        col = client.get_collection(name=collection_name, embedding_function=ef)
    except Exception:
        _save_graph(graph, user_id)
        return

    total = col.count()
    if total < 2:
        # Not enough memories to link yet
        _save_graph(graph, user_id)
        return

    # Fetch the new memory's document text to use as query
    try:
        new_mem = col.get(ids=[memory_id], include=["documents"])
        query_text = new_mem["documents"][0]
    except Exception:
        _save_graph(graph, user_id)
        return

    # Find closest neighbours (exclude self)
    n_results = min(TOP_K_LINKS + 1, total)
    results = col.query(
        query_texts=[query_text],
        n_results=n_results,
        include=["metadatas", "distances"],
    )

    for i, neighbour_id in enumerate(results["ids"][0]):
        if neighbour_id == memory_id:
            continue
        similarity = round(1 - results["distances"][0][i], 3)
        if similarity >= SIMILARITY_THRESHOLD:
            graph.add_edge(memory_id, neighbour_id, weight=similarity)
            print(f"[graph] Linked {memory_id[:8]} ↔ {neighbour_id[:8]} (similarity: {similarity:.0%})")

    _save_graph(graph, user_id)


def get_related(short_id: str, user_id: int, depth: int = 1) -> list[dict]:
    """
    Given the first 8 chars of a memory ID, return connected memories.

    Args:
        short_id: The 8-char ID shown in Telegram (e.g. "a4555f96")
        user_id: Telegram user ID
        depth: How many hops to traverse (1 = direct neighbours only)

    Returns:
        List of dicts with id, summary, weight — sorted by strength
    """
    from chromadb.utils import embedding_functions
    import chromadb
    import json as _json

    graph = _load_graph(user_id)

    # Resolve short ID to full ID
    full_id = None
    for node in graph.nodes():
        if node.startswith(short_id):
            full_id = node
            break

    if not full_id or full_id not in graph:
        return []

    # Get neighbours up to given depth
    neighbours = {}
    if depth == 1:
        for neighbour, edge_data in graph[full_id].items():
            neighbours[neighbour] = edge_data.get("weight", 0)
    else:
        for node in nx.single_source_shortest_path_length(graph, full_id, cutoff=depth):
            if node != full_id:
                # Use edge weight if direct neighbour, else decay by distance
                path = nx.shortest_path(graph, full_id, node)
                weight = 1.0
                for a, b in zip(path, path[1:]):
                    weight *= graph[a][b].get("weight", 0.5)
                neighbours[node] = round(weight, 3)

    if not neighbours:
        return []

    # Fetch summaries from ChromaDB
    CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "chroma")
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

    try:
        col = client.get_collection(name=f"u{user_id}_memories", embedding_function=ef)
        fetched = col.get(ids=list(neighbours.keys()), include=["metadatas"])
    except Exception:
        return []

    related = []
    for i, meta in enumerate(fetched["metadatas"]):
        mem_id = fetched["ids"][i]
        analysis = _json.loads(meta["full_analysis_json"])
        related.append({
            "id": mem_id,
            "summary": analysis.get("summary", ""),
            "weight": neighbours[mem_id],
        })

    return sorted(related, key=lambda x: x["weight"], reverse=True)


def get_graph_stats(user_id: int) -> dict:
    """Returns basic stats about the user's memory graph."""
    graph = _load_graph(user_id)
    if graph.number_of_nodes() == 0:
        return {"nodes": 0, "edges": 0, "clusters": 0}

    clusters = nx.number_connected_components(graph)
    return {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "clusters": clusters,
    }

def remove_node(memory_id: str, user_id: int):
    """Remove a memory and all its edges from the graph."""
    graph = _load_graph(user_id)
    if memory_id in graph:
        graph.remove_node(memory_id)
        _save_graph(graph, user_id)