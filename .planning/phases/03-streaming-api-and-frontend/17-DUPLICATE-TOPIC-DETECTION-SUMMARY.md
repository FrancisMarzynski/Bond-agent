# 17-DUPLICATE-TOPIC-DETECTION Podsumowanie: Węzeł wykrywania duplikatów tematów

**Data ukończenia:** 2026-03-24
**Faza:** 03 — Streaming API i Frontend
**Plan:** 17 — Duplicate Topic Detection Node
**Wymaganie:** DUPL-01
**Status:** ✅ Zakończone

---

## Cel

Implementacja węzła LangGraph wykrywającego podobieństwo cosinusowe tematu do wcześniej opublikowanych artykułów przechowywanych w Metadata Log (ChromaDB). Gdy wykryto duplikat, graf przechodzi do stanu HITL_WARNING — użytkownik musi kliknąć **„Kontynuuj mimo to"** lub **„Anuluj"** przed dalszym procesowaniem.

---

## Architektura

```
Użytkownik wysyła temat
        │
        ▼
duplicate_check_node
        │
        ├─ collection.count() == 0 → brak wpisów → przejście do researcher
        │
        ├─ similarity < 0.85 → brak duplikatu → przejście do researcher
        │
        └─ similarity >= 0.85 → interrupt(payload) → HITL_WARNING
                                        │
                        ┌───────────────┴───────────────┐
                        │                               │
              "Kontynuuj mimo to"                   "Anuluj"
              action="approve"                   action="reject"
                        │                               │
              duplicate_override=True        duplicate_override=False
                        │                               │
                   researcher                          END
```

---

## Zmodyfikowane pliki

### `bond/graph/nodes/duplicate_check.py` (istniejący, bez zmian)

Węzeł był już zaimplementowany. Pełna implementacja:

- Pobiera kolekcję `bond_metadata_log_v1` z ChromaDB (`get_or_create_metadata_collection()`).
- Jeśli kolekcja pusta → zwraca `{"duplicate_match": None, "duplicate_override": None}`.
- Wykonuje `collection.query(query_texts=[topic], n_results=1)` — top-1 wynik.
- Konwertuje odległość ChromaDB na podobieństwo: `similarity = 1.0 - distance`.
- Jeśli `similarity < settings.duplicate_threshold` → brak duplikatu.
- Jeśli `similarity >= settings.duplicate_threshold` → wywołuje `interrupt()` z payloadem:

```python
interrupt({
    "checkpoint": "duplicate_check",
    "type": "approve_reject",
    "warning": "Wykryto podobny temat",
    "existing_title": match_meta.get("title", "Unknown"),
    "existing_date": match_meta.get("published_date", "Unknown"),
    "similarity_score": round(similarity, 3),
})
```

- Parsuje wartość wznowienia obsługując zarówno `bool` jak i `dict`:

```python
"duplicate_override": proceed.get("action") == "approve"
    if isinstance(proceed, dict)
    else bool(proceed),
```

### `bond/config.py` (istniejący, bez zmian)

```python
duplicate_threshold: float = 0.85
```

Konfigurowalne przez zmienną środowiskową `DUPLICATE_THRESHOLD`.

### `bond/store/chroma.py` (istniejący, bez zmian)

Kolekcja `bond_metadata_log_v1` z modelem embeddinów `paraphrase-multilingual-MiniLM-L12-v2` (cosine). Funkcja `add_topic_to_metadata_collection()` wywoływana przez `save_metadata_node` po zatwierdzeniu artykułu.

### `bond/graph/graph.py` (istniejący, bez zmian)

Routing po `duplicate_check`:

```python
def _route_after_duplicate_check(state: BondState) -> str:
    if state.get("duplicate_override") is False:
        return END
    return "researcher"
```

### `frontend/src/store/chatStore.ts` ← **ZMIANA**

Rozszerzono typ `HitlPause` o pola specyficzne dla duplikatów:

```typescript
export type HitlPause = {
    checkpoint_id: string;
    type: string;
    iterations_remaining?: number;
    // Duplicate check specific fields (checkpoint_id === "duplicate_check")
    warning?: string;
    existing_title?: string;
    existing_date?: string;
    similarity_score?: number;
} | null;
```

### `frontend/src/hooks/useStream.ts` ← **ZMIANA**

Rozszerzono `HitlPauseSchema` o pola duplikatu, żeby nie były odcinane przez Zod przy deserializacji:

```typescript
const HitlPauseSchema = z.object({
    checkpoint_id: z.string(),
    type: z.string(),
    iterations_remaining: z.number().optional(),
    // Duplicate check fields
    warning: z.string().optional(),
    existing_title: z.string().optional(),
    existing_date: z.string().optional(),
    similarity_score: z.number().optional(),
});
```

Zaktualizowano wywołanie `store.setHitlPause()` w celu przekazania wszystkich pól:

```typescript
store.setHitlPause({
    checkpoint_id: result.data.checkpoint_id,
    type: result.data.type,
    iterations_remaining: result.data.iterations_remaining,
    warning: result.data.warning,
    existing_title: result.data.existing_title,
    existing_date: result.data.existing_date,
    similarity_score: result.data.similarity_score,
});
```

### `frontend/src/components/CheckpointPanel.tsx` ← **ZMIANA**

Dodano osobną gałąź renderowania dla `checkpoint_id === "duplicate_check"`:

- Żółty panel ostrzeżenia z ikoną `AlertTriangle`.
- Wyświetla: tytuł istniejącego artykułu, datę publikacji, procentowe podobieństwo.
- Przycisk **„Kontynuuj mimo to"** (amber) → `resumeStream(threadId, "approve", null, persistThreadId)`.
- Przycisk **„Anuluj"** (czerwony outline) → `resumeStream(threadId, "reject", null, persistThreadId)`.

---

## Przepływ danych end-to-end

### Wykrycie duplikatu

1. Użytkownik wpisuje temat → `POST /api/chat/stream`.
2. Graf wchodzi w `duplicate_check_node`.
3. ChromaDB zwraca top-1 wynik z odległością cosinus.
4. `similarity = 1.0 - distance >= 0.85` → wywołanie `interrupt(payload)`.
5. Graf zatrzymuje się; `aget_state().next = ["duplicate_check"]`.
6. `get_chat_history()` iteruje `state_snapshot.tasks[].interrupts` → buduje `hitlPause` ze wszystkimi polami.
7. Backend emituje SSE: `stage: idle` → `hitl_pause: {checkpoint_id: "duplicate_check", ...}`.
8. Frontend deserializuje pola przez `HitlPauseSchema` → `store.setHitlPause(...)`.
9. `CheckpointPanel` wykrywa `isDuplicateCheck === true` → renderuje panel ostrzeżenia.

### Kontynuacja mimo ostrzeżenia

1. Użytkownik klika **„Kontynuuj mimo to"**.
2. `resumeStream(threadId, "approve", null)` → `POST /api/chat/resume` z `{action: "approve"}`.
3. Backend buduje `Command(resume={"action": "approve"})`.
4. `duplicate_check_node` wznawia z `proceed = {"action": "approve"}`.
5. `duplicate_override = True` → `_route_after_duplicate_check` → `researcher`.
6. Pipeline kontynuuje normalnie.

### Anulowanie

1. Użytkownik klika **„Anuluj"**.
2. `resumeStream(threadId, "reject", null)` → `POST /api/chat/resume` z `{action: "reject"}`.
3. `proceed.get("action") == "approve"` → False → `duplicate_override = False`.
4. `_route_after_duplicate_check` → `END`.
5. Frontend otrzymuje `done` → `stage: done`.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Węzeł LangGraph sprawdza podobieństwo cosinusowe tematu do Metadata Log | ✅ `duplicate_check_node` używa ChromaDB `bond_metadata_log_v1` z cosine distance |
| Próg `DUPLICATE_THRESHOLD = 0.85` | ✅ `settings.duplicate_threshold = 0.85` (konfigurowalne przez `.env`) |
| Graf przechodzi do HITL_WARNING przy wykryciu duplikatu | ✅ `interrupt()` zatrzymuje graf; frontend renderuje panel ostrzeżenia |
| Użytkownik widzi informacje o duplikacie | ✅ Panel pokazuje tytuł, datę publikacji i % podobieństwa |
| Przycisk „Kontynuuj mimo to" kontynuuje pipeline | ✅ `action="approve"` → `duplicate_override=True` → `researcher` |
| Przycisk „Anuluj" kończy pipeline | ✅ `action="reject"` → `duplicate_override=False` → `END` |

---

## Konwencja payloadu `hitl_pause` dla duplikatu

```json
{
  "checkpoint_id": "duplicate_check",
  "type": "approve_reject",
  "warning": "Wykryto podobny temat",
  "existing_title": "<tytuł istniejącego artykułu>",
  "existing_date": "<data publikacji>",
  "similarity_score": 0.923
}
```

> **Uwaga:** `get_chat_history` w `chat.py` automatycznie kopiuje wszystkie pola z `interrupt()` payload do `hitlPause` (z pominięciem `"checkpoint"`, `"type"`, `"instructions"`). Nie wymaga ręcznej modyfikacji backendu.
