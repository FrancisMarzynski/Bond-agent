# 45-SHADOW-MODE-BONDSTATE-ROUTING Podsumowanie: Rozszerzenie BondState i routing grafu

**Data ukończenia:** 2026-04-23  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** Shadow Mode — Infrastruktura  
**Status:** ✅ Zakończone

---

## Cel

Umożliwienie selektywnego wyboru trybu pracy agenta (Author vs Shadow) w ramach jednego grafu LangGraph.

- Rozszerzenie klasy `BondState` o pola dedykowane trybowi Shadow: `original_text` i `annotations`.
- Implementacja funkcji routingowej `route_mode` kierującej flow na podstawie zmiennej `mode` przy starcie grafu.

---

## Architektura

```
[START]
  │
  ▼ route_mode(state["mode"])
  ├─ None / "author" ──→ duplicate_check
  │                            ↓
  │                       researcher
  │                            ↓
  │                        structure
  │                            ↓
  │                       checkpoint_1 ─────── ↩ (reject loop)
  │                            ↓ (approve)
  │                          writer
  │                            ↓
  │                       checkpoint_2 ─────── ↩ (reject loop)
  │                            ↓ (approve)
  │                       save_metadata
  │                            ↓
  │                          [END]
  │
  └─ "shadow" ──────────→ shadow_analyze
                                ↓
                          shadow_annotate
                                ↓
                         shadow_checkpoint ─── ↩ (reject loop)
                                ↓ (approve / hard cap)
                              [END]
```

Oba tryby współdzielą ten sam `StateGraph(BondState)` — routing odbywa się wyłącznie na krawędzi `START → pierwszyWęzeł`.

---

## Zmodyfikowane pliki

### `bond/graph/state.py`

#### Nowy typ `Annotation` (TypedDict)

Zdefiniowany przed klasą `BondState`; opisuje pojedynczą korektę stylistyczną produkowaną przez `shadow_annotate_node`:

```python
class Annotation(TypedDict):
    id: str            # stabilne unikalne ID, np. "ann_001"
    original_span: str # dokładny verbatim fragment do zastąpienia
    replacement: str   # tekst po korekcie
    reason: str        # krótkie uzasadnienie odwołujące się do stylu autora
    start_index: int   # indeks znaku (inclusive) w original_text
    end_index: int     # indeks znaku (exclusive) w original_text
```

#### Nowe pola `BondState`

```python
# --- Routing ---
mode: NotRequired[Literal["author", "shadow"]]

# --- Shadow mode fields ---
original_text: Optional[str]             # tekst do analizy stylistycznej
annotations: Optional[list[Annotation]] # lista poprawek z shadow_annotate
```

Pola powiązane (dodane w tej samej infrastrukturze Shadow Mode):

```python
shadow_corrected_text: Optional[str]          # pełny tekst z naniesionymi adnotacjami
shadow_corpus_fragments: Optional[list[dict]] # surowe fragmenty korpusu
iteration_count: int                           # liczba pętli korekty (hard cap = 3)
shadow_approved: Optional[bool]
shadow_feedback: Optional[str]
hard_cap_message: NotRequired[Optional[str]]
```

#### Alias wstecznej kompatybilności

```python
AuthorState = BondState
```

Wszystkie węzły Phase 2 (`researcher`, `structure`, `writer`, `checkpoint_1`, `checkpoint_2`, `duplicate_check`, `save_metadata`) importujące `AuthorState` działają bez żadnych modyfikacji.

---

### `bond/graph/graph.py`

#### Funkcja routingowa `route_mode`

```python
def route_mode(state: BondState) -> Literal["duplicate_check", "shadow_analyze"]:
    """Route to Author or Shadow branch based on the 'mode' field at START."""
    if state.get("mode") == "shadow":
        return "shadow_analyze"
    return "duplicate_check"
```

Zasada bezpiecznego domyślnego: brak pola `mode` lub wartość `"author"` → gałąź Author. Tylko jawne `mode="shadow"` aktywuje gałąź Shadow.

#### Krawędź warunkowa przy START

Zastąpiono `builder.add_edge(START, "duplicate_check")` przez:

```python
builder.add_conditional_edges(
    START,
    route_mode,
    {"duplicate_check": "duplicate_check", "shadow_analyze": "shadow_analyze"},
)
```

#### Węzły Shadow w rejestrze

```python
_node_registry: dict = {
    ...                           # węzły Author mode (7)
    "shadow_analyze": _shadow_analyze_node,
    "shadow_annotate": _shadow_annotate_node,
    "shadow_checkpoint": _shadow_checkpoint_node,
}
```

#### Krawędzie gałęzi Shadow

```python
builder.add_edge("shadow_analyze", "shadow_annotate")
builder.add_edge("shadow_annotate", "shadow_checkpoint")
builder.add_conditional_edges(
    "shadow_checkpoint",
    _route_after_shadow_checkpoint,
    {"shadow_annotate": "shadow_annotate", END: END},
)
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| `BondState` zawiera pole `original_text: Optional[str]` | ✅ Dodane; używane przez `shadow_analyze_node` jako wejście do analizy |
| `BondState` zawiera pole `annotations: Optional[list[Annotation]]` | ✅ Dodane; `Annotation` to TypedDict z `id`, `original_span`, `replacement`, `reason`, `start_index`, `end_index` |
| Funkcja `route_mode` implementuje logikę routingu po `mode` | ✅ `state.get("mode") == "shadow"` → `"shadow_analyze"`; wszystko inne → `"duplicate_check"` |
| Pominięcie pola `mode` jest bezpieczne (brak wyjątku) | ✅ Użycie `state.get("mode")` (nie `state["mode"]`) gwarantuje fallback do Author branch |
| `AuthorState` zachowuje wsteczną kompatybilność | ✅ `AuthorState = BondState` — alias identyczny; żaden węzeł Phase 2 nie wymaga zmian |
| Graf kompiluje się z obydwoma gałęziami | ✅ `build_author_graph()` / `build_bond_graph()` zwracają `StateGraph` bez błędu |

---

## Wywołanie w trybie Shadow

Minimalne wejście do `graph.ainvoke()` lub `graph.astream_events()` dla trybu Shadow:

```python
{
    "thread_id": "some-uuid",
    "mode": "shadow",
    "original_text": "Tekst artykułu do analizy stylistycznej...",
}
```

Wywołanie bez `mode` lub z `mode="author"` uruchamia standardowy pipeline Author Mode (bez `original_text`).

---

## Weryfikacja

```bash
.venv/bin/python -c "
from bond.graph.state import BondState, Annotation, AuthorState
from bond.graph.graph import route_mode, build_author_graph

import typing
hints = typing.get_type_hints(BondState)
assert 'original_text' in hints
assert 'annotations' in hints
assert 'mode' in hints

assert route_mode({}) == 'duplicate_check'
assert route_mode({'mode': 'shadow'}) == 'shadow_analyze'
assert route_mode({'mode': 'author'}) == 'duplicate_check'
assert AuthorState is BondState

build_author_graph()
print('OK')
"
```

Wynik: wszystkie asercje przeszły pomyślnie.
