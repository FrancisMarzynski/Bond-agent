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
