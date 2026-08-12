"""Golden and property tests for the risk engine.

The golden cases are verified by hand, not by recording whatever the code
produced. A fixture that captures current output only proves the code has not
changed; it says nothing about whether it was ever right.

The property tests exist because financial code fails in ways unit tests miss:
a sign flip that only shows on a rate cut, an ordering dependence that appears
when a portfolio is rebalanced. Properties catch those classes at once.
"""

from __future__ import annotations

import datetime as dt
import math

import pytest

from src.mcp_risk.curves import (
    CurveError, ParCurve, build_discount_curve, simple_discount_factor,
)
from src.mcp_risk.manifest import MODEL_MANIFEST, run_fingerprint
from src.mcp_risk.pricing import (
    FixedRateBond, Position, PricingError, generate_cash_flows, price_bond,
    price_portfolio,
)
from src.mcp_risk.risk import (
    RiskError, compute_dv01, compute_historical_risk, compute_key_rate_dv01,
    nearest_rank_quantile, run_stress,
)

VALUATION = dt.date(2026, 8, 15)


def flat_par(rate_pct: float, out_to: float = 30.0) -> ParCurve:
    tenors = [0.5, 1, 2, 3, 5, 7, 10, 20, out_to]
    return ParCurve(tuple(tenors), tuple(rate_pct for _ in tenors))


# --- golden: the bootstrap ---------------------------------------------------


def test_flat_par_curve_bootstraps_to_analytic_discount_factors():
    """A flat par curve has a closed form, so the bootstrap can be checked exactly.

    At a flat par rate c with semiannual periods, the par bond identity is
    satisfied by D_n = 1 / (1 + c/2)^n - the discount curve of a bond yielding c
    compounded semiannually. Any bootstrap that does not reproduce that is wrong.
    """
    c = 0.04
    curve = build_discount_curve(flat_par(4.0))
    for k in (1, 2, 10, 20, 60):
        t = k * 0.5
        expected = 1.0 / (1.0 + c / 2.0) ** k
        assert curve.discount_factor(t) == pytest.approx(expected, rel=1e-12), (
            f"discount factor at {t}y")


def test_par_bond_prices_to_par_under_its_own_curve():
    """The defining property: a bond whose coupon equals the par yield is worth 100.

    This is the single strongest check that par yields have not been mistaken
    for zero rates. Treating 4% par as a 4% spot rate prices a 10-year bond at
    roughly 100.0 too - which is why the test uses a *sloped* curve below.
    """
    curve = build_discount_curve(flat_par(4.0))
    bond = FixedRateBond("GOLD_10Y", 100.0, 4.0, dt.date(2036, 8, 15), dt.date(2026, 8, 15))
    value = price_bond(bond, VALUATION, curve).present_value
    assert value == pytest.approx(100.0, rel=1e-9)


def test_sloped_curve_par_bond_still_prices_to_par():
    """The test that actually distinguishes par from spot.

    On an upward-sloping curve the par yield and the zero rate differ
    materially. A bond paying the 10-year par coupon must still be worth 100; if
    the engine discounted at par yields as though they were spot rates, it would
    not be.
    """
    par = ParCurve((0.5, 1, 2, 3, 5, 7, 10, 20, 30),
                   (3.0, 3.2, 3.5, 3.7, 4.0, 4.3, 4.6, 5.0, 5.1))
    curve = build_discount_curve(par)
    coupon = par.par_rate_at(10.0)
    bond = FixedRateBond("GOLD_SLOPED", 100.0, coupon,
                         dt.date(2036, 8, 15), dt.date(2026, 8, 15))
    assert price_bond(bond, VALUATION, curve).present_value == pytest.approx(100.0, rel=1e-6)


def test_zero_rate_exceeds_par_yield_on_an_upward_sloping_curve():
    """Sanity on the relationship itself, not just the arithmetic."""
    par = ParCurve((0.5, 1, 2, 5, 10, 30), (2.0, 2.3, 2.8, 3.5, 4.2, 4.8))
    curve = build_discount_curve(par)
    assert curve.zero_rate(10.0) > par.par_rate_at(10.0)


def test_bootstrap_rejects_a_curve_implying_negative_forwards():
    with pytest.raises(CurveError, match="negative forward|non-positive"):
        build_discount_curve(ParCurve((0.5, 1, 2, 30), (5.0, 5.0, 5.0, -20.0)))


def test_duplicate_tenor_nodes_are_rejected():
    """The bug V013 fixed, guarded at the engine boundary as well."""
    with pytest.raises(CurveError, match="duplicate tenor"):
        ParCurve((1.0, 20.0, 20.0, 30.0), (3.0, 4.0, 4.1, 4.2))


def test_simple_discount_matches_money_market_convention():
    assert simple_discount_factor(4.0, 0.25) == pytest.approx(1 / (1 + 0.04 * 0.25))


# --- golden: cash flows ------------------------------------------------------


def test_cash_flows_are_generated_backwards_from_maturity():
    bond = FixedRateBond("B", 1000.0, 5.0, dt.date(2031, 8, 15), dt.date(2026, 8, 15))
    flows = generate_cash_flows(bond, VALUATION)
    assert len(flows) == 10                      # 5 years semiannual
    assert flows[-1].date == dt.date(2031, 8, 15)
    assert flows[0].date == dt.date(2027, 2, 15)  # anchored on maturity, not issue
    assert flows[0].amount == pytest.approx(25.0)          # 1000 * 5% / 2
    assert flows[-1].amount == pytest.approx(1025.0)       # + principal


def test_matured_bond_has_no_cash_flows_and_zero_value():
    bond = FixedRateBond("OLD", 1000.0, 5.0, dt.date(2020, 1, 1), dt.date(2010, 1, 1))
    assert generate_cash_flows(bond, VALUATION) == []
    assert price_bond(bond, VALUATION, build_discount_curve(flat_par(4.0))).present_value == 0.0


def test_unsupported_conventions_are_rejected_not_approximated():
    with pytest.raises(PricingError, match="semiannual"):
        FixedRateBond("Q", 100.0, 4.0, dt.date(2030, 1, 1), dt.date(2026, 1, 1),
                      coupon_frequency=4)
    with pytest.raises(PricingError, match="day_count"):
        FixedRateBond("D", 100.0, 4.0, dt.date(2030, 1, 1), dt.date(2026, 1, 1),
                      day_count="30_360")


# --- properties --------------------------------------------------------------


def demo_book() -> list[Position]:
    specs = [("DEMO_NOTE_2Y", 3.75, dt.date(2028, 8, 15), 5_000_000),
             ("DEMO_NOTE_5Y", 4.00, dt.date(2031, 8, 15), 10_000_000),
             ("DEMO_NOTE_10Y", 4.25, dt.date(2036, 8, 15), 8_000_000),
             ("DEMO_BOND_20Y", 4.50, dt.date(2046, 8, 15), 4_000_000),
             ("DEMO_BOND_30Y", 4.75, dt.date(2056, 8, 15), 3_000_000)]
    return [Position(FixedRateBond(i, 1000.0, c, m, dt.date(2026, 8, 15)), n)
            for i, c, m, n in specs]


def test_higher_yields_lower_the_value_of_a_long_fixed_rate_book():
    book, base_par = demo_book(), flat_par(4.0)
    base = price_portfolio(book, VALUATION, build_discount_curve(base_par)).total_present_value
    up = price_portfolio(book, VALUATION,
                         build_discount_curve(base_par.shifted(100))).total_present_value
    down = price_portfolio(book, VALUATION,
                           build_discount_curve(base_par.shifted(-100))).total_present_value
    assert up < base < down


def test_portfolio_value_is_the_sum_of_its_positions():
    book = demo_book()
    result = price_portfolio(book, VALUATION, build_discount_curve(flat_par(4.0)))
    assert result.total_present_value == pytest.approx(
        sum(p.present_value for p in result.positions), rel=1e-12)


def test_valuation_does_not_depend_on_position_order():
    book = demo_book()
    curve = build_discount_curve(flat_par(4.0))
    forward = price_portfolio(book, VALUATION, curve).total_present_value
    reverse = price_portfolio(list(reversed(book)), VALUATION, curve).total_present_value
    assert forward == pytest.approx(reverse, rel=1e-12)


def test_dv01_is_positive_for_a_long_book_and_scales_with_the_shock():
    book, par = demo_book(), flat_par(4.0)
    dv01 = compute_dv01(book, VALUATION, par).dv01
    assert dv01 > 0
    # Convexity makes this approximate, not exact - so the tolerance is loose
    # on purpose. Asserting equality here would be asserting the bond has none.
    ten = run_stress(book, VALUATION, par, {t: 10.0 for t in par.tenors_years}).pnl
    assert -ten == pytest.approx(dv01 * 10, rel=0.01)


def test_zero_shock_produces_zero_pnl():
    book, par = demo_book(), flat_par(4.0)
    assert run_stress(book, VALUATION, par,
                      {t: 0.0 for t in par.tenors_years}).pnl == pytest.approx(0.0, abs=1e-6)


def test_stress_position_contributions_sum_to_portfolio_pnl():
    book, par = demo_book(), flat_par(4.0)
    result = run_stress(book, VALUATION, par, {t: 100.0 for t in par.tenors_years})
    assert result.pnl == pytest.approx(sum(v for _, v in result.per_position), rel=1e-12)


def test_key_rate_dv01s_sum_to_approximately_the_parallel_dv01():
    book, par = demo_book(), flat_par(4.0)
    krd = compute_key_rate_dv01(book, VALUATION, par)
    parallel = compute_dv01(book, VALUATION, par).dv01
    assert krd.total == pytest.approx(parallel, rel=0.02)


def test_key_rate_bump_on_a_non_node_is_rejected():
    with pytest.raises(RiskError, match="not nodes"):
        compute_key_rate_dv01(demo_book(), VALUATION, flat_par(4.0), key_tenors_years=[12.5])


# --- golden: the quantile convention ----------------------------------------


def test_nearest_rank_quantile_is_exactly_ceil_alpha_n():
    losses = [float(i) for i in range(1, 101)]   # 1..100 ascending
    value, index = nearest_rank_quantile(losses, 0.99)
    assert (value, index) == (99.0, 98)          # ceil(0.99*100) = 99 -> 99.0
    assert nearest_rank_quantile(losses, 0.95)[0] == 95.0
    # A small sample is where interpolation conventions diverge most.
    assert nearest_rank_quantile([10.0, 20.0, 30.0], 0.99)[0] == 30.0


# --- historical risk ---------------------------------------------------------


def synthetic_history(n: int = 260) -> tuple[list[float], list[list[float]]]:
    """Deterministic sawtooth history - reproducible, no RNG dependence."""
    tenors = [2.0, 5.0, 10.0, 30.0]
    rows = [[4.0 + 0.01 * math.sin(i / 3.0 + j) for j in range(len(tenors))]
            for i in range(n)]
    return tenors, rows


def test_historical_var_and_es_are_consistent():
    book, par = demo_book(), flat_par(4.0)
    tenors, rows = synthetic_history()
    r = compute_historical_risk(book, VALUATION, par, tenors, rows,
                                confidence_level=0.99, horizon_days=1)
    assert r.scenarios_used == len(rows) - 1
    assert r.var >= 0
    # ES averages the tail at or beyond VaR, so it can never be smaller.
    assert r.expected_shortfall >= r.var
    assert r.worst_loss >= r.expected_shortfall


def test_ten_day_horizon_uses_observed_changes_not_sqrt_scaling():
    """A 10-day VaR must not be a 1-day VaR multiplied by sqrt(10)."""
    book, par = demo_book(), flat_par(4.0)
    tenors, rows = synthetic_history()
    one = compute_historical_risk(book, VALUATION, par, tenors, rows, horizon_days=1)
    ten = compute_historical_risk(book, VALUATION, par, tenors, rows, horizon_days=10)
    assert ten.scenarios_used == len(rows) - 10
    assert ten.var != pytest.approx(one.var * math.sqrt(10), rel=1e-6)


def test_insufficient_history_is_refused():
    book, par = demo_book(), flat_par(4.0)
    with pytest.raises(RiskError, match="cannot produce"):
        compute_historical_risk(book, VALUATION, par, [2.0], [[4.0], [4.1]],
                                horizon_days=10)


def test_ragged_history_is_refused():
    book, par = demo_book(), flat_par(4.0)
    with pytest.raises(RiskError, match="ragged"):
        compute_historical_risk(book, VALUATION, par, [2.0, 5.0],
                                [[4.0, 4.1], [4.0], [4.2, 4.3]])


# --- reproducibility ---------------------------------------------------------


def test_identical_inputs_produce_an_identical_fingerprint():
    payload = {"portfolio": "TREASURY_DEMO_001", "confidence": 0.99, "days": 250}
    assert run_fingerprint(payload) == run_fingerprint(dict(reversed(list(payload.items()))))


def test_fingerprint_changes_when_the_model_manifest_changes():
    payload = {"portfolio": "X"}
    before = run_fingerprint(payload)
    original = MODEL_MANIFEST["quantile_method"]
    try:
        MODEL_MANIFEST["quantile_method"] = "linear_interpolation_v1"
        assert run_fingerprint(payload) != before, (
            "changing the quantile convention must change the fingerprint, or a "
            "methodology change could masquerade as the same calculation")
    finally:
        MODEL_MANIFEST["quantile_method"] = original


def test_the_engine_never_imports_a_database_driver():
    """The calculation boundary, asserted rather than assumed.

    Checks the import graph via the AST rather than grepping for the package
    name - the first version of this test failed on a *comment* explaining that
    psycopg2 must not be imported, which is a false positive that would train
    someone to stop writing the explanation.
    """
    import ast  # noqa: PLC0415
    import pathlib  # noqa: PLC0415

    banned = {"psycopg2", "sqlalchemy", "asyncpg", "requests", "httpx",
              "anthropic", "openai", "socket", "urllib"}
    package = pathlib.Path(__file__).resolve().parents[1] / "src" / "mcp_risk"

    for path in sorted(package.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])
        offending = imported & banned
        assert not offending, (
            f"src/mcp_risk/{path.name} imports {sorted(offending)}; the risk "
            "engine must have no database, network or model access")
