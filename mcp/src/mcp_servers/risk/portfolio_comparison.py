"""Two books, the same measures.  `paired_measure_difference_v1`

"Is the hedge working?" and "what does this trade do to my risk?" are the same
question asked twice, and both reduce to running one set of measures over two
books and differencing.

The discipline that makes the comparison mean anything is that **both sides run
on identical inputs**: the same valuation date, the same curve, the same history,
the same confidence level, the same seed. A hedged book measured against
yesterday's curve looks better than it is, and nothing in the output would say
so. Every measure below is computed inside one call from one set of arguments,
so the two sides cannot drift apart.

`analyse_hypothetical_trade` builds the "after" book by **appending to a copy**.
The stored positions are never mutated, because a risk system that answers "what
if I bought this" by buying it is not a risk system. The hypothetical book exists
for the duration of the call and is thrown away.

Where a measure needs history and none was given, it is omitted from both sides
rather than defaulted on either. A comparison table with VaR on one side and a
blank on the other invites the reader to fill the blank in themselves.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass

from .contributions import run_shock
from .curves import ParCurve
from .errors import EngineError
from .pricing import FixedRateBond, Position
from .revaluation import CompiledBook, compile_book, key_rate_exposures, run_scenarios
from .risk import nearest_rank_quantile
from .sensitivities import compute_rate_sensitivities
from .stress_scenarios import ShockVector
from .volatility import observed_changes_bp


@dataclass(frozen=True)
class MeasureRow:
    measure: str
    unit: str
    portfolio_a: float
    portfolio_b: float
    difference: float
    percent_change: float | None
    interpretation: str


@dataclass(frozen=True)
class KeyRateRow:
    tenor_years: float
    portfolio_a: float
    portfolio_b: float
    difference: float


@dataclass(frozen=True)
class PortfolioComparison:
    label_a: str
    label_b: str
    valuation_date: dt.date
    rows: tuple[MeasureRow, ...]
    key_rates: tuple[KeyRateRow, ...]
    scenario_rows: tuple[MeasureRow, ...]
    risk_reduction_percent: float | None
    measures_omitted: tuple[str, ...]
    method: str = "paired_measure_difference_v1"
    note: str = (
        "Both books are measured on the same valuation date, the same curve, "
        "the same history and the same confidence level, inside one call."
    )


def _row(measure: str, unit: str, a: float, b: float, interpretation: str) -> MeasureRow:
    return MeasureRow(
        measure=measure, unit=unit, portfolio_a=a, portfolio_b=b,
        difference=b - a,
        percent_change=((b - a) / abs(a) * 100.0) if a else None,
        interpretation=interpretation)


def _historical_var_es(
    book: CompiledBook, par: ParCurve, history_tenors_years: Sequence[float],
    history_rates_percent: Sequence[Sequence[float]], confidence_level: float,
    horizon_days: int,
) -> tuple[float, float]:
    live = set(par.tenors_years)
    columns = [j for j, t in enumerate(history_tenors_years) if float(t) in live]
    tenors = [float(history_tenors_years[j]) for j in columns]
    changes = observed_changes_bp(history_rates_percent, horizon_days)
    vectors = [{tenors[i]: row[columns[i]] for i in range(len(tenors))}
               for row in changes]
    scenarios = run_scenarios(book, par, vectors)
    losses = scenarios.losses_sorted()
    var, _ = nearest_rank_quantile(losses, confidence_level)
    var = max(0.0, var)
    tail = [loss for loss in losses if loss >= var]
    return var, (sum(tail) / len(tail) if tail else var)


def compare_portfolios(
    positions_a: Sequence[Position], positions_b: Sequence[Position],
    valuation_date: dt.date, par: ParCurve,
    label_a: str = "Portfolio A", label_b: str = "Portfolio B",
    scenarios: Sequence[ShockVector] = (),
    history_tenors_years: Sequence[float] | None = None,
    history_rates_percent: Sequence[Sequence[float]] | None = None,
    confidence_level: float = 0.99, horizon_days: int = 1,
) -> PortfolioComparison:
    book_a = compile_book(positions_a, valuation_date)
    book_b = compile_book(positions_b, valuation_date)
    sens_a = compute_rate_sensitivities(book_a, par)
    sens_b = compute_rate_sensitivities(book_b, par)

    rows = [
        _row("present_value", "USD", sens_a.base_value, sens_b.base_value,
             "model-implied dirty value of the two books"),
        _row("dv01", "USD per basis point", sens_a.dv01, sens_b.dv01,
             "value lost from a parallel 1bp rise; positive for a long book"),
        _row("dollar_duration", "USD", sens_a.dollar_duration, sens_b.dollar_duration,
             "DV01 x 10,000"),
        _row("effective_duration", "years", sens_a.effective_duration_years,
             sens_b.effective_duration_years,
             f"central difference on a {sens_a.effective_bump_bp:g}bp parallel shift"),
        _row("effective_convexity", "years squared", sens_a.effective_convexity,
             sens_b.effective_convexity,
             "second-order curvature of value against a parallel yield move"),
        _row("dv01_concentration_hhi", "index",
             sens_a.dv01_concentration.herfindahl_index,
             sens_b.dv01_concentration.herfindahl_index,
             "Herfindahl index of absolute position DV01; higher is more concentrated"),
        _row("dv01_effective_position_count", "positions",
             sens_a.dv01_concentration.effective_count,
             sens_b.dv01_concentration.effective_count,
             "how many equally sized positions would be this concentrated"),
    ]

    _, krd_a, _ = key_rate_exposures(book_a, par, 1.0)
    _, krd_b, _ = key_rate_exposures(book_b, par, 1.0)
    lookup_b = dict(krd_b)
    key_rates = tuple(
        KeyRateRow(tenor_years=t, portfolio_a=v, portfolio_b=lookup_b.get(t, 0.0),
                   difference=lookup_b.get(t, 0.0) - v)
        for t, v in krd_a)

    scenario_rows = []
    for vector in scenarios:
        run_a = run_shock(book_a, par, vector)
        run_b = run_shock(book_b, par, vector)
        scenario_rows.append(_row(
            vector.scenario_name, "USD", run_a.pnl, run_b.pnl,
            "full revaluation P&L; negative is a loss"))

    omitted: list[str] = []
    if history_tenors_years is not None and history_rates_percent is not None:
        var_a, es_a = _historical_var_es(
            book_a, par, history_tenors_years, history_rates_percent,
            confidence_level, horizon_days)
        var_b, es_b = _historical_var_es(
            book_b, par, history_tenors_years, history_rates_percent,
            confidence_level, horizon_days)
        rows.append(_row(
            f"historical_var_{confidence_level:.0%}_{horizon_days}d", "USD",
            var_a, var_b, "historical simulation, full revaluation, nearest rank"))
        rows.append(_row(
            f"historical_es_{confidence_level:.0%}_{horizon_days}d", "USD",
            es_a, es_b, "mean of losses at or beyond the VaR quantile"))
    else:
        omitted.extend(["historical_var", "historical_es"])

    reduction = (((abs(sens_a.dv01) - abs(sens_b.dv01)) / abs(sens_a.dv01) * 100.0)
                 if sens_a.dv01 else None)
    return PortfolioComparison(
        label_a=label_a, label_b=label_b, valuation_date=valuation_date,
        rows=tuple(rows), key_rates=key_rates, scenario_rows=tuple(scenario_rows),
        risk_reduction_percent=reduction, measures_omitted=tuple(omitted),
    )


def analyse_hypothetical_trade(
    positions: Sequence[Position], hypothetical: Sequence[Position],
    valuation_date: dt.date, par: ParCurve,
    scenarios: Sequence[ShockVector] = (),
    history_tenors_years: Sequence[float] | None = None,
    history_rates_percent: Sequence[Sequence[float]] | None = None,
    confidence_level: float = 0.99, horizon_days: int = 1,
) -> PortfolioComparison:
    """Risk before and after adding positions, without touching the stored book."""
    if not hypothetical:
        raise EngineError(
            "INCONSISTENT_PORTFOLIOS",
            "no hypothetical positions were supplied, so there is nothing to "
            "compare the current book against.",
            category="USER_INPUT",
            suggested_action="Supply at least one position to add.")
    combined = list(positions) + list(hypothetical)
    return compare_portfolios(
        positions, combined, valuation_date, par,
        label_a="Current book", label_b="Current book plus hypothetical trade",
        scenarios=scenarios, history_tenors_years=history_tenors_years,
        history_rates_percent=history_rates_percent,
        confidence_level=confidence_level, horizon_days=horizon_days)


@dataclass(frozen=True)
class HedgeCandidate:
    tenor_years: float
    instrument_id: str
    maturity_date: dt.date
    coupon_rate_pct: float
    hedge_notional: float
    pre_hedge_key_rate_dv01: float
    post_hedge_key_rate_dv01: float
    pre_hedge_portfolio_dv01: float
    post_hedge_portfolio_dv01: float
    residual_key_rate_dv01: tuple[tuple[float, float], ...]


def size_key_rate_hedge(
    positions: Sequence[Position], valuation_date: dt.date, par: ParCurve,
    hedge_tenor_years: float, target_key_rate_dv01: float = 0.0,
) -> HedgeCandidate:
    """Size a par bond at one tenor so that tenor's key-rate DV01 hits a target.

    Deterministic risk analytics, not a recommendation. The hedge instrument is a
    newly issued bond paying the curve's own par rate at the chosen tenor, which
    is the cleanest available proxy for the on-the-run issue and keeps the
    construction reproducible: nothing about it depends on which bond happened to
    be cheapest to deliver.

    The sizing is linear - key-rate DV01 scales with notional - so it is solved
    in closed form from a single unit-notional measurement rather than iterated.
    The result reports what happens at *every other* tenor too, because a hedge
    that flattens one node and moves three others is not a hedge, and that is
    exactly what a single-number answer would conceal.
    """
    if hedge_tenor_years not in set(par.tenors_years):
        raise EngineError(
            "MISSING_CURVE_TENOR",
            f"{hedge_tenor_years:g}y is not a node on this curve, so its "
            "key-rate DV01 is not defined.",
            category="USER_INPUT",
            suggested_action=f"Choose from {list(par.tenors_years)}.",
            details={"curve_nodes_years": list(par.tenors_years)})

    book = compile_book(positions, valuation_date)
    _, krd_before, _ = key_rate_exposures(book, par, 1.0)
    before = dict(krd_before)

    coupon = par.par_rate_at(hedge_tenor_years)
    maturity = _add_years(valuation_date, hedge_tenor_years)
    unit_notional = 1_000_000.0
    probe = FixedRateBond(
        instrument_id=f"HEDGE_PAR_{hedge_tenor_years:g}Y", face_value=1000.0,
        coupon_rate_pct=coupon, maturity_date=maturity, issue_date=valuation_date)
    probe_book = compile_book([Position(probe, unit_notional)], valuation_date)
    _, probe_krd, _ = key_rate_exposures(probe_book, par, 1.0)
    probe_lookup = dict(probe_krd)
    per_million = probe_lookup[hedge_tenor_years]
    if per_million == 0:
        raise EngineError(
            "MISSING_CURVE_TENOR",
            f"a par bond maturing at {hedge_tenor_years:g}y has no measurable "
            "sensitivity to that node, so it cannot hedge it.",
            category="NUMERICAL")

    needed = (target_key_rate_dv01 - before[hedge_tenor_years]) / per_million
    notional = needed * unit_notional

    hedged = list(positions) + [Position(probe, notional)]
    hedged_book = compile_book(hedged, valuation_date)
    _, krd_after, _ = key_rate_exposures(hedged_book, par, 1.0)
    after = dict(krd_after)

    return HedgeCandidate(
        tenor_years=hedge_tenor_years, instrument_id=probe.instrument_id,
        maturity_date=maturity, coupon_rate_pct=coupon, hedge_notional=notional,
        pre_hedge_key_rate_dv01=before[hedge_tenor_years],
        post_hedge_key_rate_dv01=after[hedge_tenor_years],
        pre_hedge_portfolio_dv01=sum(before.values()),
        post_hedge_portfolio_dv01=sum(after.values()),
        residual_key_rate_dv01=tuple((t, after[t]) for t in par.tenors_years),
    )


def _add_years(date: dt.date, years: float) -> dt.date:
    """Advance a date by a possibly fractional number of years, month-aligned.

    Month arithmetic rather than day arithmetic, so a hedge at the 10-year node
    matures on the same day of the month as the valuation date and its coupon
    schedule lines up with the semiannual grid the bootstrap uses.
    """
    months = round(years * 12)
    year = date.year + (date.month - 1 + months) // 12
    month = (date.month - 1 + months) % 12 + 1
    day = min(date.day, _days_in_month(year, month))
    return dt.date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (dt.date(year + (month // 12), month % 12 + 1, 1) - dt.timedelta(days=1)).day
