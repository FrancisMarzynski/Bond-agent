# Feature: Stabilize Browser Streaming, HITL Resume, and Session Contracts

## Execution Status

Status: COMPLETE (2026-04-28)

Implementation outcome:

- backend session contract, low-corpus HITL normalization, and history-driven recovery were delivered
- browser transport was validated live with Playwright on `http://localhost:3000/shadow`
- no replay of committed `POST /api/chat/stream` or `POST /api/chat/resume` was observed in the final run

Additional root causes discovered during live browser validation:

1. `frontend/src/lib/sse.ts` assumed `\n\n` separators only; browser `ReadableStream` delivered SSE frames with `\r\n\r\n`
2. `frontend/src/hooks/useStream.ts` attempted `JSON.parse()` on every string payload, which corrupted numeric token fragments such as `"144"`
3. `frontend/src/components/ShadowPanel.tsx` used `setThreadId` instead of `persistThreadId`, so Shadow did not store `bond_thread_id` in `sessionStorage`

Independent follow-up still recommended:

- rerun a dedicated Playwright journey for full Author mode, even though it now shares the repaired transport layer

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

This workstream fixes the highest-risk issues from [.planning/E2E_REPORT_2026-04-28.md](.planning/E2E_REPORT_2026-04-28.md): browser SSE reconnect currently replays non-idempotent `POST /api/chat/stream` and `POST /api/chat/resume` requests, Shadow HITL can get stuck after a duplicate resume, `thread_id` is not injected into the initial graph state even though downstream nodes assume it exists, and the low-corpus HITL gate does not follow the same contract as the rest of the pipeline.

The goal is to make Author and Shadow stable in the browser without changing the locked JSON SSE envelope or graph edge wiring. The implementation should treat `/stream` and `/resume` as command endpoints, not safe replay endpoints.

## User Story

As an editor using Author or Shadow in the browser  
I want generation and approval flows to recover predictably after transient disconnects  
So that a single action never replays the pipeline, wedges the session, or loses the ability to continue work

## Problem Statement

The E2E report shows that the frontend currently sends `Last-Event-ID` but the backend does not implement event replay based on that header. Instead, the frontend retries by issuing a fresh `POST` against the same command endpoint, which can duplicate graph execution or replay resume actions. This causes reconnect loops in Author and stuck loading after Shadow approval attempts. In parallel, `save_metadata_node` assumes `state["thread_id"]` exists while [bond/api/routes/chat.py](bond/api/routes/chat.py) does not place it in `initial_state`, and `writer_node` emits a boolean low-corpus interrupt with a non-standard payload, making the HITL surface inconsistent.

## Solution Statement

Refactor the browser streaming flow into a commit-aware transport state machine:

1. Treat a response-bearing `POST /stream` or `POST /resume` as a committed command, not something safe to replay.
2. Allow automatic retry only before the browser receives a streaming `Response`.
3. After a committed disconnect, recover via `GET /api/chat/history/{thread_id}` instead of issuing another `POST`.
4. Extend history/session payloads so the frontend can deterministically restore `running`, `paused`, and `completed` states.
5. Inject `thread_id` into `initial_state` and normalize the low-corpus gate to the same `approve_reject` contract used elsewhere.

This keeps the existing SSE JSON envelope intact, respects the locked graph routing, and avoids a full event-buffer/replay subsystem.

## Feature Metadata

**Feature Type**: Bug Fix / Hardening  
**Estimated Complexity**: High  
**Primary Systems Affected**: FastAPI chat routes, LangGraph HITL node contract, frontend streaming hook, Zustand chat/shadow state, session restore flow  
**Dependencies**: FastAPI, LangGraph, `sse-starlette`, browser Fetch/ReadableStream APIs, Zod/Zustand

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `.planning/E2E_REPORT_2026-04-28.md` (lines 17-30, 151-170, 181-215, 303-349)
  - Why: Source-of-truth for the observed regressions, priority, and reproduction evidence.
- `bond/api/routes/chat.py` (lines 301-410)
  - Why: `/stream` and `/resume` endpoint semantics, current `initial_state`, lock handling, and SSE emission lifecycle.
- `bond/api/routes/chat.py` (lines 413-497)
  - Why: `get_chat_history()` is the only recovery surface already available to the frontend.
- `frontend/src/hooks/useStream.ts` (lines 63-335, 354-404)
  - Why: Current parser, retry loop, `Last-Event-ID` header usage, and browser replay bug live here.
- `frontend/src/store/chatStore.ts` (lines 5-128)
  - Why: Existing streaming state shape, `isStreaming`, `isReconnecting`, and controller lifecycle patterns.
- `frontend/src/hooks/useSession.ts` (lines 50-163)
  - Why: Session restore already hydrates chat and shadow state from history; this is the pattern to reuse for recovery.
- `bond/schemas.py` (lines 28-61)
  - Why: Locked public `StreamEvent` contract and `CheckpointResponse` validation model.
- `bond/graph/nodes/checkpoint_1.py` (lines 15-86)
  - Why: Canonical HITL `approve_reject` interrupt payload and `CheckpointResponse` parsing pattern.
- `bond/graph/nodes/checkpoint_2.py` (lines 16-101)
  - Why: Same contract plus warning handling and iteration metadata.
- `bond/graph/nodes/duplicate_check.py` (lines 8-60)
  - Why: Existing warning-style HITL gate that already maps to `approve_reject`.
- `bond/graph/nodes/writer.py` (lines 300-338)
  - Why: Low-corpus gate currently violates the standard checkpoint payload shape.
- `bond/graph/nodes/save_metadata.py` (lines 20-42)
  - Why: Reads `state["thread_id"]` without fallback, so `initial_state` must provide it.
- `frontend/src/components/CheckpointPanel.tsx` (lines 21-244)
  - Why: Existing Author/duplicate checkpoint UI that should be extended rather than bypassed.
- `frontend/src/components/ShadowPanel.tsx` (lines 102-180)
  - Why: Existing Shadow approve/reject UI that currently depends on `resumeStream()`.
- `frontend/src/components/StageProgress.tsx` (lines 16-99)
  - Why: Banner surface for reconnect/recovery state and user-facing alerts.
- `tests/unit/api/test_chat.py` (lines 25-83)
  - Why: Existing API route streaming test pattern.
- `tests/unit/api/test_stream.py` (lines 13-174)
  - Why: Existing event parsing expectations for SSE contract tests.
- `frontend/scripts/test-sse.mjs` (lines 146-220)
  - Why: Existing Node-based smoke validation for streaming content type and parser behavior.

### New Files to Create

- `tests/unit/api/test_chat_history.py`
  - Purpose: Verify `get_chat_history()` recovery payloads for `running`, `paused`, and `completed` sessions.
- `tests/unit/graph/test_writer_low_corpus.py`
  - Purpose: Lock low-corpus HITL payload shape and resume behavior to the standard contract.
- `frontend/src/lib/streamRecovery.ts`
  - Purpose: Extract pure helper logic for classifying disconnects and hydrating store state from history responses.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch#streaming_the_response_body
  - Specific section: Streaming the response body
  - Why: Confirms the browser-side `Response.body` / `ReadableStream` semantics used in `useStream.ts`.
- https://developer.mozilla.org/en-US/docs/Web/API/AbortController/abort
  - Specific section: `abort()` behavior
  - Why: Confirms that aborting a controller cancels fetch, body consumption, and stream reading.
- https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
  - Specific section: Event framing and default `message` behavior
  - Why: Confirms that events without `event:` are delivered as `message`, which matches the current parser fallback.
- https://nextjs.org/docs/app/api-reference/config/next-config-js/rewrites
  - Specific section: Rewrites as URL proxy
  - Why: Confirms that Next rewrites proxy requests but do not themselves implement command replay or SSE event resume.

### Patterns to Follow

**Public schema pattern**

- Use `ConfigDict(extra="forbid")` for public payload models, mirroring `StreamEvent` and `CheckpointResponse` in `bond/schemas.py`.

**HITL payload pattern**

- All human review nodes should emit:

```python
interrupt({
    "checkpoint": "<node_name>",
    "type": "approve_reject",
    ...
})
```

- Resume values should validate through `CheckpointResponse`, as done in `checkpoint_1_node()` and `checkpoint_2_node()`.

**Frontend streaming ownership**

- `useStream.ts` is the single entry point for starting/resuming streams.
- `AbortController` ownership lives in Zustand, not in components.
- Session hydration from backend history already exists in `useSession.ts`; extend this pattern instead of creating a second restore path.

**Anti-patterns to avoid**

- Do not blindly replay a committed `POST /stream` or `POST /resume`.
- Do not change LangGraph edge wiring in `bond/graph/graph.py`.
- Do not change the locked outer SSE JSON envelope defined by `StreamEvent`.

---

## IMPLEMENTATION PLAN

### Phase 1: Contract Alignment Foundation

Make the backend session contract explicit enough for safe recovery and remove known state-shape inconsistencies.

**Tasks:**

- Inject `thread_id` into the Author and Shadow `initial_state` sent to LangGraph.
- Extend the history payload with explicit recovery metadata such as `session_status`, `pending_node`, and `can_resume`.
- Normalize the low-corpus gate in `writer_node()` to the same `approve_reject` payload contract as other checkpoints.

### Phase 2: Frontend Transport Refactor

Refactor the browser stream transport so retries happen only before command commitment, and recovery after commitment is history-driven instead of replay-driven.

**Tasks:**

- Extract disconnect classification and history hydration helpers into a small pure module.
- Split transport logic into:
  - request establishment
  - SSE consumption
  - post-commit recovery
- Remove the misleading `Last-Event-ID` retry path unless true backend replay is implemented in the same change.

### Phase 3: UI Recovery Integration

Make the UI reflect recovery state clearly and support the standardized low-corpus checkpoint.

**Tasks:**

- Add recovery/pending-action UI state so buttons do not allow duplicate resume actions during uncertain transport state.
- Extend `CheckpointPanel` to support the normalized `low_corpus` warning checkpoint.
- Keep Shadow and Author UIs hydrated from history without resetting user-facing content prematurely.

### Phase 4: Testing and Documentation Sync

Add targeted tests for the new recovery contract, then sync project docs so the observed behavior and invariants match the code.

**Tasks:**

- Add backend API tests for history payloads and thread id injection.
- Add writer-node tests for low-corpus checkpoint payload and resume behavior.
- Update `.planning/STATE.md`, `.planning/REQUIREMENTS.md`, and README troubleshooting only after code behavior is finalized.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### UPDATE `bond/api/routes/chat.py`

- **IMPLEMENT**: Add `"thread_id": thread_id` to `initial_state` in `chat_stream()`.
- **IMPLEMENT**: Extend `get_chat_history()` to return explicit recovery metadata:
  - `session_status`: `idle | running | paused | completed | error`
  - `pending_node`: current `next_nodes[0]` when available
  - `can_resume`: `true` only when the session is paused at a HITL checkpoint
- **IMPLEMENT**: Ensure fallback HITL payload construction is only used for actual paused checkpoints, not as a proxy for any running node.
- **PATTERN**: Mirror the existing response assembly style in `get_chat_history()` (`bond/api/routes/chat.py:423-497`).
- **GOTCHA**: Preserve `_RECURSION_LIMIT`, `_resume_locks`, and the current SSE JSON envelope.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/api/test_chat.py -q`

### CREATE `tests/unit/api/test_chat_history.py`

- **IMPLEMENT**: Add tests for:
  - completed author session history
  - paused shadow checkpoint history with `annotations` and `shadowCorrectedText`
  - running session history with `session_status="running"` and no fabricated `hitlPause`
- **PATTERN**: Reuse the mocked FastAPI app style from `tests/unit/api/test_chat.py`.
- **IMPORTS**: `FastAPI`, `TestClient`, `AsyncMock`, router/history function helpers.
- **GOTCHA**: Avoid asserting on unstable timestamps; assert on status and shape only.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/api/test_chat_history.py -q`

### UPDATE `bond/graph/nodes/writer.py`

- **IMPLEMENT**: Replace the boolean low-corpus `interrupt()` payload with a standard checkpoint payload:
  - `checkpoint="low_corpus"`
  - `type="approve_reject"`
  - include `warning`, `corpus_count`, `threshold`
- **IMPLEMENT**: Parse resume through `CheckpointResponse`; map `approve` to continue, `reject` and `abort` to terminate.
- **PATTERN**: Mirror `checkpoint_1_node()` and `checkpoint_2_node()` validation flow.
- **GOTCHA**: Do not change the low-corpus threshold logic itself; only normalize payload and response semantics.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/graph/test_writer_low_corpus.py -q`

### CREATE `tests/unit/graph/test_writer_low_corpus.py`

- **IMPLEMENT**: Add tests for:
  - interrupt payload shape
  - approve path continuing generation
  - reject/abort path returning a safe terminal result
- **PATTERN**: Mock `get_corpus_collection()` and `interrupt()` instead of invoking the full graph.
- **IMPORTS**: `pytest`, `monkeypatch`, `MagicMock` or `Mock`.
- **GOTCHA**: Keep tests focused on contract shape, not model output text.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/graph/test_writer_low_corpus.py -q`

### UPDATE `frontend/src/store/chatStore.ts`

- **IMPLEMENT**: Add explicit recovery state fields such as:
  - `isRecoveringSession`
  - `pendingAction: "stream" | "resume" | null`
- **IMPLEMENT**: Remove or deprecate `lastEventId` if it will no longer drive any real transport behavior.
- **PATTERN**: Keep controller lifecycle in the store, as currently done with `activeController`.
- **GOTCHA**: Do not overload `isStreaming` to mean both “actively consuming stream” and “recovering from uncertain transport”.
- **VALIDATE**: `cd frontend && npm run lint`

### CREATE `frontend/src/lib/streamRecovery.ts`

- **IMPLEMENT**: Extract pure helpers for:
  - deciding whether a failure happened pre-commit or post-commit
  - mapping history payloads into store mutations
  - deciding whether the UI should resume, stop, or keep polling
- **PATTERN**: Keep it framework-light and side-effect-free so `useStream.ts` stays as the orchestrator.
- **IMPORTS**: Only project types and narrow browser-independent helpers.
- **GOTCHA**: Do not embed React hooks into this file.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/hooks/useSession.ts`

- **IMPLEMENT**: Extract the history hydration logic into a reusable helper callable both on startup and after transport recovery.
- **IMPLEMENT**: Expose a safe recovery-oriented `loadSessionHistory()` path without resetting the session first.
- **PATTERN**: Reuse existing shadow hydration logic from `useSession.ts:57-80`.
- **GOTCHA**: Do not clear session storage during transient recovery attempts unless the backend explicitly reports missing state.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/hooks/useStream.ts`

- **IMPLEMENT**: Replace blind replay retry logic with a commit-aware flow:
  - retry only if `fetch()` fails before returning a `Response`
  - once a `Response` exists, treat the command as committed
  - on unexpected stream break after commitment, stop replaying `POST` and recover through history polling
- **IMPLEMENT**: Remove the `Last-Event-ID` header path unless backend replay is implemented in the same patch.
- **IMPLEMENT**: Preserve current parsing of `thread_id`, `token`, `stage`, `hitl_pause`, `done`, `error`, `shadow_corrected_text`, and `annotations`.
- **IMPLEMENT**: Support normalized `low_corpus` history/checkpoint hydration.
- **PATTERN**: Keep `useStream()` as the single public streaming hook and continue using Zustand-owned controllers.
- **GOTCHA**: Do not clear `hitlPause` permanently before a resume result is known; otherwise the UI loses the only actionable state during uncertain transport.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/CheckpointPanel.tsx`

- **IMPLEMENT**: Handle the new `low_corpus` checkpoint as a warning panel with approve/abort controls.
- **IMPLEMENT**: Respect `isRecoveringSession` / `pendingAction` so duplicate clicks are prevented while recovery is in progress.
- **PATTERN**: Reuse the existing warning-panel shape already used for `duplicate_check`.
- **GOTCHA**: Preserve current checkpoint_1 and checkpoint_2 affordances and labels.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/ShadowPanel.tsx`

- **IMPLEMENT**: Disable Shadow approve/reject affordances while a resume command is in recovery.
- **IMPLEMENT**: Ensure recovery via history rehydrates `annotations`, `shadowCorrectedText`, and `draft` without wiping the visible comparison view.
- **PATTERN**: Reuse the shadow hydration pattern already present in `useStream.ts` and `useSession.ts`.
- **GOTCHA**: Keep `handleReset()` behavior unchanged for intentional user resets.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/StageProgress.tsx`

- **IMPLEMENT**: Differentiate “reconnecting before command commitment” from “recovering committed session state”.
- **IMPLEMENT**: Show a clear banner when the frontend is restoring the session from history rather than replaying the command.
- **PATTERN**: Extend the current reconnect/system alert banner approach.
- **GOTCHA**: Do not regress the visibility of hard-cap alerts.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/scripts/test-sse.mjs`

- **IMPLEMENT**: Extend the script to assert that `/api/chat/history/{thread_id}` returns the new recovery fields after a seeded mock or a short real session.
- **PATTERN**: Follow the existing Node `test()` structure already used in the file.
- **GOTCHA**: Keep the script resilient when the API server is down; it should still skip gracefully.
- **VALIDATE**: `node frontend/scripts/test-sse.mjs --api-url http://localhost:8000`

### UPDATE project documentation

- **IMPLEMENT**: Sync `.planning/STATE.md`, `.planning/REQUIREMENTS.md`, and the SSE troubleshooting section in `README.md` so they describe the actual frontend recovery semantics and standardized low-corpus checkpoint.
- **PATTERN**: Keep Polish wording for user-facing behavior and technical clarity in planning docs.
- **GOTCHA**: Do not update docs until the implementation and tests are green.
- **VALIDATE**: `git diff -- .planning/STATE.md .planning/REQUIREMENTS.md README.md`

---

## TESTING STRATEGY

### Unit Tests

- Add focused backend tests for history state derivation and low-corpus checkpoint contract.
- Keep API tests mocked and deterministic; do not require real LLM or Chroma calls.

### Integration Tests

- Re-run `frontend/scripts/test-sse.mjs` against a live backend.
- Re-run the API unit suite with `PYTHONPATH=.` because the report shows the shorter invocation currently fails locally.

### Edge Cases

- Browser disconnect after `fetch()` returns a `Response` but before any terminal event arrives.
- Shadow `approve` disconnect after the backend has already begun processing `Command(resume=...)`.
- History endpoint called while a session is running but not paused.
- Low-corpus checkpoint shown in browser UI.
- Author flow reaching `save_metadata_node` with guaranteed `thread_id` present.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

- `uv run ruff check .`
- `cd frontend && npm run lint`

### Level 2: Unit Tests

- `PYTHONPATH=. uv run pytest tests/unit/api/test_chat.py tests/unit/api/test_stream.py tests/unit/api/test_chat_history.py -q`
- `PYTHONPATH=. uv run pytest tests/unit/graph/test_writer_low_corpus.py -q`

### Level 3: Integration Tests

- `node frontend/scripts/test-sse.mjs --api-url http://localhost:8000`
- `curl -N -H "Content-Type: application/json" -d '{"message":"transport smoke","mode":"shadow"}' http://localhost:8000/api/chat/stream`

### Level 4: Manual Validation

1. Start backend and frontend.
2. Run Author flow in browser, then simulate a transient network interruption after streaming starts.
3. Confirm the frontend does not issue repeated `POST /api/chat/stream`.
4. Run Shadow flow to `shadow_checkpoint`, click `Zatwierdź`, interrupt transport, and confirm the frontend recovers from history without replaying `POST /api/chat/resume`.
5. Trigger low-corpus gate and confirm the browser shows a standard warning checkpoint with explicit continue/abort actions.

### Level 5: Additional Validation (Optional)

- Re-run the browser-based E2E journey described in `.planning/E2E_REPORT_2026-04-28.md`.

---

## ACCEPTANCE CRITERIA

- [ ] Browser transport no longer replays committed `POST /api/chat/stream` requests.
- [ ] Browser transport no longer replays committed `POST /api/chat/resume` requests.
- [ ] Shadow approve/reject no longer gets stuck due to duplicate resume requests triggered by reconnect logic.
- [ ] `thread_id` is present in graph state from the moment the session starts.
- [ ] Low-corpus gate uses the same `approve_reject` contract as other HITL checkpoints.
- [ ] History endpoint returns enough explicit state for deterministic frontend recovery.
- [ ] All validation commands pass with zero errors.
- [ ] Documentation matches implemented behavior.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full relevant test suite passes
- [ ] No linting or type-checking regressions
- [ ] Manual browser validation confirms recovery behavior
- [ ] Acceptance criteria all met
- [ ] Docs updated after implementation

---

## NOTES

- Do not implement true SSE event replay in this workstream unless you are also prepared to add event ids, server-side buffering, and `Last-Event-ID` consumption end-to-end. That is a different architecture.
- The chosen approach is pragmatic: non-idempotent command endpoints must not be replayed after commitment; recovery happens from persisted graph state.
- This plan intentionally bundles `thread_id` injection and low-corpus contract cleanup because both are prerequisites for trustworthy browser-side HITL recovery.

**Confidence Score:** 8/10 for one-pass implementation success
