"""Vector store abstraction (knowledge layer).

The knowledge layer talks to this interface, never to a concrete engine. The
implementation is QdrantVectorStore — embedded (a local path) for dev, or a
Dockerized Qdrant server via QDRANT_URL for the full stack. Keeping the
`VectorStore` interface means the engine can be swapped without touching the
KnowledgeBase or the agent.

Interface contract (text in, hits out; embedding is an implementation detail):
    store.upsert(ids, documents, metadatas)
    store.query(text, n_results, where=None) -> list[Hit]
    store.count() -> int
    store.reset()
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Hit:
    """A single retrieval result, engine-agnostic."""
    id: str
    document: str
    metadata: dict
    distance: float  # lower = more similar


class VectorStore(Protocol):
    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict]) -> None: ...
    def query(self, text: str, n_results: int = 3, where: dict | None = None) -> list[Hit]: ...
    def count(self) -> int: ...
    def reset(self) -> None: ...


class QdrantVectorStore:
    """Qdrant-backed store. Embeds locally with FastEmbed (no external embedding
    API). Runs embedded (local `path`) for dev, or against a Dockerized Qdrant
    server (`url`, e.g. http://localhost:6333) for the full stack."""

    EMBED_MODEL = "BAAI/bge-small-en-v1.5"  # 384-dim, small, local
    _NAMESPACE = uuid.UUID("f4b1c0de-0000-4000-8000-000000000000")

    def __init__(self, url: str | None = None, path: str | None = None,
                 collection: str = "quant_knowledge", timeout: float = 60.0):
        from fastembed import TextEmbedding
        from qdrant_client import QdrantClient, models

        self._models = models
        if url:
            # Prefer 127.0.0.1 over localhost: on Windows "localhost" can resolve
            # to IPv6 (::1) first and hang, surfacing as a client timeout.
            url = url.replace("localhost", "127.0.0.1")
            self.client = QdrantClient(url=url, timeout=timeout)
        else:
            self.client = QdrantClient(path=path or "./qdrant_db")  # embedded, no server
        self.collection_name = collection
        self.embedder = TextEmbedding(self.EMBED_MODEL)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self.embedder.embed(texts)]

    def _ensure_collection(self, dim: int) -> None:
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                self.collection_name,
                vectors_config=self._models.VectorParams(
                    size=dim, distance=self._models.Distance.COSINE),
            )

    def _point_id(self, raw_id: str) -> str:
        # Qdrant ids must be uint or UUID; derive a stable UUID from the string id.
        return str(uuid.uuid5(self._NAMESPACE, raw_id))

    def upsert(self, ids, documents, metadatas) -> None:
        if not ids:
            return
        vectors = self._embed(documents)
        self._ensure_collection(len(vectors[0]))
        points = [
            self._models.PointStruct(
                id=self._point_id(i), vector=v,
                payload={**(m or {}), "document": d, "_id": i},
            )
            for i, d, v, m in zip(ids, documents, vectors, metadatas)
        ]
        self.client.upsert(self.collection_name, points=points)

    def query(self, text, n_results=3, where=None) -> list[Hit]:
        if not self.client.collection_exists(self.collection_name):
            return []
        query_filter = None
        if where:
            query_filter = self._models.Filter(
                must=[self._models.FieldCondition(
                    key=k, match=self._models.MatchValue(value=v))
                    for k, v in where.items()]
            )
        res = self.client.query_points(
            self.collection_name, query=self._embed([text])[0],
            limit=n_results, query_filter=query_filter, with_payload=True,
        ).points
        hits = []
        for p in res:
            payload = p.payload or {}
            meta = {k: v for k, v in payload.items() if k not in ("document", "_id")}
            hits.append(Hit(
                id=payload.get("_id", str(p.id)),
                document=payload.get("document", ""),
                metadata=meta,
                distance=round(1.0 - p.score, 4),  # cosine similarity -> distance
            ))
        return hits

    def count(self) -> int:
        if not self.client.collection_exists(self.collection_name):
            return 0
        return self.client.count(self.collection_name).count

    def reset(self) -> None:
        if self.client.collection_exists(self.collection_name):
            self.client.delete_collection(self.collection_name)


def make_vector_store() -> VectorStore:
    """Build the Qdrant vector store from the environment.

    QDRANT_URL = http://host:6333  -> Dockerized server (the full stack)
    unset                          -> embedded local store at ./qdrant_db (dev)
    """
    import os

    return QdrantVectorStore(url=os.environ.get("QDRANT_URL") or None)
