"""Layer 2 tests — data provider and the /chat service.

Fast and offline: no ANTHROPIC_API_KEY, no network, no vector download. The live
LLM loop is intentionally not exercised here.
"""

from backend.providers.base import MockDataProvider


# --- Treasury-shaped mock data provider ---------------------------------------

def test_latest_curve_matches_published_base():
    d = MockDataProvider()
    curve = d.get_yield_curve()["points"]
    assert curve["y2"] == 4.22
    assert curve["y10"] == 4.70
    assert curve["y30"] == 5.24


def test_2s10s_slope():
    d = MockDataProvider()
    slope = d.get_curve_slope(short="y2", long="y10")
    assert slope["slope_bps"] == 48.0  # (4.70 - 4.22) * 100


def test_rate_history_shape():
    d = MockDataProvider()
    hist = d.get_rate_history("y10")
    assert len(hist) == 252
    assert hist[-1]["observation_date"] == "2026-08-11"
    assert all("rate_percent" in row for row in hist)


def test_series_catalogue():
    d = MockDataProvider()
    series = d.list_series()
    assert len(series) == 19  # 14 nominal + 5 real
    assert {s["rate_kind"] for s in series} == {"nominal", "real"}


def test_unknown_tenor_is_handled():
    d = MockDataProvider()
    assert d.get_rate_history("zz9") == []
    assert "error" in d.get_curve_slope(short="zz9", long="y10")


# --- clarification is structural, never inferred from the prose ---------------
#
# The old single-agent loop had to guess: it read the final character of the
# answer, so a complete 2,302-character DV01 write-up ending "Want me to run
# DV01?" was reported as a pending question, while the same answer ending "Say
# which and I'll run it." was not. Identical intent, opposite classification.
#
# The three-agent pipeline cannot make that mistake, because the orchestrator
# *decides* the route before anything is composed. These tests pin that: the
# flag follows the route, and nothing else.

def _outcome(route: str, answer: str):
    from agents.contracts import AgentOutcome, Intent

    return AgentOutcome(answer=answer, route=route,
                        intent=Intent(route=route, reasoning="fixture",
                                      question=answer))


def test_awaiting_clarification_follows_the_route_not_the_punctuation():
    """An answer that ends by offering a next step is still an answer."""
    from backend.api.service import _response_for  # noqa: PLC0415

    offer = "DV01 is the change in value for a 1bp move.\n\nWant me to run it?"
    assert _response_for(_outcome("data_request", offer)).awaiting_clarification is False
    assert _response_for(_outcome("direct", offer)).awaiting_clarification is False


def test_a_clarify_route_is_reported_as_a_pending_question():
    from backend.api.service import _response_for  # noqa: PLC0415

    ask = "Historical replay or hypothetical scenario?"
    response = _response_for(_outcome("clarify", ask))
    assert response.awaiting_clarification is True
    assert response.elicitation is not None
    assert response.elicitation.question == ask


# --- /chat service (no LLM call) ----------------------------------------------

def test_service_health_and_validation():
    from fastapi.testclient import TestClient

    from backend.api import service as agent_service

    client = TestClient(agent_service.app)
    assert client.get("/health").status_code == 200
    # empty query fails validation before any agent/LLM work happens
    assert client.post("/chat", json={"query": ""}).status_code == 422
