"""Hierarchy-aware markdown chunking with a hard token budget.

The knowledge layer's original chunker splits on headings and stops there
(`knowledge_base._chunk_markdown`). That is right for `knowledge/`, whose
documents are hand-sized: every section fits the embedding model's context.

It is wrong for a reference corpus. `BAAI/bge-small-en-v1.5` truncates at **512
tokens**, silently — the tokenizer is configured with truncation on, so an
oversized section is embedded from its first 512 tokens and the remainder is
never represented at all. Measured on `docs/market-risk-kb/`, heading-only
chunking produces 1,402 chunks of which **99 exceed 512 tokens**, discarding
26,413 tokens (8.2% of the corpus). The worst is a 2,576-token calculation
catalogue section: 66 calculations, of which about 13 would be searchable.

Truncation is the dangerous failure because it is invisible. The collection
reports the right chunk count, retrieval returns plausible neighbours, and the
missing two thirds of a table simply never match anything.

So this chunker keeps the heading hierarchy *and* enforces the budget:

    document
      -> sections (heading path preserved as a breadcrumb prefix)
        -> atoms   (a fenced formula is never separated from its prose;
                    a table is one unit until it cannot be)
          -> chunks (greedily packed to the budget, with overlap)

Three properties are worth stating because they are what make the retrieved
text usable rather than merely small:

* **Every chunk carries its full heading path.** An isolated group of table rows
  reads `# 31 - Master Calculation Catalog / ## B. Interest Rate Sensitivities`
  before its first row, so the embedding knows what the rows are about and a
  human reading the citation knows where it came from.
* **A category's blockquote header is repeated into every chunk of that
  section.** In the calculation catalogue that block states the market data,
  aggregation level and regulatory use for the whole category; a chunk of rows
  without it has lost the half of the meaning that was not in the row.
* **A split table repeats its header row.** `| IR-02 | Modified duration | ... |`
  is unreadable without `| ID | Calculation | Alt names | ... |` above it.

Pure and I/O-free, so it can be unit-tested without a model or a server.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

# --- markdown recognition ----------------------------------------------------

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
TABLE_ROW_RE = re.compile(r"^\s*\|")
TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|\-]+\|\s*$")
QUOTE_RE = re.compile(r"^\s*>")
RULE_RE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")

# Budgets, in tokens of the embedding model's own tokenizer.
#
# 512 is the model's hard ceiling, `MODEL_LIMIT` below, and it includes
# [CLS]/[SEP]. The gap to 460 is not padding for its own sake:
#
#   * a packed chunk is measured as `count(head) + count(body)`, and the
#     tokenizer does not always agree with itself across that join - measured
#     drift on this corpus is up to +12 tokens, because it is full of glyphs
#     that tokenize unevenly next to punctuation (Sigma, subscripts, middot);
#   * the ingest prepends a document title to chunks whose outermost heading is
#     not the document's own (~15 tokens).
#
# Anything that lands over the ceiling is truncated invisibly, so the margin is
# the difference between a guarantee and a hope.
MODEL_LIMIT = 512
MAX_TOKENS = 460
TARGET_TOKENS = 400
OVERLAP_TOKENS = 60


def estimate_tokens(text: str) -> int:
    """Tokenizer-free fallback: ~0.75 words per token on English prose.

    Only used when a real tokenizer is not supplied. Deliberately pessimistic
    (over-counts) so a fallback run produces chunks that are too small rather
    than chunks that are silently truncated.
    """
    return int(len(text.split()) / 0.6) + text.count("|") // 4 + 8


def bge_token_counter() -> Callable[[str], int]:
    """A token counter using the embedding model's own tokenizer.

    Loads an **independent copy** with truncation disabled. Calling
    `no_truncation()` on the embedder's live tokenizer would disable truncation
    for the embedder too, so a long input would reach the ONNX graph at its full
    length and fail on the position-embedding bound rather than being clipped.
    Counting must not change what the thing it is counting for does.
    """
    from fastembed import TextEmbedding  # noqa: PLC0415
    from tokenizers import Tokenizer  # noqa: PLC0415

    from backend.knowledge.vector_store import QdrantVectorStore  # noqa: PLC0415

    source = TextEmbedding(QdrantVectorStore.EMBED_MODEL).model.tokenizer
    counter = Tokenizer.from_str(source.to_str())
    counter.no_truncation()
    counter.no_padding()
    return lambda text: len(counter.encode(text).ids)


# --- the document model ------------------------------------------------------


@dataclass
class Block:
    """One markdown construct: a paragraph, a table, a fence, a blockquote."""

    kind: str  # paragraph | table | fence | quote | rule
    lines: list[str]
    line_start: int  # 1-based, into the source document
    line_end: int

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip("\n")


@dataclass
class Section:
    """A heading and everything under it, up to the next heading of any level."""

    path: list[str]  # heading titles, outermost first
    heading_lines: list[str]  # the literal markdown headings, for the breadcrumb
    level: int
    blocks: list[Block] = field(default_factory=list)
    line_start: int = 1

    @property
    def heading(self) -> str:
        return self.path[-1] if self.path else ""

    @property
    def breadcrumb(self) -> str:
        return " > ".join(self.path)


@dataclass
class Chunk:
    """One embeddable unit."""

    text: str
    section: Section
    index_in_section: int
    line_start: int
    line_end: int
    token_count: int = 0


def parse_blocks(lines: list[str], offset: int = 1) -> list[Block]:
    """Group raw lines into markdown constructs.

    Fences win over everything: a `|` inside a code block is not a table row,
    and a `#` inside one is not a heading. That is why fence state is tracked
    here rather than in the section splitter.
    """
    blocks: list[Block] = []
    buf: list[str] = []
    kind = "paragraph"
    start = offset

    def flush(end: int) -> None:
        nonlocal buf, kind, start
        while buf and not buf[-1].strip():
            buf.pop()
            end -= 1
        if buf:
            blocks.append(Block(kind, list(buf), start, end))
        buf = []

    i = 0
    while i < len(lines):
        line = lines[i]
        lineno = offset + i

        if FENCE_RE.match(line):
            flush(lineno - 1)
            marker = FENCE_RE.match(line).group(1)
            fence = [line]
            i += 1
            while i < len(lines):
                fence.append(lines[i])
                if lines[i].strip().startswith(marker):
                    i += 1
                    break
                i += 1
            blocks.append(Block("fence", fence, lineno, offset + i - 1))
            start = offset + i
            kind = "paragraph"
            continue

        this = ("table" if TABLE_ROW_RE.match(line)
                else "quote" if QUOTE_RE.match(line)
                else "rule" if RULE_RE.match(line)
                else "blank" if not line.strip()
                else "paragraph")

        if this == "blank":
            # A blank line ends a table or a quote; inside prose it only
            # separates paragraphs, which we keep as one packable block.
            if kind in ("table", "quote"):
                flush(lineno - 1)
                kind = "paragraph"
                start = lineno + 1
            elif buf:
                buf.append(line)
            else:
                start = lineno + 1
            i += 1
            continue

        if this == "rule":
            flush(lineno - 1)
            start = lineno + 1
            kind = "paragraph"
            i += 1
            continue

        if this != kind and buf:
            flush(lineno - 1)
            start = lineno
        kind = this
        buf.append(line)
        i += 1

    flush(offset + len(lines) - 1)
    return blocks


def parse_sections(text: str) -> list[Section]:
    """Split a document into sections, carrying the heading path down.

    A heading at level N replaces the path from N onwards, so
    `# 04 / ## 2. Duration / ### 2.1 Macaulay` gives the deepest section a
    three-element path and the ancestors keep their own bodies.
    """
    lines = text.splitlines()
    sections: list[Section] = []
    path: list[str] = []
    heading_lines: list[str] = []
    levels: list[int] = []
    current: Section | None = None
    body: list[str] = []
    body_start = 1
    in_fence = False
    marker = ""

    def close(end: int) -> None:
        nonlocal body, current
        if current is not None:
            current.blocks = parse_blocks(body, body_start)
            sections.append(current)
        body = []

    for i, line in enumerate(lines, start=1):
        if FENCE_RE.match(line):
            fence_mark = FENCE_RE.match(line).group(1)
            if not in_fence:
                in_fence, marker = True, fence_mark
            elif line.strip().startswith(marker):
                in_fence = False

        heading = None if in_fence else HEADING_RE.match(line)
        if heading:
            close(i - 1)
            level = len(heading.group(1))
            title = heading.group(2).strip()
            while levels and levels[-1] >= level:
                levels.pop()
                path.pop()
                heading_lines.pop()
            levels.append(level)
            path.append(title)
            heading_lines.append(line.rstrip())
            current = Section(path=list(path), heading_lines=list(heading_lines),
                              level=level, line_start=i)
            body_start = i + 1
            continue

        if current is None:
            # Preamble before any heading. Rare here (every doc opens with H1)
            # but dropping it would lose real text, so it gets a stub section.
            current = Section(path=["(preamble)"], heading_lines=[], level=0,
                              line_start=i)
            body_start = i
        body.append(line)

    close(len(lines))
    return sections


# --- chunking ----------------------------------------------------------------


def _atomize(blocks: list[Block]) -> list[list[Block]]:
    """Group blocks into units that must not be separated.

    The only rule is about fences, and it is the one Phase 6 asks for: a formula
    is meaningless without the sentence naming its variables, and that sentence
    is meaningless without the formula. So a fence is glued to the block before
    it when there is one, and to the block after it otherwise. In this corpus
    the pattern is heading / fence / `**Variables:** ...`, so the fence attaches
    forwards and the explanation travels with the mathematics.
    """
    atoms: list[list[Block]] = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        if block.kind == "fence":
            if atoms and atoms[-1][-1].kind == "paragraph":
                atoms[-1].append(block)
            elif i + 1 < len(blocks) and blocks[i + 1].kind == "paragraph":
                atoms.append([block, blocks[i + 1]])
                i += 2
                continue
            else:
                atoms.append([block])
        else:
            atoms.append([block])
        i += 1
    return atoms


def _atom_text(atom: list[Block]) -> str:
    return "\n\n".join(b.text for b in atom)


def _split_table(block: Block, budget: int, count: Callable[[str], int],
                 ) -> list[Block]:
    """Split one table into row groups, repeating the header in each.

    A group carries one row of overlap with the previous group, so a reader (or
    an embedding) landing on a boundary sees the row that preceded it.
    """
    lines = [ln for ln in block.lines if ln.strip()]
    if not lines:
        return [block]
    header = lines[:2] if len(lines) > 1 and TABLE_SEP_RE.match(lines[1]) else lines[:1]
    rows = lines[len(header):]
    if not rows:
        return [block]

    header_cost = count("\n".join(header))
    groups: list[Block] = []
    current: list[str] = []
    current_cost = 0
    first_row = 0
    row_offset = block.line_start + len(header)

    def emit(last_index: int) -> None:
        if current:
            groups.append(Block("table", header + list(current),
                                row_offset + first_row, row_offset + last_index))

    for index, row in enumerate(rows):
        cost = count(row)
        if current and header_cost + current_cost + cost > budget:
            emit(index - 1)
            overlap = [current[-1]] if count(current[-1]) < budget // 4 else []
            first_row = index - len(overlap)
            current = overlap
            current_cost = sum(count(r) for r in current)
        current.append(row)
        current_cost += cost
    emit(len(rows) - 1)
    return groups or [block]


def _hard_split(block: Block, budget: int, count: Callable[[str], int]) -> list[Block]:
    """Last resort: split a single oversized block on line boundaries.

    Reached only by a block that is neither a table nor splittable any other
    way — a very long fenced listing, or one enormous paragraph. Never silently
    drops text, which is the whole point of this module.
    """
    out: list[Block] = []
    current: list[str] = []
    cost = 0
    start = block.line_start
    for offset, line in enumerate(block.lines):
        line_cost = count(line)
        if current and cost + line_cost > budget:
            out.append(Block(block.kind, list(current), start,
                             block.line_start + offset - 1))
            current, cost = [], 0
            start = block.line_start + offset
        current.append(line)
        cost += line_cost
    if current:
        out.append(Block(block.kind, current, start, block.line_end))
    return out or [block]


def chunk_section(section: Section, count: Callable[[str], int],
                  max_tokens: int = MAX_TOKENS,
                  target_tokens: int = TARGET_TOKENS,
                  overlap_tokens: int = OVERLAP_TOKENS) -> list[Chunk]:
    """Turn one section into chunks that all fit the budget."""
    prefix = "\n".join(section.heading_lines)
    blocks = list(section.blocks)

    # Leading blockquotes are the section's own context header. In the
    # calculation catalogue they carry the category's market data, aggregation
    # level and regulatory use - true of every row, so repeated into every chunk.
    sticky: list[Block] = []
    while blocks and blocks[0].kind == "quote":
        sticky.append(blocks.pop(0))

    head = prefix + ("\n\n" + "\n\n".join(b.text for b in sticky) if sticky else "")
    head_cost = count(head)
    if not blocks:
        # A heading with no body of its own - a parent whose content is entirely
        # in its subsections. Emitting it would store a chunk that is only a
        # breadcrumb: it can be retrieved, it can outrank a real answer on a
        # title-shaped query, and it carries nothing a reader could use. The
        # heading is not lost, because it is the breadcrumb of every child.
        if not sticky:
            return []
        return [Chunk(head, section, 0, section.line_start,
                      sticky[-1].line_end, head_cost)]

    body_budget = max(max_tokens - head_cost, max_tokens // 4)

    whole = head + "\n\n" + "\n\n".join(b.text for b in blocks)
    whole_cost = count(whole)
    if whole_cost <= max_tokens:
        return [Chunk(whole, section, 0, section.line_start,
                      blocks[-1].line_end, whole_cost)]

    # Oversized: break anything that alone exceeds the budget, then pack.
    expanded: list[Block] = []
    for block in blocks:
        if count(block.text) <= body_budget:
            expanded.append(block)
        elif block.kind == "table":
            expanded.extend(_split_table(block, body_budget, count))
        else:
            expanded.extend(_hard_split(block, body_budget, count))

    atoms = _atomize(expanded)
    packed: list[list[list[Block]]] = []
    current: list[list[Block]] = []
    cost = 0
    soft = max(min(target_tokens - head_cost, body_budget), body_budget // 2)

    for atom in atoms:
        atom_cost = count(_atom_text(atom))
        if current and cost + atom_cost > soft and cost + atom_cost > body_budget:
            packed.append(current)
            tail = current[-1]
            tail_cost = count(_atom_text(tail))
            # Prose overlap only: repeating a table group would duplicate rows
            # that already carry their header, inflating the collection for no
            # retrieval gain.
            carry = ([tail] if tail_cost <= overlap_tokens
                     and all(b.kind == "paragraph" for b in tail) else [])
            current = list(carry)
            cost = sum(count(_atom_text(a)) for a in current)
        current.append(atom)
        cost += atom_cost
    if current:
        packed.append(current)

    chunks: list[Chunk] = []
    for index, group in enumerate(packed):
        flat = [b for atom in group for b in atom]
        body = "\n\n".join(b.text for b in flat)
        text = head + "\n\n" + body
        chunks.append(Chunk(text, section, index,
                            min(b.line_start for b in flat),
                            max(b.line_end for b in flat), count(text)))
    return chunks


def chunk_document(text: str, count: Callable[[str], int] | None = None,
                   max_tokens: int = MAX_TOKENS,
                   target_tokens: int = TARGET_TOKENS,
                   overlap_tokens: int = OVERLAP_TOKENS) -> list[Chunk]:
    """Chunk a whole markdown document, hierarchy first, budget enforced."""
    counter = count or estimate_tokens
    chunks: list[Chunk] = []
    for section in parse_sections(text):
        chunks.extend(chunk_section(section, counter, max_tokens,
                                    target_tokens, overlap_tokens))
    return [c for c in chunks if c.text.strip()]
