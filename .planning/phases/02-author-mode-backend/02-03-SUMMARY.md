---
phase: 02-author-mode-backend
plan: 03
subsystem: graph-nodes
tags: [langgraph, hitl, interrupt, rag, chromadb, seo, anthropic, openai, writer]

# Dependency graph
requires:
  - phase: 02-02
    provides: researcher_node (research_report in state), compile_graph() pattern, get_corpus_collection() from bond/store/chroma.py

provides:
  - structure_node: H1/H2/H3 Markdown heading outline from research_report; cp1_feedback incorporation on re-runs
  - checkpoint_1_node: single interrupt() pausing graph for human review of research_report and heading_structure; approve/reject path with concatenated cp1_feedback
  - writer_node: low-corpus interrupt() gate (< 10 articles), RAG few-shot exemplar injection, SEO-compliant draft with auto-retry, targeted section revision on cp2_feedback
  - _validate_draft: checks keyword_in_h1, keyword_in_first_para, meta_desc_length_ok (150-160 chars), word_count_ok
  - _fetch_rag_exemplars: own-text-preferring corpus query with fallback to all types
  - _build_writer_prompt: fresh draft and targeted revision modes with exemplar section prefix

affects: [02-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Low-corpus interrupt gate: corpus.count() < threshold triggers interrupt() with warning payload; user confirms True (proceed) or False (abort)"
    - "RAG few-shot prefix injection: exemplars formatted as system prompt prefix (soft prompt style transfer); own_text preference with fallback"
    - "SEO auto-retry: silent 3-attempt loop; constraint failure logged; draft_validated=False on exhaustion"
    - "cp1_feedback concatenation: edited_structure + 'Uwaga: ' + note joined into single feedback string"
    - "RESEARCH_MODEL / DRAFT_MODEL dispatch: 'claude' substring -> ChatAnthropic; else ChatOpenAI"

key-files:
  created:
    - bond/graph/nodes/structure.py
    - bond/graph/nodes/checkpoint_1.py
    - bond/graph/nodes/writer.py
  modified:
    - bond/graph/graph.py

key-decisions:
  - "cp1_feedback format: edited_structure + optional '\\n\\nUwaga: {note}' — single string read by structure_node on re-run; no separate fields needed"
  - "RAG exemplar injection as system prompt prefix (not appended to user message) — soft prompt injection gives strongest style transfer signal per research recommendation in 02-RESEARCH.md"
  - "Low-corpus gate: corpus count checked before ANY LLM call in writer_node; interrupt() payload includes corpus_count and threshold for UI display"
  - "Writer auto-retry: cp2_feedback only injected on attempt 0; subsequent retries fall back to fresh draft to avoid compounding revision errors"
  - "graph.py stub removal pattern: import directly at module level, remove stub function, registry auto-uses new import — no register_node() call needed"

patterns-established:
  - "structure_node: cp1_iterations > 0 AND cp1_feedback set = regeneration mode (both conditions required)"
  - "checkpoint_1_node: approve response sets cp1_approved=True only; reject increments cp1_iterations and sets cp1_feedback"
  - "_validate_draft: regex-based H1 detection (^#\\s+), first non-heading non-empty line as first_para, meta desc via IGNORECASE regex"

requirements-completed: [AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-08, AUTH-11]

# Metrics
duration: 5min
completed: 2026-02-23
---

# Phase 2 Plan 03: Structure Node, Checkpoint 1, and Writer Node Summary

**H1/H2/H3 structure proposal with HITL approval loop, RAG style exemplar injection, low-corpus interrupt gate, and SEO constraint validation with 3-attempt auto-retry**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-23T05:00:35Z
- **Completed:** 2026-02-23T05:05:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- `structure_node` in `bond/graph/nodes/structure.py`: generates H1/H2/H3 heading outline from research_report using RESEARCH_MODEL; on re-run (cp1_iterations > 0 and cp1_feedback set) incorporates user-edited structure and note as strong prompt prior
- `checkpoint_1_node` in `bond/graph/nodes/checkpoint_1.py`: single interrupt() call surfacing research_report, heading_structure, and cp1_iterations; approve path sets cp1_approved=True; reject path concatenates edited_structure + note into cp1_feedback and increments cp1_iterations
- `writer_node` in `bond/graph/nodes/writer.py`: corpus count check before generation — interrupt() with low_corpus warning if < 10 articles, abort path returns draft=None/draft_validated=False; RAG few-shot exemplars fetched from bond_style_corpus_v1 preferring source_type=own with fallback; SEO-compliant draft generated with 3-attempt silent auto-retry; targeted section revision when cp2_feedback is set (preserves unchanged sections)
- `_validate_draft` checks four hard constraints: keyword_in_h1, keyword_in_first_para, meta_desc_length_ok (150-160 chars), word_count_ok (>= min_word_count)
- `_fetch_rag_exemplars` queries corpus with source_type=own filter; falls back to unfiltered query if < 3 own-text results found
- `graph.py`: three stub functions removed; replaced with direct module-level imports; 5 of 7 nodes now real implementations (checkpoint_2 and save_metadata stubs remain for Plan 04)

## Task Commits

Each task was committed atomically:

1. **Task 1: Structure node and Checkpoint 1 HITL node (AUTH-03, AUTH-04)** - `3d627f2` (feat)
2. **Task 2: Writer node with low-corpus gate, RAG injection, and SEO constraint validation (AUTH-05, AUTH-06, AUTH-08, AUTH-11)** - `7cdde5a` (feat)

## Files Created/Modified

- `bond/graph/nodes/structure.py` - structure_node generating H1/H2/H3 outline; cp1_feedback incorporation on re-runs
- `bond/graph/nodes/checkpoint_1.py` - checkpoint_1_node with single interrupt(); approve/reject paths; cp1_feedback concatenation
- `bond/graph/nodes/writer.py` - writer_node with low-corpus gate, _fetch_rag_exemplars, _build_writer_prompt, _validate_draft, auto-retry loop
- `bond/graph/graph.py` - Replaced three stubs (_structure_node, _checkpoint_1_node, _writer_node) with real imports

## Decisions Made

- **cp1_feedback format:** User-edited structure and optional note concatenated into a single string (`edited_structure + "\n\nUwaga: " + note`). structure_node reads this single field as a strong prior. No separate state fields needed — keeps AuthorState lean.
- **RAG exemplar injection as system prompt prefix:** Exemplars prepended to the system prompt section rather than appended to the user message. This soft prompt injection technique provides the strongest style transfer signal per the recommendation in 02-RESEARCH.md.
- **Low-corpus gate position:** Corpus count checked before any LLM call or exemplar fetch — interrupt() payload contains corpus_count and threshold so the frontend can display a meaningful warning to the user.
- **Writer auto-retry with cp2_feedback:** cp2_feedback injected only on attempt 0 of the retry loop. Subsequent retries fall back to fresh draft mode to avoid compounding targeted-revision errors when constraints still fail after one revision pass.
- **graph.py stub removal pattern:** Direct module-level import replaces the stub function definition. The _node_registry dict is initialized with the real function references automatically. No register_node() call needed — clean and idiomatic Python.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `uv run python` required (as in Plan 02) — `python` not in PATH in this environment. All verifications passed with `uv run python`.
- The plan verification script for meta-description used a 118-char string and expected `meta_desc_length_ok: False` (which is correct — below 150-char threshold). The `word_count_ok: True` assertion was the meaningful check. Both assertions passed as expected.

## Next Phase Readiness

- Plan 04 can import from all five real nodes; checkpoint_2 and save_metadata stubs are the only remaining placeholders
- `add_topic_to_metadata_collection()` in `bond/store/chroma.py` is ready for save_metadata_node (Plan 04)
- All HITL interrupt() calls follow a consistent payload dict pattern — Plan 04's checkpoint_2 should match this shape
- Set `EXA_API_KEY` and any LLM API keys in `.env` before running a live end-to-end test

## Self-Check: PASSED

All created/modified files verified present on disk. Both task commits (3d627f2, 7cdde5a) confirmed in git log.

---
*Phase: 02-author-mode-backend*
*Completed: 2026-02-23*
