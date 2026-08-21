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

from agents.contracts import (
    FieldNote,
    KnowledgeChunk,
    Requirement,
    ResultValidation,
    TemporalScope,
    ToolCatalogue,
)
from llm import CallSite

from agents.observability import (
    TERMINAL_FAILURES,
    last_failure_kind,
    structured_call,
    traced,
)

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
0. THIS IS A HYPOTHESIS, NOT A COMMAND. You are opening a conversation with \
the data layer, which knows things you cannot: which inputs it actually holds, \
and - most usefully - which of your theoretical inputs its tools already \
abstract away. So state what the METHOD asks for in `candidate_fields`, \
including inputs you suspect may be unavailable. Do NOT pre-emptively delete \
them; naming them is how the data layer gets to answer with evidence. Put what \
you genuinely do not know in `open_questions`, and leave `decision` null: you \
have not decided anything yet.
1. Is the task answerable from interest-rate curve data? Answer this about the \
TASK, not about the fields. A field you cannot supply is marked "unavailable" \
and the task continues without it; only the metric itself can make a task \
unanswerable. Set answerable=false only when the thing being asked for cannot \
be produced from interest-rate data at all - CVA, EE/EPE/PFE, RWA, PD/LGD/EAD, \
counterparty exposure - or when nothing servable is left once the unavailable \
fields are removed.
   Worked example, because this is the rule most often got wrong: "give me \
observation_date, rate_percent, quote_basis, cusip, issuer_name and \
settlement_date so I can compute 10-day 99% VaR" is ANSWERABLE. Three of those \
fields exist and the VaR is computable; cusip, issuer_name and settlement_date \
are marked "unavailable" and nothing is substituted for them. Declining the \
whole request would throw away data the user asked for and can have.
   Second worked example, and the other way this rule gets got wrong: "show me \
the 30-year rate history" is ANSWERABLE with `calculation: null`. RETRIEVAL IS \
NOT A TOOL YOU SCHEDULE. Every plan returns the rows its `fields` and `tenors` \
describe; `available_calculations` lists the optional ANALYSES that can be run \
on top of those rows, and a retrieval entry being absent from it means only \
that it is not an analysis. It does NOT mean the data is unreachable, and it \
is never a reason to decline. A task that only needs data is the normal case.
2. Which fields does the calculation actually read? Only fields in the catalogue.
3. How many observations does the method consume?
4. Does it need a calculation from the data layer's tools? If so name one of \
`available_calculations` exactly, else null - and state the parameters \
it reads in `calculation_params`. `confidence_level` as a fraction (0.99 for \
99%) and `horizon_days` as a whole number of days. Take them from the user \
when they say them ("10-day 99% VaR" -> horizon_days 10, confidence_level \
0.99); otherwise from the excerpts; otherwise null, and the data layer's own \
default stands. Never state a parameter the user did not ask for and the \
corpus does not give.
5. Which tenors are relevant (e.g. y2 and y10 for a 2s10s slope)?
6. WHEN is the question about? Fill `temporal` only from what the user or the \
excerpts actually say. `as_of_date` for a single named day ("the curve on \
2008-09-15"), `start_date`/`end_date` for a named period ("during 2020", \
"between March and June 2009"), `lookback_days` for a methodology window \
("250 trading days"). Leave every field null when the user means the latest \
data. Never invent a date, and never convert "in 2008" into a row count - a \
row count is not a date, and answering a question about 2008 with recent data \
is the exact failure this field exists to prevent.
7. Which curve family: "nominal" (the standard Treasury par yield curve), \
"real" (the TIPS-derived curve), or "ambiguous". Choose "nominal" unless the \
user says real, TIPS, or inflation-linked. Choose "ambiguous" ONLY when the \
user names a maturity with no indication of which curve they mean and both \
curves publish it - "the 30 year", "10 year history". A nominal par yield and \
a real yield are different quantities and must never share a curve, so asking \
is better than guessing.

Rules you must not break:
- `row_quote` must be copied VERBATIM from the excerpts - the exact sentence \
stating the window or observation count. Do not paraphrase.
- If the excerpts do not state a window, set `rows` to null and `row_quote` to \
null, and say in `row_reason` that the corpus is silent. Do NOT supply a number \
from your own knowledge; an untraceable number is worse than an admitted gap.
- If the excerpts give a range (e.g. "250-500 trading days"), take the LOWER \
bound and quote the sentence containing it.
- Fields the user asked for that are not in the catalogue are "unavailable". \
Never substitute anything for them, and never let one make the whole task \
unanswerable - record it and carry on with what remains.
- Fields that exist but the calculation does not read are "not_needed".
"""

REVISE_SYSTEM = """\
You are the same domain expert. You opened with a hypothesis; the data layer \
has answered with EVIDENCE about what actually exists. Reassess.

This is the turn where collaboration either happens or does not. Read the \
assessment properly and let it change your mind where it should:

- `unnecessary_fields` is the most valuable thing you have been told. Those are \
inputs your method names in theory but this tool's implementation does not \
read. Drop them and say so - you could not have known this from the corpus.
- `unsupported_fields` are genuinely absent. Record each as "unavailable" and \
continue without it. Do not substitute anything.
- `available_tools` and `constraints` may mean a different, better method. If \
the data layer offers something your hypothesis did not consider, take it.
- `temporal_constraints` may mean the period you asked for is partly or wholly \
outside coverage. If so, say what you can actually answer.
- If the assessment answered your `open_questions`, remove them. If it raised \
new ones you cannot resolve, keep them and do NOT decide yet.

Then set `decision`:
- "AGREED" - the plan is executable and analytically acceptable. Set \
`is_hypothesis` false.
- "NEEDS_USER_INPUT" - a choice only the user can make is still missing.
- "UNSUPPORTED" - the objective cannot be produced from this data at all.
- "CANNOT_REACH_AGREEMENT" - you and the data layer cannot construct an \
acceptable plan.
- null - you still have unresolved questions and want another exchange.

Do not agree merely to finish. A plan you would not defend is worse than an \
admitted disagreement.

- Drop or replace anything it said it cannot serve, and record why in the field \
notes.
- If it offers fewer rows than the method needs, keep the methodology figure and \
record a warning: a short window computes a different number, it does not \
approximate the right one. Do not silently accept a smaller window as correct.
- Do not invent new numbers. Your `row_quote` must still be verbatim from the \
knowledge excerpts you were given.
- If the exchange shows the task cannot be served at all, set answerable=false \
and explain plainly. "At all" is the test: fields the data layer cannot serve \
are dropped and recorded, not grounds for refusing the whole request.
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
        "curve_family": {"type": "string",
                         "enum": ["nominal", "real", "ambiguous"],
                         "description": "nominal | real | ambiguous. See rule 7."},
        "candidate_fields": {
            "type": "array", "items": {"type": "string"},
            "description": "What the METHOD asks for, before anything is "
                           "dropped. Include inputs you suspect are missing."},
        "open_questions": {
            "type": "array", "items": {"type": "string"},
            "description": "What you need the data layer to tell you. Real, "
                           "answerable questions. Empty once you have decided."},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
        # A nullable enum, expressed without a union `type`. Pairing
        # `"type": ["string", "null"]` with an enum is valid JSON Schema and
        # Z.AI accepts it, but Anthropic rejects the request outright:
        #   Invalid schema: Enum value 'AGREED' does not match declared type
        #   '['string', 'null']'
        # so the schema was portable only by accident, and the provider seam
        # only looked swappable until something crossed it. `enum` alone with
        # `null` among the members says the same thing and both accept it.
        "decision": {
            "enum": ["AGREED", "NEEDS_USER_INPUT", "UNSUPPORTED",
                     "CANNOT_REACH_AGREEMENT", None],
            "description": "Null on the opening hypothesis. On a revision, "
                           "commit only when you are genuinely finished."},
        "temporal": {
            "type": "object",
            "properties": {
                "as_of_date": {"type": ["string", "null"]},
                "start_date": {"type": ["string", "null"]},
                "end_date": {"type": ["string", "null"]},
                "lookback_days": {"type": ["integer", "null"]},
            },
            "required": ["as_of_date", "start_date", "end_date", "lookback_days"],
            "additionalProperties": False,
        },
        "calculation_params": {
            "type": "object",
            "properties": {
                "confidence_level": {"type": ["number", "null"],
                                     "description": "0.99 for 99%. Null if unstated."},
                "horizon_days": {"type": ["integer", "null"],
                                 "description": "Whole days. Null if unstated."},
            },
            "required": ["confidence_level", "horizon_days"],
            "additionalProperties": False,
        },
    },
    # Only what `_build` genuinely cannot default. Eighteen required properties
    # was a contract no model reliably met: GLM-5.2 returned an object missing
    # `unanswerable_reason` — a field with no meaningful value when the task
    # *is* answerable — failed validation, and then produced no call at all on
    # the corrective retry. Two and a half minutes, then a false refusal.
    #
    # Everything omitted here has a defined, honest default in `_build`: absent
    # `rows` is the corpus being silent, absent `decision` is not having
    # committed. Strictness in the schema does not add rigour when the
    # rebuilder is already total; it only adds ways to fail.
    # `calculation` earns its place here even though `_build` can default it,
    # because the default is not neutral. Left optional, glm-5.2 emitted
    # `calculation_params: {horizon_days: 10, confidence_level: 0.99}` and no
    # `calculation` at all — a plan stating how to compute while naming nothing
    # to compute, which silently turned "compute 10-day 99% VaR" into a plain
    # table. Four required properties is nothing like the eighteen that broke
    # the contract, and this one closes a hole the rebuilder cannot.
    "required": ["task_understood", "answerable", "fields", "calculation"],
    "additionalProperties": False,
}

#: A revision has one extra obligation the opening hypothesis does not: say
#: whether you have committed. Left optional, a model that simply omits it
#: reads as "still thinking", and the negotiation burns all five rounds
#: discovering that. On the opening move the field must be null anyway, so
#: requiring it there would be asking for a constant.
REVISE_SCHEMA: dict[str, Any] = {
    **SCHEMA,
    "required": [*SCHEMA["required"], "decision"],
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


def _strings(value: Any) -> list[str]:
    return [str(v) for v in (value or []) if v is not None and str(v).strip()]


def _comparable(value: Any) -> Any:
    """Compare 10 with 10.0 and "10" as equal; leave everything else alone."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 9)
    try:
        return round(float(str(value)), 9)
    except (TypeError, ValueError):
        return str(value).strip().lower()


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
               requested_rows: int | None,
               prior_plan: dict[str, Any] | None = None,
               revalidation_reason: str = ""
               ) -> tuple[Requirement, list[KnowledgeChunk]]:
        """The opening analytical hypothesis, not a command.

        `prior_plan` and `revalidation_reason` are set when the user has said
        something that materially changes the analysis — "make that real rates",
        "use a 10-day horizon". The expert then reconsiders against what was
        already agreed rather than starting from nothing, which is both cheaper
        and less likely to quietly drop a constraint that still applies.
        """
        chunks = self.retrieve(task or question)
        if not chunks:
            return self._blocked(task or question,
                                 "The knowledge base returned nothing for this task, "
                                 "so no requirement could be grounded."), []

        prompt = self._prompt(question, task, catalogue, requested_fields,
                              requested_rows, self._context(chunks))
        if prior_plan:
            prompt += (
                f"\n\nYou already agreed this plan earlier in the conversation:\n"
                f"{prior_plan}\n\nThe user has since said something that changes "
                f"the analysis: {revalidation_reason or 'see the question above'}.\n"
                "Reconsider the plan in that light. Keep what still holds, change "
                "what the new information affects, and say which is which.")
        payload = structured_call(call_site=CALL_SITE, system=DERIVE_SYSTEM,
                                  prompt=prompt, schema=SCHEMA, max_tokens=6000)
        if payload is None:
            # The reasoning step failed. That is emphatically *not* the same
            # fact as "the data cannot support this question", and reporting it
            # as one tells the user something false about their data. Flagged
            # so the pipeline can say which of the two actually happened.
            kind = last_failure_kind()
            return self._blocked(
                task or question,
                f"The domain expert could not produce a structured requirement "
                f"({kind or 'no reason reported'}).",
                blocked_by=("account" if kind in TERMINAL_FAILURES
                            else "model")), chunks
        hypothesis = self._build(payload, chunks, catalogue, requested_rows,
                                 requested_fields, opening=True)
        return hypothesis, chunks

    @traced("domain_expert.revise", run_type="llm")
    def revise(self, question: str, task: str, catalogue: ToolCatalogue,
               proposal: Requirement, response, chunks: list[KnowledgeChunk],
               requested_rows: int | None,
               requested_fields: list[str] | None = None) -> Requirement:
        """Final requirement, after the data layer said what it can serve."""
        prompt = (
            f"User question:\n{question}\n\nTask:\n{task}\n\n"
            f"YOUR HYPOTHESIS (or last revision):\n{proposal.as_dict()}\n\n"
            f"THE DATA LAYER'S CAPABILITY EVIDENCE:\n{response.as_dict()}\n\n"
            f"Read `unnecessary_fields` first - those are inputs this tool does "
            f"not read, which you had no way of knowing.\n\n"
            f"Data layer catalogue:\n{catalogue.as_dict()}\n\n"
            f"Knowledge excerpts (your ONLY source for numbers):\n"
            f"{self._context(chunks)}"
        )
        payload = structured_call(call_site=CALL_SITE, system=REVISE_SYSTEM,
                                  prompt=prompt, schema=REVISE_SCHEMA,
                                  max_tokens=6000)
        if payload is None:
            # Revision failed: keep the grounded proposal rather than degrading
            # to something nobody checked.
            proposal.warnings.append(
                "The domain expert could not revise after the data layer's "
                "response; the original requirement stands.")
            return proposal
        revised = self._build(payload, chunks, catalogue, requested_rows,
                              requested_fields)
        return self._keep_ambiguity(proposal, revised)

    @staticmethod
    def _keep_ambiguity(proposal: Requirement, revised: Requirement) -> Requirement:
        """An ambiguity the expert raised is not the expert's to withdraw.

        "What is the 30 year?" was correctly opened as `ambiguous` — both curves
        publish that maturity — and then quietly revised to `nominal` on the
        next round, so the user was served a nominal par yield having never been
        asked which they meant. The transcript recorded it as
        `curve family ambiguous -> nominal`, which reads like a resolution and
        was a guess.

        The revision loop cannot settle this, and the reason is not that the
        model is careless: the question is *which quantity the user meant*, and
        a capability assessment answers what the source holds. No amount of
        evidence about the data can produce the missing fact, so the only honest
        moves are to keep asking or to be told.

        Whether there is anything to ask about is a separate question, and the
        MCP agent already answers it: a maturity only one curve publishes is
        resolved without a round trip. So this restores the ambiguity
        unconditionally and lets that check decide.
        """
        if proposal.curve_family == "ambiguous" != revised.curve_family:
            LOGGER.info("restored ambiguous curve family (expert proposed %r)",
                        revised.curve_family)
            revised.curve_family = "ambiguous"
            revised.warnings.append(
                "The curve family stayed ambiguous: a nominal par yield and a "
                "real yield are different quantities, and only the user can say "
                "which was meant.")
        return revised

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
               catalogue: ToolCatalogue, requested_rows: int | None,
               requested_fields: list[str] | None = None,
               opening: bool = False) -> Requirement:
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
        candidates = _strings(payload.get("candidate_fields")) or list(
            payload.get("fields") or [])
        # On the opening hypothesis the *stated* inputs survive intact, missing
        # ones included. Filtering them here is what used to hand the data layer
        # a pre-approved plan with nothing left to assess. From the revision
        # onward the expert has seen the evidence, so its choices are honoured
        # but still bounded by what exists.
        fields = ([f for f in candidates if f in available] if opening
                  else [f for f in payload.get("fields") or [] if f in available])
        for invariant in INVARIANT_FIELDS:
            if invariant in available and invariant not in fields:
                fields.append(invariant)
                notes.append(FieldNote(
                    invariant, "required",
                    "Carried with every rate so observations cannot be mis-combined."))

        calculation = payload.get("calculation")
        if calculation and calculation not in set(catalogue.executable_tools):
            # Dropped, never fatal: naming a retrieval capability here is a
            # category error, not a failed request. The rows still come back,
            # which is why this is a warning and the plan carries on.
            warnings.append(
                (f"`{calculation}` describes what a fetch returns rather than "
                 f"an analysis to run on it; the rows it covers are returned "
                 f"anyway."
                 if calculation in set(catalogue.retrieval_tools) else
                 f"`{calculation}` is not something the data layer can "
                 f"execute; it was dropped.")
                + f" Available calculations: "
                  f"{', '.join(catalogue.executable_tools) or 'none'}.")
            calculation = None

        params = self._calculation_params(payload.get("calculation_params"),
                                          warnings)
        if params and not calculation:
            # Settings for a calculation that was never named. Not fatal — the
            # rows are still real — but it is the signature of a plan that lost
            # its own objective, and it must not pass as an ordinary retrieval.
            warnings.append(
                f"The plan carries calculation settings "
                f"({', '.join(sorted(params))}) but names no calculation to "
                f"apply them to, so nothing was computed.")

        family = payload.get("curve_family")
        if family not in {"nominal", "real", "ambiguous"}:
            # Missing or unreadable. Nominal is the standard Treasury par curve
            # and the behaviour every earlier version of this system had, so
            # falling back to it costs nothing new.
            family = "nominal"

        answerable, unanswerable_reason, override = self._resolve_answerability(
            bool(payload.get("answerable", True)),
            payload.get("unanswerable_reason"),
            calculation, requested_fields, catalogue, notes)
        if override:
            warnings.append(override)

        decision = payload.get("decision")
        if decision not in {"AGREED", "NEEDS_USER_INPUT", "UNSUPPORTED",
                            "CANNOT_REACH_AGREEMENT"}:
            decision = None
        if opening:
            # An opening move is never a decision, whatever the model says.
            decision = None

        return Requirement(
            task=payload.get("task_understood", ""),
            answerable=answerable,
            temporal=TemporalScope.from_dict(payload.get("temporal")),
            is_hypothesis=opening or decision is None,
            candidate_fields=candidates,
            open_questions=(_strings(payload.get("open_questions"))
                            if decision is None else []),
            assumptions=_strings(payload.get("assumptions")),
            limitations=_strings(payload.get("limitations")),
            decision=decision,
            fields=fields, field_notes=notes,
            rows=rows, row_reason=payload.get("row_reason", ""), row_quote=quote,
            grounded=grounded,
            tenors=[t for t in payload.get("tenors") or [] if t in catalogue.tenors],
            calculation=calculation,
            calculation_params=params,
            curve_family=family,
            unanswerable_reason=unanswerable_reason,
            citations=[c.as_dict() for c in chunks],
            warnings=warnings,
        )

    @staticmethod
    def _calculation_params(raw: Any, warnings: list[str]) -> dict[str, Any]:
        """The stated parameters, range-checked, with nothing invented.

        A parameter the model returns outside its meaningful range is dropped
        rather than clamped: a confidence level of 99 (meaning 99%) silently
        rewritten to 0.99 would be a guess, and a guess about the number the
        whole figure is defined by. Dropping it lets the data layer's documented
        default stand, which is at least a number someone chose on purpose.
        """
        if not isinstance(raw, dict):
            return {}
        params: dict[str, Any] = {}

        confidence = raw.get("confidence_level")
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            if 0.0 < float(confidence) < 1.0:
                params["confidence_level"] = float(confidence)
            else:
                warnings.append(
                    f"A confidence level of {confidence} is not a fraction between "
                    "0 and 1; it was dropped and the data layer's default used.")

        horizon = raw.get("horizon_days")
        if isinstance(horizon, (int, float)) and not isinstance(horizon, bool):
            if float(horizon).is_integer() and 1 <= int(horizon) <= 260:
                params["horizon_days"] = int(horizon)
            else:
                warnings.append(
                    f"A horizon of {horizon} days is not a whole number of days "
                    "within a trading year; it was dropped and the data layer's "
                    "default used.")
        return params

    @staticmethod
    def _resolve_answerability(answerable: bool, reason: str | None,
                               calculation: str | None,
                               requested_fields: list[str] | None,
                               catalogue: ToolCatalogue,
                               notes: list[FieldNote]
                               ) -> tuple[bool, str | None, str | None]:
        """A partially servable request is not an unanswerable one.

        The prompt says this, and a prompt is not a guarantee. Observed on
        glm-5.2: asked for six fields of which three exist, plus a VaR the data
        layer offers, the expert assembled a perfectly good requirement - three
        fields, a grounded 250-row window - and then set `answerable=false`
        because three of the *names* were instrument identifiers. The user was
        declined outright and got nothing, when most of what they asked for was
        sitting right there.

        So the contradiction is resolved here, deterministically. A refusal
        stands only when there is genuinely nothing to serve. It is overturned
        when either signal says otherwise:

        * the user named at least one field this source publishes, or
        * the task needs a calculation the data layer actually offers.

        A request for CVA, or for nothing but CUSIPs and issuer names, matches
        neither and is still declined - which is the right answer for those. The
        override is recorded as a warning, so a reader can see that the expert's
        own verdict was corrected, and why.
        """
        if answerable:
            return True, reason, None

        servable = sorted(set(requested_fields or []) & set(catalogue.fields))
        if not servable and not calculation:
            return False, reason, None

        why = []
        if servable:
            why.append("field(s) it asked for are published here "
                       f"({', '.join(servable)})")
        if calculation:
            why.append("the calculation it needs is one the data layer offers")
        unavailable = [n.name for n in notes if n.verdict == "unavailable"]
        LOGGER.warning("overriding an unanswerable verdict: %s", "; ".join(why))
        return True, None, (
            "The expert declared this task unanswerable, but " +
            " and ".join(why) + ". The servable part was kept and " +
            (f"the unavailable field(s) ({', '.join(unavailable)}) were recorded "
             "rather than substituted." if unavailable else
             "nothing was substituted for what is missing."))

    @traced("domain_expert.validate_result", run_type="llm")
    def validate_result(self, requirement: Requirement,
                        calculation: dict[str, Any] | None,
                        summary: dict[str, Any]) -> ResultValidation:
        """Does the result match the contract that was agreed?

        The last gate before a number reaches a person, and the one this system
        was missing. It exists because of an observed failure: the agreed plan
        said a 10-day horizon, the engine computed one day, and the reply called
        it ten. Every field was true; the sentence was not.

        The mechanical checks run first and in code, because they are exact and
        a model asked to compare two numbers will occasionally say they match.
        The model is used only for interpretation, and only after the arithmetic
        has already decided the verdict.
        """
        checks: list[dict[str, Any]] = []
        mismatches: list[str] = []
        warnings: list[str] = []

        def check(name: str, expected: Any, actual: Any, blocking: bool) -> None:
            if expected is None:
                return
            ok = _comparable(expected) == _comparable(actual)
            checks.append({"check": name, "expected": expected,
                           "actual": actual, "ok": ok})
            if ok:
                return
            message = f"{name}: agreed {expected!r}, result reports {actual!r}"
            (mismatches if blocking else warnings).append(message)

        if requirement.calculation and calculation is None:
            mismatches.append(
                f"the plan agreed to run {requirement.calculation} and no "
                "calculation came back at all")
        elif calculation is not None:
            result = calculation.get("result") or {}
            if calculation.get("error"):
                mismatches.append(f"the calculation failed: {calculation['error']}")
            check("calculation", requirement.calculation, calculation.get("tool"),
                  blocking=True)
            params = requirement.calculation_params or {}
            check("horizon_days", params.get("horizon_days"),
                  result.get("horizon_days"), blocking=True)
            check("confidence_level", params.get("confidence_level"),
                  result.get("confidence_level"), blocking=True)
            if requirement.rows and result.get("trading_days"):
                check("lookback", requirement.rows, result.get("trading_days"),
                      blocking=False)
            if result and not any(str(k).lower() in ("units", "unit")
                                  for k in result):
                warnings.append("the result carries no units")

        # Temporal intent is the other thing that goes wrong silently.
        delivered = summary.get("observation_date") or summary.get("curve_date")
        if requirement.temporal.as_of_date and delivered:
            check("as_of_date", requirement.temporal.as_of_date, delivered,
                  blocking=True)

        verdict = ("INVALID" if mismatches
                   else "VALID_WITH_WARNINGS" if warnings else "VALID")
        interpretation = self._interpret(requirement, verdict, mismatches, warnings)
        if verdict != "VALID":
            LOGGER.warning("result validation %s: %s", verdict,
                           "; ".join(mismatches or warnings))
        return ResultValidation(verdict=verdict, checks=checks,  # type: ignore[arg-type]
                                mismatches=mismatches, warnings=warnings,
                                interpretation=interpretation)

    def _interpret(self, requirement: Requirement, verdict: str,
                   mismatches: list[str], warnings: list[str]) -> str:
        """One sentence on what the result means, once the checks have spoken."""
        if verdict == "INVALID":
            return ("The result does not match the agreed plan: "
                    + "; ".join(mismatches) + ".")
        payload = structured_call(
            call_site=CALL_SITE,
            system=("You are a market-risk expert confirming that a computed "
                    "result answers the question that was agreed. In at most two "
                    "sentences say what the figure represents and name the single "
                    "most important limitation on reading it. State no number "
                    "that is not in the material. Never name an internal tool or "
                    "column identifier."),
            prompt=(f"Agreed plan:\n{requirement.as_dict()}\n\n"
                    f"Checks: {verdict}. Warnings: {warnings or 'none'}"),
            schema={"type": "object",
                    "properties": {"interpretation": {"type": "string"}},
                    "required": ["interpretation"], "additionalProperties": False},
            max_tokens=800)
        return ((payload or {}).get("interpretation")
                or "The result matches the agreed plan.")

    @staticmethod
    def _blocked(task: str, reason: str, blocked_by: str = "data") -> Requirement:
        """A requirement that stops the turn, carrying *why* it stopped.

        `blocked_by="data"` means the question cannot be answered from what
        exists. `blocked_by="model"` means the reasoning step itself failed and
        nothing was learned about the data either way. Collapsing the two is the
        same class of error as writing a missing rate as zero: both produce a
        confident statement the system has no grounds for.
        """
        return Requirement(task=task, answerable=False, unanswerable_reason=reason,
                           row_reason=reason, warnings=[reason],
                           blocked_by=blocked_by)
