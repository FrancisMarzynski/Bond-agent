# 15-ANNOTATION-LIST Podsumowanie: Komponent AnnotationList i interakcja

**Data ukończenia:** 2026-03-19
**Faza:** 03 — Streaming API i Frontend
**Status:** ✅ Zakończone

---

## Cel

Implementacja sidebara z listą kart adnotacji stylistycznych w trybie Cień. Karty wyświetlają powód zmiany i podgląd diff (oryginał → sugestia). Kliknięcie karty podświetla i przewija odpowiedni fragment tekstu oryginalnego. Przycisk "Zastosuj" przywraca pełną wersję poprawioną wygenerowaną przez AI.

---

## Zmodyfikowane/Utworzone pliki

### `frontend/src/components/AnnotationList.tsx` *(nowy)*
Sidebar z listą kart adnotacji:
- **Nagłówek:** etykieta "Adnotacje (N)" + przycisk "Zastosuj" (widoczny tylko gdy są adnotacje).
- **Karta adnotacji:** badge z ID (`ann_001`, ...) + reason (max 3 linie, `line-clamp-3`) + diff `original_span → replacement` (z ikoną `ChevronRight`).
- **Aktywna karta:** podświetlona kolorem `bg-amber-50 border-amber-300` (dark: `amber-900/20`).
- **Skeleton loaders:** 3 pulsujące bloki gdy `isStreaming && annotations.length === 0`.
- **Stan pusty:** komunikat "Brak adnotacji stylistycznych" po zakończeniu bez wyników.
- Szerokość: `w-64`, `border-r`, scroll wewnętrzny.

### `frontend/src/components/ShadowPanel.tsx` *(zmodyfikowany)*
Rozbudowany z 2-kolumnowego do 3-kolumnowego układu:
- **Kolumna 1 (lewa):** `<AnnotationList>` — sidebar adnotacji.
- **Kolumna 2 (środkowa):** Tekst oryginalny z podświetlonymi spanami adnotacji (`<mark>`). Kliknięcie marka aktywuje kartę i odwrotnie.
- **Kolumna 3 (prawa):** Edytowalny textarea z poprawioną wersją (bez zmian w logice).
- **`buildSegments()`:** helper dzielący tekst na segmenty `text` i `annotation` wg `start_index`/`end_index` — obsługuje nieaktualne/nakładające się spany.
- **`spanRefs`:** `useRef<Record<string, HTMLElement | null>>` mapujący `ann.id → <mark>` — umożliwia `scrollIntoView` przy kliknięciu karty.
- **Pasek statusu:** wyświetla `"Analiza zakończona · N adnotacji"` po zakończeniu.
- Reset (`handleReset`) czyści `activeAnnotationId` i `spanRefs`.

### `frontend/src/store/shadowStore.ts` *(rozbudowany)*
Dodane pola i akcje:
- `annotations: Annotation[]` — lista adnotacji z backendu.
- `shadowCorrectedText: string` — snapshot pełnej wersji poprawionej (źródło dla "Zastosuj wszystkie").
- `setAnnotations(annotations)`, `setShadowCorrectedText(text)` — settery.
- `resetShadow()` czyści wszystkie trzy pola.
- Wyeksportowany typ `Annotation` (reużywany przez AnnotationList i ShadowPanel).

### `frontend/src/hooks/useStream.ts` *(zmodyfikowany)*
Nowe case'y w `consumeStream`:
- `"shadow_corrected_text"` → `store.setDraft(text)` + `useShadowStore.getState().setShadowCorrectedText(text)`.
- `"annotations"` → `useShadowStore.getState().setAnnotations(annotations)`.

### `bond/api/routes/chat.py` *(zmodyfikowany)*
W `/stream`, przed wysłaniem `done`, gdy graf zakończył się bez HITL:
```python
st_values = state_snapshot.values
shadow_corrected = st_values.get("shadow_corrected_text") or ""
annotations = st_values.get("annotations") or []
if shadow_corrected:
    yield StreamEvent(type="shadow_corrected_text", data=json.dumps({"text": shadow_corrected}))
if annotations:
    yield StreamEvent(type="annotations", data=json.dumps(annotations))
yield StreamEvent(type="done", data="done")
```
Zdarzenia emitowane są dla WSZYSTKICH trybów (nie tylko shadow), ale pola są puste w trybie Autor — brak efektu ubocznego.

---

## Przepływ danych

```
shadow_annotate_node (backend)
    └─ zwraca: { annotations, shadow_corrected_text } → LangGraph state

chat.py /stream (po zakończeniu grafu)
    ├─ SSE: shadow_corrected_text → { text: "..." }
    ├─ SSE: annotations → [ { id, original_span, replacement, reason, start_index, end_index }, ... ]
    └─ SSE: done

useStream.ts consumeStream()
    ├─ "shadow_corrected_text" → chatStore.setDraft(text) + shadowStore.setShadowCorrectedText(text)
    ├─ "annotations"           → shadowStore.setAnnotations(annotations)
    └─ "done"                  → chatStore.setStage("done", "complete") + setStreaming(false)

ShadowPanel (React)
    ├─ AnnotationList ← annotations, activeId, onAnnotationClick, onApplyAll
    ├─ Original text pane ← buildSegments(originalText, annotations)
    │   └─ <mark ref={spanRefs[ann.id]}> per annotation
    └─ Corrected text pane ← chatStore.draft (editable)

Kliknięcie karty adnotacji:
    setActiveAnnotationId(ann.id)
    spanRefs.current[ann.id]?.scrollIntoView({ behavior:"smooth", block:"center" })

Kliknięcie <mark> w oryginale:
    handleAnnotationClick(ann) → aktywuje kartę w sidebarze

"Zastosuj" (Apply All):
    setDraft(shadowCorrectedText || draft) — przywraca wersję AI
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Sidebar z listą kart adnotacji (powód zmiany + sugerowana fraza) | ✅ `AnnotationList` z kartami: badge ID + reason + diff `original_span → replacement` |
| Kliknięcie w kartę przewija edytor do odpowiedniego fragmentu tekstu | ✅ `spanRefs` + `scrollIntoView({ behavior:"smooth", block:"center" })` na `<mark>` w panelu oryginalnym |
| Przycisk "Apply All" kopiuje wszystkie sugestie do edytora | ✅ Przycisk "Zastosuj" w nagłówku sidebaru → `setDraft(shadowCorrectedText)` |

---

## Szczegóły implementacyjne

- **Bez zmian w infrastrukturze SSE:** nowe typy zdarzeń (`shadow_corrected_text`, `annotations`) są obsługiwane w istniejącym `switch` w `consumeStream` — bez refaktoryzacji parsera.
- **Brak nakładania się:** `buildSegments` pomija adnotacje, których `start_index` < `cursor` (nakładające się), zapobiegając błędom renderowania.
- **Highlight kolory:** `bg-amber-100` (nieaktywny), `bg-amber-300` (aktywny) — kontrast wystarczający w dark/light mode.
- **`shadowCorrectedText` vs `draft`:** `draft` może być edytowany przez użytkownika; `shadowCorrectedText` to niezmienny snapshot AI — "Zastosuj" odwołuje edycje ręczne.
- **`w-64` sidebar:** stała szerokość niezależna od liczby adnotacji; na bardzo wąskich ekranach może powodować overflow (celowo: tryb Cień zaprojektowany dla desktop).
- **Backend neutralność trybów:** `shadow_corrected_text` i `annotations` są emitowane tylko gdy `st_values.get(...)` zwraca wartość — w trybie Autor oba pola są `None`/`[]` w stanie LangGraph, więc `yield` nie jest wykonywany.
