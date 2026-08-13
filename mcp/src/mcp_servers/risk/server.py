"""risk-engine-mcp — the server.

A thin protocol wrapper over `curves`, `pricing` and `risk`. All the thinking is
in those modules; this file's job is to accept typed inputs, call them, and
attach the reproducibility block.

Deliberately absent:

* **Any database driver.** This process is launched with a sanitised
  environment containing no `DATABASE_URL`, and a test asserts no module here
  imports psycopg2. Market data arrives as a typed argument or not at all -
  which is what makes "was the input wrong, or the maths?" answerable.
* **Any LLM.** The engine must return the same number every time. A model in
  the loop would make that untrue.
* **Any network access.**

Run: `python -m mcp_servers.risk.server` (stdio). Diagnostics to stderr only.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from typing import Any, Literal

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from .curves import CurveError, ParCurve, build_discount_curve
from .manifest import MODEL_MANIFEST, reproducibility_block, sha256_of
from .pricing import FixedRateBond, Position, PricingError, price_portfolio
from .risk import (
    RiskError, compute_dv01, compute_historical_risk, compute_key_rate_dv01,
    run_stress,
)

logging.basicConfig(
    level=logging.INFO, stream=sys.stderr,
    format="%(asctime)s %(levelname)-7s mcp-risk %(message)s", datefmt="%H:%M:%S",
)
LOGGER = logging.getLogger("mcp_risk")

DETERMINISTIC = ToolAnnotations(
    read_only_hint=True, destructive_hint=False,
    idempotent_hint=True, open_world_hint=False,
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- inputs -----------------------------------------------------------------


class ParCurveInput(Strict):
    observation_date: dt.date
    curve_family: Literal["nominal", "real"] = "nominal"
    tenors_months: list[float] = Field(min_length=2)
    rates_percent: list[float] = Field(min_length=2)
    quote_basis: Literal["par_coupon_semiannual"] = Field(
        default="par_coupon_semiannual",
        description="Only par yields are accepted. Passing bank-discount or "
                    "coupon-equivalent bill quotes here would be a category error.",
    )
    dataset_snapshot_id: str | None = None


class BondInput(Strict):
    instrument_id: str
    face_value: float
    coupon_rate_pct: float
    issue_date: dt.date
    maturity_date: dt.date
    coupon_frequency: Literal[2] = 2
    day_count: Literal["ACT_ACT"] = "ACT_ACT"
    currency: Literal["USD"] = "USD"


class PositionInput(Strict):
    instrument: BondInput
    face_notional: float


class PortfolioInput(Strict):
    portfolio_id: str
    data_classification: Literal["SYNTHETIC_DEMO", "REAL_MARKET_DATA"] = "SYNTHETIC_DEMO"
    positions: list[PositionInput] = Field(min_length=1)


# --- outputs ----------------------------------------------------------------


class Reproducibility(Strict):
    input_sha256: str
    model_manifest_sha256: str
    run_fingerprint: str
    portfolio_snapshot_sha256: str | None = None
    market_snapshot_sha256: str | None = None
    dataset_snapshot_id: str | None = None


class ResultBase(Strict):
    valuation_date: dt.date
    currency: str = "USD"
    model: dict[str, Any] = Field(default_factory=lambda: dict(MODEL_MANIFEST))
    reproducibility: Reproducibility
    data_classification: str
    interpretation: str = Field(
        description="What the number is - and is not. Model-implied from the "
                    "Treasury par curve, not an executable price."
    )


class PriceResult(ResultBase):
    total_present_value: float
    positions: list[dict[str, Any]]


class Dv01Output(ResultBase):
    base_value: float
    dv01: float
    bump_bp: float
    per_position: list[dict[str, Any]]


class KeyRateOutput(ResultBase):
    base_value: float
    bump_bp: float
    key_rate_dv01: list[dict[str, float]]
    total: float


class StressOutput(ResultBase):
    base_value: float
    stressed_value: float
    pnl: float
    per_position: list[dict[str, Any]]


class HistoricalRiskOutput(ResultBase):
    base_value: float
    confidence_level: float
    horizon_days: int
    scenarios_used: int
    var: float
    expected_shortfall: float
    worst_loss: float
    best_pnl: float
    distribution: dict[str, float]


MODEL_VALUE_NOTE = (
    "Model-implied value from the published Treasury par curve using "
    f"{MODEL_MANIFEST['curve_builder_version']}. Treasury's inputs are "
    "indicative bid-side quotations and Treasury does not publish a zero-coupon "
    "curve, so this is not an executable market price."
)

VAR_NOTE = (
    "Historical simulation with full revaluation. VaR is the "
    f"{MODEL_MANIFEST['quantile_method']} quantile of the loss distribution; "
    "Expected Shortfall is the mean of losses at or beyond it. An analytical "
    "demonstration, not a regulatory capital figure - the revised Basel market-"
    "risk framework moved the internal-model approach toward Expected Shortfall."
)

server = MCPServer(
    name="risk-engine-mcp",
    title="Risk Engine",
    version="0.1.0",
    instructions=(
        "Deterministic market-risk mathematics for fixed-rate bonds: pricing, "
        "DV01, key-rate DV01, historical VaR and Expected Shortfall, and "
        "stress.\n\n"
        "This server has no database and no market data of its own. Supply the "
        "curve and the portfolio as arguments - fetch them from "
        "market-risk-data-mcp first.\n\n"
        "It accepts PAR yields only. Treasury par yields are not zero-coupon "
        "rates; the engine bootstraps a discount curve before pricing. Do not "
        "pass bill discount rates or coupon-equivalent yields as a curve.\n\n"
        "Every result carries model versions and a run fingerprint: the same "
        "inputs and the same manifest reproduce the same number exactly."
    ),
)


def _to_par_curve(curve: ParCurveInput) -> ParCurve:
    if len(curve.tenors_months) != len(curve.rates_percent):
        raise CurveError("tenors_months and rates_percent differ in length")
    return ParCurve.from_months(curve.tenors_months, curve.rates_percent)


def _to_positions(portfolio: PortfolioInput) -> list[Position]:
    return [
        Position(
            FixedRateBond(
                instrument_id=p.instrument.instrument_id,
                face_value=p.instrument.face_value,
                coupon_rate_pct=p.instrument.coupon_rate_pct,
                maturity_date=p.instrument.maturity_date,
                issue_date=p.instrument.issue_date,
                coupon_frequency=p.instrument.coupon_frequency,
                day_count=p.instrument.day_count,
                currency=p.instrument.currency,
            ),
            p.face_notional,
        )
        for p in portfolio.positions
    ]


def _repro(portfolio: PortfolioInput, curve: ParCurveInput,
           extra: dict[str, Any] | None = None) -> Reproducibility:
    inputs = {"portfolio": portfolio.model_dump(mode="json"),
              "curve": curve.model_dump(mode="json"), **(extra or {})}
    block = reproducibility_block(inputs)
    return Reproducibility(
        input_sha256=block["input_sha256"],
        model_manifest_sha256=block["model_manifest_sha256"],
        run_fingerprint=block["run_fingerprint"],
        portfolio_snapshot_sha256=sha256_of(portfolio.model_dump(mode="json")),
        market_snapshot_sha256=sha256_of(curve.model_dump(mode="json")),
        dataset_snapshot_id=curve.dataset_snapshot_id,
    )


@server.tool(annotations=DETERMINISTIC, description=(
    "Present value of a portfolio of fixed-rate bonds under a Treasury par "
    "curve. The curve is bootstrapped to discount factors first - par yields "
    "are not discount rates."
))
def price_portfolio_tool(
    portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
) -> PriceResult:
    positions = _to_positions(portfolio)
    result = price_portfolio(positions, valuation_date, build_discount_curve(_to_par_curve(par_curve)))
    return PriceResult(
        valuation_date=valuation_date, currency=result.currency,
        total_present_value=result.total_present_value,
        positions=[{"instrument_id": p.instrument_id,
                    "present_value": p.present_value,
                    "cash_flows": p.cash_flow_count} for p in result.positions],
        reproducibility=_repro(portfolio, par_curve),
        data_classification=portfolio.data_classification,
        interpretation=MODEL_VALUE_NOTE,
    )


@server.tool(annotations=DETERMINISTIC, description=(
    "DV01 by full revaluation: the value lost from a parallel rise in the par "
    "curve. Positive for a conventional long fixed-rate book."
))
def compute_dv01_tool(
    portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
    bump_bp: float = 1.0,
) -> Dv01Output:
    r = compute_dv01(_to_positions(portfolio), valuation_date,
                     _to_par_curve(par_curve), bump_bp)
    return Dv01Output(
        valuation_date=valuation_date, base_value=r.base_value, dv01=r.dv01,
        bump_bp=r.bump_bp,
        per_position=[{"instrument_id": i, "dv01": v} for i, v in r.per_position],
        reproducibility=_repro(portfolio, par_curve, {"bump_bp": bump_bp}),
        data_classification=portfolio.data_classification,
        interpretation=MODEL_VALUE_NOTE,
    )


@server.tool(annotations=DETERMINISTIC, description=(
    "Key-rate DV01: sensitivity to each par node bumped individually. Single-"
    "node bumps, no smoothing - the perturbation is exactly what the name says. "
    "Key tenors must be actual curve nodes."
))
def compute_key_rate_dv01_tool(
    portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
    key_tenors_months: list[float] | None = None, bump_bp: float = 1.0,
) -> KeyRateOutput:
    tenors = [t / 12.0 for t in key_tenors_months] if key_tenors_months else None
    r = compute_key_rate_dv01(_to_positions(portfolio), valuation_date,
                              _to_par_curve(par_curve), tenors, bump_bp)
    return KeyRateOutput(
        valuation_date=valuation_date, base_value=r.base_value, bump_bp=r.bump_bp,
        key_rate_dv01=[{"tenor_months": t * 12.0, "dv01": v} for t, v in r.key_rate_dv01],
        total=r.total,
        reproducibility=_repro(portfolio, par_curve,
                               {"key_tenors_months": key_tenors_months, "bump_bp": bump_bp}),
        data_classification=portfolio.data_classification,
        interpretation=MODEL_VALUE_NOTE,
    )


@server.tool(annotations=DETERMINISTIC, description=(
    "Revalue a portfolio under an explicit tenor-to-basis-point shock vector. "
    "For a historical replay, difference the two observed curves first and pass "
    "the result - this server does not fetch market data."
))
def run_stress_tool(
    portfolio: PortfolioInput, valuation_date: dt.date, par_curve: ParCurveInput,
    shocks_bp_by_tenor_months: dict[str, float],
) -> StressOutput:
    shocks = {float(k) / 12.0: float(v) for k, v in shocks_bp_by_tenor_months.items()}
    r = run_stress(_to_positions(portfolio), valuation_date,
                   _to_par_curve(par_curve), shocks)
    return StressOutput(
        valuation_date=valuation_date, base_value=r.base_value,
        stressed_value=r.stressed_value, pnl=r.pnl,
        per_position=[{"instrument_id": i, "pnl": v} for i, v in r.per_position],
        reproducibility=_repro(portfolio, par_curve,
                               {"shocks_bp": shocks_bp_by_tenor_months}),
        data_classification=portfolio.data_classification,
        interpretation=MODEL_VALUE_NOTE,
    )


@server.tool(annotations=DETERMINISTIC, description=(
    "Historical-simulation VaR and Expected Shortfall by full revaluation. "
    "Supply the aligned curve history as tenors plus a rates matrix - the host "
    "gets this from get_curve_history_matrix's _meta channel. Both measures "
    "come from one revaluation pass over the same scenario set. Horizons longer "
    "than a day use observed h-day changes, never sqrt(h) scaling."
))
def compute_historical_risk_tool(
    portfolio: PortfolioInput,
    valuation_date: dt.date,
    par_curve: ParCurveInput,
    history_tenors_months: list[float],
    history_rates_percent: list[list[float]],
    confidence_level: float = 0.99,
    horizon_days: int = 1,
) -> HistoricalRiskOutput:
    r = compute_historical_risk(
        _to_positions(portfolio), valuation_date, _to_par_curve(par_curve),
        [t / 12.0 for t in history_tenors_months], history_rates_percent,
        confidence_level, horizon_days,
    )
    return HistoricalRiskOutput(
        valuation_date=valuation_date, base_value=r.base_value,
        confidence_level=r.confidence_level, horizon_days=r.horizon_days,
        scenarios_used=r.scenarios_used, var=r.var,
        expected_shortfall=r.expected_shortfall, worst_loss=r.worst_loss,
        best_pnl=r.best_pnl, distribution=r.pnl_distribution_summary,
        reproducibility=_repro(portfolio, par_curve, {
            "confidence_level": confidence_level,
            "horizon_days": horizon_days,
            "scenario_set_sha256": sha256_of(history_rates_percent),
        }),
        data_classification=portfolio.data_classification,
        interpretation=VAR_NOTE,
    )


@server.resource(
    "risk://model/manifest",
    name="Model manifest",
    mime_type="application/json",
    description="Model versions and every numerical convention, so a result can be reproduced.",
)
def resource_manifest() -> str:
    import json  # noqa: PLC0415
    return json.dumps(MODEL_MANIFEST, indent=2)


@server.resource(
    "risk://methodology/curve-construction",
    name="Curve construction",
    mime_type="text/markdown",
    description="Why par yields are bootstrapped rather than used as discount rates.",
)
def resource_curve_method() -> str:
    return (
        "# Curve construction — `par_bootstrap_logdf_interp_v1`\n\n"
        "Treasury publishes a **par yield curve** on a semiannual bond-equivalent "
        "basis, and does not publish a zero-coupon curve. A 10-year CMT of 4.25% "
        "is the coupon a 10-year bond would need to trade at 100; it is not the "
        "rate at which a ten-year cash flow discounts.\n\n"
        "## Method\n\n"
        "At semiannual node *n* with annual par rate *c*, the par-bond identity\n\n"
        "    1 = (c/2) * sum_{i=1..n} D_i + D_n\n\n"
        "gives the forward recurrence\n\n"
        "    D_n = (1 - (c/2) * sum_{i=1..n-1} D_i) / (1 + c/2)\n\n"
        "Par rates are interpolated linearly onto the semiannual grid first, "
        "because Treasury publishes fourteen tenors and the bootstrap needs "
        "sixty. Between nodes, discount factors are interpolated linearly in "
        "log D; beyond the last node the final forward rate is held flat.\n\n"
        "## Guards\n\n"
        "A discount factor that is non-positive, or that rises with maturity "
        "(a negative forward), aborts the build. Those indicate an input curve "
        "the bootstrap cannot price consistently, and continuing would produce "
        "plausible-looking numbers from it.\n\n"
        "## Limits\n\n"
        "This is a transparent, reproducible construction, not a reproduction of "
        "Treasury's monotone-convex methodology, which Treasury does not publish "
        "in full. Values are model-implied.\n"
    )


# --- prompts ----------------------------------------------------------------
# User-controlled entry points. Each one names the *order* the tools must run
# in, because the ordering is where the mistakes live: pricing before the curve
# is bootstrapped, or a stress applied to a portfolio nobody fetched.


@server.prompt(
    name="risk_summary",
    description="Price a demo portfolio and summarise its rate risk.",
)
def prompt_risk_summary(portfolio_id: str = "") -> str:
    which = portfolio_id or "the first portfolio returned by list_portfolios"
    return (
        f"Produce a rate-risk summary for {which}. In order: fetch the portfolio "
        "from the data server, fetch the latest nominal par curve, then call "
        "price_portfolio_tool, compute_dv01_tool and compute_key_rate_dv01_tool. "
        "Report present value, DV01, and which key-rate bucket carries the most "
        "sensitivity. State plainly that the book is SYNTHETIC_DEMO and that "
        "values are model-implied from the par curve, not executable prices. Do "
        "not compute VaR here."
    )


@server.prompt(
    name="stress_review",
    description="Run a stress scenario against a demo portfolio and interpret it.",
)
def prompt_stress_review(scenario_id: str = "", portfolio_id: str = "") -> str:
    scen = scenario_id or "each scenario returned by list_scenarios"
    book = portfolio_id or "the first portfolio returned by list_portfolios"
    return (
        f"Stress {book} under {scen}. Fetch the portfolio and the base curve, "
        "get the scenario definition, then call run_stress_tool. For a "
        "HISTORICAL_REPLAY scenario the shock is the difference between the two "
        "named dates' observed curves - fetch both and difference them; do not "
        "invent a shock vector. Report the change in present value, the shape of "
        "the shock, and which positions drive the result. Label the book "
        "SYNTHETIC_DEMO."
    )


@server.prompt(
    name="var_methodology",
    description="Explain how this engine's VaR is computed, and what it is not.",
)
def prompt_var_methodology() -> str:
    return (
        "Read the risk://model/manifest and risk://methodology/curve-construction "
        "resources, then explain this engine's historical-simulation VaR: the "
        "window, the quantile convention, and that it revalues in full rather "
        "than using a delta approximation. State the model versions from the "
        "manifest. Be explicit that the figure is an analytical demonstration on "
        "a synthetic book, not a regulatory capital number, and that par yields "
        "are bootstrapped to discount factors rather than used directly."
    )


def main() -> None:
    LOGGER.info("risk engine %s; no database, no model, no network",
                MODEL_MANIFEST["risk_engine_version"])
    import anyio
    anyio.run(server.run_stdio_async)


if __name__ == "__main__":
    main()
