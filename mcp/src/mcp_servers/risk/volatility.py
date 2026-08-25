"""How much rates move, and together.  `sample_stdev_of_absolute_bp_changes_v1`

This is rate volatility - the standard deviation of *observed changes in par
yields*, in basis points. It is not option-implied volatility, there is no
option in this system, and the two must never appear under one heading. Implied
vol is a price; this is a measurement.

Two conventions, both load-bearing:

**Absolute, not relative.** Changes are measured in basis points, not as
percentage changes in the yield. A relative measure is unusable at the zero
bound - the front end genuinely printed 0.00% in 2020 and 2021, and a
proportional change against zero is either infinite or undefined. Every
covariance and every simulation in this engine is therefore in basis-point
space.

**Sample standard deviation, Bessel-corrected, no mean removal shortcut.** With
250 observations the difference between dividing by N and by N-1 is 0.2% of the
variance, which is small; naming which one was used costs nothing and removes an
entire class of "our numbers differ slightly" conversation.

Rolling windows are reported at 20, 60 and 250 days because those are the
horizons a rates desk actually watches, and because the ratio between them is
the regime signal: a 20-day vol at twice the 250-day vol is the definition of a
volatile period, and `find_high_volatility_window` uses exactly that.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .errors import EngineError
from .linalg import Matrix, correlation_from_covariance, is_positive_semidefinite
from .numerics import sample_stdev

TRADING_DAYS_PER_YEAR = 252
DEFAULT_ROLLING_WINDOWS = (20, 60, 250)


@dataclass(frozen=True)
class TenorVolatility:
    tenor_years: float
    observations: int
    mean_change_bp: float
    stdev_bp: float
    annualised_stdev_bp: float
    min_change_bp: float
    max_change_bp: float
    rolling: dict[str, float | None]


@dataclass(frozen=True)
class VolatilityRegime:
    start_index: int
    end_index: int
    window_days: int
    average_stdev_bp: float
    ratio_to_full_sample: float


@dataclass(frozen=True)
class RateVolatility:
    tenors_years: tuple[float, ...]
    horizon_days: int
    change_count: int
    per_tenor: tuple[TenorVolatility, ...]
    covariance_bp2: Matrix
    correlation: Matrix
    covariance_is_psd: bool
    highest_volatility_window: VolatilityRegime | None
    calmest_window: VolatilityRegime | None
    method: str = "sample_stdev_of_absolute_bp_changes_v1"


def observed_changes_bp(
    rates_percent: Sequence[Sequence[float]], horizon_days: int = 1,
) -> list[list[float]]:
    """Observed h-day changes per tenor, in basis points.

    Overlapping windows when h > 1, which is the standard historical-simulation
    convention and the reason a 10-day figure here is not a 1-day figure scaled.
    Overlap makes successive observations dependent - it does not make them
    wrong, and the alternative (non-overlapping windows) throws away nine tenths
    of a year of history to buy independence nobody uses.
    """
    rows = [list(map(float, r)) for r in rates_percent]
    n = len(rows)
    if horizon_days < 1:
        raise EngineError(
            "INVALID_HORIZON", f"horizon_days must be at least 1; got {horizon_days}",
            category="USER_INPUT")
    if n < horizon_days + 2:
        raise EngineError(
            "INSUFFICIENT_HISTORY",
            f"{n} observations cannot produce {horizon_days}-day changes; at "
            f"least {horizon_days + 2} are needed.",
            category="DATA_AVAILABILITY", retryable=True,
            suggested_action=f"Request at least {horizon_days + 2} trading days.")
    width = len(rows[0])
    if any(len(r) != width for r in rows):
        raise EngineError(
            "INSUFFICIENT_HISTORY",
            "the history matrix is ragged: every row must cover every tenor",
            category="DATA_AVAILABILITY")
    return [[(rows[i][j] - rows[i - horizon_days][j]) * 100.0 for j in range(width)]
            for i in range(horizon_days, n)]


def covariance_matrix(changes: Sequence[Sequence[float]]) -> Matrix:
    """Sample covariance of the change vectors, in basis points squared."""
    n = len(changes)
    if n < 2:
        raise EngineError(
            "INSUFFICIENT_HISTORY",
            f"a covariance needs at least two observations; got {n}",
            category="DATA_AVAILABILITY")
    width = len(changes[0])
    means = [sum(row[j] for row in changes) / n for j in range(width)]
    return [[sum((row[i] - means[i]) * (row[j] - means[j]) for row in changes) / (n - 1)
             for j in range(width)] for i in range(width)]


def _rolling_stdev(series: Sequence[float], window: int) -> float | None:
    if len(series) < window:
        return None
    return sample_stdev(list(series[-window:]))


def find_high_volatility_window(
    changes: Sequence[Sequence[float]], window_days: int = 60,
    calmest: bool = False,
) -> VolatilityRegime | None:
    """The window whose average cross-tenor volatility is highest (or lowest).

    Average across tenors rather than the volatility of any single one, because
    a regime is a property of the curve: March 2020 was not "the 10-year was
    volatile", it was everything at once.
    """
    n = len(changes)
    if n < window_days or window_days < 2:
        return None
    width = len(changes[0])
    full = [sample_stdev([row[j] for row in changes]) for j in range(width)]
    full_average = sum(full) / width if width else 0.0

    best_index, best_value = 0, None
    for start in range(n - window_days + 1):
        block = changes[start:start + window_days]
        value = sum(sample_stdev([row[j] for row in block])
                    for j in range(width)) / width
        if best_value is None or (value < best_value if calmest else value > best_value):
            best_index, best_value = start, value
    return VolatilityRegime(
        start_index=best_index, end_index=best_index + window_days - 1,
        window_days=window_days, average_stdev_bp=best_value or 0.0,
        ratio_to_full_sample=((best_value / full_average) if full_average else 0.0),
    )


def compute_rate_volatility(
    tenors_years: Sequence[float], rates_percent: Sequence[Sequence[float]],
    horizon_days: int = 1, rolling_windows: Sequence[int] = DEFAULT_ROLLING_WINDOWS,
    regime_window_days: int = 60,
) -> RateVolatility:
    changes = observed_changes_bp(rates_percent, horizon_days)
    width = len(tenors_years)
    if changes and len(changes[0]) != width:
        raise EngineError(
            "INSUFFICIENT_HISTORY",
            f"{len(changes[0])} rate columns were supplied for {width} tenors",
            category="USER_INPUT",
            suggested_action="Pass one tenor per column of the rate matrix.")

    per_tenor = []
    for j, tenor in enumerate(tenors_years):
        series = [row[j] for row in changes]
        sd = sample_stdev(series)
        per_tenor.append(TenorVolatility(
            tenor_years=float(tenor), observations=len(series),
            mean_change_bp=sum(series) / len(series) if series else 0.0,
            stdev_bp=sd,
            annualised_stdev_bp=sd * math.sqrt(TRADING_DAYS_PER_YEAR / horizon_days),
            min_change_bp=min(series) if series else 0.0,
            max_change_bp=max(series) if series else 0.0,
            rolling={f"stdev_bp_{w}d": _rolling_stdev(series, w)
                     for w in rolling_windows},
        ))

    cov = covariance_matrix(changes)
    return RateVolatility(
        tenors_years=tuple(float(t) for t in tenors_years),
        horizon_days=horizon_days, change_count=len(changes),
        per_tenor=tuple(per_tenor), covariance_bp2=cov,
        correlation=correlation_from_covariance(cov),
        covariance_is_psd=is_positive_semidefinite(cov),
        highest_volatility_window=find_high_volatility_window(
            changes, regime_window_days),
        calmest_window=find_high_volatility_window(
            changes, regime_window_days, calmest=True),
    )


def regime_changes(
    changes: Sequence[Sequence[float]], regime: VolatilityRegime,
) -> list[list[float]]:
    """The observed change vectors inside a detected regime window."""
    return [list(r) for r in changes[regime.start_index:regime.end_index + 1]]


def scale_covariance(cov: Matrix, multiplier: float) -> Matrix:
    """Scale a covariance matrix by a volatility multiplier (applied to sigma).

    The multiplier is on the *standard deviation*, so a 2x volatility scenario
    multiplies the covariance by 4. Stating this is not pedantry: applying the
    multiplier to the covariance instead produces a 1.41x volatility scenario
    labelled 2x, and the resulting VaR is 30% too small.
    """
    if multiplier <= 0:
        raise EngineError(
            "INVALID_COVARIANCE_MATRIX",
            f"the volatility multiplier must be positive; got {multiplier}",
            category="USER_INPUT")
    factor = multiplier * multiplier
    return [[value * factor for value in row] for row in cov]
