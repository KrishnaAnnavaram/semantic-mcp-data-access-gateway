"""Stress-testing tools.

The protocol wrapper for `stress_scenarios`, `stress_matrix` and
`contributions`. `run_stress_tool` in `server.py` stays exactly as it was and is
still the engine underneath every one of these: each tool here **generates a
tenor-to-basis-point shock vector and then revalues in full**.

One rule governs the whole family: **the shock vector is always returned**. A
scenario named "bear steepener" whose shape cannot be inspected is a number
nobody can check, and the moment two reports mean slightly different things by
the name, reading the vectors is the only way to find out.

The second rule is that a scenario the bootstrap refuses is reported as a
scenario that did not run, with its reason - never dropped, and never priced
anyway. A +100bp single-node bump at the 20-year inverts the 20s30s segment by
most of a percent on a normally shaped curve, and the resulting curve is
genuinely not arbitrage-consistent. Saying so is the correct answer.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import Field

from .concentration import most_sensitive_tenors
from .contracts import (
    DETERMINISTIC,
    STRESS_NOTE,
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
from .contributions import (
    AttributionMethod,
    attribute_stress,
    run_shock,
)
from .curves import CurveError
from .errors import EngineError
from .stress_matrix import (
    STANDARD_PACK_VERSION,
    bucket_table,
    build_standard_pack,
    compare_scenarios,
    run_stress_matrix,
)
from .stress_scenarios import (
    SEVERITY_BP,
    SEVERITY_NOTE,
    TEMPLATES,
    Interpolation,
    custom_shock,
    key_rate_shock,
    parallel_shock,
    severity_pack,
    template_shock,
    twist_shock,
)

TemplateName = Literal[
    "BEAR_STEEPENER", "BULL_STEEPENER", "BEAR_FLATTENER", "BULL_FLATTENER",
    "BELLY_SELLOFF", "BELLY_RALLY", "WINGS_SELLOFF", "WINGS_RALLY",
]

SeverityLabel = Literal["MILD", "MODERATE", "SEVERE", "EXTREME"]


class StressRunOutput(ResultBase):
    shock: ShockVectorOutput
    base_value: float
    stressed_value: float
    pnl: float
    pnl_percent: float
    positions: list[dict[str, Any]]
    top_position_contributors: list[dict[str, Any]]
    top_tenor_contributors: list[dict[str, Any]]
    maturity_buckets: list[dict[str, Any]]
    tenor_attribution_method: str
    tenor_explained_pnl: float
    tenor_residual_pnl: float
    tenor_residual_percent: float
    position_concentration: dict[str, float]
    tenor_concentration: dict[str, float]


class ShockLadderOutput(ResultBase):
    base_value: float
    rungs: list[dict[str, Any]]
    effective_duration_years: float
    effective_convexity: float
    convexity_note: str


class StressMatrixOutput(ResultBase):
    pack_version: str
    base_value: float
    scenario_count: int
    scenarios: list[dict[str, Any]]
    key_rate_dv01: list[dict[str, float]]
    worst_case_bucket_table: list[dict[str, Any]]
    comparison: dict[str, Any]
    skipped: list[str]
    failed: list[dict[str, str]]


class ScenarioComparisonOutput(ResultBase):
    worst_scenario: str
    worst_pnl: float
    best_scenario: str
    best_pnl: float
    loss_range: float
    severity_spread_bp: float
    dominant_position: str | None
    dominant_maturity_bucket: str | None
    dominant_scenario_type: str | None
    ranked: list[dict[str, Any]]
    pnl_concentration: dict[str, float]


class StressExplanationOutput(ResultBase):
    scenario_name: str
    shock: ShockVectorOutput
    base_value: float
    stressed_value: float
    total_pnl: float
    total_pnl_percent: float
    position_contributions: list[dict[str, Any]]
    tenor_contributions: list[dict[str, Any]]
    bucket_contributions: list[dict[str, Any]]
    tenor_explained_pnl: float
    tenor_residual_pnl: float
    largest_position: dict[str, Any] | None
    largest_tenor: dict[str, Any] | None
    concentration: dict[str, Any]
    facts_only_note: str


class SeverityPackOutput(ResultBase):
    template: str
    base_value: float
    severity_note: str
    scenarios: list[dict[str, Any]]


def _to_attribution(result: Any, top_n: int) -> tuple[list[dict], list[dict]]:
    positions = sorted(
        ({"instrument_id": p.instrument_id, "base_value": p.base_value,
          "stressed_value": p.stressed_value, "pnl": p.pnl,
          "contribution_percent": p.contribution_percent}
         for p in result.run.positions),
        key=lambda r: r["pnl"])
    tenors = sorted(
        ({"tenor_months": months(t.tenor_years), "shock_bp": t.shock_bp,
          "key_rate_dv01": t.key_rate_dv01, "pnl": t.pnl,
          "contribution_percent": t.contribution_percent,
          "attributable": t.attributable}
         for t in result.tenors),
        key=lambda r: r["pnl"])
    return positions[:top_n], tenors[:top_n]


def _stress_output(
    result: Any, portfolio: PortfolioInput, valuation_date: dt.date,
    par_curve: ParCurveInput, extra: dict[str, Any], top_n: int,
) -> StressRunOutput:
    top_positions, top_tenors = _to_attribution(result, top_n)
    return StressRunOutput(
        valuation_date=valuation_date,
        shock=shock_output(result.run.shock),
        base_value=result.run.base_value, stressed_value=result.run.stressed_value,
        pnl=result.run.pnl, pnl_percent=result.run.pnl_percent,
        positions=[{"instrument_id": p.instrument_id, "base_value": p.base_value,
                    "stressed_value": p.stressed_value, "pnl": p.pnl,
                    "contribution_percent": p.contribution_percent}
                   for p in result.run.positions],
        top_position_contributors=top_positions,
        top_tenor_contributors=top_tenors,
        maturity_buckets=[vars(b) for b in result.buckets],
        tenor_attribution_method=result.method,
        tenor_explained_pnl=result.tenor_explained_pnl,
        tenor_residual_pnl=result.tenor_residual_pnl,
        tenor_residual_percent=result.tenor_residual_percent,
        position_concentration=vars(result.position_concentration),
        tenor_concentration=vars(result.tenor_concentration),
        warnings=list(result.warnings),
        reproducibility=repro(portfolio, par_curve, extra),
        data_classification=portfolio.data_classification,
        interpretation=STRESS_NOTE,
    )


def register(server: Any) -> None:

    @server.tool(annotations=DETERMINISTIC, description=(
        "Standardised interest-rate stress by full revaluation: a parallel "
        "shift, or one of the named curve-shape templates (bear/bull steepener, "
        "bear/bull flattener, belly and wings selloff or rally). At severity "
        "100bp the templates reproduce the canonical desk shapes exactly - a "
        "bear steepener is 2Y +25, 5Y +50, 10Y +100, 30Y +150. The resolved "
        "tenor shock vector is always returned, along with per-position P&L, "
        "first-order tenor attribution and its residual."
    ))
    def run_rate_stress_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        parallel_shock_bp: float | None = Field(
            default=None,
            description="Parallel shift in basis points. Supply this OR template."),
        template: TemplateName | None = Field(
            default=None,
            description="A named curve-shape scenario. Supply this OR "
                        "parallel_shock_bp."),
        severity_bp: float = Field(
            default=100.0, gt=0,
            description="Template magnitude. At 100 the templates give the "
                        "canonical shapes."),
        interpolation: Interpolation = "linear_years",
        attribution_method: AttributionMethod = "first_order",
        top_n: int = Field(default=5, ge=1),
    ) -> StressRunOutput:
        par = to_par_curve(par_curve)
        if (parallel_shock_bp is None) == (template is None):
            raise EngineError(
                "INVALID_STRESS_VECTOR",
                "supply exactly one of parallel_shock_bp or template. Supplying "
                "both would silently run one and ignore the other; supplying "
                "neither leaves no scenario to run.",
                category="USER_INPUT",
                suggested_action=(
                    f"Pass parallel_shock_bp for a parallel shift, or one of "
                    f"{sorted(TEMPLATES)} for a curve-shape scenario."))
        vector = (parallel_shock(par, parallel_shock_bp) if template is None
                  else template_shock(par, template, severity_bp, interpolation))
        result = attribute_stress(to_book(portfolio, valuation_date), par, vector,
                                  attribution_method)
        return _stress_output(result, portfolio, valuation_date, par_curve, {
            "parallel_shock_bp": parallel_shock_bp, "template": template,
            "severity_bp": severity_bp, "interpolation": interpolation,
            "attribution_method": attribution_method}, top_n)

    @server.tool(annotations=DETERMINISTIC, description=(
        "Stress one or more individual curve nodes and nothing else, by full "
        "revaluation. Single-node bumps with no tent and no smoothing, so the "
        "result is directly comparable with compute_key_rate_dv01_tool, which "
        "perturbs the same way. Also reports the first-order KRDV01 x shock "
        "prediction next to the revalued answer, which is a model-validation "
        "check as well as an analytic: the gap between them is the convexity. "
        "A tenor that is not a curve node is refused rather than snapped to a "
        "neighbour."
    ))
    def run_key_rate_stress_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        key_tenors_months: list[float] = Field(
            min_length=1,
            description="Curve nodes to shock, in months. 120 is the 10-year."),
        shock_bp: float = Field(default=100.0),
        top_n: int = Field(default=5, ge=1),
    ) -> StressRunOutput:
        par = to_par_curve(par_curve)
        vector = key_rate_shock(par, [years(t) for t in key_tenors_months], shock_bp)
        book = to_book(portfolio, valuation_date)
        try:
            result = attribute_stress(book, par, vector, "first_order")
        except CurveError as exc:
            raise EngineError(
                "INVALID_CURVE",
                f"shocking {[f'{t:g}m' for t in key_tenors_months]} by "
                f"{shock_bp:+.0f}bp alone leaves the curve arbitrage-"
                f"inconsistent: {exc}. This is a real property of a single-node "
                "bump of this size, not a defect - the node moves past its "
                "neighbours and the bootstrap meets a negative forward.",
                category="NUMERICAL",
                suggested_action=(
                    "Use a smaller shock, or shock the neighbouring nodes with "
                    "it via run_stress_tool."),
            ) from exc
        return _stress_output(result, portfolio, valuation_date, par_curve, {
            "key_tenors_months": key_tenors_months, "shock_bp": shock_bp}, top_n)

    @server.tool(annotations=DETERMINISTIC, description=(
        "Rotate the curve about a pivot tenor: the short end falls by the "
        "magnitude, the pivot moves exactly zero, the long end rises by the "
        "magnitude, and the intermediate nodes are interpolated by the stated "
        "rule. A negative magnitude inverts the rotation. Interpolation "
        "'linear_years' spreads the rotation evenly in maturity; 'node_rank' "
        "spreads it evenly across the published nodes and reproduces the "
        "textbook 2Y -100 / 5Y -50 / 10Y 0 / 20Y +50 / 30Y +100 table exactly. "
        "Neither is more correct; which one ran is in the result."
    ))
    def run_curve_twist_stress_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        pivot_tenor_months: float = Field(
            default=120.0, description="Pivot, in months. 120 is the 10-year."),
        magnitude_bp: float = Field(default=100.0),
        interpolation: Interpolation = "linear_years",
        attribution_method: AttributionMethod = "first_order",
        top_n: int = Field(default=5, ge=1),
    ) -> StressRunOutput:
        par = to_par_curve(par_curve)
        vector = twist_shock(par, years(pivot_tenor_months), magnitude_bp, interpolation)
        result = attribute_stress(to_book(portfolio, valuation_date), par, vector,
                                  attribution_method)
        return _stress_output(result, portfolio, valuation_date, par_curve, {
            "pivot_tenor_months": pivot_tenor_months, "magnitude_bp": magnitude_bp,
            "interpolation": interpolation}, top_n)

    @server.tool(annotations=DETERMINISTIC, description=(
        "Curvature stress: sell off or rally the belly of the curve against its "
        "wings, or the wings against the belly, by full revaluation. At "
        "severity 100bp a belly selloff is 2Y +25, 5Y +100, 10Y +100, 30Y +25 "
        "and a wings selloff is 2Y +100, 5Y +25, 10Y +25, 30Y +100. This is the "
        "scenario a barbelled or bulleted book is exposed to and a parallel "
        "shift cannot show."
    ))
    def run_curve_curvature_stress_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        shape: Literal["BELLY_SELLOFF", "BELLY_RALLY",
                       "WINGS_SELLOFF", "WINGS_RALLY"] = "BELLY_SELLOFF",
        severity_bp: float = Field(default=100.0, gt=0),
        interpolation: Interpolation = "linear_years",
        attribution_method: AttributionMethod = "first_order",
        top_n: int = Field(default=5, ge=1),
    ) -> StressRunOutput:
        par = to_par_curve(par_curve)
        vector = template_shock(par, shape, severity_bp, interpolation)
        result = attribute_stress(to_book(portfolio, valuation_date), par, vector,
                                  attribution_method)
        return _stress_output(result, portfolio, valuation_date, par_curve, {
            "shape": shape, "severity_bp": severity_bp,
            "interpolation": interpolation}, top_n)

    @server.tool(annotations=DETERMINISTIC, description=(
        "A ladder of parallel shocks, each fully revalued, with the duration "
        "and duration-plus-convexity approximations and their errors beside the "
        "revalued answer at every rung. This is where a portfolio's convexity "
        "becomes visible as a number: the up and down legs of the ladder are "
        "not mirror images, and the duration-only error grows quadratically "
        "with the shock while the convexity-corrected error does not."
    ))
    def run_shock_ladder_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        shocks_bp: list[float] = Field(
            default_factory=lambda: [-300.0, -250.0, -200.0, -150.0, -100.0, -75.0,
                                     -50.0, -25.0, 0.0, 25.0, 50.0, 75.0, 100.0,
                                     150.0, 200.0, 250.0, 300.0],
            min_length=1),
        effective_bump_bp: float = Field(default=25.0, gt=0),
    ) -> ShockLadderOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        base = book.value_under(par)
        dy = effective_bump_bp / 10_000.0
        up = book.value_under(par.shifted(effective_bump_bp))
        down = book.value_under(par.shifted(-effective_bump_bp))
        duration = (down - up) / (2.0 * base * dy) if base else 0.0
        convexity = (up + down - 2.0 * base) / (base * dy * dy) if base else 0.0

        rungs = []
        for shock in sorted(shocks_bp):
            move = shock / 10_000.0
            try:
                stressed = book.value_under(par.shifted(shock))
            except CurveError as exc:
                rungs.append({"shock_bp": shock, "failed_reason": str(exc)})
                continue
            actual = stressed - base
            duration_only = -duration * move * base
            with_convexity = duration_only + 0.5 * convexity * move * move * base
            rungs.append({
                "shock_bp": shock,
                "stressed_value": stressed,
                "pnl": actual,
                "pnl_percent": (actual / base * 100.0) if base else 0.0,
                "duration_only_pnl": duration_only,
                "duration_convexity_pnl": with_convexity,
                "duration_only_error": duration_only - actual,
                "duration_convexity_error": with_convexity - actual,
            })
        return ShockLadderOutput(
            valuation_date=valuation_date, base_value=base, rungs=rungs,
            effective_duration_years=duration, effective_convexity=convexity,
            convexity_note=(
                "A positively convex book loses less on a rate rise than "
                "duration alone predicts, and gains more on a fall, so the up "
                "and down legs of this ladder are deliberately asymmetric. "
                "Compare duration_only_error with duration_convexity_error at "
                "the widest rungs: the gap is the reason this engine revalues "
                "in full rather than approximating."),
            reproducibility=repro(portfolio, par_curve, {
                "shocks_bp": sorted(shocks_bp),
                "effective_bump_bp": effective_bump_bp}),
            data_classification=portfolio.data_classification,
            interpretation=STRESS_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "The full standard scenario pack in one call: parallel shifts at "
        "+/-50, +/-100 and +/-200bp, bear and bull steepeners and flatteners at "
        "two severities, twists in both directions, belly and wings selloffs, "
        "and single-node key-rate shocks at 2Y, 5Y, 10Y, 20Y and 30Y - "
        "twenty-one scenarios, all against one base valuation and one key-rate "
        "pass. Returns a table ranked worst-first with each scenario's P&L, its "
        "largest position and tenor contributors, and its shock vector. A "
        "scenario the bootstrap refuses is listed as failed with its reason "
        "rather than dropped."
    ))
    def run_stress_matrix_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        interpolation: Interpolation = "linear_years",
        include_custom_scenarios: list[dict[str, float]] | None = Field(
            default=None,
            description="Extra scenarios as tenor-months-to-basis-point maps, "
                        "added to the standard pack."),
    ) -> StressMatrixOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        vectors, skipped = build_standard_pack(par, interpolation)
        for i, extra in enumerate(include_custom_scenarios or [], start=1):
            vectors.append(custom_shock(
                par, {years(float(k)): float(v) for k, v in extra.items()},
                name=f"Custom scenario {i}"))
        matrix = run_stress_matrix(book, par, vectors, "first_order", skipped)
        comparison = compare_scenarios(matrix)
        return StressMatrixOutput(
            valuation_date=valuation_date, pack_version=matrix.pack_version,
            base_value=matrix.base_value, scenario_count=matrix.scenario_count,
            scenarios=[{
                "rank": e.rank, "scenario_name": e.scenario_name,
                "scenario_type": e.scenario_type, "template": e.template,
                "severity_bp": e.severity_bp,
                "stressed_value": e.stressed_value, "pnl": e.pnl,
                "pnl_percent": e.pnl_percent,
                "largest_position_contributor": e.largest_position_contributor,
                "largest_position_pnl": e.largest_position_pnl,
                "largest_tenor_contributor_months": (
                    months(e.largest_tenor_contributor_years)
                    if e.largest_tenor_contributor_years is not None else None),
                "largest_tenor_pnl": e.largest_tenor_pnl,
                "largest_bucket_contributor": e.largest_bucket_contributor,
                "tenor_explained_pnl": e.tenor_explained_pnl,
                "tenor_residual_pnl": e.tenor_residual_pnl,
                "shock": shock_output(e.shock).model_dump(mode="json"),
            } for e in matrix.entries if e.failed_reason is None],
            key_rate_dv01=[{"tenor_months": months(t), "key_rate_dv01": v}
                           for t, v in matrix.key_rate_dv01],
            worst_case_bucket_table=[vars(b) for b in bucket_table(matrix, par)],
            comparison={
                "worst_scenario": comparison.worst_scenario,
                "worst_pnl": comparison.worst_pnl,
                "best_scenario": comparison.best_scenario,
                "best_pnl": comparison.best_pnl,
                "loss_range": comparison.loss_range,
                "dominant_position": comparison.dominant_position,
                "dominant_maturity_bucket": comparison.dominant_bucket,
                "dominant_scenario_type": comparison.dominant_scenario_type,
            },
            skipped=list(matrix.skipped),
            failed=[{"scenario_name": e.scenario_name, "reason": e.failed_reason}
                    for e in matrix.entries if e.failed_reason is not None],
            reproducibility=repro(portfolio, par_curve, {
                "pack_version": STANDARD_PACK_VERSION,
                "interpolation": interpolation,
                "custom_scenarios": include_custom_scenarios}),
            data_classification=portfolio.data_classification,
            interpretation=STRESS_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Rank a set of caller-supplied shock vectors against one base "
        "valuation and name what drives the extremes: worst and best scenario, "
        "the loss range between them, the dominant position, the dominant "
        "maturity bucket and the P&L concentration across the set. Use this to "
        "compare scenarios that did not come from the standard pack; the pack "
        "itself already returns its own comparison."
    ))
    def compare_stress_scenarios_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        scenarios: list[dict[str, float]] = Field(
            min_length=2,
            description="Each scenario as a map of tenor in months to shock in "
                        "basis points."),
        scenario_names: list[str] | None = None,
    ) -> ScenarioComparisonOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        if scenario_names is not None and len(scenario_names) != len(scenarios):
            raise EngineError(
                "INVALID_STRESS_VECTOR",
                f"{len(scenario_names)} names were supplied for "
                f"{len(scenarios)} scenarios",
                category="USER_INPUT",
                suggested_action="Pass one name per scenario, or omit the names.")
        vectors = [
            custom_shock(par, {years(float(k)): float(v) for k, v in scenario.items()},
                         name=(scenario_names[i] if scenario_names
                               else f"Scenario {i + 1}"))
            for i, scenario in enumerate(scenarios)]
        matrix = run_stress_matrix(book, par, vectors, "first_order",
                                   pack_version="caller_supplied_v1")
        comparison = compare_scenarios(matrix)
        return ScenarioComparisonOutput(
            valuation_date=valuation_date,
            worst_scenario=comparison.worst_scenario, worst_pnl=comparison.worst_pnl,
            best_scenario=comparison.best_scenario, best_pnl=comparison.best_pnl,
            loss_range=comparison.loss_range,
            severity_spread_bp=comparison.severity_spread_bp,
            dominant_position=comparison.dominant_position,
            dominant_maturity_bucket=comparison.dominant_bucket,
            dominant_scenario_type=comparison.dominant_scenario_type,
            ranked=[{"rank": r, "scenario_name": n, "pnl": p, "pnl_percent": pct}
                    for r, n, p, pct in comparison.ranked],
            pnl_concentration=vars(comparison.pnl_concentration),
            warnings=[f"{e.scenario_name}: {e.failed_reason}"
                      for e in matrix.entries if e.failed_reason],
            reproducibility=repro(portfolio, par_curve, {"scenarios": scenarios}),
            data_classification=portfolio.data_classification,
            interpretation=STRESS_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Decompose one scenario's loss across positions and across the curve. "
        "Position contributions are exact - they come from the same revaluation "
        "pass as the portfolio number and sum to it. Tenor contributions are "
        "not, because a curve shock is not separable, and the residual is "
        "reported rather than distributed. Method 'first_order' uses key-rate "
        "DV01 times the shock; 'isolated_reval' reprices each shocked node "
        "alone and marks any node whose isolated bump the bootstrap refuses."
    ))
    def compute_stress_contributions_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        shocks_bp_by_tenor_months: dict[str, float],
        attribution_method: AttributionMethod = "first_order",
        top_n: int = Field(default=5, ge=1),
    ) -> StressRunOutput:
        par = to_par_curve(par_curve)
        vector = custom_shock(
            par, {years(float(k)): float(v)
                  for k, v in shocks_bp_by_tenor_months.items()})
        result = attribute_stress(to_book(portfolio, valuation_date), par, vector,
                                  attribution_method)
        return _stress_output(result, portfolio, valuation_date, par_curve, {
            "shocks_bp": shocks_bp_by_tenor_months,
            "attribution_method": attribution_method}, top_n)

    @server.tool(annotations=DETERMINISTIC, description=(
        "Structured, quantitative facts about why a stress scenario loses what "
        "it loses: the shock vector, base and stressed value, every position's "
        "contribution and share, every tenor's contribution and share, the "
        "maturity-bucket split, the largest single contributor on each axis and "
        "the concentration of the loss. Returns facts only and contains no "
        "language model - the orchestrator turns these numbers into prose, and "
        "the numbers stay checkable."
    ))
    def explain_stress_loss_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        shocks_bp_by_tenor_months: dict[str, float],
        scenario_name: str = "Custom shock vector",
        attribution_method: AttributionMethod = "first_order",
    ) -> StressExplanationOutput:
        par = to_par_curve(par_curve)
        vector = custom_shock(
            par, {years(float(k)): float(v)
                  for k, v in shocks_bp_by_tenor_months.items()},
            name=scenario_name)
        result = attribute_stress(to_book(portfolio, valuation_date), par, vector,
                                  attribution_method)
        worst_position = result.run.worst_position()
        worst_tenor = min(result.tenors, key=lambda t: t.pnl, default=None)
        return StressExplanationOutput(
            valuation_date=valuation_date, scenario_name=scenario_name,
            shock=shock_output(vector), base_value=result.run.base_value,
            stressed_value=result.run.stressed_value, total_pnl=result.run.pnl,
            total_pnl_percent=result.run.pnl_percent,
            position_contributions=[vars(p) for p in result.run.positions],
            tenor_contributions=[{
                "tenor_months": months(t.tenor_years), "shock_bp": t.shock_bp,
                "key_rate_dv01": t.key_rate_dv01, "pnl": t.pnl,
                "contribution_percent": t.contribution_percent,
                "attributable": t.attributable} for t in result.tenors],
            bucket_contributions=[vars(b) for b in result.buckets],
            tenor_explained_pnl=result.tenor_explained_pnl,
            tenor_residual_pnl=result.tenor_residual_pnl,
            largest_position=vars(worst_position) if worst_position else None,
            largest_tenor=({"tenor_months": months(worst_tenor.tenor_years),
                            "shock_bp": worst_tenor.shock_bp, "pnl": worst_tenor.pnl}
                           if worst_tenor else None),
            concentration={"positions": vars(result.position_concentration),
                           "tenors": vars(result.tenor_concentration)},
            facts_only_note=(
                "Quantitative facts only. This tool has no language model and "
                "produces no narrative; the sum of position contributions equals "
                "the total P&L exactly, and the tenor residual is stated rather "
                "than absorbed."),
            warnings=list(result.warnings),
            reproducibility=repro(portfolio, par_curve, {
                "shocks_bp": shocks_bp_by_tenor_months,
                "attribution_method": attribution_method}),
            data_classification=portfolio.data_classification,
            interpretation=STRESS_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Stress the part of the curve the book is actually most exposed to, "
        "chosen by measurement rather than assumption: the tenors carrying the "
        "largest absolute key-rate DV01. Answers 'what if my biggest "
        "concentration moves against me' without anyone having to decide first "
        "where the concentration is."
    ))
    def run_concentration_stress_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        tenor_count: int = Field(
            default=3, ge=1,
            description="How many of the most sensitive curve nodes to shock."),
        shock_bp: float = Field(default=100.0),
        top_n: int = Field(default=5, ge=1),
    ) -> StressRunOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        selected = most_sensitive_tenors(book, par, tenor_count)
        tenors = [t for t, _ in selected]
        vector = key_rate_shock(
            par, tenors, shock_bp,
            name=(f"Concentration stress: {shock_bp:+.0f}bp at the "
                  f"{tenor_count} largest key-rate exposures "
                  f"({', '.join(f'{t:g}y' for t in sorted(tenors))})"))
        try:
            result = attribute_stress(book, par, vector, "first_order")
        except CurveError as exc:
            raise EngineError(
                "INVALID_CURVE",
                f"shocking the {tenor_count} most sensitive nodes by "
                f"{shock_bp:+.0f}bp leaves the curve arbitrage-inconsistent: "
                f"{exc}",
                category="NUMERICAL",
                suggested_action=(
                    "Use a smaller shock, or widen tenor_count so the shocked "
                    "nodes are adjacent and the curve keeps its shape."),
            ) from exc
        output = _stress_output(result, portfolio, valuation_date, par_curve, {
            "tenor_count": tenor_count, "shock_bp": shock_bp}, top_n)
        return output.model_copy(update={"warnings": output.warnings + [
            "Shocked tenors were selected by measured key-rate DV01: "
            + ", ".join(f"{t:g}y (KRDV01 {v:,.0f})" for t, v in selected)]})

    @server.tool(annotations=DETERMINISTIC, description=(
        "Run one scenario shape at every project-defined severity - MILD 25bp, "
        "MODERATE 100bp, SEVERE 200bp, EXTREME 300bp - and return the ranked "
        "results with each shock vector. The labels are project conventions, "
        "not a regulatory classification: no supervisor prescribes them, and "
        "the result says so."
    ))
    def run_scenario_severity_pack_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        template: Literal[
            "PARALLEL_UP", "PARALLEL_DOWN", "BEAR_STEEPENER", "BULL_STEEPENER",
            "BEAR_FLATTENER", "BULL_FLATTENER", "BELLY_SELLOFF", "BELLY_RALLY",
            "WINGS_SELLOFF", "WINGS_RALLY"] = "BEAR_STEEPENER",
        severities: list[SeverityLabel] | None = None,
        interpolation: Interpolation = "linear_years",
    ) -> SeverityPackOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        vectors = severity_pack(par, template, interpolation, severities)
        rows = []
        for vector in vectors:
            try:
                run = run_shock(book, par, vector)
            except CurveError as exc:
                rows.append({"scenario_name": vector.scenario_name,
                             "severity_bp": vector.severity_bp,
                             "failed_reason": str(exc)})
                continue
            rows.append({
                "scenario_name": vector.scenario_name,
                "severity_label": vector.parameters.get("severity_label"),
                "severity_bp": vector.severity_bp,
                "stressed_value": run.stressed_value,
                "pnl": run.pnl, "pnl_percent": run.pnl_percent,
                "largest_position_contributor": (
                    run.worst_position().instrument_id if run.worst_position() else None),
                "shock": shock_output(vector).model_dump(mode="json"),
            })
        return SeverityPackOutput(
            valuation_date=valuation_date, template=template.upper(),
            base_value=book.value_under(par), severity_note=SEVERITY_NOTE,
            scenarios=sorted(rows, key=lambda r: r.get("pnl", float("inf"))),
            reproducibility=repro(portfolio, par_curve, {
                "template": template, "severities": severities,
                "severity_bp": dict(SEVERITY_BP), "interpolation": interpolation}),
            data_classification=portfolio.data_classification,
            interpretation=STRESS_NOTE,
        )
