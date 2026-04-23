# 48-SHADOW-ROUTING-SCAFFOLD Podsumowanie: UI — Routing i Scaffold widoku Shadow

**Data ukończenia:** 2026-04-23  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** UI — Routing i Scaffold widoku Shadow  
**Status:** ✅ Zakończone

---

## Cel

Wizualne i logiczne oddzielenie trybu analizy (Shadow) od trybu tworzenia artykułów (Author).

- `ModeToggle` zsynchronizowany z globalnym stanem Zustand (`chatStore.mode`) i sessionStorage — zmiana trybu aktualizuje router, store i storage atomowo.
- Dedykowana trasa `/shadow` renderuje `ShadowPanel` — izolowany kontener z własnym przepływem UI.
- Szkielet dwukolumnowy: widok wejściowy (Tekst do analizy) + widok porównawczy (Tekst oryginalny z adnotacjami / Wersja poprawiona).

---

## Architektura

```
Layout (layout.tsx)
  ├─ <header>
  │     └─ ModeToggle
  │           ├─ Switch (checked = pathname === "/shadow")
  │           ├─ onCheckedChange → persistMode(mode) + router.push(url)
  │           └─ useEffect(isShadow) → persistMode — sync przy nawigacji wstecz/przód
  │
  └─ <main> → SessionProvider → {children}
        ├─ "/" → page.tsx  (Author: StageProgress + ChatInterface + EditorPane)
        └─ "/shadow" → shadow/page.tsx → <ShadowPanel />

persistMode (useSession.ts)
  ├─ sessionStorage.setItem("bond_mode", mode)
  └─ useChatStore.setMode(mode)   ← Zustand global state

ShadowPanel (components/ShadowPanel.tsx)
  ├─ [faza 1] Widok wejściowy
  │     └─ Textarea + Button "Analizuj styl"
  │           └─ startStream(text, threadId, "shadow", onThreadId)
  │
  └─ [faza 2] Widok porównawczy (gdy originalText !== "")
        ├─ Status bar (Loader / "Analiza zakończona · N adnotacji" / "Nowy tekst")
        ├─ Kolumna L: AnnotationList  (w-64, karty adnotacji, "Zastosuj wszystkie")
        ├─ Kolumna Ś: Tekst oryginalny z <mark> spanami (kliknięcie → scroll)
        └─ Kolumna P: Wersja poprawiona (textarea edytowalna / skeleton podczas streamingu)
```

---

## Zaimplementowane pliki

### `src/components/ModeToggle.tsx`

Integracja z Zustand przez `useSession().persistMode`:

```tsx
const handleToggle = (checked: boolean) => {
    persistMode(checked ? "shadow" : "author"); // → chatStore.setMode + sessionStorage
    router.push(checked ? "/shadow" : "/");
};

// Synchronizacja przy nawigacji wstecz/przód lub bookmarku
useEffect(() => {
    persistMode(isShadow ? "shadow" : "author");
}, [isShadow]);
```

Wizualnie: `Switch` + etykiety Autor/Cień + `Badge` z aktywnym trybem.

---

### `src/hooks/useSession.ts`

`persistMode` — atomowa operacja zmiany trybu:

```ts
const persistMode = (newMode: "author" | "shadow") => {
    sessionStorage.setItem(MODE_KEY, newMode);   // przetrwa odświeżenie strony
    setMode(newMode);                             // chatStore.mode ← Zustand
};
```

Przywracanie przy starcie (mount `SessionProvider`):
```ts
const storedMode = sessionStorage.getItem(MODE_KEY);
if (storedMode === "author" || storedMode === "shadow") {
    setMode(storedMode);
}
```

---

### `src/store/chatStore.ts`

Pole `mode` i akcja `setMode` w Zustand:

```ts
interface ChatStore {
    mode: "author" | "shadow";
    setMode: (mode: "author" | "shadow") => void;
    // ...
}
```

---

### `src/app/shadow/page.tsx`

Trasa Next.js App Router — renderuje `ShadowPanel` bezpośrednio:

```tsx
import { ShadowPanel } from "@/components/ShadowPanel";

export default function ShadowPage() {
  return <ShadowPanel />;
}
```

---

### `src/components/ShadowPanel.tsx`

Dwufazowy szkielet — kluczowy warunek `if (originalText)` steruje widokiem:

#### Faza 1 — Widok wejściowy (brak `originalText`)

```
┌──────────────────────────────────────┐
│         Tryb Cień                    │
│  [Wklej tekst do analizy...        ] │
│  (Textarea, min-h-[200px])           │
│                      [Analizuj styl] │
│  ⌘+Enter aby wysłać                 │
└──────────────────────────────────────┘
```

- Wycentrowany panel `max-w-2xl`
- `⌘+Enter` obsługiwany przez `onKeyDown`
- Przycisk blokowany gdy `isStreaming` lub pusty input

#### Faza 2 — Widok porównawczy (po ustawieniu `originalText`)

```
┌─ Status bar ─────────────────────────────────────────────────────────────┐
│  [Loader / "Analiza zakończona · N adnotacji"]         [Nowy tekst ↺]   │
├─ AnnotationList (w-64) ──┬─ Tekst oryginalny ─┬─ Wersja poprawiona ────┤
│  [ann_001]               │  Tekst z            │  <textarea>             │
│  reason...               │  <mark> spanami     │  edytowalny po          │
│  original → replacement  │  klikalnymi         │  zakończeniu streamingu │
│  [ann_002]               │                     │  (skeleton podczas)     │
│  ...                     │                     │                         │
│  [Zastosuj wszystkie]    │                     │                         │
└──────────────────────────┴─────────────────────┴─────────────────────────┘
```

Kluczowe mechanizmy:
- `buildSegments(text, annotations)` — dzieli tekst na segmenty plain/annotation; pomija overlapping spany.
- `spanRefs` (`useRef<Record<string, HTMLElement>>`) — ref każdego `<mark>` dla `scrollIntoView`.
- `handleAnnotationClick(ann)` — ustawia `activeAnnotationId` + scroll do spana.
- `handleApplyAll()` — przywraca pełny AI-corrected text do edytowalnej kolumny.
- `useMemo` na `buildSegments` — przelicza tylko przy zmianie `originalText` / `annotations`, nie co każdy token streamingu.

---

### `src/store/shadowStore.ts`

Zustand store dedykowany trybowi Shadow:

```ts
interface ShadowStore {
  originalText: string;
  annotations: Annotation[];
  shadowCorrectedText: string;
  setOriginalText, setAnnotations, setShadowCorrectedText, resetShadow
}
```

Odizolowany od `chatStore` — reset `resetShadow()` nie czyści stanu autora.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Integracja ModeToggle z globalnym stanem aplikacji w Zustand | ✅ `ModeToggle` → `persistMode` → `chatStore.setMode` + sessionStorage; synchronizacja przez `useEffect` przy nawigacji wstecz/przód |
| Stworzenie szkieletu widoku dwukolumnowego (Tekst wejściowy / Wynik z adnotacjami) | ✅ Faza 1: Textarea input; Faza 2: trzy kolumny — adnotacje + tekst oryginalny (z markerami) + wersja poprawiona (edytowalna) |

---

## Decyzje projektowe

| Decyzja | Uzasadnienie |
|---------|--------------|
| Routing URL-based (`/shadow`) zamiast flagi w stanie | URL jest shareable / bookmarkable; nawigacja przeglądarki (wstecz/przód) działa bez dodatkowej logiki |
| `persistMode` w `useSession` zamiast bezpośredniego `setMode` w `ModeToggle` | Centralizacja logiki sessionStorage i Zustand w jednym miejscu; `ModeToggle` jest czystym komponentem UI |
| `useEffect(isShadow)` w `ModeToggle` | Zabezpiecza przed desynchronizacją store↔URL gdy użytkownik nawiguje przez historię przeglądarki zamiast klikać toggle |
| `if (originalText)` jako przełącznik faz zamiast osobnych tras | Animacja przejścia w obrębie jednej trasy; `/shadow` pozostaje stabilnym URL niezależnie od fazy |
| `useMemo` na `buildSegments` | Streaming draft aktualizuje `chatStore.draft` co każdy token — bez `useMemo` pełny rebuild segmentów co każdy token byłby zbędnym kosztem |
| `shadowStore` oddzielony od `chatStore` | Izolacja pozwala na `resetShadow()` bez utraty stanu sesji autora i vice versa |
| Trzy kolumny zamiast dwóch | Annotation sidebar jako osobna kolumna zapobiega zasłanianiu tekstu i umożliwia nawigację kliknięciem bez opuszczania widoku porównawczego |

---

## Weryfikacja

TypeScript — brak błędów kompilacji:

```bash
cd frontend && npx tsc --noEmit
# (brak outputu = sukces)
```

Manualne ścieżki weryfikacji:

- Toggle Autor → Cień: URL zmienia się na `/shadow`, `chatStore.mode === "shadow"`, sessionStorage zawiera `"bond_mode" = "shadow"` ✅
- Toggle Cień → Autor: URL wraca do `/`, `chatStore.mode === "author"` ✅
- Odświeżenie strony na `/shadow`: tryb przywrócony z sessionStorage, `ModeToggle` pokazuje Cień ✅
- Nawigacja wstecz po toggle: `useEffect(isShadow)` w `ModeToggle` synchronizuje store z nowym pathname ✅
- Pusta Textarea: przycisk "Analizuj styl" zablokowany ✅
- Po `startStream`: `originalText` ustawiony → przejście do widoku porównawczego ✅
- Kliknięcie karty adnotacji: highlight aktywnej karty + scroll do `<mark>` spana ✅
- "Zastosuj wszystkie": `draft` ← `shadowCorrectedText` ✅
- "Nowy tekst": `resetSession` + `resetShadow` → powrót do widoku wejściowego ✅
