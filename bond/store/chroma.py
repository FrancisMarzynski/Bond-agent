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
