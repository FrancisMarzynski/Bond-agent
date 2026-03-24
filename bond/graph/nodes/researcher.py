import logging
import re

from langchain_anthropic import ChatAnthropic
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

from bond.config import settings
from bond.db.search_cache import compute_query_hash, get_cached_result, save_cached_result
from bond.graph.state import AuthorState
from bond.prompts.context import build_context_block

log = logging.getLogger(__name__)

EXA_MCP_URL = "https://mcp.exa.ai/mcp"
_MIN_SOURCES = 3

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


def _count_sources(report: str) -> int:
    """Count numbered source entries (lines starting with digit + dot) in the report."""
    return len(re.findall(r"^\d+\.", report, re.MULTILINE))


def _format_research_report(raw_results: str, topic: str, keywords: list[str], context_block: str = "") -> str:
    """
    Format raw MCP search results into a structured Markdown report.

    Structure (per locked user decision):
    1. Synthesis section: 2-3 paragraphs summarizing key themes across sources
    2. Numbered source list extracted from results
    """
    research_model = settings.research_model

    context_section = f"\n{context_block}\n" if context_block else ""
    synthesis_prompt = f"""Jesteś redaktorem. Na podstawie poniższych wyników wyszukiwania napisz:{context_section}

1. SYNTEZA (2-3 akapity): krótkie podsumowanie głównych tematów i trendów dotyczących "{topic}" (słowa kluczowe: {', '.join(keywords)}). Pisz po polsku. Nie cytuj źródeł bezpośrednio — syntezuj idee.

2. ŹRÓDŁA: wypisz ponumerowaną listę artykułów z wyników. Format każdej pozycji:
N. **Tytuł**
   URL
   2-3 zdania streszczenia

WYNIKI WYSZUKIWANIA:
{raw_results}

Odpowiedź zacznij od nagłówka "### Synteza", a listę źródeł od "### Źródła"."""

    if "claude" in research_model.lower():
        llm = ChatAnthropic(model=research_model, max_tokens=2500)
    else:
        llm = ChatOpenAI(model=research_model, max_tokens=2500)

    formatted = llm.invoke(synthesis_prompt).content.strip()

    return f"## Raport z badań: {topic}\n\n{formatted}"


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
        # Cache is "nice-to-have": any storage failure is logged and bypassed.
        db_result: str | None = None
        try:
            db_result = await get_cached_result(query_hash, thread_id)
        except Exception as exc:
            log.error("search_cache read failed, proceeding without cache: %s", exc)

        if db_result is not None:
            raw_results = db_result
        else:
            # Layer 3 — live Exa MCP call
            raw_results = await _call_exa_mcp(topic, keywords)
            try:
                await save_cached_result(query_hash, thread_id, raw_results)
            except Exception as exc:
                log.error("search_cache write failed (result not persisted): %s", exc)

        cache = {**cache, topic: raw_results}

    context_block = build_context_block(state.get("context_dynamic"))
    report = _format_research_report(raw_results, topic, keywords, context_block)

    source_count = _count_sources(report)
    if source_count < _MIN_SOURCES:
        raise ValueError(
            f"Raport zawiera tylko {source_count} źródeł — wymagane minimum {_MIN_SOURCES}. "
            "Sprawdź połączenie z Exa MCP lub rozszerz zapytanie."
        )

    return {
        "research_report": report,
        "search_cache": cache,
    }
