"""The wire boundary: domain contracts in, A2A messages and artifacts out.

Everything protocol-shaped lives here so nothing protocol-shaped lives anywhere
else. An agent's own module never imports `a2a.types`; it takes and returns the
dataclasses in `agents/contracts.py`, and this module is the only place the two
vocabularies meet.

    Requirement / ToolCatalogue / ServeResponse / AgentOutcome
                          ▲                │
                          │  envelope.py   ▼
              Task.artifacts        Message.parts + Message.metadata

Three things it is responsible for, each of which was a real bug waiting to
happen:

**Skills are checked against the card.** A request names a skill id, and a skill
the target agent does not advertise is refused here rather than falling through
to an attribute error inside an executor. That is what stops an Agent Card from
quietly drifting away from the code it describes.

**Structured results stay structured.** A table, a calculation and a citation
list travel as three named A2A artifacts, not as one flattened string. The
caller can then tell narrative from data from error without parsing prose.

**Integers survive the round trip.** `Part.data` is a `google.protobuf.Value`,
and JSON has one number type: a row count of 250 comes back as `250.0`. Left
alone, that reaches a `range()` or an f-string as `250.0` and shows up in a
user-visible answer as "250.0 observations". Every rebuilt contract coerces its
integer fields explicitly rather than trusting what arrives.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from a2a.helpers.proto_helpers import (
    get_data_parts,
    new_data_artifact,
    new_data_part,
    new_message,
    new_text_part,
)
from a2a.types import Artifact, Message, Part, Task, TaskState
from a2a.types.a2a_pb2 import Role

from agents.a2a.cards import skill_ids
from agents.a2a.guardrails import CallChain
from agents.a2a.identity import AgentId
from agents.contracts import (
    AgentOutcome,
    FieldNote,
    Intent,
    Negotiation,
    NegotiationTurn,
    Requirement,
    ResultValidation,
    ServeResponse,
    TemporalScope,
    ToolCatalogue,
    ToolSpec,
)

#: The one data part every request carries, so a reader of a captured message
#: can tell an A2A envelope from arbitrary JSON.
ENVELOPE_KEY = "a2a_envelope"
ENVELOPE_VERSION = 1


class SkillNotAdvertised(ValueError):
    """A request named a skill that is not on the target agent's card."""


class MalformedEnvelope(ValueError):
    """A message arrived without a readable A2A envelope."""


# --- request ----------------------------------------------------------------


@dataclass
class SkillRequest:
    """One agent asking another to do one advertised thing.

    The fields beyond `skill` and `input` are what make the traffic auditable
    rather than merely functional: who asked, why, how deep the chain already
    is, and a digest that lets a target recognise a request it has already
    answered.
    """

    skill: str
    input: dict[str, Any] = field(default_factory=dict)
    requesting_agent: str = ""
    target_agent: str = ""
    intent: str = ""
    #: The nested call path from the user boundary to this request. Replaces a
    #: flat depth integer, which could not tell five sibling negotiation rounds
    #: (fine) from five nested calls (not fine) and refused the first because it
    #: looked like the second.
    call_chain: CallChain = field(default_factory=CallChain)
    handoff_budget: int = 0
    user_request_id: str = ""
    #: Which negotiation round and phase this call belongs to. Advisory — the
    #: bounds are enforced by the planner and the ledger — but it is what makes
    #: the handoff trail readable as a conversation.
    negotiation_round: int = 0
    negotiation_phase: str = ""

    def digest(self) -> str:
        """A stable fingerprint of *what was asked, of whom* — not of who asked.

        Identity for duplicate suppression is `(target agent, skill, canonical
        input)`, evaluated inside one turn's ledger. The target belongs in it
        because two agents may advertise a skill of the same name, and a
        fingerprint that ignored the callee would let one agent's answer stand
        in for another's. The *caller* is deliberately excluded: the same
        question asked twice is the same question whoever asks it, and that is
        exactly the loop worth catching.

        Sorting keys matters: two dictionaries with the same content and a
        different insertion order are the same request, and would otherwise get
        two different fingerprints.
        """
        blob = json.dumps({"target": self.target_agent, "skill": self.skill,
                           "input": self.input}, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def as_metadata(self) -> dict[str, Any]:
        return {
            "requesting_agent": self.requesting_agent,
            "target_agent": self.target_agent,
            "intent": self.intent,
            "call_chain": self.call_chain.encode(),
            "chain_length": self.call_chain.length,
            "handoff_budget": self.handoff_budget,
            "user_request_id": self.user_request_id,
            "negotiation_round": self.negotiation_round,
            "negotiation_phase": self.negotiation_phase,
            "request_digest": self.digest(),
            "envelope_version": ENVELOPE_VERSION,
        }


def build_request_message(request: SkillRequest, *, context_id: str,
                          task_id: str | None = None) -> Message:
    """A `Message` carrying one skill request.

    A short text part goes alongside the data part on purpose. A2A messages are
    read by humans in traces far more often than the structured half suggests,
    and "domain-expert -> mcp-agent: assess_data_requirement" is the line that
    makes a handoff legible at a glance.
    """
    target = request.target_agent or "?"
    headline = (f"{request.requesting_agent or 'client'} -> {target}: "
                f"{request.skill}")
    if request.intent:
        headline = f"{headline} ({request.intent})"
    message = new_message(
        parts=[
            new_text_part(headline),
            new_data_part({ENVELOPE_KEY: {"skill": request.skill,
                                          "input": request.input}}),
        ],
        context_id=context_id,
        task_id=task_id,
        role=Role.ROLE_USER,
    )
    message.metadata.update(request.as_metadata())
    return message


def read_request_message(message: Message, target: AgentId) -> SkillRequest:
    """Recover the skill request, refusing anything the card does not advertise."""
    if message is None:
        raise MalformedEnvelope("no message on the request")
    envelope: dict[str, Any] | None = None
    for payload in get_data_parts(message.parts):
        if isinstance(payload, dict) and ENVELOPE_KEY in payload:
            envelope = payload[ENVELOPE_KEY]
            break
    if not isinstance(envelope, dict):
        raise MalformedEnvelope(
            f"{target.value} received a message with no {ENVELOPE_KEY} data part")

    skill = str(envelope.get("skill") or "")
    advertised = skill_ids(target)
    if skill not in advertised:
        raise SkillNotAdvertised(
            f"{target.value} does not advertise a skill named {skill!r}; "
            f"its card offers {sorted(advertised)}")

    meta = _struct_to_dict(message.metadata)
    return SkillRequest(
        skill=skill,
        # The inbound half of the same problem the outbound half already fixed.
        # `requested_rows` arrived as 10000.0 and was formatted straight into a
        # warning the user reads: "Requested 10,000.0 rows".
        input=restore_counts(envelope.get("input") or {}),
        requesting_agent=str(meta.get("requesting_agent") or ""),
        target_agent=target.value,
        intent=str(meta.get("intent") or ""),
        call_chain=CallChain.parse(meta.get("call_chain")),
        handoff_budget=_int(meta.get("handoff_budget"), 0) or 0,
        user_request_id=str(meta.get("user_request_id") or ""),
        negotiation_round=_int(meta.get("negotiation_round"), 0) or 0,
        negotiation_phase=str(meta.get("negotiation_phase") or ""),
    )


# --- result -----------------------------------------------------------------


@dataclass
class SkillResult:
    """What came back, with narrative, data, status and error kept apart.

    Flattening these into one string is the failure this class exists to
    prevent: a caller that has to decide from prose whether a task completed,
    failed or is waiting for a human will eventually decide wrong.
    """

    state: str
    task_id: str = ""
    context_id: str = ""
    artifacts: dict[str, Any] = field(default_factory=dict)
    narrative: str = ""
    error: dict[str, Any] | None = None
    input_request: dict[str, Any] | None = None

    @property
    def completed(self) -> bool:
        return self.state == "completed"

    @property
    def needs_input(self) -> bool:
        return self.state == "input-required"

    @property
    def canceled(self) -> bool:
        """Called off, not broken.

        Kept apart from `failed` so a caller cannot apologise for an error that
        did not happen. A user who says "never mind" should not be told the
        gateway could not complete their request.
        """
        return self.state == "canceled"

    @property
    def failed(self) -> bool:
        return self.state in {"failed", "rejected", "unknown"}

    def artifact(self, name: str, default: Any = None) -> Any:
        return self.artifacts.get(name, default)


#: Protobuf state enum -> the spelling used in logs, traces and this codebase.
STATE_NAMES: dict[int, str] = {
    TaskState.TASK_STATE_UNSPECIFIED: "unknown",
    TaskState.TASK_STATE_SUBMITTED: "submitted",
    TaskState.TASK_STATE_WORKING: "working",
    TaskState.TASK_STATE_COMPLETED: "completed",
    TaskState.TASK_STATE_FAILED: "failed",
    TaskState.TASK_STATE_CANCELED: "canceled",
    TaskState.TASK_STATE_INPUT_REQUIRED: "input-required",
    TaskState.TASK_STATE_REJECTED: "rejected",
    TaskState.TASK_STATE_AUTH_REQUIRED: "auth-required",
}

#: Artifact names the executors publish. Named constants because the caller
#: looks them up by name, and a typo on one side is a silent `None` on the other.
ARTIFACT_REQUIREMENT = "requirement"
ARTIFACT_NEGOTIATION = "negotiation"
ARTIFACT_CATALOGUE = "catalogue"
ARTIFACT_CITATIONS = "citations"
ARTIFACT_SERVE_RESPONSE = "serve_response"
ARTIFACT_DATASET = "dataset"
ARTIFACT_CALCULATION = "calculation"
ARTIFACT_CHOICES = "choices"
ARTIFACT_OUTCOME = "outcome"
ARTIFACT_ERROR = "error"
ARTIFACT_INPUT_REQUEST = "input_request"
ARTIFACT_TITLE = "title"
ARTIFACT_ASSESSMENT = "capability_assessment"
ARTIFACT_VALIDATION = "result_validation"


def data_artifact(name: str, data: Any, description: str = "") -> Artifact:
    return new_data_artifact(name=name, data=_jsonable(data),
                             media_type="application/json",
                             description=description or None)


def artifact_parts(name: str, data: Any, description: str = "") -> list[Part]:
    return list(data_artifact(name, data, description).parts)


def read_task(task: Task) -> SkillResult:
    """Turn a finished (or interrupted) A2A task into a `SkillResult`."""
    artifacts: dict[str, Any] = {}
    for art in task.artifacts:
        payloads = get_data_parts(art.parts)
        if payloads:
            artifacts[art.name] = payloads[0]
    narrative = ""
    input_request = None
    if task.status.HasField("message"):
        narrative = "\n".join(
            p.text for p in task.status.message.parts if p.HasField("text"))
        for payload in get_data_parts(task.status.message.parts):
            if isinstance(payload, dict) and payload.get("kind") == "input_request":
                input_request = payload
    return SkillResult(
        state=STATE_NAMES.get(task.status.state, "unknown"),
        task_id=task.id,
        context_id=task.context_id,
        artifacts=artifacts,
        narrative=narrative,
        error=artifacts.get(ARTIFACT_ERROR),
        input_request=input_request or artifacts.get(ARTIFACT_INPUT_REQUEST),
    )


def failure_result(message: str, kind: str = "transport") -> SkillResult:
    """A structured failure for something that never reached an agent at all.

    A timeout, an unreachable agent and a malformed reply are not the target
    agent's answer, but the caller has to treat them the same way it treats a
    reported failure — so they arrive in the same shape.
    """
    return SkillResult(state="failed", error={"kind": kind, "message": message})


# --- contract rebuilding ----------------------------------------------------
#
# One function per dataclass that crosses the wire. Explicit rather than
# reflective, because the integer coercions below are the whole point and a
# generic rebuilder would be exactly as lossy as the JSON it reads.


def _int(value: Any, default: int | None = None) -> int | None:
    """A JSON number that means an integer, as an integer.

    Returns `default` for None and for anything that is not a whole number, so
    a corrupted payload degrades to "unstated" rather than to a float that then
    prints as `250.0` in a user-visible sentence.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return default
    return int(as_float) if as_float.is_integer() else default


def _strs(value: Any) -> list[str]:
    return [str(v) for v in (value or []) if v is not None]


def requirement_from_dict(data: dict[str, Any] | None) -> Requirement | None:
    if not data:
        return None
    return Requirement(
        task=str(data.get("task") or ""),
        answerable=bool(data.get("answerable", True)),
        fields=_strs(data.get("fields")),
        field_notes=[FieldNote(str(n.get("name") or ""),
                               n.get("verdict") or "required",  # type: ignore[arg-type]
                               str(n.get("reason") or ""))
                     for n in data.get("field_notes") or [] if isinstance(n, dict)],
        rows=_int(data.get("rows")),
        row_reason=str(data.get("row_reason") or ""),
        row_quote=data.get("row_quote"),
        grounded=bool(data.get("grounded", False)),
        tenors=_strs(data.get("tenors")),
        curve_family=str(data.get("curve_family") or "nominal"),
        temporal=TemporalScope.from_dict(data.get("temporal")),
        decision=(data.get("decision")
                  if data.get("decision") in {"AGREED", "NEEDS_USER_INPUT",
                                              "UNSUPPORTED",
                                              "CANNOT_REACH_AGREEMENT"}
                  else None),
        is_hypothesis=bool(data.get("is_hypothesis", False)),
        candidate_fields=_strs(data.get("candidate_fields")),
        open_questions=_strs(data.get("open_questions")),
        assumptions=_strs(data.get("assumptions")),
        limitations=_strs(data.get("limitations")),
        calculation=data.get("calculation"),
        # Restored, not copied: `horizon_days` is a count and it is shown
        # in the data-plan panel beside the arguments that were actually
        # used. "10.0" next to "10" invites the reader to wonder which won.
        calculation_params=restore_counts(data.get("calculation_params") or {}),
        unanswerable_reason=data.get("unanswerable_reason"),
        # Must survive the wire: it is what decides whether the user is told
        # their data cannot answer this, or that a step of the system failed.
        blocked_by=str(data.get("blocked_by") or ""),
        citations=list(data.get("citations") or []),
        warnings=_strs(data.get("warnings")),
    )


def catalogue_from_dict(data: dict[str, Any] | None) -> ToolCatalogue | None:
    if not data:
        return None
    return ToolCatalogue(
        # `kind` is what the catalogue puts on the wire — "calculation" or
        # "retrieval" — because a boolean named `executable` was being read as
        # availability. `executable` is still accepted so an in-flight payload
        # from an older peer does not silently arrive with every tool
        # unschedulable, which is exactly how this went wrong once: the sender
        # was updated, the rebuilder was not, and every risk tool crossed the
        # boundary as non-executable. The plan then reported "Available
        # calculations: none" while both MCP servers sat there advertising
        # nineteen tools.
        tools=[ToolSpec(str(t.get("name") or ""), str(t.get("description") or ""),
                        str(t.get("server") or ""),
                        (t.get("kind") == "calculation"
                         if "kind" in t else bool(t.get("executable", False))))
               for t in data.get("tools") or [] if isinstance(t, dict)],
        fields=_strs(data.get("fields")),
        tenors=_strs(data.get("tenors")),
        can_calculate=bool(data.get("can_calculate", False)),
        notes=_strs(data.get("notes")),
    )


def serve_response_from_dict(data: dict[str, Any] | None) -> ServeResponse:
    data = data or {}
    return ServeResponse(
        feasible=bool(data.get("feasible", True)),
        available_fields=_strs(data.get("available_fields")),
        unsupported_fields=_strs(data.get("unsupported_fields")),
        unnecessary_fields=_strs(data.get("unnecessary_fields")),
        unsupported_calculation=data.get("unsupported_calculation"),
        available_tools=_strs(data.get("available_tools")),
        max_rows_available=_int(data.get("max_rows_available")),
        temporal_constraints=_strs(data.get("temporal_constraints")),
        constraints=_strs(data.get("constraints")),
        counter_proposal=str(data.get("counter_proposal") or ""),
        answered_questions=_strs(data.get("answered_questions")),
        open_questions=_strs(data.get("open_questions")),
        notes=_strs(data.get("notes")),
    )


def validation_from_dict(data: dict[str, Any] | None) -> ResultValidation | None:
    """Rebuild the domain expert's judgement on an execution result."""
    if not data:
        return None
    verdict = data.get("verdict")
    if verdict not in {"VALID", "VALID_WITH_WARNINGS", "INVALID"}:
        # An unreadable verdict is not a pass. Defaulting to VALID here would
        # make a broken validator indistinguishable from a satisfied one.
        verdict = "INVALID"
    return ResultValidation(
        verdict=verdict,  # type: ignore[arg-type]
        checks=list(data.get("checks") or []),
        mismatches=_strs(data.get("mismatches")),
        warnings=_strs(data.get("warnings")),
        interpretation=str(data.get("interpretation") or ""),
    )


def negotiation_from_dict(data: dict[str, Any] | None) -> Negotiation | None:
    if not data:
        return None
    negotiation = Negotiation(
        rounds_used=_int(data.get("rounds_used"), 0) or 0,
        decision=(data.get("decision")
                  if data.get("decision") in {"AGREED", "NEEDS_USER_INPUT",
                                              "UNSUPPORTED",
                                              "CANNOT_REACH_AGREEMENT"}
                  else "CANNOT_REACH_AGREEMENT"),
        held=bool(data.get("held", True)),
        outcome=str(data.get("outcome") or ""),
    )
    negotiation.turns = [
        NegotiationTurn(round=_int(t.get("round"), 0) or 0,
                        speaker=t.get("speaker") or "mcp_agent",  # type: ignore[arg-type]
                        message=str(t.get("message") or ""),
                        phase=t.get("phase") or "CAPABILITY_ASSESSMENT",  # type: ignore[arg-type]
                        # The turn payload is a free-form snapshot of whatever
                        # was on the table that round, so it has no typed
                        # rebuilder - but it is shown in the discussion panel,
                        # where a row count reading `250.0` is the same small
                        # lie it would be anywhere else.
                        payload=restore_counts(t.get("payload") or {}))
        for t in data.get("turns") or [] if isinstance(t, dict)
    ]
    return negotiation


def intent_from_dict(data: dict[str, Any] | None) -> Intent | None:
    if not data:
        return None
    return Intent(
        route=data.get("route") or "data_request",  # type: ignore[arg-type]
        reasoning=str(data.get("reasoning") or ""),
        task=str(data.get("task") or ""),
        direct_answer=str(data.get("direct_answer") or ""),
        requested_fields=_strs(data.get("requested_fields")),
        requested_rows=_int(data.get("requested_rows")),
        question=str(data.get("question") or ""),
        options=[{"label": str(o.get("label") or ""), "value": str(o.get("value") or "")}
                 for o in data.get("options") or [] if isinstance(o, dict)],
    )


#: Keys whose value is a count, wherever they appear. Restored to `int` on the
#: way back because a count is printed — "250.0 row(s)" in a data-plan panel is
#: a small lie about the one thing a row count exists to state. Rates, prices
#: and distances never appear under these names, so nothing that is genuinely
#: fractional is rounded here.
COUNT_KEYS = frozenset({
    "rows", "row_count", "displayed", "rounds_used", "round", "requested_rows",
    "rows_delivered", "rows_agreed", "rows_requested_by_user",
    "max_rows_available", "observation_count", "sequence", "depth",
    "duration_ms", "handoffs_used", "handoff_limit", "depth_limit",
    "duplicates_suppressed", "attempt", "retries_remaining",
    "lookback_days", "negotiation_round", "chain_length", "max_chain_reached", "negotiation_rounds", "chain_limit", "reentry_limit",
    # From the risk engine, through the calculation artifact.
    "scenarios_used", "horizon_days", "trading_days", "point_count",
})


def restore_counts(value: Any) -> Any:
    """Walk a decoded payload turning integral floats under count keys back to int.

    Applied to the free-form structures — the decision trace, the tables — that
    have no typed rebuilder of their own. The typed contracts coerce their own
    fields and do not need this.
    """
    if isinstance(value, dict):
        # `_int` falls back to the value itself, never to None. A count key that
        # somehow carries a fractional number is odd, but blanking it would turn
        # a surprising number into a missing one — strictly worse, and harder to
        # notice.
        return {key: (_int(item, item) if key in COUNT_KEYS and
                      isinstance(item, float) else restore_counts(item))
                for key, item in value.items()}
    if isinstance(value, list):
        return [restore_counts(item) for item in value]
    return value


def outcome_from_dict(data: dict[str, Any]) -> AgentOutcome:
    """Rebuild the orchestrator's turn outcome from its A2A artifact."""
    data = dict(data)
    data["tables"] = restore_counts(data.get("tables") or [])
    data["trace"] = restore_counts(data.get("trace") or [])
    # `waiting` carries the clarification counters back to the service, which
    # hands them to the next turn. A retry count that reads 1.0 is the same
    # small lie as a row count that does.
    data["waiting"] = restore_counts(data.get("waiting")) if data.get("waiting") else None
    data["calculation"] = (restore_counts(data.get("calculation"))
                           if data.get("calculation") else None)
    return AgentOutcome(
        answer=str(data.get("answer") or ""),
        route=data.get("route") or "data_request",  # type: ignore[arg-type]
        intent=intent_from_dict(data.get("intent")),
        requirement=requirement_from_dict(data.get("requirement")),
        negotiation=negotiation_from_dict(data.get("negotiation")),
        catalogue=catalogue_from_dict(data.get("catalogue")),
        tables=list(data.get("tables") or []),
        calculation=data.get("calculation"),
        trace=list(data.get("trace") or []),
        citations=list(data.get("citations") or []),
        langsmith_url=data.get("langsmith_url"),
        validation=validation_from_dict(data.get("validation")),
        waiting=data.get("waiting"),
        handoffs=data.get("handoffs"),
    )


def execution_from_dict(dataset: dict[str, Any] | None,
                        calculation: dict[str, Any] | None,
                        summary: dict[str, Any] | None) -> dict[str, Any]:
    """Reassemble the MCP agent's execution result from its three artifacts.

    The shape returned matches what `McpAgent.execute` produces in-process, so
    the orchestrator's own logic does not have to know whether the data came
    back over A2A or from a direct call. Row counts are re-integered here: they
    are printed to the user and compared against what was asked for.
    """
    summary = summary or {}
    table = dataset or {}
    if table:
        table = dict(table)
        table["row_count"] = _int(table.get("row_count"), 0) or 0
        table["displayed"] = _int(table.get("displayed"), 0) or 0
    return {
        "table": table,
        "rows_delivered": _int(summary.get("rows_delivered"), 0) or 0,
        "rows_agreed": _int(summary.get("rows_agreed")),
        "rows_requested_by_user": _int(summary.get("rows_requested_by_user")),
        "window_unstated": bool(summary.get("window_unstated", False)),
        "calculation": calculation,
        "notes": _strs(summary.get("notes")),
    }


# --- internals --------------------------------------------------------------


def _struct_to_dict(struct: Any) -> dict[str, Any]:
    from google.protobuf.json_format import MessageToDict

    try:
        return MessageToDict(struct) or {}
    except Exception:  # noqa: BLE001 - metadata is advisory, never load-bearing
        return {}


def _jsonable(value: Any) -> Any:
    """Make a payload safe for `google.protobuf.Value`.

    Dates, Decimals and dataclasses reach here from the data layer. `json.dumps`
    with `default=str` is the same normalisation the rest of the repository
    already applies to tool payloads, so nothing new is being decided here.
    """
    return json.loads(json.dumps(value, default=str))
