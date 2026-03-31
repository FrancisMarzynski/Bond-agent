# 22-SSE-STREAMING-ENDPOINT Podsumowanie: Streaming SSE dla Trybu Autora

**Data ukończenia:** 2026-03-31
**Faza:** 03 — Streaming API i Frontend
**Plan:** 22 — Implementacja Streamingu SSE
**Status:** ✅ Zakończone

---

## Cel

Wystawienie endpointu `/api/chat/stream` dla trybu Autora z pełnym wsparciem SSE:

- Generator oparty o `EventSourceResponse` (biblioteka `sse-starlette`).
- Integracja z `astream_events(version="v2")` z LangGraph.
- Poprawne domykanie połączenia i propagacja błędów modelu.

---

## Architektura

```
EventSourceResponse (sse-starlette)
    │
    └─ generate()  ←── async generator (surowe JSON-y StreamEvent)
           │
           ├─ emituje thread_id natychmiast
           │
           ├─ _stream_graph_events()
           │       │
           │       ├─ graph.astream_events(version="v2")   ← LangGraph
           │       │       │
           │       │       └─ parse_stream_events()
           │       │               ├─ on_chain_start → node_start + stage
           │       │               ├─ on_chain_end   → node_end
           │       │               └─ on_chat_model_stream → token(y)
           │       │
           │       ├─ heartbeat co 15 s (gdy brak eventów)
           │       ├─ wykrywanie rozłączenia (request.is_disconnected())
           │       ├─ GraphRecursionError → error event
           │       ├─ Exception modelu   → error event + had_error=True
           │       └─ META sentinel (finished_cleanly, client_disconnected)
           │
           └─ _emit_post_stream_events()
                   ├─ graf zatrzymany → stage + hitl_pause
                   └─ graf zakończony → system_alert? + done
```

---

## Zmodyfikowane pliki

### `bond/api/stream.py`

Pełne przepisanie z refaktoryzacją na pomocnicze funkcje prywatne.

**Zmiany:**

1. **`_KNOWN_NODES` (frozenset)** — zbiór węzłów biznesowych filtrujący wewnętrzne węzły LangGraph (`__start__`, `__end__`, funkcje routingu). Zdarzenia spoza tego zbioru są pomijane.

2. **`_STAGE_MAP` (dict)** — mapping `node_name → stage_label` wyciągnięty na poziom modułu, zamiast powielania wewnątrz funkcji.

3. **`parse_stream_events` — blok `try/finally`** — zamknięcie iteratora `events` jest teraz gwarantowane przez `finally`, nawet przy przerwaniu przez klienta lub błędzie modelu:
   ```python
   finally:
       if hasattr(events, "aclose"):
           try:
               await events.aclose()
           except Exception:
               pass
   ```

4. **`_extract_node_name(event)` (helper)** — wyodrębnia nazwę węzła z `metadata.langgraph_node` (priorytet) lub `event.name` (fallback). Zwraca `None` dla węzłów spoza `_KNOWN_NODES`.

5. **`_iter_token_texts(chunk)` (helper, Iterator[str])** — zamiast `_extract_token_text` zwracającego jeden string, nowy helper **yield-uje każdy blok osobno**, co zachowuje granularność streamingu dla formatów Anthropic (`list[ContentBlock]`):
   ```python
   elif isinstance(content, list):
       for block in content:
           if isinstance(block, dict) and block.get("type") == "text":
               text = block.get("text", "")
               if text:
                   yield text
   ```

---

### `bond/api/routes/chat.py`

#### Migracja na `EventSourceResponse`

Zastąpiono `StreamingResponse(generate(), media_type="text/event-stream")` przez:
```python
from sse_starlette.sse import EventSourceResponse

return EventSourceResponse(generate(), headers=_SSE_HEADERS, ping=None)
```

`EventSourceResponse` (sse-starlette ≥ 1.6, zainstalowana przez `mcp`) automatycznie ustawia:
- `Content-Type: text/event-stream; charset=utf-8`
- `Connection: keep-alive`
- `X-Accel-Buffering: no`

Dlatego `_SSE_HEADERS` ogranicza się do:
```python
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Content-Encoding": "identity",
}
```

Generatory `generate()` yield-ują teraz **surowe JSON-y** (bez formatowania `data: ...\n\n`) — SSE-wrapper dodaje `EventSourceResponse` automatycznie.

#### Naprawa błędu `finished_cleanly`

**Poprzednia logika (błędna):**
```python
except StopAsyncIteration:
    finished_cleanly = True   # ← True nawet po błędzie modelu!
    break
```

Po błędzie wewnętrzny generator `_inner()` wyemitował event `error` i zakończył się. Jego `StopAsyncIteration` ustawiał `finished_cleanly = True`, przez co `_emit_post_stream_events` był wywoływany po błędnej sesji.

**Naprawiona logika:**
```python
had_error = False   # śledzone wewnątrz _inner()

except StopAsyncIteration:
    finished_cleanly = not had_error   # False gdy model rzucił wyjątek
    break
```

`had_error` jest ustawiane przez `nonlocal` w `_inner()` przy każdym złapanym wyjątku (`GraphRecursionError` lub `Exception`).

#### Ekstrakcja `_emit_post_stream_events`

Wspólna logika post-stream (inspekcja checkpointów / emisja `done`) wyciągnięta do osobnego generatora pomocniczego — eliminuje duplikację między `/stream` a `/resume`:

```python
async def _emit_post_stream_events(graph, config, thread_id, request):
    state_snapshot = await graph.aget_state(config)
    if state_snapshot.next:
        # Graf zatrzymany na HITL → stage + hitl_pause
        ...
    else:
        # Graf zakończony → system_alert? + shadow output? + done
        ...
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Implementacja generatora `EventSourceResponse` | ✅ `EventSourceResponse(generate(), ...)` z `sse-starlette` |
| Integracja z `astream_events(version="v2")` | ✅ `graph.astream_events(..., version="v2")` w `_stream_graph_events` |
| Poprawne domykanie połączenia przy błędach modelu | ✅ `had_error` → `finished_cleanly = not had_error`; `events.aclose()` w `finally` |

---

## Format zdarzeń SSE

Każde zdarzenie przesyłane klientowi ma postać:
```
data: {"type": "<kind>", "data": "<payload>"}\r\n\r\n
```

| Typ | Dane | Kiedy |
|-----|------|-------|
| `thread_id` | `{"thread_id": "<uuid>"}` | Pierwsza emisja |
| `node_start` | `"<node_name>"` | Węzeł startuje |
| `stage` | `{"stage": "...", "status": "running"}` | Zmiana etapu |
| `token` | `"<chunk>"` | Fragment odpowiedzi LLM |
| `node_end` | `"<node_name>"` | Węzeł kończy |
| `heartbeat` | `"ping"` | Co 15 s bez eventów |
| `hitl_pause` | `{"checkpoint_id": "...", ...}` | Graf pauzuje na HITL |
| `shadow_corrected_text` | `{"text": "..."}` | Tryb Shadow — koniec |
| `annotations` | `[{...}, ...]` | Tryb Shadow — koniec |
| `system_alert` | `"<message>"` | Hard cap lub warning |
| `done` | `"done"` | Graf osiągnął END |
| `error` | `"<message>"` | Błąd modelu lub grafu |

---

## Obsługa rozłączeń klienta

`_stream_graph_events` sprawdza `request.is_disconnected()` przed każdą próbą pobrania zdarzenia. Po wykryciu rozłączenia:

1. Pętla `while True` jest przerywana (`client_disconnected = True`).
2. Blok `finally` wywołuje `await gen.aclose()`.
3. `aclose()` propaguje `GeneratorExit` do `parse_stream_events`, który w bloku `finally` wywołuje `await events.aclose()` — zwalniając połączenia modelu.
4. `finished_cleanly = False` → `_emit_post_stream_events` nie jest wywoływany.

---

## Zależności

| Biblioteka | Wersja | Cel |
|-----------|--------|-----|
| `sse-starlette` | ≥ 1.6 (zainstalowana: 3.2.0) | `EventSourceResponse` |
| `langgraph` | ≥ 0.2 | `astream_events(version="v2")` |
| `fastapi` | ≥ 0.115 | Router, Request |

`sse-starlette` była już obecna w środowisku jako zależność `mcp` — dodano ją jawnie do `pyproject.toml`.

---

## Weryfikacja

Testy jednostkowe (`PYTHONPATH=. uv run pytest`):

```
tests/unit/api/test_stream.py::test_parse_stream_events_on_chain_start_with_langgraph_node  PASSED
tests/unit/api/test_stream.py::test_parse_stream_events_on_chain_start_fallback_name         PASSED
tests/unit/api/test_stream.py::test_parse_stream_events_on_chain_start_ignored_name          PASSED
tests/unit/api/test_stream.py::test_parse_stream_events_on_chat_model_stream_string_content  PASSED
tests/unit/api/test_stream.py::test_parse_stream_events_on_chat_model_stream_dict_content    PASSED
tests/unit/api/test_stream.py::test_parse_stream_events_on_chat_model_stream_list_content    PASSED
tests/unit/api/test_stream.py::test_parse_stream_events_ignores_other_events                 PASSED
tests/unit/api/test_chat.py::test_chat_stream_returns_sse                                    PASSED

8 passed in 0.37s
```
