"""FRTB GIRR under the sensitivities-based method.  `bcbs_mar21_girr_delta_curvature_v1`

The standardised general-interest-rate-risk capital requirement, computed from
the same full-revaluation engine everything else here uses. Delta and curvature
only, for one currency bucket, because that is what the data supports - see
`constants.RISK_CLASS_SUPPORT` and the refusal it drives.

## Delta

1. **Sensitivities.** MAR21.19 defines the GIRR delta sensitivity as PV01: the
   value change for a 1bp move at a vertex, divided by 0.0001. This engine's
   key-rate DV01 is `V_base - V_up(+1bp)`, positive for a long book, so the
   Basel sensitivity is `s_t = -KRD_t / 0.0001`. The sign flip is not cosmetic -
   it is the difference between an exposure and its negative, and the
   aggregation is quadratic so the error would hide in the squares and show up
   only in the cross terms.

2. **Vertex mapping.** Basel prescribes ten vertices; Treasury publishes a
   different set. Sensitivity at a curve node that is not a prescribed vertex is
   **allocated linearly between the two neighbouring vertices**, which is the
   standard treatment and preserves the total. A node beyond the outermost
   vertex goes wholly to that vertex. The allocation is reported, because a
   reader checking a capital number against a key-rate report needs to see where
   the 7-year went.

3. **Weight and aggregate.** `WS_t = RW_t * s_t`, then within the bucket

       K_b = sqrt( max( 0, sum_t WS_t^2 + sum_{t != u} rho_tu WS_t WS_u ) )

   with `rho_tu = max(40%, exp(-3% * |T_t - T_u| / min(T_t, T_u)))` (MAR21.46)
   and the sum under the root floored at zero (MAR21.4(4)).

4. **Across buckets.** One currency, so the across-bucket step is trivial here,
   but the full formula runs anyway - including the MAR21.4(5)(b) alternative
   specification `S_b = max(min(sum WS, K_b), -K_b)` for when the sum under the
   outer root goes negative. Implementing the degenerate case as though it were
   general is how a one-currency implementation quietly becomes wrong the day a
   second currency arrives.

5. **Three scenarios.** Medium as-is; high with correlations multiplied by 1.25
   and capped at 100%; low at `max(2*rho - 100%, 75%*rho)` (MAR21.6). The
   capital requirement is the largest of the three (MAR21.7).

## Curvature

MAR21.99 makes the GIRR curvature shock a **parallel shift of the whole curve**
at the bucket's highest delta risk weight - 1.7%, the 0.25-year figure. With one
curve there is exactly one curvature risk factor, so:

    CVR+ = -( V(curve + 170bp) - V(curve) - RW * sum_t s_t )
    CVR- = -( V(curve - 170bp) - V(curve) + RW * sum_t s_t )
    K_b  = max( CVR+, CVR-, 0 )

Both revaluations are full ones, so the "curvature" being charged is the actual
convexity of the bonds rather than an estimate of it.

**A positively convex long bond book normally scores zero here, and that is
correct.** Convexity is a benefit: the book loses less than delta predicts when
rates rise and gains more when they fall, so both CVR values come out negative
and the floor takes them to zero. A curvature charge on this portfolio would
mean it had *negative* convexity somewhere. The result says which case it was
rather than just reporting a zero.

**There is no vega.** Not zero - absent. The book contains no optionality, so
the vega charge is not a number this system is entitled to produce, and it is
reported as unsupported.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from ..curves import ParCurve
from ..errors import EngineError, unsupported_scope
from ..revaluation import CompiledBook, key_rate_exposures
from .constants import (
    BASIS_POINT,
    FRTB_CONSTANTS_VERSION,
    FRTB_SOURCE,
    GIRR_CORRELATION_FLOOR,
    GIRR_CORRELATION_THETA,
    GIRR_CURVATURE_RISK_WEIGHT,
    GIRR_DELTA_RISK_WEIGHTS,
    GIRR_INTER_BUCKET_CORRELATION,
    GIRR_VERTICES_YEARS,
    HIGH_CORRELATION_MULTIPLIER,
    LOW_CORRELATION_ALTERNATIVE_MULTIPLIER,
    LOW_CORRELATION_FLOOR_MULTIPLIER,
    RISK_CLASS_SUPPORT,
    UNSUPPORTED_REASON,
)

CorrelationScenario = Literal["low", "medium", "high"]
SCENARIOS: tuple[CorrelationScenario, ...] = ("low", "medium", "high")


@dataclass(frozen=True)
class VertexSensitivity:
    vertex_years: float
    risk_weight: float
    sensitivity: float
    weighted_sensitivity: float
    sourced_from_curve_nodes: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class ScenarioResult:
    scenario: CorrelationScenario
    bucket_capital: float
    delta_capital: float
    sum_under_root: float
    floored_at_zero: bool
    used_alternative_specification: bool


@dataclass(frozen=True)
class CurvatureResult:
    risk_weight: float
    shock_bp: float
    base_value: float
    value_up: float
    value_down: float
    delta_offset: float
    cvr_up: float
    cvr_down: float
    bucket_capital: float
    book_is_positively_convex: bool
    interpretation: str


@dataclass(frozen=True)
class GirrCapital:
    currency: str
    bucket: str
    base_value: float
    vertices: tuple[VertexSensitivity, ...]
    unmapped_curve_nodes: tuple[float, float]
    scenarios: tuple[ScenarioResult, ...]
    delta_capital: float
    binding_scenario: CorrelationScenario
    curvature: CurvatureResult | None
    total_capital: float
    vega_capital: None
    unsupported_risk_classes: tuple[str, ...]
    unsupported_reason: str
    source: str = FRTB_SOURCE
    constants_version: str = FRTB_CONSTANTS_VERSION
    method: str = "bcbs_mar21_girr_delta_curvature_v1"
    scope_note: str = (
        "GIRR delta and curvature for a single currency bucket. Vega is not "
        "computed because the book contains no optionality, and no other risk "
        "class is in scope. This is a standardised-approach demonstration on a "
        "synthetic book, not a reported capital requirement."
    )


def girr_correlation(tenor_a: float, tenor_b: float) -> float:
    """MAR21.46: max(40%, exp(-3% * |Ta - Tb| / min(Ta, Tb)))."""
    if tenor_a == tenor_b:
        return 1.0
    smallest = min(tenor_a, tenor_b)
    if smallest <= 0:
        raise EngineError(
            "UNSUPPORTED_REGULATORY_SCOPE",
            "a GIRR vertex must have a positive tenor",
            category="MODEL_SCOPE")
    raw = math.exp(-GIRR_CORRELATION_THETA * abs(tenor_a - tenor_b) / smallest)
    return max(GIRR_CORRELATION_FLOOR, raw)


def scenario_correlation(base: float, scenario: CorrelationScenario) -> float:
    """MAR21.6: medium as-is, high x1.25 capped at 100%, low the max() rule."""
    if scenario == "medium":
        return base
    if scenario == "high":
        return min(1.0, base * HIGH_CORRELATION_MULTIPLIER)
    return max(LOW_CORRELATION_ALTERNATIVE_MULTIPLIER * base - 1.0,
               LOW_CORRELATION_FLOOR_MULTIPLIER * base)


def map_to_vertices(
    key_rate_dv01: Sequence[tuple[float, float]],
) -> tuple[dict[float, float], dict[float, list[tuple[float, float]]], tuple[float, float]]:
    """Allocate curve-node sensitivity onto the prescribed vertices.

    Linear allocation between the two neighbouring vertices; a node outside the
    vertex range goes entirely to the nearest end. The total sensitivity is
    preserved exactly, which a test asserts - an allocation rule that leaks
    sensitivity produces a capital number that is quietly too small.
    """
    vertices = list(GIRR_VERTICES_YEARS)
    allocated = {v: 0.0 for v in vertices}
    provenance: dict[float, list[tuple[float, float]]] = {v: [] for v in vertices}

    for tenor, krd in key_rate_dv01:
        sensitivity = -krd / BASIS_POINT
        if tenor <= vertices[0]:
            allocated[vertices[0]] += sensitivity
            provenance[vertices[0]].append((tenor, sensitivity))
            continue
        if tenor >= vertices[-1]:
            allocated[vertices[-1]] += sensitivity
            provenance[vertices[-1]].append((tenor, sensitivity))
            continue
        for lower, upper in zip(vertices, vertices[1:]):
            if lower <= tenor <= upper:
                weight = 0.0 if upper == lower else (tenor - lower) / (upper - lower)
                allocated[lower] += sensitivity * (1.0 - weight)
                allocated[upper] += sensitivity * weight
                if weight < 1.0:
                    provenance[lower].append((tenor, sensitivity * (1.0 - weight)))
                if weight > 0.0:
                    provenance[upper].append((tenor, sensitivity * weight))
                break

    node_range = (min(t for t, _ in key_rate_dv01), max(t for t, _ in key_rate_dv01))
    return allocated, provenance, node_range


def _bucket_capital(
    weighted: Sequence[tuple[float, float]], scenario: CorrelationScenario,
) -> tuple[float, float, bool]:
    """K_b for one bucket. Returns (K_b, sum under root, whether it was floored)."""
    total = sum(ws * ws for _, ws in weighted)
    for i, (tenor_i, ws_i) in enumerate(weighted):
        for j, (tenor_j, ws_j) in enumerate(weighted):
            if i == j:
                continue
            rho = scenario_correlation(girr_correlation(tenor_i, tenor_j), scenario)
            total += rho * ws_i * ws_j
    floored = total < 0
    return math.sqrt(max(0.0, total)), total, floored


def _across_buckets(
    bucket_capitals: Sequence[float], bucket_sums: Sequence[float],
    scenario: CorrelationScenario,
) -> tuple[float, bool]:
    """MAR21.4(5), including the alternative specification for a negative root."""
    gamma = scenario_correlation(GIRR_INTER_BUCKET_CORRELATION, scenario)
    s_values = list(bucket_sums)
    total = sum(k * k for k in bucket_capitals)
    for i, s_i in enumerate(s_values):
        for j, s_j in enumerate(s_values):
            if i != j:
                total += gamma * s_i * s_j
    if total >= 0:
        return math.sqrt(total), False
    # MAR21.4(5)(b): recompute with S_b = max(min(sum WS, K_b), -K_b).
    adjusted = [max(min(s, k), -k) for s, k in zip(s_values, bucket_capitals)]
    total = sum(k * k for k in bucket_capitals)
    for i, s_i in enumerate(adjusted):
        for j, s_j in enumerate(adjusted):
            if i != j:
                total += gamma * s_i * s_j
    return math.sqrt(max(0.0, total)), True


def compute_girr_capital(
    book: CompiledBook, par: ParCurve, currency: str = "USD",
    include_curvature: bool = True, bump_bp: float = 1.0,
) -> GirrCapital:
    if currency != "USD":
        raise unsupported_scope(
            "UNSUPPORTED_REGULATORY_SCOPE",
            f"this system holds only US dollar instruments; a GIRR bucket for "
            f"{currency} has no sensitivities to aggregate.",
            "Compute GIRR for USD, or add instruments in the other currency "
            "along with its yield curve.")

    base_value, krd_totals, _ = key_rate_exposures(book, par, bump_bp)
    allocated, provenance, node_range = map_to_vertices(krd_totals)

    vertices = tuple(
        VertexSensitivity(
            vertex_years=v, risk_weight=GIRR_DELTA_RISK_WEIGHTS[v],
            sensitivity=allocated[v],
            weighted_sensitivity=GIRR_DELTA_RISK_WEIGHTS[v] * allocated[v],
            sourced_from_curve_nodes=tuple(provenance[v]))
        for v in GIRR_VERTICES_YEARS)

    weighted = [(v.vertex_years, v.weighted_sensitivity) for v in vertices]
    sum_ws = sum(ws for _, ws in weighted)

    scenario_results: list[ScenarioResult] = []
    for scenario in SCENARIOS:
        k_b, under_root, floored = _bucket_capital(weighted, scenario)
        delta, alternative = _across_buckets([k_b], [sum_ws], scenario)
        scenario_results.append(ScenarioResult(
            scenario=scenario, bucket_capital=k_b, delta_capital=delta,
            sum_under_root=under_root, floored_at_zero=floored,
            used_alternative_specification=alternative))

    binding = max(scenario_results, key=lambda r: r.delta_capital)

    curvature = None
    if include_curvature:
        shock_bp = GIRR_CURVATURE_RISK_WEIGHT * 10_000.0
        value_up = book.value_under(par.shifted(shock_bp))
        value_down = book.value_under(par.shifted(-shock_bp))
        delta_offset = GIRR_CURVATURE_RISK_WEIGHT * sum(v.sensitivity for v in vertices)
        cvr_up = -(value_up - base_value - delta_offset)
        cvr_down = -(value_down - base_value + delta_offset)
        capital = max(cvr_up, cvr_down, 0.0)
        convex = cvr_up < 0 and cvr_down < 0
        curvature = CurvatureResult(
            risk_weight=GIRR_CURVATURE_RISK_WEIGHT, shock_bp=shock_bp,
            base_value=base_value, value_up=value_up, value_down=value_down,
            delta_offset=delta_offset, cvr_up=cvr_up, cvr_down=cvr_down,
            bucket_capital=capital, book_is_positively_convex=convex,
            interpretation=(
                "Both CVR values are negative, so the curvature charge floors at "
                "zero. That is the correct result for a positively convex book: "
                "full revaluation loses less than the delta approximation "
                "predicts in both directions, and Basel does not credit the "
                "benefit."
                if convex else
                "At least one CVR is positive, meaning full revaluation loses "
                "MORE than the delta approximation in that direction. For a "
                "portfolio of conventional bonds that is unexpected and worth "
                "investigating before the number is used."))

    unsupported = tuple(name for name, ok in RISK_CLASS_SUPPORT.items() if not ok)
    return GirrCapital(
        currency=currency, bucket=f"GIRR bucket: {currency} risk-free curve",
        base_value=base_value, vertices=vertices, unmapped_curve_nodes=node_range,
        scenarios=tuple(scenario_results), delta_capital=binding.delta_capital,
        binding_scenario=binding.scenario, curvature=curvature,
        total_capital=binding.delta_capital + (curvature.bucket_capital
                                               if curvature else 0.0),
        vega_capital=None, unsupported_risk_classes=unsupported,
        unsupported_reason=UNSUPPORTED_REASON,
    )
