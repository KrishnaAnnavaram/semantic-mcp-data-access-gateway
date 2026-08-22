"""What the three agents say to each other.

Every message between agents is one of these types. They are dataclasses rather
than free-form dicts for one reason: a negotiation is only auditable if each
turn has a fixed shape. When the domain expert says "I need 250 rows" and the
MCP agent answers "I can serve 250, but not those three fields", both statements
have to survive into a trace in a form a human can read back.

The flow these types carry:

    Question ──► Intent ──► Requirement ⇄ ToolCatalogue/ServeResponse ──► Outcome
                            └──────── Negotiation ────────┘
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Route = Literal["direct", "clarify", "data_request"]
Verdict = Literal["required", "not_needed", "unavailable"]

#: How a Domain ↔ MCP negotiation ended. Four states rather than a boolean,
#: because the orchestrator has to do four different things: execute, ask the
#: user, explain a limitation, or admit the two agents could not construct an
#: acceptable plan. `converged: bool` collapsed the last three into "not true"
#: and left the orchestrator guessing which one it was.
NegotiationDecision = Literal[
    "AGREED", "NEEDS_USER_INPUT", "UNSUPPORTED", "CANNOT_REACH_AGREEMENT"]

#: Whether an execution result is what the agreed plan asked for. Separate from
#: the task state on purpose: a task can complete perfectly and still return a
#: one-day VaR when ten days were agreed, which is a true number under a false
#: label and the worst thing this system can emit.
ResultVerdict = Literal["VALID", "VALID_WITH_WARNINGS", "INVALID"]


@dataclass
class TemporalScope:
    """When the user's question is about. Optional, and absent by default.

    Nothing here is invented: every field is set only when the user or the
    corpus states it. The reason it exists at all is a defect — a requirement
    that could express "250 rows" but not "in 2008" meant a question about the
    financial crisis was answered with last year's curve, and the substitution
    was silent. A row count is not a date, and a system that treats them as
    interchangeable is quietly wrong in the one direction nobody checks.
    """

    #: A single day to value or observe on. "What was the curve on 2008-09-15?"
    as_of_date: str | None = None
    #: An inclusive window. "Yields during 2020."
    start_date: str | None = None
    end_date: str | None = None
    #: Trading days of history a method consumes, when that is what was asked
    #: for rather than a calendar range. Kept apart from `rows` because a
    #: lookback is a methodology figure and `rows` is a display budget.
    lookback_days: int | None = None

    @property
    def is_empty(self) -> bool:
        return not any((self.as_of_date, self.start_date, self.end_date,
                        self.lookback_days))

    @property
    def is_historical(self) -> bool:
        """Does this ask about a named past period rather than the latest data?"""
        return bool(self.as_of_date or self.start_date or self.end_date)

    def describe(self) -> str:
        if self.as_of_date:
            return f"as of {self.as_of_date}"
        if self.start_date and self.end_date:
            return f"{self.start_date} to {self.end_date}"
        if self.start_date:
            return f"from {self.start_date}"
        if self.end_date:
            return f"up to {self.end_date}"
        if self.lookback_days:
            return f"the most recent {self.lookback_days} trading days"
        return "the latest available observation"

    def as_dict(self) -> dict[str, Any]:
        return {"as_of_date": self.as_of_date, "start_date": self.start_date,
                "end_date": self.end_date, "lookback_days": self.lookback_days,
                "described": self.describe()}

    @classmethod
    def from_dict(cls, data: Any) -> TemporalScope:
        if not isinstance(data, dict):
            return cls()
        def _date(key: str) -> str | None:
            value = data.get(key)
            return str(value) if value else None
        lookback = data.get("lookback_days")
        try:
            lookback = int(lookback) if lookback is not None else None
        except (TypeError, ValueError):
            lookback = None
        return cls(as_of_date=_date("as_of_date"), start_date=_date("start_date"),
                   end_date=_date("end_date"), lookback_days=lookback)


@dataclass
class Intent:
    """The orchestrator's reading of the question."""

    route: Route
    reasoning: str
    task: str = ""                 # what the data is for, when route == data_request
    direct_answer: str = ""        # the reply itself, when route == direct
    requested_fields: list[str] = field(default_factory=list)
    requested_rows: int | None = None
    # Set when route == "clarify": one question, and the choices that answer it.
    # Asking beats guessing when the missing detail changes the whole result.
    question: str = ""
    options: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"route": self.route, "reasoning": self.reasoning, "task": self.task,
                "direct_answer": self.direct_answer,
                "requested_fields": self.requested_fields,
                "requested_rows": self.requested_rows,
                "question": self.question, "options": self.options}


@dataclass
class KnowledgeChunk:
    """One retrieved passage. `text` is kept so a citation can be verified."""

    domain: str
    source: str
    heading: str
    text: str
    distance: float

    @property
    def label(self) -> str:
        return f"{self.domain}/{self.source} — {self.heading}"

    def as_dict(self) -> dict[str, Any]:
        return {"domain": self.domain, "source": self.source, "heading": self.heading,
                "distance": self.distance, "label": self.label}


@dataclass
class ToolSpec:
    """One capability the data layer advertises.

    `executable` is the whole point of this field existing. The catalogue used
    to list four data tools alongside four risk workflows with nothing to tell
    them apart, and the domain expert may name any catalogue tool as the
    calculation to run — so naming `get_curve_slope`, the obvious choice for a
    2s10s question, produced `no workflow named 'get_curve_slope'` instead of a
    slope. A capability that cannot be dispatched must say so rather than be
    quietly unavailable at the last step.
    """

    name: str
    description: str
    server: str
    #: Can the execution layer actually resolve and run this as a calculation?
    #: False means informational: it describes what the data layer holds, not
    #: something the expert may schedule.
    #: May this be named as a requirement's `calculation`? Retrieval helpers
    #: cannot: they describe what a fetch returns, and the fetch happens
    #: anyway. See `ToolCatalogue.as_dict` for why the distinction is presented
    #: the way it is.
    executable: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description,
                "server": self.server,
                "kind": "calculation" if self.executable else "retrieval"}


@dataclass
class ToolCatalogue:
    """What the MCP agent can actually do, as told to the domain expert.

    Advertised rather than assumed: the domain expert must not plan against a
    capability that is not connected, and under a mock backend the risk tools
    genuinely are not there.
    """

    tools: list[ToolSpec] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    tenors: list[str] = field(default_factory=list)
    can_calculate: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def executable_tools(self) -> list[str]:
        """The names a requirement may legitimately schedule as a calculation."""
        return [t.name for t in self.tools if t.executable]

    @property
    def retrieval_tools(self) -> list[str]:
        """What the fetch can return. Never scheduled; always available."""
        return [t.name for t in self.tools if not t.executable]

    def as_dict(self) -> dict[str, Any]:
        """The catalogue as the domain expert reads it.

        The split is stated in words rather than left to a boolean, because a
        boolean got read as availability. Told only that `get_rate_history` was
        "not executable", the expert concluded a plain 30-year history could
        not be served at all — and then invented a reason, asserting the data
        server was down. It was not: retrieval had run successfully moments
        earlier in the same turn.

        The distinction is real but narrow, and naming it precisely is the
        whole fix. Retrieval is not a choice the planner makes; every plan
        returns the rows its fields and tenors describe. `calculation` is an
        *optional* analysis layered on top, and only these four names may fill
        it.
        """
        return {
            "tools": [t.as_dict() for t in self.tools],
            "fields": self.fields, "tenors": self.tenors,
            "can_calculate": self.can_calculate,
            "available_calculations": self.executable_tools,
            "retrieval_always_available": self.retrieval_tools,
            "how_to_read_this": (
                "Data retrieval ALWAYS happens: a plan returns the rows its "
                "`fields` and `tenors` describe, whether or not it names a "
                "calculation. `calculation` is optional and may only be one of "
                "`available_calculations`. A task that just needs data is fully "
                "answerable with `calculation: null` — that is the normal case, "
                "not a limitation."),
            "notes": self.notes}


@dataclass
class FieldNote:
    name: str
    verdict: Verdict
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "verdict": self.verdict, "reason": self.reason}


@dataclass
class Requirement:
    """The domain expert's proposal: what this task needs, and on whose authority.

    `rows` is deliberately optional. When the knowledge base does not state a
    window, the honest requirement says so — a number the corpus cannot justify
    is worse than an admitted gap, because nobody can audit it or change it by
    editing a document.
    """

    task: str
    answerable: bool
    fields: list[str] = field(default_factory=list)
    field_notes: list[FieldNote] = field(default_factory=list)
    rows: int | None = None
    row_reason: str = ""
    row_quote: str | None = None          # verbatim, from a retrieved chunk
    grounded: bool = False
    tenors: list[str] = field(default_factory=list)
    #: Which curve the tenors belong to: "nominal", "real", or "ambiguous" when
    #: the user named a maturity both curves publish without saying which they
    #: meant. A nominal par yield and a real yield are different quantities and
    #: must never share a curve, so this travels with the tenors rather than
    #: being assumed downstream — silently serving nominal for a question about
    #: TIPS is exactly the mistake the quoting-basis rule exists to prevent.
    curve_family: str = "nominal"
    #: When the question is about. Empty means "the latest observation", which
    #: is what every earlier version silently assumed for every question.
    temporal: TemporalScope = field(default_factory=TemporalScope)
    #: The expert's own commitment, stated rather than inferred. `None` means
    #: "still thinking", which is what keeps the negotiation going for another
    #: round. The previous design inferred agreement from field arithmetic and
    #: therefore agreed on round one every time, whatever the expert thought.
    decision: str | None = None
    #: True while this is still the domain expert's opening *hypothesis* rather
    #: than an agreed plan. A hypothesis deliberately keeps inputs the data
    #: layer may not have, so the MCP agent gets to say so with evidence — the
    #: previous design normalised them away before the conversation started,
    #: which is why the negotiation had nothing left to negotiate.
    is_hypothesis: bool = False
    #: Fields the user or the method asked for, before anything was dropped.
    #: The MCP agent judges these; `fields` holds what survived.
    candidate_fields: list[str] = field(default_factory=list)
    #: What the expert wants the data layer to answer. Real questions, not
    #: rhetoric — each one should be resolvable by a capability assessment.
    open_questions: list[str] = field(default_factory=list)
    #: The assumptions the method rests on, and what it cannot tell you. Carried
    #: so result validation can check they were respected.
    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    calculation: str | None = None        # a tool name, when the task needs maths
    #: The parameters that calculation reads — confidence level, horizon. The
    #: data layer's workflows have always accepted these and always been given
    #: their defaults, so a request for a 10-day 99% VaR was computed at 1 day
    #: and then described as 10-day in the reply. A parameter the user states
    #: has to reach the thing that computes with it, or the label is a lie.
    calculation_params: dict[str, Any] = field(default_factory=dict)
    unanswerable_reason: str | None = None
    #: Why this requirement stops the turn, when it does. `""` is the normal
    #: case. `"data"` means the question cannot be answered from what exists.
    #: `"model"` means the reasoning step itself failed — the structured call
    #: came back unusable — and nothing was learned about the data either way.
    #:
    #: Separated because collapsing them tells the user something false. A
    #: provider timeout was being reported as "this task cannot be answered
    #: from the available data", which is a confident claim about *their data*
    #: that the system had no grounds for. It is the same class of error as
    #: writing a missing observation as zero.
    blocked_by: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"task": self.task, "answerable": self.answerable, "fields": self.fields,
                "field_notes": [n.as_dict() for n in self.field_notes],
                "rows": self.rows, "row_reason": self.row_reason,
                "row_quote": self.row_quote, "grounded": self.grounded,
                "tenors": self.tenors, "curve_family": self.curve_family,
                "temporal": self.temporal.as_dict(),
                "decision": self.decision,
                "is_hypothesis": self.is_hypothesis,
                "candidate_fields": self.candidate_fields,
                "open_questions": self.open_questions,
                "assumptions": self.assumptions, "limitations": self.limitations,
                "calculation": self.calculation,
                "calculation_params": self.calculation_params,
                "unanswerable_reason": self.unanswerable_reason,
                "blocked_by": self.blocked_by,
                "citations": self.citations, "warnings": self.warnings}

    #: Fields a capability assessment does not read: the expert's own
    #: bookkeeping about itself (`decision`, `blocked_by`,
    #: `unanswerable_reason`, `row_reason`) and its accumulating narrative
    #: (`warnings`, `citations`). The data layer is asked what it can serve;
    #: none of these changes that answer.
    #:
    #: **Omission has to stay honest.** The receiving side rebuilds a
    #: `Requirement` from this dict and prints `as_dict()` into its prompt, so a
    #: dropped field does not go missing — it comes back as its *default*.
    #: `warnings` reappearing as `[]` says "none shown", which is merely
    #: incomplete. `grounded` reappearing as `False` would say the expert failed
    #: to ground a citation it had in fact grounded, and `row_quote` as `null`
    #: would deny a quote that exists. Those are not omissions, they are
    #: assertions, and false ones — so both stay. They also cost nothing in
    #: stability: a citation only moves when the row count it supports moves,
    #: and the row count is assessable anyway.
    _NOT_A_CAPABILITY_QUESTION = frozenset({
        "decision", "blocked_by", "unanswerable_reason",
        "row_reason", "warnings", "citations"})

    def as_capability_request(self) -> dict[str, Any]:
        """What the data layer needs in order to say what it can serve.

        Two things at once, and the second is the one that matters.

        It is a smaller prompt — the excluded fields are prose the assessor has
        no use for. More importantly it is a **stable** one: duplicate
        suppression fingerprints a handoff by its input, and `warnings` grows on
        every round while `decision` flips as the expert thinks. Sending the
        whole requirement meant two rounds asking the identical capability
        question never looked identical, so the `idempotent` tag on
        `assess_data_requirement` could never actually fire and every round paid
        a full model call.

        Everything the assessment genuinely reads stays: the candidate inputs it
        judges, the calculation, the tenors, the period, the curve family and
        the open questions it is being asked to answer.
        """
        return {key: value for key, value in self.as_dict().items()
                if key not in self._NOT_A_CAPABILITY_QUESTION}


@dataclass
class ServeResponse:
    """The MCP agent's capability assessment of a proposed plan, before any fetch.

    This is the half of the discussion that keeps the plan honest: the domain
    expert knows what the *method* needs, and only the MCP agent knows what the
    *data source* can actually serve. Neither alone is enough.

    It answers with **evidence**, not a verdict. "Approved" tells the expert
    nothing it can reason about; `unnecessary_fields` — inputs the theory asks
    for that this tool's implementation abstracts away — is the single most
    useful thing this agent can say, because it is the one fact the expert
    cannot possibly know from the corpus. Naming it is what lets the expert
    *drop* a requirement on evidence rather than have it silently deleted.
    """

    feasible: bool
    #: Requested inputs this source publishes, named back so the expert can see
    #: its hypothesis confirmed rather than merely not contradicted.
    available_fields: list[str] = field(default_factory=list)
    unsupported_fields: list[str] = field(default_factory=list)
    #: Requested inputs that exist but this calculation does not read — the tool
    #: computes them, or does not need them. The expert may drop these without
    #: weakening the method, and only the data layer knows which they are.
    unnecessary_fields: list[str] = field(default_factory=list)
    unsupported_calculation: str | None = None
    #: Tools that could serve the stated objective, named exactly.
    available_tools: list[str] = field(default_factory=list)
    max_rows_available: int | None = None
    #: What the data layer can and cannot do about *when*: coverage, gaps, the
    #: earliest and latest observation for this selection.
    temporal_constraints: list[str] = field(default_factory=list)
    #: Hard limits the expert must plan within, in its own words.
    constraints: list[str] = field(default_factory=list)
    #: What the data layer would do instead, if it would do something different.
    counter_proposal: str = ""
    #: Answers to the expert's open questions, and any the data layer raises.
    answered_questions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"feasible": self.feasible,
                "available_fields": self.available_fields,
                "unsupported_fields": self.unsupported_fields,
                "unnecessary_fields": self.unnecessary_fields,
                "unsupported_calculation": self.unsupported_calculation,
                "available_tools": self.available_tools,
                "max_rows_available": self.max_rows_available,
                "temporal_constraints": self.temporal_constraints,
                "constraints": self.constraints,
                "counter_proposal": self.counter_proposal,
                "answered_questions": self.answered_questions,
                "open_questions": self.open_questions, "notes": self.notes}

    @property
    def has_evidence(self) -> bool:
        """Did this say anything the expert can actually reason about?

        A feasibility flag and nothing else is the "approved" the architecture
        exists to avoid. Used by the negotiation to tell a real assessment from
        a degraded one when the model was unavailable.
        """
        return bool(self.available_fields or self.unsupported_fields
                    or self.unnecessary_fields or self.available_tools
                    or self.constraints or self.temporal_constraints)


@dataclass
class ResultValidation:
    """The domain expert's judgement on an execution result.

    The last gate before a number reaches a person, and the one this system was
    missing. It exists because of an observed failure: the agreed plan said a
    10-day horizon, the engine computed one day, and the reply described it as
    ten. Every field of the calculation was true; the sentence was not.

    Validation compares the *result* against the *agreed contract*, which is a
    different question from whether the calculation succeeded.
    """

    verdict: ResultVerdict = "VALID"
    checks: list[dict[str, Any]] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    interpretation: str = ""

    @property
    def blocking(self) -> bool:
        return self.verdict == "INVALID"

    def as_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "checks": self.checks,
                "mismatches": self.mismatches, "warnings": self.warnings,
                "interpretation": self.interpretation}


#: What a negotiation turn is *for*. Named phases rather than a round number
#: alone, because "round 2" tells a reader nothing while "Revised Requirement"
#: tells them exactly what changed and why they should look.
NegotiationPhase = Literal[
    "INITIAL_HYPOTHESIS", "CAPABILITY_ASSESSMENT", "REVISION",
    "VALIDATION", "FINAL_DECISION", "RESULT_VALIDATION"]


@dataclass
class NegotiationTurn:
    round: int
    speaker: Literal["domain_expert", "mcp_agent"]
    message: str
    phase: NegotiationPhase = "CAPABILITY_ASSESSMENT"
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"round": self.round, "speaker": self.speaker,
                "phase": self.phase, "message": self.message,
                "payload": self.payload}


@dataclass
class Negotiation:
    """The full transcript of the discussion, kept for the trace panel."""

    turns: list[NegotiationTurn] = field(default_factory=list)
    rounds_used: int = 0
    #: What the negotiation actually decided. `converged` is kept as a derived
    #: convenience for existing readers, but the decision is the contract: the
    #: orchestrator executes on AGREED, asks the user on NEEDS_USER_INPUT,
    #: explains on UNSUPPORTED, and admits failure on CANNOT_REACH_AGREEMENT.
    #: A boolean could not tell the last three apart.
    decision: NegotiationDecision = "CANNOT_REACH_AGREEMENT"
    #: Whether the discussion happened at all. "Not held" and "held and did not
    #: converge" are different facts about the system, and a reader deciding
    #: whether the negotiation is broken needs to be able to tell them apart.
    held: bool = True
    outcome: str = ""

    @property
    def converged(self) -> bool:
        """Derived, not stored. AGREED is the only outcome that proceeds."""
        return self.decision == "AGREED"

    def say(self, round_: int, speaker: str, message: str,
            phase: str = "CAPABILITY_ASSESSMENT",
            payload: dict[str, Any] | None = None) -> None:
        self.turns.append(NegotiationTurn(  # type: ignore[arg-type]
            round_, speaker, message, phase, payload or {}))

    def as_dict(self) -> dict[str, Any]:
        return {"turns": [t.as_dict() for t in self.turns],
                "rounds_used": self.rounds_used, "decision": self.decision,
                "converged": self.converged,
                "held": self.held, "outcome": self.outcome}


@dataclass
class AgentOutcome:
    """What the pipeline hands back to the service."""

    answer: str
    route: Route
    intent: Intent | None = None
    requirement: Requirement | None = None
    negotiation: Negotiation | None = None
    catalogue: ToolCatalogue | None = None
    tables: list[dict[str, Any]] = field(default_factory=list)
    calculation: dict[str, Any] | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    langsmith_url: str | None = None
    # A specialist A2A task left in `input-required`, so the next turn can
    # resume *that* task rather than start unrelated work. Server-side only:
    # the service stores it against the session and the client never sees it.
    #: The domain expert's judgement on the execution result, when one was
    #: sought. Absent for catalogue lookups, which do not need a second opinion.
    validation: Any = None
    waiting: dict[str, Any] | None = None
    # The turn's agent-to-agent ledger: which agent called which, how deep, how
    # long each took, and how much of the budget was spent.
    handoffs: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "route": self.route,
            "intent": self.intent.as_dict() if self.intent else None,
            "requirement": self.requirement.as_dict() if self.requirement else None,
            "negotiation": self.negotiation.as_dict() if self.negotiation else None,
            "catalogue": self.catalogue.as_dict() if self.catalogue else None,
            "tables": self.tables,
            "calculation": self.calculation,
            "trace": self.trace,
            "citations": self.citations,
            "langsmith_url": self.langsmith_url,
            "validation": (self.validation.as_dict()
                           if self.validation is not None else None),
            "waiting": self.waiting,
            "handoffs": self.handoffs,
        }
