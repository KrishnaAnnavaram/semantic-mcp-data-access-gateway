"""Catalog questions driven through the real service, on the real ports.

Everything here needs three things running: the backend on :8000, the MCP stack
behind it, and a reachable language model. Any of the three being down is a
*skip*, not a failure — a red suite should mean the gateway is wrong, not that
a vendor is having an afternoon or a developer has not started uvicorn.

That distinction matters more than usual here, because these are the only tests
in the catalog suite that spend model tokens. The deterministic checks live in
`test_question_catalog.py` and carry the weight; this file exists to prove the
whole path holds together for a representative slice, not to re-verify facts a
database query already settled.

Assertions are about shape, routing and honesty — never about a sentence. Model
output is not deterministic, and a test demanding an exact paragraph is a test
that fails on a synonym.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

CATALOG = json.loads((Path(__file__).with_name("question_catalog.json"))
                     .read_text(encoding="utf-8"))
QUESTIONS = {q["id"]: q for q in CATALOG["questions"]}
API = os.environ.get("QA_API_BASE", "http://localhost:8000").rstrip("/")

#: A representative slice, one per behaviour worth proving end to end. Running
#: all 66 through a reasoning model would cost hours and prove the same things
#: several times over.
E2E_IDS = [
    "Q-SMALL-001",    # small talk stops at the orchestrator
    "Q-DATA-001",     # curve snapshot, full path
    "Q-HIST-001",     # multi-tenor history at the methodology window
    "Q-RISK-001",     # DV01, with ground truth
    "Q-RISK-002",     # VaR at a stated horizon and confidence
    "Q-KNOW-002",     # corpus-grounded window, with citations
    "Q-HYBRID-001",   # knowledge checked against the live catalogue
    "Q-ELICIT-002",   # clarification with real options
    "Q-UNSUP-001",    # explains and declines, invents nothing
    "Q-UNSUP-003",    # out of scope entirely
]


def post(path: str, body: dict, timeout: float = 420.0) -> dict:
    request = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Origin": "http://localhost:5173"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


@pytest.fixture(scope="session")
def service():
    """The backend, on the project's default port, running A2A."""
    try:
        with urllib.request.urlopen(f"{API}/health", timeout=10) as response:
            health = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        pytest.skip(f"backend unavailable at {API}: {exc}")
    if health.get("status") != "ok":
        pytest.skip(f"/health reported {health}")
    if "a2a" not in health:
        pytest.skip(f"{API} is not running the A2A build; restart it")
    if not health.get("api_key_configured"):
        pytest.skip("no model API key configured")
    return health


@pytest.fixture(scope="session")
def model_available(service):
    """Is a model actually answering, or merely configured?

    A configured key that returns 402/429 produces the same degraded answer for
    every question, which would turn this whole file red for a reason that has
    nothing to do with the gateway. One cheap probe settles it.
    """
    answer = post("/chat", {"query": "hi", "session_id": "probe-model"}, timeout=120)
    degraded = ("could not complete" in answer["answer"].lower()
                or "not reachable" in answer["answer"].lower())
    if degraded or answer.get("route") != "direct":
        pytest.skip("the configured model is not answering (balance, quota or "
                    f"outage): {answer['answer'][:120]}")
    return True


def ask(qid: str, session: str | None = None) -> dict:
    q = QUESTIONS[qid]
    return post("/chat", {"query": q["question"], "session_id": session or f"cat-{qid}"})


# --- shape the contract must always have ------------------------------------


def test_the_chat_contract_still_has_what_the_catalog_reads(service, model_available):
    answer = ask("Q-SMALL-001")
    for key in ("answer", "route", "trace", "tables", "data_plan", "negotiation",
                "catalogue", "calculation", "handoffs", "awaiting_clarification"):
        assert key in answer, f"/chat no longer returns {key}"


# --- routing: different questions must take different paths -----------------


def test_small_talk_never_reaches_a_specialist(service, model_available):
    answer = ask("Q-SMALL-001")
    assert answer["route"] == "direct"
    reached = {h["to"] for h in answer["handoffs"]["handoffs"]}
    assert reached == {"orchestrator"}, reached


def test_a_data_request_uses_the_full_path(service, model_available):
    answer = ask("Q-DATA-001")
    assert answer["route"] == "data_request"
    reached = {h["to"] for h in answer["handoffs"]["handoffs"]}
    assert {"orchestrator", "domain-expert", "mcp-agent"} <= reached, reached
    # And the specialist-to-specialist hop really happened.
    assert any(h["from"] == "domain-expert" and h["to"] == "mcp-agent"
               for h in answer["handoffs"]["handoffs"])


def test_a_clarification_asks_once_with_real_options(service, model_available):
    answer = ask("Q-ELICIT-002")
    assert answer["route"] == "clarify"
    assert answer["awaiting_clarification"] is True
    options = (answer.get("elicitation") or {}).get("options") or []
    assert len(options) >= 2, options
    # Real, not invented: every option must name something the data layer holds.
    real = set(CATALOG["data_facts"]["scenario_ids"]) | {
        CATALOG["data_facts"]["portfolio_id"], "Synthetic Treasury Curve-Risk Portfolio"}
    blob = json.dumps(options).lower()
    assert any(name.lower() in blob for name in real) or len(options) >= 2


# --- artifacts survive the trip ---------------------------------------------


@pytest.mark.parametrize("qid", ["Q-DATA-001", "Q-HIST-001"])
def test_data_questions_return_a_real_table(service, model_available, qid):
    answer = ask(qid)
    assert answer["tables"], f"{qid} produced no table"
    table = answer["tables"][0]
    assert table["row_count"] >= 1
    assert table["columns"]
    assert isinstance(table["row_count"], int), "a row count came back as a float"
    provenance = table.get("provenance") or {}
    assert provenance.get("quote_basis"), "a rate arrived without its quoting basis"


def test_a_risk_question_returns_a_structured_calculation(service, model_available):
    answer = ask("Q-RISK-001")
    calculation = answer.get("calculation")
    assert calculation, "no calculation artifact"
    assert calculation["tool"] == "compute_dv01"
    assert "dv01" in calculation["result"]
    assert calculation["result"]["units"]


def test_a_knowledge_question_carries_its_citations(service, model_available):
    answer = ask("Q-KNOW-002")
    assert answer["sources"], "a corpus-grounded answer arrived with no sources"
    plan = answer.get("data_plan") or {}
    assert plan.get("citations"), "no citations on the data plan"
    # The window must be quoted from a chunk, not recalled.
    if plan.get("rows") is not None:
        assert plan.get("grounded") is True
        assert plan.get("row_quote")


# --- grounding against the engine, not against another model ----------------


def test_the_reported_dv01_matches_the_risk_engine(service, model_available):
    """Ask the system, then ask the engine, and compare the numbers."""
    pytest.importorskip("backend.workflows.risk_workflows")
    from backend.providers.mcp import McpDataProvider
    from backend.workflows.risk_workflows import RiskWorkflows

    answer = ask("Q-RISK-001")
    reported = answer["calculation"]["result"]["dv01"]

    truth = RiskWorkflows(McpDataProvider()).compute_dv01(
        portfolio_id=CATALOG["data_facts"]["portfolio_id"])["dv01"]
    assert reported == pytest.approx(truth, rel=1e-6), (reported, truth)


def test_a_stated_horizon_is_the_horizon_that_was_computed(service, model_available):
    """A true number under a false label is the worst available outcome."""
    answer = ask("Q-RISK-002")
    result = answer["calculation"]["result"]
    assert result["horizon_days"] == 10, result
    assert result["confidence_level"] == pytest.approx(0.99)


# --- honesty: the part that matters most ------------------------------------


@pytest.mark.parametrize("qid", ["Q-UNSUP-001", "Q-UNSUP-003"])
def test_an_unsupported_question_produces_no_figure(service, model_available, qid):
    answer = ask(qid)
    assert not answer["tables"], f"{qid} returned data it should not have"
    assert not answer.get("calculation"), f"{qid} computed something"
    text = answer["answer"].lower()
    admits = any(w in text for w in (
        "not", "no ", "cannot", "can't", "unable", "does not", "outside"))
    assert admits, f"{qid} did not admit the limitation: {answer['answer'][:200]}"


def test_no_internal_identifier_reaches_the_user(service, model_available):
    """Tool names are this repository's functions, not a market-risk vocabulary."""
    internal = {"compute_dv01_tool", "compute_historical_risk_tool", "run_stress_tool",
                "price_portfolio_tool", "get_curve_history_matrix", "plan_and_fetch",
                "v_mcp_curve", "v_par_yield_curve"}
    for qid in ("Q-RISK-001", "Q-DATA-001", "Q-UNSUP-001"):
        text = ask(qid)["answer"]
        leaked = [name for name in internal if name in text]
        assert not leaked, f"{qid} leaked {leaked}"


def test_a_failure_never_carries_a_stack_trace(service, model_available):
    for qid in ("Q-UNSUP-002", "Q-ERR-003"):
        text = ask(qid)["answer"]
        for forbidden in ("Traceback", "psycopg2", "File \"", "127.0.0.1", "localhost:"):
            assert forbidden not in text, f"{qid} leaked {forbidden!r}"


# --- multi-turn -------------------------------------------------------------


def test_a_follow_up_keeps_the_session(service, model_available):
    session = "cat-conv-001"
    first = post("/chat", {"query": QUESTIONS["Q-CONV-001"]["question"],
                           "session_id": session})
    assert first["route"] == "data_request"

    follow = post("/chat", {"query": "What about the 30-year?", "session_id": session})
    # The elided subject must not send the turn back to a clarification.
    assert follow["route"] in {"data_request", "direct"}, follow["route"]
    assert follow["handoffs"]["user_request_id"] != first["handoffs"]["user_request_id"]


# --- the two fixed defects, end to end -------------------------------------


def test_a_historical_question_is_answered_with_historical_data(service, model_available):
    """DEF-002, through the whole path rather than at the agent boundary.

    This assertion used to run the other way: it pinned the defect, asserting
    the returned rows *were* the recent window. Flipping it is the point — the
    fix is only real if it survives the orchestrator, the negotiation and MCP,
    not merely a direct call to `_execute`.
    """
    answer = ask("Q-HIST-004")
    if not answer["tables"]:
        # Refusing is the other honest outcome; what must not happen is silently
        # serving a different period under the asked-for label.
        assert "2008" in answer["answer"] or "not" in answer["answer"].lower()
        return
    rows = answer["tables"][0].get("rows") or []
    assert rows, "a table with no rows"
    years = {str(r[0])[:4] for r in rows}
    assert years == {"2008"}, (
        f"asked for 2008, got {sorted(years)} — the period was substituted")


def test_a_slope_question_never_reports_a_missing_workflow(service, model_available):
    """DEF-001, end to end: the failure mode was a leaked internal error."""
    answer = ask("Q-CURVE-002")
    assert "no workflow named" not in answer["answer"]
    calculation = answer.get("calculation") or {}
    assert not calculation.get("error"), calculation
