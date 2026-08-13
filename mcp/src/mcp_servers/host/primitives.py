"""Exercise all six MCP primitives against the live servers.

Three primitives flow client-to-server — **tools**, **resources**, **prompts**.
Three flow the other way, mid-call — **elicitation**, **roots**, **sampling** —
and on revision 2026-07-28 all three arrive as an ``InputRequiredResult`` the
client answers by retrying.

Run it with ``python -m mcp_servers.host --primitives``. Every step prints what
was asked and what came back, because the point is not that the calls succeed
but that the *direction* of each one is visible.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.types import InputRequiredResult

from .interaction import InteractionPolicy
from .mcp_clients import McpHost

RULE = "-" * 72


def _text(result: Any) -> str:
    return "".join(getattr(c, "text", "") for c in (getattr(result, "content", None) or []))


def _structured(result: Any) -> dict:
    data = getattr(result, "structured_content", None)
    if isinstance(data, dict):
        return data
    text = _text(result)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


def _head(n: int, title: str) -> None:
    print(f"\n{RULE}\n{n}. {title}\n{RULE}")


async def run_primitives() -> int:
    # A preset answer stands in for the human who would normally be asked. It is
    # written down here, in source, rather than guessed at inside the callback -
    # the whole point of elicitation is that nothing invents this value.
    policy = InteractionPolicy.default(
        elicitation="preset",
        preset_answers={"rate_kind": "real"},
    )

    async with McpHost(policy=policy) as host:
        data = host.servers["market-risk-data"].session
        risk = host.servers["risk-engine"].session

        print(f"protocol : {data.protocol_version}")
        print(f"roots    : {', '.join(str(p) for p in policy.roots) or '(none)'}")

        # --- 1. tools -------------------------------------------------------
        _head(1, "TOOLS  (client -> server)  the curve for the latest date")
        curve = _structured(await host.call("get_curve", {"curve_family": "nominal"}))
        points = curve.get("points", [])
        print(f"  observation_date : {curve.get('observation_date')}")
        print(f"  points           : {len(points)}")
        if points:
            p = points[0]
            print(f"  first point      : {p['series_code']} = {p['rate_percent']} "
                  f"({p['quote_basis']})")

        # --- 2. resources ---------------------------------------------------
        _head(2, "RESOURCES  (client -> server)  context, not data")
        listed = await data.list_resources()
        for res in listed.resources:
            print(f"  {str(res.uri):<45} {res.name}")
        read = await data.read_resource("market-risk://docs/provenance")
        body = "".join(getattr(c, "text", "") for c in read.contents)
        print(f"  read provenance  : {len(body)} chars, first line "
              f"{body.splitlines()[0]!r}")

        # --- 3. prompts -----------------------------------------------------
        _head(3, "PROMPTS  (client -> server)  user-controlled entry points")
        for server_name, session in (("market-risk-data", data), ("risk-engine", risk)):
            prompts = await session.list_prompts()
            names = [p.name for p in prompts.prompts]
            print(f"  {server_name:<18} {names}")
        got = await data.get_prompt("curve_snapshot", {"curve_family": "nominal"})
        first = got.messages[0]
        print(f"  curve_snapshot   : {getattr(first.content, 'text', '')[:110]}...")

        # --- 4. elicitation -------------------------------------------------
        _head(4, "ELICITATION  (server -> client, mid-call)  ambiguity the server cannot resolve")
        print("  calling search_series('30 year') - matches BC_30YEAR and TC_30YEAR")
        raw = await data.call_tool("search_series", {"query": "30 year"},
                                   allow_input_required=True)
        if isinstance(raw, InputRequiredResult):
            for key, req in (raw.input_requests or {}).items():
                print(f"  server asked     : {getattr(req, 'method', '?')}  (key {key})")
                params = getattr(req, "params", None)
                print(f"  question         : {getattr(params, 'message', '')[:150]}")
        else:
            print("  (no question raised)")
        # Now the same call through the host, which answers and retries.
        answered = _structured(await host.call("search_series", {"query": "30 year"}))
        print(f"  ambiguous        : {answered.get('ambiguous')}")
        print(f"  resolution       : {answered.get('resolution')}")
        print(f"  resolved_kind    : {answered.get('resolved_rate_kind')}")
        print(f"  matches after    : {[m['series_code'] for m in answered.get('matches', [])]}")

        # Control: the same tenor, but scoped to one dataset up front. One rate
        # kind, so nothing is asked and no round trip is paid.
        unambiguous = _structured(await host.call("search_series", {
            "query": "30 year", "data_key": "daily_treasury_yield_curve"}))
        print(f"  control query    : '30 year' scoped to the nominal dataset -> "
              f"resolution={unambiguous.get('resolution')}, "
              f"matches={[m['series_code'] for m in unambiguous.get('matches', [])]}")

        # --- 5. roots -------------------------------------------------------
        _head(5, "ROOTS  (server -> client, mid-call)  where the client permits writes")
        export = _structured(await host.call("export_curve_csv", {
            "filename": "latest_nominal_curve.csv", "curve_family": "nominal"}))
        print(f"  roots offered    : {export.get('roots_offered')}")
        print(f"  written_path     : {export.get('written_path')}")
        print(f"  rows / bytes     : {export.get('row_count')} / {export.get('bytes_written')}")
        if export.get("refused_reason"):
            print(f"  refused          : {export['refused_reason']}")

        escape = _structured(await host.call("export_curve_csv", {
            "filename": "../escaped.csv", "curve_family": "nominal"}))
        print(f"  containment test : '../escaped.csv' -> "
              f"{escape.get('refused_reason') or 'WROTE (BUG)'}")

        # --- 6. sampling ----------------------------------------------------
        _head(6, "SAMPLING  (server -> client, mid-call)  the server has no model")
        brief = _structured(await host.call("brief_dataset_caveat", {
            "data_key": "daily_treasury_yield_curve"}))
        print(f"  drafted_by_model : {brief.get('drafted_by_model')}")
        print(f"  briefing         : {(brief.get('briefing') or '')[:260]}")
        print(f"  verbatim caveat  : {(brief.get('verbatim_caveat') or '')[:160]}...")

        print(f"\n{RULE}")
        print("all six primitives exercised: tools, resources, prompts, "
              "elicitation, roots, sampling")
        print(RULE)
    return 0
