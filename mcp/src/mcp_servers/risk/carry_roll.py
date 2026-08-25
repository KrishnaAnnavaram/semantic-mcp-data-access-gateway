"""Carry and roll-down.  `forward_value_carry_static_curve_roll_v1`

What a bond earns if the curve does not move. Two effects, routinely conflated,
and the conflation matters because they respond to different things:

**Carry** is the return from simply holding the position and letting time pass:
coupon received, plus the pull of the price towards par as the discounting
shortens. It is measured against the **forward curve** - the curve today's curve
implies for the horizon date - because that is the no-arbitrage benchmark. A
position earning exactly its carry has earned nothing the market did not already
promise.

**Roll-down** is the extra, and it exists only because the curve has slope. A
ten-year bond held for a year becomes a nine-year bond, and on an upward-sloping
curve a nine-year discounts at a lower rate than a ten-year did. That price gain
is roll: it is the difference between valuing the aged position on the *static*
curve and valuing it on the forward curve.

    carry = V_forward(t1) + cash received - V(t0)
    roll  = V_static(t1)  - V_forward(t1)
    total = carry + roll  =  V_static(t1) + cash received - V(t0)

On a flat curve roll is zero and carry is everything. On a steep curve roll can
be the larger half - which is precisely why a desk that reports only "carry" on
a steep curve is reporting the smaller number and calling it the total.

**Coupons received during the period are counted at face, not reinvested.**
That is a convention and it is visible in the answer: a one-year hold on a flat
6% curve returns slightly more than 6% (the position itself compounds to the
horizon) and slightly less than the 6.09% annually-compounded equivalent (the
coupon paid at six months earns nothing for the remaining six). Assuming a
reinvestment rate would embed a second market view inside a number that is
supposed to isolate the passage of time.

## The forward value, exactly

For an instrument whose remaining flow *j* sits at time `tau_j` measured from
`t0` and at `t_j` measured from `t1`, the difference `tau_j - t_j` is the same
constant for every remaining flow of that instrument - both are counted on the
same quasi-coupon grid, from different points inside it. Call it `dt`. Then

    V_forward(t1) = sum_j CF_j * D0(tau_j) / D0(dt)

which is the no-arbitrage forward value with no approximation and no separate
financing assumption. Each instrument carries its own `dt`, because each has its
own coupon dates; forcing a single calendar `dt` across the book would reintroduce
the day-count mismatch that `pricing.py` exists to avoid.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass

from .curves import ParCurve, build_discount_curve
from .errors import EngineError
from .pricing import Position
from .revaluation import compile_book


@dataclass(frozen=True)
class PositionCarryRoll:
    instrument_id: str
    start_value: float
    forward_value: float
    static_value: float
    cash_received: float
    coupons_received: int
    carry: float
    roll_down: float
    total_carry_and_roll: float
    carry_bp_of_value: float
    roll_bp_of_value: float


@dataclass(frozen=True)
class CarryRoll:
    valuation_date: dt.date
    horizon_date: dt.date
    horizon_days: int
    start_value: float
    forward_value: float
    static_value: float
    cash_received: float
    carry: float
    roll_down: float
    total_carry_and_roll: float
    annualised_carry_and_roll_percent: float
    positions: tuple[PositionCarryRoll, ...]
    curve_is_flat: bool
    method: str = "forward_value_carry_static_curve_roll_v1"
    cash_treatment: str = (
        "coupons received during the period are counted at face and not "
        "reinvested; assuming a reinvestment rate would embed a second market "
        "view in a figure meant to isolate the passage of time"
    )


def compute_carry_roll(
    positions: Sequence[Position], valuation_date: dt.date, horizon_date: dt.date,
    par: ParCurve,
) -> CarryRoll:
    if horizon_date <= valuation_date:
        raise EngineError(
            "INVALID_HORIZON",
            f"the horizon date {horizon_date} is not after the valuation date "
            f"{valuation_date}; carry and roll are earned over a forward period.",
            category="USER_INPUT",
            suggested_action="Choose a horizon date after the valuation date.")

    curve = build_discount_curve(par)
    start_book = compile_book(positions, valuation_date)
    end_book = compile_book(positions, horizon_date)

    rows: list[PositionCarryRoll] = []
    for start, end in zip(start_book.positions, end_book.positions):
        scale = start.face_notional / start.face_value
        paid = len(start.times_years) - len(end.times_years)
        cash = sum(start.amounts[:paid]) * scale if paid > 0 else 0.0
        start_value = sum(a * curve.discount_factor(t)
                          for a, t in zip(start.amounts, start.times_years)) * scale

        if not end.times_years:
            # Everything has been paid by the horizon: no forward value, no roll.
            rows.append(PositionCarryRoll(
                instrument_id=start.instrument_id, start_value=start_value,
                forward_value=0.0, static_value=0.0, cash_received=cash,
                coupons_received=paid, carry=cash - start_value, roll_down=0.0,
                total_carry_and_roll=cash - start_value,
                carry_bp_of_value=((cash - start_value) / start_value * 10_000.0
                                   if start_value else 0.0),
                roll_bp_of_value=0.0))
            continue

        remaining_times = start.times_years[paid:]
        remaining_amounts = start.amounts[paid:]
        # tau_j - t_j is constant across the remaining flows of this instrument.
        elapsed = remaining_times[0] - end.times_years[0]
        discount_to_horizon = curve.discount_factor(elapsed) if elapsed > 0 else 1.0

        pv_remaining = sum(a * curve.discount_factor(t)
                           for a, t in zip(remaining_amounts, remaining_times)) * scale
        forward_value = pv_remaining / discount_to_horizon
        static_value = sum(a * curve.discount_factor(t)
                           for a, t in zip(end.amounts, end.times_years)) * scale

        carry = forward_value + cash - start_value
        roll = static_value - forward_value
        rows.append(PositionCarryRoll(
            instrument_id=start.instrument_id, start_value=start_value,
            forward_value=forward_value, static_value=static_value,
            cash_received=cash, coupons_received=paid, carry=carry, roll_down=roll,
            total_carry_and_roll=carry + roll,
            carry_bp_of_value=(carry / start_value * 10_000.0) if start_value else 0.0,
            roll_bp_of_value=(roll / start_value * 10_000.0) if start_value else 0.0))

    start_total = sum(r.start_value for r in rows)
    total = sum(r.total_carry_and_roll for r in rows)
    days = (horizon_date - valuation_date).days
    flat = len(set(par.rates_percent)) == 1
    return CarryRoll(
        valuation_date=valuation_date, horizon_date=horizon_date, horizon_days=days,
        start_value=start_total,
        forward_value=sum(r.forward_value for r in rows),
        static_value=sum(r.static_value for r in rows),
        cash_received=sum(r.cash_received for r in rows),
        carry=sum(r.carry for r in rows), roll_down=sum(r.roll_down for r in rows),
        total_carry_and_roll=total,
        annualised_carry_and_roll_percent=(
            total / start_total * (365.0 / days) * 100.0
            if start_total and days else 0.0),
        positions=tuple(rows), curve_is_flat=flat,
    )
