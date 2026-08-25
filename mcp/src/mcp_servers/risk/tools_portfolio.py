"""Portfolio-level tools: concentration, limits, comparison and regulatory capital.

The protocol wrapper for `concentration`, `limits`, `portfolio_comparison` and
`regulatory.girr`.

Two rules govern this family in particular.

**Nothing stored is ever mutated.** `analyze_hypothetical_trade_tool` builds its
"after" book by appending to a copy that lives for the duration of the call. A
risk system that answers "what if I bought this" by buying it is not a risk
system, and the data server has no write path for positions anyway - this is the
belt to that braces.

**No risk policy is supplied.** Every limit, every amber threshold, is a caller
input. A threshold that appears in a report without a stated source becomes
policy by accident: quoted, then relied on, and by the time anyone asks where it
came from the answer is "the system".
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import Field

from .concentration import compute_concentration
from .contracts import (
    DETERMINISTIC,
    MODEL_VALUE_NOTE,
    REGULATORY_NOTE,
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
from .errors import EngineError
from .limits import LimitDefinition, evaluate_limits
from .portfolio_comparison import (
    analyse_hypothetical_trade,
    compare_portfolios,
    size_key_rate_hedge,
)
from .regulatory.constants import FRTB_SOURCE, RISK_CLASS_SUPPORT
from .regulatory.girr import compute_girr_capital
from .stress_scenarios import custom_shock

CONCENTRATION_NOTE = (
    "Concentration is measured on absolute magnitudes. A long and an offsetting "
    "short are two concentrations, not an absence of risk: the offset depends "
    "on the two legs continuing to move together, which is exactly what stops "
    "being true in a crisis."
)

LIMIT_NOTE = (
    "Utilisation against caller-supplied limits. This engine holds no risk "
    "policy: every limit amount and every amber threshold in this result came "
    "from the request. GREEN below amber, AMBER from the amber threshold up to "
    "but not including full utilisation, RED at or above it - a book sitting "
    "exactly on its limit has no headroom left."
)


class ConcentrationOutput(ResultBase):
    base_value: float
    top_n: int
    dimensions: list[dict[str, Any]]
    basis: str
    method: str


class LimitReportOutput(ResultBase):
    evaluations: list[dict[str, Any]]
    breach_count: int
    amber_count: int
    worst_utilisation_percent: float
    worst_metric: str | None
    all_within_limits: bool
    threshold_policy: str
    method: str


class PortfolioComparisonOutput(ResultBase):
    label_a: str
    label_b: str
    measures: list[dict[str, Any]]
    key_rate_dv01: list[dict[str, float]]
    scenario_pnl: list[dict[str, Any]]
    risk_reduction_percent: float | None
    measures_omitted: list[str]
    method: str
    note: str


class HedgeOutput(ResultBase):
    hedge_tenor_months: float
    hedge_instrument_id: str
    hedge_maturity_date: dt.date
    hedge_coupon_rate_pct: float
    hedge_notional: float
    target_key_rate_dv01: float
    pre_hedge_key_rate_dv01: float
    post_hedge_key_rate_dv01: float
    pre_hedge_portfolio_dv01: float
    post_hedge_portfolio_dv01: float
    residual_key_rate_dv01: list[dict[str, float]]
    not_advice: str


class GirrCapitalOutput(ResultBase):
    regulatory_framework: str
    source: str
    constants_version: str
    currency: str
    bucket: str
    base_value: float
    vertices: list[dict[str, Any]]
    correlation_scenarios: list[dict[str, Any]]
    delta_capital: float
    binding_scenario: str
    curvature: dict[str, Any] | None
    vega_capital: None
    total_capital: float
    total_capital_percent_of_value: float
    unsupported_risk_classes: list[str]
    unsupported_reason: str
    scope_note: str
    method: str


def register(server: Any) -> None:

    @server.tool(annotations=DETERMINISTIC, description=(
        "Where the risk is bunched up: present value, position DV01, notional, "
        "key-rate DV01 and maturity-bucket DV01 concentration, each with the "
        "largest and top-three shares, a Herfindahl index and the effective "
        "number of equally sized positions that would be this concentrated. "
        "Stress-loss and VaR/ES contribution concentration are included when a "
        "scenario or a history is supplied and omitted - not defaulted - when "
        "it is not. Measured on absolute magnitudes throughout."
    ))
    def compute_concentration_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        top_n: int = Field(default=5, ge=1),
        stress_shocks_bp_by_tenor_months: dict[str, float] | None = Field(
            default=None,
            description="Optional scenario. Adds stress-loss concentration."),
        history: CurveHistoryInput | None = Field(
            default=None,
            description="Optional curve history. Adds VaR and ES contribution "
                        "concentration."),
        confidence_level: float = Field(default=0.99, ge=0.5, lt=1.0),
        horizon_days: int = Field(default=1, ge=1),
    ) -> ConcentrationOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)

        stress_rows = None
        if stress_shocks_bp_by_tenor_months:
            from .contributions import run_shock
            vector = custom_shock(
                par, {years(float(k)): float(v)
                      for k, v in stress_shocks_bp_by_tenor_months.items()})
            run = run_shock(book, par, vector)
            stress_rows = [(p.instrument_id, p.pnl) for p in run.positions]

        var_rows = es_rows = None
        if history is not None:
            from .contributions import measure_contributions
            from .revaluation import run_scenarios
            from .volatility import observed_changes_bp
            tenors, rates = history_arrays(history)
            live = set(par.tenors_years)
            columns = [j for j, t in enumerate(tenors) if t in live]
            used = [tenors[j] for j in columns]
            changes = observed_changes_bp(rates, horizon_days)
            vectors = [{used[i]: row[columns[i]] for i in range(len(used))}
                       for row in changes]
            scenarios = run_scenarios(book, par, vectors)
            var_contributions = measure_contributions(
                scenarios, confidence_level, "var", include_incremental=False)
            es_contributions = measure_contributions(
                scenarios, confidence_level, "es", include_incremental=False)
            var_rows = [(c.instrument_id, c.component)
                        for c in var_contributions.positions]
            es_rows = [(c.instrument_id, c.component)
                       for c in es_contributions.positions]

        report = compute_concentration(book, par, top_n, stress_rows, var_rows, es_rows)
        return ConcentrationOutput(
            valuation_date=valuation_date, base_value=report.base_value,
            top_n=report.top_n,
            dimensions=[{
                "dimension": d.dimension, "unit": d.unit,
                "total_absolute": d.total_absolute, "net_total": d.net_total,
                "top_share_percent": d.concentration.top_share_percent,
                "top_three_share_percent": d.concentration.top_three_share_percent,
                "herfindahl_index": d.concentration.herfindahl_index,
                "effective_count": d.concentration.effective_count,
                "entries": [vars(e) for e in d.entries],
            } for d in report.dimensions],
            basis=report.basis, method=report.method,
            warnings=([] if history is not None else [
                ("No history was supplied, so VaR and ES contribution "
                "concentration are omitted rather than reported as zero.")]),
            reproducibility=repro(portfolio, par_curve, {
                "top_n": top_n,
                "stress_shocks_bp": stress_shocks_bp_by_tenor_months,
                "history_supplied": history is not None,
                "confidence_level": confidence_level}),
            data_classification=portfolio.data_classification,
            interpretation=CONCENTRATION_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Evaluate risk metrics against caller-supplied limits: current value, "
        "limit, utilisation percentage, remaining headroom and a "
        "GREEN/AMBER/RED status for each. Utilisation is the absolute value of "
        "the metric over the limit, so a large short breaches a DV01 limit too. "
        "Every limit and amber threshold is an explicit input - this engine has "
        "no default limit set and will not assume one."
    ))
    def evaluate_risk_limits_tool(
        limits: list[dict[str, Any]] = Field(
            default_factory=list,
            description="Each limit as {metric, limit_amount, current_value, "
                        "unit?, amber_utilisation_percent?, description?}."),
    ) -> LimitReportOutput:
        if not limits:
            raise EngineError(
                "INVALID_LIMIT",
                "no limits were supplied. This engine has no default limit set "
                "and will not assume one.",
                category="USER_INPUT",
                suggested_action=(
                    "Pass each limit as {metric, limit_amount, current_value} "
                    "with an optional unit and amber_utilisation_percent."))
        definitions = []
        for row in limits:
            missing = [k for k in ("metric", "limit_amount", "current_value")
                       if k not in row]
            if missing:
                raise EngineError(
                    "INVALID_LIMIT",
                    f"a limit is missing {missing}. Each needs at least a "
                    "metric name, a limit amount and the current value.",
                    category="USER_INPUT",
                    field_errors={k: "required" for k in missing})
            definitions.append(LimitDefinition(
                metric=str(row["metric"]),
                limit_amount=float(row["limit_amount"]),
                current_value=float(row["current_value"]),
                unit=str(row.get("unit", "USD")),
                amber_utilisation_percent=float(
                    row.get("amber_utilisation_percent", 80.0)),
                description=row.get("description")))
        report = evaluate_limits(definitions)
        return LimitReportOutput(
            valuation_date=dt.date.today(),
            evaluations=[vars(e) for e in report.evaluations],
            breach_count=report.breach_count, amber_count=report.amber_count,
            worst_utilisation_percent=report.worst_utilisation_percent,
            worst_metric=report.worst_metric,
            all_within_limits=report.all_within_limits,
            threshold_policy=report.threshold_policy, method=report.method,
            warnings=[f"{e.metric} is {e.status} at "
                      f"{e.utilisation_percent:.1f}% of its limit"
                      for e in report.evaluations if e.status != "GREEN"],
            reproducibility=repro(None, None, {"limits": limits}),
            data_classification="SYNTHETIC_DEMO",
            interpretation=LIMIT_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Compare two portfolios on identical inputs: present value, DV01, "
        "dollar duration, effective duration and convexity, DV01 concentration, "
        "key-rate DV01 by tenor, any scenarios supplied, and historical VaR and "
        "ES when a history is given. Both sides are measured inside one call "
        "from one set of arguments, so they cannot drift onto different curves "
        "or dates. Use it for hedged versus unhedged, or before versus after a "
        "restructuring."
    ))
    def compare_portfolio_risk_tool(
        portfolio_a: PortfolioInput, portfolio_b: PortfolioInput,
        valuation_date: dt.date, par_curve: ParCurveInput,
        label_a: str = "Portfolio A", label_b: str = "Portfolio B",
        scenario_shocks_bp_by_tenor_months: list[dict[str, float]] | None = None,
        history: CurveHistoryInput | None = None,
        confidence_level: float = Field(default=0.99, ge=0.5, lt=1.0),
        horizon_days: int = Field(default=1, ge=1),
    ) -> PortfolioComparisonOutput:
        par = to_par_curve(par_curve)
        vectors = [
            custom_shock(par, {years(float(k)): float(v) for k, v in scenario.items()},
                         name=f"Scenario {i + 1}")
            for i, scenario in enumerate(scenario_shocks_bp_by_tenor_months or [])]
        tenors = rates = None
        if history is not None:
            tenors, rates = history_arrays(history)
        result = compare_portfolios(
            to_positions(portfolio_a), to_positions(portfolio_b), valuation_date,
            par, label_a, label_b, vectors, tenors, rates,
            confidence_level, horizon_days)
        return PortfolioComparisonOutput(
            valuation_date=valuation_date, label_a=result.label_a,
            label_b=result.label_b,
            measures=[vars(r) for r in result.rows],
            key_rate_dv01=[{"tenor_months": months(k.tenor_years),
                            "portfolio_a": k.portfolio_a,
                            "portfolio_b": k.portfolio_b,
                            "difference": k.difference} for k in result.key_rates],
            scenario_pnl=[vars(r) for r in result.scenario_rows],
            risk_reduction_percent=result.risk_reduction_percent,
            measures_omitted=list(result.measures_omitted),
            method=result.method, note=result.note,
            warnings=([] if history is not None else [
                ("No history was supplied, so VaR and ES are omitted from both "
                "sides rather than shown on one.")]),
            reproducibility=repro(portfolio_a, par_curve, {
                "portfolio_b": portfolio_b.model_dump(mode="json"),
                "scenarios": scenario_shocks_bp_by_tenor_months,
                "confidence_level": confidence_level,
                "horizon_days": horizon_days}),
            data_classification=portfolio_a.data_classification,
            interpretation=MODEL_VALUE_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Incremental trade risk: measure the current book, then the same book "
        "with hypothetical positions added, and difference every measure. "
        "Answers 'what happens to my risk if I add 10m of the 10-year' without "
        "touching anything stored - the combined book is built by appending to "
        "a copy and is discarded when the call returns."
    ))
    def analyze_hypothetical_trade_tool(
        portfolio: PortfolioInput, hypothetical_positions: PortfolioInput,
        valuation_date: dt.date, par_curve: ParCurveInput,
        scenario_shocks_bp_by_tenor_months: list[dict[str, float]] | None = None,
        history: CurveHistoryInput | None = None,
        confidence_level: float = Field(default=0.99, ge=0.5, lt=1.0),
        horizon_days: int = Field(default=1, ge=1),
    ) -> PortfolioComparisonOutput:
        par = to_par_curve(par_curve)
        vectors = [
            custom_shock(par, {years(float(k)): float(v) for k, v in scenario.items()},
                         name=f"Scenario {i + 1}")
            for i, scenario in enumerate(scenario_shocks_bp_by_tenor_months or [])]
        tenors = rates = None
        if history is not None:
            tenors, rates = history_arrays(history)
        result = analyse_hypothetical_trade(
            to_positions(portfolio), to_positions(hypothetical_positions),
            valuation_date, par, vectors, tenors, rates,
            confidence_level, horizon_days)
        return PortfolioComparisonOutput(
            valuation_date=valuation_date, label_a=result.label_a,
            label_b=result.label_b,
            measures=[vars(r) for r in result.rows],
            key_rate_dv01=[{"tenor_months": months(k.tenor_years),
                            "portfolio_a": k.portfolio_a,
                            "portfolio_b": k.portfolio_b,
                            "difference": k.difference} for k in result.key_rates],
            scenario_pnl=[vars(r) for r in result.scenario_rows],
            risk_reduction_percent=result.risk_reduction_percent,
            measures_omitted=list(result.measures_omitted),
            method=result.method,
            note=("The hypothetical book exists only for this call. Nothing "
                  "stored was read for it and nothing stored was changed."),
            warnings=([] if history is not None else [
                ("No history was supplied, so VaR and ES are omitted from both "
                "sides rather than shown on one.")]),
            reproducibility=repro(portfolio, par_curve, {
                "hypothetical": hypothetical_positions.model_dump(mode="json"),
                "scenarios": scenario_shocks_bp_by_tenor_months,
                "confidence_level": confidence_level}),
            data_classification=portfolio.data_classification,
            interpretation=MODEL_VALUE_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "Size a par bond at one curve node so that node's key-rate DV01 reaches "
        "a target, usually zero. The hedge instrument is a newly issued bond "
        "paying the curve's own par rate at that tenor, so the construction is "
        "reproducible and depends on no cheapest-to-deliver judgement. Reports "
        "the effect on EVERY other tenor as well, because a hedge that flattens "
        "one node and moves three others is not a hedge - and a single-number "
        "answer would conceal exactly that. Deterministic risk analytics, not "
        "trading advice."
    ))
    def analyze_rate_hedge_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        hedge_tenor_months: float = Field(
            default=120.0,
            description="The curve node to hedge, in months. 120 is the 10-year."),
        target_key_rate_dv01: float = Field(
            default=0.0,
            description="Desired key-rate DV01 at that node after hedging."),
    ) -> HedgeOutput:
        par = to_par_curve(par_curve)
        result = size_key_rate_hedge(
            to_positions(portfolio), valuation_date, par,
            years(hedge_tenor_months), target_key_rate_dv01)
        return HedgeOutput(
            valuation_date=valuation_date,
            hedge_tenor_months=months(result.tenor_years),
            hedge_instrument_id=result.instrument_id,
            hedge_maturity_date=result.maturity_date,
            hedge_coupon_rate_pct=result.coupon_rate_pct,
            hedge_notional=result.hedge_notional,
            target_key_rate_dv01=target_key_rate_dv01,
            pre_hedge_key_rate_dv01=result.pre_hedge_key_rate_dv01,
            post_hedge_key_rate_dv01=result.post_hedge_key_rate_dv01,
            pre_hedge_portfolio_dv01=result.pre_hedge_portfolio_dv01,
            post_hedge_portfolio_dv01=result.post_hedge_portfolio_dv01,
            residual_key_rate_dv01=[{"tenor_months": months(t),
                                     "key_rate_dv01": v}
                                    for t, v in result.residual_key_rate_dv01],
            not_advice=(
                "Deterministic risk analytics. This is the notional that "
                "neutralises one measured sensitivity under this engine's own "
                "curve model; it is not a recommendation, it ignores cost, "
                "liquidity, financing and basis, and the hedge instrument is a "
                "synthetic par bond rather than a security anyone can buy."),
            reproducibility=repro(portfolio, par_curve, {
                "hedge_tenor_months": hedge_tenor_months,
                "target_key_rate_dv01": target_key_rate_dv01}),
            data_classification=portfolio.data_classification,
            interpretation=MODEL_VALUE_NOTE,
        )

    @server.tool(annotations=DETERMINISTIC, description=(
        "FRTB standardised-approach GIRR capital under the sensitivities-based "
        "method: delta and curvature for the USD risk-free curve. Key-rate "
        "DV01s are converted to Basel PV01 sensitivities, allocated onto the "
        "ten prescribed vertices, risk-weighted per MAR21.42 and aggregated "
        "with the MAR21.46 tenor correlation under all three prescribed "
        "correlation scenarios; the capital is the largest. Curvature uses a "
        "parallel shift at the bucket's highest delta risk weight with full "
        "revaluation. Vega and every other risk class are reported as "
        "unsupported rather than as zero, because this system has no options, "
        "no credit spreads, no FX, no equities and no commodities."
    ))
    def compute_frtb_girr_tool(
        portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
        currency: Literal["USD"] = "USD",
        include_curvature: bool = True,
    ) -> GirrCapitalOutput:
        par = to_par_curve(par_curve)
        book = to_book(portfolio, valuation_date)
        result = compute_girr_capital(book, par, currency, include_curvature)
        curvature = None
        if result.curvature is not None:
            curvature = {
                "risk_weight": result.curvature.risk_weight,
                "shock_bp": result.curvature.shock_bp,
                "base_value": result.curvature.base_value,
                "value_up": result.curvature.value_up,
                "value_down": result.curvature.value_down,
                "delta_offset": result.curvature.delta_offset,
                "cvr_up": result.curvature.cvr_up,
                "cvr_down": result.curvature.cvr_down,
                "bucket_capital": result.curvature.bucket_capital,
                "book_is_positively_convex": result.curvature.book_is_positively_convex,
                "interpretation": result.curvature.interpretation,
            }
        return GirrCapitalOutput(
            valuation_date=valuation_date,
            regulatory_framework="Basel FRTB standardised approach, GIRR",
            source=FRTB_SOURCE, constants_version=result.constants_version,
            currency=result.currency, bucket=result.bucket,
            base_value=result.base_value,
            vertices=[{
                "vertex_years": v.vertex_years, "risk_weight": v.risk_weight,
                "sensitivity": v.sensitivity,
                "weighted_sensitivity": v.weighted_sensitivity,
                "sourced_from_curve_nodes": [
                    {"tenor_months": months(t), "sensitivity": s}
                    for t, s in v.sourced_from_curve_nodes],
            } for v in result.vertices],
            correlation_scenarios=[vars(s) for s in result.scenarios],
            delta_capital=result.delta_capital,
            binding_scenario=result.binding_scenario,
            curvature=curvature, vega_capital=None,
            total_capital=result.total_capital,
            total_capital_percent_of_value=(
                result.total_capital / result.base_value * 100.0
                if result.base_value else 0.0),
            unsupported_risk_classes=list(result.unsupported_risk_classes),
            unsupported_reason=result.unsupported_reason,
            scope_note=result.scope_note, method=result.method,
            warnings=[
                ("Vega is not zero, it is absent: the book contains no "
                "optionality, so a vega charge is not a number this system is "
                "entitled to produce."),
                "Risk classes not measured: "
                + ", ".join(k for k, ok in RISK_CLASS_SUPPORT.items() if not ok),
            ],
            reproducibility=repro(portfolio, par_curve, {
                "currency": currency, "include_curvature": include_curvature,
                "frtb_constants_version": result.constants_version}),
            data_classification=portfolio.data_classification,
            interpretation=REGULATORY_NOTE,
        )
