import logging

from langchain_core.messages import HumanMessage

from bond.config import settings
from bond.graph.state import AuthorState
from bond.llm import estimate_cost_usd, get_draft_llm
from bond.prompts.context import build_context_block
from bond.prompts.research_context import select_research_context

log = logging.getLogger(__name__)

_STRUCTURE_MAX_OUTPUT_TOKENS = 800


def _build_structure_prompt(
    *,
    topic: str,
    keywords: list[str],
    primary_keyword: str,
    research_context: str,
    context_block: str,
    cp1_feedback: str | None,
    cp1_iterations: int,
) -> str:
    keyword_list = ", ".join(keywords)
    if cp1_feedback and cp1_iterations > 0:
        return f"""Jesteś redaktorem SEO. Zaproponuj poprawioną strukturę nagłówków (H1/H2/H3) artykułu.

{context_block}

TEMAT: {topic}
SŁOWA KLUCZOWE: {keyword_list}
GŁÓWNE SŁOWO KLUCZOWE (musi być w H1): {primary_keyword}

Użytkownik edytował poprzednią strukturę i dodał uwagi:
---
{cp1_feedback}
---

Na podstawie tych uwag i raportu badawczego, zaproponuj ostateczną strukturę nagłówków.
Uwzględnij sugestie użytkownika możliwie dokładnie.

RAPORT BADAWCZY:
{research_context}

Zwróć TYLKO strukturę nagłówków w formacie Markdown (# H1, ## H2, ### H3). Bez treści artykułu."""

    return f"""Jesteś redaktorem SEO. Na podstawie raportu badawczego zaproponuj strukturę nagłówków artykułu.

{context_block}

TEMAT: {topic}
SŁOWA KLUCZOWE: {keyword_list}
GŁÓWNE SŁOWO KLUCZOWE (musi być w H1): {primary_keyword}

WYMAGANIA:
- H1 musi zawierać główne słowo kluczowe
- Struktura: 1x H1, 3-6x H2, opcjonalnie H3 pod H2
- Nagłówki po polsku, SEO-friendly, konkretne

RAPORT BADAWCZY:
{research_context}

Zwróć TYLKO strukturę nagłówków w formacie Markdown (# H1, ## H2, ### H3). Bez treści artykułu."""


async def structure_node(state: AuthorState) -> dict:
    """
    Generate H1/H2/H3 heading structure from research_report.
    On regeneration, incorporates cp1_feedback (user-edited outline + note).
    """
    llm = get_draft_llm(max_tokens=_STRUCTURE_MAX_OUTPUT_TOKENS, temperature=0)
    topic = state["topic"]
    keywords = state.get("keywords", [])
    primary_keyword = keywords[0] if keywords else topic
    research_report = state.get("research_report", "")
    cp1_feedback = state.get("cp1_feedback")
    cp1_iterations = state.get("cp1_iterations", 0)
    context_block = build_context_block(state.get("context_dynamic"))
    research_context_selection = select_research_context(
        llm=llm,
        research_report=research_report,
        research_data=state.get("research_data"),
        build_prompt_payload=lambda research_context: [
            HumanMessage(
                content=_build_structure_prompt(
                    topic=topic,
                    keywords=keywords,
                    primary_keyword=primary_keyword,
                    research_context=research_context,
                    context_block=context_block,
                    cp1_feedback=cp1_feedback,
                    cp1_iterations=cp1_iterations,
                )
            )
        ],
        reserved_output_tokens=_STRUCTURE_MAX_OUTPUT_TOKENS,
    )
    prompt = _build_structure_prompt(
        topic=topic,
        keywords=keywords,
        primary_keyword=primary_keyword,
        research_context=research_context_selection.variant.content,
        context_block=context_block,
        cp1_feedback=cp1_feedback,
        cp1_iterations=cp1_iterations,
    )
    if not research_context_selection.fit_found:
        log.warning(
            "Structure prompt exceeded available input budget even after compaction: %s > %s (variant=%s)",
            research_context_selection.estimated_prompt_tokens,
            research_context_selection.available_input_tokens,
            research_context_selection.variant.kind,
        )

    response = await llm.ainvoke(prompt)
    heading_structure = response.content.strip()

    usage = response.usage_metadata or {}
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    call_cost = estimate_cost_usd(settings.draft_model, input_tokens, output_tokens)

    existing_research_tokens = state.get("tokens_used_research", 0)
    existing_cost = state.get("estimated_cost_usd", 0.0)

    return {
        "heading_structure": heading_structure,
        "tokens_used_research": existing_research_tokens + input_tokens + output_tokens,
        "estimated_cost_usd": existing_cost + call_cost,
    }
