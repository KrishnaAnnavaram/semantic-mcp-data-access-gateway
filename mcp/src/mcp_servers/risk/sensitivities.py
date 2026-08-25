"""Rate sensitivity, assembled into one answer.  `full_revaluation_bump_v1`

`compute_dv01` and `compute_key_rate_dv01` in `risk.py` each answer one
question and stay exactly as they were. This module answers the question a risk
report actually asks - "where is the rate risk in this book" - by running both,
adding duration, convexity and bucketing, and then **checking that the pieces
agree**.

The checks are the reason the module exists rather than three tools in a row:

* `sum of position DV01 == portfolio DV01` is exact. Both come from the same
  revaluation pass, so a mismatch is a defect, not a tolerance.
* `sum of key-rate DV01 ~= parallel DV01` is *not* exact and must not be
  asserted as though it were. Bumping every node at once is a different
  perturbation from bumping each in turn and adding: the bootstrap is
  non-linear in the par rates. The difference is reported in basis points of
  the parallel figure so a reader can see whether it is the usual fraction of a
  percent or something has gone wrong.

Duration is reported two ways for the same reason `bond_analytics` does:
effective duration from a parallel par-curve bump, and dollar duration from the
DV01 itself. They are consistent by construction here - `dollar_duration =
DV01 x 10,000` - and stating both stops a reader converting between them with
the wrong factor.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .contributions import Concentration, bucket_for, concentration_of
from .curves import ParCurve, build_discount_curve
from .errors import EngineError
from .revaluation import CompiledBook, key_rate_exposures

DEFAULT_EFFECTIVE_BUMP_BP = 25.0


@dataclass(frozen=True)
class PositionSensitivity:
    instrument_id: str
    present_value: float
    face_notional: float
    dv01: float
    dv01_share_percent: float
    dv01_per_million_notional: float
    effective_duration_years: float


@dataclass(frozen=True)
class KeyRateSensitivity:
    tenor_years: float
    key_rate_dv01: float
    share_percent: float
    per_position: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class BucketSensitivity:
    bucket: str
    key_rate_dv01: float
    share_percent: float


@dataclass(frozen=True)
class Reconciliation:
    portfolio_dv01: float
    sum_of_position_dv01: float
    position_difference: float
    sum_of_key_rate_dv01: float
    key_rate_difference: float
    key_rate_difference_bp_of_parallel: float
    note: str


@dataclass(frozen=True)
class RateSensitivities:
    base_value: float
    bump_bp: float
    dv01: float
    dollar_duration: float
    effective_duration_years: float
    effective_convexity: float
    effective_bump_bp: float
    positions: tuple[PositionSensitivity, ...]
    key_rates: tuple[KeyRateSensitivity, ...]
    buckets: tuple[BucketSensitivity, ...]
    dv01_concentration: Concentration
    key_rate_concentration: Concentration
    reconciliation: Reconciliation


def portfolio_effective_measures(
    book: CompiledBook, par: ParCurve, bump_bp: float = DEFAULT_EFFECTIVE_BUMP_BP,
) -> tuple[float, float, float]:
    """(effective duration, effective convexity, base value) for a whole book."""
    dy = bump_bp / 10_000.0
    base = book.value_under(par)
    up = book.value_under(par.shifted(bump_bp))
    down = book.value_under(par.shifted(-bump_bp))
    if base == 0:
        return 0.0, 0.0, 0.0
    return ((down - up) / (2.0 * base * dy),
            (up + down - 2.0 * base) / (base * dy * dy),
            base)


def compute_rate_sensitivities(
    book: CompiledBook, par: ParCurve, bump_bp: float = 1.0,
    effective_bump_bp: float = DEFAULT_EFFECTIVE_BUMP_BP,
    key_tenors_years: Sequence[float] | None = None,
) -> RateSensitivities:
    if bump_bp == 0:
        raise EngineError(
            "INVALID_STRESS_VECTOR",
            "bump_bp must be non-zero; a zero bump measures nothing",
            category="USER_INPUT",
            suggested_action="Use 1.0 for a conventional DV01.")
    if key_tenors_years is not None:
        nodes = set(par.tenors_years)
        unknown = [t for t in key_tenors_years if t not in nodes]
        if unknown:
            raise EngineError(
                "MISSING_CURVE_TENOR",
                f"key tenors {unknown} are not nodes on this curve",
                category="USER_INPUT",
                suggested_action=f"Choose from {list(par.tenors_years)}.",
                details={"curve_nodes_years": list(par.tenors_years)})

    base_total, base_per = book.values_under(par)
    up_total, up_per = book.values_under(par.shifted(bump_bp))
    dv01 = base_total - up_total
    per_dv01 = [b - u for b, u in zip(base_per, up_per)]

    # Effective duration is a central difference at `effective_bump_bp`, not at
    # the DV01 bump. Using the 1bp bump for both would make the two figures
    # agree by construction and hide exactly the convexity the larger bump
    # exists to expose, so the pair is computed separately and both bump sizes
    # are reported.
    eff_up_total, eff_up_per = book.values_under(par.shifted(effective_bump_bp))
    eff_down_total, eff_down_per = book.values_under(par.shifted(-effective_bump_bp))
    eff_dy = effective_bump_bp / 10_000.0
    eff_duration = ((eff_down_total - eff_up_total) / (2.0 * base_total * eff_dy)
                    if base_total else 0.0)
    eff_convexity = ((eff_up_total + eff_down_total - 2.0 * base_total)
                     / (base_total * eff_dy * eff_dy) if base_total else 0.0)

    total_abs_dv01 = sum(abs(v) for v in per_dv01)
    positions = tuple(
        PositionSensitivity(
            instrument_id=iid,
            present_value=pv,
            face_notional=notional,
            dv01=d,
            dv01_share_percent=(abs(d) / total_abs_dv01 * 100.0)
            if total_abs_dv01 else 0.0,
            dv01_per_million_notional=(d / notional * 1_000_000.0) if notional else 0.0,
            effective_duration_years=(
                (dn - u) / (2.0 * pv * eff_dy) if pv else 0.0),
        )
        for iid, pv, notional, d, u, dn in zip(
            book.instrument_ids(), base_per, book.notionals(), per_dv01,
            eff_up_per, eff_down_per))

    _, krd_totals, krd_per_position = key_rate_exposures(book, par, bump_bp)
    wanted = set(key_tenors_years) if key_tenors_years is not None else None
    selected = [(t, v) for t, v in krd_totals if wanted is None or t in wanted]
    total_abs_krd = sum(abs(v) for _, v in selected)
    per_position_lookup = dict(krd_per_position)
    key_rates = tuple(
        KeyRateSensitivity(
            tenor_years=t, key_rate_dv01=v,
            share_percent=(abs(v) / total_abs_krd * 100.0) if total_abs_krd else 0.0,
            per_position=tuple(zip(book.instrument_ids(), per_position_lookup[t])),
        )
        for t, v in selected)

    by_bucket: dict[str, float] = {}
    for t, v in selected:
        by_bucket[bucket_for(t)] = by_bucket.get(bucket_for(t), 0.0) + v
    bucket_abs = sum(abs(v) for v in by_bucket.values())
    buckets = tuple(
        BucketSensitivity(
            bucket=label, key_rate_dv01=by_bucket.get(label, 0.0),
            share_percent=(abs(by_bucket.get(label, 0.0)) / bucket_abs * 100.0)
            if bucket_abs else 0.0)
        for label in dict.fromkeys(bucket_for(t) for t, _ in selected))

    krd_sum = sum(v for _, v in selected)
    position_sum = sum(per_dv01)
    return RateSensitivities(
        base_value=base_total,
        bump_bp=bump_bp,
        dv01=dv01,
        dollar_duration=dv01 * 10_000.0,
        effective_duration_years=eff_duration,
        effective_convexity=eff_convexity,
        effective_bump_bp=effective_bump_bp,
        positions=positions,
        key_rates=key_rates,
        buckets=buckets,
        dv01_concentration=concentration_of(per_dv01),
        key_rate_concentration=concentration_of([v for _, v in selected]),
        reconciliation=Reconciliation(
            portfolio_dv01=dv01,
            sum_of_position_dv01=position_sum,
            position_difference=position_sum - dv01,
            sum_of_key_rate_dv01=krd_sum,
            key_rate_difference=krd_sum - dv01,
            key_rate_difference_bp_of_parallel=(
                (krd_sum - dv01) / dv01 * 10_000.0 if dv01 else 0.0),
            note=(
                "Position DV01s sum to the portfolio DV01 exactly - both come "
                "from one revaluation pass. Key-rate DV01s do not: bumping "
                "every node together is a different perturbation from bumping "
                "each in turn, because the bootstrap is non-linear in the par "
                "rates. The difference is reported rather than distributed."),
        ),
    )


def scale_check(book: CompiledBook, par: ParCurve, multiplier: float) -> dict[str, float]:
    """DV01 of the book against DV01 of the same book scaled by a constant.

    A pure linearity check with a use: a book whose DV01 does not double when
    every notional doubles has an ordering or aggregation bug, and the failure
    is otherwise invisible because both numbers look reasonable alone.
    """
    from .revaluation import CompiledBook as _Book
    from .revaluation import CompiledPosition

    base = compute_rate_sensitivities(book, par).dv01
    scaled = _Book(
        tuple(CompiledPosition(p.instrument_id, p.times_years, p.amounts,
                               p.face_value, p.face_notional * multiplier)
              for p in book.positions),
        book.currency, book.valuation_date)
    return {"dv01": base, "scaled_dv01": compute_rate_sensitivities(scaled, par).dv01,
            "multiplier": multiplier}


def price_under(book: CompiledBook, par: ParCurve) -> float:
    """Convenience for callers that hold a par curve and want one number."""
    return book.price(build_discount_curve(par))
