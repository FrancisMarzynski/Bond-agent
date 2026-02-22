---
phase: 01-rag-corpus-onboarding
plan: 03
subsystem: corpus
tags: [chromadb, fastapi, pydantic, retrieval, smoke-test, two-pass-retrieval, rag]

# Dependency graph
requires:
  - phase: 01-01
    provides: ChromaDB store, SQLite article log, get_article_count(), get_chunk_count(), CorpusIngestor
  - phase: 01-02
    provides: All 4 ingestion endpoints active, corpus populated via text/file/url/drive
provides:
  - run_smoke_test(query, n_results) — two-pass own-first retrieval with cosine similarity scores
  - GET /api/corpus/status — article count, chunk count, low-corpus warning
  - GET /api/corpus/smoke-test — ranked fragments with score, source_type, article_title, fragment
  - Phase 1 exit criteria satisfied (retrieval quality verified by human)
affects: [02-author-mode-backend]

# Tech tracking
tech-stack:
  added: []
  patterns: [two-pass own-before-external retrieval, cosine distance to similarity conversion (1 - distance), low-corpus warning threshold gate]

key-files:
  created:
    - bond/corpus/smoke_test.py
  modified:
    - bond/api/routes/corpus.py

key-decisions:
  - "Two-pass retrieval: own text queried first, external fills remainder — ensures author style prioritised over reference material"
  - "Cosine distance converted to similarity via score = 1.0 - distance, rounded to 4 decimal places"
  - "ChromaDB filtered query (where source_type) raises if n_results > filtered collection size — caught with except block, returns [] gracefully"
  - "CorpusStatus and SmokeTestResult Pydantic models added inline to corpus.py (small, not needed elsewhere)"
  - "low_corpus_threshold default 10 from settings — warning fires below threshold, null above"

patterns-established:
  - "Two-pass retrieval pattern: _query(own) -> fill from _query(external) if insufficient -> sort combined by score desc"
  - "Smoke test as Phase boundary gate: human verification of retrieval scores (>0.3 threshold) before Phase 2"

requirements-completed: [CORP-05, CORP-06, CORP-07]

# Metrics
duration: ~10min (including human checkpoint)
completed: 2026-02-22
---

# Phase 1 Plan 3: Corpus Status and Retrieval Smoke Test Summary

**Two-pass own-first retrieval smoke test and corpus status endpoint completing Phase 1 RAG corpus pipeline, verified at 0.63–0.68 cosine similarity on real Polish-language content**

## Performance

- **Duration:** ~10 min (automated execution) + human verification checkpoint
- **Started:** 2026-02-22
- **Completed:** 2026-02-22
- **Tasks:** 1 automated + 1 human checkpoint (approved)
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- `bond/corpus/smoke_test.py` implementing two-pass retrieval: own text first, external fills remainder, combined sorted by cosine similarity score
- `GET /api/corpus/status` returning article count, chunk count, and conditional `low_corpus_warning` below 10-article threshold
- `GET /api/corpus/smoke-test` returning ranked fragments with score (0–1), source_type, article_title, and 300-char fragment preview
- Human checkpoint approved: smoke test scores 0.63–0.68 observed on real corpus data (well above 0.3 threshold)
- Phase 1 complete: all 7 CORP requirements (CORP-01 through CORP-07) satisfied

## Retrieval Quality Observations

**Observed during human verification checkpoint:**
- Similarity scores: 0.63–0.68 for relevant Polish-language style queries
- Threshold: 0.3 (plan criterion) — observed scores comfortably exceeded threshold
- source_type field: present in all results ("own" / "external")
- article_title field: correctly populated from ingest metadata
- fragment field: 300-char preview rendering correctly
- Two-pass own-first retrieval: confirmed working — own text fragments surfaced before external when both present
- Low-corpus warning: firing correctly when article_count < 10

**Implications for Phase 2:**
- Retrieval quality at 0.63–0.68 is adequate for RAG-augmented generation
- Polish-language multilingual embeddings (paraphrase-multilingual-MiniLM-L12-v2) performing well
- Two-pass retrieval ensures author style context is prioritised in LLM prompts
- Chunk size 1875 chars (~500 tokens) appears appropriate — fragments are coherent and meaningful

## Task Commits

Each task was committed atomically:

1. **Task 1: Retrieval smoke test module and corpus status + smoke-test endpoints** - `ad6cee4` (feat)

**Plan metadata:** Committed after STATE.md update

## Files Created/Modified
- `bond/corpus/smoke_test.py` - run_smoke_test() two-pass retrieval; _query() helper with filtered ChromaDB query and exception handling; DEFAULT_QUERY constant
- `bond/api/routes/corpus.py` - Added CorpusStatus, SmokeTestResult models; GET /api/corpus/status and GET /api/corpus/smoke-test endpoints; imports for get_article_count, get_chunk_count, run_smoke_test, settings

## Decisions Made
- **Two-pass retrieval order**: Own text queried first to fill n_results; external only fills the gap. Combined results re-sorted by score. Ensures author style is always prioritised.
- **ChromaDB filtered query error handling**: When n_results exceeds available filtered results, ChromaDB raises an exception. Caught with bare `except Exception`, logs WARN, returns `[]`. This is the correct approach as there is no clean way to pre-check filtered collection size.
- **Inline Pydantic models**: CorpusStatus and SmokeTestResult added to corpus.py rather than models.py — these are endpoint-specific response shapes not needed by other modules.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None — implementation followed the plan code snippets directly. ChromaDB filtered query exception handling was already specified in the plan.

## User Setup Required
None - no external service configuration required for this plan.

## Phase 1 Completion

Phase 1 (RAG Corpus Onboarding) is now complete. All 7 CORP requirements satisfied:

| Requirement | Description | Status |
|-------------|-------------|--------|
| CORP-01 | Text paste ingestion | Done (01-01) |
| CORP-02 | File upload ingestion (PDF/DOCX/TXT) | Done (01-01) |
| CORP-03 | Blog URL scraper | Done (01-02) |
| CORP-04 | Google Drive connector | Done (01-02) |
| CORP-05 | ChromaDB with multilingual embeddings | Done (01-01) |
| CORP-06 | Corpus status endpoint (article count, chunk count) | Done (01-03) |
| CORP-07 | Low-corpus warning below threshold | Done (01-03) |

All 6 corpus endpoints registered in OpenAPI schema:
- `POST /api/corpus/ingest/text`
- `POST /api/corpus/ingest/file`
- `POST /api/corpus/ingest/url`
- `POST /api/corpus/ingest/drive`
- `GET /api/corpus/status`
- `GET /api/corpus/smoke-test`

## Next Phase Readiness
- Phase 2 (Author Mode Backend) can begin immediately
- Retrieval quality verified at 0.63–0.68 — adequate for RAG-augmented generation
- `run_smoke_test()` available as a diagnostic tool throughout Phase 2 development
- Blockers to track in Phase 2: LangGraph SqliteSaver import path (0.1 vs 0.2 API), Exa API Polish-language parameters

## Self-Check: PASSED

- FOUND: bond/corpus/smoke_test.py
- FOUND: bond/api/routes/corpus.py
- FOUND: .planning/phases/01-rag-corpus-onboarding/01-03-SUMMARY.md (this file)
- FOUND: commit ad6cee4 (Task 1)
- VERIFIED: Human checkpoint approved with scores 0.63–0.68

---
*Phase: 01-rag-corpus-onboarding*
*Completed: 2026-02-22*
