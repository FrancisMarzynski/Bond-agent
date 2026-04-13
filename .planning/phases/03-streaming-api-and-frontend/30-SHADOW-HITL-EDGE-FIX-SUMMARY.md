# 30-SHADOW-HITL-EDGE-FIX Podsumowanie: Naprawa logiki krawędzi Shadow HITL

**Data ukończenia:** 2026-04-13
**Faza:** 03 — Streaming API i Frontend
**Plan:** 30 — Shadow HITL Edge Fix
**Status:** ✅ Zakończone

---

## Cel

Przywrócenie pętli feedbacku w trybie Shadow poprzez zastąpienie stałej krawędzi `END` w grafie LangGraph krawędzią warunkową, która kieruje z powrotem do `shadow_annotate` po odrzuceniu adnotacji przez użytkownika.

---

## Problem

W `bond/graph/graph.py` krawędź po węźle `shadow_checkpoint` była zdefiniowana jako stała:

```python
# Poprzednio — zawsze kieruje do END
builder.add_edge("shadow_checkpoint", END)
```

`shadow_checkpoint_node` poprawnie obsługiwał trzy ścieżki:
- **Zatwierdzenie**: `return {"shadow_approved": True}` — dict bez `Command`, routing przez krawędź grafu
- **Odrzucenie**: `return Command(goto="shadow_annotate", update={...})` — `Command` z bezpośrednim goto
- **Abort / hard cap**: `return Command(goto=END, ...)` — `Command` z bezpośrednim goto

Krawędź statyczna blokowała routing `Command` na poziomie deklaracji grafu: LangGraph wymagał, by `shadow_annotate` było zadeklarowanym celem `shadow_checkpoint` w `path_map` krawędzi. Bez tej deklaracji `Command(goto="shadow_annotate")` nie miał zarejestrowanego docelowego węzła — pętla HITL była faktycznie zepsuta mimo poprawnej logiki w samym węźle.

---

## Rozwiązanie

### Zmieniony plik: `bond/graph/graph.py`

#### 1. Import `HARD_CAP_ITERATIONS` ze stałą z węzła

```python
from bond.graph.nodes.shadow_checkpoint import shadow_checkpoint_node as _shadow_checkpoint_node, HARD_CAP_ITERATIONS
```

Stała jest współdzielona — eliminuje ryzyko rozbieżności między progiem w węźle a progiem w routingu grafu.

#### 2. Nowa funkcja routingu `_route_after_shadow_checkpoint`

```python
def _route_after_shadow_checkpoint(state: BondState) -> str:
    """Route to END on approval or hard-cap; loop back to shadow_annotate on rejection.

    Called only when the node returns a plain dict (approve case).
    For reject/abort/hard-cap the node returns Command(goto=...) which takes precedence.
    The path_map in add_conditional_edges also serves as the LangGraph declaration of all
    valid destinations — required for Command(goto="shadow_annotate") to compile correctly.
    """
    if state.get("shadow_approved"):
        return END
    if state.get("iteration_count", 0) >= HARD_CAP_ITERATIONS:
        return END
    return "shadow_annotate"
```

#### 3. Zamiana statycznej krawędzi na warunkową

```python
# Poprzednio:
builder.add_edge("shadow_checkpoint", END)

# Teraz:
builder.add_conditional_edges(
    "shadow_checkpoint",
    _route_after_shadow_checkpoint,
    {"shadow_annotate": "shadow_annotate", END: END},
)
```

---

## Architektura routingu po naprawie

```
shadow_annotate
      │
      ▼
shadow_checkpoint_node
      │
      ├── return {"shadow_approved": True}
      │         └─► _route_after_shadow_checkpoint(state)
      │                   shadow_approved=True → END ✓
      │
      ├── return Command(goto="shadow_annotate", update={shadow_feedback, iteration_count+1})
      │         └─► Command override → shadow_annotate (pętla) ✓
      │
      ├── return Command(goto=END)  [abort]
      │         └─► Command override → END ✓
      │
      └── return Command(goto=END, update={hard_cap_message})  [hard cap]
                └─► Command override → END ✓
```

**Kluczowa zasada LangGraph:** Gdy węzeł zwraca `Command(goto=X)`, routing function jest pomijana — `Command` ma pierwszeństwo. Jednak `path_map` w `add_conditional_edges` jest wymagany przez LangGraph jako deklaracja wszystkich możliwych celów węzła, niezależnie od tego, czy routing odbywa się przez `Command` czy przez funkcję routingu.

---

## Obsługa `shadow_approved` w stanie

`BondState` zawierał już pole `shadow_approved: Optional[bool]` oraz `shadow_feedback: Optional[str]` i `iteration_count: int`. Węzeł `shadow_checkpoint_node` poprawnie ustawiał te pola. Routing w grafie nie odczytywał flagi — po naprawie `_route_after_shadow_checkpoint` sprawdza `state.get("shadow_approved")` jako warunek wyjścia z pętli.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Implementacja `_route_after_shadow_checkpoint` w `graph.py` | ✅ Dodana funkcja routingu z obsługą wszystkich stanów |
| Zamiana `add_edge("shadow_checkpoint", END)` na krawędź warunkową | ✅ `add_conditional_edges` z `path_map: {shadow_annotate, END}` |
| Obsługa flagi `shadow_approved` w stanie grafu | ✅ Routing sprawdza `state.get("shadow_approved")` |
| Graf kompiluje się bez błędów | ✅ `build_author_graph()` wywołany pomyślnie |
| Routing zatwierdzenia → END | ✅ `shadow_approved=True` → `END` |
| Routing odrzucenia → shadow_annotate | ✅ `shadow_approved=False, iter<HARD_CAP` → `shadow_annotate` |
| Routing hard cap → END | ✅ `iteration_count >= HARD_CAP_ITERATIONS` → `END` |

---

## Weryfikacja

```bash
uv run python -c "
from bond.graph.graph import build_author_graph, _route_after_shadow_checkpoint
from langgraph.graph import END
from bond.graph.nodes.shadow_checkpoint import HARD_CAP_ITERATIONS

# Kompilacja grafu
g = build_author_graph()
print('Graph build OK')

# Routing: zatwierdzenie
assert _route_after_shadow_checkpoint({'shadow_approved': True, 'iteration_count': 1}) == END

# Routing: odrzucenie
assert _route_after_shadow_checkpoint({'shadow_approved': False, 'iteration_count': 1}) == 'shadow_annotate'

# Routing: hard cap
assert _route_after_shadow_checkpoint({'shadow_approved': False, 'iteration_count': HARD_CAP_ITERATIONS}) == END

print('All routing cases pass.')
"
```

Wynik:
```
Graph build OK
All routing cases pass.
```

---

## Brak zmian w węzłach

`shadow_checkpoint_node` nie wymagał modyfikacji — logika stanu (`shadow_approved`, `shadow_feedback`, `iteration_count`) oraz użycie `interrupt()` i `Command` były już poprawnie zaimplementowane. Naprawa była wyłącznie w warstwie deklaracji grafu.
