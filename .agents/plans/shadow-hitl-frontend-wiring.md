# Feature: Shadow HITL Frontend Wiring (SHAD-05 / SHAD-06)

The following plan should be complete, but validate patterns and codebase state before implementing.
Pay special attention to Zod schema field names, exact store method signatures, and the `resumeStream` call signature.

## Feature Description

The Shadow mode backend (`shadow_checkpoint_node`) correctly pauses the graph via `interrupt()` and packages `annotations`, `shadow_corrected_text`, and `iteration_count` into the `hitl_pause` SSE event payload. However the frontend discards all three fields because `HitlPauseSchema` (Zod) doesn't declare them — Zod strips unknown keys. Additionally, the `hitl_pause` handler never calls `shadowStore`'s setters, and `ShadowPanel` has no approve/reject buttons. The result: Shadow mode is completely non-functional for users end-to-end.

## User Story

As a marketing employee using Shadow mode,
I want to see the AI's style annotations and corrected text after analysis, and be able to approve or reject them with feedback,
So that I can either accept the corrections or request alternative suggestions.

## Problem Statement

Three concrete wiring failures after the `hitl_pause` SSE event arrives:
1. `HitlPauseSchema` (Zod, `useStream.ts:24-36`) does not declare `annotations`, `shadow_corrected_text`, or `iteration_count` — Zod silently strips them on `safeParse`.
2. The `hitl_pause` branch in `consumeStream` (`useStream.ts:118-134`) never calls `useShadowStore.getState().setAnnotations()` or `setShadowCorrectedText()`.
3. `ShadowPanel.tsx` has no approve/reject buttons — there is no way to resume the graph after `shadow_checkpoint` fires.

## Solution Statement

1. Extend `HitlPause` type in `chatStore.ts` and `HitlPauseSchema` in `useStream.ts` with the three missing fields.
2. In the `hitl_pause` case of `consumeStream`, detect `checkpoint_id === "shadow_checkpoint"` and populate `shadowStore`.
3. Add an approve/reject panel to `ShadowPanel`'s comparison view that becomes visible when `hitlPause?.checkpoint_id === "shadow_checkpoint"`.

## Feature Metadata

**Feature Type**: Bug Fix  
**Estimated Complexity**: Low  
**Primary Systems Affected**: `frontend/src/store/chatStore.ts`, `frontend/src/hooks/useStream.ts`, `frontend/src/components/ShadowPanel.tsx`  
**Dependencies**: None (no new libraries required)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

- `frontend/src/hooks/useStream.ts` (lines 24-36) — `HitlPauseSchema` Zod definition missing the three fields
- `frontend/src/hooks/useStream.ts` (lines 118-134) — `hitl_pause` handler that sets `chatStore` but never touches `shadowStore`
- `frontend/src/store/chatStore.ts` (lines 6-18) — `HitlPause` TypeScript type — must stay in sync with Zod schema
- `frontend/src/store/shadowStore.ts` (lines 1-31) — `setAnnotations`, `setShadowCorrectedText` methods, `Annotation` interface
- `frontend/src/components/ShadowPanel.tsx` (lines 106-222) — comparison view where approve/reject must be injected
- `frontend/src/components/ShadowPanel.tsx` (lines 61-63) — already destructures `useShadowStore` and `useChatStore`; `useStream` is already imported
- `bond/graph/nodes/shadow_checkpoint.py` (lines 66-77) — the exact `interrupt()` payload shape (source of truth for field names)
- `bond/api/routes/chat.py` (lines 420-434) — `get_chat_history` — copies ALL `interrupt()` fields into `hitlPause` dict verbatim, so `annotations`, `shadow_corrected_text`, `iteration_count` ARE in the SSE payload already

### New Files to Create

None — all changes are in three existing files.

### Relevant Documentation

No external docs needed — this is a pure wiring fix using existing patterns.

### Patterns to Follow

**Zod schema extension** — mirror existing optional fields in `HitlPauseSchema`:
```ts
// useStream.ts — existing pattern (lines 24-36)
const HitlPauseSchema = z.object({
    checkpoint_id: z.string(),
    type: z.string(),
    iterations_remaining: z.number().optional(),
    research_report: z.string().optional(),
    heading_structure: z.string().optional(),
    warning: z.string().optional(),
    existing_title: z.string().optional(),
    existing_date: z.string().optional(),
    similarity_score: z.number().optional(),
    // ADD:
    annotations: z.array(z.object({
        id: z.string(),
        original_span: z.string(),
        replacement: z.string(),
        reason: z.string(),
        start_index: z.number(),
        end_index: z.number(),
    })).optional(),
    shadow_corrected_text: z.string().optional(),
    iteration_count: z.number().optional(),
});
```

**Accessing store outside React** — existing pattern in `consumeStream` (`useStream.ts:49`):
```ts
const store = useChatStore.getState();       // already used
useShadowStore.getState().setAnnotations([]); // same pattern for shadowStore
```

**`resumeStream` call signature** — existing usage in `CheckpointPanel.tsx`:
```ts
resumeStream(threadId, action, feedback, onThreadId)
// action: "approve" | "approve_save" | "reject"
// For shadow: "approve" or "reject" (NOT "approve_save" — no metadata to save)
```

**Button + Textarea pattern** — see `ShadowPanel.tsx:234-259` (input view) for existing Textarea + Button usage with disabled state.

---

## IMPLEMENTATION PLAN

### Phase 1: Type and Schema Extension

Extend the Zod runtime schema AND the TypeScript type that mirrors it.

### Phase 2: Store Wiring in hitl_pause Handler

Populate `shadowStore` when `checkpoint_id === "shadow_checkpoint"`.

### Phase 3: Approve/Reject UI in ShadowPanel

Add the HITL control panel inside the comparison view's status bar area.

---

## STEP-BY-STEP TASKS

### TASK 1 — UPDATE `frontend/src/store/chatStore.ts`

Extend the `HitlPause` TypeScript type (lines 6-18) with the three missing shadow fields.

- **IMPLEMENT**: Add `annotations`, `shadow_corrected_text`, `iteration_count` to the `HitlPause` type
- **PATTERN**: Mirror existing optional fields on the type (line 8: `iterations_remaining?: number`)
- **IMPORTS**: Import `Annotation` from `@/store/shadowStore`
- **GOTCHA**: `HitlPause` is a union type ending in `| null`. The new fields go on the object branch, not on the null branch.
- **VALIDATE**: `cd frontend && npx tsc --noEmit`

```ts
// New HitlPause type (replace lines 6-18):
import type { Annotation } from "@/store/shadowStore";

export type HitlPause = {
    checkpoint_id: string;
    type: string;
    iterations_remaining?: number;
    research_report?: string;
    heading_structure?: string;
    warning?: string;
    existing_title?: string;
    existing_date?: string;
    similarity_score?: number;
    // Shadow mode fields
    annotations?: Annotation[];
    shadow_corrected_text?: string;
    iteration_count?: number;
} | null;
```

---

### TASK 2 — UPDATE `frontend/src/hooks/useStream.ts` — Extend Zod schema

Extend `HitlPauseSchema` (lines 24-36) with the three missing fields.

- **IMPLEMENT**: Add `annotations` (array of annotation objects), `shadow_corrected_text` (string), `iteration_count` (number) as optional fields
- **PATTERN**: Mirror existing optional fields (`iterations_remaining: z.number().optional()`)
- **GOTCHA**: The `annotations` Zod schema must exactly match the `Annotation` interface in `shadowStore.ts` — `id`, `original_span`, `replacement`, `reason`, `start_index`, `end_index`. Zod will only parse fields it knows about, so every field must be declared.
- **VALIDATE**: `cd frontend && npx tsc --noEmit`

```ts
// Annotation sub-schema — add above HitlPauseSchema, at module scope:
const AnnotationSchema = z.object({
    id: z.string(),
    original_span: z.string(),
    replacement: z.string(),
    reason: z.string(),
    start_index: z.number(),
    end_index: z.number(),
});

// Updated HitlPauseSchema:
const HitlPauseSchema = z.object({
    checkpoint_id: z.string(),
    type: z.string(),
    iterations_remaining: z.number().optional(),
    research_report: z.string().optional(),
    heading_structure: z.string().optional(),
    warning: z.string().optional(),
    existing_title: z.string().optional(),
    existing_date: z.string().optional(),
    similarity_score: z.number().optional(),
    annotations: z.array(AnnotationSchema).optional(),
    shadow_corrected_text: z.string().optional(),
    iteration_count: z.number().optional(),
});
```

---

### TASK 3 — UPDATE `frontend/src/hooks/useStream.ts` — Wire shadowStore in hitl_pause handler

In `consumeStream`, inside the `hitl_pause` case (lines 118-134), call `shadowStore` setters when `checkpoint_id === "shadow_checkpoint"`.

- **IMPLEMENT**: After `store.setHitlPause(...)`, check `result.data.checkpoint_id === "shadow_checkpoint"` and call `useShadowStore.getState().setAnnotations()` and `setShadowCorrectedText()`
- **PATTERN**: `useShadowStore.getState()` — same pattern as `useChatStore.getState()` used at line 49
- **IMPORTS**: `useShadowStore` is already imported at line 4
- **GOTCHA**: `result.data.annotations` is `Annotation[] | undefined` after Zod parses. Provide a fallback empty array when undefined. Same for `shadow_corrected_text`.
- **GOTCHA**: The `setHitlPause` call must include ALL new fields so the store object is complete — update the spread to pass `annotations`, `shadow_corrected_text`, `iteration_count`.
- **VALIDATE**: `cd frontend && npm run build` (no type errors)

```ts
case "hitl_pause": {
    const result = HitlPauseSchema.safeParse(payload);
    if (!result.success) throw new Error("Invalid hitl_pause event data");
    store.setHitlPause({
        checkpoint_id: result.data.checkpoint_id,
        type: result.data.type,
        iterations_remaining: result.data.iterations_remaining,
        research_report: result.data.research_report,
        heading_structure: result.data.heading_structure,
        warning: result.data.warning,
        existing_title: result.data.existing_title,
        existing_date: result.data.existing_date,
        similarity_score: result.data.similarity_score,
        annotations: result.data.annotations,
        shadow_corrected_text: result.data.shadow_corrected_text,
        iteration_count: result.data.iteration_count,
    });
    // Populate shadowStore when paused at shadow_checkpoint
    if (result.data.checkpoint_id === "shadow_checkpoint") {
        const shadowState = useShadowStore.getState();
        shadowState.setAnnotations(result.data.annotations ?? []);
        shadowState.setShadowCorrectedText(result.data.shadow_corrected_text ?? "");
    }
    store.setStreaming(false);
    endedCleanly = true;
    return endedCleanly;
}
```

---

### TASK 4 — UPDATE `frontend/src/components/ShadowPanel.tsx` — Add approve/reject HITL panel

In the comparison view (the `if (originalText)` branch, lines 106-222), add an approve/reject control panel that appears when `hitlPause?.checkpoint_id === "shadow_checkpoint"`.

- **IMPLEMENT**: Add `hitlPause` and `threadId` from `useChatStore`; add `resumeStream` from `useStream`; add local `feedbackText` state; render approve/reject buttons with feedback textarea in the status bar area
- **PATTERN**: `resumeStream(threadId!, "approve", null, (id) => setThreadId(id))` — mirror CheckpointPanel's resume call pattern
- **IMPORTS**: `useStream` is already imported. Need to destructure `resumeStream`. Need to add `hitlPause`, `threadId`, `setThreadId` from `useChatStore`.
- **GOTCHA**: `threadId` may be `null` — guard with `threadId &&` before calling `resumeStream`. Type assert `threadId!` after the guard.
- **GOTCHA**: On approve, call `resumeStream` with `action: "approve"` and `feedback: null`. On reject, call with `action: "reject"` and `feedback: feedbackText`. Reset `feedbackText` to `""` after calling.
- **GOTCHA**: After resume, `hitlPause` will be set to `null` by the `hitl_pause` handler when the next event arrives OR by `store.setHitlPause(null)` called inside `resumeStream`. The panel will hide automatically.
- **VALIDATE**: `cd frontend && npm run dev` — start the dev server and manually test in browser

```tsx
// Add to destructured values from useChatStore (around line 62):
const { draft, setDraft, isStreaming, threadId, setThreadId, resetSession, hitlPause } =
    useChatStore();

// Add resumeStream from useStream (around line 63-64):
const { startStream, resumeStream } = useStream();

// Add local feedback state at top of component (around line 55):
const [feedbackText, setFeedbackText] = useState("");

// Approve/reject panel JSX — insert inside the status bar div (after the "Nowy tekst" button):
{hitlPause?.checkpoint_id === "shadow_checkpoint" && !isStreaming && threadId && (
    <div className="border-t px-4 py-3 space-y-2 shrink-0 bg-background">
        <p className="text-xs font-medium text-foreground">
            Zatwierdzasz adnotacje? ({hitlPause.iteration_count !== undefined
                ? `Iteracja ${hitlPause.iteration_count + 1}/3`
                : ""})
        </p>
        <div className="flex gap-2">
            <Button
                size="sm"
                onClick={() => {
                    resumeStream(threadId, "approve", null, (id) => setThreadId(id));
                }}
            >
                Zatwierdź
            </Button>
            <Button
                variant="outline"
                size="sm"
                onClick={() => {
                    if (!feedbackText.trim()) return;
                    resumeStream(threadId, "reject", feedbackText.trim(), (id) => setThreadId(id));
                    setFeedbackText("");
                }}
                disabled={!feedbackText.trim()}
            >
                Odrzuć
            </Button>
        </div>
        <Textarea
            value={feedbackText}
            onChange={(e) => setFeedbackText(e.target.value)}
            placeholder="Napisz co poprawić (wymagane do odrzucenia)..."
            className="text-xs min-h-[60px] resize-none"
        />
    </div>
)}
```

---

## TESTING STRATEGY

### Manual End-to-End Test (primary validation method)

1. Start both services: `docker compose up` or `uv run uvicorn bond.api.main:app --reload --port 8000` + `cd frontend && npm run dev`
2. Navigate to `/shadow`
3. Paste a text sample (>100 words) and click "Analizuj styl"
4. Observe `StageProgress` advancing through `shadow_analysis` → `shadow_annotation` → pausing
5. Verify: `AnnotationList` sidebar shows annotation cards
6. Verify: highlighted spans appear in the "Tekst oryginalny" column
7. Verify: "Wersja poprawiona" column shows corrected text
8. Verify: approve/reject panel appears below the status bar
9. Click "Zatwierdź" → verify stream resumes, graph reaches done
10. Start fresh, this time reject with feedback → verify new annotations are generated

### Unit Test (optional)

The Zod schema change can be verified with a minimal Jest snapshot if tests exist; the project currently has no frontend tests, so manual validation is the standard.

### TypeScript Check

```bash
cd frontend && npx tsc --noEmit
```

---

## VALIDATION COMMANDS

### Level 1 — Type Checking
```bash
cd frontend && npx tsc --noEmit
```

### Level 2 — Lint
```bash
cd frontend && npm run lint
```

### Level 3 — Build
```bash
cd frontend && npm run build
```

### Level 4 — Manual Validation
1. Navigate to `/shadow`
2. Submit a text sample
3. Confirm annotations appear in `AnnotationList`
4. Confirm approve/reject panel is visible after stream pauses
5. Approve → confirm graph completes
6. Reject with feedback → confirm second iteration runs and new annotations appear

---

## ACCEPTANCE CRITERIA

- [ ] `HitlPauseSchema` includes `annotations`, `shadow_corrected_text`, `iteration_count` fields
- [ ] `HitlPause` TypeScript type includes the same three fields
- [ ] After `shadow_checkpoint` fires, `shadowStore.annotations` is populated
- [ ] After `shadow_checkpoint` fires, `shadowStore.shadowCorrectedText` is populated
- [ ] `ShadowPanel` comparison view shows approve/reject panel when `hitlPause?.checkpoint_id === "shadow_checkpoint"`
- [ ] Approving resumes the graph and reaches `done`
- [ ] Rejecting with feedback sends the feedback and triggers a re-annotation
- [ ] Reject button is disabled when feedback textarea is empty
- [ ] Iteration count is visible to the user in the panel
- [ ] `npx tsc --noEmit` passes with zero errors
- [ ] `npm run lint` passes

---

## COMPLETION CHECKLIST

- [ ] Task 1 completed — `HitlPause` type extended in `chatStore.ts`
- [ ] Task 2 completed — `HitlPauseSchema` and `AnnotationSchema` in `useStream.ts`
- [ ] Task 3 completed — `shadowStore` setters called in `hitl_pause` handler
- [ ] Task 4 completed — approve/reject panel rendered in `ShadowPanel`
- [ ] `npx tsc --noEmit` passes
- [ ] `npm run lint` passes
- [ ] `npm run build` passes
- [ ] Manual end-to-end Shadow flow tested and working

---

## NOTES

**Why Zod strips fields silently**: `z.object(...)` by default calls `.strip()` on unknown keys during `safeParse`. There is no error — fields are simply dropped. This is why the bug went unnoticed during development.

**"approve_save" vs "approve" for Shadow**: The Author mode uses `"approve_save"` at checkpoint_2 to trigger metadata saving. Shadow mode only needs `"approve"` — there is no metadata log entry for Shadow corrections. The `shadow_checkpoint_node` accepts `action: "approve"` and routes to `END`.

**Abort action**: The `shadow_checkpoint_node` supports `action: "abort"` to terminate the pipeline. This plan does not add an abort button — the "Nowy tekst" reset button achieves the same UX goal without needing graph-level abort.

**Confidence Score**: 9.5/10 — all three changes are surgical, the patterns are exact, the backend contract is already correct.
