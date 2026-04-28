# Roadmap: Bond — Agent Redakcyjny

## Overview

Bond is built in four sequential phases, each unlocking the next. Phase 1 populates the RAG style corpus and proves retrieval quality — this is a hard prerequisite because no style-mimicry node has value without a validated corpus. Phase 2 implements the full Author mode pipeline end-to-end in Python, with HITL checkpoints proven in isolation before any streaming surface is added. Phase 3 wires the proven backend to a browser via FastAPI SSE and a Next.js frontend, completing the user-facing Author mode flow. Phase 4 adds Shadow mode as a second branch on the same LangGraph graph, reusing all shared infrastructure from earlier phases. YouTube and social repurposing are v2 and not covered here.

**Current status:** v1 signed off on 2026-04-28 after Shadow HITL closure, detached runtime validation, responsive remediation, confirmation of URL ingest SSRF protection already present in code, baseline live Exa validation for curated Polish research queries, post-v1 threshold calibration on local repo data (defaults retained), and post-v1 integrity/session hardening including duplicate-store reconciliation, mode-aware session restore, honest HTTP stream failures, and zero-chunk file-ingest UX. The active post-v1 operational track is internal deployment hardening under `.agents/plans/`; Plan 01 (security contract and backend baseline) is complete, and Plan 02 (frontend gateway/auth) is the current next step.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: RAG Corpus Onboarding** - Users can populate and validate the style corpus that all generation depends on
- [x] **Phase 2: Author Mode Backend** - The full research-to-approved-draft pipeline works end-to-end in Python with HITL checkpoints
- [x] **Phase 3: Streaming API and Frontend** - Users can run the complete Author mode workflow in a browser with streaming output and approval UI
- [x] **Phase 4: Shadow Mode** - Complete, including frontend HITL loop and responsive layout validation

## Phase Details

### Phase 1: RAG Corpus Onboarding
**Goal**: Users can populate the style corpus from multiple sources and verify retrieval quality before any generation runs
**Depends on**: Nothing (first phase)
**Requirements**: CORP-01, CORP-02, CORP-03, CORP-04, CORP-05, CORP-06, CORP-07
**Success Criteria** (what must be TRUE):
  1. User can add articles to the corpus by pasting text, uploading a file (PDF, DOCX, TXT), providing a Google Drive folder, or providing a blog URL
  2. Each corpus entry is tagged as "own text" or "external blogger" and that tag is visible in retrieval metadata
  3. User can see how many articles and chunks are currently in the corpus
  4. System warns the user when the corpus contains fewer than 10 articles
  5. A similarity query against the corpus returns relevant style fragments (retrieval quality verifiable before any LLM generation runs)
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — Project setup, shared foundation (config, models, ChromaDB store, article log, chunker), text paste and file upload ingestion
- [x] 01-02-PLAN.md — Blog URL scraper (trafilatura) and Google Drive folder connector ingestion paths
- [x] 01-03-PLAN.md — Corpus status endpoint (article/chunk count, low-corpus warning), retrieval smoke test with two-pass own-before-external weighting, human verification checkpoint

### Phase 2: Author Mode Backend
**Goal**: The complete Author mode pipeline — from topic input through research, HITL approval, draft generation, RAG style injection, and metadata save — works correctly in Python before any frontend exists
**Depends on**: Phase 1
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-07, AUTH-08, AUTH-09, AUTH-10, AUTH-11, DUPL-01, DUPL-02, DUPL-03, DUPL-04
**Success Criteria** (what must be TRUE):
  1. User (or test harness) can submit a topic and keywords and receive a web research report with titled sources, links, and summaries
  2. User can approve or reject the research report and proposed H1/H2/H3 structure at Checkpoint 1; rejection with feedback causes regeneration without losing session context
  3. After Checkpoint 1 approval, a complete SEO-compliant draft is generated: keyword in H1 and first paragraph, correct heading hierarchy, 150-160 character meta-description, minimum 800 words, with 3-5 RAG exemplar fragments injected
  4. User can approve or reject the stylized draft at Checkpoint 2 (max 3 feedback iterations); approval saves topic and date to Metadata Log
  5. Before research begins, the system checks for duplicate topics by embedding similarity and informs the user of any match with title and publication date; user can override the warning
  6. Web search results are cached within a session so repeating the same topic does not trigger a second Exa API call
**Plans**: 4 plans

Plans:
- [x] 02-01-PLAN.md — LangGraph StateGraph skeleton (AuthorState, graph wiring with stubs, SqliteSaver, Metadata Log SQLite schema), Phase 2 dependencies and env vars
- [x] 02-02-PLAN.md — Duplicate check node (ChromaDB embedding similarity, HITL interrupt, DUPLICATE_THRESHOLD) and Researcher node (Exa integration, session cache, report formatting)
- [x] 02-03-PLAN.md — Structure node (H1/H2/H3 proposal from research report), Checkpoint 1 HITL node (approve/reject with edited structure feedback), Writer node (SEO-compliant draft, RAG few-shot injection, auto-retry validation)
- [x] 02-04-PLAN.md — Checkpoint 2 HITL node (targeted section feedback, soft-cap iterations), metadata save node (dual-write SQLite + ChromaDB), CLI test harness, human verification of end-to-end flow

### Phase 3: Streaming API and Frontend
**Goal**: Users can run the complete Author mode workflow in a browser, seeing tokens stream progressively and approving or rejecting at each checkpoint through a dedicated UI
**Depends on**: Phase 2
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, UI-07, UI-08
**Status**: ✅ Complete — 2026-04-23
**Success Criteria** (all met):
  1. ✅ User can select Author or Shadow mode via ModeToggle in the header
  2. ✅ StageProgress stepper shows current stage; LLM tokens stream progressively via SSE
  3. ✅ Generated content appears in EditorPane (@uiw/react-md-editor) with live preview
  4. ✅ CheckpointPanel shows Approve/Reject at each HITL pause; Reject reveals feedback field; session resumes via /api/chat/resume
  5. ✅ "Approve and Save" button triggers approve_save action saving metadata to SQLite
  6. ✅ Corpus management at /corpus route: CorpusStatusPanel + CorpusAddForm (text/file/URL/Drive tabs)
**Plans**: 5 original plans + 46 additional sub-tasks completed during execution

Plans:
- [x] 03-01-PLAN.md — FastAPI scaffold (lifespan, CORS, AsyncSqliteSaver) + /api/chat/stream, /api/chat/resume, /api/corpus endpoints
- [x] 03-02-PLAN.md — Next.js 15 bootstrap, Zustand chatStore, SSEParser, useStream and useSession hooks
- [x] 03-03-PLAN.md — App layout (sidebar, header), ModeToggle, StageProgress stepper
- [x] 03-04-PLAN.md — ChatInterface, EditorPane, CheckpointPanel, main page layout
- [x] 03-05-PLAN.md — Corpus management (/corpus route), CorpusStatusPanel, CorpusAddForm (4 tabs), sidebar navigation

Additional work completed during Phase 3 (selected highlights):
- Docker + docker-compose for local dev
- Multi-query prompt generation for Researcher node
- Parallel Exa search with deduplication
- Map-reduce structured synthesis in Researcher
- ChromaDB metadata enrichment
- FlashRank reranker (two-pass retrieval)
- Few-shot label injection
- Word count validation
- Structure node promoted to frontier model (gpt-4o)
- Semantic search cache (cross-session)
- Editor export toolbar
- Checkpoint 1 research view
- Shadow mode backend infrastructure (shadow_analyze, shadow_annotate, shadow_checkpoint nodes)
- Shadow mode BondState routing
- Shadow mode HITL iteration loop (backend)
- Shadow mode frontend (ShadowPanel, AnnotationList, /shadow route, shadowStore)
- SSE reconnect with exponential backoff (MAX_RETRIES=5)
- Safety cap on HITL routing (defense-in-depth guards in graph.py)
- Global React ErrorBoundary + Next.js route-level error boundaries
- Logging standardization
- Async ainvoke refactor for all nodes

### Phase 4: Shadow Mode
**Goal**: Users can submit an existing text and receive both an annotated version (inline correction suggestions) and a corrected version, with the ability to reject and regenerate alternatives
**Depends on**: Phase 3
**Requirements**: SHAD-01, SHAD-02, SHAD-03, SHAD-04, SHAD-05, SHAD-06
**Status**: ✅ Complete — frontend HITL wiring and responsive Shadow layout validated on 2026-04-28

**What is built:**
- `shadow_analyze_node` — two-pass ChromaDB retrieval (own-first, external fill)
- `shadow_annotate_node` — structured output via `with_structured_output(AnnotationResult)` with character-level index validation and auto-correction
- `shadow_checkpoint_node` — HITL interrupt, approve/reject/abort, hard cap at 3 iterations
- `BondState` extended with all shadow fields; `AuthorState` alias preserved
- Dual-branch graph routing (`route_mode()` at START)
- `ShadowPanel` — desktop 3-column UI plus stacked mobile/tablet comparison flow below `lg`
- `AnnotationList` — sidebar / top-section annotations with click-to-scroll navigation
- `/shadow` route, `shadowStore` (Zustand)
- Shadow HITL frontend wiring: `HitlPauseSchema` carries `annotations`, `shadow_corrected_text`, `iteration_count`; approve/reject flow resumes graph correctly
- Browser validation: Shadow route, checkpoint hydration, approve/reject loop and responsive stacked layout re-tested successfully

**Validation closed 2026-04-28:**
- SHAD-05: user sees annotated original and corrected version
- SHAD-06: user can approve/reject and trigger re-generation loop
- Shadow remains usable at `375x812`, `768x1024`, and desktop widths without permanent 3-column squeeze

**Plans**: 2 plans (completed; listed for traceability)

Plans:
- [x] 04-01-PLAN.md — BondState extension + Shadow branch nodes (done during Phase 3 sub-tasks 11–19)
- [x] 04-02-PLAN.md — Shadow HITL checkpoint node + frontend

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

**Overall milestone:** v1 sign-off reached on 2026-04-28.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. RAG Corpus Onboarding | 3/3 | Complete | 2026-02-22 |
| 2. Author Mode Backend | 4/4 | Complete | 2026-02-23 |
| 3. Streaming API and Frontend | 5/5 + 46 sub-tasks | Complete | 2026-04-23 |
| 4. Shadow Mode | 2/2 | Complete | 2026-04-28 |
