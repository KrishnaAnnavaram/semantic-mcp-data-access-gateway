"""Where the money actually came from.  `carry_roll_rate_residual_v1`

Between two dates a book made or lost an amount. Attribution splits that amount
into causes, and the split is only worth having if it is checked - which is what
the residual is for.

    total P&L = value change + cash received
              = carry + roll-down + rate move + position change + residual

The first four are computed independently, each by full revaluation; the
residual is whatever is left. **It is never forced to zero, and it is never
plugged.**

At the top level it will normally come back at machine precision, and that is a
result rather than a decoration: it says the four effects, each priced
separately, actually account for the whole move. A non-zero figure there means
something in the chain disagrees with itself and the attribution should not be
used.

**The residual that carries information is `rate_unexplained`.** Splitting the
rate effect across the curve by key-rate DV01 is a first-order approximation, so
its parts do not sum to the whole - and the gap is the book's convexity. On this
demo book a 50bp move at one node leaves about a thousand dollars unexplained;
a 300bp parallel move leaves the better part of a million. That number is the
model control, it is reported next to the tenor table, and scaling the tenor
contributions up to close it would destroy the only diagnostic in the report.

## The four effects

* **Carry** - the horizon value on the forward curve, plus cash received, less
  the starting value. What holding the position earns if the market delivers
  exactly what it promised. From `carry_roll.py`.
* **Roll-down** - the extra from ageing down a sloped static curve.
* **Rate move** - the aged book revalued under the new curve rather than the old
  one. This is the market's contribution, measured at the *end* date so that it
  does not double-count the passage of time.
* **Position change** - the end book revalued under the end curve, less the
  start book revalued the same way. Zero when nothing traded, and computed only
  when a second position snapshot is supplied. Without one the field is null,
  not zero: "no positions changed" and "we were not told" are different claims.

Ordering matters and is stated: time first (on the old curve), then rates (on
the aged book), then positions. A different order attributes the interaction
terms differently and every order leaves *some* interaction in the residual.
This one is chosen because it matches how the book actually evolved.

## The rate move, by tenor

The rate effect is further split across the curve by first-order key-rate DV01
times the observed change at each node. That sum does **not** equal the rate
effect - it omits convexity and cross-tenor terms - and the shortfall is
reported as `rate_unexplained`. On a quiet day it is a rounding error; after a
150bp move on a long book it is real money, and seeing it is the point.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass

from .carry_roll import compute_carry_roll
from .contributions import bucket_for
from .curve_analytics import curve_change_bp
from .curves import ParCurve, build_discount_curve
from .errors import EngineError
from .pricing import Position
from .revaluation import compile_book, key_rate_exposures


@dataclass(frozen=True)
class TenorEffect:
    tenor_years: float
    change_bp: float
    key_rate_dv01: float
    pnl: float
    contribution_percent: float


@dataclass(frozen=True)
class PositionEffect:
    instrument_id: str
    start_value: float
    end_value: float
    cash_received: float
    total_pnl: float
    carry: float
    roll_down: float


@dataclass(frozen=True)
class PnlAttribution:
    start_date: dt.date
    end_date: dt.date
    days: int
    start_value: float
    end_value: float
    cash_received: float
    total_pnl: float

    carry: float
    roll_down: float
    rate_move: float
    position_change: float | None
    residual: float
    explained_pnl: float
    unexplained_percent: float

    tenor_effects: tuple[TenorEffect, ...]
    bucket_effects: tuple[tuple[str, float], ...]
    rate_explained_by_tenor: float
    rate_unexplained: float
    rate_unexplained_percent: float
    positions: tuple[PositionEffect, ...]

    method: str = "carry_roll_rate_residual_v1"
    ordering: str = (
        "time on the starting curve, then rates on the aged book, then position "
        "changes on the ending curve"
    )
    residual_note: str = (
        "Two residuals, and they mean different things. `residual` compares the "
        "four revalued effects with the total and should be at machine "
        "precision - a non-zero value there means the decomposition disagrees "
        "with itself. `rate_unexplained` is the first-order tenor split's "
        "shortfall against the rate effect: it is the portfolio's convexity, it "
        "grows with the size of the move, and it is never scaled away."
    )


def compute_pnl_attribution(
    positions_start: Sequence[Position], start_date: dt.date, start_curve: ParCurve,
    end_date: dt.date, end_curve: ParCurve,
    positions_end: Sequence[Position] | None = None,
) -> PnlAttribution:
    if end_date <= start_date:
        raise EngineError(
            "INVALID_HORIZON",
            f"the attribution period runs backwards or is empty: {start_date} to "
            f"{end_date}",
            category="USER_INPUT",
            suggested_action="Give an end date after the start date.")

    start_book = compile_book(positions_start, start_date)
    aged_book = compile_book(positions_start, end_date)

    start_value = start_book.value_under(start_curve)
    aged_on_old = aged_book.value_under(start_curve)
    aged_on_new = aged_book.value_under(end_curve)

    carry_roll = compute_carry_roll(positions_start, start_date, end_date, start_curve)
    cash_received = carry_roll.cash_received

    rate_move = aged_on_new - aged_on_old

    if positions_end is not None:
        end_book = compile_book(positions_end, end_date)
        end_value = end_book.value_under(end_curve)
        position_change: float | None = end_value - aged_on_new
    else:
        end_book = aged_book
        end_value = aged_on_new
        position_change = None

    total_pnl = end_value + cash_received - start_value
    explained = carry_roll.carry + carry_roll.roll_down + rate_move + (position_change or 0.0)
    residual = total_pnl - explained

    shared = sorted(set(start_curve.tenors_years) & set(end_curve.tenors_years))
    if len(shared) < 2:
        raise EngineError(
            "MISSING_CURVE_TENOR",
            "the two curves share fewer than two tenors, so the rate move cannot "
            "be split across the curve.",
            category="DATA_AVAILABILITY",
            suggested_action="Fetch both curves on the same tenor set.")
    changes = curve_change_bp(start_curve, end_curve, shared)
    _, krd_totals, _ = key_rate_exposures(aged_book, start_curve, 1.0)
    krd = dict(krd_totals)

    tenor_effects = tuple(
        TenorEffect(
            tenor_years=t, change_bp=changes[t], key_rate_dv01=krd.get(t, 0.0),
            pnl=-krd.get(t, 0.0) * changes[t],
            contribution_percent=((-krd.get(t, 0.0) * changes[t]) / rate_move * 100.0)
            if rate_move else 0.0)
        for t in shared if t in krd)
    rate_explained = sum(e.pnl for e in tenor_effects)

    by_bucket: dict[str, float] = {}
    for effect in tenor_effects:
        label = bucket_for(effect.tenor_years)
        by_bucket[label] = by_bucket.get(label, 0.0) + effect.pnl

    start_values = start_book.price_positions(build_discount_curve(start_curve))
    end_values = end_book.price_positions(build_discount_curve(end_curve))
    carry_by_id = {p.instrument_id: p for p in carry_roll.positions}
    end_by_id = dict(zip(end_book.instrument_ids(), end_values))
    position_effects = tuple(
        PositionEffect(
            instrument_id=iid,
            start_value=sv,
            end_value=end_by_id.get(iid, 0.0),
            cash_received=carry_by_id[iid].cash_received if iid in carry_by_id else 0.0,
            total_pnl=(end_by_id.get(iid, 0.0)
                       + (carry_by_id[iid].cash_received if iid in carry_by_id else 0.0)
                       - sv),
            carry=carry_by_id[iid].carry if iid in carry_by_id else 0.0,
            roll_down=carry_by_id[iid].roll_down if iid in carry_by_id else 0.0)
        for iid, sv in zip(start_book.instrument_ids(), start_values))

    return PnlAttribution(
        start_date=start_date, end_date=end_date,
        days=(end_date - start_date).days,
        start_value=start_value, end_value=end_value, cash_received=cash_received,
        total_pnl=total_pnl, carry=carry_roll.carry, roll_down=carry_roll.roll_down,
        rate_move=rate_move, position_change=position_change, residual=residual,
        explained_pnl=explained,
        unexplained_percent=(abs(residual) / abs(total_pnl) * 100.0)
        if total_pnl else 0.0,
        tenor_effects=tenor_effects,
        bucket_effects=tuple(sorted(by_bucket.items())),
        rate_explained_by_tenor=rate_explained,
        rate_unexplained=rate_move - rate_explained,
        rate_unexplained_percent=(abs(rate_move - rate_explained) / abs(rate_move)
                                  * 100.0) if rate_move else 0.0,
        positions=position_effects,
    )
