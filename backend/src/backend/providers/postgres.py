"""Real risk-data provider — reads the Treasury PostgreSQL database (Layer 3).

Implements the SAME DataProvider contract as MockDataProvider, but every method
runs SQL against the verified `analytics.*` views. Swapping this in for the mock
is the whole point of the DataProvider seam — the agent does not change.

    analytics.v_par_yield_curve   -> get_yield_curve / get_latest_rates / slope
    analytics.v_real_yield_curve  -> get_yield_curve(kind="real")
    analytics.v_observation       -> (tenor history comes from the wide views)
    analytics.v_series            -> list_series
"""

from __future__ import annotations

import os

from backend.providers.base import NOMINAL_TENORS, REAL_TENORS  # reuse the tenor vocabulary

DEFAULT_DSN = "postgresql://gateway:change-me-locally@127.0.0.1:5432/gateway"


class PostgresDataProvider:
    def __init__(self, dsn: str | None = None):
        # Prefer 127.0.0.1 to dodge the Windows localhost->IPv6 hang.
        self.dsn = (dsn or os.environ.get("DATABASE_URL") or DEFAULT_DSN).replace(
            "localhost", "127.0.0.1")

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        import psycopg2
        import psycopg2.extras

        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]

    # ---- contract ------------------------------------------------------------
    def list_series(self) -> list[dict]:
        return self._query(
            "SELECT series_code, display_name, rate_kind, quote_basis, "
            "tenor_years, tenor_label, data_key "
            "FROM analytics.v_series WHERE NOT excluded_from_analytics "
            "ORDER BY rate_kind, tenor_years"
        )

    def get_latest_rates(self) -> list[dict]:
        rows = self._query(
            "SELECT * FROM analytics.v_par_yield_curve "
            "ORDER BY observation_date DESC LIMIT 1"
        )
        if not rows:
            return []
        r = rows[0]
        date = r["observation_date"].isoformat()
        return [
            {"tenor": t, "observation_date": date, "rate_percent": float(r[t])}
            for t in NOMINAL_TENORS if r.get(t) is not None
        ]

    def get_yield_curve(self, curve_date: str | None = None, kind: str = "nominal") -> dict:
        view = "v_real_yield_curve" if kind == "real" else "v_par_yield_curve"
        tenors = REAL_TENORS if kind == "real" else NOMINAL_TENORS
        if curve_date:
            rows = self._query(
                f"SELECT * FROM analytics.{view} WHERE observation_date = %s", (curve_date,))
        else:
            rows = self._query(
                f"SELECT * FROM analytics.{view} ORDER BY observation_date DESC LIMIT 1")
        if not rows:
            return {"curve_date": curve_date, "kind": kind, "points": {}}
        r = rows[0]
        points = {t: float(r[t]) for t in tenors if r.get(t) is not None}
        return {"curve_date": r["observation_date"].isoformat(), "kind": kind, "points": points}

    def get_rate_history(self, tenor: str, start: str | None = None,
                         end: str | None = None,
                         kind: str = "nominal") -> list[dict]:
        # Validate the tenor against the known columns (also prevents SQL
        # injection). `kind` picks the view; several tenors exist on both, and
        # serving the wrong one is indistinguishable in the output.
        if kind == "real" and tenor in REAL_TENORS:
            view = "v_real_yield_curve"
        elif tenor in NOMINAL_TENORS:
            view = "v_par_yield_curve"
        elif tenor in REAL_TENORS:
            view = "v_real_yield_curve"
        else:
            return []
        clauses = [f"{tenor} IS NOT NULL"]
        params: list = []
        if start:
            clauses.append("observation_date >= %s")
            params.append(start)
        if end:
            clauses.append("observation_date <= %s")
            params.append(end)
        where = " AND ".join(clauses)
        rows = self._query(
            f"SELECT observation_date, {tenor} AS rate_percent "
            f"FROM analytics.{view} WHERE {where} ORDER BY observation_date",
            tuple(params),
        )
        return [
            {"observation_date": r["observation_date"].isoformat(),
             "rate_percent": float(r["rate_percent"])}
            for r in rows
        ]

    def get_curve_slope(self, short: str = "y2", long: str = "y10",
                        curve_date: str | None = None) -> dict:
        curve = self.get_yield_curve(curve_date, kind="nominal")
        pts = curve["points"]
        s, l = pts.get(short), pts.get(long)
        if s is None or l is None:
            return {"error": f"unknown tenor(s): {short}, {long}"}
        return {
            "curve_date": curve["curve_date"], "short": short, "long": long,
            "short_rate": s, "long_rate": l, "slope_bps": round((l - s) * 100, 1),
        }
