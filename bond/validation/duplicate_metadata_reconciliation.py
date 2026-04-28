from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from bond.db.metadata_log import get_all_article_metadata
from bond.store.chroma import (
    get_or_create_metadata_collection,
    upsert_topic_in_metadata_collection,
)


@dataclass(frozen=True)
class ArticleMetadataRow:
    row_id: int
    thread_id: str
    topic: str
    published_date: str
    mode: str


@dataclass(frozen=True)
class ChromaTopicRecord:
    thread_id: str
    topic: str
    published_date: str | None
    mode: str | None


@dataclass(frozen=True)
class DuplicateMetadataDiff:
    sqlite_count: int
    chroma_count: int
    missing_in_chroma: tuple[ArticleMetadataRow, ...]
    orphaned_in_chroma: tuple[ChromaTopicRecord, ...]


def normalize_sqlite_metadata_rows(rows: Sequence[Mapping[str, Any]]) -> list[ArticleMetadataRow]:
    normalized: list[ArticleMetadataRow] = []
    for row in rows:
        thread_id = str(row.get("thread_id") or "").strip()
        topic = str(row.get("topic") or "").strip()
        published_date = str(row.get("published_date") or "").strip()
        if not thread_id or not topic or not published_date:
            continue

        normalized.append(
            ArticleMetadataRow(
                row_id=int(row.get("id") or 0),
                thread_id=thread_id,
                topic=topic,
                published_date=published_date,
                mode=str(row.get("mode") or "author"),
            )
        )
    return normalized


def normalize_chroma_metadata_records(payload: Mapping[str, Any]) -> list[ChromaTopicRecord]:
    ids = payload.get("ids") or []
    documents = payload.get("documents") or []
    metadatas = payload.get("metadatas") or []

    normalized: list[ChromaTopicRecord] = []
    for index, raw_id in enumerate(ids):
        thread_id = raw_id if isinstance(raw_id, str) else str(raw_id or "")
        if not thread_id:
            continue

        raw_topic = documents[index] if index < len(documents) else None
        raw_metadata = metadatas[index] if index < len(metadatas) else None
        metadata = raw_metadata if isinstance(raw_metadata, Mapping) else {}
        topic = raw_topic if isinstance(raw_topic, str) else str(metadata.get("title") or "")
        if not topic:
            continue

        published_date = metadata.get("published_date")
        mode = metadata.get("mode")
        normalized.append(
            ChromaTopicRecord(
                thread_id=thread_id,
                topic=topic,
                published_date=published_date if isinstance(published_date, str) else None,
                mode=mode if isinstance(mode, str) else None,
            )
        )

    return normalized


def diff_duplicate_metadata(
    sqlite_rows: Sequence[ArticleMetadataRow],
    chroma_records: Sequence[ChromaTopicRecord],
) -> DuplicateMetadataDiff:
    sqlite_by_thread: dict[str, ArticleMetadataRow] = {}
    for row in sqlite_rows:
        sqlite_by_thread.setdefault(row.thread_id, row)

    chroma_by_thread: dict[str, ChromaTopicRecord] = {}
    for record in chroma_records:
        chroma_by_thread.setdefault(record.thread_id, record)

    missing_in_chroma = tuple(
        row for thread_id, row in sqlite_by_thread.items() if thread_id not in chroma_by_thread
    )
    orphaned_in_chroma = tuple(
        record
        for thread_id, record in chroma_by_thread.items()
        if thread_id not in sqlite_by_thread
    )

    return DuplicateMetadataDiff(
        sqlite_count=len(sqlite_rows),
        chroma_count=len(chroma_records),
        missing_in_chroma=missing_in_chroma,
        orphaned_in_chroma=orphaned_in_chroma,
    )


async def load_duplicate_metadata_diff(collection: Any | None = None) -> DuplicateMetadataDiff:
    sqlite_rows = normalize_sqlite_metadata_rows(await get_all_article_metadata())
    target_collection = collection or get_or_create_metadata_collection()
    chroma_payload = target_collection.get(include=["documents", "metadatas"])
    chroma_records = normalize_chroma_metadata_records(chroma_payload)
    return diff_duplicate_metadata(sqlite_rows, chroma_records)


def apply_missing_chroma_backfill(
    diff: DuplicateMetadataDiff,
    collection: Any | None = None,
) -> list[str]:
    if not diff.missing_in_chroma:
        return []

    target_collection = collection or get_or_create_metadata_collection()
    applied_ids: list[str] = []
    for row in diff.missing_in_chroma:
        upsert_topic_in_metadata_collection(
            thread_id=row.thread_id,
            topic=row.topic,
            published_date=row.published_date,
            mode=row.mode,
            collection=target_collection,
        )
        applied_ids.append(row.thread_id)

    return applied_ids
