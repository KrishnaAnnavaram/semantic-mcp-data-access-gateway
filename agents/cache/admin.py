"""Narrow operational commands; only cache entries are ever cleared."""

from __future__ import annotations

import argparse
import json

from agents.cache.factory import get_intelligence


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or clear Redis intelligence")
    subparsers = parser.add_subparsers(dest="command", required=True)
    health = subparsers.add_parser("health")
    health.add_argument("--analytics", action="store_true")
    clear = subparsers.add_parser("clear")
    clear.add_argument("--scope", choices=("all", "domain", "mcp", "semantic"), default="all")
    args = parser.parse_args()
    intelligence = get_intelligence()
    result = (
        intelligence.health(include_analytics=args.analytics)
        if args.command == "health"
        else intelligence.clear(args.scope)
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
