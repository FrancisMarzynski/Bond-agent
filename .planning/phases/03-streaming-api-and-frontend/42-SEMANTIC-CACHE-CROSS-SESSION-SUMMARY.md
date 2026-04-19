# 42 — Semantyczny cache: współdzielenie między sesjami i TTL

## Co zostało zmienione

`bond/db/search_cache.py` i `bond/graph/nodes/researcher.py` zostały zaktualizowane tak, by cache wyników wyszukiwania Exa był **współdzielony między wszystkimi sesjami** i **wygasał automatycznie** po 7 dniach.

---

## Problem

`save_cached_result` / `get_cached_result` używały `(query_hash, thread_id)` jako złożonego klucza głównego.  
Ten sam temat wyszukany w sesji A i sesji B generował dwa identyczne wywołania Exa API — cache nigdy nie dawał trafienia między sesjami.  
W środowisku produkcyjnym (gdzie tematy BIM, XR i instalacje powtarzają się codziennie) powodowało to niepotrzebne powtarzające się koszty API.

Dodatkowo nie było TTL — wynik z cache mógł teoretycznie być zwracany w nieskończoność, serwując nieaktualne dane.

---

## Zmiany

### `bond/db/search_cache.py`

| Aspekt | Przed | Po |
|---|---|---|
| Klucz główny | `(query_hash, thread_id)` | Tylko `query_hash` |
| Rola `thread_id` | Część klucza wyszukiwania | Przechowywany jako kolumna audytowa, nieużywany do wyszukiwania |
| TTL | Brak (permanentny) | 7 dni (`_TTL_DAYS = 7`) |
| Obsługa wygasłych wpisów | Brak | `get_cached_result` zwraca `None`; nadpisywany przy następnym zapisie |
| Migracja schematu | — | Auto-wykrywa stary złożony PK przez `PRAGMA table_info`, usuwa i odtwarza tabelę |

**Nowe sygnatury funkcji:**
```python
async def get_cached_result(query_hash: str) -> str | None
async def save_cached_result(query_hash: str, results_json: str, thread_id: str = "") -> None
```

**Sprawdzenie TTL** (wewnątrz `get_cached_result`):
```python
age = datetime.now(timezone.utc) - datetime.fromisoformat(cached_at_str)
if age.days >= _TTL_DAYS:
    return None
```

**Logika migracji** (wewnątrz `_ensure_table_once`):
```python
cursor = await conn.execute("PRAGMA table_info(search_cache)")
cols = await cursor.fetchall()
needs_migration = any(col[1] == "thread_id" and col[5] > 0 for col in cols)
```
Jeśli wykryty zostanie stary złożony PK, tabela jest usuwana i odtwarzana. Stare wpisy są odrzucane (możliwe do odtworzenia z Exa).

### `bond/graph/nodes/researcher.py`

- Odczyt cache (warstwa 2): `get_cached_result(query_hash, thread_id)` → `get_cached_result(query_hash)`
- Zapis cache (warstwa 2): `save_cached_result(query_hash, thread_id, raw_results)` → `save_cached_result(query_hash, raw_results, thread_id)`
- Komentarz zmieniony z „SQLite session cache" na „SQLite cross-session cache (keyed by query_hash only, TTL 7 days)"

---

## Projekt klucza cache

`compute_query_hash(topic, keywords)` pozostaje bez zmian — SHA-256 z `"topic:kw1:kw2:..."` (słowa kluczowe posortowane dla stabilności).  
Usunięcie `thread_id` z klucza oznacza: ten sam temat + te same słowa kluczowe = ten sam hash = gwarantowane trafienie cache między sesjami.

---

## Dlaczego bez semantycznego podobieństwa (opcjonalne AC)

Opcjonalne AC (podobieństwo cosinusowe między embeddingami zapytań) zostało odłożone.  
Dopasowanie hashowe jest wystarczające: `compute_query_hash` już normalizuje kolejność słów kluczowych.  
Dopasowanie semantyczne dodałoby opóźnienie (wywołanie embeddingu per zapytanie) i infrastrukturę (vector store dla hashy zapytań) — nieuzasadnione do czasu pojawienia się dowodów na rozbieżności w sformułowaniach słów kluczowych powodujące chybienia.

---

## Kryteria akceptacji

- [x] `thread_id` usunięty z klucza cache — wyniki są współdzielone między wszystkimi sesjami
- [x] TTL 7 dni zaimplementowany — wpisy starsze niż 7 dni zwracają `None` (wyzwalają świeże wywołanie Exa)
- [ ] Dopasowanie przez podobieństwo semantyczne — odłożono (dopasowanie hashowe jest wystarczające)

---

## Zmodyfikowane pliki

- `bond/db/search_cache.py`
- `bond/graph/nodes/researcher.py`
