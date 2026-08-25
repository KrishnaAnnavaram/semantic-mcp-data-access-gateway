"""P&L attribution, carry and roll, concentration, limits and comparison.

The strongest checks here are the ones that hold *exactly*:

* on a **flat** curve, roll-down is zero and the annualised carry equals the
  curve's own rate - which is only true if the forward-value construction is
  right, and is off by tens of basis points if it is not;
* the four attribution effects sum to the total P&L to machine precision,
  because each is a full revaluation of the same book;
* an unchanged curve produces exactly zero rate effect.

And the one that must NOT be exact: the first-order tenor split of the rate
effect leaves a residual, that residual is the book's convexity, and it grows
with the size of the move. A test asserting it were zero would be asserting the
bonds had no convexity.
"""

from __future__ import annotations

import datetime as dt

import pytest
from mcp_servers.risk.carry_roll import compute_carry_roll
from mcp_servers.risk.concentration import (
    compute_concentration,
    most_concentrated_bucket,
    most_sensitive_tenors,
)
from mcp_servers.risk.curves import build_discount_curve
from mcp_servers.risk.errors import EngineError
from mcp_servers.risk.limits import (
    LimitDefinition,
    evaluate_limit,
    evaluate_limits,
)
from mcp_servers.risk.pnl_attribution import compute_pnl_attribution
from mcp_servers.risk.portfolio_comparison import (
    analyse_hypothetical_trade,
    compare_portfolios,
    size_key_rate_hedge,
)
from mcp_servers.risk.pricing import FixedRateBond, Position
from mcp_servers.risk.stress_scenarios import parallel_shock
from risk_fixtures import (
    VALUATION,
    demo_book,
    demo_positions,
    flat_par,
    single_bond,
    sloped_par,
    synthetic_history,
)

HORIZON = dt.date(2027, 8, 15)


# --- carry and roll ----------------------------------------------------------


def test_on_a_flat_curve_roll_down_is_exactly_zero():
    """The defining property. A sloped curve is what creates roll."""
    result = compute_carry_roll(demo_positions(), VALUATION, HORIZON, flat_par(4.0))
    assert result.roll_down == pytest.approx(0.0, abs=1e-6)
    assert result.total_carry_and_roll == pytest.approx(result.carry, abs=1e-6)


@pytest.mark.parametrize("rate", [2.0, 4.0, 9.0])
def test_carry_over_a_coupon_free_window_equals_the_curve_s_own_growth_exactly(rate):
    """The exact statement of what carry is, with nothing else in the way.

    Over 15 August to 15 November no demo bond pays, so cash received is zero
    and the whole of carry is the position rolling forward on the unchanged
    curve. No-arbitrage then fixes it completely:

        carry / V(t0) = 1 / D(dt) - 1

    with D the bootstrapped discount factor to the horizon. The test computes
    the right-hand side from the curve itself and requires a match to twelve
    decimal places - which is only achievable if the forward-value construction,
    the quasi-coupon time basis and the bootstrap all agree.
    """
    horizon = dt.date(2026, 11, 15)
    result = compute_carry_roll(demo_positions(), VALUATION, horizon, flat_par(rate))
    assert result.cash_received == 0.0, "no coupon falls inside this window"

    curve = build_discount_curve(flat_par(rate))
    elapsed_years = 0.5 * (horizon - VALUATION).days / 184.0     # quasi-coupon basis
    expected_growth = 1.0 / curve.discount_factor(elapsed_years) - 1.0

    assert result.carry / result.start_value == pytest.approx(
        expected_growth, abs=1e-12)
    assert result.roll_down == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("rate", [2.0, 4.0, 6.0, 9.0])
def test_a_one_year_hold_returns_close_to_the_curve_rate(rate):
    """Close, not equal, and the gap has a stated cause.

    Over a full year two coupons are paid, and this engine counts them at face
    rather than reinvesting them. That leaves the annualised figure a little
    below the curve rate when coupons are large relative to it and a little
    above when the position's own compounding dominates. The gap stays inside
    30bp across the whole plausible range, and a construction error would put it
    far outside.
    """
    result = compute_carry_roll(demo_positions(), VALUATION, HORIZON,
                                flat_par(rate))
    assert result.annualised_carry_and_roll_percent == pytest.approx(rate, abs=0.30)
    assert "not reinvested" in result.cash_treatment


def test_an_upward_sloping_curve_produces_positive_roll_that_grows_with_maturity():
    result = compute_carry_roll(demo_positions(), VALUATION, HORIZON, sloped_par())
    assert result.roll_down > 0
    roll_bp = [p.roll_bp_of_value for p in result.positions]
    assert roll_bp[0] < roll_bp[2], "the 10y must roll further than the 2y"


def test_the_carry_and_roll_identity_holds_exactly():
    """static value + cash received - start value == carry + roll."""
    for curve in (flat_par(4.0), sloped_par()):
        result = compute_carry_roll(demo_positions(), VALUATION, HORIZON, curve)
        assert (result.static_value + result.cash_received - result.start_value
                == pytest.approx(result.total_carry_and_roll, rel=1e-10))


def test_a_position_maturing_inside_the_horizon_has_no_forward_value():
    result = compute_carry_roll(demo_positions(), VALUATION, dt.date(2029, 8, 15),
                                sloped_par())
    two_year = result.positions[0]
    assert two_year.forward_value == 0.0
    assert two_year.roll_down == 0.0
    assert two_year.coupons_received == 4      # semiannual, matures 2028-08-15


def test_a_horizon_that_does_not_advance_is_refused():
    with pytest.raises(EngineError) as excinfo:
        compute_carry_roll(demo_positions(), VALUATION, VALUATION, sloped_par())
    assert excinfo.value.code == "INVALID_HORIZON"


# --- P&L attribution ---------------------------------------------------------


def attribution(end_curve, positions_end=None, start_curve=None):
    return compute_pnl_attribution(
        demo_positions(), VALUATION, start_curve or sloped_par(),
        HORIZON, end_curve, positions_end)


def test_an_unchanged_curve_leaves_the_rate_effect_exactly_zero():
    result = attribution(sloped_par())
    assert result.rate_move == pytest.approx(0.0, abs=1e-6)
    assert result.total_pnl == pytest.approx(result.carry + result.roll_down,
                                             rel=1e-10)


def test_pure_passage_of_time_on_a_flat_curve_is_all_carry():
    result = attribution(flat_par(4.0), start_curve=flat_par(4.0))
    assert result.rate_move == pytest.approx(0.0, abs=1e-6)
    assert result.roll_down == pytest.approx(0.0, abs=1e-6)
    assert result.carry == pytest.approx(result.total_pnl, rel=1e-10)


def test_the_four_effects_sum_to_the_total_to_machine_precision():
    for end in (sloped_par(), sloped_par().shifted(100.0),
                sloped_par().shifted(-150.0),
                sloped_par().shocked({10.0: 75.0})):
        result = attribution(end)
        recomposed = (result.carry + result.roll_down + result.rate_move
                      + (result.position_change or 0.0) + result.residual)
        assert recomposed == pytest.approx(result.total_pnl, rel=1e-10)
        assert abs(result.residual) < 1e-6, (
            "the top-level residual compares four full revaluations with the "
            "total and must be at machine precision")


def test_a_parallel_rise_produces_a_negative_rate_effect_and_a_fall_a_positive_one():
    assert attribution(sloped_par().shifted(100.0)).rate_move < 0
    assert attribution(sloped_par().shifted(-100.0)).rate_move > 0


def test_a_single_key_rate_move_is_attributed_to_that_tenor():
    result = attribution(sloped_par().shocked({10.0: 50.0}))
    moved = [e for e in result.tenor_effects if e.change_bp != 0.0]
    assert len(moved) == 1
    assert moved[0].tenor_years == 10.0
    assert moved[0].change_bp == pytest.approx(50.0)
    assert moved[0].pnl < 0


def test_the_tenor_split_leaves_a_residual_that_grows_with_the_move():
    """The convexity. Scaling the parts to close it would destroy the diagnostic."""
    small = attribution(sloped_par().shifted(25.0))
    large = attribution(sloped_par().shifted(300.0))
    assert abs(small.rate_unexplained) > 0
    assert abs(large.rate_unexplained) > abs(small.rate_unexplained) * 10
    assert large.rate_unexplained_percent > small.rate_unexplained_percent


def test_the_tenor_effects_sum_to_the_reported_explained_figure():
    result = attribution(sloped_par().shifted(100.0))
    assert sum(e.pnl for e in result.tenor_effects) == pytest.approx(
        result.rate_explained_by_tenor, rel=1e-12)
    assert result.rate_unexplained == pytest.approx(
        result.rate_move - result.rate_explained_by_tenor, rel=1e-12)


def test_position_change_is_null_when_no_end_snapshot_is_supplied():
    """'Nothing traded' and 'we were not told' are different claims."""
    assert attribution(sloped_par()).position_change is None


def test_position_change_is_measured_when_an_end_snapshot_is_supplied():
    halved = [Position(p.bond, p.face_notional * 0.5) for p in demo_positions()]
    result = attribution(sloped_par(), positions_end=halved)
    assert result.position_change is not None
    assert result.position_change < 0
    assert abs(result.residual) < 1e-6


def test_an_identical_end_snapshot_gives_a_zero_position_change():
    result = attribution(sloped_par(), positions_end=demo_positions())
    assert result.position_change == pytest.approx(0.0, abs=1e-6)


def test_a_backwards_attribution_period_is_refused():
    with pytest.raises(EngineError) as excinfo:
        compute_pnl_attribution(demo_positions(), HORIZON, sloped_par(),
                                VALUATION, sloped_par())
    assert excinfo.value.code == "INVALID_HORIZON"


def test_bucket_effects_partition_the_tenor_effects():
    result = attribution(sloped_par().shifted(100.0))
    assert sum(v for _, v in result.bucket_effects) == pytest.approx(
        result.rate_explained_by_tenor, rel=1e-10)


# --- concentration -----------------------------------------------------------


def test_concentration_reports_every_dimension_it_can_compute():
    report = compute_concentration(demo_book(), sloped_par(), top_n=3)
    dimensions = {d.dimension for d in report.dimensions}
    assert {"present_value", "position_dv01", "position_notional",
            "key_rate_dv01", "maturity_bucket_dv01"} <= dimensions
    assert "component_var" not in dimensions, (
        "VaR contribution concentration must be omitted, not defaulted, when no "
        "history was supplied")


def test_concentration_includes_optional_dimensions_when_the_inputs_arrive():
    report = compute_concentration(
        demo_book(), sloped_par(), top_n=3,
        stress_position_pnl=[("A", -100.0), ("B", -50.0)],
        var_contributions=[("A", 60.0), ("B", 40.0)],
        es_contributions=[("A", 70.0), ("B", 30.0)])
    dimensions = {d.dimension for d in report.dimensions}
    assert {"stress_loss", "component_var",
            "component_expected_shortfall"} <= dimensions


def test_concentration_is_measured_on_absolute_magnitudes():
    """An offsetting long and short is two concentrations, not an absence of risk."""
    from mcp_servers.risk.contributions import concentration_of
    offsetting = concentration_of([1000.0, -1000.0])
    assert offsetting.effective_count == pytest.approx(2.0)
    assert offsetting.top_share_percent == pytest.approx(50.0)


def test_top_n_entries_are_ranked_by_absolute_magnitude():
    report = compute_concentration(demo_book(), sloped_par(), top_n=3)
    for dimension in report.dimensions:
        values = [abs(e.value) for e in dimension.entries]
        assert values == sorted(values, reverse=True)
        assert [e.rank for e in dimension.entries] == list(
            range(1, len(dimension.entries) + 1))
        assert len(dimension.entries) <= 3


def test_the_most_sensitive_tenors_are_ordered_by_key_rate_dv01():
    selected = most_sensitive_tenors(demo_book(), sloped_par(), 3)
    assert [abs(v) for _, v in selected] == sorted(
        (abs(v) for _, v in selected), reverse=True)
    assert selected[0][0] == 10.0


def test_the_most_concentrated_bucket_is_named():
    label, value = most_concentrated_bucket(demo_book(), sloped_par())
    assert label in {"0-2y", "2-5y", "5-10y", "10-20y", "20y+"}
    assert value != 0.0


def test_a_single_position_book_is_maximally_concentrated():
    from mcp_servers.risk.revaluation import compile_book
    book = compile_book(single_bond(), VALUATION)
    report = compute_concentration(book, sloped_par())
    dv01 = next(d for d in report.dimensions if d.dimension == "position_dv01")
    assert dv01.concentration.top_share_percent == pytest.approx(100.0)
    assert dv01.concentration.effective_count == pytest.approx(1.0)


def test_an_invalid_top_n_is_refused():
    with pytest.raises(EngineError) as excinfo:
        compute_concentration(demo_book(), sloped_par(), top_n=0)
    assert excinfo.value.code == "INVALID_LIMIT"


# --- limits ------------------------------------------------------------------


@pytest.mark.parametrize("current,expected", [
    (0.0, "GREEN"), (50.0, "GREEN"), (79.99, "GREEN"),
    (80.0, "AMBER"), (99.99, "AMBER"),
    (100.0, "RED"), (150.0, "RED"),
])
def test_the_status_boundaries_are_closed_from_below(current, expected):
    """At the amber threshold it is amber; at the limit it is red."""
    result = evaluate_limit(LimitDefinition("metric", 100.0, current))
    assert result.status == expected


def test_utilisation_and_headroom_are_computed_from_the_absolute_value():
    """A large short breaches a DV01 limit too."""
    result = evaluate_limit(LimitDefinition("dv01", 1000.0, -1200.0))
    assert result.utilisation_percent == pytest.approx(120.0)
    assert result.remaining_headroom == pytest.approx(-200.0)
    assert result.status == "RED"


def test_an_explicit_amber_threshold_overrides_the_default():
    strict = evaluate_limit(LimitDefinition("m", 100.0, 55.0,
                                            amber_utilisation_percent=50.0))
    lenient = evaluate_limit(LimitDefinition("m", 100.0, 55.0,
                                             amber_utilisation_percent=90.0))
    assert (strict.status, lenient.status) == ("AMBER", "GREEN")
    assert strict.amber_utilisation_percent == 50.0


@pytest.mark.parametrize("limit,amber", [
    (0.0, 80.0), (-100.0, 80.0), (100.0, 0.0), (100.0, 100.0), (100.0, -5.0),
])
def test_an_unusable_limit_definition_is_refused(limit, amber):
    with pytest.raises(EngineError) as excinfo:
        evaluate_limit(LimitDefinition("m", limit, 1.0,
                                       amber_utilisation_percent=amber))
    assert excinfo.value.code == "INVALID_LIMIT"


def test_a_report_counts_breaches_and_names_the_worst_metric():
    report = evaluate_limits([
        LimitDefinition("dv01", 25_000.0, 21_235.0),
        LimitDefinition("stress_loss", 3_000_000.0, 3_756_600.0),
        LimitDefinition("var", 100_000.0, 20_000.0),
    ])
    assert report.breach_count == 1
    assert report.amber_count == 1
    assert report.worst_metric == "stress_loss"
    assert not report.all_within_limits


def test_an_empty_limit_set_is_refused_rather_than_defaulted():
    """This engine has no default limits and must not invent one."""
    with pytest.raises(EngineError) as excinfo:
        evaluate_limits([])
    assert excinfo.value.code == "INVALID_LIMIT"
    assert "will not assume" in excinfo.value.plain_message


def test_the_threshold_policy_is_stated_in_every_report():
    report = evaluate_limits([LimitDefinition("m", 100.0, 10.0)])
    assert "caller-supplied" in report.threshold_policy
    assert "no risk policy" in report.threshold_policy


# --- portfolio comparison ----------------------------------------------------


def test_comparing_a_portfolio_with_itself_produces_zero_differences():
    result = compare_portfolios(demo_positions(), demo_positions(),
                                VALUATION, sloped_par())
    for row in result.rows:
        assert row.difference == pytest.approx(0.0, abs=1e-6), row.measure
    assert result.risk_reduction_percent == pytest.approx(0.0, abs=1e-9)


def test_a_hedge_reduces_dv01_and_the_reduction_is_reported():
    hedge = [Position(FixedRateBond("HEDGE_10Y", 1000.0, 4.25,
                                    dt.date(2036, 8, 15), VALUATION), -4_000_000)]
    result = compare_portfolios(demo_positions(), demo_positions() + hedge,
                                VALUATION, sloped_par(), "Unhedged", "Hedged")
    dv01 = next(r for r in result.rows if r.measure == "dv01")
    assert dv01.portfolio_b < dv01.portfolio_a
    assert result.risk_reduction_percent > 0


def test_var_and_es_are_omitted_from_both_sides_when_no_history_is_given():
    without = compare_portfolios(demo_positions(), demo_positions(),
                                 VALUATION, sloped_par())
    assert "historical_var" in without.measures_omitted
    assert not any("var" in r.measure for r in without.rows)

    tenors, rows = synthetic_history(260)
    with_history = compare_portfolios(
        demo_positions(), demo_positions(), VALUATION, sloped_par(),
        history_tenors_years=tenors, history_rates_percent=rows)
    assert with_history.measures_omitted == ()
    assert any("historical_var" in r.measure for r in with_history.rows)


def test_scenarios_are_run_against_both_books_on_the_same_curve():
    par = sloped_par()
    result = compare_portfolios(demo_positions(), demo_positions()[:3],
                                VALUATION, par,
                                scenarios=[parallel_shock(par, 100.0)])
    assert len(result.scenario_rows) == 1
    assert result.scenario_rows[0].portfolio_a < 0
    assert result.scenario_rows[0].portfolio_b > result.scenario_rows[0].portfolio_a


def test_a_hypothetical_trade_does_not_mutate_the_supplied_positions():
    positions = demo_positions()
    before = [(p.bond.instrument_id, p.face_notional) for p in positions]
    addition = [Position(FixedRateBond("NEW_10Y", 1000.0, 4.25,
                                       dt.date(2036, 8, 15), VALUATION), 10_000_000)]
    result = analyse_hypothetical_trade(positions, addition, VALUATION, sloped_par())
    assert [(p.bond.instrument_id, p.face_notional) for p in positions] == before
    dv01 = next(r for r in result.rows if r.measure == "dv01")
    assert dv01.portfolio_b > dv01.portfolio_a


def test_an_empty_hypothetical_trade_is_refused():
    with pytest.raises(EngineError) as excinfo:
        analyse_hypothetical_trade(demo_positions(), [], VALUATION, sloped_par())
    assert excinfo.value.code == "INCONSISTENT_PORTFOLIOS"


# --- hedge sizing ------------------------------------------------------------


def test_the_sized_hedge_drives_the_target_key_rate_to_zero():
    result = size_key_rate_hedge(demo_positions(), VALUATION, sloped_par(), 10.0)
    assert result.post_hedge_key_rate_dv01 == pytest.approx(0.0, abs=1e-6)
    assert result.hedge_notional < 0, "hedging a long book means selling"
    assert abs(result.post_hedge_portfolio_dv01) < abs(result.pre_hedge_portfolio_dv01)


def test_the_hedge_reports_its_effect_on_every_other_tenor():
    """A hedge that flattens one node and moves three others is not a hedge."""
    result = size_key_rate_hedge(demo_positions(), VALUATION, sloped_par(), 10.0)
    residual = dict(result.residual_key_rate_dv01)
    assert set(residual) == set(sloped_par().tenors_years)
    assert residual[10.0] == pytest.approx(0.0, abs=1e-6)
    assert residual[30.0] != pytest.approx(0.0, abs=1.0), (
        "the 30-year exposure is untouched by a 10-year hedge and must be shown")


def test_hedge_sizing_is_linear_in_the_target():
    par = sloped_par()
    to_zero = size_key_rate_hedge(demo_positions(), VALUATION, par, 10.0, 0.0)
    to_half = size_key_rate_hedge(demo_positions(), VALUATION, par, 10.0,
                                  to_zero.pre_hedge_key_rate_dv01 / 2.0)
    assert to_half.hedge_notional == pytest.approx(to_zero.hedge_notional / 2.0,
                                                   rel=1e-6)


def test_hedging_at_a_non_node_tenor_is_refused():
    with pytest.raises(EngineError) as excinfo:
        size_key_rate_hedge(demo_positions(), VALUATION, sloped_par(), 12.5)
    assert excinfo.value.code == "MISSING_CURVE_TENOR"


def test_the_hedge_instrument_pays_the_curve_s_own_par_rate():
    par = sloped_par()
    result = size_key_rate_hedge(demo_positions(), VALUATION, par, 10.0)
    assert result.coupon_rate_pct == pytest.approx(par.par_rate_at(10.0))
    assert result.maturity_date.year == VALUATION.year + 10
