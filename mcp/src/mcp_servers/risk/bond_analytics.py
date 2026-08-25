"""Single-bond analytics.  `icma_quasi_period_analytics_v1`

`pricing.py` answers "what is this worth". This module answers the questions a
trader asks next: what yield is that, how long is it, how convex, and what does
the accrued split look like.

Two conventions run through everything here and both are load-bearing.

**Time is measured in quasi-coupon periods, not calendar days.** The exponent on
a cash flow is `n_i = i + 1 - w`, exactly the basis `pricing.py` discounts on and
exactly the basis the bootstrap in `curves.py` was built for. A yield solved on
one basis and a price computed on another disagree by a few basis points, which
is small enough to survive review and large enough to matter on a 30-year bond.

**Yield-based and curve-based measures are different measures.** Macaulay,
modified duration and convexity here are derived from the *bond's own yield to
maturity* - a single-rate approximation. Effective duration and effective
convexity come from bumping the *par curve* and repricing in full. They do not
have to agree, and where they diverge the divergence is information about curve
shape, not an error. Both are returned, both are labelled, and neither is
presented as "the" duration.

The clean/dirty split is a real split, not a relabelling: accrued interest is
computed from the same `w` that places the cash flows, so

    clean price + accrued interest = dirty price

holds to floating-point exactly rather than approximately. `pricing.py`
deliberately returns only the dirty value; this module is where the accrued half
is actually computed, so the identity is checkable.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass

from .curves import CurveError, ParCurve, build_discount_curve
from .errors import EngineError
from .numerics import BracketError, solve_scalar
from .pricing import FixedRateBond, current_quasi_period, generate_cash_flows

# The yield search interval, in decimal. Wide enough for every environment the
# Treasury history contains (including the 1981 long end and 2020's zero front
# end) and bounded, so an un-priceable input fails as "no yield in [-50%, 200%]"
# rather than wandering.
YTM_SEARCH_LOW = -0.5
YTM_SEARCH_HIGH = 2.0
DEFAULT_EFFECTIVE_BUMP_BP = 25.0


@dataclass(frozen=True)
class BondAnalytics:
    instrument_id: str
    valuation_date: dt.date
    face_notional: float
    cash_flow_count: int
    settlement_in_period: float

    present_value: float
    accrued_interest: float
    clean_value: float
    dirty_price_per_100: float
    clean_price_per_100: float
    accrued_per_100: float

    ytm_percent: float
    ytm_converged: bool
    ytm_iterations: int
    current_yield_percent: float | None

    macaulay_duration_years: float
    modified_duration_years: float
    dollar_duration: float
    analytic_dv01: float
    convexity: float

    effective_duration_years: float
    effective_convexity: float
    effective_bump_bp: float


@dataclass(frozen=True)
class PriceApproximation:
    shock_bp: float
    actual_pnl: float
    duration_only_pnl: float
    duration_convexity_pnl: float
    duration_only_error: float
    duration_convexity_error: float


def accrued_interest(bond: FixedRateBond, valuation_date: dt.date,
                     face_notional: float | None = None) -> float:
    """Coupon earned but not yet paid, on the ACT/ACT ICMA quasi-coupon basis."""
    period = current_quasi_period(bond, valuation_date)
    if period is None:
        return 0.0
    scale = (face_notional if face_notional is not None else bond.face_value)
    return period.coupon_amount * period.elapsed_fraction / bond.face_value * scale


def _periods_and_amounts(bond: FixedRateBond,
                         valuation_date: dt.date) -> tuple[list[float], list[float]]:
    """Cash flows as (exponent in coupon periods, amount)."""
    flows = generate_cash_flows(bond, valuation_date)
    f = float(bond.coupon_frequency)
    return [cf.time_years * f for cf in flows], [cf.amount for cf in flows]


def price_from_yield(bond: FixedRateBond, valuation_date: dt.date,
                     ytm_decimal: float, face_notional: float | None = None) -> float:
    """Discount every remaining flow at a single yield. The YTM definition."""
    periods, amounts = _periods_and_amounts(bond, valuation_date)
    z = 1.0 + ytm_decimal / bond.coupon_frequency
    if z <= 0.0:
        raise EngineError(
            "SOLVER_DID_NOT_CONVERGE",
            f"a yield of {ytm_decimal:.4%} makes the semiannual compounding "
            "factor non-positive; no price is defined there",
            category="NUMERICAL",
            suggested_action="Narrow the yield search bounds.",
        )
    scale = (face_notional if face_notional is not None else bond.face_value)
    gross = sum(a * z ** (-n) for n, a in zip(periods, amounts))
    return gross / bond.face_value * scale


def yield_to_maturity(
    bond: FixedRateBond, valuation_date: dt.date, dirty_value: float,
    face_notional: float | None = None,
    low: float = YTM_SEARCH_LOW, high: float = YTM_SEARCH_HIGH,
    tolerance: float = 1e-12,
) -> tuple[float, bool, int]:
    """Solve for the single yield that reproduces `dirty_value`.

    Returns (yield as a decimal, converged, iterations). Convergence is reported
    rather than assumed: a bond whose price implies a yield outside the search
    interval is a real occurrence, and answering with the interval's edge would
    be a fabricated number wearing a solved number's clothes.
    """
    if not _has_flows(bond, valuation_date):
        raise _matured(bond, valuation_date)
    scale = (face_notional if face_notional is not None else bond.face_value)
    if dirty_value <= 0.0:
        raise EngineError(
            "SOLVER_DID_NOT_CONVERGE",
            f"{bond.instrument_id}: a non-positive price ({dirty_value:.4f}) has "
            "no yield to maturity under this cash-flow convention",
            category="NUMERICAL",
            suggested_action="Check the curve and the notional before re-running.",
        )
    try:
        result = solve_scalar(
            lambda y: price_from_yield(bond, valuation_date, y, scale),
            low, high, target=dirty_value, tolerance=tolerance,
        )
    except BracketError as exc:
        raise EngineError(
            "SOLVER_DID_NOT_CONVERGE",
            f"{bond.instrument_id}: no yield in [{low:.2%}, {high:.2%}] reprices "
            f"this bond to {dirty_value:,.4f}. {exc}",
            category="NUMERICAL",
            suggested_action=(
                "Widen the yield search bounds, or check that the price and the "
                "instrument belong together."),
        ) from exc
    return result.root, result.converged, result.iterations


def _has_flows(bond: FixedRateBond, valuation_date: dt.date) -> bool:
    return current_quasi_period(bond, valuation_date) is not None


def _matured(bond: FixedRateBond, valuation_date: dt.date) -> EngineError:
    return EngineError(
        "NO_REMAINING_CASH_FLOWS",
        f"{bond.instrument_id} matured on {bond.maturity_date} and has no cash "
        f"flows remaining at {valuation_date}. Yield, duration and convexity are "
        "undefined for it - they are not zero.",
        category="USER_INPUT",
        suggested_action=(
            "Value the bond before its maturity date, or drop it from the "
            "analytics request."),
        details={"instrument_id": bond.instrument_id,
                 "maturity_date": bond.maturity_date.isoformat()},
    )


def yield_based_measures(
    bond: FixedRateBond, valuation_date: dt.date, ytm_decimal: float,
) -> tuple[float, float, float]:
    """(Macaulay years, modified years, convexity years-squared) at a given yield.

    In coupon-period units with z = 1 + y/f and n the period exponent:

        P        = sum CF_n z^-n
        Macaulay = sum (n/f) CF_n z^-n / P
        Modified = Macaulay / z
        Convexity= sum n(n+1) CF_n z^-n / (P z^2 f^2)

    Convexity is returned in **years squared**, matched to the approximation
    dP/P = -D_mod dy + (1/2) C dy^2 with dy in decimal. Engines that report it
    in period-squared units differ from this one by a factor of f-squared, which
    is precisely why the unit is in the manifest.
    """
    periods, amounts = _periods_and_amounts(bond, valuation_date)
    f = float(bond.coupon_frequency)
    z = 1.0 + ytm_decimal / f
    discounted = [a * z ** (-n) for n, a in zip(periods, amounts)]
    price = sum(discounted)
    if price <= 0:
        raise EngineError(
            "SOLVER_DID_NOT_CONVERGE",
            "duration is undefined at a non-positive price",
            category="NUMERICAL",
        )
    macaulay = sum(n / f * d for n, d in zip(periods, discounted)) / price
    modified = macaulay / z
    convexity = (sum(n * (n + 1) * d for n, d in zip(periods, discounted))
                 / (price * z * z * f * f))
    return macaulay, modified, convexity


def effective_measures(
    bond: FixedRateBond, valuation_date: dt.date, par: ParCurve,
    face_notional: float | None = None, bump_bp: float = DEFAULT_EFFECTIVE_BUMP_BP,
) -> tuple[float, float, float]:
    """(effective duration, effective convexity, base value) by full revaluation.

    Central difference on a parallel shift of the **par** curve, rebootstrapped
    each side. A one-sided difference would embed the bond's convexity in its
    duration; the central difference separates them, which is the point of
    computing both.
    """
    from .pricing import price_bond

    dy = bump_bp / 10_000.0
    base = price_bond(bond, valuation_date, build_discount_curve(par),
                      face_notional).present_value
    try:
        up = price_bond(bond, valuation_date, build_discount_curve(par.shifted(bump_bp)),
                        face_notional).present_value
        down = price_bond(bond, valuation_date,
                          build_discount_curve(par.shifted(-bump_bp)),
                          face_notional).present_value
    except CurveError as exc:
        # Near the zero bound a symmetric bump is simply not available: a 25bp
        # down-shift of a curve trading at 10bp lands below zero, where this
        # bootstrap's no-negative-forward guard refuses to build. That is a
        # limitation worth stating rather than a crash worth propagating, and
        # the fix is a smaller bump rather than a different engine.
        lowest = min(par.rates_percent)
        raise EngineError(
            "INVALID_CURVE",
            f"a {bump_bp:g}bp central difference cannot be taken on this curve: "
            f"its lowest par rate is {lowest:g}% and the down-shift leaves "
            f"territory the bootstrap can represent ({exc}).",
            category="NUMERICAL",
            suggested_action=(
                f"Use an effective_bump_bp below {max(0.0, lowest) * 100.0:g} so "
                "the down-shift stays non-negative, or read the yield-based "
                "duration and convexity, which do not shift the curve."),
            details={"effective_bump_bp": bump_bp,
                     "lowest_par_rate_percent": lowest},
        ) from exc
    if base <= 0:
        raise EngineError(
            "SOLVER_DID_NOT_CONVERGE",
            "effective duration is undefined at a non-positive base value",
            category="NUMERICAL")
    return ((down - up) / (2.0 * base * dy),
            (up + down - 2.0 * base) / (base * dy * dy),
            base)


def analyse_bond(
    bond: FixedRateBond, valuation_date: dt.date, par: ParCurve,
    face_notional: float | None = None,
    effective_bump_bp: float = DEFAULT_EFFECTIVE_BUMP_BP,
) -> BondAnalytics:
    period = current_quasi_period(bond, valuation_date)
    if period is None:
        raise _matured(bond, valuation_date)

    scale = (face_notional if face_notional is not None else bond.face_value)
    eff_duration, eff_convexity, pv = effective_measures(
        bond, valuation_date, par, scale, effective_bump_bp)

    accrued = accrued_interest(bond, valuation_date, scale)
    clean = pv - accrued
    per_100 = 100.0 / scale if scale else 0.0

    ytm, converged, iterations = yield_to_maturity(bond, valuation_date, pv, scale)
    macaulay, modified, convexity = yield_based_measures(bond, valuation_date, ytm)

    clean_per_100 = clean * per_100
    current_yield = (bond.coupon_rate_pct / clean_per_100 * 100.0
                     if clean_per_100 > 0 else None)

    return BondAnalytics(
        instrument_id=bond.instrument_id,
        valuation_date=valuation_date,
        face_notional=scale,
        cash_flow_count=len(period.remaining_flow_dates),
        settlement_in_period=period.elapsed_fraction,
        present_value=pv,
        accrued_interest=accrued,
        clean_value=clean,
        dirty_price_per_100=pv * per_100,
        clean_price_per_100=clean_per_100,
        accrued_per_100=accrued * per_100,
        ytm_percent=ytm * 100.0,
        ytm_converged=converged,
        ytm_iterations=iterations,
        current_yield_percent=current_yield,
        macaulay_duration_years=macaulay,
        modified_duration_years=modified,
        dollar_duration=modified * pv,
        analytic_dv01=modified * pv * 1e-4,
        convexity=convexity,
        effective_duration_years=eff_duration,
        effective_convexity=eff_convexity,
        effective_bump_bp=effective_bump_bp,
    )


def approximate_price_change(
    analytics: BondAnalytics, bond: FixedRateBond, valuation_date: dt.date,
    par: ParCurve, shock_bp: float,
) -> PriceApproximation:
    """Duration and duration+convexity estimates against the full revaluation.

    The comparison is the deliverable, not the estimates. A duration-only
    approximation that is tens of thousands adrift at 300bp is exactly the
    argument for revaluing in full, and the number makes the argument.

    **The measures used here are the effective ones, not the yield-based ones,
    and the pairing is not interchangeable.** The shock being approximated is a
    parallel shift of the *par curve*; modified duration and convexity describe
    the response to a shift in the bond's *own yield*. On a sloped curve those
    are different perturbations, and pairing a curve shock with a yield-based
    duration leaves a first-order bias that the convexity term then overshoots -
    making the "improved" approximation worse than the plain one at small
    shocks. Matching the measure to the shock removes that by construction.
    """
    from .pricing import price_bond

    dy = shock_bp / 10_000.0
    shocked = price_bond(bond, valuation_date,
                         build_discount_curve(par.shifted(shock_bp)),
                         analytics.face_notional).present_value
    actual = shocked - analytics.present_value
    duration_only = -analytics.effective_duration_years * dy * analytics.present_value
    with_convexity = (duration_only
                      + 0.5 * analytics.effective_convexity * dy * dy
                      * analytics.present_value)
    return PriceApproximation(
        shock_bp=shock_bp,
        actual_pnl=actual,
        duration_only_pnl=duration_only,
        duration_convexity_pnl=with_convexity,
        duration_only_error=duration_only - actual,
        duration_convexity_error=with_convexity - actual,
    )


def portfolio_rollup(analytics: Sequence[BondAnalytics]) -> dict[str, float]:
    """Value-weighted duration and convexity across a book.

    Weighted by present value because duration is a percentage sensitivity: a
    notional-weighted average of durations is not the duration of anything.
    """
    total = sum(a.present_value for a in analytics)
    if total == 0:
        return {"total_present_value": 0.0, "weighted_modified_duration_years": 0.0,
                "weighted_macaulay_duration_years": 0.0, "weighted_convexity": 0.0,
                "weighted_effective_duration_years": 0.0, "total_accrued_interest": 0.0,
                "total_analytic_dv01": 0.0}
    return {
        "total_present_value": total,
        "total_accrued_interest": sum(a.accrued_interest for a in analytics),
        "total_analytic_dv01": sum(a.analytic_dv01 for a in analytics),
        "weighted_macaulay_duration_years":
            sum(a.macaulay_duration_years * a.present_value for a in analytics) / total,
        "weighted_modified_duration_years":
            sum(a.modified_duration_years * a.present_value for a in analytics) / total,
        "weighted_convexity":
            sum(a.convexity * a.present_value for a in analytics) / total,
        "weighted_effective_duration_years":
            sum(a.effective_duration_years * a.present_value for a in analytics) / total,
    }
