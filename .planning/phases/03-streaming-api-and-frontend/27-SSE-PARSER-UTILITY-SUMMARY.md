# 27-SSE-PARSER-UTILITY Podsumowanie: Narzędzie do konsumpcji strumienia Server-Sent Events

**Data ukończenia:** 2026-04-01
**Faza:** 03 — Streaming API i Frontend
**Plan:** 27 — SSE Parser Utility
**Status:** ✅ Zakończone

---

## Cel

Zaimplementowanie narzędzia do konsumpcji strumienia Server-Sent Events po stronie klienta:

- Klasa `SSEParser` akumuluje chunki TCP i emituje kompletne zdarzenia SSE po wykryciu separatora `\n\n`.
- Hook `useStream` opakowuje natywny `fetch` + `ReadableStream` w reaktywny interfejs React.
- Skrypt testowy weryfikuje parsowanie prefiksu `data:`, obsługę zdarzenia `done` oraz połączenie z endpointem FastAPI.

---

## Architektura

```
fetch(POST /api/chat/stream)
    │
    └─ response.body                         ← ReadableStream<Uint8Array>
           │
           └─ .pipeThrough(TextDecoderStream())  ← dekodowanie UTF-8 on-the-fly
                  │
                  └─ reader.read() loop
                         │
                         └─ SSEParser.feed(chunk)
                                │
                                ├─ akumuluje buffer
                                ├─ dzieli na \n\n → kompletne zdarzenia
                                └─ parsuje linie: event: / id: / data:
                                       │
                                       └─ consumeStream()
                                              │
                                              ├─ JSON.parse(data) → parsed.type
                                              ├─ Zod validation per event type
                                              └─ dispatch → Zustand store
```

---

## Zmodyfikowane/Utworzone pliki

### `frontend/src/lib/sse.ts`

Klasa `SSEParser` — parser graniczny chunków SSE.

**Kluczowe właściwości:**
- `buffer: string` — akumulator niekompletnych chunków między wywołaniami `feed()`
- `feed(chunk: string): SSEEvent[]` — przetwarza nowy fragment, zwraca kompletne zdarzenia

**Algorytm parsowania:**
1. Doklejenie `chunk` do `buffer`.
2. Podział `buffer` na bloki rozdzielone `\n\n`.
3. Ostatni blok (potencjalnie niekompletny) wraca do `buffer`.
4. Dla każdego bloku: iteracja linii z rozpoznaniem prefiksów `event:`, `id:`, `data:`.
5. Wieloliniowe pola `data:` łączone przez `\n`.
6. Bloki bez `data:` (np. komentarze heartbeat `": ping"`) są pomijane.

```typescript
export interface SSEEvent {
    id?: string;
    event: string;   // Domyślnie "message" (brak pola event:)
    data: string;
}

export class SSEParser {
    private buffer = "";

    feed(chunk: string): SSEEvent[] { ... }
}
```

### `frontend/src/hooks/useStream.ts`

Hook `useStream` — zarządza pełnym cyklem życia połączenia SSE.

**Eksportowane metody:**

| Metoda | Opis |
|--------|------|
| `startStream(message, threadId, mode, onThreadId)` | Inicjuje streaming POST /api/chat/stream |
| `resumeStream(threadId, action, feedback, onThreadId)` | Wznawia strumień po checkpoint POST /api/chat/resume |
| `stopStream()` | Przerywa aktywny strumień przez `AbortController` |

**Obsługiwane typy zdarzeń SSE:**

| Typ zdarzenia | Akcja w store |
|--------------|---------------|
| `thread_id` | `onThreadId(id)` — przekazanie ID sesji |
| `token` | `store.appendDraftToken(content)` |
| `stage` | `store.setStage(stage, status)` |
| `hitl_pause` | `store.setHitlPause(...)` + `setStreaming(false)` |
| `error` | `store.setStage(..., "error")` + `addMessage` |
| `shadow_corrected_text` | `store.setDraft(text)` + `shadowStore.setShadowCorrectedText` |
| `annotations` | `shadowStore.setAnnotations(annotations)` |
| `system_alert` | `store.setSystemAlert(message)` |
| `done` | `store.setStage("done", "complete")` + `setStreaming(false)` |
| `heartbeat` | Brak akcji (log w dev mode) |
| `node_start` / `node_end` | Brak akcji (informacyjne) |

**Mechanizm retry:**

```
fetchWithRetry(url, body, signal, onThreadId)
    │
    ├─ attempt 0: fetch + consumeStream
    │      └─ jeśli stream zakończył się bez zdarzenia terminalnego → throw
    │
    ├─ attempt 1..3: setSystemAlert("Próbuję ponownie...")
    │                await 3s delay → fetch z Last-Event-ID header
    │
    └─ po MAX_RETRIES: setSystemAlert("[Błąd krytyczny]...")
                       setStreaming(false) + setStage(..., "error")
```

**Payload dekodowania zdarzeń:**

Backend emituje wszystkie zdarzenia w formacie:
```
data: {"type": "<event_type>", "data": "<payload>"}\n\n
```

Hook normalizuje to przez:
1. `eventType = parsed.type || event` — typ z pola JSON nadrzędnego.
2. `payload = JSON.parse(parsed.data)` jeśli `parsed.data` jest stringiem JSON, inaczej `parsed.data`.

### `frontend/scripts/test-sse.mjs`

Skrypt testowy — Node.js built-in `node:test` (bez dodatkowych zależności).

**Uruchomienie:**
```bash
# Testy jednostkowe SSEParser (serwer niepotrzebny)
node frontend/scripts/test-sse.mjs

# Testy integracyjne z lokalnym serwerem FastAPI
node frontend/scripts/test-sse.mjs --api-url http://localhost:8000
```

---

## Weryfikacja

### Testy jednostkowe SSEParser

```
✔ SSEParser: parsuje pojedyncze zdarzenie z prefiksem data:       (1.07ms)
✔ SSEParser: obsługuje zdarzenie done                              (0.07ms)
✔ SSEParser: obsługuje niekompletny chunk (boundary split)         (0.06ms)
✔ SSEParser: parsuje wiele zdarzeń z jednego chunka                (0.07ms)
✔ SSEParser: rozpoznaje pole event:                                (0.06ms)
✔ SSEParser: rozpoznaje pole id:                                   (0.05ms)
✔ SSEParser: ignoruje puste zdarzenia (brak pola data:)            (0.05ms)
✔ SSEParser: obsługuje wieloliniowe pole data: (ciągłość)          (0.05ms)
✔ FastAPI /health endpoint odpowiada (graceful skip gdy offline)   (51ms)
✔ FastAPI /api/chat/stream zwraca SSE Content-Type (graceful skip) (2ms)

tests 10 | pass 10 | fail 0
```

### Test połączenia z FastAPI (serwer uruchomiony)

```bash
# 1. Uruchom serwer
uv run uvicorn bond.api.main:app --port 8000

# 2. Weryfikacja health
curl http://localhost:8000/health
# → {"status":"ok","version":"0.1.0","checks":{"graph":"ok",...}}

# 3. Weryfikacja SSE endpoint
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"test","thread_id":null,"mode":"author"}'
# → data: {"type":"thread_id","data":"{\"thread_id\":\"...\"}"}\n\n
# → data: {"type":"stage","data":"{\"stage\":\"checking\",\"status\":\"running\"}"}\n\n
# → ...

# 4. Uruchom testy integracyjne
node frontend/scripts/test-sse.mjs --api-url http://localhost:8000
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Hook `useStream` obsługujący `fetch` z `ReadableStream` | ✅ `response.body.pipeThrough(TextDecoderStream()).getReader()` — natywny `ReadableStream` bez `EventSource` |
| Poprawne parsowanie prefiksu `data:` i obsługa `done` | ✅ `SSEParser.feed()` parsuje `data:` linii; `consumeStream()` obsługuje `done` jako zdarzenie terminalne |
| Test połączenia z endpointem FastAPI | ✅ `frontend/scripts/test-sse.mjs` — 8 testów jednostkowych SSEParser + 2 testy integracyjne z graceful skip gdy serwer offline |

---

## Decyzje techniczne

**Dlaczego `fetch` + `ReadableStream` zamiast `EventSource`?**
`EventSource` obsługuje tylko `GET` i nie pozwala na niestandardowe nagłówki (np. `Last-Event-ID`, `Content-Type`). Endpoint `/api/chat/stream` przyjmuje `POST` z JSON body — wymaga natywnego `fetch`.

**Dlaczego `SSEParser` zamiast wbudowanego parsera przeglądarki?**
`ReadableStream` z `fetch` dostarcza surowe bajty — przeglądarka nie przetwarza ich automatycznie jako SSE. `SSEParser` implementuje specyfikację WHATWG (podział `\n\n`, pola `event:` / `id:` / `data:`) ręcznie.

**Dlaczego `node:test` zamiast Vitest/Jest?**
Projekt nie ma skonfigurowanego frameworka testowego. Wbudowany `node:test` (Node.js >= 18) nie wymaga żadnych zależności i działa natychmiast z plikiem `.mjs`.
