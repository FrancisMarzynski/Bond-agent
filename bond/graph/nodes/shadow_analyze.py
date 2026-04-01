"""Shadow analyze node — RAG corpus retrieval + comparative style analysis.

Responsibility:
1. Retrieve up to n most relevant fragments from ChromaDB corpus via two-pass retriever
   (own_text preferred; external_blogger fallback when no own_text exists).
2. Run LLM comparative analysis identifying tone, punctuation, and vocabulary differences.
3. Store analysis in state["research_report"] (re-use of existing BondState field).
4. Pass raw fragments in state["shadow_corpus_fragments"] for downstream shadow_annotate.
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from bond.config import settings
from bond.corpus.retriever import two_pass_retrieve
from bond.graph.state import BondState
from bond.llm import get_research_llm

logger = logging.getLogger(__name__)


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

async def shadow_analyze_node(state: BondState) -> dict:
    """Retrieve style corpus fragments and produce comparative analysis.

    AC compliance:
    - Retrieves up to rag_top_k corpus fragments via two-pass retriever:
        own_text (source_type='own') first; external_blogger fallback if none found.
    - Re-ranker guarantees own_text fragments precede external_blogger in the prompt.
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

    fragments = await two_pass_retrieve(original_text, n=settings.rag_top_k)
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
    llm = get_research_llm(max_tokens=2000)

    user_prompt = _build_analyze_user_prompt(original_text, fragments)
    response = await llm.ainvoke([
        SystemMessage(content=_ANALYZE_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])
    analysis: str = response.content.strip()

    return {
        "research_report": analysis,
        "shadow_corpus_fragments": fragments,
    }
