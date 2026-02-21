# Requirements: Bond — Agent Redakcyjny

**Defined:** 2026-02-20
**Core Value:** Skrócenie procesu tworzenia gotowego do publikacji draftu z 1–2 dni do maksymalnie 4 godzin — przy zachowaniu stylu nieodróżnialnego od ludzkiego, z human-in-the-loop przed każdą publikacją.

---

## v1 Requirements

### Corpus Ingestion (Onboarding RAG)

- [x] **CORP-01**: Użytkownik może dodać artykuł do bazy stylów przez wklejenie tekstu bezpośrednio w interfejsie
- [x] **CORP-02**: Użytkownik może dodać artykuły do bazy stylów przez upload pliku (PDF, DOCX, TXT)
- [ ] **CORP-03**: Użytkownik może zasilić bazę stylów ze wskazanego folderu Google Drive
- [ ] **CORP-04**: Użytkownik może zasilić bazę stylów podając URL bloga (agent scrape'uje wpisy)
- [x] **CORP-05**: Użytkownik może oznaczać źródło jako "własne teksty" lub "zewnętrzny bloger (wzorzec)"
- [ ] **CORP-06**: Użytkownik widzi liczbę artykułów i fragmentów w bazie stylów (status corpus)
- [ ] **CORP-07**: System informuje użytkownika gdy corpus zawiera mniej niż 10 artykułów (niska jakość stylizacji)

### Author Mode — Generowanie Artykułu

- [ ] **AUTH-01**: Użytkownik może uruchomić tryb Author podając temat i słowa kluczowe
- [ ] **AUTH-02**: Agent wykonuje web research (Exa) i generuje raport: lista źródeł z tytułami, linkami i streszczeniami
- [ ] **AUTH-03**: Agent proponuje strukturę nagłówków (H1/H2/H3) na podstawie researchu
- [ ] **AUTH-04**: Użytkownik zatwierdza lub odrzuca raport i strukturę nagłówków (Checkpoint 1)
- [ ] **AUTH-05**: Po zatwierdzeniu Checkpoint 1, agent generuje pełny draft z zasadami SEO: słowo kluczowe w H1 i pierwszym akapicie, poprawna hierarchia nagłówków, meta-description 150–160 znaków, minimum 800 słów
- [ ] **AUTH-06**: Agent stylizuje draft wstrzykując 3–5 fragmentów wzorcowych z bazy wektorowej (RAG Few-Shot)
- [ ] **AUTH-07**: Użytkownik zatwierdza lub odrzuca stylizowany draft (Checkpoint 2)
- [ ] **AUTH-08**: Użytkownik może podać feedback przy odrzuceniu — agent regeneruje draft bez utraty kontekstu sesji (max 3 iteracje)
- [ ] **AUTH-09**: Po zatwierdzeniu, system zapisuje metadane artykułu do Metadata Log (temat, data, tryb)
- [ ] **AUTH-10**: Wyniki web search są cache'owane w sesji — powtórne zapytanie o ten sam temat nie wywołuje ponownego API call
- [ ] **AUTH-11**: Modele LLM są konfigurowane przez zmienne środowiskowe (RESEARCH_MODEL dla research/analizy, DRAFT_MODEL dla final draft)

### Shadow Mode — Korekta Stylu

- [ ] **SHAD-01**: Użytkownik może uruchomić tryb Shadow wklejając gotowy tekst do analizy
- [ ] **SHAD-02**: Agent porównuje dostarczony tekst ze wzorcami stylistycznymi z bazy wektorowej
- [ ] **SHAD-03**: Agent generuje tekst z anotacjami inline (konkretne sugestie korekty)
- [ ] **SHAD-04**: Agent generuje poprawioną wersję tekstu (po zastosowaniu sugestii)
- [ ] **SHAD-05**: Użytkownik widzi oba outputy: tekst z anotacjami i wersję poprawioną
- [ ] **SHAD-06**: Użytkownik może odrzucić sugestie podając powód — agent regeneruje alternatywne korekty (max 3 iteracje)

### Duplicate Detection

- [ ] **DUPL-01**: Przed uruchomieniem researchu, agent sprawdza czy podobny temat nie był poruszany (embedding similarity vs Metadata Log)
- [ ] **DUPL-02**: Gdy wykryto podobny temat, agent informuje użytkownika: tytuł istniejącego artykułu + data publikacji
- [ ] **DUPL-03**: Użytkownik może przesłonić ostrzeżenie i kontynuować (temat uznany za wystarczająco różny)
- [ ] **DUPL-04**: Próg podobieństwa tematów jest konfigurowalny przez zmienną środowiskową (DUPLICATE_THRESHOLD)

### Chat Interface

- [ ] **UI-01**: Interfejs zawiera wyraźny przełącznik trybu Author / Shadow widoczny w głównym widoku czatu
- [ ] **UI-02**: Interfejs zawiera progress indicator podczas długich operacji z etapami: research → struktura → pisanie (lub: analiza → korekta)
- [ ] **UI-03**: Użytkownik widzi wygenerowany content w edytorze Markdown z podglądem
- [ ] **UI-04**: Użytkownik może zatwierdzić lub odrzucić output na każdym checkpoint (przyciski Zatwierdź / Odrzuć)
- [ ] **UI-05**: Przy odrzuceniu, użytkownik może wpisać feedback tekstowy dla agenta
- [ ] **UI-06**: Przycisk "Zatwierdź i Zapisz" zapisuje metadane do Metadata Log i oznacza temat jako użyty
- [ ] **UI-07**: Interfejs reaguje na zdarzenia strumieniowe — tokeny LLM są wyświetlane progressywnie (nie czeka na cały output)
- [ ] **UI-08**: Użytkownik ma dostęp do sekcji zarządzania corpus (dodawanie artykułów, widok statusu)

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
| CORP-03 | Phase 1 | Pending |
| CORP-04 | Phase 1 | Pending |
| CORP-05 | Phase 1 | Complete |
| CORP-06 | Phase 1 | Pending |
| CORP-07 | Phase 1 | Pending |
| AUTH-01 | Phase 2 | Pending |
| AUTH-02 | Phase 2 | Pending |
| AUTH-03 | Phase 2 | Pending |
| AUTH-04 | Phase 2 | Pending |
| AUTH-05 | Phase 2 | Pending |
| AUTH-06 | Phase 2 | Pending |
| AUTH-07 | Phase 2 | Pending |
| AUTH-08 | Phase 2 | Pending |
| AUTH-09 | Phase 2 | Pending |
| AUTH-10 | Phase 2 | Pending |
| AUTH-11 | Phase 2 | Pending |
| DUPL-01 | Phase 2 | Pending |
| DUPL-02 | Phase 2 | Pending |
| DUPL-03 | Phase 2 | Pending |
| DUPL-04 | Phase 2 | Pending |
| UI-01 | Phase 3 | Pending |
| UI-02 | Phase 3 | Pending |
| UI-03 | Phase 3 | Pending |
| UI-04 | Phase 3 | Pending |
| UI-05 | Phase 3 | Pending |
| UI-06 | Phase 3 | Pending |
| UI-07 | Phase 3 | Pending |
| UI-08 | Phase 3 | Pending |
| SHAD-01 | Phase 4 | Pending |
| SHAD-02 | Phase 4 | Pending |
| SHAD-03 | Phase 4 | Pending |
| SHAD-04 | Phase 4 | Pending |
| SHAD-05 | Phase 4 | Pending |
| SHAD-06 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 36 total
- Mapped to phases: 36
- Unmapped: 0

---

*Requirements defined: 2026-02-20*
*Last updated: 2026-02-20 after roadmap creation — traceability updated, UI moved to Phase 3, SHAD to Phase 4, DUPL grouped with AUTH in Phase 2*
