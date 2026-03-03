import os
from datetime import datetime, timezone

import aiosqlite

from bond.config import settings


async def _ensure_schema(conn: aiosqlite.Connection) -> None:
    """Inicjalizuje schemat bazy danych (idempotentnie)."""
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path) as f:
        ddl = f.read()
    await conn.executescript(ddl)
    await conn.commit()


async def save_article_metadata(thread_id: str, topic: str, mode: str = "author") -> int:
    """Wstawia rekord metadanych artykułu. Zwraca id nowego wiersza."""
    os.makedirs(os.path.dirname(os.path.abspath(settings.metadata_db_path)), exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(settings.metadata_db_path) as conn:
        await _ensure_schema(conn)
        cursor = await conn.execute(
            "INSERT INTO metadata_log (thread_id, topic, published_date, mode, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (thread_id, topic, now, mode, now),
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
