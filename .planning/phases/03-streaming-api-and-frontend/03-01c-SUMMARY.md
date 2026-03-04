# 03-01c Podsumowanie: Implementacja StreamingResponse (SSE)

**Data ukończenia:** 2026-03-04
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 03-01c (Część backendowej integracji API)
**Status:** ✅ Zakończone

---

## Cel

Uruchomienie fizycznego przesyłania danych "na żywo" do przeglądarki poprzez endpoint Server-Sent Events (SSE). Utworzenie generatora odpytującego graf agenta (LangGraph) i budującego transparentny strumień danych w czasie rzeczywistym, wraz z pełną obsługą niespodziewanego zerwania sesji klienckiej.

---

## Zmodyfikowane pliki

### `bond/api/main.py`
- Zaktualizowano pole `lifespan` aplikacji FastAPI, aby podczas cyklu życia uruchamiała `compile_graph` z LangGraph z asynchronicznym Checkpointerem w SQLite i mapowała go do `app.state.graph`.
- Dodano podłączenie nowego routera `chat_router` w celu udostępnienia nowych endpointów pod ścieżką `/api/chat`.

### `bond/api/routes/chat.py` (Nowy)
- Utworzono definicję endpointu `POST /api/chat/stream`.
- Zaimplementowano asynchroniczny generator połączony z `app.state.graph.astream_events(version="v2")`.
- Odpowiedź wykorzystuje klasę `StreamingResponse` ze sztywno zdefiniowanymi nagłówkami blokującymi cache (`Cache-Control: no-cache`, `X-Accel-Buffering: no`, itd.) i określonym `media_type="text/event-stream"`.
- Wdrożono aktywny mechanizm timeoutingu nad generatorem (`asyncio.wait_for`), pozwalający na odpytywanie `await request.is_disconnected()` w ustalonych oknach czasowych, niezależnie od tego, czy wywołanie do modelu było obfite czy przedłużało się w czasie. Wynikuje to zablokowaniem pobierania tokenów i wywołaniem instrukcji zakończenia wewnątrz samego astream_events, poprawnie czyszcząc zasoby LLMa.

### `tests/unit/api/test_chat.py` (Nowy)
- Dodano testy weryfikujące poprawność nagłówków SSE.
- Zmodyfikowano mock grafu aby zwracał wymyślone pakiety eventów, a parser (`parse_stream_events`) testowo przerabiał to na odpowiedź o strukturze SSE. Pętle walidujące przetestowano również pod kątem blokowania.

---

## Decyzje projektowe

- **Agresywny Mechanizm Disconnect:** Tradycyjne metody opierające się jedynie na zapytaniach po każdorazowym wysłaniu eventu nie dają zabezpieczenia podczas bardzo długich czasów inferencji wezłów w LLMie (brak eventów do zwrócenia pomimo rozłączenia klienta). Wdrożono zagnieżdżoną pętlę generacji opartą o `asyncio.wait_for(timeout=1.0)` by bezwzględnie weryfikować `await request.is_disconnected()` co wycelowaną ilość czasu, by w razie przerwania zamknąć `aclose()` generatora - co rzuca `CancelledError` wymuszające natychmiastowe ubicie zadania po stronie LangChain.
- **Bezpieczny Lifespan Grafu:** `compile_graph()` inicjalizowane jest tylko raz na cykl życia głównej aplikacji FastAPI i przechowywane w `request.app.state.graph`, zapobiegając utracie i zaśmiecaniu pamięci.
- **Format SSE i Routing Fazy:** Ciąg znaków wynikowych formatowany jest dokładnie tak samo jak tego oczekuje standardowy mechanizm SSE. Usunięto również pomyłki z katalogami (Przeniesiono pliki faz z `/03-streaming-api-frontend` wprost do katalogu nadrzędnego `/03-streaming-api-and-frontend` w konwencji architektonicznej).

---

## Weryfikacja

Przetestowano nową strukturę routera Chat korzystając z `pytest`. Mock testowy LangGraph z podłączonym wywoływaniem strumienia poprzez `TestClient(app).stream()` poprawnie załadował logikę SSE. Narzędzie testów asynchronicznych wskazało przejście wszystkich prób dla routera oraz dla jego parsera zdarzeń.

---

## Kryteria akceptacji (AC)

| AC | Status |
|---|---|
| Endpoint `POST /api/chat/stream` zwraca generator danych | ✅ Gotowe. Powołano do życia generator z SSE w `chat.py`. |
| Implementacja nagłówków `text/event-stream` i `no-cache` | ✅ Zaimplementowano twardą listę nagłówków wykluczających API proxy. |
| Mechanizm przerywania pracy agenta przy rozłączeniu klienta (cleanup) | ✅ Wdrożono potężne sprawdzenie rozłączania opierające się na regularnych blokach nasłuchiwania przerwanej sesji uvicorna, nie blokujące się na długich wezwaniach do LLMs. |
