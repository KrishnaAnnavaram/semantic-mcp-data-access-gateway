"""The question catalog, checked against the system it claims to describe.

`question_catalog.json` is a claim about what this gateway can answer. A claim
nobody checks rots: the data moves, a tool is renamed, a capability quietly
stops working, and the document goes on saying otherwise. These tests are what
stop that — every fact the catalog asserts is re-derived here from the live
PostgreSQL database, the live Qdrant collection, the connected MCP servers and
the agents' own code.

Four levels, in order of how much they need to be running:

    integrity     the catalog is well-formed and internally consistent  (always)
    data facts    every asserted number matches PostgreSQL / Qdrant     (needs stores)
    capability    every named tool is actually reachable                (needs MCP)
    grounding     the numbers the system reports match the engine       (needs MCP)

Nothing here calls a language model. That is deliberate: these assertions are
about capability and data, both deterministic, and a suite that needs a model to
tell you whether your database has 52 series is a suite that goes red when a
vendor has an outage. The model-dependent end-to-end checks live in
`test_catalog_e2e.py` and skip cleanly when no model is reachable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

CATALOG_PATH = Path(__file__).with_name("question_catalog.json")
CATALOG = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
FACTS = CATALOG["data_facts"]
QUESTIONS = CATALOG["questions"]

SUPPORT_VALUES = {"YES", "PARTIAL", "NO"}
ROUTES = {"direct", "clarify", "data_request"}
STATES = {"completed", "input-required", "failed", "canceled", "rejected"}
AGENTS = {"orchestrator", "domain-expert", "mcp-agent"}


def ids(questions):
    return [q["id"] for q in questions]


# --- level 1: is the catalog even coherent? ---------------------------------


def test_every_question_has_the_fields_the_tests_read():
    required = {"id", "category", "question", "intent", "sources", "expected_agents",
                "expected_route", "expected_state", "expected_artifacts",
                "expected_tools", "requires_elicitation", "supported", "assertions"}
    for q in QUESTIONS:
        missing = required - set(q)
        assert not missing, f"{q.get('id')} is missing {sorted(missing)}"


def test_ids_are_unique():
    seen = ids(QUESTIONS)
    duplicates = {i for i in seen if seen.count(i) > 1}
    assert not duplicates, f"duplicate question ids: {sorted(duplicates)}"


@pytest.mark.parametrize("q", QUESTIONS, ids=ids(QUESTIONS))
def test_enumerated_values_are_legal(q):
    assert q["supported"] in SUPPORT_VALUES
    assert q["expected_route"] in ROUTES
    assert q["expected_state"] in STATES
    assert set(q["expected_agents"]) <= AGENTS, q["expected_agents"]
    assert set(q["sources"]) <= {"postgres", "qdrant"}


@pytest.mark.parametrize("q", QUESTIONS, ids=ids(QUESTIONS))
def test_anything_less_than_supported_says_why(q):
    """A PARTIAL or NO without a reason is an unexplained excuse."""
    if q["supported"] != "YES":
        assert q.get("reason"), f"{q['id']} is {q['supported']} with no reason"
        assert len(q["reason"]) > 40, f"{q['id']} reason is too thin to act on"


@pytest.mark.parametrize("q", QUESTIONS, ids=ids(QUESTIONS))
def test_the_orchestrator_is_always_involved(q):
    """It is the user boundary; nothing reaches a user without it."""
    assert "orchestrator" in q["expected_agents"], q["id"]


@pytest.mark.parametrize("q", QUESTIONS, ids=ids(QUESTIONS))
def test_a_specialist_is_never_expected_without_the_orchestrator_first(q):
    """The expected path must be a real A2A path, not a wish."""
    if "mcp-agent" in q["expected_agents"] and q["expected_route"] == "data_request":
        # The MCP agent is reached either by the orchestrator (execute/choices)
        # or by the domain expert (catalogue/assess). Both start at the
        # orchestrator, which the previous test already pins.
        assert q["expected_agents"][0] == "orchestrator"


def test_small_talk_never_expects_a_specialist():
    """A greeting entering the expensive path is a cost bug, not a style one."""
    for q in QUESTIONS:
        if q["category"] == "small_talk":
            assert q["expected_agents"] == ["orchestrator"], q["id"]
            assert q["expected_route"] == "direct"


def test_unsupported_questions_promise_no_number():
    for q in QUESTIONS:
        if q["supported"] == "NO":
            a = q["assertions"]
            assert a.get("no_fabricated_number") or a.get("declines_calculation"), (
                f"{q['id']} is unsupported but asserts nothing about not inventing "
                "an answer, which is the only thing that matters for these")


def test_known_defects_name_the_questions_they_break():
    for defect in CATALOG["known_defects"]:
        assert defect["affects"], f"{defect['id']} affects nothing?"
        for qid in defect["affects"]:
            assert qid in ids(QUESTIONS), f"{defect['id']} names unknown {qid}"


# --- level 2: do the catalog's facts still match the stores? ----------------


@pytest.fixture(scope="module")
def db():
    try:
        from treasury_db.db import connect
        with connect() as conn:
            conn.cursor().execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL unavailable: {type(exc).__name__}: {exc}")
    return connect


def test_data_facts_still_match_the_database(db):
    """The anti-fabrication test.

    Every number the catalog quotes about the data is recounted here from the
    database itself. If someone reloads Treasury data and the coverage moves,
    this fails and the catalog gets corrected — rather than continuing to
    describe a database that no longer exists.
    """
    from treasury_db.db import fetch_all, fetch_one

    with db() as conn:
        datasets = [r["data_key"] for r in
                    fetch_all(conn, "SELECT data_key FROM treasury.dataset ORDER BY 1")]
        assert datasets == FACTS["datasets"]

        counts = fetch_one(conn, """
            SELECT (SELECT count(*) FROM treasury.observation) obs,
                   (SELECT count(*) FROM treasury.series) series,
                   (SELECT min(observation_date) FROM treasury.observation) lo,
                   (SELECT max(observation_date) FROM treasury.observation) hi""")
        assert counts["obs"] == FACTS["observation_rows"]
        assert counts["series"] == FACTS["series_count"]
        assert str(counts["lo"]) == FACTS["earliest_observation"]
        assert str(counts["hi"]) == FACTS["latest_observation"]

        for kind, key in (("nominal", "nominal_range"), ("real", "real_range")):
            r = fetch_one(conn, """
                SELECT min(o.observation_date) lo, max(o.observation_date) hi
                FROM treasury.observation o JOIN treasury.series s USING (series_id)
                WHERE s.rate_kind = %s""", (kind,))
            assert [str(r["lo"]), str(r["hi"])] == FACTS[key], kind


def test_the_series_the_catalog_calls_known_are_known(db):
    from treasury_db.db import fetch_all

    with db() as conn:
        real = {r["series_code"] for r in
                fetch_all(conn, "SELECT series_code FROM treasury.series")}
    for code in FACTS["known_series"]:
        assert code in real, f"catalog claims {code} exists; the database disagrees"
    for code in FACTS["unknown_series"]:
        assert code not in real, f"catalog uses {code} as an unknown series, but it exists"


def test_the_demo_book_is_what_the_catalog_says(db):
    from treasury_db.db import fetch_all, fetch_one

    with db() as conn:
        book = fetch_one(conn, "SELECT portfolio_id, data_classification FROM demo.portfolio")
        assert book["portfolio_id"] == FACTS["portfolio_id"]
        assert book["data_classification"] == "SYNTHETIC_DEMO"

        n = fetch_one(conn, "SELECT count(*) n FROM demo.position")["n"]
        assert n == FACTS["portfolio_positions"]

        scenarios = [r["scenario_id"] for r in
                     fetch_all(conn, "SELECT scenario_id FROM demo.scenario ORDER BY 1")]
        assert scenarios == FACTS["scenario_ids"]


def test_the_unknown_portfolio_really_is_unknown(db):
    from treasury_db.db import fetch_all

    with db() as conn:
        real = {r["portfolio_id"] for r in
                fetch_all(conn, "SELECT portfolio_id FROM demo.portfolio")}
    assert FACTS["unknown_portfolio"] not in real


# --- Qdrant -----------------------------------------------------------------


@pytest.fixture(scope="module")
def qdrant():
    try:
        from treasury_db.db import load_dotenv
        load_dotenv()
        from qdrant_client import QdrantClient
        client = QdrantClient(url=os.environ.get("QDRANT_URL") or "http://localhost:6333")
        client.get_collections()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Qdrant unavailable: {type(exc).__name__}: {exc}")
    return client


def test_qdrant_holds_what_the_catalog_says(qdrant):
    names = [c.name for c in qdrant.get_collections().collections]
    assert FACTS["qdrant_collection"] in names

    info = qdrant.get_collection(FACTS["qdrant_collection"])
    assert info.points_count == FACTS["qdrant_points"]

    points, _ = qdrant.scroll(FACTS["qdrant_collection"], limit=500,
                              with_payload=True, with_vectors=False)
    domains = sorted({p.payload["domain"] for p in points})
    documents = sorted({f"{p.payload['domain']}/{p.payload['source']}" for p in points})
    assert domains == FACTS["qdrant_domains"]
    assert documents == FACTS["qdrant_documents"]


def test_every_knowledge_question_cites_a_document_that_exists(qdrant):
    """A question promising a citation the corpus cannot supply is a false promise."""
    points, _ = qdrant.scroll(FACTS["qdrant_collection"], limit=500,
                              with_payload=True, with_vectors=False)
    real = {f"{p.payload['domain']}/{p.payload['source']}" for p in points}
    for q in QUESTIONS:
        for doc in q.get("knowledge_documents", []):
            assert doc in real, f"{q['id']} names knowledge document {doc}, which is absent"


# --- level 3: is every named capability actually reachable? -----------------


@pytest.fixture(scope="module")
def provider():
    os.environ.setdefault("DATA_BACKEND", "mcp")
    try:
        from treasury_db.db import load_dotenv
        load_dotenv()
        from backend.providers.mcp import McpDataProvider
        return McpDataProvider()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"MCP stack unavailable: {type(exc).__name__}: {exc}")


@pytest.fixture(scope="module")
def agent(provider):
    from agents.mcp_agent import McpAgent
    return McpAgent(provider)


def test_the_mcp_servers_expose_the_tools_the_catalog_relies_on(provider):
    live = set(provider.tool_names())
    for expected in ("get_curve", "get_rate_history", "search_series", "list_series",
                     "list_portfolios", "list_scenarios", "get_curve_history_matrix",
                     "compute_dv01_tool", "compute_historical_risk_tool",
                     "run_stress_tool", "price_portfolio_tool"):
        assert expected in live, f"{expected} is gone from the MCP surface"


def test_the_dispatchable_calculations_are_exactly_what_the_catalog_records(agent):
    """The catalog's `dispatchable_calculations` is a claim; here is the check."""
    from backend.workflows.risk_workflows import RiskWorkflows

    workflows = RiskWorkflows(agent.data)
    advertised = [t.name for t in agent.catalogue().tools]
    dispatchable = sorted(n for n in advertised if callable(getattr(workflows, n, None)))
    assert dispatchable == sorted(FACTS["dispatchable_calculations"])


def test_every_executable_capability_can_actually_be_dispatched(agent):
    """DEF-001, fixed and now enforced: the catalogue may not lie.

    A capability the expert is allowed to schedule must resolve in the execution
    layer. Discovering otherwise at the last step — as `get_curve_slope` used to,
    returning `no workflow named 'get_curve_slope'` — makes the domain expert
    reason against a capability that does not exist.
    """
    from backend.workflows.risk_workflows import RiskWorkflows

    workflows = RiskWorkflows(agent.data)
    catalogue = agent.catalogue()
    undispatchable = [name for name in catalogue.executable_tools
                      if not callable(getattr(workflows, name, None))]
    assert not undispatchable, (
        f"advertised as executable but not dispatchable: {undispatchable}")
    assert sorted(catalogue.executable_tools) == sorted(
        FACTS["dispatchable_calculations"])


def test_informational_capabilities_are_marked_as_such(agent):
    """The other half of the fix: retrieval helpers say they are not schedulable."""
    catalogue = agent.catalogue()
    informational = sorted(t.name for t in catalogue.tools if not t.executable)
    assert informational == sorted(FACTS["informational_tools"])
    assert "get_curve_slope" in informational


def test_the_expert_cannot_schedule_an_informational_capability(agent):
    """Naming one is dropped at the planning boundary, not discovered at execution."""
    from agents.domain_expert_agent import DomainExpertAgent

    built = DomainExpertAgent(knowledge=None)._build(
        {"task_understood": "2s10s slope", "answerable": True,
         "fields": ["rate_percent"], "field_notes": [], "rows": 1,
         "row_quote": None, "row_reason": "", "tenors": ["y2", "y10"],
         "calculation": "get_curve_slope", "curve_family": "nominal"},
        [], agent.catalogue(), None, [])
    assert built.calculation is None
    # And it is dropped as a *category error*, not as a refusal: the rows the
    # capability describes are still returned, so the task stays answerable.
    assert built.answerable is True
    assert any("get_curve_slope" in w and "returned anyway" in w
               for w in built.warnings), built.warnings


def test_the_agents_tenor_vocabulary_matches_the_database(agent, db):
    from treasury_db.db import fetch_all

    catalogue = agent.catalogue()
    assert sorted(catalogue.tenors) == sorted(FACTS["agent_tenors"]), catalogue.tenors
    assert FACTS["unknown_tenor"] not in catalogue.tenors

    with db() as conn:
        real_tenor_years = {float(r["tenor_years"]) for r in fetch_all(conn, """
            SELECT tenor_years FROM treasury.series
            WHERE data_key = 'daily_treasury_real_yield_curve'""")}
    assert real_tenor_years == {5.0, 7.0, 10.0, 20.0, 30.0}


# --- level 4: data boundaries -----------------------------------------------


def test_a_named_historical_period_is_served_or_refused_never_substituted(agent):
    """DEF-002, fixed and now enforced.

    A question about 2008 used to be answered with the most recent window, and
    the substitution was silent. It must now either serve 2008 or say plainly it
    cannot — never quietly serve something else under the same label.
    """
    from agents.contracts import Requirement, TemporalScope

    result = agent._execute(Requirement(
        task="2008 history", answerable=True, rows=250, tenors=["y10"],
        fields=["observation_date", "rate_percent", "quote_basis"],
        temporal=TemporalScope(start_date="2008-01-01", end_date="2008-12-31")))
    rows = result["table"].get("rows") or []
    assert rows, "2008 is inside coverage; it should have been served"
    dates = [str(r[0]) for r in rows]
    assert all(d.startswith("2008") for d in dates), dates[:5]


def test_a_period_outside_coverage_is_refused_rather_than_shifted(agent):
    from agents.contracts import Requirement, TemporalScope

    result = agent._execute(Requirement(
        task="1985", answerable=True, rows=10, tenors=["y10"],
        fields=["observation_date", "rate_percent", "quote_basis"],
        temporal=TemporalScope(start_date="1985-01-01", end_date="1985-12-31")))
    assert result["table"].get("out_of_range") is True
    assert result["rows_delivered"] == 0


def test_a_single_named_day_is_served_as_that_day(agent):
    from agents.contracts import Requirement, TemporalScope

    result = agent._execute(Requirement(
        task="one day", answerable=True, rows=1, tenors=["y10"],
        fields=["tenor", "rate_percent", "quote_basis"],
        temporal=TemporalScope(as_of_date="2020-03-17")))
    assert str(result["table"]["provenance"]["curve_date"]) == "2020-03-17"


def test_history_really_is_capped_where_the_catalog_says(agent):
    """Q-HIST-003 claims ~251 rows and an honest shortfall note. Verify both."""
    from agents.contracts import Requirement

    result = agent._execute(Requirement(
        task="long history", answerable=True, rows=5000, tenors=["y10"],
        fields=["observation_date", "rate_percent", "quote_basis"]))
    delivered = result["table"]["row_count"]
    assert delivered <= FACTS["agent_history_row_cap"]
    assert any("Reported, not padded" in n for n in result["notes"]), result["notes"]


def test_an_unknown_tenor_yields_nothing_rather_than_something(agent):
    from agents.contracts import Requirement

    result = agent._execute(Requirement(
        task="15 year", answerable=True, rows=10, tenors=[FACTS["unknown_tenor"]],
        fields=["observation_date", "rate_percent", "quote_basis"]))
    # An unknown tenor falls back to the agent's defaults rather than inventing a
    # 15-year series; what must never happen is a column named y15 with numbers.
    assert FACTS["unknown_tenor"] not in result["table"]["columns"]


def test_the_real_curve_carries_its_own_label(agent):
    from agents.contracts import Requirement

    result = agent._execute(Requirement(
        task="real curve", answerable=True, rows=1, tenors=["y10"],
        fields=["observation_date", "rate_percent", "quote_basis"],
        curve_family="real"))
    assert result["table"]["provenance"]["rate_kind"] == "real"
    assert "Real" in result["table"]["title"]


# --- level 5: grounding against the engine ----------------------------------


@pytest.mark.parametrize("q", [q for q in QUESTIONS if q.get("ground_truth")],
                         ids=[q["id"] for q in QUESTIONS if q.get("ground_truth")])
def test_the_catalog_ground_truth_is_reproducible(agent, q):
    """Deterministic ground truth, computed twice.

    The point is not that a number is *correct* — that is the risk engine's
    business and `verify_mcp.py` checks it. The point is that the value the
    catalog will compare an answer against is stable and reachable, so a
    grounding assertion in the end-to-end suite means something.
    """
    from backend.workflows.risk_workflows import RiskWorkflows

    truth = q["ground_truth"]
    workflows = RiskWorkflows(agent.data)
    method = getattr(workflows, truth["workflow"])
    kwargs = {"portfolio_id": FACTS["portfolio_id"], **(truth.get("params") or {})}

    first = method(**kwargs)
    assert truth["field"] in first, f"{truth['field']} absent from {truth['workflow']}"
    value = first[truth["field"]]
    assert isinstance(value, (int, float)) and value == value  # not NaN

    second = method(**kwargs)
    assert second[truth["field"]] == pytest.approx(value, rel=truth["tolerance"]), (
        "the ground truth is not reproducible, so nothing can be compared to it")


def test_stated_risk_parameters_reach_the_engine(agent):
    """Q-RISK-002 asserts a 10-day horizon. Prove the engine honours it."""
    from backend.workflows.risk_workflows import RiskWorkflows

    workflows = RiskWorkflows(agent.data)
    out = workflows.compute_var(portfolio_id=FACTS["portfolio_id"],
                                confidence_level=0.99, horizon_days=10,
                                trading_days=250)
    assert out["horizon_days"] == 10
    assert out["confidence_level"] == 0.99
    one_day = workflows.compute_var(portfolio_id=FACTS["portfolio_id"],
                                    confidence_level=0.99, horizon_days=1,
                                    trading_days=250)
    assert out["var"] != one_day["var"], (
        "a 10-day and a 1-day VaR came back identical, so the horizon is ignored")
