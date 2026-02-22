# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-20)

**Core value:** Skrócenie procesu tworzenia gotowego do publikacji draftu z 1–2 dni do maksymalnie 4 godzin — przy zachowaniu stylu nieodróżnialnego od ludzkiego, z human-in-the-loop przed każdą publikacją.
**Current focus:** Phase 1 — RAG Corpus Onboarding

## Current Position

Phase: 1 of 4 (RAG Corpus Onboarding)
Plan: 3 of 3 in current phase (at checkpoint — awaiting human verify)
Status: In progress — paused at human-verify checkpoint
Last activity: 2026-02-22 — 01-03 Task 1 complete (status + smoke-test endpoints), awaiting checkpoint approval

Progress: [█████░░░░░] 60%

## Performance Metrics

**Velocity:**
- Total plans completed: 2
- Average duration: 10 min
- Total execution time: 0.33 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-rag-corpus-onboarding | 2 | 20 min | 10 min |

**Recent Trend:**
- Last 5 plans: 16 min, 4 min
- Trend: Fast execution on task 2 (code already partially in place)

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

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1]: LangGraph SqliteSaver import path changed between 0.1 and 0.2 — verify with Context7 before writing graph skeleton code
- [Phase 2]: Exa API Polish-language query parameters need live verification before Researcher node implementation
- [Phase 2]: astream_events version="v2" needs Context7 confirmation
- [Phase 1/2]: RAG corpus quality threshold (10 articles, 0.85 cosine similarity for duplicates) are recommendations, not validated values — budget time for tuning

## Session Continuity

Last session: 2026-02-22
Stopped at: 01-03 Task 1 complete — paused at human-verify checkpoint (corpus status + smoke-test endpoints)
Resume file: None
