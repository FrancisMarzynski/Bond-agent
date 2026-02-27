import re
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt

from bond.config import settings
from bond.graph.state import AuthorState
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
# SEO constraint validation
# ---------------------------------------------------------------------------

def _validate_draft(draft: str, primary_keyword: str, min_words: int) -> dict[str, bool]:
    """Check all hard SEO constraints. Returns dict of constraint_name -> passed."""
    lines = draft.split("\n")
    h1_lines = [l for l in lines if re.match(r"^#\s+", l)]
    # First non-empty, non-heading paragraph
    first_para = next(
        (l.strip() for l in lines if l.strip() and not l.strip().startswith("#")),
        ""
    )

    # Meta description: accept "Meta-description:", "Meta opis:", "Meta description:" patterns
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
    }


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_writer_prompt(
    topic: str,
    keywords: list[str],
    heading_structure: str,
    research_report: str,
    exemplars: list[str],
    min_words: int,
    cp2_feedback: Optional[str] = None,
    current_draft: Optional[str] = None,
) -> str:
    """Build the system+user prompt for the writer LLM."""
    primary_keyword = keywords[0] if keywords else topic
    other_keywords = ", ".join(keywords[1:]) if len(keywords) > 1 else "brak"

    exemplar_section = ""
    if exemplars:
        formatted = "\n\n---\n\n".join(exemplars[:5])
        exemplar_section = f"""## WZORCE STYLISTYCZNE (Few-Shot)
Poniższe fragmenty ilustrują pożądany styl pisania. Pisz w podobnym tonie i stylu — nie kopiuj treści, tylko styl.

{formatted}

---
"""

    if cp2_feedback and current_draft:
        # Targeted revision mode: preserve unchanged sections
        return f"""Jesteś redaktorem. Użytkownik odrzucił draft artykułu i wskazał sekcje do poprawki.

{exemplar_section}## ZADANIE
Popraw TYLKO wskazane sekcje. Zachowaj pozostałe sekcje bez zmian.

## FEEDBACK UŻYTKOWNIKA
{cp2_feedback}

## OBECNY DRAFT (do poprawki)
{current_draft}

## WYMAGANIA SEO (muszą być spełnione po poprawce)
- Główne słowo kluczowe "{primary_keyword}" w H1 i pierwszym akapicie
- Meta-description: dokładnie jedna linia zaczynająca się od "Meta-description:" zawierająca 150-160 znaków
- Minimum {min_words} słów
- Hierarchia nagłówków: # H1 → ## H2 → ### H3

Zwróć CAŁY artykuł (poprawione sekcje + niezmienione sekcje)."""
    else:
        # Fresh draft generation
        return f"""Jesteś ekspertem SEO copywriterem piszącym po polsku.

{exemplar_section}## TEMAT
{topic}

## SŁOWA KLUCZOWE
Główne: {primary_keyword}
Poboczne: {other_keywords}

## STRUKTURA NAGŁÓWKÓW (obowiązkowa)
{heading_structure}

## RAPORT BADAWCZY (informacje do uwzględnienia)
{research_report[:3000]}

## WYMAGANIA SEO (wszystkie obowiązkowe)
1. Główne słowo kluczowe "{primary_keyword}" musi być w H1 i w pierwszym akapicie
2. Poprawna hierarchia nagłówków: # H1, ## H2, ### H3
3. Meta-description: JEDNA linia w formacie "Meta-description: [treść]" zawierająca dokładnie 150-160 znaków
4. Minimum {min_words} słów (nie licząc nagłówków i meta-description)
5. Naturalne wplecenie słów kluczowych (bez keyword stuffing)

Napisz kompletny artykuł blogowy w Markdown."""


# ---------------------------------------------------------------------------
# Writer node
# ---------------------------------------------------------------------------

def writer_node(state: AuthorState) -> dict:
    """
    Generate SEO-compliant draft with RAG style injection.

    Before generation:
    - Checks RAG corpus count. If < LOW_CORPUS_THRESHOLD (10 articles), interrupts with
      a warning and waits for user confirmation (locked user decision from CONTEXT.md).
      User must respond True (proceed anyway) or False (abort pipeline).

    After corpus check:
    - Auto-retries up to 2 times if hard constraints fail.
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

    # --- Low corpus gate (locked user decision) ---
    # Check corpus count before generating the draft. If the style corpus has
    # fewer than LOW_CORPUS_THRESHOLD articles, warn the user and pause.
    # The user must explicitly confirm (True) to proceed or abort (False).
    corpus_collection = get_corpus_collection()
    corpus_count = corpus_collection.count() if corpus_collection is not None else 0
    if corpus_count < LOW_CORPUS_THRESHOLD:
        proceed = interrupt({
            "warning": "low_corpus",
            "message": (
                f"Korpus stylistyczny zawiera tylko {corpus_count} artykułów "
                f"(próg: {LOW_CORPUS_THRESHOLD}). Styl generowanego draftu może być niskiej jakości. "
                "Potwierdź, aby kontynuować, lub przerwij i najpierw dodaj więcej artykułów do korpusu."
            ),
            "corpus_count": corpus_count,
            "threshold": LOW_CORPUS_THRESHOLD,
            "instructions": "Odpowiedz True, aby kontynuować generowanie, lub False, aby przerwać.",
        })
        if not proceed:
            # User chose to abort — return draft=None, draft_validated=False
            return {"draft": None, "draft_validated": False}

    # Select DRAFT_MODEL LLM (AUTH-11)
    draft_model = settings.draft_model
    if "claude" in draft_model.lower():
        llm = ChatAnthropic(model=draft_model, max_tokens=4096, temperature=0.7)
    else:
        llm = ChatOpenAI(model=draft_model, max_tokens=4096, temperature=0.7)

    # Fetch RAG exemplars from Phase 1 corpus
    exemplars = _fetch_rag_exemplars(topic, n=5)

    # Generate draft with silent auto-retry (max 2 additional attempts = 3 total)
    draft = ""
    validation = {}
    max_attempts = 3
    for attempt in range(max_attempts):
        prompt = _build_writer_prompt(
            topic=topic,
            keywords=keywords,
            heading_structure=heading_structure,
            research_report=research_report,
            exemplars=exemplars,
            min_words=min_words,
            cp2_feedback=cp2_feedback if attempt == 0 else None,  # feedback only on first targeted attempt
            current_draft=current_draft if attempt == 0 else None,
        )
        draft = llm.invoke(prompt).content.strip()
        validation = _validate_draft(draft, primary_keyword, min_words)

        all_passed = all(validation.values())
        if all_passed:
            return {"draft": draft, "draft_validated": True}

        if attempt < max_attempts - 1:
            # Silent retry — log which constraints failed
            failed = [k for k, v in validation.items() if not v]
            print(f"Writer auto-retry {attempt + 1}/{max_attempts - 1}: failed constraints: {failed}")

    # All retries exhausted — surface failure (user will see draft_validated=False)
    failed_constraints = [k for k, v in validation.items() if not v]
    print(f"WARNING: Draft failed validation after {max_attempts} attempts. Failed: {failed_constraints}")
    return {"draft": draft, "draft_validated": False}
