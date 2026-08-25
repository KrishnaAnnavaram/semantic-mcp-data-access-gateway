"""Sensitivity tests: signs, convergence, reconciliation and scaling.

The reconciliation tests are the point of this file. A DV01 that looks
reasonable is nearly impossible to falsify by inspection - it has the right
order of magnitude for almost any error short of a sign flip. What *can* be
falsified is whether the pieces agree with each other:

* position DV01s must sum to the portfolio DV01 **exactly**, because both come
  from one revaluation pass;
* key-rate DV01s must sum to the parallel DV01 **approximately**, and the gap
  must stay small - it is the non-linearity of the bootstrap, and a sudden jump
  in it means something else changed;
* doubling every notional must double the DV01 **exactly**;
* the answer must not depend on the order the positions arrive in.

Each of those has exactly one right answer and no plausible wrong one.
"""

from __future__ import annotations

import datetime as dt

import pytest
from mcp_servers.risk.contributions import bucket_for
from mcp_servers.risk.errors import EngineError
from mcp_servers.risk.pricing import FixedRateBond, Position
from mcp_servers.risk.revaluation import (
    compile_book,
    key_rate_exposures,
    run_scenarios,
)
from mcp_servers.risk.risk import compute_dv01, compute_key_rate_dv01
from mcp_servers.risk.sensitivities import (
    compute_rate_sensitivities,
    portfolio_effective_measures,
    scale_check,
)
from risk_fixtures import (
    VALUATION,
    demo_book,
    demo_positions,
    flat_par,
    single_bond,
    sloped_par,
)


def test_dv01_is_positive_for_a_conventional_long_book():
    result = compute_rate_sensitivities(demo_book(), sloped_par())
    assert result.dv01 > 0
    assert all(p.dv01 > 0 for p in result.positions)


def test_dv01_is_negative_for_a_short_position():
    """The sign convention has to survive a negative notional, not just look right."""
    short = [Position(FixedRateBond("SHORT", 1000.0, 4.0, dt.date(2036, 8, 15),
                                    VALUATION), -5_000_000)]
    result = compute_rate_sensitivities(compile_book(short, VALUATION), sloped_par())
    assert result.dv01 < 0


@pytest.mark.parametrize("bump_bp", [1.0, 0.5, 0.1])
def test_dv01_converges_to_the_derivative_as_the_bump_shrinks(bump_bp):
    """Per basis point, the figure must barely move as the bump shrinks.

    `compute_dv01` reports the value change for the bump it was given, so the
    comparison is made per basis point. What remains after that normalisation is
    the bond's convexity biasing a one-sided difference, and it must shrink with
    the bump rather than persisting - which is what distinguishes a derivative
    from an arbitrary finite difference.
    """
    book, par = demo_book(), sloped_par()
    reference = compute_rate_sensitivities(book, par, bump_bp=0.01).dv01 / 0.01
    measured = compute_rate_sensitivities(book, par, bump_bp=bump_bp).dv01 / bump_bp
    assert measured == pytest.approx(reference, rel=1e-3)
    # One-sided and downward, always: the book is positively convex.
    assert measured < reference
    error = abs(measured - reference)
    smaller = abs(compute_rate_sensitivities(
        book, par, bump_bp=bump_bp / 10.0).dv01 / (bump_bp / 10.0) - reference)
    assert smaller < error, "the error must fall with the bump, not plateau"


def test_position_dv01s_sum_to_the_portfolio_dv01_exactly():
    result = compute_rate_sensitivities(demo_book(), sloped_par())
    assert sum(p.dv01 for p in result.positions) == pytest.approx(
        result.dv01, rel=1e-12)
    assert abs(result.reconciliation.position_difference) < 1e-6


def test_key_rate_dv01s_sum_to_approximately_the_parallel_dv01():
    """Approximately, and the engine must say by how much rather than hide it."""
    result = compute_rate_sensitivities(demo_book(), sloped_par())
    assert result.reconciliation.sum_of_key_rate_dv01 == pytest.approx(
        result.dv01, rel=0.01)
    assert abs(result.reconciliation.key_rate_difference_bp_of_parallel) < 50.0
    assert result.reconciliation.key_rate_difference != 0.0, (
        "an exact match would mean the key-rate and parallel bumps were the same "
        "perturbation, which they are not")


def test_key_rate_dv01s_match_the_original_risk_module():
    """The new aggregate must not disagree with the tool it aggregates."""
    book, positions, par = demo_book(), demo_positions(), sloped_par()
    aggregate = compute_rate_sensitivities(book, par)
    original = compute_key_rate_dv01(positions, VALUATION, par)
    by_tenor = dict(original.key_rate_dv01)
    for row in aggregate.key_rates:
        assert row.key_rate_dv01 == pytest.approx(by_tenor[row.tenor_years], rel=1e-12)
    assert aggregate.dv01 == pytest.approx(
        compute_dv01(positions, VALUATION, par).dv01, rel=1e-12)


def test_per_position_key_rate_dv01s_sum_to_the_tenor_total():
    result = compute_rate_sensitivities(demo_book(), sloped_par())
    for row in result.key_rates:
        # Absolute rather than relative: a node the book barely touches carries a
        # key-rate DV01 of well under a dollar, computed as the difference of two
        # thirty-million-dollar valuations. Relative tolerance on that is a
        # tolerance on floating-point cancellation, not on the calculation.
        assert sum(v for _, v in row.per_position) == pytest.approx(
            row.key_rate_dv01, rel=1e-9, abs=1e-6)


def test_doubling_every_notional_doubles_the_dv01_exactly():
    result = scale_check(demo_book(), sloped_par(), 2.0)
    assert result["scaled_dv01"] == pytest.approx(2.0 * result["dv01"], rel=1e-12)


def test_sensitivities_do_not_depend_on_position_order():
    par = sloped_par()
    forward = compute_rate_sensitivities(demo_book(), par)
    reversed_book = compile_book(list(reversed(demo_positions())), VALUATION)
    backward = compute_rate_sensitivities(reversed_book, par)
    assert backward.dv01 == pytest.approx(forward.dv01, rel=1e-12)
    assert backward.base_value == pytest.approx(forward.base_value, rel=1e-12)
    assert {p.instrument_id: round(p.dv01, 6) for p in backward.positions} == \
           {p.instrument_id: round(p.dv01, 6) for p in forward.positions}


def test_effective_duration_reconciles_with_dv01():
    """D_eff x PV / 10,000 should land within a percent of the DV01.

    Not exactly: the DV01 is a one-sided 1bp bump and the effective duration a
    central 25bp difference, so convexity separates them. A large gap would mean
    one of the two is measuring something else.
    """
    result = compute_rate_sensitivities(demo_book(), sloped_par())
    implied = result.effective_duration_years * result.base_value / 10_000.0
    assert implied == pytest.approx(result.dv01, rel=0.01)


def test_effective_convexity_is_positive_for_a_long_bond_book():
    _, convexity, _ = portfolio_effective_measures(demo_book(), sloped_par())
    assert convexity > 0


def test_dollar_duration_is_dv01_times_ten_thousand():
    result = compute_rate_sensitivities(demo_book(), sloped_par())
    assert result.dollar_duration == pytest.approx(result.dv01 * 10_000.0, rel=1e-12)


def test_risk_shares_sum_to_one_hundred_percent():
    result = compute_rate_sensitivities(demo_book(), sloped_par())
    assert sum(p.dv01_share_percent for p in result.positions) == pytest.approx(
        100.0, rel=1e-9)
    assert sum(k.share_percent for k in result.key_rates) == pytest.approx(
        100.0, rel=1e-9)


def test_maturity_buckets_partition_the_key_rate_exposure():
    result = compute_rate_sensitivities(demo_book(), sloped_par())
    assert sum(b.key_rate_dv01 for b in result.buckets) == pytest.approx(
        result.reconciliation.sum_of_key_rate_dv01, rel=1e-10)


@pytest.mark.parametrize("tenor,expected", [
    (0.25, "0-2y"), (2.0, "0-2y"), (2.5, "2-5y"), (5.0, "2-5y"),
    (7.0, "5-10y"), (10.0, "5-10y"), (15.0, "10-20y"), (20.0, "10-20y"),
    (30.0, "20y+"),
])
def test_maturity_bucket_boundaries_are_closed_at_the_top(tenor, expected):
    """A 10-year point belongs in the bucket labelled 5-10y, not 10-20y."""
    assert bucket_for(tenor) == expected


def test_a_key_tenor_that_is_not_a_curve_node_is_refused():
    with pytest.raises(EngineError) as excinfo:
        compute_rate_sensitivities(demo_book(), sloped_par(),
                                   key_tenors_years=[12.5])
    assert excinfo.value.code == "MISSING_CURVE_TENOR"


def test_a_zero_bump_is_refused():
    with pytest.raises(EngineError) as excinfo:
        compute_rate_sensitivities(demo_book(), sloped_par(), bump_bp=0.0)
    assert excinfo.value.code == "INVALID_STRESS_VECTOR"


def test_a_longer_bond_carries_more_dv01_per_million_than_a_shorter_one():
    par = sloped_par()
    result = compute_rate_sensitivities(demo_book(), par)
    per_million = [p.dv01_per_million_notional for p in result.positions]
    assert per_million == sorted(per_million), (
        "the demo book is ordered 2y to 30y, so DV01 per million must increase")


def test_key_rate_exposure_is_concentrated_at_the_bond_s_own_maturity():
    """A single 10-year bond's key-rate risk must sit at the 10-year node."""
    book = compile_book(single_bond(4.0, dt.date(2036, 8, 15)), VALUATION)
    _, totals, _ = key_rate_exposures(book, sloped_par(), 1.0)
    largest = max(totals, key=lambda x: abs(x[1]))
    assert largest[0] == 10.0


def test_the_scenario_engine_reproduces_a_single_stress_it_is_given():
    """`run_scenarios` and a direct revaluation must not diverge."""
    book, par = demo_book(), sloped_par()
    shocks = {t: 100.0 for t in par.tenors_years}
    scenarios = run_scenarios(book, par, [shocks])
    direct = book.value_under(par.shocked(shocks)) - book.value_under(par)
    assert scenarios.pnl[0] == pytest.approx(direct, rel=1e-12)
    assert sum(scenarios.pnl_per_position[0]) == pytest.approx(
        scenarios.pnl[0], rel=1e-12)


def test_a_flat_curve_puts_almost_all_key_rate_risk_at_the_node_maturities():
    """Sanity that single-node bumps are not leaking across the curve."""
    book = compile_book(single_bond(4.0, dt.date(2031, 8, 15)), VALUATION)
    _, totals, _ = key_rate_exposures(book, flat_par(4.0), 1.0)
    by_tenor = dict(totals)
    assert by_tenor[5.0] == max(by_tenor.values())
    assert abs(by_tenor[30.0]) < abs(by_tenor[5.0]) * 0.01
