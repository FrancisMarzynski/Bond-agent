# Bond — Agent Redakcyjny

Agent AI wspomagający pracę redakcyjną, który buduje przeszukiwalny korpus z wielu źródeł treści i wykorzystuje generowanie wspomagane wyszukiwaniem (RAG) do pomocy przy zadaniach pisarskich.

## Opis

Bond pobiera artykuły z czystego tekstu, plików (PDF, DOCX), adresów URL oraz folderów Google Drive. Treści są dzielone na fragmenty, osadzane przy użyciu `sentence-transformers` i przechowywane w ChromaDB do semantycznego wyszukiwania.

## Wymagania

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)

## Instalacja

```bash
uv sync
```

Skopiuj `.env.example` do `.env` i dostosuj według potrzeb (patrz [Konfiguracja](#konfiguracja)).

Aby korzystać z importu z Google Drive, umieść plik `credentials.json` w głównym katalogu projektu (OAuth2 lub konto serwisowe).

## Uruchamianie

```bash
uv run uvicorn bond.api.main:app --reload
```

API dostępne pod adresem `http://localhost:8000`. Interaktywna dokumentacja pod `http://localhost:8000/docs`.

## API

### Stan serwera

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| GET | `/health` | Sprawdzenie stanu serwera |

### Korpus

| Metoda | Ścieżka | Opis |
|--------|---------|------|
| POST | `/api/corpus/ingest/text` | Importuj czysty tekst |
| POST | `/api/corpus/ingest/file` | Importuj plik (PDF, DOCX, TXT) |
| POST | `/api/corpus/ingest/url` | Pobierz i importuj blog/URL |
| POST | `/api/corpus/ingest/drive` | Importuj folder Google Drive |
| GET | `/api/corpus/status` | Liczba artykułów i fragmentów |
| GET | `/api/corpus/smoke-test` | Wykonaj test wyszukiwania |

Wszystkie endpointy importu przyjmują pole `source_type`: `"own"` dla własnych treści, `"external"` dla materiałów referencyjnych zewnętrznych.

## Konfiguracja

Ustawienia są wczytywane z pliku `.env` (wszystkie opcjonalne — pokazano wartości domyślne):

| Zmienna | Domyślna | Opis |
|---------|----------|------|
| `CHROMA_PATH` | `./data/chroma` | Ścieżka do przechowywania ChromaDB |
| `ARTICLE_DB_PATH` | `./data/articles.db` | Dziennik artykułów SQLite |
| `LOW_CORPUS_THRESHOLD` | `10` | Ostrzeżenie gdy korpus ma mniej artykułów niż ta wartość |
| `RAG_TOP_K` | `5` | Liczba fragmentów zwracanych przy każdym wyszukiwaniu |
| `MAX_BLOG_POSTS` | `50` | Maksymalna liczba postów pobieranych przy imporcie z URL |
| `GOOGLE_AUTH_METHOD` | `oauth` | `oauth` lub `service_account` |
| `GOOGLE_CREDENTIALS_PATH` | `./credentials.json` | Ścieżka do pliku poświadczeń Google |

## Programowanie

```bash
uv run pytest          # uruchom testy
uv run ruff check .    # sprawdź styl kodu
uv run ruff format .   # formatuj kod
```
