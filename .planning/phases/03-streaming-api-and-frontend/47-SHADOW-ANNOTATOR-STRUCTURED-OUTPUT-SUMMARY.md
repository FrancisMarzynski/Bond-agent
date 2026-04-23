# 47-SHADOW-ANNOTATOR-STRUCTURED-OUTPUT Podsumowanie: Węzeł Annotator (Structured Output)

**Data ukończenia:** 2026-04-23  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** Shadow Mode — Węzeł Annotator (Structured Output)  
**Status:** ✅ Zakończone

---

## Cel

Przetworzenie analizy stylistycznej na listę konkretnych, maszynowo parsowalnych poprawek.

- Węzeł `shadow_annotate_node` wywołuje LLM przez `with_structured_output(AnnotationResult)` — deterministic JSON schema wymuszony przez Pydantic.
- Każda adnotacja zawiera: `original_span` (dokładny fragment), `replacement` (poprawka), `reason` (uzasadnienie) oraz `start_index` / `end_index` (indeksy znakowe w oryginalnym tekście).
- Walidacja trójprzebiegowa zapewnia spójność indeksów z tekstem; błędne indeksy są auto-korygowane zamiast odrzucane gdy to możliwe.
- Skasowane adnotacje kompilowane są w `shadow_corrected_text` — pełen tekst po zastosowaniu wszystkich poprawek.

---

## Architektura

```
[BondState: original_text, shadow_corpus_fragments, shadow_feedback?]
        │
        ▼
shadow_annotate_node (bond/graph/nodes/shadow_annotate.py)
        │
        ├─ Guard: pusty original_text → early return {annotations: [], shadow_corrected_text: ""}
        ├─ Guard: brak shadow_corpus_fragments → warning, kontynuuje bez referencji stylu
        │
        ├─► get_draft_llm(max_tokens=4096, temperature=0)
        │       └── .with_structured_output(AnnotationResult)
        │               │
        │               ├─ SystemMessage: _SYSTEM_PROMPT  (3 wymiary: ton, rytm, słownictwo)
        │               └─ UserMessage: _build_user_prompt(original_text, fragments, feedback?)
        │                       └─ feedback (opcjonalny) → re-run z feedbackiem z shadow_checkpoint
        │
        ├─► for each AnnotationItem → _validate_and_fix_annotation(item, original_text)
        │       ├─ Pass 1: text[start:end] == original_span → akceptuj
        │       ├─ Pass 2: text.find(original_span) → auto-koryguj indeksy + loguj
        │       └─ Pass 3: brak w tekście → odrzuć + loguj warning
        │
        ├─► _apply_annotations(original_text, valid_annotations)
        │       └─ aplikuje w odwrotnej kolejności (reverse index) → brak przesunięć
        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│  state["annotations"]           list[Annotation]                 │
│  state["shadow_corrected_text"] str                              │
└──────────────────────────────────────────────────────────────────┘
        │
        ▼
shadow_checkpoint_node  →  approve / reject (z feedbackiem) / abort
```

---

## Zaimplementowane pliki

### `bond/graph/nodes/shadow_annotate.py`

Implementacja złożona z czterech warstw.

#### 1. Modele Pydantic (wymuszone przez `with_structured_output`)

```python
class AnnotationItem(BaseModel):
    id: str            # "ann_001", "ann_002" — unikalny, stabilny
    original_span: str # dokładny fragment ≥ 10 znaków; wystarczająco unikalny w tekście
    replacement: str   # poprawiony tekst; zachowuje kontekst interpunkcji i wielkości liter
    reason: str        # 1–2 zdania odwołujące się do korpusu stylistycznego autora
    start_index: int   # pozycja startowa original_span w tekście (włącznie, 0-based)
    end_index: int     # pozycja końcowa original_span w tekście (wyłącznie, 0-based)

class AnnotationResult(BaseModel):
    annotations: list[AnnotationItem]  # posortowane rosnąco po start_index
    alignment_summary: str             # opcjonalne; tylko gdy len(annotations) > 5
```

LangGraph wymusza JSON schema przy każdym wywołaniu — LLM nie może zwrócić niestrukturalnej odpowiedzi.

#### 2. Prompty

```python
_SYSTEM_PROMPT   # 3 wymiary: TON / RYTM ZDAŃ / SŁOWNICTWO + wymóg podania indeksów znakowych
_build_user_prompt(original_text, fragments, feedback=None)
```

Gdy `feedback` jest ustawiony (re-run po odrzuceniu przez użytkownika w `shadow_checkpoint`), prompt zawiera dodatkową sekcję `## FEEDBACK Z POPRZEDNIEJ ITERACJI` — LLM dostosowuje adnotacje do uwag.

#### 3. Walidacja indeksów (`_validate_and_fix_annotation`)

| Przebieg | Warunek | Akcja |
|----------|---------|-------|
| Pass 1 | `text[start:end] == original_span` | Zwróć bez zmian |
| Pass 2 | `text.find(original_span) != -1` | Auto-koryguj indeksy; loguj warning |
| Pass 3 | `original_span` nie w tekście | Odrzuć; loguj warning z detalami |

Trójprzebiegowe podejście minimalizuje utratę poprawnych semantycznie adnotacji gdy LLM zwróci nieprecyzyjne indeksy.

#### 4. Asemblacja tekstu (`_apply_annotations`)

```python
sorted_anns = sorted(annotations, key=lambda a: a["start_index"], reverse=True)
```

Aplikacja w odwrotnej kolejności (od końca do początku) — zmiana długości fragmentu nie przesuwa indeksów kolejnych adnotacji. Każdy `start_index` / `end_index` odnosi się do *oryginalnego* tekstu.

---

### `bond/graph/state.py`

Pola BondState używane przez węzeł:

```python
original_text: Optional[str]                    # wejście — tekst do korekty
shadow_corpus_fragments: Optional[list[dict]]   # wejście — surowe fragmenty z shadow_analyze
shadow_feedback: Optional[str]                  # wejście (re-run) — feedback z shadow_checkpoint
annotations: Optional[list[Annotation]]         # wyjście — lista walidowanych adnotacji
shadow_corrected_text: Optional[str]            # wyjście — pełen tekst po zastosowaniu poprawek
```

`Annotation` (TypedDict) jako interfejs danych między węzłami:

```python
class Annotation(TypedDict):
    id: str
    original_span: str
    replacement: str
    reason: str
    start_index: int
    end_index: int
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Model zwraca listę obiektów zawierających: fragment oryginalny, sugerowaną zmianę i uzasadnienie | ✅ `AnnotationItem`: `original_span`, `replacement`, `reason` — każda adnotacja obowiązkowo |
| Wymuszenie formatu wyjściowego za pomocą Pydantic | ✅ `llm.with_structured_output(AnnotationResult)` — JSON schema egzekwowany przez LangChain; brak możliwości zwrotu niestukturalnej odpowiedzi |
| Walidacja indeksów znakowych `start_index` / `end_index` | ✅ Trójprzebiegowa logika: akceptacja → auto-korekcja → odrzucenie |
| Asemblacja `shadow_corrected_text` | ✅ `_apply_annotations` z odwrotną kolejnością aplikacji |
| Obsługa feedbacku z iteracji re-annotate | ✅ `shadow_feedback` → dodatkowa sekcja promptu |
| Guard clause: pusty tekst wejściowy | ✅ Early return bez wywołania LLM |

---

## Decyzje projektowe

| Decyzja | Uzasadnienie |
|---------|--------------|
| `with_structured_output(AnnotationResult)` zamiast ręcznego parsowania JSON | Eliminuje regex/JSON.parse fragile code; LangChain gwarantuje re-try na schema violation |
| `temperature=0` dla structured output | Indeksy znakowe wymagają determinizmu — losowość zwiększa ryzyko błędnych pozycji |
| Trójprzebiegowa walidacja zamiast odrzucenia przy pierwszym błędzie | LLM regularnie zwraca off-by-one indeksy; auto-korekcja ratuje semantycznie poprawne adnotacje |
| Aplikacja w odwrotnej kolejności indeksów | Jedyna poprawna metoda gdy replacements mają różną długość — klasyczny algorytm diff apply |
| `get_draft_llm` (nie `get_research_llm`) | Draft model (GPT-4o / Claude Sonnet) lepiej radzi sobie z zadaniami wymagającymi precyzji znakowej i spójności JSON |
| `max_tokens=4096` | Przy 10+ adnotacjach z pełnymi cytatami i uzasadnieniami łatwo przekroczyć 2000 tokenów |
| `alignment_summary` tylko przy >5 adnotacjach | Unika redundancji dla prostych tekstów; zachowuje przydatność dla długich artykułów |

---

## Weryfikacja

```bash
.venv/bin/python -c "
from bond.graph.nodes.shadow_annotate import (
    AnnotationItem, AnnotationResult,
    _validate_and_fix_annotation, _apply_annotations,
    _SYSTEM_PROMPT,
)
from bond.graph.state import BondState, Annotation
import typing

# Pydantic schema — wymagane pola
schema = AnnotationResult.model_json_schema()
assert 'annotations' in schema['properties']
for f in ('id', 'original_span', 'replacement', 'reason', 'start_index', 'end_index'):
    assert f in AnnotationItem.model_json_schema()['properties']

# Pass 1: dokładne dopasowanie
item = AnnotationItem(id='ann_001', original_span='hello world', replacement='hi world',
                      reason='style', start_index=0, end_index=11)
ann = _validate_and_fix_annotation(item, 'hello world test')
assert ann is not None and ann['start_index'] == 0 and ann['end_index'] == 11

# Pass 2: auto-korekcja złych indeksów
item_bad = AnnotationItem(id='ann_002', original_span='hello world', replacement='hi world',
                          reason='style', start_index=99, end_index=110)
ann2 = _validate_and_fix_annotation(item_bad, 'hello world test')
assert ann2 is not None and ann2['start_index'] == 0

# Pass 3: odrzucenie — span nie w tekście
item_missing = AnnotationItem(id='ann_003', original_span='not in text', replacement='x',
                              reason='y', start_index=0, end_index=11)
assert _validate_and_fix_annotation(item_missing, 'hello world test') is None

# _apply_annotations — odwrotna kolejność
anns = [
    {'id': 'ann_001', 'original_span': 'foo', 'replacement': 'FOO', 'reason': 'r',
     'start_index': 0, 'end_index': 3},
    {'id': 'ann_002', 'original_span': 'bar', 'replacement': 'BAR', 'reason': 'r',
     'start_index': 4, 'end_index': 7},
]
assert _apply_annotations('foo bar', anns) == 'FOO BAR'

# BondState pola
hints = typing.get_type_hints(BondState)
for field in ('annotations', 'shadow_corrected_text', 'shadow_corpus_fragments', 'shadow_feedback'):
    assert field in hints

print('OK')
"
# → OK
```

Testy behawioralne węzła (mock LLM):

- Pusty `original_text` → early return bez LLM call ✅
- LLM zwraca poprawne indeksy → Pass 1, brak logów warning ✅
- LLM zwraca off-by-one indeksy → Pass 2, auto-korekcja + log warning ✅
- LLM halucynuje `original_span` → Pass 3, odrzucenie + log warning ✅
- `shadow_feedback` ustawiony → sekcja feedbacku w prompcie ✅
- Wiele adnotacji → `shadow_corrected_text` złożony poprawnie przez `_apply_annotations` ✅
