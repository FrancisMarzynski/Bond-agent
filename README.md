# Bond — Agent Redakcyjny

Agent AI wspomagający pracę redakcyjną, który buduje przeszukiwalny korpus z wielu źródeł treści i przeprowadza pełen pipeline badań oraz pisania artykułów z punktami zatwierdzenia przez człowieka (HITL).

## Opis

Bond składa się z dwóch głównych warstw:

**Korpus stylistyczny** — pobiera artykuły z czystego tekstu, plików (PDF, DOCX), adresów URL oraz folderów Google Drive. Treści są dzielone na fragmenty, osadzane przy użyciu `sentence-transformers` i przechowywane w ChromaDB do semantycznego wyszukiwania.

**Tryb Autora** — pipeline oparty na LangGraph, który na podstawie tematu i słów kluczowych przeprowadza badania webowe (Exa), proponuje strukturę artykułu (H1/H2/H3), generuje szkic zgodny z SEO z wstrzykniętymi fragmentami stylistycznymi RAG, a następnie zapisuje zatwierdzone metadane. Na etapach struktury i szkicu wymagane jest zatwierdzenie przez człowieka.

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

**Serwer API (korpus):**

```bash
uv run uvicorn bond.api.main:app --reload
```

API dostępne pod adresem `http://localhost:8000`. Interaktywna dokumentacja pod `http://localhost:8000/docs`.

**Tryb Autora — CLI (harness):**

```bash
uv run python -m bond.harness
```

Uruchamia interaktywny pipeline Trybu Autora w terminalu: podaj temat i słowa kluczowe, a następnie zatwierdzaj lub odrzucaj kolejne etapy (struktura, szkic).

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

### Korpus

| Zmienna | Domyślna | Opis |
|---------|----------|------|
| `CHROMA_PATH` | `./data/chroma` | Ścieżka do przechowywania ChromaDB |
| `ARTICLE_DB_PATH` | `./data/articles.db` | Dziennik artykułów SQLite |
| `LOW_CORPUS_THRESHOLD` | `10` | Ostrzeżenie gdy korpus ma mniej artykułów niż ta wartość |
| `RAG_TOP_K` | `5` | Liczba fragmentów zwracanych przy każdym wyszukiwaniu |
| `MAX_BLOG_POSTS` | `50` | Maksymalna liczba postów pobieranych przy imporcie z URL |
| `GOOGLE_AUTH_METHOD` | `oauth` | `oauth` lub `service_account` |
| `GOOGLE_CREDENTIALS_PATH` | `./credentials.json` | Ścieżka do pliku poświadczeń Google |

### Tryb Autora

Wymagane klucze API (muszą być ustawione w `.env`):

| Zmienna | Opis |
|---------|------|
| `OPENAI_API_KEY` | Klucz OpenAI — używany przez węzły researcher i writer |
| `EXA_API_KEY` | Klucz Exa — używany do badań webowych |

Opcjonalne ustawienia (pokazano wartości domyślne):

| Zmienna | Domyślna | Opis |
|---------|----------|------|
| `CHECKPOINT_DB_PATH` | `./data/bond_checkpoints.db` | Baza danych checkpointów LangGraph (SqliteSaver) |
| `METADATA_DB_PATH` | `./data/bond_metadata.db` | Dziennik metadanych zatwierdzonych artykułów |
| `RESEARCH_MODEL` | `gpt-4o-mini` | Model LLM używany przez węzeł badań |
| `DRAFT_MODEL` | `gpt-4o` | Model LLM używany przez węzeł pisania |
| `MIN_WORD_COUNT` | `800` | Minimalna liczba słów w wygenerowanym szkicu |
| `DUPLICATE_THRESHOLD` | `0.85` | Próg podobieństwa cosinusowego przy wykrywaniu duplikatów |

## Programowanie

```bash
uv run pytest          # uruchom testy
uv run ruff check .    # sprawdź styl kodu
uv run ruff format .   # formatuj kod
```
