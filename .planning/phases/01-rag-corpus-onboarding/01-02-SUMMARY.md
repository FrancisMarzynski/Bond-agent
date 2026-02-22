---
phase: 01-rag-corpus-onboarding
plan: 02
subsystem: corpus
tags: [trafilatura, google-drive, fastapi, pydantic, sitemap, scraping, rag]

# Dependency graph
requires:
  - phase: 01-01
    provides: CorpusIngestor, file_source.extract_text(), FastAPI corpus router, SourceType enum
provides:
  - scrape_blog(url) using trafilatura sitemap_search — list of {url, title, text} dicts
  - ingest_blog(url, source_type) — orchestrates scraping and ingestion for a blog URL
  - build_drive_service() supporting oauth and service_account auth
  - ingest_drive_folder(folder_id, source_type) — downloads and ingests PDF/DOCX/TXT/Google Docs
  - POST /api/corpus/ingest/url endpoint with graceful warning on unreachable URLs
  - POST /api/corpus/ingest/drive endpoint with auth-failure surfaced in warnings (not 500)
  - All 4 /api/corpus/ingest/* routes registered in OpenAPI schema
affects: [01-03, 02-author-mode-backend]

# Tech tracking
tech-stack:
  added: [trafilatura (sitemap_search + fetch_url + extract), google-api-python-client v3, google-auth, google-auth-oauthlib]
  patterns: [skip-and-warn failure policy per CONTEXT.md, lazy Drive auth (catch all exceptions, surface as warnings), sitemap-first URL discovery with single-URL fallback]

key-files:
  created:
    - bond/corpus/sources/url_source.py
    - bond/corpus/sources/drive_source.py
  modified:
    - bond/models.py
    - bond/api/routes/corpus.py

key-decisions:
  - "Pydantic models IngestUrlRequest, IngestDriveRequest, BatchIngestResult added to bond/models.py (not inline in router) for reuse"
  - "Drive auth failure caught at service build time and returned as warnings dict — ensures /ingest/drive never returns 500 even without credentials"
  - "sitemap_search fallback to [url] list — if sitemap unavailable, treats the URL itself as a single post to attempt"
  - "Google Docs exported as text/plain via Drive export_media API — no extra parsing needed, routes through file_source dispatch"
  - "SUPPORTED_MIME_TYPES dict used for both filtering list results and determining export format/extension for file_source dispatch"

patterns-established:
  - "Skip-and-warn at each article/file level: continue loop on any per-item failure, collect warnings in list, return in response body"
  - "MAX_BLOG_POSTS enforcement: len(urls) > max_posts truncates with WARN log before scraping loop"
  - "Service account troubleshooting hint: 0-file folder warning includes guidance to share folder with service account email"

requirements-completed: [CORP-03, CORP-04]

# Metrics
duration: 4min
completed: 2026-02-22
---

# Phase 1 Plan 2: Blog URL Scraper and Google Drive Connector Summary

**trafilatura sitemap scraper and Google Drive folder downloader completing all 4 /api/corpus/ingest/* endpoints with skip-and-warn failure handling**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-22T17:14:27Z
- **Completed:** 2026-02-22T17:19:20Z
- **Tasks:** 2
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `url_source.py` with `scrape_blog()` using trafilatura `sitemap_search` for article discovery and `fetch_url` + `extract` for per-article content extraction
- `drive_source.py` with `build_drive_service()` supporting both oauth and service_account auth, and `ingest_drive_folder()` with paginated file listing and Google Docs text export
- All 4 corpus ingestion endpoints registered: `/ingest/text`, `/ingest/file`, `/ingest/url`, `/ingest/drive`
- Skip-and-warn policy enforced at every failure point — no endpoint ever raises a 500 error

## Task Commits

Each task was committed atomically:

1. **Task 1: Blog URL scraper (url_source.py) and Drive connector (drive_source.py)** - `62ce266` (feat)
2. **Task 2: Add /ingest/url and /ingest/drive endpoints to corpus router** - `9338c1d` (feat)

**Plan metadata:** Will be committed after STATE.md update

## Files Created/Modified
- `bond/corpus/sources/url_source.py` - scrape_blog() sitemap discovery + per-article extraction; ingest_blog() orchestrator
- `bond/corpus/sources/drive_source.py` - build_drive_service() oauth/service_account; list_folder_files() paginated; download_file() with Google Docs export; ingest_drive_folder() orchestrator
- `bond/models.py` - Added IngestUrlRequest, IngestDriveRequest, BatchIngestResult Pydantic models
- `bond/api/routes/corpus.py` - Added POST /api/corpus/ingest/url and POST /api/corpus/ingest/drive endpoints with imports

## Blog Scraping Implementation Details

**Sitemap discovery:** `trafilatura.sitemaps.sitemap_search(url)` discovers all post URLs from sitemap.xml or RSS feed. Falls back to `[url]` (single-post mode) if no sitemap found.

**MAX_BLOG_POSTS enforcement:** If discovered URLs exceed `settings.max_blog_posts` (default 50, configurable via `MAX_BLOG_POSTS` env var), list is truncated with a WARN log line before the scraping loop begins.

**Per-article extraction pipeline:**
1. `trafilatura.fetch_url(post_url)` — downloads HTML
2. `trafilatura.extract(downloaded, output_format="json")` — extracts article content
3. JSON parsed for `text` and `title` fields
4. Empty text triggers WARN + skip; exception triggers WARN + skip

**Testing behavior:** On `https://example.com`, `scrape_blog()` returns an empty list with WARN logs (no sitemap, no article content) — this is expected and correct behavior.

## Drive Auth Method and Switching

**Default auth (oauth):** Uses `InstalledAppFlow` from `google-auth-oauthlib`. Requires `credentials.json` (OAuth desktop app credentials). On first run, opens browser for user consent. Token cached in `token.json` (same directory as credentials file).

**Service account auth:** Set `GOOGLE_AUTH_METHOD=service_account` in `.env`. Requires a service account key JSON file at `GOOGLE_CREDENTIALS_PATH`. **Important:** The target Drive folder must be shared with the service account email address — if not, the folder will appear empty and the response will include a troubleshooting hint pointing to the service account email.

**Switching between methods:**
```bash
# .env
GOOGLE_AUTH_METHOD=service_account  # or "oauth"
GOOGLE_CREDENTIALS_PATH=./service-account-key.json  # or ./credentials.json
```

## Trafilatura and Drive API Behavior Discoveries

**trafilatura sitemap_search:** Returns a generator (or list) of URLs. When called on a URL with no sitemap, returns an empty iterable — the `or [url]` fallback correctly handles this. The function may make multiple HTTP requests (sitemap.xml, feed URLs) so network timeouts can cause slow responses on test URLs.

**trafilatura output_format:** Using `output_format="json"` (without `include_metadata=True` as the metadata flag was not in the installed version's API) works correctly — returns a JSON string with `text` and `title` fields.

**Drive pagination:** `list` API defaults to 100 items per page; pagination loop handles `nextPageToken` correctly for folders with more than 100 files.

**Google Docs export:** `export_media(fileId=..., mimeType="text/plain")` downloads the document as UTF-8 plain text. This routes through `file_source.extract_text()` which handles `.txt` files via direct UTF-8 decode.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unsupported include_metadata=True parameter from trafilatura.extract()**
- **Found during:** Task 1 (url_source.py implementation)
- **Issue:** The plan's code snippet used `trafilatura.extract(downloaded, include_metadata=True, output_format="json")` but the installed trafilatura version does not support `include_metadata` as a keyword argument in the same call as `output_format="json"` — the JSON output format already includes all metadata
- **Fix:** Removed `include_metadata=True`, kept `output_format="json"` which returns full metadata including title in the JSON structure
- **Files modified:** bond/corpus/sources/url_source.py
- **Verification:** Import succeeds; scrape_blog() on example.com returns empty list without TypeError
- **Committed in:** 62ce266 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — minor API parameter adjustment)
**Impact on plan:** Minimal — JSON format already includes all needed metadata. Title and text extraction unchanged.

## Issues Encountered
None beyond the trafilatura API parameter adjustment above.

## User Setup Required

**Google Drive integration requires manual configuration before /ingest/drive works:**

**Option A (OAuth - default):**
1. Create OAuth desktop app credentials in Google Cloud Console
2. Enable Google Drive API
3. Download `credentials.json` and place at `GOOGLE_CREDENTIALS_PATH` (default: `./credentials.json`)
4. First call to `/ingest/drive` will open browser for OAuth consent

**Option B (Service Account):**
1. Create service account in Google Cloud Console
2. Enable Google Drive API
3. Download service account JSON key
4. Set `GOOGLE_AUTH_METHOD=service_account` and `GOOGLE_CREDENTIALS_PATH=./key.json` in `.env`
5. Share target Drive folder with the service account email address

Without credentials, `/ingest/drive` returns 200 with `"Drive auth failed: [Errno 2] No such file or directory: './credentials.json'"` in warnings — not a 500 error.

## Next Phase Readiness
- All 4 ingestion endpoints complete: text paste, file upload, blog URL, Google Drive
- Phase 1 Plan 3 (corpus status + retrieval smoke test) can proceed immediately
- Google Drive integration requires user credential setup before functional testing

## Self-Check: PASSED

- FOUND: bond/corpus/sources/url_source.py
- FOUND: bond/corpus/sources/drive_source.py
- FOUND: bond/models.py
- FOUND: bond/api/routes/corpus.py
- FOUND: .planning/phases/01-rag-corpus-onboarding/01-02-SUMMARY.md
- FOUND: commit 62ce266 (Task 1)
- FOUND: commit 9338c1d (Task 2)
- VERIFIED: All 4 /api/corpus/ingest/* routes registered in OpenAPI schema
- VERIFIED: /ingest/url with unreachable URL returns 200 with warnings (not 500)
- VERIFIED: /ingest/drive with missing credentials returns 200 with auth error in warnings (not 500)

---
*Phase: 01-rag-corpus-onboarding*
*Completed: 2026-02-22*
