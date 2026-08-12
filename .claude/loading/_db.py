"""Shared database plumbing for the loading stage.

Connection settings come from the environment, in this order:

  1. ``DATABASE_URL``
  2. ``POSTGRES_HOST`` / ``POSTGRES_PORT`` / ``POSTGRES_DB`` /
     ``POSTGRES_USER`` / ``POSTGRES_PASSWORD``

``.env`` at the repository root is read first if present, so the same file
drives both Docker Compose and the loader and the two can never disagree about
which database is being written to.
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:
    import psycopg2
    import psycopg2.extras
except ImportError:  # pragma: no cover - dependency guard
    raise SystemExit(
        "This stage requires psycopg2. Install it with: pip install psycopg2-binary"
    )

LOGGER = logging.getLogger("us_treasury.db")

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"

_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def load_dotenv(path: Path = ENV_FILE) -> dict[str, str]:
    """Read a .env file without adding a dependency.

    Values already present in the real environment win, so an operator can
    override a single setting for one command without editing the file.
    """
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _ENV_LINE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        loaded[key] = value
        os.environ.setdefault(key, value)
    return loaded


def connection_settings() -> dict[str, Any]:
    load_dotenv()
    url = os.environ.get("DATABASE_URL")
    if url:
        return {"dsn": url}
    return {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "dbname": os.environ.get("POSTGRES_DB", "gateway"),
        "user": os.environ.get("POSTGRES_USER", "gateway"),
        "password": os.environ.get("POSTGRES_PASSWORD", ""),
    }


def describe_target() -> str:
    """Human-readable target, with the password redacted."""
    settings = connection_settings()
    if "dsn" in settings:
        return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", settings["dsn"])
    return (
        f"postgresql://{settings['user']}:***@{settings['host']}:"
        f"{settings['port']}/{settings['dbname']}"
    )


@contextmanager
def connect(autocommit: bool = False) -> Iterator["psycopg2.extensions.connection"]:
    settings = connection_settings()
    conn = psycopg2.connect(**settings)
    conn.autocommit = autocommit
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(conn, sql: str, params: Any = None) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def fetch_one(conn, sql: str, params: Any = None) -> dict[str, Any] | None:
    rows = fetch_all(conn, sql, params)
    return rows[0] if rows else None


def scalar(conn, sql: str, params: Any = None) -> Any:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None


def table_columns(conn, schema: str, table: str) -> list[str]:
    return [
        row["column_name"]
        for row in fetch_all(
            conn,
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
    ]
