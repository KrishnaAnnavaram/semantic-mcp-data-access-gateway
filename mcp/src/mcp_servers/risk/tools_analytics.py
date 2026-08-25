"""Valuation, curve and sensitivity tools.

The protocol wrapper for `bond_analytics`, `curve_analytics`, `sensitivities`,
`carry_roll` and `contributions`. Nothing is computed here: each function
validates typed input, calls one deterministic module, and shapes the answer.

The tools are grouped by the question they answer rather than by the arithmetic
they perform. `compute_bond_analytics_tool` returns yield, both durations,
convexity, the clean/dirty split and the approximation error in one call,
because those are what a reader wants together - and because splitting them into
`calculate_macaulay_duration`, `calculate_modified_duration` and
`calculate_convexity` would produce three round trips, three chances to pass a
different bump size, and no reconciliation between them.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import Field

from .bond_analytics import (
    analyse_bond,
    approximate_price_change,
    portfolio_rollup,
)
from .carry_roll import compute_carry_roll
from .contracts import (
    DETERMINISTIC,
    MODEL_VALUE_NOTE,
    CurveHistoryInput,
    ParCurveInput,
    PortfolioInput,
    ResultBase,
    history_arrays,
    months,
    repro,
    to_book,
    to_par_curve,
    to_positions,
    years,
)
from .contributions import measure_contributions, with_marginals
from .curve_analytics import analyse_curve
from .manifest import sha256_of
from .revaluation import run_scenarios
from .sensitivities import compute_rate_sensitivities
from .volatility import compute_rate_volatility, observed_changes_bp

TIME_BASIS = (
    "ACT/ACT ICMA quasi-coupon periods, the same basis the bootstrap uses"
)

CURVE_ANALYTICS_NOTE = (
    "Par yields are what Treasury publishes; zero rates, discount factors and "
    "forwards here are derived from the bootstrapped curve and are model-"
    "implied. Spreads are long-tenor minus short-tenor and butterflies are "
    "2 x belly - short - long, both in basis points."
)

CONTRIBUTION_NOTE = (
    "Component VaR and component ES are exact Euler decompositions under "
    "historical simulation: they sum to the portfolio measure because they come "
    "from the same scenario set. Incremental figures answer a different question "
    "- what dropping the position would do - and do not sum to anything."
)


class BondAnalyticsOutput(ResultBase):
    instruments: list[dict[str, Any]]
    portfolio: dict[str, float]
    approximations: list[dict[str, Any]]
    conventions: dict[str, str]


class CarryRollOutput(ResultBase):
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
    positions: list[dict[str, Any]]
    method: str


class CurveAnalyticsOutput(ResultBase):
    tenor_points: list[dict[str, Any]]
    forward_rates: list[dict[str, float]]
    spreads: list[dict[str, Any]]
    butterflies: list[dict[str, Any]]
    inversion: dict[str, Any]
    shape: dict[str, Any]
    conventions: dict[str, str]


class RateVolatilityOutput(ResultBase):
    horizon_days: int
    change_count: int
    per_tenor: list[dict[str, Any]]
    covariance_bp2: list[list[float]]
    correlation: list[list[float]]
    covariance_is_positive_semidefinite: bool
    highest_volatility_window: dict[str, Any] | None
    calmest_window: dict[str, Any] | None
    method: str


class RateSensitivitiesOutput(ResultBase):
    base_value: float
    bump_bp: float
    dv01: float
    dollar_duration: float
    effective_duration_years: float
    effective_convexity: float
    effective_bump_bp: float
    positions: list[dict[str, Any]]
    key_rate_dv01: list[dict[str, Any]]
    maturity_buckets: list[dict[str, Any]]
    concentration: dict[str, Any]
    reconciliation: dict[str, Any]


class RiskContributionsOutput(ResultBase):
    measure: str
    confidence_level: float
    horizon_days: int
    portfolio_measure: float
    scenario_count: int
    tail_scenario_count: int
    positions: list[dict[str, Any]]
    reconciliation_difference: float


def register(server: Any) -> None:

    @server.tool(annotations=DETERMINISTIC, description=(
        "Full analytics for each bond in a portfolio: dirty and clean price, "
        "accrued interest, yield to maturity, current yield, Macaulay and "
        "modified duration, dollar duration, convexity, and effective duration "
        "and convexity by full revaluation. Also returns the duration-only and "
        "duration-plus-convexity price approximations against the actual "
        "revalued P&L at the requested shocks, so the approximation error is "
        "visible rather than assumed. Clean price plus accrued equals dirty "
        "price exactly. A matured instrument is refused, not reported as zero."
    ))
    def compute_bond_analytics_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        effective_bump_bp: float = Field(
            default=25.0, gt=0,
            description="Parallel bump for the central-difference effective "
                        "duration and convexity."),
        approximation_shocks_bp: list[float] = Field(
            default_factory=lambda: [-100.0, -50.0, 50.0, 100.0, 300.0],
            description="Shocks at which to compare the duration and "
                        "duration+convexity approximations with full revaluation."),
    ) -> BondAnalyticsOutput:
        par = to_par_curve(par_curve)
        positions = to_positions(portfolio)
        analytics = [
            analyse_bond(p.bond, valuation_date, par, p.face_notional, effective_bump_bp)
            for p in positions
        ]
        approximations = [
            {
                "instrument_id": a.instrument_id,
                **{
                    k: v for k, v in vars(
                        approximate_price_change(a, p.bond, valuation_date, par, shock)
                    ).items()
                },
            }
            for a, p in zip(analytics, positions)
            for shock in approximation_shocks_bp
        ]
        return BondAnalyticsOutput(
            valuation_date=valuation_date,
            instruments=[{
                "instrument_id": a.instrument_id,
                "face_notional": a.face_notional,
                "cash_flow_count": a.cash_flow_count,
                "settlement_fraction_of_period": a.settlement_in_period,
                "present_value": a.present_value,
                "accrued_interest": a.accrued_interest,
                "clean_value": a.clean_value,
                "dirty_price_per_100": a.dirty_price_per_100,
                "clean_price_per_100": a.clean_price_per_100,
                "accrued_per_100": a.accrued_per_100,
                "ytm_percent": a.ytm_percent,
                "ytm_converged": a.ytm_converged,
                "ytm_iterations": a.ytm_iterations,
                "current_yield_percent": a.current_yield_percent,
                "macaulay_duration_years": a.macaulay_duration_years,
                "modified_duration_years": a.modified_duration_years,
                "dollar_duration": a.dollar_duration,
                "analytic_dv01": a.analytic_dv01,
                "convexity": a.convexity,
                "effective_duration_years": a.effective_duration_years,
                "effective_convexity": a.effective_convexity,
                "effective_bump_bp": a.effective_bump_bp,
            } for a in analytics],
            portfolio=portfolio_rollup(analytics),
            approximations=approximations,
            conventions={
                "time_basis": TIME_BASIS,
                "duration_unit": "years",
                "convexity_unit": "years squared",
                "price_approximation": "dP/P = -D_mod * dy + 0.5 * C * dy^2, dy in decimal",
                "identity": "clean price + accrued interest = dirty price",
                "yield_vs_curve": (
                    "Macaulay, modified duration and convexity come from the "
                    "bond's own yield to maturity; effective duration and "
                    "convexity come from bumping the par curve and repricing. "
                    "They are different measures and are not expected to agree."),
            },
            reproducibility=repro(portfolio, par_curve, {
                "effective_bump_bp": effective_bump_bp,
                "approximation_shocks_bp": approximation_shocks_bp}),
            data_classification=portfolio.data_classification,
            interpretation=MODEL_VALUE_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Carry and roll-down over a holding period, assuming the curve does not "
        "move. Carry is the horizon value on the forward curve plus coupons "
        "received, less today's value - what holding the position earns if the "
        "market delivers what it already promises. Roll-down is the extra from "
        "ageing down a sloped curve, and is zero on a flat one. The two are "
        "reported separately because on a steep curve roll can be the larger "
        "half, and a desk quoting only carry is quoting the smaller number."
    ))
    def compute_carry_roll_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        horizon_date: dt.date = Field(
            description="End of the holding period. Must be after the valuation date."),
    ) -> CarryRollOutput:
        result = compute_carry_roll(
            to_positions(portfolio), valuation_date, horizon_date,
            to_par_curve(par_curve))
        return CarryRollOutput(
            valuation_date=valuation_date, horizon_date=result.horizon_date,
            horizon_days=result.horizon_days, start_value=result.start_value,
            forward_value=result.forward_value, static_value=result.static_value,
            cash_received=result.cash_received, carry=result.carry,
            roll_down=result.roll_down,
            total_carry_and_roll=result.total_carry_and_roll,
            annualised_carry_and_roll_percent=result.annualised_carry_and_roll_percent,
            positions=[vars(p) for p in result.positions],
            method=result.method,
            warnings=(["The curve is flat, so roll-down is zero by construction."]
                      if result.curve_is_flat else []),
            reproducibility=repro(portfolio, par_curve,
                                  {"horizon_date": horizon_date.isoformat()}),
            data_classification=portfolio.data_classification,
            interpretation=(
                "Expected P&L from the passage of time alone, under an unchanged "
                "curve. It is not a forecast: it is what the position earns if "
                "nothing happens, and the market rarely obliges."),
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Curve analytics from a bootstrapped par curve: par yield, discount "
        "factor and zero rate (continuous and semiannual) at each requested "
        "tenor, implied forward rates, the standard slope spreads (2s10s, "
        "5s30s and friends), butterflies, inversion diagnostics and a "
        "level/slope/curvature summary. Spread sign is long-tenor minus "
        "short-tenor, so a negative 2s10s is an inversion. A tenor outside the "
        "curve's range is refused unless extrapolation is explicitly allowed, "
        "and then it is listed in warnings."
    ))
    def compute_curve_analytics_tool(
        par_curve: ParCurveInput,
        tenors_months: list[float] | None = Field(
            default=None,
            description="Tenors to report. Defaults to the curve's own nodes."),
        forward_intervals_months: list[list[float]] | None = Field(
            default=None,
            description="Forward intervals as [start_months, end_months] pairs. "
                        "Defaults to consecutive nodes plus 5y5y."),
        spread_names: list[str] | None = Field(
            default=None,
            description="Named spreads to report, e.g. ['2s10s', '5s30s']. "
                        "Defaults to every standard spread the curve supports."),
        butterfly_names: list[str] | None = Field(
            default=None,
            description="Named butterflies, e.g. ['2s10s30s']."),
        allow_extrapolation: bool = False,
    ) -> CurveAnalyticsOutput:
        par = to_par_curve(par_curve)
        intervals = ([(years(a), years(b)) for a, b in forward_intervals_months]
                     if forward_intervals_months else None)
        result = analyse_curve(
            par,
            tenors_years=[years(t) for t in tenors_months] if tenors_months else None,
            forward_intervals=intervals,
            spread_names=spread_names, butterfly_names=butterfly_names,
            allow_extrapolation=allow_extrapolation)
        return CurveAnalyticsOutput(
            valuation_date=par_curve.observation_date,
            tenor_points=[{
                "tenor_months": months(p.tenor_years),
                "par_yield_percent": p.par_yield_percent,
                "discount_factor": p.discount_factor,
                "zero_rate_continuous_percent": p.zero_rate_continuous_percent,
                "zero_rate_semiannual_percent": p.zero_rate_semiannual_percent,
                "is_curve_node": p.is_node,
                "is_extrapolated": p.is_extrapolated,
            } for p in result.tenor_points],
            forward_rates=[{
                "start_months": months(f.start_years),
                "end_months": months(f.end_years),
                "forward_continuous_percent": f.forward_continuous_percent,
                "forward_semiannual_percent": f.forward_semiannual_percent,
            } for f in result.forwards],
            spreads=[{
                "name": s.name,
                "short_tenor_months": months(s.short_tenor_years),
                "long_tenor_months": months(s.long_tenor_years),
                "short_yield_percent": s.short_yield_percent,
                "long_yield_percent": s.long_yield_percent,
                "spread_bp": s.spread_bp,
            } for s in result.spreads],
            butterflies=[{
                "name": b.name,
                "short_tenor_months": months(b.short_tenor_years),
                "belly_tenor_months": months(b.belly_tenor_years),
                "long_tenor_months": months(b.long_tenor_years),
                "butterfly_bp": b.butterfly_bp,
            } for b in result.butterflies],
            inversion={
                "is_inverted_2s10s": result.inversion.is_inverted_2s10s,
                "inverted_segment_count": result.inversion.inverted_segment_count,
                "total_segment_count": result.inversion.total_segment_count,
                "deepest_inversion_bp": result.inversion.deepest_inversion_bp,
                "deepest_inversion_segment_months": (
                    [months(t) for t in result.inversion.deepest_inversion_segment]
                    if result.inversion.deepest_inversion_segment else None),
                "first_inverted_segment_months": (
                    [months(t) for t in result.inversion.first_inverted_segment]
                    if result.inversion.first_inverted_segment else None),
            },
            shape={
                "level_percent": result.shape.level_percent,
                "slope_bp": result.shape.slope_bp,
                "curvature_bp": result.shape.curvature_bp,
                "steepest_segment_bp_per_year": result.shape.steepest_segment_bp_per_year,
                "steepest_segment_months": (
                    [months(t) for t in result.shape.steepest_segment]
                    if result.shape.steepest_segment else None),
            },
            conventions={
                "spread": "long-tenor yield minus short-tenor yield, in basis points",
                "butterfly": "2 x belly - short wing - long wing, in basis points",
                "forward": "continuously compounded from the log discount ratio; "
                           "the semiannual equivalent is quoted alongside",
                "zero_rate": "derived from the bootstrapped discount curve, not "
                             "from the par yields directly",
            },
            warnings=list(result.warnings),
            reproducibility=repro(None, par_curve, {
                "tenors_months": tenors_months,
                "forward_intervals_months": forward_intervals_months,
                "allow_extrapolation": allow_extrapolation}),
            data_classification="REAL_MARKET_DATA",
            interpretation=CURVE_ANALYTICS_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Rate volatility from an observed curve history: per-tenor standard "
        "deviation of basis-point changes, annualised, with 20/60/250-day "
        "rolling windows, plus the covariance and correlation matrices and the "
        "most and least volatile windows in the sample. This is realised rate "
        "volatility measured from published yields - it is not option-implied "
        "volatility, of which this system has none. Changes are absolute in "
        "basis points, never proportional, because a proportional change against "
        "a front end that genuinely printed 0.00% is undefined."
    ))
    def compute_rate_volatility_tool(
        history: CurveHistoryInput,
        horizon_days: int = Field(default=1, ge=1),
        rolling_windows_days: list[int] = Field(default_factory=lambda: [20, 60, 250]),
        regime_window_days: int = Field(default=60, ge=2),
    ) -> RateVolatilityOutput:
        tenors, rates = history_arrays(history)
        result = compute_rate_volatility(
            tenors, rates, horizon_days, rolling_windows_days, regime_window_days)

        def window(regime: Any) -> dict[str, Any] | None:
            if regime is None:
                return None
            out = {
                "start_index": regime.start_index, "end_index": regime.end_index,
                "window_days": regime.window_days,
                "average_stdev_bp": regime.average_stdev_bp,
                "ratio_to_full_sample": regime.ratio_to_full_sample,
            }
            if history.dates:
                offset = horizon_days
                out["start_date"] = history.dates[
                    min(regime.start_index + offset, len(history.dates) - 1)].isoformat()
                out["end_date"] = history.dates[
                    min(regime.end_index + offset, len(history.dates) - 1)].isoformat()
            return out

        return RateVolatilityOutput(
            valuation_date=(history.dates[-1] if history.dates else dt.date.today()),
            horizon_days=result.horizon_days, change_count=result.change_count,
            per_tenor=[{
                "tenor_months": months(t.tenor_years),
                "observations": t.observations,
                "mean_change_bp": t.mean_change_bp,
                "stdev_bp": t.stdev_bp,
                "annualised_stdev_bp": t.annualised_stdev_bp,
                "min_change_bp": t.min_change_bp,
                "max_change_bp": t.max_change_bp,
                **{k: v for k, v in t.rolling.items()},
            } for t in result.per_tenor],
            covariance_bp2=result.covariance_bp2,
            correlation=result.correlation,
            covariance_is_positive_semidefinite=result.covariance_is_psd,
            highest_volatility_window=window(result.highest_volatility_window),
            calmest_window=window(result.calmest_window),
            method=result.method,
            reproducibility=repro(None, None, {
                "history_sha256": sha256_of(history.rates_percent),
                "horizon_days": horizon_days,
                "rolling_windows_days": rolling_windows_days}),
            data_classification="REAL_MARKET_DATA",
            interpretation=(
                "Realised volatility of published par yields, in basis points. "
                "Not option-implied volatility - there is no option in this "
                "system and the two must never share a heading."),
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "The whole rate-sensitivity picture in one call: portfolio and "
        "per-position DV01, key-rate DV01 at every curve node with its "
        "per-position split, maturity-bucket DV01, effective duration and "
        "convexity, dollar duration, percentage risk shares and DV01 "
        "concentration. Includes an explicit reconciliation block: position "
        "DV01s sum to the portfolio DV01 exactly, while key-rate DV01s only "
        "approximately do, and the difference is reported rather than "
        "distributed away."
    ))
    def compute_rate_sensitivities_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        bump_bp: float = Field(default=1.0, description="DV01 bump size."),
        effective_bump_bp: float = Field(
            default=25.0, gt=0,
            description="Larger parallel bump for effective duration and convexity."),
        key_tenors_months: list[float] | None = Field(
            default=None,
            description="Key-rate tenors. Must be curve nodes. Defaults to all nodes."),
    ) -> RateSensitivitiesOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        result = compute_rate_sensitivities(
            book, par, bump_bp, effective_bump_bp,
            [years(t) for t in key_tenors_months] if key_tenors_months else None)
        return RateSensitivitiesOutput(
            valuation_date=valuation_date, base_value=result.base_value,
            bump_bp=result.bump_bp, dv01=result.dv01,
            dollar_duration=result.dollar_duration,
            effective_duration_years=result.effective_duration_years,
            effective_convexity=result.effective_convexity,
            effective_bump_bp=result.effective_bump_bp,
            positions=[vars(p) for p in result.positions],
            key_rate_dv01=[{
                "tenor_months": months(k.tenor_years),
                "key_rate_dv01": k.key_rate_dv01,
                "share_percent": k.share_percent,
                "per_position": [{"instrument_id": i, "key_rate_dv01": v}
                                 for i, v in k.per_position],
            } for k in result.key_rates],
            maturity_buckets=[vars(b) for b in result.buckets],
            concentration={
                "position_dv01": vars(result.dv01_concentration),
                "key_rate_dv01": vars(result.key_rate_concentration),
            },
            reconciliation=vars(result.reconciliation),
            reproducibility=repro(portfolio, par_curve, {
                "bump_bp": bump_bp, "effective_bump_bp": effective_bump_bp,
                "key_tenors_months": key_tenors_months}),
            data_classification=portfolio.data_classification,
            interpretation=MODEL_VALUE_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Component, marginal and incremental risk contributions per position, "
        "for historical VaR or Expected Shortfall. Component figures are exact "
        "Euler decompositions - under nearest-rank historical simulation the VaR "
        "is one scenario's loss and the ES is a mean over tail scenarios, so the "
        "positions' losses in those same scenarios sum to the portfolio measure. "
        "Incremental figures re-run the quantile with the position removed and "
        "answer a different question, so they do not sum to anything."
    ))
    def compute_risk_contributions_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        history: CurveHistoryInput,
        risk_measure: Literal["var", "es"] = "var",
        confidence_level: float = Field(default=0.99, ge=0.5, lt=1.0),
        horizon_days: int = Field(default=1, ge=1),
        include_incremental: bool = True,
    ) -> RiskContributionsOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        tenors, rates = history_arrays(history)
        live = set(par.tenors_years)
        columns = [j for j, t in enumerate(tenors) if t in live]
        used = [tenors[j] for j in columns]
        changes = observed_changes_bp(rates, horizon_days)
        vectors = [{used[i]: row[columns[i]] for i in range(len(used))}
                   for row in changes]
        scenarios = run_scenarios(book, par, vectors)
        contributions = with_marginals(
            measure_contributions(scenarios, confidence_level, risk_measure,
                                  include_incremental),
            book.notionals())
        return RiskContributionsOutput(
            valuation_date=valuation_date, measure=contributions.measure,
            confidence_level=contributions.confidence_level,
            horizon_days=horizon_days,
            portfolio_measure=contributions.portfolio_measure,
            scenario_count=contributions.scenario_count,
            tail_scenario_count=contributions.tail_scenario_count,
            positions=[vars(p) for p in contributions.positions],
            reconciliation_difference=contributions.reconciliation_difference,
            reproducibility=repro(portfolio, par_curve, {
                "risk_measure": risk_measure, "confidence_level": confidence_level,
                "horizon_days": horizon_days,
                "scenario_set_sha256": sha256_of(history.rates_percent)}),
            data_classification=portfolio.data_classification,
            interpretation=CONTRIBUTION_NOTE,
        )
