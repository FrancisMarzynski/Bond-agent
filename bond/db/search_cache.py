"""
bond/db/search_cache.py — SQLite-backed Exa search result cache.

Cache entries are keyed by query_hash only (SHA-256 of topic + keywords),
making results shareable across all sessions.  A TTL of _TTL_DAYS (7 days)
ensures stale web data is refreshed automatically.

thread_id is stored as a non-key column for audit/logging purposes.

Migration: if the table was created with the old composite PK
(query_hash, thread_id), it is dropped and recreated automatically on first
use — old cached results are discarded (they are regeneratable).
"""

import asyncio
import hashlib
import logging
import os
from datetime import datetime, timezone

import aiosqlite

from bond.config import settings

log = logging.getLogger(__name__)

_TTL_DAYS = 7

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS search_cache (
    query_hash   TEXT NOT NULL PRIMARY KEY,
    thread_id    TEXT,
    results_json TEXT NOT NULL,
    cached_at    TEXT NOT NULL
);
"""

_MIGRATE_TABLE_SQL = """
DROP TABLE IF EXISTS search_cache;
CREATE TABLE search_cache (
    query_hash   TEXT NOT NULL PRIMARY KEY,
    thread_id    TEXT,
    results_json TEXT NOT NULL,
    cached_at    TEXT NOT NULL
);
"""

# Ensure the data directory exists once at import time (sync, idempotent).
os.makedirs(os.path.dirname(os.path.abspath(settings.metadata_db_path)), exist_ok=True)

# One-shot table initialisation guard.
_init_lock: asyncio.Lock | None = None
_table_ready = False


def _get_lock() -> asyncio.Lock:
    global _init_lock
    if _init_lock is None:
        _init_lock = asyncio.Lock()
    return _init_lock


async def _ensure_table_once(conn: aiosqlite.Connection) -> None:
    """Create or migrate search_cache table exactly once per process lifetime."""
    global _table_ready
    if _table_ready:
        return
    async with _get_lock():
        if _table_ready:
            return
        needs_migration = False
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='search_cache'"
        )
        if await cursor.fetchone():
            cursor = await conn.execute("PRAGMA table_info(search_cache)")
            cols = await cursor.fetchall()
            # col[1] = column name, col[5] = pk order (>0 means part of PK)
            needs_migration = any(col[1] == "thread_id" and col[5] > 0 for col in cols)

        sql = _MIGRATE_TABLE_SQL if needs_migration else _CREATE_TABLE_SQL
        await conn.executescript(sql)
        await conn.commit()
        if needs_migration:
            log.info(
                "search_cache: migrated from composite (query_hash, thread_id) PK "
                "to query_hash-only PK; old entries discarded"
            )
        _table_ready = True


def compute_query_hash(topic: str, keywords: list[str]) -> str:
    """Return a stable SHA-256 hex digest for (topic, keywords)."""
    canonical = f"{topic}:{':'.join(sorted(keywords))}"
    return hashlib.sha256(canonical.encode()).hexdigest()


async def get_cached_result(query_hash: str) -> str | None:
    """
    Return cached results for query_hash, or None on miss or TTL expiry.

    TTL is _TTL_DAYS (7 days).  Expired entries are not deleted from the table
    automatically — they are overwritten on the next save_cached_result call.
    """
    async with aiosqlite.connect(settings.metadata_db_path) as conn:
        await _ensure_table_once(conn)
        cursor = await conn.execute(
            "SELECT results_json, cached_at FROM search_cache WHERE query_hash = ?",
            (query_hash,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        results_json, cached_at_str = row
        cached_at = datetime.fromisoformat(cached_at_str)
        age = datetime.now(timezone.utc) - cached_at
        if age.days >= _TTL_DAYS:
            log.debug(
                "search_cache: TTL expired for hash %.8s (age %d days)",
                query_hash,
                age.days,
            )
            return None
        log.debug("search_cache: hit for hash %.8s (age %d days)", query_hash, age.days)
        return results_json


async def save_cached_result(
    query_hash: str,
    results_json: str,
    thread_id: str = "",
) -> None:
    """Insert or replace a cache entry keyed by query_hash only.

    thread_id is stored for audit logging but is not part of the lookup key.
    """
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(settings.metadata_db_path) as conn:
        await _ensure_table_once(conn)
        await conn.execute(
            "INSERT OR REPLACE INTO search_cache "
            "(query_hash, thread_id, results_json, cached_at) VALUES (?, ?, ?, ?)",
            (query_hash, thread_id or None, results_json, now),
        )
        await conn.commit()
