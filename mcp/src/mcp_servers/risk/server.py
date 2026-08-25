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
from typing import Any

from mcp.server import MCPServer

from .contracts import (
    DETERMINISTIC,
    MODEL_VALUE_NOTE,
    VAR_NOTE,
    ParCurveInput,
    PortfolioInput,
    ResultBase,
)
from .contracts import (
    repro as _repro,
)
from .contracts import (
    to_par_curve as _to_par_curve,
)
from .contracts import (
    to_positions as _to_positions,
)
from .curves import build_discount_curve
from .manifest import MODEL_MANIFEST, sha256_of
from .pricing import price_portfolio
from .risk import (
    compute_dv01,
    compute_historical_risk,
    compute_key_rate_dv01,
    run_stress,
)

logging.basicConfig(
    level=logging.INFO, stream=sys.stderr,
    format="%(asctime)s %(levelname)-7s mcp-risk %(message)s", datefmt="%H:%M:%S",
)
LOGGER = logging.getLogger("mcp_risk")

# --- outputs ----------------------------------------------------------------
#
# Inputs, the reproducibility block and the shared result base moved to
# `contracts.py` when the tool count went past thirty; the five original tools
# keep their own output models here, next to the tools that build them.


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
    import json
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


# --- resources for the expanded surface -------------------------------------
#
# Each of these publishes something a caller would otherwise have to guess at:
# the exact shape of a named scenario, the exact dates behind a named crisis,
# the exact regulatory constants, and - the one people forget to publish - the
# list of things this engine deliberately cannot do.


@server.resource(
    "risk://scenarios/templates",
    name="Scenario templates",
    mime_type="application/json",
    description=(
        "Every named stress shape, as control points in multiples of severity, "
        "plus the interpolation rules and the project-defined severity labels."
    ),
)
def resource_scenario_templates() -> str:
    import json

    from .stress_matrix import STANDARD_PACK_SPEC, STANDARD_PACK_VERSION
    from .stress_scenarios import SEVERITY_BP, SEVERITY_NOTE, TEMPLATES
    return json.dumps({
        "version": MODEL_MANIFEST["stress_scenario_version"],
        "templates": {
            name: {
                "scenario_type": kind,
                "control_points_as_multiples_of_severity": {
                    f"{tenor:g}y": multiple for tenor, multiple in sorted(control.items())
                },
                "at_severity_100bp": {
                    f"{tenor:g}y": multiple * 100.0
                    for tenor, multiple in sorted(control.items())
                },
            }
            for name, (kind, control) in TEMPLATES.items()
        },
        "interpolation": {
            "linear_years": (
                "Linear in tenor measured in years between control points, held "
                "flat beyond the outermost one. The default."
            ),
            "node_rank": (
                "Linear in the tenor's position within the curve's node list. "
                "Reproduces the textbook twist table (2Y -100, 5Y -50, 10Y 0, "
                "20Y +50, 30Y +100) exactly."
            ),
        },
        "severity_labels_bp": SEVERITY_BP,
        "severity_note": SEVERITY_NOTE,
        "standard_pack": {
            "version": STANDARD_PACK_VERSION,
            "scenario_count": len(STANDARD_PACK_SPEC),
            "note": (
                "Adding a scenario changes what 'the standard stress matrix' "
                "means, so the pack version and the manifest entry move together."
            ),
        },
        "sign_conventions": {
            "shock": "basis points, additive on the par yield",
            "pnl": "stressed value minus base value; negative is a loss",
        },
    }, indent=2)


@server.resource(
    "risk://scenarios/historical-crises",
    name="Historical crisis catalogue",
    mime_type="application/json",
    description=(
        "Named crisis windows as DATES ONLY. No shock vector is stored: every "
        "historical shock is measured from published curves at run time."
    ),
)
def resource_crisis_catalogue() -> str:
    import json

    from .historical_stress import CRISIS_CATALOGUE, CRISIS_CATALOGUE_VERSION
    return json.dumps({
        "version": CRISIS_CATALOGUE_VERSION,
        "principle": (
            "This catalogue contains dates, never basis points. A stored "
            "'2008 shock vector' is a number somebody typed: it decays as data "
            "is revised and nobody can audit it without re-deriving it, at "
            "which point they may as well have derived it. Fetch the curves for "
            "the window from market-risk-data-mcp and the engine measures the "
            "shock itself."
        ),
        "crises": [
            {
                "crisis_id": c.crisis_id,
                "name": c.name,
                "start_date": c.start_date.isoformat(),
                "end_date": c.end_date.isoformat(),
                "description": c.description,
                "what_happened": c.what_happened,
            }
            for c in CRISIS_CATALOGUE
        ],
        "coverage": (
            "Treasury's daily par yield curve begins in 1990, so every window "
            "above is inside the published history. Individual tenors are not: "
            "the 30-year has a genuine gap from February 2002 to February 2006. "
            "A window whose curves the caller cannot supply is refused with the "
            "gap named rather than measured from nearby dates."
        ),
    }, indent=2)


@server.resource(
    "risk://methodology/risk-measures",
    name="Risk measure methodologies",
    mime_type="text/markdown",
    description=(
        "The four loss-distribution methodologies this engine implements, what "
        "each assumes, and why they are not expected to agree."
    ),
)
def resource_risk_measures() -> str:
    return (
        "# Loss distribution methodologies\n\n"
        "Four different models, not four estimates of one number. Each has its "
        "own manifest version so a comparison table cannot present two of them "
        "as the same measure computed twice.\n\n"
        "| method | distribution | revaluation | horizon |\n"
        "|---|---|---|---|\n"
        "| historical simulation | the empirical distribution of observed moves | full | observed h-day moves |\n"
        "| parametric (delta-normal) | multivariate normal | none: linear key-rate approximation | observed, or sqrt(h) if asked |\n"
        "| Monte Carlo | multivariate normal | full | observed h-day covariance |\n"
        "| extreme tail | scaled normal, stressed covariance, Student-t, or empirical bootstrap | full | observed h-day covariance |\n\n"
        "## The horizon rule\n\n"
        "**Historical h-day risk uses observed h-day moves and never scales a "
        "one-day figure by sqrt(h).** The shortcut assumes independent, "
        "identically distributed returns, which rate moves are not: it "
        "understates exactly the clustered, trending episodes a risk number "
        "exists to capture.\n\n"
        "The parametric path may scale by sqrt(h) **because its own model "
        "already assumes independent normal increments** - there the scaling "
        "follows from the assumptions rather than contradicting them. The "
        "result names which path ran.\n\n"
        "## Quantile convention\n\n"
        "Nearest rank, `k = ceil(alpha * N)`, no interpolation, everywhere. "
        "NumPy offers nine interpolation methods and its default is not this "
        "one; two engines both reporting '99% VaR' can disagree purely on that "
        "choice, so the convention is part of the model definition.\n\n"
        "Expected Shortfall is the mean of losses at or beyond the VaR on the "
        "empirical paths, and the normal closed form "
        "`phi(z)/(1-alpha) * sigma` on the parametric path. Those are different "
        "estimators of the same concept and are labelled separately.\n\n"
        "## Contributions\n\n"
        "Component VaR and ES are **exact** Euler decompositions here, not "
        "allocation heuristics. Under nearest rank the VaR is one identified "
        "scenario's loss, so the positions' losses in that scenario sum to it; "
        "ES is a mean over tail scenarios, so the positions' mean losses over "
        "those scenarios sum to it. Incremental VaR answers a different "
        "question - what dropping a position would do - and sums to nothing.\n\n"
        "## What none of these are\n\n"
        "Analytical demonstrations on a synthetic book. Not regulatory capital: "
        "the revised Basel market-risk framework moved the internal-model "
        "approach toward Expected Shortfall at 97.5% with liquidity horizons, "
        "and none of that is implemented here.\n"
    )


@server.resource(
    "risk://methodology/regulatory-girr",
    name="FRTB GIRR scope and constants",
    mime_type="application/json",
    description=(
        "The Basel parameters this engine implements, their source, and the "
        "complete list of risk classes it deliberately does not compute."
    ),
)
def resource_regulatory_girr() -> str:
    import json

    from .regulatory import constants as k
    return json.dumps({
        "framework": "Basel FRTB standardised approach, sensitivities-based method",
        "source": k.FRTB_SOURCE,
        "constants_version": k.FRTB_CONSTANTS_VERSION,
        "girr_delta": {
            "vertices_years": list(k.GIRR_VERTICES_YEARS),
            "risk_weights": {f"{t:g}y": w
                             for t, w in k.GIRR_DELTA_RISK_WEIGHTS.items()},
            "tenor_correlation": (
                "rho(k,l) = max(40%, exp(-3% * |Tk - Tl| / min(Tk, Tl)))"),
            "correlation_theta": k.GIRR_CORRELATION_THETA,
            "correlation_floor": k.GIRR_CORRELATION_FLOOR,
            "inter_bucket_correlation": k.GIRR_INTER_BUCKET_CORRELATION,
            "sensitivity_definition": (
                "PV01: the value change for a 1bp move at a vertex, divided by "
                "0.0001. This engine's key-rate DV01 is base minus bumped, so "
                "the Basel sensitivity is its negative over 0.0001."),
        },
        "correlation_scenarios": {
            "medium": "the prescribed parameters as given",
            "high": f"multiplied by {k.HIGH_CORRELATION_MULTIPLIER}, capped at 100%",
            "low": "max(2 x rho - 100%, 75% x rho)",
            "capital": "the largest of the three",
        },
        "girr_curvature": {
            "risk_weight": k.GIRR_CURVATURE_RISK_WEIGHT,
            "shock": (
                "a parallel shift of every vertex at the bucket's highest delta "
                "risk weight, with full revaluation"),
            "note": (
                "A positively convex long bond book scores zero here and that "
                "is correct: both CVR values come out negative and the charge "
                "floors at zero. Basel does not credit the convexity benefit."),
        },
        "risk_class_support": k.RISK_CLASS_SUPPORT,
        "unsupported_reason": k.UNSUPPORTED_REASON,
        "not_a_capital_requirement": (
            "A standardised-approach demonstration on a synthetic book. No "
            "supervisor has reviewed it, the positions are invented, and only "
            "the risk classes this system can measure are included."),
    }, indent=2)


@server.resource(
    "risk://capability-gaps",
    name="Capability gaps",
    mime_type="application/json",
    description=(
        "What this engine cannot compute, why, and what each capability would "
        "require. Published so an absent number is never mistaken for a zero."
    ),
)
def resource_capability_gaps() -> str:
    import json
    return json.dumps({
        "principle": (
            "An absent capability is reported as absent, never as zero. A "
            "capital figure or a risk number that silently omits a risk class "
            "the book actually runs is not conservative - it is understated, "
            "and it is understated invisibly."
        ),
        "instruments_supported": ["FIXED_RATE_BOND (semiannual, ACT/ACT ICMA, USD)"],
        "market_data_supported": ["US Treasury par yield curve, nominal and real"],
        # One entry per line. A wrapped string inside a list literal is
        # indistinguishable from a missing comma, and this list is read by
        # people deciding what to build next.
        "gaps": {
            "credit": [
                "CS01",
                "spread VaR",
                "spread stress",
                "jump-to-default",
                "default risk charge",
            ],
            "options": [
                "delta", "gamma", "vega", "theta", "rho", "vanna", "volga",
                "implied volatility",
                "volatility surfaces",
                "smile and skew",
                "option curvature stress",
            ],
            "fx": [
                "FX delta", "FX VaR", "FX stress", "cross-currency basis",
            ],
            "equity": [
                "equity delta", "equity VaR", "beta", "equity stress",
                "index versus component basis",
            ],
            "commodity": [
                "commodity delta", "commodity VaR", "commodity stress",
                "curve, basis and location risk",
            ],
            "liquidity": [
                "bid/ask widening",
                "liquidation cost",
                "price impact",
                "market depth",
                "liquidity horizons",
                "liquidity-adjusted VaR and ES",
            ],
            "fixed_income_expansion": [
                "SOFR and OIS curves",
                "swaps", "futures", "FRNs", "TIPS", "swaptions",
                "caps and floors",
                "basis curves",
                "repo and funding",
            ],
            "regulatory": [
                "credit spread risk", "default risk charge",
                "residual risk add-on", "NMRF", "PLA",
                "IMA expected shortfall with liquidity horizons",
            ],
        },
        "full_analysis": "docs/capability-gaps.md",
    }, indent=2)


# --- prompts for the expanded surface ---------------------------------------


@server.prompt(
    name="stress_matrix_review",
    description="Run the standard stress pack and interpret the ranked table.",
)
def prompt_stress_matrix_review(portfolio_id: str = "") -> str:
    book = portfolio_id or "the first portfolio returned by list_portfolios"
    return (
        f"Produce a stress review for {book}. In order: fetch the portfolio and "
        "the latest nominal par curve from the data server, then call "
        "run_stress_matrix_tool once. Report the three worst scenarios with "
        "their P&L and percentage of value, name the position and the maturity "
        "bucket driving the worst one, and say which shape of move - parallel, "
        "steepening, flattening or curvature - the book is most exposed to. "
        "Quote the shock vector of the worst scenario so the reader can check "
        "it. List any scenario the bootstrap refused and why. Label the book "
        "SYNTHETIC_DEMO and the curve REAL_MARKET_DATA."
    )


@server.prompt(
    name="reverse_stress_review",
    description="Answer 'what move would cost us X' and set it in context.",
)
def prompt_reverse_stress_review(target_loss: str = "", portfolio_id: str = "") -> str:
    loss = target_loss or "a loss the user names"
    book = portfolio_id or "the first portfolio returned by list_portfolios"
    return (
        f"Work out what rate move costs {book} {loss}. Fetch the portfolio and "
        "the curve, then call run_reverse_stress_tool with a parallel shape, and "
        "compute_stress_thresholds_tool for a ladder of nearby loss levels. "
        "Report the solved shock in basis points, not as a multiplier, and say "
        "whether the solver converged. Then set it in context: call "
        "find_worst_historical_stresses_tool over the last year and say whether "
        "a move of that size has actually happened. Do not describe the solved "
        "move as likely or unlikely - the engine has no view on probability."
    )


@server.prompt(
    name="model_validation_review",
    description="Compare the risk methodologies and backtest the chosen one.",
)
def prompt_model_validation_review(portfolio_id: str = "") -> str:
    book = portfolio_id or "the first portfolio returned by list_portfolios"
    return (
        f"Run a model-validation review for {book}. Call compare_risk_methods_tool "
        "to put historical, parametric and Monte Carlo VaR and ES side by side. "
        "Explain the differences rather than averaging them: parametric well "
        "below historical means the loss distribution has fatter tails than a "
        "normal; Monte Carlo far from parametric on a nearly linear book means "
        "the simulation has not converged. Quote each method's own version "
        "string from the manifest. State plainly that the three are different "
        "models and are not expected to agree, and that none of them is a "
        "regulatory capital figure."
    )


@server.prompt(
    name="pnl_attribution_review",
    description="Explain a period's P&L and interrogate the residual.",
)
def prompt_pnl_attribution_review(portfolio_id: str = "") -> str:
    book = portfolio_id or "the first portfolio returned by list_portfolios"
    return (
        f"Attribute {book}'s P&L between two dates. Fetch the curve on both "
        "dates and call compute_pnl_attribution_tool. Report carry, roll-down "
        "and the rate move as amounts and as shares of the total, then name the "
        "tenors that drove the rate effect. Give the two residuals separately "
        "and explain that they mean different things: the top-level residual "
        "should be at machine precision, and rate_unexplained is the book's "
        "convexity, which grows with the size of the move. Never present the "
        "attribution as complete without quoting rate_unexplained."
    )


@server.prompt(
    name="regulatory_scope",
    description="State what regulatory capital this engine computes, and what it does not.",
)
def prompt_regulatory_scope() -> str:
    return (
        "Read risk://methodology/regulatory-girr and risk://capability-gaps, "
        "then explain exactly what regulatory calculation this system supports: "
        "FRTB standardised-approach GIRR delta and curvature, for one USD "
        "bucket, on fixed-rate Treasury bonds. Name the Basel source and the "
        "constants version. Then be explicit about the gaps - credit spread "
        "risk, default risk, FX, equity, commodity and vega are not computed "
        "and are not zero. Say why: the instruments and market data they need "
        "do not exist in this system, and a capital number that silently omits "
        "a risk class is understated rather than conservative."
    )

# --- the rest of the tool surface ------------------------------------------
#
# Registration only. Each module below owns one family of tools, validates its
# own typed input and calls a deterministic module; none of them contains
# arithmetic. They are separate files because thirty-eight tools in one module
# is a file nobody reads to the end, not because the boundaries mean anything
# at the protocol level - every tool below is advertised by this one server.

from . import (
    tools_analytics,
    tools_distribution,
    tools_historical,
    tools_portfolio,
    tools_stress,
)

tools_analytics.register(server)
tools_stress.register(server)
tools_historical.register(server)
tools_distribution.register(server)
tools_portfolio.register(server)


def main() -> None:
    LOGGER.info("risk engine %s; no database, no model, no network",
                MODEL_MANIFEST["risk_engine_version"])
    import anyio
    anyio.run(server.run_stdio_async)


if __name__ == "__main__":
    main()
