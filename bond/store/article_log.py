import os
import sqlite3
from datetime import datetime, timezone
from bond.config import settings

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS corpus_articles (
    article_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    title TEXT,
    source_url TEXT DEFAULT '',
    chunk_count INTEGER DEFAULT 0,
    ingested_at TEXT
)
"""

def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(settings.article_db_path)), exist_ok=True)
    conn = sqlite3.connect(settings.article_db_path)
    conn.execute(CREATE_TABLE)
    conn.commit()
    return conn

def log_article(article_id: str, source_type: str, title: str, source_url: str, chunk_count: int) -> None:
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO corpus_articles (article_id, source_type, title, source_url, chunk_count, ingested_at) VALUES (?, ?, ?, ?, ?, ?)",
        (article_id, source_type, title, source_url, chunk_count, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()

def get_article_count() -> int:
    conn = _get_conn()
    count = conn.execute("SELECT COUNT(*) FROM corpus_articles").fetchone()[0]
    conn.close()
    return count

def get_chunk_count() -> int:
    conn = _get_conn()
    count = conn.execute("SELECT SUM(chunk_count) FROM corpus_articles").fetchone()[0] or 0
    conn.close()
    return count


def get_articles() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT article_id, title, source_type, source_url, chunk_count, ingested_at "
        "FROM corpus_articles ORDER BY ingested_at DESC"
    ).fetchall()
    conn.close()
    return [
        {
            "article_id": row[0],
            "title": row[1] or row[0],
            "source_type": row[2],
            "source_url": row[3] or "",
            "chunk_count": row[4] or 0,
            "ingested_at": row[5],
        }
        for row in rows
    ]
