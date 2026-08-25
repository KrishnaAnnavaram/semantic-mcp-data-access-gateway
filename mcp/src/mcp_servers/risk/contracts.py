"""The risk engine's wire contract.

These models generate the tools' JSON Schemas, so they *are* the API. They were
originally declared inline in `server.py`; they live here now because thirty-odd
tools share them and a contract that exists in one file is a contract that can be
changed in one place.

Three conventions run through all of them, and each exists because its opposite
has produced a real, quiet, expensive mistake somewhere in this field.

**Nothing is a bare number.** `rate_percent`, `shock_bp`, `tenor_months`,
`horizon_days`, `present_value` - the unit is in the name. A field called
`rate` invites a caller to pass 0.0425 where 4.25 was meant, and both parse.

**Tenors cross the wire in months, and are years inside the engine.** Months at
the boundary because that is what the data server publishes and what Treasury's
own labels use (`BC_1MONTH`, `BC_1_5MONTH`); years inside because every formula
in fixed income is written in years. The conversion happens once, here, rather
than being repeated - and occasionally forgotten - in thirty tool bodies.

**Extra fields are refused.** A typo'd argument name must fail loudly. Silently
ignoring `confidence_levl` and computing a 99% figure when 95% was asked for is
far worse than an error, because the result looks entirely normal.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any, Literal

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from .curves import CurveError, ParCurve
from .manifest import MODEL_MANIFEST, reproducibility_block, sha256_of
from .pricing import FixedRateBond, Position
from .revaluation import CompiledBook, compile_book

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


class DatedCurveInput(Strict):
    """One historical curve, with the date it was published on.

    The date is not decoration. A historical replay's shock is the difference
    between two published curves, and the result has to name which two - a
    stress labelled "2020 COVID" that was actually measured across a different
    fortnight is indistinguishable from the real thing without it.
    """

    observation_date: dt.date
    tenors_months: list[float] = Field(min_length=2)
    rates_percent: list[float] = Field(min_length=2)


class CurveHistoryInput(Strict):
    """An aligned curve history: N trading days x the requested tenors.

    Exactly the shape `get_curve_history_matrix` publishes in its `_meta`
    channel, so the host forwards it without reshaping. `dates` is optional and
    only affects labelling - every calculation works on the ordering alone - but
    without it a worst-case scenario can be reported only as "row 137".
    """

    tenors_months: list[float] = Field(min_length=1)
    rates_percent: list[list[float]] = Field(min_length=3)
    dates: list[dt.date] | None = None


class ShockVectorOutput(Strict):
    """A scenario as the engine actually applied it. Always returned in full."""

    scenario_name: str
    scenario_type: str
    template: str | None = None
    severity_bp: float | None = None
    interpolation: str | None = None
    shocks_bp_by_tenor_months: dict[str, float]
    max_absolute_shock_bp: float
    parameters: dict[str, Any] = Field(default_factory=dict)


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
    warnings: list[str] = Field(default_factory=list)


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

STRESS_NOTE = (
    "Full revaluation under an explicit tenor shock vector, which is returned "
    "with the result. P&L is stressed value minus base value, so a negative "
    "number is a loss. The book is model-valued from the Treasury par curve; "
    "these are not executable prices."
)

SIMULATION_NOTE = (
    "A simulated loss distribution, not an observed one. Every path is a full "
    "revaluation, so the book's convexity is priced rather than approximated, "
    "but the distribution the paths are drawn from is a model assumption and is "
    "named in the result. Not a regulatory capital figure."
)

REGULATORY_NOTE = (
    "A standardised-approach demonstration computed on a synthetic book from "
    "real Treasury data. It is not a reported regulatory capital requirement: "
    "no supervisor has reviewed it, the book is invented, and only the risk "
    "classes this system can actually measure are included."
)


# --- conversions ------------------------------------------------------------


def to_par_curve(curve: ParCurveInput | DatedCurveInput) -> ParCurve:
    if len(curve.tenors_months) != len(curve.rates_percent):
        raise CurveError(
            f"tenors_months has {len(curve.tenors_months)} entries and "
            f"rates_percent has {len(curve.rates_percent)}; a curve has exactly "
            "one rate per tenor")
    return ParCurve.from_months(curve.tenors_months, curve.rates_percent)


def to_positions(portfolio: PortfolioInput) -> list[Position]:
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


def to_book(portfolio: PortfolioInput, valuation_date: dt.date) -> CompiledBook:
    """Compile the schedule once. Every repeated revaluation reuses it."""
    return compile_book(to_positions(portfolio), valuation_date)


def months(tenor_years: float) -> float:
    return tenor_years * 12.0


def years(tenor_months: float) -> float:
    return float(tenor_months) / 12.0


def shock_output(vector: Any) -> ShockVectorOutput:
    """Render a `ShockVector` for the wire, in months, always in full."""
    return ShockVectorOutput(
        scenario_name=vector.scenario_name,
        scenario_type=vector.scenario_type,
        template=vector.template,
        severity_bp=vector.severity_bp,
        interpolation=vector.interpolation,
        shocks_bp_by_tenor_months=vector.as_months(),
        max_absolute_shock_bp=vector.max_absolute_bp(),
        parameters=dict(vector.parameters),
    )


def repro(
    portfolio: PortfolioInput | None, curve: ParCurveInput | None,
    extra: dict[str, Any] | None = None,
) -> Reproducibility:
    inputs = {
        "portfolio": portfolio.model_dump(mode="json") if portfolio else None,
        "curve": curve.model_dump(mode="json") if curve else None,
        **(extra or {}),
    }
    block = reproducibility_block(inputs)
    return Reproducibility(
        input_sha256=block["input_sha256"],
        model_manifest_sha256=block["model_manifest_sha256"],
        run_fingerprint=block["run_fingerprint"],
        portfolio_snapshot_sha256=(sha256_of(portfolio.model_dump(mode="json"))
                                   if portfolio else None),
        market_snapshot_sha256=(sha256_of(curve.model_dump(mode="json"))
                                if curve else None),
        dataset_snapshot_id=curve.dataset_snapshot_id if curve else None,
    )


def history_arrays(history: CurveHistoryInput) -> tuple[list[float], list[list[float]]]:
    """Tenors in years, and the rate matrix as floats."""
    return ([years(t) for t in history.tenors_months],
            [[float(x) for x in row] for row in history.rates_percent])


def tenor_rows(pairs: Sequence[tuple[float, float]], value_key: str) -> list[dict[str, float]]:
    """Tenor-keyed rows for the wire, in months."""
    return [{"tenor_months": months(t), value_key: v} for t, v in pairs]
