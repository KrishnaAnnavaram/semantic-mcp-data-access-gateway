"""Distribution risk, backtesting and attribution tools.

The protocol wrapper for `parametric`, `monte_carlo`, `backtesting` and
`pnl_attribution`.

`compute_historical_risk_tool` in `server.py` is unchanged and remains the
historical-simulation measure. Everything here is a **different methodology**,
never a variant of it, and each carries its own manifest version so a comparison
table cannot accidentally present two of them as the same measure computed
twice.

The distinction that matters most: historical h-day risk uses observed h-day
moves and never scales a one-day figure by the square root of h. The parametric
path may scale by sqrt(h) *if asked*, because its own assumptions license it -
and the result says which path ran. Blurring that line is how a 10-day number
ends up 2.7 times smaller than the moves the market actually delivered.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import Field

from .backtesting import PnlKind, backtest_var
from .contracts import (
    DETERMINISTIC,
    SIMULATION_NOTE,
    VAR_NOTE,
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
)
from .errors import EngineError
from .manifest import sha256_of
from .monte_carlo import (
    DEFAULT_SCENARIO_COUNT,
    TailMethod,
    compute_monte_carlo_risk,
    correlation_stress_covariance,
    run_extreme_tail_simulation,
)
from .parametric import HorizonMethod, compute_parametric_risk
from .pnl_attribution import compute_pnl_attribution
from .revaluation import run_scenarios
from .risk import nearest_rank_quantile
from .volatility import covariance_matrix, observed_changes_bp

PARAMETRIC_NOTE = (
    "Delta-normal VaR and Expected Shortfall. The portfolio is represented by "
    "its key-rate DV01 vector, which is a LINEAR approximation with no "
    "convexity in it, and the rate changes are assumed multivariate normal. "
    "Both assumptions are stated in the result. Where this figure sits well "
    "below the historical one, the loss distribution has a fatter tail than a "
    "normal - and that is a finding, not a discrepancy to reconcile."
)

BACKTEST_NOTE = (
    "A coverage test on a VaR forecast series. An exception is a loss strictly "
    "greater than the forecast; a loss exactly equal to it is not. The kind of "
    "P&L used is reported and is not interchangeable - a hypothetical series "
    "labelled as actual flatters the model, because intraday risk reduction "
    "removes exceptions the model should have been charged for."
)

ATTRIBUTION_NOTE = (
    "P&L split into carry, roll-down, rate move and position change, each by "
    "full revaluation. The top-level residual should be at machine precision - "
    "a non-zero value means the decomposition disagrees with itself. The "
    "informative residual is rate_unexplained: the first-order tenor split's "
    "shortfall against the rate effect, which is the book's convexity and grows "
    "with the size of the move."
)


class ParametricRiskOutput(ResultBase):
    base_value: float
    confidence_level: float
    horizon_days: int
    horizon_method: str
    z_score: float
    portfolio_volatility: float
    mean_pnl: float
    var: float
    expected_shortfall: float
    observations_used: int
    factors: list[dict[str, Any]]
    covariance_is_positive_semidefinite: bool
    smallest_eigenvalue: float
    var_reconciliation_difference: float
    distribution: str
    method: str


class MonteCarloOutput(ResultBase):
    base_value: float
    confidence_level: float
    horizon_days: int
    scenario_count: int
    scenarios_priced: int
    random_seed: int
    method: str
    distribution: str
    var: float
    expected_shortfall: float
    mean_pnl: float
    stdev_pnl: float
    worst_pnl: float
    best_pnl: float
    percentiles_pnl: dict[str, float]
    tail_scenario_count: int
    covariance_repaired: bool
    covariance_diagnostics: dict[str, float]
    rejected_scenarios: int
    observations_used: int
    tenors_months: list[float]


class RiskMethodComparisonOutput(ResultBase):
    base_value: float
    confidence_level: float
    horizon_days: int
    methods: list[dict[str, Any]]
    spread_var: float
    spread_expected_shortfall: float
    widest_method: str
    narrowest_method: str
    comparison_note: str


class BacktestOutput(ResultBase):
    observations: int
    confidence_level: float
    pnl_kind: str
    exceptions: int
    exception_rate: float
    expected_exceptions: float
    expected_exception_rate: float
    exception_dates: list[str]
    exception_detail: list[dict[str, Any]]
    longest_exception_run: int
    exception_clusters: int
    mean_excess_loss: float
    worst_excess_loss: float
    kupiec_result: dict[str, Any]
    independence_result: dict[str, Any]
    conditional_coverage_result: dict[str, Any]
    basel_traffic_light: str | None
    basel_traffic_light_applicable: bool
    exception_rule: str
    method: str


class PnlAttributionOutput(ResultBase):
    start_date: dt.date
    end_date: dt.date
    days: int
    start_value: float
    end_value: float
    cash_received: float
    total_pnl: float
    carry: float
    roll_down: float
    rate_move: float
    position_change: float | None
    residual: float
    explained_pnl: float
    unexplained_percent: float
    tenor_effects: list[dict[str, Any]]
    bucket_effects: list[dict[str, Any]]
    rate_explained_by_tenor: float
    rate_unexplained: float
    rate_unexplained_percent: float
    positions: list[dict[str, Any]]
    ordering: str
    residual_note: str
    method: str


def _test_dict(result: Any) -> dict[str, Any]:
    return {
        "name": result.name, "statistic": result.statistic,
        "degrees_of_freedom": result.degrees_of_freedom,
        "p_value": result.p_value,
        "rejected_at_5_percent": result.rejected_at_5_percent,
        "computable": result.computable, "note": result.note,
    }


def _monte_carlo_output(
    result: Any, portfolio: PortfolioInput, valuation_date: dt.date,
    par_curve: ParCurveInput, extra: dict[str, Any],
) -> MonteCarloOutput:
    warnings = []
    if result.rejection_note:
        warnings.append(result.rejection_note)
    if result.covariance_repaired:
        warnings.append(
            "The estimated covariance was not positive semidefinite and was "
            "repaired by eigenvalue clipping before factorisation. The "
            "adjustment is in covariance_diagnostics; a large one means the "
            "estimation window is degenerate and the result should not be used.")
    return MonteCarloOutput(
        valuation_date=valuation_date, base_value=result.base_value,
        confidence_level=result.confidence_level, horizon_days=result.horizon_days,
        scenario_count=result.scenario_count,
        scenarios_priced=result.scenarios_priced, random_seed=result.random_seed,
        method=result.method, distribution=result.distribution, var=result.var,
        expected_shortfall=result.expected_shortfall, mean_pnl=result.mean_pnl,
        stdev_pnl=result.stdev_pnl, worst_pnl=result.worst_pnl,
        best_pnl=result.best_pnl, percentiles_pnl=result.percentiles_pnl,
        tail_scenario_count=result.tail_scenario_count,
        covariance_repaired=result.covariance_repaired,
        covariance_diagnostics=result.covariance_diagnostics,
        rejected_scenarios=result.rejected_scenarios,
        observations_used=result.observations_used,
        tenors_months=[months(t) for t in result.tenors_years],
        warnings=warnings,
        reproducibility=repro(portfolio, par_curve, extra),
        data_classification=portfolio.data_classification,
        interpretation=SIMULATION_NOTE,
    )


def register(server: Any) -> None:

    @server.tool(annotations=DETERMINISTIC, description=(
        "Parametric (delta-normal) VaR and Expected Shortfall. The portfolio is "
        "represented by its key-rate DV01 exposure vector and the rate changes "
        "by their sample covariance, assumed multivariate normal; ES uses the "
        "normal closed form. Component and marginal VaR per curve tenor are "
        "exact Euler decompositions and sum to the VaR identically. Horizon "
        "method 'observed' estimates from actual h-day changes; 'sqrt_time' "
        "estimates from one-day changes and scales - legitimate here because "
        "the model already assumes independent normal increments, and forbidden "
        "on the historical path where nothing licenses it."
    ))
    def compute_parametric_risk_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        history: CurveHistoryInput,
        confidence_level: float = Field(default=0.99, ge=0.5, lt=1.0),
        horizon_days: int = Field(default=1, ge=1),
        horizon_method: HorizonMethod = "observed",
        include_mean: bool = Field(
            default=False,
            description="Include the estimated drift. Off by default: a drift "
                        "estimated from a year of data is mostly noise and it "
                        "systematically reduces the reported loss."),
    ) -> ParametricRiskOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        tenors, rates = history_arrays(history)
        result = compute_parametric_risk(
            book, par, tenors, rates, confidence_level, horizon_days,
            horizon_method, include_mean)
        return ParametricRiskOutput(
            valuation_date=valuation_date, base_value=result.base_value,
            confidence_level=result.confidence_level,
            horizon_days=result.horizon_days, horizon_method=result.horizon_method,
            z_score=result.z_score,
            portfolio_volatility=result.portfolio_volatility,
            mean_pnl=result.mean_pnl, var=result.var,
            expected_shortfall=result.expected_shortfall,
            observations_used=result.observations_used,
            factors=[{
                "tenor_months": months(f.tenor_years),
                "key_rate_dv01": f.key_rate_dv01,
                "exposure_per_bp": f.exposure_per_bp,
                "volatility_bp": f.volatility_bp,
                "marginal_var": f.marginal_var,
                "component_var": f.component_var,
                "component_percent": f.component_percent,
            } for f in result.factors],
            covariance_is_positive_semidefinite=result.covariance_is_psd,
            smallest_eigenvalue=result.smallest_eigenvalue,
            var_reconciliation_difference=result.var_reconciliation_difference,
            distribution=result.distribution, method=result.method,
            warnings=([] if result.covariance_is_psd else [
                ("The estimated covariance is not positive semidefinite; the "
                "portfolio variance is still non-negative here, but the "
                "estimation window is degenerate and should be widened.")]),
            reproducibility=repro(portfolio, par_curve, {
                "confidence_level": confidence_level, "horizon_days": horizon_days,
                "horizon_method": horizon_method, "include_mean": include_mean,
                "history_sha256": sha256_of(history.rates_percent)}),
            data_classification=portfolio.data_classification,
            interpretation=PARAMETRIC_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Monte Carlo VaR and Expected Shortfall with full revaluation on every "
        "path, so the book's convexity is priced rather than approximated. "
        "Correlated shocks are drawn from the estimated covariance by Cholesky "
        "(or eigenvalue-clipped factorisation where the matrix is singular, "
        "reported either way) and by explicit Box-Muller over a seeded uniform "
        "stream. Fully reproducible: the same inputs, the same manifest and the "
        "same seed give the same numbers, and the seed travels into the run "
        "fingerprint."
    ))
    def compute_monte_carlo_risk_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        history: CurveHistoryInput,
        confidence_level: float = Field(default=0.99, ge=0.5, lt=1.0),
        horizon_days: int = Field(default=1, ge=1),
        scenario_count: int = Field(default=DEFAULT_SCENARIO_COUNT, ge=100, le=100_000),
        random_seed: int = Field(
            default=20260824,
            description="Required for reproducibility. Same seed, same result."),
    ) -> MonteCarloOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        tenors, rates = history_arrays(history)
        result = compute_monte_carlo_risk(
            book, par, tenors, rates, confidence_level, horizon_days,
            scenario_count, random_seed)
        return _monte_carlo_output(result, portfolio, valuation_date, par_curve, {
            "confidence_level": confidence_level, "horizon_days": horizon_days,
            "scenario_count": scenario_count, "random_seed": random_seed,
            "history_sha256": sha256_of(history.rates_percent)})

    @server.tool(annotations=DETERMINISTIC, description=(
        "A deliberately fat-tailed simulation, labelled as one. Four "
        "methodologies, each with its own manifest version so none can be "
        "mistaken for historical VaR: 'volatility_multiplier' scales every "
        "volatility (the covariance by the square of it); 'stressed_covariance' "
        "estimates from the most volatile window in the history; 'student_t' "
        "uses multivariate Student-t innovations variance-matched to the "
        "estimated covariance, so only the tail thickness changes; "
        "'empirical_bootstrap' resamples the observed change vectors with "
        "replacement and assumes no distribution at all."
    ))
    def run_extreme_tail_simulation_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        history: CurveHistoryInput,
        tail_method: TailMethod = "volatility_multiplier",
        confidence_level: float = Field(default=0.99, ge=0.5, lt=1.0),
        horizon_days: int = Field(default=1, ge=1),
        scenario_count: int = Field(default=DEFAULT_SCENARIO_COUNT, ge=100, le=100_000),
        random_seed: int = 20260824,
        volatility_multiplier: float = Field(default=2.0, gt=0),
        degrees_of_freedom: int = Field(default=5, ge=3),
        regime_window_days: int = Field(default=60, ge=2),
    ) -> MonteCarloOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        tenors, rates = history_arrays(history)
        result = run_extreme_tail_simulation(
            book, par, tenors, rates, tail_method, confidence_level, horizon_days,
            scenario_count, random_seed, volatility_multiplier,
            degrees_of_freedom, regime_window_days)
        return _monte_carlo_output(result, portfolio, valuation_date, par_curve, {
            "tail_method": tail_method, "confidence_level": confidence_level,
            "horizon_days": horizon_days, "scenario_count": scenario_count,
            "random_seed": random_seed,
            "volatility_multiplier": volatility_multiplier,
            "degrees_of_freedom": degrees_of_freedom,
            "history_sha256": sha256_of(history.rates_percent)})

    @server.tool(annotations=DETERMINISTIC, description=(
        "Rate-volatility regime stress: find the most volatile window in the "
        "supplied history and simulate from the covariance estimated there "
        "rather than from the whole sample. Uses the observed distribution of a "
        "real turbulent period instead of a chosen multiplier, so the "
        "correlations as well as the volatilities are the stressed ones. This "
        "is rate-volatility regime stress; it involves no option-implied "
        "volatility, of which this system has none."
    ))
    def run_volatility_regime_stress_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        history: CurveHistoryInput,
        confidence_level: float = Field(default=0.99, ge=0.5, lt=1.0),
        horizon_days: int = Field(default=1, ge=1),
        regime_window_days: int = Field(default=60, ge=2),
        scenario_count: int = Field(default=DEFAULT_SCENARIO_COUNT, ge=100, le=100_000),
        random_seed: int = 20260824,
    ) -> MonteCarloOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        tenors, rates = history_arrays(history)
        result = run_extreme_tail_simulation(
            book, par, tenors, rates, "stressed_covariance", confidence_level,
            horizon_days, scenario_count, random_seed,
            regime_window_days=regime_window_days)
        return _monte_carlo_output(result, portfolio, valuation_date, par_curve, {
            "regime_window_days": regime_window_days,
            "confidence_level": confidence_level, "horizon_days": horizon_days,
            "scenario_count": scenario_count, "random_seed": random_seed,
            "history_sha256": sha256_of(history.rates_percent)})

    @server.tool(annotations=DETERMINISTIC, description=(
        "Rate correlation stress: hold every tenor's volatility at its "
        "estimated level and change only how the tenors move together, then "
        "re-simulate. Modes are 'historical', 'perfect_positive' (no "
        "diversification, an upper bound on rate VaR), 'independent' (maximal "
        "diversification), 'front_end_decorrelated' and 'custom'. Isolates the "
        "diversification assumption, which is what actually breaks in a crisis. "
        "A supplied or constructed matrix that is not positive semidefinite is "
        "repaired by eigenvalue clipping and the repair is reported - it is "
        "never used as given."
    ))
    def run_rate_correlation_stress_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        history: CurveHistoryInput,
        correlation_mode: Literal[
            "historical", "perfect_positive", "independent",
            "front_end_decorrelated", "custom"] = "perfect_positive",
        custom_correlation: list[list[float]] | None = None,
        confidence_level: float = Field(default=0.99, ge=0.5, lt=1.0),
        horizon_days: int = Field(default=1, ge=1),
        scenario_count: int = Field(default=DEFAULT_SCENARIO_COUNT, ge=100, le=100_000),
        random_seed: int = 20260824,
    ) -> MonteCarloOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        tenors, rates = history_arrays(history)
        live = set(par.tenors_years)
        columns = [j for j, t in enumerate(tenors) if t in live]
        changes = observed_changes_bp(rates, horizon_days)
        trimmed = [[row[j] for j in columns] for row in changes]
        base_cov = covariance_matrix(trimmed)
        cov, label, diagnostics = correlation_stress_covariance(
            base_cov, correlation_mode, custom_correlation)
        result = compute_monte_carlo_risk(
            book, par, tenors, rates, confidence_level, horizon_days,
            scenario_count, random_seed, covariance_override=cov,
            method_label=f"correlation_stress_{correlation_mode}_v1",
            distribution_label=(
                f"multivariate normal with the estimated volatilities and "
                f"{label}"))
        output = _monte_carlo_output(result, portfolio, valuation_date, par_curve, {
            "correlation_mode": correlation_mode,
            "custom_correlation": custom_correlation,
            "confidence_level": confidence_level, "horizon_days": horizon_days,
            "scenario_count": scenario_count, "random_seed": random_seed,
            "history_sha256": sha256_of(history.rates_percent)})
        extra = []
        if diagnostics.get("repaired"):
            extra.append(
                "The requested correlation matrix was not positive "
                "semidefinite and was projected onto the nearest one; the "
                "largest element moved by "
                f"{diagnostics.get('max_absolute_adjustment', 0.0):.6f}.")
        return output.model_copy(update={"warnings": output.warnings + extra})

    @server.tool(annotations=DETERMINISTIC, description=(
        "Run historical, parametric and Monte Carlo VaR and Expected Shortfall "
        "on the same book, the same curve, the same history and the same "
        "confidence level, and return them side by side with the spread between "
        "them. A model-validation tool: the methods are NOT expected to agree, "
        "and the pattern of disagreement is the information. Parametric far "
        "below historical means fat tails; Monte Carlo far from parametric on a "
        "linear book means the simulation is not converged."
    ))
    def compare_risk_methods_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        history: CurveHistoryInput,
        confidence_level: float = Field(default=0.99, ge=0.5, lt=1.0),
        horizon_days: int = Field(default=1, ge=1),
        scenario_count: int = Field(default=DEFAULT_SCENARIO_COUNT, ge=100, le=100_000),
        random_seed: int = 20260824,
    ) -> RiskMethodComparisonOutput:
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
        losses = scenarios.losses_sorted()
        historical_var, _ = nearest_rank_quantile(losses, confidence_level)
        historical_var = max(0.0, historical_var)
        tail = [loss for loss in losses if loss >= historical_var]
        historical_es = sum(tail) / len(tail) if tail else historical_var

        parametric = compute_parametric_risk(
            book, par, tenors, rates, confidence_level, horizon_days, "observed")
        monte = compute_monte_carlo_risk(
            book, par, tenors, rates, confidence_level, horizon_days,
            scenario_count, random_seed)

        rows = [
            {"method": "historical_simulation",
             "version": "absolute_par_shock_full_revaluation_v1",
             "var": historical_var, "expected_shortfall": historical_es,
             "scenarios": scenarios.scenario_count,
             "distribution": "the empirical distribution of observed h-day moves",
             "revaluation": "full"},
            {"method": "parametric_delta_normal", "version": parametric.method,
             "var": parametric.var, "expected_shortfall": parametric.expected_shortfall,
             "scenarios": parametric.observations_used,
             "distribution": parametric.distribution,
             "revaluation": "none - linear key-rate approximation"},
            {"method": "monte_carlo", "version": monte.method,
             "var": monte.var, "expected_shortfall": monte.expected_shortfall,
             "scenarios": monte.scenarios_priced,
             "distribution": monte.distribution, "revaluation": "full"},
        ]
        var_values = [r["var"] for r in rows]
        es_values = [r["expected_shortfall"] for r in rows]
        widest = max(rows, key=lambda r: r["var"])
        narrowest = min(rows, key=lambda r: r["var"])
        return RiskMethodComparisonOutput(
            valuation_date=valuation_date, base_value=scenarios.base_value,
            confidence_level=confidence_level, horizon_days=horizon_days,
            methods=rows,
            spread_var=max(var_values) - min(var_values),
            spread_expected_shortfall=max(es_values) - min(es_values),
            widest_method=str(widest["method"]),
            narrowest_method=str(narrowest["method"]),
            comparison_note=(
                "These are three different models, not three estimates of one "
                "number, and they are not expected to agree. Historical "
                "simulation is limited to moves that happened; parametric "
                "assumes normality and linearity; Monte Carlo assumes normality "
                "but revalues in full. Read the differences, not the average."),
            reproducibility=repro(portfolio, par_curve, {
                "confidence_level": confidence_level, "horizon_days": horizon_days,
                "scenario_count": scenario_count, "random_seed": random_seed,
                "history_sha256": sha256_of(history.rates_percent)}),
            data_classification=portfolio.data_classification,
            interpretation=VAR_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Backtest a VaR forecast series against realised P&L: exception count "
        "and rate against expectation, exception dates, clustering "
        "diagnostics, and the Kupiec unconditional-coverage, Christoffersen "
        "independence and joint conditional-coverage likelihood-ratio tests "
        "with exact chi-squared p-values. An exception is a loss STRICTLY "
        "greater than the forecast. The kind of P&L is a required label and "
        "travels with the result. Degenerate cases - no exceptions, nothing "
        "following an exception - are reported as not computable rather than "
        "as a pass."
    ))
    def backtest_var_tool(
        var_forecasts: list[float] = Field(
            default_factory=list,
            description="One VaR forecast per observation, as positive loss "
                        "thresholds."),
        realised_pnl: list[float] = Field(
            default_factory=list,
            description="The outcome for the same day. Negative is a loss."),
        confidence_level: float = Field(default=0.99, ge=0.5, lt=1.0),
        pnl_kind: PnlKind = Field(
            default="HYPOTHETICAL",
            description="ACTUAL is the desk's realised P&L including intraday "
                        "trading; HYPOTHETICAL is the start-of-day book revalued "
                        "at end-of-day prices, which is what a coverage test is "
                        "about; MODEL_REVALUATION is this engine's own repricing."),
        observation_dates: list[dt.date] | None = None,
    ) -> BacktestOutput:
        result = backtest_var(var_forecasts, realised_pnl, confidence_level,
                              pnl_kind, observation_dates)
        warnings = []
        if not result.independence.computable:
            warnings.append(
                f"Independence test not computable: {result.independence.note}")
        if not result.basel_traffic_light_applicable:
            warnings.append(
                "The Basel traffic-light zones are calibrated for 250 "
                "observations at 99%. This backtest does not meet those "
                "conditions, so no zone is reported - a colour outside them "
                "would look official and mean nothing.")
        return BacktestOutput(
            valuation_date=(observation_dates[-1] if observation_dates
                            else dt.date.today()),
            observations=result.observations,
            confidence_level=result.confidence_level, pnl_kind=result.pnl_kind,
            exceptions=result.exceptions, exception_rate=result.exception_rate,
            expected_exceptions=result.expected_exceptions,
            expected_exception_rate=result.expected_exception_rate,
            exception_dates=[d.isoformat() for d in result.exception_dates if d],
            exception_detail=[vars(e) | {"date": e.date.isoformat() if e.date else None}
                              for e in result.exception_detail],
            longest_exception_run=result.longest_exception_run,
            exception_clusters=result.exception_clusters,
            mean_excess_loss=result.mean_excess_loss,
            worst_excess_loss=result.worst_excess_loss,
            kupiec_result=_test_dict(result.kupiec),
            independence_result=_test_dict(result.independence),
            conditional_coverage_result=_test_dict(result.conditional_coverage),
            basel_traffic_light=result.basel_traffic_light,
            basel_traffic_light_applicable=result.basel_traffic_light_applicable,
            exception_rule=result.exception_rule, method=result.method,
            warnings=warnings,
            reproducibility=repro(None, None, {
                "var_forecasts_sha256": sha256_of(var_forecasts),
                "pnl_sha256": sha256_of(realised_pnl),
                "confidence_level": confidence_level, "pnl_kind": pnl_kind}),
            data_classification="SYNTHETIC_DEMO",
            interpretation=BACKTEST_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Decompose the P&L between two dates into carry, roll-down, rate move "
        "and position change, each by full revaluation, with the rate effect "
        "further split across the curve by key-rate DV01. Two residuals are "
        "reported and they mean different things: the top-level one should be "
        "at machine precision, and a non-zero value means the decomposition "
        "disagrees with itself; rate_unexplained is the first-order tenor "
        "split's shortfall, which is the book's convexity and grows with the "
        "size of the move. Neither is ever forced to zero."
    ))
    def compute_pnl_attribution_tool(
        portfolio: PortfolioInput,
        start_date: dt.date, start_curve: ParCurveInput,
        end_date: dt.date, end_curve: ParCurveInput,
        portfolio_end: PortfolioInput | None = Field(
            default=None,
            description="The end-of-period positions, if they changed. Omit and "
                        "position_change comes back null - 'nothing traded' and "
                        "'we were not told' are different claims."),
    ) -> PnlAttributionOutput:
        if end_date <= start_date:
            raise EngineError(
                "INVALID_HORIZON",
                f"the attribution period {start_date} to {end_date} runs "
                "backwards or is empty",
                category="USER_INPUT",
                suggested_action="Give an end date after the start date.")
        result = compute_pnl_attribution(
            to_positions(portfolio), start_date, to_par_curve(start_curve),
            end_date, to_par_curve(end_curve),
            to_positions(portfolio_end) if portfolio_end else None)
        return PnlAttributionOutput(
            valuation_date=end_date, start_date=result.start_date,
            end_date=result.end_date, days=result.days,
            start_value=result.start_value, end_value=result.end_value,
            cash_received=result.cash_received, total_pnl=result.total_pnl,
            carry=result.carry, roll_down=result.roll_down,
            rate_move=result.rate_move, position_change=result.position_change,
            residual=result.residual, explained_pnl=result.explained_pnl,
            unexplained_percent=result.unexplained_percent,
            tenor_effects=[{
                "tenor_months": months(e.tenor_years), "change_bp": e.change_bp,
                "key_rate_dv01": e.key_rate_dv01, "pnl": e.pnl,
                "contribution_percent": e.contribution_percent,
            } for e in result.tenor_effects],
            bucket_effects=[{"bucket": b, "pnl": v} for b, v in result.bucket_effects],
            rate_explained_by_tenor=result.rate_explained_by_tenor,
            rate_unexplained=result.rate_unexplained,
            rate_unexplained_percent=result.rate_unexplained_percent,
            positions=[vars(p) for p in result.positions],
            ordering=result.ordering, residual_note=result.residual_note,
            method=result.method,
            warnings=([] if portfolio_end else [
                ("No end-of-period positions were supplied, so position_change is "
                "null rather than zero.")]),
            reproducibility=repro(portfolio, end_curve, {
                "start_date": start_date.isoformat(),
                "start_curve": start_curve.model_dump(mode="json"),
                "end_date": end_date.isoformat(),
                "positions_changed": portfolio_end is not None}),
            data_classification=portfolio.data_classification,
            interpretation=ATTRIBUTION_NOTE,
        )
