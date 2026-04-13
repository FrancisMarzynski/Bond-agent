import os
from datetime import datetime, timezone

import aiosqlite

from bond.config import settings


_TOKEN_COLUMNS: list[tuple[str, str]] = [
    ("tokens_used_research", "INTEGER NOT NULL DEFAULT 0"),
    ("tokens_used_draft",    "INTEGER NOT NULL DEFAULT 0"),
    ("estimated_cost_usd",   "REAL    NOT NULL DEFAULT 0.0"),
]


async def _ensure_schema(conn: aiosqlite.Connection) -> None:
    """Inicjalizuje schemat bazy danych (idempotentnie).

    Uruchamia DDL z schema.sql, a następnie próbuje dodać kolumny tokenów
    do istniejących tabel (migracja dla baz sprzed wersji z #15).
    SQLite nie obsługuje ADD COLUMN IF NOT EXISTS — błąd duplikatu kolumny
    jest ignorowany, co czyni operację idempotentną.
    """
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path) as f:
        ddl = f.read()
    await conn.executescript(ddl)

    for col_name, col_def in _TOKEN_COLUMNS:
        try:
            await conn.execute(
                f"ALTER TABLE metadata_log ADD COLUMN {col_name} {col_def}"
            )
        except Exception:
            pass  # column already exists — safe to ignore

    await conn.commit()


async def save_article_metadata(
    thread_id: str,
    topic: str,
    mode: str = "author",
    tokens_used_research: int = 0,
    tokens_used_draft: int = 0,
    estimated_cost_usd: float = 0.0,
) -> int:
    """Wstawia rekord metadanych artykułu. Zwraca id nowego wiersza."""
    os.makedirs(os.path.dirname(os.path.abspath(settings.metadata_db_path)), exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(settings.metadata_db_path) as conn:
        await _ensure_schema(conn)
        cursor = await conn.execute(
            "INSERT INTO metadata_log "
            "(thread_id, topic, published_date, mode, created_at, "
            "tokens_used_research, tokens_used_draft, estimated_cost_usd) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (thread_id, topic, now, mode, now,
             tokens_used_research, tokens_used_draft, estimated_cost_usd),
        )
        await conn.commit()
        return cursor.lastrowid


async def get_recent_articles(limit: int = 50) -> list[dict]:
    """Zwraca ostatnie wpisy z metadata_log jako listę słowników."""
    os.makedirs(os.path.dirname(os.path.abspath(settings.metadata_db_path)), exist_ok=True)
    async with aiosqlite.connect(settings.metadata_db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await _ensure_schema(conn)
        cursor = await conn.execute(
            "SELECT * FROM metadata_log ORDER BY published_date DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
