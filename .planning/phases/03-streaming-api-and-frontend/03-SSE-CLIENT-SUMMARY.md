# 03-SSE-CLIENT Podsumowanie: Parser SSE po stronie klienta i Magazyn Zustand

**Data ukończenia:** 2026-03-10
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 03-SSE-CLIENT (Odbiór i mapowanie zdarzeń po stronie UI)
**Status:** ✅ Zakończone

---

## Cel

Zaimplementowanie reaktywnej maszyny stanowej w środowisku deweloperskim React (używając Next.js) polegającej na odbiorze i dekodowaniu danych strumieniowych za pośrednictwem HTTP `keep-alive`. Połączenie niestandardowego interpretera `SSEParser` w obrębie Custom Hooków React (`useStream`) modyfikujących bez ingerencji drzewa renderowania `Zustand` (stan globalny). Zadbano o bezpieczeństwo strumienia, reaktywność na sygnały `AbortController` oraz zintegrowano logikę z ignorowaniem nieistotnych bądź pingujących komunikatów serwerowych typu heartbeat zapobiegając zatruciu interfejsu klienta.

---

## Zmodyfikowane/Utworzone pliki

### `frontend/src/store/chatStore.ts`
Znajduje się tu magazyn centralny logiki czatu, gdzie na bieżąco dostarczane są pojedyncze fragmenty (chunki) tekstu podczas streamingu pisania (funkcja `appendDraftToken`). Store posiada precyzyjne rozgałęzienie `stage` z konkretnymi statusami: *idle, research, structure, writing, done, error*. Bezpieczny zapis z opcjonalnym podpinaniem wątków `threadId` zachowuje powiązanie z połączonym gniazdem LangGraph.

### `frontend/src/hooks/useStream.ts`
Skrypt odpowiadający za potężną asynchroniczną pętlę poboru przychodzących zdarzeń z pakietów EventSource (`new TextDecoderStream().getReader()`).
- Zadbano na obrzeżach bloku `switch (event)` o obsługę niestandardowych stanów emitowanych przez FastAPI: `node_start`, `node_end`.
- Wdrążono omijanie na wypadek pakietu `heartbeat`, wykorzystując go jedynie do wyemitowania śladów diagnostycznych przy zmiennej środowiskowej `NODE_ENV === "development"`, i powstrzymano console.warny przed fałszywymi powiadomieniami o nieznanym typie zapytania. Zdarzenie to podtrzymuje sztucznie sesję bez zerwań między FastAPI -> Next.js podczas wydłużonych pauz generacyjnych.
- Obsługa czyszczenia zdarzeń domyka czytniki buforów zamykając otwarte wtyczki operacją `finally { reader.releaseLock() }`. Zaimplementowano uwalnianie na wzór "Abort Signal" by chronić klienta przed przepełnieniem RAMu maszyny klienckiej.

---

## Weryfikacja

Konfiguracja klienta Next.js z zastosowanymi operacjami zrezygnowała z polegania jedynie na standardowym `useEffect` na korzyść oddizolowania warstwy EventStreamu do bezpiecznego `zustand`, przez użycie walidacji predykatywnej biblioteką `Zod` z zachowaniem `catchall(z.any())`, w miejscach, które były otwarte na nieznaną logikę z Vercel i logów z AWS. Kompilator Next.js 16.1 i narzędzie tsc zatwierdziły pliki wynikiem: `✓ Compiled successfully`.

---

## Kryteria akceptacji (AC)

| AC | Status |
|---|---|
| Implementacja hooka `useStream` z obsługą parowania znaków EventSource | ✅ Zaimplementowano skrypt czytnika z odizolowaniem parsera. |
| Aktualizacja `chatStore` w czasie rzeczywistym po otrzymaniu fragmentów `chunk` | ✅ Dodano wywołanie `store.appendDraftToken` przy każdym pomyślnie zwalidowanym paczce. |
| Poprawna obsługa zamknięcia strumienia przez serwer / heartbeat | ✅ Domykanie pomyślnie kończy reader operacją wewnątrz blocku "on done", zaś `heartbeat` bezgłośnie unika rozłączenia ignorując zdarzenie omyłkowych stanów Vercel Proxy logów. |
