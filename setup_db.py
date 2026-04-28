#!/usr/bin/env python3
"""
setup_db.py — Bond Dev Setup
Automatyzuje inicjalizację baz danych i ChromaDB.

Uruchomienie:
    uv run python setup_db.py
    uv run python setup_db.py --reset   # usuwa i tworzy od nowa

Co robi:
    1. Tworzy katalog data/
    2. Inicjalizuje articles.db (corpus_articles)
    3. Inicjalizuje bond_metadata.db (metadata_log)
    4. Inicjalizuje bond_checkpoints.db (LangGraph SqliteSaver)
    5. Inicjalizuje ChromaDB z kolekcjami bond_style_corpus_v1 i bond_metadata_log_v1
"""

import argparse
import shutil
import sqlite3
import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(msg: str) -> None:
    print(f"  \033[32m✓\033[0m  {msg}")


def _skip(msg: str) -> None:
    print(f"  \033[33m–\033[0m  {msg}")


def _fail(msg: str) -> None:
    print(f"  \033[31m✗\033[0m  {msg}", file=sys.stderr)


def _header(msg: str) -> None:
    print(f"\n\033[1m{msg}\033[0m")


# ---------------------------------------------------------------------------
# SQLite initializers
# ---------------------------------------------------------------------------

ARTICLES_DDL = """
CREATE TABLE IF NOT EXISTS corpus_articles (
    article_id  TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    title       TEXT,
    source_url  TEXT DEFAULT '',
    chunk_count INTEGER DEFAULT 0,
    ingested_at TEXT
);
"""

METADATA_DDL = """
CREATE TABLE IF NOT EXISTS metadata_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id      TEXT NOT NULL,
    topic          TEXT NOT NULL,
    published_date TEXT NOT NULL,
    mode           TEXT NOT NULL DEFAULT 'author',
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metadata_log_published_date
    ON metadata_log (published_date);

-- AUTH-11: Exa search result cache, scoped per (query_hash, thread_id) session
CREATE TABLE IF NOT EXISTS search_cache (
    query_hash   TEXT NOT NULL,
    thread_id    TEXT NOT NULL,
    results_json TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    PRIMARY KEY (query_hash, thread_id)
);
"""

CHECKPOINTS_DDL = """
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id    TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type         TEXT,
    checkpoint   BLOB,
    metadata     BLOB,
    PRIMARY KEY (thread_id, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id    TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL,
    channel      TEXT NOT NULL,
    version      TEXT NOT NULL,
    type         TEXT NOT NULL,
    blob         BLOB,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id    TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    idx          INTEGER NOT NULL,
    channel      TEXT NOT NULL,
    type         TEXT,
    blob         BLOB,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

CREATE TABLE IF NOT EXISTS checkpoint_migrations (
    v INTEGER PRIMARY KEY
);
"""


def _init_sqlite(path: str, ddl: str, name: str, reset: bool) -> None:
    abs_path = Path(path).resolve()

    if reset and abs_path.exists():
        abs_path.unlink()
        _ok(f"{name}: usunięto stary plik")

    if abs_path.exists():
        _skip(f"{name}: już istnieje ({abs_path})")
    else:
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(abs_path))
        conn.executescript(ddl)
        conn.commit()
        conn.close()
        _ok(f"{name}: zainicjalizowano ({abs_path})")


# ---------------------------------------------------------------------------
# ChromaDB initializer
# ---------------------------------------------------------------------------

def _init_chroma(chroma_path: str, reset: bool) -> None:
    _header("ChromaDB")

    try:
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    except ImportError:
        _fail("chromadb nie jest zainstalowane. Uruchom: uv sync")
        sys.exit(1)

    abs_path = Path(chroma_path).resolve()

    if reset and abs_path.exists():
        shutil.rmtree(abs_path)
        _ok(f"Usunięto katalog ChromaDB: {abs_path}")

    abs_path.mkdir(parents=True, exist_ok=True)

    print("  Ładowanie modelu paraphrase-multilingual-MiniLM-L12-v2...")
    t0 = time.time()
    ef = SentenceTransformerEmbeddingFunction(
        model_name="paraphrase-multilingual-MiniLM-L12-v2",
        device="cpu",
    )
    elapsed = time.time() - t0
    _ok(f"Model załadowany ({elapsed:.1f}s)")

    client = chromadb.PersistentClient(path=str(abs_path))

    corpus = client.get_or_create_collection(
        name="bond_style_corpus_v1",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    _ok(f"Kolekcja bond_style_corpus_v1 gotowa (dokumenty: {corpus.count()})")

    metadata_col = client.get_or_create_collection(
        name="bond_metadata_log_v1",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    _ok(f"Kolekcja bond_metadata_log_v1 gotowa (dokumenty: {metadata_col.count()})")


# ---------------------------------------------------------------------------
# .env verification
# ---------------------------------------------------------------------------

def _check_env() -> None:
    _header("Weryfikacja .env")
    env_path = Path(".env")

    if not env_path.exists():
        example = Path(".env.example")
        if example.exists():
            shutil.copy(example, env_path)
            _ok(".env nie istniał — skopiowano z .env.example")
        else:
            _fail(".env i .env.example nie istnieją. Utwórz plik .env ręcznie.")
            sys.exit(1)
    else:
        _ok(".env istnieje")

    # Check required keys
    content = env_path.read_text()
    required = ["OPENAI_API_KEY"]
    for key in required:
        val = ""
        for line in content.splitlines():
            if line.startswith(f"{key}="):
                val = line.split("=", 1)[1].strip()
        if not val or val.startswith("sk-proj-...") or val == "your-key-here":
            print(f"  \033[33m⚠\033[0m  {key} nie jest ustawiony — ustaw go w .env przed uruchomieniem agenta")
        else:
            _ok(f"{key} ustawiony")


# ---------------------------------------------------------------------------
# Config loading (with fallback — no pydantic required)
# ---------------------------------------------------------------------------

def _load_paths() -> dict:
    defaults = {
        "chroma_path": "./data/chroma",
        "article_db_path": "./data/articles.db",
        "checkpoint_db_path": "./data/bond_checkpoints.db",
        "metadata_db_path": "./data/bond_metadata.db",
    }

    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().lower()
            v = v.strip().strip('"').strip("'")
            if k in defaults and v:
                defaults[k] = v

    return defaults


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bond DB setup — inicjalizacja SQLite i ChromaDB"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Usuń istniejące bazy danych i utwórz od nowa (NISZCZY DANE!)",
    )
    args = parser.parse_args()

    if args.reset:
        print("\n\033[31mUWAGA: tryb --reset — wszystkie dane zostaną usunięte!\033[0m")
        confirm = input("Wpisz 'tak' aby kontynuować: ").strip().lower()
        if confirm != "tak":
            print("Anulowano.")
            sys.exit(0)

    paths = _load_paths()

    _check_env()

    _header("SQLite — articles.db")
    _init_sqlite(paths["article_db_path"], ARTICLES_DDL, "articles.db", args.reset)

    _header("SQLite — bond_metadata.db")
    _init_sqlite(paths["metadata_db_path"], METADATA_DDL, "bond_metadata.db", args.reset)

    _header("SQLite — bond_checkpoints.db")
    _init_sqlite(paths["checkpoint_db_path"], CHECKPOINTS_DDL, "bond_checkpoints.db", args.reset)

    _init_chroma(paths["chroma_path"], args.reset)

    print("\n\033[32m✓ Setup zakończony pomyślnie.\033[0m")
    print("\nNastępne kroki:")
    print("  1. Uzupełnij OPENAI_API_KEY w .env")
    print("  2. uv run uvicorn bond.api.main:app --reload")
    print("  3. cd frontend && npm run dev")
    print()


if __name__ == "__main__":
    main()
