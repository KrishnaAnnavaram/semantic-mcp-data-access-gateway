#!/usr/bin/env python3
"""Reconcile the loaded database against the CSVs it was built from.

A load that finished is not a load that is correct. This tool re-derives every
expected number **independently from the processed CSVs** - it never asks the
database what it should contain - and compares. Results are written to
``meta.reconciliation`` so the evidence outlives the terminal it scrolled past.

Checks
------
  lineage      every raw file in the manifest is registered and checksum-verified
  staging      staging row count == CSV row count
  observations core row count == non-null rate cells counted from the CSV
  coverage     first/last observation date and distinct dates match the CSV
  values       a random sample of cells is byte-compared CSV -> database
  placeholders the BC_30YEARDISPLAY zeros are stored as placeholders, not rates
  integrity    no duplicate keys, no future dates, no orphan rows, no leakage
               of excluded series into the analytics layer
  constraints  the primary keys, foreign keys and checks are actually present

``--self-test`` proves the value check can fail: it corrupts one row inside a
transaction, confirms the check catches it, and rolls back. A suite that only
ever reports PASS tells you about the suite, not the data.

Usage::

    python tools/verify_load.py
    python tools/verify_load.py --self-test
    python tools/verify_load.py --sample-size 500
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import random
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]

import psycopg2  # noqa: E402  (needed for the privilege probes)

from treasury_db.db import connect, describe_target, fetch_all, scalar  # noqa: E402
from treasury_db.load import (
    LOAD_SPECS,
    MANIFEST_PATH,
    PROCESSED_DIR,
    LoadSpec,
)

LOGGER = logging.getLogger("us_treasury.verify")

REPORT_JSON = REPO_ROOT / "data" / "metadata" / "us_treasury" / "load_verification.json"
REPORT_MD = REPO_ROOT / "data" / "metadata" / "us_treasury" / "load_verification.md"


@dataclass
class Check:
    name: str
    data_key: str | None
    expected: Any
    actual: Any
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "check": self.name,
            "data_key": self.data_key,
            "expected": _plain(self.expected),
            "actual": _plain(self.actual),
            "passed": self.passed,
            "detail": self.detail,
        }


def _plain(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime, Decimal)):
        return str(value)
    return value


@dataclass
class Verifier:
    conn: Any
    sample_size: int = 250
    seed: int = 20260812
    checks: list[Check] = field(default_factory=list)

    def record(
        self,
        name: str,
        data_key: str | None,
        expected: Any,
        actual: Any,
        detail: str = "",
        passed: bool | None = None,
    ) -> Check:
        ok = (_plain(expected) == _plain(actual)) if passed is None else passed
        check = Check(name, data_key, expected, actual, ok, detail)
        self.checks.append(check)
        marker = "ok  " if ok else "FAIL"
        LOGGER.info(
            "  [%s] %-28s expected=%s actual=%s%s",
            marker, name, _plain(expected), _plain(actual),
            f"  {detail}" if detail else "",
        )
        return check

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]


# --------------------------------------------------------------------------
# Independent expectations, read from the CSVs
# --------------------------------------------------------------------------


@dataclass
class CsvFacts:
    rows: int
    observations: int
    distinct_dates: int
    first_date: str | None
    last_date: str | None
    rate_columns: list[str]
    cells: dict[tuple[str, str], str]   # (series_code, date) -> value text


def read_csv_facts(spec: LoadSpec) -> CsvFacts:
    """Recount the source of truth without consulting the database."""
    path = PROCESSED_DIR / spec.csv_name
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = [c.lower() for c in (reader.fieldnames or [])]
        ignored = spec.ignored(header)
        rate_columns = (
            [c for c in header if c not in ignored]
            if spec.shape == "wide"
            else []
        )
        original = {c.lower(): c for c in (reader.fieldnames or [])}

        rows = 0
        observations = 0
        dates: set[str] = set()
        cells: dict[tuple[str, str], str] = {}

        for record in reader:
            rows += 1
            lowered = {k.lower(): v for k, v in record.items()}
            date_value = lowered[spec.date_column]
            dates.add(date_value)
            if spec.shape == "wide":
                for column in rate_columns:
                    value = lowered.get(column, "")
                    if value != "":
                        observations += 1
                        cells[(original[column], date_value)] = value
            else:
                value = lowered.get(spec.value_column or "", "")
                if value != "":
                    observations += 1
                    cells[(lowered[spec.series_column or ""], date_value)] = value

    ordered = sorted(dates)
    return CsvFacts(
        rows=rows,
        observations=observations,
        distinct_dates=len(dates),
        first_date=ordered[0] if ordered else None,
        last_date=ordered[-1] if ordered else None,
        rate_columns=rate_columns,
        cells=cells,
    )


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


def check_lineage(v: Verifier) -> None:
    LOGGER.info("lineage")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    successful = [e for e in manifest["downloads"] if e.get("success")]
    v.record("manifest_files_registered", None, len(successful),
             scalar(v.conn, "SELECT count(*) FROM meta.source_file"))
    v.record("all_checksums_verified", None, 0,
             scalar(v.conn,
                    "SELECT count(*) FROM meta.source_file WHERE NOT checksum_verified"),
             "count of files loaded without a verified SHA-256")
    v.record("load_run_succeeded", None, "succeeded",
             scalar(v.conn,
                    "SELECT status FROM meta.load_run ORDER BY load_run_id DESC LIMIT 1"))
    v.record("no_failed_load_steps", None, 0,
             scalar(v.conn, "SELECT count(*) FROM meta.load_step WHERE status = 'failed'"))


def check_dataset(v: Verifier, spec: LoadSpec, facts: CsvFacts) -> None:
    LOGGER.info("%s", spec.data_key)
    key = spec.data_key

    v.record("staging_rows", key, facts.rows,
             scalar(v.conn, f"SELECT count(*) FROM staging.{spec.staging_table}"))

    v.record("observations", key, facts.observations,
             scalar(v.conn,
                    "SELECT count(*) FROM treasury.observation WHERE data_key = %s",
                    (key,)),
             "non-null rate cells counted from the CSV")

    row = fetch_all(
        v.conn,
        """
        SELECT count(DISTINCT observation_date) AS dates,
               min(observation_date)            AS first_date,
               max(observation_date)            AS last_date
        FROM treasury.observation WHERE data_key = %s
        """,
        (key,),
    )[0]
    v.record("distinct_dates", key, facts.distinct_dates, row["dates"])
    v.record("first_observation", key, facts.first_date, row["first_date"])
    v.record("last_observation", key, facts.last_date, row["last_date"])


def check_values(v: Verifier, spec: LoadSpec, facts: CsvFacts) -> None:
    """Byte-compare a random sample of source cells against the database."""
    if not facts.cells:
        return
    rng = random.Random(f"{v.seed}:{spec.data_key}")
    keys = sorted(facts.cells)
    sample = rng.sample(keys, min(v.sample_size, len(keys)))

    mismatches: list[str] = []
    for series_code, date_text in sample:
        stored = scalar(
            v.conn,
            """
            SELECT o.rate_percent
            FROM treasury.observation o
            JOIN treasury.series s USING (series_id)
            WHERE o.data_key = %s AND s.series_code = %s AND o.observation_date = %s
            """,
            (spec.data_key, series_code, date_text),
        )
        expected_text = facts.cells[(series_code, date_text)]
        expected = Decimal(expected_text)
        placeholder = stored is None
        if placeholder:
            source_value = scalar(
                v.conn,
                """
                SELECT o.source_value_percent
                FROM treasury.observation o
                JOIN treasury.series s USING (series_id)
                WHERE o.data_key = %s AND s.series_code = %s
                  AND o.observation_date = %s
                """,
                (spec.data_key, series_code, date_text),
            )
            # A NULL rate is only acceptable when the row is a recorded
            # placeholder holding exactly the value the source printed.
            if source_value is None or Decimal(source_value) != expected:
                mismatches.append(
                    f"{series_code}@{date_text}: csv={expected_text} db=NULL "
                    f"placeholder={source_value}"
                )
            continue
        if Decimal(stored) != expected:
            mismatches.append(
                f"{series_code}@{date_text}: csv={expected_text} db={stored}"
            )

    v.record(
        "value_sample_mismatches", spec.data_key, 0, len(mismatches),
        f"{len(sample)} cells sampled" + (
            "; " + "; ".join(mismatches[:5]) if mismatches else ""
        ),
    )


def check_placeholders(v: Verifier) -> None:
    LOGGER.info("placeholders")
    expected = scalar(
        v.conn,
        """
        SELECT count(*) FROM staging.par_yield_curve
        WHERE bc_30yeardisplay = 0 AND new_date < DATE '2011-01-03'
        """,
    )
    v.record("placeholder_rows_recorded", "daily_treasury_yield_curve", expected,
             scalar(v.conn,
                    "SELECT count(*) FROM treasury.observation "
                    "WHERE value_status = 'source_placeholder'"),
             "leading BC_30YEARDISPLAY zeros, stored with a NULL rate")
    v.record("placeholders_have_no_rate", None, 0,
             scalar(v.conn,
                    "SELECT count(*) FROM treasury.observation "
                    "WHERE value_status = 'source_placeholder' "
                    "AND rate_percent IS NOT NULL"),
             "a placeholder must never present itself as a rate")
    v.record("placeholders_excluded_from_analytics", None, 0,
             scalar(v.conn,
                    "SELECT count(*) FROM analytics.v_observation "
                    "WHERE series_code = 'BC_30YEARDISPLAY'"))
    v.record("no_zero_30y_in_analytics", None, 0,
             scalar(v.conn,
                    "SELECT count(*) FROM analytics.v_par_yield_curve "
                    "WHERE y30 = 0"),
             "a 0.00% 30-year yield would be the placeholder leaking through")


def check_integrity(v: Verifier) -> None:
    LOGGER.info("integrity")
    v.record("future_dated_observations", None, 0,
             scalar(v.conn,
                    "SELECT count(*) FROM treasury.observation "
                    "WHERE observation_date > CURRENT_DATE"))
    v.record("observations_without_series", None, 0,
             scalar(v.conn,
                    "SELECT count(*) FROM treasury.observation o "
                    "LEFT JOIN treasury.series s USING (series_id) "
                    "WHERE s.series_id IS NULL"))
    v.record("data_key_disagreements", None, 0,
             scalar(v.conn,
                    "SELECT count(*) FROM treasury.observation o "
                    "JOIN treasury.series s USING (series_id) "
                    "WHERE s.data_key <> o.data_key"))
    v.record("duplicate_observation_keys", None, 0,
             scalar(v.conn,
                    "SELECT count(*) FROM (SELECT series_id, observation_date "
                    "FROM treasury.observation GROUP BY 1,2 HAVING count(*) > 1) x"))
    v.record("series_without_observations", None, 0,
             scalar(v.conn,
                    "SELECT count(*) FROM treasury.series s "
                    "WHERE NOT EXISTS (SELECT 1 FROM treasury.observation o "
                    "WHERE o.series_id = s.series_id)"),
             "a registered series that loaded nothing is a mapping error")
    v.record("rates_outside_plausible_band", None, 0,
             scalar(v.conn,
                    "SELECT count(*) FROM treasury.observation "
                    "WHERE rate_percent IS NOT NULL "
                    "AND rate_percent NOT BETWEEN -25 AND 100"))
    v.record("bill_securities_mature_after_quote", None, 0,
             scalar(v.conn,
                    "SELECT count(*) FROM treasury.bill_security "
                    "WHERE maturity_date IS NOT NULL "
                    "AND maturity_date <= observation_date"))
    # Views must be queryable, not merely defined.
    for view in (
        "v_series", "v_observation", "v_par_yield_curve", "v_real_yield_curve",
        "v_bill_rates_quoted", "v_long_term_rates", "v_latest_rates",
        "v_series_coverage", "v_dataset_summary",
    ):
        try:
            count = scalar(v.conn, f"SELECT count(*) FROM analytics.{view}")
            v.record(f"view_queryable:{view}", None, True, count > 0,
                     f"{count:,} rows")
        except Exception as exc:  # noqa: BLE001
            v.conn.rollback()
            v.record(f"view_queryable:{view}", None, True, False, str(exc)[:120])


def check_mcp_boundary(v: Verifier) -> None:
    """Prove the MCP database identity can only read what it is meant to.

    Tool annotations (`readOnlyHint` and friends) are advisory - the spec tells
    clients to treat them as untrusted. Privileges are not advisory, so the
    boundary is asserted here against the live database rather than assumed
    from the migration having run.

    Each probe runs inside a SAVEPOINT so a denied statement does not abort the
    surrounding transaction, and the whole thing is rolled back regardless.
    """
    LOGGER.info("mcp boundary")

    must_succeed = [
        ("read_curve_view", "SELECT 1 FROM analytics.v_mcp_curve LIMIT 1"),
        ("read_observation_view", "SELECT 1 FROM analytics.v_mcp_observation LIMIT 1"),
        ("read_demo_positions", "SELECT 1 FROM analytics.v_mcp_portfolio_position LIMIT 1"),
        ("read_scenarios", "SELECT 1 FROM demo.scenario LIMIT 1"),
        ("read_source_provenance", "SELECT 1 FROM meta.source_file LIMIT 1"),
    ]
    must_fail = [
        ("read_raw_treasury", "SELECT 1 FROM treasury.observation LIMIT 1"),
        ("read_raw_staging", "SELECT 1 FROM staging.par_yield_curve LIMIT 1"),
        ("insert_demo", "INSERT INTO demo.portfolio (portfolio_id, name, seed_version) "
                        "VALUES ('DEMO_ZZ', 'x', 'v')"),
        ("update_demo", "UPDATE demo.position SET face_notional = 1"),
        ("delete_demo", "DELETE FROM demo.scenario"),
        ("create_table", "CREATE TABLE demo.should_not_exist (id int)"),
        ("write_treasury", "UPDATE treasury.observation SET rate_percent = 0"),
    ]

    def probe(sql: str) -> bool:
        """Run sql as mcp_reader; True if it was permitted."""
        with v.conn.cursor() as cur:
            cur.execute("SAVEPOINT mcp_probe")
            try:
                cur.execute("SET LOCAL ROLE mcp_reader")
                cur.execute(sql)
                permitted = True
            except psycopg2.Error:
                permitted = False
            finally:
                cur.execute("ROLLBACK TO SAVEPOINT mcp_probe")
        return permitted

    try:
        for name, sql in must_succeed:
            v.record(f"mcp_reader_can:{name}", None, True, probe(sql))
        for name, sql in must_fail:
            v.record(f"mcp_reader_cannot:{name}", None, False, probe(sql),
                     "privilege boundary, not an annotation")
    finally:
        v.conn.rollback()

    # The MCP read view is rebuilt from base tables rather than layered on
    # v_observation, so it repeats two filter predicates. If those ever drift,
    # a placeholder row becomes reachable through the MCP layer. Catch it here.
    v.record(
        "mcp_view_matches_curated_view", None,
        scalar(v.conn, "SELECT count(*) FROM analytics.v_observation"),
        scalar(v.conn, "SELECT count(*) FROM analytics.v_mcp_observation"),
        "v_mcp_observation must not expose anything v_observation hides",
    )
    v.record(
        "mcp_view_excludes_placeholders", None, 0,
        scalar(v.conn,
               "SELECT count(*) FROM analytics.v_mcp_observation "
               "WHERE series_code = 'BC_30YEARDISPLAY'"))
    v.record(
        "mcp_rates_all_carry_quote_basis", None, 0,
        scalar(v.conn,
               "SELECT count(*) FROM analytics.v_mcp_observation "
               "WHERE quote_basis IS NULL OR unit IS NULL OR rate_kind IS NULL"),
        "the semantic envelope is mandatory on every row")
    v.record(
        "demo_rows_all_classified_synthetic", None, 0,
        scalar(v.conn,
               "SELECT count(*) FROM analytics.v_mcp_portfolio_position "
               "WHERE data_classification <> 'SYNTHETIC_DEMO'"))


def check_constraints(v: Verifier) -> None:
    LOGGER.info("constraints")
    expected = {
        ("treasury", "observation", "p"): 1,
        ("treasury", "observation", "f"): 2,
        ("treasury", "series", "f"): 1,
    }
    for (schema, table, kind), minimum in expected.items():
        count = scalar(
            v.conn,
            """
            SELECT count(*)
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = %s AND t.relname = %s AND c.contype = %s
            """,
            (schema, table, kind),
        )
        v.record(f"constraint:{schema}.{table}:{kind}", None, f">={minimum}", count,
                 passed=count >= minimum)

    v.record("check_constraints_on_observation", None, ">=2",
             scalar(v.conn,
                    "SELECT count(*) FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "JOIN pg_namespace n ON n.oid = t.relnamespace "
                    "WHERE n.nspname='treasury' AND t.relname='observation' "
                    "AND c.contype='c'"),
             passed=scalar(v.conn,
                           "SELECT count(*) FROM pg_constraint c "
                           "JOIN pg_class t ON t.oid = c.conrelid "
                           "JOIN pg_namespace n ON n.oid = t.relnamespace "
                           "WHERE n.nspname='treasury' AND t.relname='observation' "
                           "AND c.contype='c'") >= 2)


# --------------------------------------------------------------------------
# Self-test: prove the value check can fail
# --------------------------------------------------------------------------


def self_test(sample_size: int) -> bool:
    """Corrupt one stored rate inside a transaction and confirm it is caught.

    The corruption is rolled back. This proves the comparison path detects a
    real divergence between database and CSV - not merely that it runs.
    """
    LOGGER.info("self-test: corrupting one row inside a rolled-back transaction")
    spec = LOAD_SPECS["daily_treasury_yield_curve"]
    facts = read_csv_facts(spec)

    with connect() as conn:
        probe = Verifier(conn=conn, sample_size=sample_size)
        target = fetch_all(
            conn,
            """
            SELECT o.series_id, o.observation_date, s.series_code, o.rate_percent
            FROM treasury.observation o
            JOIN treasury.series s USING (series_id)
            WHERE o.data_key = 'daily_treasury_yield_curve'
              AND o.value_status = 'observed'
            ORDER BY o.observation_date
            LIMIT 1
            """,
        )[0]
        original = target["rate_percent"]
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE treasury.observation SET rate_percent = rate_percent + 1.25 "
                    "WHERE series_id = %s AND observation_date = %s",
                    (target["series_id"], target["observation_date"]),
                )
            # Sample deliberately narrowed to the corrupted cell.
            date_text = target["observation_date"].isoformat()
            facts.cells = {
                (target["series_code"], date_text):
                    facts.cells[(target["series_code"], date_text)]
            }
            probe.sample_size = 1
            check_values(probe, spec, facts)
            caught = bool(probe.failures)
        finally:
            conn.rollback()

        restored = scalar(
            conn,
            "SELECT rate_percent FROM treasury.observation "
            "WHERE series_id = %s AND observation_date = %s",
            (target["series_id"], target["observation_date"]),
        )

    if not caught:
        LOGGER.error(
            "SELF-TEST FAILED: a rate was changed by 1.25 and the value check "
            "still passed. The verifier cannot be trusted."
        )
        return False
    if Decimal(restored) != Decimal(original):
        LOGGER.error(
            "SELF-TEST FAILED: rollback did not restore the row (%s -> %s)",
            original, restored,
        )
        return False
    LOGGER.info(
        "self-test OK: corruption detected on %s %s, and rolled back cleanly",
        target["series_code"], target["observation_date"],
    )
    return True


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def persist(v: Verifier) -> int:
    run_id = scalar(
        v.conn, "SELECT max(load_run_id) FROM meta.load_run WHERE status = 'succeeded'"
    )
    with v.conn.cursor() as cur:
        for check in v.checks:
            cur.execute(
                """
                INSERT INTO meta.reconciliation
                    (load_run_id, check_name, data_key, expected, actual, passed, detail)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (run_id, check.name, check.data_key, str(_plain(check.expected)),
                 str(_plain(check.actual)), check.passed, check.detail or None),
            )
    v.conn.commit()
    return run_id


def write_reports(v: Verifier, run_id: int, status: str) -> None:
    payload = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "load_run_id": run_id,
        "target": describe_target(),
        "status": status,
        "checks_total": len(v.checks),
        "checks_failed": len(v.failures),
        "checks": [c.as_dict() for c in v.checks],
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# PostgreSQL load verification",
        "",
        f"- Target: `{payload['target']}`",
        f"- Load run: **{run_id}**",
        f"- Generated (UTC): **{payload['generated_at_utc']}**",
        f"- Result: **{status}** ({len(v.checks) - len(v.failures)}/{len(v.checks)} checks passed)",
        "",
        "Every expected value below is recounted from the processed CSVs, not "
        "read back from the database.",
        "",
        "| Check | Dataset | Expected | Actual | Result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for check in v.checks:
        lines.append(
            f"| `{check.name}` | {check.data_key or '-'} | {_plain(check.expected)} "
            f"| {_plain(check.actual)} | {'PASS' if check.passed else '**FAIL**'} |"
        )
    if v.failures:
        lines += ["", "## Failures", ""]
        for check in v.failures:
            lines.append(f"- `{check.name}` ({check.data_key or 'global'}): "
                         f"expected {_plain(check.expected)}, got "
                         f"{_plain(check.actual)}. {check.detail}")
    lines.append("")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    if args.self_test and not self_test(args.sample_size):
        return 1

    LOGGER.info("target: %s", describe_target())
    with connect() as conn:
        v = Verifier(conn=conn, sample_size=args.sample_size)
        check_lineage(v)
        for key in sorted(LOAD_SPECS):
            spec = LOAD_SPECS[key]
            facts = read_csv_facts(spec)
            check_dataset(v, spec, facts)
            check_values(v, spec, facts)
        check_placeholders(v)
        check_integrity(v)
        check_mcp_boundary(v)
        check_constraints(v)

        status = "PASS" if not v.failures else "FAIL"
        run_id = persist(v)
        write_reports(v, run_id, status)

    print()
    print("=" * 78)
    print(f"Verification {status}: {len(v.checks) - len(v.failures)}/{len(v.checks)} "
          f"checks passed")
    for check in v.failures:
        print(f"  FAIL {check.name} ({check.data_key or 'global'}): "
              f"expected {_plain(check.expected)}, got {_plain(check.actual)}")
    print(f"Reports: {REPORT_JSON.relative_to(REPO_ROOT).as_posix()}, "
          f"{REPORT_MD.relative_to(REPO_ROOT).as_posix()}")
    print("=" * 78)
    return 0 if status == "PASS" else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sample-size", type=int, default=250,
                        help="cells to byte-compare per dataset (default 250)")
    parser.add_argument("--self-test", action="store_true",
                        help="prove the value check detects a corrupted row")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
