# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-20)

**Core value:** Skrócenie procesu tworzenia gotowego do publikacji draftu z 1–2 dni do maksymalnie 4 godzin — przy zachowaniu stylu nieodróżnialnego od ludzkiego, z human-in-the-loop przed każdą publikacją.
**Current focus:** Transport hardening kontynuowany — detached runtime zaimplementowany, bootstrap sesji scentralizowany, Shadow stages wyrównane; pełna walidacja browser-journey Author/Shadow do wykonania

## Current Position

Phase: 4 of 4 (Shadow Mode) — COMPLETE + transport hardening (in progress)
Last activity: 2026-04-28 — Zaimplementowano detached command runtime; graph nie jest już przerywany przez disconnect klienta SSE; bootstrap sesji scentralizowany w SessionProvider; Shadow stages wyrównane w historii i UI; `X-Bond-Thread-Id` header dodany jako fallback recovery
Status: Warstwa transportu ulepszona architekturalnie; pełne browser-journey dla Author i Shadow do wykonania po wdrożeniu

Progress: [█████████▓] ~97% dla aktualnego zakresu v1 — transport hardening kompletny, walidacja E2E jeszcze nie przebiegnięta

**Niedawno domknięte:**

1. `thread_id` trafia do `initial_state`, więc downstream nodes nie zakładają już pola, którego backend nie ustawiał.
2. `GET /api/chat/history/{thread_id}` zwraca jawne pola recovery: `session_status`, `pending_node`, `can_resume`, `active_command`, `error_message`.
3. Frontend nie replayuje już committed `POST` po zerwaniu SSE; po otrzymaniu `Response` odzyskuje stan z `/history`.
4. Shadow checkpoint i recovery sesji poprawnie hydratują `annotations`, `shadowCorrectedText` i `draft`.
5. `low_corpus` używa tego samego kontraktu `approve_reject` co reszta checkpointów i ma własny panel ostrzeżenia w UI.
6. Parser SSE w przeglądarce normalizuje `CRLF`, więc eventy z realnego `fetch(...).body` nie znikają już przez rozjazd `\r\n\r\n` vs `\n\n`.
7. Parser nested payloadów nie zamienia już tokenów takich jak `"144"` lub `"1"` na liczby, więc cyfry w strumieniu nie są gubione.
8. `ShadowPanel` zapisuje `thread_id` przez `persistThreadId`, więc reload strony i recovery z `sessionStorage` działają tak samo jak w Trybie Autora.
9. **Detached command runtime (`bond/api/runtime.py`)** — graph execution odłączony od lifecycle SSE response; disconnect klienta nie przerywa już wykonania grafu.
10. **Bootstrap sesji scentralizowany** — `useSession()` nie wywołuje już `/history` przy każdym mount; jeden bootstrap przez `useSessionBootstrap` w `SessionProvider`.
11. **Shadow stages wyrównane** — `/history` zwraca `shadow_analysis`/`shadow_annotation` zamiast `idle`; `Stage` type i `StageProgress` obsługują nowe wartości.
12. **`X-Bond-Thread-Id` header** — thread ID dostępny z headera response natychmiast po `fetch()`, zanim body zostanie sparsowane.

## Browser Validation Notes

Walidacja wykonana 2026-04-28 na:

- frontend: `http://localhost:3000/shadow`
- backend: `http://127.0.0.1:8000`
- narzędzie: Python Playwright (headless Chromium)

Potwierdzone zachowania:

1. Shadow wysyła dokładnie jeden `POST /api/chat/stream`.
2. Po commitcie `thread_id` i sztucznym rozłączeniu checkpoint wraca bez replayu `POST /api/chat/stream`.
3. Reload strony na `shadow_checkpoint` odtwarza panel z `sessionStorage` i `/api/chat/history/{thread_id}`.
4. `resume=approve` wysyła dokładnie jeden `POST /api/chat/resume`.
5. Po rozłączeniu po `resume` sesja kończy się poprawnie bez replayu `POST /api/chat/resume`.
6. Finalna historia sesji zwraca `session_status="completed"`, `stage="done"`, `can_resume=false`.

Artefakty lokalne:

- `/tmp/bond-playwright/03-checkpoint.png`
- `/tmp/bond-playwright/04-reloaded-checkpoint.png`
- `/tmp/bond-playwright/05-after-resume-disconnect.png`
- `/tmp/bond-playwright/06-final.png`

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
- Low-corpus gate: standardowy `interrupt({"checkpoint": "low_corpus", "type": "approve_reject", ...})`
- Writer auto-retry on cp2_feedback only on attempt 0 — avoids compounding revision errors
- save_metadata_node generates published_date at call time — ensures accurate timestamp

**Phase 3 (Streaming API + Frontend):**
- FastAPI lifespan compiles LangGraph graph once with AsyncSqliteSaver — graph lives on `app.state.graph`
- Per-thread asyncio.Lock (_resume_locks) prevents race on rapid HITL clicks
- _RECURSION_LIMIT=50 as absolute backstop behind per-node hard caps
- Safety cap guards in _route_after_cp1/cp2: check cp_iterations >= HARD_CAP before routing
- SSE event flow: thread_id → stage → node_start/end → token → [hitl_pause | done/error]
- Post-stream state inspection: _emit_post_stream_events checks state_snapshot.next to decide hitl_pause vs terminal events
- SSE reconnect: retry tylko przed uzyskaniem `Response`; po committed disconnect recovery idzie przez `GET /api/chat/history/{thread_id}`
- Historia sesji ma jawny kontrakt recovery: `session_status`, `pending_node`, `can_resume`
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
- `ShadowPanel` ma pełny approve/reject loop i blokadę duplikatów podczas recovery po committed `resume`

### Pending Todos

- [ ] Wykonać pełny browser journey Shadow i Author po implementacji detached runtime (weryfikacja end-to-end)
- [ ] Naprawić layout mobile/tablet z raportu E2E
- [ ] Dodać ochronę SSRF dla `/api/corpus/ingest/url`

### Blockers/Concerns

- Browser E2E journey po detached runtime nie został jeszcze przeprowadzony — wymagany przed finalną walidacją REC-01/02/03
- EXA_API_KEY live verification with Polish-language queries nadal nie ma osobnej formalnej walidacji
- RAG corpus quality thresholds (10 articles, 0.85 similarity) są rekomendacjami, nie wynikami empirycznej kalibracji

## Session Continuity

Last session: 2026-04-28
Stopped at: Streaming/HITL remediation complete; root cause potwierdzony w Playwright; docs i handoff dla niezależnej walidacji zaktualizowane
Resume file: None
Next task: Niezależna walidacja drugiego agenta + osobny Playwright pass dla Author, potem mobile/tablet layout remediation lub SSRF hardening dla URL ingest
