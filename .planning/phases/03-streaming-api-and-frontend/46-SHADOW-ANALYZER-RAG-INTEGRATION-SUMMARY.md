# 46-SHADOW-ANALYZER-RAG-INTEGRATION Podsumowanie: Węzeł Analyzer — Integracja RAG

**Data ukończenia:** 2026-04-23  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** Shadow Mode — Węzeł Analyzer (Integracja RAG)  
**Status:** ✅ Zakończone

---

## Cel

Automatyczna identyfikacja różnic stylistycznych między tekstem użytkownika a korpusem autorskim.

- Węzeł `shadow_analyze_node` pobiera 3–5 najbardziej trafnych fragmentów stylu z ChromaDB przez dwuprzebiegowy retriever.
- LLM przeprowadza analizę porównawczą w trzech wymiarach: **ton**, **interpunkcja/rytm zdań**, **słownictwo**.
- Wynik analizy zapisywany w `state["research_report"]`; surowe fragmenty przekazywane do `shadow_annotate_node` przez `state["shadow_corpus_fragments"]`.

---

## Architektura

```
[original_text from BondState]
        │
        ▼
shadow_analyze_node (bond/graph/nodes/shadow_analyze.py)
        │
        ├─► two_pass_retrieve(original_text, n=rag_top_k)   ← bond/corpus/retriever.py
        │       │
        │       ├─ Pass 1: ChromaDB query (source_type='own')
        │       │       ┌── 0 wyników → Pass 2 fallback
        │       │       ├── 1..n-1 wyników → fill z external → own + ext
        │       │       └── n wyników → tylko own_text
        │       │
        │       └─ Pass 2 (fallback): ChromaDB query (source_type='external')
        │               └── re-ranker gwarantuje own przed external
        │
        ├─ Guard: pusty original_text → early return (bez wywołania LLM)
        ├─ Guard: brak fragmentów → zwróć komunikat o pustym korpusie
        │
        └─► get_research_llm(max_tokens=2000)
                │
                ├─ SystemMessage: _ANALYZE_SYSTEM_PROMPT (3 wymiary + podsumowanie)
                └─ HumanMessage: _build_analyze_user_prompt(original_text, fragments)
                        │
                        ▼
        ┌────────────────────────────────────────────────────┐
        │  state["research_report"]                          │
        │  Markdown: Ton / Interpunkcja / Słownictwo         │
        │            / Podsumowanie odchyleń                 │
        └────────────────────────────────────────────────────┘
        ┌────────────────────────────────────────────────────┐
        │  state["shadow_corpus_fragments"]                  │
        │  list[dict] → shadow_annotate_node                 │
        └────────────────────────────────────────────────────┘
```

---

## Zaimplementowane pliki

### `bond/graph/nodes/shadow_analyze.py`

Pełna implementacja węzła złożona z trzech warstw:

#### 1. Retrieval (`two_pass_retrieve` z `bond/corpus/retriever.py`)

```python
fragments = await two_pass_retrieve(original_text, n=settings.rag_top_k)
```

- **Pass 1**: zapytanie ChromaDB z filtrem `source_type='own'` — własne teksty autora mają priorytet.
- **Pass 2 / fill**: jeśli Pass 1 zwrócił 0 wyników — pełny fallback do `external`; jeśli 1..n-1 — uzupełnienie wolnych slotów zewnętrznymi fragmentami.
- **Re-ranker**: fragmenty `own` zawsze poprzedzają `external` w prompcie — gwarantuje semantyczną kolejność niezależnie od score'ów cosine.
- `settings.rag_top_k = 5` (domyślnie) — konfigurowalny przez `.env`.

#### 2. Prompt porównawczy

```python
_ANALYZE_SYSTEM_PROMPT  # wymusza trzy obowiązkowe sekcje + podsumowanie odchyleń
_build_analyze_user_prompt(original_text, fragments)  # formatuje [Fragment N] bloki
```

System prompt narzuca strukturę:
```
### Analiza porównawcza stylu
#### Ton
#### Interpunkcja i rytm zdań
#### Słownictwo i konstrukcje zdań
#### Podsumowanie odchyleń   ← 3–5 punktów priorytetyzowanych od największego odchylenia
```

Każda sekcja wymaga cytatów z obu tekstów jako dowodu obserwacji.

#### 3. Węzeł główny (`shadow_analyze_node`)

| Ścieżka | Zachowanie |
|---------|------------|
| `original_text` puste | Early return `{research_report: "", shadow_corpus_fragments: []}` |
| Brak fragmentów w ChromaDB | Zwraca komunikat o braku korpusu; nie wywołuje LLM |
| Fragmenty dostępne | Wywołuje `get_research_llm(max_tokens=2000)`, zwraca pełną analizę Markdown |

---

### `bond/corpus/retriever.py`

Dedykowany moduł retrieval — jedyne źródło prawdy dla logiki dwuprzebiegowej.

#### `async two_pass_retrieve(query, n=None) → list[dict]`

| Scenariusz | Zachowanie |
|---|---|
| 0 own_text w korpusie | Zwraca `n` external_blogger (czysty fallback) |
| 1..n-1 own_text | Uzupełnia wolne sloty z external; zwraca `own + ext` |
| ≥ n own_text | Zwraca tylko `n` own_text (bez external) |

#### `rerank(fragments) → list[dict]`

Stabilny sort: wszystkie `source_type='own'` przed pozostałymi. Kolejność wewnątrz grup (według relevance score) zachowana.

#### `async _query_collection(query, n, source_type=None) → list[dict]`

Niskopoziomowy helper ChromaDB. Operacje blokujące uruchamiane przez `asyncio.to_thread()` — event loop nigdy nie jest blokowany. Zwraca `[]` na błąd lub pustą kolekcję.

---

### `bond/graph/state.py`

Pola BondState wykorzystywane przez węzeł:

```python
original_text: Optional[str]                    # wejście — tekst do analizy
research_report: Optional[str]                  # wyjście — Markdown analizy porównawczej
shadow_corpus_fragments: Optional[list[dict]]   # wyjście — surowe fragmenty → shadow_annotate
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Pobieranie 3–5 najbardziej podobnych fragmentów stylu z ChromaDB | ✅ `two_pass_retrieve(original_text, n=settings.rag_top_k)` — domyślnie 5; Pass 1 preferuje `own`, fill/fallback z `external` |
| Re-ranker gwarantuje własne teksty przed zewnętrznymi | ✅ `rerank()` w retriever — stabilny sort own → external |
| Węzeł generuje analizę porównawczą (ton, słownictwo, struktura) | ✅ `_ANALYZE_SYSTEM_PROMPT` wymusza trzy sekcje: **Ton**, **Interpunkcja i rytm zdań**, **Słownictwo i konstrukcje zdań** |
| Wynik zapisywany w `state["research_report"]` | ✅ Re-use istniejącego pola BondState; pełni analogiczną rolę w obu trybach |
| Surowe fragmenty dostępne dla `shadow_annotate_node` | ✅ `state["shadow_corpus_fragments"]` — automatyczny przepływ przez LangGraph |
| Guard clause: pusty tekst | ✅ Early return bez wywołania LLM |
| Guard clause: pusty korpus | ✅ Zwraca czytelny komunikat zamiast halucynacji |

---

## Decyzje projektowe

| Decyzja | Uzasadnienie |
|---------|--------------|
| Re-use `research_report` zamiast nowego pola | Unika rozrostu BondState; `research_report` pełni analogiczną rolę w obu trybach (feed do następnego węzła LLM) |
| Próg fallback: 0 (nie stary _MIN_OWN_FRAGMENTS=3) | Nawet 1 fragment own_text zawsze poprzedza external w prompcie dzięki re-rankerowi |
| Model `settings.research_model` (gpt-4o-mini domyślnie) | Analiza porównawcza to zadanie rozumienia, nie generowania długiej treści — lżejszy model obniża koszt |
| `asyncio.to_thread()` dla ChromaDB | ChromaDB nie jest natywnie async; przeniesienie do thread pool zapobiega blokowaniu event loop |
| `_ANALYZE_SYSTEM_PROMPT` jako stała modułu | Ułatwia podmianę w testach przez monkey-patching bez modyfikacji kodu węzła |

---

## Weryfikacja

```bash
.venv/bin/python -c "
from bond.corpus.retriever import two_pass_retrieve, rerank
from bond.graph.nodes.shadow_analyze import shadow_analyze_node, _ANALYZE_SYSTEM_PROMPT
from bond.graph.state import BondState
import typing

# Retriever API
assert callable(two_pass_retrieve)
assert callable(rerank)

# Prompt covers all 3 dimensions
assert 'TON' in _ANALYZE_SYSTEM_PROMPT
assert 'INTERPUNKCJA' in _ANALYZE_SYSTEM_PROMPT
assert 'SŁOWNICTWO' in _ANALYZE_SYSTEM_PROMPT

# BondState fields
hints = typing.get_type_hints(BondState)
assert 'original_text' in hints
assert 'research_report' in hints
assert 'shadow_corpus_fragments' in hints

print('OK')
"
# → OK
```

Testy behawioralne węzła (mock ChromaDB + LLM):

- Pusty `original_text` → early return bez LLM call ✅
- Brak fragmentów w kolekcji → komunikat o pustym korpusie ✅
- Fragmenty dostępne → analiza Markdown w `research_report`, fragmenty w `shadow_corpus_fragments` ✅

Testy retrieval:

- `rerank`: own zawsze przed external, kolejność w grupach zachowana ✅
- `two_pass_retrieve`: fallback path (brak own → external) ✅
- `two_pass_retrieve`: fill path (own + external uzupełniające wolne sloty) ✅
