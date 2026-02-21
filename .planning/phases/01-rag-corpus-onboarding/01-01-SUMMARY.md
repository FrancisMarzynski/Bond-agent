---
phase: 01-rag-corpus-onboarding
plan: 01
subsystem: corpus
tags: [chromadb, fastapi, pydantic, sqlite, langchain, embeddings, rag]

# Dependency graph
requires: []
provides:
  - Project structure with bond/ package
  - ChromaDB store with paraphrase-multilingual-MiniLM-L12-v2 embeddings
  - SQLite article log for corpus tracking
  - FastAPI app with text paste and file upload ingestion endpoints
  - RecursiveCharacterTextSplitter chunker (1875 chars / 190 overlap)
affects: [01-02, 01-03, 02-author-mode-backend]

# Tech tracking
tech-stack:
  added: [chromadb==1.5.1, sentence-transformers>=3.0, langchain-text-splitters, pymupdf, python-docx, fastapi>=0.115, uvicorn, pydantic>=2.0, pydantic-settings]
  patterns: [Singleton pattern for ChromaDB client, Pydantic Settings for config, FastAPI router pattern]

key-files:
  created:
    - pyproject.toml
    - .env.example
    - bond/__init__.py
    - bond/config.py
    - bond/models.py
    - bond/store/__init__.py
    - bond/store/chroma.py
    - bond/store/article_log.py
    - bond/corpus/__init__.py
    - bond/corpus/chunker.py
    - bond/corpus/ingestor.py
    - bond/corpus/sources/__init__.py
    - bond/corpus/sources/text_source.py
    - bond/corpus/sources/file_source.py
    - bond/api/__init__.py
    - bond/api/main.py
    - bond/api/routes/__init__.py
    - bond/api/routes/corpus.py
  modified: []

key-decisions:
  - "Singleton pattern for ChromaDB PersistentClient to avoid re-initializing embedding model (~420MB) on every request"
  - "SQLite for article log (not ChromaDB metadata) for efficient article-level counting and future admin UI"
  - "1875 chars chunk size for Polish text (~500 tokens at 3.75 chars/token average) with 10% overlap for context continuity"
  - "pymupdf import with fitz fallback for PDF parsing compatibility"

patterns-established:
  - "Pydantic Settings with .env file loading for all configuration"
  - "CorpusIngestor class as central ingestion orchestrator"
  - "SourceType enum for 'own'/'external' distinction with 422 validation on invalid values"
  - "File extraction returns None with WARN print on failure (graceful degradation)"

requirements-completed: [CORP-01, CORP-02, CORP-05]

# Metrics
duration: 16 min
completed: 2026-02-21
---

# Phase 1 Plan 1: Project Setup and Text/File Ingestion Summary

**Bootstrap project structure with ChromaDB store, SQLite article log, and FastAPI endpoints for text paste and file upload ingestion**

## Performance

- **Duration:** 16 min
- **Started:** 2026-02-21T14:29:17Z
- **Completed:** 2026-02-21T14:46:09Z
- **Tasks:** 4 (3 planned + 1 fix)
- **Files modified:** 18 created

## Accomplishments
- Complete project structure with uv-managed dependencies
- ChromaDB collection `bond_style_corpus_v1` with cosine similarity and multilingual embeddings
- SQLite article log tracking corpus statistics
- FastAPI endpoints for text paste and file upload (PDF/DOCX/TXT) ingestion
- SourceType validation rejecting invalid values with 422 error

## Task Commits

Each task was committed atomically:

1. **Task 1: Project setup and shared foundation** - `70b0044` (chore)
2. **Task 2: CorpusIngestor, file_source, text_source, and FastAPI routes** - `3382783` (feat)
3. **Bug fix: Type annotation for ChromaDB client** - `536b77e` (fix)
4. **Style: Minor formatting cleanup** - `547c52c` (style)

**Plan metadata:** Will be committed after STATE.md update

## Files Created/Modified
- `pyproject.toml` - uv-managed project with all Phase 1 dependencies
- `.env.example` - Configuration template for ChromaDB, SQLite, and Google paths
- `bond/config.py` - Pydantic Settings loading environment variables
- `bond/models.py` - SourceType enum and IngestTextRequest/IngestResult models
- `bond/store/chroma.py` - Singleton PersistentClient and corpus collection factory
- `bond/store/article_log.py` - SQLite article tracking with chunk counts
- `bond/corpus/chunker.py` - RecursiveCharacterTextSplitter (1875/190)
- `bond/corpus/ingestor.py` - CorpusIngestor class coordinating chunking, embedding, and logging
- `bond/corpus/sources/text_source.py` - Plain text paste ingestion wrapper
- `bond/corpus/sources/file_source.py` - PDF/DOCX/TXT extraction with graceful error handling
- `bond/api/main.py` - FastAPI app with health check and corpus router
- `bond/api/routes/corpus.py` - POST /api/corpus/ingest/text and /api/corpus/ingest/file endpoints

## Decisions Made
- **Singleton ChromaDB client**: Avoids re-loading the 420MB embedding model on every request
- **SQLite for article log**: More efficient for article-level counting than ChromaDB metadata queries
- **Chunk size 1875 chars**: Optimized for Polish text token ratio (~500 tokens)
- **pymupdf with fitz fallback**: Handles package naming inconsistency between versions

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ChromaDB client type annotation**
- **Found during:** Task 1 verification
- **Issue:** `_client: chromadb.PersistentClient | None = None` caused runtime error due to chromadb's internal type system
- **Fix:** Changed to `_client: Any = None` using typing.Any to satisfy both static analysis and runtime
- **Files modified:** bond/store/chroma.py
- **Verification:** Python imports succeed, no TypeError
- **Committed in:** `536b77e`

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minimal - type annotation fix necessary for runtime compatibility. No scope creep.

## Issues Encountered
None - implementation proceeded smoothly after the type annotation fix.

## User Setup Required

None - no external service configuration required for this plan. The embedding model downloads automatically on first use (~420MB).

## Next Phase Readiness
- Project foundation complete with all Phase 1 dependencies installed
- ChromaDB and SQLite stores ready for additional ingestion paths (Plan 02)
- FastAPI app structure ready for corpus status and retrieval endpoints (Plan 03)
- All verification tests passing

---
*Phase: 01-rag-corpus-onboarding*
*Completed: 2026-02-21*
