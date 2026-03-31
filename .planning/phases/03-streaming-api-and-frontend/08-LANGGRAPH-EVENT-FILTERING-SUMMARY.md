# 08-LANGGRAPH-EVENT-FILTERING Podsumowanie: Filtrowanie Eventów LangGraph

**Data ukończenia:** 2026-03-31  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 08 — LangGraph Event Filtering  
**Status:** ✅ Zakończone

---

## Cel

Oczyszczenie strumienia SSE z szumu technicznego LangGraph poprzez:

- Filtrowanie zdarzeń `on_chat_model_stream` — propagowanie wyłącznie nieustych tokenów LLM.
- Mapowanie cyklu życia węzłów (start/end) na strukturalne komunikaty JSON czytelne dla frontendu.
- Zapewnienie spójnego formatu JSON dla każdego zdarzenia w strumieniu (poza surowymi tokenami).

---

## Architektura

```
LangGraph astream_events (v2)
    │
    ├─ on_chain_start   ──► _extract_node_name()
    │                            │ node ∈ _KNOWN_NODES?
    │                            ├─ TAK → node_start  { node, label }
    │                            │        stage        { stage, status, label }
    │                            └─ NIE → odrzucone (routing fn, __start__, __end__)
    │
    ├─ on_chain_end     ──► _extract_node_name()
    │                            │ node ∈ _KNOWN_NODES?
    │                            ├─ TAK → node_end    { node, label }
    │                            └─ NIE → odrzucone
    │
    └─ on_chat_model_stream ──► _iter_token_texts(chunk)
                                     │ content niepusty?
                                     ├─ TAK → token  (surowy tekst)
                                     └─ NIE → odrzucone
```

---

## Zmodyfikowane pliki

### `bond/api/stream.py`

#### Rozszerzenie `_STAGE_MAP`

Poprzednio pokrywał wyłącznie 4 węzły trybu autora. Teraz mapuje wszystkie 10 węzłów biznesowych:

| Węzeł | Stage |
|-------|-------|
| `duplicate_check` | `checking` |
| `researcher` | `research` |
| `structure` | `structure` |
| `checkpoint_1` | `structure` |
| `writer` | `writing` |
| `checkpoint_2` | `writing` |
| `save_metadata` | `done` |
| `shadow_analyze` | `shadow_analysis` |
| `shadow_annotate` | `shadow_annotation` |
| `shadow_checkpoint` | `shadow_annotation` |

#### Nowy słownik `_NODE_LABELS`

Mapuje każdy węzeł na polskie komunikaty dla UI — osobno dla zdarzeń `start` i `end`:

```python
_NODE_LABELS: dict[str, dict[str, str]] = {
    "researcher": {
        "start": "Wyszukuję informacje o temacie...",
        "end":   "Badania zakończone",
    },
    "writer": {
        "start": "Piszę treść artykułu...",
        "end":   "Wersja robocza gotowa",
    },
    # ... (wszystkie 10 węzłów)
}
```

#### Zmiana formatu `node_start` i `node_end` na JSON

Poprzednio: `data = "researcher"` (surowy string nazwy węzła — naruszenie AC3).

Teraz:
```json
{"type": "node_start", "data": "{\"node\": \"researcher\", \"label\": \"Wyszukuję informacje o temacie...\"}"}
{"type": "node_end",   "data": "{\"node\": \"researcher\", \"label\": \"Badania zakończone\"}"}
```

#### Wzbogacenie `stage` o pole `label`

Poprzednio:
```json
{"stage": "research", "status": "running"}
```

Teraz:
```json
{"stage": "research", "status": "running", "label": "Wyszukuję informacje o temacie..."}
```

#### Token pozostaje surowym tekstem

Zdarzenie `token` świadomie nie dodaje otoczki JSON do pola `data` — tokeny LLM są strumieniowane bezpośrednio w celu minimalizacji narzutu na gorącej ścieżce. Zewnętrzna otoczka `StreamEvent` jest zawsze JSON via `model_dump_json()`.

---

## Zaktualizowane testy

### `tests/unit/api/test_stream.py`

Zaktualizowano asercje dla `node_start` i `stage`:

```python
# node_start — weryfikacja struktury JSON
assert results[0] == {
    "type": "node_start",
    "data": json.dumps({"node": "researcher", "label": "Wyszukuję informacje o temacie..."}),
}
# stage — weryfikacja pól przez parsowanie JSON
stage_data = json.loads(results[1]["data"])
assert stage_data["stage"] == "research"
assert stage_data["status"] == "running"
assert stage_data["label"] == "Wyszukuję informacje o temacie..."
```

### `tests/unit/api/test_chat.py`

Zaktualizowano asercje SSE — parsowanie przez podwójny JSON zamiast prostego dopasowania stringa:

```python
node_start_event = json.loads(lines[1].removeprefix("data: "))
node_start_data = json.loads(node_start_event["data"])
assert node_start_data["node"] == "researcher"
assert "label" in node_start_data
```

---

## Kryteria akceptacji (AC)

| AC | Status | Szczegóły |
|----|--------|-----------|
| Logika filtrująca zdarzenia `on_chat_model_stream` | ✅ | `_iter_token_texts()` odrzuca puste chunki; obsługuje format `str`, `list[ContentBlock]` (Anthropic) i `dict` |
| Mapowanie statusów węzłów na komunikaty dla UI | ✅ | `_NODE_LABELS` pokrywa wszystkie 10 węzłów z polskimi opisami `start`/`end`; `_STAGE_MAP` rozszerzony na tryb shadow |
| Format JSON dla każdego zdarzenia w strumieniu | ✅ | `node_start`, `node_end`, `stage` — `data` to JSON string; `token` — surowy tekst w JSON-owej otoczce `StreamEvent` |

---

## Konwencja payloadów

### `node_start`
```json
{"type": "node_start", "data": "{\"node\": \"<nazwa>\", \"label\": \"<komunikat_pl>\"}"}
```

### `node_end`
```json
{"type": "node_end", "data": "{\"node\": \"<nazwa>\", \"label\": \"<komunikat_pl>\"}"}
```

### `stage`
```json
{"type": "stage", "data": "{\"stage\": \"<etap>\", \"status\": \"running\", \"label\": \"<komunikat_pl>\"}"}
```

### `token`
```json
{"type": "token", "data": "<surowy_tekst>"}
```

---

## Weryfikacja

8 testów jednostkowych przechodzi po zmianach:

```
tests/unit/api/test_stream.py::test_parse_stream_events_on_chain_start_with_langgraph_node PASSED
tests/unit/api/test_stream.py::test_parse_stream_events_on_chain_start_fallback_name PASSED
tests/unit/api/test_stream.py::test_parse_stream_events_on_chain_start_ignored_name PASSED
tests/unit/api/test_stream.py::test_parse_stream_events_on_chat_model_stream_string_content PASSED
tests/unit/api/test_stream.py::test_parse_stream_events_on_chat_model_stream_dict_content PASSED
tests/unit/api/test_stream.py::test_parse_stream_events_on_chat_model_stream_list_content PASSED
tests/unit/api/test_stream.py::test_parse_stream_events_ignores_other_events PASSED
tests/unit/api/test_chat.py::test_chat_stream_returns_sse PASSED
8 passed in 0.31s
```

---

## Wpływ na frontend

Węzły `node_start`/`node_end` w `frontend/src/hooks/useStream.ts` zawierały komentarz `"no store integration yet"` i nie parsowały pola `data` — zmiana formatu na JSON nie łamie istniejącego kodu. Frontend może teraz używać `label` do wyświetlania komunikatów w UI.
