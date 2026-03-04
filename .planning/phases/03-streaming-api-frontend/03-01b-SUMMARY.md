# 03-01b Podsumowanie: Parser zdarzeń LangGraph (astream_events)

**Data ukończenia:** 2026-03-04
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 03-01b (Cześć backendowego integracji API)
**Status:** ✅ Zakończone

---

## Cel

Przetworzenie surowych danych strumieniowanych z agenta (LangGraph) na czytelne komunikaty do formatu SSE JSON dla frontendu.
Zaimplementowanie testowalnej funkcji mapującej eventy `on_chat_model_stream` na czysty tekst (tokeny) oraz obsługującej eventy `on_chain_start` w celu identyfikacji aktualnego węzła grafu. Zwracanie wyjścia jako ustandaryzowanego JSON: `{"type": "...", "data": "..."}`.

---

## Zmodyfikowane pliki

### `bond/api/stream.py` (Nowy) — Parser zdarzeń strumieniowych

Stworzono nowy moduł z asynchronicznym generatorem `parse_stream_events`. 
Analizuje on strumień zdarzeń z pakietu LangGraph wywoływany przez `astream_events(version="v2")`:
- Odbierane zdarzenia `on_chain_start` (identyfikacja węzła grafu np. `researcher`, `writer` pobierana z tagu `langgraph_node` w sekcji `metadata` lub z nazwy) są pakowane do formatu: `{"type": "node", "data": "nazwa_wezla"}`.
- Odbierane zdarzenia `on_chat_model_stream` odpowiadają za wyciągnięcie zawartego tekstu (tokenów chunk) od LLMa i wysyłane są w formacie: `{"type": "token", "data": "fragment_tekstu"}`.
- Zdarzenia irrelewantne dla klienta UI (jak wewnętrzne `on_tool_start`, `on_chain_end` itd.) są dyskretnie ignorowane.

### `tests/unit/api/test_stream.py` (Nowy) — Zestaw testów jednostkowych dla parsera

Dodano testy asynchroniczne (`pytest-asyncio`) weryfikujące poprawność dekodowania na mockowanym iteratorze z formatem wejściowych słowników testowych:
- Obsługa obecności wezłów (identyfikacja poprawnej metadanej w tagach oraz obsługa na wypadek fallbacku po `name`).
- Walidacja poprawności formatów tekstu - przetestowano standardowy tekst zawarty w obiektach (np. AIMessageChunk), słowniki i listy klastrowe bloki tekstu wysyłane np. przez Anthropic do chatu.
- Potwierdzenie że logi niezwiązane z wypluwaniem tekstu nie przekształcają strumienia.

---

## Decyzje projektowe

- **Format z JSON Dumps we wzorcu SSE:** Obiekty pakowane są jako reprezentacje string wewnątrz funkcji generatora. Zmniejszy to ciężar pracy warstwy wyżej - główny routing API FastAPI po prostu zewolve-uje je wraz z nagłówkiem EventSourceResponse `data: ...`. 
- **Złożone chunking'i zwracane z LLM'ow:** Zbudowano obsługę i warunki zapasowe na obiekty strukturalne zwracane od nowszych modeli (np. obiekty, zagnieżdżone w listach typu block `{"type": "text", "text": "value"}`).
- **Odsuwanie szumu na wczesnym etapie:** Filtrowanie zapytań nie dzieje się na zewnątrz funkcji parsera lecz pod spodem. Eliminuje to zbędne obciążenie pamięci iteratora streamingu na interfejsy aplikacji - Frontend nie dostanie powiadomienia, póki to nie jest akcja w GUI.
- **Nazewnictwo Planu 03-01b:** Z racji na bliskie pokrewieństwo z wdrażaniem Endpointów Chat w planie pierwszym fazy trzeciej (po stronie backendu), zostało to usystematyzowane w numeracji 03-01b by nie kolidować z Planem 2 skupionym stricte wokół komponentów front-endowych.

---

## Weryfikacja

Parser i środowisko testowe objęte poprawnym asynchronicznym fixture'em wydały 100% pozytywnych przypadków wywołanych komendą.

```bash
poetry run pytest tests/unit/api/test_stream.py -v

============= 7 passed in 0.01s =============
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|---|---|
| Stworzenie funkcji mapującej eventy `on_chat_model_stream` na czysty tekst | ✅ Zaimplementowana i potwierdzona przez przypadki testowe |
| Obsługa eventów `on_chain_start` w celu identyfikacji aktualnego węzła | ✅ Testowane ze standardowymi metadanymi LangGraph jak i logiką fallbackową funkcji |
| Formatowanie wyjścia do JSON: `{"type": "...", "data": "..."}` | ✅ Moduł wypycha sformatowane tokeny lub komunikaty węzłowe wyłączenie w formacie JSONowych stringów gotowych pod SSE Client |
