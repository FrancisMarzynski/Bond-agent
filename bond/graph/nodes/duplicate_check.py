from langgraph.types import interrupt

from bond.config import settings
from bond.graph.state import AuthorState
from bond.store.chroma import get_or_create_metadata_collection


def duplicate_check_node(state: AuthorState) -> dict:
    """
    Check whether the incoming topic is too similar to a previously published article.

    Uses ChromaDB metadata_log collection with cosine similarity.
    Interrupts the graph if similarity >= DUPLICATE_THRESHOLD.
    User can override (proceed) or abort (route to END).
    """
    collection = get_or_create_metadata_collection()

    # Skip check if no prior articles in metadata log
    if collection.count() == 0:
        return {"duplicate_match": None, "duplicate_override": None}

    results = collection.query(
        query_texts=[state["topic"]],
        n_results=1,
        include=["metadatas", "distances"],
    )

    # results["ids"][0] is a list; empty if collection had 0 items (already handled above)
    if not results["ids"][0]:
        return {"duplicate_match": None, "duplicate_override": None}

    # ChromaDB returns DISTANCE; convert to similarity
    distance = results["distances"][0][0]
    similarity = 1.0 - distance

    if similarity < settings.duplicate_threshold:
        # Below threshold — no duplicate
        return {"duplicate_match": None, "duplicate_override": None}

    # Duplicate found — surface to user via interrupt
    match_meta = results["metadatas"][0][0]
    match_info = {
        "existing_title": match_meta.get("title", "Unknown"),
        "existing_date": match_meta.get("published_date", "Unknown"),
        "similarity_score": round(similarity, 3),
    }

    # interrupt() pauses the graph; resume value is bool (True=proceed, False=abort)
    proceed = interrupt({
        "warning": "Wykryto podobny temat",
        "existing_title": match_info["existing_title"],
        "existing_date": match_info["existing_date"],
        "similarity_score": match_info["similarity_score"],
    })

    return {
        "duplicate_match": match_info,
        "duplicate_override": bool(proceed),
    }
