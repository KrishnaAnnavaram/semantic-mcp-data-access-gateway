"""Composed risk workflows — where the two MCP servers are joined.

The data server holds facts and does no arithmetic. The risk engine does
arithmetic and holds no facts. Something has to carry a curve from one to the
other, and that something is the host — here.

Each function below is one question a person would actually ask ("what is this
book worth", "what do I lose in a 1994 repeat") expressed as a short sequence
of tool calls. Keeping them here rather than in the model's context matters:
marshalling a portfolio into the engine's input shape is mechanical work with
one right answer, and a model that improvises it will eventually improvise it
differently.

The bulk history for VaR travels through `_meta`, so 1,250 yields reach the
risk engine without ever entering model context.
"""

from __future__ import annotations

from typing import Any

MATRIX_META_KEY = "market-risk-data/curve_history_matrix"
DEFAULT_KEY_TENORS = [24, 60, 120, 240, 360]


def _fail(result: dict, what: str) -> dict | None:
    return {"error": f"{what} failed", "detail": result["error"]} if "error" in result else None


def _portfolio_for_engine(snapshot: dict) -> dict:
    """Reshape the data server's portfolio into the engine's input contract."""
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


def _curve_for_engine(curve: dict) -> dict:
    return {
        "observation_date": curve["observation_date"],
        "curve_family": curve["curve_family"],
        "tenors_months": [float(p["tenor_months"]) for p in curve["points"]],
        "rates_percent": [float(p["rate_percent"]) for p in curve["points"]],
        "dataset_snapshot_id": curve["envelope"]["dataset_snapshot_id"],
    }


class RiskWorkflows:
    """Bound to an McpDataProvider; each method is one end-to-end question."""

    def __init__(self, provider: Any) -> None:
        self.p = provider

    # -- shared setup ---------------------------------------------------------

    def _book_and_curve(self, portfolio_id: str,
                        curve_date: str | None) -> tuple[dict, dict, str] | dict:
        book = self.p.call_tool("get_portfolio", {"portfolio_id": portfolio_id})
        if (bad := _fail(book, "get_portfolio")):
            return bad
        args: dict[str, Any] = {"curve_family": "nominal"}
        if curve_date:
            args["observation_date"] = curve_date
            args["date_policy"] = "previous"
        curve = self.p.call_tool("get_curve", args)
        if (bad := _fail(curve, "get_curve")):
            return bad
        return (_portfolio_for_engine(book), _curve_for_engine(curve),
                curve["observation_date"])

    # -- workflows ------------------------------------------------------------

    def list_portfolios(self) -> dict:
        return self.p.call_tool("list_portfolios")

    def get_portfolio(self, portfolio_id: str) -> dict:
        return self.p.call_tool("get_portfolio", {"portfolio_id": portfolio_id})

    def list_scenarios(self, scenario_type: str | None = None) -> dict:
        args = {"scenario_type": scenario_type} if scenario_type else {}
        return self.p.call_tool("list_scenarios", args)

    def price_portfolio(self, portfolio_id: str, curve_date: str | None = None) -> dict:
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        out = self.p.call_tool("price_portfolio_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve})
        if (bad := _fail(out, "price_portfolio")):
            return bad
        return {
            "valuation_date": date,
            "total_present_value": out["total_present_value"],
            "positions": [{"instrument_id": p["instrument_id"],
                           "present_value": p["present_value"]}
                          for p in out["positions"]],
            "note": "Dirty (full) present value, model-implied from the par curve. "
                    "Not an executable price.",
            "data_classification": "SYNTHETIC_DEMO portfolio, REAL_MARKET_DATA curve",
        }

    def compute_dv01(self, portfolio_id: str, curve_date: str | None = None,
                     key_rates: bool = False) -> dict:
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        payload = {"portfolio": book, "valuation_date": date, "par_curve": curve}
        out = self.p.call_tool("compute_dv01_tool", payload)
        if (bad := _fail(out, "compute_dv01")):
            return bad
        result = {"valuation_date": date, "dv01": out["dv01"],
                  "units": "USD per basis point, full revaluation"}
        if key_rates:
            krd = self.p.call_tool("compute_key_rate_dv01_tool",
                                   {**payload, "key_tenors_months": DEFAULT_KEY_TENORS})
            if "error" not in krd:
                result["key_rate_dv01"] = krd["key_rate_dv01"]
        return result

    def compute_var(self, portfolio_id: str, confidence_level: float = 0.99,
                    horizon_days: int = 1, trading_days: int = 250,
                    curve_date: str | None = None) -> dict:
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup

        summary, meta = self.p.call_tool_with_meta("get_curve_history_matrix", {
            "curve_family": "nominal", "as_of_date": date,
            "trading_days": trading_days, "tenors_months": DEFAULT_KEY_TENORS})
        if (bad := _fail(summary, "get_curve_history_matrix")):
            return bad
        matrix = meta.get(MATRIX_META_KEY)
        if not matrix:
            return {"error": "history matrix missing from _meta"}

        out = self.p.call_tool("compute_historical_risk_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "history_tenors_months": [float(t) for t in matrix["tenors_months"]],
            "history_rates_percent": [[float(x) for x in row]
                                      for row in matrix["rates_percent"]],
            "confidence_level": confidence_level, "horizon_days": horizon_days})
        if (bad := _fail(out, "compute_historical_risk")):
            return bad
        return {
            "valuation_date": date,
            "confidence_level": confidence_level,
            "horizon_days": horizon_days,
            "var": out["var"],
            "expected_shortfall": out["expected_shortfall"],
            "worst_loss": out["worst_loss"],
            "scenarios_used": out["scenarios_used"],
            "method": out["model"]["historical_risk_version"],
            "quantile_method": out["model"]["quantile_method"],
            "run_fingerprint": out["reproducibility"]["run_fingerprint"],
            "note": (f"Historical simulation from {summary['trading_days_returned']} "
                     "observed trading days. h-day changes are observed over h days, "
                     "never 1-day scaled by sqrt(h). Analytical demonstration, "
                     "not a regulatory figure."),
        }

    def run_stress(self, portfolio_id: str,
                   shocks_bp_by_tenor_months: dict[str, float] | None = None,
                   scenario_id: str | None = None,
                   curve_date: str | None = None) -> dict:
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        live = set(curve["tenors_months"])
        label = "custom shock vector"

        if scenario_id:
            s = self.p.call_tool("get_scenario", {"scenario_id": scenario_id})
            if (bad := _fail(s, "get_scenario")):
                return bad
            label = s["name"]
            defn = s["shock_definition"]
            if s["scenario_type"] == "HISTORICAL_REPLAY":
                shocks_bp_by_tenor_months = self._replay_shocks(defn, live)
                if isinstance(shocks_bp_by_tenor_months, dict) and \
                        "error" in shocks_bp_by_tenor_months:
                    return shocks_bp_by_tenor_months
            else:
                shocks_bp_by_tenor_months = {
                    k: v for k, v in defn["tenor_months"].items() if float(k) in live}

        if not shocks_bp_by_tenor_months:
            return {"error": "no shocks given; pass shocks_bp_by_tenor_months or scenario_id"}

        out = self.p.call_tool("run_stress_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "shocks_bp_by_tenor_months": shocks_bp_by_tenor_months})
        if (bad := _fail(out, "run_stress")):
            return bad
        return {"valuation_date": date, "scenario": label,
                "shocks_bp": shocks_bp_by_tenor_months,
                "stressed_value": out["stressed_value"], "pnl": out["pnl"]}

    def _replay_shocks(self, defn: dict, live: set) -> dict:
        """Difference two real observed curves, in the host, into a shock vector.

        The data server performs no arithmetic and the risk engine never learns
        the vector came from history — it receives an ordinary shock.
        """
        before = self.p.call_tool("get_curve", {
            "curve_family": "nominal", "observation_date": defn["from_date"],
            "date_policy": "previous"})
        if (bad := _fail(before, "get_curve(from_date)")):
            return bad
        after = self.p.call_tool("get_curve", {
            "curve_family": "nominal", "observation_date": defn["to_date"],
            "date_policy": "next"})
        if (bad := _fail(after, "get_curve(to_date)")):
            return bad
        b = {float(p["tenor_months"]): float(p["rate_percent"]) for p in before["points"]}
        a = {float(p["tenor_months"]): float(p["rate_percent"]) for p in after["points"]}
        return {str(t): round((a[t] - b[t]) * 100.0, 4)
                for t in sorted(set(a) & set(b) & live)}

    def explain_number(self, series_code: str, observation_date: str) -> dict:
        return self.p.call_tool("explain_number", {
            "series_code": series_code, "observation_date": observation_date})
