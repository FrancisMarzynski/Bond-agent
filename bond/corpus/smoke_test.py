"""Corpus smoke test — exercises two-pass retrieval with re-ranker.

Uses :func:`bond.corpus.retriever.two_pass_retrieve` directly so that the
smoke test validates exactly the same code path as the production pipeline.
"""
from bond.corpus.retriever import two_pass_retrieve
from bond.config import settings

DEFAULT_QUERY = "styl pisania storytelling angażujące treści"


def run_smoke_test(
    query: str = DEFAULT_QUERY,
    n_results: int | None = None,
) -> list[dict]:
    """Run two-pass retrieval smoke test.

    Returns ranked results with cosine similarity scores and source metadata.
    Own_text fragments are guaranteed to appear before external_blogger fragments
    (enforced by the re-ranker inside two_pass_retrieve).

    Returns empty list with a warning if the corpus is empty.
    """
    if n_results is None:
        n_results = settings.rag_top_k

    fragments = two_pass_retrieve(query, n=n_results)

    if not fragments:
        print("WARN: Corpus is empty — smoke test returned no results")
        return []

    output = []
    for rank, frag in enumerate(fragments, start=1):
        output.append({
            "rank": rank,
            "score": frag.get("score", 0.0),
            "source_type": frag.get("source_type", "unknown"),
            "article_title": frag.get("article_title", "unknown"),
            "source_url": frag.get("source_url", ""),
            "fragment": frag["text"][:300] + ("..." if len(frag["text"]) > 300 else ""),
        })

    return output
