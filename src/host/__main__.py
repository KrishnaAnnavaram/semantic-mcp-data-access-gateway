"""CLI entry point for the MCP host.

    python -m src.host --demo       run the end-to-end demo
    python -m src.host --tools      list what the two servers offer
    python -m src.host --isolation  prove the risk engine has no database access
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .mcp_clients import DATA_ENV_KEYS, McpHost, RISK_SERVER, sanitised_env


async def list_tools() -> int:
    async with McpHost() as host:
        for name, connected in host.servers.items():
            print(f"\n{name}  ({len(connected.tools)} tools)")
            for tool in connected.tools:
                first_line = (tool.description or "").strip().split("\n")[0]
                print(f"  {tool.name:<32} {first_line[:70]}")
            resources = await connected.session.list_resources()
            for res in resources.resources:
                print(f"  [resource] {str(res.uri):<21} {res.name}")
    return 0


async def check_isolation() -> int:
    """Show that the calculation boundary is enforced by what the child was given.

    The risk engine cannot reach the database because its environment contains
    no way to find or authenticate to one - not because it declines to try.
    """
    risk_env = sanitised_env(RISK_SERVER.env_keys)
    leaked = sorted(k for k in risk_env if k in DATA_ENV_KEYS or "PASSWORD" in k.upper()
                    or "DATABASE" in k.upper())
    print("risk-engine child environment")
    print(f"  variables passed : {len(risk_env)} ({', '.join(sorted(risk_env))})")
    print(f"  database/secrets : {leaked or 'none'}")

    async with McpHost() as host:
        tools = {t.name for t in host.servers["risk-engine"].tools}
        db_shaped = {t for t in tools
                     if any(w in t.lower() for w in ("sql", "query", "curve_history",
                                                     "portfolio_positions"))}
        print(f"  data-fetch tools : {db_shaped or 'none'}")
    ok = not leaked and not db_shaped
    print(f"\nisolation {'HOLDS' if ok else 'VIOLATED'}")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true", help="run the end-to-end demo")
    group.add_argument("--tools", action="store_true", help="list discovered tools")
    group.add_argument("--isolation", action="store_true",
                       help="prove the risk engine has no database access")
    parser.add_argument("--log-level", default="WARNING",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), stream=sys.stderr,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")

    if args.tools:
        return asyncio.run(list_tools())
    if args.isolation:
        return asyncio.run(check_isolation())
    from .demo import run_demo  # noqa: PLC0415
    return asyncio.run(run_demo())


if __name__ == "__main__":
    sys.exit(main())
