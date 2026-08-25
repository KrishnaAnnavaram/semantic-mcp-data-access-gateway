"""A whole scenario pack in one pass.  `standard_pack_2026_08_v1`

Running scenarios one at a time answers "what happens under this shock". A
matrix answers the question that actually gets asked in a risk meeting: *which*
shock hurts most, and by how much more than the next one.

That is a different deliverable, and it needs three things a sequence of
individual calls does not give you:

1. **One base valuation.** Twenty-one scenarios against twenty-one separately
   computed base values is twenty-one chances for the bases to differ, and a
   ranking built on inconsistent bases is meaningless.
2. **One key-rate pass.** First-order tenor attribution needs the key-rate
   DV01 vector, which depends on the curve and not on the scenario. Computing
   it once and reusing it across the pack turns O(scenarios x nodes)
   revaluations into O(scenarios + nodes).
3. **A stable ranking rule.** Ties are broken by scenario name, so the same
   pack run twice produces the same order. A ranking that permutes between runs
   makes "the third-worst scenario" a phrase with no referent.

The pack itself is versioned. Adding a scenario to it changes what "the
standard stress matrix" means, so the pack name and the manifest entry move
together.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .contributions import (
    AttributionMethod,
    BucketContribution,
    Concentration,
    bucket_for,
    concentration_of,
    run_shock,
)
from .curves import CurveError, ParCurve
from .revaluation import CompiledBook, key_rate_exposures
from .stress_scenarios import (
    Interpolation,
    ShockVector,
    key_rate_shock,
    parallel_shock,
    template_shock,
    twist_shock,
)

STANDARD_PACK_VERSION = "standard_pack_2026_08_v1"

# (kind, argument). Order here is the order the pack is generated in; the
# ranking is applied afterwards and does not depend on it.
STANDARD_PACK_SPEC: tuple[tuple[str, object], ...] = (
    ("parallel", 50.0), ("parallel", 100.0), ("parallel", 200.0),
    ("parallel", -50.0), ("parallel", -100.0), ("parallel", -200.0),
    ("template", ("BEAR_STEEPENER", 100.0)),
    ("template", ("BEAR_STEEPENER", 200.0)),
    ("template", ("BEAR_FLATTENER", 100.0)),
    ("template", ("BEAR_FLATTENER", 200.0)),
    ("template", ("BULL_STEEPENER", 100.0)),
    ("template", ("BULL_FLATTENER", 100.0)),
    ("twist", 100.0), ("twist", -100.0),
    ("template", ("BELLY_SELLOFF", 100.0)),
    ("template", ("WINGS_SELLOFF", 100.0)),
    ("key_rate", 2.0), ("key_rate", 5.0), ("key_rate", 10.0),
    ("key_rate", 20.0), ("key_rate", 30.0),
)

KEY_RATE_PACK_SHOCK_BP = 100.0
DEFAULT_TWIST_PIVOT_YEARS = 10.0


@dataclass(frozen=True)
class MatrixEntry:
    rank: int
    scenario_name: str
    scenario_type: str
    template: str | None
    severity_bp: float | None
    shock: ShockVector
    stressed_value: float
    pnl: float
    pnl_percent: float
    largest_position_contributor: str | None
    largest_position_pnl: float
    largest_tenor_contributor_years: float | None
    largest_tenor_pnl: float
    largest_bucket_contributor: str | None
    tenor_explained_pnl: float
    tenor_residual_pnl: float
    failed_reason: str | None = None


@dataclass(frozen=True)
class StressMatrix:
    pack_version: str
    base_value: float
    scenario_count: int
    entries: tuple[MatrixEntry, ...]
    key_rate_dv01: tuple[tuple[float, float], ...]
    skipped: tuple[str, ...]
    attribution_method: AttributionMethod


@dataclass(frozen=True)
class ScenarioComparison:
    worst_scenario: str
    worst_pnl: float
    best_scenario: str
    best_pnl: float
    loss_range: float
    severity_spread_bp: float
    dominant_position: str | None
    dominant_bucket: str | None
    dominant_scenario_type: str | None
    ranked: tuple[tuple[int, str, float, float], ...]
    pnl_concentration: Concentration


def build_standard_pack(
    par: ParCurve, interpolation: Interpolation = "linear_years",
) -> tuple[list[ShockVector], list[str]]:
    """The versioned pack, adapted to the tenors this curve actually has.

    A key-rate scenario at a tenor the curve does not publish is **skipped and
    named**, not silently approximated onto a neighbour. The 30-year has a real
    four-year hole in Treasury's history, so a pack that quietly re-pointed a
    30-year shock at the 20-year would report a smaller loss with no indication
    that the scenario it named had not been run.
    """
    nodes = set(par.tenors_years)
    vectors: list[ShockVector] = []
    skipped: list[str] = []
    for kind, arg in STANDARD_PACK_SPEC:
        if kind == "parallel":
            vectors.append(parallel_shock(par, float(arg)))
        elif kind == "template":
            name, severity = arg  # type: ignore[misc]
            vectors.append(template_shock(par, name, float(severity), interpolation))
        elif kind == "twist":
            pivot = DEFAULT_TWIST_PIVOT_YEARS
            if pivot < par.tenors_years[0] or pivot > par.tenors_years[-1]:
                skipped.append(f"Twist about {pivot:g}y: pivot outside the curve")
                continue
            vectors.append(twist_shock(par, pivot, float(arg), interpolation))
        elif kind == "key_rate":
            tenor = float(arg)  # type: ignore[arg-type]
            if tenor not in nodes:
                skipped.append(
                    f"Key rate {tenor:g}y {KEY_RATE_PACK_SHOCK_BP:+.0f}bp: "
                    f"{tenor:g}y is not a node on this curve")
                continue
            vectors.append(key_rate_shock(par, [tenor], KEY_RATE_PACK_SHOCK_BP))
    return vectors, skipped


def run_stress_matrix(
    book: CompiledBook, par: ParCurve, vectors: Sequence[ShockVector],
    attribution_method: AttributionMethod = "first_order",
    skipped: Sequence[str] = (),
    pack_version: str = STANDARD_PACK_VERSION,
) -> StressMatrix:
    base_value = book.value_under(par)
    _, krd_totals, _ = key_rate_exposures(book, par, 1.0)
    krd = dict(krd_totals)

    rows: list[MatrixEntry] = []
    for vector in vectors:
        try:
            run = run_shock(book, par, vector)
        except CurveError as exc:
            # A scenario the bootstrap refuses is a scenario that did not run.
            # It stays in the table with a stated reason and no P&L, because
            # dropping it would silently shrink the pack.
            #
            # This is not hypothetical. A +100bp single-node bump at the 20-year
            # leaves the 20s30s segment inverted by most of a percent on a
            # normally shaped Treasury curve, and the bootstrap meets a negative
            # forward. The scenario is genuinely not arbitrage-consistent; the
            # right answer is to say so, not to price it anyway.
            rows.append(MatrixEntry(
                rank=0, scenario_name=vector.scenario_name,
                scenario_type=vector.scenario_type, template=vector.template,
                severity_bp=vector.severity_bp, shock=vector,
                stressed_value=float("nan"), pnl=float("nan"),
                pnl_percent=float("nan"),
                largest_position_contributor=None, largest_position_pnl=0.0,
                largest_tenor_contributor_years=None, largest_tenor_pnl=0.0,
                largest_bucket_contributor=None,
                tenor_explained_pnl=0.0, tenor_residual_pnl=0.0,
                failed_reason=(
                    f"{exc}. A single-node bump of this size leaves the curve "
                    "arbitrage-inconsistent. Re-run this scenario at a smaller "
                    "shock, or shock the neighbouring nodes with it.")))
            continue

        tenor_pnl = [(t, -krd[t] * vector.shocks_bp_by_tenor_years.get(t, 0.0))
                     for t in par.tenors_years]
        explained = sum(v for _, v in tenor_pnl)
        worst_tenor = min(tenor_pnl, key=lambda x: x[1], default=(None, 0.0))
        by_bucket: dict[str, float] = {}
        for t, v in tenor_pnl:
            by_bucket[bucket_for(t)] = by_bucket.get(bucket_for(t), 0.0) + v
        worst_bucket = min(by_bucket.items(), key=lambda x: x[1], default=(None, 0.0))
        worst_position = run.worst_position()

        rows.append(MatrixEntry(
            rank=0, scenario_name=vector.scenario_name,
            scenario_type=vector.scenario_type, template=vector.template,
            severity_bp=vector.severity_bp, shock=vector,
            stressed_value=run.stressed_value, pnl=run.pnl,
            pnl_percent=run.pnl_percent,
            largest_position_contributor=(worst_position.instrument_id
                                          if worst_position else None),
            largest_position_pnl=worst_position.pnl if worst_position else 0.0,
            largest_tenor_contributor_years=worst_tenor[0],
            largest_tenor_pnl=worst_tenor[1],
            largest_bucket_contributor=worst_bucket[0],
            tenor_explained_pnl=explained,
            tenor_residual_pnl=run.pnl - explained,
        ))

    ran = [r for r in rows if r.failed_reason is None]
    failed = [r for r in rows if r.failed_reason is not None]
    ran.sort(key=lambda r: (r.pnl, r.scenario_name))
    ordered = tuple(
        [MatrixEntry(**{**r.__dict__, "rank": i}) for i, r in enumerate(ran, start=1)]
        + failed)

    return StressMatrix(
        pack_version=pack_version, base_value=base_value,
        scenario_count=len(ordered), entries=ordered,
        key_rate_dv01=tuple((t, krd[t]) for t in par.tenors_years),
        skipped=tuple(skipped), attribution_method=attribution_method,
    )


def compare_scenarios(matrix: StressMatrix) -> ScenarioComparison:
    """Rank a set of scenario results and name what drives the extremes."""
    ran = [e for e in matrix.entries if e.failed_reason is None]
    if not ran:
        return ScenarioComparison(
            worst_scenario="", worst_pnl=0.0, best_scenario="", best_pnl=0.0,
            loss_range=0.0, severity_spread_bp=0.0, dominant_position=None,
            dominant_bucket=None, dominant_scenario_type=None, ranked=(),
            pnl_concentration=concentration_of([]))
    worst = ran[0]
    best = max(ran, key=lambda e: (e.pnl, e.scenario_name))
    severities = [e.severity_bp for e in ran if e.severity_bp is not None]
    return ScenarioComparison(
        worst_scenario=worst.scenario_name, worst_pnl=worst.pnl,
        best_scenario=best.scenario_name, best_pnl=best.pnl,
        loss_range=best.pnl - worst.pnl,
        severity_spread_bp=(max(severities) - min(severities)) if severities else 0.0,
        dominant_position=worst.largest_position_contributor,
        dominant_bucket=worst.largest_bucket_contributor,
        dominant_scenario_type=worst.scenario_type,
        ranked=tuple((e.rank, e.scenario_name, e.pnl, e.pnl_percent) for e in ran),
        pnl_concentration=concentration_of([e.pnl for e in ran]),
    )


def bucket_table(matrix: StressMatrix, par: ParCurve) -> tuple[BucketContribution, ...]:
    """Worst-case first-order bucket contribution across the whole pack.

    Answers "which part of the curve is this book most exposed to, taking the
    worst scenario for each bucket rather than the worst scenario overall" -
    which is a different and usually larger picture than any single scenario.
    """
    worst: dict[str, float] = {}
    for entry in matrix.entries:
        if entry.failed_reason is not None:
            continue
        by_bucket: dict[str, float] = {}
        for tenor, dv01 in matrix.key_rate_dv01:
            bp = entry.shock.shocks_bp_by_tenor_years.get(tenor, 0.0)
            label = bucket_for(tenor)
            by_bucket[label] = by_bucket.get(label, 0.0) + (-dv01 * bp)
        for label, value in by_bucket.items():
            worst[label] = min(worst.get(label, 0.0), value)
    total = sum(abs(v) for v in worst.values())
    return tuple(
        BucketContribution(bucket=label, pnl=value,
                           contribution_percent=(abs(value) / total * 100.0)
                           if total else 0.0)
        for label, value in sorted(worst.items(), key=lambda x: x[1]))
