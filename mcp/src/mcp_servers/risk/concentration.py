"""Where the risk is bunched up.  `share_and_herfindahl_v1`

A book with the same DV01 spread evenly across ten positions and one carrying it
all in a single 30-year bond are not the same book, and no aggregate risk number
distinguishes them. Concentration is the measure that does.

Everything here is computed on **absolute magnitudes**. A long and a short of
equal size net to nothing and are not therefore an absence of risk: they are two
positions whose offset depends on the two legs continuing to move together.
Measuring concentration on the net would report that book as empty.

Three views, because they answer different questions:

* **Share** - what fraction the largest position, or the largest three, account
  for. The number that goes in a summary.
* **Herfindahl (HHI)** - the sum of squared shares. Sensitive to the whole
  distribution rather than to the top of it, so it moves when the tail
  consolidates and the top does not.
* **Effective count (1/HHI)** - how many equally sized positions would be this
  concentrated. The same information as HHI in a unit a reader can picture: "the
  DV01 is spread across the equivalent of 3.7 positions" lands where "HHI 0.27"
  does not.

The dimensions available depend on what has been computed. DV01, key-rate DV01
and maturity-bucket concentration always are; stress-loss and VaR/ES contribution
concentration are included only when the corresponding scenario or history was
supplied, and are omitted rather than defaulted when it was not.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .contributions import Concentration, bucket_for, concentration_of
from .curves import ParCurve
from .errors import EngineError
from .revaluation import CompiledBook, key_rate_exposures


@dataclass(frozen=True)
class ConcentrationEntry:
    label: str
    value: float
    absolute_share_percent: float
    rank: int


@dataclass(frozen=True)
class ConcentrationDimension:
    dimension: str
    unit: str
    total_absolute: float
    net_total: float
    concentration: Concentration
    entries: tuple[ConcentrationEntry, ...]


@dataclass(frozen=True)
class ConcentrationReport:
    base_value: float
    dimensions: tuple[ConcentrationDimension, ...]
    top_n: int
    method: str = "share_and_herfindahl_v1"
    basis: str = (
        "absolute magnitudes: a long and an offsetting short are two "
        "concentrations, not an absence of risk"
    )


def _dimension(name: str, unit: str, labelled: Sequence[tuple[str, float]],
               top_n: int) -> ConcentrationDimension:
    total_abs = sum(abs(v) for _, v in labelled)
    ordered = sorted(labelled, key=lambda x: abs(x[1]), reverse=True)
    entries = tuple(
        ConcentrationEntry(
            label=label, value=value,
            absolute_share_percent=(abs(value) / total_abs * 100.0) if total_abs else 0.0,
            rank=i)
        for i, (label, value) in enumerate(ordered[:top_n], start=1))
    return ConcentrationDimension(
        dimension=name, unit=unit, total_absolute=total_abs,
        net_total=sum(v for _, v in labelled),
        concentration=concentration_of([v for _, v in labelled]), entries=entries)


def compute_concentration(
    book: CompiledBook, par: ParCurve, top_n: int = 5,
    stress_position_pnl: Sequence[tuple[str, float]] | None = None,
    var_contributions: Sequence[tuple[str, float]] | None = None,
    es_contributions: Sequence[tuple[str, float]] | None = None,
) -> ConcentrationReport:
    if top_n < 1:
        raise EngineError(
            "INVALID_LIMIT", f"top_n must be at least 1; got {top_n}",
            category="USER_INPUT")

    base_total, base_per = book.values_under(par)
    _, up_per = book.values_under(par.shifted(1.0))
    ids = book.instrument_ids()

    dimensions = [
        _dimension("present_value", "USD",
                   list(zip(ids, base_per)), top_n),
        _dimension("position_dv01", "USD per basis point",
                   [(i, b - u) for i, b, u in zip(ids, base_per, up_per)], top_n),
        _dimension("position_notional", "USD face",
                   list(zip(ids, book.notionals())), top_n),
    ]

    _, krd_totals, _ = key_rate_exposures(book, par, 1.0)
    dimensions.append(_dimension(
        "key_rate_dv01", "USD per basis point",
        [(f"{t:g}y", v) for t, v in krd_totals], top_n))

    by_bucket: dict[str, float] = {}
    for tenor, value in krd_totals:
        by_bucket[bucket_for(tenor)] = by_bucket.get(bucket_for(tenor), 0.0) + value
    dimensions.append(_dimension(
        "maturity_bucket_dv01", "USD per basis point",
        sorted(by_bucket.items()), top_n))

    if stress_position_pnl is not None:
        dimensions.append(_dimension(
            "stress_loss", "USD", list(stress_position_pnl), top_n))
    if var_contributions is not None:
        dimensions.append(_dimension(
            "component_var", "USD", list(var_contributions), top_n))
    if es_contributions is not None:
        dimensions.append(_dimension(
            "component_expected_shortfall", "USD", list(es_contributions), top_n))

    return ConcentrationReport(
        base_value=base_total, dimensions=tuple(dimensions), top_n=top_n)


def most_concentrated_bucket(book: CompiledBook, par: ParCurve) -> tuple[str, float]:
    """The maturity bucket carrying the largest absolute key-rate DV01."""
    _, krd_totals, _ = key_rate_exposures(book, par, 1.0)
    by_bucket: dict[str, float] = {}
    for tenor, value in krd_totals:
        by_bucket[bucket_for(tenor)] = by_bucket.get(bucket_for(tenor), 0.0) + value
    if not by_bucket:
        raise EngineError(
            "MISSING_CURVE_TENOR", "the curve has no nodes to bucket",
            category="USER_INPUT")
    label = max(by_bucket, key=lambda k: abs(by_bucket[k]))
    return label, by_bucket[label]


def most_sensitive_tenors(book: CompiledBook, par: ParCurve,
                          count: int = 3) -> list[tuple[float, float]]:
    """The `count` curve nodes carrying the largest absolute key-rate DV01.

    The input to a concentration stress: shock what the book is actually exposed
    to, chosen by measurement rather than by a model's guess about where the
    risk probably sits.
    """
    _, krd_totals, _ = key_rate_exposures(book, par, 1.0)
    ordered = sorted(krd_totals, key=lambda x: abs(x[1]), reverse=True)
    return [(t, v) for t, v in ordered[:max(1, count)]]
