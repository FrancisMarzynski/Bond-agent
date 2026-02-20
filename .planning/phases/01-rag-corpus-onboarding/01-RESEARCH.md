# Phase 1: RAG Corpus Onboarding - Research

**Researched:** 2026-02-20
**Domain:** RAG ingestion pipeline — vector store setup, document parsing, web scraping, Google Drive integration
**Confidence:** MEDIUM-HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **Developer-only internal tooling** — no UX polish required; interface is intentionally throwaway because Phase 3 replaces corpus management surface entirely
- **All 4 ingestion paths ship in Phase 1**: text paste, file upload (PDF/DOCX/TXT), Google Drive folder, blog URL scraper
- **Source tagging**: two values only — "own text" and "external blogger"; taxonomy is a closed enum for now but extensible later
- **Batch-level tagging**: one tag per ingestion source (URL, Drive folder, etc.)
- **Tags affect retrieval weighting**: own text fragments preferred over external blogger fragments
- **Failure handling — skip and warn, continue**: blog URL unreachable → skip+warn; PDF/DOCX parse failure → skip+warn; Drive folder empty/unreadable → warn, zero articles, continue
- **Per-item inline warnings** are sufficient — no end-of-batch summary needed
- **Retrieval smoke test output**: top-N fragments with cosine similarity scores and source metadata (author tag, source type)
- **Smoke test query**: default query baked in + optional override

### Claude's Discretion

- Exact ingestion entry point (CLI vs. minimal web form vs. notebook)
- Corpus status view placement and format (article count, chunk count, low-corpus warning)
- Source tag specification UX (flag/prompt/default)
- Batch vs. individual article tag granularity within a batch
- Number of smoke test results returned (N)
- Smoke test command structure (standalone vs. part of status)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CORP-01 | User can add an article to the style corpus by pasting text directly | Text intake → chunk → embed → ChromaDB store pattern; FastAPI endpoint or CLI |
| CORP-02 | User can add articles by uploading a file (PDF, DOCX, TXT) | PyMuPDF (PDF), python-docx (DOCX), plain read (TXT); FastAPI UploadFile or file-path arg |
| CORP-03 | User can populate corpus from a specified Google Drive folder | google-api-python-client v3 with drive.readonly scope; list+download pattern |
| CORP-04 | User can populate corpus by providing a blog URL (agent scrapes posts) | trafilatura 2.0.0 for article extraction; sitemap/feed discovery for bulk posts |
| CORP-05 | User can tag source as "own text" or "external blogger" | ChromaDB metadata field `source_type`; enum enforced at ingestion boundary |
| CORP-06 | User can see number of articles and chunks currently in corpus | `collection.count()` for chunks; separate article-level counter (SQLite or in-memory) |
| CORP-07 | System warns when corpus contains fewer than 10 articles | Post-ingestion check on article count; LOW_CORPUS_THRESHOLD env var |
</phase_requirements>

---

## Summary

Phase 1 is a pure infrastructure phase with no LLM calls and no frontend. The deliverable is a populated ChromaDB vector store that all later phases consume. The work splits cleanly into three concerns: (1) document acquisition from four sources, (2) text chunking and embedding into ChromaDB, and (3) a retrieval smoke test to verify quality before generation work begins.

The standard stack is well-established: **ChromaDB 1.5.1** as the local vector store, **sentence-transformers** with `paraphrase-multilingual-MiniLM-L12-v2` for Polish-aware embeddings, **trafilatura 2.0.0** for blog scraping, **PyMuPDF** for PDF extraction, **python-docx** for DOCX parsing, and **google-api-python-client v3** for Drive access. All libraries are stable and in active maintenance. ChromaDB had a major Rust-core rewrite in 1.x; the Python API surface is largely compatible with 0.5.x for basic add/query operations but the `SentenceTransformerEmbeddingFunction` import path changed.

The single most important architectural decision for this phase is **choosing between CLI scripts and a minimal FastAPI server**. Given that Phase 3 will be a Next.js + FastAPI application, implementing the corpus ingestion as FastAPI endpoints from the start avoids a full rewrite. The CONTEXT.md defers this to Claude's discretion — **recommendation: FastAPI endpoints from day one**, with a thin CLI wrapper around them for developer use. This provides the correct `POST /api/corpus/ingest` surface that Phase 3 will call.

**Primary recommendation:** Implement Phase 1 as three FastAPI endpoints (`/api/corpus/ingest/text`, `/api/corpus/ingest/file`, `/api/corpus/ingest/url`) + one shared ingestion service, with Drive folder ingestion as a fourth endpoint. Use ChromaDB's built-in `SentenceTransformerEmbeddingFunction` for embedding — no custom wrapper needed.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| chromadb | 1.5.1 | Local vector store with persistent storage | Zero-ops, file-based, cosine similarity built in. Standard choice for single-instance RAG |
| sentence-transformers | 3.x | Local embeddings for Polish content | `paraphrase-multilingual-MiniLM-L12-v2` handles Polish without API cost. Used via ChromaDB's built-in EF |
| langchain-text-splitters | latest | Recursive character text splitting | `RecursiveCharacterTextSplitter` preserves paragraph boundaries — correct semantic unit for stylometry |
| trafilatura | 2.0.0 | Blog article extraction from URLs | Best-in-class F1 score (0.958). Handles sitemap/feed discovery for bulk blog scraping |
| PyMuPDF | latest | PDF text extraction | Fastest Python PDF extractor; preserves layout structure; handles complex PDFs |
| python-docx | latest | DOCX text extraction | Standard library for Word document parsing |
| google-api-python-client | 2.x | Google Drive v3 API access | Official Google library for file listing and download |
| google-auth | 2.x | OAuth 2.0 authentication for Drive | Handles token refresh automatically |
| fastapi | 0.115.x | Ingestion API endpoints | Chosen for Phase 3 compatibility; async-native |
| python-multipart | latest | File upload support for FastAPI | Required for `UploadFile` in FastAPI |
| langgraph-checkpoint-sqlite | 3.0.3 | SqliteSaver for LangGraph sessions | Separate package since LangGraph 0.2; needed for Phase 2 graph setup even if Phase 1 is stateless |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | 2.x | Request/response models, enum validation | Source type enum; ingestion request validation |
| python-dotenv | 1.x | Environment variable management | `CHROMA_PATH`, `GOOGLE_CREDENTIALS_PATH`, `LOW_CORPUS_THRESHOLD`, `RAG_TOP_K` |
| uvicorn | 0.30.x | ASGI server for FastAPI | Run the ingestion API locally during development |
| sqlite3 (stdlib) | built-in | Article-level metadata counter | Track article count separately from ChromaDB chunk count for CORP-06/07 |
| requests | latest | HTTP fallback for URL fetching | trafilatura handles its own HTTP; requests for edge cases |
| uv | latest | Python package management | 2025 standard; replaces pip/poetry |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyMuPDF | pypdf (PyPDF2 successor) | PyMuPDF is faster and handles complex layouts better. pypdf is simpler but misses scanned/complex PDFs |
| trafilatura | newspaper4k, BeautifulSoup | trafilatura has highest benchmark F1 (0.958 vs 0.949 for newspaper4k). Trafilatura also has built-in sitemap/feed discovery for bulk blog scraping |
| google-api-python-client | PyDrive2, gdown | Official library; most complete API coverage; maintained by Google |
| ChromaDB PersistentClient | langchain-chroma wrapper | Direct chromadb client gives more control over collection metadata and embedding function; LangChain wrapper is an additional abstraction layer with its own version constraints |
| FastAPI endpoints | CLI scripts / Jupyter notebook | CLI works but makes Phase 3 integration harder. FastAPI from day one is the right call since Phase 3 is FastAPI-based |

**Installation:**
```bash
# Phase 1 core dependencies
uv add chromadb sentence-transformers langchain-text-splitters
uv add trafilatura pymupdf python-docx
uv add "google-api-python-client>=2.0" google-auth google-auth-oauthlib
uv add fastapi uvicorn python-multipart pydantic python-dotenv
uv add langgraph-checkpoint-sqlite  # needed from Phase 1 for project setup

# Dev
uv add --dev pytest pytest-asyncio ruff httpx  # httpx for FastAPI test client
```

---

## Architecture Patterns

### Recommended Project Structure

```
bond/
├── corpus/
│   ├── __init__.py
│   ├── ingestor.py          # CorpusIngestor class (shared logic)
│   ├── chunker.py           # Text splitting + chunk metadata
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── text_source.py   # Plain text paste handler
│   │   ├── file_source.py   # PDF/DOCX/TXT parser dispatcher
│   │   ├── url_source.py    # trafilatura-based blog scraper
│   │   └── drive_source.py  # Google Drive folder downloader
│   └── smoke_test.py        # Retrieval smoke test
├── api/
│   ├── __init__.py
│   ├── main.py              # FastAPI app + router registration
│   └── routes/
│       └── corpus.py        # /api/corpus/* endpoints
├── store/
│   ├── __init__.py
│   └── chroma.py            # ChromaDB client singleton + helpers
├── config.py                # Pydantic Settings (env vars)
└── models.py                # Shared Pydantic models, SourceType enum
```

### Pattern 1: ChromaDB Persistent Client with Custom Embedding Function

**What:** Create a single `PersistentClient` at startup, passed to all ingestion sources.
**When to use:** Always — never create multiple clients to the same path.

```python
# Source: https://cookbook.chromadb.dev/core/collections/
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

def get_chroma_client(path: str) -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=path)

def get_or_create_corpus_collection(client: chromadb.PersistentClient):
    ef = SentenceTransformerEmbeddingFunction(
        model_name="paraphrase-multilingual-MiniLM-L12-v2"
    )
    return client.get_or_create_collection(
        name="bond_style_corpus_v1",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}
    )
```

**Critical:** The embedding function configuration is persisted server-side since Chroma v1.1.13. Once created, subsequent `get_collection` calls do NOT need to pass the embedding function again — but always pass it on the first `get_or_create_collection` call.

### Pattern 2: Source Type Enum for Tagging

**What:** Enforce `source_type` at the model boundary, not at string comparison level.
**When to use:** All ingestion paths.

```python
# Source: Pydantic v2 docs + CONTEXT.md decisions
from enum import Enum
from pydantic import BaseModel

class SourceType(str, Enum):
    OWN_TEXT = "own"
    EXTERNAL_BLOGGER = "external"

class IngestRequest(BaseModel):
    source_type: SourceType
    # Adding new source types later = add enum value + migration
```

### Pattern 3: Chunk Metadata Schema

**What:** Standardized metadata for every chunk in ChromaDB.
**When to use:** All ingestion paths — consistency is critical for retrieval filtering.

```python
# Each chunk added to ChromaDB gets these metadata fields
chunk_metadata = {
    "source_type": "own" | "external",   # SourceType enum value
    "article_id": "uuid4-string",         # Groups chunks from same article
    "article_title": "string",            # For smoke test display
    "source_url": "string | ''",          # URL if from blog/Drive; empty for paste
    "ingested_at": "ISO8601 datetime",    # For TTL/cleanup later
}
```

### Pattern 4: Article Count Tracking

**What:** SQLite article log alongside ChromaDB for CORP-06/07.
**When to use:** ChromaDB `collection.count()` returns chunk count, not article count. Need separate tracker.

```python
# store/article_log.py
import sqlite3

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS corpus_articles (
    article_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    title TEXT,
    source_url TEXT,
    chunk_count INTEGER,
    ingested_at TEXT
)
"""

def get_article_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM corpus_articles").fetchone()[0]

def warn_if_low(article_count: int, threshold: int = 10) -> str | None:
    if article_count < threshold:
        return f"WARNING: Corpus contains only {article_count} articles. Recommend at least {threshold} for reliable style retrieval."
    return None
```

### Pattern 5: Blog URL Scraping with trafilatura

**What:** Scrape all posts from a blog URL using sitemap discovery, then extract each article.
**When to use:** CORP-04.

```python
# Source: trafilatura 2.0.0 docs — https://trafilatura.readthedocs.io/
import trafilatura
from trafilatura.sitemaps import sitemap_search

def scrape_blog(url: str) -> list[dict]:
    """Returns list of {url, title, text} dicts; skips failures."""
    articles = []
    # Discover all post URLs via sitemap/feed
    urls = sitemap_search(url)
    if not urls:
        # Fallback: treat the single URL as one article
        urls = [url]

    for post_url in urls:
        try:
            downloaded = trafilatura.fetch_url(post_url)
            if downloaded is None:
                print(f"WARN: Could not fetch {post_url} — skipping")
                continue
            text = trafilatura.extract(downloaded, include_metadata=True, output_format="json")
            if text is None:
                print(f"WARN: No article content found at {post_url} — skipping")
                continue
            import json
            data = json.loads(text)
            articles.append({
                "url": post_url,
                "title": data.get("title", ""),
                "text": data.get("text", ""),
            })
        except Exception as e:
            print(f"WARN: {post_url} failed: {e} — skipping")
    return articles
```

### Pattern 6: Google Drive Folder Download

**What:** List all files in a folder, download supported types (PDF, DOCX, TXT).
**When to use:** CORP-03.

```python
# Source: Google Drive API v3 official docs
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
import io

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SUPPORTED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    # Google Docs export as plain text
    "application/vnd.google-apps.document": ".txt",
}

def build_drive_service(credentials_path: str):
    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)

def list_folder_files(service, folder_id: str) -> list[dict]:
    """List supported files in a Google Drive folder."""
    query = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(
        q=query,
        fields="files(id, name, mimeType)",
        pageSize=100
    ).execute()
    return [
        f for f in results.get("files", [])
        if f["mimeType"] in SUPPORTED_MIME_TYPES
    ]

def download_file(service, file_id: str, mime_type: str) -> bytes:
    """Download file content as bytes. Exports Google Docs as plain text."""
    if mime_type == "application/vnd.google-apps.document":
        request = service.files().export_media(fileId=file_id, mimeType="text/plain")
    else:
        request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()
```

### Pattern 7: PDF and DOCX Parsing

**What:** Extract text from uploaded/downloaded binary files.
**When to use:** CORP-02, and as part of CORP-03 after Drive download.

```python
# Source: PyMuPDF docs, python-docx docs
import pymupdf  # import name changed from "fitz" in new versions; "fitz" is fallback
from docx import Document
import io

def extract_text_from_pdf(content: bytes) -> str | None:
    try:
        doc = pymupdf.open(stream=content, filetype="pdf")
        return "\n\n".join(page.get_text() for page in doc)
    except Exception as e:
        print(f"WARN: PDF parse failed: {e} — skipping")
        return None

def extract_text_from_docx(content: bytes) -> str | None:
    try:
        doc = Document(io.BytesIO(content))
        return "\n\n".join(para.text for para in doc.paragraphs if para.text.strip())
    except Exception as e:
        print(f"WARN: DOCX parse failed: {e} — skipping")
        return None

def extract_text(content: bytes, filename: str) -> str | None:
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        return extract_text_from_pdf(content)
    elif ext == "docx":
        return extract_text_from_docx(content)
    elif ext == "txt":
        try:
            return content.decode("utf-8", errors="replace")
        except Exception as e:
            print(f"WARN: TXT decode failed: {e} — skipping")
            return None
    else:
        print(f"WARN: Unsupported file type .{ext} — skipping")
        return None
```

### Pattern 8: Text Chunking with Paragraph-Boundary Splitting

**What:** Split article text into 300–500 token chunks, preserving paragraph boundaries.
**When to use:** All ingestion paths, before embedding.

```python
# Source: LangChain text splitters docs
from langchain_text_splitters import RecursiveCharacterTextSplitter

# For style corpus: 400-token chunks with 10% overlap
# Paragraph boundary respected by RecursiveCharacterTextSplitter default separators
splitter = RecursiveCharacterTextSplitter(
    chunk_size=1500,  # ~400 tokens at ~3.75 chars/token average for Polish
    chunk_overlap=150,
    separators=["\n\n", "\n", " ", ""],
)

def chunk_article(text: str) -> list[str]:
    return splitter.split_text(text)
```

**Note on chunk_size:** LangChain's `RecursiveCharacterTextSplitter` measures in characters by default, not tokens. For Polish text (~3.75 chars/token avg), 1500 chars ≈ 400 tokens. To measure in actual tokens, pass `length_function=len` using a tokenizer — acceptable to skip for MVP.

### Pattern 9: Retrieval Smoke Test

**What:** Query ChromaDB with a test phrase and display top-N results with similarity scores.
**When to use:** After corpus loading, as standalone CLI command or status endpoint.

```python
# Recommendation: standalone CLI command + /api/corpus/smoke-test endpoint
def run_smoke_test(
    collection,
    query: str = "styl pisania storytelling angażujące treści",
    n_results: int = 5,
) -> list[dict]:
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
    output = []
    for i, (doc, meta, dist) in enumerate(zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    )):
        output.append({
            "rank": i + 1,
            "score": round(1 - dist, 4),  # cosine distance → similarity
            "source_type": meta.get("source_type"),
            "title": meta.get("article_title", "unknown"),
            "fragment": doc[:200] + "...",
        })
    return output
```

### Anti-Patterns to Avoid

- **Multiple ChromaDB clients to same path:** Creates file lock conflicts. Use a single `PersistentClient` singleton.
- **Embedding the full article text as one document:** Cosine similarity degrades on long texts. Always chunk first.
- **Storing only chunk count in ChromaDB:** `collection.count()` returns chunks, not articles. CORP-06/07 require article count — track separately.
- **Hardcoded source_type strings:** Use the `SourceType` enum at boundaries. "own"/"external" must be consistent across ingest and retrieval weighting.
- **Importing `fitz` without fallback:** PyMuPDF changed its import name to `pymupdf` in recent versions; `fitz` remains as backward-compatible alias but check which is installed.
- **Fetching all Drive files without pagination:** `files().list()` returns max 100 results by default. Use `pageToken` for folders with more files.
- **Passing the embedding function on every `get_collection` call:** Since Chroma 1.1.13, it's persisted server-side. Pass only on `get_or_create_collection`; safe to omit on subsequent `get_collection` calls.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Article content extraction from HTML | Custom BeautifulSoup parser | trafilatura 2.0.0 | Handles boilerplate removal, byline/nav filtering. Custom parsers break on every site's unique layout. F1 0.958 vs your parser's unknown. |
| Polish-language text embeddings | Custom embedding model | `paraphrase-multilingual-MiniLM-L12-v2` via `SentenceTransformerEmbeddingFunction` | 50+ language model including Polish. Trained on paraphrase tasks (right objective for style matching). |
| PDF parsing | PDF spec parsing from scratch | PyMuPDF | PDF is one of the most complex binary formats. PyMuPDF wraps MuPDF (C library with 20 years of edge case handling). |
| DOCX parsing | XML walking | python-docx | DOCX is a ZIP of XML files. python-docx handles paragraph/style model correctly. |
| Google Drive auth | Raw OAuth2 flow | google-auth + google-api-python-client | Token refresh, service account credential loading, scope management — all handled. |
| Vector similarity search | cosine similarity over numpy arrays | ChromaDB | ChromaDB uses HNSW index for approximate nearest neighbor — much faster than brute-force cosine on >1000 vectors. |
| Text chunking | Split on `\n\n` | `RecursiveCharacterTextSplitter` | Handles edge cases: paragraphs with single newlines, code blocks, very long sentences. Falls back through separator hierarchy gracefully. |

**Key insight:** Every item in this list represents a deceptively complex problem. The first 100 articles will work with a naive implementation. The next 100 will expose edge cases that each library has already solved.

---

## Common Pitfalls

### Pitfall 1: ChromaDB 0.x → 1.x Schema Incompatibility

**What goes wrong:** Existing ChromaDB 0.x databases cannot be read by ChromaDB 1.x. If you start with 0.5.x and later upgrade, all stored vectors are lost.
**Why it happens:** 1.x uses a Rust-core storage backend with a different schema language.
**How to avoid:** Start with ChromaDB 1.5.1 from day one. Do not pin to 0.x.
**Warning signs:** `ValueError: Could not open database` or migration errors on startup after upgrade.

### Pitfall 2: PyMuPDF Import Name Change

**What goes wrong:** `import fitz` raises ImportError on newer PyMuPDF installs.
**Why it happens:** PyMuPDF changed its canonical import from `fitz` to `pymupdf`. `fitz` is maintained as backward-compatible alias but not guaranteed long-term.
**How to avoid:** `import pymupdf` in all new code. Use `try: import pymupdf as fitz; except: import fitz` if supporting both.
**Warning signs:** `ModuleNotFoundError: No module named 'fitz'`

### Pitfall 3: trafilatura Returns None for Non-Article Pages

**What goes wrong:** Scraper returns no content for blog index/category pages, about pages, etc.
**Why it happens:** trafilatura correctly identifies these as non-article pages and returns `None`.
**How to avoid:** This is correct behavior, not a bug. Use `sitemap_search()` to discover actual post URLs; skip pages where trafilatura returns None. Do NOT add a fallback full-text grab — noise pollutes the style corpus.
**Warning signs:** Corpus article count is 0 or very low despite scraping a blog URL.

### Pitfall 4: Google Drive Folder Not Shared with Service Account

**What goes wrong:** Drive API returns empty file list for a folder that visibly contains files.
**Why it happens:** The service account is a separate Google identity. The folder must be shared with the service account's email address, or domain-wide delegation must be configured.
**How to avoid:** Document the sharing requirement clearly in the ingestion UI. Show the service account email address in the error/warning message when the folder returns 0 files.
**Warning signs:** `files().list()` returns 0 items for a known non-empty folder.

### Pitfall 5: Embedding Model Not Downloaded on First Run

**What goes wrong:** First `get_or_create_collection` call blocks for 30-120 seconds downloading the model, or fails with a network error.
**Why it happens:** `paraphrase-multilingual-MiniLM-L12-v2` (~420MB) is downloaded from HuggingFace Hub on first use.
**How to avoid:** Add an explicit startup step that pre-downloads the model. Set `TRANSFORMERS_CACHE` env var to a known path. Document in README.
**Warning signs:** Long startup hang on first run; HuggingFace download progress bar in logs.

### Pitfall 6: Corpus Article Count vs. Chunk Count Confusion

**What goes wrong:** `collection.count()` returns chunk count (could be 50 for 5 articles). The CORP-06 "10 articles" warning fires at wrong threshold.
**Why it happens:** ChromaDB's `collection.count()` is chunk-aware, not article-aware.
**How to avoid:** Maintain a separate article log (SQLite `corpus_articles` table). Track `article_id` in chunk metadata. Use article table count for CORP-07 threshold check.
**Warning signs:** CORP-07 warning never fires despite small corpus; or fires with 200 chunks (many from few articles).

### Pitfall 7: LangGraph SqliteSaver Wrong Import

**What goes wrong:** `from langgraph.checkpoint.sqlite import SqliteSaver` raises ImportError.
**Why it happens:** Since LangGraph 0.2, SQLite checkpointer is a separate installable: `langgraph-checkpoint-sqlite`.
**How to avoid:** Install `langgraph-checkpoint-sqlite` package. Import as `from langgraph.checkpoint.sqlite import SqliteSaver` (same path, separate package).
**Warning signs:** ImportError on application startup.

### Pitfall 8: Source Type Weighting Not Implemented at Retrieval Time

**What goes wrong:** Retrieval returns 5 external blogger chunks even when own text is available — contradicts CONTEXT.md decision.
**Why it happens:** ChromaDB returns results purely by cosine similarity. Source type weighting requires post-retrieval reranking or filtered queries.
**How to avoid:** Implement a two-pass retrieval: (1) query with `where={"source_type": "own"}`, n_results=3; (2) if fewer than 3 results, fill remainder from `where={"source_type": "external"}`. This is the correct pattern for "prefer own text."
**Warning signs:** Smoke test results show only external blogger fragments even when own text is in corpus.

---

## Code Examples

Verified patterns from official sources:

### ChromaDB Persistent Client Setup

```python
# Source: https://cookbook.chromadb.dev/core/collections/
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

client = chromadb.PersistentClient(path="./data/chroma")

ef = SentenceTransformerEmbeddingFunction(
    model_name="paraphrase-multilingual-MiniLM-L12-v2",
    device="cpu",
)

collection = client.get_or_create_collection(
    name="bond_style_corpus_v1",
    embedding_function=ef,
    metadata={"hnsw:space": "cosine"},
)
```

### Adding Documents with Metadata

```python
# Source: https://cookbook.chromadb.dev/core/collections/
import uuid

def add_article_chunks(collection, chunks: list[str], article_meta: dict):
    article_id = str(uuid.uuid4())
    ids = [f"{article_id}_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "source_type": article_meta["source_type"],  # "own" | "external"
            "article_id": article_id,
            "article_title": article_meta.get("title", ""),
            "source_url": article_meta.get("url", ""),
            "ingested_at": article_meta["ingested_at"],
        }
        for _ in chunks
    ]
    collection.add(documents=chunks, metadatas=metadatas, ids=ids)
    return article_id
```

### Querying with Source Type Filter

```python
# Source: ChromaDB query docs + CONTEXT.md weighting requirement
def retrieve_style_fragments(collection, query: str, n_results: int = 5) -> list[dict]:
    """Two-pass retrieval: prefer own text, fill from external."""
    # Pass 1: own text
    own = collection.query(
        query_texts=[query],
        n_results=n_results,
        where={"source_type": "own"},
        include=["documents", "metadatas", "distances"],
    )
    own_docs = own["documents"][0] if own["documents"] else []
    own_metas = own["metadatas"][0] if own["metadatas"] else []

    if len(own_docs) >= n_results:
        return _zip_results(own_docs, own_metas)

    # Pass 2: fill remainder from external
    fill_count = n_results - len(own_docs)
    ext = collection.query(
        query_texts=[query],
        n_results=fill_count,
        where={"source_type": "external"},
        include=["documents", "metadatas", "distances"],
    )
    ext_docs = ext["documents"][0] if ext["documents"] else []
    ext_metas = ext["metadatas"][0] if ext["metadatas"] else []

    return _zip_results(own_docs + ext_docs, own_metas + ext_metas)

def _zip_results(docs, metas):
    return [{"text": d, "meta": m} for d, m in zip(docs, metas)]
```

### FastAPI File Upload Endpoint

```python
# Source: FastAPI official docs — https://fastapi.tiangolo.com/reference/uploadfile/
from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel

app = FastAPI()

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

@app.post("/api/corpus/ingest/file")
async def ingest_file(
    file: UploadFile = File(...),
    source_type: str = Form(...),  # "own" | "external"
):
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return {"error": f"Unsupported file type: .{ext}"}

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        return {"error": "File too large (max 20MB)"}

    text = extract_text(content, file.filename)
    if text is None:
        return {"warning": f"Could not parse {file.filename} — skipped"}

    # ... chunk + ingest + return stats
```

### LangGraph SqliteSaver (correct import for 0.2+)

```python
# Source: https://pypi.org/project/langgraph-checkpoint-sqlite/
# Install: uv add langgraph-checkpoint-sqlite
from langgraph.checkpoint.sqlite import SqliteSaver

checkpointer = SqliteSaver.from_conn_string("./data/bond_sessions.db")
# For async: from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `chromadb` 0.x Python-only backend | `chromadb` 1.x Rust core | Mid-2025 (v1.0) | 4x write/query performance; breaking schema incompatibility with 0.x databases |
| `from langgraph.checkpoint.sqlite import SqliteSaver` (bundled) | `pip install langgraph-checkpoint-sqlite` (separate package) | LangGraph 0.2 | Must install additional package; same import path |
| `import fitz` for PyMuPDF | `import pymupdf` (canonical); `fitz` is alias | PyMuPDF recent | Use `pymupdf` in new code; `fitz` still works but deprecated |
| `newspaper3k` for blog scraping | `trafilatura 2.0.0` or `newspaper4k` | 2024-2025 | trafilatura leads benchmarks; newspaper3k unmaintained, newspaper4k is fork |
| ChromaDB embedding function passed on every `get_collection` | Persisted server-side since v1.1.13 | v1.1.13 | No need to pass EF on repeated collection access |

**Deprecated/outdated:**
- `newspaper3k`: unmaintained; use `trafilatura` or `newspaper4k` (active fork)
- `PyPDF2`: superseded by `pypdf` (same maintainer, new name); `pypdf` is current
- `MemorySaver` for LangGraph: not deprecated but wrong for production; always use `SqliteSaver`
- `langchain.vectorstores.Chroma`: use `langchain_chroma` package instead (separate since LangChain 0.3)

---

## Open Questions

1. **Google Drive auth method for developer-only phase**
   - What we know: Service account is cleanest for automated access; OAuth installed-app flow requires browser consent once
   - What's unclear: Whether the developer will use their own Google account (OAuth flow) or a service account (requires GCP project + JSON key file)
   - Recommendation: Support both; default to OAuth installed-app flow (simpler setup) with env var `GOOGLE_AUTH_METHOD=oauth|service_account`

2. **Chunk size tuning for Polish stylometry**
   - What we know: General RAG recommendation is 400-512 tokens with 10-20% overlap; Polish avg ~3.75 chars/token
   - What's unclear: Whether 400-token chunks preserve enough stylistic context; Polish sentences are longer on average than English
   - Recommendation: Start at 500-token target (1875 chars). Add a tuning TODO comment; this is validated during smoke test step

3. **Blog URL scraping scope: single article vs. entire blog**
   - What we know: CONTEXT.md says "blog URL" and CORP-04 says "agent scrapes posts" — implies bulk scraping
   - What's unclear: How to handle blogs with hundreds of posts (scraping all takes minutes); should there be a max posts limit?
   - Recommendation: Implement `MAX_BLOG_POSTS` env var defaulting to 50. Log how many were found vs. scraped.

4. **Drive folder access model: shared link vs. service account**
   - What we know: Service account requires folder to be explicitly shared with SA email
   - What's unclear: Whether the user understands this requirement; error messages must be very clear
   - Recommendation: Include service account email in the warning message when folder returns 0 files; add setup instructions as a comment in config.

---

## Sources

### Primary (HIGH confidence)
- [ChromaDB Cookbook — Collections](https://cookbook.chromadb.dev/core/collections/) — PersistentClient API, `get_or_create_collection`, add/query patterns
- [ChromaDB Migration Docs](https://docs.trychroma.com/docs/overview/migration) — 0.x → 1.x breaking changes
- [ChromaDB PyPI](https://pypi.org/project/chromadb/) — confirmed version 1.5.1 (as of 2026-02-20)
- [langgraph-checkpoint-sqlite PyPI](https://pypi.org/project/langgraph-checkpoint-sqlite/) — confirmed version 3.0.3; separate package requirement
- [trafilatura PyPI + docs](https://trafilatura.readthedocs.io/) — version 2.0.0; sitemap_search API
- [Google Drive API Python Quickstart](https://developers.google.com/drive/api/quickstart/python) — OAuth scopes, auth patterns
- [FastAPI UploadFile reference](https://fastapi.tiangolo.com/reference/uploadfile/) — file upload endpoint pattern

### Secondary (MEDIUM confidence)
- [WebSearch: ChromaDB SentenceTransformerEmbeddingFunction](https://docs.trychroma.com/docs/embeddings/embedding-functions) — `model_name` parameter confirmed; `device` and `normalize_embeddings` parameters confirmed
- [WebSearch: LangGraph SqliteSaver import path](https://github.com/langchain-ai/langgraph/issues/1274) — import error confirmed; separate package solution confirmed
- [WebSearch: trafilatura vs newspaper3k benchmark](https://github.com/scrapinghub/article-extraction-benchmark) — F1 0.958 for trafilatura; 0.949 for newspaper4k
- [WebSearch: PyMuPDF import name change](https://pymupdf.readthedocs.io/) — `pymupdf` canonical; `fitz` as backward alias
- [LangChain RecursiveCharacterTextSplitter](https://python.langchain.com/docs/integrations/vectorstores/chroma/) — chunking pattern; separator hierarchy

### Tertiary (LOW confidence)
- WebSearch: Polish characters/token ratio (~3.75) — not officially benchmarked; estimate from general multilingual NLP knowledge
- WebSearch: `MAX_BLOG_POSTS` as UX pattern — convention, not library constraint

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified against PyPI as of 2026-02-20
- Architecture patterns: HIGH — based on official ChromaDB Cookbook, FastAPI docs, Google Drive API docs
- Pitfalls: HIGH — ChromaDB 0.x→1.x and LangGraph SqliteSaver issues verified via GitHub issues + official migration docs; others MEDIUM from documented behavior
- Retrieval weighting pattern: MEDIUM — two-pass query is a known pattern; not officially documented as "the" approach for source preference

**Research date:** 2026-02-20
**Valid until:** 2026-03-22 (stable libraries; ChromaDB releases weekly — re-verify version before pinning)
