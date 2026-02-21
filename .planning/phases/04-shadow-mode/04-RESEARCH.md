# Phase 4: Shadow Mode - Research

**Researched:** 2026-02-21
**Domain:** LangGraph dual-branch routing, structured annotation output, React split-pane diff UI, HITL per-annotation reject/regenerate loop
**Confidence:** HIGH (LangGraph patterns verified via official docs; React library versions confirmed via npm/GitHub); MEDIUM (annotation structured output schema — no single canonical source; synchronized scroll implementation details)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Annotation presentation**
- All deviations annotated — comprehensive coverage, not just top-N
- Each annotation shows the suggested replacement + a brief reason (e.g., "Use X instead of Y — your style uses shorter sentences here")
- Visual annotation style: Claude's discretion (pick whatever renders cleanest in the existing MarkdownEditor)
- Whether to normalize whitespace/formatting before annotating: Claude's discretion

**Analysis scope**
- Comprehensive analysis: style (word choice, tone, rhythm), structure (paragraph flow, heading usage), grammar, and clarity — all checked against the corpus
- Corpus entry weighting (own text vs external blogger): Claude's discretion — pick the strategy that produces the most useful corrections
- Analysis granularity (full-text pass vs section-by-section): Claude's discretion based on text length
- Whether to include a summary alignment verdict: Claude's discretion — include only if annotation density makes it useful

**Dual-output layout**
- Side-by-side split pane: annotated original on the left, corrected version on the right
- Synchronized scroll — both panes move together for easy comparison
- Corrected version pane is editable — user can tweak it directly before copying
- "Copy corrected" button on the corrected pane for one-click clipboard copy

**Rejection feedback**
- Free text only — open field, user writes feedback in their own words
- Per-annotation rejection — user can dismiss individual annotations; only rejected ones regenerate (not the full set)
- After max 3 rejection iterations: Claude's discretion — handle gracefully consistent with the existing max-3-iterations pattern
- After each regeneration: highlight which annotations are new or modified vs the previous round so the user can see feedback was applied

### Claude's Discretion
- Visual annotation rendering style (diff, highlight, footnote, etc.)
- Whitespace normalization before annotation
- Corpus weighting strategy (own text vs external)
- Analysis granularity (whole text vs per-paragraph)
- Whether to include a summary alignment score
- Behavior at max iteration limit

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SHAD-01 | User can launch Shadow mode by pasting existing text | `mode: "shadow"` field in shared BondState routes graph to Shadow branch via `add_conditional_edges(START, route_by_mode)`; frontend sends text in the same `/api/chat/stream` SSE endpoint used by Author mode |
| SHAD-02 | Agent compares submitted text against style corpus vector patterns | `shadow_analyze_node` fetches top-K corpus fragments via ChromaDB two-pass query (own text preferred), embeds the submitted text, and injects fragments + submitted text into a structured prompt for the LLM analysis pass |
| SHAD-03 | Agent generates annotated version with inline correction suggestions | LLM called with `with_structured_output(AnnotationResult)` returning `list[Annotation]` where each item has `annotation_id`, `original_span`, `replacement`, `reason`; annotated text assembled by applying all suggestions to original |
| SHAD-04 | Agent generates a corrected version of the text | Corrected version assembled by applying all current (non-rejected) annotations to the original text; returned as plain Markdown string alongside annotation list |
| SHAD-05 | User sees both outputs: annotated original and corrected version side-by-side | `react-diff-viewer-continued` v4.1.2 in `splitView` mode renders annotated left / corrected right; synchronized scroll via browser scroll event listener on both pane refs (library does not provide native sync scroll) |
| SHAD-06 | User can reject annotations with a reason; agent regenerates alternatives (max 3 iterations) | `interrupt()` in dedicated `shadow_checkpoint_node` surfaces annotation list; `Command(resume={"rejected_ids": [...], "reason": "..."})` resumes; `shadow_annotate_node` regenerates only rejected annotation IDs; iteration counter in ShadowState tracks cap |
</phase_requirements>

---

## Summary

Phase 4 adds Shadow mode as a second routing branch on the existing LangGraph `StateGraph` built in Phases 2–3. The architecture decision from project initialization — "single LangGraph StateGraph with dual-branch routing" — is directly implementable via `add_conditional_edges(START, route_by_mode)`, routing on a `mode` field in a shared `BondState` TypedDict. Shadow mode nodes run entirely on a separate branch and never touch Author mode nodes; shared infrastructure (ChromaDB, SqliteSaver, FastAPI SSE endpoint) is reused without modification.

The Shadow mode pipeline has two main nodes: `shadow_analyze_node` (fetches corpus fragments, builds analysis prompt) and `shadow_annotate_node` (calls LLM with `with_structured_output(AnnotationResult)` to produce a structured list of `Annotation` objects). A dedicated `shadow_checkpoint_node` contains the single `interrupt()` call that surfaces the annotation list for per-annotation rejection. On rejection, the graph loops back to `shadow_annotate_node` with only the rejected annotation IDs and user feedback — not a full re-run.

The frontend dual-output display uses `react-diff-viewer-continued` v4.1.2 (actively maintained, React 19 compatible as of Feb 2026) in split-view mode. The library does not ship native synchronized scrolling; a custom scroll-sync hook is needed. The "corrected version" pane must be backed by a controlled `textarea` (not the read-only diff viewer) because the user can edit it before copying.

**Primary recommendation:** Model the annotation output as a Pydantic `AnnotationResult` with `list[Annotation]` (each annotation carries `annotation_id: str`, `original_span: str`, `replacement: str`, `reason: str`) and use `with_structured_output(AnnotationResult)` on the draft LLM. This is the cleanest interface for per-annotation rejection: the HITL interrupt payload passes the annotation list; the resume payload specifies `rejected_ids` + `reason`; the regenerate pass only regenerates those IDs. Do not use character-level span indices — they are fragile when the LLM produces slight paraphrases; use `original_span` as a text substring match instead.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | 1.0.9 (Feb 2026) | StateGraph routing, interrupt/resume, SqliteSaver | Project decision; same graph expanded with Shadow branch |
| langgraph-checkpoint-sqlite | 3.0.3 | Durable state persistence across Shadow sessions | Project decision; same checkpointer shared with Author mode |
| chromadb | 1.5.1 | Style corpus retrieval for corpus comparison | Phase 1 output; same `bond_style_corpus_v1` collection queried in Shadow analyze node |
| sentence-transformers | 3.x | Embed submitted text for corpus similarity query | Same model (`paraphrase-multilingual-MiniLM-L12-v2`) as Phase 1/2; no new dependency |
| langchain-openai / langchain-anthropic | latest | LLM for annotation generation via `with_structured_output` | Same providers as Author mode; `DRAFT_MODEL` env var reused |
| pydantic | v2 | `AnnotationResult` and `Annotation` BaseModel schemas for structured LLM output | Project constraint; already in stack |
| react-diff-viewer-continued | 4.1.2 | Frontend split-view diff display (annotated left, corrected right) | Actively maintained fork of react-diff-viewer; React 19 compatible as of Feb 2026; splitView prop built-in |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| fastapi | 0.115.x | Existing `/api/chat/stream` SSE and `/api/chat/resume` endpoints | Phase 3 builds these; Phase 4 reuses without new endpoints |
| diff (npm) | bundled with react-diff-viewer-continued | Text diffing algorithm | Used internally by the diff viewer; no direct import needed |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| react-diff-viewer-continued | react-diff-view (otakustay) | `react-diff-view` is git-patch oriented with tokenization support — better for code diffs. react-diff-viewer-continued is simpler, prose-optimized, and matches existing MarkdownEditor aesthetic |
| react-diff-viewer-continued | Custom two-column layout with highlights | Custom avoids the library but loses word-level diff rendering; building robust diff display is non-trivial |
| `with_structured_output(AnnotationResult)` | Raw LLM + regex parsing | Structured output is far more reliable for a list-of-objects schema; regex breaks on nested reasons, multi-sentence replacements |
| `original_span` text matching | `span_start/span_end` character indices | Character indices are fragile — LLM paraphrases change lengths; text substring matching is resilient and easier to debug |

**Installation (new additions for Phase 4):**
```bash
# Backend — no new Python packages needed (reuses Phase 1-3 stack)
# Frontend only:
npm install react-diff-viewer-continued
```

---

## Architecture Patterns

### Recommended Project Structure Extension

The Phase 2 graph structure from `bond/graph/` is extended — Shadow mode adds nodes alongside the existing Author mode nodes:

```
bond/
├── graph/
│   ├── state.py             # EXTEND: BondState = AuthorState + ShadowState fields
│   ├── graph.py             # EXTEND: add shadow branch nodes + route_by_mode function
│   └── nodes/
│       ├── [author nodes from Phase 2]
│       ├── shadow_analyze.py    # SHAD-02: corpus comparison
│       ├── shadow_annotate.py   # SHAD-03, SHAD-04: structured annotation + corrected text
│       └── shadow_checkpoint.py # SHAD-06: interrupt() only
frontend/
└── components/
    ├── [author components from Phase 3]
    ├── ShadowPanel.tsx          # SHAD-05: split-pane dual output display
    └── AnnotationList.tsx       # SHAD-06: per-annotation reject UI
```

### Pattern 1: Dual-Branch Graph Routing

**What:** A single `route_by_mode` function at START routes to Author or Shadow branch based on `state["mode"]`.

**When to use:** Single entry point — same `/api/chat/stream` endpoint, same `thread_id` management, same SqliteSaver.

**Source:** `https://docs.langchain.com/oss/python/langgraph/graph-api` — confirmed `add_conditional_edges(START, fn)` pattern.

```python
# bond/graph/graph.py (extension of Phase 2 graph)
from langgraph.graph import StateGraph, START, END
from typing import Literal

def route_by_mode(state: "BondState") -> Literal["duplicate_check", "shadow_analyze"]:
    """Route to Author or Shadow branch based on 'mode' field."""
    if state.get("mode") == "shadow":
        return "shadow_analyze"
    return "duplicate_check"  # Author mode entry point (Phase 2)

# In build_bond_graph():
builder.add_conditional_edges(
    START,
    route_by_mode,
    {"duplicate_check": "duplicate_check", "shadow_analyze": "shadow_analyze"},
)
```

**Critical:** The existing Author mode graph used `add_edge(START, "duplicate_check")`. This must be replaced with `add_conditional_edges(START, route_by_mode, ...)` when integrating Shadow mode in Phase 4.

### Pattern 2: Extended BondState TypedDict

**What:** Shadow mode fields are added to the existing `AuthorState`. Both branches share the same state schema; unused fields remain `None` for the inactive branch.

**When to use:** Single graph, single state object — simpler than separate state schemas.

```python
# bond/graph/state.py (extension of Phase 2 AuthorState)
from typing import Optional, TypedDict, Literal

class BondState(TypedDict):
    # --- Routing ---
    mode: Literal["author", "shadow"]   # NEW: determines routing branch

    # --- Author mode fields (from Phase 2) ---
    topic: Optional[str]
    keywords: Optional[list[str]]
    thread_id: str
    duplicate_match: Optional[dict]
    duplicate_override: Optional[bool]
    search_cache: dict
    research_report: Optional[str]
    heading_structure: Optional[str]
    cp1_approved: Optional[bool]
    cp1_feedback: Optional[str]
    cp1_iterations: int
    draft: Optional[str]
    draft_validated: Optional[bool]
    cp2_approved: Optional[bool]
    cp2_feedback: Optional[str]
    cp2_iterations: int
    metadata_saved: bool

    # --- Shadow mode fields (NEW in Phase 4) ---
    shadow_input_text: Optional[str]            # SHAD-01: submitted text
    shadow_corpus_fragments: Optional[list[dict]]  # retrieved style examples
    shadow_annotations: Optional[list[dict]]    # list of Annotation objects
    shadow_corrected_text: Optional[str]        # SHAD-04: full corrected version
    shadow_rejected_ids: Optional[list[str]]    # IDs rejected in this round
    shadow_rejection_reason: Optional[str]      # free-text feedback
    shadow_iterations: int                      # iteration counter (cap at 3)
    shadow_cp_approved: Optional[bool]
    shadow_previous_annotations: Optional[list[dict]]  # for highlighting new/modified
```

**Note on naming:** If Phase 2 is already in production with `AuthorState`, rename to `BondState` in one refactor step at the start of Phase 4 Plan 1.

### Pattern 3: Structured Annotation Schema (Pydantic)

**What:** LLM output constrained to a structured list of annotation objects via `with_structured_output`.

**Source:** `https://docs.langchain.com/oss/python/langchain/structured-output` — `with_structured_output(Pydantic model)` pattern.

```python
# bond/graph/nodes/shadow_annotate.py
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
import os

class Annotation(BaseModel):
    annotation_id: str = Field(
        description="Unique ID for this annotation, e.g. 'ann_001'. Stable across regeneration rounds."
    )
    original_span: str = Field(
        description="Exact verbatim text from the submitted text that should be replaced. "
                    "Used for text substitution — must match the original exactly."
    )
    replacement: str = Field(
        description="The corrected replacement text that aligns with the style corpus."
    )
    reason: str = Field(
        description="Brief explanation of why this change aligns with the author's style. "
                    "Example: 'Your style uses shorter sentences here; this splits a compound clause.'"
    )

class AnnotationResult(BaseModel):
    annotations: list[Annotation] = Field(
        description="All style corrections for the submitted text, ordered by appearance."
    )
    alignment_summary: str = Field(
        default="",
        description="Optional 1-2 sentence summary of overall style alignment. "
                    "Include only if annotation count > 5; leave empty otherwise."
    )

def shadow_annotate_node(state: "BondState") -> dict:
    llm = ChatOpenAI(model=os.environ["DRAFT_MODEL"], temperature=0.3)
    structured_llm = llm.with_structured_output(AnnotationResult)

    # Build system prompt with corpus fragments + submitted text
    system_prompt = _build_shadow_prompt(
        submitted_text=state["shadow_input_text"],
        corpus_fragments=state["shadow_corpus_fragments"],
        rejected_ids=state.get("shadow_rejected_ids") or [],
        rejection_reason=state.get("shadow_rejection_reason") or "",
        previous_annotations=state.get("shadow_previous_annotations") or [],
    )

    result: AnnotationResult = structured_llm.invoke(system_prompt)

    # Assemble corrected text by applying all annotations
    corrected = _apply_annotations(
        original=state["shadow_input_text"],
        annotations=result.annotations,
    )

    return {
        "shadow_annotations": [a.model_dump() for a in result.annotations],
        "shadow_corrected_text": corrected,
        "shadow_previous_annotations": state.get("shadow_annotations") or [],
    }
```

### Pattern 4: Corpus Analysis (shadow_analyze_node)

**What:** Retrieve style fragments from ChromaDB and embed the submitted text for comparison context.

```python
# bond/graph/nodes/shadow_analyze.py
from sentence_transformers import SentenceTransformer
import chromadb
from bond.config import settings

def shadow_analyze_node(state: "BondState") -> dict:
    """Retrieve corpus style fragments relevant to the submitted text."""
    submitted = state["shadow_input_text"]

    # Embed submitted text for query
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    query_embedding = model.encode([submitted]).tolist()

    client = chromadb.PersistentClient(path=settings.chroma_path)
    corpus = client.get_collection("bond_style_corpus_v1")

    # Two-pass retrieval: prefer own texts (same pattern as Phase 2 writer_node)
    own = corpus.query(
        query_embeddings=query_embedding,
        n_results=5,
        where={"source_type": "own"},
        include=["documents", "metadatas"],
    )
    own_docs = own["documents"][0] if own["documents"] else []

    if len(own_docs) < 5:
        fill = corpus.query(
            query_embeddings=query_embedding,
            n_results=5 - len(own_docs),
            where={"source_type": "external"},
            include=["documents", "metadatas"],
        )
        ext_docs = fill["documents"][0] if fill["documents"] else []
    else:
        ext_docs = []

    fragments = [{"text": d} for d in own_docs + ext_docs]
    return {"shadow_corpus_fragments": fragments}
```

### Pattern 5: HITL Interrupt for Per-Annotation Rejection

**What:** A dedicated checkpoint node surfaces the annotation list via `interrupt()`. The resume payload carries `rejected_ids` (list of annotation IDs to regenerate) plus free-text `reason`.

**Source:** `https://docs.langchain.com/oss/python/langgraph/interrupts` — interrupt/Command(resume=...) pattern; verified that interrupts inside subgraphs propagate to parent via `get_state(config, subgraphs=True)`.

```python
# bond/graph/nodes/shadow_checkpoint.py
from langgraph.types import interrupt

def shadow_checkpoint_node(state: "BondState") -> dict:
    """Dedicated interrupt node — no other logic here (avoids node re-execution pitfall)."""
    user_response = interrupt({
        "annotations": state["shadow_annotations"],
        "corrected_text": state["shadow_corrected_text"],
        "shadow_iterations": state["shadow_iterations"],
        "alignment_summary": "",  # populated from shadow_annotate if present
    })
    # user_response: {"approved": True} or {"approved": False, "rejected_ids": [...], "reason": "..."}
    if user_response.get("approved"):
        return {"shadow_cp_approved": True}
    else:
        return {
            "shadow_cp_approved": False,
            "shadow_rejected_ids": user_response.get("rejected_ids", []),
            "shadow_rejection_reason": user_response.get("reason", ""),
            "shadow_iterations": state["shadow_iterations"] + 1,
        }
```

**Routing after checkpoint:**
```python
def route_after_shadow_cp(state: "BondState") -> str:
    if state.get("shadow_cp_approved"):
        return END
    # Soft cap at 3 — same pattern as Author mode Checkpoint 2
    if state.get("shadow_iterations", 0) >= 3:
        # Surface max-iteration warning inside the next interrupt payload
        # but still allow regeneration (soft cap, consistent with cp2 pattern)
        pass
    return "shadow_annotate"

builder.add_conditional_edges(
    "shadow_checkpoint",
    route_after_shadow_cp,
    {"shadow_annotate": "shadow_annotate", END: END},
)
```

### Pattern 6: Applying Annotations to Produce Corrected Text

**What:** Text substitution using `original_span` substring matching (not fragile character indices).

```python
def _apply_annotations(original: str, annotations: list[Annotation]) -> str:
    """Apply all annotations to produce corrected text. Uses substring replacement."""
    corrected = original
    # Process in reverse order of appearance to preserve offsets
    # Find each original_span and replace with replacement
    for ann in reversed(annotations):
        if ann.original_span in corrected:
            corrected = corrected.replace(ann.original_span, ann.replacement, 1)
    return corrected
```

**Caveat:** `str.replace(..., 1)` replaces only the first occurrence. If the same span appears multiple times, only the first is replaced — this is correct behavior (each annotation targets a specific occurrence). For ambiguous duplicates, the LLM should be instructed to include enough surrounding context in `original_span` to make it unique.

### Pattern 7: Highlighting New/Modified Annotations

**What:** After regeneration, mark which annotations are new or changed so the user sees feedback was applied.

```python
def _mark_annotation_status(
    current: list[dict],
    previous: list[dict],
) -> list[dict]:
    """Add 'status': 'new' | 'modified' | 'unchanged' to each annotation."""
    prev_map = {a["annotation_id"]: a for a in previous}
    result = []
    for ann in current:
        aid = ann["annotation_id"]
        if aid not in prev_map:
            result.append({**ann, "status": "new"})
        elif ann["replacement"] != prev_map[aid]["replacement"]:
            result.append({**ann, "status": "modified"})
        else:
            result.append({**ann, "status": "unchanged"})
    return result
```

**Note:** The LLM must be instructed to preserve `annotation_id` values for annotations it is NOT regenerating (only the rejected ones get new content). This must be explicit in the shadow prompt system message.

### Pattern 8: Shadow Branch Graph Wiring

**Complete wiring for the Shadow branch:**

```
START
  ├─[mode=="shadow"]──► shadow_analyze_node
  │                           │
  │                   shadow_annotate_node
  │                           │
  │                   shadow_checkpoint_node
  │                       ├─[approved]──► END
  │                       └─[rejected]──► shadow_annotate_node (loop)
  │
  └─[mode=="author"]──► duplicate_check (Phase 2 Author branch)
```

```python
# In build_bond_graph() — Shadow branch additions
builder.add_node("shadow_analyze", shadow_analyze_node)
builder.add_node("shadow_annotate", shadow_annotate_node)
builder.add_node("shadow_checkpoint", shadow_checkpoint_node)

builder.add_edge("shadow_analyze", "shadow_annotate")
builder.add_edge("shadow_annotate", "shadow_checkpoint")
builder.add_conditional_edges(
    "shadow_checkpoint",
    route_after_shadow_cp,
    {"shadow_annotate": "shadow_annotate", END: END},
)
```

### Pattern 9: Frontend Split-Pane Display

**What:** `react-diff-viewer-continued` in `splitView` mode for side-by-side display. Custom scroll sync hook because the library does not provide native synchronized scrolling.

```tsx
// frontend/components/ShadowPanel.tsx
import ReactDiffViewer from "react-diff-viewer-continued";
import { useRef, useCallback } from "react";

interface ShadowPanelProps {
  annotatedText: string;    // left pane — original with inline markers
  correctedText: string;    // right pane — fully corrected
  onCorrectedChange: (text: string) => void;
  onCopy: () => void;
}

export function ShadowPanel({ annotatedText, correctedText, onCorrectedChange, onCopy }: ShadowPanelProps) {
  // react-diff-viewer-continued v4.1.2 — splitView prop
  return (
    <div className="shadow-panel">
      <ReactDiffViewer
        oldValue={annotatedText}
        newValue={correctedText}
        splitView={true}
        hideLineNumbers={true}
        // Word-level diffing to highlight specific corrections
        compareMethod="diffWords"
      />
      {/* Copy corrected button */}
      <button onClick={onCopy}>Copy corrected</button>
    </div>
  );
}
```

**Synchronized scroll:** The library does not expose scroll refs. Implement a custom hook that attaches scroll event listeners to the two generated pane DOM elements:

```tsx
// frontend/hooks/useSyncScroll.ts
import { useEffect, useRef } from "react";

export function useSyncScroll(containerRef: React.RefObject<HTMLElement>) {
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    // react-diff-viewer-continued renders two tables for split view
    const panes = container.querySelectorAll("table");
    if (panes.length < 2) return;
    const [left, right] = [panes[0], panes[1]];

    const syncFromLeft = () => { right.scrollTop = left.scrollTop; };
    const syncFromRight = () => { left.scrollTop = right.scrollTop; };

    left.addEventListener("scroll", syncFromLeft);
    right.addEventListener("scroll", syncFromRight);
    return () => {
      left.removeEventListener("scroll", syncFromLeft);
      right.removeEventListener("scroll", syncFromRight);
    };
  }, [containerRef]);
}
```

**Editable corrected pane:** `react-diff-viewer-continued` renders both panes as read-only `<table>` elements. To make the right pane editable, render the corrected text in a sibling `<textarea>` with synchronized content — do not attempt to make the diff viewer's right column editable. Show both the diff view (for visual comparison) and a separate editable textarea below the corrected pane.

**Installation:**
```bash
npm install react-diff-viewer-continued
# v4.1.2 as of Feb 2026 — React 19 compatible
```

### Anti-Patterns to Avoid

- **Placing LLM call and interrupt() in the same node:** Same critical pitfall as Author mode — the entire node re-executes on resume. The LLM call goes in `shadow_annotate_node`; the interrupt goes in `shadow_checkpoint_node`. They are always separate nodes.
- **Using character offset span indices:** Fragile when LLM paraphrases or reorders. Use `original_span: str` (verbatim text) for substitution matching.
- **Regenerating the full annotation set on partial rejection:** Only regenerate annotations whose IDs appear in `shadow_rejected_ids`. Keep approved annotations from the previous round unchanged (preserve their `annotation_id`). Instruct the LLM explicitly to preserve unchanged IDs.
- **Trying to make the diff viewer's right column editable:** `react-diff-viewer-continued` renders read-only tables. Build the editable corrected text separately as a controlled `<textarea>`.
- **Keeping `annotation_id` values non-stable across LLM calls:** The LLM must assign stable, predictable IDs (e.g., `"ann_001"`, `"ann_002"`) and preserve them for unchanged annotations on regeneration rounds. Include this requirement explicitly in the system prompt.
- **Forgetting to rename `AuthorState` to `BondState`:** Phase 2 defined `AuthorState`. Adding Shadow fields requires a rename. Do this as the first task in Phase 4 Plan 1.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Text diff display | Custom two-column HTML with manual highlight spans | `react-diff-viewer-continued` | Word-level diffing algorithm, accessibility, CSS-in-JS theming — non-trivial to implement correctly |
| Structured LLM annotation output | Prompt → regex parse → list rebuild | `with_structured_output(AnnotationResult)` | Guaranteed schema compliance; auto-retry on parse failure with modern models; handles nested lists of objects reliably |
| Corpus fragment retrieval | Custom embedding + cosine loop | ChromaDB `query()` with two-pass own-before-external | Already established in Phase 1/2; HNSW index; two-pass pattern already proven |
| HITL partial-item approval | Custom event queue or WebSocket state machine | LangGraph `interrupt()` + `Command(resume=...)` | Durable across page refresh; same pattern as Author mode checkpoints; zero new infrastructure |
| Annotation text substitution | Custom diffing/patching library | `str.replace(original_span, replacement, 1)` | Sufficient for prose text; far simpler than RFC 6902 JSON patches (designed for JSON, not prose) |

**Key insight:** Shadow mode reuses every piece of infrastructure from Phases 1-3. The only new code is three Python nodes, the state schema extension, and one React component. Scope is tightly bounded.

---

## Common Pitfalls

### Pitfall 1: Node Re-Execution on Resume (Shadow variant)

**What goes wrong:** The LLM annotation call fires twice — once when `shadow_annotate_node` first runs, and again when the graph resumes after the human rejects/approves.

**Why it happens:** LangGraph resumes by re-running the entire node containing `interrupt()`. If the LLM call is in the same node, it re-generates a completely new annotation set on resume.

**How to avoid:** Always keep `shadow_annotate_node` (LLM call) and `shadow_checkpoint_node` (interrupt only) as separate nodes. This is identical to the Author mode pattern — confirmed from LangGraph HITL docs.

**Warning signs:** LLM API cost doubles per Shadow session; annotation IDs change unexpectedly after the user approves.

### Pitfall 2: Annotation ID Instability Across Rounds

**What goes wrong:** After partial rejection, the LLM returns annotations with different IDs — the frontend cannot determine which annotations are "new" vs "modified" vs "unchanged."

**Why it happens:** LLMs don't maintain memory of previous outputs unless explicitly prompted. Without instruction, the model generates fresh IDs each time.

**How to avoid:** Include the previous annotation list (with their IDs) in the system prompt for regeneration rounds. Explicitly instruct the model: "Preserve `annotation_id` values for all annotations you are NOT asked to regenerate. Only generate new content for IDs in [rejected_ids]."

**Warning signs:** After regeneration, all annotations appear as "new" in the status tracking, even ones the user already approved.

### Pitfall 3: `original_span` Ambiguity (Repeated Phrases)

**What goes wrong:** `str.replace(original_span, replacement, 1)` applies the correction to the wrong occurrence when the same phrase appears multiple times.

**Why it happens:** Polish blog text often uses repeated connectives ("jednak", "natomiast", "warto zauważyć"). A short `original_span` matches the first occurrence, which may not be the intended target.

**How to avoid:** Include this constraint in the annotation prompt: "Make `original_span` long enough to be unique in the text (include at least one surrounding sentence fragment if the exact phrase repeats). Minimum 10 characters." Post-generation, validate that each `original_span` appears exactly once; if duplicates exist, add context until unique or skip the annotation.

**Warning signs:** Corrections appear in the wrong paragraph; the corrected text looks inconsistent.

### Pitfall 4: `AuthorState` → `BondState` Rename Breaking Phase 2 Imports

**What goes wrong:** Renaming the state TypedDict in Phase 4 breaks all Phase 2 node imports that reference `AuthorState`.

**Why it happens:** Phase 2 nodes import `from bond.graph.state import AuthorState`. After rename, those imports fail.

**How to avoid:** At the start of Phase 4 Plan 1, add a backward-compat alias: `AuthorState = BondState` in `bond/graph/state.py`. Then migrate individual node imports over the course of Phase 4. Remove the alias once all imports are updated.

**Warning signs:** `ImportError: cannot import name 'AuthorState' from 'bond.graph.state'` in Phase 2 node files.

### Pitfall 5: react-diff-viewer-continued Scroll Sync Selector Brittleness

**What goes wrong:** The scroll sync hook targets `table` elements inside the diff viewer container. If the library's internal DOM structure changes in a future version, the selector stops finding the panes.

**Why it happens:** `react-diff-viewer-continued` does not expose scroll refs or a public API for synchronization. The hook relies on internal DOM structure.

**How to avoid:** Wrap the diff viewer in a container with a stable `data-testid` and query for its two direct child panels. Write a CSS selector that targets the two visible scroll areas, not a specific element type. Add a useEffect guard that logs a warning if fewer than 2 panes are found (helps detect library upgrades that break the selector).

**Warning signs:** Scroll sync stops working after an npm update; one pane scrolls independently.

### Pitfall 6: `with_structured_output` Fails for Nested Lists with Some LLMs

**What goes wrong:** `AnnotationResult` with `list[Annotation]` causes parsing errors on some models (especially smaller models or non-OpenAI providers).

**Why it happens:** Some models struggle with deeply nested Pydantic schemas. OpenAI's structured output requires all fields to be non-optional (nullable via Union[T, None] pattern, not Python `Optional`).

**How to avoid:** Use `DRAFT_MODEL` (Frontier model) for annotation generation — not `RESEARCH_MODEL`. Frontier models (Claude Sonnet, GPT-4o) have reliable structured output for nested lists. Add a fallback: if `with_structured_output` parsing fails after 2 retries, surface a user-friendly error in the chat and prompt the user to try again.

**Warning signs:** `ValidationError: list[Annotation] — expected sequence` in logs; model returns an empty `annotations` list.

---

## Code Examples

Verified patterns from official sources:

### Complete Shadow Branch Prompt Construction

```python
# bond/graph/nodes/shadow_annotate.py
def _build_shadow_prompt(
    submitted_text: str,
    corpus_fragments: list[dict],
    rejected_ids: list[str],
    rejection_reason: str,
    previous_annotations: list[dict],
) -> str:
    exemplars = "\n\n---\n\n".join(f["text"] for f in corpus_fragments[:5])

    is_regeneration = bool(rejected_ids)
    prev_ann_str = ""
    if is_regeneration and previous_annotations:
        preserved = [a for a in previous_annotations if a["annotation_id"] not in rejected_ids]
        prev_ann_str = f"""
Previously approved annotations (preserve their annotation_id values unchanged):
{[{"annotation_id": a["annotation_id"], "original_span": a["original_span"], "replacement": a["replacement"]} for a in preserved]}

User rejected these annotation IDs: {rejected_ids}
User's feedback: {rejection_reason}
Generate NEW corrections only for the rejected IDs. Keep all other annotations identical.
"""

    return f"""You are a style editor. Your task is to annotate the submitted text with corrections that align it to the author's writing style as demonstrated in the corpus fragments below.

## Author's Style Corpus Fragments
{exemplars}

## Submitted Text
{submitted_text}
{prev_ann_str}
## Instructions
- Analyze: style (word choice, tone, rhythm), structure (paragraph flow, heading usage), grammar, clarity
- Annotate ALL deviations — comprehensive coverage
- Each annotation: exact original span, replacement, brief reason referencing the author's style
- Make original_span long enough to be unique in the text (minimum 10 characters; include surrounding context if phrase repeats)
- Assign stable annotation_id values like 'ann_001', 'ann_002' in order of appearance
- Return alignment_summary only if annotation count > 5
"""
```

### FastAPI SSE Endpoint Integration (Shadow mode — no new endpoint needed)

Shadow mode uses the same `/api/chat/stream` SSE endpoint from Phase 3. The frontend sends `mode: "shadow"` and `shadow_input_text` in the initial state payload:

```python
# Phase 3 endpoint (no changes needed for Shadow mode)
# Initial state for Shadow:
initial_shadow_state = {
    "mode": "shadow",
    "thread_id": thread_id,
    "shadow_input_text": user_submitted_text,
    "shadow_iterations": 0,
    "shadow_cp_approved": None,
    "search_cache": {},     # required by BondState schema; unused in Shadow branch
    "cp1_iterations": 0,    # same
    "cp2_iterations": 0,    # same
    "metadata_saved": False, # same
}
```

### HITL Resume for Shadow Annotation Rejection

```python
# Phase 3 /api/chat/resume endpoint (no changes needed for Shadow mode)
# Resume payload for per-annotation partial rejection:
resume_payload = {
    "approved": False,
    "rejected_ids": ["ann_003", "ann_007"],   # only these get regenerated
    "reason": "These suggestions are too formal for our blog voice"
}
# graph.invoke(Command(resume=resume_payload), config={"configurable": {"thread_id": tid}})
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Separate `AuthorState` and `ShadowState` TypedDicts, separate compiled graphs | Single `BondState` TypedDict, single graph with `add_conditional_edges(START, route_by_mode)` | LangGraph 0.2+ (conditional START routing) | Single checkpointer, single thread_id namespace, simpler FastAPI integration |
| `interrupt_before=["node_name"]` at compile | `interrupt()` inside dedicated node body | LangGraph ~0.2.19 | Arbitrary payload surfaced to frontend; more expressive per-annotation rejection data |
| Original `react-diff-viewer` (unmaintained since 2021) | `react-diff-viewer-continued` v4.1.2 (actively maintained, Feb 2026) | Fork in 2022; v4.x in 2025 | React 18/19 compatible; `splitView` prop works without workarounds |
| LangGraph `1.0.9` (latest, Feb 2026) | — | Stable API; no breaking changes anticipated for these patterns |

**Deprecated/outdated:**
- Original `react-diff-viewer` (praneshr): last released 2021, React 18+ incompatible — use `react-diff-viewer-continued` instead
- `MemorySaver`: not used (project decision); SqliteSaver from Phase 2 handles Shadow sessions too
- `interrupt_before` at compile time: use `interrupt()` inside node body (more expressive, passes annotation payload)

---

## Open Questions

1. **`add_conditional_edges(START, ...)` vs `add_edge(START, "duplicate_check")` migration**
   - What we know: Phase 2 plans use `add_edge(START, "duplicate_check")`. Phase 4 must replace this with `add_conditional_edges(START, route_by_mode, ...)`.
   - What's unclear: Whether Phase 2 plans have already been executed and the graph is live. If yes, this is a refactor; if no, Phase 4 Plan 1 simply writes the graph with dual routing from the start.
   - Recommendation: Phase 4 Plan 1 must check Phase 2 execution state and handle the `AuthorState → BondState` rename + START edge refactor as Task 1 before adding Shadow nodes.

2. **`react-diff-viewer-continued` synchronized scroll implementation**
   - What we know: The library v4.1.2 does not ship native scroll synchronization. The internal DOM structure uses `<table>` elements for each pane in split view.
   - What's unclear: Whether a future v4.x release adds native sync scroll (open discussion on GitHub). The `table` selector may break after library upgrades.
   - Recommendation: Implement the custom `useSyncScroll` hook with a selector guard (warn if fewer than 2 panes found). Pin to `react-diff-viewer-continued@4.1.2` in `package.json` until sync scroll is tested with a newer version.

3. **Annotation LLM temperature and model choice**
   - What we know: `DRAFT_MODEL` (Frontier model) is required for `with_structured_output(AnnotationResult)` reliability. Temperature should be lower than Author mode draft (0.3 vs 0.7) to reduce annotation hallucinations.
   - What's unclear: Whether the same `DRAFT_MODEL` env var is appropriate or a dedicated `SHADOW_MODEL` env var is needed.
   - Recommendation: Reuse `DRAFT_MODEL` with `temperature=0.3` for the annotation LLM. Add `SHADOW_MODEL` env var only if users report style annotation quality issues requiring a different model.

4. **Performance: embedding submitted text in `shadow_analyze_node`**
   - What we know: `paraphrase-multilingual-MiniLM-L12-v2` (~420MB) is already loaded in Phase 1/2. Loading it in a new node adds ~1-2s if the model is not cached.
   - What's unclear: Whether the model is held in memory across node calls or re-loaded. In Python, the `SentenceTransformer` constructor caches the model in RAM after first load (within the same process).
   - Recommendation: Initialize a module-level `SentenceTransformer` singleton in `shadow_analyze.py` (same pattern as Phase 2 `duplicate_check.py`). First call downloads/loads; subsequent calls are fast.

---

## Sources

### Primary (HIGH confidence)
- LangGraph official docs — `add_conditional_edges(START, fn)` routing pattern verified at `https://docs.langchain.com/oss/python/langgraph/graph-api` (2026-02-21)
- LangGraph official docs — `interrupt()` / `Command(resume=...)` per-item patterns at `https://docs.langchain.com/oss/python/langgraph/interrupts` (2026-02-21); subgraph interrupt propagation confirmed
- LangGraph GitHub README — v1.0.9 released 2026-02-19 (current stable)
- LangChain official docs — `with_structured_output(Pydantic model)` at `https://docs.langchain.com/oss/python/langchain/structured-output` (2026-02-21)
- `react-diff-viewer-continued` v4.1.2 — npm version history + GitHub: `https://github.com/Aeolun/react-diff-viewer-continued` (2026-02-21; "last published 5 days ago"); React 19 in peer deps confirmed via payloadcms PR #10834

### Secondary (MEDIUM confidence)
- WebSearch — LangGraph Command object combined routing+state update pattern (cross-confirmed with official graph-api docs)
- WebSearch — `react-diff-viewer-continued` synchronized scroll: no native support confirmed by absence in README and npm page; custom hook approach is standard for this library
- LangGraph subgraph docs — interrupt propagation from subgraph to parent confirmed at `https://docs.langchain.com/oss/python/langgraph/use-subgraphs`

### Tertiary (LOW confidence — validate before implementing)
- `useSyncScroll` DOM selector targeting `table` elements inside diff viewer — relies on internal DOM structure; validate against v4.1.2 render output before shipping
- `temperature=0.3` for annotation LLM — reasonable heuristic but not empirically validated for this specific use case; tune during smoke test

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages/versions verified against npm/PyPI/GitHub as of 2026-02-21; no new Python dependencies; one new npm package (react-diff-viewer-continued v4.1.2)
- Architecture (graph routing, HITL pattern): HIGH — `add_conditional_edges(START, ...)`, `interrupt()`, `with_structured_output` all verified against official LangGraph/LangChain docs
- Annotation schema design (`original_span` vs character offsets): MEDIUM — principled reasoning, no single authoritative source; validated against known failure modes of index-based approaches
- Frontend scroll sync: MEDIUM — library behavior confirmed; custom hook approach is the community-accepted workaround; specific selector targeting is LOW until tested against v4.1.2 DOM output

**Research date:** 2026-02-21
**Valid until:** 2026-03-23 (30 days — stable libraries; re-verify react-diff-viewer-continued version before pinning if more than 2 weeks elapse before Phase 4 starts)
