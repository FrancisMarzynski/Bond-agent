# Phase 1: RAG Corpus Onboarding - Context

**Gathered:** 2026-02-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Populate the style corpus from multiple sources and verify retrieval quality before any generation runs. This phase delivers ingestion (paste, file upload, Google Drive, blog URL), source tagging, corpus status visibility, and a retrieval smoke test. The browser UI for corpus management is Phase 3 — Phase 1 is developer-only internal tooling.

</domain>

<decisions>
## Implementation Decisions

### Ingestion interface
- Developer-only internal tooling — no UX polish required
- All 4 ingestion paths ship in Phase 1: text paste, file upload (PDF/DOCX/TXT), Google Drive folder, blog URL scraper
- Interface form (CLI scripts, minimal FastAPI+HTML, or Jupyter): Claude's discretion — choose whatever fits the Phase 3 architecture best
- Corpus status view placement (article count, chunk count, low-corpus warning): Claude's discretion

### Source tagging
- Two values: "own text" and "external blogger"
- Taxonomy is closed for now but designed as an enum — adding new values later should be easy
- How the user specifies the tag (required flag, default, interactive prompt): Claude's discretion given developer-only context
- Batch-level tagging: one tag per ingestion source (URL, Drive folder, etc.); individual article overrides within a batch are Claude's discretion
- Tags affect retrieval weighting: own text fragments are preferred over external blogger fragments when available

### Retrieval smoke test
- Output: top-N fragments with cosine similarity scores and source metadata (author tag, source type)
- Query: default query baked in + optional override to use a custom query
- Number of results (N) and smoke test structure (standalone vs. integrated with status view): Claude's discretion

### Failure handling
- All failure types follow the same policy: skip and warn, continue with the rest of the batch
  - Blog URL unreachable or not an article → skip and warn
  - PDF/DOCX parse failure (corrupt, password-protected) → skip and warn
  - Google Drive folder empty or all files unreadable/access-denied → warn, zero articles added, continue
- Report format: per-item inline warnings are sufficient; no end-of-batch summary needed

### Claude's Discretion
- Exact ingestion entry point (CLI vs. minimal web form vs. notebook)
- Corpus status view placement and format
- Source tag specification UX (flag/prompt/default)
- Batch vs. individual article tag granularity
- Number of smoke test results returned
- Smoke test command structure (standalone vs. part of status)

</decisions>

<specifics>
## Specific Ideas

- No specific UI or UX references given — open to standard developer tooling patterns
- The interface is intentionally throwaway since Phase 3 replaces the corpus management surface entirely

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-rag-corpus-onboarding*
*Context gathered: 2026-02-20*
