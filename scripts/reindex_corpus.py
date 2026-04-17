"""
Corpus re-indexing migration: adds section_type and article_type to existing chunks.

Usage:
    uv run python scripts/reindex_corpus.py           # dry-run (prints counts only)
    uv run python scripts/reindex_corpus.py --apply   # apply updates in ChromaDB
"""
import argparse
import logging
import sys
from pathlib import Path

# Make sure the project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bond.store.chroma import get_or_create_corpus_collection
from bond.corpus.ingestor import _section_type

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_chunk_index(chunk_id: str) -> int:
    """Extract positional index from chunk ID: '{article_id}_{i}' → i."""
    try:
        return int(chunk_id.rsplit("_", 1)[-1])
    except (ValueError, IndexError):
        return 1  # treat unknown as body chunk


def migrate(apply: bool = False) -> None:
    collection = get_or_create_corpus_collection()
    total = collection.count()
    if total == 0:
        logger.info("Collection is empty — nothing to migrate.")
        return

    logger.info("Collection has %d chunks. Fetching all…", total)

    # Fetch all in one batch (ChromaDB default limit is large enough for test corpus)
    result = collection.get(include=["metadatas", "documents"])
    ids: list[str] = result["ids"]
    metadatas: list[dict] = result["metadatas"]

    already_migrated = 0
    to_update_ids: list[str] = []
    to_update_metas: list[dict] = []

    for chunk_id, meta in zip(ids, metadatas):
        if "section_type" in meta and "article_type" in meta:
            already_migrated += 1
            continue

        idx = _parse_chunk_index(chunk_id)
        updated_meta = dict(meta)
        updated_meta.setdefault("section_type", _section_type(idx))
        updated_meta.setdefault("article_type", meta.get("source_type", ""))

        to_update_ids.append(chunk_id)
        to_update_metas.append(updated_meta)

    logger.info(
        "Already migrated: %d  |  Needs update: %d",
        already_migrated,
        len(to_update_ids),
    )

    if not to_update_ids:
        logger.info("Nothing to update.")
        return

    section_counts: dict[str, int] = {}
    for m in to_update_metas:
        section_counts[m["section_type"]] = section_counts.get(m["section_type"], 0) + 1
    logger.info("section_type distribution in pending updates: %s", section_counts)

    if not apply:
        logger.info("Dry-run mode — pass --apply to write changes.")
        return

    # Update in batches of 500 to avoid memory spikes
    batch_size = 500
    for start in range(0, len(to_update_ids), batch_size):
        batch_ids = to_update_ids[start : start + batch_size]
        batch_metas = to_update_metas[start : start + batch_size]
        collection.update(ids=batch_ids, metadatas=batch_metas)
        logger.info("Updated batch %d–%d", start, start + len(batch_ids) - 1)

    logger.info("Migration complete: %d chunks updated.", len(to_update_ids))

    # Verify a sample
    sample = collection.get(ids=to_update_ids[:3], include=["metadatas"])
    for sid, smeta in zip(sample["ids"], sample["metadatas"]):
        logger.info(
            "  sample %s → section_type=%s article_type=%s",
            sid,
            smeta.get("section_type"),
            smeta.get("article_type"),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add section_type + article_type to ChromaDB chunks.")
    parser.add_argument("--apply", action="store_true", help="Write updates (default: dry-run).")
    args = parser.parse_args()
    migrate(apply=args.apply)
