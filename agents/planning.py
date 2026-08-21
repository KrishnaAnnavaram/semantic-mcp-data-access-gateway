"""The Domain ↔ MCP negotiation: a hypothesis, met with evidence, then revised.

    DOMAIN EXPERT                                    MCP AGENT
         │  what can you serve at all? ──────────────────►│
         │◄──────────────────────── tools, fields, tenors │
         │
    INITIAL_HYPOTHESIS
    objective · methodology · candidate inputs
    assumptions · limitations · open questions
         │  assess this ────────────────────────────────►│
         │                                    CAPABILITY_ASSESSMENT
         │◄──── available · unavailable · unnecessary ····│
         │      tools · constraints · counter-proposal
    REVISION
    accept · drop on evidence · challenge · re-ask
         │  and this? ──────────────────────────────────►│
         │◄──────────────────────── VALIDATION ··········│
    FINAL_DECISION
    AGREED │ NEEDS_USER_INPUT │ UNSUPPORTED │ CANNOT_REACH_AGREEMENT

**Why a hypothesis rather than a requirement.** The previous design had the
expert normalise its plan *before* anyone saw it: fields the catalogue lacked
were dropped silently, so the MCP agent received something already servable and
could only say yes. That is not a negotiation, it is a rubber stamp, and it made
the second agent decorative.

Now the opening move keeps the inputs the method asks for — including ones the
data layer may not have — and states what the expert does not know. The MCP
agent answers with evidence: which inputs exist, which do not, and, most
usefully, **which are unnecessary because the tool already abstracts them**.
That last one is the fact the expert cannot get from the corpus at any price,
and it is what lets a requirement shrink on evidence instead of by assumption.

**Why it is bounded.** Two agents that can always reply will always reply. The
loop stops the moment the expert reaches a decision — often after one exchange,
because one good assessment is frequently enough — and never runs past
`MAX_NEGOTIATION_ROUNDS`. Length is not the goal: *"did the expert reassess?"*
is the goal, and a single round in which it genuinely did is worth more than
five in which it did not.

**Why the data layer is a port.** This module holds the *rules* of the
conversation; it must not hold the transport that carries it. `DataLayerPort` is
satisfied by the MCP agent over A2A in the running system, and by a stub in a
test that wants to prove the round limit holds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from agents.contracts import (
    KnowledgeChunk,
    Negotiation,
    NegotiationDecision,
    Requirement,
    ServeResponse,
    ToolCatalogue,
)
from agents.observability import traced

LOGGER = logging.getLogger("agents.planning")

#: A round is one *cycle*: the expert proposes or revises, and the data layer
#: assesses or validates. Not one message — counting transport would let
#: bookkeeping consume the budget the conversation needs.
#:
#: Five is a ceiling, not a target. Beyond about three exchanges the two are
#: restating rather than converging, and the extra rounds buy latency instead of
#: correctness; five leaves room for a genuinely contested plan without leaving
#: room for a filibuster.
MAX_NEGOTIATION_ROUNDS = 5

#: Kept as the historical name so existing imports and docs still resolve.
MAX_ROUNDS = MAX_NEGOTIATION_ROUNDS


class DataLayerPort(Protocol):
    """What the domain expert needs from whoever represents the data layer."""

    def catalogue(self) -> ToolCatalogue: ...

    def assess(self, requirement: Requirement,
               catalogue: ToolCatalogue) -> ServeResponse: ...

    def set_phase(self, round_: int, phase: str) -> None: ...


@dataclass
class DataPlan:
    """The finished proposal, and the record of how it was reached."""

    requirement: Requirement
    catalogue: ToolCatalogue
    negotiation: Negotiation = field(default_factory=Negotiation)
    chunks: list[KnowledgeChunk] = field(default_factory=list)

    @property
    def citations(self) -> list[dict[str, Any]]:
        return self.requirement.citations


class DataPlanner:
    """Runs hypothesis → assessment → revision → decision for one task."""

    def __init__(self, expert, data_layer: DataLayerPort) -> None:
        self.expert = expert
        self.data_layer = data_layer

    @traced("data_planner.plan", run_type="chain")
    def plan(self, question: str, task: str,
             requested_fields: list[str] | None = None,
             requested_rows: int | None = None,
             prior_plan: dict[str, Any] | None = None,
             revalidation_reason: str = "") -> DataPlan:
        self._phase(0, "INITIAL_HYPOTHESIS")
        catalogue = self.data_layer.catalogue()

        hypothesis, chunks = self.expert.derive(
            question, task, catalogue, requested_fields, requested_rows,
            prior_plan=prior_plan, revalidation_reason=revalidation_reason)

        if not hypothesis.answerable:
            # Nothing to negotiate. Arguing about the inputs of a task that
            # cannot be answered at all spends model calls to reach the same
            # refusal. Said explicitly rather than left to defaults: an empty
            # negotiation reads as "held and failed", which is the opposite of
            # what happened and sends a reader looking in the wrong layer.
            outcome = ("No negotiation: the model provider is not accepting "
                       "requests, so no hypothesis was ever formed. This says "
                       "nothing about the data."
                       if hypothesis.blocked_by == "account" else
                       "No negotiation: the reasoning step failed, so there was "
                       "no hypothesis to put to the data layer. Nothing was "
                       "established about the data either way."
                       if hypothesis.blocked_by == "model" else
                       "No negotiation: the task was declined before there was "
                       "anything to negotiate.")
            return DataPlan(
                requirement=hypothesis, catalogue=catalogue, chunks=chunks,
                negotiation=Negotiation(held=False, decision="UNSUPPORTED",
                                        outcome=outcome))

        requirement, negotiation = self._negotiate(
            question, task, catalogue, hypothesis, chunks, requested_rows,
            requested_fields)
        return DataPlan(requirement=requirement, catalogue=catalogue,
                        negotiation=negotiation, chunks=chunks)

    # -- the conversation ----------------------------------------------------

    @traced("negotiation", run_type="chain")
    def _negotiate(self, question: str, task: str, catalogue: ToolCatalogue,
                   hypothesis: Requirement, chunks: list[KnowledgeChunk],
                   requested_rows: int | None,
                   requested_fields: list[str] | None
                   ) -> tuple[Requirement, Negotiation]:
        negotiation = Negotiation(held=True)
        requirement = hypothesis
        negotiation.say(
            0, "domain_expert", self._hypothesis_summary(hypothesis),
            phase="INITIAL_HYPOTHESIS", payload=hypothesis.as_dict())

        for round_ in range(1, MAX_NEGOTIATION_ROUNDS + 1):
            negotiation.rounds_used = round_

            phase = "CAPABILITY_ASSESSMENT" if round_ == 1 else "VALIDATION"
            self._phase(round_, phase)
            assessment = self.data_layer.assess(requirement, catalogue)
            negotiation.say(round_, "mcp_agent",
                            self._assessment_summary(assessment),
                            phase=phase, payload=assessment.as_dict())

            self._phase(round_, "REVISION")
            revised = self.expert.revise(
                question, task, catalogue, requirement, assessment, chunks,
                requested_rows, requested_fields)

            decision = self._decision_of(revised)
            changes = self._describe_changes(requirement, revised, assessment)
            negotiation.say(round_, "domain_expert",
                            self._revision_summary(revised, decision, changes),
                            phase=("FINAL_DECISION" if decision else "REVISION"),
                            payload={**revised.as_dict(), "changes": changes})
            requirement = revised

            if decision is not None:
                negotiation.decision = decision
                negotiation.outcome = self._outcome_text(decision, round_,
                                                         requirement, changes)
                LOGGER.info("negotiation %s after %d round(s); changes=%s",
                            decision, round_, changes or "none")
                return requirement, negotiation

        # Ran out of rounds without the expert committing. Say so rather than
        # implying agreement — the requirement is still its best grounded
        # proposal, but nobody signed it off.
        negotiation.decision = "CANNOT_REACH_AGREEMENT"
        negotiation.outcome = (
            f"No agreement after {MAX_NEGOTIATION_ROUNDS} rounds. The domain "
            "expert never reached a final decision, so nothing was executed on "
            "its behalf.")
        requirement.warnings.append(negotiation.outcome)
        return requirement, negotiation

    # -- reading the expert's mind, structurally -----------------------------

    @staticmethod
    def _decision_of(requirement: Requirement) -> NegotiationDecision | None:
        """Has the expert committed, and to what?

        Read from the requirement the expert produced rather than inferred from
        field arithmetic. The old convergence test compared field sets and
        declared agreement whenever nothing was blocking — which is why it fired
        on round one every time, whatever the expert actually thought.
        """
        stated = getattr(requirement, "decision", None)
        if stated == "NEEDS_USER_INPUT" and not requirement.open_questions:
            # A request for input that cannot say what input it wants is not a
            # request. This produced a live turn whose entire clarification was
            # "Which option did you mean?" with no options attached — while the
            # plan beside it was complete: compute_var, 250 grounded rows, a
            # 10-day 99% horizon. Asking an empty question is strictly worse
            # than running the plan, and it breaks the rule that a
            # clarification must carry real choices.
            if requirement.answerable:
                LOGGER.warning("NEEDS_USER_INPUT with no question; treating the "
                               "plan as agreed")
                requirement.warnings.append(
                    "The domain expert asked for a decision from the user but "
                    "named no question, so the plan it had already settled was "
                    "used.")
                requirement.decision = "AGREED"
                return "AGREED"
            return "UNSUPPORTED"
        if stated in {"AGREED", "NEEDS_USER_INPUT", "UNSUPPORTED",
                      "CANNOT_REACH_AGREEMENT"}:
            return stated  # type: ignore[return-value]
        if not requirement.answerable:
            return "UNSUPPORTED"
        # Still carrying unanswered questions means the expert has not finished
        # thinking; give the data layer another turn to answer them.
        if requirement.open_questions:
            return None
        if not requirement.is_hypothesis:
            return "AGREED"
        return None

    @staticmethod
    def _describe_changes(before: Requirement, after: Requirement,
                          assessment: ServeResponse) -> list[str]:
        """What the expert actually changed, as facts rather than claims.

        This is the evidence that a negotiation happened. Computed by diffing
        the two requirements rather than taking the model's word for it, because
        "I have revised my plan" is exactly the sentence a model produces when
        it has not.
        """
        changes: list[str] = []
        dropped = [f for f in before.fields if f not in after.fields]
        added = [f for f in after.fields if f not in before.fields]
        if dropped:
            on_evidence = [f for f in dropped
                           if f in assessment.unsupported_fields
                           or f in assessment.unnecessary_fields]
            why = " on the data layer's evidence" if on_evidence else ""
            changes.append(f"dropped {', '.join(dropped)}{why}")
        if added:
            changes.append(f"added {', '.join(added)}")
        if before.rows != after.rows:
            changes.append(f"row window {before.rows} -> {after.rows}")
        if before.calculation != after.calculation:
            changes.append(
                f"calculation {before.calculation} -> {after.calculation}")
        if before.curve_family != after.curve_family:
            changes.append(
                f"curve family {before.curve_family} -> {after.curve_family}")
        if before.temporal.as_dict() != after.temporal.as_dict():
            changes.append(f"period {before.temporal.describe()} -> "
                           f"{after.temporal.describe()}")
        resolved = [q for q in before.open_questions
                    if q not in after.open_questions]
        if resolved:
            changes.append(f"resolved {len(resolved)} open question(s)")
        if before.is_hypothesis and not after.is_hypothesis:
            changes.append("promoted the hypothesis to an executable plan")
        return changes

    # -- prose for the trail -------------------------------------------------

    @staticmethod
    def _hypothesis_summary(hypothesis: Requirement) -> str:
        parts = [f"Objective: {hypothesis.task or 'unstated'}."]
        if hypothesis.calculation:
            parts.append(f"Candidate method: {hypothesis.calculation}.")
        if hypothesis.candidate_fields:
            parts.append(
                f"Candidate inputs: {', '.join(hypothesis.candidate_fields)}.")
        parts.append(f"Period: {hypothesis.temporal.describe()}.")
        if hypothesis.open_questions:
            parts.append(f"Open questions: {len(hypothesis.open_questions)}.")
        return " ".join(parts)

    @staticmethod
    def _assessment_summary(assessment: ServeResponse) -> str:
        if not assessment.has_evidence:
            return assessment.counter_proposal or (
                "No capability evidence was returned.")
        parts = []
        if assessment.available_fields:
            parts.append(f"available: {', '.join(assessment.available_fields)}")
        if assessment.unsupported_fields:
            parts.append(
                f"unavailable: {', '.join(assessment.unsupported_fields)}")
        if assessment.unnecessary_fields:
            parts.append("not needed by this tool: "
                         f"{', '.join(assessment.unnecessary_fields)}")
        if assessment.available_tools:
            parts.append(f"tools: {', '.join(assessment.available_tools)}")
        if assessment.temporal_constraints:
            parts.append(f"dates: {'; '.join(assessment.temporal_constraints)}")
        if assessment.constraints:
            parts.append(f"constraints: {'; '.join(assessment.constraints)}")
        return " | ".join(parts)

    @staticmethod
    def _revision_summary(requirement: Requirement,
                          decision: NegotiationDecision | None,
                          changes: list[str]) -> str:
        head = decision or "REVISION"
        body = "; ".join(changes) if changes else "no change to the plan"
        tail = (f" Still unresolved: {len(requirement.open_questions)}."
                if requirement.open_questions else "")
        return f"{head}: {body}.{tail}"

    @staticmethod
    def _outcome_text(decision: NegotiationDecision, round_: int,
                      requirement: Requirement, changes: list[str]) -> str:
        rows = requirement.rows if requirement.rows is not None else "unstated"
        if decision == "AGREED":
            detail = f" after {'; '.join(changes)}" if changes else ""
            return (f"Agreed in {round_} round(s){detail}: "
                    f"{len(requirement.fields)} field(s), {rows} row(s), "
                    f"{requirement.temporal.describe()}.")
        if decision == "NEEDS_USER_INPUT":
            return (f"Stopped after {round_} round(s): the plan cannot be "
                    "settled without something only the user can decide.")
        if decision == "UNSUPPORTED":
            return (f"Stopped after {round_} round(s): "
                    f"{requirement.unanswerable_reason or 'the data layer cannot serve this task.'}")
        return (f"Stopped after {round_} round(s) without agreement between the "
                "domain expert and the data layer.")

    def _phase(self, round_: int, phase: str) -> None:
        setter = getattr(self.data_layer, "set_phase", None)
        if callable(setter):
            setter(round_, phase)
