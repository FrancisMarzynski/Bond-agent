# Feature: Fix Research-Report Truncation

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to the current Bond invariants: do not change graph routing, do not change any HITL interrupt payload shapes, and do not regress the existing `low_corpus`, `cp1_feedback`, or `cp2_feedback` behaviors while improving prompt context quality.

## Feature Description

The Author pipeline currently generates a structured research artifact twice:

- `research_report`: Markdown for UI/HITL display
- `research_data`: structured facts, statistics, and sources already stored in state

But the two downstream quality-critical nodes do not consume that artifact faithfully:

- `bond/graph/nodes/structure.py:39-40` and `:58-59` hard-cut the report with `research_report[:2000]`
- `bond/graph/nodes/writer.py:288-289` hard-cuts it again with `research_report[:3000]`

That means late facts, statistics, and sources are silently discarded before the outline or fresh draft are generated, even though the upstream researcher already paid for and persisted them. The problem is especially visible because `researcher_node` can retain up to 20 unique sources (`bond/graph/nodes/researcher.py:17-18, 148-194`), while the writer prompt still only sees the first few thousand characters.

This fix should remove blind character slicing and replace it with a token-aware, section-aware research-context selection strategy that preserves as much useful research as the configured model budget safely allows.

## User Story

As an editor using Author mode  
I want the structure and draft nodes to use the full available research whenever it fits, and to degrade intelligently when it does not  
So that the outline and final article reflect the complete research set instead of an arbitrary early substring

## Problem Statement

The current code has three concrete issues:

- The truncation is character-based, not token-based, so it does not match actual model budgets and is especially lossy for Polish text.
- The truncation is blind: it preserves the beginning of the Markdown string rather than prioritizing all facts/statistics and then as many sources as possible.
- The structured `research_data` state already exists (`bond/graph/state.py:28-33`, `bond/graph/nodes/researcher.py:55-87, 319-327`) but downstream nodes ignore it and instead slice the presentation-oriented Markdown report.

This also diverges from existing planning guidance:

- `.planning/research/PITFALLS.md:172-183` warns against silent context truncation and recommends explicit token budgeting.
- `.planning/research/SUMMARY.md:81-85` repeats that research context should be budgeted by tokens, not characters.
- `.planning/STATE.md:147-150` already lists reducing/removing `research_report` truncation as the first post-v1 quality candidate.

There is also a testing gap: the current graph-unit coverage only protects the low-corpus gate (`tests/unit/graph/test_writer_low_corpus.py:54-107`). There are no regression tests proving that late-report content survives prompt assembly when the budget allows it.

## Solution Statement

Implement a shared, token-aware research-context utility and route both `structure_node` and the writer fresh-draft path through it.

The solution should work like this:

1. Start with the full `research_report` unchanged.
2. If the fully assembled prompt fits the model's input budget, keep the full report.
3. If it does not fit, switch to a deterministic, denser rendering based on `research_data`:
   - keep all `fakty`
   - keep all `statystyki`
   - keep as many `zrodla` as the budget allows
4. If source compaction is still insufficient, fall back to a core-only research context (`fakty` + `statystyki`) with an explicit omission marker rather than a raw `[:N]` slice.
5. Reuse the already-configured LLM object for token counting so the logic follows the actual active model configuration.

This preserves quality under current defaults, stays safe for alternative model configurations, and avoids adding new graph state or changing any frontend/API contracts.

## Feature Metadata

**Feature Type**: Bug Fix / Quality Improvement  
**Estimated Complexity**: Medium  
**Primary Systems Affected**: `researcher` output consumption, `structure_node`, `writer_node`, prompt assembly utilities, graph unit tests  
**Dependencies**: Existing `langchain-openai` / `langchain-core` token counting APIs already present in the repo; no new runtime dependency should be required

---

## VERIFIED BASELINE

These existing behaviors must remain unchanged:

- `researcher_node` already produces both `research_report` and structured `research_data` (`bond/graph/nodes/researcher.py:249-331`).
- `structure_node` already uses `get_draft_llm(max_tokens=800, temperature=0)` and tracks token/cost accumulation in `tokens_used_research` (`bond/graph/nodes/structure.py:12, 66-77`).
- `writer_node` already preserves the locked `low_corpus` HITL contract and only injects `cp2_feedback` on retry attempt 0 (`bond/graph/nodes/writer.py:324-353, 367-378`).
- `WRITER_SYSTEM_PROMPT` already instructs the model to ground claims in supplied research (`bond/prompts/writer.py:42-74`).

Local runtime observation worth preserving during implementation:

- `uv run python` currently shows `get_draft_llm()` returns a `RunnableWithFallbacks` exposing `get_num_tokens`, `get_num_tokens_from_messages`, `profile.max_input_tokens=128000`, and `max_tokens=4096` under the default `gpt-4o` draft setup.

That observation lowers the immediate overflow risk for current defaults, but the implementation should still keep a hard budget path for alternate model settings.

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `bond/graph/nodes/structure.py` (lines 12-19, 21-24, 39-40, 58-60, 66-77)
  - Why: Contains both current truncation sites and the existing token/cost accounting that must stay intact.
- `bond/graph/nodes/writer.py` (lines 223-296, 315-323, 354-416)
  - Why: Contains the writer prompt builder, the second truncation site, and the retry loop whose behavior must not change.
- `bond/graph/nodes/researcher.py` (lines 55-87, 148-194, 197-246, 307-327)
  - Why: Defines the structured `ResearchData` shape, source caps, and the canonical markdown rendering that downstream nodes should consume more intelligently.
- `bond/graph/state.py` (lines 28-33, 69-72)
  - Why: Confirms `research_data` already exists in state and no new state field is necessary.
- `bond/llm.py` (lines 21-23, 52-67, 88-105)
  - Why: Centralized LLM factory and output-token configuration; any token-budget logic must follow this configuration rather than hardcoding model assumptions.
- `bond/prompts/context.py` (lines 35-60)
  - Why: Shows the current prompt-assembly pattern for reusable context blocks.
- `bond/prompts/writer.py` (lines 42-74)
  - Why: Writer system prompt already depends on strong research grounding; losing research context directly weakens this contract.
- `tests/unit/graph/test_writer_low_corpus.py` (lines 54-107)
  - Why: Existing unit-test pattern for monkeypatching graph-node collaborators without requiring full LLM dependencies.
- `pyproject.toml` (lines 7-35)
  - Why: Confirms current dependencies include `langchain-openai` and `langchain-anthropic`; prefer using their built-in token-counting interfaces before adding any new package.
- `.planning/STATE.md` (lines 147-163)
  - Why: Confirms this is the currently selected post-v1 quality issue and should be updated after implementation/validation completes.
- `.planning/research/PITFALLS.md` (lines 172-183)
  - Why: Source-of-truth warning about context-window overflow and the recommendation to budget research context explicitly.
- `.planning/research/SUMMARY.md` (lines 81-85)
  - Why: Reinforces the same token-budgeting requirement at the roadmap-summary level.
- `.planning/COMMUNICATION_STYLE.md` (lines 33-41)
  - Why: Reconfirms that Structure uses a deterministic, fact-oriented model profile while Writer uses a higher-output drafting profile; this affects prompt-budget strategy.

### New Files to Create

- `bond/prompts/research_context.py`
  - Purpose: Shared deterministic renderer/variant generator for full-report, structured, and compacted research-context variants.
- `tests/unit/graph/test_research_context.py`
  - Purpose: Pure unit tests for research-context rendering and degradation order.
- `tests/unit/graph/test_structure_node.py`
  - Purpose: Node-level regression tests proving `structure_node` no longer blind-slices the report when the prompt fits budget.
- `tests/unit/graph/test_writer_prompt_budget.py`
  - Purpose: Writer-side regression tests proving the fresh-draft prompt keeps late-report content when budget allows and degrades by source count, not raw substring.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [LangChain ChatOpenAI API Reference](https://api.python.langchain.com/en/latest/openai/chat_models/langchain_openai.chat_models.base.ChatOpenAI.html)
  - Specific sections: `get_num_tokens`, `get_num_tokens_from_messages`, `tiktoken_model_name`
  - Why: Confirms the repo can use the active model wrapper itself for token counting instead of introducing a separate tokenizer path first.
- [LangChain BaseChatModel API Reference](https://api.python.langchain.com/en/latest/core/language_models/langchain_core.language_models.chat_models.BaseChatModel.html)
  - Specific section: generic token-counting methods
  - Why: Provides the provider-agnostic fallback behavior if the active wrapped model is not OpenAI-specific.
- [OpenAI Conversation State Guide](https://platform.openai.com/docs/guides/conversation-state?api-mode=chat)
  - Specific section: "Managing context for text generation"
  - Why: Confirms that context-window budgeting must account for both input and output tokens together.
- [OpenAI Text Generation Parameter Details](https://platform.openai.com/docs/guides/text-generation/parameter-details#managing-tokens)
  - Specific section: "Managing tokens"
  - Why: Reinforces token-based budgeting and the difference between string length and model token count.

### Patterns to Follow

**Keep node contracts stable**

- `structure_node` stays async and returns a plain state patch.
- `writer_node` keeps the existing `low_corpus` interrupt, retry behavior, and return shape.

**Prefer existing structured state over reparsing display markdown**

- Use `research_data` when present; it is already the densest canonical representation of the research.

**Token-budget with the real model object**

- Follow `bond/llm.py:88-105`; do not hardcode a single model name or assume current defaults forever.

**Preserve downstream prompt semantics**

- Structure still needs a research block in Polish.
- Writer revision mode (`cp2_feedback` + `current_draft`) should stay focused on targeted corrections, not reopen the whole research budget path unless tests expose a concrete problem.

**Anti-patterns to avoid**

- Do not replace `[:2000]` / `[:3000]` with larger magic numbers.
- Do not reparse `research_report` markdown when `research_data` is already available.
- Do not change graph edges, HITL payloads, or state schema to solve a prompt-assembly problem.
- Do not add a new dependency when built-in model token counting is sufficient.

---

## IMPLEMENTATION PLAN

### Phase 1: Shared Research-Context Variants

Create a reusable utility that can emit progressively denser research-context variants in a deterministic order.

**Tasks:**

- Add a small prompt utility that renders research context from `research_data`.
- Make the utility expose multiple variants in descending fidelity order: full report, structured all-sources, structured reduced-sources, structured core-only.
- Keep the degradation strategy explicit and testable.

### Phase 2: Structure Node Budgeting

Replace the current hard slice in `structure_node` with prompt-budget selection based on the actual active model.

**Tasks:**

- Build the full prompt candidate first.
- Count tokens on the fully assembled prompt.
- Keep the first research-context variant that fits the node's available input budget after reserving output tokens and a small safety margin.

### Phase 3: Writer Fresh-Draft Budgeting

Apply the same budgeting strategy to the writer's fresh-draft path without changing targeted revision semantics.

**Tasks:**

- Budget the research context once before the retry loop.
- Feed the chosen research block into `_build_writer_user_prompt`.
- Keep `cp2_feedback` behavior, `WRITER_SYSTEM_PROMPT`, low-corpus handling, and retry logic unchanged.

### Phase 4: Regression Tests and Planning-Doc Sync

Add focused tests around the new helper and both downstream nodes, then sync root planning docs after implementation passes validation.

**Tasks:**

- Add pure unit coverage for the helper.
- Add node-level tests proving the old blind slice is gone.
- Update `.planning/STATE.md` after code/tests land so the selected post-v1 item is marked complete and the next task is no longer stale.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### CREATE `bond/prompts/research_context.py`

- **IMPLEMENT**: Add a deterministic research-context utility. It should expose a small value object or iterator that yields prompt-ready variants in this order:
  - untouched `research_report`
  - structured rendering of all `fakty`, all `statystyki`, all `zrodla`
  - the same structured rendering with progressively fewer `zrodla`
  - core-only rendering (`fakty` + `statystyki`) with an explicit omission note
- **PATTERN**: Follow the render-only utility style from `bond/prompts/context.py:35-60`; use the existing `ResearchData` shape from `bond/graph/nodes/researcher.py:55-87`.
- **IMPORTS**: Standard-library only if possible (`dataclasses`, `typing`); keep this helper dependency-light.
- **GOTCHA**: The goal is not "summarize again with an LLM". This helper must be deterministic and non-LLM.
- **VALIDATE**: `uv run pytest tests/unit/graph/test_research_context.py`

### UPDATE `bond/graph/nodes/structure.py`

- **IMPLEMENT**: Remove both `research_report[:2000]` slices. Use the new helper to try research-context variants against the fully assembled structure prompt and keep the first one that fits the model's available input budget.
- **PATTERN**: Preserve existing async flow, `get_draft_llm(max_tokens=800, temperature=0)`, and token/cost accounting from `bond/graph/nodes/structure.py:12, 66-77`.
- **IMPORTS**: Add a module logger and the new research-context helper.
- **GOTCHA**: Reserve the node's configured output budget plus a small fixed safety margin before accepting an input variant. If the model profile is unavailable, fall back to a conservative default budget rather than reinstating character slicing.
- **VALIDATE**: `uv run pytest tests/unit/graph/test_structure_node.py`

### UPDATE `bond/graph/nodes/writer.py`

- **IMPLEMENT**: Remove `research_report[:3000]` from `_build_writer_user_prompt` fresh-draft mode. Compute a budgeted `research_context` once before the retry loop and inject that value into each fresh-draft attempt.
- **PATTERN**: Keep the low-corpus gate (`bond/graph/nodes/writer.py:324-353`), retry loop (`367-403`), and `cp2_feedback` attempt-0-only behavior (`376-377`) unchanged.
- **IMPORTS**: New helper only; do not rewrite `WRITER_SYSTEM_PROMPT`.
- **GOTCHA**: The targeted revision branch (`cp2_feedback` + `current_draft`) currently operates on the existing draft and feedback only. Preserve that behavior unless a test demonstrates a concrete regression that requires research re-injection.
- **VALIDATE**: `uv run pytest tests/unit/graph/test_writer_prompt_budget.py tests/unit/graph/test_writer_low_corpus.py`

### CREATE `tests/unit/graph/test_research_context.py`

- **IMPLEMENT**: Add pure tests that verify:
  - the full report variant is offered first
  - structured variants preserve all `fakty` and `statystyki`
  - source compaction reduces `zrodla` count before dropping facts/statistics
  - the final fallback uses an explicit omission marker instead of raw substring truncation
- **PATTERN**: Keep tests import-light and deterministic.
- **IMPORTS**: `pytest`; no real LLM clients.
- **GOTCHA**: Use sentinel strings in late sources so failures clearly show whether source-tail content survived.
- **VALIDATE**: `uv run pytest tests/unit/graph/test_research_context.py`

### CREATE `tests/unit/graph/test_structure_node.py`

- **IMPLEMENT**: Add node-level tests with a fake draft model exposing `get_num_tokens` and `ainvoke`, then assert:
  - when the prompt budget is large enough, late-report sentinel content reaches the LLM prompt
  - when the prompt budget is small, the node switches variants instead of using a raw character slice
- **PATTERN**: Mirror the monkeypatch/import isolation style from `tests/unit/graph/test_writer_low_corpus.py:1-29`.
- **IMPORTS**: `pytest`, `types.SimpleNamespace`, `importlib`, light fakes.
- **GOTCHA**: Keep the test focused on prompt assembly and return payload; do not require real OpenAI or Anthropic packages.
- **VALIDATE**: `uv run pytest tests/unit/graph/test_structure_node.py`

### CREATE `tests/unit/graph/test_writer_prompt_budget.py`

- **IMPLEMENT**: Add writer-side regression tests that verify:
  - the fresh-draft prompt includes late-report sentinel content when the assembled messages fit budget
  - under a tight budget, the writer keeps all facts/statistics and drops source count before losing core research
  - low-corpus behavior remains unchanged by the new helper integration
- **PATTERN**: Reuse the fake-module bootstrap style from `tests/unit/graph/test_writer_low_corpus.py`.
- **IMPORTS**: `pytest`, import stubs, `SimpleNamespace`.
- **GOTCHA**: Assert against the final `HumanMessage` content, not just helper output, so the test fails if someone reintroduces slicing inside `_build_writer_user_prompt`.
- **VALIDATE**: `uv run pytest tests/unit/graph/test_writer_prompt_budget.py`

### UPDATE `.planning/STATE.md`

- **IMPLEMENT**: After the fix ships and validations pass, remove this item from the "Post-v1 Candidates" backlog and update `Session Continuity -> Next task` so root planning docs reflect the new reality.
- **PATTERN**: Follow the repo rule that root planning docs are the live source of truth.
- **IMPORTS**: None.
- **GOTCHA**: Do not mark the item complete before code + tests are actually merged/passing.
- **VALIDATE**: `rg -n "research_report truncation|obcinanie .*research_report|Next task" .planning/STATE.md`

---

## TESTING STRATEGY

The key regression is prompt assembly, not API shape. Testing should therefore focus on deterministic unit tests at the helper and node boundaries.

### Unit Tests

- Pure helper tests for research-context variant ordering and compaction rules.
- `structure_node` tests with a fake model/token counter proving full-fit vs compacted-fit behavior.
- Writer fresh-draft prompt tests proving late-report content survives when budget allows.
- Existing `test_writer_low_corpus.py` rerun unchanged to confirm the low-corpus contract was not perturbed.

### Integration Tests

- Not strictly required for the first implementation pass because no HTTP, graph routing, or frontend contract changes are expected.
- Optional follow-up: a small graph-level smoke test can confirm the node imports still compose.

### Edge Cases

- `research_data` missing but `research_report` present
- `research_report` empty
- many-source report that fits current default `gpt-4o` budget without compaction
- provider/model profile absent or incomplete on the wrapped LLM object
- writer retry loop reusing the same already-budgeted research context across attempts
- `cp2_feedback` targeted revision path remaining unchanged

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and feature correctness.

### Level 1: Syntax & Style

```bash
uv run ruff check bond/graph/nodes/structure.py bond/graph/nodes/writer.py bond/prompts/research_context.py tests/unit/graph/
uv run ruff format bond/graph/nodes/structure.py bond/graph/nodes/writer.py bond/prompts/research_context.py tests/unit/graph/
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/graph/test_research_context.py
uv run pytest tests/unit/graph/test_structure_node.py
uv run pytest tests/unit/graph/test_writer_prompt_budget.py tests/unit/graph/test_writer_low_corpus.py
```

### Level 3: Focused Graph Regression

```bash
uv run pytest tests/unit/graph/
```

### Level 4: Broader Non-Graph Sanity

```bash
uv run pytest tests/unit/api/test_chat.py tests/unit/api/test_chat_history.py tests/unit/api/test_stream.py
```

### Level 5: Manual Validation

1. Run the backend: `uv run uvicorn bond.api.main:app --reload --port 8000`
2. Trigger an Author session with a topic that produces a longer research report.
3. Confirm Checkpoint 1 still shows the full `research_report` in UI and that the generated outline reflects facts/sources near the end of the report, not only the report prefix.
4. Approve Checkpoint 1 and confirm the first generated draft uses late-report facts/statistics that previously lived beyond the old `[:3000]` boundary.
5. Confirm `low_corpus`, `cp1_feedback`, and `cp2_feedback` flows behave exactly as before.

---

## ACCEPTANCE CRITERIA

- [ ] `bond/graph/nodes/structure.py` no longer contains `research_report[:2000]`
- [ ] `bond/graph/nodes/writer.py` no longer contains `research_report[:3000]`
- [ ] When the full research prompt fits the configured model budget, `structure_node` and the writer fresh-draft path pass the full report through unchanged
- [ ] When the full report does not fit, degradation is token-aware and section-aware, not raw character slicing
- [ ] `research_data` is used as the primary compaction source when present
- [ ] `low_corpus`, `cp1_feedback`, `cp2_feedback`, routing, and cost/token accumulation behaviors are unchanged
- [ ] New helper and node-level regression tests cover both full-fit and compacted-fit paths
- [ ] Root planning docs are updated after the implementation is validated

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full affected unit suite passes
- [ ] No linting or formatting errors remain
- [ ] Manual Author-mode validation confirms improved research carry-through
- [ ] `.planning/STATE.md` reflects the completed fix and the next real post-v1 task

---

## NOTES

- This is a high-ROI fix because it improves two quality-critical prompts without changing the graph shape, frontend, or HITL contracts.
- The safest implementation is not "remove truncation and hope": current defaults are generous, but the correct long-term behavior is "full research when it fits, structured compaction when it does not."
- Another viable implementation would use a fully generic token-budget helper in `bond/llm.py`, but that is broader than needed. The plan deliberately scopes the first pass to research-context rendering plus node-local budget checks.
- Confidence score for one-pass implementation success: **8.5/10**
  - Strong factors: clear call sites, existing structured state, existing token-counting APIs, small blast radius
  - Main risk: provider-specific token-count/profile behavior on non-default model configurations; mitigate with conservative fallback budget logic and fake-model tests
