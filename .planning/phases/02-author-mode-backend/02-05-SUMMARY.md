# 02-05 Podsumowanie: Migracja na Asynchroniczny Persistence Layer

**Data ukończenia:** 2026-03-03  
**Faza:** 02 — Author Mode Backend  
**Plan:** 02-05  
**Status:** ✅ Zakończone

---

## Cel

Zmiana zapisu danych na model asynchroniczny, aby nie blokować event loopa API. Zadanie obejmowało refaktor `bond/db/metadata_log.py` z `sqlite3` na `aiosqlite`, konwersję węzła `save_metadata_node` na `async def`, oraz napisanie testów jednostkowych weryfikujących brak blokowania event loopa.

---

## Zmodyfikowane pliki

### `bond/db/metadata_log.py` — Migracja na `aiosqlite`

Zastąpiono synchroniczny moduł `sqlite3` biblioteką `aiosqlite`. Usunięto funkcję `_get_conn()`. Dodano prywatną `async def _ensure_schema(conn)` wykonującą DDL idempotentnie przy każdym połączeniu. Funkcje `save_article_metadata()` i `get_recent_articles()` są teraz `async def` używającymi `async with aiosqlite.connect(...)`.

### `bond/graph/nodes/save_metadata.py` — Konwersja węzła na `async def`

Sygnatura zmieniona z `def` na `async def` — LangGraph akceptuje węzły asynchroniczne natywnie. Wywołanie `save_article_metadata()` poprzedzone `await`. Synchroniczne ChromaDB (`add_topic_to_metadata_collection`) uruchamiane przez `asyncio.to_thread()`, co zapobiega blokowaniu event loopa.

### `pyproject.toml` — Konfiguracja pytest

Dodano sekcję `[tool.pytest.ini_options]` z `asyncio_mode = "auto"`, aby testy działały bez ręcznego dekorowania każdego przypadku testowego.

### `tests/test_metadata_log_async.py` — Nowy plik

3 testy `pytest-asyncio` z fixture `in_memory_db` opartym na `tmp_path` + `monkeypatch` — testy nie dotykają produkcyjnej bazy `bond_metadata.db`.

### `tests/conftest.py` — Nowy plik

Rejestracja markera `asyncio` dla `pytest`.

---

## Decyzje projektowe

- **`graph.py` bez zmian:** `AsyncSqliteSaver` był już poprawnie wdrożony w Planie 02-01
- **`aiosqlite` zamiast `run_in_executor`:** `aiosqlite` eksponuje natywny async API — czytelniejszy kod niż ręczne `loop.run_in_executor(None, sqlite3_call)`
- **`asyncio.to_thread()` dla ChromaDB:** Biblioteka nie posiada async API; `to_thread()` jest idiomatycznym, wbudowanym rozwiązaniem w Python 3.9+ bez nowych zależności
- **`_ensure_schema()` per połączenie:** DDL jest idempotentne (`CREATE IF NOT EXISTS`) — eliminuje potrzebę globalnego singletonu połączenia
- **`asyncio_mode = "auto"` w pyproject.toml:** Dodano konfigurację pytest, aby testy asyncio działały niezawodnie
- **Brak nowych zależności:** `aiosqlite` i `pytest-asyncio` były już zadeklarowane w `pyproject.toml`

---

## Weryfikacja

```
============ test session starts ============
platform darwin -- Python 3.13.5, pytest-9.0.2, pluggy-1.6.0
asyncio: mode=Mode.AUTO

tests/test_metadata_log_async.py::test_save_does_not_block_event_loop PASSED [ 33%]
tests/test_metadata_log_async.py::test_save_returns_positive_row_id    PASSED [ 66%]
tests/test_metadata_log_async.py::test_get_recent_articles_returns_dicts PASSED [100%]

============= 3 passed in 0.06s =============
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|---|---|
| `metadata_log.py` używa `aiosqlite` zamiast `sqlite3` | ✅ `async def save_article_metadata()` i `get_recent_articles()` |
| `save_metadata_node` nie blokuje event loopa | ✅ `async def` + `asyncio.to_thread()` dla ChromaDB |
| Testy jednostkowe weryfikujące brak blokowania | ✅ 3/3 PASSED — `asyncio.gather` z 5 równoczesnych zapisów |
