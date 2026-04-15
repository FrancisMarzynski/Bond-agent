# 32-SAFETY-CAP-HITL Podsumowanie: Mechanizm Safety Cap dla pętli HITL

**Data ukończenia:** 2026-04-15  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 32 — Safety Cap dla pętli HITL  
**Status:** ✅ Zakończone

---

## Cel

Ochrona przed nieskończonymi iteracjami w grafie LangGraph przez dodanie mechanizmu twardego limitu (hard cap) dla wszystkich węzłów checkpointowych.

- `iteration_count` w `BondState` śledzi liczbę odrzuceń w pętli Shadow HITL.
- `HARD_CAP_ITERATIONS = 3` definiuje maksymalną liczbę iteracji przed wymuszonym zakończeniem pipeline'u.
- Węzeł `shadow_checkpoint_node` sprawdza limit przed każdym wywołaniem `interrupt()` i terminuje pipeline gdy jest osiągnięty.
- Ostrzeżenie logowane przez moduł `logging` przy każdym wyzwoleniu hard cap — widoczne w logach strukturalnych, filtrowane i agregowalnych.

---

## Architektura

```
shadow_annotate_node
    │
    ▼
shadow_checkpoint_node
    │
    ├─ iteration_count >= HARD_CAP_ITERATIONS (3)?
    │       │
    │       ├─ TAK → log.warning("hard cap reached, thread_id=...")
    │       │         Command(goto=END, update={hard_cap_message: "..."})
    │       │
    │       └─ NIE → interrupt({checkpoint, annotations, ...})
    │                     │
    │                     ├─ "approve" → {shadow_approved: True} → _route: END
    │                     ├─ "abort"   → Command(goto=END)
    │                     └─ "reject"  → Command(goto="shadow_annotate",
    │                                            update={iteration_count: +1, feedback: ...})
    │
    ▼  (_route_after_shadow_checkpoint w graph.py)
   END lub "shadow_annotate"
```

Hard cap sprawdzany **przed** `interrupt()` — jeśli limit jest osiągnięty, pipeline kończy się natychmiast bez oczekiwania na odpowiedź użytkownika.

---

## Stan przed zmianami

Trzy z czterech elementów mechanizmu Safety Cap były już zaimplementowane w poprzednich fazach:

| Element | Status przed zmianami |
|---|---|
| `iteration_count: int` w `BondState` | ✅ istniał (state.py:61) |
| `HARD_CAP_ITERATIONS = 3` w `shadow_checkpoint.py` | ✅ istniał (linia 24) |
| Warunek `iteration_count >= HARD_CAP_ITERATIONS` w węźle | ✅ istniał (linie 44–53) |
| `log.warning()` przy osiągnięciu limitu | ❌ brak — tylko `hard_cap_message` w stanie |

Jedynym brakującym elementem było strukturalne logowanie przez moduł `logging`.

---

## Zmodyfikowane pliki

### `bond/graph/nodes/shadow_checkpoint.py`

Dodano `import logging` i `log = logging.getLogger(__name__)`. Dodano wywołanie `log.warning()` w bloku hard cap przed `Command(goto=END)`:

```python
import logging
log = logging.getLogger(__name__)

# Hard cap — abort shadow pipeline when iteration limit is reached
if iteration_count >= HARD_CAP_ITERATIONS:
    log.warning(
        "shadow_checkpoint: hard cap reached — terminating pipeline after %d/%d iterations "
        "(thread_id=%s)",
        iteration_count,
        HARD_CAP_ITERATIONS,
        state.get("thread_id", "unknown"),
    )
    return Command(
        goto=END,
        update={
            "hard_cap_message": (
                f"Przekroczono limit {HARD_CAP_ITERATIONS} iteracji korekty stylistycznej. "
                "Ostatnia wersja adnotacji została zachowana."
            )
        },
    )
```

### `bond/graph/nodes/checkpoint_1.py`

Dodano `import logging`, `log = logging.getLogger(__name__)` i `log.warning()` w bloku hard cap (HARD_CAP_ITERATIONS = 10):

```python
log.warning(
    "checkpoint_1: hard cap reached — terminating pipeline after %d/%d iterations "
    "(thread_id=%s)",
    cp1_iterations,
    HARD_CAP_ITERATIONS,
    state.get("thread_id", "unknown"),
)
```

### `bond/graph/nodes/checkpoint_2.py`

Dodano `import logging`, `log = logging.getLogger(__name__)` i `log.warning()` w bloku hard cap (HARD_CAP_ITERATIONS = 10):

```python
log.warning(
    "checkpoint_2: hard cap reached — terminating pipeline after %d/%d iterations "
    "(thread_id=%s)",
    cp2_iterations,
    HARD_CAP_ITERATIONS,
    state.get("thread_id", "unknown"),
)
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| `iteration_count` dodany do `BondState` | ✅ Istniał od fazy Shadow Mode (`state.py:61`) |
| `HARD_CAP_ITERATIONS = 3` w węźle `shadow_checkpoint` | ✅ Istniał w `shadow_checkpoint.py` |
| Warunek wyjścia `iteration_count >= HARD_CAP_ITERATIONS` | ✅ Istniał — `Command(goto=END)` z `hard_cap_message` |
| Logowanie `log.warning()` po osiągnięciu limitu | ✅ Dodane do wszystkich trzech węzłów checkpoint |

---

## Uwagi implementacyjne

**Dlaczego `log.warning()` zamiast `log.error()`?**  
Osiągnięcie hard cap to przewidziane, obsługiwane zakończenie pipeline'u — nie błąd systemowy. Poziom `WARNING` jest właściwy: sygnalizuje potrzebę uwagi (użytkownik wielokrotnie odrzucał), ale nie jest awaria.

**Dlaczego logowanie we wszystkich trzech checkpointach?**  
`checkpoint_1` i `checkpoint_2` też miały hard cap (HARD_CAP_ITERATIONS = 10) bez logowania. Dodanie `log.warning()` jest spójne z IMPROVEMENTS.md #14 — zastąpienie `print()` strukturalnym logowaniem. Choć te węzły nie używały `print()`, brak logowania przy hard cap był taką samą luką obserwowalności.

**Format komunikatu logu**  
`"%d/%d iterations (thread_id=%s)"` pozwala na filtrowanie i alerting w systemach jak Loki lub CloudWatch. `thread_id` identyfikuje konkretną sesję artykułu, co ułatwia diagnozę.

**`state.get("thread_id", "unknown")`**  
Defensywne odczytanie — `thread_id` jest zawsze obecny w normalnych sesjach, ale getter z fallbackiem zapobiega `KeyError` w testach jednostkowych gdzie stan jest sztucznie uproszczony.

**Hard cap w `_route_after_shadow_checkpoint`**  
Funkcja routingu w `graph.py` zawiera dodatkowy sprawdzian `iteration_count >= HARD_CAP_ITERATIONS` jako krawędź warunkowa. Jest to zabezpieczenie dla przypadku gdy węzeł zwraca czysty dict zamiast `Command` — zapobiega nieskończonej pętli gdyby logika węzła zmieniła się w przyszłości.
