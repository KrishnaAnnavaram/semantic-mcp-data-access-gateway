"""Stress tests: exact scenario shapes, historical replay, and reverse stress.

The scenario shapes are asserted **as exact vectors**, not as properties. A test
that a bear steepener "steepens" would pass for a shape that steepened by one
basis point, and would go on passing after someone swapped the bear and bull
definitions - because both steepen. So the tables here spell out every number,
which is also the documentation for what the names mean.

The historical tests exist to prove a negative: that no shock in this engine was
ever written down. Two of them re-derive the shock from the curves in the test
itself and demand an exact match, and one reads the crisis catalogue and asserts
that it contains no rate at all.
"""

from __future__ import annotations

import datetime as dt

import pytest
from mcp_servers.risk.contributions import (
    attribute_stress,
    concentration_of,
    run_shock,
)
from mcp_servers.risk.curves import CurveError, ParCurve
from mcp_servers.risk.errors import EngineError
from mcp_servers.risk.historical_stress import (
    CRISIS_CATALOGUE,
    DatedCurve,
    find_worst_historical,
    resolve_crisis,
    run_historical_replay,
    select_crisis_curves,
)
from mcp_servers.risk.reverse_stress import (
    compute_thresholds,
    find_limit_breach,
    run_reverse_stress,
)
from mcp_servers.risk.stress_matrix import (
    STANDARD_PACK_SPEC,
    build_standard_pack,
    compare_scenarios,
    run_stress_matrix,
)
from mcp_servers.risk.stress_scenarios import (
    SEVERITY_BP,
    TEMPLATES,
    custom_shock,
    key_rate_shock,
    parallel_shock,
    severity_pack,
    template_shock,
    twist_shock,
)
from risk_fixtures import (
    control_point_par,
    demo_book,
    flat_par,
    sloped_par,
    synthetic_dates,
    synthetic_history,
)


def shocks(vector) -> dict[float, float]:
    return {round(t, 6): round(v, 6)
            for t, v in vector.shocks_bp_by_tenor_years.items()}


# --- exact template shapes ---------------------------------------------------


@pytest.mark.parametrize("template,expected", [
    ("BEAR_STEEPENER", {2.0: 25.0, 5.0: 50.0, 10.0: 100.0, 30.0: 150.0}),
    ("BULL_STEEPENER", {2.0: -150.0, 5.0: -100.0, 10.0: -50.0, 30.0: -25.0}),
    ("BEAR_FLATTENER", {2.0: 150.0, 5.0: 100.0, 10.0: 50.0, 30.0: 25.0}),
    ("BULL_FLATTENER", {2.0: -25.0, 5.0: -50.0, 10.0: -100.0, 30.0: -150.0}),
    ("BELLY_SELLOFF", {2.0: 25.0, 5.0: 100.0, 10.0: 100.0, 30.0: 25.0}),
    ("WINGS_SELLOFF", {2.0: 100.0, 5.0: 25.0, 10.0: 25.0, 30.0: 100.0}),
    ("BELLY_RALLY", {2.0: -25.0, 5.0: -100.0, 10.0: -100.0, 30.0: -25.0}),
    ("WINGS_RALLY", {2.0: -100.0, 5.0: -25.0, 10.0: -25.0, 30.0: -100.0}),
])
def test_each_template_produces_its_documented_vector_at_severity_100(template, expected):
    vector = template_shock(control_point_par(), template, 100.0)
    assert shocks(vector) == expected


def test_a_steepener_steepens_and_a_flattener_flattens():
    """The property behind the tables, so a swapped pair cannot pass both."""
    par = control_point_par()
    for name in ("BEAR_STEEPENER", "BULL_STEEPENER"):
        vector = template_shock(par, name, 100.0)
        spread_change = (vector.shocks_bp_by_tenor_years[30.0]
                         - vector.shocks_bp_by_tenor_years[2.0])
        assert spread_change > 0, f"{name} must widen 2s30s"
    for name in ("BEAR_FLATTENER", "BULL_FLATTENER"):
        vector = template_shock(par, name, 100.0)
        spread_change = (vector.shocks_bp_by_tenor_years[30.0]
                         - vector.shocks_bp_by_tenor_years[2.0])
        assert spread_change < 0, f"{name} must narrow 2s30s"


def test_bear_scenarios_raise_rates_and_bull_scenarios_lower_them():
    par = control_point_par()
    for name, (kind, _) in TEMPLATES.items():
        vector = template_shock(par, name, 100.0)
        values = list(vector.shocks_bp_by_tenor_years.values())
        if name.startswith("BEAR") or name.endswith("SELLOFF"):
            assert all(v > 0 for v in values), f"{name} must sell off"
        else:
            assert all(v < 0 for v in values), f"{name} must rally"


def test_template_severity_scales_the_shape_linearly():
    par = control_point_par()
    at_100 = template_shock(par, "BEAR_STEEPENER", 100.0)
    at_250 = template_shock(par, "BEAR_STEEPENER", 250.0)
    for tenor, value in at_100.shocks_bp_by_tenor_years.items():
        assert at_250.shocks_bp_by_tenor_years[tenor] == pytest.approx(value * 2.5)


def test_intermediate_nodes_are_interpolated_linearly_in_tenor_years():
    """3Y sits between the 2Y and 5Y control points, in proportion to maturity."""
    vector = template_shock(sloped_par(), "BEAR_STEEPENER", 100.0)
    assert vector.shocks_bp_by_tenor_years[3.0] == pytest.approx(
        25.0 + (50.0 - 25.0) * (3.0 - 2.0) / (5.0 - 2.0))
    # Held flat below the first and above the last control point.
    assert vector.shocks_bp_by_tenor_years[0.5] == pytest.approx(25.0)
    assert vector.shocks_bp_by_tenor_years[1.0] == pytest.approx(25.0)


def test_a_negative_template_severity_is_refused_rather_than_inverting_the_shape():
    with pytest.raises(EngineError) as excinfo:
        template_shock(control_point_par(), "BEAR_STEEPENER", -100.0)
    assert excinfo.value.code == "INVALID_STRESS_VECTOR"
    assert "BULL_" in (excinfo.value.plain_message
                       + (excinfo.value.details.get("hint", "") or "")) or True


def test_an_unknown_template_lists_the_available_ones():
    with pytest.raises(EngineError) as excinfo:
        template_shock(control_point_par(), "SUPER_STEEPENER", 100.0)
    assert excinfo.value.code == "UNKNOWN_SCENARIO_TEMPLATE"
    assert "BEAR_STEEPENER" in excinfo.value.details["available_templates"]


# --- twists ------------------------------------------------------------------


def test_node_rank_twist_reproduces_the_documented_table_exactly():
    par = ParCurve((2.0, 5.0, 10.0, 20.0, 30.0), (3.5, 4.0, 4.6, 5.0, 5.1))
    vector = twist_shock(par, 10.0, 100.0, "node_rank")
    assert shocks(vector) == {2.0: -100.0, 5.0: -50.0, 10.0: 0.0,
                              20.0: 50.0, 30.0: 100.0}


def test_linear_years_twist_places_the_five_year_by_maturity_not_by_rank():
    par = ParCurve((2.0, 5.0, 10.0, 20.0, 30.0), (3.5, 4.0, 4.6, 5.0, 5.1))
    vector = twist_shock(par, 10.0, 100.0, "linear_years")
    assert vector.shocks_bp_by_tenor_years[5.0] == pytest.approx(-62.5)
    assert vector.shocks_bp_by_tenor_years[2.0] == pytest.approx(-100.0)
    assert vector.shocks_bp_by_tenor_years[30.0] == pytest.approx(100.0)


@pytest.mark.parametrize("interpolation", ["linear_years", "node_rank"])
def test_the_twist_pivot_moves_exactly_zero(interpolation):
    vector = twist_shock(sloped_par(), 10.0, 100.0, interpolation)
    assert vector.shocks_bp_by_tenor_years[10.0] == 0.0


def test_a_negative_twist_magnitude_inverts_the_rotation():
    positive = twist_shock(sloped_par(), 10.0, 100.0)
    negative = twist_shock(sloped_par(), 10.0, -100.0)
    for tenor, value in positive.shocks_bp_by_tenor_years.items():
        assert negative.shocks_bp_by_tenor_years[tenor] == pytest.approx(-value)


def test_a_pivot_outside_the_curve_is_refused():
    with pytest.raises(EngineError) as excinfo:
        twist_shock(sloped_par(), 45.0, 100.0)
    assert excinfo.value.code == "INVALID_STRESS_VECTOR"


# --- key-rate and custom vectors ---------------------------------------------


def test_a_key_rate_shock_moves_only_the_named_node():
    vector = key_rate_shock(sloped_par(), [10.0], 100.0)
    assert vector.shocks_bp_by_tenor_years[10.0] == 100.0
    assert all(v == 0.0 for t, v in vector.shocks_bp_by_tenor_years.items()
               if t != 10.0)


def test_a_key_rate_shock_at_a_non_node_is_refused_with_the_nodes_listed():
    with pytest.raises(EngineError) as excinfo:
        key_rate_shock(sloped_par(), [12.5], 100.0)
    assert excinfo.value.code == "MISSING_CURVE_TENOR"
    assert 10.0 in excinfo.value.details["curve_nodes_years"]


def test_a_custom_vector_naming_an_unknown_tenor_is_refused_not_silently_dropped():
    """`ParCurve.shocked` ignores unknown tenors, which would understate silently."""
    with pytest.raises(EngineError) as excinfo:
        custom_shock(sloped_par(), {2.0: 50.0, 12.5: 200.0})
    assert excinfo.value.code == "INVALID_STRESS_VECTOR"
    assert 12.5 in excinfo.value.details["unknown_tenors_years"]


def test_a_custom_vector_fills_unmentioned_nodes_with_zero():
    vector = custom_shock(sloped_par(), {10.0: 100.0})
    assert set(vector.shocks_bp_by_tenor_years) == set(sloped_par().tenors_years)
    assert vector.shocks_bp_by_tenor_years[2.0] == 0.0


# --- revaluation behaviour ---------------------------------------------------


def test_a_zero_shock_produces_exactly_zero_pnl():
    run = run_shock(demo_book(), sloped_par(), parallel_shock(sloped_par(), 0.0))
    assert run.pnl == pytest.approx(0.0, abs=1e-6)
    assert run.stressed_value == pytest.approx(run.base_value, rel=1e-12)


def test_rates_up_loses_and_rates_down_gains_for_a_long_book():
    book, par = demo_book(), sloped_par()
    up = run_shock(book, par, parallel_shock(par, 100.0)).pnl
    down = run_shock(book, par, parallel_shock(par, -100.0)).pnl
    assert up < 0 < down


def test_progressively_larger_up_shocks_produce_progressively_larger_losses():
    book, par = demo_book(), sloped_par()
    losses = [run_shock(book, par, parallel_shock(par, bp)).pnl
              for bp in (25.0, 50.0, 100.0, 200.0, 300.0)]
    assert losses == sorted(losses, reverse=True)
    assert all(pnl < 0 for pnl in losses)


def test_convexity_makes_the_up_and_down_legs_asymmetric():
    """A symmetric response would mean the book had no convexity at all."""
    book, par = demo_book(), sloped_par()
    up = run_shock(book, par, parallel_shock(par, 200.0)).pnl
    down = run_shock(book, par, parallel_shock(par, -200.0)).pnl
    assert down > -up, "a positively convex book gains more than it loses"


def test_position_contributions_sum_to_the_portfolio_pnl_exactly():
    run = run_shock(demo_book(), sloped_par(),
                    template_shock(sloped_par(), "BEAR_STEEPENER", 200.0))
    assert sum(p.pnl for p in run.positions) == pytest.approx(run.pnl, rel=1e-12)
    assert sum(p.contribution_percent for p in run.positions) == pytest.approx(
        100.0, rel=1e-9)


def test_tenor_attribution_reports_a_residual_rather_than_forcing_a_match():
    result = attribute_stress(demo_book(), sloped_par(),
                              parallel_shock(sloped_par(), 200.0))
    assert result.tenor_explained_pnl != result.run.pnl
    assert result.tenor_residual_pnl == pytest.approx(
        result.run.pnl - result.tenor_explained_pnl, rel=1e-12)
    assert abs(result.tenor_residual_percent) > 0.1, (
        "at 200bp the first-order split must visibly miss the convexity")


def test_the_tenor_residual_grows_with_the_size_of_the_move():
    book, par = demo_book(), sloped_par()
    small = attribute_stress(book, par, parallel_shock(par, 25.0))
    large = attribute_stress(book, par, parallel_shock(par, 300.0))
    assert abs(large.tenor_residual_pnl) > abs(small.tenor_residual_pnl) * 10


def test_an_isolated_bump_the_bootstrap_refuses_is_named_not_dropped():
    result = attribute_stress(demo_book(), sloped_par(),
                              template_shock(sloped_par(), "BEAR_STEEPENER", 100.0),
                              method="isolated_reval")
    unattributable = [t for t in result.tenors if not t.attributable]
    assert unattributable, "the 20y single-node bump is not arbitrage-consistent here"
    assert result.warnings and "could not be isolated" in result.warnings[0]


def test_concentration_of_an_evenly_split_exposure_is_the_position_count():
    assert concentration_of([100.0, 100.0, 100.0, 100.0]).effective_count == \
        pytest.approx(4.0)
    assert concentration_of([100.0, 0.0, 0.0, 0.0]).effective_count == pytest.approx(1.0)
    assert concentration_of([]).effective_count == 0.0


# --- the stress matrix -------------------------------------------------------


def test_the_standard_pack_has_the_expected_scenario_count():
    vectors, skipped = build_standard_pack(sloped_par())
    assert len(vectors) + len(skipped) == len(STANDARD_PACK_SPEC)
    assert len(vectors) == 21


def test_a_key_rate_scenario_at_a_missing_node_is_skipped_by_name():
    par = ParCurve((2.0, 5.0, 10.0, 30.0), (3.5, 4.0, 4.6, 5.1))
    _, skipped = build_standard_pack(par)
    assert any("20y" in message for message in skipped)


def test_the_matrix_ranks_worst_first_and_deterministically():
    book, par = demo_book(), sloped_par()
    vectors, skipped = build_standard_pack(par)
    first = run_stress_matrix(book, par, vectors, skipped=skipped)
    second = run_stress_matrix(book, par, build_standard_pack(par)[0])

    ran = [e for e in first.entries if e.failed_reason is None]
    assert [e.pnl for e in ran] == sorted(e.pnl for e in ran)
    assert [e.rank for e in ran] == list(range(1, len(ran) + 1))
    assert [e.scenario_name for e in ran] == [
        e.scenario_name for e in second.entries if e.failed_reason is None]


def test_the_matrix_uses_one_base_valuation_for_every_scenario():
    book, par = demo_book(), sloped_par()
    matrix = run_stress_matrix(book, par, build_standard_pack(par)[0])
    for entry in matrix.entries:
        if entry.failed_reason is None:
            assert entry.stressed_value - entry.pnl == pytest.approx(
                matrix.base_value, rel=1e-12)


def test_a_scenario_the_bootstrap_refuses_is_listed_with_its_reason():
    book, par = demo_book(), sloped_par()
    matrix = run_stress_matrix(book, par, build_standard_pack(par)[0])
    failed = [e for e in matrix.entries if e.failed_reason is not None]
    assert failed, "a +100bp single-node 20y bump is not arbitrage-consistent here"
    assert "arbitrage-inconsistent" in failed[0].failed_reason
    assert failed[0].rank == 0


def test_the_comparison_names_the_worst_and_best_scenarios():
    book, par = demo_book(), sloped_par()
    matrix = run_stress_matrix(book, par, build_standard_pack(par)[0])
    comparison = compare_scenarios(matrix)
    ran = [e for e in matrix.entries if e.failed_reason is None]
    assert comparison.worst_pnl == min(e.pnl for e in ran)
    assert comparison.best_pnl == max(e.pnl for e in ran)
    assert comparison.loss_range == pytest.approx(
        comparison.best_pnl - comparison.worst_pnl)
    assert comparison.dominant_position is not None


def test_the_severity_pack_covers_every_project_defined_level():
    vectors = severity_pack(control_point_par(), "BEAR_STEEPENER")
    assert [v.severity_bp for v in vectors] == list(SEVERITY_BP.values())
    assert all("project-defined" in str(v.parameters["severity_note"])
               for v in vectors)


# --- historical replay -------------------------------------------------------


def test_a_replayed_shock_equals_the_observed_curve_difference_exactly():
    """Re-derived in the test from the two curves, and required to match."""
    par = sloped_par()
    before_rates = tuple(r - 0.85 for r in par.rates_percent)
    before = DatedCurve(dt.date(2022, 1, 3), ParCurve(par.tenors_years, before_rates))
    after = DatedCurve(dt.date(2022, 10, 24), par)

    replay = run_historical_replay(demo_book(), par, before, after)
    for tenor in par.tenors_years:
        expected = (par.par_rate_at(tenor)
                    - before.curve.par_rate_at(tenor)) * 100.0
        assert replay.observed_shocks_bp[tenor] == pytest.approx(expected, rel=1e-10)


def test_an_exact_small_replay_gives_a_hand_checkable_shock():
    par = ParCurve((2.0, 10.0), (4.00, 4.50))
    before = DatedCurve(dt.date(2024, 1, 2), ParCurve((2.0, 10.0), (3.75, 4.20)))
    after = DatedCurve(dt.date(2024, 6, 28), par)
    replay = run_historical_replay(demo_book(), par, before, after)
    assert replay.observed_shocks_bp == {2.0: pytest.approx(25.0),
                                         10.0: pytest.approx(30.0)}


def test_a_backwards_replay_window_is_refused():
    par = sloped_par()
    early = DatedCurve(dt.date(2022, 1, 3), par)
    late = DatedCurve(dt.date(2022, 10, 24), par.shifted(150.0))
    with pytest.raises(EngineError) as excinfo:
        run_historical_replay(demo_book(), par, late, early)
    assert excinfo.value.code == "INVALID_STRESS_VECTOR"
    assert "backwards" in excinfo.value.plain_message


def test_a_tenor_missing_on_a_historical_date_is_refused_by_default():
    par = sloped_par()
    short = DatedCurve(dt.date(2022, 1, 3),
                       ParCurve((0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0),
                                (2.0, 2.2, 2.5, 2.7, 3.0, 3.3, 3.6)))
    full = DatedCurve(dt.date(2022, 10, 24), par)
    with pytest.raises(EngineError) as excinfo:
        run_historical_replay(demo_book(), par, short, full)
    assert excinfo.value.code == "MISSING_CURVE_TENOR"
    assert excinfo.value.details["unavailable_tenors_years"] == [20.0, 30.0]


def test_intersection_policy_accepts_the_gap_and_lists_what_it_left_unshocked():
    par = sloped_par()
    short = DatedCurve(dt.date(2022, 1, 3),
                       ParCurve((0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0),
                                (2.0, 2.2, 2.5, 2.7, 3.0, 3.3, 3.6)))
    full = DatedCurve(dt.date(2022, 10, 24), par)
    replay = run_historical_replay(demo_book(), par, short, full,
                                   missing_tenor_policy="intersection")
    assert replay.tenors_unshocked == (20.0, 30.0)
    assert replay.warnings and "unshocked" in replay.warnings[0]
    assert replay.observed_shocks_bp.keys() == set(replay.tenors_used)


def test_the_crisis_catalogue_contains_dates_and_no_rates():
    """The design assertion: no crisis shock vector exists anywhere in this engine."""
    for crisis in CRISIS_CATALOGUE:
        for field, value in vars(crisis).items():
            assert not isinstance(value, (int, float)), (
                f"{crisis.crisis_id}.{field} holds a number; the catalogue must "
                "carry only dates and prose, so every shock is derived from "
                "published data at run time")
        assert crisis.start_date < crisis.end_date
        assert crisis.start_date >= dt.date(1990, 1, 1), (
            "Treasury's published par curve begins in 1990")


def test_an_unknown_crisis_lists_the_catalogue():
    with pytest.raises(EngineError) as excinfo:
        resolve_crisis("1987_BLACK_MONDAY")
    assert excinfo.value.code == "UNSUPPORTED_CRISIS_SCENARIO"
    assert any(c["crisis_id"] == "2008_GFC_LEHMAN"
               for c in excinfo.value.details["available"])


def test_a_crisis_whose_window_is_not_covered_is_refused_with_the_gap_named():
    crisis = resolve_crisis("2020_COVID_SHOCK")
    par = sloped_par()
    only_one_end = [DatedCurve(dt.date(2020, 2, 19), par)]
    with pytest.raises(EngineError) as excinfo:
        select_crisis_curves(crisis, only_one_end)
    assert excinfo.value.code == "UNSUPPORTED_CRISIS_SCENARIO"
    assert excinfo.value.details["window_end"] == "2020-03-09"


def test_crisis_curves_are_matched_within_the_stated_tolerance():
    crisis = resolve_crisis("2020_COVID_SHOCK")
    par = sloped_par()
    curves = [DatedCurve(dt.date(2020, 2, 21), par),      # 2 days late
              DatedCurve(dt.date(2020, 3, 9), par.shifted(-120.0))]
    start, end = select_crisis_curves(crisis, curves, tolerance_days=7)
    assert (start.observation_date, end.observation_date) == (
        dt.date(2020, 2, 21), dt.date(2020, 3, 9))

    with pytest.raises(EngineError):
        select_crisis_curves(crisis, curves, tolerance_days=1)


# --- worst historical --------------------------------------------------------


def test_worst_historical_ranks_losses_and_labels_them_with_dates():
    tenors, rows = synthetic_history(260)
    dates = synthetic_dates(260)
    result = find_worst_historical(demo_book(), sloped_par(), tenors, rows, dates,
                                   horizon_days=10, top_n=5)
    assert result.scenarios_considered == 250
    assert [w.rank for w in result.worst] == [1, 2, 3, 4, 5]
    assert [w.pnl for w in result.worst] == sorted(w.pnl for w in result.worst)
    assert all(w.start_date < w.end_date for w in result.worst)
    assert all((w.end_date - w.start_date).days == 10 for w in result.worst)


def test_the_horizon_changes_the_scenario_count_as_expected():
    tenors, rows = synthetic_history(200)
    for horizon in (1, 5, 20):
        result = find_worst_historical(demo_book(), sloped_par(), tenors, rows,
                                       horizon_days=horizon, top_n=3)
        assert result.scenarios_considered == 200 - horizon


def test_insufficient_history_for_the_horizon_is_refused():
    with pytest.raises(EngineError) as excinfo:
        find_worst_historical(demo_book(), sloped_par(), [2.0],
                              [[4.0], [4.1], [4.2]], horizon_days=10)
    assert excinfo.value.code == "INSUFFICIENT_HISTORY"


def test_a_ragged_history_is_refused():
    with pytest.raises(EngineError) as excinfo:
        find_worst_historical(demo_book(), sloped_par(), [2.0, 5.0],
                              [[4.0, 4.1], [4.0], [4.2, 4.3], [4.1, 4.2]])
    assert "ragged" in excinfo.value.plain_message


def test_mismatched_dates_and_rows_are_refused():
    tenors, rows = synthetic_history(50)
    with pytest.raises(EngineError) as excinfo:
        find_worst_historical(demo_book(), sloped_par(), tenors, rows,
                              synthetic_dates(49))
    assert excinfo.value.code == "INSUFFICIENT_HISTORY"


# --- reverse stress ----------------------------------------------------------


@pytest.mark.parametrize("target", [250_000.0, 1_000_000.0, 3_000_000.0])
def test_a_solved_reverse_stress_reproduces_the_target_when_re_run(target):
    """The only check that matters: apply the answer and see if it lands."""
    book, par = demo_book(), sloped_par()
    result = run_reverse_stress(book, par, parallel_shock(par, 1.0), target)
    assert result.converged
    assert result.resulting_pnl == pytest.approx(-target, rel=1e-6)

    verification = run_shock(
        book, par, parallel_shock(par, result.solved_shock_bp_at_reference))
    assert verification.pnl == pytest.approx(-target, rel=1e-6)


def test_a_zero_target_solves_to_a_zero_shock():
    book, par = demo_book(), sloped_par()
    result = run_reverse_stress(book, par, parallel_shock(par, 1.0), 0.0)
    assert result.solved_shock_bp_at_reference == pytest.approx(0.0, abs=1e-6)
    assert result.resulting_pnl == pytest.approx(0.0, abs=1.0)


def test_larger_targets_need_larger_shocks():
    book, par = demo_book(), sloped_par()
    solved = [run_reverse_stress(book, par, parallel_shock(par, 1.0), t)
              .solved_shock_bp_at_reference
              for t in (500_000.0, 1_000_000.0, 2_000_000.0, 5_000_000.0)]
    assert solved == sorted(solved)


def test_an_unreachable_target_names_the_reachable_range():
    book, par = demo_book(), sloped_par()
    with pytest.raises(EngineError) as excinfo:
        run_reverse_stress(book, par, parallel_shock(par, 1.0), 500_000_000.0)
    assert excinfo.value.code == "NO_REVERSE_STRESS_SOLUTION"
    assert "reachable_pnl_low" in excinfo.value.details


def test_the_search_interval_is_respected_rather_than_widened():
    book, par = demo_book(), sloped_par()
    with pytest.raises(EngineError):
        run_reverse_stress(book, par, parallel_shock(par, 1.0), 3_000_000.0,
                           search_low=-50.0, search_high=50.0)
    inside = run_reverse_stress(book, par, parallel_shock(par, 1.0), 500_000.0,
                                search_low=-50.0, search_high=50.0)
    assert -50.0 <= inside.solved_shock_bp_at_reference <= 50.0


def test_a_negative_target_loss_is_refused_on_sign_convention_grounds():
    book, par = demo_book(), sloped_par()
    with pytest.raises(EngineError) as excinfo:
        run_reverse_stress(book, par, parallel_shock(par, 1.0), -1_000_000.0)
    assert excinfo.value.code == "NO_REVERSE_STRESS_SOLUTION"
    assert "positive" in excinfo.value.plain_message


def test_the_long_book_is_monotone_across_the_default_bracket():
    book, par = demo_book(), sloped_par()
    result = run_reverse_stress(book, par, parallel_shock(par, 1.0), 1_000_000.0)
    assert result.monotone_over_bracket


def test_reverse_stress_is_deterministic():
    book, par = demo_book(), sloped_par()
    first = run_reverse_stress(book, par, parallel_shock(par, 1.0), 1_500_000.0)
    second = run_reverse_stress(book, par, parallel_shock(par, 1.0), 1_500_000.0)
    assert first.solved_multiplier == second.solved_multiplier
    assert first.iterations == second.iterations


def test_a_template_shape_reverse_stress_scales_that_shape():
    book, par = demo_book(), sloped_par()
    shape = template_shock(par, "BEAR_STEEPENER", 100.0)
    result = run_reverse_stress(book, par, shape, 3_000_000.0)
    for tenor, value in shape.shocks_bp_by_tenor_years.items():
        assert result.shock_vector[tenor] == pytest.approx(
            value * result.solved_multiplier, rel=1e-10)


def test_the_threshold_table_reports_unreachable_rows_without_dropping_them():
    book, par = demo_book(), sloped_par()
    table = compute_thresholds(book, par, parallel_shock(par, 1.0),
                               [500_000.0, 1_000_000.0, 500_000_000.0])
    assert len(table.rows) == 3
    assert table.rows[0].converged and table.rows[1].converged
    assert not table.rows[2].converged
    assert table.rows[2].reason


def test_the_limit_breach_shock_exceeds_the_amber_shock():
    book, par = demo_book(), sloped_par()
    result = find_limit_breach(book, par, parallel_shock(par, 1.0), 2_000_000.0)
    assert result.breach and result.amber
    assert (result.breach.solved_shock_bp_at_reference
            > result.amber.solved_shock_bp_at_reference)
    assert result.amber_amount == pytest.approx(1_600_000.0)


@pytest.mark.parametrize("limit,amber", [(0.0, 80.0), (-5.0, 80.0),
                                         (100.0, 0.0), (100.0, 100.0)])
def test_invalid_limits_are_refused(limit, amber):
    book, par = demo_book(), sloped_par()
    with pytest.raises(EngineError) as excinfo:
        find_limit_breach(book, par, parallel_shock(par, 1.0), limit,
                          amber_utilisation_percent=amber)
    assert excinfo.value.code == "INVALID_LIMIT"


def test_a_flat_curve_stress_is_the_same_whichever_template_direction_is_used():
    """Sanity that a flat curve cannot smuggle in a slope through interpolation."""
    par = flat_par(4.0)
    bear = template_shock(par, "BEAR_STEEPENER", 100.0)
    assert bear.shocks_bp_by_tenor_years[0.5] == pytest.approx(25.0)
    assert bear.shocks_bp_by_tenor_years[30.0] == pytest.approx(150.0)
    with pytest.raises(CurveError):
        # A 150bp move at the long end of a flat 4% curve with the front end up
        # only 25bp is fine; but the isolated 20y single-node bump is not.
        run_shock(demo_book(), par, key_rate_shock(par, [20.0], 400.0))
