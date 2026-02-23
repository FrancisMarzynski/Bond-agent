# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-20)

**Core value:** Skrócenie procesu tworzenia gotowego do publikacji draftu z 1–2 dni do maksymalnie 4 godzin — przy zachowaniu stylu nieodróżnialnego od ludzkiego, z human-in-the-loop przed każdą publikacją.
**Current focus:** Phase 2 — Author Mode Backend

## Current Position

Phase: 2 of 4 (Author Mode Backend) — IN PROGRESS
Plan: 4 of 4 in current phase — PAUSED AT CHECKPOINT
Status: 02-04 Tasks 1+2 complete (checkpoint_2_node, save_metadata_node, harness.py); paused at Task 3 human-verify checkpoint — requires EXA_API_KEY and LLM API keys in .env for live end-to-end pipeline run
Last activity: 2026-02-23 — 02-04 Tasks 1+2 complete (all 7 nodes implemented, CLI harness ready)

Progress: [█████████░] 97%

## Performance Metrics

**Velocity:**
- Total plans completed: 6
- Average duration: 8 min
- Total execution time: 0.7 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-rag-corpus-onboarding | 3 | 30 min | 10 min |
| 02-author-mode-backend | 3 | 10 min | 3.3 min |

**Recent Trend:**
- Last 5 plans: 4 min, 10 min, 2 min, 3 min
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
- [02-02]: ChromaDB cosine DISTANCE conversion: similarity = 1.0 - distance; distance range 0-2 maps to similarity 1.0-(-1.0), threshold of 0.85 catches near-identical topics
- [02-02]: interrupt() payload contains existing_title, existing_date, similarity_score — frontend HITL surface shape is locked
- [02-02]: Text stripped from Exa session cache after report synthesis — slim_results keeps only title/url/summary to prevent SqliteSaver state bloat
- [02-03]: cp1_feedback concatenates edited_structure + optional note into single string; structure_node reads this as strong prior on re-run
- [02-03]: RAG exemplar injection as system prompt prefix (soft prompt technique) — provides strongest style transfer signal vs user message injection
- [02-03]: Low-corpus gate: corpus count checked before any LLM call; interrupt() with warning when < 10 articles; user confirms True/False to proceed or abort
- [02-03]: Writer auto-retry cp2_feedback only on attempt 0; subsequent retries fall back to fresh draft to avoid compounding revision errors
- [02-04]: checkpoint_2 soft cap is warning only — after 3 iterations interrupt payload gains "warning" field but does not hard-block; user can still approve or reject
- [02-04]: save_metadata_node generates published_date at call time (not from state) — ensures accurate SQLite and ChromaDB persistence timestamp
- [02-04]: Harness duplicate checkpoint returns bool True (not dict) — matches resume shape expected by duplicate_check_node
- [02-04]: Harness max_interrupts=20 safety limit prevents infinite HITL loop if graph state is misconfigured

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2]: LangGraph SqliteSaver import resolved — path is `langgraph.checkpoint.sqlite` with `langgraph-checkpoint-sqlite>=3.0.3`
- [Phase 2]: Exa API Polish-language query parameters pending live verification — EXA_API_KEY not set in .env
- [Phase 2]: astream_events version="v2" needs Context7 confirmation
- [Phase 2]: RAG corpus quality threshold (10 articles, 0.85 cosine similarity for duplicates) are recommendations, not validated values — budget time for tuning

## Session Continuity

Last session: 2026-02-23
Stopped at: 02-04 Tasks 1+2 complete; paused at Task 3 human-verify checkpoint (checkpoint:human-verify) — waiting for live end-to-end pipeline run with real API keys
Resume file: None
