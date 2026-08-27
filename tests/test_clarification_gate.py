"""The gate, end to end: what it avoids, and who is allowed to ask the user.

These run the real A2A network with the model calls stubbed, so the wiring under
test is the wiring that ships: real cards, real caller allow-lists, a real
handoff ledger, real artifacts across a protobuf boundary.

The central assertion is negative and is the whole justification for the
feature: when a question is stopped at the gate, the ledger must show that
Qdrant was never searched and the MCP agent was never asked to serve anything.
A gate that asked the right question *after* spending the turn would be worse
than no gate, because it would cost the same and interrupt as well.
"""

from __future__ import annotations

import pytest

from agents.a2a.executors import DomainExpertExecutor, OrchestratorExecutor
from agents.a2a.identity import AgentId
from agents.a2a.runtime import AgentNetwork
from tests.test_a2a import StubKnowledge, wire


@pytest.fixture
def network():
    """A real network with only the model calls stubbed.

    `wire()` is the A2A suite's own harness and is reused rather than
    reimplemented, because it stubs *every* model call - including
    `McpAgent.assess`, which is easy to forget and which a negotiation invokes
    once per round. Leaving one unstubbed does not fail the test; it makes it
    quietly reach a live provider, which is how a test suite acquires a network
    dependency nobody meant to add.

    Constructed directly rather than through `get_network()`, again as the A2A
    suite does: the singleton is process-wide, and resetting it per test tears
    down an event loop and three ASGI apps other tests are entitled to keep.
    """
    from backend.providers.base import MockDataProvider

    net = wire(AgentNetwork(StubKnowledge(), MockDataProvider()))
    try:
        yield net
    finally:
        net.shutdown()


def _skills(outcome) -> list[str]:
    return [h["skill"] for h in outcome.handoffs["handoffs"]]


# --- the saving ---------------------------------------------------------------


def test_an_incomplete_question_never_reaches_qdrant_or_the_mcp_agent(network):
    """The point of the whole feature, asserted against the ledger.

    "Compare the curve" with no period is stopped by a deterministic check on
    the user's own words. What must NOT appear afterwards is any evidence that
    the expensive path ran: no requirement derivation (four vector queries and a
    reasoning call), no capability read, no negotiation, no execution.
    """
    outcome = network.handle("Compare the Treasury curve and show the biggest "
                             "movements.", session_id="s-gate")

    assert outcome.route == "clarify"
    skills = _skills(outcome)
    assert skills == ["handle_user_turn", "check_requirement_completeness"]
    assert "derive_data_requirement" not in skills
    assert "describe_data_capabilities" not in skills
    assert "assess_data_requirement" not in skills
    assert "execute_data_plan" not in skills


def test_a_complete_question_is_not_slowed_down_by_the_gate(network):
    """One extra hop, and it is the cheapest one in the turn.

    The gate must not become a tax on the questions it cannot help with, so the
    normal path is unchanged apart from the check itself.
    """
    outcome = network.handle("What is the 2s10s history?", session_id="s-ok")

    assert outcome.route == "data_request"
    assert _skills(outcome) == [
        "handle_user_turn",
        "check_requirement_completeness",
        "derive_data_requirement",
        "describe_data_capabilities",
        "assess_data_requirement",
        "execute_data_plan",
    ]


def test_the_gate_names_the_missing_field_rather_than_asking_vaguely(network):
    outcome = network.handle("Run a stress test on the demo book",
                             session_id="s-scenario")
    assert outcome.route == "clarify"
    assert outcome.clarification["missing_fields"] == ["scenario"]
    assert "scenario" in outcome.answer.lower()
    # And it carries real, clickable choices read from the data layer, so an
    # option ENDS the ambiguity instead of restating it.
    assert "list_data_choices" in _skills(outcome)


def test_a_missing_period_costs_no_catalogue_read(network):
    """The catalogue is read only when the answer comes from a list.

    "Which comparison period?" has no enumerable answer, so paying an A2A call
    and a provider round trip to attach options nobody could use would hand back
    part of what the gate just saved.
    """
    outcome = network.handle("Compare the curve and show the movements.",
                             session_id="s-period")
    assert "list_data_choices" not in _skills(outcome)


# --- continuation -------------------------------------------------------------


def test_the_users_answer_is_rejoined_to_the_question_it_answers(network):
    """"Last 30 days" is not a new question with no subject.

    Without the merge the router sees a bare fragment and classifies it as an
    unrelated request; with it, the gate revalidates the complete request and
    the turn proceeds.
    """
    first = network.handle("Compare the Treasury curve and show the biggest "
                           "movements.", session_id="s-cont")
    assert first.route == "clarify"
    assert first.clarification["rounds"] == 1

    second = network.handle("last 30 days", session_id="s-cont",
                            pending_clarification=first.clarification)

    assert second.route == "data_request"
    # The merged question, not the fragment, is what the expert was asked about.
    merged = [s for s in second.trace
              if s["label"].startswith("Combined your answer")]
    assert merged, "the clarification answer was not merged into the question"
    assert "Compare the Treasury curve" in merged[0]["detail"]["original"]
    assert "derive_data_requirement" in _skills(second)


def test_a_second_incomplete_answer_does_not_loop_the_user_forever(network):
    """Bounded, then proceed on defaults and say so.

    Asking without a bound is the user-facing twin of an unbounded agent loop.
    After the budget is spent the turn runs and the reply is expected to state
    which defaults it fell back on.
    """
    from agents import preflight

    pending = {"question": "Compare the curve and show the movements.",
               "missing_fields": ["comparison_period"],
               "rounds": preflight.max_rounds()}
    outcome = network.handle("not sure", session_id="s-bounded",
                             pending_clarification=pending)

    assert outcome.route == "data_request"
    assert "derive_data_requirement" in _skills(outcome)


# --- the authority rule -------------------------------------------------------


def test_a_specialist_cannot_be_reached_from_the_user_boundary(network):
    """Only the orchestrator's card admits the human's side of the system.

    The gate gave the domain expert a new skill, and a new skill is a new
    opportunity to accidentally open a second door to a specialist. It is served
    to the orchestrator and to nobody else.
    """
    allowed = DomainExpertExecutor.callers["check_requirement_completeness"]
    assert allowed == {AgentId.ORCHESTRATOR.value}
    assert OrchestratorExecutor.USER_BOUNDARY not in allowed


def test_the_gate_asks_through_the_orchestrator_never_directly(network):
    """The expert returns structured data; the orchestrator writes the question.

    The verdict travels as an artifact naming fields and reasons. Everything the
    user actually sees - the sentence, the grouping, the clickable options - is
    composed by the orchestrator afterwards.
    """
    outcome = network.handle("Run a stress test on the demo book",
                             session_id="s-authority")

    # The user-facing text is the orchestrator's, and the elicitation payload
    # the service will render comes from the orchestrator's intent.
    assert outcome.route == "clarify"
    assert outcome.intent is not None
    assert outcome.intent.question == outcome.answer
    # Every call in the turn originated at the orchestrator or the boundary; the
    # domain expert never called anyone to ask a human anything.
    callers = {h["from"] for h in outcome.handoffs["handoffs"]}
    assert callers <= {OrchestratorExecutor.USER_BOUNDARY,
                       AgentId.ORCHESTRATOR.value}


# --- the correlation spine ----------------------------------------------------


def test_one_request_id_ties_the_answer_to_its_events_and_its_ledger(network):
    from agents.events import bus

    outcome = network.handle("What is the 2s10s history?", session_id="s-corr")

    request_id = outcome.request_id
    assert request_id
    # The same id in all three places, which is what makes the live stream, the
    # handoff trail and the latency table views of one turn rather than three
    # observability systems that have to be reconciled.
    assert outcome.handoffs["user_request_id"] == request_id
    assert outcome.latency["request_id"] == request_id
    assert bus().history(request_id), "no events were recorded for the turn"


def test_a_client_chosen_request_id_is_adopted_by_the_turn(network):
    """The client subscribes before it asks, so it picks the id."""
    outcome = network.handle("What is the 2s10s history?", session_id="s-chosen",
                             request_id="abc123def456")
    assert outcome.request_id == "abc123def456"
    assert outcome.handoffs["user_request_id"] == "abc123def456"


def test_a_hostile_request_id_is_sanitised_rather_than_trusted(network):
    outcome = network.handle("What is the 2s10s history?", session_id="s-evil",
                             request_id="../../etc/passwd; DROP TABLE")
    assert outcome.request_id
    assert all(c.isalnum() or c in "-_" for c in outcome.request_id)


def test_the_turn_records_where_its_time_went(network):
    outcome = network.handle("What is the 2s10s history?", session_id="s-latency")
    latency = outcome.latency
    assert latency is not None
    assert latency["total_ms"] >= 0
    # Nested spans are reported but never given a percentage of a total they
    # double-count.
    for row in latency["components"]:
        if row["nested"]:
            assert row["pct"] is None
