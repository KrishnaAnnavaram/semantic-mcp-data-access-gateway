"""One-time setup: give `mcp_reader` a password.

The password is deliberately not set in a migration. Migrations are committed,
and a credential in `.claude/src/postgres/migrations/` is a credential in git forever. So V009
creates the role without a password and this script sets it from the
environment, connecting as the owner.

    MCP_READER_PASSWORD=... python -m mcp_servers.data.bootstrap

Idempotent: safe to re-run, and re-running is how you rotate the password.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from mcp_servers.paths import REPO_ROOT

from psycopg2 import sql
from treasury_db.db import connect as owner_connect, describe_target, load_dotenv

logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(levelname)-7s %(message)s")
LOGGER = logging.getLogger("mcp_data.bootstrap")


def main() -> int:
    load_dotenv()
    password = os.environ.get("MCP_READER_PASSWORD")
    if not password:
        LOGGER.error(
            "MCP_READER_PASSWORD is not set. Add it to .env (it is git-ignored) "
            "or pass it in the environment for this command."
        )
        return 2
    if len(password) < 12:
        LOGGER.error("Refusing to set a password shorter than 12 characters.")
        return 2

    user = os.environ.get("MCP_READER_USER", "mcp_reader")
    LOGGER.info("target: %s", describe_target())

    with owner_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,))
            if cur.fetchone() is None:
                LOGGER.error(
                    "Role %r does not exist. Run the migrations first: "
                    "python -m treasury_db.migrate", user)
                return 1
            # Identifier is validated against pg_roles above, and the password
            # is bound as a literal rather than concatenated.
            cur.execute(
                sql.SQL("ALTER ROLE {} WITH PASSWORD %s").format(sql.Identifier(user)),
                (password,),
            )
        conn.commit()
    LOGGER.info("password set for %r", user)

    # Prove the credential actually works and lands on a constrained identity,
    # rather than reporting success and leaving the server to fail at startup.
    from ._db import assert_constrained_identity, connect as reader_connect  # noqa: PLC0415

    os.environ.setdefault("MCP_READER_PASSWORD", password)
    with reader_connect() as conn:
        assert_constrained_identity(conn)
    LOGGER.info("verified: %r connects and is not a superuser", user)
    return 0


if __name__ == "__main__":
    sys.exit(main())
