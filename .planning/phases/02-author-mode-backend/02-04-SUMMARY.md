---
phase: 02-author-mode-backend
plan: 04
subsystem: graph-nodes
tags: [langgraph, hitl, interrupt, sqlite, chromadb, cli, harness, save-metadata]

# Dependency graph
requires:
  - phase: 02-03
    provides: structure_node, checkpoint_1_node, writer_node, compile_graph() pattern, bond/store/chroma.py (add_topic_to_metadata_collection), bond/db/metadata_log.py (save_article_metadata)

provides:
  - checkpoint_2_node: single interrupt() pausing graph for human review of draft; soft-cap warning at >= 3 iterations; targeted section feedback in cp2_feedback for writer_node
  - save_metadata_node: dual-write to SQLite metadata_log (bond_metadata.db) and ChromaDB bond_metadata_log_v1; closes DUPL-01 duplicate detection loop
  - bond/harness.py: CLI test harness driving complete Author mode pipeline through both HITL checkpoints in auto-approve or interactive mode

affects: [03-frontend, phase-3]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "checkpoint_2 soft cap: cp2_iterations >= SOFT_CAP_ITERATIONS adds warning to interrupt payload but does NOT block — user can still reject or approve at any iteration count"
    - "save_metadata dual-write: SQLite for relational article log + ChromaDB for topic embedding; both writes in single node call; DUPL-01 loop completed by adding embedding to bond_metadata_log_v1"
    - "Harness interrupt loop: graph.invoke() result inspected for __interrupt__ key; loop continues with Command(resume=...) until no interrupt or safety limit (20) reached"
    - "Harness resume mode: Command(resume={'approved': True}) passed to graph.invoke() without re-supplying initial state — SqliteSaver restores interrupted state automatically"

key-files:
  created:
    - bond/graph/nodes/checkpoint_2.py
    - bond/graph/nodes/save_metadata.py
    - bond/harness.py
  modified:
    - bond/graph/graph.py

key-decisions:
  - "checkpoint_2 soft cap is a warning only: after 3 iterations the interrupt payload includes a 'warning' field but the user can still reject or approve — no hard block, matching locked user decision"
  - "save_metadata_node uses published_date = datetime.now(timezone.utc).isoformat() at call time (not from state) — ensures accurate persistence timestamp even if state carries stale values"
  - "Harness _handle_interrupt returns plain True (not dict) for duplicate detection checkpoint — this matches the resume shape expected by duplicate_check_node (bool override)"
  - "graph.py stubs removed via direct module-level import — same pattern established in 02-03; no register_node() call needed; all 7 nodes now real implementations"
  - "Harness max_interrupts=20 safety limit: prevents infinite HITL loop if graph or state is misconfigured; chosen to be well above any realistic approval/rejection cycle"

patterns-established:
  - "checkpoint_2_node: single interrupt() call; approve response returns {cp2_approved: True} only; reject response returns {cp2_approved: False, cp2_feedback: str, cp2_iterations: n+1}"
  - "save_metadata_node: reads topic and thread_id from state; generates published_date at call time; calls save_article_metadata() then add_topic_to_metadata_collection(); returns {metadata_saved: True}"
  - "harness auto-approve: _handle_interrupt returns {approved: True} without user input when interactive=False; duplicate checkpoint returns True (bool) as override value"

requirements-completed: [AUTH-07, AUTH-08, AUTH-09]

# Metrics
duration: 8min
completed: 2026-02-23
---

# Phase 2 Plan 04: Checkpoint 2, Metadata Save, and CLI Test Harness Summary

**checkpoint_2 soft-cap HITL with targeted rejection feedback, dual-write metadata persistence (SQLite + ChromaDB DUPL-01 loop), and auto-approve CLI harness completing the full Author mode Python backend**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-23T05:06:29Z
- **Completed:** 2026-02-23T05:14:00Z
- **Tasks:** 2 auto tasks complete (Task 3 is human-verify checkpoint — paused for human verification)
- **Files modified:** 4

## Accomplishments

- `checkpoint_2_node` in `bond/graph/nodes/checkpoint_2.py`: single interrupt() exposing draft, draft_validated, cp2_iterations; soft-cap warning fires at >= 3 iterations but does not hard-block; targeted section feedback captured in cp2_feedback for writer_node revision
- `save_metadata_node` in `bond/graph/nodes/save_metadata.py`: dual-write pattern — SQLite metadata_log via `save_article_metadata()` and ChromaDB bond_metadata_log_v1 via `add_topic_to_metadata_collection()`; completes DUPL-01 loop so future duplicate_check_node queries find the saved topic embedding
- `bond/harness.py`: CLI test harness with `run_author_pipeline()` function; auto-approve mode for smoke testing; interactive mode for manual approval; resume mode for interrupted sessions; `python -m bond.harness --help` works; safety limit of 20 interrupt iterations
- `graph.py`: both stubs removed; all 7 nodes are now real implementations (`duplicate_check`, `researcher`, `structure`, `checkpoint_1`, `writer`, `checkpoint_2`, `save_metadata`)

## Task Commits

Each task was committed atomically:

1. **Task 1: Checkpoint 2 node and metadata save node (AUTH-07, AUTH-08, AUTH-09)** - `b909ccb` (feat)
2. **Task 2: CLI test harness for end-to-end pipeline validation (AUTH-01)** - `ddc2446` (feat)

## Files Created/Modified

- `bond/graph/nodes/checkpoint_2.py` - checkpoint_2_node with soft-cap warning at >= 3 iterations; targeted feedback in cp2_feedback
- `bond/graph/nodes/save_metadata.py` - save_metadata_node with dual SQLite + ChromaDB write; returns metadata_saved=True
- `bond/harness.py` - CLI test harness: run_author_pipeline(), _handle_interrupt(), auto-approve/interactive/resume modes, argparse CLI
- `bond/graph/graph.py` - Replaced two stubs (_checkpoint_2_node, _save_metadata_node) with real module-level imports; all 7 nodes registered

## Decisions Made

- **checkpoint_2 soft cap is warning only:** After SOFT_CAP_ITERATIONS (3) rejections the interrupt payload gains a "warning" field, but the user can still approve or reject. No hard block was implemented — this matches the locked user decision in the plan's must_haves.
- **published_date generated at call time:** `datetime.now(timezone.utc).isoformat()` called inside `save_metadata_node` rather than reading from state. Ensures the SQLite and ChromaDB records have the accurate persistence timestamp even if state carries older values.
- **Harness duplicate checkpoint returns bool True:** `_handle_interrupt()` returns `True` (not `{"approved": True}`) for the duplicate detection checkpoint — this matches the resume shape expected by `duplicate_check_node` which reads the interrupt response as a boolean override.
- **graph.py stub removal:** Same direct module-level import pattern from 02-03. No `register_node()` call needed — the `_node_registry` dict is initialized with real references at module load time.
- **Harness safety limit 20:** `max_interrupts=20` prevents an infinite HITL loop if the graph state is misconfigured or if a rejection loop runs unexpectedly; well above any realistic approval/rejection cycle for a single article.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `uv run python` required (same as Plans 02-03) — `python` not in PATH in this environment. All verifications passed with `uv run python`.
- ChromaDB embedding model (`paraphrase-multilingual-MiniLM-L12-v2`) weight-loading progress bars appear during first import in a session — this is expected output, not an error. The final line confirms success.

## Next Phase Readiness

- The complete Author mode Python backend is implemented: all 7 LangGraph nodes are real implementations with SqliteSaver persistence
- `python -m bond.harness` is ready for end-to-end live testing once EXA_API_KEY and LLM API keys are set in `.env`
- The DUPL-01 loop is closed: topics saved by save_metadata_node become the corpus queried by duplicate_check_node on future runs
- Task 3 (human-verify checkpoint) is pending: requires EXA_API_KEY and ANTHROPIC_API_KEY or OPENAI_API_KEY in `.env` to run a live end-to-end pipeline test

## Self-Check: PASSED

All created/modified files verified present on disk. Both task commits (b909ccb, ddc2446) confirmed in git log.

---
*Phase: 02-author-mode-backend*
*Completed: 2026-02-23*
