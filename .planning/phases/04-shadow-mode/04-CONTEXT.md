# Phase 4: Shadow Mode - Context

**Gathered:** 2026-02-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Users submit existing text and receive two outputs: an annotated version (inline correction suggestions derived from style corpus comparison) and a fully corrected version. Users can reject suggestions per-annotation and trigger regeneration up to 3 iterations without losing the original text or session context. Creating content from scratch, YouTube, and social repurposing are out of scope.

</domain>

<decisions>
## Implementation Decisions

### Annotation presentation
- All deviations annotated — comprehensive coverage, not just top-N
- Each annotation shows the suggested replacement + a brief reason (e.g., "Use X instead of Y — your style uses shorter sentences here")
- Visual annotation style: Claude's discretion (pick whatever renders cleanest in the existing MarkdownEditor)
- Whether to normalize whitespace/formatting before annotating: Claude's discretion

### Analysis scope
- Comprehensive analysis: style (word choice, tone, rhythm), structure (paragraph flow, heading usage), grammar, and clarity — all checked against the corpus
- Corpus entry weighting (own text vs external blogger): Claude's discretion — pick the strategy that produces the most useful corrections
- Analysis granularity (full-text pass vs section-by-section): Claude's discretion based on text length
- Whether to include a summary alignment verdict: Claude's discretion — include only if annotation density makes it useful

### Dual-output layout
- Side-by-side split pane: annotated original on the left, corrected version on the right
- Synchronized scroll — both panes move together for easy comparison
- Corrected version pane is editable — user can tweak it directly before copying
- "Copy corrected" button on the corrected pane for one-click clipboard copy

### Rejection feedback
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

</decisions>

<specifics>
## Specific Ideas

- No specific references — open to standard approaches consistent with the existing MarkdownEditor and HITL patterns from Phase 3

</specifics>

<deferred>
## Deferred Ideas

- None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-shadow-mode*
*Context gathered: 2026-02-21*
