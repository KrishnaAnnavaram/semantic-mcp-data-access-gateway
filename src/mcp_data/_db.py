"""Database access for the data MCP server.

Connects as `mcp_reader`, never as the owner. If the credentials are missing the
server refuses to start rather than silently falling back to a privileged
identity - a server that quietly runs as the owner looks identical to one that
is correctly constrained, right up until it does something it should not have
been able to do.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

import psycopg2
import psycopg2.extras

REPO_ROOT = Path(__file__).resolve().parents[2]

# The loading package already owns .env parsing; reuse it rather than keeping a
# second reader that can drift. `tools/verify_load.py` uses the same pattern.
sys.path.insert(0, str(REPO_ROOT / ".claude" / "loading"))
from _db import load_dotenv  # noqa: E402

LOGGER = logging.getLogger("mcp_data.db")


class ConfigurationError(RuntimeError):
    """Raised when the server cannot establish a correctly constrained identity."""


def connection_settings() -> dict[str, Any]:
    load_dotenv()
    url = os.environ.get("MCP_DATABASE_URL")
    if url:
        return {"dsn": url}

    password = os.environ.get("MCP_READER_PASSWORD")
    if not password:
        raise ConfigurationError(
            "No MCP_DATABASE_URL or MCP_READER_PASSWORD in the environment. "
            "This server must connect as the restricted `mcp_reader` role; it "
            "will not fall back to the owner account. Run "
            "`python -m src.mcp_data.bootstrap` once to set the password."
        )
    return {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "dbname": os.environ.get("POSTGRES_DB", "gateway"),
        "user": os.environ.get("MCP_READER_USER", "mcp_reader"),
        "password": password,
    }


@contextmanager
def connect() -> Iterator[psycopg2.extensions.connection]:
    conn = psycopg2.connect(**connection_settings())
    conn.set_session(readonly=True, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def assert_constrained_identity(conn) -> None:
    """Fail fast if this process is not actually running as a read-only role.

    Cheap insurance against a misconfigured `.env` pointing the server at the
    owner account, where every tool would still appear to work.
    """
    role = fetch_one(conn, "SELECT current_user AS role")["role"]
    if role != os.environ.get("MCP_READER_USER", "mcp_reader"):
        raise ConfigurationError(
            f"connected as {role!r}, expected the restricted reader role. "
            "Refusing to serve data from a privileged identity."
        )
    superuser = fetch_one(conn, "SELECT usesuper FROM pg_user WHERE usename = current_user")
    if superuser and superuser["usesuper"]:
        raise ConfigurationError(f"{role!r} is a superuser; refusing to start.")


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


def snapshot_id(conn, data_keys: Sequence[str] | None = None) -> str:
    """A content-addressed identifier for the data vintage in play.

    Derived from the SHA-256s of the raw Treasury files currently loaded, so it
    changes if and only if the underlying data changes. A restatement that
    revises history therefore produces a new snapshot id rather than silently
    reusing the old one - which is why callers can safely cache a result keyed
    on it. "The value for a past date never changes" is very nearly true and
    exactly the kind of nearly-true assumption that corrupts a cache.
    """
    if data_keys:
        rows = fetch_all(
            conn,
            "SELECT source_sha256 FROM analytics.v_source_file_current "
            "WHERE data_key = ANY(%s::text[]) ORDER BY source_sha256",
            (list(data_keys),),
        )
    else:
        rows = fetch_all(
            conn,
            "SELECT source_sha256 FROM analytics.v_source_file_current "
            "ORDER BY source_sha256",
        )
    digest = hashlib.sha256(
        "".join(r["source_sha256"] or "" for r in rows).encode()
    ).hexdigest()
    return f"treasury-{digest[:16]}"
