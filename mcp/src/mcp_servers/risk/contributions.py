"""Who lost the money.  `euler_scenario_decomposition_v1`

A portfolio loss is a single number and the next question is always the same:
which positions, and which part of the curve. This module answers both, and is
careful about the difference between the two answers - because one of them is
exact and the other is not.

**Position contributions are exact.** They come out of the same revaluation pass
as the portfolio number, so they sum to it by construction. A reconciliation
check on them tests arithmetic, and any failure is a real defect rather than a
tolerance question.

**Tenor contributions are not exact, and the residual is reported.** A curve
shock is not separable: revaluing under a 2Y move and a 10Y move separately does
not give the same answer as revaluing under both, because the bond's value is a
non-linear function of the whole curve. Two methods are offered and both state
what they left over:

* `first_order` - key-rate DV01 at each node times that node's shock. One pass
  per node, reusable across scenarios, and the residual is the convexity and
  cross-tenor terms.
* `isolated_reval` - one full revaluation per shocked node with every other node
  held still. More faithful per node, still not additive, and the residual is
  the cross terms alone.

Forcing either to add up - by scaling the parts to match the whole - would
destroy the one diagnostic that says how non-linear the scenario was. The
residual stays.

## Risk-measure contributions

Component VaR and component ES here are **exact Euler decompositions**, not
allocation heuristics, and that is a property of historical simulation rather
than a clever formula:

* Under the nearest-rank convention, VaR *is* the loss in one identified
  scenario. The positions' losses in that same scenario therefore sum to it.
* ES is the mean loss over the tail scenarios. The positions' mean losses over
  those same scenarios therefore sum to it.

Incremental VaR is computed by re-running the quantile over the portfolio with
one position removed - possible in constant time because the per-position P&L
matrix is already held. It is the honest answer to "what would dropping this
position do", and it does not sum to VaR, because incremental and component
measures answer different questions.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .curves import CurveError, ParCurve
from .errors import EngineError
from .revaluation import CompiledBook, ScenarioPnl, key_rate_exposures
from .risk import nearest_rank_quantile
from .stress_scenarios import ShockVector

AttributionMethod = Literal["first_order", "isolated_reval"]

# Maturity buckets, in years, as (label, exclusive lower, inclusive upper).
#
# Half-open at the *bottom*, so a 10-year point falls in the bucket labelled
# "5-10y" rather than in "10-20y". The opposite convention is defensible and
# produces a "5-10y" bucket that contains no 10-year risk, which every reader
# of the table reads as a bug.
MATURITY_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0-2y", 0.0, 2.0),
    ("2-5y", 2.0, 5.0),
    ("5-10y", 5.0, 10.0),
    ("10-20y", 10.0, 20.0),
    ("20y+", 20.0, math.inf),
)


def bucket_for(tenor_years: float) -> str:
    for label, lo, hi in MATURITY_BUCKETS:
        if lo < tenor_years <= hi:
            return label
    return MATURITY_BUCKETS[0][0] if tenor_years <= 0 else MATURITY_BUCKETS[-1][0]


@dataclass(frozen=True)
class PositionResult:
    instrument_id: str
    base_value: float
    stressed_value: float
    pnl: float
    contribution_percent: float


@dataclass(frozen=True)
class TenorContribution:
    tenor_years: float
    shock_bp: float
    key_rate_dv01: float | None
    pnl: float
    contribution_percent: float
    attributable: bool = True


@dataclass(frozen=True)
class BucketContribution:
    bucket: str
    pnl: float
    contribution_percent: float


@dataclass(frozen=True)
class Concentration:
    top_share_percent: float
    top_three_share_percent: float
    herfindahl_index: float
    effective_count: float


@dataclass(frozen=True)
class StressRun:
    shock: ShockVector
    base_value: float
    stressed_value: float
    pnl: float
    pnl_percent: float
    positions: tuple[PositionResult, ...]

    def worst_position(self) -> PositionResult | None:
        return min(self.positions, key=lambda p: p.pnl, default=None)


@dataclass(frozen=True)
class StressAttribution:
    run: StressRun
    method: AttributionMethod
    tenors: tuple[TenorContribution, ...]
    buckets: tuple[BucketContribution, ...]
    tenor_explained_pnl: float
    tenor_residual_pnl: float
    tenor_residual_percent: float
    position_concentration: Concentration
    tenor_concentration: Concentration
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class MeasureContribution:
    instrument_id: str
    component: float
    component_percent: float
    marginal_per_million_notional: float | None
    incremental: float | None


@dataclass(frozen=True)
class RiskContributions:
    measure: str
    confidence_level: float
    portfolio_measure: float
    scenario_count: int
    tail_scenario_count: int
    var_scenario_index: int
    positions: tuple[MeasureContribution, ...]
    reconciliation_difference: float


def run_shock(book: CompiledBook, par: ParCurve, shock: ShockVector) -> StressRun:
    """Full revaluation under one scenario, with exact position attribution."""
    base_total, base_per = book.values_under(par)
    stressed_total, stressed_per = book.values_under(
        par.shocked(shock.shocks_bp_by_tenor_years))
    pnl = stressed_total - base_total
    positions = tuple(
        PositionResult(
            instrument_id=iid, base_value=b, stressed_value=s, pnl=s - b,
            contribution_percent=((s - b) / pnl * 100.0) if pnl else 0.0)
        for iid, b, s in zip(book.instrument_ids(), base_per, stressed_per))
    return StressRun(
        shock=shock, base_value=base_total, stressed_value=stressed_total, pnl=pnl,
        pnl_percent=(pnl / base_total * 100.0) if base_total else 0.0,
        positions=positions,
    )


def concentration_of(values: Sequence[float]) -> Concentration:
    """Share and Herfindahl concentration over absolute magnitudes.

    Absolute, because a book with +100 and -100 of a risk is concentrated in
    that risk even though its net is zero. The effective count (1/HHI) is the
    number of equally sized positions that would be this concentrated, which is
    the form a reader can hold in their head.
    """
    magnitudes = sorted((abs(v) for v in values), reverse=True)
    total = sum(magnitudes)
    if total <= 0:
        return Concentration(0.0, 0.0, 0.0, 0.0)
    shares = [m / total for m in magnitudes]
    hhi = sum(s * s for s in shares)
    return Concentration(
        top_share_percent=shares[0] * 100.0,
        top_three_share_percent=sum(shares[:3]) * 100.0,
        herfindahl_index=hhi,
        effective_count=(1.0 / hhi) if hhi > 0 else 0.0,
    )


def attribute_stress(
    book: CompiledBook, par: ParCurve, shock: ShockVector,
    method: AttributionMethod = "first_order", bump_bp: float = 1.0,
) -> StressAttribution:
    run = run_shock(book, par, shock)
    shocks = shock.shocks_bp_by_tenor_years

    tenor_pnl: list[tuple[float, float, float | None, bool]] = []
    warnings: list[str] = []
    if method == "first_order":
        _, totals, _ = key_rate_exposures(book, par, bump_bp)
        krd = dict(totals)
        for tenor in par.tenors_years:
            bp = shocks.get(tenor, 0.0)
            tenor_pnl.append((tenor, -krd[tenor] * bp, krd[tenor], True))
    elif method == "isolated_reval":
        base = run.base_value
        for tenor in par.tenors_years:
            bp = shocks.get(tenor, 0.0)
            if bp == 0.0:
                tenor_pnl.append((tenor, 0.0, None, True))
                continue
            try:
                isolated = book.value_under(par.shocked({tenor: bp}))
            except CurveError as exc:
                # A large single-node bump can leave the curve
                # arbitrage-inconsistent even when the full scenario is
                # perfectly well behaved - move the 20Y 125bp while the 30Y
                # stays put and the bootstrap meets a negative forward. That is
                # a property of the isolating method, not of the scenario, so
                # the tenor is reported as unattributable and its share stays in
                # the residual. Inventing a number for it would be worse.
                warnings.append(
                    f"{tenor:g}y could not be isolated: shocking it alone by "
                    f"{bp:+.0f}bp gives a curve the bootstrap rejects ({exc}). "
                    "Its contribution is inside the residual; use "
                    "method='first_order' for a decomposition that covers "
                    "every node.")
                tenor_pnl.append((tenor, 0.0, None, False))
                continue
            tenor_pnl.append((tenor, isolated - base, None, True))
    else:  # pragma: no cover - guarded by the Literal at the boundary
        raise EngineError("INVALID_STRESS_VECTOR", f"unknown method {method!r}")

    explained = sum(v for _, v, _, _ in tenor_pnl)
    residual = run.pnl - explained
    contributions = tuple(
        TenorContribution(
            tenor_years=t, shock_bp=shocks.get(t, 0.0), key_rate_dv01=k, pnl=v,
            contribution_percent=(v / run.pnl * 100.0) if run.pnl else 0.0,
            attributable=ok)
        for t, v, k, ok in tenor_pnl)

    by_bucket: dict[str, float] = {}
    for c in contributions:
        by_bucket[bucket_for(c.tenor_years)] = by_bucket.get(bucket_for(c.tenor_years), 0.0) + c.pnl
    buckets = tuple(
        BucketContribution(
            bucket=label, pnl=by_bucket.get(label, 0.0),
            contribution_percent=(by_bucket.get(label, 0.0) / run.pnl * 100.0)
            if run.pnl else 0.0)
        for label, _, _ in MATURITY_BUCKETS)

    return StressAttribution(
        run=run, method=method, tenors=contributions, buckets=buckets,
        tenor_explained_pnl=explained, tenor_residual_pnl=residual,
        tenor_residual_percent=(residual / run.pnl * 100.0) if run.pnl else 0.0,
        position_concentration=concentration_of([p.pnl for p in run.positions]),
        tenor_concentration=concentration_of([c.pnl for c in contributions]),
        warnings=tuple(warnings),
    )


def measure_contributions(
    scenarios: ScenarioPnl, confidence_level: float, measure: str = "var",
    include_incremental: bool = True,
) -> RiskContributions:
    """Component, marginal and incremental VaR or ES from one scenario matrix."""
    if measure not in {"var", "es"}:
        raise EngineError(
            "INVALID_CONFIDENCE_LEVEL", f"unknown risk measure {measure!r}",
            category="USER_INPUT", suggested_action="Use 'var' or 'es'.")
    if not 0.5 <= confidence_level < 1.0:
        raise EngineError(
            "INVALID_CONFIDENCE_LEVEL",
            f"confidence_level {confidence_level} is outside [0.5, 1.0)",
            category="USER_INPUT",
            suggested_action="Use a level such as 0.95, 0.975 or 0.99.")
    if scenarios.scenario_count == 0:
        raise EngineError(
            "INSUFFICIENT_HISTORY", "no scenarios to decompose",
            category="DATA_AVAILABILITY")

    losses = [-p for p in scenarios.pnl]
    order = sorted(range(len(losses)), key=lambda i: losses[i])
    sorted_losses = [losses[i] for i in order]
    var, rank = nearest_rank_quantile(sorted_losses, confidence_level)
    var_scenario = order[rank]

    tail = [i for i in range(len(losses)) if losses[i] >= var]
    n_positions = len(scenarios.instrument_ids)

    if measure == "var":
        portfolio = max(0.0, var)
        components = [-scenarios.pnl_per_position[var_scenario][j] for j in range(n_positions)]
    else:
        portfolio = (sum(losses[i] for i in tail) / len(tail)) if tail else max(0.0, var)
        components = [
            (sum(-scenarios.pnl_per_position[i][j] for i in tail) / len(tail))
            if tail else -scenarios.pnl_per_position[var_scenario][j]
            for j in range(n_positions)]

    incrementals: list[float | None] = []
    if include_incremental:
        for j in range(n_positions):
            without = sorted(-p for p in scenarios.pnl_excluding(j))
            reduced, _ = nearest_rank_quantile(without, confidence_level)
            if measure == "es":
                reduced_tail = [loss for loss in without if loss >= reduced]
                reduced = (sum(reduced_tail) / len(reduced_tail)
                           if reduced_tail else reduced)
            incrementals.append(portfolio - max(0.0, reduced))
    else:
        incrementals = [None] * n_positions

    total_component = sum(components)
    out = tuple(
        MeasureContribution(
            instrument_id=scenarios.instrument_ids[j],
            component=components[j],
            component_percent=(components[j] / total_component * 100.0)
            if total_component else 0.0,
            marginal_per_million_notional=None,
            incremental=incrementals[j],
        )
        for j in range(n_positions))

    return RiskContributions(
        measure=measure.upper(), confidence_level=confidence_level,
        portfolio_measure=portfolio, scenario_count=scenarios.scenario_count,
        tail_scenario_count=len(tail), var_scenario_index=var_scenario,
        positions=out, reconciliation_difference=total_component - portfolio,
    )


def with_marginals(
    contributions: RiskContributions, notionals: Sequence[float],
) -> RiskContributions:
    """Attach marginal risk per million of notional.

    Marginal, here, is the component divided by the position's own size: the
    risk the position carries per unit held, which is what makes two positions
    of different size comparable. It is a scaling of the component measure, not
    an independent estimate, and is labelled that way.
    """
    positions = tuple(
        MeasureContribution(
            instrument_id=c.instrument_id, component=c.component,
            component_percent=c.component_percent,
            marginal_per_million_notional=(c.component / n * 1_000_000.0) if n else None,
            incremental=c.incremental)
        for c, n in zip(contributions.positions, notionals))
    return RiskContributions(
        measure=contributions.measure, confidence_level=contributions.confidence_level,
        portfolio_measure=contributions.portfolio_measure,
        scenario_count=contributions.scenario_count,
        tail_scenario_count=contributions.tail_scenario_count,
        var_scenario_index=contributions.var_scenario_index,
        positions=positions,
        reconciliation_difference=contributions.reconciliation_difference,
    )
