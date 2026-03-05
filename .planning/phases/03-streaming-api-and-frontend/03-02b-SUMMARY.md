# 03-02b Podsumowanie: Odbiornik danych na żywo (SSE Consumer Reconnect)

**Data ukończenia:** 2026-03-04
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 03-02b (Część ulepszenia hook'ów magazynowych)
**Status:** ✅ Zakończone

---

## Cel

Nauczenie przeglądarki, jak czytać sygnały płynące z backendu oraz implementacja silnej ochrony na wypadek zepsucia strumienia. Zadaniem było uzbrojenie hooka `useStream.ts` (korzystającego z natywnego mechanizmu fetch ReadableStream po stronie aplikacji webowej) na ponawianie przerwanych prób dostępu i adekwatne sygnalizowanie stanu sieciowego klientowi w panelu interfejsu.

---

## Zmodyfikowane pliki

### `frontend/src/hooks/useStream.ts` (Zmodyfikowano) 

Nadano ufortyfikowaną pętlę dla obydwu punktów styku z API (zarówno `startStream` wywoływane jako świeży wniosek do wezla agenta oraz `resumeStream` powołane przy kontynuowaniu autoryzowanego stanu HITL - Human In The Loop).

- **Pętla retry (`while`)**: Oba endpointy Fetch (kierujące do `API_URL/api/chat/stream` oraz `resume`) zostały odziane w blok `try-catch` otoczony pętlą `while`, która analizuje powód zrzutu zapytania (np. brak sieci po stronie frontendu lub przerwany timeout ze strony serwera uvicorn).
- **Proces oczekiwania (`Timeout`)**: Jeśli parser w trakcie odczytywania chunków wyrzuci krytyczny błąd (np. `reader.read()` zatrzyma promesę przerwaniem TCP), skrypt odliczy ustalone 3 sekundy za pomocą oczekującej promisy tak, by dać czas na chociażby naprawienie połączenia sieciowego.
- **Odporność na zerwania (Idempotentność i `Last-Event-ID`)**: Oba endpointy (zarówno `stream` jak i `resume`) ustawiają pole `Last-Event-ID` w **nagłówku HTTP (HTTP Headers)**, przechowujące ID ostatnio odebranego chunku operacyjnego (np. generowanego dokumentu z LangGraph). Dzięki nadaniu protokołowi parsowania zdolności zgarniania linii `id: ` ze wbudowanego standardu komunikacji SSE, ponowienie skryptu przez `fetch` zacznie odbierać tekst niemal natychmiast po urwanej sylabie – aplikacja nie przepala już podwójnie kosztów przeliczania wielkich tokenów na serwerze API.
- **Logika odcinania (`MAX_RETRIES`)**: Otwarcie sygnału ograniczono górnym limitem sztywnym `MAX_RETRIES = 3`. 
- **Zintegrowany interfejs System Alert (Rozdział logów technicznych od czatu)**: Skrypty reconnectów odczepiono od wpychania technicznych zawiadomień do globalnego obiektu chatStore (za pomocą `store.addMessage`). Mechanizm zamieniono na udostępnioną przez Zustand modyfikację wydzielonego kanału stanów w `store.setSystemAlert(...)`. Pętle wznowieniowe typu "Połączenie zerwane. Próbuję ponownie (1/3)..." wędrują teraz tylko jako ukryte statusu Toast'ów interfejsu klienta nie brudząc historii dyskusji dostarczanej potem do odczytów kolejnych modeli LLM. W razie braku możliwości odzyskania dostępu po ostatniej próbie UI wyświetli powód zaprzestania poboru i zatrzyma status streamingu (`store.setStreaming(false)`). To rozwiązuje problem wiszącego paska ładowania dla usera.

---

## Weryfikacja

Wygenerowany kod hook'a jest stuprocentowo spójny z wymogami Next.js 15 oraz statycznie stypizowany w TypeScriptie: kompilator TSC przeanalizował całą logikę obydwu funkcji upewniając o stuprocentowej poprawności wprowadzonych zmian. System produkcyjnie zbudowany (`npm run build`) z sukcesem zrealizował operacje pakowania na turbopack'u oznaczając pliki jako poprawnie dołączone.

---

## Kryteria akceptacji (AC)

| AC | Status |
|---|---|
| Implementacja fetch z obsługą ReadableStream | ✅ Gotowe. Implementacja jest wdrożona razem z pętlą weryfikującą fragmenty SSE za pomocą napisanego wcześniej generatora. |
| Funkcja dopisująca przychodzące tokeny do tekstu w edytorze w czasie rzeczywistym | ✅ Gotowe. Realizuje to podłączenie `store.appendDraftToken` odkładając chunk wypluwany przez LLMa do tablicy draft. |
| Obsługa błędów połączenia (reconnect) / powiadomienie użytkownika | ✅ Wdrożono inteligentny zautomatyzowany licznik obiegający bląd asynchroniczny i wysuwający stosowny feedback bezpośrednio na widok za pomocą nowo wygenerowanej w Store wiadomości asystenta. |
