# 03-02 Podsumowanie: Zarządzanie pamięcią aplikacji i Server-Sent Events

**Data ukończenia:** 2026-03-04
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 03-02 (Cześć frontendowego magazynu pamięci)
**Status:** ✅ Zakończone

---

## Cel

Zainicjowanie podstaw frontendu Next.js (części pierwszej), oraz utworzenie centralnego magazynu danych po stronie przeglądarki wraz ze skryptami łączącymi powiadomienia Server-Sent Events (SSE) wysyłanymi na uvicorn przez LangGraph backend ze stanem klienta (Zustand).

---

## Zmodyfikowane/Utworzone pliki

### `frontend` (Nowy) — Inicjalizacja App Dir
Zbudowano od zera projekt asynchroniczny w `Next.js 15` za pomocą `create-next-app` wspierającego natywnie `React 19` wraz ze świetnym zapleczem startowym `Tailwind CSS v4`. Zainstalowano docelowe narzędzia niezbędne do implementacji m.in `zustand` oraz interfejs UI `shadcn`. Zmieniono plik `.env.local` tak by aplikacja mogła dotykać instancji pod `:8000`.

### `frontend/src/store/chatStore.ts` (Nowy) 
Zaprojektowano schemat architektury `zustand` przechowujący cały stan operacyjny w jednym Store. Sklep posiada zdefiniowany aktualny `mode` (np. Author), identyfikator wątku `threadId`, etap rurociągu LangGraph'a np. "Writing", historię wiadomości, flagi zawieszania Human-In-The-Loop ze stoperami iteracji, jak i również generowany "na żywo" szkic budowanego felietonu. Do całości dołączono pełen plik niezbędnych typów oraz akcji m.in doprowadzanie części ze strumienia przez akcje `appendDraftToken`.

### `frontend/src/lib/sse.ts` (Nowy) 
Wdrążono i odizolowano logikę akumulowania strumienia poprzez niestandardowy parser zapytań Server-Sent Events. Zabezpiecza on operatory dzielące (chunk boundary splitting), które mogłyby urywać komunikaty w połowie, uszkadzając tym format JSON oczekiwany przy typach token/nagłówkach. Przetworzono bufor, który oczekuje na poprawne `\n\n`.

### `frontend/src/hooks/useSession.ts` (Nowy)
Stworzono mały, prosty moduł kliencki (Custom Hook React'a). Nasłuchuje on operacji ładowania ekranu poprzez natywny `useEffect` wstrzykując w przeglądarkę pod klucz `bond_thread_id` numer sesji i pozyskując ją po odświeżeniu - chroni to przed zgubieniem zawartości konwersacji (zgodnie z kryteriami akceptacyjnymi AC planu 03-02). Hook udostępnia funkcję na "nową" instancję zerując store.

### `frontend/src/hooks/useStream.ts` (Nowy)
Zapoczątkowano i połączono wszystko w asynchronicznym skrypcie sterującym konsumowaniem strumienia `stream` i `resume` (przywracanie pauzy). Odpowiada we współpracy z `chatStore.ts` nad iteracyjnym przesyłem (fetch) na odpowiednie porty FastAPI lokalnie wysyłając JSON konwersacyjny i przerabiając stream poprzez parser na potężną pętlę zmieniając na żywo flagi w samym store zależnie od tagów typu event`a tak jak "thread_id", "token", "stage" itd. Obejmuje potężny blok `try...finally { reader.releaseLock() }` dla zapobiegania przepełniania buforów (memory leak). 

---

## Decyzje projektowe

- **Tailwind 4 CSS-first:** Po migracji na najnowsze wtyczki Next.js użyto dedykowanego w V4 sposobu definicji. Usunięto i zakazano szukania globalnych styli generacji Tailwind ze starych bibliotek `npm`.
- **Zustand przed Context API:** Pomimo bliskości z UI, użyto architektonicznie lepszego stanu zewnętrznego dla uniknięcia re-renderingów całych bloków Layout po dostarczeniu strumienia. Hook `useChatStore.getState()` nie wywoła nadpisywań drzewa DOM. Zdegradowano `useContext()` do minimum.

---

## Weryfikacja

Przykłady kodu zostały odizolowane i zamknięto proces kompilatora TS wywołanego w celu poszukiwań niedokładności. 
`npx tsc --noEmit && npm run build` we frakcji frontowej przechorowało 0 niedomówień syntaktycznych przechodząc płynnie do pełnego wygenerowania Next.js.

---

## Kryteria akceptacji (AC)

| AC | Status |
|---|---|
| Implementacja `chatStore` do trzymania treści artykułu | ✅ Ukończono z podłączeniem z Zustand. Sklep dzieli logicznie operacje na zdarzeniach. |
| Obsługa `thread_id` zapobiegająca gubieniu logów po odświeżeniu witryny | ✅ Stworzono `useSession.ts` dedykowane zabezpieczaniu sessionStorage pomiędzy restartami. |
| Logika czyszczenia stanu przy rozpoczynaniu nowego tematu | ✅ Zaimplementowano w hooku komendę `newSession()`, usuwającą token oraz podpinającą logikę resetu pamięci stanu Store'a. |
