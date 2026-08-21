"""The orchestrator's workflow: route, delegate over A2A, reflect, reply.

    USER
     │  (FastAPI, acting as the user boundary)
     ▼
    ORCHESTRATOR  classify
     ├─ normal question ─────────────────────────────► reply, stop
     ├─ missing detail ──A2A──► MCP AGENT: real choices ──► ask one question
     └─ data request
          │
          ├──A2A──► DOMAIN EXPERT: derive_data_requirement
          │             │  (which itself negotiates with the MCP agent over A2A)
          │◄────────────┘  requirement · negotiation · catalogue · citations
          │
          ├──A2A──► MCP AGENT: execute_data_plan
          │◄──────  dataset · calculation · summary
          │              └─ or: task state input-required
          │
          ▼
    ORCHESTRATOR  reflect → reply   (or relay the question to the user)

This module is the orchestrator's *own* logic, hosted by `OrchestratorExecutor`
and run when a `handle_user_turn` message arrives. It is not a coordinator that
sits above the agents — the orchestrator is one of the three, and the calls it
makes to the other two are A2A calls, not method calls.

**No specialist is imported here.** `DomainExpertAgent` and `McpAgent` do not
appear in this file. The orchestrator addresses them by agent id through
`AgentNetwork`, and would work unchanged if either moved to another host.

**The orchestrator owns the conversation.** When a specialist stops in
`input-required`, this module turns the structured question into one the user
can answer and records which task is waiting. The specialist never speaks to
the user, and the user never learns that a specialist exists.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.a2a.client import dispatch
from agents.a2a.envelope import (
    ARTIFACT_CALCULATION,
    ARTIFACT_VALIDATION,
    ARTIFACT_CATALOGUE,
    ARTIFACT_CHOICES,
    ARTIFACT_DATASET,
    ARTIFACT_NEGOTIATION,
    ARTIFACT_REQUIREMENT,
    SkillResult,
    catalogue_from_dict,
    execution_from_dict,
    negotiation_from_dict,
    requirement_from_dict,
    validation_from_dict,
)
from agents.a2a.guardrails import CallChain, TurnLedger
from agents.a2a import elicitation as elicit
from agents.a2a.identity import AgentId
from agents.contracts import AgentOutcome, Intent, Negotiation, Requirement, ToolCatalogue
from agents.observability import run_url, traced
from agents.redaction import CONTRACT_KEYS, scrub_identifiers

LOGGER = logging.getLogger("agents.pipeline")

#: Calculations worth a validation pass. A catalogue lookup does not need the
#: domain expert's opinion; a risk figure does, because a risk figure carries
#: parameters that can be silently wrong.
VALIDATED_CALCULATIONS = frozenset({"compute_var", "compute_dv01",
                                    "run_stress", "price_portfolio"})


class AgentPipeline:
    """One user turn, from the orchestrator's point of view."""

    def __init__(self, *, network, orchestrator=None,
                 ledger: TurnLedger | None = None,
                 chain: CallChain | None = None) -> None:
        """Build the orchestrator's workflow.

        The network is required and keyword-only. The old signature took a
        knowledge base and a data provider positionally and built everything
        from them, which meant constructing a pipeline could quietly stand up a
        second copy of the whole system — a second entry point, and the first
        thing to drift. Those two now belong to the specialist agents the
        network hosts; the orchestrator reads neither.
        """
        self.network = network
        self.orchestrator = orchestrator or network.orchestrator_agent
        self._ledger = ledger
        # The call path that reached this workflow. Every specialist call the
        # orchestrator makes extends it, which is how nesting is measured
        # without mistaking a bounded conversation for recursion.
        self._chain = chain or CallChain()

    # -- the turn ------------------------------------------------------------

    @traced("agent_pipeline", run_type="chain")
    def handle(self, question: str, history: list[dict] | None = None,
               already_clarified: bool = False) -> AgentOutcome:
        ledger = self._ledger or self.network.ledgers.open("")
        trace: list[dict[str, Any]] = []

        # --- 1. is this a question, or a request for data? -------------------
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
            return self._finish(AgentOutcome(answer=intent.direct_answer,
                                             route="direct", intent=intent,
                                             trace=trace), ledger)

        if intent.route == "clarify":
            return self._clarify(question, intent, trace, ledger)

        return self._data_request(question, intent, trace, ledger)

    # -- clarify -------------------------------------------------------------

    def _clarify(self, question: str, intent: Intent, trace: list[dict],
                 ledger: TurnLedger) -> AgentOutcome:
        """Ask one question, with choices that really exist.

        The catalogue read happens only on this branch, so a greeting still
        costs nothing, and it is what turns "a named scenario" into "the 2008
        replay on the demo book" — an option that actually ends the ambiguity
        when clicked.
        """
        result = self._ask(AgentId.MCP, "list_data_choices", {},
                           ledger, intent="real options for a clarifying question")
        choices = result.artifact(ARTIFACT_CHOICES) or {}
        trace.append({"kind": "tool_call",
                      "label": "Asked the data layer what really exists",
                      "detail": {"state": result.state,
                                 "portfolios": len(choices.get("portfolios") or []),
                                 "scenarios": len(choices.get("scenarios") or [])}})
        intent = self.orchestrator.ground_options(question, intent, choices)
        trace.append({"kind": "clarification", "label": "Asked for a missing detail",
                      "detail": {"question": intent.question,
                                 "options": intent.options}})
        return self._finish(AgentOutcome(answer=intent.question, route="clarify",
                                         intent=intent, trace=trace), ledger)

    # -- data request --------------------------------------------------------

    def _data_request(self, question: str, intent: Intent, trace: list[dict],
                      ledger: TurnLedger) -> AgentOutcome:
        plan = self._ask(
            AgentId.DOMAIN_EXPERT, "derive_data_requirement",
            {"question": question, "task": intent.task,
             "requested_fields": intent.requested_fields,
             "requested_rows": intent.requested_rows},
            ledger, intent="what does this task actually need")

        if not plan.completed:
            return self._specialist_failed(AgentId.DOMAIN_EXPERT, plan, intent,
                                           trace, ledger)

        requirement = requirement_from_dict(plan.artifact(ARTIFACT_REQUIREMENT))
        catalogue = catalogue_from_dict(plan.artifact(ARTIFACT_CATALOGUE)) or ToolCatalogue()
        negotiation = negotiation_from_dict(plan.artifact(ARTIFACT_NEGOTIATION)) or Negotiation()
        if requirement is None:
            return self._specialist_failed(AgentId.DOMAIN_EXPERT, plan, intent,
                                           trace, ledger)

        tool_names = [t.name for t in catalogue.tools] + list(CONTRACT_KEYS)
        trace.append({
            "kind": "tool_call",
            "label": f"MCP agent advertised {len(catalogue.tools)} tool(s)",
            "detail": {"tools": tool_names, "can_calculate": catalogue.can_calculate,
                       "notes": catalogue.notes},
        })
        trace.append({
            "kind": "knowledge",
            "label": f"Domain expert cited {len(requirement.citations)} chunk(s) from Qdrant",
            "detail": [c.get("label", "") for c in requirement.citations],
        })
        trace.append({
            "kind": "decision",
            "label": ("Requirement: "
                      f"{len(requirement.fields)} field(s), "
                      f"{requirement.rows if requirement.rows is not None else 'window unstated'} row(s)"),
            "detail": requirement.as_dict(),
        })
        trace.append({
            "kind": "decision",
            "label": ("Discussion: not held — nothing was servable to negotiate"
                      if not negotiation.held else
                      f"Discussion: {negotiation.rounds_used} round(s), "
                      f"{'converged' if negotiation.converged else 'not converged'}"),
            "detail": negotiation.as_dict(),
        })

        decision = negotiation.decision if negotiation.held else "UNSUPPORTED"
        if decision != "AGREED":
            # The specialists did not produce an executable plan. Which of the
            # three non-agreement outcomes it was decides what the user is told,
            # which is exactly why a boolean was not enough.
            return self._not_agreed(decision, question, intent, requirement,
                                    negotiation, catalogue, tool_names, trace,
                                    ledger)

        execution = self._ask(
            AgentId.MCP, "execute_data_plan",
            {"requirement": requirement.as_dict(),
             "rows_requested_by_user": intent.requested_rows},
            ledger, intent="fetch the agreed data and run the agreed calculation")

        if execution.needs_input:
            return self._relay_question(execution, intent, trace, ledger,
                                        requirement=requirement,
                                        negotiation=negotiation,
                                        catalogue=catalogue)
        if not execution.completed:
            return self._specialist_failed(AgentId.MCP, execution, intent, trace,
                                           ledger, requirement=requirement,
                                           negotiation=negotiation,
                                           catalogue=catalogue)

        return self._compose(question, intent, requirement, negotiation, catalogue,
                             execution, tool_names, trace, ledger)

    def _not_agreed(self, decision: str, question: str, intent: Intent | None,
                    requirement: Requirement, negotiation: Negotiation,
                    catalogue: ToolCatalogue, tool_names: list[str],
                    trace: list[dict], ledger: TurnLedger) -> AgentOutcome:
        """Report a negotiation that did not end in an executable plan.

        Three different things went wrong and they need three different
        sentences. Collapsing them into "could not answer" throws away the only
        part the user can act on: whether to supply something, rephrase, or
        accept that this system does not do that.

        A fourth case is not a negotiation outcome at all and is handled first:
        the reasoning step itself failed, so nothing was learned about the data.
        """
        intent = intent or Intent(route="data_request", reasoning=decision)

        if requirement.blocked_by == "account":
            # No retry fixes this, so do not invite one. The provider said
            # "insufficient balance"; "asking again usually works" is advice
            # that cannot come true, and it sends the user in a circle instead
            # of to the one action that resolves it.
            answer = (
                "I could not answer this because the language model this "
                "gateway runs on is not currently accepting requests — the "
                "configured account has no remaining balance or its key is not "
                "valid. The data layer is fine; nothing was wrong with your "
                "question. This needs an operator, not another attempt.")
            trace.append({"kind": "answer", "label": "Model account unavailable",
                          "detail": {"blocked_by": "account",
                                     "reason": requirement.unanswerable_reason}})
            return self._finish(AgentOutcome(
                answer=answer, route="data_request", intent=intent,
                requirement=requirement, negotiation=negotiation,
                catalogue=catalogue, trace=trace,
                citations=requirement.citations), ledger)

        if requirement.blocked_by == "model":
            # Never say "your question cannot be answered from the available
            # data" when what actually happened is that a model call came back
            # unusable. One is a fact about their data; the other is a fact
            # about this system having a bad minute, and only the second is
            # worth retrying.
            answer = (
                "I could not complete the reasoning step for this question — "
                "the planning model did not return a usable plan, so nothing "
                "was run. This is a fault on my side, not a limit of the data. "
                "Asking again usually works.")
            trace.append({"kind": "answer", "label": "Reasoning step failed",
                          "detail": {"blocked_by": "model",
                                     "reason": requirement.unanswerable_reason}})
            return self._finish(AgentOutcome(
                answer=answer, route="data_request", intent=intent,
                requirement=requirement, negotiation=negotiation,
                catalogue=catalogue, trace=trace,
                citations=requirement.citations), ledger)
        if decision == "NEEDS_USER_INPUT":
            # `_decision_of` will not let an empty NEEDS_USER_INPUT through, so
            # the fallback should be unreachable. Kept, but no longer a
            # placeholder: if it ever fires, the user gets a sentence that
            # tells them something rather than one that asks them to choose
            # between nothing.
            asked = (requirement.open_questions or [
                "I need one more detail before I can run this, but I could not "
                "work out which. Could you restate what you are after?"])[0]
            intent.route, intent.question = "clarify", asked
            trace.append({"kind": "clarification",
                          "label": "The specialists need a decision from you",
                          "detail": {"decision": decision,
                                     "open_questions": requirement.open_questions}})
            return self._finish(AgentOutcome(
                answer=asked, route="clarify", intent=intent,
                requirement=requirement, negotiation=negotiation,
                catalogue=catalogue, trace=trace,
                citations=requirement.citations), ledger)

        if decision == "UNSUPPORTED":
            answer = scrub_identifiers(
                requirement.unanswerable_reason
                or "This task cannot be answered from the available data.",
                tool_names)
            label = "Declined"
        else:  # CANNOT_REACH_AGREEMENT
            answer = (
                "The domain expert and the data layer could not agree on a plan "
                "for this question within the exchanges they are allowed, so "
                "nothing was run. A half-negotiated plan is not a result, and "
                "guessing past the disagreement would be worse than saying so.")
            label = "No agreement"

        trace.append({"kind": "answer", "label": label,
                      "detail": {"decision": decision, "answer": answer,
                                 "outcome": negotiation.outcome}})
        return self._finish(AgentOutcome(
            answer=answer, route="data_request", intent=intent,
            requirement=requirement, negotiation=negotiation,
            catalogue=catalogue, trace=trace,
            citations=requirement.citations), ledger)

    def _compose(self, question: str, intent: Intent, requirement: Requirement,
                 negotiation: Negotiation, catalogue: ToolCatalogue,
                 execution: SkillResult, tool_names: list[str],
                 trace: list[dict], ledger: TurnLedger) -> AgentOutcome:
        result = execution_from_dict(
            execution.artifact(ARTIFACT_DATASET),
            execution.artifact(ARTIFACT_CALCULATION),
            execution.artifact("summary"))
        result["rows_requested_by_user"] = intent.requested_rows
        table = result.get("table") or {}
        trace.append({
            "kind": "tool_call",
            "label": f"Fetched {result.get('rows_delivered', 0):,} row(s)",
            "detail": {"title": table.get("title"), "notes": result.get("notes")},
        })

        validation = self._validate_result(requirement, result, trace, ledger)
        if validation is not None and validation.blocking:
            # The number is real and the label would have been wrong. Saying so
            # is the only honest option: a true figure under a false description
            # is the worst thing this system can emit, and it was emitting one.
            answer = (
                "The calculation ran, but it does not match the plan agreed for "
                "your question, so I will not present it as the answer. "
                + "; ".join(validation.mismatches[:2]) + ".")
            trace.append({"kind": "answer",
                          "label": "Result rejected by domain validation",
                          "detail": validation.as_dict()})
            return self._finish(AgentOutcome(
                answer=answer, route="data_request", intent=intent,
                requirement=requirement, negotiation=negotiation,
                catalogue=catalogue, trace=trace, validation=validation,
                citations=requirement.citations), ledger)

        if validation is not None:
            result["validation"] = validation.as_dict()

        answer = scrub_identifiers(
            self.orchestrator.reflect(question, requirement, negotiation, result),
            tool_names)
        trace.append({"kind": "answer", "label": "Composed reply", "detail": answer})

        return self._finish(AgentOutcome(
            answer=answer, route="data_request", intent=intent,
            requirement=requirement, negotiation=negotiation, catalogue=catalogue,
            tables=[table] if table.get("columns") else [],
            calculation=result.get("calculation"), trace=trace,
            validation=validation, citations=requirement.citations), ledger)

    def _validate_result(self, requirement: Requirement, result: dict[str, Any],
                         trace: list[dict], ledger: TurnLedger):
        """Send a non-trivial result back to the expert that agreed the plan.

        Only for calculations. A catalogue lookup does not benefit from a second
        opinion, and spending a model call to have one agent tell another that a
        table is still a table is ceremony, not assurance.
        """
        if requirement.calculation not in VALIDATED_CALCULATIONS:
            return None

        summary = {"observation_date": (result.get("table") or {})
                   .get("provenance", {}).get("curve_date"),
                   "rows_delivered": result.get("rows_delivered")}
        outcome = self._ask(
            AgentId.DOMAIN_EXPERT, "validate_result",
            {"requirement": requirement.as_dict(),
             "calculation": result.get("calculation"), "summary": summary},
            ledger, intent="does this result match the agreed plan",
            phase="RESULT_VALIDATION")

        validation = (validation_from_dict(outcome.artifact(ARTIFACT_VALIDATION))
                      if outcome.completed else None)
        if validation is None:
            # The validator itself failed. Not a licence to publish unchecked,
            # but not a reason to withhold either: reported as unverified, and
            # the reply says nothing it cannot support.
            trace.append({"kind": "decision",
                          "label": "Result could not be validated",
                          "detail": {"state": outcome.state}})
            return None

        trace.append({
            "kind": "decision",
            "label": f"Domain expert validated the result: {validation.verdict}",
            "detail": validation.as_dict()})
        return validation

    # -- elicitation, mediated ------------------------------------------------

    def _relay_question(self, execution: SkillResult, intent: Intent | None,
                        trace: list[dict], ledger: TurnLedger, *,
                        requirement: Requirement | None = None,
                        negotiation: Negotiation | None = None,
                        catalogue: ToolCatalogue | None = None) -> AgentOutcome:
        """A specialist stopped and needs a decision. Ask the user; remember who waits.

        The specialist's task stays alive in `input-required`. What travels to
        the browser is an ordinary clarifying question — the same shape the UI
        already renders — and what stays on the server is the task id that
        answer belongs to.
        """
        payload = execution.input_request or {}
        question = elicit.question_for_user(payload) or execution.narrative or (
            "The data layer needs one more detail before it can continue.")
        options = elicit.user_options(payload)
        attempt = int(payload.get("attempt") or 0)
        intent = intent or Intent(route="clarify", reasoning="relayed question")
        intent.route = "clarify"
        intent.question = question
        intent.options = options or intent.options
        trace.append({
            "kind": "clarification",
            "label": ("The data layer asked for a decision; relayed to the user"
                      if attempt == 0 else
                      f"Asked again (attempt {attempt + 1}); the previous reply "
                      "did not answer the question"),
            "detail": {"agent": AgentId.MCP.value, "task_id": execution.task_id,
                       "required_information": payload.get("required_information"),
                       "attempt": attempt,
                       "retries_remaining": payload.get("retries_remaining"),
                       "question": question, "options": intent.options},
        })
        LOGGER.info("relaying an input-required question from %s task=%s attempt=%d",
                    AgentId.MCP.value, execution.task_id, attempt)
        return self._finish(AgentOutcome(
            answer=question, route="clarify", intent=intent,
            requirement=requirement, negotiation=negotiation, catalogue=catalogue,
            trace=trace,
            citations=requirement.citations if requirement else [],
            # The task id is the correlation. It does not change when the
            # question is put again, which is what makes the second and third
            # attempts continuations of the same task rather than new work.
            waiting={"agent": AgentId.MCP.value, "task_id": execution.task_id,
                     "context_id": execution.context_id,
                     "input_request": payload,
                     "requested_rows": intent.requested_rows,
                     # Carried so a material clarification can be revalidated
                     # against the plan that was already agreed rather than
                     # from scratch.
                     "question": intent.task or intent.question,
                     "task": intent.task,
                     "agreed_plan": (requirement.as_dict()
                                     if requirement is not None else None)}), ledger)

    @traced("agent_pipeline.resume", run_type="chain")
    def resume(self, reply: str, waiting: dict[str, Any],
               history: list[dict] | None = None) -> AgentOutcome:
        """The user answered a specialist's question. Carry it back to that task.

        Correlated by task id, so the interrupted work continues rather than a
        new workflow starting from the user's words — which is what would happen
        if the answer were simply classified as a fresh question.

        **The reply is interpreted here, not by the specialist.** Matching what
        the user said onto the field the servers asked about is a decision about
        a human's words, and those belong to the orchestrator. The match is
        deterministic against the enum the server supplied: asking a model to
        pick from a list it was given is a way to occasionally get something
        that is not on the list.

        **An unmatched reply is not a refusal.** A user who answers "30 year
        Treasury" to "nominal or real?" has not declined; they have said
        something that does not settle the question. Terminating there throws
        away a request they still want served. The specialist's task stays in
        `input-required`, the question comes back, and the orchestrator asks
        again — up to `A2A_MAX_CLARIFICATIONS` times, after which the plan runs
        on the tool's own labelled declined path. Bounded, so it cannot become
        the user-facing twin of an unbounded agent loop.

        **An explicit refusal ends it immediately.** "cancel", "never mind" —
        the specialist cancels its task and nothing is fetched.
        """
        payload = waiting.get("input_request") or {}
        answers = elicit.match_answer(reply, payload)
        if answers is None:
            LOGGER.info("the reply does not name one of the allowed answers; "
                        "resuming task %s on the declined path rather than "
                        "asking again", waiting.get("task_id"))

        ledger = self._ledger or self.network.ledgers.open("")
        trace: list[dict[str, Any]] = [{
            "kind": "intent", "label": "Route: resume",
            "detail": f"Answering a question from {waiting.get('agent')} "
                      f"on task {waiting.get('task_id')}.",
        }]
        target = AgentId(waiting.get("agent") or AgentId.MCP.value)
        trace.append({
            "kind": "decision",
            "label": ("Matched the reply to the pending question"
                      if answers else
                      "The reply did not name one of the allowed answers"),
            "detail": {"answers": answers,
                       "required_information": payload.get("required_information")},
        })
        # D-6: some answers change *which rows to read*, and some change *what
        # the question means*. "Use portfolio X" is the first; "use real rates"
        # is the second, and continuing on a plan agreed for nominal would
        # produce a correct number answering a question nobody asked. When the
        # answer is material the domain expert reconsiders before anything runs.
        agreed = waiting.get("agreed_plan") or {}
        if answers and elicit.is_domain_material(
                answers, payload, has_methodology=bool(agreed.get("calculation"))):
            LOGGER.info("clarification %s is domain-material; revalidating",
                        sorted(answers))
            trace.append({
                "kind": "decision",
                "label": "Clarification changes the analysis; domain expert "
                         "revalidating",
                "detail": {"answers": answers,
                           "material_fields": sorted(
                               set(answers) & elicit.DOMAIN_MATERIAL_FIELDS)},
            })
            return self._revalidate(reply, answers, waiting, history, trace, ledger)

        result = self._ask(target, "provide_input",
                           {"reply": reply, "answers": answers,
                            "input_request": payload},
                           ledger, intent="the user's answer",
                           task_id=waiting.get("task_id") or None,
                           context_id=waiting.get("context_id") or None)

        if result.needs_input:
            # Still not answered. The task is alive and the question comes back
            # — the retry budget lives with the specialist that owns the task,
            # so there is exactly one place it can be exhausted.
            return self._relay_question(result, None, trace, ledger)

        if result.canceled:
            trace.append({"kind": "answer", "label": "Cancelled by the user",
                          "detail": result.narrative})
            return self._finish(AgentOutcome(
                answer=result.narrative or
                       "Cancelled. Nothing was fetched and nothing was assumed.",
                route="direct", trace=trace), ledger)

        if (result.error or {}).get("kind") == "no_pending_task":
            # The task this answer belonged to is gone — almost always because
            # the service restarted between turns. The user cannot see that and
            # did not cause it, so their message is treated as the question it
            # is rather than reported as a failure.
            LOGGER.info("no task left to resume (%s); handling the reply as a "
                        "new turn", waiting.get("task_id"))
            return self.handle(reply, history, already_clarified=True)

        if not result.completed:
            return self._specialist_failed(target, result, None, trace, ledger)

        execution = execution_from_dict(result.artifact(ARTIFACT_DATASET),
                                        result.artifact(ARTIFACT_CALCULATION),
                                        result.artifact("summary"))
        table = execution.get("table") or {}
        trace.append({"kind": "tool_call",
                      "label": f"Resumed and fetched {execution.get('rows_delivered', 0):,} row(s)",
                      "detail": {"title": table.get("title"),
                                 "notes": execution.get("notes")}})
        answer = self.orchestrator.reflect(reply, None, None, execution)
        trace.append({"kind": "answer", "label": "Composed reply", "detail": answer})
        return self._finish(AgentOutcome(
            answer=answer, route="data_request", trace=trace,
            tables=[table] if table.get("columns") else [],
            calculation=execution.get("calculation")), ledger)

    def _revalidate(self, reply: str, answers: dict[str, Any],
                    waiting: dict[str, Any], history: list[dict] | None,
                    trace: list[dict], ledger: TurnLedger) -> AgentOutcome:
        """Re-open the analysis because the user changed what was being asked.

        Not a fresh turn: the expert is given the plan it already agreed and
        told what changed, so it keeps whatever still holds instead of
        rediscovering it. Cheaper, and much less likely to quietly drop a
        constraint that is still in force.
        """
        stated = ", ".join(f"{k} = {v}" for k, v in sorted(answers.items()))
        question = waiting.get("question") or reply
        plan = self._ask(
            AgentId.DOMAIN_EXPERT, "derive_data_requirement",
            {"question": f"{question} ({stated})",
             "task": waiting.get("task") or question,
             "requested_fields": [], "requested_rows": waiting.get("requested_rows"),
             "prior_plan": waiting.get("agreed_plan"),
             "revalidation_reason": f"the user has specified {stated}"},
            ledger, intent="revalidate the plan after a material clarification",
            phase="REVISION")

        if not plan.completed:
            return self._specialist_failed(AgentId.DOMAIN_EXPERT, plan, None,
                                           trace, ledger)

        requirement = requirement_from_dict(plan.artifact(ARTIFACT_REQUIREMENT))
        negotiation = (negotiation_from_dict(plan.artifact(ARTIFACT_NEGOTIATION))
                       or Negotiation())
        catalogue = (catalogue_from_dict(plan.artifact(ARTIFACT_CATALOGUE))
                     or ToolCatalogue())
        if requirement is None:
            return self._specialist_failed(AgentId.DOMAIN_EXPERT, plan, None,
                                           trace, ledger)

        trace.append({
            "kind": "decision",
            "label": f"Revalidated plan: {negotiation.decision}",
            "detail": requirement.as_dict(),
        })
        intent = Intent(route="data_request", reasoning="revalidated after a "
                                                        "material clarification",
                        task=requirement.task)
        tool_names = [t.name for t in catalogue.tools] + list(CONTRACT_KEYS)
        if negotiation.decision != "AGREED":
            return self._not_agreed(negotiation.decision, reply, intent,
                                    requirement, negotiation, catalogue,
                                    tool_names, trace, ledger)

        execution = self._ask(
            AgentId.MCP, "execute_data_plan",
            {"requirement": requirement.as_dict(),
             "rows_requested_by_user": waiting.get("requested_rows")},
            ledger, intent="execute the revalidated plan")
        if execution.needs_input:
            return self._relay_question(execution, intent, trace, ledger,
                                        requirement=requirement,
                                        negotiation=negotiation,
                                        catalogue=catalogue)
        if not execution.completed:
            return self._specialist_failed(AgentId.MCP, execution, intent, trace,
                                           ledger, requirement=requirement,
                                           negotiation=negotiation,
                                           catalogue=catalogue)
        return self._compose(reply, intent, requirement, negotiation, catalogue,
                             execution, tool_names, trace, ledger)

    # -- failure -------------------------------------------------------------

    def _specialist_failed(self, agent: AgentId, result: SkillResult,
                           intent: Intent | None, trace: list[dict],
                           ledger: TurnLedger, **carried: Any) -> AgentOutcome:
        """Report a specialist's failure as a sentence, never as a stack trace.

        The structured cause is kept in the trace, where a developer can read
        it; what reaches the user is what the gateway could not do and why, in
        the orchestrator's own voice.
        """
        error = result.error or {}
        kind = error.get("kind") or result.state
        detail = error.get("message") or result.narrative or result.state
        LOGGER.error("specialist %s did not complete (%s): %s", agent.value, kind, detail)
        trace.append({"kind": "decision", "label": f"{agent.value} did not complete",
                      "detail": {"state": result.state, "kind": kind,
                                 "message": detail, "task_id": result.task_id}})
        answer = _user_facing_failure(agent, kind)
        trace.append({"kind": "answer", "label": "Reported the failure", "detail": answer})
        return self._finish(AgentOutcome(answer=answer, route="data_request",
                                         intent=intent, trace=trace, **carried),
                            ledger)

    # -- plumbing ------------------------------------------------------------

    def _ask(self, agent: AgentId, skill: str, payload: dict[str, Any],
             ledger: TurnLedger, *, intent: str = "",
             task_id: str | None = None,
             context_id: str | None = None,
             phase: str = "") -> SkillResult:
        """One A2A call to a specialist, from a synchronous workflow.

        The workflow runs on a worker thread (the executor put it there), so the
        coroutine is marshalled onto the network's loop and waited on. The loop
        itself stays free, which is what allows the agent being called to make a
        nested call of its own.
        """
        return dispatch(
            self.network.loop,
            self.network.link(agent).call(
                skill=skill, payload=payload,
                requesting_agent=AgentId.ORCHESTRATOR.value, ledger=ledger,
                chain=self._chain, intent=intent,
                context_id=context_id or ledger.context_id, task_id=task_id,
                negotiation_phase=phase),
            ledger.remaining_seconds() + 30)

    @staticmethod
    def _finish(outcome: AgentOutcome, ledger: TurnLedger) -> AgentOutcome:
        outcome.langsmith_url = run_url()
        outcome.handoffs = ledger.as_dict()
        return outcome


def _user_facing_failure(agent: AgentId, kind: str) -> str:
    """A failure the user can act on, without naming internals they cannot.

    Nothing from the underlying error reaches this sentence — not the exception
    type, not the message, not a host or a port. A specialist's exception text
    is written for whoever debugs it, and "qdrant refused the connection at
    10.0.0.1:6333" is an internal address disclosed to a browser. The structured
    cause is in the decision trace; what the user gets is what the gateway could
    not do and whether it is worth retrying.

    The agent id is deliberately absent too. "The domain-expert agent returned
    agent_error" describes this system's plumbing, not the user's problem.
    """
    if kind in {"timeout", "incomplete"}:
        # One sentence for both, because they are one thing to the reader: the
        # work did not finish in time. Whether the deadline surfaced as a
        # transport timeout or as a task still reported `working` is a detail
        # for the trace, not for the person waiting.
        return ("That request took longer than the gateway allows and was "
                "stopped. Nothing was returned, and nothing was assumed. Try a "
                "narrower question — fewer tenors, or a shorter history.")
    if kind in {"handoff_limit", "depth_limit"}:
        return ("The agents could not settle this request within the number of "
                "exchanges they are allowed. No partial answer was composed, "
                "because a half-negotiated data plan is not a result.")
    if kind in {"unavailable", "empty_response", "transport"}:
        return ("Part of the gateway is not reachable at the moment, so this "
                "question was not answered. No figure was produced from memory.")
    if kind == "caller_not_permitted":
        return ("That request was refused because it did not arrive through "
                "this gateway's front door, which is the only route to the "
                "data layer.")
    if agent is AgentId.DOMAIN_EXPERT:
        return ("The data requirement for this question could not be established "
                "from the knowledge base, so nothing was fetched — fetching "
                "without a grounded requirement is guessing.")
    return ("The data layer could not complete this request. No figure was "
            "substituted for the one that is missing.")
