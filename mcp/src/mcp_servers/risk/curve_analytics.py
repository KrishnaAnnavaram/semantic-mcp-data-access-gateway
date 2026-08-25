"""Reading a curve.  `bootstrapped_zero_forward_v1`

Four different numbers get called "the rate" and confusing any two of them is
the defining error of this subject:

| name         | what it is                                                    |
|--------------|---------------------------------------------------------------|
| par yield    | the coupon a bond needs to trade at 100 - what Treasury prints |
| discount factor | the price today of one dollar at time t                    |
| zero rate    | the single rate that discounts one cash flow at time t         |
| forward rate | the rate contracted today for a future interval                |

They coincide only on a flat curve, which is why a mistake here survives every
smoke test. Every function below names which of the four it returns, and the
zero and forward rates are derived from the **bootstrapped** discount curve
rather than from the par yields directly.

Two sign conventions, fixed here and pinned in the manifest because both have a
defensible opposite that other desks use:

* **Spread = long-tenor yield - short-tenor yield.** So `2s10s` is 10Y minus
  2Y, and a negative 2s10s means inversion. Reported in basis points.
* **Butterfly = 2 x belly - short wing - long wing.** So `2s10s30s` is
  2 x 10Y - 2Y - 30Y. Positive means the belly is cheap relative to the wings.
  Reported in basis points.

**No silent extrapolation.** A request for a 40-year point on a curve whose last
node is 30 years is refused unless extrapolation is asked for explicitly, and
then it is reported in `warnings`. `ParCurve.par_rate_at` holds the last rate
flat past the end, which is the right default for a bootstrap and the wrong
default for an analytics answer someone will quote.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .curves import DiscountCurve, ParCurve, build_discount_curve
from .errors import EngineError

# The standard Treasury spreads, as (short tenor years, long tenor years).
NAMED_SPREADS: dict[str, tuple[float, float]] = {
    "3m2s": (0.25, 2.0),
    "2s5s": (2.0, 5.0),
    "2s10s": (2.0, 10.0),
    "5s10s": (5.0, 10.0),
    "5s30s": (5.0, 30.0),
    "10s30s": (10.0, 30.0),
    "2s30s": (2.0, 30.0),
}

# (short wing, belly, long wing) in years.
NAMED_BUTTERFLIES: dict[str, tuple[float, float, float]] = {
    "2s5s10s": (2.0, 5.0, 10.0),
    "2s10s30s": (2.0, 10.0, 30.0),
    "5s10s30s": (5.0, 10.0, 30.0),
}


@dataclass(frozen=True)
class TenorPoint:
    tenor_years: float
    par_yield_percent: float
    discount_factor: float
    zero_rate_continuous_percent: float
    zero_rate_semiannual_percent: float
    is_node: bool
    is_extrapolated: bool


@dataclass(frozen=True)
class ForwardPoint:
    start_years: float
    end_years: float
    forward_continuous_percent: float
    forward_semiannual_percent: float


@dataclass(frozen=True)
class Spread:
    name: str
    short_tenor_years: float
    long_tenor_years: float
    short_yield_percent: float
    long_yield_percent: float
    spread_bp: float


@dataclass(frozen=True)
class Butterfly:
    name: str
    short_tenor_years: float
    belly_tenor_years: float
    long_tenor_years: float
    butterfly_bp: float


@dataclass(frozen=True)
class InversionDiagnostics:
    is_inverted_2s10s: bool
    inverted_segment_count: int
    total_segment_count: int
    deepest_inversion_bp: float
    deepest_inversion_segment: tuple[float, float] | None
    first_inverted_segment: tuple[float, float] | None


@dataclass(frozen=True)
class CurveShape:
    level_percent: float
    slope_bp: float
    curvature_bp: float
    steepest_segment_bp_per_year: float
    steepest_segment: tuple[float, float] | None


@dataclass(frozen=True)
class CurveAnalytics:
    tenor_points: tuple[TenorPoint, ...]
    forwards: tuple[ForwardPoint, ...]
    spreads: tuple[Spread, ...]
    butterflies: tuple[Butterfly, ...]
    inversion: InversionDiagnostics
    shape: CurveShape
    warnings: tuple[str, ...]


def _require_tenor(par: ParCurve, tenor_years: float, allow_extrapolation: bool,
                   what: str) -> bool:
    """True when the tenor sits outside the node range. Refuses unless permitted."""
    lo, hi = par.tenors_years[0], par.tenors_years[-1]
    outside = tenor_years < lo or tenor_years > hi
    if outside and not allow_extrapolation:
        raise EngineError(
            "MISSING_CURVE_TENOR",
            f"{what} needs {tenor_years:g}y but this curve runs from {lo:g}y to "
            f"{hi:g}y. Extrapolating would hold the end rate flat and report the "
            "result as though it had been observed.",
            category="DATA_AVAILABILITY",
            suggested_action=(
                "Request a tenor inside the curve, or pass "
                "allow_extrapolation=true to accept a flat-extrapolated value "
                "that will be listed in warnings."),
            details={"requested_tenor_years": tenor_years,
                     "curve_first_tenor_years": lo, "curve_last_tenor_years": hi},
        )
    return outside


def zero_rate_semiannual(curve: DiscountCurve, t: float) -> float:
    """Zero rate on a semiannual bond-equivalent basis, in percent.

    The same discount factor expressed the way a bond desk quotes it:
    D = (1 + z/2)^(-2t). Reported alongside the continuous rate because the two
    differ by roughly 5bp at 5% and neither is more correct than the other -
    only unlabelled ones are wrong.
    """
    if t <= 0:
        raise EngineError("INVALID_CURVE", "zero rate is undefined at t=0",
                          category="USER_INPUT")
    d = curve.discount_factor(t)
    return (d ** (-1.0 / (2.0 * t)) - 1.0) * 2.0 * 100.0


def implied_forward(curve: DiscountCurve, start_years: float,
                    end_years: float) -> ForwardPoint:
    """The rate contracted today for the interval [start, end].

    Continuously compounded: f = (ln D(t1) - ln D(t2)) / (t2 - t1). The
    semiannual equivalent is quoted next to it.
    """
    if end_years <= start_years:
        raise EngineError(
            "INVALID_CURVE",
            f"a forward interval must have positive length; got "
            f"[{start_years:g}, {end_years:g}]",
            category="USER_INPUT")
    d1 = curve.discount_factor(start_years)
    d2 = curve.discount_factor(end_years)
    span = end_years - start_years
    continuous = (math.log(d1) - math.log(d2)) / span
    semi = (math.exp(continuous / 2.0) - 1.0) * 2.0
    return ForwardPoint(start_years, end_years, continuous * 100.0, semi * 100.0)


def spread_bp(par: ParCurve, short_years: float, long_years: float) -> float:
    """Long-tenor yield minus short-tenor yield, in basis points."""
    return (par.par_rate_at(long_years) - par.par_rate_at(short_years)) * 100.0


def butterfly_bp(par: ParCurve, short_years: float, belly_years: float,
                 long_years: float) -> float:
    """2 x belly - short wing - long wing, in basis points."""
    return (2.0 * par.par_rate_at(belly_years)
            - par.par_rate_at(short_years)
            - par.par_rate_at(long_years)) * 100.0


def diagnose_inversion(par: ParCurve) -> InversionDiagnostics:
    """Where the curve slopes downward, segment by segment between nodes."""
    segments = list(zip(par.tenors_years, par.tenors_years[1:]))
    inverted: list[tuple[tuple[float, float], float]] = []
    for a, b in segments:
        move = (par.par_rate_at(b) - par.par_rate_at(a)) * 100.0
        if move < 0:
            inverted.append(((a, b), move))
    deepest = min(inverted, key=lambda x: x[1], default=None)
    has_2 = par.tenors_years[0] <= 2.0 <= par.tenors_years[-1]
    has_10 = par.tenors_years[0] <= 10.0 <= par.tenors_years[-1]
    return InversionDiagnostics(
        is_inverted_2s10s=(spread_bp(par, 2.0, 10.0) < 0) if (has_2 and has_10) else False,
        inverted_segment_count=len(inverted),
        total_segment_count=len(segments),
        deepest_inversion_bp=deepest[1] if deepest else 0.0,
        deepest_inversion_segment=deepest[0] if deepest else None,
        first_inverted_segment=inverted[0][0] if inverted else None,
    )


def describe_shape(par: ParCurve) -> CurveShape:
    """Level, slope and curvature - the three factors that explain most curve moves.

    Level is the mean of the observed nodes rather than a single tenor, so it
    does not move just because one point was added to the curve. Slope is the
    outermost spread and curvature the widest available butterfly.
    """
    rates = par.rates_percent
    level = sum(rates) / len(rates)
    lo, hi = par.tenors_years[0], par.tenors_years[-1]
    slope = spread_bp(par, lo, hi)
    mid = min(par.tenors_years, key=lambda t: abs(t - (lo + hi) / 2.0))
    curvature = butterfly_bp(par, lo, mid, hi)
    steepest, steepest_seg = 0.0, None
    for a, b in zip(par.tenors_years, par.tenors_years[1:]):
        per_year = (par.par_rate_at(b) - par.par_rate_at(a)) * 100.0 / (b - a)
        if abs(per_year) > abs(steepest):
            steepest, steepest_seg = per_year, (a, b)
    return CurveShape(level, slope, curvature, steepest, steepest_seg)


def analyse_curve(
    par: ParCurve,
    tenors_years: Sequence[float] | None = None,
    forward_intervals: Sequence[tuple[float, float]] | None = None,
    spread_names: Sequence[str] | None = None,
    butterfly_names: Sequence[str] | None = None,
    allow_extrapolation: bool = False,
) -> CurveAnalytics:
    curve = build_discount_curve(par)
    warnings: list[str] = []
    nodes = set(par.tenors_years)

    requested = list(tenors_years) if tenors_years else list(par.tenors_years)
    points: list[TenorPoint] = []
    for t in requested:
        extrapolated = _require_tenor(par, t, allow_extrapolation, f"tenor {t:g}y")
        if extrapolated:
            warnings.append(
                f"{t:g}y lies outside the curve's {par.tenors_years[0]:g}y-"
                f"{par.tenors_years[-1]:g}y range; the par rate was held flat and "
                "the discount factor extrapolated at the last observed forward.")
        points.append(TenorPoint(
            tenor_years=t,
            par_yield_percent=par.par_rate_at(t),
            discount_factor=curve.discount_factor(t),
            zero_rate_continuous_percent=curve.zero_rate(t),
            zero_rate_semiannual_percent=zero_rate_semiannual(curve, t),
            is_node=t in nodes,
            is_extrapolated=extrapolated,
        ))

    intervals = list(forward_intervals) if forward_intervals else _default_forwards(par)
    forwards = []
    for a, b in intervals:
        _require_tenor(par, b, allow_extrapolation, f"forward ending at {b:g}y")
        forwards.append(implied_forward(curve, a, b))

    spreads = []
    for name in (spread_names if spread_names is not None else NAMED_SPREADS):
        if name not in NAMED_SPREADS:
            raise EngineError(
                "INVALID_CURVE", f"unknown spread {name!r}",
                category="USER_INPUT",
                suggested_action=f"Choose from {sorted(NAMED_SPREADS)}.")
        short, long = NAMED_SPREADS[name]
        if not _within(par, short) or not _within(par, long):
            if spread_names is None:
                continue          # skip silently only for the default set
            _require_tenor(par, max(short, long), allow_extrapolation, name)
            _require_tenor(par, min(short, long), allow_extrapolation, name)
        spreads.append(Spread(
            name=name, short_tenor_years=short, long_tenor_years=long,
            short_yield_percent=par.par_rate_at(short),
            long_yield_percent=par.par_rate_at(long),
            spread_bp=spread_bp(par, short, long)))

    butterflies = []
    for name in (butterfly_names if butterfly_names is not None else NAMED_BUTTERFLIES):
        if name not in NAMED_BUTTERFLIES:
            raise EngineError(
                "INVALID_CURVE", f"unknown butterfly {name!r}",
                category="USER_INPUT",
                suggested_action=f"Choose from {sorted(NAMED_BUTTERFLIES)}.")
        short, belly, long = NAMED_BUTTERFLIES[name]
        if not all(_within(par, t) for t in (short, belly, long)):
            if butterfly_names is None:
                continue
            for t in (short, belly, long):
                _require_tenor(par, t, allow_extrapolation, name)
        butterflies.append(Butterfly(
            name=name, short_tenor_years=short, belly_tenor_years=belly,
            long_tenor_years=long,
            butterfly_bp=butterfly_bp(par, short, belly, long)))

    return CurveAnalytics(
        tenor_points=tuple(points), forwards=tuple(forwards),
        spreads=tuple(spreads), butterflies=tuple(butterflies),
        inversion=diagnose_inversion(par), shape=describe_shape(par),
        warnings=tuple(warnings),
    )


def _within(par: ParCurve, tenor_years: float) -> bool:
    return par.tenors_years[0] <= tenor_years <= par.tenors_years[-1]


def _default_forwards(par: ParCurve) -> list[tuple[float, float]]:
    """Consecutive node intervals, plus the classic 5y5y if the curve reaches it."""
    intervals = list(zip(par.tenors_years, par.tenors_years[1:]))
    if _within(par, 10.0) and _within(par, 5.0):
        intervals.append((5.0, 10.0))
    return intervals


def curve_change_bp(before: ParCurve, after: ParCurve,
                    tenors_years: Sequence[float] | None = None) -> dict[float, float]:
    """Observed change per tenor, in basis points. `after` minus `before`.

    This is the only way a historical shock enters the engine: it is *measured*
    from two curves that were actually published, never described.
    """
    tenors = (list(tenors_years) if tenors_years
              else sorted(set(before.tenors_years) & set(after.tenors_years)))
    if not tenors:
        raise EngineError(
            "MISSING_CURVE_TENOR",
            "the two curves share no tenor, so no change can be measured "
            f"between them. Before: {list(before.tenors_years)}. "
            f"After: {list(after.tenors_years)}.",
            category="DATA_AVAILABILITY",
            suggested_action="Fetch both curves on the same tenor set.")
    missing = [t for t in tenors
               if t not in set(before.tenors_years) or t not in set(after.tenors_years)]
    if missing:
        raise EngineError(
            "MISSING_CURVE_TENOR",
            f"tenors {missing} are not nodes on both curves; a change measured "
            "against an interpolated point is not an observed change.",
            category="DATA_AVAILABILITY",
            suggested_action="Restrict the tenor set to nodes present on both dates.")
    return {t: (after.par_rate_at(t) - before.par_rate_at(t)) * 100.0 for t in tenors}
