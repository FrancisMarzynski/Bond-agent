# 42 — Semantic Cache: Cross-Session Sharing & TTL

## What changed

`bond/db/search_cache.py` and `bond/graph/nodes/researcher.py` were updated to make the Exa search result cache **shared across all sessions** and **self-expiring** after 7 days.

---

## Problem

`save_cached_result` / `get_cached_result` used `(query_hash, thread_id)` as the composite primary key.  
The same topic searched in session A and session B made two identical Exa API calls — the cache never hit across session boundaries.  
In production (where BIM, XR, and instalacje tematyki recur daily) this caused avoidable repeat API spend.

Additionally, there was no TTL — a cached result could theoretically be returned indefinitely, serving stale web data.

---

## Changes

### `bond/db/search_cache.py`

| Aspect | Before | After |
|---|---|---|
| Primary key | `(query_hash, thread_id)` | `query_hash` only |
| `thread_id` role | Part of lookup key | Stored as audit column, not used for lookup |
| TTL | None (permanent) | 7 days (`_TTL_DAYS = 7`) |
| Expired entry handling | N/A | `get_cached_result` returns `None`; overwritten on next save |
| Schema migration | — | Auto-detects old composite PK via `PRAGMA table_info`, drops and recreates table |

**New function signatures:**
```python
async def get_cached_result(query_hash: str) -> str | None
async def save_cached_result(query_hash: str, results_json: str, thread_id: str = "") -> None
```

**TTL check** (inside `get_cached_result`):
```python
age = datetime.now(timezone.utc) - datetime.fromisoformat(cached_at_str)
if age.days >= _TTL_DAYS:
    return None
```

**Migration logic** (inside `_ensure_table_once`):
```python
cursor = await conn.execute("PRAGMA table_info(search_cache)")
cols = await cursor.fetchall()
needs_migration = any(col[1] == "thread_id" and col[5] > 0 for col in cols)
```
If the old composite PK is detected, the table is dropped and recreated. Old entries are discarded (regeneratable from Exa).

### `bond/graph/nodes/researcher.py`

- Layer 2 cache read: `get_cached_result(query_hash, thread_id)` → `get_cached_result(query_hash)`
- Layer 2 cache write: `save_cached_result(query_hash, thread_id, raw_results)` → `save_cached_result(query_hash, raw_results, thread_id)`
- Comment updated from "SQLite session cache" to "SQLite cross-session cache (keyed by query_hash only, TTL 7 days)"

---

## Cache key design

`compute_query_hash(topic, keywords)` remains unchanged — SHA-256 of `"topic:kw1:kw2:..."` (keywords sorted for stability).  
Removing `thread_id` from the key means: same topic + same keywords = same hash = guaranteed cache hit across sessions.

---

## Why no semantic similarity (optional AC)

The optional AC (cosine similarity between query embeddings) was deferred.  
Hash-based matching is sufficient: `compute_query_hash` already normalises keyword order.  
Semantic matching would add latency (embedding call per query) and infrastructure (vector store for query hashes) — unjustified until there is evidence of keyword phrasing divergence causing misses.

---

## Acceptance criteria

- [x] `thread_id` removed from cache key — results are shared across all sessions
- [x] TTL of 7 days implemented — entries older than 7 days return `None` (trigger fresh Exa call)
- [ ] Semantic similarity matching — deferred (hash matching is sufficient)

---

## Files modified

- `bond/db/search_cache.py`
- `bond/graph/nodes/researcher.py`
