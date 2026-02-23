import asyncio

from bond.config import settings
from bond.graph.state import AuthorState

EXA_MCP_URL = "https://mcp.exa.ai/mcp"


async def _call_exa_mcp(query: str, keywords: list[str], num_results: int = 8) -> str:
    """
    Call Exa web_search_exa tool via MCP HTTP.
    Returns the raw formatted results string.
    """
    from langchain_mcp_adapters.client import MultiServerMCPClient

    search_query = f"{query} {' '.join(keywords)}" if keywords else query

    async with MultiServerMCPClient(
        {"exa": {"url": EXA_MCP_URL, "transport": "streamable_http"}}
    ) as client:
        tools = client.get_tools()
        web_search = next((t for t in tools if t.name == "web_search_exa"), None)
        if web_search is None:
            available = [t.name for t in tools]
            raise RuntimeError(
                f"web_search_exa not found in Exa MCP. Available: {available}"
            )
        result = await web_search.ainvoke({"query": search_query, "numResults": num_results})
        return result if isinstance(result, str) else str(result)


def _format_research_report(raw_results: str, topic: str, keywords: list[str]) -> str:
    """
    Format raw MCP search results into a structured Markdown report.

    Structure (per locked user decision):
    1. Synthesis section: 2-3 paragraphs summarizing key themes across sources
    2. Numbered source list extracted from results
    """
    from langchain_anthropic import ChatAnthropic
    from langchain_openai import ChatOpenAI

    research_model = settings.research_model

    synthesis_prompt = f"""Jesteś redaktorem. Na podstawie poniższych wyników wyszukiwania napisz:

1. SYNTEZA (2-3 akapity): krótkie podsumowanie głównych tematów i trendów dotyczących "{topic}" (słowa kluczowe: {', '.join(keywords)}). Pisz po polsku. Nie cytuj źródeł bezpośrednio — syntezuj idee.

2. ŹRÓDŁA: wypisz ponumerowaną listę artykułów z wyników. Format każdej pozycji:
N. **Tytuł**
   URL
   2-3 zdania streszczenia

WYNIKI WYSZUKIWANIA:
{raw_results}

Odpowiedź zacznij od nagłówka "### Synteza", a listę źródeł od "### Źródła"."""

    if "claude" in research_model.lower():
        llm = ChatAnthropic(model=research_model, max_tokens=1200)
    else:
        llm = ChatOpenAI(model=research_model, max_tokens=1200)

    formatted = llm.invoke(synthesis_prompt).content.strip()

    return f"## Raport z badań: {topic}\n\n{formatted}"


async def researcher_node(state: AuthorState) -> dict:
    """
    Perform web research via Exa MCP. Checks session cache first (AUTH-10).

    Returns updated search_cache (raw MCP results string, keyed by topic)
    and formatted research_report (Markdown).
    """
    topic = state["topic"]
    keywords = state.get("keywords", [])
    cache = state.get("search_cache", {})

    if topic in cache:
        # Cache hit — no MCP call
        raw_results = cache[topic]
    else:
        # Cache miss — call Exa via MCP
        raw_results = await _call_exa_mcp(topic, keywords)
        cache = {**cache, topic: raw_results}

    report = _format_research_report(raw_results, topic, keywords)

    return {
        "research_report": report,
        "search_cache": cache,
    }
