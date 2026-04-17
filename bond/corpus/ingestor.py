import uuid
from datetime import datetime, timezone
from bond.store.chroma import get_or_create_corpus_collection
from bond.store.article_log import log_article
from bond.corpus.chunker import chunk_article


def _section_type(chunk_index: int) -> str:
    """Return section label based on position within article."""
    return "wstęp" if chunk_index == 0 else "rozwinięcie"


class CorpusIngestor:
    def ingest(
        self,
        text: str,
        title: str,
        source_type: str,  # "own" | "external"
        source_url: str = "",
    ) -> dict:
        """
        Chunk text, embed into ChromaDB, log article to SQLite.
        Returns: {"article_id": str, "chunks_added": int}
        """
        chunks = chunk_article(text)
        if not chunks:
            return {"article_id": "", "chunks_added": 0}

        article_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        collection = get_or_create_corpus_collection()
        ids = [f"{article_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "source_type": source_type,
                "article_type": source_type,
                "article_id": article_id,
                "article_title": title,
                "source_url": source_url,
                "ingested_at": now,
                "section_type": _section_type(i),
            }
            for i, _ in enumerate(chunks)
        ]
        collection.add(documents=chunks, metadatas=metadatas, ids=ids)
        log_article(article_id, source_type, title, source_url, len(chunks))

        return {"article_id": article_id, "chunks_added": len(chunks)}
