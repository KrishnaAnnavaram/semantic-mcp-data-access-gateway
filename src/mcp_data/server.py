"""market-risk-data-mcp — the server.

Eleven tools. That number is deliberate: a data server that exposes one tool per
table becomes a schema dump the model has to navigate, and tool-selection
accuracy falls as the list grows. These eleven cover the complete workflow
(catalogue, curve, history, provenance, book, scenarios) and nothing else.

Conventions applied to every tool:

* `readOnlyHint` / `idempotentHint` true, `destructiveHint` / `openWorldHint`
  false. Advisory only - the spec tells clients to distrust annotations - so the
  real constraint is the `mcp_reader` grant, which cannot write anywhere.
* A declared return model, so each tool advertises an `outputSchema` and the
  result arrives as `structured_content` rather than prose the model must parse.
* Failures raise `DomainError`, which the SDK surfaces as `is_error=true` with
  the structured error as JSON text. Malformed arguments stay protocol errors.

Run: `python -m src.mcp_data.server` (stdio). Diagnostics go to stderr - stdout
carries JSON-RPC and nothing else.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_DOCS = Path(__file__).resolve().parents[2] / "docs"

from mcp.server import CacheHint, MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from . import repository as repo
from ._db import assert_constrained_identity, connect, snapshot_id
from .contracts import (
    CoverageResult,
    CurveFamily,
    CurveHistorySummary,
    CurveResult,
    DatasetInfo,
    DatasetPage,
    DatePolicy,
    Envelope,
    InstrumentInfo,
    MissingPolicy,
    PortfolioList,
    PortfolioSnapshot,
    PortfolioSummary,
    PositionInfo,
    ProvenancedObservation,
    Provenance,
    RateHistoryPage,
    RatePoint,
    ScenarioInfo,
    ScenarioList,
    SeriesInfo,
    SeriesPage,
    SeriesSearchResult,
)
from . import cursor as cursors
from . import errors

# stdout is the protocol channel. Anything written there that is not a JSON-RPC
# message corrupts the stream, and the failure looks like a mysterious client
# disconnect rather than a stray print. All logging goes to stderr.
logging.basicConfig(
    level=logging.INFO, stream=sys.stderr,
    format="%(asctime)s %(levelname)-7s mcp-data %(message)s", datefmt="%H:%M:%S",
)
LOGGER = logging.getLogger("mcp_data")

READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False,
    idempotent_hint=True, open_world_hint=False,
)

server = MCPServer(
    name="market-risk-data-mcp",
    title="Market Risk Data",
    version="0.1.0",
    instructions=(
        "Read-only access to verified U.S. Treasury interest-rate data and a "
        "clearly-labelled synthetic demo portfolio.\n\n"
        "Every rate carries rate_kind, quote_basis and unit. These are not "
        "decoration: a bank-discount rate and a coupon-equivalent yield are "
        "different quantities and must never share a curve. Check quote_basis "
        "before combining series.\n\n"
        "This server retrieves facts. It does not price instruments, compute "
        "DV01, VaR, spreads or curve slopes, and it does not interpolate. Send "
        "its output to the risk engine for anything derived.\n\n"
        "Portfolio data is SYNTHETIC_DEMO and must always be described as such."
    ),
    # Catalogues change only when a migration or a daily load runs, so they are
    # worth caching hard. Rate results are NOT covered by these hints - the
    # protocol's cache fields apply to list/read methods, not tool calls.
    cache_hints={
        "tools/list": CacheHint(ttl_ms=3_600_000, scope="public"),
        "resources/list": CacheHint(ttl_ms=3_600_000, scope="public"),
        "resources/read": CacheHint(ttl_ms=900_000, scope="public"),
    },
)


# --- shared helpers ---------------------------------------------------------


def _envelope(conn, data_keys: list[str] | None = None, as_of: dt.date | None = None,
              warnings: list[str] | None = None,
              classification: str = "REAL_MARKET_DATA") -> Envelope:
    return Envelope(
        dataset_snapshot_id=snapshot_id(conn, data_keys),
        as_of=as_of,
        data_classification=classification,  # type: ignore[arg-type]
        warnings=warnings or [],
    )


def _rate_point(row: dict[str, Any]) -> RatePoint:
    return RatePoint(
        series_code=row["series_code"],
        display_name=row["display_name"],
        rate_kind=row["rate_kind"],
        quote_basis=row["quote_basis"],
        tenor_label=row.get("tenor_label"),
        tenor_months=row.get("tenor_months"),
        observation_date=row["observation_date"],
        rate_percent=row["rate_percent"],
    )


def _series_info(row: dict[str, Any]) -> SeriesInfo:
    return SeriesInfo(
        series_code=row["series_code"], display_name=row["display_name"],
        data_key=row["data_key"], rate_kind=row["rate_kind"],
        quote_basis=row["quote_basis"], tenor_label=row.get("tenor_label"),
        tenor_months=row.get("tenor_months"), is_composite=row.get("is_composite", False),
        first_observation=row.get("first_observation"),
        last_observation=row.get("last_observation"),
        observation_count=row.get("observation_count"),
    )


def _provenance(rows: list[dict[str, Any]]) -> Provenance:
    """Provenance for a result set. Uniform when one file backs it."""
    files = {r.get("source_file") for r in rows if r.get("source_file")}
    if len(files) == 1:
        row = next(r for r in rows if r.get("source_file"))
        return Provenance(
            source_file=row.get("source_file"), source_url=row.get("source_url"),
            source_sha256=row.get("source_sha256"),
            downloaded_at_utc=row.get("downloaded_at_utc"),
        )
    return Provenance(source_file=f"{len(files)} source files")


def _validate_series(conn, codes: list[str]) -> None:
    known = repo.known_series_codes(conn, codes)
    for code in codes:
        if code not in known:
            near = repo.search_series(conn, code, None, 5)
            raise errors.unknown_series(code, [_series_info(r).model_dump(mode="json") for r in near])


# --- catalogue --------------------------------------------------------------


@server.tool(annotations=READ_ONLY, description=(
    "List the five Treasury datasets with their coverage and, importantly, their "
    "market-risk caveats. Read the caveats before using a dataset - they record "
    "traps such as discontinued maturities and placeholder values."
))
def list_datasets() -> DatasetPage:
    with connect() as conn:
        rows = repo.list_datasets(conn)
        return DatasetPage(
            envelope=_envelope(conn),
            datasets=[DatasetInfo(**r) for r in rows],
        )


@server.tool(annotations=READ_ONLY, description=(
    "List rate series, optionally filtered by dataset, nominal/real, quoting "
    "basis or tenor range. Returns coverage per series, so a maturity that did "
    "not exist for part of the history is visible rather than surprising."
))
def list_series(
    data_key: str | None = None,
    rate_kind: str | None = None,
    quote_basis: str | None = None,
    tenor_min_months: float | None = None,
    tenor_max_months: float | None = None,
    page_size: int = repo.DEFAULT_CATALOGUE_PAGE,
    cursor: str | None = None,
) -> SeriesPage:
    if not 1 <= page_size <= repo.MAX_CATALOGUE_PAGE:
        raise errors.row_limit_exceeded(
            page_size, repo.MAX_CATALOGUE_PAGE,
            f"Use page_size between 1 and {repo.MAX_CATALOGUE_PAGE}.")
    args = locals().copy()
    after = cursors.decode(cursor, "list_series", args).get("c") if cursor else None
    with connect() as conn:
        rows = repo.list_series(
            conn, data_key, rate_kind, quote_basis,
            Decimal(str(tenor_min_months)) if tenor_min_months is not None else None,
            Decimal(str(tenor_max_months)) if tenor_max_months is not None else None,
            after, page_size + 1)
        more = len(rows) > page_size
        rows = rows[:page_size]
        return SeriesPage(
            envelope=_envelope(conn),
            series=[_series_info(r) for r in rows],
            next_cursor=cursors.encode("list_series", args, {"c": rows[-1]["series_code"]})
                        if more and rows else None,
        )


@server.tool(annotations=READ_ONLY, description=(
    "Resolve a natural-language description such as '10 year' or 'thirty year "
    "real' to canonical series codes. Deterministic alias and token matching, "
    "not a model. If the query spans both nominal and real series the result is "
    "flagged ambiguous - pick one explicitly rather than assuming."
))
def search_series(query: str, data_key: str | None = None, limit: int = 10) -> SeriesSearchResult:
    if not 1 <= len(query.strip()) <= 100:
        raise errors.unknown_series(query)
    limit = max(1, min(limit, 20))
    with connect() as conn:
        rows = repo.search_series(conn, query, data_key, limit)
        kinds = {r["rate_kind"] for r in rows}
        return SeriesSearchResult(
            envelope=_envelope(conn), query=query,
            matches=[_series_info(r) for r in rows],
            ambiguous=len(kinds) > 1,
        )


@server.tool(annotations=READ_ONLY, description=(
    "First and last observation, and the observation count, for named series. "
    "Use it to size a history request before making one."
))
def get_series_coverage(series_codes: list[str]) -> CoverageResult:
    if not 1 <= len(series_codes) <= 32:
        raise errors.row_limit_exceeded(len(series_codes), 32, "Request 1 to 32 series codes.")
    with connect() as conn:
        _validate_series(conn, series_codes)
        return CoverageResult(
            envelope=_envelope(conn),
            series=[_series_info(r) for r in repo.series_coverage(conn, series_codes)],
        )


# --- curve ------------------------------------------------------------------


@server.tool(annotations=READ_ONLY, description=(
    "The complete par yield curve for one date. curve_family 'nominal' is the "
    "standard Treasury curve; 'real' is the TIPS-derived curve, whose negative "
    "values are normal and correct. Omit observation_date for the latest "
    "published curve. date_policy defaults to 'exact' - the date is never "
    "shifted silently; ask for 'previous' or 'next' to accept a shift."
))
def get_curve(
    curve_family: CurveFamily = "nominal",
    observation_date: dt.date | None = None,
    date_policy: DatePolicy = "exact",
) -> CurveResult:
    with connect() as conn:
        bounds = repo.curve_dates_bounds(conn, curve_family) or {}
        if observation_date and bounds.get("first_date"):
            if not (bounds["first_date"] <= observation_date <= bounds["last_date"]):
                raise errors.date_out_of_range(
                    "observation_date", observation_date.isoformat(),
                    bounds["first_date"].isoformat(), bounds["last_date"].isoformat())

        resolved = repo.resolve_curve_date(conn, curve_family, observation_date, date_policy)
        if resolved is None:
            nearest = repo.nearest_curve_dates(conn, curve_family, observation_date)
            raise errors.date_no_data(
                observation_date.isoformat(), curve_family,
                [{"observation_date": r["observation_date"].isoformat()} for r in nearest])

        rows = repo.get_curve(conn, curve_family, resolved)
        shifted = bool(observation_date and resolved != observation_date)
        warnings = []
        if shifted:
            warnings.append(
                f"Requested {observation_date}, returned {resolved} under "
                f"date_policy={date_policy!r}.")
        return CurveResult(
            envelope=_envelope(conn, as_of=resolved, warnings=warnings),
            curve_family=curve_family, observation_date=resolved,
            requested_date=observation_date, date_policy=date_policy,
            date_was_shifted=shifted,
            points=[_rate_point(r) for r in rows],
            provenance=_provenance(rows),
        )


@server.tool(annotations=READ_ONLY, description=(
    "Historical observations for up to 16 named series over a date range, "
    "paginated. For a whole curve's history use get_curve_history_matrix "
    "instead - it is far more efficient and keeps thousands of rates out of "
    "the conversation."
))
def get_rate_history(
    series_codes: list[str],
    start_date: dt.date,
    end_date: dt.date,
    page_size: int = repo.DEFAULT_HISTORY_PAGE,
    cursor: str | None = None,
) -> RateHistoryPage:
    if start_date > end_date:
        raise errors.invalid_date_range(start_date.isoformat(), end_date.isoformat())
    if not 1 <= len(series_codes) <= repo.MAX_SERIES_PER_REQUEST:
        raise errors.row_limit_exceeded(
            len(series_codes), repo.MAX_SERIES_PER_REQUEST,
            f"Request 1 to {repo.MAX_SERIES_PER_REQUEST} series per call.")
    if not 1 <= page_size <= repo.MAX_HISTORY_PAGE:
        raise errors.row_limit_exceeded(
            page_size, repo.MAX_HISTORY_PAGE,
            f"Use page_size between 1 and {repo.MAX_HISTORY_PAGE}.")

    args = locals().copy()
    with connect() as conn:
        _validate_series(conn, series_codes)
        after = cursors.decode(cursor, "get_rate_history", args) if cursor else None
        rows = repo.rate_history(conn, series_codes, start_date, end_date, after, page_size + 1)
        more = len(rows) > page_size
        rows = rows[:page_size]
        next_cursor = None
        if more and rows:
            last = rows[-1]
            next_cursor = cursors.encode("get_rate_history", args,
                                         {"d": last["observation_date"].isoformat(),
                                          "c": last["series_code"]})
        return RateHistoryPage(
            envelope=_envelope(conn),
            items=[_rate_point(r) for r in rows],
            returned=len(rows), next_cursor=next_cursor,
            provenance=_provenance(rows),
        )


@server.tool(annotations=READ_ONLY, description=(
    "An aligned curve history for risk calculations: N trading days x the "
    "requested tenors. The numeric matrix is returned in the result's _meta for "
    "the host to forward to the risk engine; the model receives a summary "
    "instead, because reasoning does not require reading 2,750 individual "
    "yields. missing_policy 'reject' (the default) refuses to return a window "
    "with gaps, since silently dropping dates changes any risk number computed "
    "from it; 'intersection' accepts the gaps and reports excluded_dates."
))
def get_curve_history_matrix(
    curve_family: CurveFamily = "nominal",
    as_of_date: dt.date | None = None,
    trading_days: int = 250,
    tenors_months: list[float] | None = None,
    missing_policy: MissingPolicy = "reject",
) -> CurveHistorySummary:
    if not repo.MIN_TRADING_DAYS <= trading_days <= repo.MAX_TRADING_DAYS:
        raise errors.row_limit_exceeded(
            trading_days, repo.MAX_TRADING_DAYS,
            f"trading_days must be between {repo.MIN_TRADING_DAYS} and "
            f"{repo.MAX_TRADING_DAYS}.")

    with connect() as conn:
        as_of = repo.resolve_curve_date(conn, curve_family, as_of_date, "previous")
        if as_of is None:
            raise errors.date_no_data(
                (as_of_date or dt.date.today()).isoformat(), curve_family, [])

        tenors = ([Decimal(str(t)) for t in tenors_months] if tenors_months
                  else repo.available_curve_tenors(conn, curve_family, as_of))
        if not tenors:
            raise errors.date_no_data(as_of.isoformat(), curve_family, [])

        dates = repo.curve_trading_days(conn, curve_family, as_of, trading_days)
        if len(dates) < trading_days:
            first = dates[0].isoformat() if dates else "n/a"
            raise errors.insufficient_history(trading_days, len(dates), first)

        rows = repo.curve_matrix(conn, curve_family, tenors, dates[0], dates[-1])
        by_date: dict[dt.date, dict[Decimal, Any]] = {}
        for r in rows:
            by_date.setdefault(r["observation_date"], {})[r["tenor_months"]] = r["rate_percent"]

        complete = [d for d in dates if len(by_date.get(d, {})) == len(tenors)]
        excluded = [d for d in dates if d not in set(complete)]

        if excluded and missing_policy == "reject":
            raise errors.missing_observations(
                len(excluded), len(dates),
                [{"observation_date": d.isoformat(),
                  "tenors_present": len(by_date.get(d, {})),
                  "tenors_required": len(tenors)} for d in excluded])

        used = complete
        matrix = [[str(by_date[d][t]) for t in tenors] for d in used]
        summary = CurveHistorySummary(
            envelope=_envelope(conn, as_of=as_of, warnings=(
                [f"{len(excluded)} dates excluded for incomplete tenor coverage."]
                if excluded else [])),
            curve_family=curve_family, as_of_date=as_of,
            tenors_months=tenors,
            trading_days_requested=trading_days, trading_days_returned=len(used),
            first_date=used[0] if used else None, last_date=used[-1] if used else None,
            point_count=len(used) * len(tenors),
            missing_policy=missing_policy,
            excluded_dates=len(excluded),
            excluded_date_sample=excluded[:10],
            meta_key="market-risk-data/curve_history_matrix",
            provenance=_provenance(rows),
        )
        return CallToolResult(
            content=[TextContent(type="text", text=(
                f"{len(used)} trading days x {len(tenors)} tenors "
                f"({len(used) * len(tenors)} observations) for the {curve_family} "
                f"curve to {as_of}. Numeric matrix delivered in _meta under "
                f"'{summary.meta_key}'."))],
            structured_content=summary.model_dump(mode="json"),
            meta={summary.meta_key: {
                "curve_family": curve_family,
                "dates": [d.isoformat() for d in used],
                "tenors_months": [str(t) for t in tenors],
                "rates_percent": matrix,
                "unit": "percent",
                "quote_basis": "par_coupon_semiannual",
                "dataset_snapshot_id": summary.envelope.dataset_snapshot_id,
            }},
        )


# --- provenance -------------------------------------------------------------


@server.tool(annotations=READ_ONLY, description=(
    "Where a single number came from: its value plus the Treasury file, source "
    "URL and SHA-256 behind it. Use this to answer 'is that figure right?' "
    "without leaving the conversation."
))
def explain_number(series_code: str, observation_date: dt.date) -> ProvenancedObservation:
    with connect() as conn:
        _validate_series(conn, [series_code])
        row = repo.explain_number(conn, series_code, observation_date)
        if row is None:
            bounds = repo.series_date_bounds(conn, series_code) or {}
            first, last = bounds.get("first_observation"), bounds.get("last_observation")
            if first and not (first <= observation_date <= last):
                raise errors.date_out_of_range(
                    "observation_date", observation_date.isoformat(),
                    first.isoformat(), last.isoformat())
            raise errors.date_no_data(observation_date.isoformat(), series_code, [])
        return ProvenancedObservation(
            envelope=_envelope(conn, [row["data_key"]], as_of=observation_date),
            observation=_rate_point(row),
            provenance=_provenance([row]),
            lineage={
                "dataset": row["data_key"],
                "raw_file": row.get("source_file"),
                "source_url": row.get("source_url"),
                "source_sha256": row.get("source_sha256"),
                "downloaded_at_utc": (row["downloaded_at_utc"].isoformat()
                                      if row.get("downloaded_at_utc") else None),
                "chain": "Treasury XML -> checksummed raw file -> validated CSV "
                         "-> staging -> treasury.observation -> analytics view",
            },
        )


# --- demo book (SYNTHETIC) --------------------------------------------------


@server.tool(annotations=READ_ONLY, description=(
    "List available demo portfolios. All portfolios are SYNTHETIC_DEMO - "
    "invented for demonstration. Never present them as a real book."
))
def list_portfolios() -> PortfolioList:
    with connect() as conn:
        rows = repo.list_portfolios(conn)
        return PortfolioList(
            envelope=_envelope(conn, classification="SYNTHETIC_DEMO"),
            portfolios=[PortfolioSummary(
                portfolio_id=r["portfolio_id"], name=r["name"],
                description=r.get("description"), base_currency=r["base_currency"],
                seed_version=r["seed_version"], position_count=r["position_count"],
            ) for r in rows],
        )


@server.tool(annotations=READ_ONLY, description=(
    "Positions and full instrument economics for one demo portfolio - enough "
    "for the risk engine to generate cash flows and price it. SYNTHETIC_DEMO."
))
def get_portfolio(portfolio_id: str) -> PortfolioSnapshot:
    with connect() as conn:
        rows = repo.get_portfolio(conn, portfolio_id)
        if not rows:
            known = repo.list_portfolios(conn)
            raise errors.unknown_entity(
                "portfolio", portfolio_id,
                [{"portfolio_id": r["portfolio_id"], "name": r["name"]} for r in known])
        head = rows[0]
        return PortfolioSnapshot(
            envelope=_envelope(conn, classification="SYNTHETIC_DEMO"),
            portfolio=PortfolioSummary(
                portfolio_id=head["portfolio_id"], name=head["portfolio_name"],
                description=head.get("portfolio_description"),
                base_currency=head["base_currency"], seed_version=head["seed_version"],
                position_count=len(rows),
            ),
            positions=[PositionInfo(
                instrument=InstrumentInfo(
                    instrument_id=r["instrument_id"], instrument_type=r["instrument_type"],
                    display_name=r["instrument_name"], currency=r["currency"],
                    face_value=r["face_value"], coupon_rate_pct=r["coupon_rate_pct"],
                    issue_date=r["issue_date"], maturity_date=r["maturity_date"],
                    coupon_frequency=r["coupon_frequency"], day_count=r["day_count"],
                    rate_kind=r["rate_kind"],
                ),
                face_notional=r["face_notional"],
            ) for r in rows],
        )


@server.tool(annotations=READ_ONLY, description=(
    "List stress scenarios. TENOR_VECTOR_BP carries an explicit tenor-to-basis-"
    "point shock vector. HISTORICAL_REPLAY names two real dates whose observed "
    "curve move is the shock - the risk engine differences those curves; this "
    "server does not calculate."
))
def list_scenarios(scenario_type: str | None = None) -> ScenarioList:
    with connect() as conn:
        rows = repo.list_scenarios(conn, scenario_type)
        return ScenarioList(
            envelope=_envelope(conn, classification="SYNTHETIC_DEMO"),
            scenarios=[ScenarioInfo(**r) for r in rows],
        )


@server.tool(annotations=READ_ONLY, description=(
    "One scenario's full definition, including its shock vector or the pair of "
    "dates to replay."
))
def get_scenario(scenario_id: str) -> ScenarioInfo:
    with connect() as conn:
        row = repo.get_scenario(conn, scenario_id)
        if row is None:
            known = repo.list_scenarios(conn, None)
            raise errors.unknown_entity(
                "scenario", scenario_id,
                [{"scenario_id": r["scenario_id"], "name": r["name"]} for r in known])
        return ScenarioInfo(**row)


# --- resources --------------------------------------------------------------
#
# Tools fetch data. Resources explain what it means. The split matters because
# a caveat is not something the model should have to remember to ask for - it is
# context the client can attach up front.


@server.resource(
    "market-risk://catalog/datasets",
    name="Dataset catalogue",
    mime_type="application/json",
    description="The five Treasury datasets with coverage and market-risk caveats.",
)
def resource_datasets() -> str:
    import json  # noqa: PLC0415
    with connect() as conn:
        return json.dumps(repo.list_datasets(conn), indent=2, default=str)


@server.resource(
    "market-risk://catalog/series",
    name="Series catalogue",
    mime_type="application/json",
    description="All retrievable rate series with quoting basis, tenor and coverage.",
)
def resource_series() -> str:
    import json  # noqa: PLC0415
    with connect() as conn:
        rows = repo.list_series(conn, None, None, None, None, None, None, 500)
        return json.dumps(rows, indent=2, default=str)


@server.resource(
    "market-risk://caveats/{data_key}",
    name="Dataset caveat",
    mime_type="text/markdown",
    description=(
        "The market-risk warning for one dataset: which quoting basis applies, "
        "which maturities are discontinued, which values are placeholders."
    ),
)
def resource_caveat(data_key: str) -> str:
    with connect() as conn:
        rows = [d for d in repo.list_datasets(conn) if d["data_key"] == data_key]
        if not rows:
            known = ", ".join(d["data_key"] for d in repo.list_datasets(conn))
            return f"# Unknown dataset `{data_key}`\n\nKnown datasets: {known}\n"
        d = rows[0]
        return (
            f"# {d['title']}\n\n"
            f"**Data key:** `{d['data_key']}`  \n"
            f"**Coverage:** {d['first_observation']} to {d['last_observation']}  \n"
            f"**Series:** {d['series_count']}\n\n"
            f"## Caveat\n\n{d['caveat']}\n"
        )


@server.resource(
    "market-risk://docs/data-contract",
    name="Data contract",
    mime_type="text/markdown",
    description="What the numbers mean, and the traps in the source.",
)
def resource_contract() -> str:
    path = REPO_DOCS / "data-contract.md"
    return path.read_text(encoding="utf-8") if path.exists() else (
        "# Data contract\n\nSee docs/data-contract.md in the repository.\n")


@server.resource(
    "market-risk://docs/provenance",
    name="Provenance model",
    mime_type="text/markdown",
    description="How a number is traced from a response back to a Treasury file.",
)
def resource_provenance() -> str:
    with connect() as conn:
        return (
            "# Provenance\n\n"
            f"Current data snapshot: `{snapshot_id(conn)}`\n\n"
            "Every rate this server returns can be traced back to its source:\n\n"
            "```\n"
            "Treasury XML feed (home.treasury.gov)\n"
            "  -> raw file, SHA-256 recorded at download\n"
            "  -> validated CSV\n"
            "  -> staging table (mirrors the CSV exactly)\n"
            "  -> treasury.observation (typed, placeholder-aware)\n"
            "  -> analytics view (curated; placeholders excluded)\n"
            "  -> this response\n"
            "```\n\n"
            "Call `explain_number(series_code, observation_date)` to walk that "
            "chain for any single value.\n\n"
            "`dataset_snapshot_id` is derived from the SHA-256s of the raw files "
            "currently loaded. It changes if and only if the underlying data "
            "changes, so a result may be cached against it. A Treasury "
            "restatement produces a new snapshot id rather than silently "
            "reusing the old one.\n"
        )


# --- prompts ----------------------------------------------------------------
# User-controlled entry points: these become slash-commands in a client.


@server.prompt(
    name="curve_snapshot",
    description="Show and interpret the Treasury par curve for a date.",
)
def prompt_curve_snapshot(observation_date: str = "", curve_family: str = "nominal") -> str:
    when = observation_date or "the latest published date"
    return (
        f"Retrieve the {curve_family} Treasury par yield curve for {when} using "
        "get_curve, then describe its shape: level, slope (2s10s), and any "
        "inversion. State the quoting basis and note that these are par yields, "
        "not zero-coupon rates. Do not compute prices or risk figures."
    )


@server.prompt(
    name="explain_series",
    description="Explain what a rate series is and how to use it correctly.",
)
def prompt_explain_series(series_code: str) -> str:
    return (
        f"Use get_series_coverage and the catalogue to explain the series "
        f"{series_code}: what it measures, its quoting basis and rate kind, the "
        "period it covers, and any gap in that coverage. Read the dataset's "
        "caveat resource and state any trap that applies. Finish with what this "
        "series must NOT be combined with, and why."
    )


@server.prompt(
    name="coverage_report",
    description="Report what data exists and where the gaps are.",
)
def prompt_coverage_report() -> str:
    return (
        "Using list_datasets and list_series, summarise what this database "
        "holds: datasets, series counts, date ranges. Then call out every "
        "series whose coverage starts later than its dataset or has a known "
        "interruption, and explain why - a maturity that did not exist yet is "
        "not missing data. Quote each dataset's caveat."
    )


def main() -> None:
    with connect() as conn:
        assert_constrained_identity(conn)
        LOGGER.info("connected as a constrained reader; snapshot %s", snapshot_id(conn))
    import anyio
    anyio.run(server.run_stdio_async)


if __name__ == "__main__":
    main()
