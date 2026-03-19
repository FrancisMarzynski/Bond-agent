# 06-ROUTING-AND-SHADOW-SCAFFOLD Podsumowanie: Routing i Scaffold widoku Shadow

**Data ukończenia:** 2026-03-19
**Faza:** 03 — Streaming API i Frontend
**Plan:** 06 — UI: Routing i Scaffold widoku Shadow
**Status:** ✅ Zakończone

---

## Cel

Przygotowanie nawigacji i pustego layoutu panelu Shadow. Dodanie ścieżki `/shadow` w Next.js App Router, aktualizacja `ModeToggle` tak by przełączał się między `/` (Author) a `/shadow` przez nawigację routera, oraz inicjalizacja pustego `ShadowStore` w Zustand gotowego na rozbudowę w kolejnych fazach.

---

## Zmodyfikowane/Utworzone pliki

### `frontend/src/app/shadow/page.tsx` *(nowy plik)*
- Nowa strona App Router pod ścieżką `/shadow`.
- Zawiera scaffold z komunikatem „Tryb Cień / Panel analizy porównawczej — w przygotowaniu".
- Korzysta z globalnego `layout.tsx` (Sidebar, ModeToggle, SessionProvider) bez dodatkowej konfiguracji.

### `frontend/src/store/shadowStore.ts` *(nowy plik)*
- Nowy store Zustand z pustym interfejsem `ShadowStore`.
- Eksportuje `useShadowStore` gotowy na rozbudowę (stan dokumentu, wyniki analizy, adnotacje) w fazach shadow_analyze i shadow_annotate.

### `frontend/src/components/ModeToggle.tsx` *(zaktualizowany)*
- Dodano `useRouter`, `usePathname` z `next/navigation` oraz `useEffect` z React.
- Przełącznik sprawdza teraz aktualną ścieżkę (`pathname === "/shadow"`) zamiast stanu ze store'a — gwarantuje to synchronizację URL ↔ UI niezależnie od źródła nawigacji.
- `handleToggle` wywołuje `persistMode()` (zapis do `sessionStorage` + aktualizacja ChatStore) oraz `router.push()` do właściwej ścieżki.
- `useEffect([isShadow])` synchronizuje `chatStore.mode` z aktualną ścieżką przy każdej zmianie trasy (nawigacja wstecz/przód, bezpośrednie wejście na `/shadow`), eliminując niespójność między URL a stanem store'a.
- Badge i checked-state przełącznika są napędzane przez `isShadow`, a nie z Zustand.

---

## Weryfikacja

`npx tsc --noEmit` zakończył się bez błędów ani ostrzeżeń. Trzy nowe / zmodyfikowane pliki są poprawne typowo i nie wymagają żadnych dodatkowych zależności (wszystkie importy już obecne w projekcie).

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Dodanie ścieżki `/shadow` w Next.js | ✅ Plik `app/shadow/page.tsx` rejestruje trasę App Router `/shadow`. |
| ModeToggle poprawnie przełącza między `/` (Author) a `/shadow` | ✅ `usePathname` + `router.push()` synchronizują URL z przełącznikiem; `persistMode()` aktualizuje store i sessionStorage. |
| Inicjalizacja pustego ShadowStore w Zustand | ✅ `shadowStore.ts` eksportuje `useShadowStore` z pustym interfejsem gotowym na rozbudowę. |
