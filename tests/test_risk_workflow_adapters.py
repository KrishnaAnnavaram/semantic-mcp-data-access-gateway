"""Static contract and adapter tests for the expanded agent capabilities.

Two layers, deliberately kept apart from the live `/chat` suite:

**Static contract** — the catalogue may not lie. Every executable `ToolSpec`
must resolve to a `RiskWorkflows` method of exactly that name, every method the
catalogue advertises must exist, and every MCP tool the adapters name must be
registered on a server. These are cheap, deterministic, and they catch the
failure mode that is worst to discover late: the domain expert plans a
calculation that only fails at the last step.

**Adapter behaviour** — driven through a recording provider rather than a live
MCP host, so each adapter can be checked for the thing that actually matters:
*which engine tool it called, with which arguments*. No model, no database, no
child processes.

The rule these tests exist to protect is that `RiskWorkflows` is an adapter and
nothing else. It prepares inputs, calls the data server for market data, calls
the risk server for mathematics, and shapes the reply. It does not compute. A
test at the end asserts that structurally, over the module's own syntax tree.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import anyio
import pytest

from agents.mcp_agent import McpAgent
from backend.workflows.risk_workflows import (
    CRISIS_WINDOWS, TEMPLATE_CONTROL_POINTS, RiskWorkflows,
)
from mcp_servers.data.server import server as data_server
from mcp_servers.risk.server import server as risk_server

REPO = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW_SOURCE = REPO / "backend" / "src" / "backend" / "workflows" / "risk_workflows.py"


# --- a provider that records instead of calling ------------------------------


CURVE = {
    "observation_date": "2026-08-11",
    "curve_family": "nominal",
    "envelope": {"dataset_snapshot_id": "treasury-test"},
    "points": [{"tenor_months": m, "rate_percent": r} for m, r in
               ((24.0, 3.9), (60.0, 4.1), (120.0, 4.4), (240.0, 4.9), (360.0, 4.8))],
}

PORTFOLIO = {
    "portfolio": {"portfolio_id": "TREASURY_DEMO_001"},
    "positions": [{
        "instrument": {"instrument_id": "DEMO_NOTE_10Y", "face_value": 1000.0,
                       "coupon_rate_pct": 4.25, "issue_date": "2026-08-15",
                       "maturity_date": "2036-08-15"},
        "face_notional": 8_000_000.0}],
}

#: One canned reply broad enough for every adapter to shape. Real engine
#: results are far larger; these are the keys the adapters actually read.
ENGINE_REPLY = {
    "base_value": 29_500_590.35, "stressed_value": 28_468_881.25,
    "pnl": -1_031_709.10, "pnl_percent": -3.5, "dv01": 20_653.25,
    "var": 165_729.86, "expected_shortfall": 230_150.84,
    "worst_pnl": -279_767.29, "mean_pnl": 60.49, "stdev_pnl": 29_164.66,
    "positions": [{"instrument_id": "DEMO_NOTE_10Y", "pnl": -600_000.0,
                   "dv01": 6_353.79, "dv01_share_percent": 30.0}],
    "instruments": [{"instrument_id": "DEMO_NOTE_10Y", "clean_price_per_100": 96.4,
                     "dirty_price_per_100": 98.5, "accrued_per_100": 2.08,
                     "ytm_percent": 4.705, "current_yield_percent": 4.4,
                     "macaulay_duration_years": 8.03,
                     "modified_duration_years": 7.86,
                     "effective_duration_years": 7.87, "dollar_duration": 1.0,
                     "convexity": 75.24, "effective_convexity": 75.3}],
    "shock": {"shocks_bp_by_tenor_months": {"120.0": 100.0}},
    "top_tenor_contributors": [{"tenor_months": 120.0, "pnl": -600_000.0}],
    "scenarios": [{"rank": 1, "scenario_name": "Parallel +200bp", "pnl": -3.7e6,
                   "pnl_percent": -12.4, "largest_position_contributor": "DEMO_NOTE_10Y",
                   "largest_bucket_contributor": "5-10y"}],
    "worst": [{"rank": 1, "start_date": "2026-02-27", "end_date": "2026-03-13",
               "pnl": -641_414.0, "pnl_percent": -2.17,
               "largest_position_contributor": "DEMO_NOTE_10Y",
               "start_observation_index": 40}],
    "rows": [{"target_loss": 1e6, "solved_shock_bp_at_reference_tenor": 48.6,
              "converged": True, "unreachable_reason": None}],
    "rungs": [{"shock_bp": 100.0, "pnl": -1.9e6, "pnl_percent": -6.8,
               "duration_only_error": -800.0}],
    "dimensions": [{"dimension": "position_dv01", "unit": "USD per bp",
                    "top_share_percent": 30.0, "top_three_share_percent": 75.0,
                    "herfindahl_index": 0.23, "effective_count": 4.25,
                    "entries": []}],
    "evaluations": [{"metric": "dv01", "status": "AMBER"}],
    "curvature": {"bucket_capital": 0.0, "interpretation": "positively convex"},
    "reproducibility": {"run_fingerprint": "abc123"},
    "historical_start": "2022-01-03", "historical_end": "2022-10-24",
    "crisis_name": "2022 rapid Fed tightening", "crisis_id": "2022_FED_TIGHTENING",
    "observed_shocks_bp_by_tenor_months": {"120.0": 150.0},
    "solved_shock_bp_at_reference_tenor": 100.31, "solved_multiplier": 100.31,
    "resulting_pnl": -2e6, "converged": True, "iterations": 7,
    "exceptions": 4, "exception_rate": 0.016, "expected_exceptions": 2.5,
    "pnl_kind": "MODEL_REVALUATION", "observations": 40,
    "exception_rule": "strict exceedance", "basel_traffic_light": None,
    "kupiec_result": {"p_value": 0.38}, "independence_result": {"p_value": 0.04},
    "measures": [{"measure": "dv01", "portfolio_a": 20_653.25,
                  "portfolio_b": 18_058.56, "difference": -2_594.69}],
    "total_capital": 2_284_957.82, "delta_capital": 2_284_957.82,
    "methods": [{"method": "historical_simulation", "var": 165_729.86}],
    "per_tenor": [{"tenor_months": 120.0, "stdev_bp": 4.2}],
    "change_count": 249, "horizon_days": 1, "confidence_level": 0.99,
    "total_pnl": -395_671.05, "carry": 937_420.88, "roll_down": 482_288.97,
    "rate_move": -1_815_380.90, "residual": 0.0, "rate_unexplained": 1_090.76,
    "portfolio_measure": 165_729.86, "scenario_count": 249,
    "total_carry_and_roll": 1_419_709.85, "horizon_date": "2027-08-15",
    # Keys the pre-existing workflows read directly rather than via .get().
    "worst_loss": 279_767.29, "scenarios_used": 249,
    "model": {"historical_risk_version": "absolute_par_shock_full_revaluation_v1",
              "quantile_method": "nearest_rank_v1"},
    # Limit-breach shape.
    "limit_amount": 2_000_000.0, "amber_amount": 1_600_000.0,
    "breach_shock_bp": 100.31, "amber_shock_bp": 79.20,
    "breach_reason": None, "amber_reason": None,
    # Threshold and comparison shapes.
    "shape_name": "Parallel shift", "spread_var": 20_544.0,
    "widest_method": "parametric_delta_normal",
    "narrowest_method": "historical_simulation",
}


class RecordingProvider:
    """Answers like the MCP host, and remembers exactly what it was asked."""

    def __init__(self, overrides: dict | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.overrides = overrides or {}

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        self.calls.append((name, arguments or {}))
        if name in self.overrides:
            return self.overrides[name]
        if name == "get_curve":
            return dict(CURVE)
        if name == "get_portfolio":
            return dict(PORTFOLIO)
        if name == "list_portfolios":
            return {"portfolios": [{"portfolio_id": "TREASURY_DEMO_001"},
                                   {"portfolio_id": "TREASURY_DEMO_002"}]}
        if name == "list_scenarios":
            return {"scenarios": [{"scenario_id": "REPLAY_1994"}]}
        return dict(ENGINE_REPLY)

    def call_tool_with_meta(self, name: str, arguments: dict | None = None):
        self.calls.append((name, arguments or {}))
        summary = {"as_of_date": "2026-08-11", "trading_days_returned": 250}
        meta = {"market-risk-data/curve_history_matrix": {
            "tenors_months": ["24", "60", "120", "240", "360"],
            "rates_percent": [["4.0"] * 5 for _ in range(250)],
            "dates": [f"2026-01-{1 + i % 28:02d}" for i in range(250)]}}
        return summary, meta

    def tool_names(self) -> list[str]:
        return []

    def named(self) -> list[str]:
        return [name for name, _ in self.calls]

    def args_for(self, name: str) -> dict:
        for called, arguments in self.calls:
            if called == name:
                return arguments
        raise AssertionError(f"{name} was never called; called {self.named()}")


@pytest.fixture
def provider():
    return RecordingProvider()


@pytest.fixture
def workflows(provider):
    return RiskWorkflows(provider)


# --- layer 1: the static contract --------------------------------------------


def registered_tools() -> set[str]:
    return ({t.name for t in anyio.run(risk_server.list_tools)}
            | {t.name for t in anyio.run(data_server.list_tools)})


def catalogue():
    """The agent catalogue, built against a provider that can calculate."""
    return McpAgent(RecordingProvider()).catalogue()


def test_every_executable_toolspec_resolves_to_a_workflow_method():
    """No advertisement without an executor. The DEF-001 invariant, widened."""
    undispatchable = [name for name in catalogue().executable_tools
                      if not callable(getattr(RiskWorkflows, name, None))]
    assert not undispatchable, (
        f"advertised as executable but not dispatchable: {undispatchable}")


def test_every_advertised_capability_name_is_unique():
    names = [t.name for t in catalogue().tools]
    duplicates = {n for n in names if names.count(n) > 1}
    assert not duplicates, f"duplicate capability names: {sorted(duplicates)}"


def test_informational_capabilities_are_not_workflow_methods():
    """A retrieval helper must not accidentally become schedulable."""
    for name in catalogue().retrieval_tools:
        assert not callable(getattr(RiskWorkflows, name, None)), (
            f"{name} is advertised as informational but is dispatchable")


def test_every_mcp_tool_the_adapters_name_is_registered():
    """An executor may not call a tool that does not exist."""
    tree = ast.parse(WORKFLOW_SOURCE.read_text(encoding="utf-8"))
    named: set[str] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"call_tool", "call_tool_with_meta"}
                and node.args and isinstance(node.args[0], ast.Constant)):
            named.add(node.args[0].value)
        # The dispatching form: `tool, payload, label = ("run_x_tool", ...)`
        if isinstance(node, ast.Tuple):
            for element in node.elts:
                if (isinstance(element, ast.Constant)
                        and isinstance(element.value, str)
                        and element.value.endswith("_tool")):
                    named.add(element.value)
    assert named, "no MCP tool names were found; the scan needs updating"
    unknown = sorted(named - registered_tools())
    assert not unknown, f"adapters call unregistered MCP tools: {unknown}"


def test_the_original_four_capabilities_survive_unchanged():
    """Backward compatibility, asserted rather than assumed."""
    executable = set(catalogue().executable_tools)
    assert {"price_portfolio", "compute_dv01", "compute_var",
            "run_stress"} <= executable


def test_every_executable_capability_describes_when_not_to_use_it():
    """With thirty neighbours, the discriminating clause is the whole value."""
    for spec in catalogue().tools:
        if not spec.executable:
            continue
        assert "USE WHEN" in spec.description, spec.name
        assert "NOT WHEN" in spec.description, spec.name
        assert "ASKS LIKE" in spec.description, spec.name
        assert len(spec.description) >= 200, (
            f"{spec.name} is described in {len(spec.description)} characters")


def test_mirrored_engine_constants_still_match_the_engine():
    """The adapter mirrors template control points and crisis dates.

    Mirroring is a real risk: two copies of a definition drift. These assert the
    copies against the engine's own, so a change to either side fails here
    rather than producing a scenario that quietly means something else.
    """
    from mcp_servers.risk.historical_stress import CRISIS_BY_ID
    from mcp_servers.risk.stress_scenarios import TEMPLATES

    for name, points in TEMPLATE_CONTROL_POINTS.items():
        _, engine_points = TEMPLATES[name]
        mirrored = {months / 12.0: multiple for months, multiple in points.items()}
        assert mirrored == engine_points, f"{name} control points have drifted"

    for crisis_id, (start, end) in CRISIS_WINDOWS.items():
        crisis = CRISIS_BY_ID[crisis_id]
        assert crisis.start_date.isoformat() == start, crisis_id
        assert crisis.end_date.isoformat() == end, crisis_id


# --- layer 2: adapter behaviour ----------------------------------------------


def test_bond_analytics_calls_the_engine_and_shapes_the_reply(workflows, provider):
    out = workflows.compute_bond_analytics("TREASURY_DEMO_001")
    assert provider.named() == ["get_portfolio", "get_curve",
                                "compute_bond_analytics_tool"]
    row = out["instruments"][0]
    assert {"clean_price_per_100", "ytm_percent", "modified_duration_years",
            "convexity", "effective_convexity"} <= set(row)


def test_curve_analytics_needs_no_portfolio(workflows, provider):
    out = workflows.compute_curve_analytics()
    assert provider.named() == ["get_curve", "compute_curve_analytics_tool"]
    assert "spreads" in out and "inversion" in out


@pytest.mark.parametrize("scenario,expected_tool", [
    ("parallel", "run_rate_stress_tool"),
    ("bear_steepener", "run_rate_stress_tool"),
    ("bull_flattener", "run_rate_stress_tool"),
    ("twist", "run_curve_twist_stress_tool"),
    ("belly_selloff", "run_curve_curvature_stress_tool"),
    ("wings_selloff", "run_curve_curvature_stress_tool"),
])
def test_rate_stress_dispatches_to_the_right_engine_tool(
    workflows, provider, scenario, expected_tool,
):
    """One capability, three engine tools. The dispatch is the adapter's job."""
    workflows.run_rate_stress("TREASURY_DEMO_001", scenario=scenario)
    assert expected_tool in provider.named(), provider.named()


def test_an_unknown_rate_scenario_is_refused_with_the_valid_ones(workflows):
    out = workflows.run_rate_stress("TREASURY_DEMO_001", scenario="melt_up")
    assert "error" in out
    assert "bear_steepener" in out["available"]


def test_a_parallel_shock_passes_the_users_basis_points_through(workflows, provider):
    workflows.run_rate_stress("TREASURY_DEMO_001", scenario="parallel",
                              shock_bp=250.0)
    assert provider.args_for("run_rate_stress_tool")["parallel_shock_bp"] == 250.0


def test_parallel_down_inverts_a_positive_magnitude(workflows, provider):
    workflows.run_rate_stress("TREASURY_DEMO_001", scenario="parallel_down",
                              shock_bp=100.0)
    assert provider.args_for("run_rate_stress_tool")["parallel_shock_bp"] == -100.0


def test_key_rate_stress_shocks_exactly_the_named_node(workflows, provider):
    workflows.run_key_rate_stress("TREASURY_DEMO_001", tenor_months=360.0,
                                  shock_bp=-75.0)
    args = provider.args_for("run_key_rate_stress_tool")
    assert args["key_tenors_months"] == [360.0]
    assert args["shock_bp"] == -75.0


def test_a_named_crisis_resolves_to_its_documented_dates(workflows, provider):
    workflows.run_historical_stress("TREASURY_DEMO_001",
                                    crisis_id="2022_FED_TIGHTENING")
    fetched = [args.get("observation_date") for name, args in provider.calls
               if name == "get_curve" and args.get("observation_date")]
    assert fetched == ["2022-01-03", "2022-10-24"]
    assert "run_historical_crisis_stress_tool" in provider.named()


def test_explicit_dates_take_the_plain_replay_path(workflows, provider):
    workflows.run_historical_stress("TREASURY_DEMO_001",
                                    start_date="2020-02-19", end_date="2020-03-09")
    assert "run_historical_stress_tool" in provider.named()
    assert "run_historical_crisis_stress_tool" not in provider.named()


def test_a_replay_with_neither_a_crisis_nor_dates_is_refused(workflows):
    out = workflows.run_historical_stress("TREASURY_DEMO_001")
    assert "error" in out
    assert "2020_COVID_SHOCK" in out["available_crises"]


def test_an_unknown_crisis_lists_the_available_windows(workflows):
    out = workflows.run_historical_stress("TREASURY_DEMO_001", crisis_id="1987_CRASH")
    assert "error" in out and "available" in out


def test_reverse_stress_passes_the_target_loss_through(workflows, provider):
    workflows.run_reverse_stress("TREASURY_DEMO_001", target_loss=2_500_000.0)
    args = provider.args_for("run_reverse_stress_tool")
    assert args["target_loss"] == 2_500_000.0
    assert args["shape"] == "PARALLEL"


def test_reverse_stress_maps_a_named_scenario_to_an_engine_shape(workflows, provider):
    workflows.run_reverse_stress("TREASURY_DEMO_001", target_loss=1e6,
                                 scenario="bear_steepener")
    assert provider.args_for("run_reverse_stress_tool")["shape"] == "BEAR_STEEPENER"


def test_monte_carlo_passes_seed_and_scenario_count(workflows, provider):
    workflows.compute_monte_carlo_risk("TREASURY_DEMO_001", scenario_count=12_000,
                                       random_seed=7, confidence_level=0.975)
    args = provider.args_for("compute_monte_carlo_risk_tool")
    assert args["scenario_count"] == 12_000
    assert args["random_seed"] == 7
    assert args["confidence_level"] == 0.975


def test_parametric_risk_passes_confidence_and_horizon(workflows, provider):
    workflows.compute_parametric_risk("TREASURY_DEMO_001", confidence_level=0.95,
                                      horizon_days=10)
    args = provider.args_for("compute_parametric_risk_tool")
    assert args["confidence_level"] == 0.95
    assert args["horizon_days"] == 10


def test_risk_contributions_passes_the_measure(workflows, provider):
    workflows.compute_risk_contributions("TREASURY_DEMO_001", risk_measure="es")
    assert provider.args_for("compute_risk_contributions_tool")["risk_measure"] == "es"


def test_worst_historical_caps_top_n_at_the_engine_limit(workflows, provider):
    workflows.find_worst_historical_stresses("TREASURY_DEMO_001", top_n=500)
    assert provider.args_for("find_worst_historical_stresses_tool")["top_n"] == 100


def test_backtesting_restores_chronological_order_before_testing(provider):
    """Ranked losses would make the independence test read as total clustering.

    The engine returns worst-first. Feeding that straight into a coverage test
    puts every exception at the front of the series, and Christoffersen would
    report catastrophic clustering that is an artefact of the sort order.
    """
    ranked = {**ENGINE_REPLY, "worst": [
        {"rank": 1, "pnl": -900.0, "start_observation_index": 90,
         "start_date": "2026-04-01"},
        {"rank": 2, "pnl": -800.0, "start_observation_index": 10,
         "start_date": "2026-01-11"},
        {"rank": 3, "pnl": -700.0, "start_observation_index": 50,
         "start_date": "2026-02-20"},
    ] + [{"rank": i, "pnl": 100.0, "start_observation_index": 100 + i,
          "start_date": f"2026-05-{1 + i % 28:02d}"} for i in range(4, 40)]}
    recorder = RecordingProvider(
        overrides={"find_worst_historical_stresses_tool": ranked})
    RiskWorkflows(recorder).backtest_var("TREASURY_DEMO_001")
    submitted = recorder.args_for("backtest_var_tool")["realised_pnl"]
    assert submitted[:3] == [-800.0, -700.0, -900.0], (
        "the P&L series must be in observation order, not loss order")


def test_backtesting_labels_the_pnl_kind_it_actually_used(workflows, provider):
    series = {**ENGINE_REPLY, "worst": [
        {"rank": i, "pnl": -100.0 * i, "start_observation_index": i,
         "start_date": f"2026-01-{1 + i % 28:02d}"} for i in range(40)]}
    recorder = RecordingProvider(
        overrides={"find_worst_historical_stresses_tool": series})
    RiskWorkflows(recorder).backtest_var("TREASURY_DEMO_001")
    assert recorder.args_for("backtest_var_tool")["pnl_kind"] == "MODEL_REVALUATION"


def test_risk_limits_refuse_to_invent_a_policy(workflows, provider):
    out = workflows.evaluate_risk_limits("TREASURY_DEMO_001")
    assert "error" in out
    assert set(out["needs"]) == {"dv01_limit", "var_limit", "stress_loss_limit"}
    assert "evaluate_risk_limits_tool" not in provider.named()


def test_risk_limits_measure_only_what_a_limit_was_supplied_for(workflows, provider):
    workflows.evaluate_risk_limits("TREASURY_DEMO_001", dv01_limit=25_000.0)
    assert "compute_dv01_tool" in provider.named()
    assert "compute_historical_risk_tool" not in provider.named()
    limits = provider.args_for("evaluate_risk_limits_tool")["limits"]
    assert [row["metric"] for row in limits] == ["dv01"]
    assert limits[0]["limit_amount"] == 25_000.0


def test_a_hypothetical_trade_uses_a_published_node_rate_as_its_coupon(
    workflows, provider,
):
    workflows.analyze_hypothetical_trade("TREASURY_DEMO_001", tenor_months=120.0,
                                         notional=10_000_000.0)
    args = provider.args_for("analyze_hypothetical_trade_tool")
    position = args["hypothetical_positions"]["positions"][0]
    assert position["instrument"]["coupon_rate_pct"] == 4.4      # the 10y node
    assert position["face_notional"] == 10_000_000.0


def test_a_hypothetical_trade_at_a_non_node_tenor_is_refused(workflows):
    out = workflows.analyze_hypothetical_trade("TREASURY_DEMO_001",
                                               tenor_months=150.0,
                                               notional=1_000_000.0)
    assert "error" in out
    assert 120.0 in out["available_tenor_months"]


def test_portfolio_comparison_picks_a_real_second_book(workflows, provider):
    workflows.compare_portfolio_risk("TREASURY_DEMO_001")
    args = provider.args_for("compare_portfolio_risk_tool")
    assert args["label_b"] == "TREASURY_DEMO_002"


def test_history_travels_through_meta_not_through_arguments(workflows, provider):
    """1,250 yields must not enter model context, then or now."""
    workflows.compute_parametric_risk("TREASURY_DEMO_001")
    assert "get_curve_history_matrix" in provider.named()
    history = provider.args_for("compute_parametric_risk_tool")["history"]
    assert len(history["rates_percent"]) == 250


@pytest.mark.parametrize("method,tool,extra", [
    ("compute_bond_analytics", "compute_bond_analytics_tool", {}),
    ("compute_carry_roll", "compute_carry_roll_tool", {}),
    ("compute_rate_sensitivities", "compute_rate_sensitivities_tool", {}),
    ("compute_concentration", "compute_concentration_tool", {}),
    ("run_shock_ladder", "run_shock_ladder_tool", {}),
    ("run_stress_matrix", "run_stress_matrix_tool", {}),
    ("compute_stress_thresholds", "compute_stress_thresholds_tool", {}),
    ("find_limit_breach_stress", "find_limit_breach_stress_tool",
     {"limit_amount": 2_000_000.0}),
    ("compare_risk_methods", "compare_risk_methods_tool", {}),
    ("compute_frtb_girr", "compute_frtb_girr_tool", {}),
    ("compute_pnl_attribution", "compute_pnl_attribution_tool", {}),
])
def test_each_adapter_calls_exactly_its_own_engine_tool(provider, method, tool,
                                                        extra):
    getattr(RiskWorkflows(provider), method)("TREASURY_DEMO_001", **extra)
    assert tool in provider.named(), f"{method} did not call {tool}"


# --- a required input is asked for, never assumed ----------------------------


REQUIRED_INPUTS = [
    ("run_rate_stress", {}, "scenario"),
    ("run_key_rate_stress", {}, "tenor_months"),
    ("run_key_rate_stress", {"tenor_months": 120.0}, "shock_bp"),
    ("compute_stress_contributions", {}, "scenario"),
    ("run_reverse_stress", {}, "target_loss"),
    ("find_limit_breach_stress", {}, "limit_amount"),
    ("analyze_hypothetical_trade", {}, "tenor_months"),
    ("analyze_hypothetical_trade", {"tenor_months": 120.0}, "notional"),
    ("evaluate_risk_limits", {}, "dv01_limit"),
]


@pytest.mark.parametrize("method,supplied,missing", REQUIRED_INPUTS,
                         ids=[f"{m}-{k}" for m, _, k in REQUIRED_INPUTS])
def test_a_missing_required_input_is_asked_for_not_assumed(provider, method,
                                                           supplied, missing):
    """The judge finding, guarded so it cannot come back.

    A capability whose ToolSpec says NEEDS x must not quietly supply x. Reverse
    stress defaulting the target loss to a million answers a different question
    with the same confidence as a right answer; the limit-breach capability
    defaulting the limit invents desk policy in a system whose stated rule is
    that it holds none.

    The correct behaviour is a structured `needs` block that the orchestrator
    turns into one question - the existing clarification path, not a new one.
    """
    out = getattr(RiskWorkflows(provider), method)("TREASURY_DEMO_001", **supplied)
    assert "needs" in out, (
        f"{method} ran without {missing} instead of asking for it")
    assert missing in out["needs"], out["needs"]
    assert out["detail"], "a request for input must say why it is needed"
    assert not provider.named() or not any(
        n.endswith("_tool") for n in provider.named()), (
        f"{method} called the engine before it had {missing}")


def test_no_declared_required_input_carries_a_silent_default():
    """Read the ToolSpec's own NEEDS clause and check the signature against it."""
    import re

    catalogue_tools = catalogue().tools
    offenders = []
    for spec in catalogue_tools:
        if not spec.executable:
            continue
        match = re.search(r"NEEDS ([^.]*)\.", spec.description)
        if not match:
            continue
        declared = match.group(1)
        method = getattr(RiskWorkflows, spec.name, None)
        if method is None:
            continue
        for name, parameter in inspect.signature(method).parameters.items():
            if name in {"self", "portfolio_id"}:
                continue
            if (name in declared
                    and parameter.default is not inspect.Parameter.empty
                    and parameter.default is not None):
                offenders.append(f"{spec.name}.{name}={parameter.default!r}")
    assert not offenders, (
        "these capabilities declare an input as required and then supply it "
        f"themselves: {offenders}")


def test_an_engine_error_is_surfaced_rather_than_swallowed(provider):
    recorder = RecordingProvider(
        overrides={"compute_frtb_girr_tool": {"error": "engine said no"}})
    out = RiskWorkflows(recorder).compute_frtb_girr("TREASURY_DEMO_001")
    assert out["error"] == "compute_frtb_girr failed"
    assert out["detail"] == "engine said no"


def test_the_frtb_adapter_never_calls_the_result_total_capital(workflows):
    out = workflows.compute_frtb_girr("TREASURY_DEMO_001")
    assert "NOT a complete bank-wide" in out["note"]


# --- the quantitative boundary, asserted structurally ------------------------


def test_the_adapter_layer_performs_no_financial_mathematics():
    """`RiskWorkflows` prepares, calls and shapes. It must not calculate.

    Checked against the module's syntax tree rather than by reading it: any
    arithmetic operator inside a workflow method is flagged unless it appears in
    one of the shaping helpers, whose whole job is unit conversion and
    interpolation of a *scenario shape* rather than valuation.

    A financial calculation in this layer would be a second implementation of
    something the engine already owns, and the two would eventually disagree.
    """
    tree = ast.parse(WORKFLOW_SOURCE.read_text(encoding="utf-8"))
    # Methods allowed arithmetic, and why:
    #   _scenario_shocks  - interpolates a shock SHAPE onto curve tenors
    #   _stress_summary   - rounds a shock vector for display
    #   _shock_vector     - rounds for display
    #   evaluate_risk_limits - abs(min(0, pnl)) turns a P&L into a loss amount
    #   backtest_var      - list slicing bounds
    allowed = {
        "_scenario_shocks",   # interpolates a shock SHAPE onto curve tenors
        "_stress_summary",    # rounds a shock vector for display
        "_shock_vector",      # rounds for display
        "evaluate_risk_limits",  # abs(min(0, pnl)) turns a P&L into a loss
        "backtest_var",       # list bounds
        "_add_days", "_add_months",           # calendar arithmetic
        "analyze_hypothetical_trade",         # months -> years in a label
        "run_rate_stress", "run_key_rate_stress",  # months -> years in a label
        # Pre-existing and deliberate: the host differences two published
        # curves into a shock vector so the engine receives an ordinary shock
        # and the data server still performs no arithmetic. Documented in the
        # module docstring; unchanged by this integration.
        "_replay_shocks",
    }
    offenders: list[str] = []
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        if cls.name != "RiskWorkflows":
            continue
        for fn in [n for n in cls.body if isinstance(n, ast.FunctionDef)]:
            if fn.name in allowed:
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.BinOp) and isinstance(
                        node.op, (ast.Mult, ast.Div, ast.Pow, ast.Sub)):
                    offenders.append(f"{fn.name}: {ast.dump(node.op)}")
    assert not offenders, (
        "arithmetic found in the adapter layer, which must not calculate: "
        f"{offenders}")


def test_no_workflow_method_imports_the_risk_engine():
    """The adapter talks to the engine over MCP, never by importing it."""
    tree = ast.parse(WORKFLOW_SOURCE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "mcp_servers" not in imported, (
        "RiskWorkflows must reach the engine through MCP, not by importing it")


def test_every_public_workflow_method_is_either_advertised_or_deliberately_not():
    """The inverse guard: no orphaned adapter nobody can reach.

    A method that is neither advertised nor on the known-internal list is a
    capability that was built and then never connected - the exact gap this
    whole integration exists to close.
    """
    internal = {"list_portfolios", "get_portfolio", "list_scenarios",
                "explain_number"}
    advertised = set(catalogue().executable_tools)
    public = {name for name, _ in inspect.getmembers(RiskWorkflows,
                                                     inspect.isfunction)
              if not name.startswith("_")}
    orphaned = public - advertised - internal
    assert not orphaned, f"workflow methods nobody can reach: {sorted(orphaned)}"
