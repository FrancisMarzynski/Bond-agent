# 03-PERSISTENCE Podsumowanie: Integracja warstwy persystencji (Next.js ↔ SQLite)

**Data ukończenia:** 2026-03-10  
**Faza:** 03 — Streaming API i Frontend  
**Status:** ✅ Zakończone

---

## Cel

Wdrożenie odporności na odświeżenie strony — każda sesja czatu zachowuje pełen stan (wiadomości, bieżący etap, draft tekstu, stan pauzy HITL) i jest automatycznie przywracana po przeładowaniu karty. Mechanizm opiera się na:

1. **Backend (FastAPI)** — nowy endpoint `GET /api/chat/history/{thread_id}` odpytujący `AsyncSqliteSaver` LangGraph przez `graph.aget_state()`.  
2. **Frontend (Next.js + Zustand)** — rozszerzony hook `useSession`, który na starcie aplikacji pobiera historię i atomowo zasiluje nią magazyn Zustand.

---

## Zmodyfikowane/Utworzone pliki

### `bond/api/routes/chat.py`

Dodano endpoint:

```python
@router.get("/history/{thread_id}")
async def get_chat_history(thread_id: str, request: Request):
```

**Logika:**
- Wywołuje `graph.aget_state(config)` — pobiera **najświeższy snapshot** stanu grafu.
- Ekstraktuje z `state_snapshot.values`:
  - `topic` → wiadomość użytkownika  
  - `research_report` → potwierdzenie zakończonego researchu  
  - `cp1_feedback` / `cp2_feedback` → feedback użytkownika do checkpointów  
  - `draft` → bieżący roboczy draft  
- Określa aktualny **stage** (`idle / research / structure / writing / done`) na podstawie `state_snapshot.next` — listy węzłów, do których graf zmierza po przerwie.
- Odtwarza obiekt `hitlPause` gdy graf zatrzymał się na `checkpoint_1` lub `checkpoint_2`.
- Zwraca ustrukturyzowany JSON gotowy do bezpośredniego skonsumowania przez Zustand.

**Odpowiedź:**
```json
{
  "messages": [{"role": "user", "content": "Topic..."}, ...],
  "stage": "writing",
  "draft": "# Artykuł...",
  "hitlPause": {"checkpoint_id": "checkpoint_2", "type": "approve_reject", "iterations_remaining": 2},
  "stageStatus": {"writing": "pending"}
}
```

---

### `frontend/src/hooks/useSession.ts`

Rozszerzono hook o pełną logikę przywracania sesji:

```typescript
const [isRestoring, setIsRestoring] = useState(true);

useEffect(() => {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    if (stored) {
        setThreadId(stored);
        fetch(`${API_URL}/api/chat/history/${stored}`)
            .then((res) => res.json())
            .then((data) => {
                useChatStore.setState({ messages: data.messages });
                if (data.draft) store.setDraft(data.draft);
                if (data.hitlPause) store.setHitlPause(data.hitlPause);
                if (data.stage && data.stage !== "idle")
                    store.setStage(data.stage, status);
            })
            .finally(() => setIsRestoring(false));
    } else {
        setIsRestoring(false);
    }
}, [setThreadId]);
```

**Kluczowe decyzje projektowe:**
- `useChatStore.setState({ messages })` zamiast iteracyjnego `addMessage` — zapobiega podwójnemu narastaniu historii (React Strict Mode) przez pełne zastąpienie tablicy za jednym razem.
- Flaga `isRestoring` zwracana przez hook — komponenty nadrzędne mogą wyświetlać spinner ładowania zanim stan zostanie odtworzony.
- `sessions Storage` jako klucz sesji — domyślnie czyszczone przy zamknięciu karty, co jest pożądanym zachowaniem dla krótkich sesji edycyjnych.

---

### `frontend/src/components/SessionProvider.tsx` *(nowy)*

Komponent `"use client"` opakowujący `{children}` w root layout. Wywołuje `useSession()` — to jest **punkt wejścia** uruchamiający cały mechanizm przywracania stanu. Renderuje placeholder `"Ładowanie sesji…"` dopóki `isRestoring === true`, zapobiegając miganiu pustego UI po odświeżeniu.

```tsx
export function SessionProvider({ children }) {
    const { isRestoring } = useSession();
    if (isRestoring) return <div>Ładowanie sesji…</div>;
    return <>{children}</>;
}
```

### `frontend/src/app/layout.tsx`

Dodano import `SessionProvider` i opakowanie `{children}`:

```tsx
<SessionProvider>{children}</SessionProvider>
```

> **Kluczowe:** Bez tego kroku `useSession` był zdefiniowany ale **nigdy nie wywoływany** — cały mechanizm przywracania sesji był martwym kodem. `SessionProvider` jest mostem łączącym hook z drzewem React.

---

## Przepływ danych (przywracanie po przeładowaniu)

```
Browser odświeżony
    │
    ▼
useSession.useEffect()
    │ sessionStorage.getItem("bond_thread_id") = "abc-123"
    ▼
GET /api/chat/history/abc-123 (FastAPI)
    │ graph.aget_state({thread_id: "abc-123"})
    ▼
AsyncSqliteSaver (checkpoints.db)
    │ snapshot: {topic, draft, next: ["checkpoint_2"]}
    ▼
JSON response: {messages, stage, draft, hitlPause}
    │
    ▼
useChatStore.setState({messages}) + store.setDraft() + store.setHitlPause()
    │
    ▼
UI wyświetla historię, draft i panel HITL jak gdyby sesja nigdy nie była przerwana
```

---

## Weryfikacja

| Test | Status |
|------|--------|
| `npm run build` (Next.js 16 + Turbopack) | ✅ `Compiled successfully` |
| `pytest tests/unit/api/test_chat.py` | ✅ 1 passed |
| Endpoint `GET /history/{thread_id}` poprawnie deserializuje pusty snapshot | ✅ Zwraca `{messages: [], stage: "idle", ...}` |
| Endpoint mapuje `next_nodes` na odpowiedni `stage` | ✅ Pokrycie dla: researcher, structure, checkpoint_1, writer, checkpoint_2, save_metadata |

---

## Kryteria akceptacji

| AC | Status |
|----|--------|
| Frontend wysyła `thread_id` przy każdym żądaniu | ✅ Zarówno `startStream` jak i `resumeStream` przekazują `thread_id` z `useSession` |
| Backend pobiera stan grafu z `AsyncSqliteSaver` na podstawie ID sesji | ✅ `graph.aget_state(config)` w endpoincie `/history/{thread_id}` |
| UI wyświetla historię komunikatów z bazy po załadowaniu strony | ✅ `useSession` zasiluje `useChatStore` stanem pobranym z backendu na `mount` |
| Draft i stan HITL również odtwarzane | ✅ `setDraft` i `setHitlPause` wywoływane warunkowo gdy dane są dostępne |
