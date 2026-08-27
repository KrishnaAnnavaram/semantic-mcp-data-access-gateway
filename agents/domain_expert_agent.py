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

from agents import events
from agents.cache import get_intelligence
from agents.cache.fingerprints import (
    analytical_signature,
    canonical_question,
    catalogue_fingerprint,
    model_identity,
)
from agents.cache.serialization import CacheRequest
from agents.cache.versions import (
    DOMAIN_DERIVE_PROMPT_VERSION,
    DOMAIN_REQUIREMENT_SCHEMA_VERSION,
    DOMAIN_RETRIEVAL_PROMPT_VERSION,
    DOMAIN_RETRIEVAL_SCHEMA_VERSION,
    DOMAIN_REVISE_PROMPT_VERSION,
    DOMAIN_VALIDATE_PROMPT_VERSION,
    DOMAIN_VALIDATION_SCHEMA_VERSION,
)
from agents.contracts import (
    FieldNote,
    KnowledgeChunk,
    Requirement,
    ResultValidation,
    TemporalScope,
    ToolCatalogue,
)
from agents.observability import (
    TERMINAL_FAILURES,
    last_failure_kind,
    set_run_metadata,
    structured_call,
    traced,
)
from agents.redaction import humanise
from llm import CallSite

LOGGER = logging.getLogger("agents.domain_expert")

# High-capability model: this is the reasoning seat of the system.
CALL_SITE = CallSite.DOMAIN_EXPERT

EXECUTABLE_COLLECTION = "quant_knowledge"
REFERENCE_COLLECTION = "market_risk_kb"

# A second semantic view of the same task, expressed in the reference corpus's
# vocabulary.  It is deliberately one general interpretation query rather than
# a dictionary of user phrasings.  In particular, it turns questions such as
# "which maturity is driving my rate risk?" into a search that can surface Key
# Rate DV01 / curve-segment contribution material without another model call.
REFERENCE_INTERPRETATION = (
    "identify calculation method risk factor contribution sensitivity "
    "curve segment key-rate bucket maturity formula"
)

# Columns that accompany any rate regardless of task. A correctness rule, not a
# threshold: a rate without its quoting basis cannot be safely combined.
INVARIANT_FIELDS = ("observation_date", "rate_percent", "quote_basis")

DERIVE_SYSTEM = """\
You are a market-risk domain expert deciding what data a task requires.

You are given two explicitly separated corpora and a catalogue of what the data \
layer can actually provide:
- MARKET RISK REFERENCE CONTEXT is broad explanatory material. Use it to \
understand terminology, choose the relevant calculation, identify risk factors, \
and interpret formulas or regulation.
- EXECUTABLE KNOWLEDGE CONTEXT is the authoritative analytical contract. Only \
this section may support exact operational fields, observation windows, row \
counts, dates, calculation parameters, or other constraints placed into the \
requirement.

Reference material never authorizes an executable number merely because it \
contains one. You have deep domain knowledge, but you must not use it to supply \
figures: any exact value in the requirement must be stated by the user or appear \
in EXECUTABLE KNOWLEDGE CONTEXT, subject to the rules below.

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
default stands. Each entry in `available_calculations` names the parameters \
IT reads in a PARAMS clause - read that clause and fill exactly those. A \
scenario, a target loss, a limit or a tenor the user gave in words belongs \
there too ("run a bear steepener" -> scenario "bear_steepener"; "a $2m loss" \
-> target_loss 2000000; "the 10-year point" -> tenor_months 120). Never state \
a parameter the user did not ask for and the corpus does not give.
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
- `row_quote` must be copied VERBATIM from EXECUTABLE KNOWLEDGE CONTEXT - the exact sentence \
stating the window or observation count. Do not paraphrase.
- If EXECUTABLE KNOWLEDGE CONTEXT does not state a window, set `rows` to null and `row_quote` to \
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
EXECUTABLE KNOWLEDGE CONTEXT you were given. A quote from MARKET RISK REFERENCE \
CONTEXT cannot ground an executable window.
- If the exchange shows the task cannot be served at all, set answerable=false \
and explain plainly. "At all" is the test: fields the data layer cannot serve \
are dropped and recorded, not grounds for refusing the whole request.
"""

#: The vocabularies a planner may choose from, restated here rather than
#: imported. `agents` sits below `backend` — `RiskWorkflows` imports this
#: package, so importing it back would close a cycle. Duplication is the lesser
#: evil, and `tests/test_calculation_params_contract.py` fails the build if the
#: two ever disagree, which is the only real risk of restating them.
SCENARIO_NAMES: tuple[str, ...] = (
    "parallel", "parallel_up", "parallel_down", "twist",
    "bear_steepener", "bull_steepener", "bear_flattener", "bull_flattener",
    "belly_selloff", "belly_rally", "wings_selloff", "wings_rally",
)
CRISIS_IDS: tuple[str, ...] = (
    "1994_BOND_SELLOFF", "2008_GFC_LEHMAN", "2013_TAPER_TANTRUM",
    "2020_COVID_SHOCK", "2022_FED_TIGHTENING", "2023_REGIONAL_BANK_STRESS",
)
RISK_MEASURES: tuple[str, ...] = ("var", "es")


def _money(name: str) -> dict[str, Any]:
    """A currency amount the user stated, always as a positive number."""
    return {"type": ["number", "null"],
            "description": f"{name} in currency units, positive. Null if unstated."}

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
        # One union of every parameter the executable capabilities read. A
        # capability receives only the ones its own signature names, because
        # `McpAgent._calculate` filters by signature — so a union costs nothing
        # at the call and saves the schema from varying per calculation.
        #
        # `additionalProperties: False` stays, and is the reason this needed
        # extending rather than opening. With only `confidence_level` and
        # `horizon_days` declared, a planner asked for a bear steepener had
        # nowhere legal to put `scenario`: it returned `calculation_params: {}`,
        # and every capability with a required input was then blocked by its own
        # guard while the routing had been perfectly correct. The answer to a
        # closed schema missing a field is the field. An open one would have
        # accepted `scenarioo` just as willingly and failed further downstream.
        #
        # One union of every parameter the executable capabilities read. A
        # capability receives only the ones its own signature names, because
        # `McpAgent._calculate` filters by signature — so a union costs nothing
        # at the call and saves the schema from varying per calculation.
        #
        # `additionalProperties: False` stays, and is the reason this needed
        # extending rather than opening. With only `confidence_level` and
        # `horizon_days` declared, a planner asked for a bear steepener had
        # nowhere legal to put `scenario`: it returned `calculation_params: {}`,
        # and every capability with a required input was then blocked by its own
        # guard while the routing had been perfectly correct. The answer to a
        # closed schema missing a field is the field. An open one would have
        # accepted `scenarioo` just as willingly and failed further downstream.
        #
        # `required` stays at the original two. Eighteen required properties is
        # the contract this file already records glm-5.2 failing (see the note
        # under the top-level `required`), and these are optional by nature — a
        # question states two or three of them, never all.
        #
        # KNOWN LIMITATION — `LLM_BACKEND=anthropic` cannot plan with this
        # schema. Anthropic caps a schema at 16 union-typed and 24 optional
        # parameters; twenty nullable properties here reach 25 and 32:
        #
        #   too many parameters with union types (25 ...) limit: 16
        #   too many optional parameters (32 ...) limit: 24
        #
        # Z.AI enforces neither, which is why the default backend is unaffected.
        # No split of these twenty satisfies both caps — the arithmetic allows
        # seven nullable and ten optional, seventeen in all — so restoring
        # Anthropic means changing the *shape* rather than the split: one array
        # of {name, value} pairs with the names as a closed enum costs about one
        # union and one optional. That is a design change, deliberately not made
        # here. `test_no_schema_exceeds_the_optional_parameter_budget` records
        # the limitation as a strict xfail, so it will speak up when it is
        # fixed. Anthropic is separately broken on the clarify path by
        # `minItems: 2` in `orchestrator_agent.py`, which predates this.
        "calculation_params": {
            "type": "object",
            "properties": {
                "confidence_level": {"type": ["number", "null"],
                                     "description": "0.99 for 99%. Null if unstated."},
                "horizon_days": {"type": ["integer", "null"],
                                 "description": "Whole days. Null if unstated."},
                # `enum` alone with `null` among its members. Pairing a union
                # `type` with an enum is valid JSON Schema and Z.AI takes it,
                # but Anthropic rejects the whole request — see
                # `test_no_schema_pairs_a_union_type_with_an_enum`.
                "scenario": {
                    "enum": [*SCENARIO_NAMES, None],
                    "description": "Named rate-shock shape. Null if unstated."},
                "shock_bp": {
                    "type": ["number", "null"],
                    "description": "Rate move in basis points, negative for a fall."},
                "severity_bp": {
                    "type": ["number", "null"],
                    "description": "Magnitude of a template scenario, in basis points."},
                "pivot_tenor_months": {
                    "type": ["number", "null"],
                    "description": "Tenor a twist pivots about, in MONTHS (120 = 10y)."},
                "tenor_months": {
                    "type": ["number", "null"],
                    "description": "A single curve node, in MONTHS (24 = 2y, 360 = 30y)."},
                "crisis_id": {
                    "enum": [*CRISIS_IDS, None],
                    "description": "A named historical window to replay."},
                "risk_measure": {
                    "enum": [*RISK_MEASURES, None],
                    "description": "Which measure to decompose: var or es."},
                "target_loss": _money("A single loss to solve backwards for"),
                "target_losses": {
                    "type": ["array", "null"], "items": {"type": "number"},
                    "description": "Several losses to solve for, each positive."},
                "limit_amount": _money("A risk limit to find the breaching shock for"),
                "dv01_limit": _money("A DV01 limit"),
                "var_limit": _money("A VaR limit"),
                "stress_loss_limit": _money("A stress-loss limit"),
                "notional": _money("Face amount of a hypothetical trade"),
                "amber_utilisation_percent": {
                    "type": ["number", "null"],
                    "description": "Warning threshold as a percent between 0 and 100."},
                "scenario_count": {
                    "type": ["integer", "null"],
                    "description": "Number of Monte Carlo simulations to draw."},
                "top_n": {
                    "type": ["integer", "null"],
                    "description": "How many entries to rank."},
                "other_portfolio_id": {
                    "type": ["string", "null"],
                    "description": "The second book in a comparison."},
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

    def __init__(self, knowledge, n_results: int = 6, *,
                 market_risk_knowledge=None,
                 market_risk_n_results: int = 4,
                 max_reference_chunks: int = 6,
                 intelligence=None) -> None:
        self.kb = knowledge
        self.market_risk_kb = market_risk_knowledge
        self.call_site = CALL_SITE
        self.n_results = n_results
        self.market_risk_n_results = market_risk_n_results
        self.max_reference_chunks = max_reference_chunks
        self.intelligence = intelligence or get_intelligence()

    def _knowledge_version(self) -> str:
        executable = str(getattr(self.kb, "version", "unknown"))
        reference = str(getattr(self.market_risk_kb, "version", "none"))
        return f"executable={executable};reference={reference}"

    # -- knowledge -----------------------------------------------------------

    @traced("knowledge_retrieval", run_type="retriever")
    def retrieve(self, subject: str) -> list[KnowledgeChunk]:
        request = CacheRequest(
            agent="domain_expert", operation="retrieve",
            identity={"subject": canonical_question(subject),
                      "n_results": self.n_results,
                      "collection": EXECUTABLE_COLLECTION},
            versions={"knowledge": self._knowledge_version(),
                      "prompt": DOMAIN_RETRIEVAL_PROMPT_VERSION,
                      "schema": DOMAIN_RETRIEVAL_SCHEMA_VERSION},
            result_kind="knowledge_chunks",
            canonical_question=canonical_question(subject),
        )
        return self.intelligence.cached(
            request, lambda: self._retrieve(subject), cache_if=bool)

    def _retrieve(self, subject: str) -> list[KnowledgeChunk]:
        """Search executable Qdrant knowledge, the authority for requirements.

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
        with events.stage(events.EventType.RETRIEVAL_STARTED,
                          events.EventType.RETRIEVAL_COMPLETED,
                          agent="domain-expert",
                          title="Searching the executable knowledge corpus",
                          tool_name="qdrant", collection=EXECUTABLE_COLLECTION,
                          queries=len(queries)) as measured:
            chunks = self._retrieve_queries(
                self.kb, queries, n_results=self.n_results,
                default_collection=EXECUTABLE_COLLECTION)
            measured["chunks"] = len(chunks)
        return chunks

    @traced("market_risk_reference_retrieval", run_type="retriever")
    def retrieve_market_risk(self, subject: str) -> list[KnowledgeChunk]:
        request = CacheRequest(
            agent="domain_expert", operation="retrieve_reference",
            identity={"subject": canonical_question(subject),
                      "n_results": self.market_risk_n_results,
                      "max_chunks": self.max_reference_chunks,
                      "collection": REFERENCE_COLLECTION},
            versions={"knowledge": self._knowledge_version(),
                      "prompt": DOMAIN_RETRIEVAL_PROMPT_VERSION,
                      "schema": DOMAIN_RETRIEVAL_SCHEMA_VERSION},
            result_kind="knowledge_chunks",
            canonical_question=canonical_question(subject),
        )
        return self.intelligence.cached(
            request, lambda: self._retrieve_market_risk(subject), cache_if=bool)

    def _retrieve_market_risk(self, subject: str) -> list[KnowledgeChunk]:
        """Search the broad reference corpus with one bounded expansion.

        Reaching the Domain Expert is already the application's market-risk
        domain signal, so this does not need another classifier or model call.
        The second query asks for the calculation/risk-factor interpretation of
        the task and fixes a measured paraphrase weakness around curve maturity
        contribution.  The merged result is capped independently of per-query
        top-k so adding the corpus cannot grow the model context without bound.
        """
        if self.market_risk_kb is None:
            return []
        queries = [subject, f"{subject} {REFERENCE_INTERPRETATION}"]
        with events.stage(events.EventType.RETRIEVAL_STARTED,
                          events.EventType.RETRIEVAL_COMPLETED,
                          agent="domain-expert",
                          title="Searching the market-risk reference corpus",
                          tool_name="qdrant", collection=REFERENCE_COLLECTION,
                          queries=len(queries)) as measured:
            chunks = self._retrieve_queries(
                self.market_risk_kb, queries,
                n_results=self.market_risk_n_results,
                default_collection=REFERENCE_COLLECTION)
            measured["chunks"] = len(chunks)
        return chunks[:self.max_reference_chunks]

    def _retrieve_queries(self, knowledge, queries: list[str], *, n_results: int,
                          default_collection: str) -> list[KnowledgeChunk]:
        """Merge deterministic semantic queries, retaining best provenance."""
        if knowledge is None:
            return []
        merged: dict[tuple[str, str, str], KnowledgeChunk] = {}
        for query in queries:
            try:
                hits = knowledge.retrieve(query, n_results=n_results)
            except Exception as exc:  # noqa: BLE001 - reported, never fatal
                LOGGER.warning("%s retrieval failed for %r: %s",
                               default_collection, query, exc)
                continue
            for hit in hits:
                distance = float(hit.get("distance", 0.0))
                collection = str(hit.get("collection") or default_collection)
                chunk = KnowledgeChunk(
                    domain=hit.get("domain", ""), source=hit.get("source", ""),
                    heading=hit.get("heading", ""), text=hit.get("text", ""),
                    distance=distance, collection=collection,
                    chunk_id=str(hit.get("chunk_id") or ""),
                    score=float(hit.get("score", round(1.0 - distance, 4))),
                    document_path=str(hit.get("document_path") or ""),
                    line_start=hit.get("line_start"),
                    line_end=hit.get("line_end"), retrieval_query=query)
                key = (collection, chunk.chunk_id,
                       f"{chunk.source}::{chunk.heading}" if not chunk.chunk_id else "")
                # Keep the better-scoring sighting when both queries find it.
                if key not in merged or chunk.distance < merged[key].distance:
                    merged[key] = chunk
        chunks = sorted(merged.values(), key=lambda c: c.distance)
        # Retriever-level metadata for the trace: how many queries ran, how many
        # distinct chunks survived the merge, and the best distance. No document
        # text or vectors — a retriever span that dumps the corpus is noise, and
        # payload bounding is a rule of this integration.
        set_run_metadata(collection=self._collection_name(),
                         query_count=len(queries), returned_chunks=len(chunks),
                         top_k=self.n_results,
                         best_distance=round(chunks[0].distance, 4) if chunks else None)
        return chunks

    @traced("qdrant.search", run_type="retriever")
    def _qdrant_search(self, query: str) -> list[dict]:
        """One vector query against the store, as its own span.

        Nested under `knowledge_retrieval` so the two-query strategy is visible
        in the trace — and so a slow or empty query is attributable to the
        embedding call rather than lost in the merge. Failures are reported and
        swallowed: a retrieval miss must degrade to fewer citations, never take
        the turn down.
        """
        try:
            hits = self.kb.retrieve(query, n_results=self.n_results)
        except Exception as exc:  # noqa: BLE001 - reported, never fatal
            LOGGER.warning("knowledge retrieval failed for %r: %s", query, exc)
            set_run_metadata(collection=self._collection_name(), result_count=0,
                             top_k=self.n_results, error=type(exc).__name__)
            return []
        set_run_metadata(collection=self._collection_name(),
                         result_count=len(hits), top_k=self.n_results)
        return hits

    def _collection_name(self) -> str | None:
        """The Qdrant collection behind the knowledge base, if discoverable.

        Read defensively through the seams: a mock or a differently-shaped store
        may not expose it, and a missing collection name is a cosmetic gap in
        the trace, never an error.
        """
        store = getattr(self.kb, "store", None)
        return getattr(store, "collection_name", None)

    @staticmethod
    def _context(chunks: list[KnowledgeChunk]) -> str:
        return "\n\n".join(f"[{c.label}]\n{c.text}" for c in chunks)

    @staticmethod
    def _reference_chunks(chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
        return [c for c in chunks if c.collection == REFERENCE_COLLECTION]

    @staticmethod
    def _executable_chunks(chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
        return [c for c in chunks if c.collection != REFERENCE_COLLECTION]

    # -- the requirement -----------------------------------------------------

    @traced("domain_expert.derive", run_type="llm")
    def derive(self, question: str, task: str, catalogue: ToolCatalogue,
               requested_fields: list[str] | None,
               requested_rows: int | None,
               prior_plan: dict[str, Any] | None = None,
               revalidation_reason: str = ""
               ) -> tuple[Requirement, list[KnowledgeChunk]]:
        canonical = canonical_question(question)
        prior = prior_plan or {}
        request = CacheRequest(
            agent="domain_expert", operation="derive",
            identity={"question": canonical, "task": task,
                      "catalogue": catalogue_fingerprint(catalogue),
                      "requested_fields": requested_fields or [],
                      "requested_rows": requested_rows,
                      "prior_plan": prior,
                      "revalidation_reason": revalidation_reason},
            versions={"knowledge": self._knowledge_version(),
                      "prompt": DOMAIN_DERIVE_PROMPT_VERSION,
                      "schema": DOMAIN_REQUIREMENT_SCHEMA_VERSION},
            result_kind="requirement_with_chunks",
            canonical_question=canonical,
            semantic_signature=analytical_signature(
                question, task=task, requested_fields=requested_fields,
                requested_rows=requested_rows, prior_plan=prior),
            model=model_identity(CALL_SITE),
        )
        return self.intelligence.cached(
            request,
            lambda: self._derive_uncached(
                question, task, catalogue, requested_fields, requested_rows,
                prior_plan, revalidation_reason),
            cache_if=lambda result: (
                bool(result[1])
                and result[0].blocked_by not in {"model", "account"}
                and not last_failure_kind()),
        )

    def _derive_uncached(self, question: str, task: str,
                         catalogue: ToolCatalogue,
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
        subject = task or question
        reference_chunks = self.retrieve_market_risk(subject)
        executable_chunks = self.retrieve(subject)
        chunks = [*reference_chunks, *executable_chunks]
        if not executable_chunks:
            return self._blocked(task or question,
                                 "The executable knowledge base returned nothing for this task, "
                                 "so no requirement could be grounded."), []

        prompt = self._prompt(question, task, catalogue, requested_fields,
                              requested_rows,
                              self._context(reference_chunks),
                              self._context(executable_chunks))
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
        request = CacheRequest(
            agent="domain_expert", operation="revise",
            identity={"question": canonical_question(question), "task": task,
                      "catalogue": catalogue_fingerprint(catalogue),
                      "proposal": proposal.as_dict(),
                      "response": response.as_dict(),
                      "requested_rows": requested_rows,
                      "requested_fields": requested_fields or [],
                      "chunks": [chunk.as_dict() for chunk in chunks]},
            versions={"knowledge": self._knowledge_version(),
                      "prompt": DOMAIN_REVISE_PROMPT_VERSION,
                      "schema": DOMAIN_REQUIREMENT_SCHEMA_VERSION},
            result_kind="requirement",
            canonical_question=canonical_question(question),
            model=model_identity(CALL_SITE),
        )
        return self.intelligence.cached(
            request,
            lambda: self._revise_uncached(
                question, task, catalogue, proposal, response, chunks,
                requested_rows, requested_fields),
            cache_if=lambda result: (
                result.blocked_by not in {"model", "account"}
                and not last_failure_kind()),
        )

    def _revise_uncached(self, question: str, task: str,
                         catalogue: ToolCatalogue, proposal: Requirement,
                         response, chunks: list[KnowledgeChunk],
                         requested_rows: int | None,
                         requested_fields: list[str] | None = None) -> Requirement:
        """Final requirement, after the data layer said what it can serve."""
        # The citation list is dropped from the echoed proposal: it is the
        # labels of the excerpts printed at the bottom of this same prompt, and
        # sending an index of a document alongside the document is not evidence
        # twice. Everything the expert reasons *from* — its warnings, its quote,
        # its own verdicts — stays.
        proposal_view = {key: value for key, value in proposal.as_dict().items()
                         if key != "citations"}
        prompt = (
            f"User question:\n{question}\n\nTask:\n{task}\n\n"
            f"YOUR HYPOTHESIS (or last revision):\n{proposal_view}\n\n"
            f"THE DATA LAYER'S CAPABILITY EVIDENCE:\n{response.as_dict()}\n\n"
            f"Read `unnecessary_fields` first - those are inputs this tool does "
            f"not read, which you had no way of knowing.\n\n"
            f"Data layer catalogue:\n{catalogue.as_dict()}\n\n"
            f"MARKET RISK REFERENCE CONTEXT (concepts and calculation selection; "
            f"never executable numeric authority):\n"
            f"{self._context(self._reference_chunks(chunks)) or 'No reference excerpts retrieved.'}"
            f"\n\nEXECUTABLE KNOWLEDGE CONTEXT (the ONLY source for exact "
            f"operational requirements and numbers):\n"
            f"{self._context(self._executable_chunks(chunks))}"
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
                reference_context: str, executable_context: str) -> str:
        return (
            f"User question:\n{question}\n\n"
            f"Task the data is for:\n{task}\n\n"
            f"Fields the user named: {requested_fields or 'none'}\n"
            f"Rows the user named: {requested_rows or 'none'}\n\n"
            f"What the data layer can provide:\n{catalogue.as_dict()}\n\n"
            f"MARKET RISK REFERENCE CONTEXT (concepts and calculation selection; "
            f"never executable numeric authority):\n"
            f"{reference_context or 'No reference excerpts retrieved.'}\n\n"
            f"EXECUTABLE KNOWLEDGE CONTEXT (the ONLY source for exact "
            f"operational requirements and numbers):\n{executable_context}"
        )

    def _build(self, payload: dict[str, Any], chunks: list[KnowledgeChunk],
               catalogue: ToolCatalogue, requested_rows: int | None,
               requested_fields: list[str] | None = None,
               opening: bool = False) -> Requirement:
        # The central safety boundary of dual retrieval: broad reference text
        # may contain plausible windows and constants, but it cannot make them
        # executable.  Quote validation therefore sees only quant_knowledge.
        context = self._context(self._executable_chunks(chunks))
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
                "The executable knowledge base states no observation window for this task. "
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

    #: What each numeric parameter has to be for the number it names to mean
    #: anything. The range is part of the meaning, so it lives beside the name
    #: rather than in a chain of ifs: `top_n` of 0 ranks nothing, an
    #: `amber_utilisation_percent` of 150 is not a percentage, and a 20000bp
    #: shock is a unit error rather than a scenario anyone chose.
    _NUMBER_RULES: dict[str, tuple[Any, str]] = {
        "confidence_level": (lambda v: 0.0 < v < 1.0,
                             "a fraction between 0 and 1"),
        "shock_bp": (lambda v: -2000.0 <= v <= 2000.0,
                     "a move within 2000 basis points"),
        "severity_bp": (lambda v: 0.0 < v <= 2000.0,
                        "a positive magnitude within 2000 basis points"),
        "pivot_tenor_months": (lambda v: 0.0 < v <= 600.0,
                               "a tenor in months on the curve"),
        "tenor_months": (lambda v: 0.0 < v <= 600.0,
                         "a tenor in months on the curve"),
        "amber_utilisation_percent": (lambda v: 0.0 < v < 100.0,
                                      "a percentage between 0 and 100"),
        "target_loss": (lambda v: v > 0.0, "a positive amount"),
        "limit_amount": (lambda v: v > 0.0, "a positive amount"),
        "dv01_limit": (lambda v: v > 0.0, "a positive amount"),
        "var_limit": (lambda v: v > 0.0, "a positive amount"),
        "stress_loss_limit": (lambda v: v > 0.0, "a positive amount"),
        "notional": (lambda v: v > 0.0, "a positive amount"),
    }

    #: The same, for parameters that must be whole numbers.
    _INTEGER_RULES: dict[str, tuple[Any, str]] = {
        "horizon_days": (lambda v: 1 <= v <= 260,
                         "a whole number of days within a trading year"),
        "scenario_count": (lambda v: 100 <= v <= 1_000_000,
                           "a whole number between 100 and 1,000,000"),
        "top_n": (lambda v: 1 <= v <= 100, "a whole number between 1 and 100"),
    }

    #: Vocabularies. The stated word is matched case-insensitively and the
    #: canonical spelling returned - `BEAR_STEEPENER` and `bear_steepener` are
    #: the same word, and choosing between them is not a judgement about risk.
    _ENUM_RULES: dict[str, tuple[str, ...]] = {
        "scenario": SCENARIO_NAMES,
        "crisis_id": CRISIS_IDS,
        "risk_measure": RISK_MEASURES,
    }

    @classmethod
    def _calculation_params(cls, raw: Any, warnings: list[str]) -> dict[str, Any]:
        """The stated parameters, range-checked, with nothing invented.

        A parameter the model returns outside its meaningful range is dropped
        rather than clamped: a confidence level of 99 (meaning 99%) silently
        rewritten to 0.99 would be a guess, and a guess about the number the
        whole figure is defined by. Dropping it lets the data layer's documented
        default stand, which is at least a number someone chose on purpose.

        Where a capability has no default, because the answer is meaningless
        without the input - a reverse stress with no target loss, a breach
        search with no limit - dropping it is what makes the adapter ask. That
        is the intended end of this path rather than a failure of it.
        """
        if not isinstance(raw, dict):
            return {}
        params: dict[str, Any] = {}

        def number(value: Any) -> float | None:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            value = float(value)
            # NaN and the infinities satisfy or defeat every comparison below
            # without meaning anything, and are the one case a range cannot
            # catch on its own.
            return value if value == value and abs(value) != float("inf") else None

        def reject(name: str, value: Any, meaning: str) -> None:
            # `humanise`, because this text is written into the material the
            # orchestrator composes the reply from: an identifier put here
            # reaches the user as an identifier.
            warnings.append(
                f"{humanise(name).capitalize()} was given as {value!r}, which "
                f"is not {meaning}; it was dropped and the data layer's "
                f"default used.")

        for name, (acceptable, meaning) in cls._NUMBER_RULES.items():
            value = number(raw.get(name))
            if value is None:
                continue
            if acceptable(value):
                params[name] = value
            else:
                reject(name, raw[name], meaning)

        for name, (acceptable, meaning) in cls._INTEGER_RULES.items():
            value = number(raw.get(name))
            if value is None:
                continue
            if value.is_integer() and acceptable(int(value)):
                params[name] = int(value)
            else:
                reject(name, raw[name], meaning)

        for name, vocabulary in cls._ENUM_RULES.items():
            stated = raw.get(name)
            if not isinstance(stated, str) or not stated.strip():
                continue
            canonical = {word.lower(): word for word in vocabulary}
            match = canonical.get(stated.strip().lower())
            if match is not None:
                params[name] = match
            else:
                reject(name, stated, f"one of {', '.join(vocabulary)}")

        losses = raw.get("target_losses")
        if isinstance(losses, list) and losses:
            # Every entry has to be a real positive amount. A list with one bad
            # entry is dropped whole rather than silently shortened: a threshold
            # table missing a row nobody mentioned reads as complete.
            checked = [number(item) for item in losses[:20]]
            if all(value is not None and value > 0.0 for value in checked):
                params["target_losses"] = checked
            else:
                reject("target_losses", losses, "a list of positive amounts")

        other = raw.get("other_portfolio_id")
        if isinstance(other, str) and other.strip():
            params["other_portfolio_id"] = other.strip()[:64]

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
        request = CacheRequest(
            agent="domain_expert", operation="validate_result",
            identity={"requirement": requirement.as_dict(),
                      "calculation": calculation, "summary": summary},
            versions={"knowledge": self._knowledge_version(),
                      "prompt": DOMAIN_VALIDATE_PROMPT_VERSION,
                      "schema": DOMAIN_VALIDATION_SCHEMA_VERSION},
            result_kind="result_validation",
            canonical_question=canonical_question(requirement.task),
            model=model_identity(CALL_SITE),
        )
        return self.intelligence.cached(
            request,
            lambda: self._validate_result_uncached(
                requirement, calculation, summary),
            cache_if=lambda result: not last_failure_kind(),
        )

    def _validate_result_uncached(self, requirement: Requirement,
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
        """One sentence on what the result means, once the checks have spoken.

        **Deterministic first, and a model only where judgement is left.** The
        checks above are the safety, and they are arithmetic. When every one of
        them passed and nothing was flagged, there is no analytical judgement
        remaining — the sentence is a restatement of a contract that has just
        been proven to hold, and it can be written from the plan's own fields.

        That matters more than it sounds. This call declares `max_tokens=800`
        and the DOMAIN_EXPERT floor raises it to 12,000 — the same ceiling as
        deriving a whole requirement — and GLM expands its reasoning to fill
        whatever ceiling it is given (5,241 tokens under 12,000; see
        `llm/config.py`). So two sentences of prose were costing a full
        requirement-grade reasoning burn on every risk turn that passed.

        A warning is different: something *did* diverge from the plan without
        being fatal, and saying what that means for reading the figure is
        genuine interpretation. That case still asks the model.
        """
        if verdict == "INVALID":
            return ("The result does not match the agreed plan: "
                    + "; ".join(mismatches) + ".")
        if verdict == "VALID":
            return self._agreed_reading(requirement)
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
    def _agreed_reading(requirement: Requirement) -> str:
        """What the figure is, written from the contract the checks just proved.

        Every clause is copied from a field the expert itself produced and the
        mechanical checks have just confirmed the result honours. Nothing is
        generated, so nothing can be invented — and the limitation quoted is the
        expert's own grounded one rather than a fresh opinion about a plan it
        can no longer see the corpus for.
        """
        detail: list[str] = []
        params = requirement.calculation_params or {}
        confidence = params.get("confidence_level")
        horizon = params.get("horizon_days")
        if confidence is not None:
            detail.append(f"at {float(confidence) * 100:g}% confidence")
        if horizon is not None:
            detail.append(f"over a {int(horizon)}-day horizon")
        if requirement.rows:
            detail.append(f"from {requirement.rows:,} observations")
        period = requirement.temporal.describe()
        if period:
            detail.append(period)

        opening = (f"The result answers the agreed plan: "
                   f"{requirement.task or 'the stated objective'}")
        body = f"{opening}, {', '.join(detail)}." if detail else f"{opening}."
        # The expert's own stated limitation, not a new one. Its absence is not
        # papered over with an invented caveat — silence is reported as silence.
        if requirement.limitations:
            return f"{body} Limitation: {requirement.limitations[0].rstrip('.')}."
        return body

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
