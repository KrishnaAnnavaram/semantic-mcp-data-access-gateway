"""The question asked backwards.  `bracketed_bisection_secant_v1`

Forward stress asks "what do I lose at +100bp". Reverse stress asks "what move
loses me ten million", and it is the more useful question in a limit
conversation, because the answer is a market move a person can judge as likely
or not. "We breach at +57bp" is actionable in a way that "our +100bp loss is
1.9m" is not.

Mechanically it is a root find: take a scenario *shape*, scale it by a single
multiplier, and solve for the multiplier at which the full revaluation returns
the target P&L. The shape is whatever the caller chose - parallel, a steepener,
a twist, a custom vector - so the reverse stress inherits the shape's economics
rather than assuming a parallel move.

Three things make this trustworthy rather than merely convergent:

**The bracket is honest.** The search interval is an input, and a target that
cannot be reached inside it returns `NO_REVERSE_STRESS_SOLUTION` naming the
loss range that *is* reachable there. Silently widening the bounds would answer
a question nobody asked - a +900bp parallel shift is not a scenario, it is a
solver artefact.

**A bootstrap failure shrinks the bracket, and says so.** Large multiples of a
steep scenario can leave the curve arbitrage-inconsistent. Rather than crashing
mid-solve, the usable end of the interval is found by halving and reported, so
the caller can tell "no solution below the limit we set" apart from "no
solution before the curve stopped making sense".

**Monotonicity is checked, not assumed.** A long fixed-rate book loses
monotonically as rates rise, but a hedged or barbelled book need not, and a
root find on a non-monotone function returns one root of several with no
indication that others exist. The function is sampled across the bracket and the
result says whether it was monotone there.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .contributions import StressRun, run_shock
from .curves import CurveError, ParCurve
from .errors import EngineError
from .numerics import BracketError, SolveResult, is_monotone, solve_scalar
from .revaluation import CompiledBook
from .stress_scenarios import ShockVector

DEFAULT_PARALLEL_BOUNDS_BP = (-500.0, 500.0)
DEFAULT_MULTIPLIER_BOUNDS = (-5.0, 5.0)
MONOTONICITY_SAMPLES = 9


@dataclass(frozen=True)
class ReverseStressResult:
    target_loss: float
    shape_name: str
    scenario_type: str
    solved_multiplier: float
    solved_shock_bp_at_reference: float
    shock_vector: dict[float, float]
    resulting_pnl: float
    resulting_pnl_percent: float
    base_value: float
    converged: bool
    iterations: int
    search_low: float
    search_high: float
    effective_search_low: float
    effective_search_high: float
    bracket_reduced_reason: str | None
    monotone_over_bracket: bool
    tolerance: float
    run: StressRun


@dataclass(frozen=True)
class ThresholdRow:
    target_loss: float
    solved_multiplier: float
    solved_shock_bp_at_reference: float
    resulting_pnl: float
    converged: bool
    reason: str | None


@dataclass(frozen=True)
class ThresholdTable:
    shape_name: str
    base_value: float
    reference_tenor_years: float
    rows: tuple[ThresholdRow, ...]
    search_low: float
    search_high: float


def reference_shock_bp(shape: ShockVector) -> tuple[float, float]:
    """The tenor whose shock represents the shape's magnitude, and that shock.

    A multiplier alone means nothing to a reader ("x2.4 of a bear steepener").
    Quoting it at the tenor that carries the largest shock in the shape turns it
    back into basis points, which is the unit the answer gets discussed in.
    """
    if not shape.shocks_bp_by_tenor_years:
        return 0.0, 0.0
    tenor = max(shape.shocks_bp_by_tenor_years,
                key=lambda t: abs(shape.shocks_bp_by_tenor_years[t]))
    return tenor, shape.shocks_bp_by_tenor_years[tenor]


def _pnl_at(book: CompiledBook, par: ParCurve, shape: ShockVector) -> Callable[[float], float]:
    def f(multiplier: float) -> float:
        shocked = par.shocked({t: v * multiplier
                               for t, v in shape.shocks_bp_by_tenor_years.items()})
        return book.value_under(shocked) - book.value_under(par)
    return f


def _usable_bound(f: Callable[[float], float], bound: float,
                  halvings: int = 24) -> tuple[float, str | None]:
    """Shrink a bound towards zero until the revaluation succeeds."""
    current = bound
    for _ in range(halvings):
        try:
            f(current)
            if current == bound:
                return current, None
            return current, (
                f"the search bound {bound:+.6g} could not be evaluated - the "
                "scaled scenario leaves the curve arbitrage-inconsistent under "
                f"this bootstrap - so the usable end of the interval is "
                f"{current:+.6g}")
        except CurveError:
            current /= 2.0
    raise EngineError(
        "NO_REVERSE_STRESS_SOLUTION",
        f"no multiple of this scenario near {bound:+.6g} produces a curve the "
        "bootstrap accepts, so the search interval is empty on that side.",
        category="NUMERICAL",
        suggested_action="Use a gentler scenario shape or a narrower interval.")


def run_reverse_stress(
    book: CompiledBook, par: ParCurve, shape: ShockVector, target_loss: float,
    search_low: float | None = None, search_high: float | None = None,
    tolerance: float = 1e-6, max_iterations: int = 200,
) -> ReverseStressResult:
    """Solve for the multiple of `shape` whose full revaluation loses `target_loss`.

    `target_loss` is a positive number of currency units. The solver targets a
    P&L of `-target_loss`, following the engine's sign convention throughout.
    """
    if target_loss < 0:
        raise EngineError(
            "NO_REVERSE_STRESS_SOLUTION",
            f"target_loss must be a non-negative amount; got {target_loss:,.2f}. "
            "The sign convention is fixed: a loss is reported as a positive "
            "number and the P&L it corresponds to is negative.",
            category="USER_INPUT",
            suggested_action="Pass the loss as a positive amount.")

    is_parallel = shape.scenario_type == "PARALLEL"
    default_low, default_high = (
        DEFAULT_PARALLEL_BOUNDS_BP if is_parallel else DEFAULT_MULTIPLIER_BOUNDS)
    _, reference_bp = reference_shock_bp(shape)
    # For a parallel shape the multiplier *is* basis points, provided the shape
    # is normalised to 1bp. Scale the caller's bounds accordingly so the numbers
    # they pass mean what they look like.
    scale = abs(reference_bp) if reference_bp else 1.0
    low = (search_low if search_low is not None else default_low)
    high = (search_high if search_high is not None else default_high)
    if is_parallel:
        low, high = low / scale, high / scale
    if high <= low:
        raise EngineError(
            "NO_REVERSE_STRESS_SOLUTION",
            f"the search interval is empty: [{search_low}, {search_high}]",
            category="USER_INPUT",
            suggested_action="Give a low bound below the high bound.")

    f = _pnl_at(book, par, shape)
    base_value = book.value_under(par)
    usable_low, low_reason = _usable_bound(f, low)
    usable_high, high_reason = _usable_bound(f, high)
    reason = low_reason or high_reason

    samples = [usable_low + (usable_high - usable_low) * i / (MONOTONICITY_SAMPLES - 1)
               for i in range(MONOTONICITY_SAMPLES)]
    sampled = [f(x) for x in samples]
    monotone = is_monotone(sampled)

    target_pnl = -target_loss
    try:
        solved: SolveResult = solve_scalar(
            f, usable_low, usable_high, target=target_pnl,
            tolerance=tolerance, max_iterations=max_iterations)
    except BracketError as exc:
        raise EngineError(
            "NO_REVERSE_STRESS_SOLUTION",
            f"a loss of {target_loss:,.2f} is not reachable by any multiple of "
            f"'{shape.scenario_name}' inside the search interval. Over "
            f"[{usable_low:+.6g}, {usable_high:+.6g}] the P&L ranges from "
            f"{min(sampled):,.2f} to {max(sampled):,.2f}. {exc}",
            category="NUMERICAL",
            suggested_action=(
                "Widen the search interval deliberately, choose a scenario "
                "shape this book is actually exposed to, or accept that the "
                "target loss is unreachable."),
            details={"reachable_pnl_low": min(sampled),
                     "reachable_pnl_high": max(sampled),
                     "search_low": usable_low, "search_high": usable_high},
        ) from exc

    multiplier = solved.root
    scaled = shape.scaled(multiplier)
    run = run_shock(book, par, scaled)
    return ReverseStressResult(
        target_loss=target_loss, shape_name=shape.scenario_name,
        scenario_type=shape.scenario_type, solved_multiplier=multiplier,
        solved_shock_bp_at_reference=reference_bp * multiplier,
        shock_vector=scaled.shocks_bp_by_tenor_years,
        resulting_pnl=run.pnl,
        resulting_pnl_percent=run.pnl_percent,
        base_value=base_value, converged=solved.converged,
        iterations=solved.iterations,
        search_low=(search_low if search_low is not None else default_low),
        search_high=(search_high if search_high is not None else default_high),
        effective_search_low=usable_low * (scale if is_parallel else 1.0),
        effective_search_high=usable_high * (scale if is_parallel else 1.0),
        bracket_reduced_reason=reason, monotone_over_bracket=monotone,
        tolerance=tolerance, run=run,
    )


def compute_thresholds(
    book: CompiledBook, par: ParCurve, shape: ShockVector,
    target_losses: Sequence[float], search_low: float | None = None,
    search_high: float | None = None, tolerance: float = 1e-6,
) -> ThresholdTable:
    """The stress magnitude that reaches each of several loss levels.

    A target that is unreachable inside the interval is recorded with its reason
    rather than aborting the table - the rows that *did* solve are still the
    answer to most of the question, and dropping them because the last one
    failed helps nobody.
    """
    reference_tenor, _ = reference_shock_bp(shape)
    rows: list[ThresholdRow] = []
    for target in target_losses:
        try:
            result = run_reverse_stress(book, par, shape, target, search_low,
                                        search_high, tolerance)
            rows.append(ThresholdRow(
                target_loss=target, solved_multiplier=result.solved_multiplier,
                solved_shock_bp_at_reference=result.solved_shock_bp_at_reference,
                resulting_pnl=result.resulting_pnl, converged=result.converged,
                reason=None))
        except EngineError as exc:
            rows.append(ThresholdRow(
                target_loss=target, solved_multiplier=float("nan"),
                solved_shock_bp_at_reference=float("nan"),
                resulting_pnl=float("nan"), converged=False,
                reason=exc.plain_message))
    low, high = (search_low if search_low is not None else float("nan"),
                 search_high if search_high is not None else float("nan"))
    return ThresholdTable(
        shape_name=shape.scenario_name, base_value=book.value_under(par),
        reference_tenor_years=reference_tenor, rows=tuple(rows),
        search_low=low, search_high=high,
    )


@dataclass(frozen=True)
class LimitBreachResult:
    limit_name: str
    limit_amount: float
    amber_utilisation_percent: float
    amber_amount: float
    breach: ReverseStressResult | None
    amber: ReverseStressResult | None
    breach_reason: str | None
    amber_reason: str | None


def find_limit_breach(
    book: CompiledBook, par: ParCurve, shape: ShockVector,
    limit_amount: float, limit_name: str = "stress loss limit",
    amber_utilisation_percent: float = 80.0,
    search_low: float | None = None, search_high: float | None = None,
) -> LimitBreachResult:
    """The stress severity at which a stated loss limit, and its amber level, are met.

    The limit is an explicit input. This engine holds no risk policy and will
    not invent one: a threshold that appears in a report without a stated source
    becomes policy by accident.
    """
    if limit_amount <= 0:
        raise EngineError(
            "INVALID_LIMIT",
            f"a stress-loss limit must be a positive amount; got {limit_amount:,.2f}",
            category="USER_INPUT",
            suggested_action="Pass the limit as a positive loss amount.")
    if not 0 < amber_utilisation_percent < 100:
        raise EngineError(
            "INVALID_LIMIT",
            f"amber_utilisation_percent must lie strictly between 0 and 100; "
            f"got {amber_utilisation_percent}",
            category="USER_INPUT")

    amber_amount = limit_amount * amber_utilisation_percent / 100.0
    breach = amber = None
    breach_reason = amber_reason = None
    try:
        breach = run_reverse_stress(book, par, shape, limit_amount,
                                    search_low, search_high)
    except EngineError as exc:
        breach_reason = exc.plain_message
    try:
        amber = run_reverse_stress(book, par, shape, amber_amount,
                                   search_low, search_high)
    except EngineError as exc:
        amber_reason = exc.plain_message

    return LimitBreachResult(
        limit_name=limit_name, limit_amount=limit_amount,
        amber_utilisation_percent=amber_utilisation_percent,
        amber_amount=amber_amount, breach=breach, amber=amber,
        breach_reason=breach_reason, amber_reason=amber_reason,
    )
