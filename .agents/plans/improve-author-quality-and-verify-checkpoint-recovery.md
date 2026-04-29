# Feature: Improve Author Quality and Verify Checkpoint Recovery

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to the existing HITL contract, the locked graph routing, and the distinction between exploratory `agent-browser` noise and reproducible product defects.

## Feature Description

This workstream addresses two follow-ups from the 2026-04-29 E2E sweep:

1. Author draft quality still degraded to repeated HITL intervention on a realistic Polish brief, even though the workflow itself stayed healthy end-to-end.
2. Checkpoint interactions after reload felt flaky in `agent-browser`, but backend `/history`, recovery semantics, and final session outcomes remained consistent. That is not enough evidence to patch product behavior blindly.

The implementation goal is therefore split in two:

- remove the most likely quality regressions in the Author generation path
- upgrade the automated checkpoint-recovery proof so future regressions are judged by Playwright/manual evidence, not by `agent-browser` quirks alone

## User Story

As an editor and maintainer of Bond  
I want Author drafts to satisfy their own SEO constraints more reliably and checkpoint recovery to be reproducibly verifiable after reload  
So that HITL is used for editorial judgment, not for avoidable generator mistakes, and recovery changes are driven by confirmed product evidence

## Problem Statement

The quality issue is not just “the model writes weakly.” The current codebase creates two concrete failure modes:

- the web path sends all Author intent as one raw `message`, while `POST /api/chat/stream` still injects `keywords: []` into state; `structure_node` and `writer_node` then fall back to `primary_keyword = topic`, so a multi-line brief like `Temat: ... Słowa kluczowe: ... Wymagania: ...` becomes the literal SEO keyword target for H1 and the first paragraph
- the writer retry loop is effectively blind: attempts 2 and 3 rerun after validation failure without telling the model which constraints failed, so retries can repeat the same mistake with extra cost

The recovery issue is currently under-instrumented rather than clearly broken:

- existing Playwright harnesses already prove reload recovery for approve paths and local draft persistence, but they do not cover the exact reject-after-reload paths that felt flaky in `agent-browser`
- because `agent-browser` can differ from Playwright in textarea and click behavior, any product hardening should be gated on a deterministic reproduction in Playwright or a manual browser

## Solution Statement

Implement three coordinated changes:

1. Normalize Author input at the API boundary so explicit `Temat` / `Słowa kluczowe` / `Wymagania` briefs become clean `topic`, `keywords`, and `context_dynamic` before `researcher`, `structure`, and `writer` use them.
2. Turn writer validation into a first-class feedback loop: capture detailed validation results, reuse them as targeted auto-repair instructions on retries, and surface those details at `checkpoint_2` and `/history`.
3. Add a dedicated Playwright regression harness for reload + reject recovery in Author and Shadow; only if that harness reproduces a UI bug should product-side recovery behavior change. Otherwise, limit any frontend changes to stable automation hooks such as `data-testid`.

## Feature Metadata

**Feature Type**: Enhancement / Hardening  
**Estimated Complexity**: High  
**Primary Systems Affected**: FastAPI chat request normalization, Author graph state, writer/checkpoint nodes, `/history` recovery payloads, frontend checkpoint UI typing/rendering, Playwright regression tooling  
**Dependencies**: FastAPI/Pydantic, LangGraph interrupts/resume, existing `context_dynamic` prompt layer, Playwright Python sync API, current local validation scripts

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `.planning/STATE.md` (lines 13, 49-53, 92-93, 212-223)
  - Why: captures the current post-signoff state, the validated recovery harnesses already in place, and the existing note that writer auto-retry only uses `cp2_feedback` on attempt 0.
- `bond/api/routes/chat.py` (lines 156-178, 315-357, 360-427, 430-553)
  - Why: current Author request contract still only carries `message`; initial state hardcodes `keywords: []`; `/resume` and `/history` are the recovery contract that must remain stable.
- `bond/harness.py` (lines 109-174, 198-216)
  - Why: the CLI harness already models the separation between `topic`, `keywords`, and `context_dynamic`; this is the cleanest existing pattern for Author input semantics.
- `bond/prompts/context.py` (lines 35-60)
  - Why: `context_dynamic` is already a supported prompt layer and is currently unused by the web UI path.
- `bond/graph/state.py` (lines 14-73)
  - Why: this is where any new internal Author validation detail field must be added without changing the locked graph edges.
- `bond/graph/nodes/researcher.py` (lines 249-330)
  - Why: downstream research already consumes `topic`, `keywords`, and `context_dynamic`; normalized input must be available before this node runs.
- `bond/graph/nodes/structure.py` (lines 16-65, 68-132)
  - Why: `structure_node` currently falls back to `primary_keyword = topic`, which becomes pathological when `topic` still contains the entire raw brief.
- `bond/graph/nodes/writer.py` (lines 190-220, 236-310, 317-470)
  - Why: the validation rules, prompt construction, and blind retry loop all live here.
- `bond/graph/nodes/checkpoint_2.py` (lines 16-100)
  - Why: `checkpoint_2` currently exposes only a generic `validation_warning`; this is the right place to surface precise failure details to HITL.
- `bond/schemas.py` (lines 28-92, 95-132)
  - Why: `ChatHistoryResponse` is the recovery contract, and the unused `AgentInput` shows the project already conceptually expects structured Author input.
- `frontend/src/components/ChatInterface.tsx` (lines 11-30, 39-99)
  - Why: current Author UX is a single textarea and placeholder; if you keep that UX, it still needs clearer guidance for parseable structured briefs.
- `frontend/src/hooks/useStream.ts` (lines 71-91, 129-249, 509-695)
  - Why: module-scope Zod schemas, `hitl_pause` parsing, and the stream/resume lifecycle live here; any new recovery payload fields must be accepted here first.
- `frontend/src/store/chatStore.ts` (lines 17-41, 48-160)
  - Why: the `HitlPause` shape must stay aligned with any richer `checkpoint_2` payload.
- `frontend/src/components/CheckpointPanel.tsx` (lines 10-70, 149-300)
  - Why: this is the UI that currently renders only a generic warning for `checkpoint_2`; it is also the place where optional automation hooks belong.
- `frontend/src/components/ShadowPanel.tsx` (lines 115-126, 136-228)
  - Why: the Shadow reject textarea and approve/reject buttons are part of the new reload-reject regression matrix.
- `frontend/src/hooks/useSessionBootstrap.ts` (lines 31-70, 95-121)
  - Why: reload restore ownership already lives here; do not scatter recovery behavior into random components while investigating the flakiness report.
- `frontend/src/lib/streamRecovery.ts` (lines 16-31, 78-96, 98-167)
  - Why: this helper defines the current recovery disposition and hydration semantics that Playwright must keep validating.
- `tests/unit/api/test_chat.py` (lines 56-106)
  - Why: this is the right place to lock the normalized initial state created by `POST /api/chat/stream`.
- `tests/unit/api/test_chat_history.py` (lines 27-119, 204-272)
  - Why: recovery payload shape and runtime overlays are already covered here and should be extended for richer `checkpoint_2` details.
- `tests/unit/graph/test_writer_low_corpus.py` (lines 56-120)
  - Why: existing writer tests already mock interrupts and validate short-circuit behavior; new writer tests should mirror this style.
- `tests/unit/graph/test_writer_prompt_budget.py` (lines 74-224)
  - Why: this file already protects writer prompt behavior and is the best reference for adding tests that differentiate first-pass generation from retry repair prompts.
- `tests/unit/graph/test_structure_node.py` (lines 82-152)
  - Why: structure prompt tests already lock how `topic` and `keywords` affect prompt construction.
- `scripts/playwright_detached_runtime_journey.py` (lines 48-89, 220-314, 319-421)
  - Why: existing reload-recovery harness already proves approve-path recovery and exact POST counts; the new script should mirror its helper style.
- `scripts/playwright_post_signoff_regressions.py` (lines 141-217, 246-396)
  - Why: existing post-signoff harness already covers `checkpoint_2`, manual draft edits, download, and rerun behavior; extend the style, not the stack.

### New Files to Create

- `bond/api/author_input.py`
  - Purpose: deterministic normalization/parser for Author briefs (`message` + optional structured fields) into clean `topic`, `keywords`, and `context_dynamic`.
- `tests/unit/api/test_author_input.py`
  - Purpose: unit coverage for labeled Polish brief parsing, optional explicit request fields, and safe fallback when no labels are present.
- `tests/unit/graph/test_writer_autorepair.py`
  - Purpose: lock the new writer retry behavior so attempts after failure are no longer blind replays.
- `tests/fixtures/author_quality_cases.json`
  - Purpose: curated local eval matrix with realistic Polish prompts, including the failing `Temat / Słowa kluczowe / Wymagania` shape from E2E.
- `scripts/evaluate_author_quality.py`
  - Purpose: local regression harness that runs the curated Author cases and records first-pass validation outcomes plus failed constraints.
- `scripts/playwright_checkpoint_recovery_regressions.py`
  - Purpose: targeted Playwright proof for reload + reject recovery in both Author and Shadow, including exact `/resume` request counts.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
  - Specific section: resuming interrupts with the same thread ID and the note that the interrupted node re-runs from the top.
  - Why: the new plan must respect the current `Command(resume=...)` recovery contract and the cost of rerunning node-local logic.
- [Playwright Python: Auto-waiting / Actionability](https://playwright.dev/python/docs/actionability)
  - Specific section: actionability checks and auto-retrying assertions.
  - Why: if a checkpoint bug reproduces only in one tool, Playwright’s actionability model should be the source of truth before shipping UI fixes.
- [Playwright Python: Network](https://playwright.dev/python/docs/network)
  - Specific section: `page.expect_response()` and request/response observation.
  - Why: the recovery harness must verify exact `POST /api/chat/resume` counts and reject replay after reload.
- [Playwright Python: Writing Tests](https://playwright.dev/python/docs/writing-tests)
  - Specific section: web-first assertions and avoiding unnecessary manual waits.
  - Why: the new regression harness should prefer browser-observable assertions over arbitrary sleeps.
- [OpenAI Prompt Engineering Guide](https://platform.openai.com/docs/guides/prompt-engineering)
  - Specific section: writing clear, specific instructions and iterating prompts based on observed failures.
  - Why: the writer retry fix should add explicit machine-readable failure guidance, not just rerun the same prompt.
- [OpenAI Evaluation Best Practices](https://platform.openai.com/docs/guides/evaluation-best-practices)
  - Specific section: eval-driven development, task-specific datasets, and combining automated scoring with human judgment.
  - Why: prompt tuning for Author quality should be backed by a small curated regression set rather than ad hoc “looks better” checks.

### Patterns to Follow

**Author input semantics already exist in the CLI harness**

- `bond/harness.py:109-174` already separates `topic`, `keywords`, and `context_dynamic`.
- Mirror that shape instead of inventing a second meaning for the raw `message`.

**Use `context_dynamic` instead of overloading `topic`**

- `bond/prompts/context.py:35-60` is the existing prompt-layer extension point for run-specific requirements.
- User requirements such as “ton ekspercki, bez list wypunktowanych” belong there, not inside the primary SEO keyword.

**Do not change graph routing**

- `bond/graph/graph.py:62-86` is the locked routing layer.
- Normalize input in the request layer and improve behavior inside existing nodes; do not add or rewire graph edges.

**Retry improvements must stay inside writer semantics**

- `bond/graph/nodes/writer.py:404-447` already owns retries.
- Improve retries by changing prompt content between attempts, not by inflating `max_attempts` or adding side-channel nodes.

**Recovery remains server-authoritative**

- `frontend/src/hooks/useSessionBootstrap.ts:31-70` and `frontend/src/lib/streamRecovery.ts:78-167` already make `/history` the source of truth after reload.
- Investigation of checkpoint flakiness must preserve that ownership model.

**Browser regression style already exists**

- `scripts/playwright_detached_runtime_journey.py` and `scripts/playwright_post_signoff_regressions.py` use helper functions, explicit polling, screenshots, and network assertions.
- Reuse that style instead of introducing a different browser framework or assertion style.

**Anti-patterns to avoid**

- Do not “fix” Author quality by merely raising retry count or temperature.
- Do not parse arbitrary unlabeled prose aggressively; normalize only explicit fields or well-bounded patterns, then fall back safely.
- Do not treat `agent-browser` interaction failures as product bugs without Playwright/manual confirmation.
- Do not add logging in the hot SSE token path just to debug this; prefer unit tests and Playwright artifacts.
- Do not change `StreamEvent` envelope types or the `/resume` action contract.

---

## IMPLEMENTATION PLAN

### Phase 1: Normalize Author Input Before Research/Structure/Writer

Fix the input contract first, because every downstream quality tweak is distorted if the primary keyword is still the full raw brief.

**Tasks:**

- Add a deterministic Author brief normalizer for the web request path.
- Support two safe inputs:
  - explicit API fields such as `keywords` / `context_dynamic`
  - labeled Polish brief blocks inside `message` (`Temat:`, `Słowa kluczowe:`, `Wymagania:`)
- Leave unlabeled freeform prompts untouched instead of guessing aggressively.
- Keep raw `message` for chat history and session UX, but use normalized values for graph state.

### Phase 2: Make Writer Retries Targeted Instead of Blind

Once the keyword contract is sane, improve the retry loop so the model knows what failed and can repair the draft rather than regenerate randomly.

**Tasks:**

- Refactor draft validation into a richer report that includes failed checks and useful metrics.
- Feed that report back into attempts 2..N as targeted repair instructions against the previous draft.
- Persist validation details in state and expose them at `checkpoint_2` and `/history`.
- Update the frontend warning panel to render concrete failures instead of a single generic sentence.

### Phase 3: Prove Reload + Reject Recovery in Playwright

Before changing recovery behavior, add missing coverage for the exact paths that felt flaky.

**Tasks:**

- Create a dedicated Playwright regression script for:
  - Shadow: reload at checkpoint, reject with feedback, recover to next paused state, reload again, then approve
  - Author `checkpoint_1`: reload, reject with note, recover to updated structure, then approve
  - Author `checkpoint_2`: reload, reject with feedback, recover to regenerated draft, then approve/save
- Assert exact request counts for `POST /api/chat/resume` and no replay after reload.
- Add stable `data-testid` hooks only if selector ambiguity makes the harness brittle.
- Treat any UI behavior change as conditional on Playwright/manual reproduction.

### Phase 4: Lock the Outcome with Local Evals, Regression Tests, and Doc Sync

Quality tuning without regression coverage will drift back quickly.

**Tasks:**

- Add a small curated Author quality fixture set and a local evaluation script.
- Run unit tests, Playwright harnesses, and the curated quality sweep together.
- Only after all validations pass, update root `.planning/` docs in the same patch to record the new status and artifacts.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### CREATE `bond/api/author_input.py`

- **IMPLEMENT**: A pure normalization helper that accepts raw `message` plus optional explicit `keywords` and `context_dynamic`, and returns normalized `topic`, `keywords`, `context_dynamic`, and `raw_message`.
- **PATTERN**: Mirror `bond/harness.py:109-174` for the meaning of these fields and `bond/prompts/context.py:35-60` for how `context_dynamic` is consumed downstream.
- **IMPORTS**: Keep this module lightweight; prefer stdlib + optional Pydantic only if you need stricter parsing.
- **GOTCHA**: Only parse clearly labeled sections. If labels are absent, keep `topic=message`, `keywords=[]`, `context_dynamic=None`.
- **VALIDATE**: `uv run pytest tests/unit/api/test_author_input.py`

### UPDATE `bond/api/routes/chat.py`

- **IMPLEMENT**: Extend `ChatRequest` with optional `keywords` and `context_dynamic`; call the new normalizer before constructing `initial_state`; keep `messages` based on the raw user text.
- **PATTERN**: Preserve the current `thread_id`, `mode`, and Shadow path from `bond/api/routes/chat.py:315-357`.
- **IMPORTS**: `bond.api.author_input` normalizer; keep existing FastAPI/Pydantic shape.
- **GOTCHA**: Do not change Shadow request semantics. Do not break `test_chat_stream_injects_thread_id_into_initial_state`.
- **VALIDATE**: `uv run pytest tests/unit/api/test_chat.py tests/unit/api/test_author_input.py`

### UPDATE `frontend/src/components/ChatInterface.tsx`

- **IMPLEMENT**: Adjust Author placeholder/help copy so the accepted brief format is explicit (`Temat`, `Słowa kluczowe`, `Wymagania`) while preserving the current single-textarea UX.
- **PATTERN**: Keep the existing Enter/Shift+Enter behavior from `frontend/src/components/ChatInterface.tsx:24-37`.
- **IMPORTS**: Reuse existing shadcn `Textarea` and `Button`; no custom browser state management.
- **GOTCHA**: Do not add restore side effects or new stream ownership here.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `bond/graph/state.py`

- **IMPLEMENT**: Add an internal optional field for detailed draft validation results, e.g. `draft_validation_details`.
- **PATTERN**: Follow the existing `TypedDict` shape in `bond/graph/state.py:14-73`.
- **IMPORTS**: If you add a nested typed structure, keep it internal and minimal.
- **GOTCHA**: This is internal graph state, not a public REST model.
- **VALIDATE**: `uv run pytest tests/unit/graph/test_writer_autorepair.py`

### UPDATE `bond/graph/nodes/writer.py`

- **IMPLEMENT**: Refactor `_validate_draft()` into a richer validation report; add a helper that formats failed checks into a repair instruction; use that report to turn retries after attempt 1 into targeted revisions of the previous draft.
- **PATTERN**: Reuse the targeted-revision prompt shape already present in `bond/graph/nodes/writer.py:269-286`.
- **IMPORTS**: Keep using `build_context_block`, `select_research_context`, and current token/cost accounting.
- **GOTCHA**: Keep the retry budget bounded at the current `max_attempts` unless test evidence justifies a change. Preserve `cp2_feedback` precedence when the retry is user-driven rather than validation-driven.
- **VALIDATE**: `uv run pytest tests/unit/graph/test_writer_autorepair.py tests/unit/graph/test_writer_low_corpus.py tests/unit/graph/test_writer_prompt_budget.py`

### UPDATE `bond/graph/nodes/checkpoint_2.py`

- **IMPLEMENT**: Include detailed validation results in the interrupt payload when `draft_validated` is false, not just `validation_warning`.
- **PATTERN**: Keep the existing `approve` / `reject` / `abort` contract and soft/hard cap behavior from `bond/graph/nodes/checkpoint_2.py:33-100`.
- **IMPORTS**: Only use state fields already produced by `writer_node`.
- **GOTCHA**: Do not rename checkpoint IDs or action semantics.
- **VALIDATE**: `uv run pytest tests/unit/graph/test_writer_autorepair.py tests/unit/api/test_chat_history.py`

### UPDATE `bond/api/routes/chat.py`

- **IMPLEMENT**: Extend `_build_hitl_pause_from_state()` and `_build_hitl_pause_from_snapshot()` so `/history` recovery returns the same detailed `checkpoint_2` validation payload as the live stream.
- **PATTERN**: Mirror the existing `iterations_remaining` fallback behavior from `bond/api/routes/chat.py:56-133` and `:492-512`.
- **IMPORTS**: No new public schema is required if the detail remains nested under `hitlPause`.
- **GOTCHA**: Recovery payload and live interrupt payload must stay aligned, or reload will silently lose the new details.
- **VALIDATE**: `uv run pytest tests/unit/api/test_chat_history.py`

### UPDATE `frontend/src/store/chatStore.ts`

- **IMPLEMENT**: Extend `HitlPause` to carry the new detailed validation object for `checkpoint_2`.
- **PATTERN**: Keep the shared Author/Shadow store contract style from `frontend/src/store/chatStore.ts:17-41`.
- **IMPORTS**: Types only; no behavioral changes here.
- **GOTCHA**: Keep the new field optional so older history payloads still hydrate safely.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/hooks/useStream.ts`

- **IMPLEMENT**: Add Zod parsing for the detailed `checkpoint_2` validation payload and pass it through `setHitlPause`.
- **PATTERN**: Add the schema at module scope next to `HitlPauseSchema` per `frontend/src/hooks/useStream.ts:52-100`.
- **IMPORTS**: Reuse existing Zod style; do not move parsing into components.
- **GOTCHA**: The new field must survive both live `hitl_pause` events and `/history`-based recovery hydration.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/CheckpointPanel.tsx`

- **IMPLEMENT**: Render concrete `checkpoint_2` failures, such as missing keyword placement, meta length, word count, or forbidden stems; if automation remains brittle, add stable `data-testid` attributes to the buttons and feedback textarea.
- **PATTERN**: Follow the existing warning box structure from `frontend/src/components/CheckpointPanel.tsx:203-210`.
- **IMPORTS**: Existing shadcn `Button` / `Textarea` only.
- **GOTCHA**: Keep UX concise; this panel should explain why validation failed, not dump raw JSON.
- **VALIDATE**: `cd frontend && npm run lint`

### UPDATE `frontend/src/components/ShadowPanel.tsx`

- **IMPLEMENT**: Add stable `data-testid` hooks to Shadow approve/reject controls and feedback textarea only if the new Playwright harness needs them.
- **PATTERN**: Keep behavior identical to `frontend/src/components/ShadowPanel.tsx:189-227`.
- **IMPORTS**: None beyond current component dependencies.
- **GOTCHA**: This task is optional and should be skipped if role/placeholder selectors remain stable in Playwright.
- **VALIDATE**: `cd frontend && npm run lint`

### CREATE `tests/unit/api/test_author_input.py`

- **IMPLEMENT**: Cover labeled Polish briefs, explicit request-field overrides, unlabeled fallback, deduped keyword splitting, and requirements-to-`context_dynamic` mapping.
- **PATTERN**: Keep tests narrow and deterministic like `tests/unit/api/test_chat.py`.
- **IMPORTS**: New normalizer only; do not instantiate the full FastAPI app unless necessary.
- **GOTCHA**: Add at least one case matching the 2026-04-29 E2E brief shape.
- **VALIDATE**: `uv run pytest tests/unit/api/test_author_input.py`

### CREATE `tests/unit/graph/test_writer_autorepair.py`

- **IMPLEMENT**: Assert that a failed first pass produces a second-attempt prompt containing explicit failed constraints and the previous draft, instead of replaying the same prompt verbatim.
- **PATTERN**: Mirror the fake-LLM style from `tests/unit/graph/test_writer_prompt_budget.py`.
- **IMPORTS**: Mock `get_draft_llm`, `_validate_draft`, and cost helpers as in existing writer tests.
- **GOTCHA**: Also assert that successful first-pass drafts do not pay the repair-prompt penalty.
- **VALIDATE**: `uv run pytest tests/unit/graph/test_writer_autorepair.py`

### CREATE `tests/fixtures/author_quality_cases.json`

- **IMPLEMENT**: Add a small but representative set of Polish Author prompts:
  - a labeled `Temat / Słowa kluczowe / Wymagania` brief
  - a plain topic-only brief
  - a brief with explicit keyword list
  - a brief with stronger style constraints
- **PATTERN**: Keep fixtures human-readable and stable for repeated local runs.
- **IMPORTS**: JSON only.
- **GOTCHA**: Do not include secrets or external proprietary copy.
- **VALIDATE**: `jq . tests/fixtures/author_quality_cases.json`

### CREATE `scripts/evaluate_author_quality.py`

- **IMPLEMENT**: Run the curated Author cases through the current runtime, record `draft_validated`, failed constraints, retry counts, and artifact summaries under `.planning/artifacts/author-quality-<timestamp>/`.
- **PATTERN**: Mirror the artifact-writing style used by existing validation scripts and the planning artifacts described in `.planning/STATE.md`.
- **IMPORTS**: Existing graph/runtime helpers; avoid adding a new external evaluation framework.
- **GOTCHA**: This is a local regression harness, not a production dependency. Keep it non-interactive and deterministic in output shape.
- **VALIDATE**: `uv run python scripts/evaluate_author_quality.py --cases tests/fixtures/author_quality_cases.json`

### CREATE `scripts/playwright_checkpoint_recovery_regressions.py`

- **IMPLEMENT**: Add a focused Playwright harness for reload + reject paths across Shadow, `checkpoint_1`, and `checkpoint_2`, with screenshots and exact network assertions.
- **PATTERN**: Mirror helper functions such as `wait_for_history()`, screenshot capture, and request counting from `scripts/playwright_detached_runtime_journey.py` and `scripts/playwright_post_signoff_regressions.py`.
- **IMPORTS**: `playwright.sync_api`, stdlib polling helpers, existing frontend/api URLs.
- **GOTCHA**: Treat “fails only in agent-browser” as non-reproducible noise. The script should only fail on observable browser/app regressions.
- **VALIDATE**: `uv run python scripts/playwright_checkpoint_recovery_regressions.py --frontend-url http://127.0.0.1:3000 --api-url http://127.0.0.1:8000`

### UPDATE `.planning/STATE.md`, `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`

- **IMPLEMENT**: After all code and validation are complete, record the Author quality fix, the new Playwright recovery proof, and any new artifact paths in the root planning docs.
- **PATTERN**: Follow the planning-discipline rules from `AGENTS.md` and keep root docs as the live source of truth.
- **IMPORTS**: None.
- **GOTCHA**: Do not update planning docs early. They must reflect verified code and validation results from the same patch.
- **VALIDATE**: `git diff -- .planning/STATE.md .planning/PROJECT.md .planning/REQUIREMENTS.md .planning/ROADMAP.md`

---

## TESTING STRATEGY

Use a layered strategy: deterministic unit tests for normalization and writer retry logic, then Playwright for checkpoint recovery, then a curated local Author-quality sweep to guard against prompt regressions.

### Unit Tests

- `tests/unit/api/test_author_input.py`
  - Verify exact parsing and fallback rules for Author brief normalization.
- `tests/unit/api/test_chat.py`
  - Verify normalized values reach the initial graph state without breaking thread injection or Shadow mode.
- `tests/unit/api/test_chat_history.py`
  - Verify richer `checkpoint_2` validation details survive `/history` recovery.
- `tests/unit/graph/test_writer_autorepair.py`
  - Verify repair prompts are targeted and retry behavior is no longer blind.
- Existing writer/structure tests
  - Re-run `test_writer_low_corpus.py`, `test_writer_prompt_budget.py`, and `test_structure_node.py` to ensure prompt-budget and low-corpus behaviors still hold.

### Integration Tests

- `scripts/evaluate_author_quality.py`
  - Run the curated prompt set and compare first-pass validation status plus failure reasons across cases.
- `scripts/playwright_checkpoint_recovery_regressions.py`
  - Prove reload + reject recovery for Shadow, `checkpoint_1`, and `checkpoint_2`.
- Existing Playwright scripts
  - Re-run `scripts/playwright_detached_runtime_journey.py` and `scripts/playwright_post_signoff_regressions.py` to avoid regressions in already validated paths.

### Edge Cases

- Labeled brief with empty `Słowa kluczowe:` line should not synthesize garbage keywords.
- Unlabeled freeform prompt should remain backward-compatible and should not be misparsed as a structured brief.
- Keyword splitting should tolerate commas, semicolons, extra whitespace, and duplicates.
- Retry repair prompt should preserve previous draft context without double-appending stale instructions.
- Recovery payload must still hydrate safely when older sessions do not contain `draft_validation_details`.
- Shadow reload + reject must not replay `POST /api/chat/resume` after page refresh.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and high-confidence behavior.

### Level 1: Syntax & Style

- `uv run ruff check .`
- `cd frontend && npm run lint`

### Level 2: Unit Tests

- `uv run pytest tests/unit/api/test_author_input.py tests/unit/api/test_chat.py tests/unit/api/test_chat_history.py`
- `uv run pytest tests/unit/graph/test_writer_autorepair.py tests/unit/graph/test_writer_low_corpus.py tests/unit/graph/test_writer_prompt_budget.py tests/unit/graph/test_structure_node.py`

### Level 3: Integration Tests

- `uv run python scripts/evaluate_author_quality.py --cases tests/fixtures/author_quality_cases.json`
- `uv run python scripts/playwright_checkpoint_recovery_regressions.py --frontend-url http://127.0.0.1:3000 --api-url http://127.0.0.1:8000`
- `uv run python scripts/playwright_detached_runtime_journey.py --frontend-url http://127.0.0.1:3000 --api-url http://127.0.0.1:8000`
- `uv run python scripts/playwright_post_signoff_regressions.py --frontend-url http://127.0.0.1:3000 --api-url http://127.0.0.1:8000`

### Level 4: Manual Validation

1. Start backend and frontend locally.
2. Submit the same labeled Author brief shape used in the E2E sweep and verify:
   - `topic` is cleanly interpreted
   - explicit keywords appear in H1/intro validation logic
   - `checkpoint_2` either arrives with `draft_validated=true` on first pass or shows concrete failed checks
3. Reload on Author `checkpoint_1`, reject with a note, and verify the next paused state reflects `cp1_iterations + 1` without duplicate resume POSTs.
4. Reload on Author `checkpoint_2`, reject with feedback, and verify regenerated draft plus updated `cp2_iterations`.
5. Reload on Shadow checkpoint, reject with feedback, and verify the next checkpoint is recovered with incremented `iteration_count`.

### Level 5: Additional Validation (Optional)

- If `agent-browser` is still used exploratorily, compare its behavior against the Playwright artifact run before treating any discrepancy as a product issue.

---

## ACCEPTANCE CRITERIA

- [ ] A labeled Author brief no longer causes the entire raw multi-line brief to become the primary SEO keyword.
- [ ] User requirements are routed into `context_dynamic` instead of polluting `topic`.
- [ ] Writer retries after validation failure include targeted repair guidance derived from concrete failed checks.
- [ ] `checkpoint_2` and `/history` surface detailed validation failures, not only a generic warning string.
- [ ] The curated Author quality sweep records no failures caused by the old `primary_keyword = raw brief` behavior.
- [ ] Playwright proves reload + reject recovery for Shadow, `checkpoint_1`, and `checkpoint_2` with exact resume-request counts.
- [ ] No recovery behavior is changed solely on the basis of `agent-browser` quirks.
- [ ] Existing detached-runtime, post-signoff, lint, and relevant unit tests continue to pass.
- [ ] Root planning docs are updated only after implementation and validation are complete.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full relevant test suite passes
- [ ] Playwright recovery harness artifacts captured
- [ ] Author quality eval artifacts captured
- [ ] Acceptance criteria all met
- [ ] Planning docs updated to match verified repo state

---

## NOTES

- Recommended scope boundary: treat the structured Author form UX as a follow-up unless backend normalization plus clearer placeholder/help text still leaves too much ambiguity. The observed E2E failure can be addressed without a full frontend input redesign.
- The strongest likely root causes are code-level, not “model mood”:
  - web requests currently discard structured keywords
  - writer retries currently repeat without explicit failure feedback
- Because the repo already has working recovery architecture (`/history`, detached runtime, persisted checkpoints), the second workstream should default to proof-first, patch-second.
- If Playwright does not reproduce the agent-browser flakiness, the correct outcome is improved regression coverage and optional automation hooks, not speculative product logic changes.
