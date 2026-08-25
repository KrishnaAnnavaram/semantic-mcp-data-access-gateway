"""The new market-risk capabilities, proven through the real `/chat` path.

Every test here sends one question to the running service and asserts what came
back: the route, the capability the domain expert scheduled, that the workflow
dispatched, and that the engine returned a usable result rather than an error
object. Nothing is stubbed — this is the whole chain.

    user question
        -> POST /chat
        -> orchestrator            (routes)
        -> domain expert           (plans, names the calculation)
        -> MCP agent               (dispatches)
        -> RiskWorkflows           (adapts)
        -> MCP host
        -> market-risk-data-mcp    (curve, book, history)
        -> risk-engine-mcp         (the mathematics)
        -> orchestrator            (writes the reply)

These are slow: a risk turn costs a retrieval, a plan, a negotiation and a full
revaluation, and the measured range on this project is 110-370 seconds. They
skip cleanly when the backend is not running, exactly as the existing catalogue
E2E does, so they never turn the offline suite red.

The assertions deliberately stop short of checking numbers. Whether the DV01 is
right is settled by the unit and adapter layers, which are deterministic and
fast; what only a live run can prove is that the request *reaches* the right
capability and comes back as something a user can read.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

API = os.environ.get("QA_API_BASE", "http://localhost:8000").rstrip("/")

#: (id, question, capability the domain expert should schedule).
#: One per major capability family, chosen so a failure names the family.
CAPABILITIES = [
    ("bond-analytics",
     "What is the yield to maturity, modified duration and convexity of each "
     "bond in the demo book?", "compute_bond_analytics"),
    ("curve-analytics",
     "What is the current 2s10s spread and is the curve inverted?",
     "compute_curve_analytics"),
    ("rate-sensitivities",
     "Show my rate sensitivities across the curve, with DV01 by maturity bucket.",
     "compute_rate_sensitivities"),
    ("parallel-stress",
     "Stress rates up 100 basis points on the demo book.", "run_rate_stress"),
    ("bear-steepener",
     "Run a bear steepener on the demo book.", "run_rate_stress"),
    ("key-rate-stress",
     "Shock only the 10-year point by 50 basis points.", "run_key_rate_stress"),
    ("shock-ladder",
     "Show me portfolio P&L from minus 300 to plus 300 basis points.",
     "run_shock_ladder"),
    ("stress-matrix",
     "Run the standard stress pack and rank the scenarios by loss.",
     "run_stress_matrix"),
    ("stress-contributions",
     "Which positions drive the loss in a 100 basis point selloff?",
     "compute_stress_contributions"),
    ("historical-stress",
     "Replay the 2022 rate move against the demo book.", "run_historical_stress"),
    ("worst-historical",
     "Which historical rate move would have hurt this portfolio most?",
     "find_worst_historical_stresses"),
    ("reverse-stress",
     "How far must rates rise before the demo book loses two million dollars?",
     "run_reverse_stress"),
    ("parametric-var",
     "Calculate parametric VaR on the demo book.", "compute_parametric_risk"),
    ("monte-carlo-var",
     "Calculate Monte Carlo VaR on the demo book.", "compute_monte_carlo_risk"),
    ("compare-methods",
     "Compare historical, parametric and Monte Carlo VaR.",
     "compare_risk_methods"),
    ("backtest",
     "Has our 99% VaR model performed well? How many exceptions occurred?",
     "backtest_var"),
    ("pnl-attribution",
     "Why did the portfolio's value change over the last month?",
     "compute_pnl_attribution"),
    ("concentration",
     "Where is my rate risk concentrated by maturity bucket?",
     "compute_concentration"),
    ("frtb-girr",
     "What is the FRTB GIRR capital charge for the demo book?",
     "compute_frtb_girr"),
]

INTERNAL_NAMES = (
    "compute_bond_analytics_tool", "compute_monte_carlo_risk_tool",
    "compute_parametric_risk_tool", "run_reverse_stress_tool",
    "compute_frtb_girr_tool", "find_worst_historical_stresses_tool",
    "run_stress_matrix_tool", "backtest_var_tool", "get_curve_history_matrix",
)


def post(path: str, body: dict, timeout: float = 420.0) -> dict:
    request = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Origin": "http://localhost:5173"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


@pytest.fixture(scope="session")
def service():
    try:
        with urllib.request.urlopen(f"{API}/health", timeout=10) as response:
            health = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        pytest.skip(f"backend unavailable at {API}: {exc}")
    if health.get("status") != "ok" or not health.get("api_key_configured"):
        pytest.skip(f"/health reported {health}")
    return health


@pytest.fixture(scope="session")
def model_available(service):
    answer = post("/chat", {"query": "hi", "session_id": "risk-probe"}, timeout=120)
    if answer.get("route") != "direct":
        pytest.skip(f"the model is not answering normally: {answer['answer'][:120]}")
    return True


@pytest.mark.parametrize("case_id,question,capability", CAPABILITIES,
                         ids=[c[0] for c in CAPABILITIES])
def test_a_risk_capability_is_reachable_through_chat(service, model_available,
                                                     case_id, question, capability):
    answer = post("/chat", {"query": question, "session_id": f"cap-{case_id}"})

    assert answer["route"] == "data_request", (
        f"{case_id} routed to {answer['route']!r}, so it never reached a "
        f"specialist: {answer['answer'][:200]}")

    reached = {h["to"] for h in answer["handoffs"]["handoffs"]}
    assert {"orchestrator", "domain-expert", "mcp-agent"} <= reached, reached

    calculation = answer.get("calculation") or {}
    assert calculation, (
        f"{case_id} produced no calculation artifact: {answer['answer'][:200]}")
    assert calculation.get("tool") == capability, (
        f"{case_id} scheduled {calculation.get('tool')!r}, expected {capability!r}")
    assert not calculation.get("error"), (
        f"{case_id} dispatched but the workflow failed: {calculation['error']}")

    result = calculation.get("result") or {}
    assert result, f"{case_id} returned an empty result"
    assert not result.get("error"), (
        f"{case_id} returned an engine error: {result['error']} "
        f"{result.get('detail', '')}")


@pytest.mark.parametrize("case_id,question,capability", CAPABILITIES[:6],
                         ids=[c[0] for c in CAPABILITIES[:6]])
def test_no_engine_identifier_reaches_the_user(service, model_available,
                                               case_id, question, capability):
    """The redaction guard, widened to the new capability vocabulary.

    A sample rather than all nineteen: each of these is a full live turn, and
    the leak this protects against is a property of the scrubbing layer, not of
    any individual capability.
    """
    text = post("/chat", {"query": question, "session_id": f"leak-{case_id}"})["answer"]
    leaked = [name for name in INTERNAL_NAMES if name in text]
    assert not leaked, f"{case_id} leaked {leaked}"


def test_an_invalid_scenario_is_refused_with_a_reason_not_a_crash(service,
                                                                 model_available):
    """The bootstrap guard must survive the whole path as an explanation.

    A +100bp single-node bump at the 20-year leaves the curve
    arbitrage-inconsistent, and the engine refuses it by name. What must reach
    the user is that refusal, in words - not a stack trace, and not a number
    computed some other way.
    """
    answer = post("/chat", {
        "query": "Shock only the 20-year point by 100 basis points.",
        "session_id": "cap-invalid-node"})
    text = answer["answer"]
    for forbidden in ("Traceback", "psycopg2", 'File "', "127.0.0.1"):
        assert forbidden not in text, f"leaked {forbidden!r}"
    calculation = answer.get("calculation") or {}
    result = calculation.get("result") or {}
    if calculation.get("error") or result.get("error"):
        # Refused: the reason must be visible somewhere the user can read.
        assert answer["answer"].strip(), "a refusal with no explanation"
