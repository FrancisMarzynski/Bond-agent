# 51-E2E-HARDENING-V2 Podsumowanie: Wznawianie SSE, Safety Cap grafu i Error Boundary

**Data ukończenia:** 2026-04-23  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 51 — End-to-End Hardening v2 (pre-1.0)  
**Status:** ✅ Zakończone

---

## Cel

Eliminacja krytycznych luk w odporności systemu przed wersją 1.0:

1. **AC1 – SSE Auto-Reconnect:** Automatyczne wznawianie połączenia przy krótkich przerwach sieci z wykładniczym backoffem i wizualnym wskaźnikiem reconnect.
2. **AC2 – Safety Cap (ochrona grafu):** Zabezpieczenie funkcji routingu przed nieskończonymi pętlami HITL jako warstwa defense-in-depth na poziomie grafu (poza istniejącymi hard caps w węzłach).
3. **AC3 – Error Boundary:** Globalny mechanizm przechwytywania błędów React renderujący czytelne komunikaty zamiast białego ekranu.

---

## Architektura zmian

```
┌─────────────────── Frontend ────────────────────────────────────────────┐
│                                                                          │
│  layout.tsx                                                              │
│    └─ <ErrorBoundary>          ← AC3: React class Error Boundary         │
│         └─ <SessionProvider>                                             │
│              └─ {children}                                               │
│                                                                          │
│  app/error.tsx                 ← AC3: Next.js route-level boundary       │
│  app/shadow/error.tsx          ← AC3: Shadow route boundary              │
│                                                                          │
│  useStream.ts                                                            │
│    └─ fetchWithRetry()                                                   │
│         ├─ MAX_RETRIES = 5 (było 3)                                      │
│         ├─ backoffDelay(attempt)  ← AC1: wykładniczy backoff + jitter    │
│         ├─ store.setReconnecting(true)  ← AC1: stan UI                   │
│         └─ Last-Event-ID header (już istniał)                            │
│                                                                          │
│  StageProgress.tsx                                                       │
│    ├─ <reconnecting banner>    ← AC1: widoczny wskaźnik wznawiania       │
│    └─ <systemAlert banner>     ← AC2: wyświetla hard_cap_message         │
│                                                                          │
│  chatStore.ts                                                            │
│    └─ isReconnecting: boolean  ← AC1: nowy stan                          │
└──────────────────────────────────────────────────────────────────────────┘

┌─────────────────── Backend ─────────────────────────────────────────────┐
│                                                                          │
│  bond/graph/graph.py                                                     │
│    ├─ _route_after_cp1()       ← AC2: guard cp1_iterations >= 10 → END  │
│    ├─ _route_after_cp2()       ← AC2: guard cp2_iterations >= 10 → END  │
│    └─ _route_after_shadow_checkpoint()  (już miał guard, zachowany)      │
│                                                                          │
│  Importy: _CP1_HARD_CAP=10, _CP2_HARD_CAP=10, _SHADOW_HARD_CAP=3       │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Zmodyfikowane / dodane pliki

### `bond/graph/graph.py` — Safety Cap w routingu (AC2)

**Problem przed zmianą:**  
Funkcje routingu `_route_after_cp1` i `_route_after_cp2` nie sprawdzały liczby iteracji. Jedyną linią obrony były węzły (`checkpoint_1_node`, `checkpoint_2_node`), które zwracają `Command(goto=END)` po osiągnięciu `HARD_CAP_ITERATIONS`. Gdyby z powodu błędu węzeł zwrócił zwykły dict zamiast `Command`, routing przekierowałby do kolejnej iteracji bez końca.

**Zmiana:**  
Importy przemianowane na aliasy (bez kolizji):

```python
# Przed:
from bond.graph.nodes.shadow_checkpoint import ..., HARD_CAP_ITERATIONS

# Po:
from bond.graph.nodes.checkpoint_1 import ..., HARD_CAP_ITERATIONS as _CP1_HARD_CAP
from bond.graph.nodes.checkpoint_2 import ..., HARD_CAP_ITERATIONS as _CP2_HARD_CAP
from bond.graph.nodes.shadow_checkpoint import ..., HARD_CAP_ITERATIONS as _SHADOW_HARD_CAP
```

Routing z guardem:

```python
def _route_after_cp1(state: BondState) -> str:
    # Safety cap: defense-in-depth za node-level Command(goto=END)
    if state.get("cp1_iterations", 0) >= _CP1_HARD_CAP:
        return END
    if state.get("cp1_approved"):
        return "writer"
    return "structure"

def _route_after_cp2(state: BondState) -> str:
    if state.get("cp2_iterations", 0) >= _CP2_HARD_CAP:
        return END
    if state.get("cp2_approved"):
        return "save_metadata"
    return "writer"
```

`_route_after_shadow_checkpoint` już miał analogiczny guard — zachowany bez zmian.

**Dlaczego nie wystarczał sam `recursion_limit=50`?**  
`GraphRecursionError` jest ostatecznym backstopem, ale powoduje zerwanie strumienia i SSE `error` event — nieoptymalne UX. Routing-level guard kończy pipeline przez normalną ścieżkę END, co pozwala na emisję `system_alert` z `hard_cap_message`.

---

### `frontend/src/store/chatStore.ts` — Nowy stan reconnect (AC1)

Dodano `isReconnecting: boolean` do interfejsu i inicjalnego stanu:

```typescript
isReconnecting: boolean;        // ← nowe
setReconnecting: (v: boolean) => void;  // ← nowa akcja
```

Resetowane w `resetSession()` razem z pozostałymi polami.

---

### `frontend/src/hooks/useStream.ts` — Wykładniczy backoff (AC1)

**Przed:** `MAX_RETRIES = 3`, płaskie opóźnienie `3000ms`.

**Po:**

```typescript
const MAX_RETRIES = 5;
const BASE_DELAY_MS = 1_000;
const MAX_DELAY_MS = 30_000;

function backoffDelay(attempt: number): number {
    const exponential = Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
    return exponential + Math.random() * 500; // jitter
}
```

Harmonogram opóźnień (bez jitter):

| Próba | Opóźnienie |
|-------|------------|
| 1     | ~1 s       |
| 2     | ~2 s       |
| 3     | ~4 s       |
| 4     | ~8 s       |
| 5     | ~16 s      |

`fetchWithRetry` zarządza stanem `isReconnecting`:

```typescript
// W pętli retry:
store.setReconnecting(true);
await new Promise(resolve => setTimeout(resolve, backoffDelay(attempt - 1)));

// Po sukcesie:
store.setReconnecting(false);

// Po wyczerpaniu prób lub intentional abort:
store.setReconnecting(false);
```

Header `Last-Event-ID` był już wysyłany — umożliwia serwerowi pomijanie już dostarczonych eventów przy reconnect (jeśli serwer obsługuje to w przyszłości).

---

### `frontend/src/components/StageProgress.tsx` — Bannery statusu (AC1 + AC2)

`StageProgress` rozszerzony o dwa nowe bannery powyżej stepperów:

```tsx
// AC1: Baner wznawiania połączenia
{isReconnecting && (
    <div className="...amber...">
        <RefreshCw className="animate-spin" />
        <span>Wznawianie połączenia SSE...</span>
    </div>
)}

// AC2: Baner alertów systemowych (hard cap, błędy krytyczne)
{systemAlert && !isReconnecting && (
    <div className="...amber...">
        <AlertTriangle />
        <span>{systemAlert}</span>
        <button onClick={() => setSystemAlert(undefined)}>×</button>
    </div>
)}
```

Warunek renderowania rozszerzony:

```tsx
// Przed: if (stage === "idle" && !isStreaming) return null;
// Po:
if (stage === "idle" && !isStreaming && !isReconnecting && !systemAlert) return null;
```

Dzięki temu `systemAlert` (np. `hard_cap_message` po zakończeniu pipeline) pozostaje widoczny nawet gdy `stage === "idle"`.

**Wcześniej `systemAlert` był ustawiany w store ale nigdzie nie renderowany.** Ten commit zamyka ten gap.

---

### `frontend/src/components/ErrorBoundary.tsx` — Nowy plik (AC3)

React class component (Error Boundaries wymagają klasy):

```tsx
export class ErrorBoundary extends Component<Props, State> {
    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        console.error("[ErrorBoundary] Uncaught render error:", error, info.componentStack);
    }

    render() {
        if (this.state.hasError) {
            return (
                // Dwa przyciski: "Spróbuj ponownie" (reset state) + "Odśwież stronę"
                <div>...</div>
            );
        }
        return this.props.children;
    }
}
```

Props:
- `children: ReactNode` — obowiązkowe
- `fallback?: ReactNode` — opcjonalny własny fallback UI

---

### `frontend/src/app/error.tsx` + `app/shadow/error.tsx` — Nowe pliki (AC3)

Next.js App Router route-level error boundaries — łapią błędy renderowania w `page.tsx` i komponentach potomnych podczas SSR i CSR:

```tsx
// error.tsx — "use client" wymagane przez Next.js
export default function Error({ error, reset }: ErrorProps) {
    useEffect(() => { console.error("[Route Error]", error); }, [error]);

    return (
        <div>
            <h2>Błąd strony</h2>
            <p>{error.message}</p>
            {error.digest && <code>ID: {error.digest}</code>}
            <button onClick={reset}>Spróbuj ponownie</button>
        </div>
    );
}
```

`reset()` — funkcja dostarczona przez Next.js, próbuje przerenderować segment bez pełnego odświeżenia.

---

### `frontend/src/app/layout.tsx` — Owinięcie ErrorBoundary (AC3)

```tsx
import { ErrorBoundary } from "@/components/ErrorBoundary";

// Przed:
<SessionProvider>{children}</SessionProvider>

// Po:
<ErrorBoundary>
    <SessionProvider>{children}</SessionProvider>
</ErrorBoundary>
```

`ErrorBoundary` jako Client Component może być zaimportowany do Server Component (`layout.tsx`) — Next.js App Router obsługuje to poprawnie.

---

## Warstwy ochrony — mapa kompletna

```
Błąd w renderowaniu React
    → ErrorBoundary (komponent)       ← AC3: "Spróbuj ponownie" / "Odśwież"
    → app/error.tsx (route)           ← AC3: Next.js reset()
    → app/shadow/error.tsx            ← AC3: Shadow route

Nieskończona pętla HITL (cp1/cp2)
    → checkpoint_N_node: Command(goto=END) + hard_cap_message  ← już istniało
    → _route_after_cpN: guard cp_iterations >= HARD_CAP → END  ← AC2: nowe
    → _RECURSION_LIMIT=50: GraphRecursionError → SSE error     ← już istniało

Hard cap osiągnięty → system_alert
    → StageProgress: baner z alertem + przycisk zamknięcia     ← AC2/AC1: nowe

Zerwanie SSE / chwilowa przerwa sieci
    → consumeStream: zwraca false (endedCleanly=false)          ← już istniało
    → fetchWithRetry: wykładniczy backoff (1s→2s→4s→8s→16s)   ← AC1: nowe
    → store.isReconnecting: true podczas oczekiwania           ← AC1: nowe
    → StageProgress: baner "Wznawianie połączenia SSE..."      ← AC1: nowe
    → po 5 próbach: systemAlert + stage=error                  ← usprawnione
```

---

## Kryteria akceptacji (AC)

| AC | Opis | Status | Implementacja |
|----|------|--------|---------------|
| AC1 | Automatyczne wznawianie SSE przy krótkich przerwach | ✅ | Wykładniczy backoff (1–16s), 5 prób, `isReconnecting` baner w UI |
| AC2 | Safety Cap dla grafu HITL (bez nieskończonych pętli) | ✅ | Guard w `_route_after_cp1/cp2` checking `cp_iterations >= HARD_CAP` → END |
| AC3 | Globalny Error Boundary z czytelnymi komunikatami | ✅ | `ErrorBoundary.tsx` w `layout.tsx` + `app/error.tsx` + `app/shadow/error.tsx` |

---

## Weryfikacja

```bash
# Python — importy i logika routingu
python -c "
from bond.graph.graph import _route_after_cp1, _route_after_cp2, _CP1_HARD_CAP, _CP2_HARD_CAP
from langgraph.graph import END
assert _route_after_cp1({'cp1_iterations': 10}) == END
assert _route_after_cp2({'cp2_iterations': 10}) == END
assert _route_after_cp1({'cp1_approved': True, 'cp1_iterations': 0}) == 'writer'
assert _route_after_cp2({'cp2_approved': True, 'cp2_iterations': 0}) == 'save_metadata'
print('All assertions passed')
"

# TypeScript — kompilacja bez błędów
cd frontend && npx tsc --noEmit
# Output: (brak błędów)
```

Obie weryfikacje przeszły pomyślnie.

---

## Stałe limitów HITL (pełna tabela po zmianach)

| Parametr | Wartość | Lokalizacja | Zachowanie |
|----------|---------|-------------|------------|
| `SOFT_CAP_ITERATIONS` (cp2) | 3 | `checkpoint_2.py` | Warning w payloadzie HITL |
| `HARD_CAP_ITERATIONS` (cp1, cp2) | 10 | `checkpoint_1.py`, `checkpoint_2.py` | `Command(goto=END)` + `hard_cap_message` |
| `HARD_CAP_ITERATIONS` (shadow) | 3 | `shadow_checkpoint.py` | `Command(goto=END)` + `hard_cap_message` |
| Guard w routing (cp1, cp2) | 10 | `graph.py` | **Nowe:** zwraca END jeśli iteracje przekroczone |
| Guard w routing (shadow) | 3 | `graph.py` | Już istniał |
| `_RECURSION_LIMIT` | 50 | `chat.py` | `GraphRecursionError` → SSE error (ostateczny backstop) |
| `MAX_RETRIES` (SSE) | 5 (było 3) | `useStream.ts` | **Nowe:** więcej prób z backoffem |
