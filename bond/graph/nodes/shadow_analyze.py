"""Shadow analyze node — RAG corpus retrieval + comparative style analysis.

Responsibility:
1. Retrieve 3-5 most relevant fragments from ChromaDB corpus (two-pass: own texts preferred).
2. Run LLM comparative analysis identifying tone, punctuation, and vocabulary differences.
3. Store analysis in state["research_report"] (re-use of existing BondState field).
4. Pass raw fragments in state["shadow_corpus_fragments"] for downstream shadow_annotate.
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from bond.config import settings
from bond.graph.state import BondState
from bond.store.chroma import get_or_create_corpus_collection

logger = logging.getLogger(__name__)

_MIN_OWN_FRAGMENTS = 3

# ---------------------------------------------------------------------------
# Corpus retrieval (two-pass: own texts → fallback to all)
# ---------------------------------------------------------------------------

def _retrieve_corpus_fragments(query_text: str, n: int) -> list[dict[str, Any]]:
    """Two-pass ChromaDB retrieval.

    Pass 1: source_type='own' fragments only (same author, strongest style signal).
    Pass 2: all types — used when own-text pool yields fewer than _MIN_OWN_FRAGMENTS results.

    Returns a list of dicts with at least a 'text' key and any stored metadata fields.
    """
    collection = get_or_create_corpus_collection()
    if collection is None or collection.count() == 0:
        logger.warning("shadow_analyze: corpus is empty — no style fragments available.")
        return []

    safe_n = min(n, collection.count())

    # Pass 1: own-text fragments
    own_docs: list[str] = []
    own_metas: list[dict] = []
    try:
        own_results = collection.query(
            query_texts=[query_text],
            n_results=safe_n,
            where={"source_type": "own"},
            include=["documents", "metadatas"],
        )
        own_docs = own_results["documents"][0] if own_results["documents"] else []
        own_metas = own_results["metadatas"][0] if own_results["metadatas"] else []
    except Exception as exc:
        logger.warning("shadow_analyze: own-text pass failed: %s", exc)

    if len(own_docs) >= _MIN_OWN_FRAGMENTS:
        return [
            {"text": doc, "source_type": "own", **meta}
            for doc, meta in zip(own_docs[:n], own_metas[:n])
        ]

    # Pass 2: all source types as fallback
    try:
        all_results = collection.query(
            query_texts=[query_text],
            n_results=safe_n,
            include=["documents", "metadatas"],
        )
        all_docs = all_results["documents"][0] if all_results["documents"] else []
        all_metas = all_results["metadatas"][0] if all_results["metadatas"] else []
        return [
            {"text": doc, **meta}
            for doc, meta in zip(all_docs[:n], all_metas[:n])
        ]
    except Exception as exc:
        logger.warning("shadow_analyze: all-types pass failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Comparative analysis prompt
# ---------------------------------------------------------------------------

_ANALYZE_SYSTEM_PROMPT = """Jesteś analitykiem stylu językowego. Porównujesz nadesłany tekst \
z wzorcowymi fragmentami korpusu autora i identyfikujesz KONKRETNE różnice stylistyczne.

Skup się wyłącznie na trzech wymiarach:
1. TON — emocjonalny ładunek, dystans do czytelnika, pewność siebie, poziom formalności
2. INTERPUNKCJA — długość zdań, użycie myślników/przecinków/średników, rytm akapitów
3. SŁOWNICTWO — specjalistyczne vs ogólne, aktywne vs pasywne konstrukcje, powtarzające się wzorce

Format odpowiedzi (Markdown):

### Analiza porównawcza stylu

#### Ton
[konkretne różnice z cytatami z obu tekstów]

#### Interpunkcja i rytm zdań
[konkretne różnice z cytatami]

#### Słownictwo i konstrukcje zdań
[konkretne różnice z cytatami]

#### Podsumowanie odchyleń
[3-5 punktów: najważniejsze obszary do korekty, od największego odchylenia do najmniejszego]

Pisz po polsku. Bądź precyzyjny — podawaj cytaty z obu tekstów jako dowód każdej obserwacji."""


def _build_analyze_user_prompt(original_text: str, fragments: list[dict[str, Any]]) -> str:
    """Build user message for the comparative analysis LLM call."""
    corpus_block = "\n\n---\n\n".join(
        f"[Fragment {i + 1}]\n{frag['text']}" for i, frag in enumerate(fragments)
    )
    return (
        f"## TEKST DO ANALIZY\n\n{original_text}\n\n"
        f"## WZORCOWE FRAGMENTY KORPUSU AUTORA\n\n{corpus_block}\n\n"
        "Przeanalizuj powyższy tekst względem fragmentów wzorcowych i wskaż różnice stylistyczne."
    )


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def shadow_analyze_node(state: BondState) -> dict:
    """Retrieve style corpus fragments and produce comparative analysis.

    AC compliance:
    - Retrieves 3-5 most relevant corpus fragments (two-pass: own → all).
    - Prompt enforces comparative analysis across tone, punctuation, vocabulary.
    - Analysis stored in state["research_report"] (re-use of existing BondState field).
    - Raw fragments stored in state["shadow_corpus_fragments"] for shadow_annotate.
    """
    original_text = (state.get("original_text") or "").strip()
    if not original_text:
        logger.warning("shadow_analyze: original_text is empty — skipping analysis.")
        return {
            "research_report": "",
            "shadow_corpus_fragments": [],
        }

    # Retrieve corpus fragments
    n = settings.rag_top_k  # default 5, configured in bond/config.py
    fragments = _retrieve_corpus_fragments(original_text, n=n)
    logger.info("shadow_analyze: retrieved %d corpus fragment(s).", len(fragments))

    if not fragments:
        logger.warning(
            "shadow_analyze: no corpus fragments found — "
            "analysis will lack style reference. Add own-text documents to corpus."
        )
        return {
            "research_report": "Brak fragmentów korpusu — analiza stylistyczna niemożliwa.",
            "shadow_corpus_fragments": [],
        }

    # Select LLM (mirrors researcher_node model selection pattern)
    model = settings.research_model
    if "claude" in model.lower():
        llm = ChatAnthropic(model=model, max_tokens=2000)
    else:
        llm = ChatOpenAI(model=model, max_tokens=2000)

    user_prompt = _build_analyze_user_prompt(original_text, fragments)
    analysis: str = llm.invoke([
        SystemMessage(content=_ANALYZE_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]).content.strip()

    return {
        "research_report": analysis,
        "shadow_corpus_fragments": fragments,
    }
