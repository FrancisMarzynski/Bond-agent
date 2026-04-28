# Feature: Blog → Social Media Repurposing (Scenario C)

The following plan should be complete, but validate patterns and codebase state before implementing.
Pay special attention to the graph routing pattern and the `_node_registry` wiring in `graph.py`.

## Feature Description

A new "Repurpose" mode that takes a finished blog article and generates tailored post variants for Facebook, LinkedIn, Instagram, and X (Twitter). Each variant respects platform character limits and idiomatic tone. Output is plain Markdown text ready for manual copy-paste — no auto-publishing. The user can edit variants before copying.

## User Story

As a marketing employee,
I want to paste a finished blog article and receive ready-to-use social media posts for all four platforms at once,
So that I can distribute content across channels without rewriting each post from scratch.

## Problem Statement

Writing 4 distinct social media variants from a single article is repetitive, time-consuming, and prone to ignoring platform-specific conventions (Twitter length, LinkedIn professional tone, Instagram visual storytelling). Currently there is no automated path for this in Bond.

## Solution Statement

Add a third graph branch (`repurpose`) alongside the existing `author` and `shadow` branches. A single `repurpose_node` generates all four platform variants in one LLM call using `with_structured_output`. A new `/repurpose` frontend route displays the four variants in tabs, each independently editable.

**Character limits enforced:**
| Platform | Hard Limit | Target Practical Length |
|---|---|---|
| X (Twitter) | 280 chars | ≤280 chars |
| Instagram | 2,200 chars | 800–1,200 chars |
| LinkedIn | 3,000 chars | 1,200–2,000 chars |
| Facebook | 63,206 chars | 1,000–2,000 chars |

## Feature Metadata

**Feature Type**: New Capability  
**Estimated Complexity**: Medium  
**Primary Systems Affected**: `bond/graph/state.py`, `bond/graph/graph.py`, `bond/graph/nodes/` (new file), `bond/schemas.py`, `frontend/src/app/repurpose/`, `frontend/src/components/RepurposePanel.tsx`, `frontend/src/store/chatStore.ts`, `frontend/src/components/Sidebar.tsx`, `frontend/src/components/ModeToggle.tsx`  
**Dependencies**: No new Python libraries. No new npm packages.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `bond/graph/state.py` (lines 1-77) — full `BondState` TypedDict; add `social_variants` field here
- `bond/graph/graph.py` (lines 25-53) — `_node_registry` and `route_mode()` function to extend
- `bond/graph/graph.py` (lines 107-153) — `build_author_graph()` — add new node and edge here
- `bond/graph/nodes/shadow_annotate.py` (lines 28-88) — `with_structured_output` Pydantic pattern to mirror for `SocialVariants`
- `bond/graph/nodes/shadow_checkpoint.py` (lines 31-98) — node returning `dict | Command` pattern
- `bond/graph/nodes/writer.py` (lines 300-402) — async node function structure, `get_draft_llm()` usage
- `bond/llm.py` (lines 83-101) — `get_draft_llm()` factory
- `bond/schemas.py` (lines 28-35) — `StreamEvent.type` Literal — add `"social_variants"` here
- `bond/api/stream.py` (lines 11-22) — `_KNOWN_NODES` and `_STAGE_MAP` — register new node here
- `bond/api/routes/chat.py` (lines 229-248) — `_emit_post_stream_events` — add social_variants emission here
- `bond/api/routes/chat.py` (lines 273-309) — `chat_stream` endpoint — add `"repurpose"` mode to initial state
- `frontend/src/store/chatStore.ts` (lines 1-124) — add `socialVariants` field and setter
- `frontend/src/components/ModeToggle.tsx` (lines 1-39) — add "Repurpose" to the toggle
- `frontend/src/components/Sidebar.tsx` — add `/repurpose` nav link
- `frontend/src/hooks/useStream.ts` (lines 152-164) — `shadow_corrected_text` / `annotations` event cases to mirror for `social_variants`

### New Files to Create

- `bond/graph/nodes/repurpose.py` — the `repurpose_node` implementation
- `frontend/src/app/repurpose/page.tsx` — Next.js route for the Repurpose page
- `frontend/src/app/repurpose/error.tsx` — route-level error boundary (mirror `shadow/error.tsx`)
- `frontend/src/components/RepurposePanel.tsx` — full UI component for Repurpose mode

### Relevant Documentation

- Platform character limits are well-established constants; no external API needed.

### Patterns to Follow

**`with_structured_output` Pydantic model** — mirror `shadow_annotate.py` approach:
```python
class SocialVariants(BaseModel):
    facebook: str = Field(description="...")
    linkedin: str = Field(description="...")
    instagram: str = Field(description="...")
    twitter: str = Field(description="...")

structured_llm = llm.with_structured_output(SocialVariants)
result: SocialVariants = await structured_llm.ainvoke([...])
```

**New graph branch** — mirror Shadow branch wiring in `graph.py`:
```python
# route_mode now has three outcomes:
def route_mode(state: BondState) -> Literal["duplicate_check", "shadow_analyze", "repurpose"]:
    mode = state.get("mode", "author")
    if mode == "shadow":
        return "shadow_analyze"
    if mode == "repurpose":
        return "repurpose"
    return "duplicate_check"

# In build_author_graph():
builder.add_conditional_edges(
    START,
    route_mode,
    {
        "duplicate_check": "duplicate_check",
        "shadow_analyze": "shadow_analyze",
        "repurpose": "repurpose",
    },
)
builder.add_edge("repurpose", END)
```

**SSE event for structured output** — mirror `shadow_corrected_text` case in `_emit_post_stream_events`:
```python
variants = st.get("social_variants") or {}
if variants:
    yield StreamEvent(
        type="social_variants",
        data=json.dumps(variants),
    ).model_dump_json()
```

**Frontend SSE handler** — mirror `shadow_corrected_text` case in `useStream.ts`:
```ts
case "social_variants": {
    const variants = typeof payload === "object" && payload !== null ? payload : {};
    useChatStore.getState().setSocialVariants(variants as SocialVariants);
    break;
}
```

**Mode routing in frontend** — `ModeToggle` maps mode → URL path:
- `"author"` → `/`
- `"shadow"` → `/shadow`
- `"repurpose"` → `/repurpose`

---

## IMPLEMENTATION PLAN

### Phase 1: Backend — State + Node

Add `social_variants` to `BondState`, create `repurpose_node`, register in graph.

### Phase 2: Backend — Graph Wiring + SSE Contract

Extend `route_mode`, add edge, update `_KNOWN_NODES`/`_STAGE_MAP`/`StreamEvent`, emit `social_variants` in `_emit_post_stream_events`.

### Phase 3: Frontend — Store + SSE Handler

Add `SocialVariants` type, `socialVariants` state, `setSocialVariants` action in `chatStore`. Handle `social_variants` event in `useStream`.

### Phase 4: Frontend — UI

`RepurposePanel` component, `/repurpose` route, `ModeToggle` + `Sidebar` updates.

---

## STEP-BY-STEP TASKS

### TASK 1 — UPDATE `bond/graph/state.py` — Add social_variants field

Add `social_variants` to `BondState` TypedDict.

- **IMPLEMENT**: Add `social_variants: NotRequired[Optional[dict[str, str]]]` in the "# --- Output ---" section of `BondState`
- **PATTERN**: `NotRequired[Optional[...]]` — mirror `tokens_used_research: NotRequired[int]` at line 69
- **VALIDATE**: `uv run python -c "from bond.graph.state import BondState; print('ok')"`

---

### TASK 2 — CREATE `bond/graph/nodes/repurpose.py`

New node that generates all four platform variants in a single structured LLM call.

- **IMPLEMENT**: Single async node function `repurpose_node(state: BondState) -> dict`
- **PATTERN**: `with_structured_output(SocialVariants)` — mirror `shadow_annotate.py:259`
- **IMPORTS**: `from bond.llm import get_draft_llm`, `from bond.graph.state import BondState`
- **GOTCHA**: Twitter hard limit is 280 chars. Validate and truncate or re-prompt if `len(result.twitter) > 280`. Use a simple re-prompt loop (max 2 attempts), not a full HITL interrupt.
- **GOTCHA**: Use `get_draft_llm(temperature=0)` for deterministic structured output — same as `shadow_annotate_node`.
- **GOTCHA**: The blog article comes from `state.get("original_text")` (user pastes the blog article as the chat message, same as Shadow mode input path).

```python
"""Repurpose node — generate social media variants from a blog article.

Input:  state["original_text"] — the full blog article (submitted as chat message)
Output: state["social_variants"] — dict with keys: facebook, linkedin, instagram, twitter
"""
from __future__ import annotations
import logging
from pydantic import BaseModel, Field
from bond.graph.state import BondState
from bond.llm import get_draft_llm

log = logging.getLogger(__name__)

TWITTER_MAX_CHARS = 280
_MAX_RETRIES = 2


class SocialVariants(BaseModel):
    facebook: str = Field(
        description=(
            "Facebook post: engaging, conversational tone, 1000-2000 characters. "
            "Include 1-2 relevant hashtags at the end."
        )
    )
    linkedin: str = Field(
        description=(
            "LinkedIn post: professional, insight-focused, 1200-2000 characters. "
            "Open with a strong hook. Include 3-5 relevant hashtags at the end."
        )
    )
    instagram: str = Field(
        description=(
            "Instagram caption: visual storytelling style, 800-1200 characters. "
            "End with a call to action and 5-10 hashtags on a new line."
        )
    )
    twitter: str = Field(
        description=(
            f"X (Twitter) post: punchy, max {TWITTER_MAX_CHARS} characters including any hashtag. "
            "Single key insight or hook that drives clicks. No emojis unless naturally fitting."
        )
    )


_SYSTEM_PROMPT = """\
Jesteś ekspertem od content marketingu w mediach społecznościowych. \
Na podstawie artykułu blogowego tworzysz dedykowane posty dla czterech platform. \
Każdy post ma być niezależny, dostosowany do specyfiki platformy, pisany po polsku. \
Nie parafrazuj — wyciągaj najciekawszy wątek lub cytat i zbuduj wokół niego angażujący przekaz."""


async def repurpose_node(state: BondState) -> dict:
    """Generate social media variants from original_text (blog article)."""
    article = (state.get("original_text") or "").strip()
    if not article:
        log.warning("repurpose: original_text is empty — returning empty variants.")
        return {"social_variants": {}}

    llm = get_draft_llm(max_tokens=2000, temperature=0)
    structured_llm = llm.with_structured_output(SocialVariants)

    user_msg = f"## ARTYKUŁ DO PRZETWORZENIA\n\n{article}"

    for attempt in range(_MAX_RETRIES + 1):
        result: SocialVariants = await structured_llm.ainvoke([
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ])

        if len(result.twitter) <= TWITTER_MAX_CHARS:
            break

        log.warning(
            "repurpose: twitter variant too long (%d chars), retry %d/%d",
            len(result.twitter), attempt + 1, _MAX_RETRIES
        )
        user_msg += (
            f"\n\n[UWAGA: Post na X musi mieć maksymalnie {TWITTER_MAX_CHARS} znaków. "
            f"Poprzednia wersja miała {len(result.twitter)} znaków — skróć go.]"
        )

    return {
        "social_variants": {
            "facebook": result.facebook,
            "linkedin": result.linkedin,
            "instagram": result.instagram,
            "twitter": result.twitter,
        }
    }
```

- **VALIDATE**: `uv run python -c "from bond.graph.nodes.repurpose import repurpose_node; print('ok')"`

---

### TASK 3 — UPDATE `bond/graph/graph.py` — Register node and wire new branch

- **IMPLEMENT**:
  1. Import `repurpose_node` from `bond.graph.nodes.repurpose`
  2. Add `"repurpose": _repurpose_node` to `_node_registry`
  3. Change `route_mode` return type to `Literal["duplicate_check", "shadow_analyze", "repurpose"]`
  4. Add `"repurpose"` branch to `route_mode` body
  5. In `build_author_graph()`, update `add_conditional_edges(START, ...)` path_map to include `"repurpose": "repurpose"`
  6. Add `builder.add_edge("repurpose", END)` after the shadow branch edges
- **PATTERN**: Shadow branch wiring at lines 141-147
- **GOTCHA**: LangGraph `path_map` in `add_conditional_edges` must list ALL possible return values of the routing function. If `route_mode` can return `"repurpose"`, it must be in the path_map — otherwise LangGraph raises a compile error.
- **VALIDATE**: `uv run python -c "from bond.graph.graph import build_author_graph; build_author_graph(); print('graph compiled ok')"`

---

### TASK 4 — UPDATE `bond/api/stream.py` — Register node in _KNOWN_NODES and _STAGE_MAP

- **IMPLEMENT**: Add `"repurpose"` to `_KNOWN_NODES` frozenset (line 11) and `_STAGE_MAP` dict (line 26) and `_NODE_LABELS` dict (line 42)
- **PATTERN**: Shadow nodes entries in those same dicts (lines 20, 35-36, 71-82)

```python
# _KNOWN_NODES: add "repurpose"
# _STAGE_MAP: "repurpose": "repurposing"
# _NODE_LABELS: "repurpose": {"start": "Tworzę warianty dla mediów społecznościowych...", "end": "Warianty gotowe"}
```

- **VALIDATE**: `uv run python -c "from bond.api.stream import _KNOWN_NODES, _STAGE_MAP; assert 'repurpose' in _KNOWN_NODES; print('ok')"`

---

### TASK 5 — UPDATE `bond/schemas.py` — Add social_variants to StreamEvent types

- **IMPLEMENT**: Add `"social_variants"` to the `Literal[...]` type in `StreamEvent.type` (line 35)
- **PATTERN**: `"annotations"` and `"shadow_corrected_text"` in the same Literal
- **VALIDATE**: `uv run python -c "from bond.schemas import StreamEvent; print('ok')"`

---

### TASK 6 — UPDATE `bond/api/routes/chat.py` — Emit social_variants in post-stream

In `_emit_post_stream_events` (lines 229-248), add `social_variants` emission after the shadow output block.

- **IMPLEMENT**: After the `annotations` emission block, add:

```python
social_variants = st.get("social_variants") or {}
if social_variants:
    yield StreamEvent(
        type="social_variants",
        data=json.dumps(social_variants),
    ).model_dump_json()
```

- **PATTERN**: `shadow_corrected_text` emission block at lines 237-241
- **VALIDATE**: `uv run python -c "from bond.api.routes.chat import _emit_post_stream_events; print('ok')"`

---

### TASK 7 — UPDATE `bond/api/routes/chat.py` — Handle repurpose in chat_stream

In `chat_stream` (lines 281-289), the `initial_state` already sets `original_text` for shadow mode. Add the same for repurpose mode.

- **IMPLEMENT**: Extend the `if req.mode == "shadow":` block to also handle `req.mode == "repurpose"`:

```python
if req.mode in ("shadow", "repurpose"):
    initial_state["original_text"] = req.message
```

- **VALIDATE**: `uv run python -m pytest tests/ -x -q` (existing tests must still pass)

---

### TASK 8 — UPDATE `frontend/src/store/chatStore.ts` — Add socialVariants state

- **IMPLEMENT**:
  1. Add `SocialVariants` type export
  2. Add `socialVariants: SocialVariants | null` to the store state
  3. Add `setSocialVariants: (v: SocialVariants | null) => void` action
  4. Initialize `socialVariants: null` in the initial state and in `resetSession`

```ts
export type SocialVariants = {
    facebook: string;
    linkedin: string;
    instagram: string;
    twitter: string;
};
```

- **PATTERN**: `hitlPause: HitlPause` and `setHitlPause` pattern in the same file
- **VALIDATE**: `cd frontend && npx tsc --noEmit`

---

### TASK 9 — UPDATE `frontend/src/hooks/useStream.ts` — Handle social_variants SSE event

Add a `case "social_variants"` to the `switch (eventType)` block in `consumeStream`.

- **IMPLEMENT**:

```ts
case "social_variants": {
    const variants = typeof payload === "object" && payload !== null
        ? payload as import("@/store/chatStore").SocialVariants
        : null;
    if (variants) {
        useChatStore.getState().setSocialVariants(variants);
    }
    break;
}
```

- **PATTERN**: `case "annotations"` at lines 160-163
- **VALIDATE**: `cd frontend && npx tsc --noEmit`

---

### TASK 10 — CREATE `frontend/src/components/RepurposePanel.tsx`

Two-phase component: input view (paste article) → output view (4 platform tabs).

- **IMPLEMENT**: 
  - Input view: `Textarea` for pasting blog article + "Przetwórz" button → calls `startStream(text, threadId, "repurpose", persistThreadId)`
  - Output view: 4 tabs (Facebook / LinkedIn / Instagram / X), each with an editable `textarea` and a copy-to-clipboard button
  - Show `isStreaming` skeleton while waiting
  - "Nowy artykuł" reset button clears state
- **PATTERN**: `ShadowPanel.tsx` — two-phase structure (input view / comparison view), `handleSubmit`, `handleReset`, `isStreaming` guard
- **IMPORTS**: `useChatStore` (for `socialVariants`, `isStreaming`, `threadId`), `useSession` (for `persistThreadId`), `useStream` (for `startStream`), `Textarea`, `Button`, shadcn/ui tabs if available — otherwise implement with simple state + conditional render
- **GOTCHA**: `socialVariants` may be `null` before first run — check before rendering the output view. Use `originalText` equivalent: store locally in component via `useState` to track "article has been submitted".
- **GOTCHA**: The "copy" button uses `navigator.clipboard.writeText(text)` — no library needed.

```tsx
// Skeleton output view structure:
const platforms: { key: keyof SocialVariants; label: string; limit: string }[] = [
    { key: "facebook", label: "Facebook", limit: "~1,500 znaków" },
    { key: "linkedin", label: "LinkedIn", limit: "~2,000 znaków" },
    { key: "instagram", label: "Instagram", limit: "~1,000 znaków" },
    { key: "twitter", label: "X (Twitter)", limit: "maks. 280 znaków" },
];
```

- **VALIDATE**: `cd frontend && npm run build`

---

### TASK 11 — CREATE `frontend/src/app/repurpose/page.tsx`

Minimal Next.js route page (mirrors `frontend/src/app/shadow/page.tsx`).

```tsx
import { RepurposePanel } from "@/components/RepurposePanel";
export default function RepurposePage() {
    return <RepurposePanel />;
}
```

---

### TASK 12 — CREATE `frontend/src/app/repurpose/error.tsx`

Route-level error boundary (mirrors `frontend/src/app/shadow/error.tsx`).

- **IMPLEMENT**: Copy `shadow/error.tsx` verbatim and update the page label if any.
- **VALIDATE**: `cd frontend && npm run build`

---

### TASK 13 — UPDATE `frontend/src/components/ModeToggle.tsx` — Add "Przetwarzaj" option

The current toggle is a binary Switch (Author/Shadow). Extend it to support three modes.

- **IMPLEMENT**: Replace the binary `Switch` with three `Button` variants (or a segmented control using Buttons with `variant="default"` for active, `variant="outline"` for inactive):

```tsx
const modes = [
    { label: "Autor", path: "/", mode: "author" },
    { label: "Cień", path: "/shadow", mode: "shadow" },
    { label: "Repurpose", path: "/repurpose", mode: "repurpose" },
] as const;
```

- **GOTCHA**: `isShadow` boolean logic must be replaced with a `currentMode` string derived from `pathname`.
- **VALIDATE**: `cd frontend && npx tsc --noEmit`

---

### TASK 14 — UPDATE `frontend/src/components/Sidebar.tsx` — Add /repurpose nav link

- **IMPLEMENT**: Add a navigation link to `/repurpose` in the Sidebar, using the same visual style as the existing corpus/shadow links.
- **VALIDATE**: `cd frontend && npm run build`

---

## TESTING STRATEGY

### Backend Unit Test

```python
# tests/unit/nodes/test_repurpose.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_repurpose_empty_text():
    state = {"original_text": ""}
    result = await repurpose_node(state)
    assert result["social_variants"] == {}

@pytest.mark.asyncio
async def test_repurpose_twitter_length():
    # Ensure the twitter variant never exceeds 280 chars
    # (requires mocking the LLM — use the existing conftest.py patterns)
    pass
```

### Manual End-to-End Test

1. Navigate to `/repurpose`
2. Paste a blog article (500+ words)
3. Click "Przetwórz"
4. Observe `StageProgress` showing `repurposing` stage
5. Verify 4 tabs appear with platform-specific content
6. Verify X (Twitter) tab content is ≤280 characters
7. Click "Kopiuj" on each tab — verify clipboard write works
8. Edit a variant manually — verify text changes persist locally

### Edge Cases

- Empty input → "Przetwórz" button should be disabled
- Very short article (<200 words) → should still generate variants (no minimum enforced)
- Article in English → variants should still be in Polish (system prompt instructs Polish)

---

## VALIDATION COMMANDS

### Level 1 — Backend
```bash
uv run ruff check bond/graph/nodes/repurpose.py
uv run python -c "from bond.graph.graph import build_author_graph; build_author_graph(); print('graph compiled ok')"
uv run python -m pytest tests/ -x -q
```

### Level 2 — Frontend
```bash
cd frontend && npx tsc --noEmit
cd frontend && npm run lint
cd frontend && npm run build
```

### Level 3 — Manual
```bash
# Start services, then navigate to /repurpose in browser
```

---

## ACCEPTANCE CRITERIA

- [ ] `/repurpose` route is accessible and renders `RepurposePanel`
- [ ] Pasting a blog article and submitting generates 4 platform variants
- [ ] X (Twitter) variant is ≤280 characters
- [ ] Each variant is independently editable in the UI
- [ ] Copy-to-clipboard works for each variant
- [ ] Mode toggle navigates correctly between Author / Shadow / Repurpose
- [ ] Graph compiles without error after `route_mode` extension
- [ ] Backend tests pass
- [ ] TypeScript compiles without errors

---

## NOTES

**Why single-node, no HITL**: Repurposing is low-stakes — it generates draft social copy that the user will review and edit anyway. A HITL checkpoint would add friction without safety value. The user edits directly in the output view.

**No metadata log entry for repurpose**: Social variants aren't published articles. The duplicate-check logic and metadata log are Author mode concerns only. The `repurpose_node` returns `social_variants` and ends at `END` with no `save_metadata_node` in the path.

**Structured output for all 4 variants in one call**: One LLM call is cheaper and produces more coherent cross-platform theming than four separate calls. The `SocialVariants` Pydantic model enforces all four fields are present.

**Confidence Score**: 8/10 — the backend pattern is well-established. The main risk is the `ModeToggle` refactor from binary Switch to three-way — test visually.
