# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-28)

**Core value:** Skrócenie procesu tworzenia gotowego do publikacji draftu z 1–2 dni do maksymalnie 4 godzin — przy zachowaniu stylu nieodróżnialnego od ludzkiego, z human-in-the-loop przed każdą publikacją.
**Current focus:** v1 formalnie signed off 2026-04-28 po domknięciu Shadow HITL, detached runtime, recovery sesji, responsive remediation, potwierdzeniu istniejącej ochrony SSRF dla URL ingest, formalnej live walidacji Exa dla kuratorowanych polskich zapytań researchowych oraz kalibracji progów `low_corpus_threshold` / `duplicate_threshold` na lokalnych danych repo. Najbliższy follow-up post-v1 to wyrównanie driftu SQLite↔Chroma wykrytego w duplicate metadata.

## Current Position

Phase: Post-Phase 4 — v1 SIGNED OFF
Last activity: 2026-04-28 — dodano `scripts/calibrate_thresholds.py` + `bond/validation/threshold_calibration.py`, wygenerowano artefakty `.planning/artifacts/threshold-calibration-20260428-175144/summary.{md,json}`, ujednolicono writer low-corpus gate do `settings.low_corpus_threshold` + `articles.db` article_count, potwierdzono na lokalnych danych pozostawienie defaultów `low_corpus_threshold=10` i `duplicate_threshold=0.85`, wykryto drift `metadata_log` SQLite (`4`) vs Chroma duplicate collection (`3`) i domknięto targeted unit suite dla writer/calibration
Status: v1 formalnie signed off; brak otwartych blockerów dla Author, Shadow, recovery/HITL, layoutów mobile/tablet ani hardeningu `/api/corpus/ingest/url`

Progress: [██████████] 100% dla v1 + transport hardening / REC-01/02/03 + responsive remediation

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
13. **Recovery polling do trwałego stanu** — reload recovery dla dłuższych sesji nie kończy się już po ~30 s; zarówno bootstrap, jak i same-tab recovery czekają na `paused` / `completed` / `error`.
14. **Responsive app shell** — sidebar poniżej `lg` działa jako drawer z triggerem w nagłówku; desktop zachowuje persistent sidebar bez regresji.
15. **Author layout reflow** — główny workspace pozostaje stacked do `lg`; chat, checkpoint i toolbar edytora nie wymagają już poziomego scrolla na `375x812` i `768x1024`.
16. **Shadow layout reflow** — poniżej `lg` adnotacje są promowane do pełnej górnej sekcji, a panele `Tekst oryginalny` / `Wersja poprawiona` stackują się pionowo bez ścisku szerokości.
17. **URL ingest SSRF hardening już obecny w kodzie** — `/api/corpus/ingest/url` waliduje publiczne hosty przed scrapingiem, a testy pokrywają loopback, localhost, link-local, schematy inne niż HTTP(S) oraz skipowanie niebezpiecznych URL-i odkrytych przez sitemap.
18. **Token-aware research carry-through** — `structure_node` i fresh-draft path w `writer_node` nie tną już ślepo `research_report` po znakach; pełny raport przechodzi bez zmian, gdy mieści się w budżecie modelu, a przy ciasnym budżecie prompt degraduje się sekcyjnie przez `research_data` (fakty/statystyki najpierw, potem redukcja źródeł).
19. **Threshold calibration harness** — lokalny skrypt `scripts/calibrate_thresholds.py` analizuje `articles.db`, `bond_metadata.db` i Chroma, zapisuje artefakty pod `.planning/artifacts/threshold-calibration-20260428-175144/` i konserwatywnie utrzymuje defaulty `10` / `0.85`, bo obecna próba nie uzasadnia ich ruszania.

## Browser Validation Notes

Walidacja transport / recovery wykonana 2026-04-28 na:

- frontend: `http://localhost:3000`
- backend: `http://localhost:8000`
- harness: `python3 scripts/playwright_detached_runtime_journey.py`
- narzędzie: Python Playwright (headless Chromium)

Potwierdzone zachowania:

1. Shadow: dokładnie jeden `POST /api/chat/stream`, dokładnie jeden `POST /api/chat/resume`, reload na `shadow_checkpoint` odtwarza adnotacje/poprawioną wersję/akcje HITL i kończy sesję bez replayu `POST /api/chat/resume`.
2. Shadow final history: `session_status="completed"`, `stage="done"`, `can_resume=false`.
3. Author: dokładnie jeden `POST /api/chat/stream`, dokładnie dwa `POST /api/chat/resume` (cp1 approve + cp2 save) i zero dodatkowych replayów po reloadzie w trakcie committed stream/resume.
4. Author reload recovery przez `/history` dochodzi do `checkpoint_1`, potem do `checkpoint_2`, a finalnie do `completed`.
5. Odpowiedzi `/api/chat/stream` i `/api/chat/resume` wystawiają `X-Bond-Thread-Id`, więc recovery działa także wtedy, gdy body urwie się przed pierwszym eventem `thread_id`.
6. Dłuższe sesje Author po reloadzie nie gubią checkpointu przez zbyt krótki polling — recovery trwa do trwałego stanu `paused` / `completed` / `error`.

Walidacja responsive wykonana 2026-04-28 na:

- frontend: `http://localhost:3000`
- backend: `http://localhost:8000`
- narzędzie: headless Chromium przez lokalny Python Playwright

Potwierdzone zachowania:

1. `375x812`: sidebar jest ukryty domyślnie, dostępny przez trigger w nagłówku, Author pozostaje stacked i nie generuje poziomego overflow.
2. `768x1024`: Author pozostaje stacked; Shadow checkpoint przenosi `Adnotacje` nad treść i stackuje pionowo `Tekst oryginalny` / `Wersja poprawiona`.
3. `1440x900`: desktop zachowuje układ side-by-side bez widocznej regresji.
4. Dla wszystkich powyższych viewportów: `overflow_px = 0`.

Artefakty lokalne:

- `/tmp/bond-playwright-detached-runtime-20260428-122040/summary.json`
- `/tmp/bond-playwright-detached-runtime-20260428-122040/shadow-01-checkpoint.png`
- `/tmp/bond-playwright-detached-runtime-20260428-122040/shadow-02-restored.png`
- `/tmp/bond-playwright-detached-runtime-20260428-122040/shadow-03-final.png`
- `/tmp/bond-playwright-detached-runtime-20260428-122040/author-01-checkpoint-1.png`
- `/tmp/bond-playwright-detached-runtime-20260428-122040/author-02-checkpoint-2.png`
- `/tmp/bond-playwright-detached-runtime-20260428-122040/author-03-final.png`
- `e2e-screenshots/responsive/01-home-mobile.png`
- `e2e-screenshots/responsive/02-home-tablet.png`
- `e2e-screenshots/responsive/03-home-desktop.png`
- `e2e-screenshots/responsive/04-home-mobile-drawer.png`
- `e2e-screenshots/responsive/05-shadow-mobile.png`
- `e2e-screenshots/responsive/06-shadow-tablet.png`

## Exa Validation Notes

Walidacja live Exa wykonana 2026-04-28 na:

- harness: `uv run python scripts/validate_exa_polish.py`
- artifact JSON: `.planning/artifacts/exa-polish-20260428-142434/summary.json`
- artifact Markdown: `.planning/artifacts/exa-polish-20260428-142434/summary.md`

Potwierdzone zachowania:

1. Exa MCP odpowiada bez osobnej zmiennej `EXA_API_KEY`; aplikacja łączy się bezpośrednio z `https://mcp.exa.ai/mcp`.
2. Każdy z 4 kuratorowanych case'ów (AI marketing B2B, BIM, XR, cyfrowe bliźniaki) zwrócił status `pass`.
3. Każde z 3 zapytań per case zwróciło 5 parsowalnych wyników (`overview`, `stats`, `case-study`), mimo że payload MCP pakuje je do pojedynczego bloku tekstowego.
4. Deduplikowane wyniki na case: 12–15 unikalnych źródeł, 11–15 unikalnych domen, 8–11 domen `.pl`, 4–11 źródeł z datą publikacji od 2024 roku.

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
| 04-shadow-mode | Built within Phase 3, domknięte późniejszymi remediacjami | — | — |

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

- Brak otwartych zadań blokujących v1 sign-off.

### Post-v1 Candidates

- Wyrównać drift `metadata_log` SQLite ↔ Chroma duplicate collection i dodać/backfillować brakujące embeddingi tematów.
- Zebrać większą próbę realnych opublikowanych tematów przed ewentualnym ponownym ruszaniem defaultów `low_corpus_threshold` / `duplicate_threshold`.

### Blockers/Concerns

- Kalibracja progów została wykonana 2026-04-28, ale confidence pozostaje ograniczone: lokalny corpus ma tylko 12 artykułów, a kolekcja duplicate w Chroma tylko 3 tematy.
- Lokalnie wykryto drift `metadata_log` SQLite (`4` rekordy) vs Chroma duplicate collection (`3` embeddingi), co może zaniżać coverage duplicate check dla starszych tematów.
- Baseline Exa jest zwalidowany tylko na 4 kuratorowanych case'ach; brak jeszcze porównania A/B vs Tavily i brak telemetrycznego feedbacku z produkcyjnych tematów użytkowników

## Session Continuity

Last session: 2026-04-28
Stopped at: domknięto lokalną kalibrację progów (`scripts/calibrate_thresholds.py` + artefakty w `.planning/artifacts/threshold-calibration-20260428-175144/`), pozostawiono defaulty `low_corpus_threshold=10` i `duplicate_threshold=0.85`, a jako follow-up wykryto drift SQLite↔Chroma w duplicate metadata
Resume file: None
Next task: zbadać i naprawić drift `metadata_log` SQLite ↔ Chroma duplicate collection, tak aby duplicate check miał pełny coverage opublikowanych tematów
