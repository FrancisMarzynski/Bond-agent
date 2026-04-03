# 28-SMOKE-TEST-CONTAINER Podsumowanie: Weryfikacja środowiska kontenerowego

**Data ukończenia:** 2026-04-03  
**Faza:** 03 — Streaming API i Frontend  
**Plan:** 28 — Smoke Test – Środowisko Kontenerowe  
**Status:** ✅ Zakończone

---

## Cel

End-to-end weryfikacja stosu kontenerowego: uruchomienie na czystym środowisku, przeprowadzenie pełnego procesu researchu przez API oraz potwierdzenie zapisu metadanych w wolumenie.

---

## Kryteria akceptacji

| AC | Opis | Status |
|----|------|--------|
| AC1 | `docker-compose up` na czystym środowisku | ✅ |
| AC2 | Pełny proces researchu przez API | ✅ |
| AC3 | Zapis metadanych w wolumenie (persistence check) | ✅ |

---

## AC1 — Uruchomienie na czystym środowisku

```
docker compose down -v          # wyczyszczenie wolumenów
docker compose build --no-cache # budowanie bez cache
docker compose up -d            # uruchomienie
```

**Wynik:** Wszystkie 3 usługi uruchomione i sprawne:

```
NAME                         STATUS
bond-agent-bond-api-1        Up (running)
bond-agent-bond-frontend-1   Up (running)
bond-agent-chromadb-1        Up (healthy)
```

Endpoint zdrowotny potwierdza sprawność wszystkich komponentów:

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

### Wykryte błędy i poprawki

#### Bug 1: Healthcheck ChromaDB — brak `curl` w obrazie 1.0.12

Obraz `chromadb/chroma:1.0.12` nie zawiera `curl` ani żadnego klienta HTTP.  
Healthcheck oparty na `["CMD", "curl", "-f", ...]` failował z błędem `executable file not found`.

**Poprawka** (`docker-compose.yml`):

```yaml
# PRZED
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/v2/heartbeat"]

# PO
healthcheck:
  test: ["CMD-SHELL", "bash -c 'exec 3<>/dev/tcp/localhost/8000 && echo -e \"GET /api/v2/heartbeat HTTP/1.0\\r\\n\\r\\n\" >&3 && head -1 <&3 | grep -q 200'"]
```

Bash TCP redirect działa bez zewnętrznych narzędzi (bash jest dostępny w obrazie).

#### Bug 2: Limit pamięci 512M — za mało dla sentence-transformers

Model `paraphrase-multilingual-MiniLM-L12-v2` + PyTorch + FastAPI wymagają ok. 450–500 MB.  
Przy limicie 512M kontener bond-api kończył pracę po załadowaniu modelu.

**Poprawka** (`docker-compose.yml`):

```yaml
# PRZED
limits:
  cpus: "1.0"
  memory: 512M

# PO
limits:
  cpus: "2.0"
  memory: 1.5G
```

#### Bug 3: Brak `OPENAI_API_KEY` w `.env.docker`

`.env.docker` zawiera `OPENAI_API_KEY=` (pustą wartość placeholder). Klucz jest w `.env` (środowisko lokalne). Docker wczytywał tylko `.env.docker`, więc API wywoływało 401.

**Poprawka** (`docker-compose.yml`):

```yaml
# PRZED
env_file:
  - .env.docker

# PO — .env.docker nadpisuje lokalne ustawienia, .env dostarcza sekrety
env_file:
  - .env.docker
  - .env
```

`.env` jest wczytywany NA KOŃCU — jego wartości nadpisują puste pola z `.env.docker`.

#### Bug 4 (krytyczny): `asyncio.wait_for` anuluje generator SSE

W Python ≥3.11 `asyncio.wait_for(coro, timeout=1.0)` przy timeout **anuluje** wewnętrzną korutynę przez `CancelledError`. Ponieważ `CancelledError` jest `BaseException` (nie `Exception`), nie jest łapany w `_inner()`. Generator `_inner` zostaje sfinalizowany, a kolejne `__anext__()` podnosi `StopAsyncIteration`.

Objaw: strumień SSE kończył się natychmiast po `on_chain_start` dla `duplicate_check` (załadowanie modelu BERT trwa ~25s — dłużej niż 1s timeout). Historia wątku pokazywała `stage: idle` lub `stage: research` bez żadnych dalszych zdarzeń.

**Poprawka** (`bond/api/routes/chat.py`):

```python
# PRZED — asyncio.wait_for anuluje generator przy timeout
chunk = await asyncio.wait_for(gen.__anext__(), timeout=1.0)

# PO — asyncio.wait NIE anuluje zadania, tylko sprawdza timeout
if chunk_task is None:
    chunk_task = asyncio.ensure_future(gen.__anext__())

done, _ = await asyncio.wait({chunk_task}, timeout=1.0)

if done:
    chunk = chunk_task.result()   # StopAsyncIteration jeśli generator wyczerpany
    chunk_task = None
    yield chunk
    ...
else:
    # timeout — sprawdzamy heartbeat, zadanie kontynuuje
    if now - last_heartbeat > 15.0:
        yield heartbeat
```

---

## AC2 — Pełny proces researchu przez API

Przeprowadzono pełny przebieg pipeline'u przez SSE:

```
POST /api/chat/stream  {"message": "AI w diagnostyce medycznej 2026", "mode": "author"}
```

Sekwencja zdarzeń SSE (z timestampami rzeczywistymi):

```
[0s]   thread_id: c9939b8d-...
[0s]   node_start: duplicate_check
[0s]   stage: checking
[25s]  node_end: duplicate_check      ← czas ładowania modelu BERT: ~25s
[25s]  node_start: researcher
[25s]  stage: research
[67s]  token: [streaming synthesis GPT-4o-mini]  ← Exa MCP search + LLM: ~42s
...
[72s]  node_end: structure
[72s]  node_start: checkpoint_1
[72s]  stage: structure (running → pending)
[72s]  hitl_pause: {checkpoint_id: "checkpoint_1", research_report: "...", heading_structure: "..."}
```

**Wynik:** pipeline dotarł do checkpoint HITL z pełnym raportem badawczym (8 źródeł) i strukturą nagłówków.

---

## AC3 — Zapis metadanych w wolumenie

Weryfikacja danych zapisanych w wolumenie Docker `bond-agent_bond-data`:

```
/app/data/
├── articles.db              (0 B — puste, brak artykułów)
├── bond_checkpoints.db      (69 KB — 36 checkpointów LangGraph)
├── bond_checkpoints.db-shm  (32 KB)
├── bond_checkpoints.db-wal  (165 KB)
└── bond_metadata.db         (32 KB — 4 wiersze w tabeli search_cache)
```

Dane w SQLite przeżywają restart kontenera dzięki wolumenowi:

```yaml
volumes:
  bond-data:
    driver: local
```

Zweryfikowano też montowanie wolumenu ChromaDB:
```
chroma-data:/chroma/chroma  →  /var/lib/docker/volumes/bond-agent_chroma-data/_data
```

---

## Zmodyfikowane pliki

### `docker-compose.yml`

1. **Healthcheck ChromaDB** — zamiana `curl` na bash TCP redirect
2. **Limit pamięci bond-api** — podniesiony z 512M → 1.5G, CPU z 1.0 → 2.0
3. **env_file bond-api** — dodanie `.env` po `.env.docker` (sekrety z lokalnego `.env`)

### `bond/api/routes/chat.py`

**`_stream_graph_events`** — zastąpienie `asyncio.wait_for(gen.__anext__(), timeout=1.0)` przez `asyncio.wait({chunk_task}, timeout=1.0)`.

Kluczowa różnica:
- `asyncio.wait_for` **anuluje** coroutine przy timeout → przedwczesne zakończenie generatora
- `asyncio.wait` **nie anuluje** — czeka na wynik, timeout służy tylko do sprawdzenia heartbeat

---

## Architektura przepływu danych

```
Host (.env + .env.docker)
    │
    ▼
bond-api (port 8000)
    │  env: OPENAI_API_KEY, CHROMA_HOST=chromadb, ...
    ├─ /health          → sprawdza graph, SQLite, ChromaDB
    ├─ POST /api/chat/stream
    │      │
    │      ├─ LangGraph graph.astream_events()
    │      │      ├─ duplicate_check_node  (sentence-transformers → ChromaDB)
    │      │      ├─ researcher_node       (Exa MCP + ChatOpenAI)
    │      │      ├─ structure_node        (ChatOpenAI)
    │      │      └─ checkpoint_1_node     (interrupt → hitl_pause SSE)
    │      │
    │      └─ SSE events → klient
    │
    └─ /app/data/ → bond-data volume
           ├─ bond_checkpoints.db   (LangGraph checkpoints)
           └─ bond_metadata.db      (search_cache, metadata_log)

chromadb (sieć wewnętrzna, port 8000)
    └─ chroma-data volume → embeddingi korpusu

bond-frontend (port 3000)
    └─ API_URL=http://bond-api:8000
```

---

## Wydajność

| Etap | Czas (1. uruchomienie) |
|------|------------------------|
| Ładowanie modelu BERT (sentence-transformers) | ~25s |
| Exa MCP web search | ~5s |
| Synteza GPT-4o-mini (8 źródeł) | ~37s |
| Generowanie struktury (ChatOpenAI) | ~5s |
| **Łącznie do checkpoint_1** | **~72s** |

Pierwsze uruchomienie jest wolniejsze ze względu na pobranie modelu z HuggingFace Hub.  
Kolejne uruchomienia korzystają z cache PyTorch/HF (~25s → kilka sekund).

---

## Weryfikacja ręczna

```bash
# Uruchomienie czystego środowiska
docker compose down -v
docker compose build --no-cache
docker compose up -d

# Sprawdzenie zdrowia
curl http://localhost:8000/health

# Uruchomienie researchu
curl -N http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "AI w diagnostyce medycznej", "mode": "author"}'

# Sprawdzenie stanu sesji
curl http://localhost:8000/api/chat/history/<thread_id>
```
