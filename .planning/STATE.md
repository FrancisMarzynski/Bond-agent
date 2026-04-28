# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-20)

**Core value:** Skrócenie procesu tworzenia gotowego do publikacji draftu z 1–2 dni do maksymalnie 4 godzin — przy zachowaniu stylu nieodróżnialnego od ludzkiego, z human-in-the-loop przed każdą publikacją.
**Current focus:** Phase 4 — Shadow Mode (1 frontend integration gap remains)

## Current Position

Phase: 4 of 4 (Shadow Mode) — MOSTLY COMPLETE; 1 gap
Last activity: 2026-04-23 — Phase 3 E2E hardening complete (SSE reconnect, safety caps, ErrorBoundary); Shadow mode backend and UI built; frontend HITL integration gap identified
Status: All backend complete; Author mode fully working end-to-end; Shadow mode backend + UI built but the HITL loop is not connected in the frontend

Progress: [████████░░] ~90% (Shadow HITL frontend wiring remains)

**Known Gap — Shadow mode HITL frontend (SHAD-05, SHAD-06):**

When `shadow_checkpoint` fires `interrupt()`, the backend packages `annotations` and `shadow_corrected_text` into the `hitl_pause` SSE payload. Three things are broken in the frontend:

1. `HitlPauseSchema` (Zod, `chatStore.ts`) does not declare `annotations`, `shadow_corrected_text`, or `iteration_count` fields — Zod strips them, so `shadowStore` is never populated
2. The `hitl_pause` handler in `useStream.ts` does not call `useShadowStore.getState().setAnnotations()` / `setShadowCorrectedText()` for the shadow checkpoint case
3. The `/shadow` route renders only `ShadowPanel`; `ShadowPanel` has no approve/reject buttons — users cannot resume the graph

**Fix** (estimated 1–2 hours):
- Extend `HitlPauseSchema` in `chatStore.ts`: add `annotations?: Annotation[]`, `shadow_corrected_text?: string`, `iteration_count?: number`
- In `useStream.ts` `hitl_pause` handler: when `checkpoint_id === "shadow_checkpoint"`, call `useShadowStore.getState().setAnnotations()` and `setShadowCorrectedText()`
- Add approve/reject buttons to `ShadowPanel` (visible when `hitlPause?.checkpoint_id === "shadow_checkpoint"`), wired to `resumeStream(threadId, "approve"/"reject", feedback)`

## Performance Metrics

**Velocity:**
- Total tasks/sub-tasks completed: ~70+ (across all phases)
- Phase 3 alone: 51 documented sub-tasks

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-rag-corpus-onboarding | 3 | 30 min | 10 min |
| 02-author-mode-backend | 4 | 10 min | 3.3 min |
| 03-streaming-api-and-frontend | 5 + 46 sub-tasks | ~2 months | — |
| 04-shadow-mode | Built within Phase 3 + 1 gap | — | — |

## Accumulated Context

### Key Architectural Decisions

**Phase 1–2 (foundation):**
- Singleton ChromaDB PersistentClient — avoids reloading 420MB embedding model per request
- SQLite for article log (not ChromaDB metadata) — efficient article-level counting
- 1875 chars chunk size (~500 tokens for Polish text) with 10% overlap
- Two separate SQLite files: bond_checkpoints.db (LangGraph) + bond_metadata.db (metadata log) — avoids schema conflicts
- Two-pass retrieval: own-before-external weighting; author style always prioritised
- check_same_thread=False on SQLite connections — required for async execution across thread boundaries
- Schema-on-connect pattern (_get_conn runs CREATE TABLE IF NOT EXISTS on every open) — zero-config migration

**Phase 2 (Author backend):**
- Stub node replacement via _node_registry dict — graph wiring finalized in Plan 01; later plans replace stub bodies without touching edge logic
- interrupt() payload shape locked for cp1, cp2, duplicate_check
- RAG exemplar injection as system prompt prefix (soft prompt technique)
- Low-corpus gate: interrupt() warning when < 10 articles; user confirms True/False
- Writer auto-retry on cp2_feedback only on attempt 0 — avoids compounding revision errors
- save_metadata_node generates published_date at call time — ensures accurate timestamp

**Phase 3 (Streaming API + Frontend):**
- FastAPI lifespan compiles LangGraph graph once with AsyncSqliteSaver — graph lives on `app.state.graph`
- Per-thread asyncio.Lock (_resume_locks) prevents race on rapid HITL clicks
- _RECURSION_LIMIT=50 as absolute backstop behind per-node hard caps
- Safety cap guards in _route_after_cp1/cp2: check cp_iterations >= HARD_CAP before routing
- SSE event flow: thread_id → stage → node_start/end → token → [hitl_pause | done/error]
- Post-stream state inspection: _emit_post_stream_events checks state_snapshot.next to decide hitl_pause vs terminal events
- SSE reconnect: MAX_RETRIES=5, exponential backoff (1s→2s→4s→8s→16s) + jitter, Last-Event-ID header sent
- Zustand chatStore holds AbortController per stream — isolated, no module-level global
- FlashRank reranker after two-pass ChromaDB retrieval
- Semantic cache cross-session (ChromaDB embeddings for Exa results)
- Structure node promoted to DRAFT_MODEL (gpt-4o) for better H1/H2/H3 quality

**Phase 4 (Shadow Mode):**
- BondState = AuthorState (alias) — backward-compat across all Phase 2 nodes
- Shadow branch: shadow_analyze → shadow_annotate → shadow_checkpoint (with HITL loop back to shadow_annotate on reject)
- shadow_annotate uses with_structured_output(AnnotationResult) + three-pass index validation (accept / auto-correct / discard)
- _apply_annotations applies in reverse index order — preserves correct offsets after length-changing replacements
- shadow_checkpoint hard cap at 3 iterations (lower than cp1/cp2 because structured LLM calls on full user text are expensive)
- SHAD-06 frontend HITL wiring is the last remaining gap (see above)

### Pending Todos

- [ ] Fix Shadow mode HITL frontend gap (SHAD-05, SHAD-06) — see Known Gap section above

### Blockers/Concerns

- Shadow mode is functionally broken end-to-end for users until the HITL gap is fixed
- EXA_API_KEY live verification with Polish-language queries still pending from Phase 2 note (may already work; just not formally verified)
- RAG corpus quality thresholds (10 articles, 0.85 similarity) are recommendations, not empirically validated values

## Session Continuity

Last session: 2026-04-23
Stopped at: Phase 3 E2E hardening complete; Shadow mode built except for frontend HITL wiring
Resume file: None
Next task: Fix Shadow HITL frontend gap (extend HitlPauseSchema, wire setAnnotations in hitl_pause handler, add approve/reject to ShadowPanel)
