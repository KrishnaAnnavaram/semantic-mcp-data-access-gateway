"""Sensitivities, stress and historical risk. All by full revaluation.

Full revaluation throughout - bump the par curve, rebuild the discount curve,
reprice every cash flow. Slower than an analytic approximation and correct in
the presence of convexity, which is the whole point of computing risk on a
30-year bond.

Sign conventions, stated once:

* **DV01** is positive for a conventional long fixed-rate position: rates up,
  value down, so DV01 = V_base - V_up.
* **P&L** is signed: negative is a loss.
* **Loss** is -P&L, so VaR and ES are reported as positive numbers.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Sequence

from .curves import ParCurve, build_discount_curve
from .pricing import Position, price_portfolio


class RiskError(ValueError):
    """The requested calculation cannot be performed truthfully."""


@dataclass(frozen=True)
class Dv01Result:
    base_value: float
    bumped_value: float
    dv01: float
    bump_bp: float
    per_position: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class KeyRateResult:
    base_value: float
    bump_bp: float
    key_rate_dv01: tuple[tuple[float, float], ...]  # (tenor_years, dv01)
    total: float


@dataclass(frozen=True)
class StressResult:
    base_value: float
    stressed_value: float
    pnl: float
    per_position: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class HistoricalRiskResult:
    base_value: float
    confidence_level: float
    horizon_days: int
    scenarios_used: int
    var: float
    expected_shortfall: float
    worst_loss: float
    best_pnl: float
    var_scenario_index: int
    pnl_distribution_summary: dict[str, float]


def _value(positions: Sequence[Position], valuation_date: dt.date, par: ParCurve) -> float:
    return price_portfolio(positions, valuation_date, build_discount_curve(par)).total_present_value


def compute_dv01(
    positions: Sequence[Position], valuation_date: dt.date, par: ParCurve,
    bump_bp: float = 1.0,
) -> Dv01Result:
    base = price_portfolio(positions, valuation_date, build_discount_curve(par))
    bumped = price_portfolio(positions, valuation_date,
                             build_discount_curve(par.shifted(bump_bp)))
    per = tuple((b.instrument_id, b0.present_value - b.present_value)
                for b0, b in zip(base.positions, bumped.positions))
    return Dv01Result(
        base_value=base.total_present_value,
        bumped_value=bumped.total_present_value,
        dv01=base.total_present_value - bumped.total_present_value,
        bump_bp=bump_bp,
        per_position=per,
    )


def compute_key_rate_dv01(
    positions: Sequence[Position], valuation_date: dt.date, par: ParCurve,
    key_tenors_years: Sequence[float] | None = None, bump_bp: float = 1.0,
) -> KeyRateResult:
    """Bump exactly one par node at a time - no tent, no smoothing.

    The alternative (a triangular shape spread over neighbouring tenors) is
    common but requires stating the shape to be reproducible. A single-node bump
    is unambiguous, and the perturbation applied is exactly what the name says.
    """
    tenors = list(key_tenors_years) if key_tenors_years else list(par.tenors_years)
    unknown = [t for t in tenors if t not in par.tenors_years]
    if unknown:
        raise RiskError(
            f"key tenors {unknown} are not nodes on this curve; bumping a "
            f"non-node would perturb an interpolated value. Nodes: "
            f"{list(par.tenors_years)}")
    base = _value(positions, valuation_date, par)
    krd = tuple(
        (t, base - _value(positions, valuation_date, par.shocked({t: bump_bp})))
        for t in tenors
    )
    return KeyRateResult(base_value=base, bump_bp=bump_bp,
                         key_rate_dv01=krd, total=sum(v for _, v in krd))


def run_stress(
    positions: Sequence[Position], valuation_date: dt.date, par: ParCurve,
    shocks_bp_by_tenor_years: dict[float, float],
) -> StressResult:
    base = price_portfolio(positions, valuation_date, build_discount_curve(par))
    shocked_par = par.shocked(shocks_bp_by_tenor_years)
    stressed = price_portfolio(positions, valuation_date, build_discount_curve(shocked_par))
    per = tuple((s.instrument_id, s.present_value - b.present_value)
                for b, s in zip(base.positions, stressed.positions))
    return StressResult(
        base_value=base.total_present_value,
        stressed_value=stressed.total_present_value,
        pnl=stressed.total_present_value - base.total_present_value,
        per_position=per,
    )


def nearest_rank_quantile(sorted_ascending: Sequence[float], alpha: float) -> tuple[float, int]:
    """k = ceil(alpha * N), 1-indexed. Returns (value, zero-based index).

    Named and pinned because percentile implementations genuinely differ: NumPy
    offers nine interpolation methods and its default is not this one. Two
    engines both reporting "99% VaR" can disagree purely on this choice, so the
    convention is part of the model definition rather than a library default.
    """
    n = len(sorted_ascending)
    if n == 0:
        raise RiskError("no scenarios to take a quantile of")
    k = math.ceil(alpha * n)
    k = max(1, min(k, n))
    return sorted_ascending[k - 1], k - 1


def compute_historical_risk(
    positions: Sequence[Position],
    valuation_date: dt.date,
    current_par: ParCurve,
    history_tenors_years: Sequence[float],
    history_rates_percent: Sequence[Sequence[float]],
    confidence_level: float = 0.99,
    horizon_days: int = 1,
) -> HistoricalRiskResult:
    """Historical simulation VaR and Expected Shortfall by full revaluation.

    1. Take observed h-day absolute changes in par yields, per tenor.
    2. Add each change vector to today's curve.
    3. Rebuild the discount curve and reprice the book under each.
    4. VaR is the nearest-rank quantile of the loss distribution; ES is the mean
       of losses at or beyond it.

    h-day changes are *observed over h days*, never a 1-day figure scaled by
    sqrt(h). The scaling shortcut assumes independent, identically distributed
    returns, which rate moves are not - it understates exactly the clustered,
    trending episodes a risk number exists to capture.

    Both VaR and ES come from one revaluation pass. Computing them separately
    would double the work and risk them disagreeing about the same distribution.
    """
    if not 0.5 <= confidence_level < 1.0:
        raise RiskError(f"confidence_level {confidence_level} outside (0.5, 1.0)")
    if horizon_days < 1:
        raise RiskError("horizon_days must be at least 1")

    rows = [list(map(float, r)) for r in history_rates_percent]
    n_obs = len(rows)
    if n_obs < horizon_days + 2:
        raise RiskError(
            f"{n_obs} observations cannot produce {horizon_days}-day changes; "
            f"at least {horizon_days + 2} are needed")
    width = len(history_tenors_years)
    if any(len(r) != width for r in rows):
        raise RiskError("history matrix is ragged: every row must cover every tenor")

    # Observed h-day changes, per tenor.
    shocks: list[list[float]] = [
        [rows[i][j] - rows[i - horizon_days][j] for j in range(width)]
        for i in range(horizon_days, n_obs)
    ]
    if not shocks:
        raise RiskError("no scenarios could be formed from the supplied history")

    base = price_portfolio(positions, valuation_date,
                           build_discount_curve(current_par)).total_present_value

    pnls: list[float] = []
    for shock in shocks:
        shocked = current_par.shocked(
            {float(t): shock[j] * 100.0  # percent -> basis points
             for j, t in enumerate(history_tenors_years)}
        )
        pnls.append(_value(positions, valuation_date, shocked) - base)

    losses = sorted(-p for p in pnls)
    var, idx = nearest_rank_quantile(losses, confidence_level)
    var = max(0.0, var)
    tail = [loss for loss in losses if loss >= var]
    es = sum(tail) / len(tail) if tail else var

    return HistoricalRiskResult(
        base_value=base,
        confidence_level=confidence_level,
        horizon_days=horizon_days,
        scenarios_used=len(pnls),
        var=var,
        expected_shortfall=es,
        worst_loss=max(losses),
        best_pnl=max(pnls),
        var_scenario_index=idx,
        pnl_distribution_summary={
            "mean_pnl": sum(pnls) / len(pnls),
            "min_pnl": min(pnls),
            "max_pnl": max(pnls),
            "losses_beyond_var": float(len(tail)),
        },
    )
