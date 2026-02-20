# Technology Stack

**Project:** Bond — AI Blog Writing Agent
**Researched:** 2026-02-20
**Research mode:** Ecosystem
**Confidence note:** All external tooling (WebSearch, WebFetch, Context7, Bash) was unavailable during this session. Every version number below is drawn from training data (cutoff August 2025) and MUST be verified against PyPI / npm before use. Confidence levels reflect this constraint honestly.

---

## Recommended Stack

### Core Orchestration

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.12 | Runtime | 3.12 is the stable LTS target as of mid-2025; 3.11 is acceptable per project constraints but 3.12 has meaningful performance improvements. Do NOT use 3.13 (too new, ecosystem gaps). |
| LangGraph | 0.2.x | Agent orchestration, state machine, checkpointing | The canonical Python framework for multi-step LLM agents with persistent state. Provides StateGraph, human-in-the-loop interrupt points, and session memory — all required by Bond. v0.2 introduced significant stability improvements over v0.1. |
| LangChain Core | 0.3.x | LLM abstraction, prompt templates, chains | Required peer dependency of LangGraph. `langchain-core` (not full `langchain`) is the minimal install for LangGraph. Use `langchain-openai` / `langchain-anthropic` for model providers. |

**Confidence:** LOW — versions not verified against live PyPI. Verify: `pip index versions langgraph`

---

### LLM Providers

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| langchain-openai | latest | GPT-4o-mini (research/analysis), GPT-4o (final draft) | Best price/quality curve for cascaded model strategy. gpt-4o-mini is ~15x cheaper than gpt-4o — use for research nodes. Use gpt-4o for final draft only. |
| langchain-anthropic | latest | Claude Sonnet (alternative frontier for drafting) | Claude 3.5 Sonnet produces high-quality long-form prose. Useful as drafting alternative. |

**Cascade strategy:** Configure via env vars (`DRAFT_MODEL`, `RESEARCH_MODEL`). Never hardcode model names in node logic.

**Confidence:** MEDIUM — cascade pattern is well-established.

---

### Web Search

#### Recommendation: Exa (primary) with abstraction layer for Tavily fallback

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| exa-py | 1.x | Web search for research nodes | Neural/semantic search optimized for long-form content. Returns full article text. Superior for blog research vs Tavily. Exa MCP free tier is the project candidate. |

#### Exa vs Tavily Comparison

| Criterion | Exa | Tavily |
|-----------|-----|--------|
| Search paradigm | Neural/semantic | Keyword + relevance |
| Best for | Long-form content, blog research, style exemplar finding | Factual Q&A, news, quick lookups |
| Result quality for blog research | HIGH — returns full articles | MEDIUM — snippets only |
| LangGraph integration | Via exa-py SDK; wrap as Tool | Native TavilySearchResults in LangChain |
| Free tier | Yes — Exa MCP (verify current limits) | Limited, paid beyond threshold |
| Full content retrieval | Yes (`text=True`) | No — snippets only |
| Polish-language content | MEDIUM — verify with actual queries | MEDIUM — similar |

**Verdict: Use Exa.** For a blog writing agent that needs full article content for style analysis and research synthesis, Exa's neural search and full-content retrieval is architecturally superior. Tavily is optimized for factual Q&A, not content research. Implement via a `SearchProvider` protocol so the layer is swappable without touching node logic.

```python
from abc import ABC, abstractmethod

class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, num_results: int = 5) -> list[dict]: ...

class ExaSearchProvider(SearchProvider):
    def __init__(self):
        from exa_py import Exa
        self.client = Exa(api_key=os.environ["EXA_API_KEY"])

    def search(self, query: str, num_results: int = 5) -> list[dict]:
        results = self.client.search_and_contents(
            query, num_results=num_results, text=True
        )
        return [{"url": r.url, "title": r.title, "content": r.text}
                for r in results.results]
```

**Confidence:** MEDIUM — Exa vs Tavily comparison based on documented capabilities. Free tier limits need current verification.

---

### Vector Database (RAG)

#### Recommendation: ChromaDB (local, MVP) → Qdrant (if scaling needed)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| chromadb | 0.5.x | Local vector store for style examples | Zero-ops, file-based persistence. Perfect for MVP with small corpus (hundreds of style fragments). |
| langchain-chroma | latest | LangChain retriever integration | Provides Chroma vectorstore compatible with LangChain retriever interface. |
| sentence-transformers | 3.x | Local embeddings | `paraphrase-multilingual-MiniLM-L12-v2` for Polish content. Free, no API cost for corpus indexing. |

**ChromaDB vs Pinecone:**

| Criterion | ChromaDB | Pinecone |
|-----------|----------|---------|
| Setup | Zero — local file | Cloud account, API key, index setup |
| Cost | Free | ~$70/month minimum |
| Scale | < 1M vectors | Billions |
| Bond corpus size | ~500-5000 fragments | Same |
| Verdict | **Use for MVP** | Overkill |

**Why not Pinecone:** Bond's corpus is small. ChromaDB handles it with zero ops. Migrate only if corpus exceeds 100K vectors or multi-user deployment is needed.

**Embedding model note:** Use `paraphrase-multilingual-MiniLM-L12-v2` (not English-only `all-MiniLM-L6-v2`) because blog content is in Polish. If quality is insufficient, switch to `text-embedding-3-small` (OpenAI API). Configure via env var `EMBEDDING_MODEL`.

**Confidence:** MEDIUM — ChromaDB version not verified. NOTE: ChromaDB 0.4→0.5 had a breaking API change; verify stable version before pinning.

---

### YouTube Transcript Extraction

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| youtube-transcript-api | 0.6.x | Fetch YouTube captions | Standard Python library. No auth needed for public videos. Supports auto-generated + manual captions. |

```python
from youtube_transcript_api import YouTubeTranscriptApi

def get_transcript(video_url: str, languages: list[str] = ["pl", "en"]) -> str:
    video_id = extract_video_id(video_url)
    transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
    return " ".join([entry["text"] for entry in transcript])
```

**Risk:** This library breaks when YouTube changes its internal API. Check GitHub issues before pinning. Scope matches PROJECT.md: captions only, no audio processing.

**Confidence:** LOW — version not verified. Check: `pip index versions youtube-transcript-api`

---

### Frontend

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Next.js | 14.x / 15.x | React framework | App Router provides streaming SSE support. SSR improves initial load for non-technical users. |
| React | 18.x | UI library | React 18 Suspense + streaming pairs well with LLM token streaming. |
| TypeScript | 5.x | Type safety | Non-negotiable for maintainable frontend. |
| Tailwind CSS | 3.x | Styling | Fastest path to clean chat UI. No component library needed — keep it simple for non-technical audience. |

**Backend integration pattern: FastAPI + SSE**

```
Next.js App Router (client)
    ↓ fetch() with ReadableStream
FastAPI (Python, async)
    ↓ EventSourceResponse (sse-starlette)
LangGraph (async generator, .astream())
```

Do NOT use LangGraph Server / LangGraph Cloud for MVP. Run FastAPI directly.

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| fastapi | 0.115.x | HTTP API + streaming | Async-native, streaming-friendly. |
| uvicorn | 0.30.x | ASGI server | Standard for FastAPI. |
| sse-starlette | 2.x | Server-Sent Events | `EventSourceResponse` for streaming tokens to browser. |
| pydantic | 2.x | Validation | LangGraph uses Pydantic v2 internally; match versions. |

**Confidence:** MEDIUM — FastAPI/SSE pattern is the established approach. Next.js 14 vs 15 differences are significant; verify App Router streaming behavior in target version.

---

### Markdown (Frontend)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| react-markdown | 9.x | Render LLM output | Standard. Supports GFM. NOTE: v9 is ESM-only — ensure Next.js config handles this. |
| @uiw/react-md-editor | 3.x | Draft editor | Split preview + edit for the approval workflow. Lightweight. |
| remark-gfm | 4.x | GFM plugin | Required for tables, strikethrough in react-markdown. |

**Confidence:** LOW — versions not verified against npm. Check: `npm info react-markdown version`

---

### Session State & Metadata Log

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| LangGraph SqliteSaver | built-in | Session checkpointing | Persists graph state across server restarts. Use instead of MemorySaver for durability. |
| SQLite (stdlib) | 3.x | Metadata Log | Zero-ops. Stores: topic, publish_date, slug, word_count, mode. Enables duplicate topic detection (KPI3). |

**Why not Redis:** Single-user MVP. Redis is correct for horizontal scale. `SqliteSaver` is the right call for single-instance deployment.

**NOTE:** LangGraph's checkpointer API changed between 0.1 and 0.2. Verify `SqliteSaver` import path against current docs before using.

**Confidence:** MEDIUM — pattern is correct; import paths need verification.

---

### Development Tooling

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| uv | latest | Python package management | Replaces pip/venv/poetry. 10-100x faster. The 2025 standard. |
| pytest | 8.x | Testing | Standard. |
| pytest-asyncio | 0.23.x | Async test support | Required for async LangGraph node tests. |
| python-dotenv | 1.x | Env var management | Standard for local dev. |
| ruff | 0.4.x | Lint + format | Replaces black + flake8. One tool, 100x faster. |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Orchestration | LangGraph | CrewAI, AutoGen | LangGraph has explicit state machine — required for Author/Shadow mode switching and human-in-the-loop checkpoints. CrewAI hides state. |
| Vector DB | ChromaDB | Pinecone, Weaviate, Qdrant | Small corpus; Pinecone is ops-heavy; Qdrant is migration target if needed. |
| Web Search | Exa | Tavily, Serper, Google CSE | Exa returns full article text. Tavily returns snippets. Full content is required for blog research and style mimicry. |
| Embeddings | sentence-transformers (local) | OpenAI text-embedding-3-small | Local avoids per-call cost for fixed corpus indexing. Swap if quality gap. |
| Frontend | Next.js App Router | Vite + React SPA, Remix | Next.js streaming support best-in-class for LLM UIs. |
| API server | FastAPI | Flask, Django, LangGraph Server | Async-native, streaming-friendly. LangGraph Server adds lock-in without MVP benefit. |
| Session storage | SqliteSaver | Redis | Redis for multi-user scale. Single-user MVP doesn't need it. |
| Python | 3.12 | 3.11 (project minimum) | 3.12 has 10-15% perf improvement. 3.11 acceptable if environment requires it. |

---

## Installation

```bash
# Python environment (use uv)
uv init bond-agent
uv add langgraph langchain-core langchain-openai langchain-anthropic
uv add langchain-chroma chromadb sentence-transformers
uv add exa-py fastapi uvicorn sse-starlette pydantic
uv add youtube-transcript-api python-dotenv

# Dev dependencies
uv add --dev pytest pytest-asyncio ruff

# Frontend (in /frontend directory)
npx create-next-app@latest frontend --typescript --tailwind --app
cd frontend && npm install react-markdown @uiw/react-md-editor remark-gfm
```

---

## Version Verification Checklist

CRITICAL: Verify all versions before pinning — this research was compiled from training data (cutoff August 2025) without live internet access.

| Package | Verify Command | Key Risk |
|---------|---------------|---------|
| langgraph | `pip index versions langgraph` | 0.1→0.2 had breaking API changes |
| chromadb | `pip index versions chromadb` | 0.4→0.5 breaking API change |
| youtube-transcript-api | `pip index versions youtube-transcript-api` | Breaks when YouTube changes internals |
| exa-py | `pip index versions exa-py` | Free tier limits may have changed |
| react-markdown | `npm info react-markdown version` | v9 is ESM-only — Next.js config needed |
| next | `npm info next version` | 14 vs 15 App Router SSE differences |

---

## Sources

- Project context: `.planning/PROJECT.md`
- Training data (cutoff August 2025): LangGraph 0.2 docs, Exa vs Tavily community discussions, ChromaDB migration notes, FastAPI streaming patterns
- **All versions require live verification — no external sources were accessible during this session**
- Overall confidence: LOW on specific versions, MEDIUM on architectural patterns and tool selection rationale
