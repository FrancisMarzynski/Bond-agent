---
phase: 02-author-mode-backend
plan: 01
subsystem: api
tags: [langgraph, sqlite, sqlitesaver, pydantic-settings, typeddict, exa, langchain]

# Dependency graph
requires:
  - phase: 01-rag-corpus-onboarding
    provides: bond/config.py Settings base, bond package structure, data/ directory

provides:
  - AuthorState TypedDict with all 15 pipeline fields (topic, keywords, thread_id, duplicate_match, duplicate_override, search_cache, research_report, heading_structure, cp1_approved, cp1_feedback, cp1_iterations, draft, draft_validated, cp2_approved, cp2_feedback, cp2_iterations, metadata_saved)
  - bond/graph/graph.py with build_author_graph() and compile_graph(); all 7 nodes wired with conditional routing
  - NOTE: compile_graph() was later changed to an async context manager using AsyncSqliteSaver (required when researcher_node became async in 02-02). Phase 3 must use: `async with compile_graph() as graph:`
  - bond/db/metadata_log.py with create-table-on-connect, save_article_metadata(), get_recent_articles() CRUD against separate SQLite file
  - bond/config.py extended with 7 Phase 2 settings fields

affects: [02-02, 02-03, 02-04]

# Tech tracking
tech-stack:
  added:
    - langgraph>=0.2
    - langgraph-checkpoint-sqlite>=3.0.3
    - exa-py>=2.4.0
    - langchain-openai>=0.2
    - langchain-anthropic>=0.2
  patterns:
    - Stub node replacement pattern: all 7 nodes wired as stubs in graph.py; Plans 02-04 call register_node() to replace them without touching graph wiring
    - Separate SQLite files for checkpointing (bond_checkpoints.db) vs article metadata (bond_metadata.db) — avoids schema conflicts with LangGraph internal tables
    - Schema-on-connect: metadata_log.py runs schema.sql on every connection open, CREATE TABLE IF NOT EXISTS is idempotent

key-files:
  created:
    - bond/graph/__init__.py
    - bond/graph/state.py
    - bond/graph/nodes/__init__.py
    - bond/graph/graph.py
    - bond/db/__init__.py
    - bond/db/metadata_log.py
    - bond/db/schema.sql
  modified:
    - pyproject.toml
    - .env.example
    - bond/config.py

key-decisions:
  - "Stub node replacement via register_node() dict pattern: graph wiring is finalized in Plan 01; Plans 02-04 only replace stub bodies without touching edge logic"
  - "Two separate SQLite files (bond_checkpoints.db for LangGraph SqliteSaver, bond_metadata.db for article metadata_log) to avoid LangGraph internal schema conflicts"
  - "Schema-on-connect pattern in _get_conn(): CREATE TABLE IF NOT EXISTS executed on every connection, making migration zero-config"
  - "check_same_thread=False for both SQLite connections: required for LangGraph async execution across thread boundaries"

patterns-established:
  - "register_node(name, fn) pattern: Plans 02-04 import and call this to replace stubs — graph structure never changes after Plan 01"
  - "_route_after_* functions for conditional edges: routing logic isolated and stable, node implementations are independent"
  - "_get_conn() with schema bootstrap on every call: idempotent, no manual migration step needed"

requirements-completed: [AUTH-01, AUTH-11, DUPL-04]

# Metrics
duration: 2min
completed: 2026-02-23
---

# Phase 2 Plan 01: Graph Infrastructure Bootstrap Summary

**LangGraph StateGraph with 7 stub nodes, SqliteSaver checkpointer, AuthorState TypedDict, and SQLite Metadata Log module wired as the foundation for all Phase 2 plans**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-23T04:50:38Z
- **Completed:** 2026-02-23T04:52:32Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- AuthorState TypedDict with 15 fields covering the full author pipeline (input, duplicate detection, research, structure, both checkpoints, draft, and output) importable from bond.graph.state
- All 7 graph nodes wired in bond/graph/graph.py with conditional routing (duplicate_check -> researcher or END; checkpoint_1 -> writer or structure; checkpoint_2 -> save_metadata or writer); graph compiles against SqliteSaver with data/bond_checkpoints.db
- Metadata Log module (bond/db/metadata_log.py) against separate data/bond_metadata.db with schema-on-connect pattern; save_article_metadata() and get_recent_articles() verified working
- Phase 2 settings (checkpoint_db_path, metadata_db_path, exa_api_key, research_model, draft_model, min_word_count, duplicate_threshold) added to bond/config.py with correct defaults

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Phase 2 dependencies, env vars, and AuthorState TypedDict** - `7dfa6cd` (feat)
2. **Task 2: Graph wiring with stub nodes, SqliteSaver, and Metadata Log** - `91c3e11` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified
- `bond/graph/state.py` - AuthorState TypedDict with all 15 pipeline fields
- `bond/graph/graph.py` - build_author_graph() and compile_graph(); 7 stub nodes; 3 conditional routing functions; register_node() for stub replacement
- `bond/graph/__init__.py` - Package init
- `bond/graph/nodes/__init__.py` - Nodes subpackage init
- `bond/db/metadata_log.py` - SQLite CRUD: _get_conn() with schema-on-connect, save_article_metadata(), get_recent_articles()
- `bond/db/schema.sql` - metadata_log table schema with published_date index
- `bond/db/__init__.py` - Package init
- `bond/config.py` - Extended with 7 Phase 2 settings fields
- `pyproject.toml` - Added langgraph, langgraph-checkpoint-sqlite>=3.0.3, exa-py, langchain-openai, langchain-anthropic
- `.env.example` - Added Phase 2 env var block

## Decisions Made
- **Stub node replacement via register_node():** graph.py maintains a _node_registry dict; Plans 02-04 call register_node(name, fn) to swap stubs without re-wiring edges. This prevents any accidental edge modification in later plans.
- **Two separate SQLite files:** bond_checkpoints.db is exclusively for LangGraph SqliteSaver (which manages its own internal schema); bond_metadata.db holds the application-level metadata_log. Mixing them would cause schema conflicts with LangGraph's internal tables.
- **Schema-on-connect idempotency:** _get_conn() runs schema.sql with CREATE TABLE IF NOT EXISTS on every connection open. No migration tooling needed for this simple schema.
- **check_same_thread=False:** Both sqlite3.connect() calls use this flag — required because LangGraph executes nodes across thread boundaries in async contexts.

## Deviations from Plan

1. **compile_graph() API changed post-plan:** Initially implemented with sync `SqliteSaver` as written. Later in the phase, `researcher_node` was made async (Exa MCP requires async), which forced a switch to `AsyncSqliteSaver` and an async context manager pattern. The final signature is:
   ```python
   @asynccontextmanager
   async def compile_graph():
       async with AsyncSqliteSaver.from_conn_string(...) as checkpointer:
           yield builder.compile(checkpointer=checkpointer)
   ```
   **Phase 3 impact:** All graph usage must use `async with compile_graph() as graph:` — not `graph = compile_graph()`.

2. **exa-py replaced by langchain-mcp-adapters:** Plan specified `exa-py>=2.4.0` dep and `EXA_API_KEY` in settings. Replaced with `langchain-mcp-adapters` + Exa MCP server (no API key in code). `exa_api_key` field removed from `bond/config.py`.

## Issues Encountered
None — `python` command not in PATH in this environment; used `uv run python` for all verification commands. All verifications passed.

## User Setup Required
None - no external service configuration required at this stage (EXA_API_KEY placeholder added to .env.example but not required until Plan 02).

## Next Phase Readiness
- bond/graph/state.py, bond/graph/graph.py, and bond/db/metadata_log.py are ready to import — Plan 02 can begin immediately
- Plans 02-04 import AuthorState from bond.graph.state and call register_node() from bond.graph.graph
- data/bond_checkpoints.db and data/bond_metadata.db are created in the data/ directory (already .gitignored alongside other data files)
- EXA_API_KEY must be set before Plan 02 researcher node is live-tested

## Self-Check: PASSED

All created files verified present on disk. Both task commits (7dfa6cd, 91c3e11) confirmed in git log.

---
*Phase: 02-author-mode-backend*
*Completed: 2026-02-23*
