# Bond — Agent Redakcyjny

## What This Is

Bond to system agentowy (LangGraph/Python) automatyzujący tworzenie wpisów blogowych dla działu marketingu. Agent działa w dwóch trybach: **Author** (generuje artykuł od zera na podstawie tematu i słów kluczowych) oraz **Shadow** (recenzuje i koryguje tekst dostarczony przez użytkownika). Zachowuje spójny styl autora poprzez mechanizm RAG (Dynamic Few-Shot z bazy wektorowej). Interfejs: dedykowany czat w przeglądarce (Custom React/Next.js).

## Core Value

Skrócenie procesu tworzenia gotowego do publikacji draftu z 1–2 dni do maksymalnie 4 godzin — przy zachowaniu stylu nieodróżnialnego od ludzkiego, z human-in-the-loop przed każdą publikacją.

## Requirements

### Validated

(None yet — ship to validate)

### Active

**Tryb Author — Generowanie artykułu:**
- [ ] Użytkownik podaje temat + słowa kluczowe i uruchamia tryb Author
- [ ] Agent wykonuje web research i generuje raport (lista źródeł z linkami i streszczeniami)
- [ ] Użytkownik zatwierdza raport + proponowaną strukturę nagłówków (checkpoint)
- [ ] Agent generuje pełny draft w Markdown zgodny z zasadami SEO (H1/H2/H3, meta-description 150–160 znaków, min. 800 słów)
- [ ] Agent stylizuje draft przy użyciu RAG (wstrzykuje 3–5 fragmentów wzorcowych z bazy wektorowej)
- [ ] Użytkownik może odrzucić draft i podać feedback — Agent regeneruje bez utraty kontekstu sesji
- [ ] Zatwierdzenie draftu zapisuje metadane (temat, data) do Metadata Log

**Tryb Shadow — Korekta stylu:**
- [ ] Użytkownik dostarcza gotowy tekst i uruchamia tryb Shadow
- [ ] Agent analizuje tekst, porównuje ze wzorcami z bazy wektorowej i proponuje konkretne korekty
- [ ] Output: tekst z anotacjami + poprawiona wersja
- [ ] Użytkownik może odrzucić sugestie z powodem — Agent regeneruje alternatywne korekty

**Repurposing (Blog → Social Media):**
- [ ] Użytkownik dostarcza artykuł, Agent generuje warianty dla Facebook, LinkedIn, Instagram, X (Twitter)
- [ ] Output: wyłącznie tekst w Markdown, dostosowany do limitów znaków każdej platformy
- [ ] Brak automatycznej publikacji — treść do ręcznego opublikowania

**YouTube → Artykuł:**
- [ ] Użytkownik podaje link YouTube, Agent pobiera transkrypcję (youtube-transcript-api)
- [ ] Agent generuje artykuł blogowy lub streszczenie w Markdown
- [ ] Działa wyłącznie dla filmów z napisami (ręcznymi lub auto-generowanymi); brak przetwarzania audio/video

**Zarządzanie stylem (RAG):**
- [ ] Baza wektorowa przechowuje fragmenty z dwóch źródeł: własne teksty użytkownika + wskazani zewnętrzni blogerzy, tagowane według źródła
- [ ] Onboarding: użytkownik może zasilić bazę własnymi tekstami lub wskazać URL/teksty zewnętrznych blogerów

**Interfejs użytkownika:**
- [ ] Przełącznik trybu Author/Shadow widoczny w głównym widoku czatu
- [ ] Progress indicator dla długich operacji (research → struktura → pisanie)
- [ ] Edytor Markdown dla wygenerowanego contentu
- [ ] Przycisk "Zatwierdź i Zapisz" zapisujący metadane do Metadata Log

**Kontrola duplikatów:**
- [ ] Metadata Log (SQL lub JSON) rejestruje tematy z datą publikacji
- [ ] Agent weryfikuje unikalność tematu przed research'em (próg X miesięcy — do ustalenia)

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
- **Web Search**: Exa MCP jako kandydat (darmowy, wymaga walidacji jakości vs Tavily) — warstwa abstrakcji wymienna bez zmian w kodzie
- **Czas odpowiedzi**: pełny cykl Research + Write < 5 minut; progress indicator przy przekroczeniu
- **Frontend**: Custom React/Next.js (dedykowany czat w przeglądarce)
- **Bezpieczeństwo**: wyłącznie wskazane źródła (Google Drive) + publiczny internet; brak treningu modeli na danych użytkownika
- **Koszty**: cache'owanie wyników web search w sesji; monitoring zużycia per-artykuł; globalne limity miesięczne (sposób definiowania do ustalenia)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| LangGraph jako orkiestrator | Zarządzanie stanem i przepływem agentów; Python-native | — Pending |
| RAG z dwoma źródłami stylu (własne + zewnętrzni) | Elastyczność przy onboardingu; tagowanie źródła w metadanych wektora | — Pending |
| SEO przez prompt-engineering (nie API) | Brak zewnętrznych zależności w MVP; znana luka (brak danych o wolumenie fraz) | — Pending |
| Brak autopostu w MVP | Human-in-the-loop jako zasada; ryzyko niesprawdzonej treści | — Pending |
| Custom React/Next.js frontend | Pełna kontrola UX; możliwość precyzyjnego odwzorowania wymagań PRD | — Pending |
| Exa MCP dla web search (kandydat) | Darmowy; wymaga walidacji jakości vs Tavily przed decyzją finalną | — Pending |
| Kaskadowy dobór modelu LLM | Mini dla research (koszt), Frontier dla draft (jakość); konfiguracja przez env vars | ✓ Good |

---
*Last updated: 2026-02-20 after initialization*
