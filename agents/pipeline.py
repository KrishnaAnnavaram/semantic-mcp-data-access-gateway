"""The pipeline: orchestrator → domain expert ⇄ MCP agent → orchestrator.

    User question
       │
       ▼
    ORCHESTRATOR (Haiku)  classify
       ├─ normal question ─────────────────────► reply, stop
       └─ data request
            │
            ▼
       DOMAIN EXPERT (Opus)  Qdrant vector search → requirement
            │
            ├──► MCP AGENT: what tools and data do you have?
            │◄── catalogue
            │
            │  ╔════════════ DISCUSSION (bounded) ════════════╗
            │  ║  domain proposes  ⇄  mcp says what it serves ║
            │  ║  domain revises   ⇄  ...                     ║
            │  ╚══════════════════════════════════════════════╝
            │
            ▼  final requirement
       MCP AGENT (Opus)  fetch + calculate
            │
            ▼
    ORCHESTRATOR (Haiku)  reflect → reply

**Why a discussion rather than a handoff.** The domain expert knows what the
method requires; only the MCP agent knows what the source holds. A one-way
handoff produces requirements nobody can serve (six fields, three of which do
not exist) or fetches nobody asked for. Each round is a real model call and a
real LangSmith span, so the negotiation is auditable rather than implied.

**Why it is bounded.** Two agents that can always reply will always reply. The
loop stops when the MCP agent reports the requirement feasible, or after
`MAX_ROUNDS`, whichever comes first — and if it never converges, that fact is
recorded and reported instead of hidden behind a last-ditch answer.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.contracts import AgentOutcome, Negotiation
from agents.domain_expert_agent import DomainExpertAgent
from agents.mcp_agent import McpAgent
from agents.observability import run_url, traced
from agents.orchestrator_agent import OrchestratorAgent
from agents.redaction import scrub_identifiers

LOGGER = logging.getLogger("agents.pipeline")

# Two agents that can always reply will always reply. Three rounds is enough for
# "you cannot have those fields" -> "then these" -> "agreed"; beyond that they
# are usually restating rather than converging.
MAX_ROUNDS = 3


class AgentPipeline:
    """Wires the three agents together and records what passed between them."""

    def __init__(self, knowledge, data_provider,
                 orchestrator: OrchestratorAgent | None = None,
                 domain_expert: DomainExpertAgent | None = None,
                 mcp_agent: McpAgent | None = None) -> None:
        self.orchestrator = orchestrator or OrchestratorAgent()
        self.domain_expert = domain_expert or DomainExpertAgent(knowledge)
        self.mcp = mcp_agent or McpAgent(data_provider)

    @traced("agent_pipeline", run_type="chain")
    def handle(self, question: str, history: list[dict] | None = None,
               already_clarified: bool = False) -> AgentOutcome:
        trace: list[dict[str, Any]] = []

        # --- 1. orchestrator: is this a question, or a request for data? -----
        intent = self.orchestrator.classify(question, history, already_clarified)
        if already_clarified and intent.route == "clarify":
            # The prompt asks for this; the guarantee is here. A user who has
            # just answered a question must never be asked another - that is
            # a loop with no exit, and a model instruction is not a bound.
            LOGGER.info("suppressing a second consecutive clarification")
            intent.route = "data_request"
            intent.reasoning = ("Answer to a prior clarification; proceeding "
                                "rather than asking again.")
            intent.task = intent.task or question
        trace.append({"kind": "intent", "label": f"Route: {intent.route}",
                      "detail": intent.reasoning})

        if intent.route == "direct":
            trace.append({"kind": "answer", "label": "Answered by the orchestrator",
                          "detail": intent.direct_answer})
            return AgentOutcome(answer=intent.direct_answer, route="direct",
                                intent=intent, trace=trace, langsmith_url=run_url())

        if intent.route == "clarify":
            # Stop before the expensive path. A missing detail that would change
            # the result is worth one question; guessing it wastes a vector
            # search and two Opus calls on the wrong task.
            #
            # But ask it with real choices. The catalogue read happens only on
            # this branch, so a greeting still costs nothing, and it is what
            # turns "a named scenario" into "the 2008 replay on TREASURY_DEMO_001"
            # - an option that actually ends the ambiguity when clicked.
            intent = self.orchestrator.ground_options(
                question, intent, self.mcp.choices())
            trace.append({"kind": "clarification", "label": "Asked for a missing detail",
                          "detail": {"question": intent.question,
                                     "options": intent.options}})
            return AgentOutcome(answer=intent.question, route="clarify",
                                intent=intent, trace=trace, langsmith_url=run_url())

        # --- 2. what can the data layer actually do? -------------------------
        catalogue = self.mcp.catalogue()
        # Taken from the live catalogue rather than a hard-coded list, so a tool
        # added tomorrow is covered without anyone remembering to update this.
        tool_names = [t.name for t in catalogue.tools]
        trace.append({
            "kind": "tool_call",
            "label": f"MCP agent advertised {len(catalogue.tools)} tool(s)",
            "detail": {"tools": [t.name for t in catalogue.tools],
                       "can_calculate": catalogue.can_calculate,
                       "notes": catalogue.notes},
        })

        # --- 3. domain expert: what does this task need? ---------------------
        requirement, chunks = self.domain_expert.derive(
            question, intent.task, catalogue,
            intent.requested_fields, intent.requested_rows)
        trace.append({
            "kind": "knowledge",
            "label": f"Domain expert retrieved {len(chunks)} chunk(s) from Qdrant",
            "detail": [c.label for c in chunks],
        })
        trace.append({
            "kind": "decision",
            "label": ("Requirement: "
                      f"{len(requirement.fields)} field(s), "
                      f"{requirement.rows if requirement.rows is not None else 'window unstated'} row(s)"),
            "detail": requirement.as_dict(),
        })

        if not requirement.answerable:
            answer = scrub_identifiers(
                requirement.unanswerable_reason
                or "This task cannot be answered from the available data.",
                tool_names)
            trace.append({"kind": "answer", "label": "Declined", "detail": answer})
            return AgentOutcome(answer=answer, route="data_request", intent=intent,
                                requirement=requirement, catalogue=catalogue,
                                trace=trace, citations=requirement.citations,
                                langsmith_url=run_url())

        # --- 4. the discussion ----------------------------------------------
        requirement, negotiation = self._discuss(
            question, intent, catalogue, requirement, chunks)
        trace.append({
            "kind": "decision",
            "label": (f"Discussion: {negotiation.rounds_used} round(s), "
                      f"{'converged' if negotiation.converged else 'not converged'}"),
            "detail": negotiation.as_dict(),
        })

        # --- 5. execute ------------------------------------------------------
        result = self.mcp.execute(requirement)
        result["rows_requested_by_user"] = intent.requested_rows
        table = result.get("table") or {}
        trace.append({
            "kind": "tool_call",
            "label": f"Fetched {result.get('rows_delivered', 0):,} row(s)",
            "detail": {"title": table.get("title"), "notes": result.get("notes")},
        })

        # --- 6. orchestrator reflects ----------------------------------------
        answer = scrub_identifiers(
            self.orchestrator.reflect(question, requirement, negotiation, result),
            tool_names)
        trace.append({"kind": "answer", "label": "Composed reply", "detail": answer})

        return AgentOutcome(
            answer=answer, route="data_request", intent=intent,
            requirement=requirement, negotiation=negotiation, catalogue=catalogue,
            tables=[table] if table.get("columns") else [],
            calculation=result.get("calculation"), trace=trace,
            citations=requirement.citations, langsmith_url=run_url(),
        )

    @traced("discussion", run_type="chain")
    def _discuss(self, question: str, intent, catalogue, requirement, chunks):
        """Domain expert and MCP agent converge on a servable requirement."""
        negotiation = Negotiation()
        negotiation.say(0, "domain_expert",
                        f"Proposing {len(requirement.fields)} field(s) and "
                        f"{requirement.rows if requirement.rows is not None else 'an unstated'} "
                        f"row window for: {requirement.task}",
                        requirement.as_dict())

        for round_ in range(1, MAX_ROUNDS + 1):
            response = self.mcp.assess(requirement, catalogue)
            negotiation.rounds_used = round_
            negotiation.say(round_, "mcp_agent",
                            response.counter_proposal or
                            ("Can serve this as proposed." if response.feasible
                             else "Cannot serve this as proposed."),
                            response.as_dict())

            # Convergence is about the fields still being *asked for*. The MCP
            # agent naturally keeps naming the user's impossible fields (cusip
            # and friends) as unsupported, and it is right to - but the expert
            # already dropped them, so counting those as unresolved would loop
            # until the round limit every time.
            blocking = set(response.unsupported_fields) & set(requirement.fields)
            if response.feasible and not blocking and not response.unsupported_calculation:
                negotiation.converged = True
                negotiation.outcome = (
                    f"Agreed after {round_} round(s): "
                    f"{len(requirement.fields)} field(s), "
                    f"{requirement.rows if requirement.rows is not None else 'window unstated'} row(s).")
                return requirement, negotiation

            requirement = self.domain_expert.revise(
                question, intent.task, catalogue, requirement, response, chunks,
                intent.requested_rows)
            negotiation.say(round_, "domain_expert",
                            f"Revised to {len(requirement.fields)} field(s) and "
                            f"{requirement.rows if requirement.rows is not None else 'an unstated'} "
                            "row window.",
                            requirement.as_dict())

        # Ran out of rounds. Say so rather than implying agreement - the
        # requirement is still the expert's best grounded proposal.
        negotiation.outcome = (
            f"No agreement after {MAX_ROUNDS} rounds; proceeding with the domain "
            "expert's last grounded requirement.")
        requirement.warnings.append(negotiation.outcome)
        return requirement, negotiation
