"""Agent 2 — the domain expert. Decides what a task needs, using Qdrant as its brain.

Runs on a **high-capability model**, because this is where the thinking is. It
is the only agent that reads the knowledge base, and the only one allowed to say
what a calculation requires.

**It holds no thresholds of its own.** Every number it states must be quoted from
a chunk it actually retrieved, and the quote is checked against the retrieved
text before the requirement is accepted. A window recalled from training is
rejected exactly like a constant hardcoded in the source — both are
unfalsifiable. You cannot change them by editing a document and you cannot audit
them by reading one.

    question ─► Qdrant vector search ─► model reads ONLY those chunks
                                         │
                                         ├─ what is being asked?
                                         ├─ which fields does the method read?
                                         └─ how many rows, quoting what sentence?
                                         │
                                  verify the quote is in the context
                                         │
                                    Requirement (+ citations)

When the corpus is silent, `rows` is None and `grounded` is False, and the
caller is told the corpus does not state a window rather than handed a plausible
default. Adding the sentence to a knowledge document fixes it — no code change,
no release. **The knowledge base is the authority, and a domain expert can edit
it without an engineer.**

The agent also *revises*: after the MCP agent reports what it can actually serve,
this agent reconsiders and issues a final requirement. That exchange is the
discussion, and it exists because neither side knows enough alone — the expert
knows what the method needs, the MCP agent knows what the source holds.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agents.contracts import FieldNote, KnowledgeChunk, Requirement, ToolCatalogue
from llm import CallSite

from agents.observability import structured_call, traced

LOGGER = logging.getLogger("agents.domain_expert")

# High-capability model: this is the reasoning seat of the system.
CALL_SITE = CallSite.DOMAIN_EXPERT

# Columns that accompany any rate regardless of task. A correctness rule, not a
# threshold: a rate without its quoting basis cannot be safely combined.
INVARIANT_FIELDS = ("observation_date", "rate_percent", "quote_basis")

DERIVE_SYSTEM = """\
You are a market-risk domain expert deciding what data a task requires.

You are given retrieved excerpts from a quant knowledge base, and a catalogue of \
what the data layer can actually provide. The excerpts are your ONLY source of \
authority for numbers. You have deep domain knowledge, but you must not use it \
to supply figures: any number you state must appear in the excerpts.

Decide:
1. Is the task answerable from interest-rate curve data? If it needs portfolio \
positions, counterparty data, or instrument-level identifiers that a Treasury par \
yield curve does not contain, set answerable=false and say what is missing.
2. Which fields does the calculation actually read? Only fields in the catalogue.
3. How many observations does the method consume?
4. Does it need a calculation from the data layer's tools? If so name the tool \
exactly as it appears in the catalogue, else null.
5. Which tenors are relevant (e.g. y2 and y10 for a 2s10s slope)?

Rules you must not break:
- `row_quote` must be copied VERBATIM from the excerpts - the exact sentence \
stating the window or observation count. Do not paraphrase.
- If the excerpts do not state a window, set `rows` to null and `row_quote` to \
null, and say in `row_reason` that the corpus is silent. Do NOT supply a number \
from your own knowledge; an untraceable number is worse than an admitted gap.
- If the excerpts give a range (e.g. "250-500 trading days"), take the LOWER \
bound and quote the sentence containing it.
- Fields the user asked for that are not in the catalogue are "unavailable". \
Never substitute anything for them.
- Fields that exist but the calculation does not read are "not_needed".
"""

REVISE_SYSTEM = """\
You are the same domain expert, revising your requirement after the data layer \
told you what it can actually serve.

You proposed a requirement. The MCP agent responded with what is feasible. \
Produce the FINAL requirement.

- Drop or replace anything it said it cannot serve, and record why in the field \
notes.
- If it offers fewer rows than the method needs, keep the methodology figure and \
record a warning: a short window computes a different number, it does not \
approximate the right one. Do not silently accept a smaller window as correct.
- Do not invent new numbers. Your `row_quote` must still be verbatim from the \
knowledge excerpts you were given.
- If the exchange shows the task cannot be served at all, set answerable=false \
and explain plainly.
"""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "task_understood": {"type": "string"},
        "answerable": {"type": "boolean"},
        "unanswerable_reason": {"type": ["string", "null"]},
        "fields": {"type": "array", "items": {"type": "string"}},
        "field_notes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "verdict": {"type": "string",
                                "enum": ["required", "not_needed", "unavailable"]},
                    "reason": {"type": "string"},
                },
                "required": ["name", "verdict", "reason"],
                "additionalProperties": False,
            },
        },
        "rows": {"type": ["integer", "null"]},
        "row_quote": {"type": ["string", "null"],
                      "description": "VERBATIM sentence from the excerpts."},
        "row_reason": {"type": "string"},
        "tenors": {"type": "array", "items": {"type": "string"}},
        "calculation": {"type": ["string", "null"],
                        "description": "Tool name from the catalogue, or null."},
    },
    "required": ["task_understood", "answerable", "unanswerable_reason", "fields",
                 "field_notes", "rows", "row_quote", "row_reason", "tenors",
                 "calculation"],
    "additionalProperties": False,
}


def _normalise(text: str) -> str:
    """Collapse whitespace and unify punctuation so a fair quote still matches.

    Chunks wrap mid-sentence and models re-emit en dashes as hyphens; neither is
    a paraphrase. Failing an honest quote on typography would push the agent
    toward inventing numbers instead of citing them.

    **Markdown emphasis is typography too.** The corpus is markdown, and the
    sentence the agent must cite is written

        Historical simulation reads a fixed lookback window of
        **250 trading days** of daily observations.

    A model that reproduces the asterisks matched; one that quoted the same
    sentence as plain prose did not, and had its correct citation discarded as
    ungrounded. That is the guard failing on formatting rather than substance -
    and it fails *toward* the outcome this whole design exists to prevent, since
    an agent whose honest quotes keep getting rejected has no way left to
    justify a number.

    Stripping the markers from **both** sides keeps the check exactly as strict:
    a paraphrase still does not appear in the source, emphasised or not.
    """
    text = (text or "").replace("–", "-").replace("—", "-")
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_is_grounded(quote: str | None, context: str) -> bool:
    """Is the cited sentence really in what the model was given?

    The guard that makes "no hardcoding" checkable rather than promised. A model
    recalling "250 trading days" from training produces a quote absent from the
    context, and the requirement is marked ungrounded.
    """
    if not quote:
        return False
    needle = _normalise(quote)
    if len(needle) < 12:      # too short to be evidence of anything
        return False
    return needle in _normalise(context)


class DomainExpertAgent:
    """Reads the corpus, decides the requirement, and defends it in discussion."""

    def __init__(self, knowledge, n_results: int = 6) -> None:
        self.kb = knowledge
        self.call_site = CALL_SITE
        self.n_results = n_results

    # -- knowledge -----------------------------------------------------------

    @traced("knowledge_retrieval", run_type="retriever")
    def retrieve(self, subject: str) -> list[KnowledgeChunk]:
        """Vector search over Qdrant. The agent's only source of authority.

        Two queries, not one, because the agent needs two different things and a
        single embedding cannot be near both. Asked "I need data for a 97.5%
        expected shortfall calculation", one query returns the ES *definition* -
        semantically the closest chunk - and never surfaces the section stating
        the observation window, so the row count comes back ungrounded even
        though the corpus contains it.

        So: one query for what the task means, one for the window it reads. The
        second is phrased in the corpus's own vocabulary rather than the user's,
        which is the point - the agent knows what it is looking for even when
        the user does not.
        """
        queries = [
            subject,
            f"{subject} observation window how many rows lookback observations read",
        ]
        merged: dict[tuple[str, str], KnowledgeChunk] = {}
        for query in queries:
            try:
                hits = self.kb.retrieve(query, n_results=self.n_results)
            except Exception as exc:  # noqa: BLE001 - reported, never fatal
                LOGGER.warning("knowledge retrieval failed for %r: %s", query, exc)
                continue
            for hit in hits:
                key = (hit.get("source", ""), hit.get("heading", ""))
                chunk = KnowledgeChunk(
                    domain=hit.get("domain", ""), source=hit.get("source", ""),
                    heading=hit.get("heading", ""), text=hit.get("text", ""),
                    distance=hit.get("distance", 0.0))
                # Keep the better-scoring sighting when both queries find it.
                if key not in merged or chunk.distance < merged[key].distance:
                    merged[key] = chunk
        return sorted(merged.values(), key=lambda c: c.distance)

    @staticmethod
    def _context(chunks: list[KnowledgeChunk]) -> str:
        return "\n\n".join(f"[{c.label}]\n{c.text}" for c in chunks)

    # -- the requirement -----------------------------------------------------

    @traced("domain_expert.derive", run_type="llm")
    def derive(self, question: str, task: str, catalogue: ToolCatalogue,
               requested_fields: list[str] | None,
               requested_rows: int | None) -> tuple[Requirement, list[KnowledgeChunk]]:
        """First proposal: what the corpus says this task needs."""
        chunks = self.retrieve(task or question)
        if not chunks:
            return self._blocked(task or question,
                                 "The knowledge base returned nothing for this task, "
                                 "so no requirement could be grounded."), []

        prompt = self._prompt(question, task, catalogue, requested_fields,
                              requested_rows, self._context(chunks))
        payload = structured_call(call_site=CALL_SITE, system=DERIVE_SYSTEM,
                                  prompt=prompt, schema=SCHEMA, max_tokens=6000)
        if payload is None:
            return self._blocked(task or question,
                                 "The domain expert could not produce a structured "
                                 "requirement."), chunks
        return self._build(payload, chunks, catalogue, requested_rows), chunks

    @traced("domain_expert.revise", run_type="llm")
    def revise(self, question: str, task: str, catalogue: ToolCatalogue,
               proposal: Requirement, response, chunks: list[KnowledgeChunk],
               requested_rows: int | None) -> Requirement:
        """Final requirement, after the data layer said what it can serve."""
        prompt = (
            f"User question:\n{question}\n\nTask:\n{task}\n\n"
            f"Your previous requirement:\n{proposal.as_dict()}\n\n"
            f"What the data layer said it can serve:\n{response.as_dict()}\n\n"
            f"Data layer catalogue:\n{catalogue.as_dict()}\n\n"
            f"Knowledge excerpts (your ONLY source for numbers):\n"
            f"{self._context(chunks)}"
        )
        payload = structured_call(call_site=CALL_SITE, system=REVISE_SYSTEM,
                                  prompt=prompt, schema=SCHEMA, max_tokens=6000)
        if payload is None:
            # Revision failed: keep the grounded proposal rather than degrading
            # to something nobody checked.
            proposal.warnings.append(
                "The domain expert could not revise after the data layer's "
                "response; the original requirement stands.")
            return proposal
        return self._build(payload, chunks, catalogue, requested_rows)

    # -- assembly ------------------------------------------------------------

    @staticmethod
    def _prompt(question: str, task: str, catalogue: ToolCatalogue,
                requested_fields: list[str] | None, requested_rows: int | None,
                context: str) -> str:
        return (
            f"User question:\n{question}\n\n"
            f"Task the data is for:\n{task}\n\n"
            f"Fields the user named: {requested_fields or 'none'}\n"
            f"Rows the user named: {requested_rows or 'none'}\n\n"
            f"What the data layer can provide:\n{catalogue.as_dict()}\n\n"
            f"Retrieved knowledge (your ONLY source for any number):\n{context}"
        )

    def _build(self, payload: dict[str, Any], chunks: list[KnowledgeChunk],
               catalogue: ToolCatalogue, requested_rows: int | None) -> Requirement:
        context = self._context(chunks)
        quote = payload.get("row_quote")
        rows = payload.get("rows")
        grounded = quote_is_grounded(quote, context)
        warnings: list[str] = []

        if rows is not None and not grounded:
            LOGGER.warning("ungrounded row count %r discarded", rows)
            warnings.append(
                f"The expert proposed {rows} rows but its citation is not in the "
                "retrieved knowledge, so the figure was discarded. Add the window "
                "to a knowledge document and it will be used immediately.")
            rows, quote = None, None
        elif rows is None:
            warnings.append(
                "The knowledge base states no observation window for this task. "
                "Add one to the relevant document - no code change is needed.")

        if requested_rows and rows and requested_rows != rows:
            warnings.append(
                f"Requested {requested_rows:,} rows; the method consumes {rows:,}."
                if requested_rows > rows else
                f"Requested {requested_rows:,} rows, fewer than the {rows:,} this "
                "method consumes. A short window computes a different number "
                "rather than approximating it.")

        notes = [FieldNote(n.get("name", ""), n.get("verdict", "required"),  # type: ignore[arg-type]
                           n.get("reason", ""))
                 for n in payload.get("field_notes") or []]

        available = set(catalogue.fields)
        fields = [f for f in payload.get("fields") or [] if f in available]
        for invariant in INVARIANT_FIELDS:
            if invariant in available and invariant not in fields:
                fields.append(invariant)
                notes.append(FieldNote(
                    invariant, "required",
                    "Carried with every rate so observations cannot be mis-combined."))

        calculation = payload.get("calculation")
        if calculation and calculation not in {t.name for t in catalogue.tools}:
            warnings.append(
                f"The expert asked for a calculation the data layer does not "
                f"offer ({calculation}); it was dropped.")
            calculation = None

        return Requirement(
            task=payload.get("task_understood", ""),
            answerable=bool(payload.get("answerable", True)),
            fields=fields, field_notes=notes,
            rows=rows, row_reason=payload.get("row_reason", ""), row_quote=quote,
            grounded=grounded,
            tenors=[t for t in payload.get("tenors") or [] if t in catalogue.tenors],
            calculation=calculation,
            unanswerable_reason=payload.get("unanswerable_reason"),
            citations=[c.as_dict() for c in chunks],
            warnings=warnings,
        )

    @staticmethod
    def _blocked(task: str, reason: str) -> Requirement:
        return Requirement(task=task, answerable=False, unanswerable_reason=reason,
                           row_reason=reason, warnings=[reason])
