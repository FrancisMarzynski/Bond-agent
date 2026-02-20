# Phase 2: Author Mode Backend - Context

**Gathered:** 2026-02-20
**Status:** Ready for planning

<domain>
## Phase Boundary

The complete Author mode pipeline running in Python: topic + keywords input → web research → HITL Checkpoint 1 (structure approval) → draft generation with RAG style injection → HITL Checkpoint 2 (draft approval) → metadata save. No frontend in this phase — all interaction is via the test harness or Python entrypoint. LangGraph StateGraph with SqliteSaver checkpointer.

</domain>

<decisions>
## Implementation Decisions

### Research report format
- Structure: Title + URL + 2-3 sentence summary per source
- Begins with a brief synthesis section (2-3 paragraphs) summarizing key themes across sources before the source list
- Number of sources: Claude's discretion based on topic complexity
- Storage and persistence within session: Claude's discretion (LangGraph state or file-backed — whatever fits the graph design)

### Checkpoint 1 interaction model
- On rejection: user edits the H1/H2/H3 structure outline directly, with an optional free-text note
- Edited structure + note are fed back to regenerate the proposal

### Checkpoint 2 interaction model
- On rejection: targeted revision of flagged sections only — user specifies which sections to redo, others remain
- The 3-iteration limit is a soft cap: after 3 iterations, continue with a warning (no hard block — user can keep going)
- Session recovery: resume from last LangGraph checkpoint via SqliteSaver if interrupted (no lost work)

### Draft quality enforcement
- If hard constraints aren't met (keyword placement, heading hierarchy, meta-description length, word count, RAG fragment count): auto-retry silently up to 2 times, then surface the failure
- RAG style fragment integration: Claude's discretion — pick the approach that produces the most natural style transfer
- Minimum word count: configurable via env var, default 800 words
- Low corpus warning: if corpus is below the 10-article threshold, warn the user and pause — proceed only if user confirms

### Duplicate detection
- Override mechanism: HITL interrupt — pipeline pauses, user decides yes/no before research begins
- Warning content: Claude's discretion — show what's most useful to make the override decision
- Default similarity threshold: Claude's discretion — calibrate to embedding similarity norms
- Override logging: none — once overridden, the session proceeds as a clean new run (no trace in Metadata Log)

### Claude's Discretion
- Number of research sources (scale to topic complexity)
- Research report storage within session (in-graph state vs. file-backed)
- RAG fragment integration approach (soft prompt injection vs. structural placement)
- Duplicate warning content (what context to surface)
- Default DUPLICATE_THRESHOLD value

</decisions>

<specifics>
## Specific Ideas

- No specific product references mentioned — open to standard approaches for LangGraph HITL patterns and research report structure

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-author-mode-backend*
*Context gathered: 2026-02-20*
