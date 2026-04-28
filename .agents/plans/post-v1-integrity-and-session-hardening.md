# Feature: Post-v1 Integrity and Session Hardening

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

This workstream closes the remaining post-v1 issues left open after the 2026-04-28 E2E pass:

1. historical drift between SQLite `metadata_log` and the Chroma duplicate-topic collection
2. saved sessions do not persist enough mode metadata to reliably reopen the correct UI route
3. the frontend stream transport treats every `!response.ok` as if it were a committed-disconnect recovery case
4. file ingest can return `chunks_added=0`, while the frontend still shows a success banner

The goal is to finish the medium-priority integrity and UX hardening without changing the locked graph routing or the SSE envelope, and without introducing hidden startup mutations.

## User Story

As an editor or operator using Bond after v1 sign-off  
I want duplicate-topic metadata to stay complete, restored sessions to reopen in the correct mode, stream errors to be classified honestly, and failed file ingests to surface clearly  
So that the app remains trustworthy in day-to-day use and follow-up validation can treat these areas as closed

## Problem Statement

The repo is functionally in good shape, but the remaining open issues still affect trust:

- duplicate detection can miss older published topics because one historical SQLite record has no Chroma embedding
- a restored thread can briefly or permanently land in the wrong mode because local session metadata stores only `id`, `title`, and `updatedAt`
- HTTP 4xx/5xx responses are not disconnects, but `useStream.ts` still routes them into history recovery when a thread ID is present
- the corpus file-upload flow ignores the backend payload and reports success on `chunks_added=0`, even when the backend explicitly returns warnings

These are not architectural blockers, but they touch data integrity, route correctness, and user trust. They should be fixed deliberately and verified with both automated tests and targeted manual validation.

## Solution Statement

Implement four coordinated fixes:

1. Add an explicit, idempotent duplicate-metadata reconciliation path that backfills missing Chroma records from SQLite by `thread_id`, and make metadata writes safe to rerun.
2. Extend the session/history contract to carry `mode`, persist that mode in local session metadata, and route restored sessions to `/` or `/shadow` accordingly.
3. Treat `!response.ok` as terminal HTTP failure, not committed recovery; keep history recovery only for a 2xx stream that disconnects after command commitment.
4. Keep the backend file-ingest contract as `200 + warnings + chunks_added`, but make the frontend honor it and stop showing success when zero chunks were indexed.

## Feature Metadata

**Feature Type**: Hardening / Bug Fix  
**Estimated Complexity**: Medium  
**Primary Systems Affected**: Chroma duplicate-topic store, SQLite metadata log, validation/admin scripts, chat history contract, session bootstrap, frontend stream transport, corpus upload UX, post-v1 planning docs  
**Dependencies**: ChromaDB 1.5.1, FastAPI, Next.js App Router, browser Fetch API, local/session storage

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `e2e-test-report.md` (lines 98-129)
  - Why: Canonical list of the remaining runtime issue plus the three code-analysis findings still open.
- `.planning/STATE.md` (lines 8-14, 167-183)
  - Why: Live source-of-truth says v1 is signed off and identifies SQLite↔Chroma drift as the next task; these lines must change when the work is complete.
- `.planning/PROJECT.md` (lines 15-27)
  - Why: Post-v1 duplicate-store reconciliation is still marked active here.
- `bond/store/chroma.py` (lines 51-82)
  - Why: Metadata collection singleton and current `add` / `delete` helpers live here.
- `bond/db/metadata_log.py` (lines 40-94)
  - Why: Current SQLite metadata helpers support insert, delete-by-row-id, and recent-list reads only.
- `bond/graph/nodes/save_metadata.py` (lines 12-65)
  - Why: Current dual-write path already compensates on new-write failure; the reconciliation work must complement this rather than replace it.
- `bond/validation/threshold_calibration.py` (lines 181-199, 589-670)
  - Why: Existing post-v1 analysis already loads SQLite and Chroma metadata topics and emits drift warnings; reuse its discovery patterns instead of re-inventing them.
- `scripts/reindex_corpus.py` (lines 1-106)
  - Why: Existing dry-run / `--apply` admin script pattern to mirror for metadata reconciliation.
- `bond/api/routes/chat.py` (lines 430-549)
  - Why: `/api/chat/history/{thread_id}` is the public recovery contract and currently omits `mode`.
- `bond/schemas.py` (lines 28-61)
  - Why: Public API/schema pattern uses `ConfigDict(extra="forbid")`; any new history response model should follow this.
- `frontend/src/hooks/useSession.ts` (lines 13-205)
  - Why: Local session metadata contract, thread/mode persistence, and `switchSession()` behavior all live here.
- `frontend/src/hooks/useSessionBootstrap.ts` (lines 17-109)
  - Why: Centralized restore path currently trusts `MODE_KEY` before it knows server truth.
- `frontend/src/components/Sidebar.tsx` (lines 13-27, 46-59)
  - Why: Saved-session switching currently has no route-aware mode handling.
- `frontend/src/components/StageProgress.tsx` (lines 21-127)
  - Why: UI stepper rendering depends on `useChatStore().mode`, so wrong mode means visibly wrong progress UX.
- `frontend/src/hooks/useStream.ts` (lines 381-545, 560-682)
  - Why: Request establishment, HTTP error handling, committed recovery, and public `startStream` / `resumeStream` APIs live here.
- `frontend/src/lib/streamRecovery.ts` (lines 10-145)
  - Why: Existing recovery type contract and hydration helpers should absorb any new `mode` field or recovery decision changes.
- `bond/api/routes/corpus.py` (lines 69-113)
  - Why: File ingest intentionally returns `warnings` plus `chunks_added`, including the zero-chunk path.
- `frontend/src/components/CorpusAddForm.tsx` (lines 201-233, 318-335, 529-531)
  - Why: File upload currently discards the JSON payload and only has success/error banners.
- `tests/unit/api/test_chat_history.py` (lines 27-115)
  - Why: Existing history endpoint test pattern to extend with `mode`.
- `tests/unit/graph/test_save_metadata.py` (lines 17-80)
  - Why: Existing metadata save durability tests must remain green after idempotency changes.
- `tests/unit/api/test_corpus_url_ingest.py` (lines 12-176)
  - Why: FastAPI + monkeypatch API test pattern to mirror for new file-ingest tests.
- `tests/unit/validation/test_threshold_calibration.py` (lines 81-107)
  - Why: Existing validation-layer test style already asserts drift warning semantics.

### New Files to Create

- `bond/validation/duplicate_metadata_reconciliation.py`
  - Purpose: Pure reconciliation/diff logic between SQLite metadata rows and Chroma duplicate-topic records.
- `scripts/reconcile_duplicate_metadata.py`
  - Purpose: Dry-run and `--apply` CLI for backfilling historical Chroma records from SQLite.
- `tests/unit/validation/test_duplicate_metadata_reconciliation.py`
  - Purpose: Unit tests for diff detection, backfill application, and idempotent reruns.
- `tests/unit/api/test_corpus_file_ingest.py`
  - Purpose: Lock the backend file-ingest contract for both zero-chunk warning and positive ingest paths.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [Chroma Python Collection Reference](https://docs.trychroma.com/reference/python/collection)
  - Specific section: `add`, `get`, `upsert`, `delete`
  - Why: `add` raises if an ID already exists, while reconciliation wants idempotent `upsert` and targeted delete semantics.
- [MDN: Using the Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)
  - Specific section: Handling the response / checking response status
  - Why: Confirms that `fetch()` fulfills on HTTP 4xx/5xx and only rejects on network-like failures; this is the basis for fixing `!response.ok` handling.
- [MDN: Response.ok](https://developer.mozilla.org/en-US/docs/Web/API/Response/ok)
  - Specific section: `ok` boolean semantics
  - Why: Confirms `ok` is strictly “status in the 200-299 range,” not “request committed and should be recovered.”
- [Next.js App Router `useRouter`](https://nextjs.org/docs/app/api-reference/functions/use-router)
  - Specific section: `router.push()` / `router.replace()`
  - Why: Needed to route restored sessions to `/` or `/shadow` from client components and bootstrap hooks.

### Patterns to Follow

**Public schema pattern**

- `bond/schemas.py:28-61` uses `ConfigDict(extra="forbid")` for public payloads.
- If `/api/chat/history/{thread_id}` gets a typed response model, it should live in `bond/schemas.py` and follow the same pattern.

**Chroma singleton pattern**

- `bond/store/chroma.py:51-82` centralizes metadata collection access.
- Do not instantiate `PersistentClient` or `HttpClient` inside reconciliation/business logic.

**SQLite schema-on-connect pattern**

- `bond/db/metadata_log.py:16-37` ensures the schema on every connection.
- Any new metadata read helper should reuse this module rather than opening ad hoc sqlite connections elsewhere in app code.

**Admin script pattern**

- `scripts/reindex_corpus.py:1-106` defaults to dry-run and requires `--apply` for writes.
- Reconciliation should follow the same operator safety pattern.

**Frontend session ownership**

- `frontend/src/components/SessionProvider.tsx` and `frontend/src/hooks/useSessionBootstrap.ts` own restore-time side effects.
- Avoid spreading restore/navigation decisions across many components.

**Recovery helper pattern**

- `frontend/src/lib/streamRecovery.ts:70-145` already owns recovery typing and hydration decisions.
- Extend it where the decision is pure; keep browser/network IO inside `useStream.ts`.

**Anti-patterns to avoid**

- Do not auto-mutate Chroma at app startup to “self-heal” drift.
- Do not infer mode from the currently open route alone when switching sessions.
- Do not recover from ordinary HTTP validation/server errors as if they were body disconnects.
- Do not rewrite historical E2E report snapshots as if they were live planning docs.

---

## IMPLEMENTATION PLAN

### Phase 1: Duplicate-Store Reconciliation Foundation

Make historical SQLite↔Chroma drift observable, repairable, and safe to rerun.

**Tasks:**

- Add row-level metadata readers/diff logic keyed by `thread_id`.
- Prefer idempotent Chroma writes for reconciliation and future resilience.
- Ship an explicit dry-run/apply CLI instead of hidden startup repair.

### Phase 2: Session Mode Contract and Route Restoration

Extend the history/session contract so saved sessions can reopen the correct mode and route deterministically.

**Tasks:**

- Add `mode` to the public history payload.
- Persist `mode` in local session metadata.
- Route restored and switched sessions to `/` or `/shadow` using App Router navigation.

### Phase 3: Transport and Ingest UX Hardening

Tighten frontend error classification and align corpus upload messaging with backend semantics.

**Tasks:**

- Treat `!response.ok` as terminal HTTP failure.
- Keep committed recovery only for interrupted 2xx SSE streams.
- Read file-ingest payloads and surface zero-chunk results as warning/error, not success.

### Phase 4: Validation and Planning Docs Sync

Verify each fix, then update root planning docs in the same patch.

**Tasks:**

- Add unit tests for reconciliation and file-ingest semantics.
- Re-run targeted backend/frontend validation.
- Update `.planning/STATE.md`, `.planning/PROJECT.md`, and `.planning/ROADMAP.md` after the code/test state actually changes.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### UPDATE `bond/store/chroma.py`

- **IMPLEMENT**: Make metadata writes idempotent for reconciliation-safe use:
  - either change `add_topic_to_metadata_collection()` to use `collection.upsert(...)`
  - or add a new explicit helper such as `upsert_topic_in_metadata_collection(...)` and migrate all callers intentionally
- **IMPLEMENT**: Keep targeted delete helper semantics by `thread_id`
- **PATTERN**: Reuse `get_or_create_metadata_collection()` (`bond/store/chroma.py:51-82`)
- **GOTCHA**: Chroma `add` raises when an ID already exists; dry-run/apply reconciliation must be repeatable without duplicate-ID failures
- **VALIDATE**: `uv run ruff check bond/store/chroma.py`

### UPDATE `bond/db/metadata_log.py`

- **IMPLEMENT**: Add a deterministic read helper for all metadata rows needed by reconciliation, for example `get_all_article_metadata()` returning `id`, `thread_id`, `topic`, `published_date`, `mode`
- **PATTERN**: Reuse `_ensure_schema()` and the existing async connection pattern (`bond/db/metadata_log.py:16-37`, `40-94`)
- **GOTCHA**: Preserve existing `delete_article_metadata(row_id)` semantics; reconciliation needs additional reads, not a new persistence abstraction
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/test_metadata_log_async.py -q`

### CREATE `bond/validation/duplicate_metadata_reconciliation.py`

- **IMPLEMENT**: Add pure functions that:
  - load SQLite metadata rows via `bond.db.metadata_log`
  - load Chroma records via `get_or_create_metadata_collection().get(include=["documents", "metadatas"])`
  - diff by `thread_id`
  - report `missing_in_chroma`, `orphaned_in_chroma`, and counts
  - optionally apply backfill for `missing_in_chroma` only
- **PATTERN**: Mirror the post-v1 validation style from `bond/validation/threshold_calibration.py:181-199` and `589-670`
- **GOTCHA**: Diff by stable identifier (`thread_id`), not by topic text; topics can contain newlines and are not guaranteed unique
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/validation/test_duplicate_metadata_reconciliation.py -q`

### CREATE `scripts/reconcile_duplicate_metadata.py`

- **IMPLEMENT**: Add an operator CLI with:
  - dry-run by default
  - `--apply` to write missing Chroma records
  - concise stdout summary of counts and sample IDs
- **PATTERN**: Mirror `scripts/reindex_corpus.py:1-106`
- **GOTCHA**: Do not mutate anything unless `--apply` is explicitly passed
- **VALIDATE**: `uv run python scripts/reconcile_duplicate_metadata.py`

### CREATE `tests/unit/validation/test_duplicate_metadata_reconciliation.py`

- **IMPLEMENT**: Add tests for:
  - detecting `missing_in_chroma`
  - detecting `orphaned_in_chroma`
  - applying a backfill only for missing IDs
  - idempotent rerun producing no duplicate writes
- **PATTERN**: Follow the focused pure-function style of `tests/unit/validation/test_threshold_calibration.py:81-107`
- **GOTCHA**: Mock the Chroma collection object; do not depend on the real persistent local collection in unit tests
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/validation/test_duplicate_metadata_reconciliation.py -q`

### UPDATE `bond/schemas.py`

- **IMPLEMENT**: Add a typed history response model, e.g. `ChatHistoryResponse`, with `ConfigDict(extra="forbid")`
- **IMPLEMENT**: Include a `mode: Literal["author", "shadow"]` field in that public contract
- **PATTERN**: Mirror `StreamEvent` / `CheckpointResponse` structure (`bond/schemas.py:28-61`)
- **GOTCHA**: Keep existing SSE event types unchanged; this task is about `/history`, not the streaming envelope
- **VALIDATE**: `uv run ruff check bond/schemas.py`

### UPDATE `bond/api/routes/chat.py`

- **IMPLEMENT**: Return `mode` from `/api/chat/history/{thread_id}` using checkpoint state truth (`st.get("mode", "author")`)
- **IMPLEMENT**: Wire the route to the new response model if one is introduced
- **PATTERN**: Preserve the current recovery metadata (`session_status`, `pending_node`, `can_resume`, `active_command`, `error_message`) from `bond/api/routes/chat.py:430-549`
- **GOTCHA**: Old sessions may not have `mode` in every state snapshot; default conservatively to `"author"` only when the field is truly absent
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/api/test_chat_history.py -q`

### UPDATE `tests/unit/api/test_chat_history.py`

- **IMPLEMENT**: Extend existing assertions so history payloads explicitly include `mode`
- **IMPLEMENT**: Cover at least:
  - completed author session returns `mode="author"`
  - paused/running shadow sessions return `mode="shadow"`
- **PATTERN**: Reuse the existing mocked `MockStateSnapshot` setup (`tests/unit/api/test_chat_history.py:27-115`)
- **GOTCHA**: Do not assert on unrelated history fields unless the new mode behavior depends on them
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/api/test_chat_history.py -q`

### UPDATE `frontend/src/lib/streamRecovery.ts`

- **IMPLEMENT**: Extend `SessionHistoryResponse` with `mode: "author" | "shadow"`
- **IMPLEMENT**: Keep pure hydration logic here, but remove or simplify any recovery helper that encourages `!response.ok` to be treated as a disconnect
- **PATTERN**: Keep transport IO out of this file; this module should remain decision-logic only (`frontend/src/lib/streamRecovery.ts:66-145`)
- **GOTCHA**: Backward compatibility matters for persisted frontend state and history payloads; do not assume `mode` is always present until the backend change lands
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/hooks/useSession.ts`

- **IMPLEMENT**: Extend `SessionMeta` to include `mode`
- **IMPLEMENT**: Persist `mode` alongside `id`, `title`, and `updatedAt`
- **IMPLEMENT**: Make `switchSession()` mode-aware:
  - prefer local `session.mode` for immediate route choice
  - fall back to `history.mode` when local metadata is missing or old
- **PATTERN**: Keep `loadSessionHistory()` as the single hydrator (`frontend/src/hooks/useSession.ts:50-90`)
- **GOTCHA**: Existing `bond_sessions` entries in localStorage will not have `mode`; add a tolerant migration path instead of hard-failing JSON parse or property access
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/hooks/useSessionBootstrap.ts`

- **IMPLEMENT**: After loading history, reconcile `MODE_KEY`, Zustand `mode`, and the actual route using `router.replace(...)` when needed
- **PATTERN**: Keep bootstrap centralized here (`frontend/src/hooks/useSessionBootstrap.ts:17-109`)
- **IMPORTS**: `useRouter`, and if helpful `usePathname`, from `next/navigation`
- **GOTCHA**: Avoid bootstrap loops where route correction re-triggers restore logic or leaves `isRestoring` stuck true
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/Sidebar.tsx`

- **IMPLEMENT**: Use the saved session `mode` when switching from session history so the user lands on the correct page immediately
- **PATTERN**: Keep the sidebar as the click surface and `useSession()` as the data source (`frontend/src/components/Sidebar.tsx:13-27`, `46-59`)
- **GOTCHA**: Do not make the sidebar depend on stale `threadId` alone; the route must follow the selected session’s mode
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/hooks/useStream.ts`

- **IMPLEMENT**: Treat `!response.ok` as terminal HTTP failure:
  - read and surface the error body
  - do not call `recoverCommittedSession()` from this branch
- **IMPLEMENT**: Keep history recovery only for the case where `response.ok === true` and the SSE body ends unexpectedly after commitment
- **PATTERN**: Preserve the existing transport split: `openCommandStream()` for pre-response retries, `consumeStream()` for body consumption, `recoverCommittedSession()` for post-commit recovery (`frontend/src/hooks/useStream.ts:381-545`)
- **GOTCHA**: Fetch fulfills on HTTP 4xx/5xx; do not confuse “received headers” with “safe to recover the command”
- **VALIDATE**: `cd frontend && npm run lint`

### CREATE `tests/unit/api/test_corpus_file_ingest.py`

- **IMPLEMENT**: Add API tests for:
  - unsupported or unreadable file returns `200` with `chunks_added=0` and a warning
  - positive path returns `chunks_added>0`
- **PATTERN**: Mirror `FastAPI` + `TestClient` style from `tests/unit/api/test_corpus_url_ingest.py:12-176`
- **GOTCHA**: The backend contract should stay warning-based for parse failures; the UX fix happens in the frontend
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/api/test_corpus_file_ingest.py -q`

### UPDATE `frontend/src/components/CorpusAddForm.tsx`

- **IMPLEMENT**: Parse the JSON payload from `/api/corpus/ingest/file`
- **IMPLEMENT**: If `chunks_added === 0`:
  - do not set `justSucceeded`
  - do not show `Plik zaindeksowany`
  - surface the first backend warning or a fallback error/warning message
  - do not call `onSuccess()` because corpus counts did not change
- **IMPLEMENT**: Keep the positive path unchanged for `chunks_added > 0`
- **PATTERN**: Reuse existing banner state where possible (`frontend/src/components/CorpusAddForm.tsx:318-335`, `529-531`)
- **GOTCHA**: Avoid broadening scope into a full new notification system unless the component genuinely needs a third “warning” state
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE root planning docs

- **IMPLEMENT**: Update `.planning/STATE.md`, `.planning/PROJECT.md`, and `.planning/ROADMAP.md` in the same patch once code/tests/manual validation close the items
- **IMPLEMENT**: Replace stale drift counts (`4` vs `3`) with the new post-fix status or completion note
- **PATTERN**: Follow repo rule that root `.planning/` files, not historical reports, are the live source of truth
- **GOTCHA**: Do not rewrite `e2e-test-report.md` as if it were current status; leave it as a historical snapshot and move current truth into root planning docs
- **VALIDATE**: `git diff -- .planning/STATE.md .planning/PROJECT.md .planning/ROADMAP.md`

---

## TESTING STRATEGY

Use existing backend unit tests for persistence and API contracts, and use lint/build plus manual browser verification for the frontend because the repo does not currently include a dedicated frontend test runner.

### Unit Tests

- Add `tests/unit/validation/test_duplicate_metadata_reconciliation.py` for pure diff/backfill logic.
- Add `tests/unit/api/test_corpus_file_ingest.py` for backend file-ingest contract semantics.
- Extend `tests/unit/api/test_chat_history.py` for the new `mode` field.
- Keep `tests/unit/graph/test_save_metadata.py` green to ensure new idempotency work does not regress the dual-write path.

### Integration Tests

- Run the targeted chat/corpus/history unit suites together.
- Run the reconciliation CLI in dry-run mode against the local repo data.
- After `--apply`, verify SQLite and Chroma counts match and the CLI reports zero missing records on the next dry-run.

### Edge Cases

- SQLite and Chroma counts match globally but IDs still differ.
- Old localStorage session entries have no `mode`.
- A saved shadow session is opened while the user is currently on `/`.
- `fetch()` returns `422` or `500` with a body; the UI must show an error, not a recovery banner.
- File parse fails and returns `chunks_added=0` plus warnings.
- Reconciliation is run twice and must not create duplicate Chroma records.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and high confidence.

### Level 1: Syntax & Style

- `uv run ruff check .`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`

### Level 2: Unit Tests

- `PYTHONPATH=. uv run pytest tests/unit/api/test_chat.py tests/unit/api/test_chat_history.py tests/unit/api/test_corpus_url_ingest.py tests/unit/api/test_corpus_file_ingest.py -q`
- `PYTHONPATH=. uv run pytest tests/unit/graph/test_save_metadata.py tests/test_metadata_log_async.py -q`
- `PYTHONPATH=. uv run pytest tests/unit/validation/test_threshold_calibration.py tests/unit/validation/test_duplicate_metadata_reconciliation.py -q`

### Level 3: Focused Repo Regression

- `uv run pytest`

### Level 4: Manual Validation

- `uv run python scripts/reconcile_duplicate_metadata.py`
- `sqlite3 data/bond_metadata.db 'SELECT COUNT(*) FROM metadata_log;'`
- `uv run python -c "from chromadb import PersistentClient; c=PersistentClient(path='data/chroma'); print(c.get_collection('bond_metadata_log_v1').count())"`
- `uv run python scripts/reconcile_duplicate_metadata.py --apply`
- `uv run python scripts/reconcile_duplicate_metadata.py`
- Start backend: `uv run uvicorn bond.api.main:app --reload --port 8000`
- Start frontend: `cd frontend && npm run dev`
- In the browser:
  - open a saved Author session while on `/shadow` and verify automatic navigation to `/`
  - open a saved Shadow session while on `/` and verify automatic navigation to `/shadow`
  - force a `/api/chat/stream` or `/api/chat/resume` HTTP error and verify the UI shows a terminal error instead of a recovery banner
  - upload an unsupported or unreadable file and verify the form shows warning/error, not `Plik zaindeksowany`, and corpus counts stay unchanged

### Level 5: Additional Validation (Optional)

- If local browser automation is desired after implementation, rerun the existing detached-runtime harness and a focused manual session-switching pass:
  - `python3 scripts/playwright_detached_runtime_journey.py`

---

## ACCEPTANCE CRITERIA

- [ ] SQLite and Chroma duplicate-topic stores can be diffed and reconciled by a repeatable CLI
- [ ] Running reconciliation twice does not create duplicate Chroma entries
- [ ] `/api/chat/history/{thread_id}` returns a typed `mode` field
- [ ] Saved sessions reopen in the correct route and store mode for both Author and Shadow
- [ ] `!response.ok` no longer triggers committed-session recovery
- [ ] File ingest no longer shows success when `chunks_added=0`
- [ ] All listed validation commands pass
- [ ] Root `.planning/` docs reflect the new post-v1 status

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes
- [ ] No linting or Next build errors
- [ ] Manual validation confirms correct mode restoration and file-ingest UX
- [ ] Root planning docs updated in the same patch
- [ ] No stale “next task” references remain for duplicate-store drift

---

## NOTES

- Current live repo data shows the exact missing ID is `test-thread-001`; there are no orphaned Chroma IDs at the moment. Design reconciliation around generic drift anyway, not this one snapshot.
- Prefer an explicit admin/backfill command over automatic startup repair. Silent startup mutation makes debugging harder and can unexpectedly write embeddings during local boot.
- Do not broaden this patch into a full frontend test-infrastructure adoption unless it becomes necessary. The repo currently relies on backend `pytest` plus frontend lint/build and browser validation.
- When the work is complete, the live source of truth should be the root `.planning/` files, not the dated E2E report.

**Confidence Score:** 9/10 that one-pass implementation will succeed if tasks are executed in order.
