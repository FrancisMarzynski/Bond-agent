import re
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt

from bond.config import settings
from bond.graph.state import AuthorState
from bond.prompts.context import build_context_block
from bond.prompts.writer import FORBIDDEN_WORD_STEMS, WRITER_SYSTEM_PROMPT
from bond.store.chroma import get_corpus_collection

LOW_CORPUS_THRESHOLD = 10


# ---------------------------------------------------------------------------
# RAG exemplar retrieval
# ---------------------------------------------------------------------------

def _fetch_rag_exemplars(topic: str, n: int = 5) -> list[str]:
    """
    Fetch style exemplar fragments from Phase 1 corpus.
    Prefers own_text source; falls back to all types if < 3 own-text results found.
    Returns a list of text strings.
    """
    collection = get_corpus_collection()
    if collection is None or collection.count() == 0:
        return []

    # Try own_text first
    try:
        own_results = collection.query(
            query_texts=[topic],
            n_results=n,
            where={"source_type": "own"},
            include=["documents"],
        )
        own_docs = own_results["documents"][0] if own_results["documents"] else []
    except Exception:
        own_docs = []

    if len(own_docs) >= 3:
        return own_docs[:n]

    # Fall back to all source types
    try:
        all_results = collection.query(
            query_texts=[topic],
            n_results=n,
            include=["documents"],
        )
        return all_results["documents"][0] if all_results["documents"] else []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Output cleanup
# ---------------------------------------------------------------------------

def _strip_thinking_tags(text: str) -> str:
    """Remove <thinking>...</thinking> blocks emitted by the LLM's reasoning step."""
    return re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL).strip()


def _strip_markdown_wrapper(text: str) -> str:
    """Strip ```markdown ... ``` or ``` ... ``` wrappers the LLM may add despite instructions."""
    text = text.strip()
    if text.startswith("```markdown"):
        text = text[len("```markdown"):].lstrip("\n")
    elif text.startswith("```"):
        text = text[3:].lstrip("\n")
    if text.endswith("```"):
        text = text[:-3].rstrip("\n")
    return text.strip()


def _clean_output(text: str) -> str:
    """Full output cleanup pipeline: strip thinking tags, then markdown wrappers."""
    return _strip_markdown_wrapper(_strip_thinking_tags(text))


# ---------------------------------------------------------------------------
# SEO + tone constraint validation
# ---------------------------------------------------------------------------

def _check_forbidden_words(draft: str) -> list[str]:
    """Return list of forbidden word stems found in draft (stem = catches all inflected forms)."""
    draft_lower = draft.lower()
    return [stem for stem in FORBIDDEN_WORD_STEMS if stem in draft_lower]


def _validate_draft(draft: str, primary_keyword: str, min_words: int) -> dict[str, bool]:
    """Check all hard constraints. Returns dict of constraint_name -> passed."""
    lines = draft.split("\n")
    h1_lines = [l for l in lines if re.match(r"^#\s+", l)]
    first_para = next(
        (l.strip() for l in lines if l.strip() and not l.strip().startswith("#")),
        ""
    )

    meta_match = re.search(
        r"(?:Meta[- ]?[Dd]escription|Meta opis)[:\s]+(.+)",
        draft,
        re.IGNORECASE,
    )
    meta_desc = meta_match.group(1).strip() if meta_match else ""

    word_count = len(draft.split())
    pk_lower = primary_keyword.lower()

    return {
        "keyword_in_h1": bool(h1_lines and pk_lower in h1_lines[0].lower()),
        "keyword_in_first_para": pk_lower in first_para.lower(),
        "meta_desc_length_ok": 150 <= len(meta_desc) <= 160,
        "word_count_ok": word_count >= min_words,
        "no_forbidden_words": len(_check_forbidden_words(draft)) == 0,
    }


# ---------------------------------------------------------------------------
# Prompt builder (user message only — system prompt is in bond/prompts/writer.py)
# ---------------------------------------------------------------------------

def _build_writer_user_prompt(
    topic: str,
    keywords: list[str],
    heading_structure: str,
    research_report: str,
    exemplars: list[str],
    min_words: int,
    context_block: str = "",
    cp2_feedback: Optional[str] = None,
    current_draft: Optional[str] = None,
) -> str:
    """Build the user message for the writer LLM. System directives live in WRITER_SYSTEM_PROMPT."""
    primary_keyword = keywords[0] if keywords else topic
    other_keywords = ", ".join(keywords[1:]) if len(keywords) > 1 else "brak"

    exemplar_section = ""
    if exemplars:
        formatted = "\n\n---\n\n".join(exemplars[:5])
        exemplar_section = f"""
## WZORCE STYLISTYCZNE (Few-Shot)
Pisz w podobnym tonie i stylu — nie kopiuj treści, tylko styl.

{formatted}

---
"""

    context_section = f"\n{context_block}\n" if context_block else ""

    if cp2_feedback and current_draft:
        return f"""## ZADANIE
Popraw TYLKO wskazane sekcje artykułu. Zachowaj pozostałe sekcje bez zmian.
{context_section}

## FEEDBACK UŻYTKOWNIKA
{cp2_feedback}

## OBECNY DRAFT (do poprawki)
{current_draft}
{exemplar_section}
## WYMAGANIA SEO (muszą być spełnione po poprawce)
- Główne słowo kluczowe "{primary_keyword}" w H1 i pierwszym akapicie
- Meta-description: dokładnie jedna linia zaczynająca się od "Meta-description:" zawierająca 150-160 znaków
- Minimum {min_words} słów
- Hierarchia nagłówków: # H1 → ## H2 → ### H3

Zwróć CAŁY artykuł (poprawione sekcje + niezmienione sekcje)."""
    else:
        return f"""## ZADANIE
Napisz kompletny artykuł blogowy w Markdown.
{context_section}
## TEMAT
{topic}

## SŁOWA KLUCZOWE
Główne: {primary_keyword}
Poboczne: {other_keywords}

## STRUKTURA NAGŁÓWKÓW (obowiązkowa)
{heading_structure}

## RAPORT BADAWCZY
{research_report[:3000]}
{exemplar_section}
## WYMAGANIA SEO (wszystkie obowiązkowe)
1. Główne słowo kluczowe "{primary_keyword}" musi być w H1 i w pierwszym akapicie
2. Poprawna hierarchia nagłówków: # H1, ## H2, ### H3
3. Meta-description: JEDNA linia w formacie "Meta-description: [treść]" zawierająca dokładnie 150-160 znaków
4. Minimum {min_words} słów (nie licząc nagłówków i meta-description)
5. Naturalne wplecenie słów kluczowych (bez keyword stuffing)"""


# ---------------------------------------------------------------------------
# Writer node
# ---------------------------------------------------------------------------

def writer_node(state: AuthorState) -> dict:
    """
    Generate SEO-compliant draft with RAG style injection and Tone of Voice enforcement.

    Before generation:
    - Checks RAG corpus count. If < LOW_CORPUS_THRESHOLD (10 articles), interrupts with
      a warning and waits for user confirmation (locked user decision from CONTEXT.md).
      User must respond True (proceed anyway) or False (abort pipeline).

    After corpus check:
    - Auto-retries up to 2 times if hard constraints fail (SEO or forbidden words).
    - On cp2_feedback: targeted section revision (preserves unchanged sections).
    """
    topic = state["topic"]
    keywords = state.get("keywords", [])
    primary_keyword = keywords[0] if keywords else topic
    heading_structure = state.get("heading_structure", "")
    research_report = state.get("research_report", "")
    cp2_feedback = state.get("cp2_feedback")
    current_draft = state.get("draft")  # for targeted revision
    min_words = settings.min_word_count

    # --- Low corpus gate ---
    corpus_collection = get_corpus_collection()
    corpus_count = corpus_collection.count() if corpus_collection is not None else 0
    if corpus_count < LOW_CORPUS_THRESHOLD:
        proceed = interrupt({
            "warning": "low_corpus",
            "message": (
                f"Korpus zawiera tylko {corpus_count} artykułów "
                f"(minimum: {LOW_CORPUS_THRESHOLD}). Styl draftu może być niespójny. "
                "Kontynuować?"
            ),
            "corpus_count": corpus_count,
            "threshold": LOW_CORPUS_THRESHOLD,
            "instructions": "Odpowiedz True, aby kontynuować, lub False, aby przerwać.",
        })
        if not proceed:
            return {"draft": None, "draft_validated": False}

    # Select DRAFT_MODEL LLM (temperature 0.5–0.7 per COMMUNICATION_STYLE.md §3)
    draft_model = settings.draft_model
    if "claude" in draft_model.lower():
        llm = ChatAnthropic(model=draft_model, max_tokens=4096, temperature=0.7)
    else:
        llm = ChatOpenAI(model=draft_model, max_tokens=4096, temperature=0.7)

    # Fetch RAG exemplars from Phase 1 corpus
    exemplars = _fetch_rag_exemplars(topic, n=5)
    context_block = build_context_block(state.get("context_dynamic"))

    # Generate draft with silent auto-retry (max 2 additional attempts = 3 total)
    draft = ""
    validation = {}
    max_attempts = 3
    for attempt in range(max_attempts):
        user_prompt = _build_writer_user_prompt(
            topic=topic,
            keywords=keywords,
            heading_structure=heading_structure,
            research_report=research_report,
            exemplars=exemplars,
            min_words=min_words,
            context_block=context_block,
            cp2_feedback=cp2_feedback if attempt == 0 else None,
            current_draft=current_draft if attempt == 0 else None,
        )
        messages = [
            SystemMessage(content=WRITER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
        draft = _clean_output(llm.invoke(messages).content)
        validation = _validate_draft(draft, primary_keyword, min_words)

        all_passed = all(validation.values())
        if all_passed:
            return {"draft": draft, "draft_validated": True}

        if attempt < max_attempts - 1:
            failed = [k for k, v in validation.items() if not v]
            print(f"Writer auto-retry {attempt + 1}/{max_attempts - 1}: failed constraints: {failed}")

    # All retries exhausted
    failed_constraints = [k for k, v in validation.items() if not v]
    print(f"WARNING: Draft failed validation after {max_attempts} attempts. Failed: {failed_constraints}")
    return {"draft": draft, "draft_validated": False}
