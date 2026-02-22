---
phase: 01-rag-corpus-onboarding
verified: 2026-02-22T18:00:00Z
status: passed
score: 12/12 must-haves verified
re_verification: false
gaps: []
human_verification:
  - test: "Ingest real article via POST /api/corpus/ingest/text and run GET /api/corpus/smoke-test"
    expected: "Smoke test returns results with score 0.0–1.0, source_type 'own', matching article_title, and non-empty fragment"
    why_human: "Requires a running server with the 420MB embedding model loaded; retrieval score quality and fragment meaningfulness cannot be checked by static grep"
  - test: "Run GET /api/corpus/status when article_count is below 10 and again after ingesting 10+ articles"
    expected: "low_corpus_warning is non-null below threshold and null at or above threshold"
    why_human: "Threshold boundary behaviour depends on live SQLite state; functional test requires server execution"
  - test: "POST /api/corpus/ingest/url with a real blog URL that has a sitemap"
    expected: "Multiple articles ingested, articles_ingested > 0, total_chunks > 0, no 500 error"
    why_human: "Requires live network access and a real blog; cannot be verified statically"
---

# Phase 1: RAG Corpus Onboarding — Verification Report

**Phase Goal:** Users can populate the style corpus from multiple sources and verify retrieval quality before any generation runs
**Verified:** 2026-02-22T18:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Text paste via POST /api/corpus/ingest/text stores chunks in ChromaDB and logs article in SQLite | VERIFIED | `corpus.py:36-50` calls `ingest_text()` → `CorpusIngestor.ingest()` → `collection.add()` + `log_article()` |
| 2 | File upload via POST /api/corpus/ingest/file stores parsed PDF/DOCX/TXT chunks in ChromaDB | VERIFIED | `corpus.py:53-97` calls `extract_text()` then `CorpusIngestor.ingest()` with full chain to ChromaDB |
| 3 | source_type='own' and 'external' are only accepted values; any other returns 422 | VERIFIED | `SourceType(str, Enum)` in `models.py:5-7`; file endpoint raises HTTPException 422 at `corpus.py:60-66`; text endpoint fails at Pydantic parse |
| 4 | Collection bond_style_corpus_v1 exists in ChromaDB with cosine similarity and paraphrase-multilingual-MiniLM-L12-v2 embeddings | VERIFIED | `chroma.py:27-31` — `get_or_create_collection(name="bond_style_corpus_v1", metadata={"hnsw:space": "cosine"})` with `SentenceTransformerEmbeddingFunction(model_name="paraphrase-multilingual-MiniLM-L12-v2")` |
| 5 | POST /api/corpus/ingest/url discovers posts via sitemap and ingests each article, skipping on failures | VERIFIED | `url_source.py:19` — `sitemap_search(url) or [url]`; per-article try/except with WARN+continue; `corpus.py:100-110` calls `ingest_blog()` |
| 6 | POST /api/corpus/ingest/drive downloads PDF/DOCX/TXT from Google Drive and ingests them, skipping unreadable files | VERIFIED | `drive_source.py:96-160` — `list_folder_files()` → `download_file()` → `extract_text()` → `CorpusIngestor.ingest()`; each step has skip-and-warn |
| 7 | Blog scraping respects MAX_BLOG_POSTS and logs WARN when URL is unreachable or returns no content | VERIFIED | `url_source.py:22-27` — `len(urls) > max_posts` truncation with WARN; `url_source.py:33-35` — fetch returns None → WARN+continue |
| 8 | Drive connector shows service account hint in warning when folder returns 0 files | VERIFIED | `drive_source.py:114-119` — explicit warning string includes "ensure the folder is shared with the service account email" |
| 9 | GET /api/corpus/status returns article count, chunk count, and low_corpus_warning when below threshold | VERIFIED | `corpus.py:129-149` — calls `get_article_count()`, `get_chunk_count()`, compares to `settings.low_corpus_threshold`; returns `CorpusStatus` model |
| 10 | GET /api/corpus/smoke-test returns top-N fragments with cosine similarity scores, source_type, article title, and text preview | VERIFIED | `smoke_test.py:62-70` — `score = round(1.0 - dist, 4)`, `source_type`, `article_title`, `fragment = doc[:300]` all returned; wired at `corpus.py:152-166` |
| 11 | source_type metadata is visible in every smoke test result; own text fragments preferred when available | VERIFIED | `smoke_test.py:26` — pass 1 queries `where={"source_type": "own"}`; pass 2 only fills remainder; `meta.get("source_type")` returned for every result |
| 12 | Low-corpus warning fires when article count < LOW_CORPUS_THRESHOLD and is absent when count >= threshold | VERIFIED | `corpus.py:138-143` — `if article_count < settings.low_corpus_threshold:` sets warning; else warning remains `None` |

**Score:** 12/12 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bond/config.py` | Pydantic Settings loading CHROMA_PATH, ARTICLE_DB_PATH, LOW_CORPUS_THRESHOLD, RAG_TOP_K, MAX_BLOG_POSTS, GOOGLE_CREDENTIALS_PATH | VERIFIED | All 7 fields present; `google_auth_method` also present; `settings = Settings()` singleton exported |
| `bond/models.py` | SourceType enum ('own'/'external'), IngestTextRequest, IngestResult (plan called it IngestFileResponse — name differs, function identical) | VERIFIED | `SourceType`, `IngestTextRequest`, `IngestResult`, `IngestUrlRequest`, `IngestDriveRequest`, `BatchIngestResult` all present |
| `bond/store/chroma.py` | get_chroma_client() and get_or_create_corpus_collection() singletons | VERIFIED | Both functions present; singleton via module-level `_client`/`_collection`; `get_corpus_collection()` also present |
| `bond/store/article_log.py` | SQLite article log with log_article(), get_article_count(), get_chunk_count() | VERIFIED | All three functions implemented; CREATE TABLE IF NOT EXISTS; INSERT OR REPLACE |
| `bond/corpus/chunker.py` | chunk_article() using RecursiveCharacterTextSplitter at 1875 chars / 190 overlap | VERIFIED | Exact parameters match; filters chunks < 50 chars |
| `bond/corpus/ingestor.py` | CorpusIngestor.ingest(text, title, source_type, source_url) — adds chunks to ChromaDB, logs to SQLite | VERIFIED | Full implementation; `collection.add()` at line 38; `log_article()` at line 39 |
| `bond/corpus/sources/text_source.py` | ingest_text(text, source_type, title) — wraps CorpusIngestor | VERIFIED | 5-line implementation; delegates to `CorpusIngestor().ingest()` |
| `bond/corpus/sources/file_source.py` | extract_text(content, filename) — dispatches PDF/DOCX/TXT; returns None and prints WARN on failure | VERIFIED | Full dispatch with 20MB size check; all three formats handled; WARN prints confirmed |
| `bond/corpus/sources/url_source.py` | scrape_blog(url) using trafilatura sitemap_search | VERIFIED | `sitemap_search` import and use confirmed; `ingest_blog()` orchestrator present |
| `bond/corpus/sources/drive_source.py` | build_drive_service() and ingest_drive_folder(folder_id, source_type) | VERIFIED | Both oauth and service_account auth paths implemented; paginated file listing; Google Docs export |
| `bond/corpus/smoke_test.py` | run_smoke_test(query, n_results) using two-pass retrieval; returns ranked results with cosine similarity scores | VERIFIED | Two-pass implementation with `_query()` helper; distance-to-similarity conversion; `DEFAULT_QUERY` exported |
| `bond/api/routes/corpus.py` | POST /ingest/text, /ingest/file, /ingest/url, /ingest/drive; GET /status, /smoke-test | VERIFIED | All 6 endpoints present; prefix="/api/corpus"; all response models applied |
| `bond/api/main.py` | FastAPI app with /api/corpus router mounted | VERIFIED | `app.include_router(corpus_router)`; `/health` endpoint |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `bond/api/routes/corpus.py` | `bond/corpus/ingestor.py` | `CorpusIngestor.ingest()` called in both text and file endpoints | WIRED | `corpus.py:13` import; called at lines 40, 84 |
| `bond/corpus/ingestor.py` | `bond/store/chroma.py` | `collection.add()` call | WIRED | `ingestor.py:3` import `get_or_create_corpus_collection`; `collection.add()` at line 38 |
| `bond/corpus/ingestor.py` | `bond/store/article_log.py` | `log_article()` call | WIRED | `ingestor.py:4` import; `log_article()` called at line 39 |
| `bond/corpus/sources/file_source.py` | pymupdf / python-docx | `extract_text_from_pdf` / `extract_text_from_docx` | WIRED | `import pymupdf` with fitz fallback at lines 3-10; `from docx import Document` at line 12 |
| `bond/api/routes/corpus.py` | `bond/corpus/sources/url_source.py` | `ingest_blog()` call | WIRED | Import at line 14; called at `corpus.py:104` |
| `bond/api/routes/corpus.py` | `bond/corpus/sources/drive_source.py` | `ingest_drive_folder()` call | WIRED | Import at line 15; called at `corpus.py:117` |
| `bond/corpus/sources/drive_source.py` | `bond/corpus/sources/file_source.py` | `extract_text()` called on downloaded bytes | WIRED | Import at `drive_source.py:5`; called at line 139 |
| `bond/api/routes/corpus.py` (GET /status) | `bond/store/article_log.py` | `get_article_count()` and `get_chunk_count()` | WIRED | Import at `corpus.py:16`; called at lines 135-136 |
| `bond/api/routes/corpus.py` (GET /smoke-test) | `bond/corpus/smoke_test.py` | `run_smoke_test()` | WIRED | Import at `corpus.py:17`; called at line 161 |
| `bond/corpus/smoke_test.py` | `bond/store/chroma.py` | `get_corpus_collection().query()` — two-pass own-then-external | WIRED | Import at `smoke_test.py:1`; `get_corpus_collection()` at line 20; `where={"source_type": "own"}` and `"external"` at lines 26/34 |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CORP-01 | 01-01 | User can add article by pasting text | SATISFIED | `POST /api/corpus/ingest/text` implemented in `corpus.py:35-50`; full chain to ChromaDB and SQLite |
| CORP-02 | 01-01 | User can add articles by uploading file (PDF, DOCX, TXT) | SATISFIED | `POST /api/corpus/ingest/file` at `corpus.py:53-97`; `file_source.py` handles all three formats |
| CORP-03 | 01-02 | User can populate corpus from Google Drive folder | SATISFIED | `POST /api/corpus/ingest/drive` at `corpus.py:113-126`; `drive_source.py` with full oauth/service_account support |
| CORP-04 | 01-02 | User can populate corpus by providing blog URL | SATISFIED | `POST /api/corpus/ingest/url` at `corpus.py:100-110`; `url_source.py` with trafilatura sitemap discovery |
| CORP-05 | 01-01, 01-02 | User can tag sources as "own text" or "external blogger" | SATISFIED | `SourceType(str, Enum)` with values "own"/"external"; enforced in all 4 ingestion paths; stored in ChromaDB metadata |
| CORP-06 | 01-03 | User can see article count and chunk count (corpus status) | SATISFIED | `GET /api/corpus/status` returns `article_count` and `chunk_count` from SQLite via `get_article_count()`/`get_chunk_count()` |
| CORP-07 | 01-03 | System warns when corpus has fewer than 10 articles | SATISFIED | `corpus.py:138-143` — `low_corpus_warning` populated when `article_count < settings.low_corpus_threshold` (default 10) |

**All 7 CORP requirements accounted for. No orphaned requirements.**

REQUIREMENTS.md traceability table maps CORP-01 through CORP-07 exclusively to Phase 1 — all are covered by plans 01-01, 01-02, 01-03.

---

### Anti-Patterns Found

No blockers or warnings detected.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `bond/corpus/smoke_test.py` | 23 | `return []` | Info | Valid empty-corpus guard — expected behavior when collection.count() == 0 |
| `bond/corpus/smoke_test.py` | 55 | `return []` | Info | Valid exception handler — ChromaDB raises when n_results > filtered collection size |

No TODO/FIXME/PLACEHOLDER/HACK comments found in any file. No unimplemented endpoint stubs. No static return values masquerading as real data.

---

### Human Verification Required

The following items require a running server and cannot be verified statically:

#### 1. Retrieval Quality Confirmation

**Test:** Start `uvicorn bond.api.main:app --reload`, ingest 3+ articles via `POST /api/corpus/ingest/text`, then run `GET /api/corpus/smoke-test?n=3`
**Expected:** Results have `score` between 0.3 and 1.0, `source_type` matches ingested type, `article_title` matches the ingested title, `fragment` shows readable text excerpt (not empty string)
**Why human:** Requires the 420MB `paraphrase-multilingual-MiniLM-L12-v2` embedding model to be loaded and real ChromaDB data to be present; score quality is a semantic judgment

#### 2. Low-Corpus Warning Boundary

**Test:** Hit `GET /api/corpus/status` with fewer than 10 articles, then add articles to reach exactly 10, then check again
**Expected:** `low_corpus_warning` is non-null string below 10, and `null` at exactly 10
**Why human:** Requires live SQLite state with specific article counts

#### 3. Blog URL Scraping (live network)

**Test:** `POST /api/corpus/ingest/url` with a real Polish-language blog that has a sitemap.xml
**Expected:** `articles_ingested` > 0, `total_chunks` > 0, no 500 error; unreachable URL returns 200 with warning
**Why human:** Requires live network access; no test server mocking in this codebase

---

### Minor Discrepancy Note

Plan 01-01 artifact description for `bond/models.py` states `IngestFileResponse` as one of the models provided. The actual implementation uses `IngestResult` for both text and file response shapes. This is a naming discrepancy in the plan documentation only — the actual code is functionally correct and consistent. `IngestResult` is used throughout `corpus.py` and imported correctly.

---

## Summary

Phase 1 goal is achieved. All 12 observable truths are verified against the actual codebase. Every artifact exists, is substantive (non-stub), and is wired into the data flow. All 10 key links are confirmed. All 7 CORP requirements are satisfied with direct code evidence. No anti-patterns were found that would block the goal.

The codebase delivers exactly what the phase goal requires: users can populate the style corpus from four distinct sources (text paste, file upload, blog URL, Google Drive) and verify retrieval quality before any LLM generation runs, with source-type tagging, corpus status visibility, and low-corpus warnings all operational.

The only items requiring human confirmation are live-server behaviors (retrieval quality scores, network-dependent URL scraping) that cannot be assessed by static code inspection. These are verification hygiene items, not blockers.

---

_Verified: 2026-02-22T18:00:00Z_
_Verifier: Claude (gsd-verifier)_
