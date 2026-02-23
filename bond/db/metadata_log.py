import os
import sqlite3
from datetime import datetime, timezone
from bond.config import settings


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(settings.metadata_db_path)), exist_ok=True)
    conn = sqlite3.connect(settings.metadata_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Create tables on first connection
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path) as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


def save_article_metadata(thread_id: str, topic: str, mode: str = "author") -> int:
    """Insert a metadata record. Returns the new row id."""
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO metadata_log (thread_id, topic, published_date, mode, created_at) VALUES (?, ?, ?, ?, ?)",
        (thread_id, topic, now, mode, now),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def get_recent_articles(limit: int = 50) -> list[dict]:
    """Return most recent metadata_log entries as dicts."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM metadata_log ORDER BY published_date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
