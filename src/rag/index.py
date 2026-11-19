"""Builds and opens the embedded Chroma index of the knowledge base.

Chroma runs embedded in the app's process only (never as a server), and vectors always come from
the embeddings client passed in (OpenRouter, or a fake in tests), never from Chroma's own
embedding functions.
"""

from pathlib import Path

import chromadb
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

from src import config
from src.knowledge import Place, load_places

_MODEL_KEY = "embedding_model"


def _client(persist_dir: Path) -> chromadb.ClientAPI:
    """Return the embedded Chroma client for a directory, with telemetry off."""
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(persist_dir), settings=chromadb.Settings(anonymized_telemetry=False)
    )


def build_index(
    embeddings: Embeddings,
    places: tuple[Place, ...] | None = None,
    persist_dir: Path = config.CHROMA_DIR,
    model_name: str = config.EMBEDDING_MODEL,
) -> int:
    """Embed every place and write a fresh collection; return the number of documents."""
    places = places if places is not None else load_places()
    client = _client(persist_dir)
    if config.CHROMA_COLLECTION in [c.name for c in client.list_collections()]:
        client.delete_collection(config.CHROMA_COLLECTION)
    client.create_collection(
        config.CHROMA_COLLECTION,
        embedding_function=None,
        metadata={_MODEL_KEY: model_name, "hnsw:space": "cosine"},
    )
    store = Chroma(
        collection_name=config.CHROMA_COLLECTION, embedding_function=embeddings, client=client
    )
    docs = [p.to_document() for p in places]
    store.add_documents(docs, ids=[d.id for d in docs])
    return len(docs)


def open_index(embeddings: Embeddings, persist_dir: Path = config.CHROMA_DIR) -> Chroma | None:
    """Open the existing index, or return None when it has not been built yet."""
    if not persist_dir.exists():
        return None
    client = _client(persist_dir)
    if config.CHROMA_COLLECTION not in [c.name for c in client.list_collections()]:
        return None
    return Chroma(
        collection_name=config.CHROMA_COLLECTION, embedding_function=embeddings, client=client
    )
