"""Two-pass corpus retriever with re-ranker.

Retrieval priority (Phase 1 Success Criteria 5):
  Pass 1 — fetch up to n fragments tagged source_type='own' (own_text).
  Pass 2 — if Pass 1 returns 0 results, fetch n fragments tagged source_type='external'
            (external_blogger) as fallback.
  Fill    — if Pass 1 returns 1..n-1 results, fill remaining slots from external.

Re-ranker — stable sort that guarantees own_text fragments always precede
             external_blogger fragments in the final list, regardless of
             their individual similarity scores.
"""
from __future__ import annotations

import logging
from typing import Any

from bond.config import settings
from bond.store.chroma import get_or_create_corpus_collection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Re-ranker
# ---------------------------------------------------------------------------

def rerank(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable re-ranker: own_text always precedes external_blogger.

    Within each group the original order (by relevance) is preserved.
    Documents with unknown source_type are treated as external.
    """
    own = [f for f in fragments if f.get("source_type") == "own"]
    external = [f for f in fragments if f.get("source_type") != "own"]
    return own + external


# ---------------------------------------------------------------------------
# Low-level ChromaDB query helper
# ---------------------------------------------------------------------------

def _query_collection(
    query: str,
    n: int,
    source_type: str | None = None,
) -> list[dict[str, Any]]:
    """Query the style corpus collection and return a list of fragment dicts.

    Args:
        query: Query string used for embedding-based similarity search.
        n: Maximum number of results to return.
        source_type: Optional ChromaDB ``where`` filter value for ``source_type``.
                     Pass ``None`` to query all source types.

    Returns:
        List of dicts with keys ``text``, ``source_type``, and any stored metadata.
        Returns [] on error or when the collection is empty.
    """
    collection = get_or_create_corpus_collection()
    if collection is None or collection.count() == 0:
        return []

    safe_n = min(n, collection.count())
    if safe_n == 0:
        return []

    kwargs: dict[str, Any] = {
        "query_texts": [query],
        "n_results": safe_n,
        "include": ["documents", "metadatas", "distances"],
    }
    if source_type is not None:
        kwargs["where"] = {"source_type": source_type}

    try:
        results = collection.query(**kwargs)
    except Exception as exc:
        logger.warning(
            "retriever: ChromaDB query failed (source_type=%s, n=%d): %s",
            source_type,
            n,
            exc,
        )
        return []

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    output: list[dict[str, Any]] = []
    for doc, meta, dist in zip(docs, metas, distances):
        entry: dict[str, Any] = {
            "text": doc,
            "score": round(1.0 - dist, 4),  # cosine distance → similarity
        }
        entry.update(meta)  # spreads stored metadata (source_type, article_title, …)
        output.append(entry)

    return output


# ---------------------------------------------------------------------------
# Two-pass retrieval (public API)
# ---------------------------------------------------------------------------

def two_pass_retrieve(
    query: str,
    n: int | None = None,
) -> list[dict[str, Any]]:
    """Two-pass corpus retrieval with re-ranker.

    Pass 1 — Fetch up to ``n`` fragments with ``source_type='own'``.
    Pass 2 — If Pass 1 returns 0 fragments, fetch ``n`` fragments with
             ``source_type='external'`` (fallback when no own_text exists).
    Fill   — If Pass 1 returns 1..n-1 fragments, fill the remaining slots
             with external fragments.

    The final list is run through :func:`rerank` so own_text fragments always
    appear before external_blogger fragments in the returned list.

    Args:
        query: Embedding query string.
        n: Number of fragments to retrieve. Defaults to ``settings.rag_top_k``.

    Returns:
        Ordered list of fragment dicts with ``text``, ``score``, ``source_type``
        and additional metadata fields. Own_text fragments come first.
    """
    if n is None:
        n = settings.rag_top_k

    # Pass 1: own_text
    own_fragments = _query_collection(query, n=n, source_type="own")
    logger.debug("retriever: Pass 1 — %d own_text fragment(s).", len(own_fragments))

    if len(own_fragments) == 0:
        # No own_text in corpus at all → full fallback to external_blogger
        logger.info(
            "retriever: no own_text fragments found — falling back to external_blogger."
        )
        ext_fragments = _query_collection(query, n=n, source_type="external")
        logger.debug(
            "retriever: Pass 2 (fallback) — %d external_blogger fragment(s).",
            len(ext_fragments),
        )
        return ext_fragments  # already pure external, no re-ranking needed

    if len(own_fragments) >= n:
        # Enough own_text — return as-is (no external mixed in)
        return own_fragments[:n]

    # Fill remaining slots from external_blogger
    fill_count = n - len(own_fragments)
    ext_fragments = _query_collection(query, n=fill_count, source_type="external")
    logger.debug(
        "retriever: fill — %d external_blogger fragment(s) appended.",
        len(ext_fragments),
    )

    combined = own_fragments + ext_fragments
    return rerank(combined)
