"""The wire contract.

These models generate the tools' JSON Schemas, so they are the API. Two
conventions run through all of them.

**A rate is never a bare number.** Every `RatePoint` carries `rate_kind`,
`quote_basis` and `unit`. On 2026-08-11 the 4-week bill quotes 3.64 on a
bank-discount actual/360 basis and 3.70 coupon-equivalent; both are correct and
they are not interchangeable. Stored as adjacent bare numbers they eventually
share a curve. Carrying the basis makes that mistake require ignoring an
explicit label rather than merely not knowing.

**Decimals stay decimal.** Rates and money serialise as JSON strings, not
floats, so a value cannot pick up binary floating-point noise in transit and a
reader cannot mistake `4.2` for `4.2000000000000002`. The risk engine converts
once, deliberately, at its own boundary.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CurveFamily = Literal["nominal", "real"]
DataClassification = Literal["REAL_MARKET_DATA", "SYNTHETIC_DEMO"]
DatePolicy = Literal["exact", "previous", "next"]
MissingPolicy = Literal["reject", "intersection"]

QuoteBasis = Literal[
    "par_coupon_semiannual",
    "bank_discount_act360",
    "coupon_equivalent",
    "average_real_yield",
]


class Strict(BaseModel):
    """Reject unrecognised fields.

    A typo'd argument should fail loudly. Silently ignoring `serie_codes` and
    returning every series is far worse than an error.
    """

    model_config = ConfigDict(extra="forbid")


# --- provenance -------------------------------------------------------------


class Provenance(Strict):
    source_system: str = "U.S. Department of the Treasury"
    source_file: str | None = None
    source_url: str | None = None
    source_sha256: str | None = None
    downloaded_at_utc: dt.datetime | None = None


class Envelope(Strict):
    """Present on every result, so a payload is self-describing in isolation."""

    contract_version: str = "1.0"
    dataset_snapshot_id: str = Field(
        description="Content-addressed id of the data vintage. Changes if and "
                    "only if the underlying Treasury files change, so results "
                    "may be cached against it."
    )
    as_of: dt.date | None = None
    data_classification: DataClassification = "REAL_MARKET_DATA"
    warnings: list[str] = Field(default_factory=list)


# --- rates ------------------------------------------------------------------


class RatePoint(Strict):
    series_code: str
    display_name: str
    rate_kind: Literal["nominal", "real"]
    quote_basis: QuoteBasis
    tenor_label: str | None = None
    tenor_months: Decimal | None = Field(
        default=None,
        description="Fractional by design: BC_1_5MONTH is genuinely 1.5 months "
                    "and a 4-week bill is 0.92. Rounding to integer would merge "
                    "distinct points on the curve.",
    )
    observation_date: dt.date
    rate_percent: Decimal = Field(description="In percent as published: 3.72 means 3.72%.")
    unit: Literal["percent"] = "percent"
    data_classification: Literal["REAL_MARKET_DATA"] = "REAL_MARKET_DATA"


class SeriesInfo(Strict):
    series_code: str
    display_name: str
    data_key: str
    rate_kind: Literal["nominal", "real"]
    quote_basis: QuoteBasis
    tenor_label: str | None = None
    tenor_months: Decimal | None = None
    is_composite: bool = False
    first_observation: dt.date | None = None
    last_observation: dt.date | None = None
    observation_count: int | None = None


class DatasetInfo(Strict):
    data_key: str
    title: str
    shape: str
    documented_first_year: int
    caveat: str = Field(
        description="The market-risk warning that belongs with these numbers. "
                    "Carried in the payload so it cannot be separated from the data."
    )
    series_count: int
    first_observation: dt.date | None = None
    last_observation: dt.date | None = None


# --- results ----------------------------------------------------------------


class DatasetPage(Strict):
    envelope: Envelope
    datasets: list[DatasetInfo]


class SeriesPage(Strict):
    envelope: Envelope
    series: list[SeriesInfo]
    next_cursor: str | None = None


class SeriesSearchResult(Strict):
    envelope: Envelope
    query: str
    matches: list[SeriesInfo]
    ambiguous: bool = Field(
        default=False,
        description="True when matches span more than one rate_kind, e.g. "
                    "'30 year' matching both BC_30YEAR and TC_30YEAR.",
    )


class CoverageResult(Strict):
    envelope: Envelope
    series: list[SeriesInfo]


class CurveResult(Strict):
    envelope: Envelope
    curve_family: CurveFamily
    observation_date: dt.date
    requested_date: dt.date | None = None
    date_policy: DatePolicy = "exact"
    date_was_shifted: bool = False
    points: list[RatePoint]
    provenance: Provenance


class RateHistoryPage(Strict):
    envelope: Envelope
    items: list[RatePoint]
    returned: int
    next_cursor: str | None = None
    provenance: Provenance


class CurveHistorySummary(Strict):
    """Deliberately carries no rates.

    A 250-day, 11-tenor matrix is ~2,750 numbers. Putting them in
    `structured_content` burns model context to no purpose - the model does not
    reason over individual yields, it decides *that* a history is needed and
    hands it to the risk engine. So the numbers travel in the result's `_meta`
    channel, which the host reads and forwards; the model sees this summary and
    can still verify shape, completeness and provenance.
    """

    envelope: Envelope
    curve_family: CurveFamily
    as_of_date: dt.date
    tenors_months: list[Decimal]
    trading_days_requested: int
    trading_days_returned: int
    first_date: dt.date | None = None
    last_date: dt.date | None = None
    point_count: int
    missing_policy: MissingPolicy
    excluded_dates: int = 0
    excluded_date_sample: list[dt.date] = Field(default_factory=list)
    unit: Literal["percent"] = "percent"
    quote_basis: QuoteBasis = "par_coupon_semiannual"
    meta_key: str = Field(
        description="Key under which the numeric matrix is published in the "
                    "result's _meta. The host reads it; the model does not need to."
    )
    provenance: Provenance


class ProvenancedObservation(Strict):
    envelope: Envelope
    observation: RatePoint
    provenance: Provenance
    lineage: dict[str, Any] = Field(
        description="How this number reached the database: Treasury URL, raw "
                    "file, its SHA-256, and when it was downloaded."
    )


# --- portfolio (SYNTHETIC) --------------------------------------------------


class InstrumentInfo(Strict):
    instrument_id: str
    instrument_type: Literal["FIXED_RATE_BOND"]
    display_name: str
    currency: str
    face_value: Decimal
    coupon_rate_pct: Decimal
    issue_date: dt.date
    maturity_date: dt.date
    coupon_frequency: int
    day_count: Literal["ACT_ACT"]
    rate_kind: Literal["nominal", "real"]
    data_classification: Literal["SYNTHETIC_DEMO"] = "SYNTHETIC_DEMO"


class PositionInfo(Strict):
    instrument: InstrumentInfo
    face_notional: Decimal


class PortfolioSummary(Strict):
    portfolio_id: str
    name: str
    description: str | None = None
    base_currency: str
    seed_version: str
    position_count: int
    data_classification: Literal["SYNTHETIC_DEMO"] = "SYNTHETIC_DEMO"


class PortfolioSnapshot(Strict):
    envelope: Envelope
    portfolio: PortfolioSummary
    positions: list[PositionInfo]
    synthetic_warning: str = (
        "SYNTHETIC_DEMO. These positions are invented for demonstration. They "
        "are not a real book and must never be presented as one. The market "
        "data they are valued against is real and verified; the book is not."
    )


class PortfolioList(Strict):
    envelope: Envelope
    portfolios: list[PortfolioSummary]


class ScenarioInfo(Strict):
    scenario_id: str
    name: str
    description: str | None = None
    scenario_type: Literal["TENOR_VECTOR_BP", "HISTORICAL_REPLAY"]
    shock_definition: dict[str, Any]
    data_classification: Literal["SYNTHETIC_DEMO"] = "SYNTHETIC_DEMO"


class ScenarioList(Strict):
    envelope: Envelope
    scenarios: list[ScenarioInfo]
