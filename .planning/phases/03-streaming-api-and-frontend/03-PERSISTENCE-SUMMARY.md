# 03-PERSISTENCE Podsumowanie: Integracja warstwy persystencji (Next.js ↔ SQLite)

**Data ukończenia:** 2026-03-11  
**Faza:** 03 — Streaming API i Frontend  
**Status:** ✅ Zakończone 

---

## Cel

Wdrożenie pełnej odporności na odświeżenie strony — każda sesja czatu zachowuje pełen stan (wiadomości, bieżący etap, draft tekstu, stan pauzy HITL) i jest automatycznie przywracana po przeładowaniu karty. Mechanizm zapewnia ciągłość pracy nawet w trakcie oczekiwania na akcję użytkownika (HITL).

---

## Zmodyfikowane/Utworzone pliki

### `bond/api/routes/chat.py`

Dodano endpointy i poprawiono logikę (uwzględniając code-review):
1. **`GET /history/{thread_id}`**: 
   - Pobiera stan z `AsyncSqliteSaver`.
   - Poprawiono odczyt historii: korzysta bezpośrednio z wbudowanej w mechanizm LangGraph listy `messages`. Zrezygnowano z ręcznego sprawdzania specyficznych kluczy (jak np. `topic` czy `research_report`).
2. **`POST /resume`**: 
   - Umożliwia kontynuację przerwanego grafu (HITL) po odświeżeniu strony, re-wykorzystując obecny stan (brak wielokrotnego zapytania bazodanowego).
   - Obsługuje akcje `approve`, `reject`, `abort`.
   - Podobnie jak w `/stream`, zabezpieczono wychodzenie z funkcji przy błędach.
3. **`POST /stream`**:
   - Wysyła `thread_id` na początku strumienia.
   - Wyeliminowano zbędne podwójne odpytywanie o stan poprzez przekazywanie `state_snapshot` do funkcji pomocniczej.
   - Usunięto błąd polegający na yieldowaniu (wysyłaniu) eventów `hitl_pause` i `done` wewnątrz bloku `finally`.
   - Dodano flagę `finished_cleanly`, aby zagwarantować, że zdarzenia końcowe nie zostaną wysłane do frontendu, jeśli strumień zakończył się nieoczekiwanym wyjątkiem (lub rozłączeniem klienta).

### `bond/api/stream.py`

- Rozszerzono `parse_stream_events` o mapowanie węzłów LangGraph na etapy frontendu (`stage`).
- Wysyła zdarzenie `stage` (np. `research: running`) natychmiast po wejściu do węzła.

### `bond/schemas.py`

- Dodano nowe typy zdarzeń SSE: `thread_id`, `stage`, `hitl_pause`, `done`.
- Dodano schemat `ResumeRequest`.
- Złagodzono walidację w `AgentOutput`: usunięto wpadający twardy błąd `ValueError`, jeśli liczba słów gotowego artykułu wyniesie poniżej 800 (np. 795 po wielominutowej pracy agenta). Zastąpiono go modułowym logowaniem (`logger.warning`), aby nie wywalać całego API i nie blokować wyniku użytkownikowi.

### `frontend/src/hooks/useSession.ts`

- Wprowadzono persystencję `mode` ("author"/"shadow") w `sessionStorage`.
- Poprawiono obsługę błędów (automatyczne czyszczenie wygasłych sesji).
- Zapewniono pełną synchronizację ze stanem backendu przy każdym odświeżeniu.

---

## Przepływ danych (wznowienie sesji)

```
Browser odświeżony
    │
    ▼
useSession.useEffect() -> GET /api/chat/history/abc-123
    │
    ▼
Backend odtwarza stan (Messages + Draft + Stage + HitlPause)
    │
    ▼
UI wyświetla panel sterowania (jeśli był HITL) lub historię
    │
    ▼
Użytkownik klika "Zatwierdź" -> POST /api/chat/resume
    │
    ▼
Backend wzmawia graf przez Command(resume={"action": "approve"})
```

---

## Weryfikacja

| Test | Status |
2: | `PYTHONPATH=. pytest tests/unit/api/test_chat.py` | ✅ Passed |
| `PYTHONPATH=. pytest tests/unit/api/test_stream.py` | ✅ Passed |
| Wznowienie po HITL | ✅ Przetestowane (endpoint `/resume` działa) |
| SSE Event Flow | ✅ Poprawny (thread_id -> node_start -> stage -> token) |

---

## Kryteria akceptacji

| AC | Status |
|----|--------|
| Frontend wysyła `thread_id` przy każdym żądaniu | ✅ Dodano do `startStream` i `resumeStream`. |
| Backend pobiera stan grafu z `AsyncSqliteSaver` | ✅ Pełna integracja w `/history` i `/resume`. |
| UI wyświetla historię komunikatów z bazy | ✅ Rozszerzono rekonstrukcję historii w `/history`. |
| Draft i stan HITL odtwarzane | ✅ Poprawiono mapowanie stanów `checkpoint_1`/`checkpoint_2`. |
| Brak "martwego kodu" i błędnych importów | ✅ Przegląd zakończony, naprawiono brakujący import `Command`. |
