from bond.validation.duplicate_metadata_reconciliation import (
    ArticleMetadataRow,
    ChromaTopicRecord,
    apply_missing_chroma_backfill,
    diff_duplicate_metadata,
    normalize_chroma_metadata_records,
)


class FakeMetadataCollection:
    def __init__(self, records: list[tuple[str, str, dict]] | None = None):
        self.records = {
            thread_id: {"document": topic, "metadata": metadata}
            for thread_id, topic, metadata in (records or [])
        }
        self.upsert_calls: list[list[str]] = []

    def get(self, include=None):
        ids = list(self.records.keys())
        documents = [self.records[thread_id]["document"] for thread_id in ids]
        metadatas = [self.records[thread_id]["metadata"] for thread_id in ids]
        return {
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
        }

    def upsert(self, ids, documents, metadatas):
        self.upsert_calls.append(list(ids))
        for thread_id, topic, metadata in zip(ids, documents, metadatas):
            self.records[thread_id] = {"document": topic, "metadata": metadata}


def _sqlite_row(thread_id: str, topic: str) -> ArticleMetadataRow:
    return ArticleMetadataRow(
        row_id=1,
        thread_id=thread_id,
        topic=topic,
        published_date="2026-04-28T12:00:00+00:00",
        mode="author",
    )


def test_diff_duplicate_metadata_detects_missing_in_chroma():
    diff = diff_duplicate_metadata(
        sqlite_rows=[
            _sqlite_row("thread-1", "Temat A"),
            _sqlite_row("thread-2", "Temat B"),
        ],
        chroma_records=[
            ChromaTopicRecord(
                thread_id="thread-1",
                topic="Temat A",
                published_date="2026-04-28T12:00:00+00:00",
                mode="author",
            )
        ],
    )

    assert diff.sqlite_count == 2
    assert diff.chroma_count == 1
    assert [row.thread_id for row in diff.missing_in_chroma] == ["thread-2"]
    assert diff.orphaned_in_chroma == ()


def test_diff_duplicate_metadata_detects_orphaned_in_chroma():
    diff = diff_duplicate_metadata(
        sqlite_rows=[_sqlite_row("thread-1", "Temat A")],
        chroma_records=[
            ChromaTopicRecord(
                thread_id="thread-1",
                topic="Temat A",
                published_date="2026-04-28T12:00:00+00:00",
                mode="author",
            ),
            ChromaTopicRecord(
                thread_id="thread-orphan",
                topic="Temat osierocony",
                published_date="2026-04-28T12:05:00+00:00",
                mode=None,
            ),
        ],
    )

    assert diff.sqlite_count == 1
    assert diff.chroma_count == 2
    assert diff.missing_in_chroma == ()
    assert [record.thread_id for record in diff.orphaned_in_chroma] == ["thread-orphan"]


def test_apply_missing_chroma_backfill_writes_only_missing_ids():
    collection = FakeMetadataCollection(
        records=[
            (
                "thread-1",
                "Temat A",
                {"title": "Temat A", "published_date": "2026-04-28T12:00:00+00:00"},
            ),
            (
                "thread-orphan",
                "Temat osierocony",
                {"title": "Temat osierocony", "published_date": "2026-04-28T12:05:00+00:00"},
            ),
        ]
    )
    diff = diff_duplicate_metadata(
        sqlite_rows=[
            _sqlite_row("thread-1", "Temat A"),
            _sqlite_row("thread-2", "Temat B"),
        ],
        chroma_records=normalize_chroma_metadata_records(collection.get(include=["documents", "metadatas"])),
    )

    applied_ids = apply_missing_chroma_backfill(diff, collection=collection)

    assert applied_ids == ["thread-2"]
    assert collection.upsert_calls == [["thread-2"]]
    assert "thread-orphan" in collection.records


def test_apply_missing_chroma_backfill_is_idempotent_on_rerun():
    collection = FakeMetadataCollection(
        records=[
            (
                "thread-1",
                "Temat A",
                {"title": "Temat A", "published_date": "2026-04-28T12:00:00+00:00"},
            )
        ]
    )
    sqlite_rows = [
        _sqlite_row("thread-1", "Temat A"),
        _sqlite_row("thread-2", "Temat B"),
    ]

    first_diff = diff_duplicate_metadata(
        sqlite_rows=sqlite_rows,
        chroma_records=normalize_chroma_metadata_records(collection.get(include=["documents", "metadatas"])),
    )
    assert apply_missing_chroma_backfill(first_diff, collection=collection) == ["thread-2"]

    second_diff = diff_duplicate_metadata(
        sqlite_rows=sqlite_rows,
        chroma_records=normalize_chroma_metadata_records(collection.get(include=["documents", "metadatas"])),
    )
    assert second_diff.missing_in_chroma == ()
    assert apply_missing_chroma_backfill(second_diff, collection=collection) == []
    assert collection.upsert_calls == [["thread-2"]]
