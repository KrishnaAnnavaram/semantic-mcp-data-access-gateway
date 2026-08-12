#!/usr/bin/env python3
"""Verify the MCP servers honour their contracts.

Mirrors `verify_load.py`: checks are recorded, not printed, and the suite must
be able to fail. `--self-test` runs three canaries - deliberately broken tool
results that the checks are required to catch. A suite that has only ever
reported PASS is equally consistent with a suite that cannot detect anything.

    python tools/verify_mcp.py --self-test
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.mcp_data.server import server as data_server  # noqa: E402

LOGGER = logging.getLogger("verify_mcp")

REPORT_JSON = REPO_ROOT / "data" / "metadata" / "us_treasury" / "mcp_verification.json"
REPORT_MD = REPO_ROOT / "data" / "metadata" / "us_treasury" / "mcp_verification.md"

# Fields without which a rate is not an answer. A bare 4.26 could be a par
# yield, a bank-discount rate or a real yield; the reader cannot tell.
REQUIRED_RATE_FIELDS = {"series_code", "rate_kind", "quote_basis", "unit",
                        "observation_date", "rate_percent"}


@dataclass
class Check:
    name: str
    expected: Any
    actual: Any
    passed: bool
    detail: str = ""


@dataclass
class Verifier:
    checks: list[Check] = field(default_factory=list)

    def record(self, name: str, expected: Any, actual: Any,
               detail: str = "", passed: bool | None = None) -> Check:
        ok = (expected == actual) if passed is None else passed
        check = Check(name, expected, actual, ok, detail)
        self.checks.append(check)
        LOGGER.info("  [%s] %-42s expected=%s actual=%s%s",
                    "ok  " if ok else "FAIL", name, expected, actual,
                    f"  {detail}" if detail else "")
        return check

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]


# --- the assertions, reusable so canaries can be run through them -----------


def audit_rate_payloads(v: Verifier, label: str, payload: Any) -> None:
    """Every rate-shaped object anywhere in a payload must be fully described."""
    offenders: list[str] = []
    placeholders: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if "rate_percent" in node:
                missing = REQUIRED_RATE_FIELDS - set(node)
                if missing:
                    offenders.append(f"{path}: missing {sorted(missing)}")
                if node.get("series_code") == "BC_30YEARDISPLAY":
                    placeholders.append(path)
            for k, val in node.items():
                walk(val, f"{path}.{k}")
        elif isinstance(node, list):
            for i, val in enumerate(node):
                walk(val, f"{path}[{i}]")

    walk(payload, label)
    v.record(f"envelope_complete:{label}", 0, len(offenders),
             "; ".join(offenders[:3]) if offenders else "every rate carries its semantics")
    v.record(f"no_placeholder_series:{label}", 0, len(placeholders),
             "BC_30YEARDISPLAY must be unreachable through any tool")


def audit_synthetic_labelling(v: Verifier, label: str, payload: Any) -> None:
    """Demo data must announce itself wherever it appears."""
    unlabelled: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if "instrument_id" in node or "portfolio_id" in node:
                if node.get("data_classification") != "SYNTHETIC_DEMO":
                    unlabelled.append(path)
            for k, val in node.items():
                walk(val, f"{path}.{k}")
        elif isinstance(node, list):
            for i, val in enumerate(node):
                walk(val, f"{path}[{i}]")

    walk(payload, label)
    v.record(f"synthetic_labelled:{label}", 0, len(unlabelled),
             "demo rows must never appear unclassified")


# --- checks -----------------------------------------------------------------


async def check_tool_declarations(v: Verifier) -> None:
    LOGGER.info("tool declarations")
    tools = await data_server.list_tools()
    v.record("tools_advertised", True, len(tools) >= 12, f"{len(tools)} tools")
    v.record("all_have_output_schema", 0,
             sum(1 for t in tools if not t.output_schema),
             "structured results, not prose the model must parse")
    v.record("all_read_only", 0,
             sum(1 for t in tools
                 if not (t.annotations and t.annotations.read_only_hint)))
    v.record("none_destructive", 0,
             sum(1 for t in tools
                 if t.annotations and t.annotations.destructive_hint))
    v.record("all_described", 0, sum(1 for t in tools if not t.description),
             "an undescribed tool cannot be selected correctly")
    # Deterministic ordering lets a client cache tools/list and improves the
    # model's prompt-cache hit rate.
    again = await data_server.list_tools()
    v.record("tool_order_deterministic", [t.name for t in tools],
             [t.name for t in again], passed=[t.name for t in tools] == [t.name for t in again])
    # The single most important negative: no SQL escape hatch, anywhere.
    sql_like = [t.name for t in tools
                if any(w in t.name.lower() for w in ("sql", "query", "execute", "raw"))]
    v.record("no_sql_escape_hatch", [], sql_like,
             "a run_sql tool would move schema knowledge into the prompt")
    banned = {"columns", "table", "schema", "order_by", "sql", "where"}
    leaky = [f"{t.name}.{p}" for t in tools
             for p in (t.input_schema.get("properties") or {}) if p in banned]
    v.record("no_sql_fragment_parameters", [], leaky)


async def check_tool_behaviour(v: Verifier) -> None:
    LOGGER.info("tool behaviour")

    curve = (await data_server.call_tool("get_curve", {"curve_family": "nominal"})).structured_content
    v.record("curve_returns_points", True, len(curve["points"]) > 0,
             f"{len(curve['points'])} tenors on {curve['observation_date']}")
    audit_rate_payloads(v, "get_curve", curve)
    v.record("curve_has_provenance", True,
             bool(curve["provenance"]["source_sha256"]),
             curve["provenance"].get("source_file") or "")
    v.record("curve_tenors_unique", len(curve["points"]),
             len({p["tenor_months"] for p in curve["points"]}),
             "one node per tenor, or the bootstrap consumes a duplicate")
    v.record("curve_tenors_ordered", True,
             all(float(a["tenor_months"]) < float(b["tenor_months"])
                 for a, b in zip(curve["points"], curve["points"][1:])))

    hist = (await data_server.call_tool("get_rate_history", {
        "series_codes": ["BC_10YEAR"], "start_date": "2026-01-02",
        "end_date": "2026-08-11", "page_size": 50})).structured_content
    audit_rate_payloads(v, "get_rate_history", hist)
    v.record("history_paginates", True, hist["next_cursor"] is not None,
             f"{hist['returned']} rows returned, cursor issued")

    # A cursor must not survive a change of filters, or the caller silently
    # paginates through a different result set than they started.
    tampered = False
    try:
        await data_server.call_tool("get_rate_history", {
            "series_codes": ["BC_2YEAR"], "start_date": "2026-01-02",
            "end_date": "2026-08-11", "page_size": 50, "cursor": hist["next_cursor"]})
    except Exception as exc:
        tampered = "INVALID_CURSOR" in str(exc)
    v.record("cursor_bound_to_query", True, tampered,
             "replaying a cursor against different filters is rejected")

    edited = False
    try:
        bad = hist["next_cursor"][:-4] + "AAAA"
        await data_server.call_tool("get_rate_history", {
            "series_codes": ["BC_10YEAR"], "start_date": "2026-01-02",
            "end_date": "2026-08-11", "page_size": 50, "cursor": bad})
    except Exception as exc:
        edited = "INVALID_CURSOR" in str(exc)
    v.record("cursor_tamper_evident", True, edited)

    matrix = await data_server.call_tool("get_curve_history_matrix", {
        "curve_family": "nominal", "trading_days": 250,
        "tenors_months": [24, 60, 120, 360]})
    summary_bytes = len(json.dumps(matrix.structured_content))
    meta_bytes = len(json.dumps(matrix.meta))
    v.record("bulk_matrix_in_meta", True,
             "market-risk-data/curve_history_matrix" in (matrix.meta or {}))
    v.record("bulk_rates_absent_from_model_view", False,
             "rates_percent" in json.dumps(matrix.structured_content),
             f"summary {summary_bytes}B vs matrix {meta_bytes}B")
    v.record("bulk_matrix_shape", 250 * 4,
             len(matrix.meta["market-risk-data/curve_history_matrix"]["rates_percent"]) * 4)

    book = (await data_server.call_tool(
        "get_portfolio", {"portfolio_id": "TREASURY_DEMO_001"})).structured_content
    audit_synthetic_labelling(v, "get_portfolio", book)
    v.record("portfolio_classified_synthetic", "SYNTHETIC_DEMO",
             book["envelope"]["data_classification"])

    prov = (await data_server.call_tool("explain_number", {
        "series_code": "BC_10YEAR", "observation_date": "2026-08-11"})).structured_content
    v.record("explain_number_has_sha256", True,
             bool(prov["lineage"]["source_sha256"]),
             prov["lineage"].get("raw_file") or "")


async def check_error_contract(v: Verifier) -> None:
    """Errors must be actionable: the model should be able to retry successfully."""
    LOGGER.info("error contract")

    async def failing(name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            await data_server.call_tool(name, args)
        except Exception as exc:
            text = str(exc)
            return json.loads(text[text.find("{"):]) if "{" in text else {}
        return {}

    err = await failing("get_curve", {"curve_family": "nominal",
                                      "observation_date": "2026-07-04"})
    v.record("holiday_error_code", "DATE_NO_DATA", err.get("error_code"))
    v.record("holiday_error_offers_dates", True, bool(err.get("candidates")),
             "the model must be able to retry without a human")

    err = await failing("get_rate_history", {"series_codes": ["BC_10Y"],
                                             "start_date": "2026-01-01",
                                             "end_date": "2026-02-01"})
    v.record("unknown_series_error_code", "UNKNOWN_SERIES", err.get("error_code"))
    v.record("unknown_series_suggests_alternatives", True, bool(err.get("candidates")))

    err = await failing("get_curve_history_matrix", {
        "curve_family": "nominal", "as_of_date": "2005-06-30",
        "trading_days": 250, "tenors_months": [24, 120, 360]})
    v.record("missing_history_refuses_by_default", "MISSING_OBSERVATIONS",
             err.get("error_code"),
             "silently dropping dates changes any risk number computed from them")

    err = await failing("get_rate_history", {"series_codes": ["BC_10YEAR"],
                                             "start_date": "2026-08-01",
                                             "end_date": "2026-01-01"})
    v.record("reversed_range_rejected", "INVALID_DATE_RANGE", err.get("error_code"))

    # SQL metacharacters must die at the catalogue boundary, not reach the planner.
    err = await failing("get_rate_history", {
        "series_codes": ["BC_10YEAR'; DROP TABLE treasury.observation; --"],
        "start_date": "2026-01-01", "end_date": "2026-02-01"})
    v.record("sql_injection_rejected", "UNKNOWN_SERIES", err.get("error_code"),
             "rejected as an unknown series, never interpolated into SQL")


async def check_resources(v: Verifier) -> None:
    LOGGER.info("resources")
    resources = await data_server.list_resources()
    uris = {str(r.uri) for r in resources}
    v.record("catalogue_resources_present", True,
             {"market-risk://catalog/datasets", "market-risk://catalog/series"} <= uris,
             f"{len(uris)} resources")
    caveat = await data_server.read_resource("market-risk://caveats/daily_treasury_bill_rates")
    text = "".join(c.content for c in caveat if hasattr(c, "content"))
    v.record("caveat_resource_warns_on_quote_basis", True,
             "DISCOUNT" in text.upper() and "COUPON-EQUIVALENT" in text.upper(),
             "the bill caveat must state the basis trap")
    prompts = await data_server.list_prompts()
    v.record("prompts_present", True, len(prompts) >= 3, f"{len(prompts)} prompts")


# --- canaries ---------------------------------------------------------------


async def self_test() -> bool:
    """Prove the checks bite, by feeding them results that must be rejected."""
    LOGGER.info("self-test: three deliberately broken payloads")
    results: list[tuple[str, bool]] = []

    probe = Verifier()
    audit_rate_payloads(probe, "canary_missing_basis", {
        "points": [{"series_code": "BC_10YEAR", "rate_percent": "4.70",
                    "observation_date": "2026-08-11", "unit": "percent",
                    "rate_kind": "nominal"}]})  # quote_basis removed
    results.append(("rate without quote_basis", bool(probe.failures)))

    probe = Verifier()
    audit_rate_payloads(probe, "canary_placeholder", {
        "points": [{"series_code": "BC_30YEARDISPLAY", "rate_percent": "0.0000",
                    "observation_date": "1995-01-03", "unit": "percent",
                    "rate_kind": "nominal", "quote_basis": "par_coupon_semiannual"}]})
    results.append(("placeholder series leaked", bool(probe.failures)))

    probe = Verifier()
    audit_synthetic_labelling(probe, "canary_unlabelled_demo", {
        "positions": [{"instrument_id": "DEMO_NOTE_10Y", "face_notional": "8000000"}]})
    results.append(("demo position unlabelled", bool(probe.failures)))

    ok = True
    for label, caught in results:
        LOGGER.info("  canary %-28s %s", label, "caught" if caught else "MISSED")
        ok = ok and caught
    if not ok:
        LOGGER.error("SELF-TEST FAILED: a canary went undetected. The suite cannot be trusted.")
    else:
        LOGGER.info("self-test OK: all three canaries were caught")
    return ok


# --- reporting --------------------------------------------------------------


def write_reports(v: Verifier, status: str) -> None:
    import datetime as dt  # noqa: PLC0415
    payload = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "status": status,
        "checks_total": len(v.checks),
        "checks_failed": len(v.failures),
        "checks": [{"check": c.name, "expected": c.expected, "actual": c.actual,
                    "passed": c.passed, "detail": c.detail} for c in v.checks],
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")

    lines = ["# MCP server verification", "",
             f"- Result: **{status}** "
             f"({len(v.checks) - len(v.failures)}/{len(v.checks)} checks passed)",
             f"- Generated (UTC): {payload['generated_at_utc']}", "",
             "| Check | Expected | Actual | Result |", "| --- | --- | --- | --- |"]
    for c in v.checks:
        lines.append(f"| `{c.name}` | {c.expected} | {c.actual} | "
                     f"{'PASS' if c.passed else '**FAIL**'} |")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def run(args: argparse.Namespace) -> int:
    if args.self_test and not await self_test():
        return 1
    v = Verifier()
    await check_tool_declarations(v)
    await check_tool_behaviour(v)
    await check_error_contract(v)
    await check_resources(v)

    status = "PASS" if not v.failures else "FAIL"
    write_reports(v, status)
    print()
    print("=" * 78)
    print(f"MCP verification {status}: "
          f"{len(v.checks) - len(v.failures)}/{len(v.checks)} checks passed")
    for c in v.failures:
        print(f"  FAIL {c.name}: expected {c.expected}, got {c.actual}  {c.detail}")
    print("=" * 78)
    return 0 if status == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--self-test", action="store_true",
                        help="prove the checks detect broken payloads")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), stream=sys.stderr,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
