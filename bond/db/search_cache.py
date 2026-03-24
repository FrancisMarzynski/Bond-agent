"""
bond/db/search_cache.py — SQLite-backed Exa search result cache (AUTH-11).

Cache entries are keyed by (query_hash, thread_id) so they are strictly
scoped to a single pipeline session.  The query hash is a SHA-256 digest
of the canonical "topic + sorted keywords" string, making it stable across
minor keyword reorderings.

The table lives in bond_metadata.db alongside metadata_log.  Schema is
created lazily via _ensure_cache_table(), so no manual migration is needed
when deploying alongside an existing bond_metadata.db.
"""

import hashlib
import os
from datetime import datetime, timezone

import aiosqlite

from bond.config import settings

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS search_cache (
    query_hash   TEXT NOT NULL,
    thread_id    TEXT NOT NULL,
    results_json TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    PRIMARY KEY (query_hash, thread_id)
);
"""


def compute_query_hash(topic: str, keywords: list[str]) -> str:
    """Return a stable SHA-256 hex digest for (topic, keywords)."""
    canonical = f"{topic}:{':'.join(sorted(keywords))}"
    return hashlib.sha256(canonical.encode()).hexdigest()


async def _ensure_cache_table(conn: aiosqlite.Connection) -> None:
    await conn.executescript(_CREATE_TABLE_SQL)
    await conn.commit()


async def get_cached_result(query_hash: str, thread_id: str) -> str | None:
    """
    Return cached raw results string for (query_hash, thread_id), or None on
    cache miss.
    """
    os.makedirs(
        os.path.dirname(os.path.abspath(settings.metadata_db_path)), exist_ok=True
    )
    async with aiosqlite.connect(settings.metadata_db_path) as conn:
        await _ensure_cache_table(conn)
        cursor = await conn.execute(
            "SELECT results_json FROM search_cache "
            "WHERE query_hash = ? AND thread_id = ?",
            (query_hash, thread_id),
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def save_cached_result(
    query_hash: str, thread_id: str, results_json: str
) -> None:
    """Insert or replace a cache entry for (query_hash, thread_id)."""
    os.makedirs(
        os.path.dirname(os.path.abspath(settings.metadata_db_path)), exist_ok=True
    )
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(settings.metadata_db_path) as conn:
        await _ensure_cache_table(conn)
        await conn.execute(
            "INSERT OR REPLACE INTO search_cache "
            "(query_hash, thread_id, results_json, timestamp) VALUES (?, ?, ?, ?)",
            (query_hash, thread_id, results_json, now),
        )
        await conn.commit()
