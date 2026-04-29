# Feature: Close 2026-04-29 E2E Regressions

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to existing session/bootstrap ownership, SSE invariants, and the distinction between server-authoritative history and tab-local UI state.

## Feature Description

This workstream closes the remaining regressions left open by the comprehensive E2E sweep completed on 2026-04-29. The repo already fixed the first batch of issues discovered in live testing, but four user-facing follow-ups still block treating the current branch as a freshly revalidated sign-off candidate:

1. manual Author draft edits are still lost after reload or saved-session restore
2. writer `<thinking>` tokens still leak into the live draft stream and rendered Markdown
3. `Pobierz .md` still lacks deterministic browser-level validation and likely needs a small hardening pass
4. browser-only file upload validation remains ambiguous because the in-app browser harness stalled after file selection, even though backend ingest is already green

The goal is to close these without changing locked graph routing, without changing the SSE wire envelope, and without turning local draft edits into new backend persistence semantics.

## User Story

As an editor using Bond after v1 sign-off  
I want my local Author edits to survive reloads, the editor to stay free of leaked reasoning tokens, markdown export to be reliably downloadable, and file upload to be reproducibly verifiable in a real browser harness  
So that the final editorial workflow is trustworthy enough for fresh end-to-end sign-off

## Problem Statement

The remaining issues all sit in the trust layer between a technically working system and a system that is safe to sign off again:

- the backend correctly preserves Author session history, but the frontend has no tab-local persistence for manual edits that happen after `checkpoint_2`
- the writer prompt still explicitly asks for visible `<thinking>` output, and the backend only strips it after the full model response is complete, so raw stream tokens still hit the UI
- the markdown download button uses `Blob` + `createObjectURL()` + `<a download>`, but the current path was not yet validated with an actual download observer and revokes the object URL immediately after click
- the product file-upload path is already validated at API level, but the remaining E2E gap is browser automation itself: the harness needs to target the hidden `input[type=file]` directly instead of relying on the agent-browser chooser flow

These are not new product features. They are sign-off-blocking quality gaps in state persistence, streaming hygiene, and browser-observable validation.

## Solution Statement

Implement four coordinated fixes:

1. Add tab-scoped Author draft override persistence in `sessionStorage`, keyed by thread ID, and layer it over server history only when it is safe to do so.
2. Remove the explicit visible-`<thinking>` instruction from the writer prompt and add a stateful backend stream sanitizer so writer token streams never emit `<thinking>` content to clients, even across split chunks.
3. Harden the markdown export flow in `EditorPane` and prove it with Playwright download capture rather than DOM inspection.
4. Add a dedicated Playwright regression harness that covers manual Author persistence, markdown download, and corpus file upload using `set_input_files()` on the hidden file input.

## Feature Metadata

**Feature Type**: Bug Fix / Hardening  
**Estimated Complexity**: Medium  
**Primary Systems Affected**: frontend session restore/hydration, EditorPane, frontend stream consumer, backend SSE token parser, writer prompt surface, Playwright browser validation, root planning docs  
**Dependencies**: Next.js App Router, Zustand, browser `sessionStorage`, browser Blob/object-URL APIs, Playwright Python sync API

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `.planning/STATE.md` (lines 12-14, 207-232)
  - Why: live source-of-truth for the exact open regressions and the current next task.
- `.planning/PROJECT.md` (lines 15-19, 26-33)
  - Why: project-level sign-off language already distinguishes historyczny sign-off from the still-open follow-up.
- `.planning/REQUIREMENTS.md` (lines 5, 55-66)
  - Why: requirement mapping remains complete, but the branch is explicitly not a fresh revalidated sign-off candidate.
- `frontend/src/components/SessionProvider.tsx` (lines 1-30)
  - Why: bootstrap ownership is intentionally centralized here; do not reintroduce restore side effects elsewhere.
- `frontend/src/hooks/useSessionBootstrap.ts` (lines 31-69, 95-121)
  - Why: startup restore/polling flow already exists and must stay the single mount-time bootstrap path.
- `frontend/src/hooks/useSession.ts` (lines 17-26, 35-53, 117-165, 193-284)
  - Why: current storage keys, saved-session metadata, `/history` loading, and store hydration live here.
- `frontend/src/lib/streamRecovery.ts` (lines 15-30, 95-149)
  - Why: pure hydration decisions belong here; current logic overwrites draft from history unless the mode is a live recovery.
- `frontend/src/store/chatStore.ts` (lines 48-160)
  - Why: shared Author/Shadow state shape and store actions; any persistence overlay must respect this contract.
- `frontend/src/components/EditorPane.tsx` (lines 11-81)
  - Why: manual Author edits and markdown download both originate here.
- `frontend/src/hooks/useStream.ts` (lines 170-185, 208-248, 317-327, 418-554, 568-690)
  - Why: live token handling, writer draft reset, committed-session recovery, and stream/resume lifecycles live here.
- `bond/prompts/writer.py` (lines 37-73)
  - Why: current writer prompt explicitly asks the model to emit `<thinking>...</thinking>`.
- `bond/api/stream.py` (lines 86-139, 172-196)
  - Why: backend SSE event parser is the best place to suppress leaked writer tokens before they ever reach the browser.
- `bond/graph/nodes/writer.py` (lines 140-159)
  - Why: final cleanup already strips `<thinking>` after full generation; the stream fix must complement, not replace, this safety net.
- `bond/api/routes/chat.py` (lines 430-552)
  - Why: server history remains authoritative for persisted session state; local draft persistence must not mutate this contract.
- `frontend/src/components/CorpusAddForm.tsx` (lines 241-280, 481-555)
  - Why: file-upload success/error semantics are already correct in product code, and the hidden file input shape drives the harness design.
- `tests/unit/api/test_stream.py` (lines 13-174)
  - Why: existing stream-parser test file is the right place to lock the `<thinking>` sanitizer against chunk-splitting regressions.
- `tests/unit/api/test_corpus_file_ingest.py` (lines 13-70)
  - Why: confirms the backend file-ingest contract is already covered and should not be reopened unless browser validation finds a product bug.
- `scripts/playwright_detached_runtime_journey.py` (lines 41-88, 91-199, 221-260)
  - Why: existing Playwright harness already provides helper patterns for polling history, capturing artifacts, and tracking network requests.
- `e2e-fixtures/upload-sample.txt`
  - Why: existing local upload fixture should be reused instead of inventing a new browser-upload input file.

### New Files to Create

- `frontend/src/lib/draftPersistence.ts`
  - Purpose: safe `sessionStorage` helpers for tab-local Author draft overrides keyed by thread ID.
- `scripts/playwright_post_signoff_regressions.py`
  - Purpose: targeted browser regression harness for manual Author draft persistence, markdown download, and corpus file upload.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [MDN: Window.sessionStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage#basic_usage)
  - Specific section: basic usage and autosave example
  - Why: confirms page-session storage survives reloads/restores and matches the same-tab behavior we want for unsaved Author edits.
- [MDN: Web Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API)
  - Specific section: `sessionStorage` vs `localStorage`, synchronous behavior
  - Why: explains why this persistence should be tab-scoped and lightly debounced instead of written on every keystroke without restraint.
- [MDN: URL.createObjectURL()](https://developer.mozilla.org/en-US/docs/Web/API/URL/createObjectURL_static)
  - Specific section: object URL lifecycle
  - Why: the export flow depends on Blob-backed object URLs.
- [MDN: URL.revokeObjectURL()](https://developer.mozilla.org/en-US/docs/Web/API/URL/revokeObjectURL_static)
  - Specific section: revoke when you are finished using the object URL
  - Why: supports deferring cleanup until after the browser has had a real chance to start the download.
- [MDN: HTMLAnchorElement.download](https://developer.mozilla.org/en-US/docs/Web/API/HTMLAnchorElement/download)
  - Specific section: proposed filename and caveat that the property does not prove a download occurred
  - Why: means the sign-off check must observe an actual browser download event, not just the anchor attributes.
- [Playwright: Actions / Upload files](https://playwright.dev/docs/input#upload-files)
  - Specific section: `locator.setInputFiles()` and `filechooser` fallback
  - Why: the corpus upload harness should drive the hidden file input directly instead of reproducing the agent-browser chooser stall.
- [Playwright Python: Downloads](https://playwright.dev/python/docs/downloads)
  - Specific section: `page.expect_download()` and `download.save_as()`
  - Why: required for deterministic `Pobierz .md` validation.

### Patterns to Follow

**Single-owner bootstrap**

- `frontend/src/components/SessionProvider.tsx:1-30` and `frontend/src/hooks/useSessionBootstrap.ts:31-69` make startup restore a single-owner concern.
- Keep reload/bootstrap decisions there or in pure helpers they call. Do not re-spread restore side effects across random components.

**Pure hydration decisions**

- `frontend/src/lib/streamRecovery.ts:95-149` is already the decision layer for choosing history vs current UI state.
- Extend this with an explicit Author draft override input rather than inventing a second hydration policy elsewhere.

**Store access outside React**

- `frontend/src/hooks/useSession.ts:35-53` and `frontend/src/hooks/useStream.ts:183-185` use `useChatStore.getState()` / `setState()` for non-component flows.
- Reuse that pattern for thread-aware persistence helpers and stream-time cleanup.

**Backend streaming boundary**

- `bond/api/stream.py:86-139` already owns token extraction from LangGraph events.
- If a token must never reach any client, suppress it here instead of adding client-specific cleanup only in React.

**Browser harness style**

- `scripts/playwright_detached_runtime_journey.py:41-88` and `:91-199` already show the repo’s Python Playwright style: helper functions, explicit polling, screenshots, and request tracking.
- Mirror that style for the new regression harness instead of introducing a different browser stack.

**Planning-doc sync rule**

- Root `.planning/` files are the live source of truth per `AGENTS.md`.
- Update `.planning/STATE.md`, `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, and `.planning/ROADMAP.md` in the same patch only after the fixes and validation are actually complete.

**Anti-patterns to avoid**

- Do not persist manual Author edits into backend checkpoint/history storage; this is a client-local continuity fix, not a new server write contract.
- Do not store volatile draft overrides in `localStorage`; that would create cross-tab bleed and is the wrong scope for reload-only continuity.
- Do not clear the local Author draft override on every `resume`; preserve it for `approve_save` from `checkpoint_2`, and only discard it when a fresh writer pass starts.
- Do not change `StreamEvent` types, the SSE envelope, or graph routing functions to solve this.
- Do not treat `HTMLAnchorElement.download` or DOM mutation as proof that a file was downloaded.
- Do not block final sign-off on the in-app agent-browser file chooser once the Playwright harness proves real browser upload behavior.

---

## IMPLEMENTATION PLAN

### Phase 1: Tab-Local Author Draft Persistence

Preserve manual Author edits across reload and saved-session restore without changing server history semantics.

**Tasks:**

- Add a thread-scoped `sessionStorage` overlay for manual Author draft edits.
- Prefer that overlay over server history only when the session is not actively running a new writer pass.
- Ensure a fresh writer pass clears stale local overrides before new streamed draft content appears.

### Phase 2: Writer Stream Hygiene

Stop visible reasoning leakage at the source and at the streaming boundary.

**Tasks:**

- Remove the explicit visible-`<thinking>` requirement from the writer prompt.
- Add a backend token sanitizer in the SSE parser for writer tokens, including split-tag chunk handling.
- Keep final output cleanup in `writer.py` as defense-in-depth.

### Phase 3: Deterministic Browser Validation for Export and Upload

Turn the remaining browser-only ambiguities into reproducible pass/fail checks.

**Tasks:**

- Harden the markdown export flow if needed and validate it with Playwright download capture.
- Drive corpus upload through the hidden file input using Playwright `set_input_files()`.
- Reuse the existing local upload fixture and artifact conventions.

### Phase 4: Sign-off Revalidation and Planning Sync

Re-run the right commands, then update live project docs in the same patch.

**Tasks:**

- Run targeted unit tests for stream sanitization and existing ingest coverage.
- Run frontend lint/build.
- Run both the detached-runtime harness and the new regression harness.
- Update root `.planning/` files only after the branch is actually revalidated.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### CREATE `frontend/src/lib/draftPersistence.ts`

- **IMPLEMENT**: Add safe `sessionStorage` helpers for tab-local Author draft overrides keyed by thread ID. Store at minimum `draft`, `updatedAt`, and enough metadata to distinguish a manual Author override from ordinary server history.
- **PATTERN**: Mirror storage key parsing/validation style from `frontend/src/hooks/useSession.ts:17-19` and `:55-97`.
- **IMPORTS**: Reuse `SessionMode` only if it keeps the helper honest; otherwise keep the module minimal and browser-only.
- **GOTCHA**: Use `sessionStorage`, not `localStorage`. Per MDN, `sessionStorage` survives reloads/restores in the same tab, which is exactly the desired scope.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/EditorPane.tsx`

- **IMPLEMENT**: Persist manual Author edits through the new helper when the user edits the markdown draft. Keep this write path lightweight with a small debounce because Web Storage is synchronous.
- **IMPLEMENT**: Fold the markdown export hardening into the same component. Keep `Blob` + object URL + `<a download>`, but revoke the object URL asynchronously after click rather than in the same synchronous stack.
- **PATTERN**: Build on the existing controlled editor and export toolbar at `frontend/src/components/EditorPane.tsx:11-81`.
- **IMPORTS**: `useChatStore`, the draft persistence helper, and any timer refs needed for debounced writes.
- **GOTCHA**: Only persist manual Author edits for a real `threadId`. Do not persist while streaming, and do not let this helper treat Shadow content as Author draft state.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/lib/streamRecovery.ts`

- **IMPLEMENT**: Extend `buildSessionHydration()` so it can accept an optional Author draft override and prefer it over `history.draft` only when all of the following are true:
  - the session mode is `author`
  - the server session is not currently `running`
  - the override belongs to the same thread
  - the user is restoring a draft-review/completed Author workspace, not shadow content
- **PATTERN**: Keep this as a pure decision function; do not perform browser storage IO inside this module.
- **GOTCHA**: Never let a stale local override win during live recovery or while a new writer pass is in progress.
- **VALIDATE**: `cd frontend && npm run build`

### UPDATE `frontend/src/hooks/useSession.ts`

- **IMPLEMENT**: Resolve the thread’s local Author draft override before calling `buildSessionHydration()` and thread it through `hydrateSessionStores()`.
- **IMPLEMENT**: On `SessionHistoryNotFoundError`, clear any orphaned local draft override for that missing thread alongside the existing `sessionStorage` cleanup.
- **PATTERN**: Keep saved-session metadata handling (`saveSessionMeta`, `switchSession`) unchanged except where it needs to respect the new per-thread draft overlay.
- **GOTCHA**: Do not wipe another thread’s local override when the user switches sessions; the whole point is that they can return to it in the same tab.
- **VALIDATE**: `cd frontend && npm run build`

### UPDATE `frontend/src/hooks/useStream.ts`

- **IMPLEMENT**: Clear the local Author draft override when a fresh writer run actually starts for the thread, using the existing `node_start` handling for `writer` before `setDraft("")`.
- **IMPLEMENT**: Keep the current `checkpoint_2` hydration behavior, but do not eagerly clear local edits on every resume action; `approve_save` from `checkpoint_2` must preserve the user’s local post-edit draft.
- **PATTERN**: Extend the existing writer-node handling at `frontend/src/hooks/useStream.ts:317-327`.
- **GOTCHA**: The discard point is “new writer output begins”, not merely “a resume request was sent”.
- **VALIDATE**: `cd frontend && npm run build`

### UPDATE `bond/prompts/writer.py`

- **IMPLEMENT**: Remove the explicit instruction to emit visible `<thinking>...</thinking>` blocks. Replace it with a silent-planning instruction that preserves output formatting rules without asking the model to surface chain-of-thought.
- **PATTERN**: Keep the rest of the strict final-output formatting rules intact at `bond/prompts/writer.py:68-73`.
- **GOTCHA**: Do not weaken the `Meta-description` / H1 / “no code fence” requirements while editing the prompt.
- **VALIDATE**: `uv run pytest tests/unit/graph/test_writer_prompt_budget.py`

### UPDATE `bond/api/stream.py`

- **IMPLEMENT**: Add a small stateful sanitizer for writer token streams that suppresses text inside `<thinking>...</thinking>` before emitting `token` events.
- **IMPLEMENT**: Track the active business node from `on_chain_start` / `on_chain_end` and apply the sanitizer only while the active node is `writer`.
- **PATTERN**: Build on the existing `parse_stream_events()` loop and preserve current stage/node lifecycle emissions unchanged.
- **GOTCHA**: Handle split tags across multiple chunks. A naive `.replace()` per token is not sufficient.
- **VALIDATE**: `uv run pytest tests/unit/api/test_stream.py`

### UPDATE `tests/unit/api/test_stream.py`

- **IMPLEMENT**: Add regression cases for:
  - a single writer chunk containing both `<thinking>` and visible output
  - split opening/closing thinking tags across multiple writer chunks
  - non-writer token streams staying untouched
- **PATTERN**: Reuse the existing async generator test style already used in this file.
- **GOTCHA**: The assertions should check emitted SSE `token` payloads, not the internal helper state.
- **VALIDATE**: `uv run pytest tests/unit/api/test_stream.py`

### UPDATE `tests/unit/graph/test_writer_prompt_budget.py`

- **IMPLEMENT**: Add a narrow assertion that the writer prompt no longer explicitly requires visible `<thinking>` output.
- **PATTERN**: Keep this test lightweight and string-level; do not over-couple it to unrelated prompt wording.
- **GOTCHA**: Assert the contract, not the whole prompt body.
- **VALIDATE**: `uv run pytest tests/unit/graph/test_writer_prompt_budget.py`

### CREATE `scripts/playwright_post_signoff_regressions.py`

- **IMPLEMENT**: Add a targeted Python Playwright harness covering all remaining open browser-level gaps:
  - Author flow to `checkpoint_2`
  - manual edit of the draft with a sentinel string
  - page reload and restored session preserving that sentinel
  - `checkpoint_2` continuation path proving local edits survive `approve_save`
  - a fresh writer rerun path proving stale local override is cleared before new draft output
  - markdown export captured with `page.expect_download()` and file-content assertion
  - corpus file upload through the hidden `input[type=file]` using `set_input_files()` with `e2e-fixtures/upload-sample.txt`
- **PATTERN**: Reuse helper structure from `scripts/playwright_detached_runtime_journey.py:41-88` and `:91-199`.
- **IMPORTS**: `sync_playwright`, `Path`, `json`, `time`, and any helper dataclasses you need for output dirs / network tracking.
- **GOTCHA**: This script is the replacement for the ambiguous agent-browser file chooser path. Target the hidden input directly and save download artifacts before the browser context closes.
- **VALIDATE**: `uv run python scripts/playwright_post_signoff_regressions.py --frontend-url http://127.0.0.1:3000 --api-url http://127.0.0.1:8000`

### UPDATE `.planning/STATE.md`

- **IMPLEMENT**: Replace the current open E2E follow-up bullets only after the code, tests, and browser harnesses are green. Record the actual revalidation date and what specifically was proven.
- **PATTERN**: Follow the live-status style already used in `.planning/STATE.md:12-16` and `:207-232`.
- **GOTCHA**: Do not mark the branch as a fresh sign-off candidate before both Playwright harnesses and the required validation commands succeed.
- **VALIDATE**: `uv run pytest && cd frontend && npm run lint && npm run build`

### UPDATE `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, AND `.planning/ROADMAP.md`

- **IMPLEMENT**: Sync the project-level narrative with the new validated state once the regression work is actually closed.
- **PATTERN**: Preserve the distinction between historical v1 sign-off and fresh revalidation language already present in these files.
- **GOTCHA**: Historical reports such as `.planning/E2E_REPORT_2026-04-28.md` are snapshots, not live status files.
- **VALIDATE**: `uv run pytest && cd frontend && npm run lint && npm run build`

---

## TESTING STRATEGY

The repo does not currently have a dedicated frontend unit-test runner. Do not introduce Vitest/Jest just for this remediation unless implementation complexity forces it. Prefer:

1. pure frontend decision logic kept in small helpers
2. backend unit tests for stream sanitization
3. Playwright browser validation for the actual user journeys

### Unit Tests

- Extend `tests/unit/api/test_stream.py` to lock the writer-token sanitizer against chunk-splitting regressions.
- Add a narrow assertion in `tests/unit/graph/test_writer_prompt_budget.py` so visible `<thinking>` output does not get reintroduced by prompt drift.
- Keep `tests/unit/api/test_corpus_file_ingest.py` in the targeted test run because it already proves the backend file-ingest contract.

### Integration Tests

- Re-run `scripts/playwright_detached_runtime_journey.py` to ensure the older detached-runtime/recovery guarantees were not broken while fixing current regressions.
- Run the new `scripts/playwright_post_signoff_regressions.py` for the remaining browser-only gaps.

### Edge Cases

- Manual Author draft edit survives reload in the same tab.
- Restored Author session preserves the local edited draft without reintroducing Shadow content leakage.
- Local draft override is discarded when a new writer pass starts, so stale sentinel text does not contaminate regenerated output.
- Split `<thinking>` tags across multiple streamed writer chunks never reach the browser.
- `approve_save` from `checkpoint_2` does not silently discard local edited draft continuity.
- `Pobierz .md` yields a real download with the expected filename and matching file contents.
- Hidden file input upload works via Playwright `set_input_files()` without depending on agent-browser chooser behavior.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and reliable browser-level sign-off.

### Level 1: Syntax & Style

- `cd frontend && npm run lint`

### Level 2: Targeted Unit Tests

- `uv run pytest tests/unit/api/test_stream.py`
- `uv run pytest tests/unit/graph/test_writer_prompt_budget.py`
- `uv run pytest tests/unit/api/test_corpus_file_ingest.py`

### Level 3: Full Regression Safety

- `uv run pytest`
- `cd frontend && npm run build`

### Level 4: Browser Validation

- `uv run python scripts/playwright_detached_runtime_journey.py --frontend-url http://127.0.0.1:3000 --api-url http://127.0.0.1:8000`
- `uv run python scripts/playwright_post_signoff_regressions.py --frontend-url http://127.0.0.1:3000 --api-url http://127.0.0.1:8000`

### Level 5: Manual Spot Checks

1. Open Author mode, reach `checkpoint_2`, manually edit the draft, reload the page, and confirm the edit remains.
2. From the same browser tab, reopen the saved Author session from the sidebar and confirm the local edit still wins over server history.
3. Reject the draft to force a fresh writer pass and confirm the old manual sentinel does not survive into the new generated draft.
4. Click `Pobierz .md` and confirm the downloaded file content matches the visible draft.
5. Upload `e2e-fixtures/upload-sample.txt` through the corpus file tab and confirm the file name preview, submit path, and success state are observable.

---

## ACCEPTANCE CRITERIA

- [ ] Manual Author draft edits survive same-tab reload and saved-session restore.
- [ ] Local Author draft overrides never leak into Shadow mode or a different thread.
- [ ] Fresh writer passes clear stale local overrides before new draft tokens appear.
- [ ] No `<thinking>` text is visible during live writer streaming, at `checkpoint_2`, after restore, or in the completed editor.
- [ ] Stream-sanitizer unit tests cover split-tag chunking and pass.
- [ ] `Pobierz .md` produces a real downloaded file with the expected filename and contents.
- [ ] Corpus file upload is reproducibly validated in Playwright using the hidden file input.
- [ ] Existing detached-runtime/recovery validation still passes after these changes.
- [ ] Root `.planning/` docs are updated in the same patch after validation is green.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] Targeted unit tests executed successfully
- [ ] Full `uv run pytest` suite passes
- [ ] Frontend lint and build pass
- [ ] Existing detached-runtime harness passes
- [ ] New post-signoff regression harness passes
- [ ] Manual spot checks confirm browser behavior
- [ ] Root planning docs reflect the actual validated repo state

---

## NOTES

- This is intentionally a tab-local continuity fix, not a server-side “save edited draft” feature. If future requirements demand cross-device or cross-tab persistence of manual edits, that is a separate API/product change.
- The recommended place to suppress leaked writer reasoning is the backend SSE parser, because that protects every client and is testable in Python.
- The prompt change and the SSE sanitizer should ship together. The prompt change reduces the chance of leakage; the sanitizer makes leakage impossible to render even if the prompt regresses later.
- The export hardening around `revokeObjectURL()` is partly an inference from observed browser behavior plus MDN’s lifecycle guidance; the real source of truth for sign-off is the Playwright download assertion.
- Confidence Score: 8/10 for one-pass implementation success.
