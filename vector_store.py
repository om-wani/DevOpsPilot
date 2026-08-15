"""ChromaDB persistent vector store.

One collection holds every chunk. Writes go through `upsert` keyed on the
deterministic chunk id, so re-indexing after an edit replaces the old vector
instead of leaving a stale copy behind to be retrieved twice.
"""

from functools import lru_cache
from pathlib import Path

import chromadb

PERSIST_DIR = Path(__file__).parent / "chroma"
COLLECTION_NAME = "devops_pilot"


@lru_cache(maxsize=1)
def get_collection():
    client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    # Embeddings are supplied by us, so no embedding function is configured here.
    return client.get_or_create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )


def upsert_chunks(chunks, vectors):
    """Store chunks and their vectors. Order must match."""
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors must be the same length")
    if not chunks:
        return 0

    get_collection().upsert(
        ids=[c["id"] for c in chunks],
        embeddings=vectors,
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )
    return len(chunks)


def query(vector, top_n=8, where=None):
    """Return the closest chunks as a list of dicts: id, text, metadata, distance."""
    result = get_collection().query(
        query_embeddings=[vector],
        n_results=top_n,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    return _flatten(result)


def get_chunk(chunk_id):
    """Fetch one chunk by its deterministic id. Returns None if it is not stored.

    Distance is 0.0 because this is an exact lookup, not a similarity match, which
    keeps the shape identical to `query` results for callers that rank them together.
    """
    result = get_collection().get(ids=[chunk_id], include=["documents", "metadatas"])

    ids = result.get("ids") or []
    if not ids:
        return None

    return {
        "id": ids[0],
        "text": (result.get("documents") or [""])[0],
        "metadata": (result.get("metadatas") or [{}])[0] or {},
        "distance": 0.0,
    }


def _flatten(result):
    ids = (result.get("ids") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    return [
        {
            "id": ids[i],
            "text": documents[i],
            "metadata": metadatas[i] or {},
            "distance": distances[i],
        }
        for i in range(len(ids))
    ]


def count():
    return get_collection().count()


def reset():
    """Drop every vector. Used by the index script's --rebuild flag."""
    client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    get_collection.cache_clear()
    return get_collection()
