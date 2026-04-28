# Bond — Agent Redakcyjny

## What This Is

Bond to system agentowy (LangGraph/Python) automatyzujący tworzenie wpisów blogowych dla działu marketingu. Agent działa w dwóch trybach: **Author** (generuje artykuł od zera na podstawie tematu i słów kluczowych) oraz **Shadow** (recenzuje i koryguje tekst dostarczony przez użytkownika). Zachowuje spójny styl autora poprzez mechanizm RAG (Dynamic Few-Shot z bazy wektorowej). Interfejs: dedykowany czat w przeglądarce (Custom React/Next.js).

## Core Value

Skrócenie procesu tworzenia gotowego do publikacji draftu z 1–2 dni do maksymalnie 4 godzin — przy zachowaniu stylu nieodróżnialnego od ludzkiego, z human-in-the-loop przed każdą publikacją.

## Requirements

### Validated

- [x] **v1 signed off — 2026-04-28.** Author i Shadow przeszły end-to-end walidację po domknięciu detached runtime, recovery sesji oraz responsive remediation.
- [x] **Post-v1 Exa baseline — 2026-04-28.** Formalna live walidacja Exa dla 4 kuratorowanych polskich case'ów researchowych zakończona powodzeniem; artefakty: `.planning/artifacts/exa-polish-20260428-142434/summary.{md,json}`.
- [x] **Corpus onboarding**: text, file, Google Drive i blog URL działają; corpus pokazuje status i low-corpus warning.
- [x] **Author mode**: topic → research → checkpoint 1 → draft → checkpoint 2 → save metadata działa w UI z pełnym HITL.
- [x] **Shadow mode**: użytkownik widzi anotacje i wersję poprawioną oraz może approve/reject z pętlą regeneracji.
- [x] **Frontend v1**: streaming SSE, progress indicator, edytor Markdown z exportem, corpus panel i lokalna historia sesji w sidebarze są dostępne.
- [x] **URL ingest hardening**: `/api/corpus/ingest/url` waliduje wyłącznie publiczne adresy `http/https`; hosty prywatne, loopback i link-local są odrzucane przed scrapingiem.

### Active

- [ ] **Post-v1 calibration**: skalibrować progi `low_corpus_threshold` i duplicate similarity na realnych danych.
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
*Last updated: 2026-04-28 after Exa baseline validation and docs sync*
