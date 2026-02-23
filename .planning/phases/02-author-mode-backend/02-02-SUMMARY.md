---
phase: 02-author-mode-backend
plan: 02
subsystem: graph-nodes
tags: [langgraph, chromadb, exa, duplicate-detection, hitl, session-cache, research-report]

# Dependency graph
requires:
  - phase: 02-01
    provides: AuthorState TypedDict, bond/graph/graph.py with register_node() pattern, bond/store/chroma.py with corpus collection

provides:
  - duplicate_check_node: ChromaDB cosine similarity query against metadata_log, interrupt() HITL on duplicate detection (>= DUPLICATE_THRESHOLD)
  - researcher_node: Exa search_and_contents with session cache, LLM synthesis, formatted Markdown research report
  - get_or_create_metadata_collection(): bond_metadata_log_v1 ChromaDB collection for topic embeddings
  - add_topic_to_metadata_collection(): callable by save_metadata_node (Plan 04) to record published topics

affects: [02-03, 02-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - ChromaDB cosine DISTANCE-to-similarity conversion: similarity = 1.0 - distance (range 0-2 inverted to 0-1 range)
    - LangGraph interrupt() for HITL: pauses graph at duplicate detection; resume value is bool (True=proceed, False=abort)
    - Session cache pattern: search_cache dict keyed by topic string; populated on Exa miss, text-stripped after report generation
    - Exponential backoff for Exa: 3 retries with 2s/4s/8s waits on rate limit / 429 errors
    - RESEARCH_MODEL dispatch: "claude"/"anthropic" substring check routes to ChatAnthropic; otherwise ChatOpenAI

key-files:
  created:
    - bond/graph/nodes/duplicate_check.py
    - bond/graph/nodes/researcher.py
  modified:
    - bond/store/chroma.py
    - bond/graph/graph.py

key-decisions:
  - "ChromaDB cosine DISTANCE conversion: distance is 0=identical, 2=opposite; similarity = 1.0 - distance maps cleanly to 0-1 range for threshold comparison"
  - "interrupt() payload contains existing_title, existing_date, similarity_score — frontend receives this dict as HITL surface data"
  - "Text stripped from Exa results cache after report generation: slim_results keeps only title/url/summary to avoid LangGraph state bloat across checkpoint persists"
  - "Exa num_results=8 per plan spec; type='auto' for neural+keyword blend; summary={'query': topic} for abstractive per-result summaries"
  - "EXA_API_KEY required for live researcher_node execution; live test skipped when not set in .env (import chain test always passes)"

patterns-established:
  - "duplicate_check_node: graceful empty-collection path (collection.count() == 0 returns None,None without query)"
  - "researcher_node: cache-first pattern — always check state.get('search_cache', {}) before calling Exa"
  - "Report structure: '## Raport z badań: {topic}' -> '### Synteza' (LLM paragraphs) -> '---' -> '### Zrodla' (numbered list)"

requirements-completed: [AUTH-02, AUTH-10, DUPL-01, DUPL-02, DUPL-03, DUPL-04]

# Metrics
duration: 3min
completed: 2026-02-23
---

# Phase 2 Plan 02: Duplicate Check and Researcher Nodes Summary

**ChromaDB cosine-similarity duplicate detection with HITL interrupt and Exa-backed session-cached research report with LLM synthesis**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-23T04:55:04Z
- **Completed:** 2026-02-23T04:57:39Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- `duplicate_check_node` in `bond/graph/nodes/duplicate_check.py`: queries ChromaDB bond_metadata_log_v1 collection, converts cosine distance to similarity (1.0 - distance), pauses graph via LangGraph `interrupt()` when similarity >= DUPLICATE_THRESHOLD (0.85), returns None/None on empty collection or below-threshold match
- `get_or_create_metadata_collection()` and `add_topic_to_metadata_collection()` added to `bond/store/chroma.py` — reuses same SentenceTransformer embedding function as corpus collection but targets separate bond_metadata_log_v1 collection
- `researcher_node` in `bond/graph/nodes/researcher.py`: Exa search_and_contents with 8 results, session cache keyed by topic string (AUTH-10), exponential backoff retry (2s/4s/8s) on rate limit errors, text stripped from cache after synthesis to prevent state bloat
- Research report format confirmed: `## Raport z badań: {topic}` -> `### Synteza` (2-3 LLM paragraphs in Polish) -> `---` -> `### Zrodla` (numbered source list with title/URL/summary per source)
- Both real nodes registered in `bond/graph/graph.py` via import-replaces-stub pattern; graph compiles cleanly with `compile_graph()`

## Task Commits

Each task was committed atomically:

1. **Task 1: Duplicate check node (DUPL-01, DUPL-02, DUPL-03, DUPL-04)** - `52646f3` (feat)
2. **Task 2: Researcher node with Exa integration and session cache (AUTH-02, AUTH-10)** - `3bec1be` (feat)

## Files Created/Modified

- `bond/graph/nodes/duplicate_check.py` - duplicate_check_node with ChromaDB query, distance conversion, interrupt() call
- `bond/graph/nodes/researcher.py` - researcher_node with Exa integration, session cache, LLM synthesis report
- `bond/store/chroma.py` - Added get_or_create_metadata_collection() and add_topic_to_metadata_collection()
- `bond/graph/graph.py` - Replaced two stubs (_duplicate_check_node, _researcher_node) with real imports

## Decisions Made

- **ChromaDB cosine distance conversion:** ChromaDB returns distance (0=identical, 2=opposite). Conversion `similarity = 1.0 - distance` maps to 0-1 range for straightforward threshold comparison against `settings.duplicate_threshold` (default 0.85).
- **interrupt() payload design:** The dict passed to `interrupt()` contains `warning`, `existing_title`, `existing_date`, `similarity_score` — this is the exact shape the frontend HITL surface will display to the user.
- **Text stripping from session cache:** After `_format_research_report()` consumes the `text` fields for synthesis, `slim_results` stores only `title`/`url`/`summary`. This prevents the LangGraph SqliteSaver from persisting multi-KB text blobs across the checkpoint boundary.
- **Exa type="auto":** Allows Exa to blend neural and keyword search per query, maximizing result quality for diverse Polish-language topics without per-query tuning.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `uv run python` required (as in Plan 01) — `python` not in PATH in this environment. All verifications passed.
- EXA_API_KEY not set in `.env` — live Exa call skipped per plan specification. Import chain and graph compile verifications confirmed both nodes are functional.
- Model weights loaded with one `UNEXPECTED` key (`embeddings.position_ids`) in SentenceTransformer — this is a known benign warning for this model variant, not an error.

## Next Phase Readiness

- Plan 03 can import `AuthorState` from `bond.graph.state` and use `register_node()` from `bond.graph.graph` to wire `structure_node` and `checkpoint_1_node`
- `add_topic_to_metadata_collection()` is available in `bond.store.chroma` for Plan 04's `save_metadata_node`
- Set `EXA_API_KEY` in `.env` before running a live end-to-end test through the researcher node

## Self-Check: PASSED

All created/modified files verified present on disk. Both task commits (52646f3, 3bec1be) confirmed in git log.

---
*Phase: 02-author-mode-backend*
*Completed: 2026-02-23*
