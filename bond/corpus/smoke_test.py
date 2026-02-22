from bond.store.chroma import get_corpus_collection
from bond.config import settings

DEFAULT_QUERY = "styl pisania storytelling angażujące treści"


def run_smoke_test(
    query: str = DEFAULT_QUERY,
    n_results: int | None = None,
) -> list[dict]:
    """
    Query ChromaDB using two-pass retrieval (own text preferred, external fills remainder).
    Returns ranked results with cosine similarity scores and source metadata.

    Returns empty list with warning print if corpus is empty.
    """
    if n_results is None:
        n_results = settings.rag_top_k

    collection = get_corpus_collection()
    if collection.count() == 0:
        print("WARN: Corpus is empty — smoke test returned no results")
        return []

    # Pass 1: own text
    own_results = _query(collection, query, n_results, source_type="own")
    own_count = len(own_results)

    if own_count >= n_results:
        return own_results

    # Pass 2: fill remainder from external
    fill_count = n_results - own_count
    ext_results = _query(collection, query, fill_count, source_type="external")

    combined = own_results + ext_results
    # Re-rank combined by score descending (own results already preferred)
    combined.sort(key=lambda x: x["score"], reverse=True)
    return combined


def _query(collection, query: str, n: int, source_type: str) -> list[dict]:
    """Query ChromaDB filtered by source_type. Returns [] if no results."""
    try:
        results = collection.query(
            query_texts=[query],
            n_results=n,
            where={"source_type": source_type},
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        # ChromaDB raises if n_results > collection size for a filtered query
        # Retry with n_results=1 as minimum to check availability
        print(f"WARN: Retrieval for source_type={source_type} failed ({e}) — returning empty")
        return []

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    output = []
    for rank, (doc, meta, dist) in enumerate(zip(docs, metas, distances), start=1):
        output.append({
            "rank": rank,
            "score": round(1.0 - dist, 4),  # cosine distance → similarity
            "source_type": meta.get("source_type", "unknown"),
            "article_title": meta.get("article_title", "unknown"),
            "source_url": meta.get("source_url", ""),
            "fragment": doc[:300] + ("..." if len(doc) > 300 else ""),
        })
    return output
