"""Was the VaR any good?  `exception_counting_strict_exceedance_v1`

A VaR number is a forecast, and a forecast that is never checked against
outcomes is an opinion with a decimal point. Backtesting is the only part of
market risk where the model can actually be shown wrong.

## What counts as an exception

`loss > VaR`, strictly. A day whose loss lands exactly on the forecast is not an
exception. The opposite convention is defensible and, on real data, almost never
changes the count - but "almost never" is not "never", and a synthetic test set
built to sit on the boundary will disagree under the two rules. So the rule is
named, tested at the boundary, and in the manifest.

## Which P&L

The result carries `pnl_kind` and it is not decoration:

* `ACTUAL` - the desk's realised P&L, including intraday trading, fees and new
  business. What the business earned.
* `HYPOTHETICAL` - the start-of-day portfolio revalued at end-of-day prices, with
  no intraday activity. What the *model* forecast, and what a coverage test is
  actually about.
* `MODEL_REVALUATION` - the same portfolio revalued by this engine under an
  observed curve move. Useful and further removed from the tape still.

Basel requires both actual and hypothetical backtesting for exactly this reason.
Labelling a hypothetical series "actual" is the most common way a backtest ends
up flattering: intraday risk reduction removes exceptions the model should have
been charged for.

## The three tests

* **Kupiec (1995) unconditional coverage.** Are there the right *number* of
  exceptions? `LR_uc ~ chi2(1)`.
* **Christoffersen (1998) independence.** Are exceptions *clustered*? A model
  with the right count that produces all of them in one week has not captured
  volatility clustering. Tested as a first-order Markov chain on the exception
  indicator; `LR_ind ~ chi2(1)`.
* **Conditional coverage.** `LR_cc = LR_uc + LR_ind ~ chi2(2)`. Both at once.

The chi-squared tail probabilities are computed exactly rather than looked up:
one degree of freedom gives `p = 2(1 - Phi(sqrt(x)))`, two gives
`p = exp(-x/2)`. No table, no interpolation, no dependency.

Degenerate cases are reported as not computable rather than as a pass. With
zero exceptions the independence test has no transitions to learn from, and a
`p`-value of 1.0 there would read as "independence confirmed" when the honest
answer is "nothing was tested".
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist
from typing import Literal

from .errors import EngineError

PnlKind = Literal["ACTUAL", "HYPOTHETICAL", "MODEL_REVALUATION"]

MINIMUM_OBSERVATIONS = 30
BASEL_TRAFFIC_LIGHT_OBSERVATIONS = 250
BASEL_TRAFFIC_LIGHT_CONFIDENCE = 0.99
# BCBS traffic-light zones for 250 observations at 99% (Basel framework,
# MAR99 / the 1996 backtesting amendment). Green 0-4, amber 5-9, red 10+.
BASEL_GREEN_MAX = 4
BASEL_AMBER_MAX = 9

_NORMAL = NormalDist(0.0, 1.0)


@dataclass(frozen=True)
class TestResult:
    name: str
    statistic: float | None
    degrees_of_freedom: int
    p_value: float | None
    rejected_at_5_percent: bool | None
    computable: bool
    note: str


@dataclass(frozen=True)
class Exception_:
    index: int
    date: dt.date | None
    var_forecast: float
    pnl: float
    loss: float
    excess: float


@dataclass(frozen=True)
class BacktestResult:
    observations: int
    confidence_level: float
    pnl_kind: PnlKind
    exceptions: int
    exception_rate: float
    expected_exceptions: float
    expected_exception_rate: float
    exception_dates: tuple[dt.date | None, ...]
    exception_detail: tuple[Exception_, ...]
    longest_exception_run: int
    exception_clusters: int
    mean_excess_loss: float
    worst_excess_loss: float
    kupiec: TestResult
    independence: TestResult
    conditional_coverage: TestResult
    basel_traffic_light: str | None
    basel_traffic_light_applicable: bool
    method: str = "exception_counting_strict_exceedance_v1"
    exception_rule: str = "an exception is a loss strictly greater than the VaR forecast"


def _chi2_sf(statistic: float, degrees_of_freedom: int) -> float:
    """Upper tail of a chi-squared, exactly, for the only two dof used here."""
    if statistic <= 0:
        return 1.0
    if degrees_of_freedom == 1:
        return 2.0 * (1.0 - _NORMAL.cdf(math.sqrt(statistic)))
    if degrees_of_freedom == 2:
        return math.exp(-statistic / 2.0)
    raise EngineError(  # pragma: no cover - only 1 and 2 dof are used
        "INSUFFICIENT_BACKTEST_DATA",
        f"no closed form is implemented for {degrees_of_freedom} degrees of freedom",
        category="NUMERICAL")


def _xlogy(count: float, probability: float) -> float:
    """count * log(probability), with the 0 * log(0) = 0 convention.

    The convention is not a fudge: it is the limit of the likelihood term as the
    count goes to zero, and without it a backtest with no exceptions raises a
    math domain error rather than reporting the perfectly meaningful answer
    "zero exceptions, and here is what that implies".
    """
    if count == 0:
        return 0.0
    if probability <= 0:
        return float("-inf")
    return count * math.log(probability)


def kupiec_unconditional_coverage(observations: int, exceptions: int,
                                  confidence_level: float) -> TestResult:
    """Kupiec's proportion-of-failures test. LR ~ chi2(1)."""
    p = 1.0 - confidence_level
    n, x = observations, exceptions
    if n == 0:
        return TestResult("kupiec_unconditional_coverage", None, 1, None, None,
                          False, "no observations")
    observed_rate = x / n
    log_null = _xlogy(n - x, 1.0 - p) + _xlogy(x, p)
    log_alt = _xlogy(n - x, 1.0 - observed_rate) + _xlogy(x, observed_rate)
    statistic = -2.0 * (log_null - log_alt)
    statistic = max(0.0, statistic)
    p_value = _chi2_sf(statistic, 1)
    return TestResult(
        "kupiec_unconditional_coverage", statistic, 1, p_value, p_value < 0.05, True,
        f"tests whether {x} exceptions in {n} days is consistent with a "
        f"{confidence_level:.1%} model, which expects {n * p:.2f}")


def christoffersen_independence(indicators: Sequence[int]) -> TestResult:
    """Christoffersen's Markov independence test on the exception series. LR ~ chi2(1)."""
    n00 = n01 = n10 = n11 = 0
    for previous, current in zip(indicators, indicators[1:]):
        if previous == 0 and current == 0:
            n00 += 1
        elif previous == 0 and current == 1:
            n01 += 1
        elif previous == 1 and current == 0:
            n10 += 1
        else:
            n11 += 1

    total = n00 + n01 + n10 + n11
    if total == 0:
        return TestResult("christoffersen_independence", None, 1, None, None, False,
                          "fewer than two observations")
    if (n01 + n11) == 0:
        return TestResult(
            "christoffersen_independence", None, 1, None, None, False,
            "no exceptions occurred, so there are no transitions into the "
            "exception state to learn from. Independence is untested here, "
            "which is not the same as confirmed.")
    if (n10 + n11) == 0:
        return TestResult(
            "christoffersen_independence", None, 1, None, None, False,
            "no observation follows an exception, so the conditional "
            "probability of a repeat cannot be estimated")

    pi = (n01 + n11) / total
    pi01 = n01 / (n00 + n01) if (n00 + n01) else 0.0
    pi11 = n11 / (n10 + n11) if (n10 + n11) else 0.0
    log_null = _xlogy(n00 + n10, 1.0 - pi) + _xlogy(n01 + n11, pi)
    log_alt = (_xlogy(n00, 1.0 - pi01) + _xlogy(n01, pi01)
               + _xlogy(n10, 1.0 - pi11) + _xlogy(n11, pi11))
    statistic = max(0.0, -2.0 * (log_null - log_alt))
    p_value = _chi2_sf(statistic, 1)
    return TestResult(
        "christoffersen_independence", statistic, 1, p_value, p_value < 0.05, True,
        f"transitions n00={n00} n01={n01} n10={n10} n11={n11}; tests whether an "
        "exception makes another exception more likely the next day")


def conditional_coverage(kupiec: TestResult, independence: TestResult) -> TestResult:
    """Kupiec + Christoffersen, jointly. LR_cc ~ chi2(2)."""
    if not (kupiec.computable and independence.computable):
        return TestResult(
            "conditional_coverage", None, 2, None, None, False,
            "requires both the coverage and the independence statistics; "
            f"coverage computable={kupiec.computable}, "
            f"independence computable={independence.computable}")
    statistic = (kupiec.statistic or 0.0) + (independence.statistic or 0.0)
    p_value = _chi2_sf(statistic, 2)
    return TestResult(
        "conditional_coverage", statistic, 2, p_value, p_value < 0.05, True,
        "the joint test: correct number of exceptions AND no clustering")


def basel_traffic_light(observations: int, exceptions: int,
                        confidence_level: float) -> tuple[str | None, bool]:
    """The BCBS zone, but only where the BCBS rule actually applies.

    The green/amber/red boundaries are calibrated for 250 observations at 99%.
    Applying them to a 60-day window or a 95% model produces a colour that looks
    official and means nothing, so outside those conditions the zone is None and
    the applicability flag says why.
    """
    applicable = (observations == BASEL_TRAFFIC_LIGHT_OBSERVATIONS
                  and abs(confidence_level - BASEL_TRAFFIC_LIGHT_CONFIDENCE) < 1e-12)
    if not applicable:
        return None, False
    if exceptions <= BASEL_GREEN_MAX:
        return "GREEN", True
    if exceptions <= BASEL_AMBER_MAX:
        return "AMBER", True
    return "RED", True


def backtest_var(
    var_forecasts: Sequence[float], pnl: Sequence[float],
    confidence_level: float = 0.99, pnl_kind: PnlKind = "HYPOTHETICAL",
    dates: Sequence[dt.date] | None = None,
) -> BacktestResult:
    if len(var_forecasts) != len(pnl):
        raise EngineError(
            "MISSING_PNL_SERIES",
            f"{len(var_forecasts)} VaR forecasts were supplied against "
            f"{len(pnl)} P&L observations. A backtest compares each day's "
            "forecast with that same day's outcome, so the two series must "
            "align one to one.",
            category="USER_INPUT",
            suggested_action="Trim both series to the overlapping dates.")
    if dates is not None and len(dates) != len(pnl):
        raise EngineError(
            "MISSING_PNL_SERIES",
            f"{len(dates)} dates were supplied for {len(pnl)} observations",
            category="USER_INPUT",
            suggested_action="Pass one date per observation, or omit them.")
    if len(pnl) < MINIMUM_OBSERVATIONS:
        raise EngineError(
            "INSUFFICIENT_BACKTEST_DATA",
            f"{len(pnl)} observations is too few to say anything about a "
            f"{confidence_level:.1%} model, which expects an exception roughly "
            f"every {1 / (1 - confidence_level):.0f} days. At least "
            f"{MINIMUM_OBSERVATIONS} are required.",
            category="DATA_AVAILABILITY", retryable=True,
            suggested_action=(
                f"Supply at least {MINIMUM_OBSERVATIONS} paired observations; "
                "250 is the conventional window."))
    if not 0.5 <= confidence_level < 1.0:
        raise EngineError(
            "INVALID_CONFIDENCE_LEVEL",
            f"confidence_level {confidence_level} is outside [0.5, 1.0)",
            category="USER_INPUT")
    negative = [i for i, v in enumerate(var_forecasts) if v < 0]
    if negative:
        raise EngineError(
            "INVALID_VAR_FORECAST",
            f"VaR forecasts must be non-negative loss thresholds; "
            f"{len(negative)} of them are negative (first at index "
            f"{negative[0]}). A negative threshold would make every day an "
            "exception and the test would report a catastrophic model failure "
            "that was actually a sign convention.",
            category="USER_INPUT",
            suggested_action="Pass VaR as a positive loss amount.")

    detail: list[Exception_] = []
    indicators: list[int] = []
    for i, (forecast, outcome) in enumerate(zip(var_forecasts, pnl)):
        loss = -outcome
        is_exception = loss > forecast
        indicators.append(1 if is_exception else 0)
        if is_exception:
            detail.append(Exception_(
                index=i, date=dates[i] if dates else None, var_forecast=forecast,
                pnl=outcome, loss=loss, excess=loss - forecast))

    longest = current = 0
    clusters = 0
    for flag in indicators:
        if flag:
            current += 1
            if current == 1:
                clusters += 1
            longest = max(longest, current)
        else:
            current = 0

    n = len(pnl)
    x = len(detail)
    kupiec = kupiec_unconditional_coverage(n, x, confidence_level)
    independence = christoffersen_independence(indicators)
    zone, applicable = basel_traffic_light(n, x, confidence_level)

    return BacktestResult(
        observations=n, confidence_level=confidence_level, pnl_kind=pnl_kind,
        exceptions=x, exception_rate=x / n,
        expected_exceptions=n * (1.0 - confidence_level),
        expected_exception_rate=1.0 - confidence_level,
        exception_dates=tuple(e.date for e in detail),
        exception_detail=tuple(detail),
        longest_exception_run=longest, exception_clusters=clusters,
        mean_excess_loss=(sum(e.excess for e in detail) / x) if x else 0.0,
        worst_excess_loss=max((e.excess for e in detail), default=0.0),
        kupiec=kupiec, independence=independence,
        conditional_coverage=conditional_coverage(kupiec, independence),
        basel_traffic_light=zone, basel_traffic_light_applicable=applicable,
    )
