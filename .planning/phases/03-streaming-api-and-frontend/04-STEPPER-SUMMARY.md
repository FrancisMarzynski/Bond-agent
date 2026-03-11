# 03-STEPPER Podsumowanie: Komponent paska postępu etapów (Stepper)

**Data ukończenia:** 2026-03-11  
**Faza:** 03 — Streaming API i Frontend  
**Status:** ✅ Zakończone 

---

## Cel

Celem zadania było wdrożenie wizualnego komponentu reagującego na stan agenta (fazy Research → Strukturacja → Pisanie). Komponent ma na bieżąco odbierać status postępu prac ze strumienia SSE i ułatwić użytkownikowi śledzenie cyklu życia aplikacji (LangGraph), radząc sobie z elastycznym wyświetlaniem i reagowaniem na awarie w trakcie długich generacji po stronie serwera.

---

## Zmodyfikowane/Utworzone pliki

### `frontend/src/components/StageProgress.tsx`
- Zaimplementowano komponent Steppera mapujący typy z magazynu Zustand na dedykowane, renderowane komponenty UI (ikony z `lucide-react`).
- **Zasady logiki:** Stepper potrafi śledzić "najdalszy osiągnięty indeks kroku", by uprościć architekturę i zagwarantować spójne wizualne odznaczenie poprzednich kroków, w przypadku braku jawnego eventu domknięcia (node_end → stage "complete").

### `frontend/src/store/chatStore.ts`
- Zaimplementowano strukturę statusów z możliwością utrzymywania wielu trwających `pending/running` lub wymuszenia w nich stanu `error` (dla podtrzymania awarii w panelu i blokady znikającego steppera).
- Zintegrowano zdarzenia do zasilania bezpośrednio komponentów frontendowych przez reaktywny root Zustand.

### `frontend/src/hooks/useStream.ts` (Aktualizacja w ramach przeglądu)
- **Krytyczna Poprawka:** Wzmocniono `consumeStream` by czytnik opierał w głównej mierze rozstrzyganie switch() o pole `parsed.type`, radząc sobie z problemami obranego formatowania obiektów JSON serwowanego ze `StreamEvent` po stronie Pythona (gdzie wszystkie paczki są rzutowane per `data` bez tagów `event:` w samym SSE).
- Naprawiono obsługę odczytu zawartości po rzutowaniu Zod (wyciąganie `string` tokenów z JSON zamiast podwójnego zagnieżdżenia).

### `bond/api/stream.py` oraz `bond/api/routes/chat.py`
- Utworzono mapowania zdarzeń z LangGraph (takie jak wejście w węzły `researcher`, `structure` czy `writer`) prosto na kompatybilne notacje dla Frontendu w formacie SSE type `stage`. Błędy na nowo opakowują się w stan `error` z persystentnym logowaniem w UI.

---

## Weryfikacja

Komponent reaguje płynnie w interfejsie przeglądarki. Połączenie niezależnie izolowanego Steppera ze streamowanym drzewem stanu powoduje, że odświeżanie strony / persystencja działa stabilnie. W razie wymuszonego exception, parser przekierowuje dany event do logiki `isError` podświetlając konkretny etap trwających prac na czerwono, uniemożliwiając wirtualny "spadek" z powrotem na stan "idle".

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Wizualny wskaźnik etapów: Research → Strukturacja → Pisanie | ✅ Pomyślnie zintegrowano shadcn/ui oraz lucide-react do konstrukcji logicznej UI w pliku `StageProgress.tsx`. |
| Automatyczna zmiana statusu etapu na podstawie metadanych ze strumienia SSE | ✅ Dopracowano asynchroniczny odbiór pakietów SSE tak, by prawidłowo reagował na type "stage" i aktualizował obiekty `stageStatus` trzymając stan za pomocą hooka `useStream`. |
| Obsługa stanu błędu na dowolnym etapie | ✅ Zdarzenia rozłączeń, timeout i typ wyjątku `except Exception` rzutują globalnym "error" powstrzymując spinner ładowania, i blokując stepper wizualnie z podświetleniem pomyłki, na etapie w którym przerwało generowanie. |
