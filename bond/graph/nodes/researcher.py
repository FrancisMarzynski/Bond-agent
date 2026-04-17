import asyncio
import logging
import re

from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel, field_validator

from bond.config import settings
from bond.db.search_cache import compute_query_hash, get_cached_result, save_cached_result
from bond.graph.state import AuthorState
from bond.llm import estimate_cost_usd, get_research_llm
from bond.prompts.context import build_context_block

log = logging.getLogger(__name__)

EXA_MCP_URL = "https://mcp.exa.ai/mcp"
_MIN_SOURCES = 3
_MAX_UNIQUE_SOURCES = 20

# Matches any http/https URL (stops at whitespace or common closing punctuation).
_URL_RE = re.compile(r"https?://[^\s\])\">'\,]+")


class ResearchQueries(BaseModel):
    """Exactly 3 Exa search queries covering different angles of the topic."""

    general: str
    stats: str
    case_study: str

    @field_validator("general", "stats", "case_study")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("query must not be empty")
        return v.strip()

    def as_list(self) -> list[str]:
        return [self.general, self.stats, self.case_study]


class SourceItem(BaseModel):
    """Single cited source extracted from Exa results."""

    title: str
    url: str
    summary: str

    @field_validator("url")
    @classmethod
    def clean_url(cls, v: str) -> str:
        return v.strip().rstrip(".,;")


class ResearchData(BaseModel):
    """Structured research output split into facts, statistics, and sources."""

    fakty: list[str]
    statystyki: list[str]
    zrodla: list[SourceItem]

    @field_validator("fakty", "statystyki")
    @classmethod
    def strip_items(cls, v: list[str]) -> list[str]:
        return [item.strip() for item in v if item.strip()]

    def to_markdown(self, topic: str) -> str:
        """Render structured data as a Markdown report for downstream nodes."""
        parts = [f"## Raport z badań: {topic}"]

        if self.fakty:
            facts_block = "\n".join(f"- {f}" for f in self.fakty)
            parts.append(f"### Fakty\n{facts_block}")

        if self.statystyki:
            stats_block = "\n".join(f"- {s}" for s in self.statystyki)
            parts.append(f"### Statystyki\n{stats_block}")

        if self.zrodla:
            source_lines = []
            for i, src in enumerate(self.zrodla, 1):
                source_lines.append(
                    f"{i}. **{src.title}**\n   {src.url}\n   {src.summary}"
                )
            parts.append("### Źródła\n" + "\n\n".join(source_lines))

        return "\n\n".join(parts)


# Module-level tools cache — fetched once per process, reused across node calls.
_exa_tools_cache: list | None = None


async def _get_exa_tools() -> list:
    """Fetch Exa MCP tools and cache them for the lifetime of the process."""
    global _exa_tools_cache
    if _exa_tools_cache is not None:
        return _exa_tools_cache
    client = MultiServerMCPClient(
        {"exa": {"url": EXA_MCP_URL, "transport": "streamable_http"}}
    )
    _exa_tools_cache = await client.get_tools()
    return _exa_tools_cache


async def _generate_sub_queries(topic: str, keywords: list[str]) -> ResearchQueries:
    """Generate 3 diverse Exa queries (General, Stats, Case Study) via structured LLM output."""
    kw_str = ", ".join(keywords) if keywords else topic
    prompt = f"""Jesteś specjalistą SEO. Wygeneruj 3 zapytania do wyszukiwarki Exa dla artykułu o temacie: "{topic}" (słowa kluczowe: {kw_str}).

Każde zapytanie musi pokrywać inny kąt:
- general: ogólne tło i kontekst tematu
- stats: liczby, statystyki, dane rynkowe, raporty
- case_study: przykłady wdrożeń, studia przypadku, konkretne realizacje

Zapytania pisz po polsku lub angielsku (wybierz język, który da lepsze wyniki). Każde zapytanie: 5-12 słów, precyzyjne, wyszukiwarkowo skuteczne."""

    llm = get_research_llm(max_tokens=300, temperature=0)
    structured_llm = llm.with_structured_output(ResearchQueries)
    result: ResearchQueries = await structured_llm.ainvoke(prompt)
    log.info(
        "sub-queries generated — general=%r stats=%r case_study=%r",
        result.general,
        result.stats,
        result.case_study,
    )
    return result


async def _call_exa_mcp(query: str, keywords: list[str], num_results: int = 8) -> str:
    """
    Call Exa web_search_exa tool via MCP HTTP.
    Returns the raw formatted results string.
    """
    search_query = f"{query} {' '.join(keywords)}" if keywords else query

    tools = await _get_exa_tools()
    web_search = next((t for t in tools if t.name == "web_search_exa"), None)
    if web_search is None:
        available = [t.name for t in tools]
        raise RuntimeError(
            f"web_search_exa not found in Exa MCP. Available: {available}"
        )
    result = await web_search.ainvoke({"query": search_query, "numResults": num_results})
    return result if isinstance(result, str) else str(result)


def _deduplicate_sections(labeled_sections: list[tuple[str, str]]) -> tuple[str, int]:
    """
    Merge labeled result sections, deduplicating entries by their first URL.

    Each Exa result block starts with a digit-dot prefix (e.g. "1. Title").
    We split on those boundaries, extract the primary URL from each block,
    and keep only the first occurrence.  Stops after _MAX_UNIQUE_SOURCES unique
    sources have been collected across all sections.

    Args:
        labeled_sections: [(label, raw_exa_string), ...]

    Returns:
        (combined_markdown_string, unique_source_count)
    """
    seen_urls: set[str] = set()
    output_parts: list[str] = []

    for label, section in labeled_sections:
        # Split before each numbered result entry.
        blocks = re.split(r"(?m)^(?=\d+\.)", section)
        kept: list[str] = []
        for block in blocks:
            stripped = block.strip()
            if not stripped:
                continue
            urls = _URL_RE.findall(stripped)
            if not urls:
                # Non-result preamble text — keep as-is
                kept.append(block)
                continue
            primary_url = urls[0].rstrip(".,;")
            if primary_url in seen_urls:
                log.debug("dedup: skipping duplicate URL %s", primary_url)
                continue
            if len(seen_urls) >= _MAX_UNIQUE_SOURCES:
                log.debug("dedup: reached max unique sources (%d), skipping", _MAX_UNIQUE_SOURCES)
                continue
            seen_urls.add(primary_url)
            kept.append(block)

        if kept:
            output_parts.append(f"### {label}\n" + "".join(kept))

    unique_count = len(seen_urls)
    log.info("dedup: %d unique sources retained (max %d)", unique_count, _MAX_UNIQUE_SOURCES)
    return "\n\n".join(output_parts), unique_count


async def _synthesize_structured(
    raw_results: str,
    topic: str,
    keywords: list[str],
    context_block: str = "",
) -> tuple[ResearchData, int, int]:
    """
    Map-reduce synthesis: extract Facts, Statistics, and Sources as structured data.

    Uses with_structured_output(ResearchData, include_raw=True) to enforce the
    Pydantic schema and still capture LLM token usage from the raw AIMessage.

    Returns:
        (ResearchData, input_tokens, output_tokens)
    """
    context_section = f"\n{context_block}\n" if context_block else ""
    prompt = f"""Jesteś analitykiem badań. Przeanalizuj poniższe wyniki wyszukiwania i wyekstraktuj dane w 3 kategoriach:{context_section}

TEMAT: {topic}
SŁOWA KLUCZOWE: {', '.join(keywords)}

WYNIKI WYSZUKIWANIA:
{raw_results}

Wyekstraktuj:
- fakty: lista 5-10 kluczowych twierdzeń merytorycznych (po polsku, zwięźle — sam fakt lub wniosek, bez danych liczbowych)
- statystyki: lista 5-10 konkretnych danych liczbowych wyekstraktowanych ze źródeł (format: "N% / N mln / N lat — krótki kontekst")
- zrodla: lista wszystkich unikalnych artykułów (każde: title, url, summary 1-2 zdania po polsku)"""

    llm = get_research_llm(max_tokens=3000)
    structured_llm = llm.with_structured_output(ResearchData, include_raw=True)
    raw_output: dict = await structured_llm.ainvoke(prompt)

    data: ResearchData | None = raw_output.get("parsed")
    parsing_error = raw_output.get("parsing_error")
    if data is None:
        raise ValueError(f"Structured synthesis failed to parse LLM output: {parsing_error}")

    raw_response = raw_output.get("raw")
    usage = (raw_response.usage_metadata or {}) if raw_response else {}
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    log.info(
        "synthesis: %d facts, %d stats, %d sources",
        len(data.fakty),
        len(data.statystyki),
        len(data.zrodla),
    )
    return data, input_tokens, output_tokens


async def researcher_node(state: AuthorState) -> dict:
    """
    Perform web research via Exa MCP.  Cache lookup order (AUTH-10 / AUTH-11):

    1. In-memory state cache  — avoids duplicate calls within the same graph run.
    2. SQLite search_cache    — avoids duplicate calls across re-runs in the same
                                session (same thread_id).  Table: bond_metadata.db.
    3. Exa MCP API            — live search; result is written to both caches.

    Returns updated search_cache (raw MCP results string, keyed by topic)
    and formatted research_report (Markdown).

    Raises ValueError if the formatted report contains fewer than _MIN_SOURCES sources.

    Known limitation: source URLs are not validated for reachability or paywall status.
    Exa returns indexed content but cannot guarantee live access at generation time.
    """
    topic = state["topic"]
    keywords = state.get("keywords", [])
    thread_id = state.get("thread_id", "")
    cache = state.get("search_cache", {})

    if topic in cache:
        # Layer 1 hit — in-memory state cache (AUTH-10)
        raw_results = cache[topic]
    else:
        query_hash = compute_query_hash(topic, keywords)

        # Layer 2 — SQLite session cache (AUTH-11).
        db_result: str | None = None
        try:
            db_result = await get_cached_result(query_hash, thread_id)
        except Exception as exc:
            log.error("search_cache read failed, proceeding without cache: %s", exc)

        if db_result is not None:
            raw_results = db_result
        else:
            # Layer 3 — parallel multi-query Exa MCP calls (General / Stats / Case Study)
            sub_queries = await _generate_sub_queries(topic, keywords)
            labels = ["General", "Stats", "Case Study"]
            queries = sub_queries.as_list()
            for label, query in zip(labels, queries):
                log.info("exa search [%s]: %r", label, query)

            sections: list[str] = await asyncio.gather(
                *[_call_exa_mcp(q, keywords, num_results=8) for q in queries]
            )
            labeled = list(zip(labels, sections))
            raw_results, unique_count = _deduplicate_sections(labeled)
            log.info("exa parallel search complete: %d unique sources", unique_count)
            try:
                await save_cached_result(query_hash, thread_id, raw_results)
            except Exception as exc:
                log.error("search_cache write failed (result not persisted): %s", exc)

        cache = {**cache, topic: raw_results}

    context_block = build_context_block(state.get("context_dynamic"))
    research_data, input_tokens, output_tokens = await _synthesize_structured(
        raw_results, topic, keywords, context_block
    )

    source_count = len(research_data.zrodla)
    if source_count < _MIN_SOURCES:
        raise ValueError(
            f"Raport zawiera tylko {source_count} źródeł — wymagane minimum {_MIN_SOURCES}. "
            "Sprawdź połączenie z Exa MCP lub rozszerz zapytanie."
        )

    report = research_data.to_markdown(topic)

    existing_research_tokens = state.get("tokens_used_research", 0)
    existing_cost = state.get("estimated_cost_usd", 0.0)
    call_cost = estimate_cost_usd(settings.research_model, input_tokens, output_tokens)

    return {
        "research_report": report,
        "research_data": research_data.model_dump(),
        "search_cache": cache,
        "tokens_used_research": existing_research_tokens + input_tokens + output_tokens,
        "estimated_cost_usd": existing_cost + call_cost,
    }
