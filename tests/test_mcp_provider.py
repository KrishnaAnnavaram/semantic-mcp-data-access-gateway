"""Integration tests for the MCP-backed DataProvider — the agent's road to Postgres.

These need a loaded database and the two MCP servers, so they skip rather than
fail when the stack is not up. The unit-level guarantees (curve maths, quantile
convention) are covered by `test_risk_engine.py`; what is tested here is the
*seam*: that the agent's contract is honoured across a process boundary and that
the numbers survive the trip unchanged.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Numbers the mechanical demo produces. If the bridge changes them, the bridge is
# wrong -- these are asserted against `python -m mcp_servers.host --demo`.
DEMO_PV = 29_500_590.35
DEMO_DV01 = 20_653.25
DEMO_PORTFOLIO = "TREASURY_DEMO_001"


@pytest.fixture(scope="module")
def provider():
    """One provider for the module — the child processes are expensive to start."""
    try:
        from backend.providers.mcp import McpDataProvider, McpUnavailable
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"mcp_data_provider unimportable: {exc}")
    try:
        return McpDataProvider()
    except Exception as exc:  # noqa: BLE001 - any startup failure means "stack down"
        pytest.skip(f"MCP stack unavailable: {exc}")


@pytest.fixture(scope="module")
def risk(provider):
    from backend.workflows.risk_workflows import RiskWorkflows
    return RiskWorkflows(provider)


# -- the seam ----------------------------------------------------------------


def test_provider_satisfies_the_dataprovider_contract(provider):
    """Every method the agent may call must exist with the agreed name."""
    from backend.providers.base import DataProvider

    # `__protocol_attrs__` only exists from 3.12, so read the members off the
    # class instead — this has to keep working on the 3.11 the repo runs on.
    expected = [name for name, value in vars(DataProvider).items()
                if not name.startswith("_") and callable(value)]
    assert expected, "no protocol members found — the contract moved"
    for method in expected:
        assert callable(getattr(provider, method, None)), f"missing {method}"


def test_backend_selection_routes_to_mcp(monkeypatch):
    from backend.providers.base import make_data_provider

    monkeypatch.setenv("DATA_BACKEND", "mcp")
    # Constructing for real would spawn servers; assert the branch, not the object.
    from backend.providers import mcp as mcp_provider_module

    called = {}
    monkeypatch.setattr(mcp_provider_module, "McpDataProvider",
                        lambda: called.setdefault("built", True))
    make_data_provider()
    assert called.get("built"), "DATA_BACKEND=mcp must select the MCP provider"


def test_mock_remains_the_default(monkeypatch):
    from backend.providers.base import MockDataProvider, make_data_provider

    monkeypatch.delenv("DATA_BACKEND", raising=False)
    assert isinstance(make_data_provider(), MockDataProvider)


# -- semantics survive the wire ----------------------------------------------


def test_every_curve_point_maps_to_a_known_tenor(provider):
    curve = provider.get_yield_curve()
    from backend.providers.mcp import MONTHS_BY_TENOR

    assert curve["points"], "curve came back empty"
    assert set(curve["points"]) <= set(MONTHS_BY_TENOR)


def test_curve_carries_its_quoting_basis_and_provenance(provider):
    """A rate without its basis is the bug the whole envelope exists to prevent."""
    curve = provider.get_yield_curve()
    assert curve["quote_basis"] == "par_coupon_semiannual"
    assert curve["dataset_snapshot_id"].startswith("treasury-")
    assert curve["source_file"]


def test_twenty_year_resolves_to_the_par_curve_series(provider):
    """Treasury publishes a 20-year in two feeds; the curve must use one source."""
    assert provider._series_code("y20") == "BC_20YEAR"


def test_holiday_shifts_explicitly_rather_than_silently(provider):
    """4 July 2026 has no curve. Shifting is fine; hiding the shift is not."""
    curve = provider.get_yield_curve("2026-07-04")
    assert curve["date_was_shifted"] is True
    assert curve["curve_date"] != "2026-07-04"
    assert curve["requested_date"] == "2026-07-04"


def test_unknown_tenor_is_reported_not_guessed(provider):
    rows = provider.get_rate_history("y17")
    assert rows and "error" in rows[0]


def test_slope_is_the_difference_of_two_real_points(provider):
    slope = provider.get_curve_slope("y2", "y10")
    expected = round((slope["long_rate"] - slope["short_rate"]) * 100, 1)
    assert slope["slope_bps"] == expected


def test_history_is_bounded_and_ordered(provider):
    rows = provider.get_rate_history("y10", start="2026-01-01", end="2026-08-11")
    dates = [r["observation_date"] for r in rows]
    assert dates == sorted(dates), "history must come back in date order"
    assert len(rows) < 2000


# -- the risk engine reached through the same seam ---------------------------


def test_price_matches_the_mechanical_demo(risk):
    out = risk.price_portfolio(DEMO_PORTFOLIO)
    assert out["total_present_value"] == pytest.approx(DEMO_PV, abs=0.01)


def test_dv01_matches_the_mechanical_demo(risk):
    out = risk.compute_dv01(DEMO_PORTFOLIO, key_rates=True)
    assert out["dv01"] == pytest.approx(DEMO_DV01, abs=0.01)
    assert len(out["key_rate_dv01"]) == 5


def test_var_is_reproducible_and_es_exceeds_it(risk):
    a = risk.compute_var(DEMO_PORTFOLIO)
    b = risk.compute_var(DEMO_PORTFOLIO)
    assert a["run_fingerprint"] == b["run_fingerprint"], "same inputs, same fingerprint"
    assert a["var"] == b["var"]
    # ES is the mean of the tail at or beyond VaR, so it cannot be smaller.
    assert a["expected_shortfall"] >= a["var"]
    assert a["quantile_method"] == "nearest_rank_v1"


def test_historical_replay_reproduces_the_observed_move(risk):
    """The 1994 shock must come from the data, not from a stored constant."""
    out = risk.run_stress(DEMO_PORTFOLIO, scenario_id="REPLAY_1994_BOND_MASSACRE")
    assert out["shocks_bp"]["120.0"] == pytest.approx(39.0, abs=0.5)
    assert out["pnl"] < 0, "a sell-off must lose money on a long book"


def test_convexity_is_visible_in_stress(risk):
    """Full revaluation, so a down-shock must gain more than an up-shock loses."""
    tenors = [1, 1.5, 2, 3, 4, 6, 12, 24, 36, 60, 84, 120, 240, 360]
    up = risk.run_stress(DEMO_PORTFOLIO,
                         shocks_bp_by_tenor_months={str(float(t)): 100 for t in tenors})
    down = risk.run_stress(DEMO_PORTFOLIO,
                           shocks_bp_by_tenor_months={str(float(t)): -100 for t in tenors})
    assert down["pnl"] > abs(up["pnl"]), "an analytic DV01 would make these equal"


def test_bulk_history_travels_out_of_band(provider):
    """1,250 yields must reach the engine via _meta, not through model context."""
    summary, meta = provider.call_tool_with_meta("get_curve_history_matrix", {
        "curve_family": "nominal", "as_of_date": "2026-08-11",
        "trading_days": 250, "tenors_months": [24, 60, 120, 240, 360]})
    from backend.workflows.risk_workflows import MATRIX_META_KEY

    assert MATRIX_META_KEY in meta
    assert "rates_percent" not in summary, "bulk rates must not be in the model's view"
    assert summary["point_count"] == 1250


def test_synthetic_and_real_stay_distinguishable(risk):
    out = risk.price_portfolio(DEMO_PORTFOLIO)
    assert "SYNTHETIC_DEMO" in out["data_classification"]
    assert "REAL_MARKET_DATA" in out["data_classification"]
