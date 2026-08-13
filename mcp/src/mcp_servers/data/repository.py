"""Every SQL statement the server issues.

Concentrated in one module on purpose. The tools translate business intent into
calls here; this module owns the SQL. Caller input supplies **values only** -
there is no code path anywhere that interpolates a caller-supplied identifier,
column, table, ordering or predicate into a statement.

That is the whole difference between a semantic gateway and a SQL proxy. A
`run_sql` tool would move schema knowledge into the model's prompt, make row and
column limits unenforceable, and turn every query into an unbounded resource
request. The abstraction offered instead is not "the model may query the
database" but "the model may request approved business concepts".

All reads go through `analytics.*` views, never base tables - and the
`mcp_reader` role could not reach the base tables even if a statement here
tried.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Sequence

from ._db import fetch_all, fetch_one, scalar

# Hard ceilings. Exceeding one is an error, never a silent truncation: a caller
# who asked for 5,000 rows and received 2,000 without being told has been given
# a wrong answer, not a partial one.
MAX_HISTORY_PAGE = 2000
DEFAULT_HISTORY_PAGE = 500
MAX_SERIES_PER_REQUEST = 16
MAX_CATALOGUE_PAGE = 500
DEFAULT_CATALOGUE_PAGE = 100
MAX_TRADING_DAYS = 1250
MIN_TRADING_DAYS = 60


# --- catalogue --------------------------------------------------------------


def list_datasets(conn) -> list[dict[str, Any]]:
    return fetch_all(conn, """
        SELECT data_key, title, shape, documented_first_year, caveat,
               series_count, first_observation, last_observation
        FROM analytics.v_mcp_dataset
        ORDER BY data_key
    """)


def list_series(
    conn,
    data_key: str | None,
    rate_kind: str | None,
    quote_basis: str | None,
    tenor_min_months: Decimal | None,
    tenor_max_months: Decimal | None,
    after_code: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Keyset pagination on series_code - stable, and no OFFSET to degrade."""
    return fetch_all(conn, """
        SELECT c.series_code,
               c.display_name,
               c.data_key,
               c.rate_kind,
               c.quote_basis,
               c.tenor_label,
               c.tenor_months,
               c.is_composite,
               c.first_observation,
               c.last_observation,
               c.observation_count
        FROM analytics.v_mcp_series_catalogue c
        WHERE (%(data_key)s     IS NULL OR c.data_key    = %(data_key)s)
          AND (%(rate_kind)s    IS NULL OR c.rate_kind   = %(rate_kind)s)
          AND (%(quote_basis)s  IS NULL OR c.quote_basis = %(quote_basis)s)
          AND (%(tmin)s IS NULL OR c.tenor_months >= %(tmin)s)
          AND (%(tmax)s IS NULL OR c.tenor_months <= %(tmax)s)
          AND (%(after)s IS NULL OR c.series_code > %(after)s)
        ORDER BY c.series_code
        LIMIT %(limit)s
    """, {
        "data_key": data_key, "rate_kind": rate_kind, "quote_basis": quote_basis,
        "tmin": tenor_min_months, "tmax": tenor_max_months,
        "after": after_code, "limit": limit,
    })


def search_series(conn, query: str, data_key: str | None, limit: int) -> list[dict[str, Any]]:
    """Deterministic lexical search - aliases and tokens, never an LLM.

    An LLM inside a data server would put reasoning back on the wrong side of
    the boundary and make the same query return different results on different
    days. Ranking is by exact code, then prefix, then token overlap, then tenor.
    """
    return fetch_all(conn, """
        WITH q AS (SELECT upper(btrim(%(query)s)) AS raw),
        scored AS (
            SELECT c.*,
                   CASE
                       WHEN upper(c.series_code) = (SELECT raw FROM q)               THEN 0
                       WHEN upper(c.series_code) LIKE (SELECT raw FROM q) || '%%'    THEN 1
                       WHEN upper(c.display_name) LIKE '%%' || (SELECT raw FROM q) || '%%' THEN 2
                       WHEN upper(COALESCE(c.tenor_label,'')) = (SELECT raw FROM q)  THEN 2
                       WHEN upper(COALESCE(c.tenor_label,'')) LIKE '%%' || regexp_replace((SELECT raw FROM q), '[^0-9.]', '', 'g') || '%%'
                            AND regexp_replace((SELECT raw FROM q), '[^0-9.]', '', 'g') <> '' THEN 3
                       ELSE 9
                   END AS rank
            FROM analytics.v_mcp_series_catalogue c
            WHERE (%(data_key)s IS NULL OR c.data_key = %(data_key)s)
        )
        SELECT series_code, display_name, data_key, rate_kind, quote_basis,
               tenor_label, tenor_months, is_composite,
               first_observation, last_observation, observation_count
        FROM scored
        WHERE rank < 9
        ORDER BY rank, tenor_months NULLS LAST, series_code
        LIMIT %(limit)s
    """, {"query": query, "data_key": data_key, "limit": limit})


def series_coverage(conn, series_codes: Sequence[str]) -> list[dict[str, Any]]:
    return fetch_all(conn, """
        SELECT series_code, display_name, data_key, rate_kind, quote_basis,
               tenor_label, tenor_months, is_composite,
               first_observation, last_observation, observation_count
        FROM analytics.v_mcp_series_catalogue
        WHERE series_code = ANY(%s::text[])
        ORDER BY series_code
    """, (list(series_codes),))


def known_series_codes(conn, series_codes: Sequence[str]) -> set[str]:
    rows = fetch_all(conn,
        "SELECT series_code FROM analytics.v_mcp_series_catalogue "
        "WHERE series_code = ANY(%s::text[])", (list(series_codes),))
    return {r["series_code"] for r in rows}


# --- curve ------------------------------------------------------------------


def curve_dates_bounds(conn, curve_family: str) -> dict[str, Any] | None:
    return fetch_one(conn, """
        SELECT min(observation_date) AS first_date,
               max(observation_date) AS last_date
        FROM analytics.v_mcp_curve WHERE curve_family = %s
    """, (curve_family,))


def resolve_curve_date(
    conn, curve_family: str, requested: dt.date | None, policy: str
) -> dt.date | None:
    """Find the observation date to use. Never shifts unless asked to."""
    if requested is None:
        return scalar(conn,
            "SELECT max(observation_date) FROM analytics.v_mcp_curve "
            "WHERE curve_family = %s", (curve_family,))
    exact = scalar(conn,
        "SELECT observation_date FROM analytics.v_mcp_curve "
        "WHERE curve_family = %s AND observation_date = %s LIMIT 1",
        (curve_family, requested))
    if exact or policy == "exact":
        return exact
    if policy == "previous":
        return scalar(conn,
            "SELECT max(observation_date) FROM analytics.v_mcp_curve "
            "WHERE curve_family = %s AND observation_date < %s",
            (curve_family, requested))
    return scalar(conn,
        "SELECT min(observation_date) FROM analytics.v_mcp_curve "
        "WHERE curve_family = %s AND observation_date > %s",
        (curve_family, requested))


def nearest_curve_dates(conn, curve_family: str, around: dt.date) -> list[dict[str, Any]]:
    """Concrete alternatives for a DATE_NO_DATA error, so the model can retry."""
    return fetch_all(conn, """
        (SELECT DISTINCT observation_date FROM analytics.v_mcp_curve
          WHERE curve_family = %(f)s AND observation_date < %(d)s
          ORDER BY observation_date DESC LIMIT 2)
        UNION ALL
        (SELECT DISTINCT observation_date FROM analytics.v_mcp_curve
          WHERE curve_family = %(f)s AND observation_date > %(d)s
          ORDER BY observation_date ASC LIMIT 2)
    """, {"f": curve_family, "d": around})


def get_curve(conn, curve_family: str, observation_date: dt.date) -> list[dict[str, Any]]:
    # v_mcp_curve exposes the nominal/real axis as `curve_family` because that
    # is the curve-shaped name for it; the wire contract calls the same thing
    # `rate_kind` on an individual observation. Aliased here so the two vocabularies
    # meet in exactly one place.
    return fetch_all(conn, """
        SELECT series_code, display_name, curve_family AS rate_kind, quote_basis,
               tenor_label, tenor_months, observation_date, rate_percent,
               source_file, source_url, source_sha256
        FROM analytics.v_mcp_curve
        WHERE curve_family = %s AND observation_date = %s
        ORDER BY tenor_months
    """, (curve_family, observation_date))


def curve_trading_days(
    conn, curve_family: str, as_of: dt.date, limit: int
) -> list[dt.date]:
    rows = fetch_all(conn, """
        SELECT DISTINCT observation_date
        FROM analytics.v_mcp_curve
        WHERE curve_family = %s AND observation_date <= %s
        ORDER BY observation_date DESC
        LIMIT %s
    """, (curve_family, as_of, limit))
    return sorted(r["observation_date"] for r in rows)


def curve_matrix(
    conn, curve_family: str, tenors_months: Sequence[Decimal],
    first_date: dt.date, last_date: dt.date,
) -> list[dict[str, Any]]:
    return fetch_all(conn, """
        SELECT observation_date, tenor_months, rate_percent
        FROM analytics.v_mcp_curve
        WHERE curve_family = %(f)s
          AND observation_date BETWEEN %(a)s AND %(b)s
          AND tenor_months = ANY(%(t)s::numeric[])
        ORDER BY observation_date, tenor_months
    """, {"f": curve_family, "a": first_date, "b": last_date,
          "t": [Decimal(str(t)) for t in tenors_months]})


def available_curve_tenors(conn, curve_family: str, as_of: dt.date) -> list[Decimal]:
    rows = fetch_all(conn, """
        SELECT DISTINCT tenor_months FROM analytics.v_mcp_curve
        WHERE curve_family = %s AND observation_date = %s
        ORDER BY tenor_months
    """, (curve_family, as_of))
    return [r["tenor_months"] for r in rows]


# --- history ----------------------------------------------------------------


def rate_history(
    conn, series_codes: Sequence[str], start_date: dt.date, end_date: dt.date,
    after: dict[str, Any] | None, limit: int,
) -> list[dict[str, Any]]:
    """Keyset pagination on (observation_date, series_code)."""
    return fetch_all(conn, """
        SELECT series_code, display_name, rate_kind, quote_basis, tenor_label,
               tenor_months, observation_date, rate_percent,
               source_file, source_url, source_sha256
        FROM analytics.v_mcp_observation
        WHERE series_code = ANY(%(codes)s::text[])
          AND observation_date BETWEEN %(a)s AND %(b)s
          AND (%(ad)s::date IS NULL
               OR (observation_date, series_code) > (%(ad)s::date, %(ac)s::text))
        ORDER BY observation_date, series_code
        LIMIT %(limit)s
    """, {
        "codes": list(series_codes), "a": start_date, "b": end_date,
        "ad": (after or {}).get("d"), "ac": (after or {}).get("c"),
        "limit": limit,
    })


def rate_history_count(
    conn, series_codes: Sequence[str], start_date: dt.date, end_date: dt.date
) -> int:
    return scalar(conn, """
        SELECT count(*) FROM analytics.v_mcp_observation
        WHERE series_code = ANY(%s::text[]) AND observation_date BETWEEN %s AND %s
    """, (list(series_codes), start_date, end_date))


def explain_number(conn, series_code: str, observation_date: dt.date) -> dict[str, Any] | None:
    return fetch_one(conn, """
        SELECT series_code, display_name, rate_kind, quote_basis, tenor_label,
               tenor_months, observation_date, rate_percent, data_key,
               source_file, source_url, source_sha256, downloaded_at_utc
        FROM analytics.v_mcp_observation
        WHERE series_code = %s AND observation_date = %s
    """, (series_code, observation_date))


def series_date_bounds(conn, series_code: str) -> dict[str, Any] | None:
    return fetch_one(conn,
        "SELECT first_observation, last_observation "
        "FROM analytics.v_mcp_series_catalogue WHERE series_code = %s", (series_code,))


# --- demo book (SYNTHETIC) --------------------------------------------------


def list_portfolios(conn) -> list[dict[str, Any]]:
    return fetch_all(conn, """
        SELECT portfolio_id, portfolio_name AS name, portfolio_description AS description,
               base_currency, seed_version, data_classification,
               count(*) AS position_count
        FROM analytics.v_mcp_portfolio_position
        GROUP BY portfolio_id, portfolio_name, portfolio_description,
                 base_currency, seed_version, data_classification
        ORDER BY portfolio_id
    """)


def get_portfolio(conn, portfolio_id: str) -> list[dict[str, Any]]:
    return fetch_all(conn, """
        SELECT * FROM analytics.v_mcp_portfolio_position
        WHERE portfolio_id = %s
        ORDER BY maturity_date
    """, (portfolio_id,))


def list_scenarios(conn, scenario_type: str | None) -> list[dict[str, Any]]:
    return fetch_all(conn, """
        SELECT scenario_id, name, description, scenario_type,
               shock_definition, data_classification
        FROM demo.scenario
        WHERE (%s::text IS NULL OR scenario_type = %s::text)
        ORDER BY scenario_id
    """, (scenario_type, scenario_type))


def get_scenario(conn, scenario_id: str) -> dict[str, Any] | None:
    return fetch_one(conn, """
        SELECT scenario_id, name, description, scenario_type,
               shock_definition, data_classification
        FROM demo.scenario WHERE scenario_id = %s
    """, (scenario_id,))
