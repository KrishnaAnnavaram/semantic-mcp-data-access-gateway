"""Historical and reverse stress tools.

The protocol wrapper for `historical_stress` and `reverse_stress`.

Two families that look unrelated and share one discipline: **neither invents a
number**. A historical scenario's shock is measured from two curves the data
server published, at the moment of use. A reverse stress's answer is solved from
the same full revaluation everything else uses, inside a bracket the caller set,
and reports whether it converged.

The named crisis catalogue is a list of **dates**, never of basis points. The
catalogue itself is published as `risk://scenarios/historical-crises`, and a
crisis whose window the supplied history does not cover is refused with the gap
named rather than approximated from whatever dates happen to be to hand.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import Field

from .contracts import (
    DETERMINISTIC,
    CurveHistoryInput,
    DatedCurveInput,
    ParCurveInput,
    PortfolioInput,
    ResultBase,
    ShockVectorOutput,
    months,
    repro,
    shock_output,
    to_book,
    to_par_curve,
    years,
)
from .errors import EngineError
from .historical_stress import (
    DatedCurve,
    MissingTenorPolicy,
    find_worst_historical,
    resolve_crisis,
    run_historical_replay,
    select_crisis_curves,
)
from .manifest import sha256_of
from .reverse_stress import (
    compute_thresholds,
    find_limit_breach,
    run_reverse_stress,
)
from .stress_scenarios import (
    Interpolation,
    custom_shock,
    parallel_shock,
    template_shock,
)

HISTORICAL_NOTE = (
    "The shock is the observed difference between two published Treasury "
    "curves, measured at run time. Nothing in this scenario was written down: "
    "change the dates and the shock changes, because the shock is the data."
)

REVERSE_NOTE = (
    "A solved stress magnitude, not an observed one. It is the multiple of the "
    "chosen scenario shape whose full revaluation produces the target loss, "
    "found by bracketed root finding inside the search interval given. It says "
    "nothing about how likely that move is."
)


class HistoricalStressOutput(ResultBase):
    historical_start: dt.date
    historical_end: dt.date
    crisis_id: str | None
    crisis_name: str | None
    shock: ShockVectorOutput
    observed_shocks_bp_by_tenor_months: dict[str, float]
    tenors_used_months: list[float]
    tenors_unshocked_months: list[float]
    base_value: float
    stressed_value: float
    pnl: float
    pnl_percent: float
    positions: list[dict[str, Any]]
    largest_position_contributor: str | None


class WorstHistoricalOutput(ResultBase):
    base_value: float
    horizon_days: int
    scenarios_considered: int
    lookback_observations: int
    first_date: dt.date | None
    last_date: dt.date | None
    worst: list[dict[str, Any]]
    best_pnl: float
    mean_pnl: float


class ReverseStressOutput(ResultBase):
    target_loss: float
    shape_name: str
    scenario_type: str
    solved_multiplier: float
    solved_shock_bp_at_reference_tenor: float
    shock: ShockVectorOutput
    base_value: float
    resulting_pnl: float
    resulting_pnl_percent: float
    converged: bool
    iterations: int
    search_low: float
    search_high: float
    effective_search_low: float
    effective_search_high: float
    monotone_over_bracket: bool
    tolerance: float
    methodology: str


class ThresholdTableOutput(ResultBase):
    shape_name: str
    base_value: float
    reference_tenor_months: float
    rows: list[dict[str, Any]]


class LimitBreachOutput(ResultBase):
    limit_name: str
    limit_amount: float
    amber_utilisation_percent: float
    amber_amount: float
    breach_shock_bp: float | None
    breach_multiplier: float | None
    breach_shock_vector: dict[str, float] | None
    amber_shock_bp: float | None
    amber_multiplier: float | None
    breach_reason: str | None
    amber_reason: str | None
    base_value: float


ShapeName = Literal[
    "PARALLEL", "BEAR_STEEPENER", "BULL_STEEPENER", "BEAR_FLATTENER",
    "BULL_FLATTENER", "BELLY_SELLOFF", "WINGS_SELLOFF", "CUSTOM",
]


def _shape_for(par: Any, shape: str, severity_bp: float,
               interpolation: Interpolation,
               custom: dict[str, float] | None) -> Any:
    """The direction the reverse-stress solver scales.

    Only the *shape* matters here, not its magnitude - the solver finds the
    multiple. A parallel shape is normalised to 1bp so the solved multiplier
    reads directly as basis points.
    """
    if shape == "PARALLEL":
        return parallel_shock(par, 1.0, name="Parallel shift")
    if shape == "CUSTOM":
        if not custom:
            raise EngineError(
                "INVALID_STRESS_VECTOR",
                "shape 'CUSTOM' needs custom_shape_bp_by_tenor_months, which "
                "defines the direction the solver scales.",
                category="USER_INPUT",
                suggested_action=(
                    "Supply the shape as a tenor-to-basis-point map. Its "
                    "magnitude does not matter - it is what gets scaled."))
        return custom_shock(par, {years(float(k)): float(v) for k, v in custom.items()},
                            name="Custom shape")
    return template_shock(par, shape, severity_bp, interpolation)


def register(server: Any) -> None:

    @server.tool(annotations=DETERMINISTIC, description=(
        "Replay an observed historical curve move against today's book. The "
        "shock is the difference between the two supplied published curves, "
        "measured here - no historical shock is stored anywhere in this engine. "
        "Fetch both curves from market-risk-data-mcp and pass them in. A tenor "
        "present on the valuation curve but missing on either historical date "
        "is refused by default, because leaving it unshocked understates the "
        "loss silently; missing_tenor_policy='intersection' accepts that and "
        "lists the tenors it left alone."
    ))
    def run_historical_stress_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        historical_start_curve: DatedCurveInput,
        historical_end_curve: DatedCurveInput,
        missing_tenor_policy: MissingTenorPolicy = "reject",
    ) -> HistoricalStressOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        replay = run_historical_replay(
            book, par,
            DatedCurve(historical_start_curve.observation_date,
                       to_par_curve(historical_start_curve)),
            DatedCurve(historical_end_curve.observation_date,
                       to_par_curve(historical_end_curve)),
            missing_tenor_policy)
        worst = replay.run.worst_position()
        return HistoricalStressOutput(
            valuation_date=valuation_date,
            historical_start=replay.historical_start,
            historical_end=replay.historical_end,
            crisis_id=replay.crisis_id, crisis_name=replay.crisis_name,
            shock=shock_output(replay.run.shock),
            observed_shocks_bp_by_tenor_months={
                str(months(t)): v for t, v in sorted(replay.observed_shocks_bp.items())},
            tenors_used_months=[months(t) for t in replay.tenors_used],
            tenors_unshocked_months=[months(t) for t in replay.tenors_unshocked],
            base_value=replay.run.base_value,
            stressed_value=replay.run.stressed_value,
            pnl=replay.run.pnl, pnl_percent=replay.run.pnl_percent,
            positions=[vars(p) for p in replay.run.positions],
            largest_position_contributor=worst.instrument_id if worst else None,
            warnings=list(replay.warnings),
            reproducibility=repro(portfolio, par_curve, {
                "historical_start": historical_start_curve.model_dump(mode="json"),
                "historical_end": historical_end_curve.model_dump(mode="json"),
                "missing_tenor_policy": missing_tenor_policy}),
            data_classification=portfolio.data_classification,
            interpretation=HISTORICAL_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Replay a named historical crisis against today's book: the 1994 bond "
        "selloff, the 2008 Lehman quarter, the 2013 taper tantrum, the March "
        "2020 COVID shock, the 2022 tightening cycle or the March 2023 regional "
        "bank stress. The catalogue holds documented DATES ONLY - the shock is "
        "derived from the supplied published curves at run time, so no crisis "
        "shock vector is stored anywhere. Supply curves covering the window; if "
        "they do not cover it the scenario is refused with the gap named, "
        "rather than measured from whatever dates are to hand."
    ))
    def run_historical_crisis_stress_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        crisis_id: str = Field(
            description="A catalogue id, e.g. '2020_COVID_SHOCK'. Read "
                        "risk://scenarios/historical-crises for the full list."),
        historical_curves: list[DatedCurveInput] = Field(
            default_factory=list,
            description="Published curves covering the crisis window."),
        tolerance_days: int = Field(
            default=7, ge=0,
            description="How far from the documented dates a published curve may "
                        "be. Treasury does not publish at weekends, so some "
                        "tolerance is always needed."),
        missing_tenor_policy: MissingTenorPolicy = "reject",
    ) -> HistoricalStressOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        crisis = resolve_crisis(crisis_id)
        curves = [DatedCurve(c.observation_date, to_par_curve(c))
                  for c in historical_curves]
        start, end = select_crisis_curves(crisis, curves, tolerance_days)
        replay = run_historical_replay(book, par, start, end,
                                       missing_tenor_policy, crisis)
        worst = replay.run.worst_position()
        return HistoricalStressOutput(
            valuation_date=valuation_date,
            historical_start=replay.historical_start,
            historical_end=replay.historical_end,
            crisis_id=replay.crisis_id, crisis_name=replay.crisis_name,
            shock=shock_output(replay.run.shock),
            observed_shocks_bp_by_tenor_months={
                str(months(t)): v for t, v in sorted(replay.observed_shocks_bp.items())},
            tenors_used_months=[months(t) for t in replay.tenors_used],
            tenors_unshocked_months=[months(t) for t in replay.tenors_unshocked],
            base_value=replay.run.base_value,
            stressed_value=replay.run.stressed_value,
            pnl=replay.run.pnl, pnl_percent=replay.run.pnl_percent,
            positions=[vars(p) for p in replay.run.positions],
            largest_position_contributor=worst.instrument_id if worst else None,
            warnings=list(replay.warnings) + [
                (f"Documented window: {crisis.start_date} to {crisis.end_date}. "
                f"Curves used: {replay.historical_start} to {replay.historical_end}."),
                crisis.what_happened],
            reproducibility=repro(portfolio, par_curve, {
                "crisis_id": crisis.crisis_id,
                "documented_window": [crisis.start_date.isoformat(),
                                      crisis.end_date.isoformat()],
                "curves_used": [replay.historical_start.isoformat(),
                                replay.historical_end.isoformat()],
                "tolerance_days": tolerance_days}),
            data_classification=portfolio.data_classification,
            interpretation=HISTORICAL_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "If today's portfolio had existed throughout the supplied history, "
        "which observed rate moves would have hurt it most? Every h-day move in "
        "the window is applied to today's curve and the book is revalued in "
        "full, then the losses are ranked. Because it revalues rather than "
        "approximating, the answer is frequently not the largest move: a book "
        "concentrated in the belly loses more from a mid-curve shock than from "
        "a bigger parallel one. Returns the ranked windows with their dates, "
        "shock vectors and largest contributor."
    ))
    def find_worst_historical_stresses_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        history: CurveHistoryInput,
        horizon_days: int = Field(default=1, ge=1),
        top_n: int = Field(default=10, ge=1, le=100),
    ) -> WorstHistoricalOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        result = find_worst_historical(
            book, par, [years(t) for t in history.tenors_months],
            [[float(x) for x in row] for row in history.rates_percent],
            history.dates, horizon_days, top_n)
        return WorstHistoricalOutput(
            valuation_date=valuation_date, base_value=result.base_value,
            horizon_days=result.horizon_days,
            scenarios_considered=result.scenarios_considered,
            lookback_observations=result.lookback_observations,
            first_date=result.first_date, last_date=result.last_date,
            worst=[{
                "rank": w.rank,
                "start_date": w.start_date.isoformat() if w.start_date else None,
                "end_date": w.end_date.isoformat() if w.end_date else None,
                "start_observation_index": w.start_index,
                "end_observation_index": w.end_index,
                "shocks_bp_by_tenor_months": {str(months(t)): v
                                              for t, v in sorted(w.shocks_bp.items())},
                "pnl": w.pnl, "pnl_percent": w.pnl_percent,
                "largest_position_contributor": w.largest_position_contributor,
                "largest_position_pnl": w.largest_position_pnl,
            } for w in result.worst],
            best_pnl=result.best_pnl, mean_pnl=result.mean_pnl,
            warnings=([] if history.dates else [
                ("No dates were supplied with the history, so the worst windows "
                "are identified by row index only.")]),
            reproducibility=repro(portfolio, par_curve, {
                "horizon_days": horizon_days, "top_n": top_n,
                "history_sha256": sha256_of(history.rates_percent)}),
            data_classification=portfolio.data_classification,
            interpretation=HISTORICAL_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Reverse stress: solve for the rate move that produces a given loss. "
        "Takes a scenario SHAPE - parallel, a named template, or a custom "
        "vector - and finds the multiple of it whose full revaluation loses the "
        "target amount. Returns the solved shock vector, the resulting P&L, "
        "convergence status, iteration count, the search interval and whether "
        "the P&L was monotone across it. A target unreachable inside the "
        "interval is refused with the reachable loss range named, never "
        "answered by silently widening the search."
    ))
    def run_reverse_stress_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        target_loss: float = Field(
            default=1_000_000.0, ge=0,
            description="The loss to solve for, as a positive amount."),
        shape: ShapeName = "PARALLEL",
        custom_shape_bp_by_tenor_months: dict[str, float] | None = None,
        severity_bp: float = Field(default=100.0, gt=0),
        interpolation: Interpolation = "linear_years",
        search_low: float | None = Field(
            default=None,
            description="Lower search bound: basis points for PARALLEL, a shape "
                        "multiplier otherwise. Defaults to -500bp / -5x."),
        search_high: float | None = Field(
            default=None,
            description="Upper search bound. Defaults to +500bp / +5x."),
        tolerance: float = Field(default=1e-6, gt=0),
        max_iterations: int = Field(default=200, ge=10, le=1000),
    ) -> ReverseStressOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        shape_vector = _shape_for(par, shape, severity_bp, interpolation,
                                  custom_shape_bp_by_tenor_months)
        result = run_reverse_stress(book, par, shape_vector, target_loss,
                                    search_low, search_high, tolerance,
                                    max_iterations)
        warnings = []
        if result.bracket_reduced_reason:
            warnings.append(result.bracket_reduced_reason)
        if not result.monotone_over_bracket:
            warnings.append(
                "P&L is not monotone across the search interval, so more than "
                "one shock magnitude may produce this loss. The solver returns "
                "one root; treat it as a root rather than the root.")
        if not result.converged:
            warnings.append(
                f"The solver stopped after {result.iterations} iterations "
                "without meeting the tolerance. Treat the answer as approximate.")
        return ReverseStressOutput(
            valuation_date=valuation_date, target_loss=result.target_loss,
            shape_name=result.shape_name, scenario_type=result.scenario_type,
            solved_multiplier=result.solved_multiplier,
            solved_shock_bp_at_reference_tenor=result.solved_shock_bp_at_reference,
            shock=shock_output(result.run.shock),
            base_value=result.base_value, resulting_pnl=result.resulting_pnl,
            resulting_pnl_percent=result.resulting_pnl_percent,
            converged=result.converged, iterations=result.iterations,
            search_low=result.search_low, search_high=result.search_high,
            effective_search_low=result.effective_search_low,
            effective_search_high=result.effective_search_high,
            monotone_over_bracket=result.monotone_over_bracket,
            tolerance=result.tolerance,
            methodology=(
                "Brent root finding on the full-revaluation P&L of a scaled "
                "scenario shape, inside an explicit bracket. Deterministic: the "
                "same inputs give the same multiplier."),
            warnings=warnings,
            reproducibility=repro(portfolio, par_curve, {
                "target_loss": target_loss, "shape": shape,
                "custom_shape": custom_shape_bp_by_tenor_months,
                "severity_bp": severity_bp, "search_low": search_low,
                "search_high": search_high, "tolerance": tolerance}),
            data_classification=portfolio.data_classification,
            interpretation=REVERSE_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "The stress magnitude required to reach each of several loss "
        "thresholds - the table that turns 'we lose 1.9m at +100bp' into 'we "
        "lose 1m at +49bp and 5m at +278bp'. Each row is solved independently "
        "by full revaluation. A threshold that cannot be reached inside the "
        "search interval is reported with its reason and the other rows still "
        "return."
    ))
    def compute_stress_thresholds_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        target_losses: list[float] = Field(
            default_factory=lambda: [500_000.0, 1_000_000.0, 2_000_000.0, 5_000_000.0],
            description="Loss levels to solve for, as positive amounts."),
        shape: ShapeName = "PARALLEL",
        custom_shape_bp_by_tenor_months: dict[str, float] | None = None,
        severity_bp: float = Field(default=100.0, gt=0),
        interpolation: Interpolation = "linear_years",
        search_low: float | None = None,
        search_high: float | None = None,
    ) -> ThresholdTableOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        shape_vector = _shape_for(par, shape, severity_bp, interpolation,
                                  custom_shape_bp_by_tenor_months)
        table = compute_thresholds(book, par, shape_vector, target_losses,
                                   search_low, search_high)
        return ThresholdTableOutput(
            valuation_date=valuation_date, shape_name=table.shape_name,
            base_value=table.base_value,
            reference_tenor_months=months(table.reference_tenor_years),
            rows=[{
                "target_loss": r.target_loss,
                "solved_multiplier": r.solved_multiplier,
                "solved_shock_bp_at_reference_tenor": r.solved_shock_bp_at_reference,
                "resulting_pnl": r.resulting_pnl,
                "converged": r.converged,
                "unreachable_reason": r.reason,
            } for r in table.rows],
            warnings=[f"target {r.target_loss:,.0f}: {r.reason}"
                      for r in table.rows if r.reason],
            reproducibility=repro(portfolio, par_curve, {
                "target_losses": target_losses, "shape": shape,
                "search_low": search_low, "search_high": search_high}),
            data_classification=portfolio.data_classification,
            interpretation=REVERSE_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "The stress severity at which a stated loss limit is breached, and the "
        "severity at which it turns amber. The limit is an explicit input - "
        "this engine holds no risk policy and will not supply one, because a "
        "threshold that appears in a report without a stated source becomes "
        "policy by accident. Nothing stored is modified."
    ))
    def find_limit_breach_stress_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        limit_amount: float = Field(
            default=2_000_000.0, gt=0,
            description="The stress-loss limit, as a positive amount."),
        limit_name: str = "stress loss limit",
        amber_utilisation_percent: float = Field(default=80.0, gt=0, lt=100),
        shape: ShapeName = "PARALLEL",
        custom_shape_bp_by_tenor_months: dict[str, float] | None = None,
        severity_bp: float = Field(default=100.0, gt=0),
        interpolation: Interpolation = "linear_years",
        search_low: float | None = None,
        search_high: float | None = None,
    ) -> LimitBreachOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        shape_vector = _shape_for(par, shape, severity_bp, interpolation,
                                  custom_shape_bp_by_tenor_months)
        result = find_limit_breach(book, par, shape_vector, limit_amount, limit_name,
                                   amber_utilisation_percent, search_low, search_high)
        warnings = [w for w in (result.breach_reason, result.amber_reason) if w]
        return LimitBreachOutput(
            valuation_date=valuation_date, limit_name=result.limit_name,
            limit_amount=result.limit_amount,
            amber_utilisation_percent=result.amber_utilisation_percent,
            amber_amount=result.amber_amount,
            breach_shock_bp=(result.breach.solved_shock_bp_at_reference
                             if result.breach else None),
            breach_multiplier=(result.breach.solved_multiplier
                               if result.breach else None),
            breach_shock_vector=({str(months(t)): v for t, v
                                  in sorted(result.breach.shock_vector.items())}
                                 if result.breach else None),
            amber_shock_bp=(result.amber.solved_shock_bp_at_reference
                            if result.amber else None),
            amber_multiplier=(result.amber.solved_multiplier
                              if result.amber else None),
            breach_reason=result.breach_reason, amber_reason=result.amber_reason,
            base_value=book.value_under(par),
            warnings=warnings,
            reproducibility=repro(portfolio, par_curve, {
                "limit_amount": limit_amount, "limit_name": limit_name,
                "amber_utilisation_percent": amber_utilisation_percent,
                "shape": shape}),
            data_classification=portfolio.data_classification,
            interpretation=(
                REVERSE_NOTE + " The limit and its amber threshold are the "
                "caller's, not this engine's."),
        )
