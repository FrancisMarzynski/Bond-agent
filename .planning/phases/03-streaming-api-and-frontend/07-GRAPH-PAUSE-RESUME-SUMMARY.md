# 07-GRAPH-PAUSE-RESUME Podsumowanie: Logika wstrzymywania i wznawiania grafu

**Data ukończenia:** 2026-03-12  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 07 — Checkpoints & HITL Resume  
**Status:** ✅ Zakończone

---

## Cel

Implementacja pełnego cyklu wstrzymywania (pause) i wznawiania (resume) grafu LangGraph po stronie API.

- Backend wykrywa stan `INTERRUPT` w LangGraph i wysyła flagę `hitl_pause` przez SSE do frontendu.
- Endpoint `/api/chat/resume` poprawnie wstrzykuje decyzję użytkownika (feedback) do stanu sesji poprzez `Command(resume=...)`.
- Endpoint `/api/chat/history` dynamicznie odtwarza pełny stan pauzy (w tym payload `hitlPause`) z zadań LangGraph — bez twardego mappingu w kodzie.

---

## Architektura

```
Frontend (useStream.ts)
    │
    ├─ POST /api/chat/stream ─────────────► LangGraph.astream_events(input)
    │                                              │
    │                                       interrupt() wywołany w węźle
    │                                              │
    │   ◄── SSE: stage event ──────────────── aget_state → .next truthy
    │   ◄── SSE: hitl_pause event ────────── aget_state → .tasks[].interrupts
    │
    ├─ GET /api/chat/history/{id} ────────── aget_state → tasksinterrupts → hitlPause JSON
    │
    └─ POST /api/chat/resume ─────────────► LangGraph.astream_events(Command(resume=value))
                                                   │
                                            Węzeł wznawia z resume_value
                                                   │
                                            ◄── SSE events (kolejne węzły)
                                            ◄── SSE: hitl_pause (kolejny checkpoint)
                                            ◄── SSE: done (koniec pipeline)
```

---

## Zmodyfikowane pliki

### `bond/api/routes/chat.py`

#### `/api/chat/stream` — POST

- Rozszerzono `input` grafu o obowiązkowe pola `AuthorState`: `topic` (z `req.message`) oraz `keywords: []`, tak aby `duplicate_check_node` nie rzucał `KeyError`.
- Po czystym zakończeniu strumienia (`finished_cleanly = True`, `client_connected = True`) endpoint wykonuje `graph.aget_state(config)`.
- Jeśli `state_snapshot.next` jest niepuste (graf zatrzymany na przerwaniu), wywołuje `get_chat_history()` i emituje events SSE:
  1. `stage` — aktualny etap z `stageStatus`
  2. `hitl_pause` — pełny payload payloadu przerwania (z zadań LangGraph)
- Jeśli `state_snapshot.next` jest puste (brak oczekujących węzłów), emituje `done`.

#### `/api/chat/resume` — POST

- Buduje `resume_value = {"action": req.action}` i dokłada opcjonalne pola: `feedback`, `edited_structure`, `note`.
- Wywołuje `graph.astream_events(Command(resume=resume_value), config, version="v2")`.
- Ta sama logika post-stream co w `/stream`: sprawdza kolejny checkpoint lub emituje `done`.

#### `get_chat_history` — GET `/api/chat/history/{thread_id}` (wewnętrzna)

**Główna zmiana: dynamiczne odtwarzanie `hitlPause` z `state_snapshot.tasks`.**

Poprzednio: twardy mapping oparty o zawartość stanu (`"heading_structure" in st`, `"draft" in st`).  
Teraz: iteracja przez `state_snapshot.tasks` → `task.interrupts` → `Interrupt.value`.

```python
if hasattr(state_snapshot, "tasks"):
    for task in state_snapshot.tasks:
        if hasattr(task, "interrupts") and task.interrupts:
            for intr in task.interrupts:
                val = getattr(intr, "value", intr)
                if isinstance(val, dict):
                    hitl_pause = {
                        "checkpoint_id": val.get("checkpoint", task.name),
                        "type": val.get("type", "approve_reject"),
                    }
                    # Kopiuj pozostałe pola (bez wewnętrznych kluczy)
                    for k, v in val.items():
                        if k not in ["checkpoint", "type", "instructions"]:
                            hitl_pause[k] = v
```

Dodano obsługę węzła `duplicate_check` w mapowaniu `next_node → stage`.

### `bond/graph/nodes/checkpoint_1.py`

Dodano klucze `"checkpoint"` i `"type"` do payloadu `interrupt()`:

```python
user_response = interrupt({
    "checkpoint": "checkpoint_1",
    "type": "approve_reject",
    "research_report": ...,
    "heading_structure": ...,
    ...
})
```

### `bond/graph/nodes/checkpoint_2.py`

Payload `interrupt()` już zawierał klucz `"checkpoint": "checkpoint_2"` — brak zmian.

### `bond/graph/nodes/duplicate_check.py`

1. Dodano `"checkpoint": "duplicate_check"` i `"type": "approve_reject"` do payloadu `interrupt()`.
2. Zaktualizowano parsowanie wartości `resume` — obsługa zarówno `bool` jak i słownika z kluczem `action`:

```python
"duplicate_override": proceed.get("action") == "approve" 
    if isinstance(proceed, dict) 
    else bool(proceed),
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Backend wykrywa stan INTERRUPT w LangGraph | ✅ `aget_state().next` jest sprawdzane po każdym strumieniu; `.tasks[].interrupts` jest iterowane |
| Wysłanie flagi `hitl_pause` przez SSE | ✅ Po wykryciu przerwania stream emituje event `hitl_pause` z pełnym payloadem z węzła |
| `stage` event poprzedza `hitl_pause` | ✅ Kolejność emisji: `stage` → `hitl_pause` (klient wie o etapie zanim otrzyma prompt) |
| `/api/chat/resume` wstrzykuje feedback | ✅ `resume_value` zawiera `action` + opcjonalne `feedback`, `edited_structure`, `note` |
| `Command(resume=resume_value)` przywraca graf | ✅ LangGraph wznawia węzeł z punktu `interrupt()`; kolejne węzły streamują normalnie |
| `/api/chat/history` odtwarza `hitlPause` | ✅ Dynamicznie z `state_snapshot.tasks` — nie wymaga ręcznego mappingu |
| Obsługa wszystkich checkpointów (cp1, cp2, duplicate) | ✅ Każdy checkpoint emituje ustandaryzowany payload z `checkpoint` i `type` |

---

## Konwencja payloadu `hitl_pause`

Każdy węzeł wywołujący `interrupt()` musi zawrzeć w słowniku co najmniej:

```json
{
  "checkpoint": "<nazwa_węzła>",
  "type": "approve_reject",
  ...inne_pola_specyficzne_dla_węzła...
}
```

Frontend (`useStream.ts`) deserializuje to do `HitlPauseSchema`:

```typescript
const HitlPauseSchema = z.object({
  checkpoint_id: z.string(),       // ← mapowany z "checkpoint"
  type: z.string(),
  iterations_remaining: z.number().optional(),
});
```

> **Uwaga:** `get_chat_history` mapuje `val["checkpoint"]` → `hitl_pause["checkpoint_id"]` (wyrównanie nazewnictwa frontendu).

---

## Przepływ wznowienia krok po kroku

1. **Frontend** wywołuje `resumeStream(threadId, "approve", null)`.
2. Hook `useStream.ts` wysyła `POST /api/chat/resume` z `{thread_id, action: "approve"}`.
3. Endpoint buduje `resume_value = {"action": "approve"}`.
4. `graph.astream_events(Command(resume=resume_value), config, version="v2")` jest wywołany.
5. LangGraph wznawia węzeł (np. `checkpoint_1_node`) w miejscu `interrupt()` — zwraca `resume_value` jako wynik.
6. `checkpoint_1_node` parsuje odpowiedź przez `CheckpointResponse(**resume_value)`.
7. Węzeł zwraca `{"cp1_approved": True}`.
8. Graf kontynuuje do `writer`.
9. Jeśli `writer` kieruje do `checkpoint_2`, po zakończeniu strumienia wysyłany jest kolejny `hitl_pause`.
10. Jeśli `save_metadata` zostanie ukończony, emitowany jest `done`.

---

## Weryfikacja

Przeprowadzono ręczną weryfikację z uruchomionym serwerem:

```
uv run python -m uvicorn bond.api.main:app --reload --port 8000
```

- `POST /api/chat/stream` → poprawnie inicjuje graf z `topic`/`keywords`
- `GET /api/chat/history/{id}` → zwraca `stage`, `hitlPause: null` gdy brak przerwania, `hitlPause: {...}` gdy graf zatrzymany
- `POST /api/chat/resume` → kanał SSE wznawia; po wywołaniu `Command(resume=...)` LangGraph kontynuuje poprawnie

Zweryfikowano mechanizm `interrupt()` / `Command(resume=...)` w izolacji (skrypty testowe):
- Węzeł zatrzymuje się na `interrupt()`, `state.next` zawiera nazwę węzła, `state.tasks[].interrupts` zawiera `Interrupt.value`
- `Command(resume=value)` przywraca węzeł — graf biegnie do końca
