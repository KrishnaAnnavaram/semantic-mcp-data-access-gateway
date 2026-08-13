"""Risk-data layer — Treasury data contract + mock stub (Layer 2 seam).

The quant agent decides *what* data it needs and calls this provider to get it.
The contract is shaped to the data that actually exists in Layer 3: the U.S.
Treasury interest-rate database (PostgreSQL `analytics.*` views). Each method
maps 1:1 onto a view, so the real `PostgresDataProvider` is a drop-in later:

    get_yield_curve   -> analytics.v_par_yield_curve / v_real_yield_curve
    get_rate_history  -> analytics.v_observation
    get_latest_rates  -> analytics.v_latest_rates
    list_series       -> analytics.v_series
    get_curve_slope   -> derived from v_par_yield_curve

Today the concrete implementation is MockDataProvider (Treasury-shaped sample
data). The agent only ever talks to the DataProvider interface, so swapping in
the DB-backed provider does not touch the agent.
"""

from __future__ import annotations

import datetime as _dt
import math
from typing import Protocol

# Nominal par-curve tenors, in canonical order (matches v_par_yield_curve columns).
NOMINAL_TENORS = ["m1", "m1_5", "m2", "m3", "m4", "m6",
                  "y1", "y2", "y3", "y5", "y7", "y10", "y20", "y30"]
REAL_TENORS = ["y5", "y7", "y10", "y20", "y30"]

_LATEST_DATE = _dt.date(2026, 8, 11)


def make_data_provider() -> "DataProvider":
    """Choose the data provider from the environment.

    DATA_BACKEND = mcp | postgres | mock (default)

      mcp       through market-risk-data-mcp as `mcp_reader`. The privilege
                boundary holds, every rate carries its quoting basis, and the
                risk engine's tools come with it. This is the full stack.
      postgres  direct psycopg2 as the owner role. Fewer moving parts, but the
                agent process holds a credential that can write to the source
                of record. DATABASE_URL selects the target.
      mock      synthetic Treasury-shaped data; no database needed.
    """
    import os

    backend = os.environ.get("DATA_BACKEND", "mock").strip().lower()
    if backend == "mcp":
        from backend.providers.mcp import McpDataProvider
        return McpDataProvider()
    if backend == "postgres":
        from backend.providers.postgres import PostgresDataProvider
        return PostgresDataProvider()
    return MockDataProvider()


class DataProvider(Protocol):
    def list_series(self) -> list[dict]: ...
    def get_latest_rates(self) -> list[dict]: ...
    def get_yield_curve(self, curve_date: str | None = None, kind: str = "nominal") -> dict: ...
    def get_rate_history(self, tenor: str, start: str | None = None, end: str | None = None) -> list[dict]: ...
    def get_curve_slope(self, short: str = "y2", long: str = "y10", curve_date: str | None = None) -> dict: ...


def _business_days_back(end: _dt.date, n: int) -> list[_dt.date]:
    """n business days up to and including `end`, oldest first (weekends only)."""
    days: list[_dt.date] = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= _dt.timedelta(days=1)
    return list(reversed(days))


class MockDataProvider:
    """Treasury-shaped sample data. Replace with PostgresDataProvider later.

    The base curve is the real published nominal par curve for 2026-08-11
    (source: analytics.v_par_yield_curve), extended to the full tenor set with
    plausible interior points so demos exercise every maturity.
    """

    _NOMINAL_BASE = {
        "m1": 3.79, "m1_5": 3.82, "m2": 3.83, "m3": 3.89, "m4": 3.94, "m6": 3.99,
        "y1": 4.03, "y2": 4.22, "y3": 4.30, "y5": 4.45, "y7": 4.58, "y10": 4.70,
        "y20": 5.05, "y30": 5.24,
    }
    _REAL_BASE = {"y5": 1.65, "y7": 1.78, "y10": 1.92, "y20": 2.20, "y30": 2.35}

    _TENOR_YEARS = {
        "m1": 1 / 12, "m1_5": 1.5 / 12, "m2": 2 / 12, "m3": 0.25, "m4": 4 / 12,
        "m6": 0.5, "y1": 1, "y2": 2, "y3": 3, "y5": 5, "y7": 7, "y10": 10,
        "y20": 20, "y30": 30,
    }

    # ---- helpers -------------------------------------------------------------
    def _base(self, kind: str) -> dict:
        return self._REAL_BASE if kind == "real" else self._NOMINAL_BASE

    def _rate_on(self, tenor: str, base: float, day_offset: int) -> float:
        """Deterministic small daily wiggle so history/curves are reproducible.
        Anchored so day_offset 0 (the latest date) equals the published base."""
        phase = len(tenor)
        wiggle = (math.sin(day_offset * 0.11 + phase) - math.sin(phase)) * 0.05
        return round(base + wiggle, 4)

    # ---- contract ------------------------------------------------------------
    def list_series(self) -> list[dict]:
        """Catalogue of series (mirrors analytics.v_series)."""
        out = []
        for t in NOMINAL_TENORS:
            out.append({
                "tenor": t, "tenor_years": round(self._TENOR_YEARS[t], 4),
                "rate_kind": "nominal", "quote_basis": "par_coupon_semiannual",
                "data_key": "daily_treasury_yield_curve",
            })
        for t in REAL_TENORS:
            out.append({
                "tenor": t, "tenor_years": round(self._TENOR_YEARS[t], 4),
                "rate_kind": "real", "quote_basis": "average_real_yield",
                "data_key": "daily_treasury_real_yield_curve",
            })
        return out

    def get_latest_rates(self) -> list[dict]:
        """Most recent value per nominal tenor (mirrors analytics.v_latest_rates)."""
        return [
            {"tenor": t, "observation_date": _LATEST_DATE.isoformat(), "rate_percent": r}
            for t, r in self._NOMINAL_BASE.items()
        ]

    def get_yield_curve(self, curve_date: str | None = None, kind: str = "nominal") -> dict:
        """One day's curve, wide (mirrors analytics.v_par_yield_curve)."""
        date = _dt.date.fromisoformat(curve_date) if curve_date else _LATEST_DATE
        offset = (date - _LATEST_DATE).days
        base = self._base(kind)
        points = {t: self._rate_on(t, r, offset) for t, r in base.items()}
        return {"curve_date": date.isoformat(), "kind": kind, "points": points}

    def get_rate_history(self, tenor: str, start: str | None = None,
                         end: str | None = None) -> list[dict]:
        """Daily history for one tenor (mirrors analytics.v_observation)."""
        base = self._NOMINAL_BASE.get(tenor) or self._REAL_BASE.get(tenor)
        if base is None:
            return []
        end_date = _dt.date.fromisoformat(end) if end else _LATEST_DATE
        days = _business_days_back(end_date, 252)
        if start:
            start_date = _dt.date.fromisoformat(start)
            days = [d for d in days if d >= start_date]
        return [
            {"observation_date": d.isoformat(),
             "rate_percent": self._rate_on(tenor, base, (d - _LATEST_DATE).days)}
            for d in days
        ]

    def get_curve_slope(self, short: str = "y2", long: str = "y10",
                        curve_date: str | None = None) -> dict:
        """Slope between two tenors, e.g. 2s10s (derived from the curve)."""
        curve = self.get_yield_curve(curve_date, kind="nominal")["points"]
        s, l = curve.get(short), curve.get(long)
        if s is None or l is None:
            return {"error": f"unknown tenor(s): {short}, {long}"}
        return {
            "curve_date": curve_date or _LATEST_DATE.isoformat(),
            "short": short, "long": long,
            "short_rate": s, "long_rate": l,
            "slope_bps": round((l - s) * 100, 1),
        }
