# 20-GOOGLE-DRIVE-MCP-CONNECTOR Podsumowanie: Konektor MCP dla Google Drive

**Data ukończenia:** 2026-03-25
**Faza:** 03 — Streaming API i Frontend
**Plan:** 20 — Google Drive MCP Connector
**Status:** ✅ Zakończone

---

## Cel

Automatyczne pobieranie artykułów do korpusu prosto z Google Drive poprzez serwer MCP.

- Konfiguracja serwera MCP (`bond-drive`) integrującego Google Drive z Claude Code i agentami LangGraph.
- Udostępnienie narzędzia `list_drive_folder` do listowania plików w wybranym folderze.
- Implementacja endpointu `/api/corpus/drive-ingest` z rozszerzonym wynikiem (listing + ingestion).

---

## Architektura

```
Claude Code / LangGraph Agent
        │
        ├─ MCP tool: list_drive_folder(folder_id) ──► bond/mcp/drive_server.py
        │                                                    │
        ├─ MCP tool: drive_ingest(folder_id, source_type) ──┤
        │                                                    │
        │                                          bond/corpus/sources/drive_source.py
        │                                          ├─ build_drive_service()
        │                                          ├─ list_folder_files()
        │                                          └─ ingest_drive_folder()
        │
        └─ POST /api/corpus/drive-ingest ──────────► bond/api/routes/corpus.py
                                                      └─ DriveIngestResult (files_found + ingestion)
```

---

## Nowe i zmienione pliki

### `bond/mcp/__init__.py` (nowy)
Pusty plik inicjujący pakiet MCP.

### `bond/mcp/drive_server.py` (nowy)
FastMCP server rejestrujący dwa narzędzia (oba `async`, I/O delegowane przez `asyncio.to_thread`):

```python
mcp = FastMCP("bond-drive")

@mcp.tool()
async def list_drive_folder(folder_id: str) -> list[DriveFileInfo]:
    """Zwraca listę obsługiwanych plików w folderze Drive."""
    service = await asyncio.to_thread(build_drive_service)
    return await asyncio.to_thread(list_folder_files, service, folder_id)

@mcp.tool()
async def drive_ingest(
    folder_id: str, source_type: SourceType = SourceType.OWN_TEXT
) -> dict:
    """Pobiera i ingestuje pliki z folderu Drive do korpusu."""
    return await asyncio.to_thread(
        ingest_drive_folder, folder_id=folder_id, source_type=source_type.value
    )
```

Uruchomienie: `uv run python -m bond.mcp.drive_server`

### `.claude/settings.json` (nowy)
Konfiguracja serwera MCP na poziomie projektu:

```json
{
  "mcpServers": {
    "bond-drive": {
      "command": "uv",
      "args": ["run", "python", "-m", "bond.mcp.drive_server"],
      "env": {
        "GOOGLE_AUTH_METHOD": "oauth",
        "GOOGLE_CREDENTIALS_PATH": "./credentials.json"
      }
    }
  }
}
```

Claude Code automatycznie wykrywa tę konfigurację i udostępnia narzędzia `list_drive_folder` i `drive_ingest` podczas pracy w katalogu projektu.

### `bond/models.py` (zaktualizowany)
Dodano dwa nowe modele Pydantic:

```python
class DriveFileInfo(BaseModel):
    id: str
    name: str
    mime_type: str

class DriveIngestResult(BaseModel):
    files_found: int
    articles_ingested: int
    total_chunks: int
    source_type: str
    files: list[DriveFileInfo] = []
    warnings: list[str] = []
```

### `bond/corpus/sources/drive_source.py` (zaktualizowany)
`list_folder_files` zwraca teraz `list[DriveFileInfo]` zamiast `list[dict]` — konwertuje odpowiedź Google API (`mimeType` → `mime_type`) bezpośrednio do modeli Pydantic. `ingest_drive_folder` używa atrybutów obiektów (`f.id`, `f.name`, `f.mime_type`) zamiast kluczy słownika.

### `bond/api/routes/corpus.py` (zaktualizowany)
Dodano endpoint `POST /api/corpus/drive-ingest`:
- Najpierw listuje pliki przez `build_drive_service()` + `list_folder_files()` (zwraca `list[DriveFileInfo]`)
- Następnie wywołuje `ingest_drive_folder()` w celu ingestion
- Zwraca `DriveIngestResult` zawierający listing plików i podsumowanie ingestion; ręczna konwersja słownikowa usunięta — `list_folder_files` dostarcza gotowe obiekty Pydantic

Istniejący endpoint `POST /api/corpus/ingest/drive` pozostaje niezmieniony.

### `pyproject.toml` (zaktualizowany)
Dodano zależność `mcp>=1.0` (oficjalny Python SDK dla protokołu MCP, zawiera `FastMCP`).

---

## Kryteria akceptacji (AC)

| AC | Status |
|----|--------|
| Konfiguracja serwera MCP dla Google Drive | ✅ `.claude/settings.json` rejestruje `bond-drive` uruchamiany przez `uv run python -m bond.mcp.drive_server` |
| Agent może listować pliki w folderze | ✅ Narzędzie MCP `list_drive_folder(folder_id)` zwraca listę `{id, name, mimeType}` |
| Endpoint `/api/corpus/drive-ingest` | ✅ `POST /api/corpus/drive-ingest` listuje pliki, ingestuje korpus, zwraca `DriveIngestResult` |

---

## Obsługiwane formaty plików

| MIME Type | Rozszerzenie | Obsługa |
|-----------|-------------|---------|
| `application/pdf` | .pdf | PyMuPDF |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | .docx | python-docx |
| `text/plain` | .txt | Bezpośredni odczyt |
| `application/vnd.google-apps.document` | Google Docs | Eksport jako plain text |

---

## Konfiguracja autoryzacji Google

Serwer obsługuje dwie metody uwierzytelniania (konfiguracja przez `.env`):

| Zmienna | Wartość | Opis |
|---------|---------|------|
| `GOOGLE_AUTH_METHOD` | `oauth` (domyślnie) | OAuth installed-app flow, wymaga `credentials.json` i interaktywnego logowania przy pierwszym uruchomieniu |
| `GOOGLE_AUTH_METHOD` | `service_account` | Service Account, wymaga klucza JSON; folder musi być udostępniony e-mailem konta serwisowego |
| `GOOGLE_CREDENTIALS_PATH` | `./credentials.json` | Ścieżka do pliku z poświadczeniami |

---

## Różnica między `/ingest/drive` a `/drive-ingest`

| Endpoint | Response | Zastosowanie |
|----------|----------|--------------|
| `POST /api/corpus/ingest/drive` | `BatchIngestResult` | Prosty ingestion — summary bez listingu |
| `POST /api/corpus/drive-ingest` | `DriveIngestResult` | Rozszerzony — zawiera `files_found` i pełny listing plików; przeznaczony do wywołania przez MCP lub frontend z podglądem |

---

## Weryfikacja

Aby przetestować serwer MCP lokalnie:

```bash
# Uruchom serwer MCP bezpośrednio
uv run python -m bond.mcp.drive_server

# Przetestuj endpoint drive-ingest
curl -X POST http://localhost:8000/api/corpus/drive-ingest \
  -H "Content-Type: application/json" \
  -d '{"folder_id": "<FOLDER_ID>", "source_type": "own"}'
```

Narzędzia MCP są automatycznie dostępne w Claude Code po otwarciu projektu (dzięki `.claude/settings.json`).
