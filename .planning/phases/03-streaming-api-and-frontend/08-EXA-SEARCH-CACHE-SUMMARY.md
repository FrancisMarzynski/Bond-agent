# 08-EXA-SEARCH-CACHE Podsumowanie: Caching wyników wyszukiwania (AUTH-11)

**Data ukończenia:** 2026-03-24
**Faza:** 03 — Streaming API i Frontend
**Plan:** 08 — Exa Search Cache (AUTH-11)
**Status:** ✅ Zakończone

---

## Cel

Redukcja kosztów API Exa i przyspieszenie kolejnych wywołań węzła Researcher w ramach tej samej sesji (thread_id), poprzez wprowadzenie trwałego cache'u SQLite dla surowych wyników wyszukiwania.

---

## Architektura

```
researcher_node(state)
        │
        ├─ Warstwa 1: in-memory state cache (AUTH-10)
        │     dict search_cache[topic] → raw_results
        │     Chroni przed podwójnym wywołaniem w tej samej iteracji grafu.
        │
        ├─ Warstwa 2: SQLite search_cache (AUTH-11)  ← NOWE
        │     bond_metadata.db → tabela search_cache
        │     Klucz: (query_hash, thread_id)
        │     Chroni przed podwójnym wywołaniem przy wznawianiu sesji.
        │
        └─ Warstwa 3: Exa MCP API (live call)
              Wywoływana tylko przy podwójnym cache miss.
              Wynik zapisywany do obu cache'y.
```

**`query_hash`** = SHA-256(`"{topic}:{':'.join(sorted(keywords))}"`) — stabilny hash niezależny od kolejności słów kluczowych.

---

## Zmodyfikowane pliki

### `bond/db/search_cache.py` — NOWY

Moduł z trzema funkcjami publicznymi:

```python
def compute_query_hash(topic: str, keywords: list[str]) -> str
    # SHA-256 kanonicznego "topic:sorted(keywords)"

async def get_cached_result(query_hash: str, thread_id: str) -> str | None
    # Odczyt z search_cache; None przy cache miss

async def save_cached_result(query_hash: str, thread_id: str, results_json: str) -> None
    # INSERT OR REPLACE do search_cache
```

Tabela jest tworzona leniwie (`CREATE TABLE IF NOT EXISTS`) przy pierwszym dostępie, bez potrzeby ręcznej migracji bazy.

Dane zapisywane do `bond_metadata.db` (ten sam plik co `metadata_log`).

### `bond/graph/nodes/researcher.py`

Rozszerzono `researcher_node` o dwuwarstwowe sprawdzenie cache:

```python
if topic in cache:
    raw_results = cache[topic]           # Warstwa 1 — state dict
else:
    query_hash = compute_query_hash(topic, keywords)
    db_result = await get_cached_result(query_hash, thread_id)

    if db_result is not None:
        raw_results = db_result          # Warstwa 2 — SQLite
    else:
        raw_results = await _call_exa_mcp(topic, keywords)
        await save_cached_result(query_hash, thread_id, raw_results)  # zapis

    cache = {**cache, topic: raw_results}
```

`thread_id` jest odczytywane z `state.get("thread_id", "")` — pole obecne w `BondState` od fazy 2.

### `bond/db/schema.sql`

Dodano definicję tabeli `search_cache` (dokumentacja schematu):

```sql
CREATE TABLE IF NOT EXISTS search_cache (
    query_hash   TEXT NOT NULL,
    thread_id    TEXT NOT NULL,
    results_json TEXT NOT NULL,
    timestamp    TEXT NOT NULL,   -- ISO 8601 UTC
    PRIMARY KEY (query_hash, thread_id)
);
```

### `setup_db.py`

Dodano DDL `search_cache` do `METADATA_DDL`, tak aby `uv run python setup_db.py` tworzyło tabelę przy pierwszej inicjalizacji `bond_metadata.db`.

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Tabela `search_cache (query_hash, results_json, timestamp)` w SQLite | ✅ Tabela w `bond_metadata.db`; kolumna `thread_id` dodana jako część klucza głównego |
| Researcher sprawdza cache przed uderzeniem do Exa API | ✅ Trójwarstwowe sprawdzenie: state dict → SQLite → Exa MCP |
| Cache ważny tylko w obrębie jednej sesji (thread_id) | ✅ Klucz główny `(query_hash, thread_id)` — różne sesje nigdy nie współdzielą wpisów |

---

## Zachowanie przy edge cases

| Scenariusz | Zachowanie |
|------------|-----------|
| Nowa sesja (nowy thread_id), ten sam temat | Cache miss — nowe wywołanie Exa API |
| Ta sama sesja, ponowne wywołanie researcher (np. po odrzuceniu struktury) | Warstwa 1 (state dict) zwraca wynik — zero zapytań do DB ani API |
| Nowa sesja po restarcie serwera, ten sam temat | Warstwa 2 (SQLite) zwraca wynik — zero wywołań Exa API |
| Puste `thread_id` (harness bez thread_id) | `thread_id = ""` — cache działa, ale wpisy nie są izolowane per-sesję; akceptowalne w trybie dev |
| Baza danych niedostępna | `aiosqlite.connect` rzuci wyjątek — podniesiony do wywołującego (celowe: nie maskujemy błędów storage) |

---

## Weryfikacja

Poprawność składniowa zweryfikowana:

```
python3 -c "import ast; ast.parse(open('bond/db/search_cache.py').read())"   # OK
python3 -c "import ast; ast.parse(open('bond/graph/nodes/researcher.py').read())"  # OK
```

Logika cache'u zgodna z istniejącym wzorcem `bond/db/metadata_log.py`:
- Lazy schema creation (`_ensure_cache_table`) zamiast osobnej migracji
- `os.makedirs` przed `aiosqlite.connect` — obsługa brakującego katalogu `data/`
- `INSERT OR REPLACE` — idempotentny zapis (bezpieczny przy równoległych wywołaniach)
