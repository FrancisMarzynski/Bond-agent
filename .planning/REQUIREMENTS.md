# Requirements: Bond — Agent Redakcyjny

**Defined:** 2026-02-20
**Core Value:** Skrócenie procesu tworzenia gotowego do publikacji draftu z 1–2 dni do maksymalnie 4 godzin — przy zachowaniu stylu nieodróżnialnego od ludzkiego, z human-in-the-loop przed każdą publikacją.
**Status:** v1 signed off historycznie na 2026-04-28; kompleksowy sweep E2E z 2026-04-29 utrzymał wszystkie 39 wymagań v1 jako zaimplementowane, ale otworzył follow-up regresyjny w UX/stanie (manual persistence Author, leak `<thinking>`, końcowa walidacja download/upload harness), więc bieżącego brancha nie należy traktować jako świeżo rewalidowanego sign-off candidate.

---

## v1 Requirements

### Corpus Ingestion (Onboarding RAG)

- [x] **CORP-01**: Użytkownik może dodać artykuł do bazy stylów przez wklejenie tekstu bezpośrednio w interfejsie
- [x] **CORP-02**: Użytkownik może dodać artykuły do bazy stylów przez upload pliku (PDF, DOCX, TXT)
- [x] **CORP-03**: Użytkownik może zasilić bazę stylów ze wskazanego folderu Google Drive
- [x] **CORP-04**: Użytkownik może zasilić bazę stylów podając URL bloga (agent scrape'uje wpisy)
- [x] **CORP-05**: Użytkownik może oznaczać źródło jako "własne teksty" lub "zewnętrzny bloger (wzorzec)"
- [x] **CORP-06**: Użytkownik widzi liczbę artykułów i fragmentów w bazie stylów (status corpus)
- [x] **CORP-07**: System informuje użytkownika gdy corpus zawiera mniej niż 10 artykułów (niska jakość stylizacji)

### Author Mode — Generowanie Artykułu

- [x] **AUTH-01**: Użytkownik może uruchomić tryb Author podając temat i słowa kluczowe
- [x] **AUTH-02**: Agent wykonuje web research (Exa) i generuje raport: lista źródeł z tytułami, linkami i streszczeniami
- [x] **AUTH-03**: Agent proponuje strukturę nagłówków (H1/H2/H3) na podstawie researchu
- [x] **AUTH-04**: Użytkownik zatwierdza lub odrzuca raport i strukturę nagłówków (Checkpoint 1)
- [x] **AUTH-05**: Po zatwierdzeniu Checkpoint 1, agent generuje pełny draft z zasadami SEO: słowo kluczowe w H1 i pierwszym akapicie, poprawna hierarchia nagłówków, meta-description 150–160 znaków, minimum 800 słów
- [x] **AUTH-06**: Agent stylizuje draft wstrzykując 3–5 fragmentów wzorcowych z bazy wektorowej (RAG Few-Shot)
- [x] **AUTH-07**: Użytkownik zatwierdza lub odrzuca stylizowany draft (Checkpoint 2)
- [x] **AUTH-08**: Użytkownik może podać feedback przy odrzuceniu — agent regeneruje draft bez utraty kontekstu sesji (max 3 iteracje)
- [x] **AUTH-09**: Po zatwierdzeniu, system zapisuje metadane artykułu do Metadata Log (temat, data, tryb)
- [x] **AUTH-10**: Wyniki web search są cache'owane w sesji — powtórne zapytanie o ten sam temat nie wywołuje ponownego API call
- [x] **AUTH-11**: Modele LLM są konfigurowane przez zmienne środowiskowe (RESEARCH_MODEL dla research/analizy, DRAFT_MODEL dla final draft)

### Shadow Mode — Korekta Stylu

- [x] **SHAD-01**: Użytkownik może uruchomić tryb Shadow wklejając gotowy tekst do analizy
- [x] **SHAD-02**: Agent porównuje dostarczony tekst ze wzorcami stylistycznymi z bazy wektorowej
- [x] **SHAD-03**: Agent generuje tekst z anotacjami inline (konkretne sugestie korekty)
- [x] **SHAD-04**: Agent generuje poprawioną wersję tekstu (po zastosowaniu sugestii)
- [x] **SHAD-05**: Użytkownik widzi oba outputy: tekst z anotacjami i wersję poprawioną
- [x] **SHAD-06**: Użytkownik może odrzucić sugestie podając powód — agent regeneruje alternatywne korekty (max 3 iteracje)

### Duplicate Detection

- [x] **DUPL-01**: Przed uruchomieniem researchu, agent sprawdza czy podobny temat nie był poruszany (embedding similarity vs Metadata Log)
- [x] **DUPL-02**: Gdy wykryto podobny temat, agent informuje użytkownika: tytuł istniejącego artykułu + data publikacji
- [x] **DUPL-03**: Użytkownik może przesłonić ostrzeżenie i kontynuować (temat uznany za wystarczająco różny)
- [x] **DUPL-04**: Próg podobieństwa tematów jest konfigurowalny przez zmienną środowiskową (DUPLICATE_THRESHOLD)

### Chat Interface

- [x] **UI-01**: Interfejs zawiera wyraźny przełącznik trybu Author / Shadow widoczny w głównym widoku czatu
- [x] **UI-02**: Interfejs zawiera progress indicator podczas długich operacji z etapami: research → struktura → pisanie (lub: analiza → korekta)
- [x] **UI-03**: Użytkownik widzi wygenerowany content w edytorze Markdown z podglądem
- [x] **UI-04**: Użytkownik może zatwierdzić lub odrzucić output na każdym checkpoint (przyciski Zatwierdź / Odrzuć)
- [x] **UI-05**: Przy odrzuceniu, użytkownik może wpisać feedback tekstowy dla agenta
- [x] **UI-06**: Przycisk "Zatwierdź i Zapisz" zapisuje metadane do Metadata Log i oznacza temat jako użyty
- [x] **UI-07**: Interfejs reaguje na zdarzenia strumieniowe — tokeny LLM są wyświetlane progressywnie (nie czeka na cały output)
- [x] **UI-08**: Użytkownik ma dostęp do sekcji zarządzania corpus (dodawanie artykułów, widok statusu)

### Streaming i Recovery Sesji

- [x] **REC-01**: Frontend retry'uje `POST /api/chat/stream` i `POST /api/chat/resume` wyłącznie przed otrzymaniem streaming `Response`
- [x] **REC-02**: Po committed disconnect frontend odzyskuje stan wyłącznie przez `GET /api/chat/history/{thread_id}`, bez replayu zatwierdzonego `POST`
- [x] **REC-03**: Reload strony na checkpointcie Shadow przywraca `annotations`, `shadow_corrected_text`, `draft` i akcje HITL z historii sesji

---

## v2 Requirements

### YouTube → Artykuł

- **YT-01**: Użytkownik podaje link YouTube, agent pobiera transkrypcję (youtube-transcript-api)
- **YT-02**: Agent generuje artykuł blogowy lub streszczenie w Markdown na podstawie transkrypcji
- **YT-03**: Feature działa wyłącznie dla filmów z napisami (ręcznymi lub auto-generowanymi); brak audio processing
- **YT-04**: Agent wyraźnie informuje o braku napisów gdy transkrypcja jest niedostępna

### Social Media Repurposing

- **REPR-01**: Na podstawie zatwierdzonego artykułu, użytkownik może wygenerować warianty dla Facebook, LinkedIn, Instagram, X (Twitter)
- **REPR-02**: Każdy wariant respektuje limity znaków: X ≤280, LinkedIn ≤3000, Instagram ≤2200, Facebook ≤400 (praktyczny)
- **REPR-03**: Output wyłącznie w formacie Markdown — brak automatycznej publikacji
- **REPR-04**: Użytkownik może odrzucić wariant z feedbackiem — agent regeneruje

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Autopost do CMS (WordPress) lub Social Media | Human-in-the-loop jest zasadą projektu; ryzyko publikacji niezatwierdzonej treści. Rozważyć Phase 2. |
| Integracja z API SEO (Ahrefs, Semrush, Surfer, Google Trends) | SEO przez prompt-engineering w MVP; znana luka (brak danych o wolumenie fraz). |
| Przetwarzanie audio/video (Whisper API) | Znaczna złożoność infrastruktury; YouTube captions wystarczają dla zakresu MVP. |
| Fine-tuning modeli na danych użytkownika | Ryzyko GDPR + ogromny koszt obliczeniowy; RAG + Few-Shot (ICL) jest wystarczające. |
| Generowanie obrazów / sugestii wizualnych | Poza zakresem narzędzia do pisania; rozważyć Phase 2. |
| Tryb wieloużytkownikowy i zarządzanie uprawnieniami | Projekt MVP = 1-2 użytkowników (CEO, marketing). |
| Grammar / plagiarism checker (Grammarly-style) | Shadow mode pokrywa korektę stylu; weryfikacja gramatyki — odpowiedzialność użytkownika. |
| Harmonogram publikacji / content calendar | Bond = narzędzie do pisania, nie CMS. |
| Scraping Google Drive bez wskazania folderu | Tylko wskazane foldery/pliki — zasada bezpieczeństwa z PRD. |

---

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CORP-01 | Phase 1 | Complete |
| CORP-02 | Phase 1 | Complete |
| CORP-03 | Phase 1 | Complete |
| CORP-04 | Phase 1 | Complete |
| CORP-05 | Phase 1 | Complete |
| CORP-06 | Phase 1 | Complete |
| CORP-07 | Phase 1 | Complete |
| AUTH-01 | Phase 2 | Complete |
| AUTH-02 | Phase 2 | Complete |
| AUTH-03 | Phase 2 | Complete |
| AUTH-04 | Phase 2 | Complete |
| AUTH-05 | Phase 2 | Complete |
| AUTH-06 | Phase 2 | Complete |
| AUTH-07 | Phase 2 | Complete |
| AUTH-08 | Phase 2 | Complete |
| AUTH-09 | Phase 2 | Complete |
| AUTH-10 | Phase 2 | Complete |
| AUTH-11 | Phase 2 | Complete |
| DUPL-01 | Phase 2 | Complete |
| DUPL-02 | Phase 2 | Complete |
| DUPL-03 | Phase 2 | Complete |
| DUPL-04 | Phase 2 | Complete |
| UI-01 | Phase 3 | Complete |
| UI-02 | Phase 3 | Complete |
| UI-03 | Phase 3 | Complete |
| UI-04 | Phase 3 | Complete |
| UI-05 | Phase 3 | Complete |
| UI-06 | Phase 3 | Complete |
| UI-07 | Phase 3 | Complete |
| UI-08 | Phase 3 | Complete |
| SHAD-01 | Phase 4 | Complete |
| SHAD-02 | Phase 4 | Complete |
| SHAD-03 | Phase 4 | Complete |
| SHAD-04 | Phase 4 | Complete |
| SHAD-05 | Phase 4 | Complete |
| SHAD-06 | Phase 4 | Complete |
| REC-01 | Post-Phase 4 hardening | Complete — validated 2026-04-28 on detached runtime (`scripts/playwright_detached_runtime_journey.py`) |
| REC-02 | Post-Phase 4 hardening | Complete — validated 2026-04-28 on detached runtime (`scripts/playwright_detached_runtime_journey.py`) |
| REC-03 | Post-Phase 4 hardening | Complete — validated 2026-04-28 on detached runtime (`scripts/playwright_detached_runtime_journey.py`) |

**Coverage:**
- v1 requirements: 39 total
- Mapped to phases: 39
- Unmapped: 0

---

*Requirements defined: 2026-02-20*
*Last updated: 2026-04-29 — wymagania v1 pozostają mapped complete; dodatkowy sweep E2E zamknął CP1 structure visibility, CP2 validation-warning visibility i mode-switch leak, ale odsłonił otwarte follow-upy regresyjne poza samym mappingiem wymagań*
