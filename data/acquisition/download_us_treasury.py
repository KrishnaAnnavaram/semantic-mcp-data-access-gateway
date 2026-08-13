#!/usr/bin/env python3
"""Acquire, validate and organise the official U.S. Department of the Treasury
daily interest-rate datasets.

Source of truth (verified 2026-08-11):

  * https://home.treasury.gov/treasury-daily-interest-rate-xml-feed
  * https://home.treasury.gov/resource-center/data-chart-center/interest-rates/
    daily-treasury-rate-archives

Request structure documented by Treasury::

    BaseURL  https://home.treasury.gov
    Endpoint /resource-center/data-chart-center/interest-rates/pages/xml
    Params   ?data=<data key>&field_tdr_date_value=<yyyy>

The script downloads one raw XML document per (dataset, year), never mutates a
raw file once written, then derives a normalised CSV per dataset plus a
download manifest, a schema report and a data-quality validation report.

No financial transformation of any kind is performed: values are parsed and
typed, never derived, interpolated, filled or smoothed.

Usage::

    python -m acquisition.download_us_treasury
    python -m acquisition.download_us_treasury --dataset daily_treasury_yield_curve
    python -m acquisition.download_us_treasury --start-year 2020 --end-year 2026
    python -m acquisition.download_us_treasury --refresh
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    import requests
except ImportError:  # pragma: no cover - dependency guard
    sys.exit("This script requires 'requests'.  Install it with: pip install requests")


LOGGER = logging.getLogger("us_treasury")

# This file lives at <repo>/data/acquisition/, so the repository root is two
# levels up. Anchoring on the repo rather than on this file's parent means
# moving the script cannot silently relocate the whole data tree.
from paths import REPO_ROOT  # noqa: E402  (script-relative; see data/acquisition/paths.py)

SOURCE_ORGANISATION = "U.S. Department of the Treasury"
BASE_URL = "https://home.treasury.gov"
ENDPOINT = "/resource-center/data-chart-center/interest-rates/pages/xml"
FEED_URL = f"{BASE_URL}{ENDPOINT}"

DOCUMENTATION_URLS = [
    "https://home.treasury.gov/treasury-daily-interest-rate-xml-feed",
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates"
    "/daily-treasury-rate-archives",
]

# Atom + Microsoft ADO.NET data-services namespaces used by the Treasury feed.
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
    "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
}

USER_AGENT = (
    "us-treasury-rate-downloader/1.0 (market-risk data acquisition; "
    "contact: repository maintainer)"
)

# Tokens Treasury uses for "no observation".  Converted to NULL, never to 0.
MISSING_TOKENS = {"", "n/a", "na", "n.a.", "null", "none", "-", "--"}

EDM_NUMERIC_TYPES = {
    "Edm.Double",
    "Edm.Decimal",
    "Edm.Single",
    "Edm.Int16",
    "Edm.Int32",
    "Edm.Int64",
    "Edm.Byte",
    "Edm.SByte",
}
EDM_INTEGER_TYPES = {"Edm.Int16", "Edm.Int32", "Edm.Int64", "Edm.Byte", "Edm.SByte"}
EDM_DATE_TYPES = {"Edm.DateTime", "Edm.DateTimeOffset"}

# Plausibility band for a published Treasury rate, in percent.  Treasury rates
# CAN be negative (real/TIPS yields routinely are), so the band is deliberately
# wide and is used to flag values for human review only - nothing is dropped.
RATE_PLAUSIBLE_MIN = -10.0
RATE_PLAUSIBLE_MAX = 25.0
# Day-over-day move, in percentage points, above which a value is flagged.
RATE_JUMP_THRESHOLD = 1.50


# --------------------------------------------------------------------------
# Dataset registry
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DatasetSpec:
    """One Treasury interest-rate dataset as published by the XML feed."""

    data_key: str
    title: str
    slug: str
    # "Available From" year, per Treasury's Data Availability table on
    # https://home.treasury.gov/treasury-daily-interest-rate-xml-feed
    first_year: int
    date_field: str
    natural_key: tuple[str, ...]
    shape: str  # "wide" (one row per date) or "long" (one row per date+series)
    description: str
    caveat: str

    @property
    def raw_dir_name(self) -> str:
        return self.slug


DATASETS: dict[str, DatasetSpec] = {
    "daily_treasury_yield_curve": DatasetSpec(
        data_key="daily_treasury_yield_curve",
        title="Daily Treasury Par Yield Curve Rates",
        slug="par_yield_curve",
        first_year=1990,
        date_field="NEW_DATE",
        natural_key=("NEW_DATE",),
        shape="wide",
        description=(
            "Par yields on the most recently auctioned Treasury securities, "
            "quoted on a bond-equivalent, semi-annual coupon basis and derived "
            "by Treasury's monotone-convex par-yield curve methodology."
        ),
        caveat=(
            "These are PAR yields, not zero-coupon/spot rates and not "
            "executable market prices. BC_30YEAR is absent 2003-2005 because "
            "the 30-year bond was discontinued in 2002 and reintroduced in "
            "2006. BC_30YEARDISPLAY is Treasury's display variant and is "
            "published as a literal 0 for every date before 2011-01-03 - that "
            "0 is a placeholder, not a 0.00% yield. Use BC_30YEAR as the "
            "30-year series."
        ),
    ),
    "daily_treasury_bill_rates": DatasetSpec(
        data_key="daily_treasury_bill_rates",
        title="Daily Treasury Bill Rates",
        slug="bill_rates",
        first_year=2002,
        date_field="INDEX_DATE",
        natural_key=("INDEX_DATE",),
        shape="wide",
        description=(
            "Closing market bid discount rates and the corresponding "
            "coupon-equivalent yields for the most recently auctioned bills at "
            "each benchmark tenor, together with the CUSIP and maturity date of "
            "the bill actually quoted."
        ),
        caveat=(
            "ROUND_B1_CLOSE_* / CS_*_CLOSE_AVG are DISCOUNT rates on a "
            "bank-discount (actual/360) basis. ROUND_B1_YIELD_* / "
            "CS_*_YIELD_AVG are COUPON-EQUIVALENT yields. The two are not "
            "interchangeable and must not be mixed on one curve."
        ),
    ),
    "daily_treasury_long_term_rate": DatasetSpec(
        data_key="daily_treasury_long_term_rate",
        title="Daily Treasury Long-Term Rates",
        slug="long_term_rates",
        first_year=2000,
        date_field="QUOTE_DATE",
        natural_key=("QUOTE_DATE", "RATE_TYPE"),
        shape="long",
        description=(
            "Long-term rate series published in tall format: one row per "
            "quote date per RATE_TYPE (e.g. BC_20year, Over_10_Years, "
            "Real_Rate), with the extrapolation factor Treasury applied."
        ),
        caveat=(
            "The natural key is (QUOTE_DATE, RATE_TYPE) - a date legitimately "
            "carries several rows. The Real_Rate rows inside this nominal feed "
            "are Treasury's long-term real rate average; do not merge them with "
            "the nominal series."
        ),
    ),
    "daily_treasury_real_yield_curve": DatasetSpec(
        data_key="daily_treasury_real_yield_curve",
        title="Daily Treasury Par Real Yield Curve Rates",
        slug="real_yield_curve",
        first_year=2003,
        date_field="NEW_DATE",
        natural_key=("NEW_DATE",),
        shape="wide",
        description=(
            "Par real yield curve rates derived from Treasury Inflation "
            "Protected Securities (TIPS) at the 5, 7, 10, 20 and 30 year points."
        ),
        caveat=(
            "REAL yields (TIPS-based), not nominal. Negative values are normal "
            "and correct - they must never be treated as errors or clipped. The "
            "nominal-minus-real difference is a breakeven-inflation calculation "
            "and is deliberately not computed here."
        ),
    ),
    "daily_treasury_real_long_term": DatasetSpec(
        data_key="daily_treasury_real_long_term",
        title="Daily Treasury Real Long-Term Rates",
        slug="real_long_term_rates",
        first_year=2000,
        date_field="QUOTE_DATE",
        natural_key=("QUOTE_DATE",),
        shape="wide",
        description=(
            "Treasury's long-term real rate average: the unweighted average of "
            "bid real yields on TIPS with remaining maturity of more than 10 "
            "years."
        ),
        caveat=(
            "REAL (TIPS) rate. Coverage is interrupted where Treasury suspended "
            "publication; missing days are genuinely absent, not zero."
        ),
    ),
}

# Columns that are identifiers/labels rather than rates.  Used only to decide
# which numeric columns get plausibility screening.
NON_RATE_COLUMN_PATTERNS = (
    re.compile(r"(^|_)ID$", re.IGNORECASE),
    re.compile(r"^DailyTreasury.*Id$", re.IGNORECASE),
    re.compile(r"CUSIP", re.IGNORECASE),
    re.compile(r"DATE", re.IGNORECASE),
    re.compile(r"WEEK$", re.IGNORECASE),
    re.compile(r"RATE_TYPE", re.IGNORECASE),
    re.compile(r"UNAVAIL_REASON", re.IGNORECASE),
    re.compile(r"EXTRAPOLATION_FACTOR", re.IGNORECASE),
)

# Number of consecutive leading zero observations above which an all-zero run
# at the start of a column's history is treated as a placeholder rather than a
# genuine 0.00% print.
SENTINEL_ZERO_MIN_RUN = 250

# Full-day U.S. bond-market / Treasury-publication closures that are NOT
# federal holidays and not Good Friday.  Used to suppress known-good gaps in
# the business-day completeness check.  Anything not listed here is reported
# for review.
KNOWN_SPECIAL_CLOSURES: dict[str, str] = {
    "1994-04-27": "National day of mourning - President Nixon",
    "2001-09-11": "September 11 attacks - markets closed",
    "2001-09-12": "September 11 attacks - markets closed",
    "2001-09-13": "September 11 attacks - markets closed",
    "2001-09-14": "September 11 attacks - markets closed",
    "2004-06-11": "National day of mourning - President Reagan",
    "2012-10-29": "Hurricane Sandy",
    "2012-10-30": "Hurricane Sandy",
    "2018-12-05": "National day of mourning - President G.H.W. Bush",
    "2025-01-09": "National day of mourning - President Carter",
}


# --------------------------------------------------------------------------
# Calendar helpers (completeness checking only - never used to create data)
# --------------------------------------------------------------------------


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """n-th (1-based) `weekday` of `month`; n = -1 means the last one."""
    if n > 0:
        first = dt.date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + dt.timedelta(days=offset + 7 * (n - 1))
    last_day = (dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1))
    last_day -= dt.timedelta(days=1)
    offset = (last_day.weekday() - weekday) % 7
    return last_day - dt.timedelta(days=offset)


def _observed(day: dt.date) -> dt.date:
    """Weekend federal holidays are observed Friday/Monday."""
    if day.weekday() == 5:
        return day - dt.timedelta(days=1)
    if day.weekday() == 6:
        return day + dt.timedelta(days=1)
    return day


def easter_sunday(year: int) -> dt.date:
    """Gregorian Easter (anonymous computus)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def good_friday(year: int) -> dt.date:
    """The U.S. bond market closes on Good Friday; Treasury publishes nothing."""
    return easter_sunday(year) - dt.timedelta(days=2)


def us_federal_holidays(year: int) -> set[dt.date]:
    """Federal holidays observed in `year` (Treasury markets closed)."""
    days = {
        _observed(dt.date(year, 1, 1)),                      # New Year's Day
        _nth_weekday(year, 1, 0, 3),                         # MLK Jr. (1986-)
        _nth_weekday(year, 2, 0, 3),                         # Washington's Birthday
        _nth_weekday(year, 5, 0, -1),                        # Memorial Day
        _observed(dt.date(year, 7, 4)),                      # Independence Day
        _nth_weekday(year, 9, 0, 1),                         # Labor Day
        _nth_weekday(year, 10, 0, 2),                        # Columbus Day
        _observed(dt.date(year, 11, 11)),                    # Veterans Day
        _nth_weekday(year, 11, 3, 4),                        # Thanksgiving
        _observed(dt.date(year, 12, 25)),                    # Christmas
    }
    if year >= 2021:
        days.add(_observed(dt.date(year, 6, 19)))            # Juneteenth
    # New Year's Day of the following year can be observed on 31 December.
    nyd_next = _observed(dt.date(year + 1, 1, 1))
    if nyd_next.year == year:
        days.add(nyd_next)
    return days


def expected_business_days(start: dt.date, end: dt.date) -> list[dt.date]:
    """Weekdays in [start, end] on which Treasury is expected to publish.

    Excludes weekends, U.S. federal holidays, Good Friday (bond market closed)
    and the recorded ad-hoc closures.  Used purely to *detect* gaps; it never
    creates, fills or infers an observation.
    """
    holidays: set[dt.date] = set()
    for year in range(start.year, end.year + 1):
        holidays |= us_federal_holidays(year)
        holidays.add(good_friday(year))
    closures = {dt.date.fromisoformat(k) for k in KNOWN_SPECIAL_CLOSURES}
    out: list[dt.date] = []
    day = start
    one = dt.timedelta(days=1)
    while day <= end:
        if day.weekday() < 5 and day not in holidays and day not in closures:
            out.append(day)
        day += one
    return out


# --------------------------------------------------------------------------
# HTTP client
# --------------------------------------------------------------------------


class TreasuryFeedError(RuntimeError):
    """Raised when the Treasury feed cannot be retrieved or is unusable."""


@dataclass
class FetchResult:
    url: str
    status_code: int
    content_type: str
    content: bytes
    attempts: int
    elapsed_seconds: float
    fetched_at_utc: str


class TreasuryFeedClient:
    """Thin, well-behaved HTTP client for the Treasury XML feed."""

    def __init__(
        self,
        *,
        connect_timeout: float = 15.0,
        read_timeout: float = 180.0,
        max_attempts: int = 5,
        backoff_base: float = 1.5,
        backoff_cap: float = 60.0,
        polite_delay: float = 0.4,
        session: "requests.Session | None" = None,
    ) -> None:
        self.timeout = (connect_timeout, read_timeout)
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.polite_delay = polite_delay
        self.session = session or requests.Session()
        self.session.headers.update(
            {"User-Agent": USER_AGENT, "Accept": "application/xml, text/xml, */*"}
        )

    RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504, 522, 524}

    def fetch_year(self, data_key: str, year: int) -> FetchResult:
        return self._fetch({"data": data_key, "field_tdr_date_value": str(year)})

    def fetch_month(self, data_key: str, year: int, month: int) -> FetchResult:
        return self._fetch(
            {"data": data_key, "field_tdr_date_value_month": f"{year}{month:02d}"}
        )

    def _fetch(self, params: dict[str, str]) -> FetchResult:
        last_error: str | None = None
        started = time.monotonic()
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(
                    FEED_URL, params=params, timeout=self.timeout
                )
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                LOGGER.warning(
                    "  transport error (attempt %d/%d): %s",
                    attempt,
                    self.max_attempts,
                    last_error,
                )
            else:
                if response.status_code == 200:
                    content_type = response.headers.get("Content-Type", "")
                    if "xml" not in content_type.lower():
                        last_error = f"unexpected Content-Type {content_type!r}"
                        LOGGER.warning(
                            "  %s (attempt %d/%d)",
                            last_error,
                            attempt,
                            self.max_attempts,
                        )
                    else:
                        if self.polite_delay:
                            time.sleep(self.polite_delay)
                        return FetchResult(
                            url=response.url,
                            status_code=response.status_code,
                            content_type=content_type,
                            content=response.content,
                            attempts=attempt,
                            elapsed_seconds=round(time.monotonic() - started, 3),
                            fetched_at_utc=utc_now_iso(),
                        )
                elif response.status_code in self.RETRYABLE_STATUS:
                    last_error = f"HTTP {response.status_code}"
                    LOGGER.warning(
                        "  retryable %s (attempt %d/%d)",
                        last_error,
                        attempt,
                        self.max_attempts,
                    )
                else:
                    raise TreasuryFeedError(
                        f"HTTP {response.status_code} for {response.url} "
                        "(non-retryable)"
                    )

            if attempt < self.max_attempts:
                delay = min(self.backoff_cap, self.backoff_base ** attempt)
                delay += random.uniform(0, 0.5 * delay)  # jitter
                LOGGER.info("  backing off %.1fs", delay)
                time.sleep(delay)

        raise TreasuryFeedError(
            f"exhausted {self.max_attempts} attempts for {FEED_URL} "
            f"params={params}: {last_error}"
        )


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


@dataclass
class ParsedProperty:
    name: str
    raw_text: str | None
    edm_type: str | None


@dataclass
class ParsedFeed:
    title: str | None
    updated: str | None
    records: list[dict[str, ParsedProperty]]
    column_order: list[str]


def parse_feed(content: bytes) -> ParsedFeed:
    """Parse a Treasury Atom/OData feed into ordered property dictionaries."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise TreasuryFeedError(f"response is not well-formed XML: {exc}") from exc

    if not root.tag.endswith("}feed") and root.tag != "feed":
        raise TreasuryFeedError(f"unexpected XML root element {root.tag!r}")

    title_el = root.find("atom:title", NS)
    updated_el = root.find("atom:updated", NS)

    records: list[dict[str, ParsedProperty]] = []
    column_order: list[str] = []
    seen: set[str] = set()

    for entry in root.findall("atom:entry", NS):
        props_el = entry.find("atom:content/m:properties", NS)
        if props_el is None:
            continue
        record: dict[str, ParsedProperty] = {}
        for prop in props_el:
            name = prop.tag.split("}", 1)[-1].strip()
            edm_type = prop.get(f"{{{NS['m']}}}type")
            is_null = prop.get(f"{{{NS['m']}}}null") == "true"
            text = None if is_null else (prop.text if prop.text is not None else "")
            record[name] = ParsedProperty(name, text, edm_type)
            if name not in seen:
                seen.add(name)
                column_order.append(name)
        records.append(record)

    return ParsedFeed(
        title=(title_el.text if title_el is not None else None),
        updated=(updated_el.text if updated_el is not None else None),
        records=records,
        column_order=column_order,
    )


def is_missing(text: str | None) -> bool:
    return text is None or text.strip().lower() in MISSING_TOKENS


def normalise_value(prop: ParsedProperty) -> tuple[Any, str | None]:
    """Return (value, error).  Missing observations become None - never zero."""
    if is_missing(prop.raw_text):
        return None, None

    text = (prop.raw_text or "").strip()
    edm = prop.edm_type

    if edm in EDM_DATE_TYPES:
        parsed = parse_treasury_datetime(text)
        if parsed is None:
            return text, f"unparseable date {text!r}"
        date_part, time_part = parsed
        return (date_part if time_part == "00:00:00" else f"{date_part}T{time_part}"), None

    if edm in EDM_NUMERIC_TYPES:
        try:
            if edm in EDM_INTEGER_TYPES:
                return int(text), None
            return float(text), None
        except ValueError:
            return text, f"unparseable numeric {text!r} (declared {edm})"

    # Untyped => Treasury string field (CUSIP, RATE_TYPE, reason codes...).
    # A few string fields still carry dates, e.g. CF_NEW_DATE = MM/DD/YYYY.
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", text)
    if match:
        month, day, year = match.groups()
        try:
            return dt.date(int(year), int(month), int(day)).isoformat(), None
        except ValueError:
            return text, f"invalid calendar date {text!r}"
    return text, None


def parse_treasury_datetime(text: str) -> tuple[str, str] | None:
    """Split an Edm.DateTime literal into ('YYYY-MM-DD', 'HH:MM:SS')."""
    candidate = text.strip().rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            parsed = dt.datetime.strptime(candidate, fmt)
        except ValueError:
            continue
        return parsed.date().isoformat(), parsed.time().isoformat()
    return None


# --------------------------------------------------------------------------
# Filesystem layout
# --------------------------------------------------------------------------


@dataclass
class Layout:
    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "raw" / "us_treasury"

    @property
    def processed(self) -> Path:
        return self.root / "processed" / "us_treasury"

    @property
    def metadata(self) -> Path:
        return self.root / "metadata" / "us_treasury"

    def raw_dir(self, spec: DatasetSpec) -> Path:
        return self.raw / spec.raw_dir_name

    def raw_file(self, spec: DatasetSpec, year: int) -> Path:
        return self.raw_dir(spec) / f"{spec.data_key}_{year}.xml"

    def processed_file(self, spec: DatasetSpec) -> Path:
        return self.processed / f"{spec.slug}.csv"

    def ensure(self, specs: Iterable[DatasetSpec]) -> None:
        for spec in specs:
            self.raw_dir(spec).mkdir(parents=True, exist_ok=True)
        self.processed.mkdir(parents=True, exist_ok=True)
        self.metadata.mkdir(parents=True, exist_ok=True)


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        LOGGER.warning("could not read %s; ignoring", path)
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=False, default=str) + "\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# Download stage
# --------------------------------------------------------------------------


@dataclass
class YearOutcome:
    spec: DatasetSpec
    year: int
    entry: dict[str, Any]
    parsed: ParsedFeed | None
    path: Path | None

    @property
    def ok(self) -> bool:
        return self.entry.get("status") in {"success", "cached"}


class Downloader:
    def __init__(
        self,
        client: TreasuryFeedClient,
        layout: Layout,
        *,
        refresh: bool = False,
        refresh_current_year: bool = True,
        previous_manifest: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.client = client
        self.layout = layout
        self.refresh = refresh
        self.refresh_current_year = refresh_current_year
        self.previous = previous_manifest or {}

    @staticmethod
    def manifest_id(spec: DatasetSpec, year: int) -> str:
        return f"{spec.data_key}:{year}"

    def download_year(self, spec: DatasetSpec, year: int) -> YearOutcome:
        path = self.layout.raw_file(spec, year)
        current_year = dt.datetime.now(dt.timezone.utc).year
        must_refresh = (
            self.refresh
            or (self.refresh_current_year and year >= current_year)
        )

        if path.exists() and not must_refresh:
            outcome = self._reuse_cached(spec, year, path)
            if outcome is not None:
                return outcome

        url = f"{FEED_URL}?data={spec.data_key}&field_tdr_date_value={year}"
        LOGGER.info("GET  %s", url)
        try:
            result = self.client.fetch_year(spec.data_key, year)
            parsed = parse_feed(result.content)
        except TreasuryFeedError as exc:
            LOGGER.error("  FAILED %s %s: %s", spec.data_key, year, exc)
            return YearOutcome(
                spec=spec,
                year=year,
                parsed=None,
                path=None,
                entry=self._entry(
                    spec,
                    year,
                    url=url,
                    status="failed",
                    error=str(exc),
                    downloaded_at_utc=utc_now_iso(),
                ),
            )

        # Write raw bytes exactly as received; raw files are immutable
        # afterwards.  A temporary file plus replace keeps partial writes from
        # ever being visible as a "valid" raw artefact.
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(result.content)
        os.replace(tmp, path)

        records = len(parsed.records)
        dates = self._observation_dates(spec, parsed)
        LOGGER.info(
            "  HTTP %s  %d records  %s  ->  %s",
            result.status_code,
            records,
            f"{dates[0]} .. {dates[-1]}" if dates else "no observations",
            path.name,
        )

        return YearOutcome(
            spec=spec,
            year=year,
            parsed=parsed,
            path=path,
            entry=self._entry(
                spec,
                year,
                url=result.url,
                status="success",
                downloaded_at_utc=result.fetched_at_utc,
                http_status=result.status_code,
                content_type=result.content_type,
                attempts=result.attempts,
                elapsed_seconds=result.elapsed_seconds,
                bytes_downloaded=len(result.content),
                path=path,
                records=records,
                dates=dates,
                feed_updated=parsed.updated,
                columns=parsed.column_order,
            ),
        )

    def collect_existing(
        self, spec: DatasetSpec, exclude_years: set[int]
    ) -> list[YearOutcome]:
        """Load raw files already on disk for years not requested this run.

        The processed CSV is always rebuilt from every raw file present, so a
        partial run (`--start-year 2020`) refreshes those years without
        truncating the dataset's history.
        """
        outcomes: list[YearOutcome] = []
        pattern = re.compile(rf"^{re.escape(spec.data_key)}_(\d{{4}})\.xml$")
        for path in sorted(self.layout.raw_dir(spec).glob(f"{spec.data_key}_*.xml")):
            match = pattern.match(path.name)
            if not match:
                continue
            year = int(match.group(1))
            if year in exclude_years:
                continue
            outcome = self._reuse_cached(spec, year, path)
            if outcome is not None:
                outcomes.append(outcome)
        return outcomes

    def _reuse_cached(
        self, spec: DatasetSpec, year: int, path: Path
    ) -> YearOutcome | None:
        try:
            parsed = parse_feed(path.read_bytes())
        except (TreasuryFeedError, OSError) as exc:
            LOGGER.warning(
                "  cached %s unusable (%s); re-downloading", path.name, exc
            )
            return None

        prior = self.previous.get(self.manifest_id(spec, year), {})
        dates = self._observation_dates(spec, parsed)
        LOGGER.info(
            "SKIP %s %s (cached, %d records)", spec.data_key, year, len(parsed.records)
        )
        return YearOutcome(
            spec=spec,
            year=year,
            parsed=parsed,
            path=path,
            entry=self._entry(
                spec,
                year,
                url=prior.get(
                    "source_url",
                    f"{FEED_URL}?data={spec.data_key}&field_tdr_date_value={year}",
                ),
                status="cached",
                downloaded_at_utc=prior.get("downloaded_at_utc"),
                http_status=prior.get("http_status", 200),
                content_type=prior.get("content_type", "text/xml"),
                attempts=prior.get("attempts"),
                path=path,
                records=len(parsed.records),
                dates=dates,
                feed_updated=parsed.updated,
                columns=parsed.column_order,
                bytes_downloaded=path.stat().st_size,
            ),
        )

    @staticmethod
    def _observation_dates(spec: DatasetSpec, parsed: ParsedFeed) -> list[str]:
        dates: list[str] = []
        for record in parsed.records:
            prop = record.get(spec.date_field)
            if prop is None:
                continue
            value, _ = normalise_value(prop)
            if isinstance(value, str) and value:
                dates.append(value[:10])
        return sorted(dates)

    def _entry(
        self,
        spec: DatasetSpec,
        year: int,
        *,
        url: str,
        status: str,
        downloaded_at_utc: str | None = None,
        http_status: int | None = None,
        content_type: str | None = None,
        attempts: int | None = None,
        elapsed_seconds: float | None = None,
        bytes_downloaded: int | None = None,
        path: Path | None = None,
        records: int = 0,
        dates: Sequence[str] | None = None,
        feed_updated: str | None = None,
        columns: Sequence[str] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        dates = list(dates or [])
        return {
            "manifest_id": self.manifest_id(spec, year),
            "source": SOURCE_ORGANISATION,
            "source_documentation": DOCUMENTATION_URLS,
            "dataset": spec.title,
            "data_key": spec.data_key,
            "requested_year": year,
            "source_url": url,
            "downloaded_at_utc": downloaded_at_utc,
            "http_status": http_status,
            "content_type": content_type,
            "request_attempts": attempts,
            "elapsed_seconds": elapsed_seconds,
            "bytes_downloaded": bytes_downloaded,
            "output_file": (
                path.relative_to(self.layout.root.parent).as_posix()
                if path is not None
                else None
            ),
            "sha256": sha256_of(path) if path is not None and path.exists() else None,
            "records": records,
            "columns_in_response": list(columns or []),
            "earliest_observation_date": dates[0] if dates else None,
            "latest_observation_date": dates[-1] if dates else None,
            "feed_updated_timestamp": feed_updated,
            "status": status,
            "success": status in {"success", "cached"},
            "error": error,
        }


# --------------------------------------------------------------------------
# Normalisation stage
# --------------------------------------------------------------------------


@dataclass
class NormalisedDataset:
    spec: DatasetSpec
    columns: list[str]
    rows: list[dict[str, Any]]
    column_first_year: dict[str, int]
    column_last_year: dict[str, int]
    column_years: dict[str, list[int]]
    column_edm_types: dict[str, set[str]]
    parse_errors: list[dict[str, Any]]
    exact_duplicates: list[dict[str, Any]]
    year_record_counts: dict[int, int]
    rows_before_dedup: int


LINEAGE_COLUMNS = ("_source_year", "_source_file")


def normalise(spec: DatasetSpec, outcomes: Sequence[YearOutcome]) -> NormalisedDataset:
    """Turn per-year parsed feeds into one chronologically ordered table.

    Only representational changes are made: date literals become YYYY-MM-DD,
    Treasury's missing tokens become NULL, and typed numerics become numbers.
    No value is imputed, filled, rescaled or derived.
    """
    columns: list[str] = []
    seen: set[str] = set()
    first_year: dict[str, int] = {}
    last_year: dict[str, int] = {}
    years_seen: dict[str, list[int]] = {}
    edm_types: dict[str, set[str]] = {}
    parse_errors: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    year_counts: dict[int, int] = {}

    for outcome in sorted(outcomes, key=lambda o: o.year):
        if outcome.parsed is None:
            continue
        year = outcome.year
        year_counts[year] = len(outcome.parsed.records)
        for name in outcome.parsed.column_order:
            if name not in seen:
                seen.add(name)
                columns.append(name)
                first_year[name] = year
            last_year[name] = year
            years_seen.setdefault(name, []).append(year)

        source_file = outcome.path.name if outcome.path else None
        for index, record in enumerate(outcome.parsed.records):
            row: dict[str, Any] = {}
            for name, prop in record.items():
                value, error = normalise_value(prop)
                row[name] = value
                if prop.edm_type:
                    edm_types.setdefault(name, set()).add(prop.edm_type)
                elif not is_missing(prop.raw_text):
                    edm_types.setdefault(name, set()).add("(untyped string)")
                if error:
                    parse_errors.append(
                        {
                            "data_key": spec.data_key,
                            "year": year,
                            "record_index": index,
                            "column": name,
                            "raw_value": prop.raw_text,
                            "error": error,
                        }
                    )
            row["_source_year"] = year
            row["_source_file"] = source_file
            rows.append(row)

    rows_before_dedup = len(rows)

    # Exact duplicates are removed only after being recorded.  Comparison uses
    # source columns only - lineage columns are excluded so that a record
    # genuinely republished in two year files is still detected.
    deduped: list[dict[str, Any]] = []
    fingerprints: dict[tuple, dict[str, Any]] = {}
    exact_duplicates: list[dict[str, Any]] = []
    for row in rows:
        fingerprint = tuple(row.get(col) for col in columns)
        prior = fingerprints.get(fingerprint)
        if prior is not None:
            exact_duplicates.append(
                {
                    "data_key": spec.data_key,
                    "natural_key": {k: row.get(k) for k in spec.natural_key},
                    "kept_from": prior.get("_source_file"),
                    "dropped_from": row.get("_source_file"),
                }
            )
            continue
        fingerprints[fingerprint] = row
        deduped.append(row)

    def sort_key(row: dict[str, Any]) -> tuple:
        parts: list[str] = []
        for key in spec.natural_key:
            value = row.get(key)
            parts.append("" if value is None else str(value))
        return tuple(parts)

    deduped.sort(key=sort_key)

    ordered_columns = [spec.date_field] + [c for c in columns if c != spec.date_field]
    return NormalisedDataset(
        spec=spec,
        columns=ordered_columns,
        rows=deduped,
        column_first_year=first_year,
        column_last_year=last_year,
        column_years={k: sorted(set(v)) for k, v in years_seen.items()},
        column_edm_types=edm_types,
        parse_errors=parse_errors,
        exact_duplicates=exact_duplicates,
        year_record_counts=year_counts,
        rows_before_dedup=rows_before_dedup,
    )


def format_csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        # '.10g' keeps every digit Treasury publishes while avoiding binary
        # float artefacts such as 4.2000000000000002.
        return format(value, ".10g")
    return str(value)


def write_processed_csv(path: Path, dataset: NormalisedDataset) -> None:
    header = list(dataset.columns) + list(LINEAGE_COLUMNS)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for row in dataset.rows:
            writer.writerow([format_csv_value(row.get(col)) for col in header])


# --------------------------------------------------------------------------
# Schema profiling
# --------------------------------------------------------------------------


def infer_type(values: Sequence[Any], edm_types: set[str]) -> str:
    if any(t in EDM_INTEGER_TYPES for t in edm_types):
        return "integer"
    if any(t in EDM_NUMERIC_TYPES for t in edm_types):
        return "numeric"
    if any(t in EDM_DATE_TYPES for t in edm_types):
        return "date"
    non_null = [v for v in values if v is not None]
    if non_null and all(
        isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in non_null
    ):
        return "date"
    if non_null and all(isinstance(v, (int, float)) for v in non_null):
        return "numeric"
    return "string"


def build_schema_report(datasets: Sequence[NormalisedDataset]) -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_at_utc": utc_now_iso(),
        "source": SOURCE_ORGANISATION,
        "source_documentation": DOCUMENTATION_URLS,
        "note": (
            "Schema is discovered from the actual Treasury responses, per year. "
            "Column presence is tracked over time so that the eventual "
            "relational design reflects the source rather than an assumption."
        ),
        "datasets": {},
    }

    for dataset in datasets:
        spec = dataset.spec
        total = len(dataset.rows)
        columns_payload = []
        all_years = sorted(dataset.year_record_counts)
        years_with_data = [y for y in all_years if dataset.year_record_counts[y] > 0]

        for column in dataset.columns:
            values = [row.get(column) for row in dataset.rows]
            non_null = [v for v in values if v is not None]
            examples: list[Any] = []
            for value in non_null:
                if value not in examples:
                    examples.append(value)
                if len(examples) == 3:
                    break
            present_years = dataset.column_years.get(column, [])
            missing_years = [
                y for y in years_with_data if y not in set(present_years)
            ]
            columns_payload.append(
                {
                    "column": column,
                    "inferred_type": infer_type(
                        values, dataset.column_edm_types.get(column, set())
                    ),
                    "source_edm_types": sorted(
                        dataset.column_edm_types.get(column, set())
                    ),
                    "first_year_present": dataset.column_first_year.get(column),
                    "last_year_present": dataset.column_last_year.get(column),
                    "years_present_count": len(present_years),
                    "years_absent_from_response": missing_years,
                    "total_rows": total,
                    "non_null_rows": len(non_null),
                    "null_rows": total - len(non_null),
                    "null_percentage": round(
                        100.0 * (total - len(non_null)) / total, 4
                    )
                    if total
                    else None,
                    "examples": examples,
                }
            )

        added, removed = schema_timeline(dataset, years_with_data)
        report["datasets"][spec.data_key] = {
            "dataset": spec.title,
            "data_key": spec.data_key,
            "shape": spec.shape,
            "date_field": spec.date_field,
            "natural_key": list(spec.natural_key),
            "total_rows": total,
            "total_columns": len(dataset.columns),
            "years_covered": years_with_data,
            "columns": columns_payload,
            "schema_changes": {
                "columns_added_by_year": added,
                "columns_removed_by_year": removed,
            },
            "financial_caveat": spec.caveat,
        }

    return report


def schema_timeline(
    dataset: NormalisedDataset, years: Sequence[int]
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Columns appearing/disappearing between consecutive populated years."""
    per_year: dict[int, set[str]] = {y: set() for y in years}
    for column, column_years in dataset.column_years.items():
        for year in column_years:
            if year in per_year:
                per_year[year].add(column)

    added: dict[str, list[str]] = {}
    removed: dict[str, list[str]] = {}
    previous: set[str] | None = None
    for year in years:
        current = per_year[year]
        if previous is None:
            added[str(year)] = sorted(current)
        else:
            new = sorted(current - previous)
            gone = sorted(previous - current)
            if new:
                added[str(year)] = new
            if gone:
                removed[str(year)] = gone
        previous = current
    return added, removed


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def is_rate_column(column: str, inferred_type: str) -> bool:
    if inferred_type not in {"numeric"}:
        return False
    return not any(p.search(column) for p in NON_RATE_COLUMN_PATTERNS)


def validate_dataset(
    dataset: NormalisedDataset,
    outcomes: Sequence[YearOutcome],
    requested_years: Sequence[int],
    processed_path: Path,
) -> dict[str, Any]:
    spec = dataset.spec
    rows = dataset.rows
    total = len(rows)
    today = dt.datetime.now(dt.timezone.utc).date()

    warnings: list[str] = []
    errors: list[str] = []

    failed_years = [o.year for o in outcomes if not o.ok]
    empty_years = [
        o.year for o in outcomes if o.ok and o.parsed is not None and not o.parsed.records
    ]
    downloaded_years = sorted(o.year for o in outcomes if o.ok)
    missing_years = [y for y in requested_years if y not in set(downloaded_years)]

    if failed_years:
        errors.append(f"years failed to download: {failed_years}")
    if missing_years:
        errors.append(f"requested years absent from output: {missing_years}")
    if empty_years:
        warnings.append(f"years returning zero observations: {empty_years}")
    if total == 0:
        errors.append("dataset contains no observations")

    # --- dates -----------------------------------------------------------
    date_values: list[str] = []
    malformed_dates: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        value = row.get(spec.date_field)
        if value is None:
            malformed_dates.append({"row_index": index, "value": None})
            continue
        text = str(value)[:10]
        try:
            dt.date.fromisoformat(text)
        except ValueError:
            malformed_dates.append({"row_index": index, "value": value})
            continue
        date_values.append(text)

    if malformed_dates:
        errors.append(f"{len(malformed_dates)} malformed or missing observation dates")

    unique_dates = sorted(set(date_values))
    earliest = unique_dates[0] if unique_dates else None
    latest = unique_dates[-1] if unique_dates else None

    chronological = date_values == sorted(date_values)
    if not chronological:
        errors.append("rows are not in chronological order after normalisation")

    future_dates = [d for d in unique_dates if dt.date.fromisoformat(d) > today]
    if future_dates:
        errors.append(
            f"{len(future_dates)} observation dates are in the future "
            f"(first: {future_dates[0]})"
        )

    # --- business-day completeness ---------------------------------------
    gaps: list[dict[str, str]] = []
    if earliest and latest:
        present = set(unique_dates)
        for day in expected_business_days(
            dt.date.fromisoformat(earliest), dt.date.fromisoformat(latest)
        ):
            if day.isoformat() not in present:
                gaps.append({"date": day.isoformat(), "weekday": day.strftime("%A")})
        if gaps:
            warnings.append(
                f"{len(gaps)} expected business days have no observation "
                "(reported, not filled)"
            )
        unexpected = [
            d
            for d in unique_dates
            if dt.date.fromisoformat(d).weekday() >= 5
        ]
        if unexpected:
            warnings.append(
                f"{len(unexpected)} observations fall on a weekend: "
                f"{unexpected[:5]}"
            )

    longest_gap = None
    if len(unique_dates) > 1:
        parsed_dates = [dt.date.fromisoformat(d) for d in unique_dates]
        spans = [
            (parsed_dates[i + 1] - parsed_dates[i]).days
            for i in range(len(parsed_dates) - 1)
        ]
        widest = max(range(len(spans)), key=lambda i: spans[i])
        longest_gap = {
            "calendar_days": spans[widest],
            "from": parsed_dates[widest].isoformat(),
            "to": parsed_dates[widest + 1].isoformat(),
        }

    # --- duplicates -------------------------------------------------------
    key_counts: dict[tuple, int] = {}
    for row in rows:
        key = tuple(str(row.get(k)) for k in spec.natural_key)
        key_counts[key] = key_counts.get(key, 0) + 1
    duplicate_keys = [
        {
            "natural_key": dict(zip(spec.natural_key, key)),
            "occurrences": count,
        }
        for key, count in sorted(key_counts.items())
        if count > 1
    ]
    if duplicate_keys:
        warnings.append(
            f"{len(duplicate_keys)} natural-key duplicates on "
            f"{list(spec.natural_key)} (retained for review, not deleted)"
        )
    if dataset.exact_duplicates:
        warnings.append(
            f"{len(dataset.exact_duplicates)} exact duplicate source records "
            "removed (documented in this report)"
        )

    # --- missing values ---------------------------------------------------
    column_stats: list[dict[str, Any]] = []
    numeric_issues: list[dict[str, Any]] = []
    suspicious_values: list[dict[str, Any]] = []
    zero_screens: list[dict[str, Any]] = []
    all_null_columns: list[str] = []

    for column in dataset.columns:
        values = [row.get(column) for row in rows]
        non_null = [v for v in values if v is not None]
        inferred = infer_type(values, dataset.column_edm_types.get(column, set()))
        stats = {
            "column": column,
            "inferred_type": inferred,
            "total_rows": total,
            "non_null_rows": len(non_null),
            "null_rows": total - len(non_null),
            "null_percentage": round(100.0 * (total - len(non_null)) / total, 4)
            if total
            else None,
        }
        if inferred in {"numeric", "integer"} and non_null:
            numbers = [v for v in non_null if isinstance(v, (int, float))]
            non_numeric = [v for v in non_null if not isinstance(v, (int, float))]
            if non_numeric:
                numeric_issues.append(
                    {
                        "column": column,
                        "count": len(non_numeric),
                        "examples": non_numeric[:5],
                    }
                )
            if numbers:
                stats["min"] = min(numbers)
                stats["max"] = max(numbers)
                stats["mean"] = round(sum(numbers) / len(numbers), 6)
        if not non_null and total:
            all_null_columns.append(column)
        column_stats.append(stats)

        if is_rate_column(column, inferred):
            suspicious_values.extend(screen_rate_column(dataset, column, spec))
            zero_screen = screen_zero_values(dataset, column, spec)
            if zero_screen is not None:
                zero_screens.append(zero_screen)

    if numeric_issues:
        errors.append(
            "columns declared numeric by Treasury contain non-numeric values: "
            + ", ".join(i["column"] for i in numeric_issues)
        )
    if all_null_columns:
        warnings.append(
            f"columns that are null for every row: {all_null_columns}"
        )
    if suspicious_values:
        warnings.append(
            f"{len(suspicious_values)} rate observations flagged for review "
            "(out-of-band level or large day-over-day move); none removed"
        )
    placeholders = [z for z in zero_screens if z["suspected_placeholder"]]
    if placeholders:
        warnings.append(
            "columns whose leading zeros look like placeholders rather than "
            "0.00% rates (preserved as published - must be treated as "
            "'no observation' when loading): "
            + ", ".join(
                f"{z['column']} ({z['zero_valued_observations']} rows through "
                f"{z['last_zero_date']})"
                for z in placeholders
            )
        )
    if dataset.parse_errors:
        errors.append(
            f"{len(dataset.parse_errors)} values could not be parsed to their "
            "declared type"
        )

    status = "FAIL" if errors else ("WARNING" if warnings else "PASS")

    file_size = processed_path.stat().st_size if processed_path.exists() else 0
    raw_files = [o.path for o in outcomes if o.path is not None]
    raw_bytes = sum(p.stat().st_size for p in raw_files if p.exists())

    return {
        "dataset": spec.title,
        "data_key": spec.data_key,
        "source": SOURCE_ORGANISATION,
        "shape": spec.shape,
        "natural_key": list(spec.natural_key),
        "financial_caveat": spec.caveat,
        "validation_status": status,
        "coverage": {
            "treasury_documented_first_year": spec.first_year,
            "requested_years": list(requested_years),
            "years_downloaded": downloaded_years,
            "years_failed": failed_years,
            "years_with_zero_observations": empty_years,
            "years_missing_from_output": missing_years,
            "earliest_observation_date": earliest,
            "latest_observation_date": latest,
            "distinct_observation_dates": len(unique_dates),
            "records_per_year": {
                str(y): dataset.year_record_counts[y]
                for y in sorted(dataset.year_record_counts)
            },
        },
        "volume": {
            "rows_parsed": dataset.rows_before_dedup,
            "rows_after_exact_dedup": total,
            "columns": len(dataset.columns),
            "raw_files": len(raw_files),
            "raw_bytes": raw_bytes,
            "processed_file": str(processed_path.name),
            "processed_bytes": file_size,
        },
        "dates": {
            "chronologically_ordered": chronological,
            "malformed_dates": malformed_dates[:25],
            "malformed_date_count": len(malformed_dates),
            "future_dated_observations": future_dates,
            "missing_expected_business_days_count": len(gaps),
            "missing_expected_business_days_sample": gaps[:25],
            "longest_gap_between_observations": longest_gap,
        },
        "duplicates": {
            "exact_duplicate_records_removed": len(dataset.exact_duplicates),
            "exact_duplicate_sample": dataset.exact_duplicates[:25],
            "natural_key_duplicate_count": len(duplicate_keys),
            "natural_key_duplicate_sample": duplicate_keys[:25],
        },
        "missing_values": column_stats,
        "numeric_validation": {
            "columns_with_non_numeric_values": numeric_issues,
            "parse_errors": dataset.parse_errors[:25],
            "parse_error_count": len(dataset.parse_errors),
            "flagged_observations_count": len(suspicious_values),
            "flagged_observations_sample": suspicious_values[:25],
            "zero_value_screening": zero_screens,
            "screening_rule": {
                "plausible_range_percent": [RATE_PLAUSIBLE_MIN, RATE_PLAUSIBLE_MAX],
                "day_over_day_move_threshold_pp": RATE_JUMP_THRESHOLD,
                "action": "flag only - no value is removed, clipped or imputed",
                "note": (
                    "Negative Treasury rates are legitimate, especially for "
                    "real/TIPS yields, and are not flagged by the range rule."
                ),
            },
        },
        "warnings": warnings,
        "errors": errors,
    }


def screen_zero_values(
    dataset: NormalisedDataset, column: str, spec: DatasetSpec
) -> dict[str, Any] | None:
    """Characterise exact-zero observations in a rate column.

    A published 0.00% is entirely legitimate for short Treasury tenors during
    the 2008-2015 and 2020-2021 zero-rate episodes, so zeros are never removed.
    What must be caught is the opposite case: a column Treasury back-fills with
    a literal 0 for years before the series existed.  Loading such a column as
    a rate would put a 0% yield into a risk model, so a long unbroken run of
    zeros at the very start of a column's history is reported as a suspected
    placeholder.
    """
    observations: list[tuple[str, float]] = []
    for row in dataset.rows:
        value = row.get(column)
        if isinstance(value, (int, float)):
            observations.append((str(row.get(spec.date_field))[:10], float(value)))
    zeros = [d for d, v in observations if v == 0.0]
    if not zeros:
        return None

    leading_run = 0
    for _, value in observations:
        if value != 0.0:
            break
        leading_run += 1

    sentinel = leading_run >= SENTINEL_ZERO_MIN_RUN and leading_run == len(zeros)
    return {
        "column": column,
        "zero_valued_observations": len(zeros),
        "first_zero_date": zeros[0],
        "last_zero_date": zeros[-1],
        "leading_zero_run": leading_run,
        "suspected_placeholder": sentinel,
        "assessment": (
            "Suspected PLACEHOLDER: the column opens with an unbroken run of "
            f"{leading_run} zeros ending {zeros[-1]} and holds no other zeros. "
            "Treat these as 'no observation', not as a 0.00% rate. Values are "
            "preserved exactly as published - the correction belongs in the "
            "load/modelling layer, not in the source of record."
            if sentinel
            else "Consistent with genuine 0.00% prints during zero-rate "
            "episodes; retained as published."
        ),
    }


def screen_rate_column(
    dataset: NormalisedDataset, column: str, spec: DatasetSpec
) -> list[dict[str, Any]]:
    """Flag implausible levels and outsized daily moves.  Never mutates data."""
    flagged: list[dict[str, Any]] = []
    series: list[tuple[str, float]] = []
    for row in dataset.rows:
        value = row.get(column)
        if not isinstance(value, (int, float)):
            continue
        date = str(row.get(spec.date_field))
        if spec.shape == "long":
            date = f"{date}|{row.get('RATE_TYPE')}"
        series.append((date, float(value)))
        if value < RATE_PLAUSIBLE_MIN or value > RATE_PLAUSIBLE_MAX:
            flagged.append(
                {
                    "column": column,
                    "date": date,
                    "value": value,
                    "reason": "outside plausible published-rate range",
                }
            )

    if spec.shape == "long":
        # Day-over-day differencing across interleaved series would be
        # meaningless; level screening above is sufficient here.
        return flagged

    for i in range(1, len(series)):
        move = series[i][1] - series[i - 1][1]
        if abs(move) > RATE_JUMP_THRESHOLD:
            flagged.append(
                {
                    "column": column,
                    "date": series[i][0],
                    "previous_date": series[i - 1][0],
                    "value": series[i][1],
                    "previous_value": series[i - 1][1],
                    "change_pp": round(move, 4),
                    "reason": "day-over-day move exceeds threshold",
                }
            )
    return flagged


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def render_validation_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# U.S. Treasury interest-rate data - validation report")
    lines.append("")
    lines.append(f"- Source: **{SOURCE_ORGANISATION}** ({BASE_URL})")
    lines.append(f"- Generated (UTC): **{report['generated_at_utc']}**")
    lines.append(f"- Feed endpoint: `{FEED_URL}`")
    lines.append(f"- Overall status: **{report['overall_status']}**")
    lines.append("")

    totals = report["totals"]
    lines.append("## Totals")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    for label, key in [
        ("Total datasets", "datasets"),
        ("Total raw files", "raw_files"),
        ("Total records", "records"),
        ("Total disk size (bytes)", "disk_bytes"),
        ("Total disk size", "disk_human"),
        ("Successful year downloads", "successful_downloads"),
        ("Failed year downloads", "failed_downloads"),
    ]:
        lines.append(f"| {label} | {totals[key]} |")
    lines.append("")

    for entry in report["datasets"]:
        coverage = entry["coverage"]
        volume = entry["volume"]
        dup = entry["duplicates"]
        lines.append(f"## {entry['dataset']}")
        lines.append("")
        lines.append(f"- Data key: `{entry['data_key']}`")
        lines.append(f"- Source: {entry['source']}")
        lines.append(
            "- Historical period: "
            f"**{coverage['earliest_observation_date']} -> "
            f"{coverage['latest_observation_date']}**"
        )
        lines.append(f"- Rows: **{volume['rows_after_exact_dedup']:,}**")
        lines.append(f"- Columns: **{volume['columns']}**")
        lines.append(f"- Raw files: {volume['raw_files']}")
        lines.append(f"- Processed file: `{volume['processed_file']}`")
        lines.append(
            f"- Years downloaded: {len(coverage['years_downloaded'])} "
            f"({coverage['years_downloaded'][0] if coverage['years_downloaded'] else '-'}"
            f"-{coverage['years_downloaded'][-1] if coverage['years_downloaded'] else '-'})"
        )
        lines.append(f"- Failed years: {coverage['years_failed'] or 'none'}")
        lines.append(
            f"- Natural key: `{', '.join(entry['natural_key'])}` - "
            f"duplicates: {dup['natural_key_duplicate_count']}"
        )
        lines.append(
            f"- Exact duplicate records removed: "
            f"{dup['exact_duplicate_records_removed']}"
        )
        lines.append(
            "- Missing expected business days: "
            f"{entry['dates']['missing_expected_business_days_count']}"
        )
        changes = entry.get("schema_changes", {})
        added = {k: v for k, v in changes.get("columns_added_by_year", {}).items()}
        removed = changes.get("columns_removed_by_year", {})
        first_key = next(iter(added), None)
        later_added = {k: v for k, v in added.items() if k != first_key}
        lines.append(
            "- Schema changes detected: "
            + (
                f"added {later_added}; removed {removed}"
                if later_added or removed
                else "none after the first populated year"
            )
        )
        lines.append(f"- Validation status: **{entry['validation_status']}**")
        lines.append("")
        lines.append(f"> {entry['financial_caveat']}")
        lines.append("")

        lines.append("### Missing values by column")
        lines.append("")
        lines.append("| Column | Type | Total rows | Non-null | Null | Null % |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
        for stat in entry["missing_values"]:
            lines.append(
                f"| `{stat['column']}` | {stat['inferred_type']} | "
                f"{stat['total_rows']:,} | {stat['non_null_rows']:,} | "
                f"{stat['null_rows']:,} | {stat['null_percentage']:.2f} |"
            )
        lines.append("")

        zero_screens = entry["numeric_validation"].get("zero_value_screening", [])
        if zero_screens:
            lines.append("### Zero-valued rate observations")
            lines.append("")
            lines.append(
                "| Column | Zeros | First | Last | Suspected placeholder |"
            )
            lines.append("| --- | ---: | --- | --- | --- |")
            for screen in zero_screens:
                lines.append(
                    f"| `{screen['column']}` | "
                    f"{screen['zero_valued_observations']:,} | "
                    f"{screen['first_zero_date']} | {screen['last_zero_date']} | "
                    f"{'YES' if screen['suspected_placeholder'] else 'no'} |"
                )
            lines.append("")
            for screen in zero_screens:
                if screen["suspected_placeholder"]:
                    lines.append(f"- `{screen['column']}`: {screen['assessment']}")
            lines.append("")

        if entry["warnings"]:
            lines.append("### Warnings")
            lines.append("")
            for warning in entry["warnings"]:
                lines.append(f"- {warning}")
            lines.append("")
        if entry["errors"]:
            lines.append("### Errors")
            lines.append("")
            for error in entry["errors"]:
                lines.append(f"- {error}")
            lines.append("")

    lines.append("## Interpretation notes")
    lines.append("")
    lines.append(
        "- Missing observations are NULL. They were never replaced with zero, "
        "a previous day's rate, an interpolation or an average."
    )
    lines.append(
        "- Flagged values are reported for human review only; no statistical "
        "outlier was removed."
    )
    lines.append(
        "- Business-day expectations use the U.S. federal holiday calendar, "
        "Good Friday and a list of known ad-hoc market closures; remaining "
        "gaps are surfaced rather than filled."
    )
    lines.append(
        "- An exact 0 is not automatically a missing value: short Treasury "
        "tenors genuinely printed 0.00% in 2008-2015 and 2020-2021. Only "
        "columns marked 'suspected placeholder' above should be read as "
        "absent rather than zero."
    )
    lines.append(
        "- Rates are quoted in percent as published (3.72 means 3.72%), not "
        "in decimals or basis points."
    )
    lines.append("")
    return "\n".join(lines)


def human_bytes(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def resolve_years(
    spec: DatasetSpec, start_year: int | None, end_year: int | None
) -> list[int]:
    current = dt.datetime.now(dt.timezone.utc).year
    first = max(spec.first_year, start_year) if start_year else spec.first_year
    last = end_year or current
    if last < first:
        return []
    return list(range(first, last + 1))


def run(args: argparse.Namespace) -> int:
    layout = Layout(Path(args.output_dir).expanduser().resolve())
    selected = set(args.datasets)
    # --dataset restricts what is *fetched*; the manifest and the reports always
    # describe every dataset with raw files on disk, so a targeted run never
    # erases another dataset's lineage.
    specs = list(DATASETS.values())
    layout.ensure(specs)

    manifest_path = layout.metadata / "download_manifest.json"
    prior_manifest = read_json(manifest_path) or {}
    prior_entries = {
        entry["manifest_id"]: entry
        for entry in prior_manifest.get("downloads", [])
        if isinstance(entry, dict) and entry.get("manifest_id")
    }

    client = TreasuryFeedClient(
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
        max_attempts=args.max_attempts,
        polite_delay=args.delay,
    )
    downloader = Downloader(
        client,
        layout,
        refresh=args.refresh,
        refresh_current_year=not args.no_refresh_current_year,
        previous_manifest=prior_entries,
    )

    all_entries: list[dict[str, Any]] = []
    normalised: list[NormalisedDataset] = []
    validations: list[dict[str, Any]] = []
    outcomes_by_key: dict[str, list[YearOutcome]] = {}
    requested_by_key: dict[str, list[int]] = {}

    for spec in specs:
        years = (
            resolve_years(spec, args.start_year, args.end_year)
            if spec.data_key in selected
            else []
        )
        requested_by_key[spec.data_key] = years
        if years:
            LOGGER.info(
                "=== %s (%s): %d year(s) %s-%s ===",
                spec.title,
                spec.data_key,
                len(years),
                years[0],
                years[-1],
            )
        else:
            LOGGER.info(
                "=== %s (%s): not requested; rebuilding from raw files on disk "
                "===",
                spec.title,
                spec.data_key,
            )
        outcomes = [downloader.download_year(spec, year) for year in years]
        carried = downloader.collect_existing(spec, exclude_years=set(years))
        if carried:
            LOGGER.info(
                "  carrying %d previously downloaded year(s) into the "
                "processed output",
                len(carried),
            )
        outcomes = sorted(outcomes + carried, key=lambda o: o.year)
        if not outcomes:
            LOGGER.info("  nothing on disk and nothing requested; skipping")
            continue
        outcomes_by_key[spec.data_key] = outcomes
        all_entries.extend(o.entry for o in outcomes)

        dataset = normalise(spec, outcomes)
        normalised.append(dataset)
        processed_path = layout.processed_file(spec)
        write_processed_csv(processed_path, dataset)
        LOGGER.info(
            "  wrote %s (%d rows, %d source columns)",
            processed_path,
            len(dataset.rows),
            len(dataset.columns),
        )

    # Manifest -------------------------------------------------------------
    successful = sum(1 for e in all_entries if e["success"])
    failed = len(all_entries) - successful
    write_json(
        manifest_path,
        {
            "generated_at_utc": utc_now_iso(),
            "source": SOURCE_ORGANISATION,
            "source_base_url": BASE_URL,
            "feed_endpoint": FEED_URL,
            "source_documentation": DOCUMENTATION_URLS,
            "request_pattern": (
                f"{FEED_URL}?data=<data_key>&field_tdr_date_value=<yyyy>"
            ),
            "downloader": "data/acquisition/download_us_treasury.py",
            "totals": {
                "requests": len(all_entries),
                "successful": successful,
                "failed": failed,
                "records": sum(e["records"] for e in all_entries),
            },
            "downloads": all_entries,
        },
    )
    LOGGER.info("wrote %s", manifest_path)

    # Schema report --------------------------------------------------------
    schema_report = build_schema_report(normalised)
    write_json(layout.metadata / "schema_report.json", schema_report)
    LOGGER.info("wrote %s", layout.metadata / "schema_report.json")

    # Validation -----------------------------------------------------------
    total_raw_files = 0
    total_records = 0
    total_bytes = 0
    for dataset in normalised:
        spec = dataset.spec
        processed_path = layout.processed_file(spec)
        result = validate_dataset(
            dataset,
            outcomes_by_key[spec.data_key],
            requested_by_key[spec.data_key],
            processed_path,
        )
        result["schema_changes"] = schema_report["datasets"][spec.data_key][
            "schema_changes"
        ]
        validations.append(result)
        total_raw_files += result["volume"]["raw_files"]
        total_records += result["volume"]["rows_after_exact_dedup"]
        total_bytes += result["volume"]["raw_bytes"] + result["volume"][
            "processed_bytes"
        ]

    statuses = {v["validation_status"] for v in validations}
    overall = "FAIL" if "FAIL" in statuses else ("WARNING" if "WARNING" in statuses else "PASS")
    validation_report = {
        "generated_at_utc": utc_now_iso(),
        "source": SOURCE_ORGANISATION,
        "source_documentation": DOCUMENTATION_URLS,
        "overall_status": overall,
        "totals": {
            "datasets": len(validations),
            "raw_files": total_raw_files,
            "records": total_records,
            "disk_bytes": total_bytes,
            "disk_human": human_bytes(total_bytes),
            "successful_downloads": successful,
            "failed_downloads": failed,
        },
        "datasets": validations,
    }
    write_json(layout.metadata / "validation_report.json", validation_report)
    (layout.metadata / "validation_report.md").write_text(
        render_validation_markdown(validation_report), encoding="utf-8"
    )
    LOGGER.info("wrote %s", layout.metadata / "validation_report.json")
    LOGGER.info("wrote %s", layout.metadata / "validation_report.md")

    print_summary(validation_report)
    return 1 if overall == "FAIL" else 0


def print_summary(report: dict[str, Any]) -> None:
    print()
    print("=" * 78)
    print(f"U.S. Treasury data acquisition - {report['generated_at_utc']}")
    print("=" * 78)
    for entry in report["datasets"]:
        coverage = entry["coverage"]
        volume = entry["volume"]
        nulls = sum(s["null_rows"] for s in entry["missing_values"])
        cells = sum(s["total_rows"] for s in entry["missing_values"]) or 1
        print()
        print(f"Dataset          : {entry['dataset']} ({entry['data_key']})")
        print(f"Source           : {entry['source']}")
        print(
            "Historical range : "
            f"{coverage['earliest_observation_date']} -> "
            f"{coverage['latest_observation_date']}"
        )
        print(f"Rows downloaded  : {volume['rows_after_exact_dedup']:,}")
        print(f"Columns          : {volume['columns']}")
        print(f"Raw files        : {volume['raw_files']}")
        print(f"Processed file   : {volume['processed_file']}")
        print(
            "File size        : "
            f"{human_bytes(volume['processed_bytes'])} processed / "
            f"{human_bytes(volume['raw_bytes'])} raw"
        )
        print(
            "Missing values   : "
            f"{nulls:,} null cells ({100.0 * nulls / cells:.2f}% of grid)"
        )
        print(
            "Duplicates       : "
            f"{entry['duplicates']['exact_duplicate_records_removed']} exact removed, "
            f"{entry['duplicates']['natural_key_duplicate_count']} natural-key"
        )
        print(f"Validation       : {entry['validation_status']}")
        if entry["warnings"]:
            for warning in entry["warnings"]:
                print(f"  ! {warning}")
        if entry["errors"]:
            for error in entry["errors"]:
                print(f"  X {error}")
    totals = report["totals"]
    print()
    print("-" * 78)
    print(f"Total datasets      : {totals['datasets']}")
    print(f"Total raw files     : {totals['raw_files']}")
    print(f"Total records       : {totals['records']:,}")
    print(f"Total disk size     : {totals['disk_human']} ({totals['disk_bytes']:,} bytes)")
    print(f"Successful downloads: {totals['successful_downloads']}")
    print(f"Failed downloads    : {totals['failed_downloads']}")
    print(f"Overall validation  : {report['overall_status']}")
    print("-" * 78)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download, validate and organise official U.S. Department of the "
            "Treasury daily interest-rate datasets."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Datasets: " + ", ".join(DATASETS),
    )
    parser.add_argument(
        "--dataset",
        action="append",
        dest="datasets",
        choices=sorted(DATASETS),
        help="Treasury data key to download (repeatable; default: all five).",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        help="Earliest year to request (clamped to each dataset's first year).",
    )
    parser.add_argument(
        "--end-year", type=int, help="Latest year to request (default: current year)."
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-download every year even if a valid raw file already exists.",
    )
    parser.add_argument(
        "--no-refresh-current-year",
        action="store_true",
        help=(
            "Do not automatically re-download the current year. By default the "
            "current year is always refreshed because Treasury appends to it "
            "daily."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "data"),
        help="Root data directory (default: <repo>/data).",
    )
    parser.add_argument("--connect-timeout", type=float, default=15.0)
    parser.add_argument("--read-timeout", type=float, default=180.0)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument(
        "--delay",
        type=float,
        default=0.4,
        help="Polite delay in seconds between successful requests.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.datasets:
        args.datasets = list(DATASETS)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        return run(args)
    except KeyboardInterrupt:  # pragma: no cover
        LOGGER.error("interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
