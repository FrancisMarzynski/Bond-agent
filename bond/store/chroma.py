from typing import Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from bond.config import settings

_client: Any = None
_collection: Any = None


def get_chroma_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
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


def add_topic_to_metadata_collection(thread_id: str, topic: str, published_date: str) -> None:
    """Add a published topic embedding to the metadata_log collection.
    Called by save_metadata_node after article approval."""
    collection = get_or_create_metadata_collection()
    collection.add(
        ids=[thread_id],
        documents=[topic],
        metadatas=[{"title": topic, "published_date": published_date}],
    )
