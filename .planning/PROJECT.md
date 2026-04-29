# Bond — Agent Redakcyjny

## What This Is

Bond to system agentowy (LangGraph/Python) automatyzujący tworzenie wpisów blogowych dla działu marketingu. Agent działa w dwóch trybach: **Author** (generuje artykuł od zera na podstawie tematu i słów kluczowych) oraz **Shadow** (recenzuje i koryguje tekst dostarczony przez użytkownika). Zachowuje spójny styl autora poprzez mechanizm RAG (Dynamic Few-Shot z bazy wektorowej). Interfejs: dedykowany czat w przeglądarce (Custom React/Next.js).

## Core Value

Skrócenie procesu tworzenia gotowego do publikacji draftu z 1–2 dni do maksymalnie 4 godzin — przy zachowaniu stylu nieodróżnialnego od ludzkiego, z human-in-the-loop przed każdą publikacją.

## Requirements

### Validated

- [x] **v1 signed off historycznie — 2026-04-28.** Author i Shadow przeszły end-to-end walidację po domknięciu detached runtime, recovery sesji oraz responsive remediation.
- [x] **Fresh sign-off candidate po sweepie 2026-04-29.** Follow-up regresyjny po szerokim sweepie E2E został domknięty i ponownie zwalidowany: ręczne edycje Author przeżywają reload i restore z sidebaru w tym samym tabie, `<thinking>` nie trafia już do live draftu ani finalnego renderu, `Pobierz .md` jest potwierdzony realnym downloadem, a upload pliku został przeprowadzony przez hidden `input[type=file]` w Playwright.
- [x] **Post-v1 Exa baseline — 2026-04-28.** Formalna live walidacja Exa dla 4 kuratorowanych polskich case'ów researchowych zakończona powodzeniem; artefakty: `.planning/artifacts/exa-polish-20260428-142434/summary.{md,json}`.
- [x] **Post-v1 threshold calibration — 2026-04-28.** Dodano harness `scripts/calibrate_thresholds.py` + `bond/validation/threshold_calibration.py`, przeanalizowano lokalne `articles.db` / `bond_metadata.db` / Chroma i zapisano artefakty `.planning/artifacts/threshold-calibration-20260428-175144/summary.{md,json}`; defaulty `low_corpus_threshold=10` i `duplicate_threshold=0.85` pozostawiono bez zmian, bo próba nie uzasadnia ich przesunięcia.
- [x] **Post-v1 integrity/session hardening — 2026-04-28.** Dodano `bond/validation/duplicate_metadata_reconciliation.py` + `scripts/reconcile_duplicate_metadata.py`, wyzerowano lokalny drift duplicate metadata (`6` rekordów SQLite vs `6` rekordów Chroma, `missing=0`), rozszerzono `/api/chat/history` o `mode`, utrwalono `mode` w sesjach frontendu, zakończono zwykłe HTTP 4xx/5xx błędem zamiast recovery i poprawiono UX file-ingest dla `chunks_added=0`.
- [x] **Corpus onboarding**: text, file, Google Drive i blog URL działają; corpus pokazuje status i low-corpus warning.
- [x] **Author mode**: topic → research → checkpoint 1 → draft → checkpoint 2 → save metadata działa w UI z pełnym HITL.
- [x] **Shadow mode**: użytkownik widzi anotacje i wersję poprawioną oraz może approve/reject z pętlą regeneracji.
- [x] **Frontend v1**: streaming SSE, progress indicator, edytor Markdown z exportem, corpus panel i lokalna historia sesji w sidebarze są dostępne.
- [x] **URL ingest hardening**: `/api/corpus/ingest/url` waliduje wyłącznie publiczne adresy `http/https`; hosty prywatne, loopback i link-local są odrzucane przed scrapingiem.

### Active Post-v1 Work

- [x] **Internal deployment hardening.** Wszystkie 3 plany są domknięte w kodzie i docs: repo ma gateway auth, backend trusted-proxy enforcement, health/readiness, non-root backend z trwałym cache modeli, kanoniczny runtime Next `standalone` oraz wewnętrzny profil Compose. Shape został zwalidowany live na Compose, włącznie z Author i Shadow przez publiczny frontend. Repo należy traktować jako `internal production ready`.
  - `[x]` `.agents/plans/internal-deployment-hardening-01-security-contract-and-backend-baseline.md` — env contract (`internal_auth_enabled`, `internal_proxy_token`, credentials pod frontend auth), trusted header `X-Bond-Internal-Proxy-Token`, middleware fail-closed z `X-Request-Id`, `/health`, `/health/live`, `/health/ready`, testy kontraktowe backendu
  - `[x]` `.agents/plans/internal-deployment-hardening-02-frontend-gateway-and-auth.md` — centralny gateway `Basic Auth`, same-origin proxy `/api/*` przez `src/app/api/[...path]/route.ts` z trusted headerem, publiczne `/healthz`, walidacja `build`/`lint`/`test-proxy-auth`, kompatybilność z aktualnym Next 15 przez cienki shim `src/middleware.ts` delegujący do `src/proxy.ts`
  - `[x]` `.agents/plans/internal-deployment-hardening-03-deployment-hardening-and-docs.md` — non-root backend `Dockerfile`, trwały cache modeli w `/app/data/.cache`, `HF_HUB_DISABLE_XET=1`, healthchecki + `init: true` w `docker-compose.yml`, `docker-compose.internal.yml` z backendem na loopbackie hosta i siecią `bond-internal`, `frontend/Dockerfile` z kanonicznym `node .next/standalone/server.js`, README z operator flow i lokalnym smoke testem `standalone`
- [x] **E2E regression remediation po sweepie 2026-04-29.** Domknięto tab-local persistence Author, backendowy sanitizer streamu writera, utwardzony flow `Pobierz .md` oraz browser-level upload validation; rewalidacja przeszła przez `uv run pytest`, frontend `lint/build`, `playwright_detached_runtime_journey.py` i `playwright_post_signoff_regressions.py`.
- [ ] **Threshold/telemetry follow-up pozostaje odroczony.** Większa próbka opublikowanych tematów i telemetryczny feedback wracają dopiero wtedy, gdy priorytet produktu świadomie wróci do tego tematu i nie będzie konkurował z pilniejszą remediacją E2E.

### Active

- [ ] **V2 — Repurposing**: blog → Facebook / LinkedIn / Instagram / X.
- [ ] **V2 — YouTube → Artykuł**: generowanie artykułu lub streszczenia z napisów.

### Out of Scope

- Integracja z API SEO (Ahrefs, Semrush, Surfer, Google Trends) — SEO przez prompt-engineering w MVP
- Fine-tuning modeli — wyłącznie In-Context Learning (RAG + Few-Shot)
- Przetwarzanie plików audio/video (Whisper API) — tylko tekst/napisy
- Autoposting do CMS (WordPress) lub Social Media — rozważyć w fazie 2
- Generowanie obrazów / sugestii wizualnych — rozważyć w fazie 2
- Tryb wieloużytkownikowy i zarządzanie uprawnieniami

## Context

- Użytkownicy: pracownicy działu administracji/marketingu, poziom niespecjalistyczny — interfejs musi być intuicyjny
- Zatwierdzanie treści: CEO lub Kierownik biura (human-in-the-loop przed każdą publikacją)
- Filozofia: Agent wykonuje ciężką pracę (research, struktura, draft) — człowiek podejmuje decyzje
- Problemy baseline: tworzenie artykułu zajmuje 1–2 dni; trudność z "czystą kartką"; brak kontroli duplikatów tematów
- KPI sukcesu: draft w <4h (KPI1), >50% acceptance rate bez przepisywania (KPI2), zero duplikatów tematów (KPI3), styl nieodróżnialny od ludzkiego w ślepych testach (KPI4)

## Constraints

- **Tech Stack**: LangGraph (Python 3.11+), Pydantic, architektura modułowa (nodes)
- **LLM**: Kaskadowe — modele "Mini" do research/analizy, modele "Frontier" do final draft; konfiguracja przez zmienne środowiskowe
- **Web Search**: Exa MCP zwalidowany baseline'owo dla polskich zapytań researchowych; warstwa abstrakcji pozostaje wymienna bez zmian w kodzie
- **Czas odpowiedzi**: pełny cykl Research + Write < 5 minut; progress indicator przy przekroczeniu
- **Frontend**: Custom React/Next.js (dedykowany czat w przeglądarce)
- **Bezpieczeństwo**: wyłącznie wskazane źródła (Google Drive) + publiczny internet; brak treningu modeli na danych użytkownika
- **Koszty**: cache'owanie wyników web search w sesji; monitoring zużycia per-artykuł; globalne limity miesięczne (sposób definiowania do ustalenia)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| LangGraph jako orkiestrator | Zarządzanie stanem i przepływem agentów; Python-native | ✓ Validated in v1 |
| RAG z dwoma źródłami stylu (własne + zewnętrzni) | Elastyczność przy onboardingu; tagowanie źródła w metadanych wektora | ✓ Implemented in v1 |
| SEO przez prompt-engineering (nie API) | Brak zewnętrznych zależności w MVP; znana luka (brak danych o wolumenie fraz) | ✓ Implemented in v1 |
| Brak autopostu w MVP | Human-in-the-loop jako zasada; ryzyko niesprawdzonej treści | ✓ Maintained in v1 |
| Custom React/Next.js frontend | Pełna kontrola UX; możliwość precyzyjnego odwzorowania wymagań PRD | ✓ Validated in v1 |
| Exa MCP dla web search | Darmowy; baseline live dla polskich zapytań zamknięty 2026-04-28, ewentualne porównanie vs Tavily pozostaje opcjonalne | ✓ Baseline validated |
| Kaskadowy dobór modelu LLM | Mini dla research (koszt), Frontier dla draft (jakość); konfiguracja przez env vars | ✓ Good |

---
*Last updated: 2026-04-29 after closing and revalidating the remaining post-sign-off regressions from the comprehensive E2E sweep*
