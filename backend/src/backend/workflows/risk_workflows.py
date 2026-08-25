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

import datetime as dt
from typing import Any

MATRIX_META_KEY = "market-risk-data/curve_history_matrix"
DEFAULT_KEY_TENORS = [24, 60, 120, 240, 360]

DEMO_CLASSIFICATION = "SYNTHETIC_DEMO portfolio, REAL_MARKET_DATA curve"

STRESS_NOTE = (
    "Full revaluation under an explicit tenor shock vector, which is returned "
    "with the result. P&L is stressed value minus base value, so a negative "
    "number is a loss."
)

#: Named curve-shape scenarios the engine implements, mirrored here so the
#: adapter can dispatch to the right tool. These are *names*, not mathematics.
TEMPLATE_SCENARIOS = {
    "BEAR_STEEPENER", "BULL_STEEPENER", "BEAR_FLATTENER", "BULL_FLATTENER",
}
CURVATURE_SHAPES = {
    "belly_selloff", "belly_rally", "wings_selloff", "wings_rally",
}

#: The engine's published control points, in tenor MONTHS, as multiples of the
#: requested severity. Mirrored only so a stress-contribution request can be
#: expressed as the explicit vector that tool takes. No revaluation happens
#: here; if these ever diverge from the engine a contract test fails.
TEMPLATE_CONTROL_POINTS: dict[str, dict[float, float]] = {
    "BEAR_STEEPENER": {24.0: 0.25, 60.0: 0.50, 120.0: 1.00, 360.0: 1.50},
    "BULL_STEEPENER": {24.0: -1.50, 60.0: -1.00, 120.0: -0.50, 360.0: -0.25},
    "BEAR_FLATTENER": {24.0: 1.50, 60.0: 1.00, 120.0: 0.50, 360.0: 0.25},
    "BULL_FLATTENER": {24.0: -0.25, 60.0: -0.50, 120.0: -1.00, 360.0: -1.50},
    "BELLY_SELLOFF": {24.0: 0.25, 60.0: 1.00, 120.0: 1.00, 360.0: 0.25},
    "BELLY_RALLY": {24.0: -0.25, 60.0: -1.00, 120.0: -1.00, 360.0: -0.25},
    "WINGS_SELLOFF": {24.0: 1.00, 60.0: 0.25, 120.0: 0.25, 360.0: 1.00},
    "WINGS_RALLY": {24.0: -1.00, 60.0: -0.25, 120.0: -0.25, 360.0: -1.00},
}

#: Documented crisis windows, mirrored from the engine's own catalogue so a
#: named replay can be resolved to the two dates whose curves must be fetched.
#: Dates only - the shock is always measured from published data at run time.
CRISIS_WINDOWS: dict[str, tuple[str, str]] = {
    "1994_BOND_SELLOFF": ("1994-01-31", "1994-11-30"),
    "2008_GFC_LEHMAN": ("2008-09-12", "2008-12-31"),
    "2013_TAPER_TANTRUM": ("2013-05-01", "2013-09-05"),
    "2020_COVID_SHOCK": ("2020-02-19", "2020-03-09"),
    "2022_FED_TIGHTENING": ("2022-01-03", "2022-10-24"),
    "2023_REGIONAL_BANK_STRESS": ("2023-03-08", "2023-03-24"),
}

#: How a user-facing scenario name maps to a reverse-stress shape the engine
#: understands. Anything unrecognised falls back to a parallel move.
_REVERSE_SHAPES = {
    "parallel": "PARALLEL", "bear_steepener": "BEAR_STEEPENER",
    "bull_steepener": "BULL_STEEPENER", "bear_flattener": "BEAR_FLATTENER",
    "bull_flattener": "BULL_FLATTENER", "belly_selloff": "BELLY_SELLOFF",
    "wings_selloff": "WINGS_SELLOFF",
}


def _reverse_shape(scenario: str | None) -> str:
    return _REVERSE_SHAPES.get((scenario or "parallel").strip().lower(), "PARALLEL")


def _add_days(date: str, days: int) -> str:
    return (dt.date.fromisoformat(date) + dt.timedelta(days=days)).isoformat()


def _add_months(date: str, months: int) -> str:
    """Month arithmetic that clamps to the end of a short month."""
    start = dt.date.fromisoformat(date)
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    last = (dt.date(year + (month // 12), month % 12 + 1, 1)
            - dt.timedelta(days=1)).day
    return dt.date(year, month, min(start.day, last)).isoformat()


def _dated_curve(curve: dict) -> dict:
    """The engine's DatedCurveInput shape."""
    return {"observation_date": curve["observation_date"],
            "tenors_months": curve["tenors_months"],
            "rates_percent": curve["rates_percent"]}


def _fail(result: dict, what: str) -> dict | None:
    return {"error": f"{what} failed", "detail": result["error"]} if "error" in result else None


def _needs(capability: str, missing: dict[str, str], detail: str) -> dict:
    """A structured request for input the user has to supply.

    Returned rather than raised, and returned rather than guessed. The MCP agent
    passes it up unchanged and the orchestrator asks - the same path a mid-call
    elicitation already takes. Substituting a plausible default here would
    answer a question nobody asked, and the answer would carry the same
    confidence as a correct one.
    """
    return {"error": f"{capability} needs input that was not supplied",
            "needs": missing, "detail": detail}

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

    # -- shared setup for the expanded capabilities ---------------------------

    def _history(self, date: str, trading_days: int = 250,
                 tenors_months: list[int] | None = None) -> tuple[dict, dict] | dict:
        """Fetch the aligned curve history, keeping the matrix out of model context.

        The numbers travel in the result's `_meta` channel exactly as they
        already do for VaR: a 250 x 5 matrix is 1,250 yields, and the reasoning
        layer never needs to read one. This helper exists so the eight
        capabilities that need history do not each re-implement that routing.
        """
        summary, meta = self.p.call_tool_with_meta("get_curve_history_matrix", {
            "curve_family": "nominal", "as_of_date": date,
            "trading_days": trading_days,
            "tenors_months": tenors_months or DEFAULT_KEY_TENORS})
        if (bad := _fail(summary, "get_curve_history_matrix")):
            return bad
        matrix = meta.get(MATRIX_META_KEY)
        if not matrix:
            return {"error": "history matrix missing from _meta"}
        return summary, {
            "tenors_months": [float(t) for t in matrix["tenors_months"]],
            "rates_percent": [[float(x) for x in row]
                              for row in matrix["rates_percent"]],
            "dates": matrix.get("dates"),
        }

    def _curve_on(self, observation_date: str) -> dict:
        """One published curve, in the engine's input shape."""
        curve = self.p.call_tool("get_curve", {
            "curve_family": "nominal", "observation_date": observation_date,
            "date_policy": "previous"})
        if "error" in curve:
            return curve
        return _curve_for_engine(curve)

    @staticmethod
    def _shock_vector(shock: dict[str, Any] | None) -> dict[str, float]:
        """Render a returned shock vector compactly, in months."""
        if not shock:
            return {}
        return {k: round(float(v), 4)
                for k, v in (shock.get("shocks_bp_by_tenor_months") or {}).items()}

    def _stress_summary(self, out: dict, label: str, top_n: int = 3) -> dict:
        """The compact shape every stress capability returns.

        Deliberately small. The engine returns per-position and per-tenor detail
        for every scenario; the reasoning layer needs the headline, the shape of
        the shock and the few largest contributors. Everything else stays in the
        engine's own result and out of model context.
        """
        positions = sorted(out.get("positions") or [],
                           key=lambda p: p.get("pnl", 0.0))[:top_n]
        return {
            "scenario": label,
            "base_value": out.get("base_value"),
            "stressed_value": out.get("stressed_value"),
            "pnl": out.get("pnl"),
            "pnl_percent": out.get("pnl_percent"),
            "shock_bp_by_tenor_months": self._shock_vector(out.get("shock")),
            "top_position_contributors": [
                {"instrument_id": p.get("instrument_id"), "pnl": p.get("pnl")}
                for p in positions],
            "top_tenor_contributors": (out.get("top_tenor_contributors") or [])[:top_n],
            "tenor_residual_pnl": out.get("tenor_residual_pnl"),
            "warnings": out.get("warnings") or [],
            "run_fingerprint": (out.get("reproducibility") or {}).get("run_fingerprint"),
            "note": STRESS_NOTE,
        }

    # -- bond and curve analytics --------------------------------------------

    def compute_bond_analytics(self, portfolio_id: str,
                               curve_date: str | None = None) -> dict:
        """Per-bond valuation analytics: price split, yield, duration, convexity."""
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        out = self.p.call_tool("compute_bond_analytics_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve})
        if (bad := _fail(out, "compute_bond_analytics")):
            return bad
        return {
            "valuation_date": date,
            "instruments": [{
                "instrument_id": row["instrument_id"],
                "clean_price_per_100": row["clean_price_per_100"],
                "dirty_price_per_100": row["dirty_price_per_100"],
                "accrued_per_100": row["accrued_per_100"],
                "ytm_percent": row["ytm_percent"],
                "current_yield_percent": row["current_yield_percent"],
                "macaulay_duration_years": row["macaulay_duration_years"],
                "modified_duration_years": row["modified_duration_years"],
                "effective_duration_years": row["effective_duration_years"],
                "dollar_duration": row["dollar_duration"],
                "convexity": row["convexity"],
                "effective_convexity": row["effective_convexity"],
            } for row in out.get("instruments", [])],
            "portfolio": out.get("portfolio"),
            "conventions": out.get("conventions"),
            "note": "Clean price plus accrued equals dirty price exactly. "
                    "Yield-based and curve-based durations are different "
                    "measures and are reported separately.",
            "data_classification": DEMO_CLASSIFICATION,
        }

    def compute_curve_analytics(self, curve_date: str | None = None,
                                tenors_months: list[float] | None = None) -> dict:
        """Zero rates, forwards, named spreads, butterflies and inversion."""
        args: dict[str, Any] = {"curve_family": "nominal"}
        if curve_date:
            args["observation_date"] = curve_date
            args["date_policy"] = "previous"
        curve = self.p.call_tool("get_curve", args)
        if (bad := _fail(curve, "get_curve")):
            return bad
        payload: dict[str, Any] = {"par_curve": _curve_for_engine(curve)}
        if tenors_months:
            payload["tenors_months"] = [float(t) for t in tenors_months]
        out = self.p.call_tool("compute_curve_analytics_tool", payload)
        if (bad := _fail(out, "compute_curve_analytics")):
            return bad
        return {
            "observation_date": curve["observation_date"],
            "spreads": out.get("spreads"),
            "butterflies": out.get("butterflies"),
            "inversion": out.get("inversion"),
            "shape": out.get("shape"),
            "tenor_points": out.get("tenor_points"),
            "forward_rates": (out.get("forward_rates") or [])[:8],
            "conventions": out.get("conventions"),
            "warnings": out.get("warnings") or [],
            "data_classification": "REAL_MARKET_DATA",
        }

    def compute_rate_volatility(self, trading_days: int = 250,
                                horizon_days: int = 1,
                                curve_date: str | None = None) -> dict:
        """Realised volatility of published par yields. Not option-implied vol."""
        date = curve_date or self._latest_curve_date()
        if isinstance(date, dict):
            return date
        history = self._history(date, trading_days)
        if isinstance(history, dict):
            return history
        summary, matrix = history
        out = self.p.call_tool("compute_rate_volatility_tool", {
            "history": matrix, "horizon_days": horizon_days})
        if (bad := _fail(out, "compute_rate_volatility")):
            return bad
        return {
            "as_of_date": summary.get("as_of_date"),
            "observations": out.get("change_count"),
            "horizon_days": out.get("horizon_days"),
            "per_tenor": out.get("per_tenor"),
            "covariance_is_positive_semidefinite":
                out.get("covariance_is_positive_semidefinite"),
            "highest_volatility_window": out.get("highest_volatility_window"),
            "method": out.get("method"),
            "note": "Realised rate volatility in basis points, measured from "
                    "published par yields. This is not option-implied "
                    "volatility - this system holds no options.",
        }

    def compute_carry_roll(self, portfolio_id: str, horizon_days: int = 365,
                           curve_date: str | None = None) -> dict:
        """Carry and roll-down over a holding period on an unchanged curve."""
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        horizon = _add_days(date, max(1, int(horizon_days)))
        out = self.p.call_tool("compute_carry_roll_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "horizon_date": horizon})
        if (bad := _fail(out, "compute_carry_roll")):
            return bad
        return {
            "valuation_date": date, "horizon_date": out.get("horizon_date"),
            "horizon_days": out.get("horizon_days"),
            "carry": out.get("carry"), "roll_down": out.get("roll_down"),
            "total_carry_and_roll": out.get("total_carry_and_roll"),
            "annualised_percent": out.get("annualised_carry_and_roll_percent"),
            "cash_received": out.get("cash_received"),
            "method": out.get("method"),
            "note": "Carry is measured against the forward curve; roll-down is "
                    "the extra the curve's slope provides and is zero on a flat "
                    "curve. Coupons are counted at face, not reinvested.",
            "data_classification": DEMO_CLASSIFICATION,
        }

    # -- sensitivities --------------------------------------------------------

    def compute_rate_sensitivities(self, portfolio_id: str,
                                   curve_date: str | None = None) -> dict:
        """DV01, key-rate DV01, buckets, duration and convexity, reconciled."""
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        out = self.p.call_tool("compute_rate_sensitivities_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve})
        if (bad := _fail(out, "compute_rate_sensitivities")):
            return bad
        return {
            "valuation_date": date,
            "base_value": out.get("base_value"),
            "dv01": out.get("dv01"),
            "dollar_duration": out.get("dollar_duration"),
            "effective_duration_years": out.get("effective_duration_years"),
            "effective_convexity": out.get("effective_convexity"),
            "key_rate_dv01": [{"tenor_months": k["tenor_months"],
                               "key_rate_dv01": k["key_rate_dv01"],
                               "share_percent": k["share_percent"]}
                              for k in out.get("key_rate_dv01", [])],
            "maturity_buckets": out.get("maturity_buckets"),
            "positions": [{"instrument_id": p["instrument_id"], "dv01": p["dv01"],
                           "dv01_share_percent": p["dv01_share_percent"]}
                          for p in out.get("positions", [])],
            "reconciliation": out.get("reconciliation"),
            "units": "USD per basis point, full revaluation",
            "data_classification": DEMO_CLASSIFICATION,
        }

    def compute_risk_contributions(self, portfolio_id: str,
                                   risk_measure: str = "var",
                                   confidence_level: float = 0.99,
                                   horizon_days: int = 1,
                                   trading_days: int = 250,
                                   curve_date: str | None = None) -> dict:
        """Component, marginal and incremental VaR or ES per position."""
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        history = self._history(date, trading_days)
        if isinstance(history, dict):
            return history
        _, matrix = history
        out = self.p.call_tool("compute_risk_contributions_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "history": matrix, "risk_measure": risk_measure,
            "confidence_level": confidence_level, "horizon_days": horizon_days})
        if (bad := _fail(out, "compute_risk_contributions")):
            return bad
        return {
            "valuation_date": date, "measure": out.get("measure"),
            "confidence_level": out.get("confidence_level"),
            "horizon_days": out.get("horizon_days"),
            "portfolio_measure": out.get("portfolio_measure"),
            "scenario_count": out.get("scenario_count"),
            "positions": out.get("positions"),
            "reconciliation_difference": out.get("reconciliation_difference"),
            "note": "Component figures are exact Euler decompositions and sum to "
                    "the portfolio measure. Incremental figures answer a "
                    "different question and do not sum to anything.",
            "data_classification": DEMO_CLASSIFICATION,
        }

    def compute_concentration(self, portfolio_id: str, top_n: int = 5,
                              curve_date: str | None = None) -> dict:
        """Where the rate risk is bunched up, by position, tenor and bucket."""
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        out = self.p.call_tool("compute_concentration_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "top_n": top_n})
        if (bad := _fail(out, "compute_concentration")):
            return bad
        return {
            "valuation_date": date, "base_value": out.get("base_value"),
            "dimensions": [{
                "dimension": d["dimension"], "unit": d["unit"],
                "top_share_percent": d["top_share_percent"],
                "top_three_share_percent": d["top_three_share_percent"],
                "herfindahl_index": d["herfindahl_index"],
                "effective_count": d["effective_count"],
                "entries": d["entries"],
            } for d in out.get("dimensions", [])],
            "basis": out.get("basis"),
            "data_classification": DEMO_CLASSIFICATION,
        }

    # -- standardised stress --------------------------------------------------

    def run_rate_stress(self, portfolio_id: str, scenario: str | None = None,
                        shock_bp: float | None = None,
                        severity_bp: float = 100.0,
                        pivot_tenor_months: float = 120.0,
                        curve_date: str | None = None) -> dict:
        """Named deterministic rate scenarios, all by full revaluation.

        One capability rather than four, because a planner choosing between
        `run_rate_stress`, `run_curve_twist_stress` and
        `run_curve_curvature_stress` is choosing between names, not between
        questions. The adapter dispatches to the right engine tool; the
        mathematics is entirely the engine's.
        """
        if not scenario:
            return _needs("run_rate_stress",
                          {"scenario": "which rate scenario to run"},
                          "Name the scenario: parallel, bear_steepener, "
                          "bull_steepener, bear_flattener, bull_flattener, "
                          "twist, belly_selloff or wings_selloff.")
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        base = {"portfolio": book, "valuation_date": date, "par_curve": curve}
        key = scenario.strip().lower()

        if key in {"parallel", "parallel_up", "parallel_down"}:
            move = shock_bp if shock_bp is not None else severity_bp
            if key == "parallel_down" and move > 0:
                move = -move
            tool, payload, label = ("run_rate_stress_tool",
                                    {**base, "parallel_shock_bp": float(move)},
                                    f"Parallel {float(move):+.0f}bp")
        elif key == "twist":
            magnitude = shock_bp if shock_bp is not None else severity_bp
            tool, payload, label = ("run_curve_twist_stress_tool",
                                    {**base, "pivot_tenor_months": pivot_tenor_months,
                                     "magnitude_bp": float(magnitude)},
                                    f"Twist about {pivot_tenor_months / 12:g}y")
        elif key in CURVATURE_SHAPES:
            tool, payload, label = ("run_curve_curvature_stress_tool",
                                    {**base, "shape": key.upper(),
                                     "severity_bp": severity_bp},
                                    key.replace("_", " ").title())
        elif key.upper() in TEMPLATE_SCENARIOS:
            tool, payload, label = ("run_rate_stress_tool",
                                    {**base, "template": key.upper(),
                                     "severity_bp": severity_bp},
                                    key.replace("_", " ").title())
        else:
            # One vocabulary, lower case, so the error a planner reads back
            # is spelled the way the parameter must be supplied.
            return {"error": f"unknown rate scenario {scenario!r}",
                    "available": sorted(
                        {t.lower() for t in TEMPLATE_SCENARIOS}
                        | set(CURVATURE_SHAPES)
                        | {"parallel", "parallel_up", "parallel_down", "twist"})}

        out = self.p.call_tool(tool, payload)
        if (bad := _fail(out, "run_rate_stress")):
            return bad
        return {"valuation_date": date, **self._stress_summary(out, label)}

    def run_key_rate_stress(self, portfolio_id: str,
                            tenor_months: float | None = None,
                            shock_bp: float | None = None,
                            curve_date: str | None = None) -> dict:
        """Move one curve node and nothing else."""
        missing = {}
        if tenor_months is None:
            missing["tenor_months"] = "which curve node to shock, in months"
        if shock_bp is None:
            missing["shock_bp"] = "how far to move it, in basis points"
        if missing:
            return _needs("run_key_rate_stress", missing,
                          "A key-rate stress moves one named node by a named "
                          "amount; neither can be assumed.")
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        out = self.p.call_tool("run_key_rate_stress_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "key_tenors_months": [float(tenor_months)], "shock_bp": float(shock_bp)})
        if (bad := _fail(out, "run_key_rate_stress")):
            return bad
        return {"valuation_date": date,
                **self._stress_summary(
                    out, f"Key rate {float(tenor_months) / 12:g}y {shock_bp:+.0f}bp")}

    def run_shock_ladder(self, portfolio_id: str,
                         curve_date: str | None = None) -> dict:
        """P&L across a ladder of parallel shocks, with the convexity error."""
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        out = self.p.call_tool("run_shock_ladder_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve})
        if (bad := _fail(out, "run_shock_ladder")):
            return bad
        return {
            "valuation_date": date, "base_value": out.get("base_value"),
            "effective_duration_years": out.get("effective_duration_years"),
            "effective_convexity": out.get("effective_convexity"),
            "rungs": [{"shock_bp": r.get("shock_bp"), "pnl": r.get("pnl"),
                       "pnl_percent": r.get("pnl_percent"),
                       "duration_only_error": r.get("duration_only_error")}
                      for r in out.get("rungs", [])],
            "convexity_note": out.get("convexity_note"),
            "data_classification": DEMO_CLASSIFICATION,
        }

    def run_stress_matrix(self, portfolio_id: str,
                          curve_date: str | None = None) -> dict:
        """The standard scenario pack in one pass, ranked worst first."""
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        out = self.p.call_tool("run_stress_matrix_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve})
        if (bad := _fail(out, "run_stress_matrix")):
            return bad
        return {
            "valuation_date": date,
            "pack_version": out.get("pack_version"),
            "base_value": out.get("base_value"),
            "scenario_count": out.get("scenario_count"),
            # Rank, name, P&L and the driver. The full shock vector of every one
            # of twenty-one scenarios is not something a reader needs, and it is
            # roughly two hundred numbers.
            "scenarios": [{
                "rank": s["rank"], "scenario_name": s["scenario_name"],
                "pnl": s["pnl"], "pnl_percent": s["pnl_percent"],
                "largest_position_contributor": s["largest_position_contributor"],
                "largest_bucket_contributor": s["largest_bucket_contributor"],
            } for s in out.get("scenarios", [])],
            "comparison": out.get("comparison"),
            "not_run": out.get("failed") or [],
            "skipped": out.get("skipped") or [],
            "note": STRESS_NOTE,
            "data_classification": DEMO_CLASSIFICATION,
        }

    def compute_stress_contributions(self, portfolio_id: str,
                                     scenario: str | None = None,
                                     shock_bp: float | None = None,
                                     severity_bp: float = 100.0,
                                     curve_date: str | None = None) -> dict:
        """Which positions and which parts of the curve drive a stress loss."""
        if not scenario:
            return _needs("compute_stress_contributions",
                          {"scenario": "which stress scenario to decompose"},
                          "A decomposition needs the scenario whose loss is "
                          "being explained.")
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        shocks = self._scenario_shocks(scenario, shock_bp, severity_bp, curve)
        if isinstance(shocks, dict) and "error" in shocks:
            return shocks
        out = self.p.call_tool("compute_stress_contributions_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "shocks_bp_by_tenor_months": shocks})
        if (bad := _fail(out, "compute_stress_contributions")):
            return bad
        summary = self._stress_summary(out, scenario, top_n=5)
        summary["tenor_contributions"] = out.get("top_tenor_contributors")
        summary["maturity_buckets"] = out.get("maturity_buckets")
        summary["position_concentration"] = out.get("position_concentration")
        return {"valuation_date": date, **summary}

    def _scenario_shocks(self, scenario: str, shock_bp: float | None,
                         severity_bp: float, curve: dict) -> dict[str, float] | dict:
        """Build an explicit tenor shock vector for a named scenario.

        Shape only - the multipliers are the engine's published template
        definitions, mirrored here so a contribution request can be expressed as
        the explicit vector the contribution tool takes. No revaluation and no
        financial mathematics happens in this method.
        """
        tenors = [float(t) for t in curve["tenors_months"]]
        key = (scenario or "parallel").strip().lower()
        if key.startswith("parallel"):
            move = shock_bp if shock_bp is not None else severity_bp
            if key == "parallel_down" and move > 0:
                move = -move
            return {str(t): float(move) for t in tenors}
        control = TEMPLATE_CONTROL_POINTS.get(key.upper())
        if control is None:
            return {"error": f"unknown scenario {scenario!r} for contributions",
                    "available": sorted(TEMPLATE_CONTROL_POINTS)}
        points = sorted((months, multiple * severity_bp)
                        for months, multiple in control.items())
        out: dict[str, float] = {}
        for tenor in tenors:
            if tenor <= points[0][0]:
                out[str(tenor)] = points[0][1]
            elif tenor >= points[-1][0]:
                out[str(tenor)] = points[-1][1]
            else:
                for (x0, v0), (x1, v1) in zip(points, points[1:]):
                    if x0 <= tenor <= x1:
                        weight = 0.0 if x1 == x0 else (tenor - x0) / (x1 - x0)
                        out[str(tenor)] = v0 + (v1 - v0) * weight
                        break
        return out

    # -- historical stress ----------------------------------------------------

    def run_historical_stress(self, portfolio_id: str,
                              crisis_id: str | None = None,
                              start_date: str | None = None,
                              end_date: str | None = None,
                              curve_date: str | None = None) -> dict:
        """Replay an observed curve move, by name or by explicit dates.

        The shock is never stored: both paths difference two curves the data
        server actually published. A named crisis resolves to documented dates
        through the engine's own catalogue.
        """
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup

        if crisis_id:
            window = CRISIS_WINDOWS.get(crisis_id.upper())
            if window is None:
                return {"error": f"unknown crisis {crisis_id!r}",
                        "available": sorted(CRISIS_WINDOWS)}
            start_date, end_date = window
        if not (start_date and end_date):
            return {"error": "a historical replay needs either a crisis name or "
                             "both a start and an end date",
                    "available_crises": sorted(CRISIS_WINDOWS)}

        before = self._curve_on(start_date)
        if "error" in before:
            return before
        after = self._curve_on(end_date)
        if "error" in after:
            return after

        payload = {"portfolio": book, "valuation_date": date, "par_curve": curve,
                   "historical_start_curve": _dated_curve(before),
                   "historical_end_curve": _dated_curve(after),
                   "missing_tenor_policy": "intersection"}
        if crisis_id:
            payload["crisis_id"] = crisis_id.upper()
            payload["historical_curves"] = [_dated_curve(before), _dated_curve(after)]
            payload.pop("historical_start_curve")
            payload.pop("historical_end_curve")
            out = self.p.call_tool("run_historical_crisis_stress_tool", payload)
        else:
            out = self.p.call_tool("run_historical_stress_tool", payload)
        if (bad := _fail(out, "run_historical_stress")):
            return bad

        label = out.get("crisis_name") or (
            f"{out.get('historical_start')} to {out.get('historical_end')}")
        summary = self._stress_summary(out, label)
        summary.update({
            "historical_start": out.get("historical_start"),
            "historical_end": out.get("historical_end"),
            "crisis_id": out.get("crisis_id"),
            "observed_shocks_bp_by_tenor_months":
                out.get("observed_shocks_bp_by_tenor_months"),
            "tenors_unshocked_months": out.get("tenors_unshocked_months"),
            "note": "The shock is the observed difference between two published "
                    "Treasury curves, measured at run time. Nothing was invented.",
        })
        return {"valuation_date": date, **summary}

    def find_worst_historical_stresses(self, portfolio_id: str,
                                       horizon_days: int = 1, top_n: int = 10,
                                       trading_days: int = 250,
                                       curve_date: str | None = None) -> dict:
        """Which observed rate moves would have hurt this book most."""
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        history = self._history(date, trading_days)
        if isinstance(history, dict):
            return history
        _, matrix = history
        out = self.p.call_tool("find_worst_historical_stresses_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "history": matrix, "horizon_days": horizon_days,
            "top_n": min(int(top_n), 100)})
        if (bad := _fail(out, "find_worst_historical_stresses")):
            return bad
        return {
            "valuation_date": date, "base_value": out.get("base_value"),
            "horizon_days": out.get("horizon_days"),
            "scenarios_considered": out.get("scenarios_considered"),
            "window": [out.get("first_date"), out.get("last_date")],
            "worst": [{
                "rank": w["rank"], "start_date": w["start_date"],
                "end_date": w["end_date"], "pnl": w["pnl"],
                "pnl_percent": w["pnl_percent"],
                "largest_position_contributor": w["largest_position_contributor"],
            } for w in out.get("worst", [])],
            "best_pnl": out.get("best_pnl"),
            "note": "Every candidate is an observed move applied to today's book "
                    "and revalued in full.",
            "data_classification": DEMO_CLASSIFICATION,
        }

    # -- reverse stress -------------------------------------------------------

    def run_reverse_stress(self, portfolio_id: str,
                           target_loss: float | None = None,
                           scenario: str = "parallel",
                           curve_date: str | None = None) -> dict:
        """Solve for the rate move that produces a stated loss."""
        if target_loss is None:
            return _needs("run_reverse_stress",
                          {"target_loss": "the loss to solve for, as a "
                                          "positive amount"},
                          "Reverse stress solves for the move that causes a "
                          "stated loss. Assuming the amount would answer a "
                          "different question.")
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        out = self.p.call_tool("run_reverse_stress_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "target_loss": float(target_loss),
            "shape": _reverse_shape(scenario)})
        if (bad := _fail(out, "run_reverse_stress")):
            return bad
        return {
            "valuation_date": date, "target_loss": out.get("target_loss"),
            "shape": out.get("shape_name"),
            "solved_shock_bp": out.get("solved_shock_bp_at_reference_tenor"),
            "solved_multiplier": out.get("solved_multiplier"),
            "resulting_pnl": out.get("resulting_pnl"),
            "converged": out.get("converged"),
            "iterations": out.get("iterations"),
            "search_interval": [out.get("search_low"), out.get("search_high")],
            "monotone": out.get("monotone_over_bracket"),
            "shock_bp_by_tenor_months": self._shock_vector(out.get("shock")),
            "warnings": out.get("warnings") or [],
            "note": "A solved stress magnitude, not an observed one. It says "
                    "nothing about how likely that move is.",
            "data_classification": DEMO_CLASSIFICATION,
        }

    def compute_stress_thresholds(self, portfolio_id: str,
                                  target_losses: list[float] | None = None,
                                  scenario: str = "parallel",
                                  curve_date: str | None = None) -> dict:
        """The rate move needed to reach each of several loss levels."""
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        payload: dict[str, Any] = {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "shape": _reverse_shape(scenario)}
        if target_losses:
            payload["target_losses"] = [float(t) for t in target_losses]
        out = self.p.call_tool("compute_stress_thresholds_tool", payload)
        if (bad := _fail(out, "compute_stress_thresholds")):
            return bad
        return {
            "valuation_date": date, "shape": out.get("shape_name"),
            "base_value": out.get("base_value"),
            "rows": [{"target_loss": r["target_loss"],
                      "solved_shock_bp": r["solved_shock_bp_at_reference_tenor"],
                      "converged": r["converged"],
                      "unreachable_reason": r["unreachable_reason"]}
                     for r in out.get("rows", [])],
            "data_classification": DEMO_CLASSIFICATION,
        }

    def find_limit_breach_stress(self, portfolio_id: str,
                                 limit_amount: float | None = None,
                                 scenario: str = "parallel",
                                 amber_utilisation_percent: float = 80.0,
                                 curve_date: str | None = None) -> dict:
        """The stress severity at which a stated loss limit goes amber, then red."""
        if limit_amount is None:
            return _needs("find_limit_breach_stress",
                          {"limit_amount": "the loss limit, as a positive "
                                           "amount"},
                          "This system holds no risk policy and will not "
                          "assume a limit. Supply the limit the desk actually "
                          "runs.")
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        out = self.p.call_tool("find_limit_breach_stress_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "limit_amount": float(limit_amount),
            "amber_utilisation_percent": float(amber_utilisation_percent),
            "shape": _reverse_shape(scenario)})
        if (bad := _fail(out, "find_limit_breach_stress")):
            return bad
        return {
            "valuation_date": date, "limit_amount": out.get("limit_amount"),
            "amber_amount": out.get("amber_amount"),
            "breach_shock_bp": out.get("breach_shock_bp"),
            "amber_shock_bp": out.get("amber_shock_bp"),
            "breach_reason": out.get("breach_reason"),
            "amber_reason": out.get("amber_reason"),
            "warnings": out.get("warnings") or [],
            "note": "The limit is a caller-supplied input. This system holds no "
                    "risk policy of its own.",
            "data_classification": DEMO_CLASSIFICATION,
        }

    # -- distribution risk ----------------------------------------------------

    def compute_parametric_risk(self, portfolio_id: str,
                                confidence_level: float = 0.99,
                                horizon_days: int = 1, trading_days: int = 250,
                                curve_date: str | None = None) -> dict:
        """Delta-normal VaR and ES. A different model from historical simulation."""
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        history = self._history(date, trading_days)
        if isinstance(history, dict):
            return history
        _, matrix = history
        out = self.p.call_tool("compute_parametric_risk_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "history": matrix, "confidence_level": confidence_level,
            "horizon_days": horizon_days})
        if (bad := _fail(out, "compute_parametric_risk")):
            return bad
        return {
            "valuation_date": date, "confidence_level": out.get("confidence_level"),
            "horizon_days": out.get("horizon_days"),
            "horizon_method": out.get("horizon_method"),
            "var": out.get("var"), "expected_shortfall": out.get("expected_shortfall"),
            "portfolio_volatility": out.get("portfolio_volatility"),
            "observations_used": out.get("observations_used"),
            "factors": [{"tenor_months": f["tenor_months"],
                         "component_var": f["component_var"],
                         "component_percent": f["component_percent"]}
                        for f in out.get("factors", [])],
            "distribution": out.get("distribution"),
            "method": out.get("method"),
            "note": "Delta-normal: a linear key-rate approximation under an "
                    "assumed normal distribution. Not historical simulation.",
            "data_classification": DEMO_CLASSIFICATION,
        }

    def compute_monte_carlo_risk(self, portfolio_id: str,
                                 confidence_level: float = 0.99,
                                 horizon_days: int = 1,
                                 scenario_count: int = 5000,
                                 random_seed: int = 20260824,
                                 trading_days: int = 250,
                                 curve_date: str | None = None) -> dict:
        """Simulated VaR and ES with full revaluation on every path."""
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        history = self._history(date, trading_days)
        if isinstance(history, dict):
            return history
        _, matrix = history
        out = self.p.call_tool("compute_monte_carlo_risk_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "history": matrix, "confidence_level": confidence_level,
            "horizon_days": horizon_days,
            "scenario_count": int(scenario_count), "random_seed": int(random_seed)})
        if (bad := _fail(out, "compute_monte_carlo_risk")):
            return bad
        return {
            "valuation_date": date, "confidence_level": out.get("confidence_level"),
            "horizon_days": out.get("horizon_days"),
            "scenario_count": out.get("scenario_count"),
            "scenarios_priced": out.get("scenarios_priced"),
            "random_seed": out.get("random_seed"),
            "var": out.get("var"), "expected_shortfall": out.get("expected_shortfall"),
            "mean_pnl": out.get("mean_pnl"), "stdev_pnl": out.get("stdev_pnl"),
            "worst_pnl": out.get("worst_pnl"),
            "percentiles_pnl": out.get("percentiles_pnl"),
            "covariance_repaired": out.get("covariance_repaired"),
            "method": out.get("method"), "distribution": out.get("distribution"),
            "note": "Same inputs, same manifest and same seed reproduce this "
                    "number exactly.",
            "data_classification": DEMO_CLASSIFICATION,
        }

    def compare_risk_methods(self, portfolio_id: str,
                             confidence_level: float = 0.99,
                             horizon_days: int = 1, trading_days: int = 250,
                             scenario_count: int = 5000,
                             curve_date: str | None = None) -> dict:
        """Historical, parametric and Monte Carlo VaR and ES, side by side."""
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        history = self._history(date, trading_days)
        if isinstance(history, dict):
            return history
        _, matrix = history
        out = self.p.call_tool("compare_risk_methods_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "history": matrix, "confidence_level": confidence_level,
            "horizon_days": horizon_days, "scenario_count": int(scenario_count)})
        if (bad := _fail(out, "compare_risk_methods")):
            return bad
        return {
            "valuation_date": date, "confidence_level": out.get("confidence_level"),
            "horizon_days": out.get("horizon_days"),
            "methods": out.get("methods"),
            "spread_var": out.get("spread_var"),
            "widest_method": out.get("widest_method"),
            "narrowest_method": out.get("narrowest_method"),
            "comparison_note": out.get("comparison_note"),
            "data_classification": DEMO_CLASSIFICATION,
        }

    def backtest_var(self, portfolio_id: str, confidence_level: float = 0.99,
                     observations: int = 100, trading_days: int = 250,
                     curve_date: str | None = None) -> dict:
        """Check a VaR forecast against outcomes: exceptions and coverage tests.

        The P&L series is **model revaluation**, not the desk's realised P&L:
        each observed daily curve move is applied to today's book and revalued
        by the engine. That is labelled in the result, because a hypothetical
        series presented as actual flatters the model.

        The forecast is held constant across the window - this system has no
        rolling-VaR history - and the result says so.
        """
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        history = self._history(date, trading_days)
        if isinstance(history, dict):
            return history
        _, matrix = history

        risk = self.p.call_tool("compute_historical_risk_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "history_tenors_months": matrix["tenors_months"],
            "history_rates_percent": matrix["rates_percent"],
            "confidence_level": confidence_level, "horizon_days": 1})
        if (bad := _fail(risk, "compute_historical_risk")):
            return bad
        forecast = risk["var"]

        window = max(30, min(int(observations), 100))
        moves = self.p.call_tool("find_worst_historical_stresses_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve,
            "history": matrix, "horizon_days": 1, "top_n": window})
        if (bad := _fail(moves, "find_worst_historical_stresses")):
            return bad
        # Ranked worst-first by the engine. Restore chronological order before
        # backtesting: the independence test reads the *sequence* of exceptions,
        # and a ranked series would put every exception at the front and report
        # catastrophic clustering that is an artefact of the sort.
        ordered = sorted(moves.get("worst", []),
                         key=lambda w: w.get("start_observation_index", 0))
        pnl = [w["pnl"] for w in ordered]
        dates = [w.get("start_date") for w in ordered]
        if len(pnl) < 30:
            return {"error": "not enough observations to backtest",
                    "detail": f"{len(pnl)} available, 30 required"}

        out = self.p.call_tool("backtest_var_tool", {
            "var_forecasts": [forecast] * len(pnl), "realised_pnl": pnl,
            "confidence_level": confidence_level,
            "pnl_kind": "MODEL_REVALUATION",
            "observation_dates": [d for d in dates if d] or None})
        if (bad := _fail(out, "backtest_var")):
            return bad
        return {
            "valuation_date": date,
            "observations": out.get("observations"),
            "confidence_level": out.get("confidence_level"),
            "pnl_kind": out.get("pnl_kind"),
            "var_forecast_used": forecast,
            "exceptions": out.get("exceptions"),
            "exception_rate": out.get("exception_rate"),
            "expected_exceptions": out.get("expected_exceptions"),
            "exception_dates": out.get("exception_dates"),
            "longest_exception_run": out.get("longest_exception_run"),
            "kupiec_result": out.get("kupiec_result"),
            "independence_result": out.get("independence_result"),
            "conditional_coverage_result": out.get("conditional_coverage_result"),
            "basel_traffic_light": out.get("basel_traffic_light"),
            "exception_rule": out.get("exception_rule"),
            "note": "P&L is model revaluation, not the desk's realised P&L, and "
                    "the VaR forecast is held constant across the window. Both "
                    "are stated because a backtest that hides either flatters "
                    "the model.",
            "data_classification": DEMO_CLASSIFICATION,
        }

    # -- P&L, limits, comparison, regulatory ---------------------------------

    def compute_pnl_attribution(self, portfolio_id: str,
                                start_date: str | None = None,
                                end_date: str | None = None,
                                lookback_days: int = 30) -> dict:
        """Split a period's P&L into carry, roll-down, rate move and residual."""
        book_raw = self.p.call_tool("get_portfolio", {"portfolio_id": portfolio_id})
        if (bad := _fail(book_raw, "get_portfolio")):
            return bad
        book = _portfolio_for_engine(book_raw)

        if not end_date:
            latest = self._latest_curve_date()
            if isinstance(latest, dict):
                return latest
            end_date = latest
        if not start_date:
            start_date = _add_days(end_date, -abs(int(lookback_days)))

        start_curve = self._curve_on(start_date)
        if "error" in start_curve:
            return start_curve
        end_curve = self._curve_on(end_date)
        if "error" in end_curve:
            return end_curve

        out = self.p.call_tool("compute_pnl_attribution_tool", {
            "portfolio": book,
            "start_date": start_curve["observation_date"],
            "start_curve": start_curve,
            "end_date": end_curve["observation_date"],
            "end_curve": end_curve})
        if (bad := _fail(out, "compute_pnl_attribution")):
            return bad
        return {
            "start_date": out.get("start_date"), "end_date": out.get("end_date"),
            "days": out.get("days"),
            "total_pnl": out.get("total_pnl"),
            "carry": out.get("carry"), "roll_down": out.get("roll_down"),
            "rate_move": out.get("rate_move"),
            "position_change": out.get("position_change"),
            "residual": out.get("residual"),
            "rate_explained_by_tenor": out.get("rate_explained_by_tenor"),
            "rate_unexplained": out.get("rate_unexplained"),
            "rate_unexplained_percent": out.get("rate_unexplained_percent"),
            "tenor_effects": out.get("tenor_effects"),
            "bucket_effects": out.get("bucket_effects"),
            "residual_note": out.get("residual_note"),
            "data_classification": DEMO_CLASSIFICATION,
        }

    def evaluate_risk_limits(self, portfolio_id: str,
                             dv01_limit: float | None = None,
                             var_limit: float | None = None,
                             stress_loss_limit: float | None = None,
                             amber_utilisation_percent: float = 80.0,
                             confidence_level: float = 0.99,
                             trading_days: int = 250,
                             curve_date: str | None = None) -> dict:
        """Compare measured risk against caller-supplied limits.

        No limit is invented. With none supplied the capability reports what it
        would need, and the orchestrator asks - which is the existing
        clarification path, not a new one.
        """
        supplied = {k: v for k, v in (
            ("dv01", dv01_limit), ("var_99_1d", var_limit),
            ("stress_loss_200bp", stress_loss_limit)) if v is not None}
        if not supplied:
            return {"error": "no risk limits were supplied",
                    "needs": ["dv01_limit", "var_limit", "stress_loss_limit"],
                    "detail": "This system holds no risk policy and will not "
                              "assume one. Supply at least one limit amount."}

        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        base = {"portfolio": book, "valuation_date": date, "par_curve": curve}

        measured: dict[str, float] = {}
        if "dv01" in supplied:
            dv01 = self.p.call_tool("compute_dv01_tool", base)
            if (bad := _fail(dv01, "compute_dv01")):
                return bad
            measured["dv01"] = dv01["dv01"]
        if "var_99_1d" in supplied:
            history = self._history(date, trading_days)
            if isinstance(history, dict):
                return history
            _, matrix = history
            risk = self.p.call_tool("compute_historical_risk_tool", {
                **base, "history_tenors_months": matrix["tenors_months"],
                "history_rates_percent": matrix["rates_percent"],
                "confidence_level": confidence_level, "horizon_days": 1})
            if (bad := _fail(risk, "compute_historical_risk")):
                return bad
            measured["var_99_1d"] = risk["var"]
        if "stress_loss_200bp" in supplied:
            stress = self.p.call_tool("run_rate_stress_tool",
                                      {**base, "parallel_shock_bp": 200.0})
            if (bad := _fail(stress, "run_rate_stress")):
                return bad
            measured["stress_loss_200bp"] = abs(min(0.0, stress["pnl"]))

        limits = [{"metric": metric, "limit_amount": float(amount),
                   "current_value": measured[metric],
                   "amber_utilisation_percent": float(amber_utilisation_percent)}
                  for metric, amount in supplied.items() if metric in measured]
        out = self.p.call_tool("evaluate_risk_limits_tool", {"limits": limits})
        if (bad := _fail(out, "evaluate_risk_limits")):
            return bad
        return {
            "valuation_date": date,
            "evaluations": out.get("evaluations"),
            "breach_count": out.get("breach_count"),
            "amber_count": out.get("amber_count"),
            "all_within_limits": out.get("all_within_limits"),
            "threshold_policy": out.get("threshold_policy"),
            "data_classification": DEMO_CLASSIFICATION,
        }

    def compare_portfolio_risk(self, portfolio_id: str,
                               other_portfolio_id: str | None = None,
                               curve_date: str | None = None) -> dict:
        """Two stored books measured on identical inputs, and differenced."""
        if not other_portfolio_id:
            listing = self.list_portfolios()
            books = [b.get("portfolio_id") for b in (listing.get("portfolios") or [])]
            others = [b for b in books if b != portfolio_id]
            if not others:
                return {"error": "only one portfolio exists, so there is nothing "
                                 "to compare against",
                        "available_portfolios": books}
            other_portfolio_id = others[0]

        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book_a, curve, date = setup
        other = self.p.call_tool("get_portfolio",
                                 {"portfolio_id": other_portfolio_id})
        if (bad := _fail(other, "get_portfolio")):
            return bad
        out = self.p.call_tool("compare_portfolio_risk_tool", {
            "portfolio_a": book_a, "portfolio_b": _portfolio_for_engine(other),
            "valuation_date": date, "par_curve": curve,
            "label_a": portfolio_id, "label_b": other_portfolio_id})
        if (bad := _fail(out, "compare_portfolio_risk")):
            return bad
        return {
            "valuation_date": date, "portfolio_a": portfolio_id,
            "portfolio_b": other_portfolio_id,
            "measures": out.get("measures"),
            "key_rate_dv01": out.get("key_rate_dv01"),
            "risk_reduction_percent": out.get("risk_reduction_percent"),
            "measures_omitted": out.get("measures_omitted"),
            "data_classification": DEMO_CLASSIFICATION,
        }

    def analyze_hypothetical_trade(self, portfolio_id: str,
                                   tenor_months: float | None = None,
                                   notional: float | None = None,
                                   curve_date: str | None = None) -> dict:
        """Incremental risk of adding a Treasury position. Nothing is mutated.

        The hypothetical instrument is a newly issued bond at a **published**
        curve node, carrying that node's own quoted par rate as its coupon. The
        rate is read from the fetched curve, not interpolated - a tenor with no
        published node is refused with the available ones named.
        """
        missing = {}
        if tenor_months is None:
            missing["tenor_months"] = "the maturity to add, in months"
        if notional is None:
            missing["notional"] = "the face amount to add"
        if missing:
            return _needs("analyze_hypothetical_trade", missing,
                          "Incremental risk depends entirely on what is being "
                          "added; neither the tenor nor the size can be "
                          "assumed.")
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup

        nodes = {float(t): float(r) for t, r
                 in zip(curve["tenors_months"], curve["rates_percent"])}
        tenor = float(tenor_months)
        if tenor not in nodes:
            return {"error": f"{tenor / 12:g}y is not a published curve node",
                    "available_tenor_months": sorted(nodes),
                    "detail": "The hypothetical bond takes its coupon from a "
                              "published par rate; no rate is interpolated."}

        maturity = _add_months(date, int(round(tenor)))
        hypothetical = {
            "portfolio_id": f"HYPOTHETICAL_{tenor / 12:g}Y",
            "data_classification": "SYNTHETIC_DEMO",
            "positions": [{
                "instrument": {
                    "instrument_id": f"HYPO_{tenor / 12:g}Y",
                    "face_value": 1000.0, "coupon_rate_pct": nodes[tenor],
                    "issue_date": date, "maturity_date": maturity},
                "face_notional": float(notional)}]}

        out = self.p.call_tool("analyze_hypothetical_trade_tool", {
            "portfolio": book, "hypothetical_positions": hypothetical,
            "valuation_date": date, "par_curve": curve})
        if (bad := _fail(out, "analyze_hypothetical_trade")):
            return bad
        return {
            "valuation_date": date,
            "hypothetical_trade": {"tenor_months": tenor, "notional": notional,
                                   "coupon_rate_pct": nodes[tenor],
                                   "maturity_date": maturity},
            "measures": out.get("measures"),
            "key_rate_dv01": out.get("key_rate_dv01"),
            "note": out.get("note"),
            "data_classification": DEMO_CLASSIFICATION,
        }

    def compute_frtb_girr(self, portfolio_id: str,
                          curve_date: str | None = None) -> dict:
        """FRTB standardised-approach GIRR delta and curvature, Treasury scope."""
        setup = self._book_and_curve(portfolio_id, curve_date)
        if isinstance(setup, dict):
            return setup
        book, curve, date = setup
        out = self.p.call_tool("compute_frtb_girr_tool", {
            "portfolio": book, "valuation_date": date, "par_curve": curve})
        if (bad := _fail(out, "compute_frtb_girr")):
            return bad
        return {
            "valuation_date": date,
            "framework": out.get("regulatory_framework"),
            "source": out.get("source"),
            "delta_capital": out.get("delta_capital"),
            "binding_scenario": out.get("binding_scenario"),
            "curvature_capital": (out.get("curvature") or {}).get("bucket_capital"),
            "curvature_interpretation": (out.get("curvature") or {}).get("interpretation"),
            "total_capital": out.get("total_capital"),
            "total_capital_percent_of_value":
                out.get("total_capital_percent_of_value"),
            "vega_capital": out.get("vega_capital"),
            "unsupported_risk_classes": out.get("unsupported_risk_classes"),
            "scope_note": out.get("scope_note"),
            "note": "General Interest Rate Risk only, for the supported "
                    "Treasury/rates scope. This is NOT a complete bank-wide "
                    "FRTB market-risk capital requirement.",
            "data_classification": DEMO_CLASSIFICATION,
        }

    # -- helpers --------------------------------------------------------------

    def _latest_curve_date(self) -> str | dict:
        curve = self.p.call_tool("get_curve", {"curve_family": "nominal"})
        if "error" in curve:
            return curve
        return curve["observation_date"]
