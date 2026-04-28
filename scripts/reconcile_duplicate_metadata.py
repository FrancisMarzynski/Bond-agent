"""
Duplicate metadata reconciliation for historical SQLite <-> Chroma drift.

Usage:
    uv run python scripts/reconcile_duplicate_metadata.py
    uv run python scripts/reconcile_duplicate_metadata.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bond.validation.duplicate_metadata_reconciliation import (
    apply_missing_chroma_backfill,
    load_duplicate_metadata_diff,
)


def _sample_thread_ids(items, limit: int = 5) -> str:
    sample = [item.thread_id for item in items[:limit]]
    return ", ".join(sample) if sample else "brak"


def _print_summary(diff) -> None:
    print(f"SQLite rows: {diff.sqlite_count}")
    print(f"Chroma records: {diff.chroma_count}")
    print(f"Missing in Chroma: {len(diff.missing_in_chroma)}")
    print(f"Orphaned in Chroma: {len(diff.orphaned_in_chroma)}")
    print(f"Sample missing thread_id: {_sample_thread_ids(diff.missing_in_chroma)}")
    print(f"Sample orphaned thread_id: {_sample_thread_ids(diff.orphaned_in_chroma)}")


async def reconcile(apply: bool = False) -> None:
    diff = await load_duplicate_metadata_diff()
    _print_summary(diff)

    if not apply:
        print("Dry-run mode — pass --apply to backfill only missing Chroma records.")
        return

    applied_ids = apply_missing_chroma_backfill(diff)
    print(f"Applied backfill for {len(applied_ids)} thread_id(s).")

    final_diff = await load_duplicate_metadata_diff()
    _print_summary(final_diff)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconcile duplicate-topic metadata between SQLite and Chroma."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write missing Chroma records (default: dry-run).",
    )
    args = parser.parse_args()
    asyncio.run(reconcile(apply=args.apply))


if __name__ == "__main__":
    main()
