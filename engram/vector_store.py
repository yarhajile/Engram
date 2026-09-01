from __future__ import annotations

import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHROMA_PATH = ROOT / ".engram" / "chromadb"
COLLECTION_NAME = "engrams"

_client: Any | None = None
_collection: Any | None = None
_available: bool | None = None


def is_enabled() -> bool:
    return os.environ.get("ENGRAM_DISABLE_CHROMA", "").lower() not in {"1", "true", "yes"}


def is_available() -> bool:
    global _available
    if _available is not None:
        return _available
    if not is_enabled():
        _available = False
        return False
    try:
        import chromadb  # noqa: F401
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction  # noqa: F401
    except Exception:
        _available = False
    else:
        _available = True
    return _available


def collection(path: Path = DEFAULT_CHROMA_PATH):
    global _client, _collection
    if not is_available():
        return None
    if _collection is not None:
        return _collection

    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    path.mkdir(parents=True, exist_ok=True)
    embedding_function = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    _client = chromadb.PersistentClient(path=str(path))
    _collection = _client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def document_for_engram(engram: dict[str, Any]) -> str:
    tags = " ".join(engram.get("tags") or [])
    files = " ".join(engram.get("files") or [])
    return "\n".join(
        [
            f"Title: {engram.get('title', '')}",
            f"Kind: {engram.get('kind', '')}",
            f"Summary: {engram.get('summary', '')}",
            f"Body: {engram.get('body', '')}",
            f"Tags: {tags}",
            f"Files: {files}",
        ]
    )


def upsert_engram(engram: dict[str, Any], path: Path = DEFAULT_CHROMA_PATH) -> bool:
    coll = collection(path)
    if coll is None:
        return False
    coll.upsert(
        ids=[str(engram["id"])],
        documents=[document_for_engram(engram)],
        metadatas=[
            {
                "status": engram.get("status", "active"),
                "kind": engram.get("kind", "note"),
                "continuity": engram.get("continuity", "low"),
                "durable": engram.get("durable", "low"),
                "importance": int(engram.get("importance") or 3),
            }
        ],
    )
    return True


def search(query: str, limit: int = 8, path: Path = DEFAULT_CHROMA_PATH) -> list[tuple[int, float]]:
    coll = collection(path)
    if coll is None or coll.count() == 0:
        return []
    result = coll.query(
        query_texts=[query],
        n_results=min(limit, coll.count()),
        where={"status": "active"},
    )
    ids = result.get("ids", [[]])[0]
    distances = result.get("distances", [[]])[0]
    matches: list[tuple[int, float]] = []
    for raw_id, distance in zip(ids, distances):
        matches.append((int(raw_id), 1.0 - float(distance)))
    return matches


def delete_engram(engram_id: int, path: Path = DEFAULT_CHROMA_PATH) -> bool:
    coll = collection(path)
    if coll is None:
        return False
    coll.delete(ids=[str(engram_id)])
    return True
