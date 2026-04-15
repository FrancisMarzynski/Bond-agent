import asyncio
import logging
from datetime import datetime, timezone

from bond.db.metadata_log import save_article_metadata
from bond.graph.state import AuthorState
from bond.store.chroma import add_topic_to_metadata_collection

log = logging.getLogger(__name__)


async def save_metadata_node(state: AuthorState) -> dict:
    """
    Asynchronicznie zapisuje metadane opublikowanego artykułu po zatwierdzeniu przez Checkpoint 2.

    Zapisuje do:
    - SQLite metadata_log (bond_metadata.db) — rekord relacyjny (przez aiosqlite)
    - ChromaDB bond_metadata_log_v1 — embedding tematu do przyszłych kontroli duplikatów
    """
    topic = state["topic"]
    thread_id = state["thread_id"]
    published_date = datetime.now(timezone.utc).isoformat()

    # 1. Asynchroniczny zapis rekordu relacyjnego do SQLite
    await save_article_metadata(
        thread_id=thread_id,
        topic=topic,
        mode="author",
        tokens_used_research=state.get("tokens_used_research", 0),
        tokens_used_draft=state.get("tokens_used_draft", 0),
        estimated_cost_usd=state.get("estimated_cost_usd", 0.0),
    )

    # 2. ChromaDB jest synchroniczne — uruchomione w osobnym wątku, aby nie blokować event loopa
    await asyncio.to_thread(
        add_topic_to_metadata_collection,
        thread_id=thread_id,
        topic=topic,
        published_date=published_date,
    )

    log.info("Metadane zapisane: topic='%s', thread_id=%s", topic, thread_id)
    return {"metadata_saved": True}
