"""Simulated curve moves, revalued in full.  `cholesky_box_muller_full_reval_v1`

Historical simulation is limited to the moves that happened; parametric VaR is
limited to a linear portfolio and a normal distribution. Monte Carlo relaxes the
second limit while keeping full revaluation, so the convexity of a 30-year bond
is priced rather than approximated - which is the whole reason to spend the
compute.

## Reproducibility is a property of the design, not a promise

A simulation whose answer changes between runs cannot be checked, cannot be
signed off, and cannot appear in a report twice. Three decisions make this one
deterministic:

1. **The seed is an explicit input** and travels into the run fingerprint.
2. **The normal draws are generated here, by Box-Muller, from
   `random.Random(seed).random()`** rather than by `random.gauss`. The library's
   Gaussian generator caches a spare variate between calls and its algorithm is
   an implementation detail; Box-Muller over the raw uniform stream is fully
   specified, so the same seed reproduces the same numbers on any Python that
   keeps the Mersenne Twister - which the language guarantees.
3. **The draws are consumed in a fixed order**: factor by factor, scenario by
   scenario.

Same inputs, same manifest, same seed, same answer. A test asserts it, and a
second test asserts that a *different* seed gives a different one, because a
"deterministic" simulation that ignores its seed is also perfectly reproducible.

## The factorisation

The covariance is factorised by Cholesky where it is positive definite, and by
eigenvalue clipping where it is not. Which one ran, and how much the matrix was
moved, is reported. A curve history routinely produces a singular covariance -
two adjacent tenors that moved identically all window, or a front end pinned at
zero - and a plain Cholesky simply fails on it. Repairing silently would be
worse than failing; repairing loudly is right.

## Extreme tail methodologies

`run_extreme_tail_simulation` offers four, and each is a *different model* with
its own manifest version, never a relabelling of this one:

* `volatility_multiplier` - the same normal model with sigma scaled.
* `stressed_covariance` - the normal model estimated on the most volatile window
  found in the history rather than on all of it.
* `student_t` - multivariate Student-t innovations, variance-matched to the
  estimated covariance so that only the tail thickness changes.
* `empirical_bootstrap` - resampling the observed change vectors with
  replacement. No distributional assumption at all; the tail is whatever
  happened.

None of them may be presented as historical VaR, and none of them shares its
version string.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .curves import CurveError, ParCurve
from .errors import EngineError
from .linalg import Matrix, psd_factor
from .revaluation import CompiledBook
from .risk import nearest_rank_quantile
from .volatility import (
    covariance_matrix,
    find_high_volatility_window,
    observed_changes_bp,
    regime_changes,
    scale_covariance,
)

TailMethod = Literal[
    "volatility_multiplier", "stressed_covariance", "student_t",
    "empirical_bootstrap",
]

DEFAULT_SCENARIO_COUNT = 5000
MAX_SCENARIO_COUNT = 100_000
REPORTED_PERCENTILES = (1.0, 5.0, 25.0, 50.0, 75.0, 95.0, 99.0)


@dataclass(frozen=True)
class MonteCarloRisk:
    base_value: float
    confidence_level: float
    horizon_days: int
    scenario_count: int
    scenarios_priced: int
    random_seed: int
    method: str
    distribution: str
    var: float
    expected_shortfall: float
    mean_pnl: float
    stdev_pnl: float
    worst_pnl: float
    best_pnl: float
    percentiles_pnl: dict[str, float]
    tail_scenario_count: int
    covariance_repaired: bool
    covariance_diagnostics: dict[str, float]
    rejected_scenarios: int
    rejection_note: str | None
    observations_used: int
    tenors_years: tuple[float, ...]


def standard_normals(count: int, seed: int) -> list[float]:
    """`count` standard normal variates by Box-Muller over one uniform stream.

    Written out rather than delegated so the sequence is part of the model
    definition. `u1` is drawn from the open interval by rejecting exact zero -
    log(0) is the one input that turns a simulation into a crash.
    """
    rng = random.Random(seed)
    out: list[float] = []
    while len(out) < count:
        u1 = rng.random()
        while u1 <= 0.0:
            u1 = rng.random()
        u2 = rng.random()
        radius = math.sqrt(-2.0 * math.log(u1))
        angle = 2.0 * math.pi * u2
        out.append(radius * math.cos(angle))
        if len(out) < count:
            out.append(radius * math.sin(angle))
    return out


def _validate(confidence_level: float, horizon_days: int, scenario_count: int) -> None:
    if not 0.5 <= confidence_level < 1.0:
        raise EngineError(
            "INVALID_CONFIDENCE_LEVEL",
            f"confidence_level {confidence_level} is outside [0.5, 1.0)",
            category="USER_INPUT", suggested_action="Use 0.95, 0.975 or 0.99.")
    if horizon_days < 1:
        raise EngineError(
            "INVALID_HORIZON", f"horizon_days must be at least 1; got {horizon_days}",
            category="USER_INPUT")
    if not 100 <= scenario_count <= MAX_SCENARIO_COUNT:
        raise EngineError(
            "MONTE_CARLO_FAILURE",
            f"scenario_count must be between 100 and {MAX_SCENARIO_COUNT:,}; got "
            f"{scenario_count:,}. Below 100 the tail estimate is noise; above "
            f"{MAX_SCENARIO_COUNT:,} the run stops being interactive and the "
            "extra precision is smaller than the model error.",
            category="USER_INPUT",
            suggested_action=f"Use {DEFAULT_SCENARIO_COUNT:,} for a normal run.")


def _draw_shock_vectors(
    factor: Matrix, tenors: Sequence[float], scenario_count: int, seed: int,
    degrees_of_freedom: int | None = None,
) -> list[dict[float, float]]:
    """Correlated shock vectors from a factor matrix, in basis points."""
    n = len(tenors)
    per_scenario = n + (degrees_of_freedom or 0)
    stream = standard_normals(scenario_count * per_scenario, seed)
    vectors: list[dict[float, float]] = []
    scale = 1.0
    if degrees_of_freedom:
        # Variance-match the Student-t so only the tail thickness changes.
        scale = math.sqrt((degrees_of_freedom - 2.0) / degrees_of_freedom)
    for s in range(scenario_count):
        offset = s * per_scenario
        z = stream[offset:offset + n]
        multiplier = 1.0
        if degrees_of_freedom:
            chi = sum(x * x for x in stream[offset + n:offset + per_scenario])
            multiplier = scale / math.sqrt(chi / degrees_of_freedom) if chi > 0 else 0.0
        vectors.append({
            float(tenors[i]): multiplier * sum(factor[i][k] * z[k] for k in range(n))
            for i in range(n)})
    return vectors


def _price_vectors(
    book: CompiledBook, par: ParCurve, vectors: Sequence[dict[float, float]],
) -> tuple[list[float], int, str | None]:
    """Revalue, dropping only the scenarios the bootstrap genuinely refuses."""
    usable: list[dict[float, float]] = []
    rejected = 0
    for vector in vectors:
        try:
            par.shocked(vector)
            usable.append(vector)
        except CurveError:
            # A draw large enough to push a par rate outside the plausible band
            # ParCurve enforces. Rare, and counted rather than swallowed.
            rejected += 1
    priced: list[float] = []
    base = book.value_under(par)
    for vector in usable:
        try:
            priced.append(book.value_under(par.shocked(vector)) - base)
        except CurveError:
            rejected += 1
    note = None
    if rejected:
        note = (
            f"{rejected:,} of {len(vectors):,} simulated curves were rejected by "
            "the bootstrap as not arbitrage-consistent and are excluded. The "
            "quantile is taken over the scenarios that priced; a large rejection "
            "count means the estimated covariance is generating curve shapes "
            "this bootstrap cannot represent, and the result should not be used.")
    return priced, rejected, note


def _summarise(
    pnl: Sequence[float], base_value: float, confidence_level: float,
) -> tuple[float, float, int, dict[str, float]]:
    losses = sorted(-p for p in pnl)
    var, _ = nearest_rank_quantile(losses, confidence_level)
    var = max(0.0, var)
    tail = [loss for loss in losses if loss >= var]
    es = sum(tail) / len(tail) if tail else var
    ordered = sorted(pnl)
    percentiles = {}
    for p in REPORTED_PERCENTILES:
        value, _ = nearest_rank_quantile(ordered, p / 100.0)
        percentiles[f"p{p:g}"] = value
    return var, es, len(tail), percentiles


def compute_monte_carlo_risk(
    book: CompiledBook, par: ParCurve,
    history_tenors_years: Sequence[float],
    history_rates_percent: Sequence[Sequence[float]],
    confidence_level: float = 0.99, horizon_days: int = 1,
    scenario_count: int = DEFAULT_SCENARIO_COUNT, random_seed: int = 20260824,
    covariance_override: Matrix | None = None,
    method_label: str = "cholesky_box_muller_full_reval_v1",
    distribution_label: str = "multivariate normal on absolute basis-point changes",
    degrees_of_freedom: int | None = None,
) -> MonteCarloRisk:
    _validate(confidence_level, horizon_days, scenario_count)
    live = set(par.tenors_years)
    columns = [j for j, t in enumerate(history_tenors_years) if float(t) in live]
    tenors = [float(history_tenors_years[j]) for j in columns]
    if not tenors:
        raise EngineError(
            "MISSING_REQUIRED_MARKET_DATA",
            "none of the history's tenors are nodes on the valuation curve",
            category="DATA_AVAILABILITY",
            suggested_action=(
                "Fetch the history on the same tenor set as the valuation curve."))

    changes = observed_changes_bp(history_rates_percent, horizon_days)
    trimmed = [[row[j] for j in columns] for row in changes]
    cov = covariance_override if covariance_override is not None else covariance_matrix(trimmed)
    if len(cov) != len(tenors):
        raise EngineError(
            "INVALID_COVARIANCE_MATRIX",
            f"the covariance matrix is {len(cov)}x{len(cov)} but there are "
            f"{len(tenors)} risk factors",
            category="USER_INPUT")

    factor, diagnostics = psd_factor(cov)
    vectors = _draw_shock_vectors(factor, tenors, scenario_count, random_seed,
                                  degrees_of_freedom)
    pnl, rejected, note = _price_vectors(book, par, vectors)
    if not pnl:
        raise EngineError(
            "MONTE_CARLO_FAILURE",
            "no simulated curve could be priced; every draw left the bootstrap "
            "with a non-positive or rising discount factor.",
            category="NUMERICAL",
            suggested_action=(
                "Check the estimation window - a covariance dominated by one "
                "extreme day generates implausible curve shapes."))

    var, es, tail_count, percentiles = _summarise(pnl, book.value_under(par),
                                                  confidence_level)
    mean = sum(pnl) / len(pnl)
    variance = (sum((p - mean) ** 2 for p in pnl) / (len(pnl) - 1)
                if len(pnl) > 1 else 0.0)
    return MonteCarloRisk(
        base_value=book.value_under(par), confidence_level=confidence_level,
        horizon_days=horizon_days, scenario_count=scenario_count,
        scenarios_priced=len(pnl), random_seed=random_seed, method=method_label,
        distribution=distribution_label, var=var, expected_shortfall=es,
        mean_pnl=mean, stdev_pnl=math.sqrt(variance), worst_pnl=min(pnl),
        best_pnl=max(pnl), percentiles_pnl=percentiles,
        tail_scenario_count=tail_count,
        covariance_repaired=bool(diagnostics.get("repaired")),
        covariance_diagnostics=diagnostics, rejected_scenarios=rejected,
        rejection_note=note, observations_used=len(trimmed),
        tenors_years=tuple(tenors),
    )


def run_extreme_tail_simulation(
    book: CompiledBook, par: ParCurve,
    history_tenors_years: Sequence[float],
    history_rates_percent: Sequence[Sequence[float]],
    tail_method: TailMethod = "volatility_multiplier",
    confidence_level: float = 0.99, horizon_days: int = 1,
    scenario_count: int = DEFAULT_SCENARIO_COUNT, random_seed: int = 20260824,
    volatility_multiplier: float = 2.0, degrees_of_freedom: int = 5,
    regime_window_days: int = 60,
) -> MonteCarloRisk:
    """A deliberately fat-tailed simulation, labelled as one."""
    live = set(par.tenors_years)
    columns = [j for j, t in enumerate(history_tenors_years) if float(t) in live]
    tenors = [float(history_tenors_years[j]) for j in columns]
    changes = observed_changes_bp(history_rates_percent, horizon_days)
    trimmed = [[row[j] for j in columns] for row in changes]

    if tail_method == "volatility_multiplier":
        cov = scale_covariance(covariance_matrix(trimmed), volatility_multiplier)
        return compute_monte_carlo_risk(
            book, par, history_tenors_years, history_rates_percent,
            confidence_level, horizon_days, scenario_count, random_seed,
            covariance_override=cov,
            method_label=f"stressed_normal_volatility_x{volatility_multiplier:g}_v1",
            distribution_label=(
                f"multivariate normal with every volatility scaled by "
                f"{volatility_multiplier:g} (covariance scaled by "
                f"{volatility_multiplier ** 2:g})"))

    if tail_method == "stressed_covariance":
        regime = find_high_volatility_window(trimmed, regime_window_days)
        if regime is None:
            raise EngineError(
                "INSUFFICIENT_HISTORY",
                f"a {regime_window_days}-day volatility regime cannot be found "
                f"in {len(trimmed)} observed changes.",
                category="DATA_AVAILABILITY", retryable=True,
                suggested_action=(
                    "Request a longer history or a shorter regime window."))
        cov = covariance_matrix(regime_changes(trimmed, regime))
        return compute_monte_carlo_risk(
            book, par, history_tenors_years, history_rates_percent,
            confidence_level, horizon_days, scenario_count, random_seed,
            covariance_override=cov,
            method_label="stressed_covariance_worst_volatility_window_v1",
            distribution_label=(
                f"multivariate normal estimated on the most volatile "
                f"{regime_window_days}-day window in the history (observations "
                f"{regime.start_index}-{regime.end_index}, average volatility "
                f"{regime.ratio_to_full_sample:.2f}x the full sample)"))

    if tail_method == "student_t":
        if degrees_of_freedom <= 2:
            raise EngineError(
                "MONTE_CARLO_FAILURE",
                f"a Student-t needs more than two degrees of freedom to have a "
                f"finite variance; got {degrees_of_freedom}",
                category="USER_INPUT",
                suggested_action="Use 4 to 8 for a plausibly fat-tailed rate model.")
        return compute_monte_carlo_risk(
            book, par, history_tenors_years, history_rates_percent,
            confidence_level, horizon_days, scenario_count, random_seed,
            method_label=f"student_t_df{degrees_of_freedom}_full_reval_v1",
            distribution_label=(
                f"multivariate Student-t with {degrees_of_freedom} degrees of "
                "freedom, variance-matched to the estimated covariance so only "
                "the tail thickness differs from the normal case"),
            degrees_of_freedom=degrees_of_freedom)

    if tail_method == "empirical_bootstrap":
        _validate(confidence_level, horizon_days, scenario_count)
        if not trimmed:
            raise EngineError(
                "INSUFFICIENT_HISTORY", "no observed changes to resample from",
                category="DATA_AVAILABILITY")
        rng = random.Random(random_seed)
        draws = [rng.randrange(len(trimmed)) for _ in range(scenario_count)]
        vectors = [{tenors[i]: trimmed[d][i] for i in range(len(tenors))}
                   for d in draws]
        pnl, rejected, note = _price_vectors(book, par, vectors)
        if not pnl:
            raise EngineError(
                "MONTE_CARLO_FAILURE", "no resampled curve could be priced",
                category="NUMERICAL")
        base = book.value_under(par)
        var, es, tail_count, percentiles = _summarise(pnl, base, confidence_level)
        mean = sum(pnl) / len(pnl)
        variance = (sum((p - mean) ** 2 for p in pnl) / (len(pnl) - 1)
                    if len(pnl) > 1 else 0.0)
        return MonteCarloRisk(
            base_value=base, confidence_level=confidence_level,
            horizon_days=horizon_days, scenario_count=scenario_count,
            scenarios_priced=len(pnl), random_seed=random_seed,
            method="empirical_bootstrap_resample_v1",
            distribution=(
                "the empirical distribution of observed change vectors, "
                "resampled with replacement - no distributional assumption, and "
                "no move that did not happen"),
            var=var, expected_shortfall=es, mean_pnl=mean,
            stdev_pnl=math.sqrt(variance), worst_pnl=min(pnl), best_pnl=max(pnl),
            percentiles_pnl=percentiles, tail_scenario_count=tail_count,
            covariance_repaired=False, covariance_diagnostics={"repaired": 0.0},
            rejected_scenarios=rejected, rejection_note=note,
            observations_used=len(trimmed), tenors_years=tuple(tenors))

    raise EngineError(  # pragma: no cover - guarded by the Literal
        "MONTE_CARLO_FAILURE", f"unknown tail method {tail_method!r}",
        category="USER_INPUT")


def correlation_stress_covariance(
    base_covariance: Matrix, mode: str, custom_correlation: Matrix | None = None,
) -> tuple[Matrix, str, dict[str, float]]:
    """Rebuild a covariance with a different correlation structure, same volatilities.

    Correlation is what a rate book's diversification rests on, and it is the
    assumption that moves most in a crisis. Holding each tenor's volatility
    fixed while changing only the correlation isolates that effect: any change
    in VaR is attributable to co-movement rather than to the size of the moves.

    Every result is checked for positive semidefiniteness and repaired if
    needed, with the repair reported. A hand-written correlation matrix is very
    often not a valid one.
    """
    from .linalg import (
        correlation_from_covariance,
        covariance_from_correlation,
        nearest_psd,
    )

    n = len(base_covariance)
    stdevs = [math.sqrt(base_covariance[i][i]) if base_covariance[i][i] > 0 else 0.0
              for i in range(n)]
    base_corr = correlation_from_covariance(base_covariance)

    if mode == "historical":
        target = base_corr
        label = "the correlation estimated from the supplied history"
    elif mode == "perfect_positive":
        target = [[1.0 for _ in range(n)] for _ in range(n)]
        label = ("every tenor perfectly correlated - the no-diversification "
                 "case, and an upper bound on rate VaR")
    elif mode == "independent":
        target = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
        label = "every tenor independent - maximal diversification benefit"
    elif mode == "front_end_decorrelated":
        midpoint = n // 2
        target = [[1.0 if i == j
                   else (base_corr[i][j] if (i < midpoint) == (j < midpoint) else 0.0)
                   for j in range(n)] for i in range(n)]
        label = ("the front and long halves of the curve decorrelated from each "
                 "other, each keeping its internal correlation")
    elif mode == "custom":
        if custom_correlation is None:
            raise EngineError(
                "INVALID_COVARIANCE_MATRIX",
                "mode 'custom' needs a correlation matrix",
                category="USER_INPUT")
        if len(custom_correlation) != n:
            raise EngineError(
                "INVALID_COVARIANCE_MATRIX",
                f"the supplied correlation matrix is {len(custom_correlation)}x"
                f"{len(custom_correlation)} but there are {n} risk factors",
                category="USER_INPUT")
        target = [list(row) for row in custom_correlation]
        label = "a caller-supplied correlation matrix"
    else:
        raise EngineError(
            "INVALID_COVARIANCE_MATRIX", f"unknown correlation mode {mode!r}",
            category="USER_INPUT",
            suggested_action=(
                "Use historical, perfect_positive, independent, "
                "front_end_decorrelated or custom."))

    repaired, info = nearest_psd(target, floor=0.0)
    needed_repair = info["smallest_eigenvalue_before"] < -1e-10
    used = repaired if needed_repair else target
    diagnostics = {**info, "repaired": 1.0 if needed_repair else 0.0}
    return covariance_from_correlation(used, stdevs), label, diagnostics
