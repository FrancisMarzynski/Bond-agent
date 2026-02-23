# Roadmap: Bond — Agent Redakcyjny

## Overview

Bond is built in four sequential phases, each unlocking the next. Phase 1 populates the RAG style corpus and proves retrieval quality — this is a hard prerequisite because no style-mimicry node has value without a validated corpus. Phase 2 implements the full Author mode pipeline end-to-end in Python, with HITL checkpoints proven in isolation before any streaming surface is added. Phase 3 wires the proven backend to a browser via FastAPI SSE and a Next.js frontend, completing the user-facing Author mode flow. Phase 4 adds Shadow mode as a second branch on the same LangGraph graph, reusing all shared infrastructure from earlier phases. YouTube and social repurposing are v2 and not covered here.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: RAG Corpus Onboarding** - Users can populate and validate the style corpus that all generation depends on
- [ ] **Phase 2: Author Mode Backend** - The full research-to-approved-draft pipeline works end-to-end in Python with HITL checkpoints
- [ ] **Phase 3: Streaming API and Frontend** - Users can run the complete Author mode workflow in a browser with streaming output and approval UI
- [ ] **Phase 4: Shadow Mode** - Users can submit existing text for style analysis and receive annotated corrections against their style corpus

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
- [ ] 02-02-PLAN.md — Duplicate check node (ChromaDB embedding similarity, HITL interrupt, DUPLICATE_THRESHOLD) and Researcher node (Exa integration, session cache, report formatting)
- [ ] 02-03-PLAN.md — Structure node (H1/H2/H3 proposal from research report), Checkpoint 1 HITL node (approve/reject with edited structure feedback), Writer node (SEO-compliant draft, RAG few-shot injection, auto-retry validation)
- [ ] 02-04-PLAN.md — Checkpoint 2 HITL node (targeted section feedback, soft-cap iterations), metadata save node (dual-write SQLite + ChromaDB), CLI test harness, human verification of end-to-end flow

### Phase 3: Streaming API and Frontend
**Goal**: Users can run the complete Author mode workflow in a browser, seeing tokens stream progressively and approving or rejecting at each checkpoint through a dedicated UI
**Depends on**: Phase 2
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, UI-07, UI-08
**Success Criteria** (what must be TRUE):
  1. User can select Author or Shadow mode via a visible toggle in the main chat view
  2. During long operations (research, writing), a progress indicator shows the current stage (research, structure, writing) and LLM tokens appear progressively as they are generated — the user never sees a blank screen for more than 5 seconds
  3. Generated content appears in a Markdown editor with rendered preview
  4. Approve and Reject buttons appear at each checkpoint; Reject reveals a feedback text field; the session resumes correctly from the checkpoint after the user acts
  5. The "Approve and Save" button saves metadata to the Metadata Log and marks the topic as used
  6. The corpus management section is accessible from the UI, showing article count, chunk count, and allowing new article ingestion
**Plans**: 5 plans

Plans:
- [ ] 03-01-PLAN.md — FastAPI app scaffold (lifespan, CORS, AsyncSqliteSaver) + /api/chat/stream, /api/chat/resume, /api/corpus/ingest, /api/corpus/status endpoints
- [ ] 03-02-PLAN.md — Next.js 15 project bootstrap, Zustand chatStore, SSEParser, useStream and useSession hooks
- [ ] 03-03-PLAN.md — App layout (sidebar, header), ModeToggle (Author/Shadow switch), StageProgress stepper (Research → Structure → Writing)
- [ ] 03-04-PLAN.md — ChatInterface, EditorPane (@uiw/react-md-editor streaming), CheckpointPanel (Approve/Reject/Approve+Save), main page layout
- [ ] 03-05-PLAN.md — Corpus management page (/corpus route), CorpusStatus, IngestionForm (4 stacked cards), sidebar navigation, human verification checkpoint

### Phase 4: Shadow Mode
**Goal**: Users can submit an existing text and receive both an annotated version (inline correction suggestions) and a corrected version, with the ability to reject and regenerate alternatives
**Depends on**: Phase 3
**Requirements**: SHAD-01, SHAD-02, SHAD-03, SHAD-04, SHAD-05, SHAD-06
**Success Criteria** (what must be TRUE):
  1. User can paste existing text and trigger Shadow mode analysis from the main chat interface
  2. The agent compares the submitted text against the style corpus and produces concrete, inline correction annotations
  3. User sees two outputs side by side: the annotated original and the fully corrected version
  4. User can reject the suggestions with a reason; the agent regenerates alternative corrections (max 3 iterations) without losing the original text or session context
**Plans**: 2 plans

Plans:
- [ ] 04-01-PLAN.md — BondState extension + Shadow branch nodes (shadow_analyze, shadow_annotate, graph dual-branch routing, AuthorState alias)
- [ ] 04-02-PLAN.md — Shadow HITL checkpoint node, full branch wiring, FastAPI shadow state init, frontend ShadowPanel + AnnotationList + useSyncScroll, end-to-end smoke test

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. RAG Corpus Onboarding | 3/3 | Complete | 2026-02-22 |
| 2. Author Mode Backend | 2/4 | In Progress|  |
| 3. Streaming API and Frontend | 0/4 | Not started | - |
| 4. Shadow Mode | 0/2 | Not started | - |
