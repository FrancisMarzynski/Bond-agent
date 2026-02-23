import time

from exa_py import Exa

from bond.config import settings
from bond.graph.state import AuthorState


def _call_exa_with_retry(exa: Exa, query: str, keywords: list[str], max_retries: int = 3) -> list[dict]:
    """Call Exa search_and_contents with exponential backoff on rate limit errors."""
    for attempt in range(max_retries):
        try:
            response = exa.search_and_contents(
                query=f"{query} {' '.join(keywords)}",
                num_results=8,
                type="auto",                          # neural + keyword blend
                text={"max_characters": 2000},        # for synthesis; stripped from cache after
                summary={"query": query},             # abstractive summary per result
            )
            return [
                {
                    "title": r.title or "Brak tytułu",
                    "url": r.url or "",
                    "summary": r.summary or "",
                    "text": r.text or "",             # used for synthesis; stripped from cache after
                }
                for r in response.results
                if r.url  # filter results with no URL
            ]
        except Exception as e:
            err_str = str(e).lower()
            if "rate" in err_str or "429" in err_str:
                wait = 2 ** attempt
                print(f"Exa rate limit hit, waiting {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            raise  # non-rate-limit errors propagate immediately
    raise RuntimeError(f"Exa API rate limit exceeded after {max_retries} retries")


def _format_research_report(results: list[dict], topic: str, keywords: list[str]) -> str:
    """
    Format results into Markdown report.

    Structure (per locked user decision):
    1. Synthesis section: 2-3 paragraphs summarizing key themes across sources
    2. Numbered source list: Title / URL / 2-3 sentence summary per source
    """
    from langchain_anthropic import ChatAnthropic
    from langchain_openai import ChatOpenAI

    research_model = settings.research_model

    # Build context for synthesis from article texts
    source_texts = "\n\n".join(
        f"### {r['title']}\nURL: {r['url']}\n{r['text'][:1000]}"
        for r in results
        if r.get("text")
    )

    synthesis_prompt = f"""Jesteś redaktorem. Na podstawie poniższych artykułów napisz krótką syntezę (2-3 akapity)
głównych tematów i trendów dotyczących: "{topic}" (słowa kluczowe: {', '.join(keywords)}).
Pisz po polsku. Nie cytuj źródeł bezpośrednio — syntezuj idee.

ARTYKUŁY:
{source_texts}

SYNTEZA:"""

    # Select LLM based on RESEARCH_MODEL env var
    if "claude" in research_model.lower() or "anthropic" in research_model.lower():
        llm = ChatAnthropic(model=research_model, max_tokens=600)
    else:
        llm = ChatOpenAI(model=research_model, max_tokens=600)

    synthesis = llm.invoke(synthesis_prompt).content.strip()

    # Build numbered source list
    source_lines = []
    for i, r in enumerate(results, 1):
        summary = r.get("summary") or r.get("text", "")[:300]
        source_lines.append(f"{i}. **{r['title']}**  \n   {r['url']}  \n   {summary}\n")

    sources_section = "\n".join(source_lines)

    return f"""## Raport z badań: {topic}

### Synteza

{synthesis}

---

### Źródła

{sources_section}"""


def researcher_node(state: AuthorState) -> dict:
    """
    Perform web research via Exa. Checks session cache first (AUTH-10).

    Returns updated search_cache (with text stripped to save state space)
    and formatted research_report (Markdown).
    """
    topic = state["topic"]
    keywords = state.get("keywords", [])
    cache = state.get("search_cache", {})

    if topic in cache:
        # Cache hit — no Exa API call
        raw_results = cache[topic]
    else:
        # Cache miss — call Exa
        exa = Exa(api_key=settings.exa_api_key)
        raw_results = _call_exa_with_retry(exa, topic, keywords)

    # Format report (uses text field for synthesis)
    report = _format_research_report(raw_results, topic, keywords)

    # Strip text from cache after report generation to avoid state bloat (Pitfall 4)
    slim_results = [
        {"title": r["title"], "url": r["url"], "summary": r.get("summary", "")}
        for r in raw_results
    ]
    cache[topic] = slim_results

    return {
        "research_report": report,
        "search_cache": cache,
    }
