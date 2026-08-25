"""FRTB GIRR under the sensitivities-based method.

Every constant asserted here is checked against the published Basel value
written out in the test, not against the module that stores it. That is the
whole point of a regulatory test: the module and the test agreeing proves only
that someone typed the same number twice, so the number the test carries has to
come from the standard.

Source for all of them: BCBS, *Minimum capital requirements for market risk*,
chapter MAR21 "Standardised approach: sensitivities-based method". National
implementations renumber the same text - the Saudi Central Bank rulebook carries
it as sections 7.x - and the parameters are identical.

The other thing this file guards is the scope. A capital number that silently
omits a risk class the bank actually runs is understated rather than
conservative, so the unsupported classes are asserted to be *absent* rather than
zero, and vega is asserted to be `None` rather than `0.0`.
"""

from __future__ import annotations

import math

import pytest
from mcp_servers.risk.errors import EngineError
from mcp_servers.risk.pricing import Position
from mcp_servers.risk.regulatory import constants as k
from mcp_servers.risk.regulatory.girr import (
    compute_girr_capital,
    girr_correlation,
    map_to_vertices,
    scenario_correlation,
)
from mcp_servers.risk.revaluation import compile_book, key_rate_exposures
from risk_fixtures import VALUATION, demo_book, demo_positions, sloped_par

# --- the prescribed constants ------------------------------------------------


def test_the_delta_vertices_are_the_ten_prescribed_by_mar21_8():
    assert k.GIRR_VERTICES_YEARS == (0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0,
                                     15.0, 20.0, 30.0)


def test_the_delta_risk_weights_match_the_mar21_42_table():
    """MAR21.42, Table 1. Written out here so the module cannot drift silently."""
    published = {0.25: 0.017, 0.5: 0.017, 1.0: 0.016, 2.0: 0.013, 3.0: 0.012,
                 5.0: 0.011, 10.0: 0.011, 15.0: 0.011, 20.0: 0.011, 30.0: 0.011}
    assert k.GIRR_DELTA_RISK_WEIGHTS == published


def test_the_correlation_parameters_match_the_standard():
    assert k.GIRR_CORRELATION_THETA == 0.03          # MAR21.46 footnote
    assert k.GIRR_CORRELATION_FLOOR == 0.40          # the same footnote
    assert k.GIRR_INTER_BUCKET_CORRELATION == 0.50   # MAR21.50
    assert k.HIGH_CORRELATION_MULTIPLIER == 1.25     # MAR21.6


def test_the_curvature_risk_weight_is_the_bucket_s_highest_delta_weight():
    """MAR21.99: a parallel shift at the most punitive tenor weight, 1.7%."""
    assert k.GIRR_CURVATURE_RISK_WEIGHT == 0.017
    assert k.GIRR_CURVATURE_RISK_WEIGHT == max(k.GIRR_DELTA_RISK_WEIGHTS.values())


def test_a_basis_point_is_one_ten_thousandth():
    """MAR21.19 divides the 1bp value change by 0.0001. A factor of 10,000."""
    assert k.BASIS_POINT == 0.0001


# --- the correlation formula -------------------------------------------------


@pytest.mark.parametrize("a,b", [(0.25, 0.5), (1.0, 2.0), (2.0, 10.0),
                                 (10.0, 15.0), (20.0, 30.0)])
def test_tenor_correlation_matches_the_published_formula(a, b):
    """rho = max(40%, exp(-3% * |Ta - Tb| / min(Ta, Tb)))."""
    expected = max(0.40, math.exp(-0.03 * abs(a - b) / min(a, b)))
    assert girr_correlation(a, b) == pytest.approx(expected, rel=1e-12)


def test_the_forty_percent_floor_binds_for_widely_separated_tenors():
    assert girr_correlation(0.25, 30.0) == pytest.approx(0.40)
    assert math.exp(-0.03 * 29.75 / 0.25) < 0.40, "the raw formula is far below"


def test_a_tenor_is_perfectly_correlated_with_itself():
    for tenor in k.GIRR_VERTICES_YEARS:
        assert girr_correlation(tenor, tenor) == 1.0


def test_correlation_is_symmetric():
    assert girr_correlation(2.0, 10.0) == pytest.approx(girr_correlation(10.0, 2.0))


def test_correlation_falls_as_tenors_separate():
    values = [girr_correlation(2.0, t) for t in (3.0, 5.0, 10.0, 20.0)]
    assert values == sorted(values, reverse=True)


# --- the three correlation scenarios -----------------------------------------


def test_the_medium_scenario_uses_the_parameters_unchanged():
    assert scenario_correlation(0.6, "medium") == 0.6


@pytest.mark.parametrize("base,expected", [(0.4, 0.5), (0.6, 0.75), (0.9, 1.0)])
def test_the_high_scenario_multiplies_by_1_25_and_caps_at_one(base, expected):
    assert scenario_correlation(base, "high") == pytest.approx(expected)


@pytest.mark.parametrize("base,expected", [
    (0.40, 0.30),      # max(2*0.4 - 1, 0.75*0.4) = max(-0.2, 0.30)
    (0.60, 0.45),      # max(0.20, 0.45)
    (0.90, 0.80),      # max(0.80, 0.675)
    (1.00, 1.00),      # max(1.00, 0.75)
])
def test_the_low_scenario_uses_the_published_max_rule(base, expected):
    """max(2 x rho - 100%, 75% x rho), per MAR21.6."""
    assert scenario_correlation(base, "low") == pytest.approx(expected)


def test_the_low_scenario_never_exceeds_medium_and_high_never_falls_below_it():
    for base in (0.4, 0.5, 0.7, 0.9, 1.0):
        low = scenario_correlation(base, "low")
        high = scenario_correlation(base, "high")
        assert low <= base <= high


# --- vertex mapping ----------------------------------------------------------


def test_mapping_to_vertices_preserves_the_total_sensitivity_exactly():
    """An allocation rule that leaks sensitivity understates the capital."""
    book, par = demo_book(), sloped_par()
    _, krd, _ = key_rate_exposures(book, par, 1.0)
    allocated, _, _ = map_to_vertices(krd)

    expected_total = sum(-v / k.BASIS_POINT for _, v in krd)
    assert sum(allocated.values()) == pytest.approx(expected_total, rel=1e-9)


def test_a_curve_node_between_two_vertices_is_split_between_them():
    """The 7-year sits between the 5- and 10-year vertices, by maturity."""
    allocated, provenance, _ = map_to_vertices([(7.0, -1.0)])
    sensitivity = 1.0 / k.BASIS_POINT
    assert allocated[5.0] == pytest.approx(sensitivity * (10.0 - 7.0) / (10.0 - 5.0))
    assert allocated[10.0] == pytest.approx(sensitivity * (7.0 - 5.0) / (10.0 - 5.0))
    assert allocated[2.0] == 0.0
    assert [t for t, _ in provenance[5.0]] == [7.0]


def test_a_node_on_a_vertex_maps_entirely_to_it():
    allocated, _, _ = map_to_vertices([(10.0, -1.0)])
    assert allocated[10.0] == pytest.approx(1.0 / k.BASIS_POINT)
    assert sum(v for t, v in allocated.items() if t != 10.0) == pytest.approx(0.0)


def test_a_node_beyond_the_last_vertex_maps_wholly_to_it():
    allocated, _, _ = map_to_vertices([(40.0, -1.0)])
    assert allocated[30.0] == pytest.approx(1.0 / k.BASIS_POINT)


def test_the_sensitivity_sign_is_flipped_from_the_engine_convention():
    """KRDV01 is base minus bumped; Basel's PV01 is bumped minus base over 1bp.

    A long book has a positive key-rate DV01 and a negative Basel sensitivity.
    Getting this backwards hides inside the quadratic aggregation and only
    surfaces in the cross terms, which is exactly why it is asserted directly.
    """
    allocated, _, _ = map_to_vertices([(10.0, 500.0)])     # positive KRDV01
    assert allocated[10.0] < 0


# --- the capital calculation -------------------------------------------------


def test_delta_capital_is_the_largest_of_the_three_correlation_scenarios():
    result = compute_girr_capital(demo_book(), sloped_par())
    assert result.delta_capital == max(s.delta_capital for s in result.scenarios)
    assert {s.scenario for s in result.scenarios} == {"low", "medium", "high"}


def test_the_high_scenario_binds_for_a_one_directional_book():
    """Every vertex sensitivity has the same sign, so more correlation costs more."""
    result = compute_girr_capital(demo_book(), sloped_par())
    assert result.binding_scenario == "high"
    ordered = {s.scenario: s.delta_capital for s in result.scenarios}
    assert ordered["low"] < ordered["medium"] < ordered["high"]


def test_delta_capital_is_close_to_dv01_times_the_dominant_risk_weight():
    """An order-of-magnitude sanity check with an independent derivation.

    Almost all of this book's risk sits at vertices weighted 1.1%, so the delta
    charge must land near DV01 x 110bp. A factor-of-10,000 error in the PV01
    conversion, or a missing risk weight, moves it far outside this band.
    """
    from mcp_servers.risk.sensitivities import compute_rate_sensitivities
    book, par = demo_book(), sloped_par()
    dv01 = compute_rate_sensitivities(book, par).dv01
    result = compute_girr_capital(book, par)
    assert result.delta_capital == pytest.approx(dv01 * 110.0, rel=0.25)


def test_capital_scales_linearly_with_the_book():
    """Delta capital is homogeneous of degree one in the sensitivities."""
    par = sloped_par()
    single = compute_girr_capital(demo_book(), par).delta_capital
    doubled = compute_girr_capital(
        compile_book([Position(p.bond, p.face_notional * 2)
                      for p in demo_positions()], VALUATION), par).delta_capital
    assert doubled == pytest.approx(single * 2.0, rel=1e-9)


def test_the_bucket_aggregate_is_floored_at_zero_under_the_square_root():
    """MAR21.4(4). The flag must be reported rather than silently applied."""
    result = compute_girr_capital(demo_book(), sloped_par())
    for scenario in result.scenarios:
        assert scenario.bucket_capital >= 0
        if scenario.sum_under_root >= 0:
            assert not scenario.floored_at_zero
            assert scenario.bucket_capital == pytest.approx(
                math.sqrt(scenario.sum_under_root), rel=1e-12)


def test_curvature_floors_at_zero_for_a_positively_convex_book_and_says_why():
    """Basel does not credit the convexity benefit, and the result explains it."""
    result = compute_girr_capital(demo_book(), sloped_par())
    curvature = result.curvature
    assert curvature is not None
    assert curvature.cvr_up < 0 and curvature.cvr_down < 0
    assert curvature.bucket_capital == 0.0
    assert curvature.book_is_positively_convex
    assert "correct result for a positively convex book" in curvature.interpretation


def test_the_curvature_shock_is_a_parallel_170bp_shift():
    result = compute_girr_capital(demo_book(), sloped_par())
    assert result.curvature.shock_bp == pytest.approx(170.0)
    assert result.curvature.value_up < result.curvature.base_value
    assert result.curvature.value_down > result.curvature.base_value


def test_curvature_can_be_switched_off():
    result = compute_girr_capital(demo_book(), sloped_par(), include_curvature=False)
    assert result.curvature is None
    assert result.total_capital == result.delta_capital


# --- scope ------------------------------------------------------------------


def test_vega_is_absent_rather_than_zero():
    """The book has no optionality, so a vega charge is not a number to produce."""
    result = compute_girr_capital(demo_book(), sloped_par())
    assert result.vega_capital is None
    assert k.RISK_CLASS_SUPPORT["GIRR_VEGA"] is False


def test_every_unmeasurable_risk_class_is_listed_as_unsupported():
    result = compute_girr_capital(demo_book(), sloped_par())
    unsupported = set(result.unsupported_risk_classes)
    assert {"CSR_NON_SEC", "EQUITY", "FX", "COMMODITY",
            "DEFAULT_RISK_CHARGE", "GIRR_VEGA"} <= unsupported
    assert "GIRR_DELTA" not in unsupported
    assert "understated" in result.unsupported_reason


def test_a_non_usd_bucket_is_refused_as_out_of_scope():
    with pytest.raises(EngineError) as excinfo:
        compute_girr_capital(demo_book(), sloped_par(), currency="EUR")
    assert excinfo.value.code == "UNSUPPORTED_REGULATORY_SCOPE"
    assert excinfo.value.category == "MODEL_SCOPE"


def test_the_result_carries_its_source_and_constants_version():
    result = compute_girr_capital(demo_book(), sloped_par())
    assert "MAR21" in result.source
    assert result.constants_version == k.FRTB_CONSTANTS_VERSION
    assert "not a reported regulatory capital" in result.scope_note.lower() or \
           "not a reported capital requirement" in result.scope_note.lower()


def test_the_regulatory_constants_module_holds_no_other_risk_class_weights():
    """Scope creep guard: a table without instruments behind it is a liability."""
    names = [name for name in dir(k) if name.isupper()]
    for forbidden in ("EQUITY_RISK_WEIGHTS", "FX_RISK_WEIGHTS",
                      "CSR_RISK_WEIGHTS", "COMMODITY_RISK_WEIGHTS"):
        assert forbidden not in names, (
            f"{forbidden} would let a capital figure be produced for a risk "
            "class this system cannot measure")
