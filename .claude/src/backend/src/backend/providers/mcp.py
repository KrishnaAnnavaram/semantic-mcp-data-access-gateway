"""DataProvider backed by the MCP layer — the agent's road to PostgreSQL.

This is the third implementation of the `DataProvider` seam, and the one the
full stack uses:

    MockDataProvider      synthetic, no database          DATA_BACKEND=mock
    PostgresDataProvider  direct psycopg2, owner role     DATA_BACKEND=postgres
    McpDataProvider       through market-risk-data-mcp    DATA_BACKEND=mcp   <-- here

Why route through MCP rather than connect directly, when both read the same
`analytics.*` views:

  * **Privilege.** The MCP data server connects as `mcp_reader`, which cannot
    write anything and cannot see `treasury.*` or `staging.*` at all. A direct
    provider holds the owner credential, so an agent bug is a write away from
    the source of record. The boundary is a PostgreSQL grant, not a convention.
  * **Semantics.** Every rate arrives carrying `quote_basis`, `rate_kind`,
    `unit` and `data_classification`. A bill discount rate cannot be quietly
    mistaken for a par yield downstream.
  * **Provenance.** Every response carries a `dataset_snapshot_id`, and
    `explain_number` can name the Treasury file and its SHA-256.
  * **The risk engine comes with it.** Pricing, DV01, VaR and stress are one
    `call_tool` away, on a server that has no database credential at all.

## The async/sync problem

`McpHost` is asyncio and owns two child processes over stdio; `DataProvider` is
a synchronous contract called from FastAPI request handlers. Rather than spawn
servers per call — which would pay process startup on every question — the
bridge runs one event loop on a daemon thread for the process lifetime and
marshals calls onto it. The child processes stay warm.
"""

from __future__ import annotations

import asyncio
import atexit
import datetime as _dt
import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("mcp_data_provider")

# The agent's tenor vocabulary expressed in months. This is a translation between
# two naming conventions, not a list of Treasury fields -- series codes are still
# resolved from the live catalogue, so a maturity Treasury adds needs no edit here.
MONTHS_BY_TENOR: dict[str, float] = {
    "m1": 1, "m1_5": 1.5, "m2": 2, "m3": 3, "m4": 4, "m6": 6,
    "y1": 12, "y2": 24, "y3": 36, "y5": 60, "y7": 84,
    "y10": 120, "y20": 240, "y30": 360,
}
TENOR_BY_MONTHS: dict[float, str] = {v: k for k, v in MONTHS_BY_TENOR.items()}

CALL_TIMEOUT_S = 120.0
STARTUP_TIMEOUT_S = 90.0


class McpUnavailable(RuntimeError):
    """The MCP servers could not be started or have gone away."""


class _McpBridge:
    """One event loop, one McpHost, both alive for the life of the process.

    Deliberately a process-wide singleton: the child processes are the expensive
    resource, and `mcp_reader` is capped at 5 connections, so a bridge per agent
    instance would exhaust the pool under concurrent requests.
    """

    _instance: "_McpBridge | None" = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "_McpBridge":
        with cls._lock:
            if cls._instance is None:
                cls._instance = _McpBridge()
                atexit.register(cls._instance.shutdown)
            return cls._instance

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._host: Any = None
        self._stop: asyncio.Event | None = None
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, name="mcp-bridge", daemon=True)
        self._thread.start()
        if not self._ready.wait(STARTUP_TIMEOUT_S):
            raise McpUnavailable(
                f"MCP servers did not start within {STARTUP_TIMEOUT_S:.0f}s")
        if self._error is not None:
            raise McpUnavailable(f"MCP servers failed to start: {self._error}") from self._error

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except BaseException as exc:  # noqa: BLE001 - reported to the waiting thread
            self._error = exc
            self._ready.set()
        finally:
            try:
                self._loop.close()
            except Exception:  # pragma: no cover - best-effort teardown
                pass

    async def _serve(self) -> None:
        from mcp_servers.host.mcp_clients import McpHost  # noqa: PLC0415 - keeps import cost off module load

        self._stop = asyncio.Event()
        async with McpHost() as host:
            self._host = host
            LOGGER.info("mcp bridge up: %s", ", ".join(host.servers))
            self._ready.set()
            await self._stop.wait()
        self._host = None

    def call_raw(self, tool: str, arguments: dict[str, Any]) -> Any:
        """Call a tool and return the full CallToolResult (so `_meta` survives)."""
        if self._host is None:
            raise McpUnavailable("MCP host is not running")
        future = asyncio.run_coroutine_threadsafe(
            self._host.call(tool, arguments), self._loop)
        return future.result(CALL_TIMEOUT_S)

    def tool_names(self) -> list[str]:
        if self._host is None:
            return []
        return [t.name for t in self._host.all_tools()]

    def shutdown(self) -> None:
        if self._stop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._stop.set)
            self._thread.join(timeout=10)


def _structured(result: Any) -> dict[str, Any]:
    """Unwrap a tool result, converting a domain error into `{"error": ...}`.

    Tool execution errors are returned rather than raised on purpose: the agent
    feeds tool results back to the model, and every MCP error names its own fix
    ("retry with date_policy='previous'", candidate dates, ...). Handing that to
    the model lets it self-correct, which a stack trace would not.
    """
    if getattr(result, "is_error", False):
        text = "".join(getattr(c, "text", "") for c in (result.content or []))
        start = text.find("{")
        if start >= 0:
            try:
                return {"error": json.loads(text[start:])}
            except json.JSONDecodeError:
                pass
        return {"error": {"message": text or "tool reported an error with no detail"}}
    if result.structured_content is not None:
        return result.structured_content
    text = "".join(getattr(c, "text", "") for c in (result.content or []))
    return json.loads(text) if text.strip().startswith("{") else {"text": text}


def _f(value: Any) -> float | None:
    """Decimal strings on the wire -> float for the agent's contract."""
    return None if value is None else float(value)


class McpDataProvider:
    """Implements the DataProvider protocol over the two MCP servers."""

    def __init__(self) -> None:
        self._bridge = _McpBridge.instance()
        self._series_cache: list[dict] | None = None

    # -- plumbing -------------------------------------------------------------

    def call_tool(self, tool: str, arguments: dict[str, Any] | None = None) -> dict:
        """Escape hatch to any MCP tool, including the risk engine's five."""
        return _structured(self._bridge.call_raw(tool, arguments or {}))

    def call_tool_with_meta(self, tool: str,
                            arguments: dict[str, Any] | None = None) -> tuple[dict, dict]:
        """As `call_tool`, but also returns `_meta` — where bulk arrays travel."""
        raw = self._bridge.call_raw(tool, arguments or {})
        return _structured(raw), dict(getattr(raw, "meta", None) or {})

    def tool_names(self) -> list[str]:
        return self._bridge.tool_names()

    def _catalogue(self) -> list[dict]:
        """The full series catalogue, paged through once and cached."""
        if self._series_cache is not None:
            return self._series_cache
        out: list[dict] = []
        cursor = None
        while True:
            args: dict[str, Any] = {"page_size": 200}
            if cursor:
                args["cursor"] = cursor
            page = self.call_tool("list_series", args)
            if "error" in page:
                raise McpUnavailable(f"list_series failed: {page['error']}")
            out.extend(page.get("series", []))
            cursor = page.get("next_cursor")
            if not cursor:
                break
        self._series_cache = out
        return out

    # Treasury publishes a 20-year point in two places -- BC_20YEAR on the par
    # yield curve and BC_20year on the long-term feed -- so a tenor lookup can
    # match twice. Prefer the par curve, the same single source migration V013
    # settled on for curve construction; mixing the two would put two different
    # 20-year rates on one curve depending on which matched first.
    _PREFERRED_DATA_KEY = {
        "nominal": "daily_treasury_yield_curve",
        "real": "daily_treasury_real_yield_curve",
    }

    def _matching_series(self, tenor: str, kind: str) -> list[dict]:
        months = MONTHS_BY_TENOR.get(tenor)
        if months is None:
            return []
        return [s for s in self._catalogue()
                if s["rate_kind"] == kind
                and s.get("tenor_months") is not None
                and abs(float(s["tenor_months"]) - months) < 1e-6]

    def _series_code(self, tenor: str, kind: str = "nominal") -> str | None:
        """Resolve a tenor key to a series code using the live catalogue."""
        matches = self._matching_series(tenor, kind)
        if not matches:
            return None
        preferred = self._PREFERRED_DATA_KEY.get(kind)
        for s in matches:
            if s["data_key"] == preferred:
                return s["series_code"]
        return matches[0]["series_code"]

    def _last_observation(self, series_code: str) -> str | None:
        for s in self._catalogue():
            if s["series_code"] == series_code:
                return s.get("last_observation")
        return None

    # -- DataProvider contract ------------------------------------------------

    def list_series(self) -> list[dict]:
        out = []
        for s in self._catalogue():
            # Some catalogued series carry no tenor at all (composite or
            # non-curve rows); they are not curve points and are skipped.
            if s.get("tenor_months") is None:
                continue
            months = float(s["tenor_months"])
            tenor = TENOR_BY_MONTHS.get(months)
            if tenor is None:
                continue  # a series outside the agent's curve vocabulary (e.g. bills)
            out.append({
                "tenor": tenor,
                "tenor_years": round(months / 12.0, 4),
                "rate_kind": s["rate_kind"],
                "quote_basis": s["quote_basis"],
                "data_key": s["data_key"],
                "series_code": s["series_code"],
                "first_observation": s.get("first_observation"),
                "last_observation": s.get("last_observation"),
                "observation_count": s.get("observation_count"),
            })
        return out

    def get_latest_rates(self) -> list[dict]:
        curve = self.call_tool("get_curve", {"curve_family": "nominal"})
        if "error" in curve:
            return [curve]
        date = curve["observation_date"]
        out = []
        for p in curve["points"]:
            tenor = TENOR_BY_MONTHS.get(float(p["tenor_months"]))
            if tenor:
                out.append({"tenor": tenor, "observation_date": date,
                            "rate_percent": _f(p["rate_percent"]),
                            "quote_basis": p["quote_basis"]})
        return out

    def get_yield_curve(self, curve_date: str | None = None,
                        kind: str = "nominal") -> dict:
        args: dict[str, Any] = {"curve_family": kind}
        if curve_date:
            # 'previous' rather than 'exact': a user naming a weekend or holiday
            # means the nearest published curve, and the response says so via
            # date_was_shifted rather than pretending the date was honoured.
            args["observation_date"] = curve_date
            args["date_policy"] = "previous"
        curve = self.call_tool("get_curve", args)
        if "error" in curve:
            return curve
        points = {}
        for p in curve["points"]:
            tenor = TENOR_BY_MONTHS.get(float(p["tenor_months"]))
            if tenor:
                points[tenor] = _f(p["rate_percent"])
        return {
            "curve_date": curve["observation_date"],
            "kind": kind,
            "points": points,
            "date_was_shifted": curve.get("date_was_shifted", False),
            "requested_date": curve.get("requested_date"),
            "quote_basis": curve["points"][0]["quote_basis"] if curve["points"] else None,
            "dataset_snapshot_id": curve["envelope"]["dataset_snapshot_id"],
            "source_file": curve.get("provenance", {}).get("source_file"),
        }

    def get_rate_history(self, tenor: str, start: str | None = None,
                         end: str | None = None) -> list[dict]:
        # The agent's history tool has no `kind` argument, so this is the nominal
        # par curve. Real-curve history goes through call_tool("get_rate_history")
        # with an explicit TC_* series code.
        code = self._series_code(tenor, "nominal")
        if code is None:
            return [{"error": {"message": f"unknown tenor {tenor!r}",
                               "known": sorted(MONTHS_BY_TENOR)}}]
        # The tool requires an explicit range on both sides -- an open-ended
        # history is how you accidentally pull 9,000 rows. Default the end to the
        # series' last published observation and the start to a year before it.
        end = end or self._last_observation(code)
        if end is None:
            return [{"error": {"message": f"no observations recorded for {code}"}}]
        if not start:
            end_d = _dt.date.fromisoformat(end)
            start = (end_d - _dt.timedelta(days=365)).isoformat()
        args: dict[str, Any] = {"series_codes": [code], "page_size": 500,
                                "start_date": start, "end_date": end}
        rows: list[dict] = []
        cursor = None
        while True:
            if cursor:
                args["cursor"] = cursor
            page = self.call_tool("get_rate_history", dict(args))
            if "error" in page:
                return [page]
            rows.extend(
                {"observation_date": i["observation_date"],
                 "rate_percent": _f(i["rate_percent"])}
                for i in page.get("items", [])
            )
            cursor = page.get("next_cursor")
            # One page is enough for the histories the agent asks for; following
            # every cursor could pull 9,000 rows into model context by accident.
            if not cursor or len(rows) >= 2000:
                break
        return rows

    def get_curve_slope(self, short: str = "y2", long: str = "y10",
                        curve_date: str | None = None) -> dict:
        curve = self.get_yield_curve(curve_date, kind="nominal")
        if "error" in curve:
            return curve
        points = curve["points"]
        s, l = points.get(short), points.get(long)
        if s is None or l is None:
            return {"error": f"unknown tenor(s): {short}, {long}"}
        return {
            "curve_date": curve["curve_date"],
            "short": short, "long": long,
            "short_rate": s, "long_rate": l,
            "slope_bps": round((l - s) * 100, 1),
        }
