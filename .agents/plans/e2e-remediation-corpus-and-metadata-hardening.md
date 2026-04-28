# Feature: Harden Corpus URL Ingestion and Metadata Durability

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

This workstream addresses the remaining backend hardening items from [.planning/E2E_REPORT_2026-04-28.md](.planning/E2E_REPORT_2026-04-28.md): URL ingestion currently accepts arbitrary URLs without visible SSRF protection, and metadata persistence is split across SQLite and Chroma without any application-level rollback strategy when the second write fails.

The goal is to make corpus URL ingestion safer by default and make metadata writes behave atomically from the application’s point of view, without rewriting the storage architecture.

## User Story

As an operator feeding external sources into Bond  
I want URL ingestion to reject unsafe internal targets and metadata writes to either succeed fully or fail cleanly  
So that the system is safer to expose and duplicate detection cannot silently drift out of sync

## Problem Statement

The E2E report flags two backend risks:

- `POST /api/corpus/ingest/url` accepts arbitrary URLs and passes them to sitemap discovery and fetch without host validation.
- `save_metadata_node()` first writes to SQLite and then writes to Chroma, so a Chroma failure leaves persisted relational metadata without a duplicate-detection embedding.

These are both medium-priority findings, but they affect data integrity and security boundaries rather than pure UX.

## Solution Statement

Add two targeted hardening layers:

1. Introduce a reusable public-URL validator for ingest paths that allows only safe `http/https` URLs resolving to public network addresses and re-validates any discovered sitemap URLs before fetch.
2. Add application-level rollback/compensation around the SQLite + Chroma metadata write sequence so the system no longer reports a successful metadata save when only one store was updated.

This keeps the current stack intact while removing the most important operational gaps.

## Feature Metadata

**Feature Type**: Hardening / Bug Fix  
**Estimated Complexity**: Medium  
**Primary Systems Affected**: Corpus ingest API, URL scraper, settings/config, metadata persistence, Chroma helpers, backend tests  
**Dependencies**: FastAPI, `urllib.parse`, `socket`, `ipaddress`, SQLite, ChromaDB

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `.planning/E2E_REPORT_2026-04-28.md` (lines 303-349)
  - Why: Source of the remaining security/integrity findings and their recommended priority.
- `bond/api/routes/corpus.py` (lines 116-126)
  - Why: `/api/corpus/ingest/url` is currently a thin pass-through with no SSRF validation.
- `bond/corpus/sources/url_source.py` (lines 15-96)
  - Why: Sitemap discovery and `trafilatura.fetch_url()` use unvalidated URLs today.
- `bond/config.py` (lines 3-35)
  - Why: New ingest hardening flags belong in the shared settings singleton.
- `bond/models.py` (lines 24-38)
  - Why: URL ingest request/response models may need stricter validation messaging.
- `bond/graph/nodes/save_metadata.py` (lines 12-42)
  - Why: This is the current two-store write sequence with no compensation path.
- `bond/db/metadata_log.py` (lines 16-62)
  - Why: Existing SQLite schema-on-connect and insert patterns should be extended, not replaced.
- `bond/store/chroma.py` (lines 51-76)
  - Why: Metadata collection helper exists here; any delete/compensation helper should live alongside it.
- `tests/test_metadata_log_async.py` (lines 24-108)
  - Why: Existing database test style to mirror for new rollback/durability tests.

### New Files to Create

- `bond/security/url_validation.py`
  - Purpose: Central public-URL validation and resolution guard reused by URL ingest.
- `tests/unit/api/test_corpus_url_ingest.py`
  - Purpose: Assert SSRF-blocking behavior and request validation semantics.
- `tests/unit/graph/test_save_metadata.py`
  - Purpose: Assert rollback/cleanup behavior when Chroma write fails after SQLite insert.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
  - Specific section: Validation and allow/deny rules for outbound requests
  - Why: Baseline SSRF defense guidance for URL fetch features.
- https://docs.python.org/3/library/urllib.parse.html
  - Specific section: `urlsplit()` and the security note on defensive validation
  - Why: Confirms Python URL parsing does not validate inputs for you.
- https://sqlite.org/atomiccommit.html
  - Specific section: Atomic commit model
  - Why: Useful for distinguishing SQLite transaction guarantees from cross-system write guarantees.
- https://docs.trychroma.com/reference/python/collection
  - Specific section: `add` and `delete`
  - Why: Needed for compensating cleanup on metadata collection writes.

### Patterns to Follow

**Settings pattern**

- New runtime knobs belong in `bond.config.settings`; do not instantiate `Settings()` elsewhere.

**Schema-on-connect SQLite pattern**

- `metadata_log.py` already initializes schema lazily on every connection. Extend this approach instead of creating a migration framework.

**Chroma singleton pattern**

- Reuse `get_or_create_metadata_collection()` and add complementary helpers beside it. Do not instantiate a new client in business logic.

**Logging pattern**

- One logger per module, warnings for rejected inputs or partial failures, no noisy logging inside hot request loops.

**Anti-patterns to avoid**

- Do not rely on `urllib.parse` alone as “validation”.
- Do not trust sitemap-discovered URLs without re-checking them.
- Do not claim true distributed atomicity across SQLite and Chroma; implement explicit compensation and document the guarantee correctly.

---

## IMPLEMENTATION PLAN

### Phase 1: SSRF Guard Foundation

Create a reusable validator for outbound ingest URLs and decide the default policy.

**Tasks:**

- Allow only `http` and `https`.
- Reject credentials in URLs, missing hosts, and hosts resolving to loopback/private/link-local/reserved IPs.
- Make the policy configurable only where there is a clear operational need; default should stay safe.

### Phase 2: Ingest Integration

Apply the validator consistently at the API boundary and again before network fetches.

**Tasks:**

- Validate the user-provided URL in `/api/corpus/ingest/url`.
- Re-validate every sitemap-discovered `post_url` before `trafilatura.fetch_url()`.
- Return clear, user-facing API errors instead of silent acceptance.

### Phase 3: Metadata Durability

Add application-level rollback/cleanup so a failed Chroma write does not leave the system in a misleading half-saved state.

**Tasks:**

- Add delete helpers for SQLite metadata rows and Chroma metadata collection records.
- Wrap the two-store write path with compensation.
- Add tests for the failure path.

### Phase 4: Validation and Documentation

Confirm safe URL rejection behavior and document the real durability guarantee.

**Tasks:**

- Add unit tests for bad URLs and rollback.
- Update troubleshooting/ops docs after implementation.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### CREATE `bond/security/url_validation.py`

- **IMPLEMENT**: Add a reusable validator that:
  - parses with `urllib.parse.urlsplit()`
  - allows only `http` / `https`
  - rejects empty hosts and embedded credentials
  - resolves DNS and rejects loopback, private, link-local, multicast, unspecified, and reserved IPs using `ipaddress`
- **PATTERN**: Keep the module dependency-light and synchronous so it can be reused at both API and scraper layers.
- **IMPORTS**: `socket`, `ipaddress`, `urllib.parse`, `dataclasses` or simple functions only.
- **GOTCHA**: Re-resolve discovered sitemap URLs too; validating only the entry URL is insufficient.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/api/test_corpus_url_ingest.py -q`

### UPDATE `bond/config.py`

- **IMPLEMENT**: Add narrowly scoped configuration flags only if needed, for example:
  - `allow_private_url_ingest: bool = False`
  - optional allowlist/denylist fields if the execution design truly uses them
- **PATTERN**: Keep safe defaults in the singleton settings object.
- **GOTCHA**: Do not over-configure before the validator behavior is clear; every new setting becomes operational surface area.
- **VALIDATE**: `uv run ruff check bond/config.py`

### UPDATE `bond/api/routes/corpus.py`

- **IMPLEMENT**: Validate `request.url` before calling `ingest_blog()`.
- **IMPLEMENT**: Return a clear `HTTPException(status_code=422 or 400)` when the URL is unsafe.
- **PATTERN**: Follow the existing explicit input validation style already used for empty text and invalid `source_type`.
- **GOTCHA**: Preserve current successful response models and warnings shape.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/api/test_corpus_url_ingest.py -q`

### UPDATE `bond/corpus/sources/url_source.py`

- **IMPLEMENT**: Re-validate:
  - the entry URL before sitemap discovery
  - every `post_url` discovered from `sitemap_search()`
- **IMPLEMENT**: Skip and warn on invalid discovered URLs rather than aborting the whole batch.
- **PATTERN**: Mirror the existing “skip and warn” behavior already used for extraction failures.
- **GOTCHA**: Avoid DNS resolution on every loop iteration when the exact same URL is repeated; basic memoization inside the validator is acceptable if needed.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/api/test_corpus_url_ingest.py -q`

### CREATE `tests/unit/api/test_corpus_url_ingest.py`

- **IMPLEMENT**: Add tests for:
  - rejecting `http://127.0.0.1/...`
  - rejecting `http://localhost/...`
  - rejecting cloud metadata-style/private addresses
  - rejecting non-HTTP schemes
  - allowing a mocked public `https://...` URL
- **PATTERN**: Keep tests focused on endpoint behavior and validator semantics with mocked DNS resolution/fetch.
- **IMPORTS**: `pytest`, `FastAPI`/`TestClient` if endpoint-level, plus `monkeypatch`.
- **GOTCHA**: Mock network resolution deterministically; do not depend on live DNS.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/api/test_corpus_url_ingest.py -q`

### UPDATE `bond/store/chroma.py`

- **IMPLEMENT**: Add a companion helper for deleting metadata collection entries by `thread_id`, e.g. `delete_topic_from_metadata_collection(thread_id: str)`.
- **PATTERN**: Keep it beside `add_topic_to_metadata_collection()` and reuse the singleton collection accessor.
- **GOTCHA**: Use Chroma’s `delete(ids=[...])` semantics, not a full collection rebuild.
- **VALIDATE**: `uv run ruff check bond/store/chroma.py`

### UPDATE `bond/db/metadata_log.py`

- **IMPLEMENT**: Add a targeted delete helper for rollback, e.g. by row id or `thread_id`.
- **IMPLEMENT**: Keep schema-on-connect intact and avoid introducing a new migration system.
- **PATTERN**: Mirror the existing async connection and commit style.
- **GOTCHA**: Make the delete helper idempotent so repeated rollback attempts do not fail noisily.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/test_metadata_log_async.py -q`

### UPDATE `bond/graph/nodes/save_metadata.py`

- **IMPLEMENT**: Wrap the SQLite insert + Chroma add sequence in explicit compensation logic:
  - write SQLite record
  - attempt Chroma add
  - on Chroma failure, delete the just-written SQLite record and re-raise or surface a controlled failure
- **IMPLEMENT**: Optionally add reverse cleanup if a later step fails after a Chroma write has already succeeded.
- **PATTERN**: Keep SQLite as the source-of-truth store and Chroma as the derived duplicate-detection index.
- **GOTCHA**: Document the guarantee honestly: this is application-level compensation, not distributed 2PC.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/graph/test_save_metadata.py -q`

### CREATE `tests/unit/graph/test_save_metadata.py`

- **IMPLEMENT**: Add tests for:
  - happy path: SQLite + Chroma both succeed
  - failure path: mocked Chroma add throws, SQLite row is removed/rolled back
- **PATTERN**: Mock `add_topic_to_metadata_collection()` and inspect the SQLite DB via existing helpers.
- **IMPORTS**: `pytest`, `pytest_asyncio`, `monkeypatch`, `AsyncMock` where helpful.
- **GOTCHA**: Do not rely on the real Chroma client in unit tests.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/graph/test_save_metadata.py -q`

### UPDATE documentation

- **IMPLEMENT**: Update README or operational notes to describe:
  - URL ingest safety restrictions
  - the actual metadata durability guarantee after compensation is introduced
- **PATTERN**: Keep user-facing copy concise and technical guidance explicit.
- **GOTCHA**: If configuration flags are added, document their secure defaults.
- **VALIDATE**: `git diff -- README.md .planning/E2E_REPORT_2026-04-28.md`

---

## TESTING STRATEGY

### Unit Tests

- Add deterministic tests for URL validation and save-metadata rollback behavior.
- Reuse temporary SQLite DB patterns from `tests/test_metadata_log_async.py`.

### Integration Tests

- Exercise `/api/corpus/ingest/url` with a mocked safe public URL.
- Confirm that unsafe URLs are rejected before network fetch is attempted.

### Edge Cases

- URL with credentials (`https://user:pass@example.com/...`)
- URL that resolves to multiple IPs, one of which is private
- Sitemap that mixes valid public posts with internal/private links
- Chroma failure after SQLite insert
- Repeated rollback call for the same failed write

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

- `uv run ruff check .`

### Level 2: Unit Tests

- `PYTHONPATH=. uv run pytest tests/unit/api/test_corpus_url_ingest.py -q`
- `PYTHONPATH=. uv run pytest tests/unit/graph/test_save_metadata.py tests/test_metadata_log_async.py -q`

### Level 3: Targeted API Validation

- `curl -X POST http://localhost:8000/api/corpus/ingest/url -H "Content-Type: application/json" -d '{"url":"http://127.0.0.1/test","source_type":"own"}'`
- `curl -X POST http://localhost:8000/api/corpus/ingest/url -H "Content-Type: application/json" -d '{"url":"https://example.com","source_type":"external"}'`

### Level 4: Manual Validation

1. Attempt URL ingest with a loopback/private URL and confirm the API rejects it immediately.
2. Attempt URL ingest with a safe public URL and confirm the scraper still runs.
3. Simulate a Chroma failure during metadata save and confirm no orphaned SQLite metadata remains afterward.

---

## ACCEPTANCE CRITERIA

- [ ] URL ingest rejects unsafe/internal/private targets before fetch.
- [ ] Sitemap-discovered post URLs are re-validated before extraction.
- [ ] Safe public URLs still ingest successfully.
- [ ] Metadata save no longer leaves a success-path SQLite row behind when the Chroma write fails.
- [ ] New tests cover both SSRF rejection and metadata compensation behavior.
- [ ] All validation commands pass.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Unsafe URL cases manually verified
- [ ] Metadata rollback path manually verified
- [ ] Acceptance criteria all met

---

## NOTES

- True cross-system atomicity is not available here without a distributed transaction or an outbox/reconciliation design. This plan intentionally chooses application-level compensation as the pragmatic fix.
- Keep the SSRF validator centralized. Do not scatter ad hoc hostname checks across route handlers and scraper code.
- This plan depends on the `thread_id` initialization fix from the streaming/HITL plan for full end-to-end confidence in metadata save flows.

**Confidence Score:** 8/10 for one-pass implementation success
