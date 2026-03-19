# 14-SHADOW-PANEL-LAYOUT Podsumowanie: Dwukolumnowy panel trybu Cień

**Data ukończenia:** 2026-03-19
**Faza:** 03 — Streaming API i Frontend
**Status:** ✅ Zakończone

---

## Cel

Implementacja interfejsu trybu Cień z dwukolumnowym układem prezentującym oryginalny tekst użytkownika obok edytowalnego podglądu wersji poprawionej przez model. Panel zastąpił istniejący stub strony `/shadow`.

---

## Zmodyfikowane/Utworzone pliki

### `frontend/src/components/ShadowPanel.tsx` *(nowy)*
Główny komponent trybu Cień z dwufazową logiką wyświetlania:
- **Faza 1 — Widok wejściowy:** wyświetlany przed wysłaniem tekstu; centruje na ekranie formularz z `<Textarea>` (min. 200px) i przyciskiem "Analizuj styl". Obsługuje skrót ⌘+Enter do wysyłki.
- **Faza 2 — Widok porównawczy:** aktywowany po ustawieniu `originalText` w store; dwie kolumny `flex-col md:flex-row`:
  - **Lewa kolumna** (`md:w-1/2`, `border-r`, `overflow-y-auto`): oryginalny tekst read-only renderowany jako `<p>` z `whitespace-pre-wrap`.
  - **Prawa kolumna** (`flex-1`, `bg-muted/10`): `<textarea>` bez ramki połączony z `chatStore.draft`. W trakcie strumieniowania: `readOnly`; po zakończeniu: w pełni edytowalny. Przed pojawieniem się pierwszych tokenów wyświetlany jest skeleton (4 pulsujące paski).
- Pasek statusu (h-10, `border-b`) ze wskaźnikiem `Loader2` podczas strumieniowania i przyciskiem "Nowy tekst" do resetowania sesji.

### `frontend/src/store/shadowStore.ts` *(rozbudowany)*
Rozbudowano pusty stub Zustand o:
- `originalText: string` — tekst wklejony przez użytkownika
- `setOriginalText(text)` — ustawiany przed startem strumienia
- `resetShadow()` — czyści `originalText` przy resecie sesji

### `frontend/src/app/shadow/page.tsx` *(zmodyfikowany)*
Zastąpiono placeholder `<div>` pojedynczym wywołaniem `<ShadowPanel />`.

---

## Przepływ danych

```
Użytkownik wkleja tekst
        ↓
handleSubmit() → resetSession() + setOriginalText() + startStream(mode:"shadow")
        ↓
SSE tokens → chatStore.appendDraftToken() → chatStore.draft
        ↓
ComparisonView: originalText (shadowStore) | draft (chatStore)
        ↓
Po zakończeniu: użytkownik edytuje draft → chatStore.setDraft()
```

Tekst poprawiony akumulowany jest w `chatStore.draft` — tej samej infrastrukturze co w trybie Autor — bez duplikowania logiki strumieniowania.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Implementacja layoutu dwukolumnowego (flex/grid) | ✅ `flex-col md:flex-row` z separatorem `border-r`; responsywny (na mobile: stack, na desktop: obok siebie) |
| Lewa strona: Tekst oryginalny (Read-only) | ✅ `<p>` z `whitespace-pre-wrap`; brak możliwości edycji; etykieta "Tekst oryginalny" z ikoną `FileText` |
| Prawa strona: Podgląd poprawionej wersji z możliwością edycji | ✅ `<textarea>` połączony z `chatStore.draft`; `readOnly` podczas strumieniowania, edytowalny po zakończeniu; etykieta "Wersja poprawiona" z ikoną `Pencil` |

---

## Szczegóły implementacyjne

- **Zarządzanie stanem:** `useShadowStore` przechowuje `originalText`; `useChatStore.draft` pełni rolę bufora poprawionego tekstu (reużycie istniejącej infrastruktury tokenowej).
- **Reset sesji:** `handleReset()` wywołuje jednocześnie `resetSession()` (czyści draft i isStreaming) oraz `resetShadow()` (czyści originalText), przywracając widok wejściowy.
- **Streaming guard:** przycisk "Analizuj styl" jest wyłączony (`disabled`) podczas aktywnego strumienia; przycisk "Nowy tekst" analogicznie blokuje reset w trakcie generowania.
- **Skeleton loader:** wyświetlany gdy `isStreaming && !draft`, czyli zanim pojawią się pierwsze tokeny — eliminuje "blank flash".
- **Kompatybilność:** komponent używa `useStream` i `useChatStore` — tych samych hooków co tryb Autor — bez modyfikacji backendu ani routingu SSE.
