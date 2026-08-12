"""Vector store abstraction (Phase 3, step 3.4).

The knowledge layer talks to this interface, never to a concrete engine. Today
the only implementation is ChromaVectorStore (embedded, zero-setup, no Docker).
When we containerize, a PgVectorStore backed by Postgres + the pgvector
extension slots in behind the same interface — the KnowledgeBase and the agent
do not change.

Interface contract (text in, hits out; embedding is an implementation detail):
    store.upsert(ids, documents, metadatas)
    store.query(text, n_results, where=None) -> list[Hit]
    store.count() -> int
    store.reset()
"""

from __future__ import annotations

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


class ChromaVectorStore:
    """ChromaDB-backed store. Embeds locally with Chroma's default model
    (all-MiniLM-L6-v2) — no external embedding API required."""

    def __init__(self, path: str, collection: str = "quant_knowledge"):
        import chromadb

        self._chromadb = chromadb
        self.path = path
        self.collection_name = collection
        self.client = chromadb.PersistentClient(path=path)
        self.collection = self.client.get_or_create_collection(collection)

    def upsert(self, ids, documents, metadatas) -> None:
        if ids:
            self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def query(self, text, n_results=3, where=None) -> list[Hit]:
        res = self.collection.query(
            query_texts=[text], n_results=n_results, where=where or None
        )
        hits = []
        for id_, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            hits.append(Hit(id=id_, document=doc, metadata=meta or {}, distance=float(dist)))
        return hits

    def count(self) -> int:
        return self.collection.count()

    def reset(self) -> None:
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(self.collection_name)


# --- Future (Docker target) ---------------------------------------------------
# class PgVectorStore:
#     """Postgres + pgvector implementation of VectorStore. Same methods; embeds
#     with a bundled local model and stores vectors in a `knowledge_chunks` table
#     alongside the risk-data tables. Swap in by changing which store the
#     KnowledgeBase constructs — nothing else changes."""
#     ...
