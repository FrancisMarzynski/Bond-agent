# 49-ANNOTATION-LIST-INTERACTION Podsumowanie: Komponent AnnotationList i interakcja

**Data ukończenia:** 2026-04-23  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** UI — Komponent AnnotationList i interakcja  
**Status:** ✅ Zakończone

---

## Cel

Umożliwienie użytkownikowi wygodnego przeglądania i nawigacji po poprawkach agenta.

- `AnnotationList` renderuje listę kart adnotacji w panelu bocznym (w-64) obok kolumny tekstu oryginalnego.
- Kliknięcie karty → `scrollIntoView({ behavior: "smooth", block: "center" })` na odpowiednim `<mark>` spanie w tekście oryginalnym.
- Dwukierunkowa nawigacja: kliknięcie `<mark>` w tekście również aktywuje kartę w `AnnotationList`.

---

## Architektura

```
ShadowPanel (orchestrator)
  │
  ├─ state: activeAnnotationId (string | null)
  ├─ ref:   spanRefs { [ann.id]: HTMLElement | null }
  │
  ├─ handleAnnotationClick(ann)
  │     ├─ setActiveAnnotationId(ann.id)
  │     └─ spanRefs.current[ann.id]?.scrollIntoView({ behavior: "smooth", block: "center" })
  │
  ├─ [Column 1] AnnotationList
  │     props: annotations, activeId, onAnnotationClick, onApplyAll, isStreaming
  │     ├─ Skeleton loaders (isStreaming && annotations.length === 0)
  │     ├─ Annotation cards (ann.id → isActive gdy ann.id === activeId)
  │     │     ├─ Badge (ann.id — font-mono)
  │     │     ├─ reason  (line-clamp-3)
  │     │     └─ original_span → replacement diff (red/emerald, truncate)
  │     ├─ "Zastosuj wszystkie" (onApplyAll, visible gdy annotations.length > 0)
  │     └─ Empty state (! isStreaming && annotations.length === 0)
  │
  └─ [Column 2] Tekst oryginalny
        ├─ buildSegments(originalText, annotations) → Segment[]
        │     (memoised — przelicza tylko przy zmianie originalText lub annotations)
        └─ segments.map → <span> (plain) | <mark> (annotation)
              <mark>
                ref={(el) => spanRefs.current[ann.id] = el}
                onClick={() => handleAnnotationClick(ann)}
                title={ann.reason}
                className: inactive=amber-100 | active=amber-300
```

---

## Zaimplementowane pliki

### `src/components/AnnotationList.tsx`

Panel boczny z kartami adnotacji.

#### Props

```ts
interface AnnotationListProps {
  annotations: Annotation[];      // lista wszystkich adnotacji
  activeId: string | null;        // id aktywnej karty (wyróżnienie)
  onAnnotationClick: (annotation: Annotation) => void;
  onApplyAll: () => void;         // zastosuj pełną AI-corrected wersję
  isStreaming: boolean;
}
```

#### Stany renderowania

| Stan | Widok |
|------|-------|
| `isStreaming && annotations.length === 0` | 3 skeleton karty (`animate-pulse`) |
| `annotations.length > 0` | Karty adnotacji + przycisk "Zastosuj wszystkie" w nagłówku |
| `!isStreaming && annotations.length === 0` | "Brak adnotacji stylistycznych" (empty state) |

#### Karta adnotacji

```
┌─────────────────────────────┐
│ [ann_001]  ← Badge font-mono│
│ reason text...              │  line-clamp-3, text-xs
│ oryginalny_span → zamiana   │  red/emerald, truncate, max-w-[40%]
└─────────────────────────────┘
```

Aktywna karta: `bg-amber-50 border-amber-300 shadow-sm` (light) / `bg-amber-900/20 border-amber-700` (dark).

---

### `src/components/ShadowPanel.tsx` — mechanizm scroll

#### `spanRefs` — referencje do `<mark>` elementów

```tsx
const spanRefs = useRef<Record<string, HTMLElement | null>>({});

// Przypisywane podczas renderowania segmentów:
<mark
  ref={(el) => { spanRefs.current[seg.annotation.id] = el; }}
  onClick={() => handleAnnotationClick(seg.annotation)}
  ...
>
```

Refs są resetowane (`spanRefs.current = {}`) przy każdym nowym `handleSubmit` i `handleReset` — brak stale refs z poprzedniej analizy.

#### `handleAnnotationClick`

```tsx
const handleAnnotationClick = useCallback((ann: Annotation) => {
  setActiveAnnotationId(ann.id);
  const el = spanRefs.current[ann.id];
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}, []);
```

Wywołana z dwóch miejsc:
1. `AnnotationList` → kliknięcie karty (`onAnnotationClick`)
2. Tekst oryginalny → kliknięcie `<mark>` (`onClick`)

Dwukierunkowa nawigacja: obie akcje ustawiają ten sam `activeAnnotationId`, co wyróżnia zarówno kartę jak i span jednocześnie.

#### `buildSegments` — segmentacja tekstu

```tsx
const segments = useMemo(
  () => buildSegments(originalText, annotations),
  [originalText, annotations]
);
```

```
buildSegments(text, annotations):
  sorted = annotations.sort(by start_index asc)
  for ann in sorted:
    if ann.start_index < cursor: skip (overlapping)
    if ann.start_index > cursor: push { type: "text", content: text[cursor..start] }
    push { type: "annotation", annotation: ann, content: text[start..end] }
    cursor = ann.end_index
  if cursor < text.length: push { type: "text", content: text[cursor..] }
```

`useMemo` — przelicza tylko gdy `originalText` lub `annotations` się zmienią. Draft streaming nie triggeruje rebuild.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Renderowanie listy sugestii w panelu bocznym obok edytora | ✅ `AnnotationList` — w-64, border-r, scroll wewnętrzny; karty z ID, reason, diff original→replacement; skeleton podczas streamingu; empty state |
| Kliknięcie w adnotację powoduje scroll do odpowiedniego fragmentu w tekście oryginalnym | ✅ `handleAnnotationClick` → `spanRefs.current[ann.id].scrollIntoView({ behavior: "smooth", block: "center" })`; `<mark>` ref przypisany podczas renderowania segmentów |

---

## Decyzje projektowe

| Decyzja | Uzasadnienie |
|---------|--------------|
| `spanRefs` jako `useRef<Record<string, HTMLElement>>` zamiast `ref` per-segment | Jeden obiekt zamiast wielu `useRef` calls; dostęp O(1) po `ann.id` bez iteracji |
| `scrollIntoView({ block: "center" })` | `"start"` chowałby element za stałym nagłówkiem; `"center"` zapewnia pełną widoczność fragmentu |
| `buildSegments` zwraca typy `"text"` / `"annotation"` zamiast JSX | Oddziela logikę segmentacji od renderowania — łatwiejszy test jednostkowy segmentatora |
| `useMemo` na `buildSegments` | Streaming draft aktualizuje `chatStore.draft` co każdy token; bez memo każdy token triggerowałby rebuild segmentów |
| Pominięcie overlapping annotacji (`if ann.start_index < cursor: continue`) | LLM może zwrócić nachodzące spany — ciche pominięcie zamiast rzucania błędu |
| `line-clamp-3` na `reason` w karcie | Zachowuje stałą wysokość kart w sidebarze niezależnie od długości uzasadnienia |
| `max-w-[40%]` + `truncate` na diff | Przy długich spanach diff nie łamie layoutu karty; pełna wartość dostępna przez `title` |
| Aktywna karta wyróżniona kolorem bez przeniesienia fokusu | UX: użytkownik może wracać do listy i scrollować bez utraty pozycji w tekście |

---

## Weryfikacja

TypeScript — brak błędów kompilacji:

```bash
cd frontend && npx tsc --noEmit
# (brak outputu = sukces)
```

Manualne ścieżki weryfikacji:

- Po analizie: lista kart pojawia się w sidebarze z ID, reason, diff ✅
- `isStreaming && annotations.length === 0`: 3 skeleton karty animate-pulse ✅
- `!isStreaming && annotations.length === 0`: "Brak adnotacji stylistycznych" ✅
- Kliknięcie karty: karta zmienia tło na amber-50/amber-300; `<mark>` w tekście staje się amber-300; smooth scroll do spana ✅
- Kliknięcie `<mark>` w tekście: ta sama logika — aktywuje kartę w sidebarze ✅
- "Zastosuj wszystkie": `draft` ← `shadowCorrectedText` ✅
- "Nowy tekst" / nowy submit: `spanRefs.current = {}` — brak stale refs ✅
- Overlapping annotacje: pominięte cicho, pozostałe karty i spany działają poprawnie ✅
