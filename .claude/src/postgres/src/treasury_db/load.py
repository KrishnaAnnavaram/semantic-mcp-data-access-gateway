#!/usr/bin/env python3
"""Load the acquired U.S. Treasury datasets into PostgreSQL.

Reads only what the acquisition stage produced - the processed CSVs and
``download_manifest.json`` - and never contacts Treasury. Acquisition and
loading are separate stages precisely so that a database problem can never be
mistaken for a data problem.

Pipeline per dataset::

    processed CSV ──COPY──► staging.<table> ──SQL──► treasury.observation
                                    │                        │
                                    └─── meta.load_step ─────┘

Three rules this loader will not break:

  * **It never writes a row Treasury did not publish.** A NULL cell in the CSV
    produces no observation. Absence stays absence - it is never zeroed,
    carried forward or interpolated.
  * **It never silently drops a column.** Every rate-bearing staging column
    must map to a registered series before any insert happens. An unmapped
    column - a maturity Treasury added since the series registry was written -
    aborts the run naming the column.
  * **It never loads unverified bytes.** Every raw file's SHA-256 is recomputed
    and checked against the manifest first.

Usage::

    python -m treasury_db.load
    python -m treasury_db.load --dataset daily_treasury_yield_curve
    python -m treasury_db.load --dry-run
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from treasury_db.db import (
    REPO_ROOT,
    connect,
    describe_target,
    fetch_all,
    scalar,
    table_columns,
)

LOGGER = logging.getLogger("us_treasury.load")

LOADER_VERSION = "1.0.0"

DATA_ROOT = REPO_ROOT / "data"
PROCESSED_DIR = DATA_ROOT / "processed" / "us_treasury"
RAW_DIR = DATA_ROOT / "raw" / "us_treasury"
METADATA_DIR = DATA_ROOT / "metadata" / "us_treasury"
MANIFEST_PATH = METADATA_DIR / "download_manifest.json"

# Columns present in every processed CSV that describe provenance rather than
# an observation.
LINEAGE_COLUMNS = ("_source_year", "_source_file")


class LoadError(RuntimeError):
    """Raised when the load cannot proceed truthfully."""


@dataclass(frozen=True)
class LoadSpec:
    """How one dataset moves from CSV to core."""

    data_key: str
    csv_name: str
    staging_table: str
    date_column: str
    shape: str                       # 'wide' | 'long'
    # Non-rate columns. Everything else must resolve to a registered series.
    ignore_columns: tuple[str, ...] = ()
    ignore_patterns: tuple[str, ...] = ()
    # 'long' only:
    series_column: str | None = None
    value_column: str | None = None
    extras: tuple[str, ...] = ()

    def ignored(self, columns: Sequence[str]) -> set[str]:
        ignored = {self.date_column, *LINEAGE_COLUMNS, *self.ignore_columns}
        for pattern in self.ignore_patterns:
            regex = re.compile(pattern)
            ignored |= {c for c in columns if regex.fullmatch(c)}
        if self.shape == "long":
            ignored |= {c for c in (self.series_column, self.value_column) if c}
        return ignored


LOAD_SPECS: dict[str, LoadSpec] = {
    "daily_treasury_yield_curve": LoadSpec(
        data_key="daily_treasury_yield_curve",
        csv_name="par_yield_curve.csv",
        staging_table="par_yield_curve",
        date_column="new_date",
        shape="wide",
        ignore_columns=("id",),
    ),
    "daily_treasury_bill_rates": LoadSpec(
        data_key="daily_treasury_bill_rates",
        csv_name="bill_rates.csv",
        staging_table="bill_rates",
        date_column="index_date",
        shape="wide",
        # quote_date and cf_new_date are verified-identical restatements of
        # index_date; cf_week is a Treasury week number, not a rate.
        ignore_columns=(
            "dailytreasurybillratedataid",
            "bond_mkt_unavail_reason",
            "quote_date",
            "cf_new_date",
            "cf_week",
        ),
        ignore_patterns=(r"cusip_\w+", r"maturity_date_\w+"),
        extras=("bill_security", "market_note"),
    ),
    "daily_treasury_long_term_rate": LoadSpec(
        data_key="daily_treasury_long_term_rate",
        csv_name="long_term_rates.csv",
        staging_table="long_term_rates",
        date_column="quote_date",
        shape="long",
        ignore_columns=("id", "extrapolation_factor"),
        series_column="rate_type",
        value_column="rate",
        extras=("long_term_extrapolation",),
    ),
    "daily_treasury_real_yield_curve": LoadSpec(
        data_key="daily_treasury_real_yield_curve",
        csv_name="real_yield_curve.csv",
        staging_table="real_yield_curve",
        date_column="new_date",
        shape="wide",
        ignore_columns=("dailytreasuryrealyieldcurveratedataid",),
    ),
    "daily_treasury_real_long_term": LoadSpec(
        data_key="daily_treasury_real_long_term",
        csv_name="real_long_term_rates.csv",
        staging_table="real_long_term_rates",
        date_column="quote_date",
        shape="wide",
    ),
}


# --------------------------------------------------------------------------
# Run bookkeeping
# --------------------------------------------------------------------------


@dataclass
class Run:
    conn: Any
    run_id: int
    steps: list[dict[str, Any]] = field(default_factory=list)

    def step(
        self,
        step: str,
        data_key: str | None,
        rows_in: int | None,
        rows_out: int | None,
        status: str = "succeeded",
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.load_step
                    (load_run_id, step, data_key, finished_at, rows_in, rows_out,
                     status, detail)
                VALUES (%s, %s, %s, now(), %s, %s, %s, %s)
                """,
                (
                    self.run_id,
                    step,
                    data_key,
                    rows_in,
                    rows_out,
                    status,
                    json.dumps(detail) if detail else None,
                ),
            )
        self.steps.append(
            {"step": step, "data_key": data_key, "rows_in": rows_in,
             "rows_out": rows_out, "status": status}
        )


def open_run(conn, datasets: Sequence[str], manifest: dict[str, Any]) -> Run:
    generated = manifest.get("generated_at_utc")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO meta.load_run
                (loader_version, manifest_generated_at, datasets_requested)
            VALUES (%s, %s, %s)
            RETURNING load_run_id
            """,
            (LOADER_VERSION, generated, list(datasets)),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    LOGGER.info("load_run %d opened", run_id)
    return Run(conn=conn, run_id=run_id)


def close_run(run: Run, status: str, error: str | None = None) -> None:
    with run.conn.cursor() as cur:
        cur.execute(
            """
            UPDATE meta.load_run
               SET finished_at = now(),
                   status = %s,
                   error = %s,
                   rows_staged = COALESCE((SELECT sum(rows_in)  FROM meta.load_step
                                            WHERE load_run_id = %s AND step = 'stage'), 0),
                   rows_loaded = COALESCE((SELECT sum(rows_out) FROM meta.load_step
                                            WHERE load_run_id = %s AND step = 'core'), 0)
             WHERE load_run_id = %s
            """,
            (status, error, run.run_id, run.run_id, run.run_id),
        )
    run.conn.commit()


# --------------------------------------------------------------------------
# Source-file verification
# --------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register_source_files(run: Run, manifest: dict[str, Any], datasets: Sequence[str]) -> int:
    """Mirror the manifest into meta.source_file, re-verifying every checksum.

    A mismatch means the bytes on disk are not the bytes that were validated
    upstream, so the load stops. Loading them anyway would put data into the
    database that no report describes.
    """
    entries = [
        e for e in manifest.get("downloads", [])
        if e.get("success") and e.get("data_key") in set(datasets)
    ]
    mismatches: list[str] = []
    registered = 0

    for entry in entries:
        relative = entry.get("output_file")
        if not relative:
            continue
        path = (REPO_ROOT / relative).resolve()
        if not path.exists():
            mismatches.append(f"{relative}: missing from disk")
            continue
        actual = sha256_of(path)
        if actual != entry.get("sha256"):
            mismatches.append(
                f"{relative}: manifest {entry.get('sha256', '')[:12]}..., "
                f"disk {actual[:12]}..."
            )
            continue
        with run.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.source_file
                    (data_key, requested_year, file_name, source_url, sha256,
                     bytes, records, downloaded_at_utc, earliest_observation,
                     latest_observation, http_status, content_type,
                     first_seen_run_id, last_seen_run_id, checksum_verified)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
                ON CONFLICT (data_key, requested_year, sha256) DO UPDATE
                   SET last_seen_run_id = EXCLUDED.last_seen_run_id,
                       checksum_verified = true
                """,
                (
                    entry["data_key"],
                    entry["requested_year"],
                    path.name,
                    entry["source_url"],
                    actual,
                    entry.get("bytes_downloaded"),
                    entry.get("records", 0),
                    entry.get("downloaded_at_utc"),
                    entry.get("earliest_observation_date"),
                    entry.get("latest_observation_date"),
                    entry.get("http_status"),
                    entry.get("content_type"),
                    run.run_id,
                    run.run_id,
                ),
            )
        registered += 1

    if mismatches:
        raise LoadError(
            "raw source files do not match the manifest, refusing to load:\n  "
            + "\n  ".join(mismatches)
        )

    run.conn.commit()
    LOGGER.info("verified and registered %d raw source file(s)", registered)
    run.step("source_files", None, len(entries), registered)
    return registered


# --------------------------------------------------------------------------
# Staging
# --------------------------------------------------------------------------


def stage_csv(run: Run, spec: LoadSpec) -> int:
    csv_path = PROCESSED_DIR / spec.csv_name
    if not csv_path.exists():
        raise LoadError(
            f"{csv_path} not found - run the acquisition stage first: "
            "python -m acquisition.download_us_treasury"
        )

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    columns = [c.lower() for c in header]

    known = set(table_columns(run.conn, "staging", spec.staging_table))
    unknown = [c for c in columns if c not in known]
    if unknown:
        raise LoadError(
            f"{spec.csv_name} has column(s) with no home in "
            f"staging.{spec.staging_table}: {unknown}. Treasury has changed the "
            "feed - add a migration for the new column rather than dropping it."
        )

    column_list = ", ".join(f'"{c}"' for c in columns)
    with run.conn.cursor() as cur:
        cur.execute(f"TRUNCATE staging.{spec.staging_table}")
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            cur.copy_expert(
                f"COPY staging.{spec.staging_table} ({column_list}) "
                "FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')",
                handle,
            )
        cur.execute(f"SELECT count(*) FROM staging.{spec.staging_table}")
        staged = cur.fetchone()[0]
    run.conn.commit()

    LOGGER.info("  staged %6d rows -> staging.%s", staged, spec.staging_table)
    run.step("stage", spec.data_key, staged, staged,
             detail={"csv": spec.csv_name, "columns": len(columns)})
    return staged


# --------------------------------------------------------------------------
# Series mapping guard
# --------------------------------------------------------------------------


def registered_series(conn, data_key: str) -> dict[str, int]:
    rows = fetch_all(
        conn,
        "SELECT series_code, series_id FROM treasury.series WHERE data_key = %s",
        (data_key,),
    )
    return {row["series_code"]: row["series_id"] for row in rows}


def assert_every_column_maps(run: Run, spec: LoadSpec) -> list[str]:
    """No rate column may reach the core layer without a series to live in.

    This is the check that stops a maturity Treasury adds next year from being
    quietly discarded by a JOIN.
    """
    series = registered_series(run.conn, spec.data_key)
    lowered = {code.lower(): code for code in series}

    if spec.shape == "long":
        values = [
            row["value"]
            for row in fetch_all(
                run.conn,
                f"SELECT DISTINCT {spec.series_column} AS value "
                f"FROM staging.{spec.staging_table} "
                f"WHERE {spec.series_column} IS NOT NULL",
            )
        ]
        unmapped = [v for v in values if v not in series]
        if unmapped:
            raise LoadError(
                f"{spec.data_key}: {spec.series_column} value(s) with no "
                f"registered series: {unmapped}. Add them to "
                "postgres/migrations as a new migration before loading."
            )
        return sorted(values)

    columns = table_columns(run.conn, "staging", spec.staging_table)
    ignored = spec.ignored(columns)
    rate_columns = [c for c in columns if c not in ignored]
    unmapped = [c for c in rate_columns if c not in lowered]
    if unmapped:
        raise LoadError(
            f"{spec.data_key}: staging column(s) with no registered series: "
            f"{unmapped}. Treasury has published a series this database does "
            "not know about. Add it in a migration - do not let the load drop it."
        )
    LOGGER.info("  %d rate column(s) all map to registered series", len(rate_columns))
    return sorted(lowered[c] for c in rate_columns)


# --------------------------------------------------------------------------
# Core transform
# --------------------------------------------------------------------------


OBSERVATION_COLUMNS = (
    "series_id, observation_date, data_key, rate_percent, value_status, "
    "source_value_percent, source_file, load_run_id"
)


def load_core_wide(run: Run, spec: LoadSpec) -> int:
    columns = table_columns(run.conn, "staging", spec.staging_table)
    ignored = sorted(spec.ignored(columns))

    sql = f"""
        INSERT INTO treasury.observation ({OBSERVATION_COLUMNS})
        SELECT s.series_id,
               st."{spec.date_column}",
               %(data_key)s,
               CASE WHEN ph.is_placeholder THEN NULL ELSE kv.value::numeric END,
               (CASE WHEN ph.is_placeholder THEN 'source_placeholder'
                     ELSE 'observed' END)::treasury.value_status,
               CASE WHEN ph.is_placeholder THEN kv.value::numeric END,
               st."_source_file",
               %(run_id)s
        FROM staging.{spec.staging_table} st
        CROSS JOIN LATERAL jsonb_each_text(to_jsonb(st) - %(ignored)s::text[])
                        AS kv(key, value)
        JOIN treasury.series s
          ON s.data_key = %(data_key)s
         AND lower(s.series_code) = kv.key
        CROSS JOIN LATERAL (
            SELECT s.placeholder_zero_before IS NOT NULL
               AND st."{spec.date_column}" < s.placeholder_zero_before
               AND kv.value::numeric = 0 AS is_placeholder
        ) ph
        WHERE kv.value IS NOT NULL
        ON CONFLICT (series_id, observation_date) DO UPDATE
           SET rate_percent = EXCLUDED.rate_percent,
               value_status = EXCLUDED.value_status,
               source_value_percent = EXCLUDED.source_value_percent,
               source_file = EXCLUDED.source_file,
               load_run_id = EXCLUDED.load_run_id
    """
    with run.conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM treasury.observation WHERE data_key = %s", (spec.data_key,)
        )
        cur.execute(sql, {"data_key": spec.data_key, "run_id": run.run_id,
                          "ignored": ignored})
        return cur.rowcount


def load_core_long(run: Run, spec: LoadSpec) -> int:
    sql = f"""
        INSERT INTO treasury.observation ({OBSERVATION_COLUMNS})
        SELECT s.series_id,
               st."{spec.date_column}",
               %(data_key)s,
               st."{spec.value_column}",
               'observed'::treasury.value_status,
               NULL,
               st."_source_file",
               %(run_id)s
        FROM staging.{spec.staging_table} st
        JOIN treasury.series s
          ON s.data_key = %(data_key)s
         AND s.series_code = st."{spec.series_column}"
        WHERE st."{spec.value_column}" IS NOT NULL
        ON CONFLICT (series_id, observation_date) DO UPDATE
           SET rate_percent = EXCLUDED.rate_percent,
               value_status = EXCLUDED.value_status,
               source_file = EXCLUDED.source_file,
               load_run_id = EXCLUDED.load_run_id
    """
    with run.conn.cursor() as cur:
        cur.execute(
            "DELETE FROM treasury.observation WHERE data_key = %s", (spec.data_key,)
        )
        cur.execute(sql, {"data_key": spec.data_key, "run_id": run.run_id})
        return cur.rowcount


# --------------------------------------------------------------------------
# Dataset extras
# --------------------------------------------------------------------------


def load_bill_security(run: Run, spec: LoadSpec) -> int:
    """CUSIP and maturity of the bill actually quoted at each tenor.

    Tenor codes are discovered from the staging columns rather than listed, so
    a new bill tenor arrives without a code change.
    """
    columns = table_columns(run.conn, "staging", spec.staging_table)
    tenors = sorted(
        {m.group(1) for c in columns if (m := re.fullmatch(r"cusip_(\w+)", c))}
    )
    if not tenors:
        return 0

    pairs = ",\n            ".join(
        f"('{t.upper()}', st.cusip_{t}, st.maturity_date_{t})" for t in tenors
    )
    sql = f"""
        INSERT INTO treasury.bill_security
            (observation_date, tenor_code, cusip, maturity_date, load_run_id)
        SELECT st."{spec.date_column}", t.code, t.cusip, t.maturity_date, %(run_id)s
        FROM staging.{spec.staging_table} st
        CROSS JOIN LATERAL (VALUES
            {pairs}
        ) AS t(code, cusip, maturity_date)
        WHERE t.cusip IS NOT NULL OR t.maturity_date IS NOT NULL
        ON CONFLICT (observation_date, tenor_code) DO UPDATE
           SET cusip = EXCLUDED.cusip,
               maturity_date = EXCLUDED.maturity_date,
               load_run_id = EXCLUDED.load_run_id
    """
    with run.conn.cursor() as cur:
        cur.execute("DELETE FROM treasury.bill_security")
        cur.execute(sql, {"run_id": run.run_id})
        return cur.rowcount


def load_market_note(run: Run, spec: LoadSpec) -> int:
    sql = f"""
        INSERT INTO treasury.market_note (data_key, observation_date, note, load_run_id)
        SELECT %(data_key)s, st."{spec.date_column}",
               btrim(st.bond_mkt_unavail_reason), %(run_id)s
        FROM staging.{spec.staging_table} st
        WHERE st.bond_mkt_unavail_reason IS NOT NULL
          AND btrim(st.bond_mkt_unavail_reason) <> ''
        ON CONFLICT (data_key, observation_date) DO UPDATE
           SET note = EXCLUDED.note, load_run_id = EXCLUDED.load_run_id
    """
    with run.conn.cursor() as cur:
        cur.execute(
            "DELETE FROM treasury.market_note WHERE data_key = %s", (spec.data_key,)
        )
        cur.execute(sql, {"data_key": spec.data_key, "run_id": run.run_id})
        return cur.rowcount


def load_long_term_extrapolation(run: Run, spec: LoadSpec) -> int:
    conflicting = scalar(
        run.conn,
        f"""
        SELECT count(*) FROM (
            SELECT "{spec.date_column}"
            FROM staging.{spec.staging_table}
            WHERE extrapolation_factor IS NOT NULL
              AND btrim(extrapolation_factor) <> ''
            GROUP BY 1
            HAVING count(DISTINCT extrapolation_factor) > 1
        ) x
        """,
    )
    if conflicting:
        raise LoadError(
            f"{conflicting} date(s) carry more than one extrapolation factor. "
            "The factor is modelled per date on the evidence that it never "
            "differs across rate types; that assumption no longer holds and the "
            "model must change before this can load."
        )

    sql = f"""
        INSERT INTO treasury.long_term_extrapolation
            (quote_date, extrapolation_factor, source_text, load_run_id)
        SELECT DISTINCT "{spec.date_column}",
               btrim(extrapolation_factor)::numeric,
               btrim(extrapolation_factor),
               %(run_id)s
        FROM staging.{spec.staging_table}
        WHERE extrapolation_factor IS NOT NULL
          AND btrim(extrapolation_factor) <> ''
        ON CONFLICT (quote_date) DO UPDATE
           SET extrapolation_factor = EXCLUDED.extrapolation_factor,
               source_text = EXCLUDED.source_text,
               load_run_id = EXCLUDED.load_run_id
    """
    with run.conn.cursor() as cur:
        cur.execute("DELETE FROM treasury.long_term_extrapolation")
        cur.execute(sql, {"run_id": run.run_id})
        return cur.rowcount


EXTRA_LOADERS = {
    "bill_security": load_bill_security,
    "market_note": load_market_note,
    "long_term_extrapolation": load_long_term_extrapolation,
}


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def load_dataset(run: Run, spec: LoadSpec) -> dict[str, Any]:
    LOGGER.info("=== %s ===", spec.data_key)
    staged = stage_csv(run, spec)
    series_codes = assert_every_column_maps(run, spec)

    if spec.shape == "wide":
        loaded = load_core_wide(run, spec)
    else:
        loaded = load_core_long(run, spec)
    run.conn.commit()
    LOGGER.info("  loaded %6d observations into treasury.observation", loaded)
    run.step("core", spec.data_key, staged, loaded,
             detail={"series": len(series_codes)})

    extras: dict[str, int] = {}
    for extra in spec.extras:
        rows = EXTRA_LOADERS[extra](run, spec)
        run.conn.commit()
        extras[extra] = rows
        LOGGER.info("  loaded %6d rows into treasury.%s", rows, extra)
        run.step(f"extra:{extra}", spec.data_key, staged, rows)

    return {"staged": staged, "observations": loaded, "series": len(series_codes),
            "extras": extras}


VACUUM_TARGETS = (
    "treasury.observation",
    "treasury.bill_security",
    "treasury.long_term_extrapolation",
    "treasury.market_note",
    "staging.par_yield_curve",
    "staging.bill_rates",
    "staging.long_term_rates",
    "staging.real_yield_curve",
    "staging.real_long_term_rates",
)


def reclaim(conn) -> None:
    """VACUUM ANALYZE the tables the load rewrote.

    Core is delete-then-insert, so every run leaves a full generation of dead
    tuples behind and the planner's statistics describing the previous load.
    Left to autovacuum, the database roughly doubles in size between runs and
    the first queries after a load plan against stale stats. VACUUM cannot run
    inside a transaction, hence the autocommit switch.
    """
    previous = conn.autocommit
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for table in VACUUM_TARGETS:
                cur.execute(f"VACUUM (ANALYZE) {table}")
    finally:
        conn.autocommit = previous
    LOGGER.info("reclaimed dead tuples and refreshed planner statistics")


def run_load(args: argparse.Namespace) -> int:
    if not MANIFEST_PATH.exists():
        raise LoadError(
            f"{MANIFEST_PATH} not found. Run the acquisition stage first: "
            "python -m acquisition.download_us_treasury"
        )
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    datasets = args.datasets or list(LOAD_SPECS)
    LOGGER.info("target: %s", describe_target())
    LOGGER.info("datasets: %s", ", ".join(datasets))

    with connect() as conn:
        missing = [
            key for key in datasets
            if not scalar(conn, "SELECT 1 FROM treasury.dataset WHERE data_key = %s",
                          (key,))
        ]
        if missing:
            raise LoadError(
                f"dataset(s) not registered in treasury.dataset: {missing}. "
                "Run: python -m treasury_db.migrate"
            )

        if args.dry_run:
            LOGGER.info("--dry-run: verifying inputs only, writing nothing")
            for key in datasets:
                spec = LOAD_SPECS[key]
                path = PROCESSED_DIR / spec.csv_name
                LOGGER.info(
                    "  %-34s %s (%s)",
                    key,
                    "present" if path.exists() else "MISSING",
                    f"{path.stat().st_size:,} bytes" if path.exists() else "-",
                )
            return 0

        run = open_run(conn, datasets, manifest)
        summary: dict[str, Any] = {}
        try:
            register_source_files(run, manifest, datasets)
            # On a full load every core row is about to be replaced. TRUNCATE
            # reclaims the space immediately; the per-dataset DELETE that
            # follows would instead leave a whole generation of dead tuples
            # behind and grow the database on every run. The DELETE is still
            # correct and still runs - it is simply operating on an empty table
            # here - which keeps the partial-load path unchanged.
            if set(datasets) == set(LOAD_SPECS):
                with conn.cursor() as cur:
                    cur.execute(
                        "TRUNCATE treasury.observation, treasury.bill_security, "
                        "treasury.long_term_extrapolation, treasury.market_note"
                    )
                conn.commit()
                LOGGER.info("full load: core tables truncated")
            for key in datasets:
                summary[key] = load_dataset(run, LOAD_SPECS[key])
        except Exception as exc:
            conn.rollback()
            close_run(run, "failed", str(exc))
            LOGGER.error("load_run %d FAILED: %s", run.run_id, exc)
            return 1

        close_run(run, "succeeded")
        reclaim(conn)
        print_summary(conn, run, summary)
    return 0


def print_summary(conn, run: Run, summary: dict[str, Any]) -> None:
    print()
    print("=" * 78)
    print(f"Load run {run.run_id} - {describe_target()}")
    print("=" * 78)
    rows = fetch_all(
        conn,
        """
        SELECT data_key, title, series, observations, first_observation,
               last_observation, distinct_dates
        FROM analytics.v_dataset_summary
        ORDER BY data_key
        """,
    )
    for row in rows:
        extras = summary.get(row["data_key"], {}).get("extras", {})
        print()
        print(f"Dataset      : {row['title']}")
        print(f"Data key     : {row['data_key']}")
        print(f"Series       : {row['series']}")
        print(f"Observations : {row['observations']:,}")
        print(f"Dates        : {row['distinct_dates']:,} "
              f"({row['first_observation']} -> {row['last_observation']})")
        if extras:
            print("Extras       : "
                  + ", ".join(f"{k}={v:,}" for k, v in extras.items()))
    totals = fetch_all(
        conn,
        """
        SELECT (SELECT count(*) FROM treasury.observation)             AS observations,
               (SELECT count(*) FROM treasury.series)                  AS series,
               (SELECT count(*) FROM treasury.observation
                 WHERE value_status = 'source_placeholder')            AS placeholders,
               (SELECT count(*) FROM meta.source_file)                 AS source_files,
               (SELECT pg_size_pretty(pg_database_size(current_database()))) AS db_size
        """,
    )[0]
    print()
    print("-" * 78)
    print(f"Series registered   : {totals['series']}")
    print(f"Observations loaded : {totals['observations']:,}")
    print(f"Placeholder rows    : {totals['placeholders']:,} (NULL rate, kept for audit)")
    print(f"Source files tracked: {totals['source_files']}")
    print(f"Database size       : {totals['db_size']}")
    print("-" * 78)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load acquired U.S. Treasury data into PostgreSQL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Datasets: " + ", ".join(LOAD_SPECS),
    )
    parser.add_argument("--dataset", action="append", dest="datasets",
                        choices=sorted(LOAD_SPECS),
                        help="dataset to load (repeatable; default: all five)")
    parser.add_argument("--dry-run", action="store_true",
                        help="verify inputs and connectivity, write nothing")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        return run_load(args)
    except LoadError as exc:
        LOGGER.error("%s", exc)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        LOGGER.error("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
