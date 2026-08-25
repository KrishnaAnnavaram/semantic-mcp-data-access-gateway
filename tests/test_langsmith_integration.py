"""LangSmith observability wired into the running system — offline.

Like `test_a2a.py`, these run with no model key, no Qdrant and no database: the
agents' model calls are stubbed and the transport is real. What is proved here is
that the observability plumbing is correct — trace headers cross the A2A boundary,
`/health` reports (and redacts) tracing status, the `/chat` contract carries the
trace fields, and a turn completes whether or not tracing is available.

LangSmith itself is not installed in this environment, so these also exercise the
fail-open path: every tracing helper is a no-op and no turn is harmed by it.
"""

from __future__ import annotations

import contextlib

import pytest
from backend.providers.base import MockDataProvider

from agents.a2a.envelope import (
    SkillRequest,
    build_request_message,
    read_request_message,
)
from agents.a2a.guardrails import CallChain
from agents.a2a.identity import AgentId
from agents.a2a.runtime import AgentNetwork

# Reuse the exact stubbing harness the A2A tests use, so these exercise the real
# wiring rather than a second, divergent set of doubles.
from tests.test_a2a import StubKnowledge, wire


@pytest.fixture
def network():
    net = wire(AgentNetwork(StubKnowledge(), MockDataProvider()))
    try:
        yield net
    finally:
        net.shutdown()


# --- envelope: trace headers cross the wire ---------------------------------


def test_trace_headers_round_trip_through_the_envelope():
    headers = {"langsmith-trace": "20240101T000000000000Zabc", "baggage": "k=v"}
    request = SkillRequest(
        skill="assess_data_requirement", input={"x": 1},
        requesting_agent="domain-expert", target_agent="mcp-agent",
        call_chain=CallChain(("orchestrator.handle_user_turn",)),
        trace_headers=headers)
    message = build_request_message(request, context_id="ctx-1")
    restored = read_request_message(message, AgentId.MCP)
    assert restored.trace_headers == headers


def test_missing_trace_headers_restore_as_none():
    request = SkillRequest(
        skill="assess_data_requirement", input={"x": 1},
        requesting_agent="domain-expert", target_agent="mcp-agent",
        call_chain=CallChain(("orchestrator.handle_user_turn",)))
    message = build_request_message(request, context_id="ctx-1")
    restored = read_request_message(message, AgentId.MCP)
    assert restored.trace_headers is None


def test_trace_headers_do_not_affect_the_duplicate_digest():
    # Duplicate suppression keys on what was asked, not on which trace it belongs
    # to. Two identical calls in different traces must still look identical.
    base = dict(skill="assess_data_requirement", input={"x": 1},
                requesting_agent="domain-expert", target_agent="mcp-agent")
    a = SkillRequest(**base, trace_headers={"langsmith-trace": "A"})
    b = SkillRequest(**base, trace_headers={"langsmith-trace": "B"})
    c = SkillRequest(**base, trace_headers=None)
    assert a.digest() == b.digest() == c.digest()


# --- /health reports and redacts --------------------------------------------


def test_health_includes_langsmith_block_and_hides_the_key(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_never_expose_this")
    from fastapi.testclient import TestClient

    from backend.api import service

    client = TestClient(service.app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "langsmith" in body
    assert body["langsmith"]["enabled"] is True
    assert body["langsmith"]["api_key_configured"] is True
    # The key itself must never appear anywhere in the response.
    assert "lsv2_never_expose_this" not in response.text


def test_health_is_ok_even_when_tracing_is_disabled(monkeypatch):
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2",
                 "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    from fastapi.testclient import TestClient

    from backend.api import service

    response = TestClient(service.app).get("/health")
    assert response.status_code == 200
    assert response.json()["langsmith"]["enabled"] is False


# --- /chat contract carries the trace fields --------------------------------


def test_chat_response_exposes_trace_fields(network):
    from backend.api.service import _response_for

    outcome = network.handle("What is the 2s10s history?", session_id="s-ls")
    response = _response_for(outcome)
    # The fields exist on the contract. They are None here because LangSmith is
    # not enabled in this environment — which is exactly the "tracing disabled ->
    # clean null URL" behaviour the frontend relies on.
    assert response.langsmith_url is None
    assert response.langsmith_trace_id is None
    assert response.langsmith_project is None
    # The handoff ledger, however, is always populated.
    assert response.handoffs is not None
    assert response.handoffs["handoffs_used"] >= 1


# --- distributed propagation across A2A -------------------------------------


def test_trace_headers_propagate_to_every_specialist(network, monkeypatch):
    """The core of distributed tracing: the headers a turn captures reach the
    specialists' executions, so their spans nest under one root.

    LangSmith is not installed, so instead of asserting on a real trace tree we
    prove the plumbing: stub the capture to a sentinel and record what each
    executor received on the far side of the A2A hop.
    """
    sentinel = {"langsmith-trace": "SENTINEL-TRACE", "baggage": "turn=1"}
    # Patch the capture at both worker-thread call sites (the names are bound at
    # import, so patch them where they are used).
    import agents.a2a.ports as ports
    import agents.pipeline as pipeline

    monkeypatch.setattr(pipeline, "current_trace_headers", lambda: sentinel)
    monkeypatch.setattr(ports, "current_trace_headers", lambda: sentinel)

    received: list[dict | None] = []

    @contextlib.contextmanager
    def recording_continue_trace(headers):
        received.append(headers)
        yield

    import agents.a2a.executors as executors

    monkeypatch.setattr(executors, "continue_trace", recording_continue_trace)

    outcome = network.handle("Give me the 2s10s history", session_id="s-prop")
    assert outcome.answer  # the turn still completes

    # Every specialist execution reached over A2A saw the sentinel headers. The
    # orchestrator's own execution is entered from the user boundary (no parent),
    # so at least the domain-expert and MCP-agent executions must carry them.
    with_sentinel = [h for h in received if h == sentinel]
    assert len(with_sentinel) >= 2


def test_turn_completes_when_trace_capture_returns_nothing(network, monkeypatch):
    """Fail-open: with no headers captured (tracing off, the default here), the
    turn runs exactly as before — propagation is additive, never required."""
    import agents.a2a.ports as ports
    import agents.pipeline as pipeline

    monkeypatch.setattr(pipeline, "current_trace_headers", lambda: None)
    monkeypatch.setattr(ports, "current_trace_headers", lambda: None)

    outcome = network.handle("What is the 2s10s history?", session_id="s-open")
    assert outcome.answer
    assert outcome.route == "data_request"


def test_real_capture_helper_is_safe_during_a_turn(network):
    """The shipped helpers must never raise on the request path.

    With LangSmith absent (this environment) the capture returns None, and a real
    turn using the genuine helpers completes normally — the contract the whole
    fail-open design rests on.
    """
    from agents.observability import current_trace_headers, run_id, run_url

    # Safe to call outside any run, too.
    assert current_trace_headers() is None
    assert run_url() is None
    assert run_id() is None

    outcome = network.handle("2s10s history", session_id="s-safe")
    assert outcome.answer
    # No trace was produced, so the outcome's link fields are cleanly null.
    assert outcome.langsmith_url is None
    assert outcome.langsmith_trace_id is None
