"""The end-to-end demo: data server -> host -> risk engine.

Deliberately has no LLM in it. This path is the *mechanical* chain, and it needs
to be verifiable on its own: if a VaR number is wrong, you want to know whether
the plumbing is broken before you start asking whether the model reasoned badly.
The reasoning layer goes on top of exactly these calls.

The route the bulk data takes is the point:

    data server --(_meta)--> host --(typed argument)--> risk engine

2,750 yields never enter model context, and the risk engine receives them as
data rather than reaching for a database it has no credentials for.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

from .mcp_clients import McpHost

LOGGER = logging.getLogger("host.demo")

MATRIX_META_KEY = "market-risk-data/curve_history_matrix"
PORTFOLIO_ID = "TREASURY_DEMO_001"


def _structured(result: Any) -> dict[str, Any]:
    """Pull structured content out of a tool result, or raise with its error."""
    if getattr(result, "is_error", False):
        text = "".join(getattr(c, "text", "") for c in (result.content or []))
        raise RuntimeError(text or "tool reported an error with no detail")
    if result.structured_content is not None:
        return result.structured_content
    text = "".join(getattr(c, "text", "") for c in (result.content or []))
    return json.loads(text) if text.strip().startswith("{") else {"text": text}


def _money(x: float) -> str:
    return f"{x:>16,.2f}"


def _portfolio_for_engine(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Reshape the data server's portfolio into the engine's input contract.

    The two contracts are close but not identical, and that is intentional: the
    data server describes what is stored, the engine describes what it can
    price. Translating here keeps neither one bent to suit the other.
    """
    return {
        "portfolio_id": snapshot["portfolio"]["portfolio_id"],
        "data_classification": "SYNTHETIC_DEMO",
        "positions": [
            {
                "instrument": {
                    "instrument_id": p["instrument"]["instrument_id"],
                    "face_value": float(p["instrument"]["face_value"]),
                    "coupon_rate_pct": float(p["instrument"]["coupon_rate_pct"]),
                    "issue_date": p["instrument"]["issue_date"],
                    "maturity_date": p["instrument"]["maturity_date"],
                },
                "face_notional": float(p["face_notional"]),
            }
            for p in snapshot["positions"]
        ],
    }


def _curve_for_engine(curve: dict[str, Any]) -> dict[str, Any]:
    return {
        "observation_date": curve["observation_date"],
        "curve_family": curve["curve_family"],
        "tenors_months": [float(p["tenor_months"]) for p in curve["points"]],
        "rates_percent": [float(p["rate_percent"]) for p in curve["points"]],
        "dataset_snapshot_id": curve["envelope"]["dataset_snapshot_id"],
    }


async def run_demo() -> int:
    async with McpHost() as host:
        tools = host.all_tools()
        print()
        print("=" * 78)
        print("semantic-mcp-data-access-gateway — Treasury market-risk demo")
        print("=" * 78)
        print(f"servers   : {', '.join(host.servers)}")
        print(f"tools     : {len(tools)} discovered at runtime "
              f"({sum(1 for t in tools if host.owner_of(t.name) == 'market-risk-data')} data, "
              f"{sum(1 for t in tools if host.owner_of(t.name) == 'risk-engine')} risk)")

        # --- 1. facts ------------------------------------------------------
        book = _structured(await host.call("get_portfolio", {"portfolio_id": PORTFOLIO_ID}))
        curve = _structured(await host.call("get_curve", {"curve_family": "nominal"}))
        valuation_date = curve["observation_date"]

        print()
        print(f"[1] Portfolio  {book['portfolio']['name']}")
        print(f"    {len(book['positions'])} positions, "
              f"{book['envelope']['data_classification']}")
        print(f"[2] Curve      {valuation_date}, {len(curve['points'])} tenors, "
              f"snapshot {curve['envelope']['dataset_snapshot_id']}")
        print(f"    provenance {curve['provenance']['source_file']} "
              f"sha256 {curve['provenance']['source_sha256'][:12]}")

        engine_book = _portfolio_for_engine(book)
        engine_curve = _curve_for_engine(curve)

        # --- 2. value and sensitivity ---------------------------------------
        priced = _structured(await host.call("price_portfolio_tool", {
            "portfolio": engine_book, "valuation_date": valuation_date,
            "par_curve": engine_curve}))
        print()
        print(f"[3] Mark to market      {_money(priced['total_present_value'])} USD")
        for p in priced["positions"]:
            print(f"      {p['instrument_id']:<16}{_money(p['present_value'])}")

        dv01 = _structured(await host.call("compute_dv01_tool", {
            "portfolio": engine_book, "valuation_date": valuation_date,
            "par_curve": engine_curve}))
        print()
        print(f"[4] DV01                {_money(dv01['dv01'])} per basis point")

        krd = _structured(await host.call("compute_key_rate_dv01_tool", {
            "portfolio": engine_book, "valuation_date": valuation_date,
            "par_curve": engine_curve,
            "key_tenors_months": [24, 60, 120, 240, 360]}))
        print("[5] Key-rate DV01")
        for k in krd["key_rate_dv01"]:
            print(f"      {int(k['tenor_months'] / 12):>3}Y        {_money(k['dv01'])}")

        # --- 3. bulk history: _meta -> host -> engine ------------------------
        matrix_result = await host.call("get_curve_history_matrix", {
            "curve_family": "nominal", "as_of_date": valuation_date,
            "trading_days": 250, "tenors_months": [24, 60, 120, 240, 360]})
        summary = _structured(matrix_result)
        matrix = (matrix_result.meta or {})[MATRIX_META_KEY]

        model_bytes = len(json.dumps(summary))
        matrix_bytes = len(json.dumps(matrix))
        print()
        print(f"[6] History             {summary['trading_days_returned']} trading days "
              f"x {len(summary['tenors_months'])} tenors "
              f"= {summary['point_count']} observations")
        print(f"      model context     {model_bytes:,} bytes (summary only)")
        print(f"      routed via _meta  {matrix_bytes:,} bytes "
              f"({matrix_bytes / model_bytes:.0f}x larger, never seen by a model)")

        var = _structured(await host.call("compute_historical_risk_tool", {
            "portfolio": engine_book, "valuation_date": valuation_date,
            "par_curve": engine_curve,
            "history_tenors_months": [float(t) for t in matrix["tenors_months"]],
            "history_rates_percent": [[float(x) for x in row]
                                      for row in matrix["rates_percent"]],
            "confidence_level": 0.99, "horizon_days": 1}))
        print()
        print(f"[7] Historical VaR 99% / 1 day")
        print(f"      VaR               {_money(var['var'])}")
        print(f"      Expected Shortfall{_money(var['expected_shortfall'])}")
        print(f"      worst scenario    {_money(var['worst_loss'])}")
        print(f"      scenarios         {var['scenarios_used']}")

        # --- 4. stress -------------------------------------------------------
        scenarios = _structured(await host.call("list_scenarios",
                                                {"scenario_type": "TENOR_VECTOR_BP"}))
        print()
        print("[8] Hypothetical stress")
        for s in scenarios["scenarios"][:3]:
            shocks = s["shock_definition"]["tenor_months"]
            applicable = {k: v for k, v in shocks.items()
                          if float(k) in {float(p["tenor_months"]) for p in curve["points"]}}
            stressed = _structured(await host.call("run_stress_tool", {
                "portfolio": engine_book, "valuation_date": valuation_date,
                "par_curve": engine_curve, "shocks_bp_by_tenor_months": applicable}))
            print(f"      {s['name']:<22}{_money(stressed['pnl'])}")

        # --- 5. historical replay --------------------------------------------
        print()
        print("[9] Historical replay — real dates, real moves")
        replays = _structured(await host.call("list_scenarios",
                                              {"scenario_type": "HISTORICAL_REPLAY"}))
        for s in replays["scenarios"]:
            defn = s["shock_definition"]
            try:
                before = _structured(await host.call("get_curve", {
                    "curve_family": "nominal",
                    "observation_date": defn["from_date"], "date_policy": "previous"}))
                after = _structured(await host.call("get_curve", {
                    "curve_family": "nominal",
                    "observation_date": defn["to_date"], "date_policy": "next"}))
            except RuntimeError as exc:
                print(f"      {s['name']:<42}unavailable: {str(exc)[:40]}")
                continue

            # The DIFFERENCE is computed here, in the host, from two observed
            # curves. The data server does no arithmetic; the risk engine
            # receives an ordinary shock vector and does not know or care that
            # it came from history.
            b = {float(p["tenor_months"]): float(p["rate_percent"]) for p in before["points"]}
            a = {float(p["tenor_months"]): float(p["rate_percent"]) for p in after["points"]}
            live = {float(p["tenor_months"]) for p in curve["points"]}
            shocks = {str(t): (a[t] - b[t]) * 100.0
                      for t in sorted(set(a) & set(b) & live)}
            if not shocks:
                print(f"      {s['name']:<42}no overlapping tenors")
                continue
            stressed = _structured(await host.call("run_stress_tool", {
                "portfolio": engine_book, "valuation_date": valuation_date,
                "par_curve": engine_curve, "shocks_bp_by_tenor_months": shocks}))
            # Tenor keys are stringified floats ("120.0"), so look the 10-year
            # up by value rather than by an assumed spelling.
            move = next((v for k, v in shocks.items() if float(k) == 120.0), None)
            label = f"10y {move:+.0f}bp" if move is not None else "10y n/a"
            print(f"      {s['name']:<42}{_money(stressed['pnl'])}  ({label})")

        # --- 6. reproducibility ----------------------------------------------
        again = _structured(await host.call("compute_historical_risk_tool", {
            "portfolio": engine_book, "valuation_date": valuation_date,
            "par_curve": engine_curve,
            "history_tenors_months": [float(t) for t in matrix["tenors_months"]],
            "history_rates_percent": [[float(x) for x in row]
                                      for row in matrix["rates_percent"]],
            "confidence_level": 0.99, "horizon_days": 1}))
        identical = (again["reproducibility"]["run_fingerprint"]
                     == var["reproducibility"]["run_fingerprint"]
                     and again["var"] == var["var"])
        print()
        print("[10] Reproducibility")
        print(f"      fingerprint       {var['reproducibility']['run_fingerprint'][:32]}")
        print(f"      re-run identical  {identical}")
        print(f"      market snapshot   {var['reproducibility']['dataset_snapshot_id']}")
        print(f"      method            {var['model']['historical_risk_version']}, "
              f"{var['model']['quantile_method']}")

        print()
        print("-" * 78)
        print(f"Market data : REAL, verified, {curve['envelope']['dataset_snapshot_id']}")
        print(f"Portfolio   : {book['envelope']['data_classification']} — invented for demonstration")
        print(f"Values      : model-implied from the par curve, not executable prices")
        print("-" * 78)
        return 0 if identical else 1
