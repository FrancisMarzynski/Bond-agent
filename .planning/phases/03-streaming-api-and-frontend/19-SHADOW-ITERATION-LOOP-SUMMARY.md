# 19-SHADOW-ITERATION-LOOP Podsumowanie: Pętla Feedbacku i Regeneracji (Shadow Mode)

**Data ukończenia:** 2026-03-25
**Faza:** 03 — Streaming API i Frontend
**Plan:** 19 — Shadow Mode Iteration Loop (SHAD-04)
**Status:** ✅ Zakończone

---

## Cel

Implementacja pętli feedbacku i regeneracji dla Shadow Mode (wymóg SHAD-04).

- Dodanie pola `iteration_count` do `BondState` jako licznika pętli regeneracji adnotacji.
- Nowy węzeł `shadow_checkpoint` zatrzymuje graf po wygenerowaniu adnotacji i czeka na decyzję użytkownika.
- Odrzucenie (`reject`) kieruje graf z powrotem do `shadow_annotate` z feedbackiem użytkownika.
- Hard-stop po 3 iteracjach chroni przed pętlą kosztową.

---

## Architektura

```
shadow_analyze
     │
     ▼
shadow_annotate ◄──────────────────────────────────┐
     │                                             │
     ▼                                             │
shadow_checkpoint ──── approve ────► END           │
     │                                             │
     └──── reject (Command goto="shadow_annotate") ┘
              │
              └── hard-stop po 3 iteracjach ──► END (z hard_cap_message)
```

**Kluczowe zasady:**
- `shadow_checkpoint` używa `Command(goto="shadow_annotate")` przy odrzuceniu — pomija zdefiniowane krawędzie grafu.
- Przy zatwierdzeniu (`approve`) zwraca dict `{"shadow_approved": True}` — graf korzysta ze zdefiniowanej krawędzi do `END`.
- Przy `abort` zwraca `Command(goto=END)` — natychmiastowe zakończenie.

---

## Zmodyfikowane / nowe pliki

### `bond/graph/state.py` — nowe pola w `BondState`

```python
# --- Shadow mode checkpoint ---
iteration_count: int          # licznik pętli regeneracji (hard cap: 3)
shadow_approved: Optional[bool]   # True po zatwierdzeniu przez użytkownika
shadow_feedback: Optional[str]    # feedback użytkownika przy odrzuceniu
```

### `bond/graph/nodes/shadow_checkpoint.py` — nowy węzeł

Odpowiedzialność:
1. Sprawdza `iteration_count >= HARD_CAP_ITERATIONS (3)` — jeśli tak, kończy z `hard_cap_message`.
2. Wywołuje `interrupt()` z payloadem zawierającym `annotations`, `shadow_corrected_text`, `iteration_count`.
3. Parsuje odpowiedź przez `CheckpointResponse`.
4. `abort` → `Command(goto=END)`.
5. `approve` → `{"shadow_approved": True}` (krawędź do END).
6. `reject` → `Command(goto="shadow_annotate", update={"shadow_feedback": ..., "iteration_count": +1})`.

Payload `interrupt()`:

```json
{
  "checkpoint": "shadow_checkpoint",
  "type": "approve_reject",
  "annotations": [...],
  "shadow_corrected_text": "...",
  "iteration_count": 0,
  "instructions": "Wyślij {\"action\": \"approve\"}, {\"action\": \"reject\", \"feedback\": \"...\"} lub {\"action\": \"abort\"}"
}
```

### `bond/graph/nodes/shadow_annotate.py` — obsługa feedbacku

Funkcja `_build_user_prompt` rozszerzona o opcjonalny parametr `feedback`:

```python
def _build_user_prompt(
    original_text: str,
    fragments: list[dict],
    feedback: str | None = None,
) -> str:
    ...
    if feedback:
        base += (
            f"## FEEDBACK Z POPRZEDNIEJ ITERACJI\n\n{feedback}\n\n"
            "Uwzględnij powyższy feedback — popraw adnotacje zgodnie z uwagami użytkownika. "
        )
    ...
```

Węzeł odczytuje `state.get("shadow_feedback")` i przekazuje do prompta przy re-runach.

### `bond/graph/graph.py` — nowe krawędzie

```python
# Nowy import
from bond.graph.nodes.shadow_checkpoint import shadow_checkpoint_node as _shadow_checkpoint_node

# Nowy wpis w _node_registry
"shadow_checkpoint": _shadow_checkpoint_node,

# Zmienione krawędzie (zastąpiono stub shadow_annotate → END)
builder.add_edge("shadow_analyze", "shadow_annotate")
builder.add_edge("shadow_annotate", "shadow_checkpoint")
builder.add_edge("shadow_checkpoint", END)  # używana tylko przy approve
```

---

## Przepływ iteracji krok po kroku

### Iteracja 1 (approve)

1. `shadow_analyze` → `shadow_annotate` generuje adnotacje.
2. `shadow_checkpoint` wywołuje `interrupt()` z `iteration_count=0`.
3. Użytkownik wysyła `{"action": "approve"}`.
4. Węzeł zwraca `{"shadow_approved": True}`.
5. Graf korzysta z krawędzi `shadow_checkpoint → END`.

### Iteracja z odrzuceniem

1. `shadow_checkpoint` wywołuje `interrupt()` z `iteration_count=0`.
2. Użytkownik wysyła `{"action": "reject", "feedback": "Zbyt formalny ton w akapicie 2."}`.
3. Węzeł zwraca `Command(goto="shadow_annotate", update={"shadow_feedback": "Zbyt formalny...", "iteration_count": 1})`.
4. `shadow_annotate` jest wznawiane — prompt zawiera sekcję `## FEEDBACK Z POPRZEDNIEJ ITERACJI`.
5. LLM generuje poprawione adnotacje uwzględniając feedback.
6. `shadow_checkpoint` wywołuje `interrupt()` z `iteration_count=1`.

### Hard-stop (3 iteracje)

1. `shadow_checkpoint` sprawdza `iteration_count >= 3`.
2. Zwraca `Command(goto=END, update={"hard_cap_message": "Przekroczono limit 3 iteracji..."})`.
3. Graf kończy z ostatnio wygenerowanymi adnotacjami zachowanymi w stanie.

---

## Kryteria akceptacji (SHAD-04)

| AC | Status |
|----|--------|
| Pole `iteration_count` dodane do `BondState` | ✅ `bond/graph/state.py` — sekcja Shadow mode checkpoint |
| Graf wraca do `shadow_annotate` przy Reject z feedbackiem | ✅ `Command(goto="shadow_annotate")` z `shadow_feedback` w update |
| Hard-stop po 3 iteracjach | ✅ `HARD_CAP_ITERATIONS = 3` w `shadow_checkpoint.py` |
| Feedback trafia do promptu LLM przy re-runie | ✅ `_build_user_prompt(..., feedback=feedback)` w `shadow_annotate.py` |
| Kompatybilność z istniejącym `CheckpointResponse` | ✅ Używa istniejącego pola `feedback` z `schemas.py` |
| Graf buduje się bez błędów | ✅ `build_author_graph()` zweryfikowane przez `uv run python` |

---

## Konwencja payloadu `shadow_checkpoint`

Spójna z istniejącymi checkpointami (cp1, cp2, duplicate_check):

```json
{
  "checkpoint": "shadow_checkpoint",
  "type": "approve_reject",
  "annotations": [...],
  "shadow_corrected_text": "...",
  "iteration_count": 0,
  "instructions": "..."
}
```

Frontend mapuje `checkpoint` → `checkpoint_id` w `HitlPauseSchema` (bez zmian w logice `get_chat_history`).

---

## Stałe

| Stała | Wartość | Plik |
|-------|---------|------|
| `HARD_CAP_ITERATIONS` | `3` | `shadow_checkpoint.py` |

Porównanie z trybem autora:

| Węzeł | Soft Cap | Hard Cap |
|-------|----------|----------|
| `checkpoint_1` | brak | 10 |
| `checkpoint_2` | 3 (ostrzeżenie) | 10 |
| `shadow_checkpoint` | brak | **3** |

Shadow Mode ma niższy hard cap (3 vs 10) ponieważ każda iteracja wymaga pełnego wywołania LLM na oryginalnym tekście użytkownika — koszt jest proporcjonalnie wyższy niż w trybie autora.

---

## Weryfikacja

```bash
uv run python -c "
from bond.graph.state import BondState
from bond.graph.nodes.shadow_checkpoint import shadow_checkpoint_node, HARD_CAP_ITERATIONS
from bond.graph.graph import build_author_graph, _node_registry
print('iteration_count w BondState:', 'iteration_count' in BondState.__annotations__)
print('HARD_CAP_ITERATIONS:', HARD_CAP_ITERATIONS)
print('shadow_checkpoint w registry:', 'shadow_checkpoint' in _node_registry)
build_author_graph()
print('Graf zbudowany poprawnie')
"
# Output:
# iteration_count w BondState: True
# HARD_CAP_ITERATIONS: 3
# shadow_checkpoint w registry: True
# Graf zbudowany poprawnie
```
