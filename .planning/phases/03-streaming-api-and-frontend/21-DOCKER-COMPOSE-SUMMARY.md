# 21-DOCKER-COMPOSE Podsumowanie: Orkiestracja środowiska multi-container

**Data ukończenia:** 2026-03-31
**Faza:** 03 — Streaming API i Frontend
**Plan:** 21 — Docker Compose Orchestration
**Status:** ✅ Zakończone

---

## Cel

Konfiguracja środowiska multi-container łączącego serwis `bond-api` (FastAPI) z bazą wektorową ChromaDB. Zapewnienie trwałego zapisu danych oraz izolacji sieciowej baz danych.

---

## Architektura

```
Host
 │
 ├─ port 8000 ──────────────────── bond-api (FastAPI)
 │                                     │
 │                             network: bond-public
 │                             network: bond-internal
 │                                     │
 │                           chromadb:8000 (internal only)
 │                                     │
 │                              network: bond-internal
 │                              [internal: true — niedostępne z hosta]
 │
 └─ volumes:
       bond-data  → /app/data          (SQLite: articles, checkpoints, metadata)
       chroma-data → /chroma/chroma    (wektory ChromaDB)
```

---

## Nowe pliki

### `Dockerfile`

Wieloetapowy obraz `python:3.11-slim`:
- Instaluje `uv` i synchronizuje zależności przez `uv sync --frozen --no-dev`.
- Kopiuje tylko `bond/` i pliki konfiguracyjne (`.dockerignore` wyklucza `.venv`, `data/`, `frontend/`, `tests/`).
- Uruchamia `uvicorn bond.api.main:app --host 0.0.0.0 --port 8000`.

### `docker-compose.yml`

```yaml
services:
  bond-api:
    ports: ["8000:8000"]
    networks: [bond-public, bond-internal]
    volumes: [bond-data:/app/data]
    depends_on:
      chromadb:
        condition: service_healthy

  chromadb:
    image: chromadb/chroma:1.0.12
    expose: ["8000"]                    # tylko wewnętrznie
    networks: [bond-internal]
    volumes: [chroma-data:/chroma/chroma]

networks:
  bond-public:   { driver: bridge }
  bond-internal: { driver: bridge, internal: true }  # ← izolacja sieciowa

volumes:
  bond-data:    { driver: local }
  chroma-data:  { driver: local }
```

Healthcheck ChromaDB:
```bash
curl -f http://localhost:8000/api/v2/heartbeat
```
`bond-api` startuje dopiero gdy ChromaDB jest zdrowe (`condition: service_healthy`).

### `.env.docker`

Plik środowiskowy dla trybu Docker (nie commitowany — dodany do `.gitignore`):
- `CHROMA_HOST=chromadb` — aktywuje tryb HTTP client w `bond/store/chroma.py`.
- `CHROMA_PORT=8000`
- Ścieżki SQLite wskazują na `/app/data/` (volume `bond-data`).

### `.dockerignore`

Wyklucza z kontekstu budowania: `.venv/`, `data/`, `chroma/`, `frontend/`, `tests/`, `.planning/`, pliki `.env*`, `credentials.json`.

---

## Zmodyfikowane pliki

### `bond/config.py`

Dodano dwa nowe pola do `Settings`:

```python
chroma_host: str = ""      # pusty → tryb lokalny (PersistentClient)
chroma_port: int = 8000    # port ChromaDB HTTP server
```

### `bond/store/chroma.py`

Funkcja `get_chroma_client()` przełącza się między trybami na podstawie `settings.chroma_host`:

```python
def get_chroma_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        if settings.chroma_host:
            _client = chromadb.HttpClient(
                host=settings.chroma_host,
                port=settings.chroma_port,
            )
        else:
            _client = chromadb.PersistentClient(path=settings.chroma_path)
    return _client
```

Zmiana jest wstecznie kompatybilna — lokalne środowisko deweloperskie pozostaje bez zmian (`CHROMA_HOST` jest domyślnie puste).

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| `docker-compose.yml` definiuje serwisy `bond-api` i `chromadb` | ✅ Oba serwisy zdefiniowane z odpowiednimi obrazami i konfiguracją |
| Volumes dla trwałego zapisu SQLite i wektorów Chroma | ✅ `bond-data` (SQLite) i `chroma-data` (Chroma) jako named volumes |
| Izolacja sieciowa (internal network dla baz danych) | ✅ `bond-internal` z flagą `internal: true`; ChromaDB `expose` (nie `ports`) |

---

## Uruchomienie

```bash
# Skopiuj i uzupełnij .env.docker
cp .env.docker .env.docker.local
# Wypełnij OPENAI_API_KEY i inne sekrety

# Zbuduj i uruchom
docker compose --env-file .env.docker up --build

# Health check
curl http://localhost:8000/health
```

Oczekiwana odpowiedź po poprawnym starcie:

```json
{
  "status": "ok",
  "checks": {
    "graph": "ok",
    "checkpoint_db": "ok",
    "metadata_db": "ok",
    "articles_db": "ok",
    "chroma": "ok"
  }
}
```

---

## Weryfikacja

- `docker compose config --quiet` → bez błędów (składnia YAML poprawna).
- `uv run python -c "from bond.store.chroma import get_chroma_client; print(type(get_chroma_client()).__name__)"` → `Client` (tryb lokalny bez `CHROMA_HOST`).
- Lokalny serwer deweloperski działa bez zmian — `CHROMA_HOST` domyślnie puste, `PersistentClient` pozostaje aktywny.
