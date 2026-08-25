"""Multi-capability workflows, driven through the adapter layer.

A realistic market-risk request is rarely one calculation. "Run a bear steepener
and tell me what drives the loss" is two: the scenario, then its decomposition.
These tests prove the composition works — that the second capability can consume
what the first produced, on the same book and the same curve, and that the two
agree about the number they share.

They run against a recording provider rather than a live model, because what is
being tested is the *composition*, not the planner's ability to notice that two
steps are needed. Whether the planner notices is a routing question and lives in
`tests/use_cases/test_routing_catalog.py`; whether the pieces fit is this file.

The agreement checks are the point. A stress loss reported by `run_rate_stress`
and the same loss decomposed by `compute_stress_contributions` must be the same
number, or one of the two is answering a different question than the user
thinks.
"""

from __future__ import annotations

import pytest

from backend.workflows.risk_workflows import RiskWorkflows

from test_risk_workflow_adapters import ENGINE_REPLY, RecordingProvider

BOOK = "TREASURY_DEMO_001"


@pytest.fixture
def provider():
    return RecordingProvider()


@pytest.fixture
def workflows(provider):
    return RiskWorkflows(provider)


def called(provider) -> list[str]:
    """Only the engine tools, in order, so the shape of a workflow is legible."""
    return [name for name in provider.named() if name.endswith("_tool")]


# --- Case A: stress, then what drove it --------------------------------------


def test_a_stress_and_its_explanation_compose(workflows, provider):
    """'Run a bear steepener and tell me what drives the loss.'"""
    stress = workflows.run_rate_stress(BOOK, scenario="bear_steepener",
                                       severity_bp=100.0)
    drivers = workflows.compute_stress_contributions(BOOK,
                                                     scenario="bear_steepener",
                                                     severity_bp=100.0)
    assert called(provider) == ["run_rate_stress_tool",
                                "compute_stress_contributions_tool"]
    assert stress["pnl"] == drivers["pnl"], (
        "the scenario and its decomposition must report the same loss")
    assert drivers["top_position_contributors"]
    assert "tenor_contributions" in drivers


def test_the_contribution_step_reuses_the_same_scenario_shape(workflows, provider):
    """The decomposition must stress the same curve move, not a similar one."""
    workflows.compute_stress_contributions(BOOK, scenario="bear_steepener",
                                           severity_bp=200.0)
    shocks = provider.args_for(
        "compute_stress_contributions_tool")["shocks_bp_by_tenor_months"]
    # The engine's own BEAR_STEEPENER control points at severity 200.
    assert shocks["24.0"] == pytest.approx(50.0)
    assert shocks["60.0"] == pytest.approx(100.0)
    assert shocks["120.0"] == pytest.approx(200.0)
    assert shocks["360.0"] == pytest.approx(300.0)


# --- Case B: worst historical, then what drove it ----------------------------


def test_worst_historical_then_its_drivers_compose(workflows, provider):
    """'Find my worst historical scenario and explain the loss.'"""
    worst = workflows.find_worst_historical_stresses(BOOK, horizon_days=10, top_n=5)
    assert worst["worst"], "no ranked scenarios came back"
    top = worst["worst"][0]
    assert top["rank"] == 1
    assert top["start_date"] and top["end_date"]

    replay = workflows.run_historical_stress(BOOK, start_date=top["start_date"],
                                             end_date=top["end_date"])
    assert "find_worst_historical_stresses_tool" in called(provider)
    assert "run_historical_stress_tool" in called(provider)
    assert replay["observed_shocks_bp_by_tenor_months"], (
        "the replay must carry the shock it measured")


# --- Case C: VaR, then whether the model has been any good -------------------


def test_var_then_backtest_compose(provider):
    """'Calculate my VaR and tell me whether the model has been performing well.'"""
    series = {**ENGINE_REPLY, "worst": [
        {"rank": i, "pnl": -1000.0 * (i % 7), "start_observation_index": i,
         "start_date": f"2026-0{1 + i % 9}-{1 + i % 28:02d}"} for i in range(40)]}
    recorder = RecordingProvider(
        overrides={"find_worst_historical_stresses_tool": series})
    workflows = RiskWorkflows(recorder)

    var = workflows.compute_var(BOOK, confidence_level=0.99, horizon_days=1)
    backtest = workflows.backtest_var(BOOK, confidence_level=0.99)

    assert var["var"] == backtest["var_forecast_used"], (
        "the backtest must judge the same forecast the user was quoted")
    assert backtest["confidence_level"] == var["confidence_level"]
    assert backtest["pnl_kind"] == "MODEL_REVALUATION"
    assert "model revaluation" in backtest["note"]


def test_the_backtest_is_a_different_engine_tool_from_the_var(provider):
    """Backtesting is not VaR with extra steps; it is a separate calculation."""
    series = {**ENGINE_REPLY, "worst": [
        {"rank": i, "pnl": -100.0, "start_observation_index": i,
         "start_date": "2026-01-05"} for i in range(40)]}
    recorder = RecordingProvider(
        overrides={"find_worst_historical_stresses_tool": series})
    RiskWorkflows(recorder).backtest_var(BOOK)
    tools = [n for n in recorder.named() if n.endswith("_tool")]
    assert "compute_historical_risk_tool" in tools
    assert "backtest_var_tool" in tools
    assert tools.index("compute_historical_risk_tool") < tools.index("backtest_var_tool")


# --- Case D: current risk, then the incremental trade ------------------------


def test_current_risk_then_a_hypothetical_trade_compose(workflows, provider):
    """'Show current risk and what changes if I add $10M 10Y Treasury.'"""
    current = workflows.compute_rate_sensitivities(BOOK)
    trade = workflows.analyze_hypothetical_trade(BOOK, tenor_months=120.0,
                                                 notional=10_000_000.0)
    assert called(provider) == ["compute_rate_sensitivities_tool",
                                "analyze_hypothetical_trade_tool"]
    assert current["dv01"]
    assert trade["hypothetical_trade"]["notional"] == 10_000_000.0
    assert trade["measures"], "the comparison must return paired measures"


def test_the_hypothetical_trade_never_touches_the_stored_book(workflows, provider):
    workflows.analyze_hypothetical_trade(BOOK, tenor_months=120.0,
                                         notional=10_000_000.0)
    args = provider.args_for("analyze_hypothetical_trade_tool")
    assert args["portfolio"]["portfolio_id"] == BOOK
    assert args["hypothetical_positions"]["portfolio_id"].startswith("HYPOTHETICAL")
    # Only read tools were used on the stored side.
    assert {"get_portfolio", "get_curve"} <= set(provider.named())


# --- Case E: the limit question ----------------------------------------------


def test_limit_headroom_then_breach_severity_compose(workflows, provider):
    """'How much can rates rise before I breach my $2M stress limit?'"""
    today = workflows.evaluate_risk_limits(BOOK, stress_loss_limit=2_000_000.0)
    breach = workflows.find_limit_breach_stress(BOOK, limit_amount=2_000_000.0)
    assert "evaluate_risk_limits_tool" in called(provider)
    assert "find_limit_breach_stress_tool" in called(provider)
    assert today["evaluations"], "current utilisation must be reported"
    assert breach["limit_amount"] == 2_000_000.0
    assert provider.args_for(
        "find_limit_breach_stress_tool")["limit_amount"] == 2_000_000.0


# --- Case F: comparing the three risk methods --------------------------------


def test_comparing_risk_methods_is_one_call_not_three(workflows, provider):
    """The engine composes the three internally; the adapter must not re-do it."""
    out = workflows.compare_risk_methods(BOOK)
    engine_calls = called(provider)
    assert engine_calls == ["compare_risk_methods_tool"], engine_calls
    assert out["methods"]


def test_each_named_method_still_reaches_its_own_engine_tool(provider):
    """And asking for one method must not silently run the comparison."""
    workflows = RiskWorkflows(provider)
    workflows.compute_parametric_risk(BOOK)
    workflows.compute_monte_carlo_risk(BOOK)
    tools = set(called(provider))
    assert {"compute_parametric_risk_tool",
            "compute_monte_carlo_risk_tool"} <= tools
    assert "compare_risk_methods_tool" not in tools


# --- shared-input discipline across a composed workflow ----------------------


def test_a_composed_workflow_values_both_steps_on_the_same_curve(workflows, provider):
    """Two capabilities in one turn must not drift onto different curve dates."""
    workflows.compute_rate_sensitivities(BOOK)
    workflows.run_stress_matrix(BOOK)
    dates = {args.get("valuation_date") for name, args in provider.calls
             if name.endswith("_tool") and "valuation_date" in args}
    assert len(dates) == 1, f"steps valued on different dates: {dates}"


def test_history_is_fetched_once_per_capability_not_once_per_tenor(workflows,
                                                                   provider):
    """The bulk matrix is one retrieval; a per-tenor loop would be 5x the work."""
    workflows.compute_parametric_risk(BOOK)
    assert provider.named().count("get_curve_history_matrix") == 1
