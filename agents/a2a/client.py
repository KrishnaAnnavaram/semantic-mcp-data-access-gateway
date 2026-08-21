"""The calling half of A2A: one agent addressing another.

`AgentLink` is a handle on one remote agent. Everything protocol-shaped about a
handoff happens here — building the message, applying the guardrails, waiting
with a deadline, cancelling a call that overran, and turning whatever comes back
into a `SkillResult`. The agents' own modules never see a `Task`, a `TaskState`
or an httpx client.

Two properties this layer guarantees to its callers:

**Every outcome has the same shape.** A completed task, a failed task, a task
waiting on the user, an unreachable agent and a timeout all arrive as a
`SkillResult`. A caller that had to distinguish "the agent said no" from "the
agent never answered" by catching different exception types would eventually
catch the wrong one and report a transport fault as a domain refusal.

**No raw fault ever escapes.** An httpx error, a JSON-RPC error and a protobuf
decode failure become `SkillResult(state="failed", error={...})` with a message
written for a reader. The user-facing text is composed by the orchestrator from
that structure, so no stack trace can reach the browser.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from a2a.client import Client
from a2a.types import CancelTaskRequest, SendMessageRequest

from agents.a2a.cards import is_idempotent
from agents.a2a.envelope import (
    SkillRequest,
    SkillResult,
    build_request_message,
    failure_result,
    read_task,
)
from agents.a2a.guardrails import CallChain, HandoffRefused, TurnLedger
from agents.a2a.identity import AgentId

LOGGER = logging.getLogger("agents.a2a.client")


class AgentLink:
    """A handle on one agent, over whatever transport was configured."""

    def __init__(self, agent: AgentId, client: Client) -> None:
        self.agent = agent
        self._client = client

    async def call(self, *, skill: str, payload: dict[str, Any],
                   requesting_agent: str, ledger: TurnLedger,
                   chain: CallChain | None = None,
                   intent: str = "", context_id: str | None = None,
                   task_id: str | None = None,
                   negotiation_round: int = 0,
                   negotiation_phase: str = "") -> SkillResult:
        """Ask this agent for one advertised skill, within the turn's budget.

        `chain` is the caller's own call path; this call extends it by one. A
        caller that passes nothing is at the user boundary, which is the only
        place a chain legitimately starts empty.
        """
        chain = chain or CallChain()
        request = SkillRequest(
            skill=skill, input=payload, requesting_agent=requesting_agent,
            target_agent=self.agent.value, intent=intent,
            call_chain=chain.extend(self.agent.value, skill),
            handoff_budget=ledger.handoff_limit,
            user_request_id=ledger.user_request_id,
            negotiation_round=negotiation_round,
            negotiation_phase=negotiation_phase,
        )
        digest = request.digest()
        # Read from the target's own card. A skill it does not tag `idempotent`
        # is executed again every time it is asked for, however identical the
        # request: a market fetch and a risk calculation answer a question about
        # now, and replaying one would be a cache wearing a guardrail's clothes.
        repeatable = is_idempotent(self.agent, skill)
        try:
            handoff, cached = ledger.authorise(
                requesting_agent=requesting_agent, target_agent=self.agent.value,
                skill=skill, chain=chain, digest=digest, repeatable=repeatable,
                negotiation_round=negotiation_round,
                negotiation_phase=negotiation_phase)
        except HandoffRefused as refusal:
            LOGGER.warning("a2a refused | turn=%s %s -> %s.%s | %s",
                           ledger.user_request_id, requesting_agent,
                           self.agent.value, skill, refusal.reason)
            return failure_result(refusal.reason, kind=refusal.kind)

        if cached is not None:
            LOGGER.info("a2a duplicate | turn=%s seq=%d %s -> %s.%s | answered "
                        "from the identical earlier call in this turn",
                        ledger.user_request_id, handoff.sequence, requesting_agent,
                        self.agent.value, skill)
            handoff.state = getattr(cached, "state", "") or ""
            handoff.task_id = getattr(cached, "task_id", "") or ""
            return cached

        message = build_request_message(
            request, context_id=context_id or ledger.context_id, task_id=task_id)
        LOGGER.info("a2a --> | turn=%s seq=%d chain=%d %s -> %s.%s%s ctx=%s task=%s",
                    ledger.user_request_id, handoff.sequence,
                    handoff.chain_length, requesting_agent, self.agent.value,
                    skill,
                    f" r{negotiation_round}/{negotiation_phase}"
                    if negotiation_round else "",
                    message.context_id, task_id or "-")

        started = time.perf_counter()
        # Bounded by what is left of the turn, not by a flat per-call number.
        # A call contains every call beneath it, so a flat deadline made the
        # outermost the tightest bound in the system and killed negotiations
        # that were proceeding normally. The remaining budget nests correctly
        # by construction: a child can never outlive its parent.
        result = await self._send(message, ledger.remaining_seconds())
        ledger.record(handoff, digest, result, started)
        LOGGER.info("a2a <-- | turn=%s seq=%d %s.%s state=%s task=%s %dms%s",
                    ledger.user_request_id, handoff.sequence, self.agent.value,
                    skill, result.state, result.task_id or "-",
                    handoff.duration_ms,
                    f" error={result.error.get('kind')}" if result.error else "")
        return result

    #: States a caller may act on. Everything else means the task is still in
    #: flight and whatever came back is a progress report, not an answer.
    SETTLED = frozenset({"completed", "failed", "canceled", "rejected",
                         "input-required", "auth-required"})

    async def _send(self, message: Any, timeout_s: float) -> SkillResult:
        """One `SendMessage`, with a deadline and a best-effort cancel.

        Two ways a deadline shows up, and both are handled. Over a socket the
        wait raises `TimeoutError`. In-process — where the ASGI app runs inside
        the caller's own task — the cancellation can be absorbed by the server
        stack, which then answers with the task *as it stands*: state `working`,
        no artifacts. A caller that took that at face value would report an
        empty answer as a successful one, so a non-settled state is treated as
        the failure it is rather than as a result.
        """
        task_id_seen = ""
        try:
            async with asyncio.timeout(timeout_s):
                final: SkillResult | None = None
                async for event in self._client.send_message(
                        SendMessageRequest(message=message)):
                    if event.HasField("task"):
                        task_id_seen = event.task.id
                        final = read_task(event.task)
                    elif event.HasField("message"):
                        # An agent that answers with a bare Message rather than a
                        # Task has completed in one shot. Legal in A2A, and this
                        # system does not use it — but reporting it as "no
                        # answer" would be a lie about what arrived.
                        final = SkillResult(
                            state="completed",
                            context_id=event.message.context_id,
                            narrative="\n".join(p.text for p in event.message.parts
                                                if p.HasField("text")))
                if final is None:
                    return failure_result(
                        f"{self.agent.value} returned no task and no message.",
                        kind="empty_response")
                if final.state not in self.SETTLED:
                    await self._cancel(final.task_id or task_id_seen)
                    return failure_result(
                        f"{self.agent.value} was still {final.state} after "
                        f"{timeout_s:.0f}s and never reached a finished state; "
                        "the call was abandoned.", kind="incomplete")
                return final
        except TimeoutError:
            await self._cancel(task_id_seen)
            return failure_result(
                f"{self.agent.value} did not answer within {timeout_s:.0f}s; the "
                "call was cancelled.", kind="timeout")
        except asyncio.CancelledError:
            await self._cancel(task_id_seen)
            raise
        except Exception as exc:  # noqa: BLE001 - the whole point of this layer
            LOGGER.warning("a2a transport failure calling %s: %s",
                           self.agent.value, exc)
            return failure_result(
                f"{self.agent.value} could not be reached: "
                f"{type(exc).__name__}: {exc}", kind="unavailable")

    async def _cancel(self, task_id: str) -> None:
        """Tell the agent to stop. Never raises — this runs on a failure path."""
        if not task_id:
            return
        try:
            await self._client.cancel_task(CancelTaskRequest(id=task_id))
            LOGGER.info("a2a cancel sent | %s task=%s", self.agent.value, task_id)
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("cancel of %s task %s failed: %s",
                         self.agent.value, task_id, exc)

    async def aclose(self) -> None:
        try:
            await self._client.close()
        except Exception as exc:  # noqa: BLE001 - shutdown is best effort
            # Best effort, but not silent: a close that always fails is a real
            # leak, and swallowing it without a word is how it stays invisible.
            LOGGER.debug("closing %s failed: %s", self.agent.value, exc)


def dispatch(loop: asyncio.AbstractEventLoop, coroutine: Any,
             timeout_s: float) -> SkillResult:
    """Run an `AgentLink.call` from a worker thread and wait for its result.

    The agents' workflows are synchronous and run on worker threads; the A2A
    clients live on one loop. This is the only crossing between the two, and it
    exists as a function so both callers handle the awkward case identically:
    the loop being gone.

    A loop that has stopped — process shutting down, or a network closed under a
    test — makes `run_coroutine_threadsafe` raise, and the coroutine object is
    then dropped without ever being awaited. Closing it explicitly is what keeps
    a shutdown quiet, and turning the condition into a structured failure is
    what keeps it from surfacing as an unrelated `RuntimeError` three frames up.
    """
    try:
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
    except RuntimeError as exc:
        coroutine.close()
        return failure_result(f"the A2A network is not running: {exc}",
                              kind="unavailable")
    try:
        # The link enforces its own deadline; this one only guards against the
        # loop having gone away mid-call, which would otherwise hang this thread
        # for the life of the process.
        return future.result(timeout_s)
    except Exception as exc:  # noqa: BLE001 - a worker thread must not die here
        LOGGER.warning("a2a dispatch failed: %s", exc)
        return failure_result(f"the A2A call could not be completed: "
                              f"{type(exc).__name__}: {exc}", kind="unavailable")
