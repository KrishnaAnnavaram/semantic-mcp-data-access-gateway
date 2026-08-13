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
    name: str
    description: str
    server: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "server": self.server}


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

    def as_dict(self) -> dict[str, Any]:
        return {"tools": [t.as_dict() for t in self.tools], "fields": self.fields,
                "tenors": self.tenors, "can_calculate": self.can_calculate,
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
    calculation: str | None = None        # a tool name, when the task needs maths
    unanswerable_reason: str | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"task": self.task, "answerable": self.answerable, "fields": self.fields,
                "field_notes": [n.as_dict() for n in self.field_notes],
                "rows": self.rows, "row_reason": self.row_reason,
                "row_quote": self.row_quote, "grounded": self.grounded,
                "tenors": self.tenors, "calculation": self.calculation,
                "unanswerable_reason": self.unanswerable_reason,
                "citations": self.citations, "warnings": self.warnings}


@dataclass
class ServeResponse:
    """The MCP agent's answer to a proposed requirement, before any fetch.

    This is the half of the discussion that keeps the plan honest: the domain
    expert knows what the *method* needs, and only the MCP agent knows what the
    *data source* can actually serve. Neither alone is enough.
    """

    feasible: bool
    unsupported_fields: list[str] = field(default_factory=list)
    unsupported_calculation: str | None = None
    max_rows_available: int | None = None
    counter_proposal: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"feasible": self.feasible,
                "unsupported_fields": self.unsupported_fields,
                "unsupported_calculation": self.unsupported_calculation,
                "max_rows_available": self.max_rows_available,
                "counter_proposal": self.counter_proposal, "notes": self.notes}


@dataclass
class NegotiationTurn:
    round: int
    speaker: Literal["domain_expert", "mcp_agent"]
    message: str
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"round": self.round, "speaker": self.speaker,
                "message": self.message, "payload": self.payload}


@dataclass
class Negotiation:
    """The full transcript of the discussion, kept for the trace panel."""

    turns: list[NegotiationTurn] = field(default_factory=list)
    rounds_used: int = 0
    converged: bool = False
    outcome: str = ""

    def say(self, round_: int, speaker: str, message: str,
            payload: dict[str, Any] | None = None) -> None:
        self.turns.append(NegotiationTurn(round_, speaker, message, payload or {}))  # type: ignore[arg-type]

    def as_dict(self) -> dict[str, Any]:
        return {"turns": [t.as_dict() for t in self.turns],
                "rounds_used": self.rounds_used, "converged": self.converged,
                "outcome": self.outcome}


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
        }
