"""A2A tests — the protocol layer, the guardrails, and the elicitation relay.

Fast and offline. No model key, no Qdrant, no database: the three agents' *model
calls* are stubbed so what is exercised is the thing A2A actually changed — how
the agents reach each other, what crosses the wire, and what happens when a
specialist stops, fails or is asked something it may not answer.

The transport is not stubbed. Every call below is a real JSON-RPC request
serialised through httpx's ASGI transport into a real `DefaultRequestHandler`,
with a real task lifecycle on the other side. A test that mocked the transport
would prove that the code calls a mock.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any, ClassVar

import httpx
import pytest
from types import SimpleNamespace
from backend.providers.base import MockDataProvider

from agents.a2a.cards import agent_card, all_cards, is_idempotent, skill_ids
from agents.a2a.elicitation import (
    input_request_payload,
    is_refusal,
    match_answer,
    max_clarification_retries,
    user_options,
)
from agents.a2a.envelope import (
    ARTIFACT_CATALOGUE,
    ARTIFACT_CITATIONS,
    ARTIFACT_NEGOTIATION,
    ARTIFACT_REQUIREMENT,
    SkillRequest,
    build_request_message,
    read_request_message,
    requirement_from_dict,
)
from agents.a2a.executors import active_execution
from agents.a2a.guardrails import CallChain, HandoffRefused, TurnLedger
from agents.a2a.identity import MOUNT_PATHS, AgentId
from agents.a2a.runtime import AgentNetwork
from agents.contracts import (
    Intent,
    KnowledgeChunk,
    Requirement,
    ResultValidation,
    ServeResponse,
    TemporalScope,
)

# --- doubles ----------------------------------------------------------------
#
# Only the model-backed methods are replaced. The agents' own plumbing - the
# catalogue read, the discussion loop, the execution shaping - is the code under
# test and is left alone.

CHUNK = KnowledgeChunk(
    "market_risk", "value_at_risk.md", "Observation window",
    "Historical simulation reads a fixed lookback window of 250 trading days.",
    0.11)


class StubKnowledge:
    """A knowledge base with exactly one passage, so citations are checkable."""

    def retrieve(self, query: str, n_results: int = 6) -> list[dict]:
        return [{"domain": CHUNK.domain, "source": CHUNK.source,
                 "heading": CHUNK.heading, "text": CHUNK.text,
                 "distance": CHUNK.distance}]


def stub_requirement(task: str = "2s10s history", rows: int | None = 250,
                     answerable: bool = True,
                     curve_family: str = "nominal",
                     decision: str | None = None,
                     temporal: TemporalScope | None = None,
                     calculation: str | None = None) -> Requirement:
    """A requirement in whichever state the test needs.

    `decision=None` is an opening hypothesis — the expert has not committed.
    `decision="AGREED"` is what a revision returns once it has.
    """
    return Requirement(
        task=task, answerable=answerable,
        fields=["observation_date", "rate_percent", "quote_basis"],
        candidate_fields=["observation_date", "rate_percent", "quote_basis"],
        rows=rows, row_quote="250 trading days", grounded=True,
        tenors=["y2", "y10"], curve_family=curve_family,
        temporal=temporal or TemporalScope(),
        decision=decision, is_hypothesis=decision is None,
        calculation=calculation,
        unanswerable_reason=(None if answerable else
                             "A par yield curve holds no instrument records."),
        citations=[CHUNK.as_dict()])


def wire(network: AgentNetwork, *, route: str = "data_request",
         serve: ServeResponse | None = None, rows: int | None = 250,
         answerable: bool = True,
         curve_family: str = "nominal",
         temporal: TemporalScope | None = None,
         calculation: str | None = None,
         validation: ResultValidation | None = None) -> AgentNetwork:
    """Replace every model call with a fixed answer, leaving the wiring real."""
    network.orchestrator_agent.classify = lambda q, h=None, c=False: Intent(
        route=route, reasoning="stubbed routing", task=q, direct_answer="Hello.",
        question="Which book?", requested_rows=rows)
    network.orchestrator_agent.ground_options = lambda q, intent, choices: intent
    network.orchestrator_agent.reflect = lambda q, req, neg, res: (
        f"Returned {res.get('rows_delivered')} rows.")
    network.orchestrator_agent.summarise_session = lambda messages: "Treasury curve history"
    # derive returns a HYPOTHESIS (no decision); revise returns the commitment.
    network._domain_expert_agent.derive = lambda question, task, cat, f, r, **kw: (
        stub_requirement(task or question, rows, answerable, curve_family,
                         decision=None, temporal=temporal,
                         calculation=calculation), [CHUNK])
    network._domain_expert_agent.revise = lambda *a, **k: stub_requirement(
        rows=rows, answerable=answerable, curve_family=curve_family,
        decision="AGREED", temporal=temporal, calculation=calculation)
    network._domain_expert_agent.validate_result = (
        lambda requirement, calc, summary:
        validation or ResultValidation(verdict="VALID",
                                       interpretation="matches the agreed plan"))
    network._mcp_agent.assess = lambda req, cat: (
        serve if serve is not None
        else ServeResponse(feasible=True, counter_proposal="Can serve this."))
    return network


@pytest.fixture
def network():
    net = wire(AgentNetwork(StubKnowledge(), MockDataProvider()))
    try:
        yield net
    finally:
        net.shutdown()


def post_jsonrpc(app, path: str, message: Any) -> dict:
    """One raw JSON-RPC `message/send`, straight at a mounted agent."""
    from a2a.types import SendMessageRequest
    from google.protobuf.json_format import MessageToDict

    # Protocol 1.0 names its JSON-RPC methods in PascalCase; `message/send` is
    # the 0.3 spelling and is answered with "method not found".
    body = {
        "jsonrpc": "2.0", "id": "test-1", "method": "SendMessage",
        "params": MessageToDict(SendMessageRequest(message=message)),
    }

    async def _post() -> dict:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://agents.a2a.local") as client:
            response = await client.post(path, json=body,
                                         headers={"A2A-Version": "1.0"})
            return {"status": response.status_code, "body": response.json()}

    return asyncio.run(_post())


# --- Agent Cards ------------------------------------------------------------


def test_each_existing_agent_has_a_card_and_no_others_do():
    """Three agents, three cards. A fourth card would be a fourth agent."""
    cards = all_cards()
    assert {a.value for a in cards} == {"orchestrator", "domain-expert", "mcp-agent"}


def test_nothing_but_the_three_agents_is_addressable(network):
    """A fourth card, mount or executor would be a fourth agent."""
    assert len(all_cards()) == 3
    assert len(MOUNT_PATHS) == 3
    assert len(network.apps) == 3
    assert set(network.apps) == set(AgentId)
    # Helpers are helpers. None of them carries an identity of its own.
    from agents import planning

    for helper in (planning,):
        assert not hasattr(helper, "agent_card")
        assert not hasattr(helper, "AGENT_ID")
    assert "planning" not in {a.value for a in AgentId}


def test_cards_advertise_the_skills_the_executors_actually_serve():
    assert skill_ids(AgentId.ORCHESTRATOR) == {
        "handle_user_turn", "relay_user_input", "summarise_session"}
    assert skill_ids(AgentId.DOMAIN_EXPERT) == {"derive_data_requirement",
                                                "validate_result"}
    assert skill_ids(AgentId.MCP) == {
        "describe_data_capabilities", "assess_data_requirement",
        "execute_data_plan", "list_data_choices", "provide_input"}


def test_skills_describe_real_responsibilities_not_generic_ones():
    """A card is a contract. 'Can answer questions' is not one."""
    banned = {"can answer questions", "general purpose", "does things",
              "helpful assistant"}
    for agent in AgentId:
        card = agent_card(agent)
        assert card.description and len(card.description) > 60
        for skill in card.skills:
            assert skill.tags, f"{agent.value}.{skill.id} has no tags"
            assert len(skill.description) > 80, f"{skill.id} is too vague to act on"
            assert skill.description.lower() not in banned


def test_capabilities_do_not_claim_what_the_server_does_not_do():
    for agent in AgentId:
        capabilities = agent_card(agent).capabilities
        assert capabilities.streaming is False
        assert capabilities.push_notifications is False


def test_each_card_is_served_over_http_at_its_own_address(network):
    """Independently addressable, verified by fetching the card from the mount."""
    async def _fetch(path: str) -> dict:
        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=network.network_app),
                base_url="http://agents.a2a.local") as client:
            response = await client.get(f"{path}/.well-known/agent-card.json")
            assert response.status_code == 200
            return response.json()

    for agent in AgentId:
        card = asyncio.run(_fetch(MOUNT_PATHS[agent]))
        assert card["name"] == agent.value
        assert {s["id"] for s in card["skills"]} == skill_ids(agent)


# --- the envelope -----------------------------------------------------------


def test_a_skill_the_card_does_not_advertise_is_refused_at_the_boundary():
    request = SkillRequest(skill="drop_database", requesting_agent="orchestrator",
                           target_agent="mcp-agent")
    message = build_request_message(request, context_id="c1")
    with pytest.raises(Exception) as caught:
        read_request_message(message, AgentId.MCP)
    assert "does not advertise" in str(caught.value)


def test_integers_survive_the_protobuf_round_trip():
    """JSON has one number type; a row count of 250 must not come back 250.0."""
    from a2a.helpers.proto_helpers import get_data_parts, new_data_part

    payload = get_data_parts([new_data_part({"rows": 250, "max": 9000})])[0]
    assert payload["rows"] == 250.0 and isinstance(payload["rows"], float)

    rebuilt = requirement_from_dict({"task": "t", "answerable": True,
                                     "rows": payload["rows"], "fields": []})
    assert rebuilt.rows == 250 and isinstance(rebuilt.rows, int)
    assert f"{rebuilt.rows:,}" == "250"


def test_counts_are_integers_on_the_way_in_as_well_as_out():
    """A row count reached a user-visible warning as "Requested 10,000.0 rows"."""
    request = SkillRequest(skill="derive_data_requirement",
                           input={"requested_rows": 10_000, "question": "q"},
                           target_agent="domain-expert")
    message = build_request_message(request, context_id="c")
    received = read_request_message(message, AgentId.DOMAIN_EXPERT)

    assert received.input["requested_rows"] == 10_000
    assert isinstance(received.input["requested_rows"], int)
    assert f"{received.input['requested_rows']:,}" == "10,000"


def test_a_count_key_carrying_a_fraction_keeps_its_value():
    """Blanking a surprising number makes it a missing one — strictly worse."""
    from agents.a2a.envelope import restore_counts

    assert restore_counts({"rows": 2.5}) == {"rows": 2.5}
    assert restore_counts({"rows": 250.0}) == {"rows": 250}
    # And a genuine float under a non-count key is never touched.
    assert restore_counts({"var": 165_729.857}) == {"var": 165_729.857}


def test_the_request_digest_ignores_key_order_but_not_content():
    a = SkillRequest(skill="assess_data_requirement", input={"x": 1, "y": 2})
    b = SkillRequest(skill="assess_data_requirement", input={"y": 2, "x": 1})
    c = SkillRequest(skill="assess_data_requirement", input={"y": 2, "x": 3})
    assert a.digest() == b.digest()
    assert a.digest() != c.digest()


# --- orchestrator -> specialists, over A2A ----------------------------------


def test_a_data_request_travels_through_a2a_and_not_through_method_calls(network):
    outcome = network.handle("What is the 2s10s history?", session_id="s-a2a")

    assert outcome.route == "data_request"
    calls = [(h["from"], h["to"], h["skill"]) for h in outcome.handoffs["handoffs"]]
    assert calls == [
        ("user-boundary", "orchestrator", "handle_user_turn"),
        ("orchestrator", "domain-expert", "derive_data_requirement"),
        ("domain-expert", "mcp-agent", "describe_data_capabilities"),
        ("domain-expert", "mcp-agent", "assess_data_requirement"),
        ("orchestrator", "mcp-agent", "execute_data_plan"),
    ]
    assert outcome.negotiation.decision == "AGREED"
    assert all(h["state"] == "completed" for h in outcome.handoffs["handoffs"])
    # Every hop is a distinct A2A task, and every task belongs to the session.
    task_ids = {h["task_id"] for h in outcome.handoffs["handoffs"]}
    assert len(task_ids) == len(calls)
    assert {h["context_id"] for h in outcome.handoffs["handoffs"]} == {"s-a2a"}


def test_the_orchestrator_module_imports_no_specialist():
    """A2A is not A2A if the caller can still reach the callee directly.

    Checked against the parsed import graph rather than the file's text, so the
    module docstring is free to name the agents it talks to — which it should,
    since a reader needs to know — while the code must not be able to reach
    them.
    """
    import ast
    import inspect

    from agents import pipeline

    tree = ast.parse(inspect.getsource(pipeline))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)

    forbidden = {"agents.domain_expert_agent", "agents.mcp_agent"}
    assert not any(name.startswith(tuple(forbidden)) for name in imported), imported
    assert any(name.startswith("agents.a2a") for name in imported)


def test_structured_results_come_back_as_named_artifacts(network):
    """Not one flattened string: the caller can tell a table from a transcript."""
    ledger = TurnLedger(context_id="s-art")
    result = asyncio.run_coroutine_threadsafe(
        network.link(AgentId.DOMAIN_EXPERT).call(
            skill="derive_data_requirement",
            payload={"question": "q", "task": "2s10s history",
                     "requested_fields": [], "requested_rows": 250},
            requesting_agent="orchestrator", ledger=ledger,
            chain=CallChain(("orchestrator.handle_user_turn",))),
        network.loop).result(60)

    assert result.state == "completed"
    assert set(result.artifacts) >= {ARTIFACT_REQUIREMENT, ARTIFACT_NEGOTIATION,
                                     ARTIFACT_CATALOGUE, ARTIFACT_CITATIONS}
    assert result.artifact(ARTIFACT_REQUIREMENT)["rows"] == 250
    assert result.artifact(ARTIFACT_NEGOTIATION)["converged"] is True
    assert result.artifact(ARTIFACT_CITATIONS)[0]["source"] == "value_at_risk.md"
    # Narrative travels too, but beside the data rather than instead of it.
    assert "field(s)" in result.narrative


def test_mcp_data_access_still_works_behind_a2a(network):
    """A2A did not replace MCP: the data still comes from the data layer."""
    outcome = network.handle("Give me the 2s10s history", session_id="s-data")
    assert outcome.tables, "no table came back through A2A"
    table = outcome.tables[0]
    assert table["row_count"] == 250
    assert "observation_date" in table["columns"]
    assert isinstance(table["row_count"], int)
    # And the catalogue the expert planned against was read live, not declared.
    assert outcome.catalogue is not None
    assert "get_yield_curve" in [t.name for t in outcome.catalogue.tools]


def test_every_specialist_execution_happened_inside_an_a2a_task(network):
    """Stronger than "the orchestrator does not import a specialist".

    An import test proves the caller cannot *name* the callee. This proves that
    when specialist domain code actually ran, it was running inside an A2A task
    whose id appears in the turn's handoff ledger — so a hidden direct call,
    which would execute with no task context at all, cannot hide.
    """
    seen: list[tuple[str, Any]] = []

    def watch(agent_name: str, label: str, original):
        def wrapper(*args, **kwargs):
            seen.append((f"{agent_name}.{label}", active_execution()))
            return original(*args, **kwargs)
        return wrapper

    expert = network._domain_expert_agent
    mcp = network._mcp_agent
    expert.derive = watch("domain-expert", "derive", expert.derive)
    mcp.catalogue = watch("mcp-agent", "catalogue", mcp.catalogue)
    mcp.assess = watch("mcp-agent", "assess", mcp.assess)
    mcp.execute = watch("mcp-agent", "execute", mcp.execute)

    outcome = network.handle("2s10s history", session_id="s-nobypass")
    assert outcome.route == "data_request"
    assert len(seen) >= 4, "the specialists did not run at all"

    ledger = {h["task_id"]: h for h in outcome.handoffs["handoffs"]}
    for label, context in seen:
        agent = label.split(".", 1)[0]
        assert context is not None, f"{label} ran outside any A2A task"
        assert context.agent == agent, f"{label} ran as {context.agent}"
        assert context.task_id in ledger, f"{label} ran on an unrecorded task"
        assert ledger[context.task_id]["to"] == agent
        assert context.call_chain, f"{label} ran with an empty call chain"
        assert context.context_id == "s-nobypass"
        assert context.user_request_id == outcome.handoffs["user_request_id"]


def test_specialist_domain_code_has_no_a2a_context_when_called_directly(network):
    """The other half of the proof: outside a task there is no context to find."""
    assert active_execution() is None
    catalogue = network._mcp_agent.catalogue()
    assert catalogue.tools           # it would have worked...
    assert active_execution() is None  # ...but nothing recorded it as A2A work


# --- rule 3: only the orchestrator talks to the user ------------------------


def test_a_specialist_refuses_a_request_from_the_user_boundary(network):
    """The frontend cannot drive a specialist, even knowing its address."""
    from a2a.types import TaskState

    for agent, skill in ((AgentId.MCP, "execute_data_plan"),
                         (AgentId.DOMAIN_EXPERT, "derive_data_requirement")):
        message = build_request_message(
            SkillRequest(skill=skill, input={}, requesting_agent="user-boundary",
                         target_agent=agent.value,
                         call_chain=CallChain((f"{agent.value}.{skill}",))),
            context_id="s-direct")
        response = post_jsonrpc(network.network_app, f"{MOUNT_PATHS[agent]}/", message)
        assert response["status"] == 200
        task = response["body"]["result"]["task"]
        assert task["status"]["state"] == TaskState.Name(TaskState.TASK_STATE_REJECTED)
        blob = json.dumps(response["body"])
        assert "may not call" in blob


def test_a_specialist_cannot_call_the_orchestrator(network):
    """The shape a 'let me just ask the user' bypass would take."""
    from a2a.types import TaskState

    message = build_request_message(
        SkillRequest(skill="handle_user_turn", input={"query": "ask the user"},
                     requesting_agent="mcp-agent", target_agent="orchestrator",
                     call_chain=CallChain(("orchestrator.handle_user_turn",))),
        context_id="s-bypass")
    response = post_jsonrpc(network.network_app,
                            f"{MOUNT_PATHS[AgentId.ORCHESTRATOR]}/", message)
    task = response["body"]["result"]["task"]
    assert task["status"]["state"] == TaskState.Name(TaskState.TASK_STATE_REJECTED)


# --- rule 4: elicitation is mediated ----------------------------------------


class ElicitingProvider(MockDataProvider):
    """A data provider whose servers raise a question only a human can answer.

    Mirrors the real relay exactly: `input_scope` collects the question, and an
    answer supplied by the caller resolves it instead. What the MCP layer
    produces is the same `pending` record `ElicitationRelay` records.
    """

    QUESTION = ("'30 year' matches both nominal and real series. A nominal par "
                "yield and a real yield are different quantities and must not be "
                "combined on one curve. Which do you want?")
    SCHEMA: ClassVar[dict] = {"properties": {"rate_kind": {
        "type": "string", "enum": ["nominal", "real"],
        "description": "Which curve family."}}}

    def __init__(self) -> None:
        super().__init__()
        self.scopes: list[dict[str, Any] | None] = []
        self.tool_calls: list[tuple[str, dict]] = []
        self._answers: dict[str, Any] | None = None

    def __init_subclass__(cls, **kw):  # pragma: no cover - defensive
        super().__init_subclass__(**kw)

    def call_tool(self, tool, arguments=None):
        """Stand in for the real `search_series`, including its decline path."""
        self.tool_calls.append((tool, dict(arguments or {})))
        if tool != "search_series":
            return {}
        answered = (self._answers or {}).get("rate_kind")
        return {"query": (arguments or {}).get("query"), "ambiguous": True,
                "resolved_rate_kind": answered,
                "resolution": "elicited" if answered else "declined"}

    class _Relay:
        def __init__(self, answers):
            self.answers = answers or {}
            self.pending = None

    def input_scope(self, answers=None):
        import contextlib

        @contextlib.contextmanager
        def _scope():
            self.scopes.append(answers)
            self._answers = answers
            relay = self._Relay(answers)
            if not relay.answers.get("rate_kind"):
                relay.pending = {"tool": "search_series", "message": self.QUESTION,
                                 "schema": self.SCHEMA, "fields": ["rate_kind"]}
            yield relay

        return _scope()


class CountingProvider(MockDataProvider):
    """Counts what it was actually asked for, so replay is visible."""

    def __init__(self) -> None:
        super().__init__()
        self.history_calls = 0

    def get_rate_history(self, tenor, start=None, end=None, kind="nominal"):
        self.history_calls += 1
        return super().get_rate_history(tenor, start, end, kind)


@pytest.fixture
def counting_network():
    net = wire(AgentNetwork(StubKnowledge(), CountingProvider()))
    try:
        yield net
    finally:
        net.shutdown()


@pytest.fixture
def eliciting_network():
    # `ambiguous` is what makes the MCP agent ask at all: the requirement says
    # the user named a maturity without saying which curve, which is precisely
    # the question `search_series` exists to raise.
    net = wire(AgentNetwork(StubKnowledge(), ElicitingProvider()),
               curve_family="ambiguous")
    try:
        yield net
    finally:
        net.shutdown()


def test_a_missing_input_stops_the_task_and_never_reaches_the_user_directly(
        eliciting_network):
    outcome = eliciting_network.handle("30 year history", session_id="s-elicit")

    # The user is asked, by the orchestrator, in the ordinary clarify shape.
    assert outcome.route == "clarify"
    assert "nominal" in outcome.answer and "real" in outcome.answer
    assert [o["label"] for o in outcome.intent.options] == ["nominal", "real"]

    # And the specialist's task is still alive, waiting, correlated by id.
    assert outcome.waiting["agent"] == "mcp-agent"
    assert outcome.waiting["task_id"]
    assert outcome.waiting["input_request"]["required_information"] == ["rate_kind"]

    last = eliciting_network.ledgers  # the relay hop is on the record
    assert last is not None
    relayed = [step for step in outcome.trace
               if step["kind"] == "clarification"
               and step["detail"].get("agent") == "mcp-agent"]
    assert relayed, "the relayed question is not in the decision trace"


def test_the_users_answer_resumes_the_same_task_rather_than_starting_a_new_one(
        eliciting_network):
    first = eliciting_network.handle("30 year history", session_id="s-resume")
    waiting = first.waiting
    assert waiting["task_id"]

    second = eliciting_network.handle(
        "Use the nominal series for this.", session_id="s-resume",
        waiting=waiting, history=[])

    assert second.route == "data_request"
    resumed = [h for h in second.handoffs["handoffs"] if h["skill"] == "provide_input"]
    assert len(resumed) == 1
    assert resumed[0]["to"] == "mcp-agent"
    # Same task id: the interrupted work continued, it did not restart.
    assert resumed[0]["task_id"] == waiting["task_id"]
    assert resumed[0]["state"] == "completed"
    # And the answer actually reached the data layer.
    provider = eliciting_network._mcp_agent.data
    assert provider.scopes[-1] == {"rate_kind": "nominal"}
    assert second.tables and second.tables[0]["row_count"] > 0


def test_an_answer_that_settles_nothing_asks_again_on_the_same_task(eliciting_network):
    """The blocker: "30 year Treasury" answers neither nominal nor real."""
    first = eliciting_network.handle("30 year history", session_id="s-retry")
    task_id = first.waiting["task_id"]
    assert first.route == "clarify"

    # An answer to a different question. Not a refusal, and not an answer.
    second = eliciting_network.handle("30 year Treasury", session_id="s-retry",
                                      waiting=first.waiting, history=[])

    assert second.route == "clarify", "it gave up instead of asking again"
    assert second.waiting is not None
    assert second.waiting["task_id"] == task_id, "it started a new task"
    payload = second.waiting["input_request"]
    assert payload["attempt"] == 1
    assert payload["retries_remaining"] == max_clarification_retries() - 1
    # The re-ask acknowledges what was said and names what is still needed.
    assert "rate_kind" in second.answer
    assert "30 year Treasury" in second.answer
    assert [o["label"] for o in second.intent.options] == ["nominal", "real"]

    # Now answer it properly: the SAME task resumes and completes.
    third = eliciting_network.handle("Use the real series for this.",
                                     session_id="s-retry",
                                     waiting=second.waiting, history=[])
    assert third.route == "data_request"
    assert third.waiting is None
    resumed = [h for h in third.handoffs["handoffs"] if h["skill"] == "provide_input"]
    assert [h["task_id"] for h in resumed] == [task_id]
    assert resumed[0]["state"] == "completed"
    assert eliciting_network._mcp_agent.data.scopes[-1] == {"rate_kind": "real"}
    assert third.tables and third.tables[0]["row_count"] > 0


def test_the_clarification_retry_budget_is_bounded(eliciting_network):
    """Bounded, or it is the same defect as an unbounded agent loop."""
    outcome = eliciting_network.handle("30 year history", session_id="s-bounded")
    task_id = outcome.waiting["task_id"]
    asked = 1

    for _ in range(max_clarification_retries() + 3):
        if outcome.route != "clarify":
            break
        outcome = eliciting_network.handle("something else entirely",
                                           session_id="s-bounded",
                                           waiting=outcome.waiting, history=[])
        asked += 1

    assert outcome.route == "data_request", "the clarification loop never ended"
    assert outcome.waiting is None
    # First ask + the allowed retries, and not one more.
    assert asked == max_clarification_retries() + 2
    # It terminated on the tool's own declined path, and said so.
    details = [step.get("detail") for step in outcome.trace
               if isinstance(step.get("detail"), dict)]
    notes = [n for detail in details for n in detail.get("notes") or []]
    assert any("nothing was chosen on your behalf" in n for n in notes)
    # Every attempt stayed on the one task.
    assert all(h["task_id"] == task_id for h in outcome.handoffs["handoffs"]
               if h["skill"] == "provide_input")


def test_an_explicit_refusal_cancels_the_task(eliciting_network):
    first = eliciting_network.handle("30 year history", session_id="s-cancel")
    second = eliciting_network.handle("never mind", session_id="s-cancel",
                                      waiting=first.waiting, history=[])

    assert second.route == "direct"
    assert second.waiting is None
    assert "ancel" in second.answer
    cancelled = [h for h in second.handoffs["handoffs"] if h["skill"] == "provide_input"]
    assert cancelled and cancelled[0]["state"] == "canceled"
    assert cancelled[0]["task_id"] == first.waiting["task_id"]
    # Nothing was fetched on the way out.
    assert not second.tables


def test_a_lost_waiting_task_becomes_a_new_question_not_a_failure(eliciting_network):
    """The service restarts; the browser still holds the old session."""
    first = eliciting_network.handle("30 year history", session_id="s-lost")
    stale = dict(first.waiting)
    stale["task_id"] = "a-task-that-no-longer-exists"

    second = eliciting_network.handle("Use the nominal series for this.",
                                      session_id="s-lost", waiting=stale, history=[])

    # Not reported as a failure: the user cannot see a restart and did not cause it.
    assert "could not" not in second.answer.lower()
    assert second.route in {"data_request", "clarify"}
    routes = [step["label"] for step in second.trace if step["kind"] == "intent"]
    assert any("Route:" in label for label in routes)


def test_the_clarification_counters_survive_the_wire_as_integers(eliciting_network):
    """Counts that reach a log or a panel must not read 1.0."""
    first = eliciting_network.handle("30 year history", session_id="s-counts")
    second = eliciting_network.handle("30 year Treasury", session_id="s-counts",
                                      waiting=first.waiting, history=[])
    payload = second.waiting["input_request"]
    assert isinstance(payload["attempt"], int)
    assert isinstance(payload["retries_remaining"], int)
    assert payload["attempt"] == 1


def test_a_refusal_is_only_a_refusal_when_it_says_so():
    """Vagueness is not consent to stop; inferring it would kill live requests."""
    assert is_refusal("cancel")
    assert is_refusal("Never mind, forget it")
    assert is_refusal("stop")
    assert not is_refusal("nominal")
    assert not is_refusal("30 year Treasury")
    assert not is_refusal("I am not sure")
    assert not is_refusal("")


def test_a_new_turn_never_inherits_an_earlier_turns_data(counting_network):
    """The ledger dies with the turn, so nothing can be served from yesterday."""
    provider = counting_network._mcp_agent.data

    first = counting_network.handle("2s10s history", session_id="s-fresh")
    after_first = provider.history_calls
    assert after_first > 0
    assert first.tables

    # Same question, same input, brand new turn. The data layer must be read
    # again — this is exactly the case a cache would get wrong.
    second = counting_network.handle("2s10s history", session_id="s-fresh")
    assert provider.history_calls > after_first, (
        "the second turn was served from the first turn's result")
    assert second.tables
    # And the two turns are genuinely separate: different ledger, different tasks.
    assert first.handoffs["user_request_id"] != second.handoffs["user_request_id"]
    first_tasks = {h["task_id"] for h in first.handoffs["handoffs"]}
    second_tasks = {h["task_id"] for h in second.handoffs["handoffs"]}
    assert not (first_tasks & second_tasks)


def test_elicitation_answer_matching_refuses_to_guess():
    payload = input_request_payload({
        "tool": "search_series", "message": "nominal or real?",
        "schema": ElicitingProvider.SCHEMA, "fields": ["rate_kind"]})
    assert [o["label"] for o in user_options(payload)] == ["nominal", "real"]
    assert match_answer("Use the real series for this.", payload) == {"rate_kind": "real"}
    assert match_answer("either nominal or real is fine", payload) is None
    assert match_answer("whatever you think", payload) is None


def test_a_declined_task_does_not_claim_a_discussion_that_never_happened(network):
    """"0 rounds, did not converge" described a failure that never occurred."""
    wire(network, answerable=False)
    outcome = network.handle("give me the cusip for every bond", session_id="s-decl")

    assert outcome.negotiation is not None
    assert outcome.negotiation.held is False
    assert outcome.negotiation.decision == "UNSUPPORTED"
    assert outcome.negotiation.rounds_used == 0
    assert "declined before there was anything to negotiate" in outcome.negotiation.outcome

    labels = [s["label"] for s in outcome.trace]
    assert any("Discussion: not held" in label for label in labels), labels
    assert not any("did not converge" in label or "not converged" in label
                   for label in labels)
    # And the MCP agent was never asked to assess something nobody could serve.
    skills = [h["skill"] for h in outcome.handoffs["handoffs"]]
    assert "assess_data_requirement" not in skills


def test_a_held_discussion_still_reports_its_rounds(network):
    outcome = network.handle("2s10s history", session_id="s-held")
    assert outcome.negotiation.held is True
    assert outcome.negotiation.decision == "AGREED"
    assert any("1 round(s), converged" in s["label"] for s in outcome.trace)


def test_the_requirements_curve_family_reaches_the_data_layer(network):
    """A question about TIPS must not be answered with the nominal curve."""
    seen: list[str] = []
    provider = network._mcp_agent.data
    original = provider.get_rate_history

    def watch(tenor, start=None, end=None, kind="nominal"):
        seen.append(kind)
        return original(tenor, start, end, kind)

    provider.get_rate_history = watch

    wire(network, curve_family="real")
    outcome = network.handle("the real 10 year history", session_id="s-real")
    assert seen and set(seen) == {"real"}, seen
    assert outcome.tables
    assert outcome.tables[0]["provenance"]["rate_kind"] == "real"

    seen.clear()
    wire(network, curve_family="nominal")
    network.handle("the 10 year history", session_id="s-nom")
    assert seen and set(seen) == {"nominal"}, seen


def test_an_ambiguous_curve_family_asks_the_series_catalogue(eliciting_network):
    """The live route to a real MCP elicitation, and why one ever fires."""
    outcome = eliciting_network.handle("30 year history", session_id="s-ask")

    asked = [args for tool, args in eliciting_network._mcp_agent.data.tool_calls
             if tool == "search_series"]
    assert asked, "the agent guessed a curve family instead of asking"
    # y2 is nominal-only; y10 is published on both curves. Asking about the
    # nominal-only one would come back unambiguous and quietly settle a question
    # that was never actually put.
    assert asked[0]["query"] == "10 year", asked
    assert outcome.route == "clarify"


def test_an_ambiguous_family_with_no_named_tenors_still_asks(network):
    """A snapshot names no tenors, and that used to settle the question.

    "What is the 30 year?" was marked `ambiguous` by the expert — correctly, it
    is published on both curves — and then resolved silently to nominal,
    because a snapshot returns the whole curve and so carries no tenor list for
    the shared-tenor filter to match. The user was served a nominal par yield
    having never been asked, which is the exact silent wrong-curve failure the
    filter exists to prevent, reached by the one path it did not cover.

    An absent tenor list is not evidence that there is nothing to ask about.
    """
    calls: list[tuple[str, dict]] = []
    provider = network._mcp_agent.data
    provider.call_tool = lambda tool, args=None: calls.append((tool, args or {})) or {}

    family = network._mcp_agent._resolve_family(
        SimpleNamespace(curve_family="ambiguous"), [])

    assert any(t == "search_series" for t, _ in calls), (
        "an ambiguous family was resolved without asking anyone")
    assert family == "nominal"     # the fallback still stands once nobody answers


def test_a_maturity_only_one_curve_publishes_is_never_asked_about(network):
    """No round trip, and no question the user could not act on."""
    calls: list[tuple[str, dict]] = []
    provider = network._mcp_agent.data
    provider.call_tool = lambda tool, args=None: calls.append((tool, args or {})) or {}

    wire(network, curve_family="ambiguous")
    outcome = network.handle("the 2 year history", session_id="s-unambig")

    # The stub requirement asks for y2 and y10 — y10 is shared, so it IS asked.
    assert any(t == "search_series" for t, _ in calls)

    # Now a requirement whose tenors exist on the nominal curve alone.
    calls.clear()
    network._domain_expert_agent.derive = lambda q, t, c, f, r: (
        Requirement(task=t or q, answerable=True,
                    fields=["observation_date", "rate_percent", "quote_basis"],
                    rows=250, row_quote="250 trading days", grounded=True,
                    tenors=["y2", "y3"], curve_family="ambiguous",
                    citations=[CHUNK.as_dict()]), [CHUNK])
    outcome = network.handle("the 2s3s history", session_id="s-unambig-2")
    assert not any(t == "search_series" for t, _ in calls), calls
    assert outcome.route == "data_request"


# --- rule 7: guardrails -----------------------------------------------------


def test_the_handoff_budget_stops_a_turn_that_will_not_converge():
    """Breadth, which neither the chain nor the re-entry guard measures."""
    ledger = TurnLedger(handoff_limit=2)
    for _ in range(2):
        ledger.authorise(requesting_agent="a", target_agent="b", skill="s",
                         chain=CallChain(("a.x",)), digest="d1")
    with pytest.raises(HandoffRefused) as caught:
        ledger.authorise(requesting_agent="a", target_agent="b", skill="s",
                         chain=CallChain(("a.x",)), digest="d2")
    assert caught.value.kind == "handoff_limit"


def test_a_bounded_negotiation_is_not_mistaken_for_recursion():
    """The defect the flat depth counter caused, pinned.

    Five negotiation rounds are five *sibling* calls at one chain length. The
    old model counted them as nesting and refused the fourth, which is why the
    conversation the architecture was built for could never actually happen.
    """
    ledger = TurnLedger()
    chain = CallChain(("orchestrator.handle_user_turn",
                       "domain-expert.derive_data_requirement"))
    for round_ in range(1, 6):
        handoff, _ = ledger.authorise(
            requesting_agent="domain-expert", target_agent="mcp-agent",
            skill="assess_data_requirement", chain=chain,
            digest=f"round-{round_}", negotiation_round=round_,
            negotiation_phase="CAPABILITY_ASSESSMENT")
        assert handoff.chain_length == 3, "a sibling call grew the chain"
    assert ledger.used == 5
    assert ledger.as_dict()["negotiation_rounds"] == 5


def test_a_real_cycle_is_stopped_by_the_re_entry_guard():
    """A -> B -> A -> B -> A ... terminates, and says why."""
    ledger = TurnLedger(reentry_limit=3)
    chain = CallChain()
    with pytest.raises(HandoffRefused) as caught:
        for _ in range(10):
            target, skill = ("mcp-agent", "assess_data_requirement")
            ledger.authorise(requesting_agent="domain-expert",
                             target_agent=target, skill=skill,
                             chain=chain, digest="cycle")
            # A genuine cycle *nests*: each call happens inside the last.
            chain = chain.extend(target, skill)
    assert caught.value.kind == "reentry_limit"
    assert "cycle" in caught.value.reason


def test_runaway_nesting_is_stopped_by_the_chain_guard():
    """Distinct agents, ever deeper, never repeating: only length stops this."""
    ledger = TurnLedger(chain_limit=4)
    chain = CallChain()
    with pytest.raises(HandoffRefused) as caught:
        for i in range(10):
            ledger.authorise(requesting_agent="a", target_agent=f"agent{i}",
                             skill=f"skill{i}", chain=chain, digest=f"d{i}")
            chain = chain.extend(f"agent{i}", f"skill{i}")
    assert caught.value.kind == "chain_limit"


class _Completed:
    state = "completed"
    task_id = "t1"


def test_a_repeated_idempotent_request_is_answered_from_the_first_one():
    ledger = TurnLedger()
    handoff, cached = ledger.authorise(requesting_agent="a", target_agent="b",
                                       skill="s", chain=CallChain(("a.x",)),
                                       digest="same", repeatable=True)
    ledger.record(handoff, "same", _Completed(), time.perf_counter())
    _second, cached = ledger.authorise(requesting_agent="a", target_agent="b",
                                       skill="s", chain=CallChain(("a.x",)),
                                       digest="same", repeatable=True)
    assert cached is not None and cached.task_id == "t1"
    assert ledger.as_dict()["duplicates_suppressed"] == 1


def test_a_freshness_sensitive_repeat_is_never_answered_from_an_old_result():
    """Suppression is loop prevention, not a cache. Fetching data is repeated."""
    ledger = TurnLedger()
    handoff, cached = ledger.authorise(requesting_agent="a", target_agent="b",
                                       skill="execute", chain=CallChain(("a.x",)),
                                       digest="same")
    assert cached is None
    ledger.record(handoff, "same", _Completed(), time.perf_counter())
    second, cached = ledger.authorise(requesting_agent="a", target_agent="b",
                                      skill="execute", chain=CallChain(("a.x",)),
                                      digest="same")
    assert cached is None, "a data fetch was replayed from an earlier result"
    assert second.duplicate is False
    # It still costs a handoff, so a loop of them is bounded by the budget.
    assert ledger.used == 2


def test_the_cards_decide_what_may_be_replayed():
    """Read from the card, so discovery and enforcement cannot disagree."""
    assert is_idempotent(AgentId.MCP, "describe_data_capabilities")
    assert is_idempotent(AgentId.MCP, "assess_data_requirement")
    assert is_idempotent(AgentId.MCP, "list_data_choices")
    assert is_idempotent(AgentId.DOMAIN_EXPERT, "derive_data_requirement")
    # The three that touch data, money or a live task never are.
    assert not is_idempotent(AgentId.MCP, "execute_data_plan")
    assert not is_idempotent(AgentId.MCP, "provide_input")
    assert not is_idempotent(AgentId.ORCHESTRATOR, "handle_user_turn")
    # An unknown skill defaults to "do the work again".
    assert not is_idempotent(AgentId.MCP, "not_a_skill")


def test_identity_includes_the_agent_that_was_asked():
    """Two agents may advertise the same skill name; the callee is part of identity."""
    to_mcp = SkillRequest(skill="describe_data_capabilities", input={},
                          target_agent="mcp-agent")
    to_expert = SkillRequest(skill="describe_data_capabilities", input={},
                             target_agent="domain-expert")
    assert to_mcp.digest() != to_expert.digest()
    # But who asked is deliberately not part of it: the same question twice is
    # the same question, and that is the loop worth catching.
    same_question = SkillRequest(skill="describe_data_capabilities", input={},
                                 target_agent="mcp-agent",
                                 requesting_agent="orchestrator")
    assert to_mcp.digest() == same_question.digest()


def test_an_agent_refuses_a_chain_deeper_than_its_own_limit(network):
    """Enforced by the callee against its own configuration, not the caller's claim."""
    from a2a.types import TaskState

    deep = CallChain(tuple(f"agent{i}.skill{i}" for i in range(12)))
    message = build_request_message(
        SkillRequest(skill="describe_data_capabilities", input={},
                     requesting_agent="domain-expert", target_agent="mcp-agent",
                     call_chain=deep, handoff_budget=99),
        context_id="s-deep")
    response = post_jsonrpc(network.network_app,
                            f"{MOUNT_PATHS[AgentId.MCP]}/", message)
    task = response["body"]["result"]["task"]
    assert task["status"]["state"] == TaskState.Name(TaskState.TASK_STATE_REJECTED)
    assert "beyond the limit" in json.dumps(response["body"])


def test_an_agent_refuses_a_chain_that_keeps_revisiting_it(network):
    from a2a.types import TaskState

    cycling = CallChain(("mcp-agent.describe_data_capabilities",) * 4)
    message = build_request_message(
        SkillRequest(skill="describe_data_capabilities", input={},
                     requesting_agent="domain-expert", target_agent="mcp-agent",
                     call_chain=cycling, handoff_budget=99),
        context_id="s-cycle")
    response = post_jsonrpc(network.network_app,
                            f"{MOUNT_PATHS[AgentId.MCP]}/", message)
    task = response["body"]["result"]["task"]
    assert task["status"]["state"] == TaskState.Name(TaskState.TASK_STATE_REJECTED)
    assert "cycle" in json.dumps(response["body"])


def test_the_real_turn_stays_well_inside_its_budget(network):
    outcome = network.handle("2s10s history", session_id="s-budget")
    ledger = outcome.handoffs
    assert ledger["handoffs_used"] < ledger["handoff_limit"]
    assert ledger["max_chain_reached"] <= ledger["chain_limit"]


# --- rule 9: failure --------------------------------------------------------


def test_a_failing_specialist_becomes_a_sentence_not_a_stack_trace(network):
    def explode(*args, **kwargs):
        raise RuntimeError("qdrant refused the connection at 10.0.0.1:6333")

    network._domain_expert_agent.derive = explode
    outcome = network.handle("2s10s history", session_id="s-fail")

    assert "Traceback" not in outcome.answer
    assert "10.0.0.1" not in outcome.answer
    assert "could not be established" in outcome.answer
    # The cause is kept where a developer will look for it.
    failures = [s for s in outcome.trace if "did not complete" in s["label"]]
    assert failures and failures[0]["detail"]["kind"] == "agent_error"
    assert "RuntimeError" in failures[0]["detail"]["message"]


def test_an_unreachable_agent_is_reported_as_a_failure_not_as_an_empty_answer(network):
    class Dead:
        async def send_message(self, request, *, context=None):
            raise httpx.ConnectError("connection refused")
            yield  # pragma: no cover - makes this an async generator

        async def cancel_task(self, request, *, context=None):
            return None

    network.link(AgentId.MCP)._client = Dead()
    outcome = network.handle("2s10s history", session_id="s-dead")
    assert "not reachable" in outcome.answer
    assert "connection refused" not in outcome.answer


def test_a_call_that_overruns_is_cancelled_and_reported(network):
    """A hanging agent fails its caller rather than holding the turn open."""
    # Released once the assertions are made, so the abandoned worker finishes
    # inside the test rather than during fixture teardown. A `sleep` here would
    # be both slower and non-deterministic.
    release = threading.Event()

    def slow(*args, **kwargs):
        release.wait(30)
        return stub_requirement(), [CHUNK]

    network._domain_expert_agent.derive = slow
    ledger = TurnLedger(context_id="s-slow", turn_timeout_s=1)
    result = asyncio.run_coroutine_threadsafe(
        network.link(AgentId.DOMAIN_EXPERT).call(
            skill="derive_data_requirement",
            payload={"question": "q", "task": "t", "requested_fields": [],
                     "requested_rows": None},
            requesting_agent="orchestrator", ledger=ledger,
            chain=CallChain(("orchestrator.handle_user_turn",))),
        network.loop).result(30)

    assert result.state == "failed"
    # Over a socket a deadline raises; in-process the server can answer with the
    # unfinished task instead. Both are "it did not finish", and neither may be
    # mistaken for an answer.
    assert result.error["kind"] in {"timeout", "incomplete"}
    assert "1s" in result.error["message"]
    assert not result.artifacts
    release.set()


def test_a_calls_deadline_is_what_remains_of_the_turn_not_a_flat_number():
    """The bug this replaced was structural, not a mistuned constant.

    A call *contains* every call beneath it, so one flat deadline applied at
    every depth makes the outermost call the tightest bound in the system: it
    expires first by construction. In the running gateway that killed a
    negotiation which was proceeding normally — `derive` 80s, `assess` 78s,
    both legitimate provider retries — and reported the turn as hung.

    The remaining budget nests correctly instead: a child is always granted
    less than its parent, because time has passed.
    """
    ledger = TurnLedger(context_id="s-nest", turn_timeout_s=600)
    parent = ledger.remaining_seconds()
    ledger.started_at -= 120          # 2 minutes of the turn have gone
    child = ledger.remaining_seconds()

    assert child < parent, "a child was granted at least as long as its parent"
    assert child == pytest.approx(480, abs=2)


def test_an_exhausted_turn_still_grants_a_moment_rather_than_zero():
    """Zero would fail with a deadline error that reads like a hang."""
    ledger = TurnLedger(context_id="s-spent", turn_timeout_s=10)
    ledger.started_at -= 3600
    assert ledger.remaining_seconds() == 1.0


def test_the_turn_budget_cannot_be_configured_below_a_single_call(monkeypatch):
    from agents.a2a.guardrails import turn_timeout_s

    monkeypatch.setenv("A2A_CALL_TIMEOUT_SECONDS", "300")
    monkeypatch.setenv("A2A_TURN_TIMEOUT_SECONDS", "5")
    assert turn_timeout_s() == 300.0


def test_every_failure_kind_maps_to_a_sentence_with_no_internals_in_it():
    """The user-facing half of a failure names no host, port or exception."""
    from agents.pipeline import _user_facing_failure

    for kind in ("timeout", "handoff_limit", "depth_limit", "unavailable",
                 "empty_response", "caller_not_permitted", "agent_error"):
        for agent in AgentId:
            sentence = _user_facing_failure(agent, kind)
            assert sentence and sentence[0].isupper() and sentence.endswith(".")
            assert agent.value not in sentence
            assert kind not in sentence


# --- the other two routes ---------------------------------------------------


def test_small_talk_never_leaves_the_orchestrator(network):
    wire(network, route="direct")
    outcome = network.handle("hi", session_id="s-hi")
    assert outcome.route == "direct"
    calls = [h["to"] for h in outcome.handoffs["handoffs"]]
    assert calls == ["orchestrator"], "a greeting reached a specialist"


def test_a_clarification_is_grounded_in_what_the_data_layer_really_has(network):
    wire(network, route="clarify")
    outcome = network.handle("run a stress test", session_id="s-clarify")
    assert outcome.route == "clarify"
    calls = [(h["to"], h["skill"]) for h in outcome.handoffs["handoffs"]]
    assert ("mcp-agent", "list_data_choices") in calls


def test_summarise_goes_through_the_orchestrator_too(network):
    assert network.summarise([{"role": "user", "content": "yields"}]) == \
        "Treasury curve history"


def test_a_catalogue_keeps_its_calculations_across_the_wire():
    """The sender was updated and the rebuilder was not, and nothing caught it.

    `ToolSpec.as_dict` began emitting `kind: "calculation" | "retrieval"`, while
    `catalogue_from_dict` still read a boolean `executable`. Every risk tool
    therefore crossed the A2A boundary as unschedulable, and the domain expert
    reported "Available calculations: none" for a VaR question while both MCP
    servers sat there advertising nineteen tools. A round trip is the only test
    that would have seen it — each side was self-consistent.
    """
    from agents.a2a.envelope import catalogue_from_dict
    from agents.contracts import ToolCatalogue, ToolSpec

    sent = ToolCatalogue(
        tools=[ToolSpec("get_rate_history", "daily series", "data"),
               ToolSpec("compute_var", "historical VaR", "risk", executable=True)],
        fields=["rate_percent"], tenors=["y10"], can_calculate=True)
    back = catalogue_from_dict(sent.as_dict())

    assert back.executable_tools == sent.executable_tools == ["compute_var"]
    assert back.retrieval_tools == sent.retrieval_tools == ["get_rate_history"]


def test_an_older_peers_boolean_is_still_understood():
    """Accepting the old spelling costs one expression and removes a silent
    failure mode during a rollout."""
    from agents.a2a.envelope import catalogue_from_dict

    back = catalogue_from_dict({"tools": [
        {"name": "compute_var", "description": "d", "server": "risk",
         "executable": True}]})
    assert back.executable_tools == ["compute_var"]
