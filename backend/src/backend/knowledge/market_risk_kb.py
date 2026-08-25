"""The Market Risk reference library, as a second Qdrant collection.

`docs/market-risk-kb/` is 47 documents, ~167,000 words: the taxonomy, the
instrument coverage, the risk-class treatments, VaR/ES/stress, the FRTB
framework, and six large reference catalogues (calculations, formulas, risk
factors, glossary, question-to-calculation, dependency graph).

It is **not** the `knowledge/` corpus and must never be mixed with it.

    knowledge/            executable analytical contracts. Short, mapped to real
                          MCP tools, and the thing the domain expert *grounds*
                          a requirement in - "historical VaR reads 250 trading
                          days" has to be quotable from here or the number is
                          rejected. Collection: `quant_knowledge`.

    docs/market-risk-kb/  a reference library written for people. Broad,
                          explanatory, regulatory. It answers "what is DV01",
                          "how does DRC aggregate", "what does MAR21.8 fix".
                          Collection: `market_risk_kb`.

Separate collections rather than one collection with a `corpus` payload field,
for three reasons that all reduce to blast radius:

1. `KnowledgeBase(rebuild=True)` calls `store.reset()`, which **deletes the
   collection**. Sharing one collection means the documented re-ingest command
   for `knowledge/` silently destroys 1,485 market-risk vectors. A payload flag
   cannot protect against a collection-level delete.
2. The two corpora have different chunking. `knowledge/` is heading-only;
   this one is budget-enforced and hierarchy-aware. Storing both under one
   schema would mean one of them lying about how it was built.
3. Retrieval can be measured per corpus, which is what makes a regression in
   one visible rather than averaged away.

Ingestion is idempotent: ids are deterministic, so a rerun upserts in place, and
any chunk a document no longer produces is pruned rather than left orphaned.
"""

from __future__ import annotations

import hashlib
import logging
import pathlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from backend.knowledge.markdown_chunker import (
    MODEL_LIMIT,
    Chunk,
    bge_token_counter,
    chunk_document,
)
from backend.knowledge.vector_store import VectorStore, make_vector_store
from backend.knowledge.versioning import corpus_version
from backend.paths import MARKET_RISK_KB_DIR

LOGGER = logging.getLogger(__name__)

COLLECTION = "market_risk_kb"
CORPUS = "market_risk_kb"          # the `domain` a retrieved chunk reports
BATCH_SIZE = 128

# --- metadata derivation -----------------------------------------------------
#
# Everything below is *derived from observable text* - a regex over the heading
# path, the document title, or the chunk's own body. Nothing is inferred, and a
# field with no match is omitted rather than guessed. That is the difference
# between metadata and decoration: a `risk_category` nobody can trace back to a
# line of the document is worse than no `risk_category` at all, because it will
# eventually be filtered on.

_SOURCE_TYPE = (
    ("reference_catalog", r"catalog|catalogue|handbook|register|glossary|index|graph"),
    ("worked_examples", r"worked example"),
    ("implementation", r"pseudocode|data model|architecture|agent knowledge|contracts"),
    ("regulation", r"regulatory|frtb|irrbb|basel|trading book boundary|default risk"),
    ("governance_process", r"governance|control|roles|workflow|reporting|limit|"
                           r"validation|backtesting|model risk"),
    ("learning_path", r"learning path"),
)

_RISK_CATEGORY = (
    ("interest_rate", r"interest[- ]rate|\bgirr\b|\birrbb\b|duration|dv01|pv01|"
                      r"key[- ]rate|yield curve|convexity"),
    ("credit_spread", r"credit spread|\bcsr\b|\bcs01\b|z-spread|asset swap"),
    ("default_risk", r"default risk|\bdrc\b|jump[- ]to[- ]default|\bjtd\b"),
    ("fx", r"\bfx\b|foreign exchange"),
    ("equity", r"\bequit(y|ies)\b|dividend"),
    ("commodity", r"commodit"),
    ("volatility", r"option|greek|\bvega\b|\bgamma\b|volatilit|smile|skew"),
    ("var_es", r"\bvar\b|value at risk|expected shortfall|\bes\b(?!\w)"),
    ("stress", r"stress|scenario"),
    ("capital", r"capital|\brwa\b|standardised approach|internal models"),
    ("counterparty", r"\bcva\b|\bsimm\b|counterparty|\bxva\b"),
    ("pnl", r"p&l|profit and loss|attribution"),
)

_ASSET_CLASS = (
    ("rates", r"interest[- ]rate|\bgirr\b|\birrbb\b|swap|bond|treasury|yield curve"),
    ("credit", r"credit|\bcds\b|\bcsr\b|default|issuer"),
    ("fx", r"\bfx\b|foreign exchange|currency"),
    ("equity", r"\bequit(y|ies)\b"),
    ("commodity", r"commodit"),
)

_FRAMEWORK = (
    ("FRTB", r"\bfrtb\b"),
    ("IRRBB", r"\birrbb\b"),
    ("ISDA SIMM", r"\bsimm\b"),
    ("Basel III", r"basel"),
)

_JURISDICTION = (
    ("US", r"united states|\bus\b|\bfrb\b|federal reserve"),
    ("EU", r"european union|\beu\b|\bcrr\b|\beba\b"),
    ("UK", r"united kingdom|\buk\b|\bpra\b"),
    ("Global", r"basel committee|\bbcbs\b"),
)

# Multi-word or unambiguous only, and matched with word boundaries on both
# sides. A bare three-letter term is how `instrument: ["fra"]` ends up on a
# chunk of the regulatory tracker, because "framework" begins with one.
_INSTRUMENTS = (
    "government bond", "corporate bond", "floating-rate note", "inflation-linked",
    "mortgage-backed", "asset-backed", "interest-rate swap", "cross-currency swap",
    "swaption", "bond future", "interest-rate future", "fx forward", "fx swap",
    "fx option", "credit default swap", "cds index", "equity option",
    "equity future", "commodity future", "treasury bill", "repo",
)

# Basel/supervisory citations, as they are actually written in this corpus.
_REGULATION_RE = re.compile(
    r"\b(?:MAR|CRE|RBC|SRP|CAP|LEX|DIS)\d{1,3}(?:\.\d+)*\b"
    r"|\bSR \d{2}-\d+\b|\bBCBS \d{2,3}\b|\bCRR ?\d*\b|\bIFRS \d+\b")

# The calculation-ID scheme this corpus defines for itself (PV-01, IR-12, FR-07).
_CALC_ID_RE = re.compile(r"\b([A-Z]{2})-(\d{2})\b")
# `| IR-02 | **Modified duration** | ...` - the catalogue's own row shape.
_CALC_ROW_RE = re.compile(r"\|\s*[A-Z]{2}-\d{2}\s*\|\s*\*\*(.+?)\*\*\s*\|")

_NUMBER_RE = re.compile(r"^(\d{1,2}[A-Z]?)[_-]")
_HEADING_NUM_RE = re.compile(r"^\s*(?:\d+(?:\.\d+)*|[A-Z])[.)]?\s+")


def _first_match(table: tuple[tuple[str, str], ...], haystack: str) -> str | None:
    for label, pattern in table:
        if re.search(pattern, haystack, re.IGNORECASE):
            return label
    return None


def _all_matches(table: tuple[tuple[str, str], ...], haystack: str) -> list[str]:
    return [label for label, pattern in table
            if re.search(pattern, haystack, re.IGNORECASE)]


def _slug(text: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


@dataclass
class DocumentMeta:
    """Facts about a whole document, read once from its own text."""

    path: pathlib.Path
    rel: str
    document_id: str
    document_number: str | None
    document_name: str
    source_type: str
    risk_category: str | None
    asset_class: str | None
    frameworks: list[str] = field(default_factory=list)


def read_document_meta(path: pathlib.Path, text: str,
                       root: pathlib.Path) -> DocumentMeta:
    """Derive document-level metadata from the document itself."""
    rel = path.relative_to(root).as_posix()
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem
    number = _NUMBER_RE.match(path.stem)
    # The **title only**, never the body and never the full heading list. A
    # document that mentions ISDA SIMM in one subsection is not a counterparty
    # document, and scanning every heading is exactly how `29 - The Regulatory
    # Framework` acquired `risk_category: counterparty` on all 24 of its chunks.
    # A field nobody can trace to a specific line is worse than an absent one.
    return DocumentMeta(
        path=path, rel=rel, document_id=path.stem,
        document_number=number.group(1) if number else None,
        document_name=title,
        source_type=_first_match(_SOURCE_TYPE, title) or "concept",
        risk_category=_first_match(_RISK_CATEGORY, title),
        asset_class=_first_match(_ASSET_CLASS, title),
        frameworks=_all_matches(_FRAMEWORK, title),
    )


def chunk_payload(chunk: Chunk, doc: DocumentMeta, index: int,
                  total: int) -> dict:
    """The payload stored beside one vector.

    Split in two halves on purpose. The first is always present and is what
    makes a retrieved chunk traceable to a line range in a file on disk. The
    second is derived, and each field is absent when nothing in the text
    supports it.
    """
    path = chunk.section.path
    # The H1 is the document, so the citation-worthy heading is everything below.
    trail = path[1:] if len(path) > 1 else path
    heading = " > ".join(trail) if trail else doc.document_name

    payload = {
        # -- identity and traceability (always present)
        "corpus": CORPUS,
        "domain": CORPUS,                 # the key the agent's citation reads
        "source": doc.document_id,        # ditto
        "document_name": doc.document_name,
        "document_path": doc.rel,
        "document_id": doc.document_id,
        "chunk_index": index,
        "total_chunks": total,
        "heading": heading,
        "heading_path": " > ".join(path),
        "section": trail[0] if trail else doc.document_name,
        "source_type": doc.source_type,
        "line_start": chunk.line_start,
        "line_end": chunk.line_end,
        "token_count": chunk.token_count,
        "content_sha256": hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
        "has_formula": "```" in chunk.text,
        "has_table": "\n|" in chunk.text,
    }
    if doc.document_number:
        payload["document_number"] = doc.document_number
    if len(trail) > 1:
        payload["subsection"] = trail[1]

    # -- derived, omitted when the text does not support them.
    # Scope is the document title plus this chunk's own heading path - two
    # short, specific strings a reader can check. No document-wide heading scan
    # and no fallback: if neither the title nor the heading names a risk class,
    # the chunk does not claim one.
    scope = f"{doc.document_name}\n{' '.join(path)}"
    category = _first_match(_RISK_CATEGORY, scope)
    if category:
        payload["risk_category"] = category
    asset = _first_match(_ASSET_CLASS, scope)
    if asset:
        payload["asset_class"] = asset

    frameworks = _all_matches(_FRAMEWORK, f"{scope}\n{chunk.text}")
    if frameworks:
        payload["framework"] = frameworks
    jurisdiction = _first_match(_JURISDICTION, " ".join(path))
    if jurisdiction:
        payload["jurisdiction"] = jurisdiction

    regulations = sorted({m.group(0) for m in _REGULATION_RE.finditer(chunk.text)})
    if regulations:
        payload["regulation"] = regulations[:24]

    calc_ids = sorted({m.group(0) for m in _CALC_ID_RE.finditer(chunk.text)})
    if calc_ids:
        payload["calculation_id"] = calc_ids[:40]
    calc_names = sorted({m.group(1).strip() for m in _CALC_ROW_RE.finditer(chunk.text)})
    if calc_names:
        payload["calculation_name"] = calc_names[:40]
    # In the formula handbook the deepest heading *is* the formula's name, by
    # the document's own construction. Nowhere else is that true, so nowhere
    # else is the field set - the fenced blocks in docs 24/25/40 are pseudocode.
    if doc.document_number == "32" and trail:
        payload["formula_name"] = _HEADING_NUM_RE.sub("", trail[-1]).strip()

    instruments = [i for i in _INSTRUMENTS
                   if re.search(rf"\b{re.escape(i)}s?\b", " ".join(path), re.IGNORECASE)]
    if instruments:
        payload["instrument"] = instruments
    return payload


def _with_document_title(chunk: Chunk, doc: DocumentMeta) -> str:
    """Guarantee every chunk names its document.

    The chunker's breadcrumb is the heading path, and the outermost heading is
    usually the document title. Usually. The formula handbook restarts at H1 per
    level (`# LEVEL 3 - Bond Mathematics`), so a chunk of it would otherwise
    never say "Formula Handbook" - and a search for "formula for modified
    duration" is looking for exactly that word.
    """
    if chunk.section.path and chunk.section.path[0] == doc.document_name:
        return chunk.text
    return f"# {doc.document_name}\n{chunk.text}"


def chunk_id(doc: DocumentMeta, chunk: Chunk, index: int) -> str:
    """A stable identity for one chunk, independent of its content.

    `path :: ordinal :: section-slug`. The ordinal is what guarantees
    uniqueness - two sections in one document can legitimately share a heading,
    and an id built from the heading alone would let the second silently
    overwrite the first. The slug is carried anyway because an opaque id is
    impossible to debug from a Qdrant payload dump.

    Deliberately **not** hashed over the content. If the id changed when the
    text changed, editing a document would write a new point and abandon the
    old one; the content hash lives in the payload instead, where it records
    change without fragmenting identity.
    """
    trail = chunk.section.path[1:] or chunk.section.path
    return f"{CORPUS}/{doc.rel}::{index:04d}::{_slug(' '.join(trail))[:60]}"


# --- ingestion ---------------------------------------------------------------


@dataclass
class IngestReport:
    """What actually happened, including what did not work."""

    documents_discovered: int = 0
    documents_processed: int = 0
    documents_succeeded: int = 0
    documents_failed: int = 0
    chunks_created: int = 0
    embeddings_generated: int = 0
    vectors_upserted: int = 0
    vectors_failed: int = 0
    vectors_pruned: int = 0
    words: int = 0
    tokens: int = 0
    chunk_seconds: float = 0.0
    embed_upsert_seconds: float = 0.0
    failures: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.documents_failed == 0 and self.vectors_failed == 0

    def render(self) -> str:
        lines = [
            f"Documents discovered : {self.documents_discovered}",
            f"Documents processed  : {self.documents_processed}",
            f"Documents succeeded  : {self.documents_succeeded}",
            f"Documents failed     : {self.documents_failed}",
            f"Chunks created       : {self.chunks_created}",
            f"Embeddings generated : {self.embeddings_generated}",
            f"Vectors upserted     : {self.vectors_upserted}",
            f"Vectors failed       : {self.vectors_failed}",
            f"Stale vectors pruned : {self.vectors_pruned}",
            f"Corpus words         : {self.words:,}",
            f"Chunk tokens         : {self.tokens:,}",
            f"Chunking time        : {self.chunk_seconds:.1f}s",
            f"Embed + upsert time  : {self.embed_upsert_seconds:.1f}s",
        ]
        for name, error in self.failures:
            lines.append(f"  FAILED {name}: {error}")
        return "\n".join(lines)


def discover(root: pathlib.Path | None = None) -> list[pathlib.Path]:
    """Every markdown document in the Market Risk corpus, and nothing else."""
    root = root or MARKET_RISK_KB_DIR
    if not root.is_dir():
        raise FileNotFoundError(f"Market Risk corpus not found at {root}")
    return sorted(p for p in root.rglob("*.md") if p.is_file())


class MarketRiskKnowledgeBase:
    """Ingest and retrieval for the Market Risk reference library."""

    def __init__(self, store: VectorStore | None = None,
                 root: pathlib.Path | None = None,
                 count_tokens: Callable[[str], int] | None = None) -> None:
        self.store = store or make_vector_store(collection=COLLECTION)
        self.root = root or MARKET_RISK_KB_DIR
        self._count = count_tokens
        self._version = corpus_version(self.root)

    @property
    def version(self) -> str:
        """Content identity carried into every derived cache key."""
        return self._version

    @property
    def count_tokens(self) -> Callable[[str], int]:
        if self._count is None:
            self._count = bge_token_counter()
        return self._count

    # -- ingest ---------------------------------------------------------------

    def ingest(self, prune: bool = True,
               progress: Callable[[str], None] | None = None) -> IngestReport:
        """Chunk, embed and upsert every document. Failures are reported, never
        swallowed: one unreadable file must not look like a clean run."""
        report = IngestReport()
        paths = discover(self.root)
        report.documents_discovered = len(paths)

        for path in paths:
            report.documents_processed += 1
            try:
                self._ingest_one(path, report, prune)
                report.documents_succeeded += 1
                if progress:
                    progress(f"  ok   {path.name}")
            except Exception as exc:  # noqa: BLE001 - recorded and re-reported
                report.documents_failed += 1
                report.failures.append((path.name, f"{type(exc).__name__}: {exc}"))
                LOGGER.exception("market-risk ingest failed for %s", path)
                if progress:
                    progress(f"  FAIL {path.name}: {type(exc).__name__}: {exc}")
        if report.documents_failed == 0:
            self._version = corpus_version(self.root)
        return report

    def _ingest_one(self, path: pathlib.Path, report: IngestReport,
                    prune: bool) -> None:
        text = path.read_text(encoding="utf-8")
        report.words += len(text.split())
        doc = read_document_meta(path, text, self.root)

        started = time.perf_counter()
        chunks = chunk_document(text, self.count_tokens)
        report.chunk_seconds += time.perf_counter() - started
        if not chunks:
            raise ValueError("produced no chunks - empty or unparseable document")

        ids, docs, metas = [], [], []
        for index, chunk in enumerate(chunks):
            text = _with_document_title(chunk, doc)
            # Measured on the final string, after the title injection, because
            # that is the string the model will see. An oversized chunk is not
            # an error the embedder reports - it silently drops the tail - so
            # this is the only place it can be caught.
            tokens = self.count_tokens(text)
            if tokens > MODEL_LIMIT:
                raise ValueError(
                    f"chunk {index} ({chunk.section.breadcrumb!r}) is {tokens} "
                    f"tokens, over the model limit of {MODEL_LIMIT}; it would "
                    f"be truncated without warning")
            payload = chunk_payload(chunk, doc, index, len(chunks))
            payload["token_count"] = tokens
            ids.append(chunk_id(doc, chunk, index))
            docs.append(text)
            metas.append(payload)
            report.tokens += tokens
        report.chunks_created += len(chunks)

        started = time.perf_counter()
        for start in range(0, len(ids), BATCH_SIZE):
            stop = start + BATCH_SIZE
            try:
                self.store.upsert(ids[start:stop], docs[start:stop], metas[start:stop])
            except Exception:
                report.vectors_failed += len(ids[start:stop])
                raise
            report.embeddings_generated += len(ids[start:stop])
            report.vectors_upserted += len(ids[start:stop])
        report.embed_upsert_seconds += time.perf_counter() - started

        if prune:
            report.vectors_pruned += self._prune(doc.rel, set(ids))

    def _prune(self, document_path: str, keep: set[str]) -> int:
        """Delete chunks this document no longer produces.

        Upsert alone makes a rerun non-duplicating, not idempotent. Shorten a
        document and its surplus chunks stay in the collection, still matching
        queries, still citing line numbers that have moved. Nobody notices,
        because the only visible symptom is a point count that is a little too
        high.
        """
        stale = [i for i in self.store.ids_where({"document_path": document_path})
                 if i not in keep]
        return self.store.delete(stale) if stale else 0

    # -- retrieval ------------------------------------------------------------

    def retrieve(self, query: str, n_results: int = 6,
                 where: dict | None = None) -> list[dict]:
        """Cosine search, in the shape the rest of the knowledge layer speaks."""
        hits = self.store.query(query, n_results=n_results, where=where)
        return [
            {
                "domain": hit.metadata.get("domain", CORPUS),
                "source": hit.metadata.get("source", ""),
                "heading": hit.metadata.get("heading", ""),
                "text": hit.document,
                "distance": round(hit.distance, 4),
                "score": round(1.0 - hit.distance, 4),
                "collection": COLLECTION,
                "chunk_id": hit.id,
                "document_path": hit.metadata.get("document_path", ""),
                "line_start": hit.metadata.get("line_start"),
                "line_end": hit.metadata.get("line_end"),
                "metadata": hit.metadata,
            }
            for hit in hits
        ]

    def count(self) -> int:
        return self.store.count()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rebuild", action="store_true",
                        help="drop the market_risk_kb collection first "
                             "(never touches quant_knowledge)")
    parser.add_argument("--no-prune", action="store_true",
                        help="keep chunks a document no longer produces")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    kb = MarketRiskKnowledgeBase()
    if args.rebuild:
        print(f"resetting collection {COLLECTION}")
        kb.store.reset()

    before = kb.count()
    print(f"collection {COLLECTION}: {before} points before")
    report = kb.ingest(prune=not args.no_prune,
                       progress=None if args.quiet else print)
    print()
    print(report.render())
    print(f"\ncollection {COLLECTION}: {kb.count()} points after")
    if not report.ok:
        print("\nINGEST FAILED - see failures above")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
