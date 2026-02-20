# Project Research Summary

**Project:** Bond — AI Blog Writing Agent (Agent Redakcyjny)
**Domain:** LangGraph-based multi-step LLM agent with RAG style mimicry, dual-mode operation, and human-in-the-loop checkpoints
**Researched:** 2026-02-20
**Confidence:** MEDIUM — all external tooling unavailable during research; findings based on training data (cutoff August 2025) + PROJECT.md analysis. Versions require live verification.

## Executive Summary

Bond is a single-user AI blog writing agent with two distinct operating modes: Author (research + draft + style injection) and Shadow (style review + correction). This is not a simple LLM wrapper — it is a stateful, multi-step agentic system with real human approval gates embedded in the execution flow. The canonical Python framework for this class of system is LangGraph, which provides explicit state machines, persistent checkpointing, and interrupt/resume primitives — all of which Bond requires. The architecture decision is clear: one LangGraph StateGraph with a routing node dispatching into dual branches (Author and Shadow), sharing a single ChromaDB RAG store and SQLite checkpointer.

The recommended approach is a layered build starting with zero-LLM infrastructure (RAG corpus ingestion, SQLite, env schema), then adding the graph skeleton with HITL interrupt points, then adding generation nodes one by one, and finally wiring streaming SSE to a Next.js frontend. This order is non-negotiable: the RAG corpus must be populated and validated before any style-mimicry node runs, and the HITL mechanism must be proven in isolation before streaming is added on top. The two signature differentiators — RAG style mimicry and dual-mode operation — are what make Bond genuinely novel; table stakes like long-form generation and web research are necessary but not sufficient.

The dominant risk is invisible degradation: a RAG corpus that is too small produces outputs that look plausible but fail the style-fidelity blind test (KPI4). A HITL checkpoint wired incorrectly re-runs expensive research nodes on resume instead of continuing forward. LLM context window overflow silently truncates research before the writer node sees it. All three of these can appear to work in simple tests and only fail under realistic load. Mitigation is test-first at each layer boundary, with explicit corpus quality checks before integrating with generation.

## Key Findings

### Recommended Stack

The Python backend is built on LangGraph 0.2.x (agent orchestration, state machine, HITL) with LangChain Core 0.3.x as a peer dependency. LLMs are configured via env vars with a cascade strategy: GPT-4o-mini or Claude Haiku for research/analysis nodes, GPT-4o or Claude Sonnet for final draft generation. This reduces cost by 60-80% vs using a frontier model everywhere. Web research uses Exa (not Tavily) because Exa returns full article text rather than snippets — full content is required for blog research and style exemplar retrieval. Vector storage uses ChromaDB (local, file-based) with `paraphrase-multilingual-MiniLM-L12-v2` embeddings for Polish-language content. Session state persists via LangGraph `SqliteSaver` (not `MemorySaver`) from day one.

The frontend is Next.js 14/15 (App Router) with React 18, TypeScript, and Tailwind CSS. The backend API is FastAPI with `sse-starlette` for streaming. YouTube transcript extraction uses `youtube-transcript-api`. All Python tooling uses `uv` for package management.

**Core technologies:**
- LangGraph 0.2.x: agent state machine, HITL interrupt/resume, session checkpointing — the only Python framework with explicit state machines and pause/resume required by Bond
- FastAPI + sse-starlette: async streaming API — matches LangGraph's async generator model natively
- ChromaDB + sentence-transformers: local RAG vector store with multilingual embeddings — zero-ops, free, sized correctly for a small style corpus
- Exa (exa-py): web research with full content retrieval — architecturally superior to snippet-only alternatives for blog research
- Next.js App Router: streaming SSE consumer with React 18 Suspense — best-in-class for LLM token streaming UIs
- SqliteSaver (LangGraph built-in): session persistence — required for HITL resume across page refreshes
- SQLite (stdlib): Metadata Log for duplicate topic detection — zero-ops for single-user MVP

**Critical version risks:** LangGraph 0.1→0.2 had breaking API changes. ChromaDB 0.4→0.5 had breaking API changes. `react-markdown` v9 is ESM-only. Verify all package versions against live registries before pinning.

### Expected Features

Bond's table stakes are long-form Markdown article generation (800+ words with H1/H2/H3 and 150-160 char meta-description), web research with cited sources, an inline feedback/regeneration loop, session context persistence, a Markdown editor with preview, progress indicators, and a visible Author/Shadow mode toggle. These are the floor — any AI writing tool users evaluate will have these.

The differentiators that make Bond worth building are: (1) RAG-based style mimicry that injects the author's own voice into generated content — virtually no competitor does this; (2) Shadow mode for style review and annotated correction against a personal style baseline — most tools only generate; (3) human-in-the-loop checkpoints at research approval and draft approval — competitors auto-proceed, Bond treats the human as the decision-maker; (4) duplicate topic detection via embedding similarity against a Metadata Log — directly addresses a stated baseline problem.

**Must have (table stakes):**
- Long-form article generation (800+ words, H1/H2/H3, meta-description) — core use case
- Web research with cited sources — expected by any content marketer
- Inline feedback / regeneration loop without losing session context — non-negotiable UX
- Progress indication for long operations — users assume broken after 30s silence
- Markdown editor with preview — raw textarea is inadequate for reviewing 800+ word drafts
- Mode selection UI (Author/Shadow toggle) — without it, users are confused about the product

**Should have (core differentiators — MVP):**
- RAG style mimicry from uploaded corpus — the signature feature; directly maps to KPI4
- Shadow mode (style review + annotated correction) — unique in the market
- Human-in-the-loop checkpoints at research and draft stages — builds trust, reduces rejection
- Duplicate topic detection (Metadata Log with embedding similarity) — directly maps to KPI3
- Cascaded model selection (Mini for research, Frontier for draft) — 60-80% cost reduction

**Defer (Phase 2+):**
- YouTube transcript → article pipeline — useful, but depends on the core Author loop working
- Social media repurposing (4 platform variants) — extends value of existing articles, not a foundation feature
- CMS autopost, image suggestions, SEO API integrations — explicitly out of scope for MVP
- Chat history search / archive — nice-to-have UX pattern, not critical for MVP workflow

**Anti-features (do not build):**
- Auto-publish to CMS or social media — bypasses HITL, the core design principle
- Audio/video processing (Whisper, ffmpeg) — YouTube has captions; use `youtube-transcript-api` only
- Fine-tuning on user data — GDPR risk + enormous cost; use RAG + ICL as constrained
- Multi-user accounts / role management — Bond is single-user for MVP

### Architecture Approach

Bond uses a single LangGraph StateGraph with a `route_mode` entry node that dispatches via conditional edges into Author and Shadow branches. Both branches share one `rag_retriever` node and one `save_metadata` node, avoiding redundant ChromaDB calls and duplicate checkpointer state. The HITL interrupt points are wired via `interrupt_before` to pause execution at research approval, structure approval, and draft approval. The streaming surface is LangGraph `astream_events` → FastAPI `EventSourceResponse` → Next.js `ReadableStream`. Three SSE event types carry all communication: `token` (LLM output chunk), `node_complete` (drives progress indicator), and `hitl_pause` (shows approval UI).

**Major components:**
1. LangGraph StateGraph (single graph, dual-branch): Author and Shadow branches share `rag_retriever` and `save_metadata` nodes; `route_mode` dispatches via `state.mode`
2. ChromaDB RAG store: single `bond_style_corpus_v1` collection with per-chunk metadata (`source_type`, `author_id`); queried with topic + first paragraph for dynamic few-shot retrieval
3. FastAPI streaming API: `/api/chat/stream` (SSE, `astream_events`) + `/api/chat/resume` (HITL resume with `graph.update_state`); `/api/corpus/ingest` for RAG population
4. SQLite dual-purpose: `SqliteSaver` for LangGraph session checkpointing + `metadata_log` table for duplicate topic detection
5. Next.js frontend: ChatInterface + ModeToggle + ProgressIndicator + MarkdownEditor + ApproveRejectPanel; thread ID stored in `sessionStorage`

### Critical Pitfalls

1. **RAG corpus too small for reliable style mimicry** — minimum 10+ full articles chunked at paragraph boundaries (300-500 tokens per chunk). Test retrieval quality before wiring to generation. This is a Phase 1 prerequisite that blocks KPI4. See PITFALLS.md #1.

2. **HITL checkpoint not resuming correctly** — always pass the same `thread_id` in `{"configurable": {"thread_id": session_id}}`; use `interrupt_before` on the node after the checkpoint, not on the checkpoint node itself; store `thread_id` in `sessionStorage` not component state. Test the full interrupt→frontend→resume cycle in isolation before wiring to UI. See PITFALLS.md #3.

3. **LLM context window overflow on research + draft cycle** — budget context explicitly: research report max 2000 tokens, exemplar chunks max 1500 tokens total, draft prompt template max 500 tokens. Summarize research before injecting into draft prompt. Use structured output (`{"meta_description": ..., "h1": ..., "body": ...}`). See PITFALLS.md #8.

4. **LangGraph state blowup on long sessions** — use `SqliteSaver` from day one (never `MemorySaver`); keep draft text in dedicated state fields not in `messages` list; limit correction loop history to last N feedback messages only. See PITFALLS.md #2.

5. **Streaming tokens lost or duplicated in React frontend** — use `astream_events` (not `astream`); implement SSE `id:` field for reconnect resume; add SSE heartbeat every 5s to prevent connection timeouts. See PITFALLS.md #4.

## Implications for Roadmap

The dependency chain from FEATURES.md is unambiguous and determines phase order:

```
RAG Corpus (populated + validated) → Style Mimicry → Author mode → Shadow mode
Graph skeleton + HITL → Author branch → Streaming API → Frontend
Metadata Log → Duplicate detection
```

Nothing in the application works correctly without the RAG corpus being populated first, and no style-sensitive output has value without it. The HITL mechanism must be proven before streaming is added, because debugging pause/resume through an SSE stream is significantly harder than debugging it with direct Python calls.

### Phase 1: Foundation — Infrastructure, RAG, and Graph Skeleton

**Rationale:** The RAG corpus is a prerequisite for every style-sensitive node. The graph skeleton with HITL must exist before any generation node is added, because retrofitting checkpointing later breaks state schema compatibility. This is pure foundation with no frontend and no LLM generation — just infrastructure that validates all assumptions.

**Delivers:** Populated RAG corpus with validated retrieval quality; LangGraph StateGraph with routing, HITL interrupt points, and SQLite checkpointer; Metadata Log schema; env var schema with startup validation.

**Addresses:** Corpus ingestion + retrieval (differentiator #1 foundation); duplicate topic detection (differentiator #4 foundation); HITL mechanism (differentiator #3 foundation).

**Avoids:** RAG corpus too small (Pitfall #1 — caught before any generation runs); LangGraph state blowup (Pitfall #2 — SqliteSaver from day one); HITL not resuming correctly (Pitfall #3 — tested in isolation before streaming).

**Research flag:** NEEDS RESEARCH — LangGraph `SqliteSaver` import path changed between 0.1 and 0.2; `interrupt_before` API specifics need Context7 verification before implementation.

### Phase 2: Author Mode Core — Research, Draft, Style Injection

**Rationale:** Author mode is the primary value delivery. The full pipeline (research → HITL checkpoint → structure → draft → RAG style injection → HITL checkpoint → metadata save) must work end-to-end before any secondary feature is added. This phase produces the first real article.

**Delivers:** Working Author mode pipeline from topic input to approved Markdown draft with style injection; cascaded model selection (Mini for research, Frontier for draft); duplicate topic detection active; research caching.

**Addresses:** Long-form article generation (table stakes); web research with cited sources (table stakes); RAG style mimicry (differentiator #1); HITL checkpoints (differentiator #3); duplicate detection (differentiator #4); cascaded model selection (differentiator #8 in FEATURES.md).

**Avoids:** Context window overflow (Pitfall #3 — context budgeted in writer node); Exa quality for Polish queries (Pitfall #5 — language hints + domain filtering implemented); SEO prompt drift (Pitfall #10 — structured output + post-generation validation); hardcoded model names (minor pitfall — env vars from day one).

**Research flag:** NEEDS RESEARCH — Exa API query parameters for Polish-language filtering need live verification; `astream_events` API version (`version="v2"`) needs Context7 confirmation.

### Phase 3: Streaming API and Frontend

**Rationale:** Only after Author mode works end-to-end in Python (Phase 2) should the streaming surface be added. Debugging SSE streaming + HITL simultaneously is exponentially harder than debugging each in isolation. The frontend is a pure consumer of the API — no business logic lives in it.

**Delivers:** FastAPI SSE endpoint (`/api/chat/stream`, `/api/chat/resume`, `/api/corpus/ingest`); Next.js frontend with ChatInterface, ModeToggle, ProgressIndicator, MarkdownEditor, and ApproveRejectPanel; thread ID persistence in sessionStorage; complete user-facing Author mode flow.

**Addresses:** All UI table stakes (progress indicator, Markdown editor, mode toggle, inline feedback loop); streaming token display; HITL approval UI.

**Avoids:** Streaming tokens lost/duplicated (Pitfall #4 — SSE `id:` field, heartbeat, `astream_events`); missing loading states (minor pitfall — heartbeat every 5s); `MemorySaver` on server restart (minor pitfall — already addressed in Phase 1).

**Research flag:** STANDARD PATTERNS — FastAPI + SSE + Next.js App Router streaming is a well-documented community pattern. Next.js 14 vs 15 App Router differences may affect SSE consumer implementation; verify target version.

### Phase 4: Shadow Mode

**Rationale:** Shadow mode reuses the RAG retriever and HITL mechanism from Phases 1-3. It is a branch of the same graph, not a new system. Adding it after Author mode is proven means the shared infrastructure is already validated.

**Delivers:** Shadow branch (`shadow_analyze` + `shadow_annotate` nodes); side-by-side annotated original + corrected version output; same HITL approve/reject loop as Author mode.

**Addresses:** Shadow mode style review (differentiator #2 in FEATURES.md).

**Avoids:** Two separate graphs anti-pattern (ARCHITECTURE.md — one graph with conditional edges); duplicate ChromaDB calls (shared `rag_retriever` node already exists).

**Research flag:** STANDARD PATTERNS — Shadow branch reuses infrastructure already tested in Phases 1-3. LLM prompt design for annotation is the only novel element.

### Phase 5: YouTube Pipeline and Social Media Repurposing

**Rationale:** These features extend the value of an article that already exists. They are distribution-layer features, not core writing features. Both depend on the Author mode pipeline being stable (they feed into the same Markdown output). Ship the foundation, validate KPIs 1-4, then add the distribution layer.

**Delivers:** YouTube transcript → article pipeline (`youtube_extractor` node, captions only); social media repurposing (4 platform variants: Facebook, LinkedIn, Instagram, X) with enforced character limits and post-generation validation.

**Addresses:** YouTube → article pipeline (FEATURES.md Phase 2 recommendation); social media repurposing (FEATURES.md Phase 2 recommendation).

**Avoids:** `youtube-transcript-api` silent failures (Pitfall #7 — multi-language fallbacks, retry with backoff, explicit user-facing error message); social media character limit violations (Pitfall #9 — post-generation validation, regenerate if exceeded, never truncate).

**Research flag:** NEEDS RESEARCH — `youtube-transcript-api` version stability and current YouTube endpoint compatibility need verification at implementation time (breaks 2-3x per year).

### Phase Ordering Rationale

- Phase 1 before all else: RAG corpus quality cannot be validated retroactively; discovering it at Phase 3 means rework across all generation nodes.
- Phase 2 before frontend: Debugging HITL pause/resume through SSE is exponentially harder than through direct Python calls. Prove the graph works first.
- Phase 3 after Author mode: The frontend is a pure SSE consumer. It should not be built until the API contract (event types, thread ID flow, resume endpoint) is stable.
- Phase 4 after Phase 3: Shadow mode reuses everything from Phases 1-3. Adding it earlier would mean testing against unstable infrastructure.
- Phase 5 last: Distribution features. Not on the KPI critical path for MVP validation.

### Research Flags Summary

Needs deeper research during planning:
- **Phase 1:** LangGraph `SqliteSaver` import path (changed between 0.1 and 0.2); `interrupt_before` exact API contract — use Context7 `/langgraph` before implementation.
- **Phase 2:** Exa API Polish-language query parameters; `astream_events` `version="v2"` confirmation; LangGraph context budget approach for long research cycles.
- **Phase 5:** `youtube-transcript-api` current version compatibility and YouTube endpoint stability at implementation time.

Standard patterns (skip or minimize research):
- **Phase 3:** FastAPI + sse-starlette + Next.js App Router streaming is thoroughly documented community pattern.
- **Phase 4:** Shadow branch reuses all infrastructure from earlier phases; only LLM prompt design is novel.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | LOW-MEDIUM | Architectural choices (LangGraph, ChromaDB, Exa, FastAPI+SSE) are HIGH confidence. Specific version numbers are LOW — no live PyPI/npm access during research. All versions must be verified before pinning. |
| Features | MEDIUM-HIGH | Table stakes based on training data (Jasper, Writesonic, Copy.ai patterns). Differentiators are HIGH — derived directly from PROJECT.md requirements, which are internally validated. Anti-features are HIGH — clear scope boundaries from PROJECT.md. |
| Architecture | MEDIUM | Component boundaries and patterns (single graph, dual-branch, shared RAG node, SqliteSaver) are HIGH confidence. Specific LangGraph API import paths and `interrupt_before` exact behavior are MEDIUM — LangGraph 0.1→0.2 had breaking changes; verify with Context7 before implementation. |
| Pitfalls | MEDIUM | Patterns are well-established from LangGraph community issues and RAG system experience. Specific failure modes (HITL resume, streaming deduplication) are documented community problems. |

**Overall confidence:** MEDIUM

### Gaps to Address

- **All version numbers:** Must be verified against live PyPI and npm before pinning. Use the verification checklist in STACK.md. Critical packages: `langgraph`, `chromadb`, `youtube-transcript-api`, `exa-py`, `react-markdown`, `next`.

- **LangGraph import paths:** `SqliteSaver` import path changed between 0.1 and 0.2. `interrupt_before` API contract needs Context7 verification before Phase 1 implementation begins. Do not write Phase 1 code from training data alone.

- **Exa free tier limits:** Current rate limits and query parameters for language filtering need live verification before Phase 2 Researcher node is implemented.

- **ChromaDB 0.4→0.5 migration:** If the pinned version is 0.5.x, verify the collection API has not changed from training data examples. Use `pip index versions chromadb` to find stable version.

- **RAG corpus quality threshold:** The 10-article minimum corpus recommendation is based on general RAG experience, not Bond-specific empirical testing. The actual minimum for KPI4 (style indistinguishable in blind test) needs validation with real corpus loading during Phase 1.

- **Duplicate detection threshold:** Starting threshold of 0.85 cosine similarity is a recommendation, not a validated value. Budget time for threshold tuning in Phase 1 or early Phase 2.

## Sources

### Primary (HIGH confidence)
- `.planning/PROJECT.md` — project requirements, KPIs, out-of-scope list, constraints, target users

### Secondary (MEDIUM confidence)
- Training data (cutoff August 2025): LangGraph 0.2 documentation patterns, StateGraph, SqliteSaver, interrupt_before, astream_events
- Training data: FastAPI SSE + LangGraph streaming community pattern
- Training data: ChromaDB multi-source collection design, standard RAG patterns
- Training data: Exa vs Tavily comparison (documented capabilities, community discussions)
- Training data: Jasper.ai, Writesonic, Copy.ai, Perplexity AI feature landscape (as of August 2025)

### Tertiary (LOW confidence — requires live verification)
- PyPI package versions for: langgraph, langchain-core, langchain-openai, langchain-anthropic, chromadb, exa-py, youtube-transcript-api, fastapi, sse-starlette, sentence-transformers
- npm package versions for: next, react, react-markdown, @uiw/react-md-editor, remark-gfm
- Exa free tier current limits and Polish-language query parameters
- youtube-transcript-api current YouTube endpoint compatibility

---
*Research completed: 2026-02-20*
*Ready for roadmap: yes*
