# Bond — Plan Ulepszeń

Dokument opisuje konkretne usprawnienia zidentyfikowane w kodzie. Każdy punkt zawiera opis problemu, przyczynę i proponowane rozwiązanie.

**Status note (2026-04-28):** ten dokument zawiera miks otwartych ulepszeń i historycznych znalezisk z okresu przed v1 sign-off. Część pozycji została już domknięta w kodzie i zwalidowana gdzie indziej, w tym Shadow HITL loop, research report w UI, export/copy draftu, lokalna historia sesji, async `ainvoke`, cross-session search cache, logging standardization oraz cost tracking. Traktuj pozostałe punkty jako backlog do ponownej weryfikacji względem aktualnego stanu repo, a nie jako listę bieżących blockerów.

---

## Spis treści

1. [Jakość outputów](#jakość-outputów)
   - [1. Obcinanie raportu badawczego](#1-obcinanie-raportu-badawczego)
   - [2. RAG bez rerankingu](#2-rag-bez-rerankingu)
   - [3. Fragmenty RAG bez metadanych](#3-fragmenty-rag-bez-metadanych)
   - [4. Błędna walidacja liczby słów](#4-błędna-walidacja-liczby-słów)
   - [5. Jedno zapytanie do Exa](#5-jedno-zapytanie-do-exa)
   - [6. Minimodel generuje strukturę nagłówków](#6-minimodel-generuje-strukturę-nagłówków)
2. [Brakująca funkcjonalność](#brakująca-funkcjonalność)
   - [7. Pętla HITL w trybie Shadow jest zepsuta](#7-pętla-hitl-w-trybie-shadow-jest-zepsuta)
   - [8. Raport badawczy niewidoczny w UI](#8-raport-badawczy-niewidoczny-w-ui)
   - [9. Brak eksportu i kopiowania draftu](#9-brak-eksportu-i-kopiowania-draftu)
   - [10. Brak historii sesji](#10-brak-historii-sesji)
3. [Architektura i niezawodność](#architektura-i-niezawodność)
   - [12. Blokujące wywołania LLM w asynchronicznym grafie](#12-blokujące-wywołania-llm-w-asynchronicznym-grafie)
   - [13. Cache wyszukiwań nie jest współdzielony między sesjami](#13-cache-wyszukiwań-nie-jest-współdzielony-między-sesjami)
   - [14. Instrukcje print() zamiast logowania](#14-instrukcje-print-zamiast-logowania)
   - [15. Brak śledzenia kosztów per artykuł](#15-brak-śledzenia-kosztów-per-artykuł)
4. [Priorytetyzacja](#priorytetyzacja)

---

## Jakość outputów

### 1. Obcinanie raportu badawczego

**Problem**

`writer_node` przekazuje do prompta tylko pierwsze 3000 znaków raportu badawczego:

```python
# bond/graph/nodes/writer.py, _build_writer_user_prompt()
{research_report[:3000]}
```

`structure_node` obcina go jeszcze bardziej — do 2000 znaków:

```python
# bond/graph/nodes/structure.py
{research_report[:2000]}
```

Pełny raport z Exa zawiera zazwyczaj 6000–12 000 znaków (synteza + lista numerowanych źródeł z URL-ami i streszczeniami). Obcięcie powoduje, że writer generuje tekst bez dostępu do większości zebranych danych — traci konkretne statystyki, daty i cytaty ze źródeł, które są kluczowe dla zasady „Show, Don't Tell" wbudowanej w system prompt.

**Rozwiązanie**

Zamiast surowego obcinania, zbudować skondensowaną wersję raportu zachowującą wszystkie kluczowe fakty: syntezę + pełną listę źródeł (tytuł + URL + jedno zdanie streszczenia). Alternatywnie zwiększyć limit do co najmniej 6000 znaków i użyć modelu z większym oknem kontekstowym jeśli prompt przekracza limit.

---

### 2. RAG bez rerankingu

**Problem**

`_fetch_rag_exemplars()` w `writer_node` pobiera fragmenty z ChromaDB używając wyłącznie cosine similarity z modelu embeddingowego:

```python
# bond/graph/nodes/writer.py
own_results = collection.query(
    query_texts=[topic],
    n_results=n,
    where={"source_type": "own"},
    include=["documents"],
)
```

Cosine similarity mierzy podobieństwo semantyczne tematu, ale nie ocenia, czy dany fragment jest dobrym przykładem stylistycznym dla konkretnego kontekstu pisania. Przy małym korpusie (np. 15–30 artykułów) wyniki mogą być słabe — fragmenty tematycznie zbliżone, ale stylistycznie nieprzydatne (np. fragmenty ze wstępów kontra fragmenty z sekcji technicznych).

**Rozwiązanie**

Dodać przebieg rerankingu po pobraniu kandydatów z ChromaDB. Cross-encoder (np. `cross-encoder/ms-marco-MiniLM-L-6-v2` z biblioteki `sentence-transformers`) ocenia każdą parę (zapytanie, fragment) i zwraca score jakości dopasowania znacznie precyzyjniejszy niż cosine similarity. Reranker powinien działać lokalnie — jest mały i szybki. Schemat:

1. Pobierz `n*3` kandydatów z ChromaDB (np. 15 zamiast 5)
2. Reranker nadaje score każdemu kandydatowi
3. Zwróć top-5 według scoreu rerankera

---

### 3. Fragmenty RAG bez metadanych

**Problem**

Writer dostaje fragmenty jako czysty tekst bez żadnego kontekstu:

```python
# bond/graph/nodes/writer.py, _build_writer_user_prompt()
formatted = "\n\n---\n\n".join(exemplars[:5])
exemplar_section = f"""
## WZORCE STYLISTYCZNE (Few-Shot)
Pisz w podobnym tonie i stylu — nie kopiuj treści, tylko styl.

{formatted}
```

LLM nie wie, czym wyróżniają się te fragmenty — czy to wzorce otwierające artykuł, sekcje techniczne, podsumowania, czy teksty adresowane do inżynierów versus menedżerów. Bez tego kontekstu model traktuje wszystkie fragmenty jednakowo i nie może selektywnie przejąć konkretnych cech stylistycznych.

**Rozwiązanie**

Podczas ingestion do ChromaDB zapisywać dodatkowe metadane per fragment: `article_type` (case study, poradnik, analiza), `section_type` (wstęp, sekcja techniczna, podsumowanie), `tone_label` (techniczny/ekspercki, przystępny/edukacyjny). W bloku few-shot przekazywać te etykiety razem z fragmentem:

```
[Fragment 1 | Typ: case study | Sekcja: wstęp | Ton: techniczny/ekspercki]
<tekst fragmentu>
```

Pozwoli to modelowi dopasować styl do kontekstu generowanej sekcji.

---

### 4. Błędna walidacja liczby słów

**Problem**

`_validate_draft()` liczy słowa w całym drafcie:

```python
# bond/graph/nodes/writer.py
word_count = len(draft.split())
return {
    ...
    "word_count_ok": word_count >= min_words,
}
```

`draft.split()` liczy wszystko — linię `Meta-description:`, nagłówki `# H1`, `## H2`, `### H3` oraz potencjalne pozostałości tagów `<thinking>`. Artykuł z 780 słowami w treści plus 40 słowami w nagłówkach i meta-opisie przejdzie walidację jako „800 słów", mimo że faktyczna treść jest poniżej normy. Odwrotnie — draft z długim meta-opisem może fałszywie wykazać nadliczbę słów.

**Rozwiązanie**

Przed liczeniem odfiltrować linie nagłówków (`^#+ `) i linię meta-description:

```python
def _count_body_words(draft: str) -> int:
    body_lines = [
        line for line in draft.split("\n")
        if line.strip()
        and not line.strip().startswith("#")
        and not re.match(r"^Meta[- ]?[Dd]escription", line.strip(), re.IGNORECASE)
    ]
    return len(" ".join(body_lines).split())
```

---

### 5. Jedno zapytanie do Exa

**Problem**

`_call_exa_mcp()` buduje jedno zapytanie łącząc temat i słowa kluczowe:

```python
# bond/graph/nodes/researcher.py
search_query = f"{query} {' '.join(keywords)}" if keywords else query
result = await web_search.ainvoke({"query": search_query, "numResults": 8})
```

Dla złożonych tematów technicznych (np. „BIM w projektowaniu instalacji elektrycznych dla obiektów szpitalnych") jedno zapytanie zwraca jednorodne wyniki — zazwyczaj artykuły przeglądowe. Brakuje: studiów przypadku, danych statystycznych, porównań technologii, aktualnych trendów. Writer nie ma z czego budować sekcji data-driven.

**Rozwiązanie**

Uruchomić 2–3 równoległe zapytania Exa pokrywające różne kąty tematu:

- Zapytanie 1: definicja/przegląd — `"{topic} {primary_keyword}"`
- Zapytanie 2: dane i statystyki — `"{topic} statystyki dane badania 2024"`
- Zapytanie 3: studia przypadku — `"{topic} case study realizacja przykład"`

Wywołania uruchomić równolegle (`asyncio.gather`), połączyć wyniki i deduplikować po URL przed formatowaniem raportu. Zwiększy to liczbę źródeł z ~8 do 15–20 unikalnych artykułów przy minimalnym wzroście czasu (zapytania równoległe).

---

### 6. Minimodel generuje strukturę nagłówków

**Problem**

`structure_node` używa `get_research_llm()` — modelu tańszego (np. `gpt-4o-mini`):

```python
# bond/graph/nodes/structure.py
llm = get_research_llm(max_tokens=800)
```

Struktura nagłówków (H1/H2/H3) to kluczowa decyzja architektoniczna artykułu — determinuje flow narracyjny, SEO i podział treści. Minimodel generuje poprawne, ale generyczne struktury. Dla technicznej niszy (BIM, XR, instalacje elektryczne) różnica między „dobrą" a „wybitną" strukturą leży w niuansach kolejności sekcji i sposobie formułowania nagłówków pod konkretne intencje wyszukiwania.

**Rozwiązanie**

Przełączyć `structure_node` na `get_draft_llm()`. Struktura to jeden krótki call (max_tokens=800) — koszt różnicy między mini a frontier modelem dla jednego artykułu jest pomijalny, a jakość wyjściowa znacząco wyższa. Alternatywnie: zastosować minimodel do pierwszego draftu struktury, a frontier model do oceny i refinementu tej struktury przed wyświetleniem użytkownikowi.

---

## Brakująca funkcjonalność

### 7. Pętla HITL w trybie Shadow jest zepsuta

**Problem**

W `graph.py` krawędź po `shadow_checkpoint` zawsze prowadzi do `END`:

```python
# bond/graph/graph.py
builder.add_edge("shadow_checkpoint", END)
```

Tymczasem `BondState` zawiera pola obsługujące pętlę odrzuceń: `shadow_approved`, `shadow_feedback`, `iteration_count`. `shadow_checkpoint_node` ustawia te pola, ale graf ignoruje ich wartość i zawsze kończy pipeline. Oznacza to, że użytkownik trybu Shadow nie może odrzucić adnotacji i podać feedbacku — brakuje faktycznej pętli HITL mimo że cały mechanizm stanu jest już zaimplementowany.

**Rozwiązanie**

Zastąpić stałą krawędź warunkową, analogicznie do krawędzi po `checkpoint_2` w trybie Author:

```python
# Zamiast: builder.add_edge("shadow_checkpoint", END)
builder.add_conditional_edges(
    "shadow_checkpoint",
    _route_after_shadow_checkpoint,
    {"shadow_annotate": "shadow_annotate", END: END},
)

def _route_after_shadow_checkpoint(state: BondState) -> str:
    if state.get("shadow_approved"):
        return END
    if state.get("iteration_count", 0) >= HARD_CAP_ITERATIONS:
        return END
    return "shadow_annotate"
```

---

### 8. Raport badawczy niewidoczny w UI

**Problem**

Po zakończeniu `researcher_node` raport trafia do stanu (`research_report`), ale frontend go nie wyświetla. Użytkownik widzi tylko komunikat postępu w `StageProgress`, a następnie od razu Checkpoint 1 z prośbą o zatwierdzenie struktury nagłówków. Zatwierdza strukturę bez możliwości przeczytania badań, na których jest ona oparta — co podważa sens etapu human-in-the-loop.

**Rozwiązanie**

W panelu Checkpoint 1 dodać sekcję z raportem badawczym (zwijana, domyślnie otwarta). Backend już emituje event SSE z `type: "stage"` i payload'em dla każdego węzła — wystarczy dodać `research_report` do payloadu eventu `hitl_pause` dla `checkpoint_1` i wyrenderować go w `CheckpointPanel.tsx`. Alternatywnie: dedykowana zakładka „Badania" widoczna po lewej stronie obok `ChatInterface`.

---

### 9. Brak eksportu i kopiowania draftu

**Problem**

`EditorPane.tsx` nie ma żadnego przycisku do eksportu ani kopiowania. Po zatwierdzeniu draftu użytkownik musi ręcznie zaznaczyć całość tekstu i skopiować go do schowka lub zewnętrznego edytora. Przy artykułach 1000–2000 słów jest to uciążliwe i podatne na błędy (pominięcie fragmentów).

**Rozwiązanie**

Dodać pasek narzędziowy nad edytorem z przyciskami:
- **Kopiuj Markdown** — `navigator.clipboard.writeText(draft)`
- **Pobierz .md** — `Blob` + dynamiczny link `<a download>`
- **Kopiuj HTML** — konwersja Markdown → HTML przez bibliotekę `marked` lub `remark`, następnie skopiowanie do schowka

Przyciski widoczne tylko gdy `draft` nie jest pusty i `!isStreaming`.

---

### 10. Brak historii sesji

**Problem**

Frontend nie ma żadnego widoku ani komponentu umożliwiającego wgląd w poprzednie sesje. LangGraph zapisuje stan checkpointów w SQLite (`bond_checkpoints.db`), a zatwierdzone metadane artykułów w osobnej bazie (`bond_metadata.db`). Dane istnieją, ale są niedostępne z poziomu UI. Użytkownik, który zamknął przeglądarkę w trakcie pisania artykułu, nie może wznowić pracy bez znajomości `thread_id`.

**Rozwiązanie**

1. Dodać endpoint `GET /api/sessions` zwracający listę `thread_id` z metadanych checkpointów (temat, data, ostatni węzeł, status).
2. W `Sidebar.tsx` dodać sekcję „Historia" z listą sesji.
3. Kliknięcie sesji ładuje jej `thread_id` do stanu frontendu i wywołuje `GET /api/chat/status/{thread_id}` do odtworzenia aktualnego stanu (draft, stage, oczekujące HITL).

---

## Architektura i niezawodność

### 12. Blokujące wywołania LLM w asynchronicznym grafie

**Problem**

`researcher_node` i `structure_node` używają synchronicznego `llm.invoke()` zamiast `await llm.ainvoke()`:

```python
# bond/graph/nodes/researcher.py
formatted = llm.invoke(synthesis_prompt).content.strip()

# bond/graph/nodes/structure.py
heading_structure = llm.invoke(prompt).content.strip()
```

LangGraph uruchamia węzły w pętli asyncio. Synchroniczne `invoke()` blokuje wątek event loopa na czas całego wywołania LLM (typowo 5–30 sekund). W tym czasie serwer nie może obsługiwać innych żądań, co powoduje: zawieszenie heartbeatów SSE, opóźnienia w odpowiedziach na inne requesty, potencjalne timeouty po stronie klienta przy wolnych odpowiedziach modelu.

**Rozwiązanie**

Zamienić wszystkie `llm.invoke()` na `await llm.ainvoke()` w węzłach oznaczonych jako `async def`:

```python
# Przed:
formatted = llm.invoke(synthesis_prompt).content.strip()

# Po:
formatted = (await llm.ainvoke(synthesis_prompt)).content.strip()
```

Wymaga też zmiany sygnatury `researcher_node` i `structure_node` z `def` na `async def`.

---

### 13. Cache wyszukiwań nie jest współdzielony między sesjami

**Problem**

`save_cached_result()` i `get_cached_result()` kluczują cache'owanym wynikiem po `(query_hash, thread_id)`:

```python
# bond/db/search_cache.py (wywołanie w researcher.py)
db_result = await get_cached_result(query_hash, thread_id)
await save_cached_result(query_hash, thread_id, raw_results)
```

Ten sam temat wyszukany w dwóch różnych sesjach (`thread_id` A i B) generuje dwa oddzielne wywołania Exa API. W środowisku produkcyjnym, gdzie marketing regularnie wraca do podobnych tematów (BIM, XR, instalacje), ten sam research jest pobierany wielokrotnie co bezpośrednio przekłada się na koszty API.

**Rozwiązanie**

Usunąć `thread_id` z klucza cache lub traktować go jako pole informacyjne (do logowania), nie jako część klucza unikalności. Dodać TTL (np. 7 dni) po którym cache wygasa i następuje świeże zapytanie — dane webowe starzeją się, więc bezterminowe cachowanie prowadziłoby do nieaktualnych raportów.

---

### 14. Instrukcje print() zamiast logowania

**Problem**

`writer_node` używa `print()` do logowania retry'ów i ostrzeżeń walidacji:

```python
# bond/graph/nodes/writer.py
print(f"Writer auto-retry {attempt + 1}/{max_attempts - 1}: failed constraints: {failed}")
print(f"WARNING: Draft failed validation after {max_attempts} attempts. Failed: {failed_constraints}")
```

`print()` trafia tylko na stdout procesu. W środowisku kontenerowym (Docker Compose z konfiguracją obecną w repozytorium) te komunikaty giną lub trafiają do surowych logów bez struktury, poziomu ważności ani timestampu. Nie można ich filtrować, agregować ani ustawić alertów.

**Rozwiązanie**

Zastąpić wszystkie `print()` w węzłach grafowych wywołaniami modułu `logging`:

```python
import logging
log = logging.getLogger(__name__)

# Zamiast print():
log.warning("Writer auto-retry %d/%d: failed constraints: %s", attempt + 1, max_attempts - 1, failed)
log.warning("Draft failed validation after %d attempts. Failed: %s", max_attempts, failed_constraints)
```

---

### 15. Brak śledzenia kosztów per artykuł

**Problem**

`BondState` nie zawiera żadnych pól do śledzenia zużycia tokenów. `writer_node` może wywołać `get_draft_llm()` (GPT-4o) do 3 razy (auto-retry) z max_tokens=4096 za każdym razem. Nie ma mechanizmu, który mierzyłby ile tokenów (i pieniędzy) kosztował każdy artykuł. `PROJECT.md` wymaga explicite „monitoring zużycia per-artykuł" — ta funkcja nie istnieje.

**Rozwiązanie**

1. Dodać pola do `BondState`:
   ```python
   tokens_used_research: int    # tokeny zużyte przez researcher + structure
   tokens_used_draft: int       # tokeny zużyte przez writer (wszystkie próby)
   estimated_cost_usd: float    # przybliżony koszt w USD
   ```
2. Po każdym wywołaniu `llm.ainvoke()` odczytać `response.usage_metadata` (dostępne w LangChain) i akumulować liczniki.
3. Zapisywać `tokens_used_*` i `estimated_cost_usd` do `bond_metadata.db` razem z metadanymi artykułu w `save_metadata_node`.
4. Wyświetlać koszt sesji w UI po zatwierdzeniu artykułu.

---

## Priorytetyzacja

| # | Ulepszenie | Wysiłek | Wpływ |
|---|---|---|---|
| 1 | Naprawienie pętli HITL w Shadow (#7) | Niski | Błąd krytyczny |
| 2 | Raport badawczy w UI przy Checkpoint 1 (#8) | Niski | UX podstawowy |
| 3 | Naprawa walidacji liczby słów (#4) | Niski | Jakość outputu |
| 4 | Async `ainvoke` w węzłach (#12) | Niski | Niezawodność |
| 5 | Eksport i kopiowanie draftu (#9) | Niski | UX |
| 6 | Usunięcie `print()` na rzecz `logging` (#14) | Niski | Obserwowalność |
| 7 | Usunięcie obcinania raportu (#1) | Średni | Jakość outputu |
| 8 | Wielokierunkowe zapytania Exa (#5) | Średni | Jakość badań |
| 9 | Frontier model dla struktury (#6) | Niski | Jakość outputu |
| 10 | Cache zapytań bez thread_id (#13) | Niski | Koszty API |
| 11 | Reranking RAG (#2) | Średni | Jakość stylu |
| 12 | Metadane fragmentów RAG (#3) | Średni | Jakość stylu |
| 13 | Śledzenie kosztów per artykuł (#15) | Średni | Monitoring |
| 14 | Historia sesji w UI (#10) | Wysoki | UX |
