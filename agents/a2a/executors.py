"""The hosting half of A2A: one `AgentExecutor` per existing agent.

An executor is an adapter and nothing else. It reads a skill request off the
wire, checks that the caller is allowed to ask for it, runs the agent's own
domain object, and publishes the answer as named artifacts and a task state.
None of the reasoning moved here — `OrchestratorAgent`, `DomainExpertAgent` and
`McpAgent` are the same classes with the same prompts they had before A2A
existed, and this module imports them rather than reimplementing them.

    A2A message ──► executor ──► agent domain object ──► artifacts + task state

Three rules hold for every executor below.

**Domain work never runs on the event loop.** The agents are synchronous and
call into blocking bridges (Qdrant, the MCP child processes, HTTP model APIs).
Each executor hands its work to a worker thread, which is what allows a nested
A2A call — the domain expert asking the MCP agent to assess a requirement —
without the loop that has to serve that call being blocked by the call that made
it.

**Nothing raw escapes.** An unexpected exception becomes a failed task with a
structured error artifact, not a stack trace on the wire. The orchestrator turns
that into a sentence; a traceback never reaches a browser.

**Who may call what is checked, not assumed.** Each skill names its permitted
callers. That is what makes "why was this agent called?" answerable, and it is
the mechanism that stops the frontend — or any other client that finds the
mounted endpoint — from driving a specialist directly.

Be precise about what that check is: **internal caller authorization**, a
logical boundary between components inside one trusted process, read from
message metadata the caller supplied. It is not authentication — nothing here
verifies that a message claiming to come from the orchestrator did. For a
local-development system where all three agents share a process and the only
network listener is the developer's own service, a logical boundary is the right
weight; it makes the architecture enforceable and reviewable without pretending
to a security property it does not have. Deploying an agent on a host someone
else can reach is the point at which this would need real authentication, and
that is a deployment change, not a code comment.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, ClassVar

from a2a.helpers.proto_helpers import (
    new_data_part,
    new_message,
    new_task_from_user_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Task, TaskState
from a2a.types.a2a_pb2 import Role

from agents.a2a import elicitation as elicit
from agents.a2a.envelope import (
    ARTIFACT_ASSESSMENT,
    ARTIFACT_CALCULATION,
    ARTIFACT_CATALOGUE,
    ARTIFACT_CHOICES,
    ARTIFACT_CITATIONS,
    ARTIFACT_DATASET,
    ARTIFACT_ERROR,
    ARTIFACT_INPUT_REQUEST,
    ARTIFACT_NEGOTIATION,
    ARTIFACT_OUTCOME,
    ARTIFACT_REQUIREMENT,
    ARTIFACT_SERVE_RESPONSE,
    ARTIFACT_TITLE,
    ARTIFACT_VALIDATION,
    MalformedEnvelope,
    SkillNotAdvertised,
    SkillRequest,
    artifact_parts,
    catalogue_from_dict,
    read_request_message,
    requirement_from_dict,
)
from agents.a2a.guardrails import LedgerRegistry, max_chain, max_reentry
from agents.a2a.identity import AgentId

LOGGER = logging.getLogger("agents.a2a.executors")

#: Artifact name -> a one-line description, so a reader of a captured task can
#: tell what each artifact is without consulting this file.
DESCRIPTIONS = {
    ARTIFACT_REQUIREMENT: "The data requirement, with its citations and warnings.",
    ARTIFACT_NEGOTIATION: "Transcript of the bounded discussion with the data layer.",
    ARTIFACT_CATALOGUE: "The tools, fields and tenors actually connected.",
    ARTIFACT_CITATIONS: "Knowledge chunks retrieved, with distances.",
    ARTIFACT_SERVE_RESPONSE: "What the data layer can and cannot serve.",
    ARTIFACT_DATASET: "The table that was fetched, with provenance.",
    ARTIFACT_CALCULATION: "The risk calculation and its arguments.",
    ARTIFACT_CHOICES: "Real portfolios, scenarios and curve families.",
    ARTIFACT_OUTCOME: "The orchestrator's full outcome for this turn.",
    ARTIFACT_ERROR: "Why this task failed, in a form a caller can act on.",
    ARTIFACT_INPUT_REQUEST: "What information is missing, and who must supply it.",
    ARTIFACT_TITLE: "A short name for the conversation.",
    ARTIFACT_ASSESSMENT: "What the data layer can and cannot serve, with evidence.",
    ARTIFACT_VALIDATION: "Whether the result matches the agreed analytical contract.",
}


@dataclass(frozen=True)
class ExecutionContext:
    """The A2A task an agent's domain code is currently running inside.

    Published so that "the specialists are only ever reached over A2A" is a
    checkable claim rather than a stylistic one. An import test proves the
    orchestrator cannot *name* a specialist; this proves that when a specialist
    actually ran, it ran inside a task — with an id that has to appear in the
    turn's handoff ledger. A hidden direct call would execute with no context at
    all, and the integration test fails on the spot.

    `asyncio.to_thread` copies the calling task's context, so the value set here
    before the hand-off is visible on the worker thread that does the work, and
    nowhere else: a nested A2A call runs in a new task with its own context and
    sets its own.
    """

    agent: str
    skill: str
    task_id: str
    context_id: str
    user_request_id: str
    #: The nested call path that reached this execution, so a reviewer can see
    #: not only that specialist work ran inside A2A but exactly how it was
    #: reached.
    call_chain: tuple[str, ...] = ()


_ACTIVE_EXECUTION: contextvars.ContextVar[ExecutionContext | None] = \
    contextvars.ContextVar("a2a_active_execution", default=None)


def active_execution() -> ExecutionContext | None:
    """The A2A task this thread is executing for, or None if there is none."""
    return _ACTIVE_EXECUTION.get()


@dataclass
class Outcome:
    """What an executor produced, before it becomes a task."""

    artifacts: list[tuple[str, Any]] = field(default_factory=list)
    narrative: str = ""
    state: str = "completed"
    input_request: dict[str, Any] | None = None
    #: Set on a failure the agent itself decided on, as opposed to an exception.
    #: Published as the `error` artifact so the caller can tell one failure from
    #: another instead of only knowing that something went wrong.
    error_kind: str = "agent_error"

    def add(self, name: str, data: Any) -> Outcome:
        if data is not None:
            self.artifacts.append((name, data))
        return self


class SkillRefused(RuntimeError):
    """The request will not be attempted: wrong caller, wrong skill, too deep."""

    def __init__(self, reason: str, kind: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.kind = kind


class BaseAgentExecutor(AgentExecutor):
    """Shared lifecycle: admit, work on a thread, publish, terminate."""

    agent_id: AgentId
    #: skill id -> the agent names allowed to ask for it. `user-boundary` is the
    #: FastAPI service acting for the human; only the orchestrator accepts it.
    #: Internal caller *authorization*, from caller-supplied metadata — a
    #: logical boundary between trusted components, not authentication.
    callers: ClassVar[dict[str, set[str]]] = {}

    def __init__(self, ledgers: LedgerRegistry) -> None:
        self.ledgers = ledgers

    # -- AgentExecutor -------------------------------------------------------

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            # A2A requires the Task itself before any status update; without it
            # the framework rejects the first event and the caller sees a
            # protocol error rather than the agent's answer.
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            request = read_request_message(context.message, self.agent_id)
            self._admit(request)
        except (SkillNotAdvertised, MalformedEnvelope, SkillRefused) as refusal:
            kind = getattr(refusal, "kind", "bad_request")
            LOGGER.warning("%s rejected a request (%s): %s",
                           self.agent_id.value, kind, refusal)
            await updater.add_artifact(
                artifact_parts(ARTIFACT_ERROR,
                               {"kind": kind, "message": str(refusal)},
                               DESCRIPTIONS[ARTIFACT_ERROR]),
                name=ARTIFACT_ERROR)
            await updater.update_status(
                TaskState.TASK_STATE_REJECTED,
                message=self._text(task, str(refusal)))
            return

        LOGGER.info("a2a exec | turn=%s %s.%s task=%s chain=%s caller=%s%s",
                    request.user_request_id, self.agent_id.value, request.skill,
                    task.id, request.call_chain.length,
                    request.requesting_agent or "-",
                    f" r{request.negotiation_round}/{request.negotiation_phase}"
                    if request.negotiation_round else "")
        await updater.update_status(TaskState.TASK_STATE_WORKING)

        token = _ACTIVE_EXECUTION.set(ExecutionContext(
            agent=self.agent_id.value, skill=request.skill, task_id=task.id,
            context_id=task.context_id, user_request_id=request.user_request_id,
            call_chain=request.call_chain.steps))
        try:
            outcome = await asyncio.to_thread(self.handle, request, task)
        except Exception as exc:
            LOGGER.exception("%s.%s failed", self.agent_id.value, request.skill)
            await updater.add_artifact(
                artifact_parts(ARTIFACT_ERROR,
                               {"kind": "agent_error", "skill": request.skill,
                                "message": f"{type(exc).__name__}: {exc}"},
                               DESCRIPTIONS[ARTIFACT_ERROR]),
                name=ARTIFACT_ERROR)
            await updater.update_status(
                TaskState.TASK_STATE_FAILED,
                message=self._text(
                    task,
                    f"{self.agent_id.value} could not complete {request.skill}."))
            return
        finally:
            _ACTIVE_EXECUTION.reset(token)

        for name, data in outcome.artifacts:
            await updater.add_artifact(
                artifact_parts(name, data, DESCRIPTIONS.get(name, "")), name=name)

        if outcome.state == "input-required":
            await updater.update_status(
                TaskState.TASK_STATE_INPUT_REQUIRED,
                message=self._input_message(task, outcome))
            return
        if outcome.state == "canceled":
            # The user called it off. Distinct from `failed` on purpose: nothing
            # went wrong, and a reply that apologises for an error would be
            # describing something that did not happen.
            await updater.update_status(
                TaskState.TASK_STATE_CANCELED,
                message=self._text(task, outcome.narrative))
            return
        if outcome.state == "failed":
            await updater.add_artifact(
                artifact_parts(ARTIFACT_ERROR,
                               {"kind": outcome.error_kind, "skill": request.skill,
                                "message": outcome.narrative},
                               DESCRIPTIONS[ARTIFACT_ERROR]),
                name=ARTIFACT_ERROR)
            await updater.update_status(
                TaskState.TASK_STATE_FAILED,
                message=self._text(task, outcome.narrative))
            return
        await updater.update_status(
            TaskState.TASK_STATE_COMPLETED,
            message=self._text(task, outcome.narrative))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        task_id = task.id if task else (context.task_id or "")
        context_id = task.context_id if task else (context.context_id or "")
        LOGGER.info("a2a cancel | %s task=%s", self.agent_id.value, task_id)
        if task_id:
            await TaskUpdater(event_queue, task_id, context_id).update_status(
                TaskState.TASK_STATE_CANCELED)

    # -- subclass contract ---------------------------------------------------

    def handle(self, request: SkillRequest, task: Task) -> Outcome:
        raise NotImplementedError

    # -- admission -----------------------------------------------------------

    def _admit(self, request: SkillRequest) -> None:
        """Internal caller authorization. Logical, not cryptographic.

        The caller identifies itself in message metadata and this agent takes
        it at its word. That is honest for three agents sharing one process
        behind one developer's service, and it is what makes the architecture
        checkable — every refusal below is a boundary a test can exercise. It
        would not survive an untrusted network, and it is not claimed to.
        """
        allowed = self.callers.get(request.skill)
        caller = request.requesting_agent or "unknown"
        if allowed is not None and caller not in allowed:
            raise SkillRefused(
                f"{caller!r} may not call {self.agent_id.value}.{request.skill}; "
                f"that skill is served to {sorted(allowed)}.",
                kind="caller_not_permitted")
        # Enforced against this agent's own configuration rather than against
        # anything the caller declared. A caller is not a trustworthy source for
        # the limit it is being held to, and an agent reached from another host
        # is where that stops being a theoretical point.
        #
        # Two separate checks, because nesting and cycling are different
        # failures. A negotiation issues sibling calls at constant chain length;
        # only genuine nesting grows it, and only a genuine cycle repeats a
        # pair. The flat counter this replaced conflated the two and refused
        # legitimate collaboration to prevent a recursion that was not happening.
        chain = request.call_chain
        if chain.length < 1:
            raise SkillRefused(
                "a request arrived with an empty call chain; every A2A call "
                "must record the path that reached it.", kind="chain_missing")
        if chain.length > max_chain():
            raise SkillRefused(
                f"call chain is {chain.length} deep, beyond the limit of "
                f"{max_chain()}: {chain}", kind="chain_limit")
        here = chain.reentries(self.agent_id.value, request.skill)
        if here > max_reentry():
            raise SkillRefused(
                f"{self.agent_id.value}.{request.skill} appears {here} times on "
                f"this call chain, beyond the re-entry limit of {max_reentry()}. "
                f"This is a cycle: {chain}", kind="reentry_limit")

    # -- message helpers -----------------------------------------------------

    @staticmethod
    def _text(task: Task, text: str):
        """A narrative status message, or nothing when there is nothing to say."""
        if not text:
            return None
        return new_message([new_text_part(text)], context_id=task.context_id,
                           task_id=task.id, role=Role.ROLE_AGENT)

    @staticmethod
    def _input_message(task: Task, outcome: Outcome):
        """The question, in both channels.

        Prose for whoever will read it, and the same question as structured data
        beside it so the orchestrator can act on the field names and the allowed
        answers without parsing the sentence.
        """
        payload = outcome.input_request or {}
        return new_message(
            [new_text_part(outcome.narrative or payload.get("question") or
                           "More information is required to continue."),
             new_data_part(payload)],
            context_id=task.context_id, task_id=task.id, role=Role.ROLE_AGENT)


# --- MCP agent --------------------------------------------------------------


class McpAgentExecutor(BaseAgentExecutor):
    """Hosts `McpAgent`: the data layer's representative on the A2A network.

    It is the only executor that can stop a task in `input-required`, because it
    is the only one sitting in front of servers that can raise a question — and
    it answers that question to nobody. It hands it upward and waits.
    """

    agent_id = AgentId.MCP
    callers: ClassVar[dict[str, set[str]]] = {
        # The discussion is domain-expert-to-data-layer, so those two skills are
        # served to the expert. Execution and choices belong to the turn's owner.
        "describe_data_capabilities": {AgentId.DOMAIN_EXPERT.value,
                                       AgentId.ORCHESTRATOR.value},
        "assess_data_requirement": {AgentId.DOMAIN_EXPERT.value},
        "execute_data_plan": {AgentId.ORCHESTRATOR.value},
        "list_data_choices": {AgentId.ORCHESTRATOR.value},
        "provide_input": {AgentId.ORCHESTRATOR.value},
    }
    #: How many interrupted plans to remember. One per waiting conversation;
    #: far more than a local system ever has open at once.
    WAITING_CAPACITY = 128

    def __init__(self, ledgers: LedgerRegistry, agent) -> None:
        super().__init__(ledgers)
        self.agent = agent
        self._waiting: dict[str, dict[str, Any]] = {}
        self._waiting_lock = threading.Lock()

    def handle(self, request: SkillRequest, task: Task) -> Outcome:
        if request.skill == "describe_data_capabilities":
            catalogue = self.agent.catalogue()
            return Outcome(narrative=(
                f"{len(catalogue.tools)} tool(s) connected; "
                f"calculations {'available' if catalogue.can_calculate else 'unavailable'}."
            )).add(ARTIFACT_CATALOGUE, catalogue.as_dict())

        if request.skill == "assess_data_requirement":
            requirement = requirement_from_dict(request.input.get("requirement"))
            catalogue = catalogue_from_dict(request.input.get("catalogue"))
            if requirement is None or catalogue is None:
                return Outcome(state="failed",
                               narrative="assess_data_requirement needs both a "
                                         "requirement and a catalogue.")
            response = self.agent.assess(requirement, catalogue)
            return Outcome(narrative=response.counter_proposal or
                           ("Can serve this as proposed." if response.feasible
                            else "Cannot serve this as proposed.")
                           ).add(ARTIFACT_SERVE_RESPONSE, response.as_dict())

        if request.skill == "list_data_choices":
            return Outcome(narrative="Real portfolios, scenarios and curve families."
                           ).add(ARTIFACT_CHOICES, self.agent.choices())

        if request.skill == "execute_data_plan":
            requirement = requirement_from_dict(request.input.get("requirement"))
            if requirement is None:
                return Outcome(state="failed",
                               narrative="execute_data_plan needs a requirement.")
            return self._run(task, requirement,
                             request.input.get("rows_requested_by_user"),
                             answers=None, may_wait=True)

        if request.skill == "provide_input":
            return self._resume(task, request)

        return Outcome(state="failed",
                       narrative=f"unhandled skill {request.skill!r}")

    # -- execution + elicitation --------------------------------------------

    def _run(self, task: Task, requirement, rows_requested: Any,
             answers: dict[str, Any] | None, may_wait: bool) -> Outcome:
        result = self.agent.execute(requirement, answers)
        pending = result.get("pending_input")

        if pending and may_wait:
            payload = elicit.input_request_payload(pending)
            self._remember(task.id, {"requirement": requirement.as_dict(),
                                     "rows_requested_by_user": rows_requested,
                                     "input_request": payload})
            LOGGER.info("a2a input-required | mcp-agent task=%s fields=%s",
                        task.id, payload.get("required_information"))
            return Outcome(
                state="input-required",
                narrative=payload.get("question") or
                          "The data layer needs a decision it cannot make.",
                input_request=payload,
            ).add(ARTIFACT_INPUT_REQUEST, payload)

        notes = list(result.get("notes") or [])
        if pending:
            # A second question on a resumed call would be a loop. The tool's own
            # declined path is a labelled, honest result, so it is reported with
            # the reason attached rather than asked again.
            notes.append(
                "The data layer raised a further question that could not be "
                "answered from what you supplied, so its unfiltered result is "
                "reported and nothing was chosen on your behalf.")
        summary = {"rows_delivered": result.get("rows_delivered", 0),
                   "rows_agreed": result.get("rows_agreed"),
                   "rows_requested_by_user": rows_requested,
                   "window_unstated": result.get("window_unstated", False),
                   "notes": notes}
        outcome = Outcome(narrative=f"Fetched {result.get('rows_delivered', 0):,} row(s).")
        outcome.add(ARTIFACT_DATASET, result.get("table") or {})
        outcome.add(ARTIFACT_CALCULATION, result.get("calculation"))
        outcome.add("summary", summary)
        return outcome

    def _resume(self, task: Task, request: SkillRequest) -> Outcome:
        """Continue an interrupted task with what the user said.

        Four outcomes, in the order they are tested:

        **Refused.** "cancel", "never mind" — the user ended the exchange. The
        task is cancelled. Running the plan anyway because it was already half
        set up would be doing work that was just called off.

        **Answered.** The reply names one of the allowed values; the plan runs
        with it and the task completes.

        **Not an answer, retries left.** The task stays in `input-required` and
        the question goes back up. This is the case that used to terminate: a
        user who replies "30 year Treasury" to "nominal or real?" has not
        refused and has not answered, and declining on their behalf discards a
        request they still want served.

        **Not an answer, retries exhausted.** The plan runs on the tool's own
        declined path — a labelled, honest result — and the task completes. The
        loop is bounded by attempt count, not by patience.
        """
        waiting = self._peek(task.id)
        if waiting is None:
            # The commonest cause is a restarted service: the browser still
            # holds a session whose waiting task died with the old process.
            # Named so the orchestrator can recover from it — treating the
            # user's next message as a new question — rather than reporting a
            # failure for something they cannot see and did not cause.
            return Outcome(state="failed", error_kind="no_pending_task",
                           narrative="There is no interrupted plan on this task "
                                     "to resume; nothing was assumed.")
        requirement = requirement_from_dict(waiting["requirement"])
        payload = waiting["input_request"]
        reply = str(request.input.get("reply") or "")
        rows = waiting.get("rows_requested_by_user")

        if elicit.is_refusal(reply):
            self._forget(task.id)
            LOGGER.info("a2a cancelled by the user | mcp-agent task=%s", task.id)
            return Outcome(state="canceled",
                           narrative="Cancelled at your request. Nothing was "
                                     "fetched and nothing was chosen for you.")

        answers = request.input.get("answers")
        if not isinstance(answers, dict) or not answers:
            answers = elicit.match_answer(reply, payload)

        if answers:
            self._forget(task.id)
            LOGGER.info("a2a resume | mcp-agent task=%s answered=%s",
                        task.id, sorted(answers))
            return self._run(task, requirement, rows, answers=answers,
                             may_wait=False)

        if int(payload.get("retries_remaining") or 0) > 0:
            retried = elicit.retry_payload(payload, reply)
            waiting["input_request"] = retried
            self._remember(task.id, waiting)
            LOGGER.info("a2a input-required again | mcp-agent task=%s attempt=%d "
                        "retries_remaining=%d", task.id, retried["attempt"],
                        retried["retries_remaining"])
            return Outcome(
                state="input-required",
                narrative=elicit.question_for_user(retried),
                input_request=retried,
            ).add(ARTIFACT_INPUT_REQUEST, retried)

        self._forget(task.id)
        LOGGER.info("a2a resume | mcp-agent task=%s exhausted its clarification "
                    "attempts; continuing on the declined path", task.id)
        return self._run(task, requirement, rows, answers=None, may_wait=False)

    def _remember(self, task_id: str, state: dict[str, Any]) -> None:
        with self._waiting_lock:
            self._waiting[task_id] = state
            while len(self._waiting) > self.WAITING_CAPACITY:
                self._waiting.pop(next(iter(self._waiting)))

    def _peek(self, task_id: str) -> dict[str, Any] | None:
        """Read the interrupted plan without discarding it.

        A resume that ends in another `input-required` has to leave the plan
        where it was; popping first and putting it back is a window in which a
        concurrent retry finds nothing to resume.
        """
        with self._waiting_lock:
            return self._waiting.get(task_id)

    def _forget(self, task_id: str) -> dict[str, Any] | None:
        with self._waiting_lock:
            return self._waiting.pop(task_id, None)


# --- domain expert ----------------------------------------------------------


class DomainExpertExecutor(BaseAgentExecutor):
    """Hosts `DomainExpertAgent` and the bounded discussion it runs.

    The discussion is the one place in this system where two specialists talk to
    each other: the planner calls the MCP agent over A2A for the catalogue and
    for each round of assessment. That is the shape the architecture has always
    documented; before A2A it was a loop in the pipeline standing in for a
    conversation that never actually crossed an agent boundary.
    """

    agent_id = AgentId.DOMAIN_EXPERT
    callers: ClassVar[dict[str, set[str]]] = {
        "derive_data_requirement": {AgentId.ORCHESTRATOR.value},
        # Result validation is requested by the workflow authority, not by the
        # agent that produced the number. Keeping the orchestrator in the middle
        # is what stops the MCP agent certifying its own output.
        "validate_result": {AgentId.ORCHESTRATOR.value},
    }

    def __init__(self, ledgers: LedgerRegistry, agent, network) -> None:
        super().__init__(ledgers)
        self.agent = agent
        self.network = network

    def handle(self, request: SkillRequest, task: Task) -> Outcome:
        from agents.a2a.ports import A2ADataLayer
        from agents.planning import DataPlanner

        if request.skill == "validate_result":
            return self._validate(request)

        ledger = self.ledgers.find(request.user_request_id, task.context_id)
        data_layer = A2ADataLayer(
            self.network.link(AgentId.MCP), self.network.loop, ledger,
            requesting_agent=self.agent_id.value, chain=request.call_chain)

        plan = DataPlanner(self.agent, data_layer).plan(
            question=str(request.input.get("question") or ""),
            task=str(request.input.get("task") or ""),
            requested_fields=request.input.get("requested_fields") or [],
            requested_rows=request.input.get("requested_rows"),
            prior_plan=request.input.get("prior_plan"),
            revalidation_reason=str(request.input.get("revalidation_reason") or ""),
        )

        rows = plan.requirement.rows
        narrative = (
            f"{plan.negotiation.decision} after "
            f"{plan.negotiation.rounds_used} negotiation round(s): "
            f"{len(plan.requirement.fields)} field(s), "
            f"{rows if rows is not None else 'window unstated'} row(s), "
            f"{plan.requirement.temporal.describe()}.")
        return (Outcome(narrative=narrative)
                .add(ARTIFACT_REQUIREMENT, plan.requirement.as_dict())
                .add(ARTIFACT_NEGOTIATION, plan.negotiation.as_dict())
                .add(ARTIFACT_CATALOGUE, plan.catalogue.as_dict())
                .add(ARTIFACT_CITATIONS, [c.as_dict() for c in plan.chunks]))

    def _validate(self, request: SkillRequest) -> Outcome:
        """Judge an execution result against the contract that was agreed.

        Deliberately a separate skill rather than a step inside execution: the
        agent that computed a number is the wrong one to certify it, and the
        expert that agreed the plan is the only one that knows what was
        promised.
        """
        requirement = requirement_from_dict(request.input.get("requirement"))
        if requirement is None:
            return Outcome(state="failed", error_kind="bad_request",
                           narrative="validate_result needs the agreed requirement.")
        validation = self.agent.validate_result(
            requirement, request.input.get("calculation"),
            request.input.get("summary") or {})
        return (Outcome(narrative=f"{validation.verdict}: "
                                  f"{validation.interpretation[:160]}")
                .add(ARTIFACT_VALIDATION, validation.as_dict()))


# --- orchestrator -----------------------------------------------------------


class OrchestratorExecutor(BaseAgentExecutor):
    """Hosts the orchestrator: the only agent a user's words reach.

    Its permitted caller is the service acting for the human. The two specialist
    agents are not on that list, and a specialist that tried to call the
    orchestrator — the shape a "let me ask the user" bypass would take — is
    rejected with the reason recorded.
    """

    agent_id = AgentId.ORCHESTRATOR
    USER_BOUNDARY = "user-boundary"
    callers: ClassVar[dict[str, set[str]]] = {
        "handle_user_turn": {USER_BOUNDARY},
        "relay_user_input": {USER_BOUNDARY},
        "summarise_session": {USER_BOUNDARY},
    }

    def __init__(self, ledgers: LedgerRegistry, agent, network) -> None:
        super().__init__(ledgers)
        self.agent = agent
        self.network = network

    def handle(self, request: SkillRequest, task: Task) -> Outcome:
        from agents.pipeline import AgentPipeline

        if request.skill == "summarise_session":
            title = self.agent.summarise_session(request.input.get("messages") or [])
            return Outcome(narrative=title or "").add(ARTIFACT_TITLE, {"title": title})

        # `find`, not `open`. The turn's budget was opened by whoever sent this
        # message and already counts the hop that arrived here; opening a second
        # ledger would reset the count and make the turn limit unenforceable at
        # exactly the point it matters. The caller that opened it also closes
        # it — this executor borrows it.
        ledger = self.ledgers.find(request.user_request_id, task.context_id)
        pipeline = AgentPipeline(orchestrator=self.agent, network=self.network,
                                 ledger=ledger, chain=request.call_chain)
        if request.skill == "relay_user_input":
            outcome = pipeline.resume(
                reply=str(request.input.get("query") or ""),
                waiting=request.input.get("waiting") or {},
                history=request.input.get("history") or [])
        else:
            outcome = pipeline.handle(
                question=str(request.input.get("query") or ""),
                history=request.input.get("history") or [],
                already_clarified=bool(request.input.get("already_clarified")))

        # The ledger is deliberately NOT shipped in this artifact. Numbers that
        # cross a `google.protobuf.Value` come back as floats, and a handoff
        # count of `4.0` in a developer-facing trace is a small lie about a
        # thing whose whole purpose is to be counted. The caller holds the same
        # ledger object and attaches it natively.
        return Outcome(narrative=outcome.answer).add(ARTIFACT_OUTCOME,
                                                     outcome.as_dict())
