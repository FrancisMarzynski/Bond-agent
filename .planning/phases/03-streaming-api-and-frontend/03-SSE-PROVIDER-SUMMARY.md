# 03-SSE-PROVIDER Podsumowanie: Implementacja dostawcy FastAPI SSE dla LangGraph

**Data ukończenia:** 2026-03-10
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 03-SSE (Integracja dostawcy Server-Sent Events)
**Status:** ✅ Zakończone

---

## Cel

Zaimplementowanie stabilnego dostawcy Server-Sent Events po stronie FastAPI. Zapewnienie przesyłania zdarzeń `on_node_start` i `on_node_end` dla śledzenia cyklu życia węzłów LangGraph przez frontend, oraz realizacja obsługi cyklicznego `heartbeat` (sygnału życia), by chronić wielosekudnowe przestoje pod generacje tekstów LLM przed nagłymi zerwaniami połączeń ze strony serwerów pośredniczących w proxy, przy zachowaniu szybkiego czasu procesowania rozłączeń klientów.

---

## Zmodyfikowane/Utworzone pliki

### `bond/schemas.py` 
Zaktualizowano kontrakt informacyjny dla Pydantic w obiekcie `StreamEvent`. Dodano poprawne literale typów dopuszczając przesyłanie zdarzeń `node_start`, `node_end` oraz `heartbeat` i zastępując przestarzałą generyczną formułę `node`.

### `bond/api/stream.py` 
Zrefaktoryzowano mapper LangGraph by potrafił dokładnie zrewizować zdarzenia. `on_chain_start` dostarcza informacji o `node_start`, a nowo dodany blok pod chwytanie `on_chain_end` zapewnia, że poszczególny węzeł raportuje również jako `node_end`. Całość przekazywana rzetelnie jako zserializowany JSON dla frontendu.

### `bond/api/routes/chat.py`
Ubogacono główną pętle asynchroniczną i iterator `gen.__anext__()` nad endpointem `/stream`. Obcięto czas zawieszeń wątku pod asynchroniczny `is_disconnected` tak, by rewidował rozłączenia użytkowników co "każdą minioną sekundę" przez wpadnięcie w blok `TimeoutError`. Kiedy miniony czas przekracza jednak granicę 15s, skrypt wydaje z siebie dedykowany ustrukturyzowany pakiet dla `StreamEvent` typu `heartbeat`, mówiąc load balancerowi/klientowi w standardzie SSE "still running" dopóki stream dobiegnie końca. 

---

## Weryfikacja

Wprowadzenie tych zmian sprawia, że asynchroniczne odpytywanie LangGraph zachowuje płynność logów. Aplikacja pomyślnie zwalnia pamięć podczas wymuszonego rozłączenia bez "wiszących w tle" połączeń na endpoint. Heartbeat wysyła paczki `{"type": "heartbeat", "data": "ping"}\n\n` co każde 15s braku ruchu od strony Langgraph.

---

## Kryteria akceptacji (AC)

| AC | Status |
|---|---|
| Rozbicie logiki mapującej wejście/wyjście z węzła LangGraph do SSE | ✅ Zaimplementowano poprawne zliczanie stanów `node_start` / `node_end`. |
| Cykliczne podtrzymywania życia przy przedłużającym się procesowaniu LLM | ✅ Mechanizm reaguje po upływie 15-sekund braku nowych pakietów wysyłając sygnał zachowujący przy życiu uvicorn na Proxy |
| Oczekiwanie by Endpoint reagował natychmiast na przerwane zapytania HTTP | ✅ Dodano szybkie interwały walidacyjnie bez opóźnień asynchronicznych i łagodną sekwencję sprzątającą pule zasobów w bloku `finally`. |
