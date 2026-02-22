# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-20)

**Core value:** Skrócenie procesu tworzenia gotowego do publikacji draftu z 1–2 dni do maksymalnie 4 godzin — przy zachowaniu stylu nieodróżnialnego od ludzkiego, z human-in-the-loop przed każdą publikacją.
**Current focus:** Phase 2 — Author Mode Backend

## Current Position

Phase: 1 of 4 (RAG Corpus Onboarding) — COMPLETE
Plan: 3 of 3 in current phase — COMPLETE
Status: Phase 1 complete — ready for Phase 2
Last activity: 2026-02-22 — 01-03 complete (corpus status + smoke-test endpoints, human verification approved)

Progress: [███████░░░] 75%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: 10 min
- Total execution time: 0.5 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-rag-corpus-onboarding | 3 | 30 min | 10 min |

**Recent Trend:**
- Last 5 plans: 16 min, 4 min, 10 min
- Trend: Consistent ~10 min per plan

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Init]: Single LangGraph StateGraph with dual-branch routing (Author + Shadow); shared RAG retriever and save_metadata nodes
- [Init]: SqliteSaver from day one (never MemorySaver) — required for HITL resume across page refreshes
- [Init]: ChromaDB + paraphrase-multilingual-MiniLM-L12-v2 for Polish-language embeddings
- [Init]: Exa (not Tavily) for web research — returns full article text, not snippets
- [Init]: Author mode backend proved in Python before streaming frontend is added
- [01-01]: Singleton pattern for ChromaDB PersistentClient to avoid re-initializing 420MB embedding model
- [01-01]: SQLite for article log (not ChromaDB metadata) for efficient article-level counting
- [01-01]: 1875 chars chunk size (~500 tokens for Polish text) with 10% overlap
- [01-02]: Pydantic models for URL/Drive requests added to bond/models.py (not inline in router) for reuse
- [01-02]: Drive auth failure caught at service build time and returned as warnings — /ingest/drive never returns 500
- [01-02]: sitemap_search fallback to [url] list for single-post mode when no sitemap found
- [01-03]: Two-pass retrieval (own-first, external fills remainder) — author style always prioritised in RAG context
- [01-03]: ChromaDB filtered query exception caught broadly — no clean way to pre-check filtered collection size
- [01-03]: CorpusStatus and SmokeTestResult Pydantic models inline in corpus.py (endpoint-specific, not shared)

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2]: LangGraph SqliteSaver import path changed between 0.1 and 0.2 — verify with Context7 before writing graph skeleton code
- [Phase 2]: Exa API Polish-language query parameters need live verification before Researcher node implementation
- [Phase 2]: astream_events version="v2" needs Context7 confirmation
- [Phase 2]: RAG corpus quality threshold (10 articles, 0.85 cosine similarity for duplicates) are recommendations, not validated values — budget time for tuning

## Session Continuity

Last session: 2026-02-22
Stopped at: Phase 1 complete — all 3 plans done, ready to begin Phase 2
Resume file: None
