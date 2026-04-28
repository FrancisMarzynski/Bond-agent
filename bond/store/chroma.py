from typing import Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from bond.config import settings

_client: Any = None
_collection: Any = None


def get_chroma_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        if settings.chroma_host:
            # Docker / remote mode: talk to ChromaDB over HTTP
            _client = chromadb.HttpClient(
                host=settings.chroma_host,
                port=settings.chroma_port,
            )
        else:
            # Local dev mode: embedded persistent storage
            _client = chromadb.PersistentClient(path=settings.chroma_path)
    return _client


def get_or_create_corpus_collection():
    global _collection
    if _collection is None:
        client = get_chroma_client()
        ef = SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2",
            device="cpu",
        )
        _collection = client.get_or_create_collection(
            name="bond_style_corpus_v1",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def get_corpus_collection():
    """Get existing collection without creating it. Returns None if not initialized."""
    return _collection or get_or_create_corpus_collection()


_metadata_collection = None


def get_or_create_metadata_collection():
    """Get or create the metadata_log ChromaDB collection for duplicate topic detection."""
    global _metadata_collection
    if _metadata_collection is None:
        client = get_chroma_client()
        ef = SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2",
            device="cpu",
        )
        _metadata_collection = client.get_or_create_collection(
            name="bond_metadata_log_v1",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    return _metadata_collection


def upsert_topic_in_metadata_collection(
    thread_id: str,
    topic: str,
    published_date: str,
    mode: str | None = None,
    *,
    collection: Any | None = None,
) -> None:
    """Create or update a published topic embedding by thread_id."""
    target_collection = collection or get_or_create_metadata_collection()
    metadata = {"title": topic, "published_date": published_date}
    if mode:
        metadata["mode"] = mode

    target_collection.upsert(
        ids=[thread_id],
        documents=[topic],
        metadatas=[metadata],
    )


def add_topic_to_metadata_collection(thread_id: str, topic: str, published_date: str) -> None:
    """Add a published topic embedding to the metadata_log collection.
    Called by save_metadata_node after article approval."""
    upsert_topic_in_metadata_collection(
        thread_id=thread_id,
        topic=topic,
        published_date=published_date,
    )


def delete_topic_from_metadata_collection(thread_id: str) -> None:
    """Delete a published topic embedding from the metadata_log collection."""
    collection = get_or_create_metadata_collection()
    collection.delete(ids=[thread_id])
