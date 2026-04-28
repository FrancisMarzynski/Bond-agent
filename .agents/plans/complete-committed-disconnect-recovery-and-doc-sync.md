# Feature: Complete Committed-Disconnect Recovery and Documentation Sync

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to existing transport invariants: do not change the outer SSE JSON envelope, do not change graph edge wiring, and do not regress the already-correct CRLF parser, numeric token handling, or Shadow checkpoint hydration.

## Feature Description

This follow-up closes the gap found during independent validation of the recent streaming/HITL remediation. The current codebase already fixes several real issues:

- browser SSE parsing now handles CRLF-delimited chunks
- nested payload parsing no longer corrupts numeric token strings like `"1"` or `"144"`
- Shadow persists `bond_thread_id` in `sessionStorage`
- frontend retries only before a streaming `Response` is received
- post-checkpoint restore hydrates Shadow annotations, corrected text, draft, and actions
- `low_corpus` now uses the same `approve_reject` contract as the other checkpoints

However, one critical behavior remains incomplete: after a committed `POST /api/chat/resume`, a client disconnect or reload does not replay the POST, but the backend also stops executing the graph, leaving the session stuck in `session_status="running"` instead of progressing to the next durable checkpoint or `completed`. In parallel, startup restore is duplicated across multiple mounted components, producing multiple identical `/history` GETs, and the Shadow UI can present a running session as if analysis had already finished.

This plan finishes the transport/recovery work so the code, runtime behavior, and docs all agree.

## User Story

As an editor using Author or Shadow in the browser  
I want a committed start or resume action to continue safely even if the SSE client disconnects or I reload the page  
So that my action is never replayed, my session reaches the next durable state, and the UI/docs reflect the real behavior

## Problem Statement

The current remediation correctly prevents replaying committed `POST /api/chat/stream` and `POST /api/chat/resume`, but it still ties graph execution to the SSE request lifecycle:

- `bond/api/routes/chat.py` breaks the loop on `await request.is_disconnected()` and closes the inner generator (`bond/api/routes/chat.py:211-266`)
- `parse_stream_events()` closes the underlying `astream_events` iterator in `finally` (`bond/api/stream.py:140-148`)
- a committed disconnect therefore cancels graph progress instead of merely detaching the client
- reload recovery on startup is one-shot only (`frontend/src/hooks/useSession.ts:126-155`), so a running session is hydrated once and then left alone
- `useSession()` is mounted from multiple components (`frontend/src/components/SessionProvider.tsx:15`, `Sidebar.tsx:9`, `ModeToggle.tsx:9`, `ChatInterface.tsx:13`, `CheckpointPanel.tsx:12`, `ShadowPanel.tsx:64`), causing duplicate `/history` requests
- history maps Shadow running nodes to `stage="idle"` (`bond/api/routes/chat.py:44-55`), while stream events use `shadow_analysis` / `shadow_annotation` (`bond/api/stream.py:24-37`)

The docs currently overstate validation and completion in `.planning/STATE.md`, `.planning/E2E_REPORT_2026-04-28.md`, `.planning/REQUIREMENTS.md`, and `README.md`.

## Solution Statement

Implement a detached-command runtime for `/api/chat/stream` and `/api/chat/resume`:

1. Start graph execution in a background task owned by the backend, not by the SSE response loop.
2. Let the connected client consume live SSE events from that background task while attached.
3. If the client disconnects after command commitment, detach the consumer but keep the graph running until the next durable state (`hitl_pause`, `done`, or terminal error).
4. Expose runtime-aware recovery metadata through `GET /api/chat/history/{thread_id}` so both same-tab recovery and page-reload recovery can poll history without replaying the POST.
5. Centralize frontend session bootstrap so startup restore runs once, not once per mounted consumer.
6. Align Shadow stage/state handling so a running Shadow session is visibly running, not mislabeled as complete or idle.
7. Update docs only after all live validations pass again, and only claim the exact validation level that was actually rerun.

## Feature Metadata

**Feature Type**: Bug Fix / Hardening / Documentation Correction  
**Estimated Complexity**: High  
**Primary Systems Affected**: FastAPI chat transport, LangGraph execution lifecycle, session history contract, frontend session bootstrap, shared progress UI, project docs  
**Dependencies**: FastAPI, Starlette request lifecycle, LangGraph durable execution + interrupts, `sse-starlette`, browser Fetch/ReadableStream APIs, Zustand, Zod

---

## VERIFIED BASELINE

These behaviors were independently verified and must remain true after implementation:

- `frontend/src/lib/sse.ts:13-46` correctly normalizes CRLF before splitting SSE frames.
- `frontend/src/hooks/useStream.ts:35-50` preserves numeric token strings by only JSON-parsing strings that begin with `{` or `[`.
- `frontend/src/hooks/useSession.ts:185-197` persists `bond_thread_id` and mode to storage.
- `frontend/src/hooks/useStream.ts:353-389` retries only before `fetch()` returns a `Response`.
- `frontend/src/hooks/useStream.ts:391-448` and `frontend/src/lib/streamRecovery.ts:68-133` recover through `/history`, not POST replay.
- `bond/graph/nodes/writer.py:324-353` and `frontend/src/components/CheckpointPanel.tsx:21-139` already use the normalized `low_corpus` HITL contract.

Do not reopen these fixes while solving the remaining gap.

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `.planning/STATE.md` (lines 8-45, 103-127)
  - Why: Contains the current overclaims that must not survive the fix.
- `.planning/E2E_REPORT_2026-04-28.md` (lines 3-33, 49-63)
  - Why: Documents claims about remediation completion and current validation scope.
- `.planning/REQUIREMENTS.md` (lines 61-66, 145-157)
  - Why: Current REC requirement status says complete; this must match actual behavior after rerun.
- `README.md` (lines 228-252)
  - Why: Troubleshooting section currently claims post-`resume` recovery should finish cleanly after disconnect.
- `bond/api/main.py` (lines 24-41)
  - Why: FastAPI lifespan and middleware are the right place for app-scoped runtime state and exposed headers.
- `bond/api/routes/chat.py` (lines 44-55, 152-266, 273-320, 327-437, 440-536)
  - Why: Current stream lifecycle, disconnect cancellation, post-stream event emission, and `/history` contract all live here.
- `bond/api/stream.py` (lines 24-37, 86-148)
  - Why: Stream stage labels already distinguish Shadow stages; cleanup behavior currently cancels graph work on disconnect.
- `bond/graph/graph.py` (lines 48-149, 156-167)
  - Why: Graph routing is locked; implementation must work without changing edges.
- `bond/graph/state.py` (lines 14-73)
  - Why: Existing state fields available for runtime/history hydration.
- `frontend/src/store/chatStore.ts` (lines 5-148)
  - Why: Shared transport state currently lacks Shadow stages and runtime/session-status metadata.
- `frontend/src/lib/streamRecovery.ts` (lines 10-133)
  - Why: Existing recovery policy is pure and should remain the place for state-transition decisions.
- `frontend/src/hooks/useStream.ts` (lines 35-50, 125-350, 353-505, 510-622)
  - Why: Commit-aware retry exists, but post-commit recovery still assumes the backend continued executing.
- `frontend/src/hooks/useSession.ts` (lines 50-91, 93-155, 185-223)
  - Why: Startup restore is one-shot and duplicated per component mount.
- `frontend/src/components/SessionProvider.tsx` (lines 12-26)
  - Why: Provider already blocks initial render and is the right owner for one-time bootstrap.
- `frontend/src/components/ShadowPanel.tsx` (lines 62-124, 133-205)
  - Why: Current Shadow status text can misreport a still-running recovered session as "Analiza zakończona".
- `frontend/src/components/StageProgress.tsx` (lines 6-118)
  - Why: Shared reconnect/recovery banners exist here, but only Author uses them today.
- `frontend/src/app/page.tsx` (lines 1-22)
  - Why: Author route already renders `StageProgress`.
- `frontend/src/app/shadow/page.tsx` (lines 1-4)
  - Why: Shadow route currently omits shared progress/recovery UI entirely.
- `tests/unit/api/test_chat.py` (lines 24-104)
  - Why: Existing route-level SSE test pattern.
- `tests/unit/api/test_chat_history.py` (lines 25-113)
  - Why: Existing history contract tests that need extension for the runtime-aware contract.
- `tests/unit/api/test_stream.py` (lines 13-174)
  - Why: Existing event-shape tests guard stream parsing and stage mapping.
- `tests/unit/graph/test_writer_low_corpus.py` (lines 54-108)
  - Why: Existing low-corpus contract tests must continue to pass unchanged.

### New Files to Create

- `bond/api/runtime.py`
  - Purpose: App-scoped detached command runtime that owns background graph tasks, live subscriber queues, active command metadata, and terminal cleanup.
- `tests/unit/api/test_runtime.py`
  - Purpose: Unit tests for "disconnect detaches consumer but does not cancel producer", lock retention, queue cleanup, and terminal status propagation.
- `frontend/src/hooks/useSessionBootstrap.ts`
  - Purpose: One-time startup restore + history polling hook used only by `SessionProvider`, so consumer hooks stop causing duplicate restore fetches.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [MDN: Using the Fetch API - Streaming the response body](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch#streaming_the_response_body)
  - Specific section: `Response.body` as `ReadableStream`, incremental chunk processing
  - Why: Confirms the frontend can process a streaming body incrementally and that the response exists before the body is fully read.
- [MDN: AbortController.abort()](https://developer.mozilla.org/en-US/docs/Web/API/AbortController/abort)
  - Specific section: aborting fetch requests, body consumption, and streams
  - Why: Confirms why a client-side abort must not be allowed to double as "cancel the backend command".
- [MDN: Using server-sent events - Event stream format](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events#event_stream_format)
  - Specific section: event framing and `data:` semantics
  - Why: Confirms SSE framing invariants that must remain intact.
- [MDN: Access-Control-Expose-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Expose-Headers)
  - Specific section: custom response headers visible to browser scripts
  - Why: Required if `/stream` exposes `X-Bond-Thread-Id` so the frontend can recover even when the body breaks before the first `thread_id` SSE event is parsed.
- [Starlette Requests](https://www.starlette.io/requests/)
  - Specific section: `await request.is_disconnected()`
  - Why: Confirms that disconnect detection belongs in the response layer, not in the ownership of graph execution itself.
- [LangGraph Durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)
  - Specific sections: requirements, determinism and consistent replay, recovering from failures
  - Why: Confirms the graph can resume from durable checkpoints and that side effects must remain deterministic/idempotent.
- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
  - Specific sections: pause using `interrupt`, resuming interrupts, rules of interrupts
  - Why: Confirms the correct HITL resume model and that resumed nodes restart from node boundaries rather than exact source lines.
- [LangGraph Streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
  - Specific sections: tasks/debug streaming modes, multiple modes
  - Why: Confirms current event-stream strategy is valid and helps reason about producer/consumer separation.

### Patterns to Follow

**Graph routing stability**

- Do not change edge declarations or routing function bodies in `bond/graph/graph.py:48-149`.

**HITL payload stability**

- Keep the locked interrupt shape:

```python
interrupt({
    "checkpoint": "<node_name>",
    "type": "approve_reject",
    ...
})
```

**App-scoped ownership**

- Long-lived infrastructure belongs on `app.state`, following `app.state.graph` in `bond/api/main.py:24-41`.

**Frontend transport ownership**

- `useStream()` remains the single public API for starting/resuming commands.
- `SessionProvider` should own bootstrap side effects.
- Components should consume session APIs without triggering network restore side effects on mount.

**Anti-patterns to avoid**

- Do not cancel LangGraph execution just because the SSE client disconnected.
- Do not replay a committed `POST /api/chat/stream` or `POST /api/chat/resume`.
- Do not keep claiming "Playwright validated" unless a committed Playwright spec exists and was rerun in this pass.
- Do not mark REC requirements complete until the live Shadow and Author reruns pass again.

---

## IMPLEMENTATION PLAN

### Phase 1: Detached Backend Command Runtime

Break the coupling between SSE response lifetime and graph execution lifetime.

**Tasks:**

- Create an app-scoped runtime that starts a background graph task per committed command.
- Keep a live event queue for the currently attached client, but allow the producer to continue after the client detaches.
- Preserve terminal metadata (`finished_cleanly`, `active_command`, `terminal_error`) so `/history` can report the real recovery state.
- Keep per-thread resume locking until the detached command actually reaches a durable stop.

### Phase 2: Runtime-Aware History Contract

Make `/api/chat/history/{thread_id}` the authoritative source for post-commit recovery.

**Tasks:**

- Merge persisted checkpoint state with runtime metadata for active/running commands.
- Add enough metadata for reload recovery to know whether a session is running because of `stream` or `resume`.
- Align Shadow stages between stream events and history responses.

### Phase 3: Single-Owner Frontend Bootstrap and Recovery Polling

Make startup restore run once, then keep polling history when a committed command is still in flight.

**Tasks:**

- Move bootstrap/restore side effects under `SessionProvider`.
- Start a recovery polling loop on reload when history reports `session_status="running"`.
- Use runtime metadata to clear stale HITL controls during resume recovery without wiping visible content.

### Phase 4: Shadow/Author UI State Alignment

Expose the same recovery truth to both routes.

**Tasks:**

- Extend shared stage modeling to include Shadow stages.
- Render shared progress/recovery UI on Shadow too.
- Ensure a running recovered Shadow session cannot be presented as "done" or "idle".

### Phase 5: Validation and Doc Correction

Only after the runtime and frontend are fixed, rerun validation and bring the docs back in sync.

**Tasks:**

- Re-run the existing lint/test/smoke suite.
- Re-run manual/live Shadow and Author browser journeys.
- Update docs to state only what was actually rerun and verified.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### CREATE `bond/api/runtime.py`

- **IMPLEMENT**: Add a detached command runtime with:
  - per-thread active run registry
  - background producer task for `graph.astream_events(...)`
  - optional subscriber queue for the currently connected SSE response
  - `active_command: "stream" | "resume"`
  - terminal status fields such as `finished_cleanly`, `terminal_error`, `detached_at`, `completed_at`
- **IMPLEMENT**: Keep the producer running after the subscriber detaches; only stop it on graph completion, terminal error, or app shutdown.
- **IMPLEMENT**: Hold the per-thread resume lock until the detached producer stops, not merely until the SSE response closes.
- **PATTERN**: Mirror app-scoped ownership used for `app.state.graph` in `bond/api/main.py:24-41`.
- **GOTCHA**: Do not buffer unbounded events after detachment; once no subscriber is attached, drop live events but keep executing the graph.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/api/test_runtime.py -q`

### UPDATE `bond/api/main.py`

- **IMPLEMENT**: Initialize the new runtime during FastAPI lifespan and store it on `app.state`.
- **IMPLEMENT**: Cancel/await active runtime tasks cleanly during shutdown.
- **IMPLEMENT**: Expose any custom response header needed for recovery, e.g. `X-Bond-Thread-Id`, through CORS if the frontend reads the backend directly on a different port.
- **PATTERN**: Keep the existing `compile_graph()` lifecycle intact.
- **GOTCHA**: Do not regress current `allow_origins` / credentials behavior while exposing the custom header.
- **VALIDATE**: `uv run ruff check bond/api/main.py bond/api/runtime.py`

### UPDATE `bond/api/routes/chat.py`

- **IMPLEMENT**: Replace request-owned graph execution with runtime-owned execution for both `/stream` and `/resume`.
- **IMPLEMENT**: Keep emitting the `thread_id` SSE event first, but also include the same thread ID in a response header so recovery still works if the body drops before the first event is parsed.
- **IMPLEMENT**: Stop calling `request.is_disconnected()` as a reason to cancel the graph producer; use it only to detach the SSE consumer.
- **IMPLEMENT**: Run `_emit_post_stream_events(...)` as part of the producer completion path so connected clients still receive `hitl_pause`, `done`, `shadow_corrected_text`, and `annotations`.
- **IMPLEMENT**: Extend `/history` to merge persisted state with runtime metadata:
  - `session_status`
  - `pending_node`
  - `can_resume`
  - `active_command`
  - optional `error_message`
- **IMPLEMENT**: Align `_STAGE_MAP` for Shadow to `shadow_analysis` / `shadow_annotation`, matching `bond/api/stream.py:24-37`.
- **PATTERN**: Preserve the current public JSON envelope from `StreamEvent`.
- **GOTCHA**: Do not turn every `!response.ok` case into recovery; non-2xx upfront responses should remain ordinary errors.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/api/test_chat.py tests/unit/api/test_chat_history.py -q`

### UPDATE `bond/api/stream.py`

- **IMPLEMENT**: Keep stream event translation unchanged, but update cleanup/comment semantics so the producer owns iterator shutdown at producer completion instead of "client disconnect means cancel graph work".
- **IMPLEMENT**: Ensure Shadow stream stage names remain the canonical source for `shadow_analysis` / `shadow_annotation`.
- **PATTERN**: Preserve token hot-path behavior and existing SSE event kinds.
- **GOTCHA**: Do not regress the already-correct CRLF and numeric token protections; those live in the frontend and are already validated.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/api/test_stream.py -q`

### CREATE `tests/unit/api/test_runtime.py`

- **IMPLEMENT**: Add runtime tests for:
  - disconnect detaches the subscriber without cancelling the producer
  - producer completion clears the active run registry
  - terminal errors are captured for `/history`
  - resume lock remains held until the producer finishes
- **PATTERN**: Use fake async generators instead of invoking real LLMs.
- **IMPORTS**: `asyncio`, `pytest`, runtime class/helpers, `AsyncMock` or lightweight fakes.
- **GOTCHA**: Keep tests deterministic; avoid sleeps longer than necessary.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/api/test_runtime.py -q`

### UPDATE `tests/unit/api/test_chat_history.py`

- **IMPLEMENT**: Extend history contract tests to cover:
  - running Shadow session returns `stage="shadow_annotation"` or `shadow_analysis`, not `idle`
  - runtime-reported `active_command="resume"` is surfaced for a running recovered session
  - optional `error_message` stops polling when background execution fails
- **PATTERN**: Reuse the existing `MockStateSnapshot` + `TestClient` style.
- **GOTCHA**: Keep persisted-state assertions separate from runtime-overlay assertions.
- **VALIDATE**: `PYTHONPATH=. uv run pytest tests/unit/api/test_chat_history.py -q`

### UPDATE `frontend/src/store/chatStore.ts`

- **IMPLEMENT**: Extend `Stage` to include Shadow stages (`shadow_analysis`, `shadow_annotation`) and initialize `stageStatus` for them.
- **IMPLEMENT**: Add session/runtime metadata needed by the UI, such as:
  - `sessionStatus`
  - `pendingNode`
  - `activeCommand`
- **IMPLEMENT**: Keep `isStreaming`, `isReconnecting`, and `isRecoveringSession` semantically distinct.
- **PATTERN**: Preserve current AbortController ownership in the store.
- **GOTCHA**: Do not overload `pendingAction`; distinguish "what command the frontend sent" from "what command the backend says is still active".
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/lib/streamRecovery.ts`

- **IMPLEMENT**: Extend `SessionHistoryResponse` to include the runtime-aware fields returned by `/history`.
- **IMPLEMENT**: Refine recovery helpers so:
  - non-2xx upfront responses are terminal, not recovery-worthy
  - running sessions can carry `active_command`
  - resume recovery can clear stale `hitlPause` while preserving visible content
- **IMPLEMENT**: Support Shadow stages without falling back to `idle`.
- **PATTERN**: Keep this module pure and framework-free.
- **GOTCHA**: Preserve current numeric-token-safe payload handling in `useStream.ts`; do not move parsing back into a less-constrained helper.
- **VALIDATE**: `cd frontend && npm run lint`

### CREATE `frontend/src/hooks/useSessionBootstrap.ts`

- **IMPLEMENT**: Extract one-time startup restore into a dedicated hook used only by `SessionProvider`.
- **IMPLEMENT**: After the first history hydration, if the session is still `running`, start polling `/history` until it reaches `paused`, `completed`, or `error`.
- **IMPLEMENT**: Use `active_command` from history to decide whether stale HITL controls should remain visible or be cleared during recovery.
- **PATTERN**: Reuse `loadSessionHistory()` and `buildSessionHydration()` rather than duplicating store writes.
- **GOTCHA**: Block initial render only for the first hydration, not for the entire recovery poll.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/hooks/useSession.ts`

- **IMPLEMENT**: Remove mount-time restore side effects from the consumer hook so calling `useSession()` in multiple components no longer triggers duplicate `/history` fetches.
- **IMPLEMENT**: Keep storage/session actions (`persistThreadId`, `persistMode`, `newSession`, `switchSession`) intact and side-effect-safe.
- **IMPLEMENT**: Keep `loadSessionHistory()` reusable for both startup restore and same-tab committed recovery.
- **PATTERN**: Preserve current shadow hydration (`originalText`, `annotations`, `shadowCorrectedText`) from `useSession.ts:50-91`.
- **GOTCHA**: A paused checkpoint reload should result in one startup `/history` GET, not one per mounted consumer.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/SessionProvider.tsx`

- **IMPLEMENT**: Use the new bootstrap hook as the single owner of startup restore/recovery.
- **IMPLEMENT**: Continue blocking child render until the first hydration finishes.
- **PATTERN**: Keep `SessionProvider` mounted at the root in `frontend/src/app/layout.tsx:29-32`.
- **GOTCHA**: Do not move bootstrap back into leaf components.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/hooks/useStream.ts`

- **IMPLEMENT**: Read the thread ID from the response header immediately after `fetch()` succeeds, before consuming the body, and pass it through `onThreadId`.
- **IMPLEMENT**: Treat only a successful streaming response as a committed command; do not history-poll after an upfront HTTP error.
- **IMPLEMENT**: Continue using `/history` after unexpected post-commit body loss, but now rely on the backend runtime to have continued the command.
- **IMPLEMENT**: Consume the new runtime-aware history fields so same-tab recovery and reload recovery share the same semantics.
- **PATTERN**: Preserve the existing SSE parser flow, Zod schemas, Shadow hydration, and `clearPauseOnProgress` behavior.
- **GOTCHA**: For fresh `/stream`, recovery must still work even if the body breaks before the first `thread_id` SSE event arrives.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/StageProgress.tsx`

- **IMPLEMENT**: Support both Author and Shadow step sets based on `mode`.
- **IMPLEMENT**: Continue showing reconnect/recovery banners, but with copy grounded in runtime truth (`activeCommand`, `sessionStatus`).
- **IMPLEMENT**: Handle Shadow running stages without collapsing back to "idle".
- **PATTERN**: Reuse the existing banner surface instead of inventing a second shared transport banner.
- **GOTCHA**: Do not regress the Author route; existing research/structure/writing progress must still render correctly.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/app/shadow/page.tsx`

- **IMPLEMENT**: Render `StageProgress` on the Shadow route so shared transport banners and stage indicators are visible there too.
- **PATTERN**: Mirror the Author page’s composition, but keep the Shadow layout intact.
- **GOTCHA**: Avoid duplicate progress surfaces by only rendering one shared progress component per route.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/ShadowPanel.tsx`

- **IMPLEMENT**: Base the status bar on real recovery/session metadata so a running recovered session cannot show "Analiza zakończona".
- **IMPLEMENT**: Keep `annotations`, `shadowCorrectedText`, `draft`, and actions restored after checkpoint reload.
- **IMPLEMENT**: During resume recovery, keep visible comparison content but suppress stale approve/reject affordances until the backend reaches the next durable state.
- **PATTERN**: Preserve current approve/reject handlers and `handleReset()` semantics.
- **GOTCHA**: Reload on `shadow_checkpoint` must still restore the action panel without issuing a second stream POST.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/CheckpointPanel.tsx`

- **IMPLEMENT**: Adapt to the side-effect-free `useSession()` consumer API if signatures change.
- **IMPLEMENT**: Keep `low_corpus` and duplicate-check warning flows intact while honoring the richer recovery metadata.
- **PATTERN**: Preserve current warning panel and standard checkpoint affordances.
- **GOTCHA**: Do not regress Author cp1/cp2 behavior while fixing shared session bootstrapping.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/Sidebar.tsx`, `ModeToggle.tsx`, `ChatInterface.tsx`

- **IMPLEMENT**: Consume the new side-effect-free session API without triggering restore fetches on mount.
- **PATTERN**: Preserve current user-facing behavior.
- **GOTCHA**: `ModeToggle` still needs to persist mode on route changes, but must not become a second restore owner.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `.planning/STATE.md`, `.planning/E2E_REPORT_2026-04-28.md`, `.planning/REQUIREMENTS.md`, `README.md`

- **IMPLEMENT**: Rewrite only the claims that were inaccurate:
  - remove or rephrase any statement that post-`resume` committed disconnect is already fully solved until it is rerun
  - remove or rephrase any tool-specific claim ("Playwright potwierdził") unless a reproducible Playwright run is added in this pass
  - update REC requirement status only after the new live validations pass
- **IMPLEMENT**: Record exact validation scope and exact date of rerun.
- **PATTERN**: Keep docs factual and scoped; separate "verified in this pass" from "shared by code path but not independently rerun."
- **GOTCHA**: Do not let docs overclaim Author validation if only Shadow was rerun.
- **VALIDATE**: `rg -n "Playwright|completed|REC-0|resume" .planning README.md`

---

## TESTING STRATEGY

### Unit Tests

- Add backend runtime tests for detached execution and lock lifetime.
- Extend history contract tests for Shadow running state, runtime overlay, and error propagation.
- Keep existing stream parser and low-corpus contract tests green.

### Integration Tests

- Run the targeted pytest/API suite after the backend runtime refactor.
- Re-run `frontend/scripts/test-sse.mjs` to ensure SSE framing and numeric tokens stay correct.

### Edge Cases

- disconnect after `fetch()` returns a `Response` but before the first `thread_id` SSE event is parsed
- reload while a committed `resume` is still processing
- paused checkpoint reload should restore once, not fan out five identical `/history` requests
- running Shadow session should display a running state, not `idle`/complete
- upfront HTTP 4xx/5xx from `/resume` should surface as errors, not trigger recovery polling
- duplicate resume clicks while a detached producer is still running should remain blocked

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and correct recovery semantics.

### Level 1: Syntax & Style

```bash
uv run ruff check .
cd frontend && npm run lint
```

### Level 2: Unit Tests

```bash
PYTHONPATH=. uv run pytest tests/unit/api/test_chat.py tests/unit/api/test_stream.py tests/unit/api/test_chat_history.py tests/unit/api/test_runtime.py tests/unit/graph/test_writer_low_corpus.py -q
```

### Level 3: Transport Smoke

```bash
node frontend/scripts/test-sse.mjs --api-url http://127.0.0.1:8000
```

### Level 4: Manual Validation

```bash
uv run python -m uvicorn bond.api.main:app --port 8000
cd frontend && npm run dev
```

Shadow:

1. Open `http://localhost:3000/shadow`.
2. Start a new Shadow session and confirm exactly one `POST /api/chat/stream`.
3. Reach `shadow_checkpoint`.
4. Reload the page and confirm:
   - exactly one `GET /api/chat/history/{thread_id}`
   - no second `POST /api/chat/stream`
   - annotations, corrected text, draft, and actions are restored
5. Click `Zatwierdź` or `Odrzuć` and confirm exactly one `POST /api/chat/resume`.
6. Disconnect or reload after the committed resume and confirm:
   - no replay of `POST /api/chat/resume`
   - `/history` polling continues until `paused`, `completed`, or `error`
   - the UI shows recovery/running state, not "Analiza zakończona"
7. For an approve path, confirm the final `GET /api/chat/history/{thread_id}` returns:
   - `session_status="completed"`
   - `stage="done"`
   - `can_resume=false`

Author:

1. Open `http://localhost:3000/`.
2. Start an Author session and confirm exactly one `POST /api/chat/stream`.
3. Interrupt after commitment and confirm reload recovery uses `/history`, not POST replay.
4. Complete a cp1/cp2 journey and confirm resume actions also avoid POST replay after committed disconnect.
5. Confirm the final history returns `completed` and the route never enters a reconnect/replay loop.

### Level 5: Additional Validation (Optional but Recommended)

- If `.venv` entrypoints are stale after a repo move, run `uv sync --reinstall` before the commands above.
- Capture backend access logs during the live runs so "exactly one POST" and "exactly one GET on paused reload" are evidenced, not inferred.

---

## ACCEPTANCE CRITERIA

- [ ] A committed `/api/chat/stream` or `/api/chat/resume` continues executing after client disconnect; disconnect detaches the consumer but does not cancel the backend command.
- [ ] Shadow reload at `shadow_checkpoint` restores annotations, corrected text, draft, and HITL actions without a second stream POST.
- [ ] A paused checkpoint reload performs one startup `/history` fetch, not one per mounted consumer.
- [ ] A committed disconnect after `resume` does not replay `/api/chat/resume`, and `/history` eventually reaches a durable end state (`paused`, `completed`, or `error`).
- [ ] Running Shadow sessions surface a real running/recovery UI state; they are never mislabeled as `idle` or "Analiza zakończona".
- [ ] Recovery still works when the body drops before the first `thread_id` SSE event is parsed.
- [ ] `low_corpus` remains on the shared `approve_reject` contract and all current tests still pass.
- [ ] `uv run ruff check .`, frontend lint, targeted pytest suite, and `frontend/scripts/test-sse.mjs` all pass.
- [ ] Shadow and Author both pass a fresh live browser journey without replay loops.
- [ ] Docs claim only what was actually rerun and verified in this pass.

---

## COMPLETION CHECKLIST

- [ ] Detached runtime implemented and app-scoped
- [ ] `/history` upgraded to runtime-aware recovery contract
- [ ] `useSession()` no longer triggers restore fetches from multiple components
- [ ] Shadow stages aligned between stream events, history responses, and UI
- [ ] Response-header fallback for thread ID implemented and exposed if needed
- [ ] Same-tab recovery and reload recovery both use `/history`
- [ ] Targeted tests added and passing
- [ ] Live Shadow rerun passed
- [ ] Live Author rerun passed
- [ ] Docs corrected after rerun

---

## NOTES

- Verified fact: the current remediation is partially correct, not wholly wrong. The plan must preserve the already-fixed CRLF parser, numeric token parsing, sessionStorage persistence, and low-corpus contract.
- Verified fact: the remaining blocker is backend execution ownership after committed disconnect, plus startup restore duplication and Shadow running-state presentation.
- Assumption for this pass: fix same-process client disconnect/reload recovery first. Do not broaden scope into cross-worker/distributed runtime coordination unless testing proves it is required.
- If you decide to claim Playwright validation in docs, first add a reproducible Playwright setup to the repo and rerun it in this pass. Otherwise, phrase validation as manual/browser automation without naming unsupported tooling.
- Confidence score for one-pass implementation success after following this plan: **8/10**.
