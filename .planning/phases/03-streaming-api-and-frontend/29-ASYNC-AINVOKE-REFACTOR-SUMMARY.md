# 29-ASYNC-AINVOKE-REFACTOR Podsumowanie: Refaktor asynchroniczny węzłów LLM (ainvoke)

**Data ukończenia:** 2026-04-13  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 29 — Async ainvoke refactor (researcher + structure + writer)  
**Status:** ✅ Zakończone

---

## Cel

Wyeliminowanie wszystkich blokujących wywołań synchronicznych `llm.invoke()` w węzłach grafu LangGraph działających w pętli asyncio.

- `researcher_node`, `structure_node` i `writer_node` używały `llm.invoke()`, które blokuje wątek event loopa na czas odpowiedzi LLM (5–30 sekund).
- W tym czasie serwer nie mógł obsługiwać innych żądań: zawieszały się heartbeaty SSE, rosły opóźnienia, możliwe były timeouty klienta.
- Zamiana na `await llm.ainvoke()` oddaje kontrolę event loopowi podczas oczekiwania na model.

---

## Architektura — przed i po

```
# PRZED (blokujące)
def structure_node(state) -> dict:
    llm = get_research_llm(...)
    heading_structure = llm.invoke(prompt).content.strip()   # ← blokuje event loop
    return {"heading_structure": heading_structure}

def _format_research_report(...) -> str:
    llm = get_research_llm(...)
    formatted = llm.invoke(synthesis_prompt).content.strip() # ← blokuje event loop
    return f"## Raport z badań: {topic}\n\n{formatted}"

def writer_node(state) -> dict:
    llm = get_draft_llm(...)
    draft = _clean_output(llm.invoke(messages).content)      # ← blokuje event loop (x3 retry)
    ...

# PO (nieblokujące)
async def structure_node(state) -> dict:
    llm = get_research_llm(...)
    heading_structure = (await llm.ainvoke(prompt)).content.strip()  # ← nieblokujące
    return {"heading_structure": heading_structure}

async def _format_research_report(...) -> str:
    llm = get_research_llm(...)
    formatted = (await llm.ainvoke(synthesis_prompt)).content.strip() # ← nieblokujące
    return f"## Raport z badań: {topic}\n\n{formatted}"

async def writer_node(state) -> dict:
    llm = get_draft_llm(...)
    draft = _clean_output((await llm.ainvoke(messages)).content)      # ← nieblokujące
    ...
```

LangGraph obsługuje zarówno `def` jak i `async def` jako węzły grafu — zmiana sygnatur nie wymaga modyfikacji `graph.py` ani rejestracji w `_node_registry`.

---

## Zmodyfikowane pliki

### `bond/graph/nodes/researcher.py`

**Zmiana 1:** `_format_research_report` zmieniona z `def` na `async def`.

```python
# Przed:
def _format_research_report(raw_results, topic, keywords, context_block="") -> str:
    ...
    formatted = llm.invoke(synthesis_prompt).content.strip()

# Po:
async def _format_research_report(raw_results, topic, keywords, context_block="") -> str:
    ...
    formatted = (await llm.ainvoke(synthesis_prompt)).content.strip()
```

**Zmiana 2:** Wywołanie `_format_research_report` w `researcher_node` poprzedzone `await`.

```python
# Przed:
report = _format_research_report(raw_results, topic, keywords, context_block)

# Po:
report = await _format_research_report(raw_results, topic, keywords, context_block)
```

`researcher_node` była już `async def` (wymagane przez `_call_exa_mcp`). Żadna zmiana sygnatury węzła nie była potrzebna.

---

### `bond/graph/nodes/structure.py`

**Zmiana 1:** Sygnatura węzła zmieniona z `def` na `async def`.

```python
# Przed:
def structure_node(state: AuthorState) -> dict:

# Po:
async def structure_node(state: AuthorState) -> dict:
```

**Zmiana 2:** Wywołanie `llm.invoke` zmienione na `await llm.ainvoke`.

```python
# Przed:
heading_structure = llm.invoke(prompt).content.strip()

# Po:
heading_structure = (await llm.ainvoke(prompt)).content.strip()
```

---

## Zmodyfikowane pliki

### `bond/graph/nodes/writer.py`

**Zmiana 1:** Sygnatura węzła zmieniona z `def` na `async def`.

```python
# Przed:
def writer_node(state: AuthorState) -> dict:

# Po:
async def writer_node(state: AuthorState) -> dict:
```

**Zmiana 2:** Wywołanie LLM w pętli retry zmienione na `await llm.ainvoke`.

```python
# Przed:
draft = _clean_output(llm.invoke(messages).content)

# Po:
draft = _clean_output((await llm.ainvoke(messages)).content)
```

`interrupt()` wewnątrz węzła pozostaje synchroniczne — LangGraph's `interrupt()` rzuca `GraphInterrupt` jako wyjątek i działa identycznie w kontekście `async def`.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| `llm.invoke()` zamienione na `await llm.ainvoke()` w `researcher.py` | ✅ `_format_research_report` używa `await llm.ainvoke()` |
| `llm.invoke()` zamienione na `await llm.ainvoke()` w `structure.py` | ✅ `structure_node` używa `await llm.ainvoke()` |
| `llm.invoke()` zamienione na `await llm.ainvoke()` w `writer.py` | ✅ `writer_node` używa `await llm.ainvoke()` (wszystkie 3 próby retry) |
| Sygnatury węzłów zmienione na `async def` | ✅ `structure_node`, `writer_node`, `_format_research_report` → `async def` |
| Streaming SSE pozostaje stabilny po zmianie | ✅ LangGraph natywnie obsługuje `async def` węzły; `astream_events` nie wymaga zmian |
| Brak regresji w logice cache (researcher) | ✅ Logika 3-warstwowego cache (memory → SQLite → Exa MCP) nie zmieniona |
| Brak regresji w logice retry (writer) | ✅ Pętla retry i walidacja draftu niezmienione; tylko wywołanie LLM jest async |
| Zero pozostałych `llm.invoke()` w `bond/` | ✅ Potwierdzone grepm — brak dopasowań |

---

## Uwagi implementacyjne

### Dlaczego `_format_research_report` jest funkcją pomocniczą, a nie częścią węzła

Funkcja `_format_research_report` była dotąd synchroniczna mimo że `researcher_node` jest `async def`. Python pozwala na wywołanie synchronicznej funkcji pomocniczej z kontekstu async — ale jej wewnętrzne `llm.invoke()` i tak blokowało event loop. Zmiana sygnatury na `async` i dodanie `await` przy wywołaniu naprawia problem na poziomie wykonania.

### Dlaczego `graph.py` nie wymaga zmian

LangGraph traktuje węzły jako `Runnable` — zarówno `def` jak i `async def` są akceptowane. Węzły `async def` są automatycznie wywoływane przez `await` wewnątrz LangGraph. Rejestracja w `_node_registry` i budowa grafu w `build_author_graph()` pozostają bez zmian.

### `interrupt()` w `async def writer_node`

`interrupt()` z LangGraph jest funkcją synchroniczną rzucającą `GraphInterrupt`. Działa identycznie wewnątrz `async def` — wyjątek jest łapany przez runtime LangGraph niezależnie od tego, czy węzeł jest sync czy async.

---

## Weryfikacja stabilności SSE

Streaming SSE przesyła eventy z `parse_stream_events()` (`bond/api/stream.py`), który iteruje `astream_events` LangGraph. Zmiana węzłów z `def` na `async def` nie wpływa na:

- emisję eventów `on_chain_start` / `on_chain_end` dla `researcher` i `structure`
- token streaming przez `on_chat_model_stream`
- kolejność eventów SSE widzianą przez frontend

LangGraph `astream_events(version="v2")` natywnie obsługuje mieszane środowiska sync/async w grafie — refaktor jest bezpieczny dla istniejącego pipeline'u SSE.
