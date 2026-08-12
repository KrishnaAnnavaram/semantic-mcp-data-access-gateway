"""Knowledge / RAG layer (Phase 3, steps 3.5-3.7).

Walks knowledge/<domain>/<doc>.md, chunks each doc on markdown headings, tags
every chunk with its domain (the subfolder name) and source, and ingests them
into a VectorStore. Retrieval is semantic and can be scoped to a domain.

    kb = KnowledgeBase()                      # builds/loads the store
    kb.retrieve("how do I compute VaR")       # -> list[dict]
    kb.retrieve("EAD", domain="credit_risk")  # domain-scoped
"""

from __future__ import annotations

import pathlib
import re

from vector_store import ChromaVectorStore, VectorStore

KNOWLEDGE_DIR = pathlib.Path(__file__).resolve().parent.parent / "knowledge"
CHROMA_DIR = pathlib.Path(__file__).resolve().parent.parent / "chroma_db"


def _chunk_markdown(text: str) -> list[dict]:
    """Split a doc into chunks on markdown headings (deterministic, dry)."""
    parts = re.split(r"\n(?=#{1,6}\s)", text.strip())
    chunks = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        heading = part.splitlines()[0].lstrip("# ").strip()
        chunks.append({"heading": heading, "text": part})
    return chunks


def _iter_chunks(knowledge_dir: pathlib.Path):
    """Yield (id, text, metadata) for every chunk. Domain = subfolder name."""
    for path in sorted(knowledge_dir.rglob("*.md")):
        rel = path.relative_to(knowledge_dir)
        domain = rel.parts[0] if len(rel.parts) > 1 else "general"
        source = path.stem
        for i, chunk in enumerate(_chunk_markdown(path.read_text(encoding="utf-8"))):
            yield (
                f"{domain}/{source}::{i}",
                chunk["text"],
                {"domain": domain, "source": source, "heading": chunk["heading"]},
            )


class KnowledgeBase:
    def __init__(self, store: VectorStore | None = None, rebuild: bool = False):
        self.store = store or ChromaVectorStore(path=str(CHROMA_DIR))
        if rebuild:
            self.store.reset()
        if self.store.count() == 0:
            self.ingest()

    def ingest(self) -> int:
        ids, docs, metas = [], [], []
        for id_, text, meta in _iter_chunks(KNOWLEDGE_DIR):
            ids.append(id_)
            docs.append(text)
            metas.append(meta)
        self.store.upsert(ids, docs, metas)
        return len(ids)

    def retrieve(self, query: str, n_results: int = 3, domain: str | None = None) -> list[dict]:
        where = {"domain": domain} if domain else None
        hits = self.store.query(query, n_results=n_results, where=where)
        return [
            {
                "domain": h.metadata.get("domain"),
                "source": h.metadata.get("source"),
                "heading": h.metadata.get("heading"),
                "text": h.document,
                "distance": round(h.distance, 4),
            }
            for h in hits
        ]

    def count(self) -> int:
        return self.store.count()


if __name__ == "__main__":
    kb = KnowledgeBase(rebuild=True)
    print(f"Ingested {kb.count()} chunks from {KNOWLEDGE_DIR}\n")

    samples = [
        ("how do I compute 1-day VaR", None),
        ("average loss beyond the VaR threshold", "market_risk"),
        ("counterparty default risk pricing", None),
        ("loss given default and exposure at default", "credit_risk"),
    ]
    for q, dom in samples:
        tag = f" [domain={dom}]" if dom else ""
        print(f"Q: {q}{tag}")
        for h in kb.retrieve(q, n_results=2, domain=dom):
            print(f"   -> {h['domain']}/{h['source']}/{h['heading']}  (dist={h['distance']})")
        print()
