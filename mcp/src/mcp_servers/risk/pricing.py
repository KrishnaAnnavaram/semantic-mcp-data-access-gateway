"""Cash flows and present value for fixed-rate bonds.  `fixed_coupon_full_pv_v1`

Scope is deliberately narrow: semiannual fixed-rate bonds, no accrued-interest
split. The value returned is the **full present value of remaining cash flows**
- a dirty price, not a clean one. Risk figures are differences of that value, so
the accrued component cancels; reporting it as a clean price without computing
accrued would be a quiet lie.

Time basis: ACT/ACT ICMA, quasi-coupon periods
----------------------------------------------
Cash-flow times are measured in **coupon periods**, not calendar days:

    t_i = (i + 1 - w) / frequency,   w = elapsed fraction of the current period

This is not a stylistic choice. The bootstrap in `curves.py` solves the par-bond
identity on a semiannual grid, placing discount factors at exactly 0.5, 1.0,
1.5 years. If the pricer measured the same cash flows in ACT/365 calendar time,
a coupon 184 days away would be discounted at t = 0.5041 while the curve was
built assuming 0.5 - and a bond paying exactly the par coupon would price to
99.96 instead of 100.

That 3.6bp error is small, silent, systematic, and grows with maturity and curve
slope. Aligning the two conventions removes it by construction, and the
alignment is what the golden par-bond test verifies.

An instrument whose conventions this module does not implement is rejected, not
approximated. Silently pricing a floating-rate note with a fixed-coupon engine
produces a number, and the number is wrong.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Sequence

from .curves import DiscountCurve

# Retained for reference; discounting uses coupon-period time, not calendar days.
DAYS_PER_YEAR = 365.0


class PricingError(ValueError):
    """The instrument cannot be priced under the implemented conventions."""


@dataclass(frozen=True)
class FixedRateBond:
    instrument_id: str
    face_value: float
    coupon_rate_pct: float
    maturity_date: dt.date
    issue_date: dt.date
    coupon_frequency: int = 2
    day_count: str = "ACT_ACT"
    currency: str = "USD"

    def __post_init__(self) -> None:
        if self.coupon_frequency != 2:
            raise PricingError(
                f"{self.instrument_id}: coupon_frequency {self.coupon_frequency} "
                "is not implemented; this engine prices semiannual bonds only")
        if self.day_count != "ACT_ACT":
            raise PricingError(
                f"{self.instrument_id}: day_count {self.day_count!r} is not implemented")
        if self.face_value <= 0:
            raise PricingError(f"{self.instrument_id}: face_value must be positive")
        if self.maturity_date <= self.issue_date:
            raise PricingError(f"{self.instrument_id}: maturity precedes issue")


@dataclass(frozen=True)
class CashFlow:
    date: dt.date
    amount: float
    time_years: float
    kind: str  # "coupon" | "coupon+principal"


@dataclass(frozen=True)
class Position:
    bond: FixedRateBond
    face_notional: float


@dataclass(frozen=True)
class PositionValue:
    instrument_id: str
    present_value: float
    cash_flow_count: int


@dataclass(frozen=True)
class PortfolioValue:
    total_present_value: float
    currency: str
    positions: tuple[PositionValue, ...]


def generate_cash_flows(bond: FixedRateBond, valuation_date: dt.date) -> list[CashFlow]:
    """Remaining cash flows, generated backwards from maturity.

    Backwards because the maturity date anchors the schedule - a bond pays on
    its maturity anniversary, and rolling forward from issue accumulates drift
    that leaves the final coupon on the wrong day.
    """
    if valuation_date >= bond.maturity_date:
        return []

    months = 12 // bond.coupon_frequency
    dates: list[dt.date] = []
    d = bond.maturity_date
    while d > valuation_date:
        dates.append(d)
        d = _subtract_months(d, months)
    dates.reverse()
    # `d` now holds the quasi-coupon date at or before valuation - the start of
    # the current period. It may precede issue for the first period; that is
    # what "quasi" means and it is the correct ICMA reference point.
    period_start = d
    period_end = dates[0]

    span = (period_end - period_start).days
    elapsed = (valuation_date - period_start).days
    w = (elapsed / span) if span > 0 else 0.0

    coupon = bond.face_value * (bond.coupon_rate_pct / 100.0) / bond.coupon_frequency
    flows: list[CashFlow] = []
    for i, date in enumerate(dates):
        last = i == len(dates) - 1
        amount = coupon + (bond.face_value if last else 0.0)
        flows.append(CashFlow(
            date=date,
            amount=amount,
            # Periods, not calendar days - see the module docstring.
            time_years=(i + 1 - w) / bond.coupon_frequency,
            kind="coupon+principal" if last else "coupon",
        ))
    return flows


def _subtract_months(date: dt.date, months: int) -> dt.date:
    """Month arithmetic that clamps to the end of a short month."""
    year = date.year + (date.month - months - 1) // 12
    month = (date.month - months - 1) % 12 + 1
    day = min(date.day, _days_in_month(year, month))
    return dt.date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (dt.date(year + (month // 12), month % 12 + 1, 1) - dt.timedelta(days=1)).day


def price_bond(
    bond: FixedRateBond, valuation_date: dt.date, curve: DiscountCurve,
    face_notional: float | None = None,
) -> PositionValue:
    """Present value of remaining cash flows, scaled to the held notional."""
    flows = generate_cash_flows(bond, valuation_date)
    if not flows:
        return PositionValue(bond.instrument_id, 0.0, 0)
    pv_per_unit_face = sum(
        cf.amount * curve.discount_factor(cf.time_years) for cf in flows
    ) / bond.face_value
    scale = face_notional if face_notional is not None else bond.face_value
    return PositionValue(bond.instrument_id, pv_per_unit_face * scale, len(flows))


def price_portfolio(
    positions: Sequence[Position], valuation_date: dt.date, curve: DiscountCurve,
) -> PortfolioValue:
    values = tuple(
        price_bond(p.bond, valuation_date, curve, p.face_notional) for p in positions
    )
    currencies = {p.bond.currency for p in positions}
    if len(currencies) > 1:
        raise PricingError(
            f"portfolio mixes currencies {sorted(currencies)}; this engine has "
            "no FX conversion and will not sum across them")
    return PortfolioValue(
        total_present_value=sum(v.present_value for v in values),
        currency=next(iter(currencies)) if currencies else "USD",
        positions=values,
    )
