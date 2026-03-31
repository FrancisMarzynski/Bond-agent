# FASTAPI-INIT-CORS-HEALTH Podsumowanie: Inicjalizacja FastAPI, CORS i endpoint /health

**Data ukończenia:** 2026-03-31
**Faza:** 03 — Streaming API i Frontend
**Plan:** FastAPI Init & CORS
**Status:** ✅ Zakończone

---

## Cel

Setup szkieletu API gotowego do komunikacji z frontendem:

- FastAPI z obsługą lifespan (inicjalizacja grafu LangGraph przy starcie).
- Middleware `CORSMiddleware` skonfigurowane dla domeny frontendu (konfigurowalnie przez `.env`).
- Endpoint `/health` zwracający status połączenia z każdą bazą danych.

---

## Architektura

```
bond/api/main.py
    │
    ├─ lifespan(app) ──────────────────► compile_graph()
    │                                         │
    │                              AsyncSqliteSaver → bond_checkpoints.db
    │                              LangGraph StateGraph compiled
    │                              app.state.graph = graph
    │
    ├─ CORSMiddleware ─────────────────► settings.cors_origins (z .env)
    │                                    domyślnie: ["http://localhost:3000"]
    │
    └─ GET /health ────────────────────► asyncio.gather(
                                             _check_sqlite(checkpoint_db),
                                             _check_sqlite(metadata_db),
                                             _check_sqlite(articles_db),
                                         ) + run_in_executor(_check_chroma_sync)
                                         + getattr(app.state, "graph", None)
```

---

## Zmodyfikowane pliki

### `bond/api/main.py`

#### Lifespan — inicjalizacja grafu

Bez zmian w logice — `compile_graph()` już było jako `@asynccontextmanager`. Graf LangGraph kompiluje się z `AsyncSqliteSaver` jako checkpointerem i przypisywany jest do `app.state.graph` przed przyjęciem pierwszego requestu.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with compile_graph() as graph:
        app.state.graph = graph
        yield
```

#### CORSMiddleware

Bez zmian w logice — origins odczytywane z `settings.cors_origins` (pole `list[str]` z `pydantic-settings`, domyślnie `["http://localhost:3000"]`).

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### `/health` — pełny status baz danych

**Główna zmiana:** endpoint wzbogacony o równoległe sondy baz danych zamiast prostego `{"status": "ok"}`.

**Trzy SQLite (aiosqlite):**
```python
async def _check_sqlite(path: str) -> str:
    try:
        async with aiosqlite.connect(path) as conn:
            await conn.execute("SELECT 1")
        return "ok"
    except Exception as exc:
        return f"error: {exc}"
```

Sondy uruchamiane przez `asyncio.gather` — nie blokują się wzajemnie.

**ChromaDB (synchroniczny klient):**
```python
def _check_chroma_sync() -> str:
    try:
        from bond.store.chroma import get_chroma_client
        get_chroma_client().heartbeat()
        return "ok"
    except Exception as exc:
        return f"error: {exc}"
```

Wywołany przez `loop.run_in_executor(None, ...)` — nie blokuje event loop ASGI.

**Graph readiness:**
```python
graph_status = "ok" if getattr(request.app.state, "graph", None) is not None else "not_ready"
```

**Przykładowa odpowiedź (wszystko OK):**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "timestamp": "2026-03-31T10:00:00+00:00",
  "checks": {
    "graph": "ok",
    "checkpoint_db": "ok",
    "metadata_db": "ok",
    "articles_db": "ok",
    "chroma": "ok"
  }
}
```

**Przykładowa odpowiedź (degraded):**
```json
{
  "status": "degraded",
  "version": "0.1.0",
  "timestamp": "2026-03-31T10:00:00+00:00",
  "checks": {
    "graph": "ok",
    "checkpoint_db": "ok",
    "metadata_db": "error: unable to open database file",
    "articles_db": "ok",
    "chroma": "ok"
  }
}
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Aplikacja FastAPI z obsługą lifespan (inicjalizacja grafu) | ✅ `compile_graph()` wywoływany przy starcie; graf dostępny przez cały czas życia aplikacji pod `app.state.graph` |
| CORSMiddleware skonfigurowane dla domeny frontendu | ✅ `allow_origins=settings.cors_origins`; konfiguracja przez `.env` (domyślnie `http://localhost:3000`) |
| Endpoint `/health` zwracający status połączenia z bazami | ✅ Sprawdza 3 bazy SQLite + ChromaDB + gotowość grafu; status zagregowany (`"ok"` / `"degraded"`) |

---

## Bazy danych sprawdzane przez `/health`

| Klucz w `checks` | Baza | Metoda sondy |
|------------------|------|--------------|
| `checkpoint_db` | `bond_checkpoints.db` | `aiosqlite` → `SELECT 1` |
| `metadata_db` | `bond_metadata.db` | `aiosqlite` → `SELECT 1` |
| `articles_db` | `articles.db` | `aiosqlite` → `SELECT 1` |
| `chroma` | ChromaDB (`./data/chroma`) | `PersistentClient.heartbeat()` w thread pool |
| `graph` | LangGraph (in-memory) | `app.state.graph is not None` |

---

## Konfiguracja przez `.env`

| Zmienna | Domyślna wartość | Opis |
|---------|-----------------|------|
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Lista dozwolonych origin dla CORS |
| `CHECKPOINT_DB_PATH` | `./data/bond_checkpoints.db` | Ścieżka do bazy checkpointów |
| `METADATA_DB_PATH` | `./data/bond_metadata.db` | Ścieżka do bazy metadanych |
| `ARTICLE_DB_PATH` | `./data/articles.db` | Ścieżka do katalogu artykułów |
| `CHROMA_PATH` | `./data/chroma` | Ścieżka do ChromaDB |

---

## Weryfikacja

```bash
uv run uvicorn bond.api.main:app --reload --port 8000
curl http://localhost:8000/health
```

Oczekiwana odpowiedź: `{"status": "ok", ..., "checks": {"graph": "ok", ...}}` gdy wszystkie bazy dostępne.

Przy brakującej bazie — pole odpowiedniego klucza zawiera `"error: ..."`, a `status` zmienia się na `"degraded"`.
