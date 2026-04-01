# 24-BACKEND-CONTAINERIZATION Podsumowanie: Konteneryzacja backendu

**Data ukończenia:** 2026-04-01
**Faza:** 03 — Streaming API i Frontend
**Plan:** 24 — Backend Containerization
**Status:** ✅ Zakończone

---

## Cel

Przygotowanie gotowego do produkcji obrazu Docker dla logiki agenta Bond. Obraz oparty na `python:3.11-slim` z optymalizacją warstw dla szybkiej przebudowy po zmianach kodu.

---

## Architektura obrazu

```
python:3.11-slim
│
├─ [warstwa 1] pip install uv           ← instalacja menedżera pakietów
├─ [warstwa 2] COPY pyproject.toml + uv.lock
├─ [warstwa 3] uv sync --no-install-project  ← zależności (cache ~2GB, torch/chroma)
├─ [warstwa 4] COPY bond/ setup_db.py
├─ [warstwa 5] uv sync --no-editable    ← instalacja samego pakietu bond
├─ [warstwa 6] mkdir /app/data
│
EXPOSE 8000
CMD uv run uvicorn bond.api.main:app --host 0.0.0.0 --port 8000
```

Kluczowe: warstwy 1–3 są cache'owane — przebudowa po zmianie kodu zajmuje tylko czas warstwy 4–5 (< 1s).

---

## Zmodyfikowane pliki

### `Dockerfile`

Poprawiona kolejność kroków budowania względem pierwotnej wersji:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency manifests first — layer cached until deps change
COPY pyproject.toml uv.lock ./

# Install only third-party dependencies (skip the project itself)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY bond/ ./bond/
COPY setup_db.py ./

# Install the project itself (fast — deps already cached above)
RUN uv sync --frozen --no-dev --no-editable

# Create data directory (SQLite DBs and volumes mounted here)
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "bond.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Poprawka względem poprzedniej wersji:** oryginalne `uv sync --frozen --no-dev --no-editable` uruchamiane było przed `COPY bond/`, co powodowało próbę instalacji pakietu `bond` bez kodu źródłowego. Rozwiązanie: podział na dwa kroki — `--no-install-project` (tylko zależności) i pełne `uv sync` po skopiowaniu źródeł.

### `.dockerignore` (bez zmian — już poprawny)

```
.venv/
.git/
__pycache__/
*.py[cod]
data/
chroma/
*.db
*.sqlite3
frontend/
tests/
.planning/
.claude/
uvicorn.log
.env
.env.docker
credentials.json
```

Wykluczone kategorie:
- **Środowisko wirtualne:** `.venv/` — zależności instalowane są wewnątrz kontenera
- **Cache Python:** `__pycache__/`, `*.py[cod]` — artefakty kompilacji
- **Dane bazy:** `data/`, `chroma/`, `*.db`, `*.sqlite3` — montowane przez volumes
- **Frontend:** `frontend/` — osobny kontener/serwer
- **Testy i konfiguracja:** `tests/`, `.planning/`, `.claude/`
- **Sekrety:** `.env`, `.env.docker`, `credentials.json`

---

## Wynik budowania

```
docker build -t bond-agent:local .
```

```
#9  [5/9] uv sync --no-install-project → 153 packages installed in 13.2s  ✅
#12 [8/9] uv sync --no-editable        → Checked 153 packages in 1ms       ✅
#14 exporting to image                 → bond-agent:local (2.09GB)          ✅
```

Rozmiar: **2.09 GB** (dominuje `torch` ~1.4GB + `chromadb`/`onnxruntime` + `sentence-transformers`).

```
REPOSITORY    TAG     IMAGE ID       SIZE
bond-agent    local   fe1e5c3f1011   2.09GB
```

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Dockerfile oparty na `python:3.11-slim` z optymalizacją warstw | ✅ Dwuetapowy `uv sync`: deps osobno od pakietu |
| `.dockerignore` pomijający `.venv`, `__pycache__`, dane bazy | ✅ Wszystkie kategorie wykluczone |
| Pomyślny build obrazu lokalnie | ✅ `bond-agent:local` zbudowany bez błędów |

---

## Uruchomienie

```bash
# Build
docker build -t bond-agent:local .

# Uruchomienie standalone (bez ChromaDB — tylko dev/test)
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY=sk-... \
  bond-agent:local

# Uruchomienie z docker-compose (pełne środowisko)
docker compose --env-file .env.docker up --build
```

---

## Weryfikacja

```bash
# Rozmiar kontekstu budowania (powinno być ~1.1MB bez wykluczonych katalogów)
docker build --no-cache --progress=plain . 2>&1 | grep "transferring context"
# → transferring context: 1.08MB

# Sprawdzenie że bond jest importowalny
docker run --rm bond-agent:local uv run python -c "import bond; print('ok')"
# → ok
```
