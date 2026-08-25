"""Stress from what actually happened.  `observed_curve_difference_full_reval_v1`

The strongest scenario is one nobody designed. A hypothetical bear steepener is
an opinion about how curves move; the move from 2008-09-12 to 2008-12-31 is a
fact, and a portfolio's loss under it is a fact about the portfolio.

So **no shock in this module is written down anywhere**. Every one is the
difference between two curves that Treasury published, measured here, at the
moment of use. The crisis catalogue below contains *dates*, never basis points.
That distinction is the whole design: a hard-coded "2008 shock vector" is a
number somebody typed, it decays as the data is revised, and nobody can audit it
without re-deriving it - at which point they may as well have derived it.

## Coverage is checked, never assumed

A named crisis whose window the supplied history does not cover returns
`UNSUPPORTED_CRISIS_SCENARIO` naming what was missing. A tenor present on one
date and absent on the other is refused by default, because a shock vector that
silently omits the 30-year understates the loss on every long bond in the book
and reports success. `missing_tenor_policy='intersection'` accepts that
trade-off explicitly and lists the tenors it left unshocked.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .contributions import StressRun, run_shock
from .curve_analytics import curve_change_bp
from .curves import CurveError, ParCurve
from .errors import EngineError
from .revaluation import CompiledBook, run_scenarios
from .stress_scenarios import ShockVector

MissingTenorPolicy = Literal["reject", "intersection"]

CRISIS_CATALOGUE_VERSION = "documented_windows_v1"


@dataclass(frozen=True)
class HistoricalCrisis:
    """A named window, and nothing else. The shock is derived, never stored."""

    crisis_id: str
    name: str
    start_date: dt.date
    end_date: dt.date
    description: str
    what_happened: str


# Windows chosen from the documented record of each episode and expressed as
# Treasury publication dates. Each is checked against the history actually
# supplied before it is used; none carries a rate.
CRISIS_CATALOGUE: tuple[HistoricalCrisis, ...] = (
    HistoricalCrisis(
        crisis_id="1994_BOND_SELLOFF",
        name="1994 bond market selloff",
        start_date=dt.date(1994, 1, 31), end_date=dt.date(1994, 11, 30),
        description=(
            "The Federal Reserve began tightening on 4 February 1994 after five "
            "years of easing, and continued through the year."),
        what_happened=(
            "A large, sustained, broadly parallel rise in Treasury yields across "
            "the curve. The canonical bad year for a long duration book."),
    ),
    HistoricalCrisis(
        crisis_id="2008_GFC_LEHMAN",
        name="2008 financial crisis (Lehman to year end)",
        start_date=dt.date(2008, 9, 12), end_date=dt.date(2008, 12, 31),
        description=(
            "From the last trading day before Lehman Brothers filed for "
            "bankruptcy to the end of 2008."),
        what_happened=(
            "A violent flight to quality: Treasury yields collapsed across the "
            "curve, with the front end pinned near zero. A long Treasury book "
            "*gained* here - which is exactly why it belongs in a stress pack "
            "that is meant to test a portfolio rather than confirm it."),
    ),
    HistoricalCrisis(
        crisis_id="2013_TAPER_TANTRUM",
        name="2013 taper tantrum",
        start_date=dt.date(2013, 5, 1), end_date=dt.date(2013, 9, 5),
        description=(
            "From before the 22 May 2013 congressional testimony that raised the "
            "prospect of tapering asset purchases, to the early-September peak "
            "in yields."),
        what_happened=(
            "A sharp bear steepening. The belly and long end sold off far more "
            "than the anchored front end."),
    ),
    HistoricalCrisis(
        crisis_id="2020_COVID_SHOCK",
        name="March 2020 COVID rate shock",
        start_date=dt.date(2020, 2, 19), end_date=dt.date(2020, 3, 9),
        description=(
            "From the pre-pandemic equity peak to the 9 March 2020 low in "
            "Treasury yields."),
        what_happened=(
            "The fastest collapse in Treasury yields on record; the entire curve "
            "fell below 1%. A bull flattening of extraordinary speed."),
    ),
    HistoricalCrisis(
        crisis_id="2022_FED_TIGHTENING",
        name="2022 rapid Fed tightening",
        start_date=dt.date(2022, 1, 3), end_date=dt.date(2022, 10, 24),
        description=(
            "From the first trading day of 2022 to the October peak in long "
            "yields, spanning the fastest tightening cycle since 1994."),
        what_happened=(
            "A very large bear flattening: the front end rose far more than the "
            "long end, and the curve inverted. The worst calendar year for US "
            "Treasuries in the modern record."),
    ),
    HistoricalCrisis(
        crisis_id="2023_REGIONAL_BANK_STRESS",
        name="March 2023 regional bank stress",
        start_date=dt.date(2023, 3, 8), end_date=dt.date(2023, 3, 24),
        description=(
            "From the day before Silicon Valley Bank's failure became public to "
            "the end of the acute phase."),
        what_happened=(
            "A violent bull steepening: the two-year fell by roughly a percentage "
            "point in days while the long end moved far less."),
    ),
)

CRISIS_BY_ID = {c.crisis_id: c for c in CRISIS_CATALOGUE}


@dataclass(frozen=True)
class DatedCurve:
    observation_date: dt.date
    curve: ParCurve


@dataclass(frozen=True)
class HistoricalReplay:
    run: StressRun
    historical_start: dt.date | None
    historical_end: dt.date | None
    observed_shocks_bp: dict[float, float]
    tenors_used: tuple[float, ...]
    tenors_unshocked: tuple[float, ...]
    crisis_id: str | None
    crisis_name: str | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class WorstCase:
    rank: int
    start_date: dt.date | None
    end_date: dt.date | None
    start_index: int
    end_index: int
    shocks_bp: dict[float, float]
    pnl: float
    pnl_percent: float
    largest_position_contributor: str | None
    largest_position_pnl: float


@dataclass(frozen=True)
class WorstHistorical:
    base_value: float
    horizon_days: int
    scenarios_considered: int
    lookback_observations: int
    first_date: dt.date | None
    last_date: dt.date | None
    worst: tuple[WorstCase, ...]
    best_pnl: float
    mean_pnl: float


def observed_shock(
    before: ParCurve, after: ParCurve, live_tenors: Sequence[float],
    missing_tenor_policy: MissingTenorPolicy = "reject",
) -> tuple[dict[float, float], tuple[float, ...], tuple[float, ...], list[str]]:
    """Difference two published curves onto the tenors of the curve being stressed."""
    shared = sorted(set(before.tenors_years) & set(after.tenors_years) & set(live_tenors))
    missing = sorted(set(live_tenors) - set(shared))
    warnings: list[str] = []
    if len(shared) < 2:
        raise EngineError(
            "MISSING_REQUIRED_MARKET_DATA",
            "the two historical curves and the curve being stressed share fewer "
            "than two tenors, so no meaningful move can be measured between them.",
            category="DATA_AVAILABILITY",
            suggested_action=(
                "Fetch both historical curves on the same tenor set as the "
                "valuation curve."),
            details={"shared_tenors_years": shared,
                     "before_tenors_years": list(before.tenors_years),
                     "after_tenors_years": list(after.tenors_years)})
    if missing and missing_tenor_policy == "reject":
        raise EngineError(
            "MISSING_CURVE_TENOR",
            f"tenors {missing} exist on the valuation curve but not on both "
            "historical dates. Leaving them unshocked would understate the loss "
            "on every position that discounts off them, and the result would "
            "not say so.",
            category="DATA_AVAILABILITY",
            retryable=True,
            suggested_action=(
                "Choose historical dates where those tenors were published, or "
                "pass missing_tenor_policy='intersection' to accept that they "
                "stay unshocked - the result will list them."),
            details={"unavailable_tenors_years": missing})
    if missing:
        warnings.append(
            f"tenors {missing} were not published on both historical dates and "
            "were left unshocked; the loss is understated for positions "
            "discounting off them.")
    return curve_change_bp(before, after, shared), tuple(shared), tuple(missing), warnings


def run_historical_replay(
    book: CompiledBook, par: ParCurve, before: DatedCurve, after: DatedCurve,
    missing_tenor_policy: MissingTenorPolicy = "reject",
    crisis: HistoricalCrisis | None = None,
) -> HistoricalReplay:
    if after.observation_date <= before.observation_date:
        raise EngineError(
            "INVALID_STRESS_VECTOR",
            f"the replay window runs backwards: {before.observation_date} to "
            f"{after.observation_date}. A shock is the later curve minus the "
            "earlier one, so the order changes its sign.",
            category="USER_INPUT",
            suggested_action="Swap the two dates.")
    shocks, used, missing, warnings = observed_shock(
        before.curve, after.curve, par.tenors_years, missing_tenor_policy)

    label = (f"{crisis.name} ({before.observation_date} to {after.observation_date})"
             if crisis else
             f"Historical replay {before.observation_date} to {after.observation_date}")
    vector = ShockVector(
        scenario_name=label, scenario_type="HISTORICAL_REPLAY",
        shocks_bp_by_tenor_years={t: shocks.get(t, 0.0) for t in par.tenors_years},
        severity_bp=max((abs(v) for v in shocks.values()), default=0.0),
        parameters={
            "historical_start": before.observation_date.isoformat(),
            "historical_end": after.observation_date.isoformat(),
            "derivation": "observed curve difference, measured at run time",
            **({"crisis_id": crisis.crisis_id} if crisis else {}),
        })
    try:
        run = run_shock(book, par, vector)
    except CurveError as exc:
        raise EngineError(
            "INVALID_CURVE",
            f"applying the observed {before.observation_date} to "
            f"{after.observation_date} move to the valuation curve produces a "
            f"curve the bootstrap rejects: {exc}",
            category="NUMERICAL",
            suggested_action=(
                "This combination of a historical move and today's curve shape "
                "is not arbitrage-consistent under this bootstrap. Try a "
                "shorter window or a different valuation date."),
        ) from exc

    return HistoricalReplay(
        run=run, historical_start=before.observation_date,
        historical_end=after.observation_date, observed_shocks_bp=shocks,
        tenors_used=used, tenors_unshocked=missing,
        crisis_id=crisis.crisis_id if crisis else None,
        crisis_name=crisis.name if crisis else None,
        warnings=tuple(warnings),
    )


def resolve_crisis(crisis_id: str) -> HistoricalCrisis:
    key = crisis_id.upper()
    if key not in CRISIS_BY_ID:
        raise EngineError(
            "UNSUPPORTED_CRISIS_SCENARIO",
            f"{crisis_id!r} is not in this engine's crisis catalogue.",
            category="USER_INPUT",
            suggested_action=(
                "Read risk://scenarios/historical-crises for the catalogue, or "
                "use run_historical_stress_tool with two explicit dates."),
            details={"available": [
                {"crisis_id": c.crisis_id, "name": c.name,
                 "start_date": c.start_date.isoformat(),
                 "end_date": c.end_date.isoformat()} for c in CRISIS_CATALOGUE]})
    return CRISIS_BY_ID[key]


def select_crisis_curves(
    crisis: HistoricalCrisis, curves: Sequence[DatedCurve],
    tolerance_days: int = 7,
) -> tuple[DatedCurve, DatedCurve]:
    """Pick the published curves closest to the documented window boundaries.

    Treasury does not publish on weekends or holidays, so an exact match on a
    documented date is the exception. A tolerance is allowed and the dates
    actually used are reported; beyond it the scenario is refused rather than
    stretched, because a "2020 COVID shock" measured from a date three weeks
    away is a different scenario wearing the same name.
    """
    if not curves:
        raise EngineError(
            "UNSUPPORTED_CRISIS_SCENARIO",
            f"no historical curves were supplied for {crisis.name}.",
            category="DATA_AVAILABILITY",
            suggested_action=(
                f"Fetch the curves for {crisis.start_date} and "
                f"{crisis.end_date} from the data server and pass them in."))

    def nearest(target: dt.date) -> tuple[DatedCurve, int]:
        best = min(curves, key=lambda c: abs((c.observation_date - target).days))
        return best, abs((best.observation_date - target).days)

    start, start_gap = nearest(crisis.start_date)
    end, end_gap = nearest(crisis.end_date)
    if start_gap > tolerance_days or end_gap > tolerance_days:
        raise EngineError(
            "UNSUPPORTED_CRISIS_SCENARIO",
            f"the supplied history does not cover {crisis.name}. The window is "
            f"{crisis.start_date} to {crisis.end_date}; the nearest curves "
            f"supplied are {start.observation_date} ({start_gap} days away) and "
            f"{end.observation_date} ({end_gap} days away), and the tolerance is "
            f"{tolerance_days} days.",
            category="DATA_AVAILABILITY",
            suggested_action=(
                "Fetch curves inside the documented window, or widen "
                "tolerance_days deliberately and accept that the scenario is no "
                "longer the one it is named after."),
            details={"crisis_id": crisis.crisis_id,
                     "window_start": crisis.start_date.isoformat(),
                     "window_end": crisis.end_date.isoformat(),
                     "nearest_start": start.observation_date.isoformat(),
                     "nearest_end": end.observation_date.isoformat()})
    if end.observation_date <= start.observation_date:
        raise EngineError(
            "UNSUPPORTED_CRISIS_SCENARIO",
            f"the curves matched to {crisis.name} do not straddle the window "
            f"({start.observation_date} to {end.observation_date}).",
            category="DATA_AVAILABILITY",
            suggested_action="Supply curves for both ends of the window.")
    return start, end


def find_worst_historical(
    book: CompiledBook, par: ParCurve,
    history_tenors_years: Sequence[float],
    history_rates_percent: Sequence[Sequence[float]],
    history_dates: Sequence[dt.date] | None = None,
    horizon_days: int = 1, top_n: int = 10,
) -> WorstHistorical:
    """Replay every observed h-day move in the window against today's book.

    "If this portfolio had existed throughout history, which moves would have
    hurt most?" Each candidate is a full revaluation, so the ranking reflects
    the book's convexity rather than a delta approximation - and the answer is
    frequently not the largest move, because a portfolio concentrated in the
    belly loses more from a mid-curve shock than from a bigger parallel one.
    """
    rows = [list(map(float, r)) for r in history_rates_percent]
    n_obs = len(rows)
    width = len(history_tenors_years)
    if horizon_days < 1:
        raise EngineError(
            "INVALID_HORIZON", f"horizon_days must be at least 1; got {horizon_days}",
            category="USER_INPUT")
    if top_n < 1:
        raise EngineError(
            "INVALID_HORIZON", f"top_n must be at least 1; got {top_n}",
            category="USER_INPUT")
    if n_obs < horizon_days + 2:
        raise EngineError(
            "INSUFFICIENT_HISTORY",
            f"{n_obs} observations cannot produce {horizon_days}-day changes; at "
            f"least {horizon_days + 2} are needed.",
            category="DATA_AVAILABILITY", retryable=True,
            suggested_action=(
                f"Request at least {horizon_days + 2} trading days, or shorten "
                "the horizon."))
    if any(len(r) != width for r in rows):
        raise EngineError(
            "INSUFFICIENT_HISTORY",
            "the history matrix is ragged: every row must cover every tenor",
            category="DATA_AVAILABILITY",
            suggested_action="Re-fetch the matrix with missing_policy='reject'.")
    if history_dates is not None and len(history_dates) != n_obs:
        raise EngineError(
            "INSUFFICIENT_HISTORY",
            f"{len(history_dates)} dates were supplied for {n_obs} rows of rates",
            category="USER_INPUT",
            suggested_action="Pass one date per row, or omit the dates entirely.")

    live = set(par.tenors_years)
    index_of = {j: float(t) for j, t in enumerate(history_tenors_years)}
    vectors: list[dict[float, float]] = []
    windows: list[tuple[int, int]] = []
    for i in range(horizon_days, n_obs):
        shocks = {index_of[j]: (rows[i][j] - rows[i - horizon_days][j]) * 100.0
                  for j in range(width) if index_of[j] in live}
        vectors.append(shocks)
        windows.append((i - horizon_days, i))

    scenarios = run_scenarios(book, par, vectors)
    order = sorted(range(len(scenarios.pnl)), key=lambda i: scenarios.pnl[i])
    ids = scenarios.instrument_ids

    worst: list[WorstCase] = []
    for rank, idx in enumerate(order[:top_n], start=1):
        row = scenarios.pnl_per_position[idx]
        j = min(range(len(row)), key=lambda k: row[k]) if row else None
        start_i, end_i = windows[idx]
        worst.append(WorstCase(
            rank=rank,
            start_date=history_dates[start_i] if history_dates else None,
            end_date=history_dates[end_i] if history_dates else None,
            start_index=start_i, end_index=end_i,
            shocks_bp=vectors[idx], pnl=scenarios.pnl[idx],
            pnl_percent=(scenarios.pnl[idx] / scenarios.base_value * 100.0)
            if scenarios.base_value else 0.0,
            largest_position_contributor=ids[j] if j is not None else None,
            largest_position_pnl=row[j] if j is not None else 0.0))

    return WorstHistorical(
        base_value=scenarios.base_value, horizon_days=horizon_days,
        scenarios_considered=len(vectors), lookback_observations=n_obs,
        first_date=history_dates[0] if history_dates else None,
        last_date=history_dates[-1] if history_dates else None,
        worst=tuple(worst), best_pnl=max(scenarios.pnl),
        mean_pnl=sum(scenarios.pnl) / len(scenarios.pnl),
    )
