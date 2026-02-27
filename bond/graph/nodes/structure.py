from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from bond.config import settings
from bond.graph.state import AuthorState
from bond.prompts.context import build_context_block


def _get_research_llm():
    """Return LLM for research/analysis tasks based on RESEARCH_MODEL env var."""
    model = settings.research_model
    if "claude" in model.lower():
        return ChatAnthropic(model=model, max_tokens=800)
    return ChatOpenAI(model=model, max_tokens=800)


def structure_node(state: AuthorState) -> dict:
    """
    Generate H1/H2/H3 heading structure from research_report.
    On regeneration, incorporates cp1_feedback (user-edited outline + note).
    """
    llm = _get_research_llm()
    topic = state["topic"]
    keywords = state.get("keywords", [])
    primary_keyword = keywords[0] if keywords else topic
    research_report = state.get("research_report", "")
    cp1_feedback = state.get("cp1_feedback")
    cp1_iterations = state.get("cp1_iterations", 0)
    context_block = build_context_block(state.get("context_dynamic"))

    if cp1_feedback and cp1_iterations > 0:
        # Re-run with user feedback: treat edited structure as strong prior
        prompt = f"""Jesteś redaktorem SEO. Zaproponuj poprawioną strukturę nagłówków (H1/H2/H3) artykułu.

{context_block}

TEMAT: {topic}
SŁOWA KLUCZOWE: {', '.join(keywords)}
GŁÓWNE SŁOWO KLUCZOWE (musi być w H1): {primary_keyword}

Użytkownik edytował poprzednią strukturę i dodał uwagi:
---
{cp1_feedback}
---

Na podstawie tych uwag i raportu badawczego, zaproponuj ostateczną strukturę nagłówków.
Uwzględnij sugestie użytkownika możliwie dokładnie.

RAPORT BADAWCZY:
{research_report[:2000]}

Zwróć TYLKO strukturę nagłówków w formacie Markdown (# H1, ## H2, ### H3). Bez treści artykułu."""
    else:
        # First run
        prompt = f"""Jesteś redaktorem SEO. Na podstawie raportu badawczego zaproponuj strukturę nagłówków artykułu.

{context_block}

TEMAT: {topic}
SŁOWA KLUCZOWE: {', '.join(keywords)}
GŁÓWNE SŁOWO KLUCZOWE (musi być w H1): {primary_keyword}

WYMAGANIA:
- H1 musi zawierać główne słowo kluczowe
- Struktura: 1x H1, 3-6x H2, opcjonalnie H3 pod H2
- Nagłówki po polsku, SEO-friendly, konkretne

RAPORT BADAWCZY:
{research_report[:2000]}

Zwróć TYLKO strukturę nagłówków w formacie Markdown (# H1, ## H2, ### H3). Bez treści artykułu."""

    heading_structure = llm.invoke(prompt).content.strip()
    return {"heading_structure": heading_structure}
