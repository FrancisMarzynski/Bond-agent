# 08-E2E-HARDENING Podsumowanie: Zabezpieczenia end-to-end i obsługa błędów

**Data ukończenia:** 2026-03-19
**Faza:** 03 — Streaming API i Frontend
**Plan:** 08 — End-to-End Hardening i Error Handling
**Status:** ✅ Zakończone

---

## Cel

Wzmocnienie odporności systemu na przypadki brzegowe i błędy operacyjne:

- Twardy limit iteracji HITL (max 10 na checkpoint) — zapobiega nieskończonej pętli.
- LangGraph `recursion_limit = 50` jako sieć bezpieczeństwa na poziomie grafu.
- Walidacja długości tekstu wejściowego (Shadow Mode, maks. 10 000 znaków).
- Mutex per-wątek w `/api/chat/resume` eliminuje race condition przy szybkim klikaniu "Odrzuć".
- Frontend wykrywa zerwanie połączenia SSE i ponawia próbę lub wyświetla komunikat błędu.
- Poprawiony typ `StreamEvent` — dodano brakujące wartości `shadow_corrected_text` i `annotations`.

---

## Architektura zmian

```
Klient (useStream.ts)
    │
    ├─ POST /api/chat/stream ──► LangGraph (recursion_limit=50)
    │    └─ input validation          │
    │       (max 10 000 znaków)       ▼
    │                          checkpoint_1_node / checkpoint_2_node
    │                                 │
    │                          Hard cap check (iterations >= 10)
    │                                 │
    │                          → Command(goto=END) lub interrupt()
    │
    ├─ POST /api/chat/resume ──► asyncio.Lock (per thread_id)
    │    └─ concurrent duplicate       │
    │       → SSE error event         ▼
    │                          LangGraph.astream_events(Command(resume=...))
    │
    └─ consumeStream() → zwraca bool (endedCleanly)
         └─ jeśli False → fetchWithRetry ponawia (max 3 próby, 3s przerwy)
              └─ po wyczerpaniu prób → systemAlert + stage "error"
```

---

## Zmodyfikowane pliki

### `bond/schemas.py`

Rozszerzono `StreamEvent.type` o brakujące typy zdarzeń Shadow Mode:

```python
# Przed:
type: Literal["node_start", "node_end", "token", "heartbeat", "error",
              "thread_id", "stage", "hitl_pause", "done"]

# Po:
type: Literal["node_start", "node_end", "token", "heartbeat", "error",
              "thread_id", "stage", "hitl_pause", "done",
              "shadow_corrected_text", "annotations"]
```

**Powód:** `chat.py` emitował te zdarzenia przez `StreamEvent(type='shadow_corrected_text', ...)`,
co skutkowało `ValidationError` w runtime z powodu `extra="forbid"` na modelu.

---

### `bond/graph/nodes/checkpoint_1.py`

Dodano stałą `HARD_CAP_ITERATIONS = 10` i sprawdzenie przed `interrupt()`:

```python
HARD_CAP_ITERATIONS = 10

def checkpoint_1_node(state: AuthorState) -> dict | Command:
    cp1_iterations = state.get("cp1_iterations", 0)

    # Hard cap — abort pipeline when iteration limit is reached
    if cp1_iterations >= HARD_CAP_ITERATIONS:
        return Command(goto=END)

    user_response = interrupt({...})
```

**Zachowanie:** Po 10 odrzuceniach przez użytkownika checkpoint_1 automatycznie kończy pipeline
przez `Command(goto=END)` — bez wyświetlania kolejnego okna HITL.

---

### `bond/graph/nodes/checkpoint_2.py`

Dodano stałą `HARD_CAP_ITERATIONS = 10` z analogiczną logiką:

```python
SOFT_CAP_ITERATIONS = 3   # warning (istniejące)
HARD_CAP_ITERATIONS = 10  # hard abort (nowe)

def checkpoint_2_node(state: AuthorState) -> dict | Command:
    cp2_iterations = state.get("cp2_iterations", 0)

    # Hard cap — abort pipeline when iteration limit is reached
    if cp2_iterations >= HARD_CAP_ITERATIONS:
        return Command(goto=END)

    # ... soft cap warning przy >= 3, interrupt(), walidacja odpowiedzi
```

**Hierarchia limitów:**
- Iteracja 3: soft warning (użytkownik widzi ostrzeżenie, może kontynuować)
- Iteracja 10: hard abort (pipeline kończy się automatycznie)

---

### `bond/api/routes/chat.py`

#### 1. Recursion limit w konfiguracji LangGraph

```python
_RECURSION_LIMIT = 50

config = {
    "configurable": {"thread_id": thread_id},
    "recursion_limit": _RECURSION_LIMIT,
}
```

Obliczenie: ścieżka bazowa (7 węzłów) + cp1 pętla (10 × 2 = 20) + cp2 pętla (10 × 2 = 20) = 47.
Limit 50 zapewnia margines i chroni przed `GraphRecursionError` jako ostateczny backstop.

#### 2. Obsługa `GraphRecursionError`

```python
from langgraph.errors import GraphRecursionError

async def formatted_events():
    try:
        async for json_str in parse_stream_events(events):
            yield f"data: {json_str}\n\n"
    except GraphRecursionError:
        error_msg = (
            "Osiągnięto limit iteracji pętli HITL. "
            "Pipeline zatrzymany automatycznie po przekroczeniu maksymalnej liczby kroków."
        )
        yield f"data: {json.dumps({'type': 'error', 'data': error_msg})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'data': str(exc)})}\n\n"
```

#### 3. Walidacja długości tekstu wejściowego

```python
SHADOW_MAX_CHARS = 10_000  # ~2 500 tokenów

class ChatRequest(BaseModel):
    message: str
    ...

    @field_validator("message")
    @classmethod
    def validate_message_length(cls, v: str, info) -> str:
        if len(v) > SHADOW_MAX_CHARS:
            raise ValueError(
                f"Tekst wejściowy jest zbyt długi ({len(v)} znaków). "
                f"Maksimum dla trybu Shadow Mode: {SHADOW_MAX_CHARS} znaków."
            )
        return v
```

FastAPI zwróci HTTP 422 z czytelnym komunikatem walidacyjnym przed uruchomieniem grafu.

#### 4. Mutex per-wątek dla `/api/chat/resume`

```python
_resume_locks: dict[str, asyncio.Lock] = {}

def _get_resume_lock(thread_id: str) -> asyncio.Lock:
    if thread_id not in _resume_locks:
        _resume_locks[thread_id] = asyncio.Lock()
    return _resume_locks[thread_id]

@router.post("/resume")
async def chat_resume(req: ResumeRequest, request: Request):
    lock = _get_resume_lock(req.thread_id)

    async def generate():
        if lock.locked():
            # Równoległy request — odrzuć natychmiast z komunikatem
            yield f"data: {json.dumps({'type': 'error', 'data': '...'})}\n\n"
            return

        async with lock:
            # ... przetwarzanie jednego resume na raz
```

**Powód:** `AsyncSqliteSaver` używa SQLite, który serializuje zapisy, ale dwa równoległe wywołania
`graph.astream_events(Command(resume=...))` dla tego samego `thread_id` mogą odczytać przestarzały
stan checkpointu, prowadząc do zduplikowanego wznowienia lub błędu stanu grafu.

#### 5. Poprawiona inicjalizacja stanu Shadow Mode

```python
initial_state: dict = {
    "topic": req.message,
    "keywords": [],
    "messages": [{"role": "user", "content": req.message}],
    "mode": req.mode,
}
if req.mode == "shadow":
    initial_state["original_text"] = req.message  # ← brakujące pole
```

`shadow_analyze_node` wymaga pola `original_text` w stanie — wcześniej nie było ustawiane.

#### 6. Refaktoryzacja wspólnej logiki strumieniowania

Wyodrębniono `_stream_graph_events()` — asynchroniczny generator współdzielony przez `/stream`
i `/resume`. Eliminuje duplikację pętli heartbeat/disconnect. Używa wzorca sentinel `"__META__:"`
do przekazania `finished_cleanly` i `client_disconnected` do generatorów nadrzędnych.

---

### `frontend/src/hooks/useStream.ts`

#### Wykrywanie zerwania połączenia SSE

`consumeStream` zmieniona z `Promise<void>` na `Promise<boolean>`:

```typescript
async function consumeStream(
    response: Response,
    signal: AbortSignal,
    onThreadId: (id: string) => void
): Promise<boolean> {  // ← true = clean end, false = connection drop
    let endedCleanly = false;
    ...
    // Terminalne zdarzenia ustawiają endedCleanly = true przed return:
    case "done":
        store.setStage("done", "complete");
        store.setStreaming(false);
        endedCleanly = true;
        return endedCleanly;

    case "hitl_pause":
        ...
        endedCleanly = true;
        return endedCleanly;

    case "error":
        ...
        endedCleanly = true; // Błąd to terminal state — nie ponawiaj
        return endedCleanly;
    ...
    return endedCleanly; // false jeśli brak zdarzenia terminalnego
}
```

#### Retry przy nagłym rozłączeniu

```typescript
const endedCleanly = await consumeStream(response, signal, onThreadId);
if (!endedCleanly) {
    // Strumień zakończył się bez zdarzenia terminalnego → ponów
    throw new Error("Połączenie SSE zerwane przed zakończeniem strumienia.");
}
return; // Sukces
```

**Logika retry (istniejąca, zachowana):**
- Max 3 próby z 3-sekundowymi przerwami
- Po wyczerpaniu: `systemAlert` z komunikatem + `stage "error"`
- Intentional abort (`AbortError`) — zawsze traktowany jako clean exit, bez retry

---

## Kryteria akceptacji (AC)

| AC | Status | Implementacja |
|----|--------|---------------|
| Recursion limit (max 10 iteracji) dla pętli HITL | ✅ | Hard cap w `checkpoint_1/2_node` + LangGraph `recursion_limit=50` jako backstop |
| Frontend obsługuje zerwanie SSE (auto-reconnect lub błąd) | ✅ | `consumeStream` zwraca `bool`; `fetchWithRetry` ponawia przy `false`; po 3 próbach → `systemAlert` |
| Walidacja tokenów wejściowych w Shadow Mode | ✅ | `ChatRequest.validate_message_length` — HTTP 422 przy > 10 000 znaków |
| Race condition przy szybkim klikaniu "Odrzuć" | ✅ | `asyncio.Lock` per `thread_id` w `/api/chat/resume`; zduplikowany request → SSE error |

---

## Szczegóły: AsyncSqliteSaver i race conditions

### Problem

`AsyncSqliteSaver` zapisuje stan grafu do SQLite przy każdej zmianie węzła. SQLite serializuje zapisy
przez blokadę na poziomie pliku (`WAL mode`), więc **baza nie ulega korupcji**. Problem jest wyżej:

```
T=0ms: Użytkownik klika "Odrzuć" → POST /resume #1 → aget_state() odczytuje snapshot S1
T=5ms: Użytkownik klika "Odrzuć" → POST /resume #2 → aget_state() odczytuje snapshot S1 (ten sam!)
T=10ms: Resume #1 zapisuje nowy stan S2 (cp2_iterations += 1)
T=15ms: Resume #2 zapisuje nowy stan S3 nadpisując S2 → ZDUPLIKOWANA iteracja
```

### Rozwiązanie

`asyncio.Lock` per `thread_id` gwarantuje, że tylko jeden `astream_events(Command(resume=...))` dla
danego wątku może wykonywać się w danym momencie. Drugi request wykrywa zablokowany lock i natychmiast
zwraca SSE error zamiast czekać (co mogłoby prowadzić do nagromadzenia requestów).

---

## Konwencja ograniczeń iteracji

| Parametr | Wartość | Zachowanie |
|----------|---------|------------|
| `SOFT_CAP_ITERATIONS` (cp2) | 3 | Warning w payloadzie HITL — użytkownik może kontynuować |
| `HARD_CAP_ITERATIONS` (cp1, cp2) | 10 | Automatyczny abort przez `Command(goto=END)` |
| `_RECURSION_LIMIT` (LangGraph) | 50 | `GraphRecursionError` → SSE error event |

---

## Weryfikacja

- `bond/schemas.py`: `StreamEvent(type="shadow_corrected_text", data="...")` — nie rzuca `ValidationError`
- `checkpoint_1_node`: przy `cp1_iterations = 10` zwraca `Command(goto=END)` bez `interrupt()`
- `checkpoint_2_node`: przy `cp2_iterations = 10` zwraca `Command(goto=END)` bez `interrupt()`
- `/api/chat/stream`: tekst > 10 000 znaków → HTTP 422 przed uruchomieniem grafu
- `/api/chat/resume`: drugi równoległy request → SSE `error` event natychmiast
- `consumeStream`: strumień zakończony bez `done` → `fetchWithRetry` ponawia próbę
