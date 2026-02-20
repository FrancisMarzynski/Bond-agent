# Phase 3: Streaming API and Frontend - Context

**Gathered:** 2026-02-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Browser UI for the complete Author mode workflow — streaming output, dedicated markdown editor, checkpoint approval/rejection, and corpus management access. Shadow mode UI is out of scope (Phase 4). New capabilities like user accounts, settings, or analytics belong in future phases.

</domain>

<decisions>
## Implementation Decisions

### Layout & content structure
- Draft appears in a dedicated editor pane — separate from the chat, with its own scroll
- Author / Shadow mode toggle is a toggle switch in the header/nav — always visible, not dominant
- Session history appears in a left sidebar — users can revisit past drafts and resume incomplete sessions
- Overall layout structure (how chat and editor pane are arranged spatially): Claude's discretion

### Streaming & progress UX
- Research stage: a stage indicator shows while research runs; full result appears at once when done (no word-by-word streaming for research)
- Writing stage: tokens stream directly into the editor pane as they arrive — the draft builds up live in the editor
- Stage progression (Research → Structure → Writing) communicated via a stepper / progress bar at the top showing the current stage
- Errors during long operations: error message appears in the chat with a retry button

### Checkpoint interaction
- Reject feedback flow: chat-style — Reject action triggers an agent message asking what to change, focus moves to the normal chat input for the user's reply
- Iteration limit display: remaining attempts counter is shown near the Reject button at Checkpoint 2 (e.g. "2 of 3 attempts remaining")
- Approve/Reject button placement and post-checkpoint transitions: Claude's discretion

### Corpus management
- Ingestion form presents all 4 input types as stacked form sections: paste text, file upload, Google Drive folder, blog URL — each as a distinct card/section on the page
- Ingestion progress: inline feedback within the submitted section (spinner → success/error state)
- Where corpus management lives in the app and how corpus status is surfaced: Claude's discretion

### Claude's Discretion
- Overall spatial layout (how chat column and editor pane relate)
- Approve/Reject button placement at checkpoints
- Post-checkpoint visual transitions (what happens after user approves)
- Corpus management page/route location
- How corpus status (article count, low-corpus warning) is surfaced in the main UI

</decisions>

<specifics>
## Specific Ideas

No specific references — open to standard approaches that feel clean and minimal.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-streaming-api-and-frontend*
*Context gathered: 2026-02-20*
