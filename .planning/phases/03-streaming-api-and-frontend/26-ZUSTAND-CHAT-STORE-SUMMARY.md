# 26-ZUSTAND-CHAT-STORE Podsumowanie: Zarządzanie stanem – chatStore (Zustand)

**Data ukończenia:** 2026-04-01
**Faza:** 03 — Streaming API i Frontend
**Plan:** 26 — Zarządzanie stanem – Zustand
**Status:** ✅ Zakończone

---

## Cel

Implementacja `chatStore` (Zustand) do obsługi sesji czatu i streamingu SSE po stronie frontendu.

- Definicja centralnego stanu czatu: historia wiadomości, aktualny etap agenta, status streamingu.
- Akcje pozwalające na przyrostowe dodawanie tokenów do trwającego streamu (SSE).
- Obsługa błędów połączenia w stanie aplikacji (alerty systemowe, stan `error`).

---

## Architektura

```
useChatStore (Zustand)
│
├── Stan sesji
│   ├── threadId          — identyfikator wątku LangGraph
│   ├── mode              — "author" | "shadow"
│   └── messages[]        — historia wiadomości (user / assistant)
│
├── Stan agenta
│   ├── stage             — bieżący etap: idle | research | structure | writing | done | error
│   ├── stageStatus       — mapa etap → "pending" | "running" | "complete" | "error"
│   └── hitlPause         — payload przerwania HITL (null gdy brak)
│
├── Stan streamingu
│   ├── isStreaming        — flaga aktywnego streamu
│   ├── draft             — bieżący tekst roboczy (akumulowany przez appendDraftToken)
│   ├── lastEventId       — ID ostatniego zdarzenia SSE (do reconnect)
│   └── activeController  — AbortController aktywnego połączenia
│
└── Obsługa błędów
    └── systemAlert       — komunikat błędu wyświetlany użytkownikowi
```

---

## Zmodyfikowane pliki

### `frontend/src/store/chatStore.ts`

Pełna definicja store'u opartego na Zustand (`create<ChatStore>`).

#### Typy

```typescript
export type Stage = "idle" | "research" | "structure" | "writing" | "done" | "error";
export type StageStatus = "pending" | "running" | "complete" | "error";

export interface ChatMessage {
    role: "user" | "assistant";
    content: string;
}

export type HitlPause = {
    checkpoint_id: string;
    type: string;
    iterations_remaining?: number;
    warning?: string;
    existing_title?: string;
    existing_date?: string;
    similarity_score?: number;
} | null;
```

#### Stan (state)

| Pole | Typ | Opis |
|---|---|---|
| `mode` | `"author" \| "shadow"` | Aktywny tryb czatu |
| `threadId` | `string \| null` | ID wątku LangGraph |
| `stage` | `Stage` | Bieżący etap pipeline'u |
| `stageStatus` | `Record<Stage, StageStatus>` | Status każdego etapu |
| `draft` | `string` | Akumulowany tekst roboczy |
| `messages` | `ChatMessage[]` | Historia wiadomości |
| `hitlPause` | `HitlPause` | Payload punktu przerwania HITL |
| `isStreaming` | `boolean` | Czy stream jest aktywny |
| `lastEventId` | `string \| undefined` | ID ostatniego SSE (do reconnect) |
| `systemAlert` | `string \| undefined` | Komunikat błędu dla użytkownika |
| `activeController` | `AbortController \| null` | Kontroler bieżącego połączenia |

#### Akcje

| Akcja | Opis |
|---|---|
| `appendDraftToken(token)` | Dodaje token do `draft` (akumulacja streamu) |
| `setDraft(draft)` | Nadpisuje cały draft (np. shadow correction) |
| `addMessage(msg)` | Dodaje wiadomość do historii |
| `setStage(stage, status)` | Ustawia etap i jego status |
| `setStreaming(v)` | Ustawia flagę aktywnego streamu |
| `setHitlPause(pause)` | Ustawia / czyści payload HITL |
| `setSystemAlert(alert)` | Ustawia / czyści komunikat błędu |
| `setLastEventId(id)` | Zapisuje ID zdarzenia SSE |
| `createController()` | Tworzy nowy AbortController, anuluje poprzedni; zwraca signal |
| `abortController()` | Anuluje bieżące połączenie i czyści kontroler |
| `resetSession()` | Zeruje cały stan (nowa sesja) |

---

## Obsługa błędów połączenia

Błędy połączenia są obsługiwane na trzech poziomach:

### 1. Zdarzenie `error` z serwera (SSE)
`useStream.ts` dekoduje event `error` ze strumienia i wywołuje:
```typescript
store.setStage(currentStage, "error");
store.addMessage({ role: "assistant", content: `Error: ${errorMessage}` });
store.setStreaming(false);
```

### 2. Nieoczekiwane zerwanie połączenia (retry loop)
`fetchWithRetry` w `useStream.ts` wykrywa brak terminalnego zdarzenia i retryuje do `MAX_RETRIES=3` razy, informując użytkownika przez:
```typescript
store.setSystemAlert(`Połączenie zerwane. Próbuję ponownie (${attempt}/${MAX_RETRIES})...`);
```

Po wyczerpaniu prób:
```typescript
store.setSystemAlert(`[Błąd krytyczny]: Nie udało się nawiązać stabilnego połączenia...`);
store.setStreaming(false);
store.setStage(currentStage, "error");
```

### 3. AbortController — intencjonalne przerwanie
`abortController()` czyści stan bez oznaczenia błędu:
```typescript
abortController: () => {
    const controller = get().activeController;
    if (controller) controller.abort();
    set({ activeController: null, isStreaming: false });
}
```

---

## Przepływ addToken — akumulacja streamu

```
SSE: {type: "token", data: "<fragment>"}
        │
        ▼
useStream.ts: store.appendDraftToken(tokenContent)
        │
        ▼
chatStore: set((s) => ({ draft: s.draft + token }))
        │
        ▼
EditorPane.tsx: draft ze store → wyświetlony na żywo
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Definicja chatStore (historia wiadomości, aktualny status agenta) | ✅ `messages[]`, `stage`, `stageStatus`, `hitlPause` — pełna definicja w store'ze |
| Akcje do dodawania tokenów do trwającego streamu | ✅ `appendDraftToken(token)` akumuluje `draft`; wywoływana przez `useStream.ts` przy każdym zdarzeniu `token` |
| Obsługa błędów połączenia w stanie aplikacji | ✅ `systemAlert`, `setSystemAlert`; `setStage(..., "error")`; retry loop w `fetchWithRetry` |

---

## Integracja

Store jest konsumowany przez:

- `useStream.ts` — główny konsument: zapisuje tokeny, etapy, błędy, kontroler
- `ChatInterface.tsx` — wyświetla wiadomości i status streamingu
- `StageProgress.tsx` — odczytuje `stage` i `stageStatus`
- `CheckpointPanel.tsx` — odczytuje i reaguje na `hitlPause`
- `EditorPane.tsx` — wyświetla `draft` aktualizowany na żywo
- `SessionProvider.tsx` — odczytuje `threadId` i zarządza sesją
