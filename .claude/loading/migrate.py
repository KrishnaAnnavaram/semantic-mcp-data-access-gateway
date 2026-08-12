#!/usr/bin/env python3
"""Apply the SQL migrations in db/migrations to the target database.

Deliberately small: no migration framework, no ORM, no downgrade path. The
whole contract is four rules.

  1. A migration file is applied exactly once, in filename order.
  2. Each migration runs inside its own transaction. A failure rolls that
     migration back completely - the database is never left half-migrated.
  3. The SHA-256 of every applied file is recorded. If a file that has already
     been applied is later edited, the next run FAILS instead of silently
     ignoring the change. Editing an applied migration is the single most
     common way a team's databases drift apart.
  4. Forward only. To change something, add V00N+1.

Usage::

    python .claude/loading/migrate.py            # apply everything pending
    python .claude/loading/migrate.py --status   # show what is applied
    python .claude/loading/migrate.py --dry-run  # list pending, change nothing
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import REPO_ROOT, connect, describe_target, fetch_all  # noqa: E402

LOGGER = logging.getLogger("us_treasury.migrate")

MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"
MIGRATION_PATTERN = re.compile(r"^V(\d+)__([A-Za-z0-9_\-]+)\.sql$")

LEDGER_DDL = """
CREATE SCHEMA IF NOT EXISTS meta;

CREATE TABLE IF NOT EXISTS meta.schema_migration (
    version      integer     PRIMARY KEY,
    name         text        NOT NULL,
    filename     text        NOT NULL,
    sha256       char(64)    NOT NULL,
    applied_at   timestamptz NOT NULL DEFAULT now(),
    duration_ms  integer     NOT NULL
);

COMMENT ON TABLE meta.schema_migration IS
    'Which migrations this database has. The sha256 is what makes an edited '
    'migration a loud failure instead of a silent divergence.';
"""


class MigrationError(RuntimeError):
    pass


def discover() -> list[tuple[int, str, Path]]:
    if not MIGRATIONS_DIR.is_dir():
        raise MigrationError(f"no migrations directory at {MIGRATIONS_DIR}")
    found: list[tuple[int, str, Path]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        match = MIGRATION_PATTERN.match(path.name)
        if not match:
            raise MigrationError(
                f"{path.name} does not match V<number>__<name>.sql - rename it "
                "or move it out of db/migrations/"
            )
        found.append((int(match.group(1)), match.group(2), path))
    versions = [v for v, _, _ in found]
    duplicates = {v for v in versions if versions.count(v) > 1}
    if duplicates:
        raise MigrationError(f"duplicate migration versions: {sorted(duplicates)}")
    return found


def sha256_of(path: Path) -> str:
    """Checksum a migration by its CONTENT, not its encoding.

    CRLF is normalised to LF first. Git rewrites line endings on checkout on
    Windows, so hashing raw bytes makes a migration's identity depend on which
    machine cloned it: every file looks "edited" on a fresh Windows clone and
    the drift guard fires on all of them at once. That turns a real safety
    check into noise people learn to ignore, which is worse than not having it.

    `.gitattributes` pins *.sql to LF as well; this is the belt to that
    braces, because a checkout can always be configured otherwise.
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def applied_migrations(conn) -> dict[int, dict]:
    rows = fetch_all(
        conn,
        "SELECT version, name, filename, sha256, applied_at FROM meta.schema_migration"
        " ORDER BY version",
    )
    return {row["version"]: row for row in rows}


def ensure_ledger(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(LEDGER_DDL)
    conn.commit()


def run(args: argparse.Namespace) -> int:
    migrations = discover()
    LOGGER.info("target: %s", describe_target())
    LOGGER.info("found %d migration(s) in %s", len(migrations), MIGRATIONS_DIR)

    with connect() as conn:
        ensure_ledger(conn)
        applied = applied_migrations(conn)

        # Rule 3: an already-applied migration must not have changed on disk.
        drifted: list[str] = []
        for version, name, path in migrations:
            record = applied.get(version)
            if record and record["sha256"] != sha256_of(path):
                drifted.append(
                    f"V{version:03d} {path.name}: applied "
                    f"{record['sha256'][:12]}..., on disk {sha256_of(path)[:12]}..."
                )
        if drifted:
            LOGGER.error("applied migrations have been edited since they ran:")
            for line in drifted:
                LOGGER.error("  %s", line)
            LOGGER.error(
                "Migrations are forward-only. Revert the edit and add a new "
                "migration instead."
            )
            return 2

        if args.status:
            print(f"{'ver':>5}  {'status':<9} {'applied at':<28} name")
            for version, name, path in migrations:
                record = applied.get(version)
                stamp = str(record["applied_at"]) if record else "-"
                state = "applied" if record else "PENDING"
                print(f"V{version:03d}  {state:<9} {stamp:<28} {name}")
            return 0

        pending = [(v, n, p) for v, n, p in migrations if v not in applied]
        if not pending:
            LOGGER.info("database is up to date (%d applied)", len(applied))
            return 0

        LOGGER.info("%d migration(s) pending", len(pending))
        if args.dry_run:
            for version, name, path in pending:
                LOGGER.info("  would apply V%03d %s", version, path.name)
            return 0

        for version, name, path in pending:
            sql = path.read_text(encoding="utf-8")
            started = time.monotonic()
            LOGGER.info("applying V%03d %s", version, path.name)
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    duration_ms = int((time.monotonic() - started) * 1000)
                    cur.execute(
                        """
                        INSERT INTO meta.schema_migration
                            (version, name, filename, sha256, duration_ms)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (version, name, path.name, sha256_of(path), duration_ms),
                    )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                LOGGER.error("V%03d FAILED and was rolled back: %s", version, exc)
                return 1
            LOGGER.info("  ok (%d ms)", duration_ms)

        LOGGER.info("migrated to V%03d", pending[-1][0])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--status", action="store_true", help="show applied/pending and exit")
    parser.add_argument("--dry-run", action="store_true", help="list pending, change nothing")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        return run(args)
    except MigrationError as exc:
        LOGGER.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
