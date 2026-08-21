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
from llm import CallSite

from agents.observability import structured_call, traced

LOGGER = logging.getLogger("agents.mcp_agent")

CALL_SITE = CallSite.MCP_AGENT

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
has opened with an analytical HYPOTHESIS. Answer it with EVIDENCE about what \
actually exists, so the expert can reassess. Do not simply approve.

The single most valuable thing you can tell it is `unnecessary_fields`: inputs \
its method names in theory that YOUR TOOL DOES NOT READ, because the tool \
computes or abstracts them. The expert cannot learn this from a textbook - only \
you know how the implementation behaves. Naming those lets it drop a \
requirement on evidence instead of guessing.

Answer its `open_questions` explicitly in `answered_questions`. If its stated \
period is outside coverage, say so in `temporal_constraints` rather than \
serving a different period.

You hold daily nominal and real par yield curves and a clearly-labelled \
synthetic demo portfolio. You do NOT hold instrument-level records: no CUSIPs, \
no issuer names, no settlement dates, no trade or position data beyond the demo \
book.

For the proposed requirement, report:
- `feasible`: can you serve the core of it?
- `available_fields`: requested inputs you DO publish. Name them back.
- `unsupported_fields`: requested inputs you cannot provide at all.
- `unnecessary_fields`: requested inputs that exist or are theoretical but this \
calculation does not read. See above - this is the useful one.
- `unsupported_calculation`: a named calculation you cannot execute, else null.
- `available_tools`: the ANALYSES that could serve the objective. Retrieval is not one of them: rows always come back, so a plan that only needs data is feasible with no tool at all.
- `max_rows_available`: the most observations you can supply, or null.
- `temporal_constraints`: what you can and cannot do about the requested period.
- `constraints`: hard limits the expert must plan within.
- `counter_proposal`: what you would do instead, concretely. A colleague's \
suggestion, not an error message.
- `answered_questions`: direct answers to the expert's open questions.
- `open_questions`: anything you need decided before you can commit.

Never offer to substitute a different field for a missing one. Saying "I do not \
have that" is correct; quietly serving something adjacent is not.
"""

ASSESS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "feasible": {"type": "boolean"},
        "available_fields": {"type": "array", "items": {"type": "string"}},
        "unsupported_fields": {"type": "array", "items": {"type": "string"}},
        "unnecessary_fields": {"type": "array", "items": {"type": "string"}},
        "unsupported_calculation": {"type": ["string", "null"]},
        "available_tools": {"type": "array", "items": {"type": "string"}},
        "max_rows_available": {"type": ["integer", "null"]},
        "temporal_constraints": {"type": "array", "items": {"type": "string"}},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "counter_proposal": {"type": "string"},
        "answered_questions": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    # Only what the model alone can supply. Coverage lists are recomputed from
    # the catalogue and merged *over* whatever comes back, so demanding them
    # here bought nothing and cost everything: thirteen required properties is
    # a contract GLM-5.2 failed outright, and a failed assessment turns a
    # negotiation into a rubber stamp at the exact moment it matters.
    #
    # `unnecessary_fields` stays required because it is the one genuinely
    # useful thing this agent can say — the inputs the tool abstracts away,
    # which the expert cannot learn from the corpus at any price.
    "required": ["feasible", "unnecessary_fields", "counter_proposal"],
    "additionalProperties": False,
}


class McpAgent:
    """Advertises what the data layer can do, negotiates, and executes."""

    def __init__(self, data_provider) -> None:
        self.data = data_provider
        self.call_site = CALL_SITE

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

        # Informational: these describe what the data layer can *retrieve* as
        # part of fulfilling a requirement. They are not schedulable
        # calculations, and saying so is the fix for a real defect — the expert
        # used to name `get_curve_slope` as the calculation for a 2s10s question
        # and get an error object back at the last step.
        tools = [
            ToolSpec("get_yield_curve", "One day's full par curve, by tenor.",
                     "data", executable=False),
            ToolSpec("get_rate_history", "Daily history for one tenor.",
                     "data", executable=False),
            ToolSpec("get_curve_slope",
                     "Slope between two tenors, in basis points. Retrieved as "
                     "part of a curve request, not scheduled on its own.",
                     "data", executable=False),
            ToolSpec("list_series", "Catalogue of available series and tenors.",
                     "data", executable=False),
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
                         "Present value of the SYNTHETIC_DEMO book on a par curve.",
                         "risk", executable=True),
                ToolSpec("compute_dv01",
                         "DV01 by full revaluation, with key-rate breakdown.",
                         "risk", executable=True),
                ToolSpec("compute_var",
                         "Historical-simulation VaR and Expected Shortfall.",
                         "risk", executable=True),
                ToolSpec("run_stress",
                         "Revalue the book under a tenor shock vector.",
                         "risk", executable=True),
            ]
        else:
            notes.append("Risk engine not connected under this backend; "
                         "calculations are unavailable.")

        return ToolCatalogue(
            tools=tools, fields=sorted(fields),
            tenors=sorted(set(tenors) or set(TENOR_MONTHS), key=lambda t: TENOR_MONTHS[t]),
            can_calculate=can_calculate, notes=notes,
        )

    @traced("mcp_agent.choices", run_type="tool")
    def choices(self) -> dict[str, Any]:
        """The concrete things a user could actually pick, for a clarifying question.

        Without this the orchestrator writes options from imagination and offers
        "a named scenario on your portfolio" - which is not an answer, so the
        user picks it and gets asked *which* named scenario. Real ids end that
        loop: you cannot click "the 2008 replay on TREASURY_DEMO_001" and still
        be ambiguous.

        Fetched only on the clarify branch, so a greeting still costs nothing.
        """
        out: dict[str, Any] = {"portfolios": [], "scenarios": [],
                               "curve_families": ["nominal", "real"],
                               "tenors": list(DEFAULT_TENORS)}
        workflows = self._workflows()
        if workflows is None:
            return out
        try:
            books = (workflows.list_portfolios() or {}).get("portfolios") or []
            out["portfolios"] = [{"id": b.get("portfolio_id"), "name": b.get("name")}
                                 for b in books][:8]
        except Exception as exc:  # noqa: BLE001 - a thinner question beats none
            LOGGER.warning("could not list portfolios for choices: %s", exc)
        try:
            scenarios = (workflows.list_scenarios() or {}).get("scenarios") or []
            out["scenarios"] = [{"id": s.get("scenario_id"), "name": s.get("name"),
                                 "type": s.get("scenario_type")}
                                for s in scenarios][:8]
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("could not list scenarios for choices: %s", exc)
        return out

    # -- negotiate -----------------------------------------------------------

    @traced("mcp_agent.assess", run_type="llm")
    def assess(self, requirement, catalogue: ToolCatalogue) -> ServeResponse:
        """Answer a proposed plan with capability evidence.

        Two halves, deliberately. The **mechanical** half is computed here from
        the live catalogue and coverage: which requested inputs this source
        actually publishes, which it does not, and whether the requested period
        is inside the data. Those are facts, and a model asked to restate facts
        will eventually restate them wrong.

        The **judgement** half is the model's: which theoretically-required
        inputs this tool does not read, what it would do instead, and what the
        expert still needs to decide. That is reading, not lookup.

        The mechanical findings are merged over the model's afterwards, so a
        confident wrong answer about what exists cannot survive.
        """
        facts = self._capability_facts(requirement, catalogue)
        payload = structured_call(
            call_site=CALL_SITE, system=ASSESS_SYSTEM,
            prompt=(f"The expert's hypothesis:\n{requirement.as_dict()}\n\n"
                    f"Its open questions:\n{requirement.open_questions or 'none'}\n\n"
                    f"Your catalogue:\n{catalogue.as_dict()}\n\n"
                    f"What your own coverage check already established "
                    f"(authoritative - do not contradict it):\n{facts}"),
            schema=ASSESS_SCHEMA, max_tokens=3000,
        )
        if payload is None:
            # Cannot judge. Report the mechanical facts anyway rather than a
            # bare "proceed": the expert can still reassess against real
            # coverage, and the reply must not imply a negotiation happened.
            return ServeResponse(
                feasible=True,
                available_fields=facts["available_fields"],
                unsupported_fields=facts["unsupported_fields"],
                available_tools=facts["executable_tools"],
                temporal_constraints=facts["temporal_constraints"],
                counter_proposal="The data layer could not judge this plan; only "
                                 "its mechanical coverage check is reported.",
                notes=["assessment model unavailable"])

        return ServeResponse(
            feasible=bool(payload.get("feasible", True)),
            # Coverage is a fact, not an opinion: the checked lists win.
            available_fields=facts["available_fields"],
            unsupported_fields=facts["unsupported_fields"],
            unnecessary_fields=_strs(payload.get("unnecessary_fields")),
            unsupported_calculation=payload.get("unsupported_calculation"),
            available_tools=(_strs(payload.get("available_tools"))
                             or facts["executable_tools"]),
            max_rows_available=payload.get("max_rows_available"),
            temporal_constraints=(facts["temporal_constraints"]
                                  + _strs(payload.get("temporal_constraints"))),
            constraints=_strs(payload.get("constraints")),
            counter_proposal=payload.get("counter_proposal", ""),
            answered_questions=_strs(payload.get("answered_questions")),
            open_questions=_strs(payload.get("open_questions")),
            notes=_strs(payload.get("notes")),
        )

    def _capability_facts(self, requirement, catalogue: ToolCatalogue) -> dict[str, Any]:
        """What is true about this plan, checked rather than believed."""
        wanted = list(requirement.candidate_fields or requirement.fields)
        published = set(catalogue.fields)
        facts: dict[str, Any] = {
            "available_fields": [f for f in wanted if f in published],
            "unsupported_fields": [f for f in wanted if f not in published],
            "executable_tools": catalogue.executable_tools,
            "temporal_constraints": [],
            # Stated as a fact rather than left for the model to infer from a
            # flag. Told only that `get_rate_history` was "not executable", the
            # expert concluded a 30-year history could not be served at all and
            # asserted the data server was down — in a turn where retrieval had
            # already succeeded twice.
            "retrieval_is_always_available": True,
            "retrieval_note": (
                "Rows for the requested fields and tenors come back whether or "
                "not a calculation is named. A plan that only needs data is "
                "feasible with no tool at all; never report one as unservable."),
        }
        scope = getattr(requirement, "temporal", None)
        if scope is not None and scope.is_historical:
            facts["temporal_constraints"] = self._temporal_facts(
                scope, requirement.curve_family)
        return facts

    def _temporal_facts(self, scope, family: str) -> list[str]:
        """Is the requested period actually inside the data?

        Answered from the live series catalogue rather than assumed. A question
        about 1985 must be told that coverage begins later, not quietly served
        the most recent curve — which is precisely what happened before a
        requirement could express a date at all.
        """
        try:
            series = [s for s in (self.data.list_series() or [])
                      if isinstance(s, dict)
                      and s.get("rate_kind") == ("real" if family == "real"
                                                 else "nominal")]
        except Exception as exc:  # noqa: BLE001 - a thinner answer beats none
            LOGGER.warning("coverage lookup failed: %s", exc)
            return []
        firsts = [s["first_observation"] for s in series if s.get("first_observation")]
        lasts = [s["last_observation"] for s in series if s.get("last_observation")]
        if not firsts or not lasts:
            return []
        earliest, latest = min(map(str, firsts)), max(map(str, lasts))
        out = [f"{family} coverage runs {earliest} to {latest}"]
        for label, day in (("as_of_date", scope.as_of_date),
                           ("start_date", scope.start_date),
                           ("end_date", scope.end_date)):
            if not day:
                continue
            if str(day) < earliest:
                out.append(f"the requested {label} {day} is before coverage "
                           f"begins ({earliest}); it cannot be served")
            elif str(day) > latest:
                out.append(f"the requested {label} {day} is after the last "
                           f"observation ({latest}); it cannot be served")
        return out

    # -- execute -------------------------------------------------------------

    @traced("mcp_agent.execute", run_type="tool")
    def execute(self, requirement, answers: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fetch the agreed requirement; calculate if one was agreed.

        Wrapped in the provider's input scope when the provider has one, so a
        question the MCP servers raise mid-call — a query that matches both a
        nominal and a real series, say — comes back as `pending_input` instead
        of being silently declined or asked on some terminal nobody is watching.
        This agent never answers such a question and never asks the user: it
        reports it, and the orchestrator owns the conversation.

        `answers` is that question coming back with the user's reply, which
        resumes the same work rather than starting new work.
        """
        scope = getattr(self.data, "input_scope", None)
        if scope is None:
            return self._execute(requirement)
        with scope(answers) as relay:
            result = self._execute(requirement)
        if relay.pending is not None:
            result["pending_input"] = relay.pending
        return result

    def _execute(self, requirement) -> dict[str, Any]:
        tenors = [t for t in requirement.tenors if t in TENOR_MONTHS] or list(DEFAULT_TENORS)
        window_unstated = requirement.rows is None
        rows_wanted = requirement.rows or SAMPLE_ROWS
        notes: list[str] = []
        if window_unstated:
            notes.append(
                f"The knowledge base states no observation window for this task, so "
                f"the most recent {SAMPLE_ROWS} observations were returned as a "
                f"sample. This is not a methodology figure.")

        family = self._resolve_family(requirement, tenors)
        scope = getattr(requirement, "temporal", None)
        # A named single day is a snapshot however many rows were budgeted:
        # "the curve on 2008-09-15" is one curve, not a window ending there.
        wants_snapshot = rows_wanted <= 1 or bool(scope and scope.as_of_date)
        table = (self._snapshot(requirement, family, scope) if wants_snapshot
                 else self._history(tenors, rows_wanted, family, scope))
        if isinstance(table, dict) and table.get("out_of_range"):
            # Refused rather than substituted. Serving the latest curve for a
            # question about 1985 is the silent wrong answer this whole field
            # exists to prevent, and it is worse than an honest refusal.
            return {"table": table, "rows_delivered": 0,
                    "rows_agreed": requirement.rows, "window_unstated": False,
                    "calculation": None,
                    "notes": [table.get("error", {}).get("message", "")]}
        delivered = table.get("row_count", 0)
        if not window_unstated and delivered < rows_wanted:
            notes.append(f"Asked for {rows_wanted:,} observations; the source holds "
                         f"{delivered:,} for this selection. Reported, not padded.")

        calculation = None
        if requirement.calculation:
            calculation = self._calculate(requirement.calculation, requirement)

        return {"table": table, "rows_delivered": delivered,
                "rows_agreed": requirement.rows, "window_unstated": window_unstated,
                "calculation": calculation, "notes": notes}

    @traced("mcp_agent.calculate", run_type="tool")
    def _calculate(self, tool: str, requirement: Any = None) -> dict[str, Any]:
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
            names = method.__code__.co_varnames
            if "portfolio_id" in names:
                portfolio_id = self._first_portfolio(workflows)
                if portfolio_id is None:
                    return {"tool": tool, "error": "no portfolio available to price"}
                kwargs["portfolio_id"] = portfolio_id
            if "scenario_id" in names:
                # A stress test without a shock is not a stress test. The
                # workflow takes either a scenario id or an explicit shock
                # vector and refuses with neither, so resolve a real scenario
                # rather than letting the call fail at the last step.
                scenario_id = self._first_scenario(workflows)
                if scenario_id is None:
                    return {"tool": tool,
                            "error": "no stress scenario available to apply"}
                kwargs["scenario_id"] = scenario_id

            # The parameters the requirement actually states, and only those the
            # workflow accepts. Filtering by signature rather than by a list
            # kept here means a workflow that grows a parameter needs no edit,
            # and one that never had it cannot be handed a surprise.
            for name, value in (getattr(requirement, "calculation_params", None)
                                or {}).items():
                if name in names and value is not None:
                    kwargs[name] = value
            # The window the expert grounded in the corpus is the window the
            # calculation should read. Citing 250 trading days and then computing
            # over the workflow's own default would make the citation decorative.
            rows = getattr(requirement, "rows", None)
            if "trading_days" in names and isinstance(rows, int) and rows > 1:
                kwargs["trading_days"] = rows
            # Value the book on the day the user asked about, not on the latest
            # curve. A DV01 "as of 2020-03-17" priced on today's curve is a
            # different number wearing the requested date's name.
            scope = getattr(requirement, "temporal", None)
            as_of = getattr(scope, "as_of_date", None) if scope else None
            if as_of and "curve_date" in names:
                kwargs["curve_date"] = as_of

            return {"tool": tool, "result": method(**kwargs),
                    "arguments": kwargs}
        except Exception as exc:  # noqa: BLE001 - surfaced, never fatal
            return {"tool": tool, "error": f"{type(exc).__name__}: {exc}"}

    def _workflows(self):
        if not hasattr(self.data, "call_tool"):
            return None
        if not hasattr(self, "_risk_workflows"):
            try:
                from backend.workflows.risk_workflows import RiskWorkflows  # noqa: PLC0415

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

    @staticmethod
    def _first_scenario(workflows) -> str | None:
        try:
            listing = workflows.list_scenarios() or {}
            scenarios = listing.get("scenarios") or []
            return scenarios[0].get("scenario_id") if scenarios else None
        except Exception:  # noqa: BLE001
            return None

    # -- which curve? --------------------------------------------------------

    @traced("mcp_agent.resolve_family", run_type="tool")
    def _resolve_family(self, requirement, tenors: list[str]) -> str:
        """Nominal, real, or ask.

        A nominal par yield and a real yield are different quantities that must
        never share a curve, and the tenor alone does not say which is wanted —
        `y30` exists on both. The domain expert states the family when the user
        made it clear, and marks it `ambiguous` when they did not.

        `ambiguous` is the one case where this agent cannot decide and must not
        guess: the information needed is in the user's head. So it asks the data
        server the question the server is built to answer — `search_series`
        elicits when a query spans two rate kinds — and the resulting question
        travels up as `input-required`. This agent still never speaks to the
        user; it stops, and the orchestrator asks.

        Before this existed the family was hardcoded `nominal`, so a question
        about TIPS was silently answered with the nominal curve. That is the
        precise failure the quoting-basis rule exists to prevent, and it was
        happening in the one place nobody was looking.
        """
        family = getattr(requirement, "curve_family", "nominal") or "nominal"
        if family in {"nominal", "real"}:
            return family
        if not hasattr(self.data, "call_tool"):
            # Nothing to ask with. Nominal is what this backend has always
            # served, and the answer carries the label either way.
            return "nominal"

        # Ask about a maturity that genuinely exists on both curves, discovered
        # from the live catalogue rather than listed here. Asking about a
        # nominal-only tenor would come back unambiguous and resolve the whole
        # requirement to nominal without anyone noticing the question that was
        # never put — which is the silent wrong-curve failure wearing a new hat.
        shared = self._shared_tenors()
        candidates = [t for t in tenors if t in shared]
        if not candidates and not tenors:
            # A snapshot names no tenors — it returns the whole curve — so
            # "none of these is shared" is not what happened here; there was
            # simply nothing to filter. Falling through to nominal answered a
            # question the expert had explicitly said it could not answer:
            # "what is the 30 year?" was marked `ambiguous`, resolved silently
            # to nominal, and served as a nominal par yield with nobody asked.
            #
            # An absent tenor list is not evidence that there is nothing to
            # ask about. Every maturity both curves publish is a candidate.
            candidates = sorted(shared)
        if not candidates:
            # None of these maturities is published on both curves, so there was
            # never anything to ask. No round trip, and no question the user
            # cannot act on.
            LOGGER.info("curve family unambiguous for %s; using nominal", tenors)
            return "nominal"

        query = _tenor_phrase(candidates)
        found = self.data.call_tool("search_series", {"query": query, "limit": 20})
        resolved = (found or {}).get("resolved_rate_kind")
        if resolved in {"nominal", "real"}:
            LOGGER.info("curve family resolved to %r for %r", resolved, query)
            return resolved
        # Either the server raised a question nobody has answered yet — in which
        # case `execute` is about to return `input-required` and this table is
        # never used — or the query turned out to be unambiguous after all.
        return "nominal"

    def _shared_tenors(self) -> set[str]:
        """Tenors both curve families publish, from the live series catalogue."""
        by_kind: dict[str, set[str]] = {}
        try:
            for row in self.data.list_series() or []:
                if isinstance(row, dict) and row.get("tenor"):
                    by_kind.setdefault(row.get("rate_kind", ""), set()).add(row["tenor"])
        except Exception as exc:  # noqa: BLE001 - a thinner question beats none
            LOGGER.warning("could not read the series catalogue: %s", exc)
            return set()
        return by_kind.get("nominal", set()) & by_kind.get("real", set())

    # -- shapes --------------------------------------------------------------

    def _snapshot(self, requirement, family: str = "nominal",
                  scope=None) -> dict[str, Any]:
        as_of = getattr(scope, "as_of_date", None) if scope else None
        curve = self.data.get_yield_curve(as_of, family)
        if not isinstance(curve, dict) or "error" in curve:
            return self._out_of_range(as_of, curve) if as_of else \
                self._empty("Curve unavailable", curve)
        rows = [{"tenor": tenor, "rate_percent": rate,
                 "quote_basis": curve.get("quote_basis"), "rate_kind": family,
                 "observation_date": curve.get("curve_date")}
                for tenor, rate in (curve.get("points") or {}).items()]
        allowed = {"tenor", "rate_percent", "quote_basis", "rate_kind", "observation_date"}
        columns = [c for c in requirement.fields if c in allowed] or \
                  ["tenor", "rate_percent", "quote_basis"]
        title = f"{family.capitalize()} par curve — {curve.get('curve_date')}"
        table = self._table(rows, columns, title, self._provenance(curve, family))
        if as_of and curve.get("date_was_shifted"):
            # The date moved to the nearest published curve — a weekend or a
            # holiday. Legitimate, but the answer must say so rather than let
            # the reader assume they got the day they asked for.
            table["date_was_shifted"] = True
            table["requested_date"] = as_of
        return table

    def _history(self, tenors: list[str], rows_wanted: int,
                 family: str = "nominal", scope=None) -> dict[str, Any]:
        start = getattr(scope, "start_date", None) if scope else None
        end = getattr(scope, "end_date", None) if scope else None
        by_date: dict[str, dict[str, Any]] = {}
        for tenor in tenors:
            try:
                series = self.data.get_rate_history(tenor, start, end,
                                                    kind=family) or []
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("history failed for %s: %s", tenor, exc)
                continue
            for point in series:
                if isinstance(point, dict) and "error" not in point:
                    day = point.get("observation_date")
                    if day:
                        by_date.setdefault(day, {"observation_date": day})[tenor] = \
                            point.get("rate_percent")

        if not by_date and (start or end):
            return self._out_of_range(
                f"{start or 'the start of coverage'} to {end or 'the latest observation'}",
                {"message": "no observations were published in that period"})

        curve = self.data.get_yield_curve(None, family)
        basis = curve.get("quote_basis") if isinstance(curve, dict) else None
        # A window is the N most recent observations, not the first N returned.
        ordered = [by_date[day] for day in sorted(by_date, reverse=True)][:rows_wanted]
        for row in ordered:
            row["quote_basis"] = basis
        # Naming fourteen tenors makes a four-line heading that swallows the
        # panel. The full tenor list is already the table's columns.
        label = (", ".join(tenors) if len(tenors) <= 4
                 else f"{len(tenors)} tenors ({tenors[0]}–{tenors[-1]})")
        kind = "Real" if family == "real" else "Par"
        when = (f"{start or 'start'} to {end or 'latest'}" if (start or end)
                else f"most recent {len(ordered)} rows")
        # A history table is not a curve, so it does not carry a `curve_date`.
        # Borrowing the latest curve's date — which is fetched here only to
        # learn the quoting basis — put "Data as of 2026-08-11" on a table of
        # 2008 observations. The number was right and the label was wrong,
        # which is the worse of the two failures: nothing downstream could tell.
        provenance = self._provenance(curve, family)
        provenance.pop("curve_date", None)
        days = sorted(row["observation_date"] for row in ordered)
        if days:
            provenance["observed_from"] = str(days[0])
            provenance["observed_to"] = str(days[-1])
        return self._table(ordered, ["observation_date", *tenors, "quote_basis"],
                           f"{kind} yields — {label} ({when})", provenance)

    @staticmethod
    def _out_of_range(requested: Any, detail: Any) -> dict[str, Any]:
        """A period the source does not cover. Refused, and labelled as refused.

        Marked `out_of_range` so `execute` stops rather than falling through to
        a table built from whatever the provider returned instead. The one
        outcome that must never happen here is a plausible curve carrying the
        wrong date.
        """
        message = (detail or {}).get("message") if isinstance(detail, dict) else None
        return {"title": f"No data for {requested}", "columns": [], "rows": [],
                "row_count": 0, "displayed": 0, "truncated": False,
                "provenance": {}, "out_of_range": True,
                "error": {"message": (
                    f"The source publishes no observations for {requested}"
                    + (f": {message}" if message else "."))}}

    @staticmethod
    def _provenance(curve: Any, family: str = "nominal") -> dict[str, Any]:
        if not isinstance(curve, dict):
            return {}
        return {"dataset_snapshot_id": curve.get("dataset_snapshot_id"),
                "source_file": curve.get("source_file"),
                "curve_date": curve.get("curve_date"),
                "quote_basis": curve.get("quote_basis"),
                # Which curve this came from, alongside the basis. A reader
                # comparing two tables must be able to see that one is TIPS-
                # derived without inferring it from the numbers.
                "rate_kind": family,
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


#: Tenor key -> the words a person would use, for the one query this agent
#: sends to `search_series`. Not a Treasury field list — it is a translation of
#: this agent's own tenor vocabulary, and a maturity Treasury adds needs no edit
#: here because an unknown key simply falls through to itself.
_TENOR_WORDS = {
    "m1": "1 month", "m1_5": "1.5 month", "m2": "2 month", "m3": "3 month",
    "m4": "4 month", "m6": "6 month", "y1": "1 year", "y2": "2 year",
    "y3": "3 year", "y5": "5 year", "y7": "7 year", "y10": "10 year",
    "y20": "20 year", "y30": "30 year",
}


def _tenor_phrase(tenors: list[str]) -> str:
    """The query to ask the series catalogue about, in a person's words."""
    for tenor in tenors:
        if tenor in _TENOR_WORDS:
            return _TENOR_WORDS[tenor]
    return tenors[0] if tenors else "10 year"


def _strs(value: Any) -> list[str]:
    return [str(v) for v in (value or []) if v is not None and str(v).strip()]


def _cell(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value
