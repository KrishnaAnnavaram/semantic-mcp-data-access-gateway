"""Adapters that let domain logic call another agent without knowing it did.

`DataPlanner` needs a data layer that can advertise a catalogue and assess a
requirement. It must not need an A2A client, a task id or a protobuf, or the
rules of the discussion would be tangled with the transport that carries them
and neither could be tested alone.

So the port is satisfied here, in the adapter layer, by an object that speaks
A2A on one side and the repository's own dataclasses on the other:

    DataPlanner ──► DataLayerPort ──► A2ADataLayer ──A2A──► mcp-agent

The synchronous shape is deliberate. The planner runs on a worker thread (an
executor hands its domain work off with `to_thread` so the event loop stays free
for the nested call this port is about to make), so these methods block that
worker thread and marshal the coroutine onto the A2A loop. The alternative —
making the planner async — would push protocol concerns back into the reasoning
code this file exists to keep them out of.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agents.a2a.client import AgentLink, dispatch
from agents.a2a.envelope import (
    ARTIFACT_CATALOGUE,
    ARTIFACT_SERVE_RESPONSE,
    SkillResult,
    catalogue_from_dict,
    serve_response_from_dict,
)
from agents.a2a.guardrails import CallChain, TurnLedger
from agents.contracts import Requirement, ServeResponse, ToolCatalogue

LOGGER = logging.getLogger("agents.a2a.ports")


class A2ADataLayer:
    """`DataLayerPort` implemented by calling the MCP agent over A2A."""

    def __init__(self, link: AgentLink, loop: asyncio.AbstractEventLoop,
                 ledger: TurnLedger, *, requesting_agent: str,
                 chain: CallChain) -> None:
        self._link = link
        self._loop = loop
        self._ledger = ledger
        self._requesting_agent = requesting_agent
        self._chain = chain
        self._round = 0
        self._phase = ""

    def set_phase(self, round_: int, phase: str) -> None:
        """Label the calls this port is about to make, for the handoff trail.

        The planner owns the conversation and therefore knows which round and
        phase each call belongs to; the port only carries the label. Without it
        the ledger shows five identical `assess_data_requirement` rows and the
        negotiation is unreadable.
        """
        self._round, self._phase = round_, phase

    # -- DataLayerPort -------------------------------------------------------

    def catalogue(self) -> ToolCatalogue:
        result = self._call("describe_data_capabilities", {},
                            intent="what can the data layer actually serve")
        catalogue = catalogue_from_dict(result.artifact(ARTIFACT_CATALOGUE))
        if catalogue is not None:
            return catalogue
        # The data layer could not be reached or answered without a catalogue.
        # An empty catalogue with the reason attached is the honest input to the
        # expert: it plans against nothing rather than against an assumption,
        # and the note survives into the requirement's warnings.
        return ToolCatalogue(notes=[self._why(result, "capability catalogue")])

    def assess(self, requirement: Requirement,
               catalogue: ToolCatalogue) -> ServeResponse:
        result = self._call(
            "assess_data_requirement",
            {"requirement": requirement.as_dict(), "catalogue": catalogue.as_dict()},
            intent="can this requirement be served as proposed")
        if result.completed and result.artifact(ARTIFACT_SERVE_RESPONSE) is not None:
            return serve_response_from_dict(result.artifact(ARTIFACT_SERVE_RESPONSE))
        # No verdict. Accept the requirement rather than block the request, and
        # say so — the same degradation the agent already applies when its own
        # assessment model is unavailable, so the reply never implies a
        # negotiation that did not happen.
        reason = self._why(result, "assessment")
        return ServeResponse(feasible=True, counter_proposal=reason,
                             notes=[reason])

    # -- plumbing ------------------------------------------------------------

    def _call(self, skill: str, payload: dict[str, Any], *, intent: str) -> SkillResult:
        return dispatch(
            self._loop,
            self._link.call(skill=skill, payload=payload,
                            requesting_agent=self._requesting_agent,
                            ledger=self._ledger, chain=self._chain, intent=intent,
                            negotiation_round=self._round,
                            negotiation_phase=self._phase),
            self._ledger.remaining_seconds() + 30)

    @staticmethod
    def _why(result: SkillResult, what: str) -> str:
        detail = (result.error or {}).get("message") or result.narrative
        return (f"The data layer did not return a {what} "
                f"({result.state}): {detail}" if detail else
                f"The data layer did not return a {what} ({result.state}).")
