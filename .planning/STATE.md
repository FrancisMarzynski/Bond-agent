# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-20)

**Core value:** Skrócenie procesu tworzenia gotowego do publikacji draftu z 1–2 dni do maksymalnie 4 godzin — przy zachowaniu stylu nieodróżnialnego od ludzkiego, z human-in-the-loop przed każdą publikacją.
**Current focus:** Phase 2 — Author Mode Backend

## Current Position

Phase: 2 of 4 (Author Mode Backend) — IN PROGRESS
Plan: 1 of 4 in current phase — COMPLETE
Status: 02-01 complete — graph infrastructure bootstrapped, ready for Plan 02
Last activity: 2026-02-23 — 02-01 complete (AuthorState, graph wiring with SqliteSaver, Metadata Log module)

Progress: [████████░░] 80%

## Performance Metrics

**Velocity:**
- Total plans completed: 4
- Average duration: 8 min
- Total execution time: 0.6 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-rag-corpus-onboarding | 3 | 30 min | 10 min |
| 02-author-mode-backend | 1 | 2 min | 2 min |

**Recent Trend:**
- Last 5 plans: 16 min, 4 min, 10 min, 2 min
- Trend: Consistent, fast for infrastructure plans

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
- [02-01]: Stub node replacement via register_node() dict pattern — graph wiring finalized in Plan 01; Plans 02-04 only replace stub bodies without touching edge logic
- [02-01]: Two separate SQLite files (bond_checkpoints.db for LangGraph SqliteSaver, bond_metadata.db for article metadata_log) to avoid LangGraph internal schema conflicts
- [02-01]: Schema-on-connect pattern (_get_conn() runs CREATE TABLE IF NOT EXISTS on every open) — zero-config migration for simple schema
- [02-01]: check_same_thread=False for both SQLite connections — required for LangGraph async execution across thread boundaries

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2]: LangGraph SqliteSaver import resolved — path is `langgraph.checkpoint.sqlite` with `langgraph-checkpoint-sqlite>=3.0.3`
- [Phase 2]: Exa API Polish-language query parameters need live verification before Researcher node implementation
- [Phase 2]: astream_events version="v2" needs Context7 confirmation
- [Phase 2]: RAG corpus quality threshold (10 articles, 0.85 cosine similarity for duplicates) are recommendations, not validated values — budget time for tuning

## Session Continuity

Last session: 2026-02-23
Stopped at: 02-01 complete — graph infrastructure bootstrapped, beginning 02-02
Resume file: None
