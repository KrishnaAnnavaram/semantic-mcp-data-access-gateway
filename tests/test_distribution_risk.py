"""VaR, Expected Shortfall, simulation and backtesting.

Where a golden value could be looked up, it is: the Kupiec likelihood ratio is
written out algebraically in the test, and the normal ES-to-sigma ratio is
computed from the standard normal rather than from this engine.

Where it could not be, an independent route is built inside the test. The
historical VaR check constructs a history whose implied daily changes are known
exactly by construction, reprices the book under each of them directly, and
requires the tool's answer to equal the k-th worst of those - which tests the
scenario construction, the revaluation and the quantile convention at once
without trusting any of them.
"""

from __future__ import annotations

import math

import pytest
from mcp_servers.risk.backtesting import (
    backtest_var,
    basel_traffic_light,
    christoffersen_independence,
    conditional_coverage,
    kupiec_unconditional_coverage,
)
from mcp_servers.risk.contributions import measure_contributions, run_shock
from mcp_servers.risk.errors import EngineError
from mcp_servers.risk.linalg import quadratic_form
from mcp_servers.risk.monte_carlo import (
    compute_monte_carlo_risk,
    correlation_stress_covariance,
    run_extreme_tail_simulation,
    standard_normals,
)
from mcp_servers.risk.parametric import (
    STANDARD_NORMAL,
    compute_parametric_risk,
    normal_expected_shortfall_multiplier,
    parametric_from_covariance,
)
from mcp_servers.risk.revaluation import key_rate_exposures, run_scenarios
from mcp_servers.risk.risk import compute_historical_risk, nearest_rank_quantile
from mcp_servers.risk.stress_scenarios import custom_shock
from mcp_servers.risk.volatility import (
    compute_rate_volatility,
    covariance_matrix,
    observed_changes_bp,
    scale_covariance,
)
from risk_fixtures import (
    VALUATION,
    demo_book,
    demo_positions,
    sloped_par,
    synthetic_dates,
    synthetic_history,
)

HISTORY_TENORS = (2.0, 5.0, 10.0, 30.0)


def history_from_changes(changes_bp: list[list[float]],
                         start: float = 4.0) -> list[list[float]]:
    """Build a rate history whose one-day changes are exactly `changes_bp`."""
    rows = [[start for _ in changes_bp[0]]]
    for change in changes_bp:
        rows.append([previous + delta / 100.0
                     for previous, delta in zip(rows[-1], change)])
    return rows


# --- historical VaR and ES, checked against a hand-built scenario set --------


def test_historical_var_is_the_kth_worst_of_scenarios_priced_independently():
    """The whole pipeline, checked without trusting any part of it.

    The history is constructed so that its implied daily changes are a known
    list. Each of those changes is then applied to today's curve directly, in
    this test, and the book repriced. The tool's VaR must equal the loss of the
    ceil(alpha * N)-th worst of those - which is the nearest-rank convention
    applied to a distribution the test built itself.
    """
    book, par = demo_book(), sloped_par()
    changes = [[float(i) - 25.0, float(i) - 20.0, float(i) - 15.0, float(i) - 10.0]
               for i in range(50)]
    rows = history_from_changes(changes)

    result = compute_historical_risk(
        demo_positions(), VALUATION, par, list(HISTORY_TENORS), rows,
        confidence_level=0.95, horizon_days=1)

    independent = []
    for change in changes:
        vector = custom_shock(par, dict(zip(HISTORY_TENORS, change)),
                              allow_unknown_tenors=True)
        independent.append(run_shock(book, par, vector).pnl)

    losses = sorted(-p for p in independent)
    expected_var, index = nearest_rank_quantile(losses, 0.95)
    expected_es = sum(loss for loss in losses if loss >= expected_var) / \
        len([loss for loss in losses if loss >= expected_var])

    assert result.scenarios_used == len(changes)
    assert result.var == pytest.approx(expected_var, rel=1e-9)
    assert result.expected_shortfall == pytest.approx(expected_es, rel=1e-9)
    assert index == math.ceil(0.95 * len(changes)) - 1


def test_expected_shortfall_is_never_below_var_and_worst_loss_never_below_es():
    tenors, rows = synthetic_history(260)
    result = compute_historical_risk(demo_positions(), VALUATION, sloped_par(),
                                     tenors, rows, 0.99, 1)
    assert result.expected_shortfall >= result.var
    assert result.worst_loss >= result.expected_shortfall


@pytest.mark.parametrize("confidence", [0.95, 0.975, 0.99])
def test_a_higher_confidence_level_never_lowers_the_var(confidence):
    tenors, rows = synthetic_history(300)
    levels = sorted({0.90, confidence})
    figures = [compute_historical_risk(demo_positions(), VALUATION, sloped_par(),
                                       tenors, rows, level, 1).var
               for level in levels]
    assert figures == sorted(figures)


def test_a_ten_day_horizon_uses_observed_moves_not_sqrt_ten_scaling():
    """The rule the whole historical path is built around."""
    tenors, rows = synthetic_history(300)
    one = compute_historical_risk(demo_positions(), VALUATION, sloped_par(),
                                  tenors, rows, 0.99, 1)
    ten = compute_historical_risk(demo_positions(), VALUATION, sloped_par(),
                                  tenors, rows, 0.99, 10)
    assert ten.scenarios_used == len(rows) - 10
    assert ten.var != pytest.approx(one.var * math.sqrt(10), rel=1e-6)


def test_var_scales_with_portfolio_size():
    tenors, rows = synthetic_history(260)
    single = compute_historical_risk(demo_positions(), VALUATION, sloped_par(),
                                     tenors, rows, 0.99, 1)
    doubled = [type(p)(p.bond, p.face_notional * 2) for p in demo_positions()]
    double = compute_historical_risk(doubled, VALUATION, sloped_par(),
                                     tenors, rows, 0.99, 1)
    assert double.var == pytest.approx(single.var * 2.0, rel=1e-9)


def test_scenario_order_does_not_change_the_var():
    tenors, rows = synthetic_history(200)
    changes = observed_changes_bp(rows, 1)
    book, par = demo_book(), sloped_par()
    vectors = [dict(zip(HISTORY_TENORS, change)) for change in changes]
    forward = run_scenarios(book, par, vectors)
    backward = run_scenarios(book, par, list(reversed(vectors)))
    assert nearest_rank_quantile(forward.losses_sorted(), 0.99)[0] == pytest.approx(
        nearest_rank_quantile(backward.losses_sorted(), 0.99)[0], rel=1e-12)


# --- risk contributions ------------------------------------------------------


def test_component_var_sums_to_the_portfolio_var_exactly():
    """A theorem under nearest rank, not a normalisation applied afterwards."""
    tenors, rows = synthetic_history(260)
    changes = observed_changes_bp(rows, 1)
    scenarios = run_scenarios(demo_book(), sloped_par(),
                              [dict(zip(HISTORY_TENORS, c)) for c in changes])
    result = measure_contributions(scenarios, 0.99, "var")
    assert sum(p.component for p in result.positions) == pytest.approx(
        result.portfolio_measure, rel=1e-9)
    assert abs(result.reconciliation_difference) < 1e-6


def test_component_expected_shortfall_sums_to_the_portfolio_es_exactly():
    tenors, rows = synthetic_history(260)
    changes = observed_changes_bp(rows, 1)
    scenarios = run_scenarios(demo_book(), sloped_par(),
                              [dict(zip(HISTORY_TENORS, c)) for c in changes])
    result = measure_contributions(scenarios, 0.99, "es")
    assert sum(p.component for p in result.positions) == pytest.approx(
        result.portfolio_measure, rel=1e-9)
    assert result.tail_scenario_count >= 1


def test_incremental_var_does_not_pretend_to_sum_to_the_portfolio_var():
    tenors, rows = synthetic_history(260)
    changes = observed_changes_bp(rows, 1)
    scenarios = run_scenarios(demo_book(), sloped_par(),
                              [dict(zip(HISTORY_TENORS, c)) for c in changes])
    result = measure_contributions(scenarios, 0.99, "var")
    incrementals = [p.incremental for p in result.positions]
    assert all(v is not None for v in incrementals)
    assert sum(incrementals) != pytest.approx(result.portfolio_measure, rel=0.01)


def test_an_invalid_confidence_level_is_refused():
    tenors, rows = synthetic_history(100)
    changes = observed_changes_bp(rows, 1)
    scenarios = run_scenarios(demo_book(), sloped_par(),
                              [dict(zip(HISTORY_TENORS, c)) for c in changes])
    with pytest.raises(EngineError) as excinfo:
        measure_contributions(scenarios, 1.5, "var")
    assert excinfo.value.code == "INVALID_CONFIDENCE_LEVEL"


# --- volatility --------------------------------------------------------------


def test_tenor_volatility_matches_an_independently_written_sample_stdev():
    tenors, rows = synthetic_history(250)
    result = compute_rate_volatility(tenors, rows, 1)
    changes = observed_changes_bp(rows, 1)
    for j, entry in enumerate(result.per_tenor):
        series = [row[j] for row in changes]
        mean = sum(series) / len(series)
        expected = math.sqrt(sum((v - mean) ** 2 for v in series) / (len(series) - 1))
        assert entry.stdev_bp == pytest.approx(expected, rel=1e-12)


def test_annualisation_uses_252_trading_days():
    tenors, rows = synthetic_history(250)
    result = compute_rate_volatility(tenors, rows, 1)
    for entry in result.per_tenor:
        assert entry.annualised_stdev_bp == pytest.approx(
            entry.stdev_bp * math.sqrt(252), rel=1e-12)


def test_a_constant_history_has_zero_volatility_and_a_singular_covariance():
    tenors = [2.0, 10.0]
    rows = [[4.0, 4.5] for _ in range(60)]
    result = compute_rate_volatility(tenors, rows, 1)
    assert all(t.stdev_bp == 0.0 for t in result.per_tenor)
    assert result.covariance_bp2 == [[0.0, 0.0], [0.0, 0.0]]


def test_a_volatility_multiplier_scales_sigma_not_the_covariance():
    """2x volatility means 4x covariance. Getting this backwards understates VaR."""
    base = [[4.0, 1.0], [1.0, 9.0]]
    scaled = scale_covariance(base, 2.0)
    assert scaled == [[16.0, 4.0], [4.0, 36.0]]
    assert math.sqrt(scaled[0][0]) == pytest.approx(2.0 * math.sqrt(base[0][0]))


def test_the_high_volatility_window_is_found_where_it_was_planted():
    calm = [[0.0, 0.0] for _ in range(100)]
    stormy = [[10.0 * (1 if i % 2 else -1), 8.0 * (1 if i % 2 else -1)]
              for i in range(40)]
    changes = calm[:50] + stormy + calm[50:]
    from mcp_servers.risk.volatility import find_high_volatility_window
    regime = find_high_volatility_window(changes, window_days=40)
    assert 45 <= regime.start_index <= 55
    assert regime.ratio_to_full_sample > 1.0


# --- parametric --------------------------------------------------------------


def test_parametric_var_matches_the_closed_form_on_a_hand_built_covariance():
    """Fully analytic: sigma^2 = e' C e, VaR = z sigma, ES = phi(z)/(1-a) sigma."""
    exposure = [-1000.0, -2500.0]
    covariance = [[4.0, 1.2], [1.2, 9.0]]
    sigma, var, es = parametric_from_covariance(exposure, covariance, 0.99, 1)

    expected_variance = (exposure[0] ** 2 * 4.0 + exposure[1] ** 2 * 9.0
                         + 2 * exposure[0] * exposure[1] * 1.2)
    z = STANDARD_NORMAL.inv_cdf(0.99)
    assert sigma == pytest.approx(math.sqrt(expected_variance), rel=1e-12)
    assert var == pytest.approx(z * sigma, rel=1e-12)
    assert es == pytest.approx(
        STANDARD_NORMAL.pdf(z) / 0.01 * sigma, rel=1e-12)


@pytest.mark.parametrize("confidence,expected_ratio", [
    (0.95, 2.062713), (0.975, 2.337803), (0.99, 2.665214),
])
def test_the_normal_es_multiplier_matches_published_values(confidence, expected_ratio):
    assert normal_expected_shortfall_multiplier(confidence) == pytest.approx(
        expected_ratio, rel=1e-6)


def test_parametric_sigma_uses_the_sample_covariance_of_the_exposure_vector():
    """Recomputed in the test from an independently written covariance loop."""
    tenors, rows = synthetic_history(250)
    book, par = demo_book(), sloped_par()
    result = compute_parametric_risk(book, par, tenors, rows, 0.99, 1)

    changes = observed_changes_bp(rows, 1)
    n = len(changes)
    means = [sum(row[j] for row in changes) / n for j in range(len(tenors))]
    covariance = [[sum((row[i] - means[i]) * (row[j] - means[j]) for row in changes)
                   / (n - 1) for j in range(len(tenors))] for i in range(len(tenors))]
    _, krd, _ = key_rate_exposures(book, par, 1.0)
    by_tenor = dict(krd)
    exposure = [-by_tenor[t] for t in tenors]

    assert result.portfolio_volatility == pytest.approx(
        math.sqrt(quadratic_form(exposure, covariance)), rel=1e-12)


def test_parametric_component_var_reconciles_to_machine_precision():
    tenors, rows = synthetic_history(250)
    result = compute_parametric_risk(demo_book(), sloped_par(), tenors, rows, 0.99, 1)
    assert abs(result.var_reconciliation_difference) < 1e-6
    assert sum(f.component_var for f in result.factors) == pytest.approx(
        result.var, rel=1e-9)


def test_parametric_sqrt_time_scaling_is_exact_and_labelled():
    tenors, rows = synthetic_history(300)
    one = compute_parametric_risk(demo_book(), sloped_par(), tenors, rows,
                                  0.99, 1, "sqrt_time")
    ten = compute_parametric_risk(demo_book(), sloped_par(), tenors, rows,
                                  0.99, 10, "sqrt_time")
    assert ten.var == pytest.approx(one.var * math.sqrt(10), rel=1e-10)
    assert ten.horizon_method == "sqrt_time"


def test_parametric_observed_and_sqrt_time_horizons_disagree():
    """If they agreed there would be no reason to offer both."""
    tenors, rows = synthetic_history(300)
    observed = compute_parametric_risk(demo_book(), sloped_par(), tenors, rows,
                                       0.99, 10, "observed")
    scaled = compute_parametric_risk(demo_book(), sloped_par(), tenors, rows,
                                     0.99, 10, "sqrt_time")
    assert observed.var != pytest.approx(scaled.var, rel=1e-3)


def test_parametric_es_is_always_above_parametric_var():
    tenors, rows = synthetic_history(250)
    result = compute_parametric_risk(demo_book(), sloped_par(), tenors, rows, 0.99, 1)
    assert result.expected_shortfall > result.var


def test_a_history_sharing_no_tenor_with_the_curve_is_refused():
    with pytest.raises(EngineError) as excinfo:
        compute_parametric_risk(demo_book(), sloped_par(), [4.0, 6.0],
                                [[4.0, 4.1]] * 10, 0.99, 1)
    assert excinfo.value.code == "MISSING_REQUIRED_MARKET_DATA"


# --- Monte Carlo -------------------------------------------------------------


def test_box_muller_draws_are_deterministic_and_standard_normal():
    first = standard_normals(20_000, 12345)
    second = standard_normals(20_000, 12345)
    assert first == second
    assert standard_normals(20_000, 999) != first

    mean = sum(first) / len(first)
    variance = sum((x - mean) ** 2 for x in first) / (len(first) - 1)
    assert mean == pytest.approx(0.0, abs=0.03)
    assert variance == pytest.approx(1.0, abs=0.03)


def test_the_same_seed_reproduces_the_same_monte_carlo_result_exactly():
    tenors, rows = synthetic_history(250)
    args = (demo_book(), sloped_par(), tenors, rows, 0.99, 1, 2000, 20260824)
    first = compute_monte_carlo_risk(*args)
    second = compute_monte_carlo_risk(*args)
    assert first.var == second.var
    assert first.expected_shortfall == second.expected_shortfall
    assert first.worst_pnl == second.worst_pnl
    assert first.percentiles_pnl == second.percentiles_pnl


def test_a_different_seed_gives_a_different_monte_carlo_result():
    """A 'deterministic' simulation that ignores its seed is also reproducible."""
    tenors, rows = synthetic_history(250)
    base = compute_monte_carlo_risk(demo_book(), sloped_par(), tenors, rows,
                                    0.99, 1, 2000, 1)
    other = compute_monte_carlo_risk(demo_book(), sloped_par(), tenors, rows,
                                     0.99, 1, 2000, 2)
    assert base.var != other.var


def test_monte_carlo_converges_towards_the_parametric_answer_on_a_linear_book():
    """Same distributional assumption; the gap is convexity plus sampling error."""
    tenors, rows = synthetic_history(250)
    parametric = compute_parametric_risk(demo_book(), sloped_par(), tenors, rows,
                                         0.99, 1)
    simulated = compute_monte_carlo_risk(demo_book(), sloped_par(), tenors, rows,
                                         0.99, 1, 20_000, 4242)
    assert simulated.var == pytest.approx(parametric.var, rel=0.10)


def test_more_paths_reduce_the_gap_to_the_parametric_answer():
    tenors, rows = synthetic_history(250)
    parametric = compute_parametric_risk(demo_book(), sloped_par(), tenors, rows,
                                         0.99, 1).var
    errors = []
    for count in (500, 20_000):
        simulated = compute_monte_carlo_risk(demo_book(), sloped_par(), tenors, rows,
                                             0.99, 1, count, 7).var
        errors.append(abs(simulated - parametric) / parametric)
    assert errors[1] < errors[0]


def test_monte_carlo_expected_shortfall_is_above_its_var():
    tenors, rows = synthetic_history(250)
    result = compute_monte_carlo_risk(demo_book(), sloped_par(), tenors, rows,
                                      0.99, 1, 2000, 11)
    assert result.expected_shortfall >= result.var
    assert result.worst_pnl <= -result.var


def test_an_out_of_range_scenario_count_is_refused():
    tenors, rows = synthetic_history(250)
    for count in (50, 200_000):
        with pytest.raises(EngineError) as excinfo:
            compute_monte_carlo_risk(demo_book(), sloped_par(), tenors, rows,
                                     0.99, 1, count, 1)
        assert excinfo.value.code == "MONTE_CARLO_FAILURE"


@pytest.mark.parametrize("method", [
    "volatility_multiplier", "stressed_covariance", "student_t",
    "empirical_bootstrap",
])
def test_each_extreme_tail_method_has_its_own_version_string(method):
    tenors, rows = synthetic_history(250)
    plain = compute_monte_carlo_risk(demo_book(), sloped_par(), tenors, rows,
                                     0.99, 1, 1000, 5)
    tail = run_extreme_tail_simulation(demo_book(), sloped_par(), tenors, rows,
                                       method, 0.99, 1, 1000, 5)
    assert tail.method != plain.method, (
        "a different model must not share the plain simulation's version string")
    assert tail.distribution != plain.distribution


def test_doubling_volatility_roughly_doubles_the_simulated_var():
    tenors, rows = synthetic_history(250)
    plain = compute_monte_carlo_risk(demo_book(), sloped_par(), tenors, rows,
                                     0.99, 1, 4000, 3)
    doubled = run_extreme_tail_simulation(demo_book(), sloped_par(), tenors, rows,
                                          "volatility_multiplier", 0.99, 1, 4000, 3,
                                          volatility_multiplier=2.0)
    assert doubled.var == pytest.approx(plain.var * 2.0, rel=0.15)


def test_student_t_produces_a_fatter_tail_than_the_normal_case():
    tenors, rows = synthetic_history(250)
    normal = compute_monte_carlo_risk(demo_book(), sloped_par(), tenors, rows,
                                      0.99, 1, 8000, 17)
    fat = run_extreme_tail_simulation(demo_book(), sloped_par(), tenors, rows,
                                      "student_t", 0.99, 1, 8000, 17,
                                      degrees_of_freedom=4)
    assert (fat.expected_shortfall / fat.var) > (normal.expected_shortfall / normal.var)


def test_a_student_t_with_too_few_degrees_of_freedom_is_refused():
    tenors, rows = synthetic_history(250)
    with pytest.raises(EngineError) as excinfo:
        run_extreme_tail_simulation(demo_book(), sloped_par(), tenors, rows,
                                    "student_t", 0.99, 1, 1000, 1,
                                    degrees_of_freedom=2)
    assert excinfo.value.code == "MONTE_CARLO_FAILURE"


def test_perfect_correlation_raises_var_above_the_historical_correlation_case():
    """The diversification assumption, isolated: same volatilities, no offset."""
    tenors, rows = synthetic_history(250)
    changes = observed_changes_bp(rows, 1)
    base = covariance_matrix(changes)
    historical, _, _ = correlation_stress_covariance(base, "historical")
    perfect, _, _ = correlation_stress_covariance(base, "perfect_positive")

    book, par = demo_book(), sloped_par()
    _, krd, _ = key_rate_exposures(book, par, 1.0)
    by_tenor = dict(krd)
    exposure = [-by_tenor[t] for t in tenors]
    _, historical_var, _ = parametric_from_covariance(exposure, historical, 0.99, 1)
    _, perfect_var, _ = parametric_from_covariance(exposure, perfect, 0.99, 1)
    assert perfect_var > historical_var


def test_a_correlation_matrix_that_is_not_psd_is_repaired_and_reported():
    base = [[4.0, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 4.0]]
    invalid = [[1.0, 0.99, 0.99], [0.99, 1.0, -0.99], [0.99, -0.99, 1.0]]
    _, _, diagnostics = correlation_stress_covariance(base, "custom", invalid)
    assert diagnostics["repaired"] == 1.0
    assert diagnostics["smallest_eigenvalue_before"] < 0
    assert diagnostics["smallest_eigenvalue_after"] >= -1e-12


def test_an_unknown_correlation_mode_is_refused():
    with pytest.raises(EngineError) as excinfo:
        correlation_stress_covariance([[1.0]], "wishful_thinking")
    assert excinfo.value.code == "INVALID_COVARIANCE_MATRIX"


# --- backtesting -------------------------------------------------------------


def test_kupiec_matches_the_likelihood_ratio_written_out_algebraically():
    n, x, p = 250, 10, 0.01
    expected = (-2 * ((n - x) * math.log(1 - p) + x * math.log(p))
                + 2 * ((n - x) * math.log(1 - x / n) + x * math.log(x / n)))
    result = kupiec_unconditional_coverage(n, x, 0.99)
    assert result.statistic == pytest.approx(expected, rel=1e-12)
    assert result.rejected_at_5_percent is True


def test_kupiec_with_zero_exceptions_uses_the_limiting_form():
    """0 * log(0) = 0 is the limit of the likelihood term, not a fudge."""
    result = kupiec_unconditional_coverage(250, 0, 0.99)
    assert result.statistic == pytest.approx(-2 * 250 * math.log(0.99), rel=1e-12)
    assert result.computable


def test_kupiec_is_zero_when_the_exception_count_is_exactly_expected():
    assert kupiec_unconditional_coverage(100, 1, 0.99).statistic == pytest.approx(
        0.0, abs=1e-12)
    assert kupiec_unconditional_coverage(100, 1, 0.99).p_value == pytest.approx(1.0)


def test_christoffersen_rejects_clustered_exceptions_and_accepts_spread_ones():
    clustered = [0] * 240 + [1] * 10
    spread = [1 if i % 25 == 0 else 0 for i in range(250)]
    assert christoffersen_independence(clustered).rejected_at_5_percent is True
    assert christoffersen_independence(spread).rejected_at_5_percent is False


def test_christoffersen_is_not_computable_without_any_exception():
    result = christoffersen_independence([0] * 100)
    assert not result.computable
    assert result.p_value is None
    assert "not the same as confirmed" in result.note


def test_conditional_coverage_is_the_sum_of_the_two_statistics():
    kupiec = kupiec_unconditional_coverage(250, 8, 0.99)
    independence = christoffersen_independence(
        [1 if i in (10, 11, 50, 90, 120, 121, 200, 240) else 0 for i in range(250)])
    joint = conditional_coverage(kupiec, independence)
    assert joint.statistic == pytest.approx(kupiec.statistic + independence.statistic)
    assert joint.degrees_of_freedom == 2
    assert joint.p_value == pytest.approx(math.exp(-joint.statistic / 2.0), rel=1e-12)


def test_an_exception_is_a_strictly_greater_loss_not_an_equal_one():
    forecasts = [100_000.0] * 60
    pnl = [0.0] * 60
    pnl[10] = -100_000.0        # exactly at the forecast: not an exception
    pnl[20] = -100_000.01       # a cent over: an exception
    result = backtest_var(forecasts, pnl, 0.99)
    assert result.exceptions == 1
    assert [e.index for e in result.exception_detail] == [20]


def test_exception_dates_and_clustering_are_reported():
    forecasts = [100_000.0] * 250
    pnl = [1000.0] * 250
    for i in (5, 40, 41, 42, 200):
        pnl[i] = -150_000.0
    dates = synthetic_dates(250)
    result = backtest_var(forecasts, pnl, 0.99, "HYPOTHETICAL", dates)
    assert result.exceptions == 5
    assert result.longest_exception_run == 3
    assert result.exception_clusters == 3
    assert [d.isoformat() for d in result.exception_dates] == [
        dates[i].isoformat() for i in (5, 40, 41, 42, 200)]
    assert result.mean_excess_loss == pytest.approx(50_000.0)


@pytest.mark.parametrize("exceptions,zone", [
    (0, "GREEN"), (4, "GREEN"), (5, "AMBER"), (9, "AMBER"), (10, "RED"), (25, "RED"),
])
def test_the_basel_traffic_light_boundaries(exceptions, zone):
    assert basel_traffic_light(250, exceptions, 0.99) == (zone, True)


def test_the_traffic_light_is_withheld_outside_the_conditions_it_was_calibrated_for():
    assert basel_traffic_light(100, 2, 0.99) == (None, False)
    assert basel_traffic_light(250, 2, 0.95) == (None, False)


def test_the_pnl_kind_travels_with_the_result():
    forecasts = [100_000.0] * 60
    for kind in ("ACTUAL", "HYPOTHETICAL", "MODEL_REVALUATION"):
        assert backtest_var(forecasts, [0.0] * 60, 0.99, kind).pnl_kind == kind


def test_too_few_observations_are_refused():
    with pytest.raises(EngineError) as excinfo:
        backtest_var([100_000.0] * 10, [0.0] * 10, 0.99)
    assert excinfo.value.code == "INSUFFICIENT_BACKTEST_DATA"


def test_mismatched_series_lengths_are_refused():
    with pytest.raises(EngineError) as excinfo:
        backtest_var([100_000.0] * 60, [0.0] * 50, 0.99)
    assert excinfo.value.code == "MISSING_PNL_SERIES"


def test_a_negative_var_forecast_is_refused_as_a_sign_convention_error():
    forecasts = [100_000.0] * 60
    forecasts[3] = -1.0
    with pytest.raises(EngineError) as excinfo:
        backtest_var(forecasts, [0.0] * 60, 0.99)
    assert excinfo.value.code == "INVALID_VAR_FORECAST"


def test_a_perfect_model_produces_the_expected_exception_count():
    """Constructed so the count is exactly right; Kupiec must not reject."""
    forecasts = [100_000.0] * 200
    pnl = [1000.0] * 200
    for i in range(2):                      # 1% of 200
        pnl[i * 90] = -200_000.0
    result = backtest_var(forecasts, pnl, 0.99)
    assert result.exceptions == 2
    assert result.expected_exceptions == pytest.approx(2.0)
    assert result.kupiec.rejected_at_5_percent is False
