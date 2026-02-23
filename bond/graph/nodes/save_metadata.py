from datetime import datetime, timezone

from bond.db.metadata_log import save_article_metadata
from bond.graph.state import AuthorState
from bond.store.chroma import add_topic_to_metadata_collection


def save_metadata_node(state: AuthorState) -> dict:
    """
    Save published article metadata after Checkpoint 2 approval.

    Writes to:
    - SQLite metadata_log (bond_metadata.db) — relational record
    - ChromaDB bond_metadata_log_v1 — topic embedding for DUPL-01 future checks
    """
    topic = state["topic"]
    thread_id = state["thread_id"]
    published_date = datetime.now(timezone.utc).isoformat()

    # 1. Relational record in SQLite metadata_log
    save_article_metadata(
        thread_id=thread_id,
        topic=topic,
        mode="author",
    )

    # 2. Topic embedding in ChromaDB for future duplicate detection
    add_topic_to_metadata_collection(
        thread_id=thread_id,
        topic=topic,
        published_date=published_date,
    )

    print(f"Metadata saved: topic='{topic}', thread_id={thread_id}")
    return {"metadata_saved": True}
