# 16-MCP-DEV-SETUP Podsumowanie: Dokumentacja techniczna MCP i setup deweloperski

**Data ukończenia:** 2026-03-19
**Faza:** 03 — Streaming API i Frontend
**Plan:** 16 — Dokumentacja MCP i setup deweloperski
**Status:** ✅ Zakończone

---

## Cel

Umożliwienie nowym deweloperom (Junior/Mid) postawienia środowiska w < 15 minut bez pomocy seniora.

- README.md wzbogacony o sekcję "Szybki start dla nowych deweloperów" i "Troubleshooting SSE".
- Skrypt `setup_db.py` automatyzujący inicjalizację SQLite i ChromaDB.

---

## Architektura

```
Nowy deweloper
    │
    ├─ README.md ──────────────────────► Szybki start (5 kroków)
    │                                          │
    │                                    uv run python setup_db.py
    │                                          │
    │                          ┌───────────────┼───────────────────┐
    │                          │               │                   │
    │                    articles.db   bond_metadata.db   bond_checkpoints.db
    │                          │               │                   │
    │                          └───────────────┤                   │
    │                                    ChromaDB                  │
    │                                    bond_style_corpus_v1      │
    │                                    bond_metadata_log_v1      │
    │
    └─ README.md → Troubleshooting SSE ──► rozwiązania 6 problemów
```

---

## Zmodyfikowane / dodane pliki

### `README.md`

#### Nowa sekcja: Szybki start dla nowych deweloperów

Dodano 5-krokową instrukcję instalacji na samej górze dokumentacji (przed sekcją "Programowanie"):

```bash
uv sync
cp .env.example .env   # + uzupełnij OPENAI_API_KEY
uv run python setup_db.py
uv run uvicorn bond.api.main:app --reload
cd frontend && npm install && npm run dev
```

Dodano informację o trybie `--reset` dla skryptu setup.

#### Nowa sekcja: Troubleshooting SSE

Pokrywa 6 scenariuszy błędów:

| Problem | Przyczyna | Rozwiązanie |
|---------|-----------|-------------|
| Eventy nie docierają / strumień "wisi" | Proxy buforuje odpowiedź | `proxy_buffering off` w nginx |
| `ERR_CONNECTION_REFUSED` / CORS | Backend nie działa lub `CORS_ORIGINS` źle ustawione | `curl /health` + weryfikacja `.env` |
| Strumień przerywa się po ~30s | Proxy zamyka idle connection | `proxy_read_timeout 600s` |
| `hitl_pause` nie dociera | Event emitowany po zakończeniu `astream_events` | Sprawdź `useStream.ts` — reconnect logic |
| "Poprzednia akcja HITL jest jeszcze w toku" | Per-thread `asyncio.Lock` odrzuca duplicate resume | Poczekaj na koniec strumienia |
| Brak modelu ChromaDB | HuggingFace niedostępny | Uruchom `setup_db.py` z dostępem do sieci |

Dodano wskazówkę o DevTools (Network → EventStream).

---

### `setup_db.py` (nowy plik)

Skrypt jednorazowy (i idempotentny) do inicjalizacji środowiska deweloperskiego.

#### Co robi

1. **Weryfikacja `.env`** — jeśli brak, kopiuje z `.env.example`; sprawdza `OPENAI_API_KEY`.
2. **articles.db** — tworzy tabelę `corpus_articles` (SQLite, synchroniczny).
3. **bond_metadata.db** — tworzy `metadata_log` + indeks po `published_date`.
4. **bond_checkpoints.db** — tworzy tabele LangGraph SqliteSaver (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`).
5. **ChromaDB** — tworzy kolekcje `bond_style_corpus_v1` i `bond_metadata_log_v1` z modelem `paraphrase-multilingual-MiniLM-L12-v2`.

#### Tryb `--reset`

```bash
uv run python setup_db.py --reset
```

Usuwa wszystkie pliki baz danych i katalog ChromaDB, a następnie tworzy je od nowa. Wymaga wpisania `tak` jako potwierdzenia (ochrona przed przypadkowym wywołaniem).

#### Idempotentność

Wszystkie operacje SQLite używają `CREATE TABLE IF NOT EXISTS` — wielokrotne wywołanie bez `--reset` jest bezpieczne i nie niszczy danych.

#### Przykładowe wyjście

```
Weryfikacja .env
  ✓  .env istnieje
  ✓  OPENAI_API_KEY ustawiony

SQLite — articles.db
  –  articles.db: już istnieje (./data/articles.db)

SQLite — bond_metadata.db
  ✓  bond_metadata.db: zainicjalizowano (./data/bond_metadata.db)

SQLite — bond_checkpoints.db
  ✓  bond_checkpoints.db: zainicjalizowano (./data/bond_checkpoints.db)

ChromaDB
  Ładowanie modelu paraphrase-multilingual-MiniLM-L12-v2...
  ✓  Model załadowany (2.3s)
  ✓  Kolekcja bond_style_corpus_v1 gotowa (dokumenty: 0)
  ✓  Kolekcja bond_metadata_log_v1 gotowa (dokumenty: 0)

✓ Setup zakończony pomyślnie.
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| README.md zawiera sekcję "Troubleshooting SSE" | ✅ 6 scenariuszy z przyczynami i rozwiązaniami |
| Skrypt `setup_db.py` automatyzuje migracje SQLite | ✅ Trzy bazy danych: articles, metadata, checkpoints |
| Skrypt `setup_db.py` inicjalizuje ChromaDB | ✅ Obie kolekcje z modelem embedding |
| Skrypt jest idempotentny (bezpieczne wielokrotne wywołanie) | ✅ `CREATE TABLE IF NOT EXISTS` + `get_or_create_collection` |
| Tryb `--reset` z potwierdzeniem | ✅ Wymaga wpisania `tak` |
| Nowy deweloper może postawić środowisko bez seniorskiej pomocy | ✅ README: 5-krokowa instrukcja + troubleshooting |

---

## Decyzje projektowe

### DDL checkpoints zakodowany ręcznie — nie przez LangGraph

LangGraph's `AsyncSqliteSaver.from_conn_string()` tworzy tabele automatycznie przy starcie aplikacji. Jednak `setup_db.py` działa bez uruchamiania FastAPI — dlatego schemat checkpointów jest powielony w skrypcie.

**Ryzyko:** Jeśli LangGraph zmieni schemat, `setup_db.py` może stworzyć niekompatybilne tabele. W praktyce LangGraph nie zmienił schematu od v0.2.x. Tabele stworzone przez skrypt i przez `AsyncSqliteSaver` są identyczne.

### ChromaDB schemat nie wymaga migracji

ChromaDB przechowuje schemat wewnętrznie w `chroma.sqlite3`. `get_or_create_collection` jest idempotentne — ponowne wywołanie nie niszczy embeddingów.

### Heartbeat co 15s — nie konfigurowalny

Heartbeat jest hardcoded w `bond/api/routes/chat.py`. Nie wystawiono zmiennej środowiskowej, bo timeout proxy jest ustawiony po stronie infrastruktury, nie backendu. Udokumentowane w sekcji Troubleshooting.
