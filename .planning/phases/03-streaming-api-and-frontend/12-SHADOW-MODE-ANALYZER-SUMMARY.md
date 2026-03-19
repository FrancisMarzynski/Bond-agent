# 12-SHADOW-MODE-ANALYZER Podsumowanie: Węzeł Analyzer — RAG Integration

**Data ukończenia:** 2026-03-19
**Faza:** 04 — Shadow Mode
**Plan:** 02 — Analyzer (RAG Integration)
**Status:** ✅ Zakończone

---

## Cel

Pełna implementacja węzła `shadow_analyze_node` — zastąpienie stubu działającą logiką ChromaDB. Węzeł pobiera 3–5 najbardziej pasujących fragmentów z korpusu stylistycznego, uruchamia porównawczą analizę LLM (ton, interpunkcja, słownictwo) i zapisuje wynik w `state["research_report"]` (re-use pola), a surowe fragmenty przekazuje do `shadow_annotate` przez nowe pole `shadow_corpus_fragments`.

---

## Zmodyfikowane/Utworzone pliki

### `bond/graph/nodes/shadow_analyze.py` *(przepisany z zera)*

Zastąpiono stub pełną implementacją złożoną z trzech warstw:

**1. Dwuprzejściowe pobieranie fragmentów korpusu (`_retrieve_corpus_fragments`)**
- Pass 1: zapytanie `bond_style_corpus_v1` z filtrem `where={"source_type": "own"}` — preferencja własnych tekstów autora.
- Pass 2 (fallback): jeśli Pass 1 zwrócił mniej niż `_MIN_OWN_FRAGMENTS = 3` fragmentów, wykonuje zapytanie bez filtra i uzupełnia pulę ze wszystkich typów źródeł.
- Zwraca `list[dict]` z kluczem `text` i wszystkimi metadanymi z kolekcji.
- Liczba pobranych fragmentów kontrolowana przez `settings.rag_top_k` (domyślnie 5).
- Obsługa wyjątków: każde przejście owinięte w `try/except` z logiem WARNING — węzeł nigdy nie crashuje nawet gdy ChromaDB jest niedostępne.

**2. Prompt porównawczy (`_ANALYZE_SYSTEM_PROMPT` + `_build_analyze_user_prompt`)**
- System prompt wymusza analizę wyłącznie w trzech wymiarach: **Ton**, **Interpunkcja i rytm zdań**, **Słownictwo i konstrukcje zdań**.
- Każda sekcja wymaga cytatów z obu tekstów jako dowodu obserwacji.
- Finalna sekcja `#### Podsumowanie odchyleń` — 3–5 punktów priorytetyzowanych od największego odchylenia do najmniejszego.
- Prompt pisany po polsku, stosowany do modelu `settings.research_model`.

**3. Węzeł główny (`shadow_analyze_node`)**
- Guard clause: pusty `original_text` → early return bez wywołania LLM.
- Guard clause: pusta lista fragmentów → wróć z czytelnym komunikatem zamiast halucynacji.
- Wybór LLM: `ChatAnthropic` jeśli `"claude"` w nazwie modelu, inaczej `ChatOpenAI` — identyczny wzorzec jak w `researcher_node`.
- Zwraca:
  - `research_report`: tekst analizy porównawczej (re-use istniejącego pola BondState)
  - `shadow_corpus_fragments`: surowe fragmenty (do dalszego użycia przez `shadow_annotate_node`)

### `bond/graph/state.py`

- Dodano pole `shadow_corpus_fragments: Optional[list[dict]]` w sekcji Shadow mode fields.
- Pole opisuje przepływ danych z `shadow_analyze` → `shadow_annotate` bez modyfikacji istniejących pól.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Węzeł `shadow_analyze` pobiera 3–5 najbardziej pasujących fragmentów z korpusu | ✅ Dwuprzejściowe zapytanie: Pass 1 (`source_type='own'`, n=`rag_top_k`), Pass 2 (wszystkie typy jako fallback gdy <3 własnych) |
| Prompt wymusza analizę porównawczą (szukanie różnic w tonie, interpunkcji, słownictwie) | ✅ `_ANALYZE_SYSTEM_PROMPT` definiuje trzy obowiązkowe sekcje + sekcję podsumowania z cytatami jako dowodem |
| Wynik analizy zapisywany w `state["research_report"]` (re-use pola) | ✅ Węzeł zwraca `{"research_report": analysis, "shadow_corpus_fragments": fragments}` — `research_report` to istniejące pole BondState, bezpiecznie nadpisywane w trybie Shadow |

---

## Architektura przepływu danych

```
[original_text] ─────────────────────────────────┐
                                                   ▼
                                  _retrieve_corpus_fragments()
                                  ┌─────────────────────────┐
                                  │ Pass 1: own-text only   │
                                  │ n_results = rag_top_k   │
                                  │ where source_type='own' │
                                  └──────────┬──────────────┘
                                             │ < 3 wyniki?
                                             ▼
                                  ┌─────────────────────────┐
                                  │ Pass 2: fallback — all  │
                                  │ n_results = rag_top_k   │
                                  └──────────┬──────────────┘
                                             │
                                  list[dict] fragments (3–5)
                                             │
                    ┌────────────────────────┴───────────────────┐
                    ▼                                             ▼
       state["shadow_corpus_fragments"]          LLM comparative analysis
       (surowe fragmenty → shadow_annotate)      (SystemMessage + HumanMessage)
                                                              │
                                                 state["research_report"]
                                                 (Markdown: Ton / Interpunkcja
                                                  / Słownictwo / Podsumowanie)
```

---

## Decyzje projektowe

| Decyzja | Uzasadnienie |
|---------|--------------|
| Re-use `research_report` zamiast nowego pola | Unika rozrostu BondState; `research_report` pełni analogiczną rolę w obu trybach (feed do następnego węzła LLM) |
| `_MIN_OWN_FRAGMENTS = 3` jako próg fallback | Poniżej 3 własnych fragmentów sygnał stylistyczny jest zbyt słaby — zewnętrzne teksty lepsze niż żadne |
| Model z `settings.research_model` | Analiza porównawcza to zadanie rozumienia, nie generowania długiej treści — lżejszy model (`gpt-4o-mini`) wystarczy i obniża koszt |
| Guard clause dla pustego korpusu | Węzeł nie może crashować — Shadow mode musi być testowalny end-to-end nawet na pustej bazie |
| `safe_n = min(n, collection.count())` | ChromaDB zgłasza błąd gdy `n_results > count()` — zabezpieczenie dla małych korpusów |

---

## Uwagi deweloperskie

- `shadow_corpus_fragments` jest dostępne w stanie dla `shadow_annotate_node` bez dodatkowego kroku — dane przepływają automatycznie przez graf LangGraph.
- `_ANALYZE_SYSTEM_PROMPT` jest zdefiniowany jako stała modułu (nie funkcja) — ułatwia podmianę prompta w testach jednostkowych przez monkey-patching.
- Wyjątki w obu przejściach ChromaDB są logowane jako WARNING, nie ERROR — zapobiega niepotrzebnemu alarmowaniu gdy korpus jest poprawny ale filtr `source_type` nie dał wyników.
