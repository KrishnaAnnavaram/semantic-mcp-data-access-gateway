"""Tier 6 — the running service, end to end. Needs the backend on :8000.

The hardest tier and the slowest: every test here spends real model tokens, so
responses are shared across assertions where the assertions are independent.

Model output is not deterministic, so these assert *invariants* — the shape of
the contract, the labels that must survive, the identifiers that must never
leak — never an exact sentence.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

pytestmark = pytest.mark.usefixtures("api")

# Internal identifiers that must never reach the user as if they were speech.
INTERNAL_TOOL_NAMES = {
    "list_datasets", "list_series", "search_series", "get_series_coverage",
    "get_curve", "get_rate_history", "get_curve_history_matrix", "explain_number",
    "list_portfolios", "get_portfolio", "list_scenarios", "get_scenario",
    "export_curve_csv", "brief_dataset_caveat", "price_portfolio_tool",
    "compute_dv01_tool", "compute_key_rate_dv01_tool", "run_stress_tool",
    "compute_historical_risk_tool", "retrieve_knowledge", "get_curve_slope",
    "get_latest_rates",
}

CONTRACT_KEYS = {"answer", "sources", "trace", "awaiting_clarification"}


def fresh(name: str) -> str:
    """A session id no previous run has used.

    Sessions are held server-side for the life of the process, so a fixed id
    silently carries yesterday's transcript into today's assertion — which is
    exactly how `test_a_specific_data_question_actually_calls_a_tool` first went
    red against perfectly good code.
    """
    import uuid
    return f"qa-t6-{name}-{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="module")
def curve_answer(chat):
    return chat("What is the current 2s10s slope?", fresh("curve"))


@pytest.fixture(scope="module")
def clarify_answer(chat):
    return chat("i want to perform stress testing", fresh("clarify"))


@pytest.fixture(scope="module")
def portfolio_answer(chat):
    return chat("List the demo portfolios available.", fresh("portfolio"))


# --- the contract -----------------------------------------------------------


def test_health_reports_its_key_configuration(api):
    with urllib.request.urlopen(f"{api}/health", timeout=10) as response:
        body = json.loads(response.read())
    assert body["status"] == "ok"
    assert body["api_key_configured"] is True


def test_chat_returns_every_contract_key(curve_answer):
    assert CONTRACT_KEYS <= set(curve_answer)


def test_chat_rejects_a_malformed_body(api):
    """A missing `query` must be a validation error, not a 500."""
    request = urllib.request.Request(
        f"{api}/chat", data=json.dumps({"nope": 1}).encode(),
        headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=30)
    assert caught.value.code == 422


def test_the_trace_is_json_serialisable(curve_answer):
    """The UI renders it; a non-serialisable step breaks the whole panel."""
    json.dumps(curve_answer["trace"])


def test_every_trace_step_declares_a_kind(curve_answer):
    kinds = [s.get("kind") or s.get("type") for s in curve_answer["trace"]]
    assert all(kinds)
    assert set(kinds) <= {"intent", "knowledge", "decision", "tool_call",
                          "answer", "clarification"}


def test_a_trace_never_repeats_the_same_step_twice_in_a_row(curve_answer,
                                                            clarify_answer,
                                                            portfolio_answer):
    """Regression: the orchestrator used to re-append the quant agent's own
    clarification step, so the panel showed the question twice."""
    for response in (curve_answer, clarify_answer, portfolio_answer):
        steps = [(s.get("kind") or s.get("type"), str(s.get("detail"))[:120])
                 for s in response["trace"]]
        duplicates = [a for a, b in zip(steps, steps[1:]) if a == b]
        assert duplicates == [], f"repeated trace step: {duplicates}"


# --- routing ----------------------------------------------------------------


def test_a_specific_data_question_is_answered_not_queried_back(curve_answer):
    assert curve_answer["awaiting_clarification"] is False
    assert curve_answer["answer"].strip()


def test_a_specific_data_question_actually_calls_a_tool(curve_answer):
    """An answer with no tool call is a number the model invented."""
    kinds = [s.get("kind") or s.get("type") for s in curve_answer["trace"]]
    assert "tool_call" in kinds


def test_an_underspecified_request_asks_rather_than_guessing(clarify_answer):
    assert clarify_answer["awaiting_clarification"] is True
    assert clarify_answer["answer"].rstrip().endswith("?")


def test_a_clarification_carries_an_elicitation_payload(clarify_answer):
    assert clarify_answer.get("elicitation")


def test_a_completed_answer_carries_no_elicitation(curve_answer, portfolio_answer):
    """Regression: a complete answer ending in '?' was flagged as a pending question."""
    for response in (curve_answer, portfolio_answer):
        assert response["awaiting_clarification"] is False
        assert not response.get("elicitation")


# --- what reaches the user --------------------------------------------------


def test_elicitation_options_are_speech_not_internal_identifiers(clarify_answer):
    """The value is sent verbatim as the user's next turn.

    Observed defect: an option whose value was `list_portfolios` put a raw tool
    name in the transcript as if the user had typed it. Whatever the model
    generates, an option must read as something a person would say.
    """
    options = (clarify_answer.get("elicitation") or {}).get("options") or []
    if not options:
        pytest.skip("this turn offered no options (model output varies)")
    leaked = [o for o in options
              if o.get("value", "").strip() in INTERNAL_TOOL_NAMES
              or o.get("label", "").strip() in INTERNAL_TOOL_NAMES]
    assert leaked == [], f"internal identifier offered as a user utterance: {leaked}"


def test_elicitation_options_are_complete(clarify_answer):
    options = (clarify_answer.get("elicitation") or {}).get("options") or []
    if not options:
        pytest.skip("this turn offered no options (model output varies)")
    assert all(o.get("label", "").strip() and o.get("value", "").strip() for o in options)


def test_the_demo_book_is_never_presented_as_real(portfolio_answer):
    """SYNTHETIC_DEMO must survive all the way into the wording."""
    answer = portfolio_answer["answer"].upper()
    assert "SYNTHETIC" in answer or "DEMO" in answer


def test_a_curve_answer_states_its_observation_date(curve_answer):
    """A rate without a date is not an answer."""
    assert "2026-" in curve_answer["answer"] or "202" in curve_answer["answer"]


# --- sessions ---------------------------------------------------------------


def test_a_clarification_can_be_continued_in_the_same_session(chat):
    """The whole point of session_id: the answer must land in context."""
    session = fresh("session")
    first = chat("i want to run a stress test", session)
    assert first["awaiting_clarification"] is True
    second = chat("historical replay", session)
    assert second["answer"].strip()


def test_separate_sessions_do_not_share_history(chat):
    chat("Remember the number 8675309.", fresh("iso-a"))
    other = chat("What number did I just ask you to remember?", fresh("iso-b"))
    assert "8675309" not in other["answer"]


@pytest.mark.xfail(
    strict=False,
    reason="KNOWN DEFECT (QA-1): asked the same market-data question twice in one "
           "session, the agent answers from conversation memory instead of "
           "re-fetching. Harmless seconds apart; across a data refresh it serves a "
           "stale rate while calling it current.",
)
def test_a_repeated_market_question_refetches_rather_than_recalling(chat):
    """Rates change daily; 'current' must mean re-read, not remembered.

    Turn 1 calls a tool. Turn 2, identical question, returns
    'Same as just reported' with a trace of intent/decision/answer and no tool
    call - so the figure's currency is asserted rather than checked. The
    envelope carries `dataset_snapshot_id` precisely so staleness is detectable,
    and a recalled answer never consults it.
    """
    session = fresh("refetch")
    first = chat("What is the current 2s10s slope?", session)
    second = chat("What is the current 2s10s slope?", session)

    def kinds(response):
        return [s.get("kind") or s.get("type") for s in response["trace"]]

    assert "tool_call" in kinds(first)
    assert "tool_call" in kinds(second), (
        "second turn answered without re-reading the curve: " + str(kinds(second)))
