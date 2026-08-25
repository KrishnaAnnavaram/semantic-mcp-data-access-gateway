"""Golden and validation tests for bond analytics and curve analytics.

The golden values here are established three ways, and never by recording what
the code produced:

1. **Closed form.** The Macaulay duration of a level-coupon bond has an
   algebraic solution; it is written out in the test and compared.
2. **Definitional identity.** A par bond is worth 100; clean plus accrued is
   dirty; a flat par curve's semiannual zero rate equals the par rate at every
   node. These are true by definition and cannot be satisfied by a wrong engine.
3. **An independent numerical route.** Duration and convexity are also computed
   by finite differences of `price_from_yield`, which is a different code path
   from the analytic formulas in `yield_based_measures`. Two implementations
   agreeing to seven digits is evidence; one implementation agreeing with itself
   is not.
"""

from __future__ import annotations

import datetime as dt
import math

import pytest
from mcp_servers.risk.bond_analytics import (
    accrued_interest,
    analyse_bond,
    approximate_price_change,
    portfolio_rollup,
    price_from_yield,
    yield_based_measures,
    yield_to_maturity,
)
from mcp_servers.risk.curve_analytics import (
    NAMED_BUTTERFLIES,
    NAMED_SPREADS,
    analyse_curve,
    butterfly_bp,
    curve_change_bp,
    diagnose_inversion,
    implied_forward,
    spread_bp,
    zero_rate_semiannual,
)
from mcp_servers.risk.curves import ParCurve, build_discount_curve
from mcp_servers.risk.errors import EngineError
from mcp_servers.risk.pricing import FixedRateBond, current_quasi_period
from risk_fixtures import (
    VALUATION,
    demo_positions,
    flat_par,
    inverted_par,
    sloped_par,
)


def par_bond(coupon: float = 4.0, maturity: dt.date = dt.date(2036, 8, 15),
             issue: dt.date = VALUATION, face: float = 100.0) -> FixedRateBond:
    return FixedRateBond("GOLD", face, coupon, maturity, issue)


# --- golden: prices and the clean/dirty split --------------------------------


def test_par_bond_on_its_own_flat_curve_is_worth_exactly_100():
    analytics = analyse_bond(par_bond(), VALUATION, flat_par(4.0))
    assert analytics.dirty_price_per_100 == pytest.approx(100.0, rel=1e-12)
    assert analytics.accrued_per_100 == pytest.approx(0.0, abs=1e-12)
    assert analytics.clean_price_per_100 == pytest.approx(100.0, rel=1e-12)


def test_par_bond_ytm_equals_the_flat_par_rate_exactly():
    """The strongest single check that the yield solver and the pricer agree.

    A bond paying 4% on a flat 4% par curve prices to 100, so the yield that
    reprices it must be 4%. Any disagreement between the solver's cash-flow
    convention and the pricer's shows up here immediately.
    """
    analytics = analyse_bond(par_bond(), VALUATION, flat_par(4.0))
    assert analytics.ytm_percent == pytest.approx(4.0, abs=1e-9)
    assert analytics.ytm_converged


def test_clean_plus_accrued_equals_dirty_to_floating_point():
    """Not approximately. The split uses the same w that places the cash flows."""
    for valuation in (dt.date(2026, 10, 1), dt.date(2026, 12, 31),
                      dt.date(2027, 2, 14), dt.date(2027, 8, 14)):
        bond = FixedRateBond("MID", 1000.0, 5.0, dt.date(2031, 2, 15),
                             dt.date(2021, 2, 15))
        a = analyse_bond(bond, valuation, flat_par(4.0), face_notional=5_000_000)
        assert a.clean_price_per_100 + a.accrued_per_100 == pytest.approx(
            a.dirty_price_per_100, abs=1e-11), f"identity failed at {valuation}"
        assert a.clean_value + a.accrued_interest == pytest.approx(
            a.present_value, rel=1e-12)


def test_accrued_interest_matches_the_day_count_computed_independently():
    """ACT/ACT ICMA: coupon x elapsed days / days in the quasi-coupon period."""
    valuation = dt.date(2026, 10, 1)
    bond = FixedRateBond("MID", 1000.0, 5.0, dt.date(2031, 2, 15), dt.date(2021, 2, 15))
    period = current_quasi_period(bond, valuation)
    elapsed = (valuation - period.period_start).days
    span = (period.period_end - period.period_start).days
    expected_per_100 = 5.0 / 2.0 * (elapsed / span)

    assert (elapsed, span) == (47, 184)
    assert accrued_interest(bond, valuation, face_notional=100.0) == pytest.approx(
        expected_per_100, rel=1e-12)
    # Scaling to the held notional is linear and exact.
    assert accrued_interest(bond, valuation, face_notional=5_000_000.0) == pytest.approx(
        expected_per_100 * 50_000.0, rel=1e-12)


def test_accrued_is_zero_exactly_on_a_coupon_date():
    bond = FixedRateBond("ONCOUPON", 1000.0, 5.0, dt.date(2031, 2, 15),
                         dt.date(2021, 2, 15))
    assert accrued_interest(bond, dt.date(2027, 2, 15)) == 0.0


def test_ytm_reprices_the_bond_it_was_solved_from():
    """The defining property of a yield to maturity."""
    bond = FixedRateBond("REPRICE", 1000.0, 5.5, dt.date(2041, 3, 31),
                         dt.date(2019, 3, 31))
    analytics = analyse_bond(bond, VALUATION, sloped_par(), face_notional=7_500_000)
    repriced = price_from_yield(bond, VALUATION, analytics.ytm_percent / 100.0,
                                7_500_000)
    assert repriced == pytest.approx(analytics.present_value, rel=1e-10)


# --- golden: duration and convexity ------------------------------------------


def test_macaulay_duration_matches_the_closed_form_for_a_level_coupon_bond():
    """The algebraic solution, written out rather than trusted.

        D (periods) = (1+i)/i  -  [(1+i) + n(g - i)] / [g((1+i)^n - 1) + i]

    with i the periodic yield, g the periodic coupon rate and n the number of
    periods. Divided by the frequency it is duration in years.
    """
    coupon, ytm, years = 4.0, 0.04, 10
    macaulay, modified, _ = yield_based_measures(
        par_bond(coupon), VALUATION, ytm)

    i, g, n = ytm / 2.0, coupon / 100.0 / 2.0, years * 2
    closed_form_periods = (1 + i) / i - ((1 + i) + n * (g - i)) / (g * ((1 + i) ** n - 1) + i)
    assert macaulay == pytest.approx(closed_form_periods / 2.0, rel=1e-10)
    assert modified == pytest.approx(macaulay / (1 + i), rel=1e-12)


@pytest.mark.parametrize("coupon,ytm,maturity", [
    (4.0, 0.04, dt.date(2036, 8, 15)),
    (2.0, 0.05, dt.date(2046, 8, 15)),
    (6.5, 0.03, dt.date(2031, 8, 15)),
    (0.5, 0.0025, dt.date(2056, 8, 15)),
])
def test_duration_and_convexity_agree_with_finite_differences_of_the_price_function(
    coupon, ytm, maturity,
):
    """An independent numerical route to the same two numbers.

    `yield_based_measures` derives duration and convexity analytically from the
    discounted cash flows. Here they are derived instead by perturbing
    `price_from_yield`, which shares no code with those formulas. Agreement to
    six or seven digits means both are right; agreement to two would mean one of
    them is a rearrangement of the other.
    """
    bond = par_bond(coupon, maturity)
    macaulay, modified, convexity = yield_based_measures(bond, VALUATION, ytm)

    h = 1e-5
    price = price_from_yield(bond, VALUATION, ytm)
    up = price_from_yield(bond, VALUATION, ytm + h)
    down = price_from_yield(bond, VALUATION, ytm - h)

    numeric_modified = (down - up) / (2.0 * price * h)
    numeric_convexity = (up + down - 2.0 * price) / (price * h * h)

    assert modified == pytest.approx(numeric_modified, rel=1e-6)
    assert convexity == pytest.approx(numeric_convexity, rel=1e-4)
    assert macaulay > modified > 0


def test_effective_duration_from_the_curve_is_close_to_but_not_identical_to_modified():
    """Two different measures, and the difference is information, not error.

    Modified duration comes from the bond's own yield; effective duration comes
    from shifting the whole par curve and repricing. On a sloped curve they
    differ, and an engine reporting them as equal has silently used one for both.
    """
    bond = par_bond(4.25, dt.date(2046, 8, 15))
    analytics = analyse_bond(bond, VALUATION, sloped_par())
    assert analytics.effective_duration_years == pytest.approx(
        analytics.modified_duration_years, rel=0.05)
    assert analytics.effective_duration_years != analytics.modified_duration_years


def test_dollar_duration_and_analytic_dv01_are_consistent():
    analytics = analyse_bond(par_bond(4.0), VALUATION, flat_par(4.0),
                             face_notional=1_000_000)
    assert analytics.dollar_duration == pytest.approx(
        analytics.modified_duration_years * analytics.present_value, rel=1e-12)
    assert analytics.analytic_dv01 == pytest.approx(
        analytics.dollar_duration * 1e-4, rel=1e-12)


def test_current_yield_is_the_coupon_over_the_clean_price():
    bond = par_bond(6.0, dt.date(2036, 8, 15))
    analytics = analyse_bond(bond, VALUATION, flat_par(4.0))
    assert analytics.current_yield_percent == pytest.approx(
        6.0 / analytics.clean_price_per_100 * 100.0, rel=1e-12)


# --- the approximations, and why full revaluation exists ---------------------


@pytest.mark.parametrize("shock_bp", [25.0, 100.0, 300.0])
def test_convexity_correction_improves_the_duration_approximation(shock_bp):
    bond = par_bond(4.25, dt.date(2056, 8, 15))
    analytics = analyse_bond(bond, VALUATION, sloped_par(), face_notional=3_000_000)
    result = approximate_price_change(analytics, bond, VALUATION, sloped_par(), shock_bp)
    assert abs(result.duration_convexity_error) < abs(result.duration_only_error)


def test_the_duration_only_error_grows_faster_than_linearly_with_the_shock():
    """Which is the whole argument for revaluing rather than approximating."""
    bond = par_bond(4.25, dt.date(2056, 8, 15))
    analytics = analyse_bond(bond, VALUATION, sloped_par(), face_notional=3_000_000)
    small = abs(approximate_price_change(
        analytics, bond, VALUATION, sloped_par(), 50.0).duration_only_error)
    large = abs(approximate_price_change(
        analytics, bond, VALUATION, sloped_par(), 200.0).duration_only_error)
    assert large > small * 4 * 0.9      # roughly quadratic in the shock


# --- monotonicity properties -------------------------------------------------


def test_higher_yields_lower_the_price_of_a_conventional_long_bond():
    bond = par_bond(4.0)
    prices = [price_from_yield(bond, VALUATION, y)
              for y in (0.01, 0.02, 0.04, 0.06, 0.10)]
    assert prices == sorted(prices, reverse=True)


def test_longer_maturity_increases_duration_at_a_fixed_coupon():
    durations = [
        analyse_bond(par_bond(4.0, m), VALUATION, flat_par(4.0)).modified_duration_years
        for m in (dt.date(2028, 8, 15), dt.date(2031, 8, 15),
                  dt.date(2036, 8, 15), dt.date(2056, 8, 15))
    ]
    assert durations == sorted(durations)


def test_higher_coupon_reduces_duration_at_a_fixed_maturity():
    durations = [
        analyse_bond(par_bond(c), VALUATION, flat_par(4.0)).modified_duration_years
        for c in (0.5, 2.0, 4.0, 8.0)
    ]
    assert durations == sorted(durations, reverse=True)


# --- edge and boundary cases -------------------------------------------------


def test_a_matured_bond_is_refused_rather_than_reported_as_zero():
    """Yield, duration and convexity are undefined for it. They are not zero."""
    bond = FixedRateBond("OLD", 1000.0, 5.0, dt.date(2020, 1, 1), dt.date(2010, 1, 1))
    with pytest.raises(EngineError) as excinfo:
        analyse_bond(bond, VALUATION, flat_par(4.0))
    assert excinfo.value.code == "NO_REMAINING_CASH_FLOWS"


def test_a_bond_maturing_tomorrow_still_prices_and_yields():
    bond = FixedRateBond("NEAR", 1000.0, 5.0, dt.date(2026, 8, 16), dt.date(2016, 8, 16))
    analytics = analyse_bond(bond, VALUATION, flat_par(4.0))
    assert analytics.cash_flow_count == 1
    assert analytics.modified_duration_years < 0.02
    assert analytics.ytm_converged


@pytest.mark.parametrize("rate", [0.25, 1.0, 8.0, 15.0])
def test_analytics_hold_across_a_wide_rate_environment(rate):
    analytics = analyse_bond(par_bond(4.0), VALUATION, flat_par(rate))
    assert analytics.ytm_converged
    assert analytics.ytm_percent == pytest.approx(rate, abs=1e-8)
    assert analytics.convexity > 0


def test_near_the_zero_bound_the_default_central_difference_is_refused_by_name():
    """A limitation stated, not a crash propagated.

    At a 10bp curve a 25bp down-shift lands below zero, where this bootstrap's
    no-negative-forward guard will not build. The engine says so and names the
    fix rather than surfacing a raw CurveError from three layers down.
    """
    with pytest.raises(EngineError) as excinfo:
        analyse_bond(par_bond(4.0), VALUATION, flat_par(0.10))
    assert excinfo.value.code == "INVALID_CURVE"
    assert "central difference" in excinfo.value.plain_message
    assert "effective_bump_bp" in (excinfo.value.details or {})


def test_a_smaller_bump_recovers_effective_measures_at_the_zero_bound():
    analytics = analyse_bond(par_bond(4.0), VALUATION, flat_par(0.10),
                             effective_bump_bp=5.0)
    assert analytics.ytm_percent == pytest.approx(0.10, abs=1e-8)
    assert analytics.effective_duration_years > 0
    assert analytics.effective_convexity > 0


def test_negative_par_curves_are_refused_by_this_bootstrap_rather_than_approximated():
    """A documented scope limit, asserted so it cannot become a silent one.

    A genuinely negative par curve implies discount factors above one that rise
    with maturity. That is correct economics in a negative-rate regime and it is
    indistinguishable, to this bootstrap's guard, from an arbitrage-inconsistent
    input - so the guard refuses. The engine does not pretend otherwise, and it
    does not quietly price the curve anyway.
    """
    from mcp_servers.risk.curves import CurveError
    with pytest.raises(CurveError, match="negative forward"):
        build_discount_curve(flat_par(-0.25))


def test_leap_day_and_month_end_schedules_are_handled():
    bond = FixedRateBond("EOM", 100.0, 3.0, dt.date(2032, 2, 29), dt.date(2024, 2, 29))
    analytics = analyse_bond(bond, dt.date(2028, 2, 29), flat_par(4.0))
    assert analytics.cash_flow_count == 8
    assert analytics.clean_price_per_100 + analytics.accrued_per_100 == pytest.approx(
        analytics.dirty_price_per_100, abs=1e-11)

    august_end = FixedRateBond("AUG31", 100.0, 3.0, dt.date(2033, 8, 31),
                               dt.date(2023, 8, 31))
    assert analyse_bond(august_end, dt.date(2027, 3, 31), flat_par(4.0)).ytm_converged


def test_an_unreachable_yield_is_reported_rather_than_clamped_to_the_bound():
    bond = par_bond(4.0)
    with pytest.raises(EngineError) as excinfo:
        yield_to_maturity(bond, VALUATION, 100.0, low=0.10, high=0.12)
    assert excinfo.value.code == "SOLVER_DID_NOT_CONVERGE"
    assert "reprices" in excinfo.value.plain_message


def test_a_non_positive_price_has_no_yield():
    with pytest.raises(EngineError) as excinfo:
        yield_to_maturity(par_bond(4.0), VALUATION, -5.0)
    assert excinfo.value.code == "SOLVER_DID_NOT_CONVERGE"


def test_portfolio_rollup_weights_duration_by_present_value():
    analytics = [analyse_bond(p.bond, VALUATION, sloped_par(), p.face_notional)
                 for p in demo_positions()]
    rollup = portfolio_rollup(analytics)
    total = sum(a.present_value for a in analytics)
    expected = sum(a.modified_duration_years * a.present_value
                   for a in analytics) / total
    assert rollup["weighted_modified_duration_years"] == pytest.approx(expected, rel=1e-12)
    assert rollup["total_present_value"] == pytest.approx(total, rel=1e-12)


# --- curve analytics ---------------------------------------------------------


def test_flat_par_curve_has_a_flat_semiannual_zero_curve_at_the_par_rate():
    """True by definition: D_n = 1/(1+c/2)^n means the semiannual zero rate is c."""
    curve = build_discount_curve(flat_par(4.0))
    for tenor in (0.5, 1.0, 2.0, 5.0, 10.0, 30.0):
        assert zero_rate_semiannual(curve, tenor) == pytest.approx(4.0, rel=1e-10)


def test_flat_curve_forwards_equal_the_par_rate():
    curve = build_discount_curve(flat_par(4.0))
    forward = implied_forward(curve, 5.0, 10.0)
    assert forward.forward_semiannual_percent == pytest.approx(4.0, rel=1e-10)
    assert forward.forward_continuous_percent == pytest.approx(
        2.0 * math.log(1.02) * 100.0, rel=1e-10)


def test_zero_rate_exceeds_the_par_yield_on_an_upward_sloping_curve():
    curve = build_discount_curve(sloped_par())
    assert zero_rate_semiannual(curve, 10.0) > sloped_par().par_rate_at(10.0)


def test_discount_factors_fall_monotonically_with_maturity():
    curve = build_discount_curve(sloped_par())
    factors = [curve.discount_factor(t) for t in (0.5, 1, 2, 5, 10, 20, 30)]
    assert factors == sorted(factors, reverse=True)
    assert all(0 < f <= 1 for f in factors)


def test_spread_convention_is_long_tenor_minus_short_tenor():
    par = sloped_par()
    assert spread_bp(par, 2.0, 10.0) == pytest.approx((4.6 - 3.5) * 100.0, rel=1e-12)
    assert spread_bp(par, 5.0, 30.0) == pytest.approx((5.1 - 4.0) * 100.0, rel=1e-12)
    assert spread_bp(par, 10.0, 2.0) == pytest.approx(-spread_bp(par, 2.0, 10.0))


def test_a_flat_curve_has_zero_slope_and_zero_butterfly():
    par = flat_par(4.0)
    for name, (short, long) in NAMED_SPREADS.items():
        assert spread_bp(par, short, long) == pytest.approx(0.0, abs=1e-12), name
    for name, (short, belly, long) in NAMED_BUTTERFLIES.items():
        assert butterfly_bp(par, short, belly, long) == pytest.approx(0.0, abs=1e-12), name


def test_butterfly_convention_is_two_belly_minus_the_wings():
    par = sloped_par()
    expected = (2 * 4.6 - 3.5 - 5.1) * 100.0
    assert butterfly_bp(par, 2.0, 10.0, 30.0) == pytest.approx(expected, rel=1e-12)
    assert expected == pytest.approx(60.0, rel=1e-12)


def test_inversion_is_detected_and_the_deepest_segment_named():
    diagnosis = diagnose_inversion(inverted_par())
    assert diagnosis.is_inverted_2s10s
    assert diagnosis.inverted_segment_count > 0
    assert diagnosis.deepest_inversion_bp < 0
    assert diagnosis.deepest_inversion_segment == (3.0, 5.0)


def test_an_upward_sloping_curve_reports_no_inversion():
    diagnosis = diagnose_inversion(sloped_par())
    assert not diagnosis.is_inverted_2s10s
    assert diagnosis.inverted_segment_count == 0
    assert diagnosis.first_inverted_segment is None


def test_interpolation_between_nodes_is_linear_in_par_yield():
    par = sloped_par()
    midpoint = par.par_rate_at(4.0)          # between 3y (3.7) and 5y (4.0)
    assert midpoint == pytest.approx(3.7 + (4.0 - 3.7) * (4.0 - 3.0) / (5.0 - 3.0),
                                     rel=1e-12)


def test_extrapolation_is_refused_by_default_and_reported_when_permitted():
    with pytest.raises(EngineError) as excinfo:
        analyse_curve(sloped_par(), tenors_years=[40.0])
    assert excinfo.value.code == "MISSING_CURVE_TENOR"

    permitted = analyse_curve(sloped_par(), tenors_years=[40.0],
                              allow_extrapolation=True)
    assert permitted.tenor_points[0].is_extrapolated
    assert permitted.warnings and "outside" in permitted.warnings[0]


def test_a_backwards_forward_interval_is_refused():
    curve = build_discount_curve(sloped_par())
    with pytest.raises(EngineError) as excinfo:
        implied_forward(curve, 10.0, 5.0)
    assert excinfo.value.code == "INVALID_CURVE"


def test_an_unknown_spread_name_is_refused_with_the_valid_ones_listed():
    with pytest.raises(EngineError) as excinfo:
        analyse_curve(sloped_par(), spread_names=["7s13s"])
    assert "unknown spread" in excinfo.value.plain_message


def test_curve_change_is_measured_only_between_shared_nodes():
    before = sloped_par()
    after = before.shifted(37.5)
    changes = curve_change_bp(before, after)
    assert all(v == pytest.approx(37.5, rel=1e-10) for v in changes.values())
    assert set(changes) == set(before.tenors_years)


def test_measuring_a_change_at_a_non_node_tenor_is_refused():
    with pytest.raises(EngineError) as excinfo:
        curve_change_bp(sloped_par(), sloped_par().shifted(10.0), tenors_years=[12.5])
    assert excinfo.value.code == "MISSING_CURVE_TENOR"
    assert "not nodes on both" in excinfo.value.plain_message


def test_duplicate_tenor_nodes_are_still_refused_at_the_curve_boundary():
    with pytest.raises(Exception, match="duplicate tenor"):
        ParCurve((1.0, 20.0, 20.0, 30.0), (3.0, 4.0, 4.1, 4.2))
