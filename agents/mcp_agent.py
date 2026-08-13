"""Agent 3 — the MCP agent. Owns the data connection, and argues its side.

Runs on a **high-capability model**, because it does more than fetch. Only this
agent knows what the source actually holds, so it is the half of the discussion
that keeps a plan honest: the domain expert knows what the *method* requires,
this agent knows what the *data* can supply, and neither alone is enough.

Three jobs:

**Advertise.** `catalogue()` reports the tools, fields and tenors that are really
connected. Read live rather than declared, because under a mock backend the risk
tools genuinely are not there, and a domain expert planning against a capability
that does not exist produces a requirement nobody can serve.

**Assess.** Given a proposed requirement, it says what it can and cannot serve
and offers a counter-proposal. This is the model call — judging whether
"settlement_date" is servable from a par yield curve needs reading, not a set
lookup.

**Execute.** Fetch exactly the agreed requirement, run a calculation if one was
agreed, and report what actually arrived. Requested and delivered are separate
numbers on the result, because a fetch that quietly came up short is the one
failure that reaches an answer looking like success.

It never decides *what the task needs*. That belongs to the domain expert, and
splitting it means a wrong number has exactly one author.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from agents.contracts import ServeResponse, ToolCatalogue, ToolSpec
from agents.observability import structured_call, traced

LOGGER = logging.getLogger("agents.mcp_agent")

MODEL = "claude-opus-5"

TENOR_MONTHS: dict[str, float] = {
    "m1": 1, "m1_5": 1.5, "m2": 2, "m3": 3, "m4": 4, "m6": 6,
    "y1": 12, "y2": 24, "y3": 36, "y5": 60, "y7": 84,
    "y10": 120, "y20": 240, "y30": 360,
}
DEFAULT_TENORS = ("y2", "y10")
MAX_DISPLAY_ROWS = 500

# Used only when the corpus states no window. Never presented as methodology:
# the result is flagged `window_unstated` so the reply says the corpus is silent.
SAMPLE_ROWS = 60

ASSESS_SYSTEM = """\
You are the data layer of a U.S. Treasury market-risk gateway. A domain expert \
has proposed what a task requires. Say what you can actually serve.

You hold daily nominal and real par yield curves and a clearly-labelled \
synthetic demo portfolio. You do NOT hold instrument-level records: no CUSIPs, \
no issuer names, no settlement dates, no trade or position data beyond the demo \
book.

For the proposed requirement, decide:
- `feasible`: can you serve the core of it?
- `unsupported_fields`: requested fields you cannot provide. Be precise - a \
field being absent from your catalogue is enough.
- `unsupported_calculation`: a named calculation you do not offer, else null.
- `max_rows_available`: the most observations you can supply for this selection, \
or null if you cannot tell without fetching.
- `counter_proposal`: one or two sentences to the domain expert. Say what you \
CAN do instead. This is a conversation between colleagues, not an error message.

Never offer to substitute a different field for a missing one. Saying "I do not \
have that" is correct; quietly serving something adjacent is not.
"""

ASSESS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "feasible": {"type": "boolean"},
        "unsupported_fields": {"type": "array", "items": {"type": "string"}},
        "unsupported_calculation": {"type": ["string", "null"]},
        "max_rows_available": {"type": ["integer", "null"]},
        "counter_proposal": {"type": "string"},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["feasible", "unsupported_fields", "unsupported_calculation",
                 "max_rows_available", "counter_proposal", "notes"],
    "additionalProperties": False,
}


class McpAgent:
    """Advertises what the data layer can do, negotiates, and executes."""

    def __init__(self, data_provider, model: str = MODEL) -> None:
        self.data = data_provider
        self.model = model

    # -- advertise -----------------------------------------------------------

    @traced("mcp_agent.catalogue", run_type="tool")
    def catalogue(self) -> ToolCatalogue:
        """What is really connected, read from the live provider."""
        fields: set[str] = {"observation_date", "rate_percent", "quote_basis", "tenor"}
        tenors: list[str] = []
        notes: list[str] = []
        try:
            catalogue_rows = self.data.list_series() or []
            for row in catalogue_rows:
                if isinstance(row, dict):
                    fields.update(row.keys())
                    if row.get("tenor") in TENOR_MONTHS:
                        tenors.append(row["tenor"])
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Series catalogue unavailable: {exc}")

        tools = [
            ToolSpec("get_yield_curve", "One day's full par curve, by tenor.", "data"),
            ToolSpec("get_rate_history", "Daily history for one tenor.", "data"),
            ToolSpec("get_curve_slope", "Slope between two tenors, in basis points.", "data"),
            ToolSpec("list_series", "Catalogue of available series and tenors.", "data"),
        ]
        # Risk tools exist only when the provider can reach the risk engine.
        # Advertising them otherwise would have the expert plan a calculation
        # that cannot run.
        can_calculate = hasattr(self.data, "call_tool")
        if can_calculate:
            # Names match `RiskWorkflows` methods exactly, because that is what
            # `_calculate` dispatches to. Advertising a name the executor cannot
            # resolve makes the domain expert plan a calculation that then fails
            # at the last step, which is the worst place to discover it.
            tools += [
                ToolSpec("price_portfolio",
                         "Present value of the SYNTHETIC_DEMO book on a par curve.", "risk"),
                ToolSpec("compute_dv01",
                         "DV01 by full revaluation, with key-rate breakdown.", "risk"),
                ToolSpec("compute_var",
                         "Historical-simulation VaR and Expected Shortfall.", "risk"),
                ToolSpec("run_stress",
                         "Revalue the book under a tenor shock vector.", "risk"),
            ]
        else:
            notes.append("Risk engine not connected under this backend; "
                         "calculations are unavailable.")

        return ToolCatalogue(
            tools=tools, fields=sorted(fields),
            tenors=sorted(set(tenors) or set(TENOR_MONTHS), key=lambda t: TENOR_MONTHS[t]),
            can_calculate=can_calculate, notes=notes,
        )

    # -- negotiate -----------------------------------------------------------

    @traced("mcp_agent.assess", run_type="llm")
    def assess(self, requirement, catalogue: ToolCatalogue) -> ServeResponse:
        """Judge a proposed requirement against what this source truly holds."""
        payload = structured_call(
            model=self.model, system=ASSESS_SYSTEM,
            prompt=(f"Proposed requirement:\n{requirement.as_dict()}\n\n"
                    f"Your catalogue:\n{catalogue.as_dict()}"),
            schema=ASSESS_SCHEMA, max_tokens=3000,
        )
        if payload is None:
            # Cannot judge: accept the requirement rather than block the request,
            # and say so, so the reply does not imply a negotiation happened.
            return ServeResponse(
                feasible=True,
                counter_proposal="The data layer could not assess this requirement; "
                                 "it will be executed as proposed.",
                notes=["assessment model unavailable"])
        return ServeResponse(
            feasible=bool(payload.get("feasible", True)),
            unsupported_fields=payload.get("unsupported_fields") or [],
            unsupported_calculation=payload.get("unsupported_calculation"),
            max_rows_available=payload.get("max_rows_available"),
            counter_proposal=payload.get("counter_proposal", ""),
            notes=payload.get("notes") or [],
        )

    # -- execute -------------------------------------------------------------

    @traced("mcp_agent.execute", run_type="tool")
    def execute(self, requirement) -> dict[str, Any]:
        """Fetch the agreed requirement; calculate if one was agreed."""
        tenors = [t for t in requirement.tenors if t in TENOR_MONTHS] or list(DEFAULT_TENORS)
        window_unstated = requirement.rows is None
        rows_wanted = requirement.rows or SAMPLE_ROWS
        notes: list[str] = []
        if window_unstated:
            notes.append(
                f"The knowledge base states no observation window for this task, so "
                f"the most recent {SAMPLE_ROWS} observations were returned as a "
                f"sample. This is not a methodology figure.")

        table = (self._snapshot(requirement) if rows_wanted <= 1
                 else self._history(tenors, rows_wanted))
        delivered = table.get("row_count", 0)
        if not window_unstated and delivered < rows_wanted:
            notes.append(f"Asked for {rows_wanted:,} observations; the source holds "
                         f"{delivered:,} for this selection. Reported, not padded.")

        calculation = None
        if requirement.calculation:
            calculation = self._calculate(requirement.calculation)

        return {"table": table, "rows_delivered": delivered,
                "rows_agreed": requirement.rows, "window_unstated": window_unstated,
                "calculation": calculation, "notes": notes}

    @traced("mcp_agent.calculate", run_type="tool")
    def _calculate(self, tool: str) -> dict[str, Any]:
        """Run a risk calculation through the workflow layer, not the raw tool.

        `RiskWorkflows` is what knows how to marshal a portfolio into the risk
        engine's input shape and how to difference two curves into a replay
        shock. Calling the MCP tool directly means reproducing that marshalling
        here, and a second implementation of it would eventually disagree with
        the first.
        """
        workflows = self._workflows()
        if workflows is None:
            return {"tool": tool, "error": "risk engine not connected under this backend"}
        method = getattr(workflows, tool, None)
        if method is None:
            return {"tool": tool, "error": f"no workflow named {tool!r}"}
        try:
            # Every risk workflow is portfolio-scoped, and the demo book is the
            # only one; resolve it rather than making the domain expert guess an id.
            kwargs: dict[str, Any] = {}
            if "portfolio_id" in method.__code__.co_varnames:
                portfolio_id = self._first_portfolio(workflows)
                if portfolio_id is None:
                    return {"tool": tool, "error": "no portfolio available to price"}
                kwargs["portfolio_id"] = portfolio_id
            return {"tool": tool, "result": method(**kwargs)}
        except Exception as exc:  # noqa: BLE001 - surfaced, never fatal
            return {"tool": tool, "error": f"{type(exc).__name__}: {exc}"}

    def _workflows(self):
        if not hasattr(self.data, "call_tool"):
            return None
        if not hasattr(self, "_risk_workflows"):
            try:
                from backend.agent.risk_workflows import RiskWorkflows  # noqa: PLC0415

                self._risk_workflows = RiskWorkflows(self.data)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("risk workflows unavailable: %s", exc)
                self._risk_workflows = None
        return self._risk_workflows

    @staticmethod
    def _first_portfolio(workflows) -> str | None:
        try:
            listing = workflows.list_portfolios() or {}
            books = listing.get("portfolios") or []
            return books[0].get("portfolio_id") if books else None
        except Exception:  # noqa: BLE001
            return None

    # -- shapes --------------------------------------------------------------

    def _snapshot(self, requirement) -> dict[str, Any]:
        curve = self.data.get_yield_curve(None, "nominal")
        if not isinstance(curve, dict) or "error" in curve:
            return self._empty("Curve unavailable", curve)
        rows = [{"tenor": tenor, "rate_percent": rate,
                 "quote_basis": curve.get("quote_basis"), "rate_kind": "nominal",
                 "observation_date": curve.get("curve_date")}
                for tenor, rate in (curve.get("points") or {}).items()]
        allowed = {"tenor", "rate_percent", "quote_basis", "rate_kind", "observation_date"}
        columns = [c for c in requirement.fields if c in allowed] or \
                  ["tenor", "rate_percent", "quote_basis"]
        return self._table(rows, columns,
                           f"Nominal par curve — {curve.get('curve_date')}",
                           self._provenance(curve))

    def _history(self, tenors: list[str], rows_wanted: int) -> dict[str, Any]:
        by_date: dict[str, dict[str, Any]] = {}
        for tenor in tenors:
            try:
                series = self.data.get_rate_history(tenor) or []
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("history failed for %s: %s", tenor, exc)
                continue
            for point in series:
                if isinstance(point, dict) and "error" not in point:
                    day = point.get("observation_date")
                    if day:
                        by_date.setdefault(day, {"observation_date": day})[tenor] = \
                            point.get("rate_percent")

        curve = self.data.get_yield_curve(None, "nominal")
        basis = curve.get("quote_basis") if isinstance(curve, dict) else None
        # A window is the N most recent observations, not the first N returned.
        ordered = [by_date[day] for day in sorted(by_date, reverse=True)][:rows_wanted]
        for row in ordered:
            row["quote_basis"] = basis
        return self._table(ordered, ["observation_date", *tenors, "quote_basis"],
                           f"Par yields — {', '.join(tenors)} "
                           f"(most recent {len(ordered)} rows)",
                           self._provenance(curve))

    @staticmethod
    def _provenance(curve: Any) -> dict[str, Any]:
        if not isinstance(curve, dict):
            return {}
        return {"dataset_snapshot_id": curve.get("dataset_snapshot_id"),
                "source_file": curve.get("source_file"),
                "curve_date": curve.get("curve_date"),
                "quote_basis": curve.get("quote_basis"),
                "classification": "REAL_MARKET_DATA"}

    @staticmethod
    def _table(rows: list[dict[str, Any]], columns: list[str], title: str,
               provenance: dict[str, Any]) -> dict[str, Any]:
        shown = rows[:MAX_DISPLAY_ROWS]
        return {"title": title, "columns": columns,
                "rows": [[_cell(r.get(c)) for c in columns] for r in shown],
                "row_count": len(rows), "displayed": len(shown),
                "truncated": len(rows) > len(shown), "provenance": provenance}

    @staticmethod
    def _empty(title: str, detail: Any) -> dict[str, Any]:
        return {"title": title, "columns": [], "rows": [], "row_count": 0,
                "displayed": 0, "truncated": False, "provenance": {},
                "error": detail if isinstance(detail, dict) else str(detail)}


def _cell(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value
