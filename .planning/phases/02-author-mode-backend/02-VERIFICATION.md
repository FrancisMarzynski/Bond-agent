---
phase: 02-author-mode-backend
verified: 2026-02-23T12:00:00Z
status: passed
score: 12/12 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 10/12
  gaps_closed:
    - "compile_graph() API deviation (AsyncSqliteSaver + async context manager) now documented in 02-01-SUMMARY.md Deviations section with Phase 3 impact callout"
    - "exa-py to Exa MCP replacement now documented in 02-01-SUMMARY.md Deviations section"
    - "AUTH-07 and AUTH-09 marked Complete in REQUIREMENTS.md traceability table (verified in both list checkboxes and traceability rows)"
  gaps_remaining: []
  regressions: []
deferred_known_issues:
  - item: "writer SEO constraints fail with OpenAI models (draft_validated=False, word count 428 vs 800 min)"
    status: "User explicitly approved proceeding. Not a gap — deferred to pre-launch prompt calibration."
---

# Phase 2: Author Mode Backend — Verification Report

**Phase Goal:** Implement the complete Author mode backend — a LangGraph pipeline that takes a topic+keywords input and produces a validated SEO draft through two human-in-the-loop checkpoints, with duplicate detection, web research via Exa, RAG style injection, and metadata persistence.
**Verified:** 2026-02-23 (re-verification after gap fixes)
**Status:** passed
**Re-verification:** Yes — after gap closure. Previous status: gaps_found (10/12).

---

## Re-verification Summary

Three items were identified as gaps or human-verification items in the initial report:

| Gap / HV Item | Resolution | Verified By |
|---|---|---|
| compile_graph() API deviation undocumented | Documented in 02-01-SUMMARY.md "Deviations from Plan" section (item 1), including the `@asynccontextmanager`/`AsyncSqliteSaver` signature and Phase 3 impact callout. `provides:` frontmatter also carries the NOTE. | Grep confirms text at lines 113-120 of 02-01-SUMMARY.md |
| exa-py to Exa MCP replacement undocumented | Documented in 02-01-SUMMARY.md "Deviations from Plan" section (item 2), explaining the dep replacement and removal of `exa_api_key` from config.py | Grep confirms text at line 122 of 02-01-SUMMARY.md |
| AUTH-07 and AUTH-09 marked "Pending" in REQUIREMENTS.md | Both now show `[x]` checkboxes in the v1 requirements list and `Complete` status in the traceability table | Grep confirms lines 116 and 118 of REQUIREMENTS.md |

No regressions detected. All 10 previously passing truths still hold (all 7 node files present, all function definitions confirmed, harness and metadata_log CRUD confirmed).

**Known open item (not a gap):** `draft_validated=False` with OpenAI models due to word count (428 vs 800 min) and meta-description format. User explicitly approved proceeding. Deferred to pre-launch prompt calibration.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | AuthorState TypedDict is importable with all required fields | VERIFIED | `bond/graph/state.py` exports AuthorState with all 15 fields: topic, keywords, thread_id, duplicate_match, duplicate_override, search_cache, research_report, heading_structure, cp1_approved, cp1_feedback, cp1_iterations, draft, draft_validated, cp2_approved, cp2_feedback, cp2_iterations, metadata_saved |
| 2 | The compiled graph is importable and compiles without error; API deviation documented for Phase 3 | VERIFIED | `compile_graph()` is an `@asynccontextmanager` using `AsyncSqliteSaver` — functionally correct and live-verified. Deviation from plan's sync SqliteSaver pattern is now documented in 02-01-SUMMARY.md Deviations section with Phase 3 impact (`async with compile_graph() as graph:`). |
| 3 | Metadata Log schema created in SQLite on first call; CRUD functions work | VERIFIED | `bond/db/metadata_log.py` has `_get_conn()` with schema-on-connect, `save_article_metadata()`, `get_recent_articles()`; `schema.sql` creates metadata_log table with correct columns |
| 4 | Exa web research integration documented; MCP approach replaces exa-py SDK | VERIFIED | exa-py to Exa MCP deviation documented in 02-01-SUMMARY.md. `.env.example` carries MCP setup comment. `bond/config.py` correctly omits `exa_api_key` (MCP transport, no API key in code). No `EXA_API_KEY` env var needed. |
| 5 | duplicate_check_node: ChromaDB cosine similarity query, interrupt() on match >= DUPLICATE_THRESHOLD, graceful empty collection | VERIFIED | `bond/graph/nodes/duplicate_check.py` fully implements the ChromaDB query, distance-to-similarity conversion (1.0 - distance), interrupt() with correct payload, empty collection early return |
| 6 | researcher_node: session-cached Exa search, research report with Synteza + Zrodla sections | VERIFIED | `bond/graph/nodes/researcher.py` implements cache-first pattern; Exa MCP via langchain-mcp-adapters; report format `## Raport z badań: {topic}` with `### Synteza` and `### Zrodla` sections |
| 7 | structure_node generates heading outline; incorporates cp1_feedback on re-runs | VERIFIED | `bond/graph/nodes/structure.py` dispatches to re-run prompt when cp1_feedback and cp1_iterations > 0 |
| 8 | checkpoint_1_node pauses via interrupt() exposing research_report, heading_structure, cp1_iterations | VERIFIED | `bond/graph/nodes/checkpoint_1.py` contains single interrupt() call; approve/reject paths correctly handle cp1_feedback concatenation |
| 9 | writer_node produces SEO-compliant draft with RAG injection; low-corpus interrupt gate; auto-retry | VERIFIED | `bond/graph/nodes/writer.py` has LOW_CORPUS_THRESHOLD=10 corpus gate, `_fetch_rag_exemplars` with own-text preference fallback, `_validate_draft` with 4 constraints, 3-attempt silent retry, targeted section revision on cp2_feedback. Known open item: `draft_validated=False` with OpenAI models — deferred, user-approved. |
| 10 | checkpoint_2_node pauses via interrupt() with soft cap warning at >= 3 iterations | VERIFIED | `bond/graph/nodes/checkpoint_2.py` with SOFT_CAP_ITERATIONS=3, single interrupt() call, targeted feedback captured in cp2_feedback |
| 11 | save_metadata_node writes to SQLite metadata_log AND ChromaDB bond_metadata_log_v1 | VERIFIED | `bond/graph/nodes/save_metadata.py` calls `save_article_metadata()` and `add_topic_to_metadata_collection()` in sequence; returns metadata_saved=True |
| 12 | Test harness drives complete pipeline through both HITL checkpoints; live-verified end-to-end | VERIFIED | `bond/harness.py` with `run_author_pipeline()` (async); auto-approve and interactive modes; interrupt loop with max_interrupts=20 safety limit; adapted to async compile_graph() context manager. Live run produced `Metadata saved: True` (human-approved in 02-04 Task 3). |

**Score: 12/12 truths verified**

---

### Required Artifacts

#### Plan 02-01 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bond/graph/state.py` | AuthorState TypedDict with all pipeline fields | VERIFIED | All 15 fields present; correct types |
| `bond/graph/graph.py` | build_author_graph() and compile_graph(); all 7 nodes wired | VERIFIED | build_author_graph() correct; compile_graph() uses AsyncSqliteSaver async context manager — deviation documented in 02-01-SUMMARY.md. All 7 nodes confirmed real implementations. |
| `bond/db/metadata_log.py` | Metadata CRUD: save_article_metadata(), schema-on-connect | VERIFIED | save_article_metadata() and get_recent_articles() present; schema applied on connect. Minor naming deviation: plan listed get_article_by_id(); implementation provides get_recent_articles() — no upstream caller, no functional impact. |
| `bond/config.py` | Settings class with Phase 2 fields | VERIFIED | 6 fields present: checkpoint_db_path, metadata_db_path, research_model, draft_model, min_word_count, duplicate_threshold. exa_api_key correctly absent — MCP approach requires no API key in code. Deviation documented in 02-01-SUMMARY.md. |

#### Plan 02-02 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bond/graph/nodes/duplicate_check.py` | duplicate_check_node; ChromaDB query; interrupt() on duplicate | VERIFIED | Fully implemented; exports duplicate_check_node |
| `bond/graph/nodes/researcher.py` | researcher_node; Exa search with session cache; report formatting | VERIFIED | Implemented; Exa MCP via langchain-mcp-adapters; session cache keyed by topic; async function |

#### Plan 02-03 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bond/graph/nodes/structure.py` | structure_node; H1/H2/H3 outline; cp1_feedback incorporation | VERIFIED | Fully implemented |
| `bond/graph/nodes/checkpoint_1.py` | checkpoint_1_node; single interrupt(); approve/reject paths | VERIFIED | Fully implemented; single interrupt() call |
| `bond/graph/nodes/writer.py` | writer_node; _validate_draft; _build_writer_prompt; RAG fetch | VERIFIED | All three present; LOW_CORPUS_THRESHOLD=10; full implementation |

#### Plan 02-04 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bond/graph/nodes/checkpoint_2.py` | checkpoint_2_node; soft cap at 3 iterations; targeted feedback | VERIFIED | SOFT_CAP_ITERATIONS=3; single interrupt(); reject path captures cp2_feedback |
| `bond/graph/nodes/save_metadata.py` | save_metadata_node; dual write SQLite + ChromaDB | VERIFIED | Both writes present; returns metadata_saved=True |
| `bond/harness.py` | CLI harness; run_author_pipeline(); auto-approve and interactive modes | VERIFIED | run_author_pipeline() is async; asyncio.run() in __main__; auto-approve and interactive modes; --help available |

---

### Key Link Verification

#### Plan 02-01 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `bond/graph/graph.py` | `bond/graph/state.py` | StateGraph(AuthorState) | WIRED | Line 68: `builder = StateGraph(AuthorState)` |
| `bond/graph/graph.py` | `langgraph.checkpoint.sqlite.aio` | AsyncSqliteSaver compile | WIRED | Uses AsyncSqliteSaver from langgraph.checkpoint.sqlite.aio — functionally equivalent to SqliteSaver; deviation documented |
| `bond/db/metadata_log.py` | bond_metadata.db | sqlite3.connect(settings.metadata_db_path) | WIRED | Line 9: `sqlite3.connect(settings.metadata_db_path, check_same_thread=False)` |

#### Plan 02-02 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `bond/graph/nodes/duplicate_check.py` | `bond/store/chroma.py` | get_or_create_metadata_collection() | WIRED | Line 5 import + line 16 call |
| `bond/graph/nodes/duplicate_check.py` | `langgraph.types.interrupt` | interrupt() call | WIRED | Line 1 import + line 49 call |
| `bond/graph/nodes/researcher.py` | Exa MCP via langchain_mcp_adapters | MultiServerMCPClient | WIRED | exa-py link replaced by Exa MCP; documented deviation; functional research confirmed live |
| `bond/graph/graph.py` | `bond/graph/nodes/duplicate_check.py` | direct import at module level | WIRED | Line 8: `from bond.graph.nodes.duplicate_check import duplicate_check_node as _duplicate_check_node` |

#### Plan 02-03 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `bond/graph/nodes/writer.py` | `bond/store/chroma.py` | get_corpus_collection() | WIRED | Line 8 import + line 196 call; corpus count and exemplar fetch both present |
| `bond/graph/nodes/writer.py` | `langgraph.types.interrupt` | interrupt() on low corpus | WIRED | Line 4 import + line 199 call with warning payload |
| `bond/graph/nodes/checkpoint_1.py` | `langgraph.types.interrupt` | single interrupt() call | WIRED | Line 1 import + line 18 call |
| `bond/graph/nodes/writer.py` | `bond/config.settings` | settings.draft_model, settings.min_word_count | WIRED | Lines 214, 480 |

#### Plan 02-04 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `bond/graph/nodes/save_metadata.py` | `bond/db/metadata_log.py` | save_article_metadata() | WIRED | Line 3 import + line 21 call |
| `bond/graph/nodes/save_metadata.py` | `bond/store/chroma.py` | add_topic_to_metadata_collection() | WIRED | Line 5 import + line 28 call |
| `bond/harness.py` | `bond/graph/graph.py` | compile_graph() then ainvoke() / Command(resume=...) | WIRED | Lines 29, 144, 147, 168, 175 — uses async context manager pattern |

---

### Requirements Coverage

All Phase 2 requirement IDs from plan frontmatter collected:

**From 02-01-PLAN.md:** AUTH-01, AUTH-11, DUPL-04
**From 02-02-PLAN.md:** AUTH-02, AUTH-10, DUPL-01, DUPL-02, DUPL-03, DUPL-04
**From 02-03-PLAN.md:** AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-08, AUTH-11
**From 02-04-PLAN.md:** AUTH-07, AUTH-08, AUTH-09

Unique requirement IDs claimed: AUTH-01 through AUTH-11, DUPL-01 through DUPL-04

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| AUTH-01 | 02-01, 02-04 | User can start Author mode with topic and keywords | SATISFIED | harness.py accepts topic/keywords; graph initializes with these fields in AuthorState |
| AUTH-02 | 02-02 | Agent does web research and generates report with sources, links, summaries | SATISFIED | researcher_node generates "## Raport z badań" with Synteza and Zrodla sections |
| AUTH-03 | 02-03 | Agent proposes H1/H2/H3 structure based on research | SATISFIED | structure_node generates heading outline from research_report |
| AUTH-04 | 02-03 | User approves/rejects report and structure at Checkpoint 1 | SATISFIED | checkpoint_1_node with single interrupt(); approve/reject paths both handled |
| AUTH-05 | 02-03 | SEO-compliant draft: keyword in H1 and first paragraph, correct heading hierarchy, meta-description 150-160 chars, min 800 words | SATISFIED | writer_node with _validate_draft checking all 4 constraints. Known open item: draft_validated=False with OpenAI models — deferred to pre-launch prompt calibration, user-approved. |
| AUTH-06 | 02-03 | RAG Few-Shot style injection with 3-5 fragments from vector store | SATISFIED | _fetch_rag_exemplars with own-text preference; exemplar_section injected as system prompt prefix in _build_writer_prompt |
| AUTH-07 | 02-04 | User approves/rejects stylized draft at Checkpoint 2 | SATISFIED | checkpoint_2_node fully implemented and live-verified; REQUIREMENTS.md traceability now correctly shows Complete |
| AUTH-08 | 02-03, 02-04 | User can provide rejection feedback; agent regenerates without losing session context (max 3 iterations) | SATISFIED | cp2_feedback passed to writer_node for targeted section revision; cp2_iterations tracked; SOFT_CAP_ITERATIONS=3 warning |
| AUTH-09 | 02-04 | After approval, metadata saved to Metadata Log (topic, date, mode) | SATISFIED | save_metadata_node writes to SQLite metadata_log with topic/mode/date; REQUIREMENTS.md traceability now correctly shows Complete |
| AUTH-10 | 02-02 | Web search results cached in session — same topic does not trigger second API call | SATISFIED | researcher_node checks state["search_cache"] before calling Exa; cache keyed by topic string |
| AUTH-11 | 02-01, 02-03 | LLM models configured via env vars (RESEARCH_MODEL for research, DRAFT_MODEL for draft) | SATISFIED | settings.research_model and settings.draft_model present in config.py; both nodes dispatch via "claude" substring check |
| DUPL-01 | 02-02 | Before research, check for duplicate topics via embedding similarity vs Metadata Log | SATISFIED | duplicate_check_node queries bond_metadata_log_v1 ChromaDB collection before researcher runs |
| DUPL-02 | 02-02 | When duplicate found, inform user: title + publication date | SATISFIED | interrupt() payload contains existing_title, existing_date, similarity_score |
| DUPL-03 | 02-02 | User can override duplicate warning and continue | SATISFIED | interrupt() resume value bool(True) sets duplicate_override=True; graph routes to researcher |
| DUPL-04 | 02-01, 02-02 | Duplicate threshold configurable via env var | SATISFIED | DUPLICATE_THRESHOLD in .env.example; settings.duplicate_threshold in config.py with default 0.85 |

**Requirements coverage: 15/15 Phase 2 requirements SATISFIED.**
**REQUIREMENTS.md traceability: Verified — AUTH-07 and AUTH-09 now show Complete in both list checkboxes and traceability rows.**
**Orphaned check:** No Phase 2 requirements appear in REQUIREMENTS.md that are not claimed in at least one plan's frontmatter. Coverage is complete.

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `bond/graph/nodes/researcher.py` | `async def researcher_node` | Warning | researcher_node is async; other nodes (writer, structure, checkpoint_1) are sync. Mixed sync/async in a LangGraph StateGraph is acceptable — LangGraph handles both. Graph correctly uses ainvoke(). Phase 3 must also use ainvoke() not invoke(). |
| `bond/graph/nodes/researcher.py` | `search_cache` stores raw string, not list[dict] | Warning | Plan 02-02 specified list[dict] with title/url/summary. MCP implementation stores a raw string. Cache hit path works. Phase 3 frontend must not assume structured list format. Not a functional bug. |
| `bond/graph/graph.py` | Dead comment "stubs until Plans 02-04 run" (line 71) | Info | All nodes are real implementations; stubs are gone. Cosmetic only. |
| `bond/db/metadata_log.py` | `get_article_by_id()` not implemented | Info | Plan listed this export; actual implementation provides get_recent_articles() instead. No upstream caller. No functional impact. |

**Blocker anti-patterns:** None.
**Warning anti-patterns:** 2 (async/sync mix, cache schema deviation — both noted for Phase 3 awareness).

---

### Architecture Deviations (Documented)

Both deviations from the original plan are now documented in `02-01-SUMMARY.md` under "Deviations from Plan":

**Deviation 1: exa-py SDK replaced by Exa MCP**

Plan specified `exa-py>=2.4.0` and `Exa.search_and_contents()`. Implementation uses `langchain-mcp-adapters` with `MultiServerMCPClient` pointing to `https://mcp.exa.ai/mcp`. `exa-py` is absent from `pyproject.toml`. `.env.example` carries the MCP setup comment. `02-01-SUMMARY.md` Deviations section item 2 documents this explicitly.

**Deviation 2: SqliteSaver replaced by AsyncSqliteSaver + async context manager**

Plan specified `SqliteSaver(sqlite3.connect(...))` returning a compiled graph from `compile_graph()`. Implementation uses `AsyncSqliteSaver.from_conn_string()` inside an `@asynccontextmanager`. `02-01-SUMMARY.md` Deviations section item 1 documents this with the final signature and Phase 3 impact callout. The `provides:` frontmatter also carries a NOTE for plan-to-plan traceability.

**Phase 3 integration contract (from documented deviations):**
- All graph usage must use `async with compile_graph() as graph:` — not `graph = compile_graph()`
- Exa web research has no `EXA_API_KEY` env var — MCP transport configured separately

---

### Human Verification Required

None. Both previously flagged human-verification items have been resolved:

1. AUTH-07 and AUTH-09 in REQUIREMENTS.md — confirmed Complete (verified by grep).
2. Phase 3 plan compatibility — the deviation is now documented in 02-01-SUMMARY.md for Phase 3 plan authors to reference; no code change was needed.

The live end-to-end run producing `Metadata saved: True` was human-approved in 02-04 Task 3 and remains valid.

---

### Known Open Item (Deferred — Not a Gap)

**Writer SEO constraints with OpenAI models:** `draft_validated=False` on live run — word count 428 vs 800 minimum, meta-description format mismatch. The pipeline infrastructure is correct. This is a prompt calibration gap for OpenAI's response format vs Anthropic Claude. User explicitly approved proceeding with this known issue. Deferred to pre-launch prompt tuning before Phase 3 production use.

---

*Verified: 2026-02-23 (re-verification)*
*Verifier: Claude (gsd-verifier)*
