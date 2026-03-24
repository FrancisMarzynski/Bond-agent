-- Separate from LangGraph checkpoint DB (bond_checkpoints.db)
-- Stores published article metadata for duplicate detection and history

CREATE TABLE IF NOT EXISTS metadata_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    published_date TEXT NOT NULL,   -- ISO 8601 UTC
    mode TEXT NOT NULL DEFAULT 'author',
    created_at TEXT NOT NULL
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_metadata_log_published_date ON metadata_log (published_date);

-- AUTH-11: Exa search result cache, scoped per (query_hash, thread_id) session
CREATE TABLE IF NOT EXISTS search_cache (
    query_hash   TEXT NOT NULL,
    thread_id    TEXT NOT NULL,
    results_json TEXT NOT NULL,
    timestamp    TEXT NOT NULL,   -- ISO 8601 UTC, set at cache write time
    PRIMARY KEY (query_hash, thread_id)
);
