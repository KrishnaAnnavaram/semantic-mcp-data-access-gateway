"""One book, compiled once, repriced many times.  `compiled_full_reval_v1`

Everything in this engine is computed by full revaluation, which is the right
choice and an expensive one. A Monte Carlo run at 5,000 paths reprices the book
5,000 times; the historical worst-case search does it once per observed move.

`price_portfolio` regenerates every cash flow on every call, and cash-flow
generation is calendar arithmetic - month subtraction, end-of-month clamping,
day counts. None of that depends on the curve. So the schedule is built once
here and only the discounting is repeated.

**This is an optimisation and nothing else.** `CompiledBook.price` reproduces
`price_portfolio` to the last bit: the same sum, in the same order, divided by
face value and then scaled by notional in the same sequence. A test asserts the
two agree exactly, because a faster pricer that disagrees with the slow one in
the seventeenth decimal makes every reconciliation in this engine unfalsifiable.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass

from .curves import DiscountCurve, ParCurve, build_discount_curve
from .pricing import Position, PricingError, generate_cash_flows


@dataclass(frozen=True)
class CompiledPosition:
    """A position's remaining schedule, fixed at one valuation date."""

    instrument_id: str
    times_years: tuple[float, ...]
    amounts: tuple[float, ...]
    face_value: float
    face_notional: float

    @property
    def cash_flow_count(self) -> int:
        return len(self.times_years)


@dataclass(frozen=True)
class CompiledBook:
    positions: tuple[CompiledPosition, ...]
    currency: str
    valuation_date: dt.date

    def price_positions(self, curve: DiscountCurve) -> tuple[float, ...]:
        out = []
        for p in self.positions:
            if not p.times_years:
                out.append(0.0)
                continue
            gross = sum(a * curve.discount_factor(t)
                        for a, t in zip(p.amounts, p.times_years))
            out.append(gross / p.face_value * p.face_notional)
        return tuple(out)

    def price(self, curve: DiscountCurve) -> float:
        return sum(self.price_positions(curve))

    def value_under(self, par: ParCurve) -> float:
        """Bootstrap and price. The single call the risk modules repeat."""
        return self.price(build_discount_curve(par))

    def values_under(self, par: ParCurve) -> tuple[float, tuple[float, ...]]:
        """Total and per-position, from one bootstrap.

        Per-position values are what make every contribution figure in this
        engine an exact decomposition rather than an allocation rule: the
        portfolio P&L of a scenario *is* the sum of its positions' P&L, because
        both come from the same revaluation pass.
        """
        per = self.price_positions(build_discount_curve(par))
        return sum(per), per

    def instrument_ids(self) -> tuple[str, ...]:
        return tuple(p.instrument_id for p in self.positions)

    def notionals(self) -> tuple[float, ...]:
        return tuple(p.face_notional for p in self.positions)


def compile_book(positions: Sequence[Position], valuation_date: dt.date) -> CompiledBook:
    compiled: list[CompiledPosition] = []
    currencies = {p.bond.currency for p in positions}
    if len(currencies) > 1:
        raise PricingError(
            f"portfolio mixes currencies {sorted(currencies)}; this engine has "
            "no FX conversion and will not sum across them")
    for p in positions:
        flows = generate_cash_flows(p.bond, valuation_date)
        compiled.append(CompiledPosition(
            instrument_id=p.bond.instrument_id,
            times_years=tuple(cf.time_years for cf in flows),
            amounts=tuple(cf.amount for cf in flows),
            face_value=p.bond.face_value,
            face_notional=(p.face_notional if p.face_notional is not None
                           else p.bond.face_value),
        ))
    return CompiledBook(tuple(compiled), next(iter(currencies)) if currencies else "USD",
                        valuation_date)


def shocked_values(
    book: CompiledBook, par: ParCurve, shocks_bp_by_tenor_years: dict[float, float],
) -> tuple[float, tuple[float, ...]]:
    return book.values_under(par.shocked(shocks_bp_by_tenor_years))


@dataclass(frozen=True)
class ScenarioPnl:
    """One revaluation pass over many shock vectors, kept per position.

    Every decomposition in this engine - component VaR, component ES,
    incremental VaR, stress attribution - is computed from this one object
    rather than from a second pass. That is not only cheaper: it is what makes
    the decompositions *exact*. The portfolio P&L of a scenario is the sum of
    its positions' P&L because both sides came from the same revaluation, so a
    reconciliation check here tests the arithmetic rather than two independent
    estimates of the same thing.
    """

    base_value: float
    base_per_position: tuple[float, ...]
    instrument_ids: tuple[str, ...]
    pnl: tuple[float, ...]
    pnl_per_position: tuple[tuple[float, ...], ...]

    @property
    def scenario_count(self) -> int:
        return len(self.pnl)

    def losses_sorted(self) -> list[float]:
        return sorted(-p for p in self.pnl)

    def pnl_excluding(self, index: int) -> list[float]:
        """The portfolio's P&L in every scenario with one position removed."""
        return [total - row[index] for total, row in zip(self.pnl, self.pnl_per_position)]


def run_scenarios(
    book: CompiledBook, par: ParCurve,
    shock_vectors: Sequence[dict[float, float]],
) -> ScenarioPnl:
    """Revalue the book under each shock vector, keeping per-position detail."""
    base_total, base_per = book.values_under(par)
    pnl: list[float] = []
    rows: list[tuple[float, ...]] = []
    for shocks in shock_vectors:
        total, per = book.values_under(par.shocked(shocks))
        pnl.append(total - base_total)
        rows.append(tuple(s - b for b, s in zip(base_per, per)))
    return ScenarioPnl(
        base_value=base_total, base_per_position=base_per,
        instrument_ids=book.instrument_ids(),
        pnl=tuple(pnl), pnl_per_position=tuple(rows),
    )


def key_rate_exposures(
    book: CompiledBook, par: ParCurve, bump_bp: float = 1.0,
) -> tuple[float, tuple[tuple[float, float], ...], tuple[tuple[float, tuple[float, ...]], ...]]:
    """Key-rate DV01 per node, and per node per position, from one pass per node.

    Returns (base value, [(tenor_years, dv01)], [(tenor_years, per-position dv01)]).
    Sign follows the engine convention: positive means the position loses value
    when that node rises.
    """
    base_total, base_per = book.values_under(par)
    totals: list[tuple[float, float]] = []
    per_position: list[tuple[float, tuple[float, ...]]] = []
    for tenor in par.tenors_years:
        bumped_total, bumped_per = book.values_under(par.shocked({tenor: bump_bp}))
        totals.append((tenor, base_total - bumped_total))
        per_position.append((tenor, tuple(b - s for b, s in zip(base_per, bumped_per))))
    return base_total, tuple(totals), tuple(per_position)
