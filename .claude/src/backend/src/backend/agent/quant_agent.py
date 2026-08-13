"""Quant agent (Phase 4).

A Claude-driven reasoning loop that:
  1. receives a client request,
  2. understands intent (asks to clarify if genuinely ambiguous),
  3. retrieves relevant quant knowledge from the vector DB (domain-scoped),
  4. decides which risk data is actually required,
  5. calls the data tools (DataProvider) to fetch only that,
  6. composes an answer,
  7. and emits a structured decision trace at every step.

The agent talks only to the KnowledgeBase and the DataProvider interface, so
swapping the vector engine, or the mock data -> the real Postgres provider,
requires no change here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic

from backend.providers.base import DataProvider, make_data_provider
from backend.knowledge.knowledge_base import KnowledgeBase

MODEL = "claude-opus-5"
MAX_STEPS = 12
DOMAINS = ["market_risk", "xva", "regulatory_capital", "credit_risk"]

SYSTEM_PROMPT = """\
You are a server-side market-risk agent for a bank. Your data source is the U.S. \
Treasury interest-rate database — daily nominal and real par yield curves, plus \
the associated rate history. You answer questions about the yield curve and the \
market-risk metrics that can be computed from interest rates.

What you can do with the available data:
- Curve levels and history: the latest curve, a single tenor's history, the \
latest rate per tenor, and the series catalogue.
- Curve shape: slopes such as 2s10s (get_curve_slope).
- Rate market-risk metrics grounded in the knowledge base: interest-rate VaR and \
Expected Shortfall from rate-change history, DV01 / sensitivities on the curve, \
and parallel-shift stress.

Scope limits — be honest about them:
- You have NO portfolio positions and NO counterparty data. Metrics that need \
them — CVA, counterparty exposure (EE/EPE/PFE), RWA, PD/LGD/EAD — you can explain \
from the knowledge base, but you cannot compute them. Say so plainly and offer \
what you CAN compute from rates instead.

How to work:
- First understand the intent. If genuinely ambiguous (which tenor, which date, \
which metric, what horizon/confidence), ask ONE concise clarifying question.
- Before computing a metric, call `retrieve_knowledge` to ground yourself in its \
definition and required inputs. Pass a `domain` when you know it.
- Fetch only the data you need. Tenors are keys like m1, m3, m6, y1, y2, y10, y30.
- When the user asks for a TABLE, ROWS, FIELDS/COLUMNS, a dataset or an extract - \
or names a row count - call `plan_and_fetch_dataset`. Pass what the data is FOR as \
`task`, plus any fields and row count they named. It decides the minimal set and \
returns the table to the UI directly.
- After that call your reply must be SHORT: at most three sentences, no headings, \
no bullet lists, no tables. The table and the full reasoning are already on screen \
in a panel the user can open. Lead with the single most useful fact - usually the \
row count against what they asked for - and stop. Do not restate the field list, \
do not re-print rows, do not enumerate the sources; the panel shows all of that. \
Example of the right length: "250 rows, not 10,000 - that's the window historical \
simulation actually revalues over. Three of your six fields aren't published by \
this dataset; the panel shows which and why."
- For every other kind of answer: show the calculation at a high level and state \
the result plainly, with units and the assumptions you used. Keep it focused and \
concise, and prefer short prose over long bulleted breakdowns.
"""

TOOLS = [
    {
        "name": "retrieve_knowledge",
        "description": (
            "Search the quant knowledge base (VaR/ES/stress/Greeks, CVA/exposure, "
            "RWA/Basel, PD/LGD/EAD) for definitions, formulas, and which data "
            "inputs each metric requires. Call this before deciding what data to "
            "fetch. Optionally scope to a domain for sharper results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look up."},
                "domain": {
                    "type": "string",
                    "enum": DOMAINS,
                    "description": "Optional desk to scope the search to.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "plan_and_fetch_dataset",
        "description": (
            "USE THIS whenever the user asks for a table, rows, columns/fields, a "
            "dataset, an extract, or names a row count ('give me 10,000 rows of "
            "...'). It decides which fields and how many rows the stated task "
            "actually needs, grounded in the knowledge base, then returns both the "
            "plan and the data as a real table. Prefer it over get_rate_history for "
            "any request phrased as data delivery rather than a single number. "
            "Report the plan's reasoning to the user - the point is that the "
            "reduction is explained, not silent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "What the data is FOR, in the user's own terms "
                                   "(e.g. '10-day 99% historical VaR on the book'). "
                                   "This drives the field and row decision.",
                },
                "requested_fields": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Fields the user asked for, if they named any.",
                },
                "requested_rows": {
                    "type": "integer",
                    "description": "Row count the user asked for, if they named one.",
                },
                "tenors": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Tenor keys such as y2, y10. Defaults to y2 and y10.",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "list_series",
        "description": "Catalogue of available rate series/tenors (tenor, tenor_years, rate_kind, quote_basis).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_latest_rates",
        "description": "The most recent rate per tenor on the nominal par curve.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_yield_curve",
        "description": "One day's full yield curve, wide by tenor. Defaults to the latest date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "curve_date": {"type": "string", "description": "ISO date YYYY-MM-DD; omit for latest."},
                "kind": {"type": "string", "enum": ["nominal", "real"], "description": "Curve kind (default nominal)."},
            },
        },
    },
    {
        "name": "get_rate_history",
        "description": "Daily history for one tenor (e.g. 'y10'), for rate-change VaR/ES/volatility.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tenor": {"type": "string", "description": "Tenor key, e.g. m3, y2, y10, y30."},
                "start": {"type": "string", "description": "ISO start date; optional."},
                "end": {"type": "string", "description": "ISO end date; optional (default latest)."},
            },
            "required": ["tenor"],
        },
    },
    {
        "name": "get_curve_slope",
        "description": "Slope between two tenors in basis points, e.g. 2s10s (short=y2, long=y10).",
        "input_schema": {
            "type": "object",
            "properties": {
                "short": {"type": "string", "description": "Short tenor (default y2)."},
                "long": {"type": "string", "description": "Long tenor (default y10)."},
                "curve_date": {"type": "string", "description": "ISO date; omit for latest."},
            },
        },
    },
]


# Offered only when the data provider is MCP-backed, because they need the
# risk engine and the demo book behind it. With a mock or direct-Postgres
# provider the agent simply never sees them and says so honestly.
RISK_TOOLS = [
    {
        "name": "list_portfolios",
        "description": "Portfolios available to value. These are SYNTHETIC_DEMO books, not real positions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_portfolio",
        "description": "Positions in one portfolio: instruments, coupons, maturities, notionals.",
        "input_schema": {
            "type": "object",
            "properties": {"portfolio_id": {"type": "string"}},
            "required": ["portfolio_id"],
        },
    },
    {
        "name": "price_portfolio",
        "description": (
            "Mark a portfolio to market off the Treasury par curve. Bootstraps a "
            "discount curve first — par yields are NOT used as discount rates. "
            "Returns dirty (full) present value per position and in total."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "curve_date": {"type": "string", "description": "ISO date; omit for latest."},
            },
            "required": ["portfolio_id"],
        },
    },
    {
        "name": "compute_dv01",
        "description": (
            "DV01 by full revaluation (not an analytic approximation, so convexity "
            "is captured). Set key_rates for per-tenor sensitivities at 2/5/10/20/30Y."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "curve_date": {"type": "string"},
                "key_rates": {"type": "boolean", "description": "Also return key-rate DV01s."},
            },
            "required": ["portfolio_id"],
        },
    },
    {
        "name": "compute_var",
        "description": (
            "Historical-simulation VaR and Expected Shortfall from one revaluation "
            "pass over observed curve history. h-day horizons use observed h-day "
            "changes, never 1-day scaled by sqrt(h)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "confidence_level": {"type": "number", "description": "e.g. 0.99 (default)."},
                "horizon_days": {"type": "integer", "description": "Default 1."},
                "trading_days": {"type": "integer", "description": "Observation window, default 250."},
            },
            "required": ["portfolio_id"],
        },
    },
    {
        "name": "list_scenarios",
        "description": "Stress scenarios: TENOR_VECTOR_BP (hypothetical) or HISTORICAL_REPLAY (real dates).",
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario_type": {"type": "string", "enum": ["TENOR_VECTOR_BP", "HISTORICAL_REPLAY"]},
            },
        },
    },
    {
        "name": "run_stress",
        "description": (
            "Revalue a portfolio under a shock. Give either a scenario_id, or an "
            "explicit shock vector keyed by tenor in months (e.g. {\"120.0\": 100} "
            "for +100bp on the 10-year)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "scenario_id": {"type": "string"},
                "shocks_bp_by_tenor_months": {
                    "type": "object",
                    "description": "Tenor-in-months -> basis points, e.g. {\"120.0\": 100}.",
                    "additionalProperties": {"type": "number"},
                },
                "curve_date": {"type": "string"},
            },
            "required": ["portfolio_id"],
        },
    },
    {
        "name": "explain_number",
        "description": (
            "Provenance for a single published rate: the Treasury source file, its "
            "URL and SHA-256. Use when asked where a number came from."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "series_code": {"type": "string", "description": "e.g. BC_10YEAR."},
                "observation_date": {"type": "string", "description": "ISO date."},
            },
            "required": ["series_code", "observation_date"],
        },
    },
]

RISK_PROMPT = """\

You are connected to a risk engine and a synthetic demo portfolio, so you CAN \
value positions and compute portfolio risk. This supersedes any assumption that \
you have no positions.

- Value a book with `price_portfolio`; sensitivity with `compute_dv01`; \
VaR and Expected Shortfall with `compute_var`; scenarios with `run_stress`.
- The portfolio is SYNTHETIC_DEMO — invented for demonstration. The market data \
is real and verified. Always keep that distinction explicit in your answer.
- Bond values are model-implied from the par curve, not executable prices.
- Reported VaR is an analytical demonstration, not a regulatory figure.
- When asked where a number came from, use `explain_number` — it returns the \
Treasury file and its SHA-256.
- You still have no counterparty data, so CVA, EE/EPE/PFE and RWA remain \
explainable but not computable.
"""


# Tool name -> RiskWorkflows method. Arguments pass straight through, so the
# schemas above and the method signatures must agree.
_RISK_DISPATCH = {
    "list_portfolios": "list_portfolios",
    "get_portfolio": "get_portfolio",
    "price_portfolio": "price_portfolio",
    "compute_dv01": "compute_dv01",
    "compute_var": "compute_var",
    "list_scenarios": "list_scenarios",
    "run_stress": "run_stress",
    "explain_number": "explain_number",
}


@dataclass
class TraceStep:
    kind: str          # intent|knowledge|decision|tool_call|answer|clarification
    label: str
    detail: object = None


@dataclass
class AgentResult:
    answer: str
    trace: list[TraceStep] = field(default_factory=list)
    awaiting_clarification: bool = False
    messages: list = field(default_factory=list)  # full conversation, to persist per session
    # Structured tabular output, kept out of the prose on purpose: the UI needs a
    # real table widget, and a markdown string cannot be sorted or scrolled.
    tables: list = field(default_factory=list)
    data_plan: dict | None = None


# A clarification is short by nature: it is the agent saying it cannot proceed.
# Anything past this length has answered something first.
_MAX_CLARIFICATION_CHARS = 400

# Markdown structure is the clearest evidence that a turn delivered content
# rather than asking for it. A question does not need a table.
_STRUCTURE_MARKERS = ("\n#", "\n|", "\n- ", "\n* ", "\n1. ", "```", "\n\n")


def is_clarification(text: str) -> bool:
    """True when the turn is *nothing but* a question.

    A trailing '?' alone is not enough, and relying on it was a real defect: a
    complete 2,300-character answer that ended "Want me to run DV01 on the demo
    book?" was flagged as awaiting clarification, while the same answer ending
    "Say which and I'll run it." was not. Identical intent, opposite
    classification, decided by the final character.

    Downstream that mistake is expensive - the service reports
    `awaiting_clarification: true`, and the UI draws a "pick one" prompt under a
    finished answer. So the test is whether the agent produced substance before
    asking, not whether it happened to end on a question mark.
    """
    body = (text or "").rstrip()
    if not body.endswith("?"):
        return False
    if any(marker in body for marker in _STRUCTURE_MARKERS):
        return False
    return len(body) <= _MAX_CLARIFICATION_CHARS


class QuantAgent:
    def __init__(self, kb: KnowledgeBase | None = None, data: DataProvider | None = None):
        self.client = anthropic.Anthropic()
        self.kb = kb or KnowledgeBase()
        self.data = data or make_data_provider()

        # Portfolio and risk tools depend on the risk engine, which only the MCP
        # provider can reach. Detect the capability rather than reading the env
        # var again, so an injected provider is honoured too.
        self.risk = None
        if hasattr(self.data, "call_tool"):
            from backend.agent.risk_workflows import RiskWorkflows  # noqa: PLC0415
            self.risk = RiskWorkflows(self.data)

        self.tools = TOOLS + (RISK_TOOLS if self.risk else [])
        self.system_prompt = SYSTEM_PROMPT + (RISK_PROMPT if self.risk else "")

    @staticmethod
    def _provenance_of(curve: dict) -> dict:
        """Where a table's numbers came from, for the panel's Source tab.

        Carried on the table rather than left in the prose: a reviewer checking
        a figure should not have to scroll a conversation to find the file and
        snapshot it came from.
        """
        return {
            "dataset_snapshot_id": curve.get("dataset_snapshot_id"),
            "source_file": curve.get("source_file"),
            "curve_date": curve.get("curve_date"),
            "quote_basis": curve.get("quote_basis"),
            "classification": "REAL_MARKET_DATA",
        }

    def _plan_and_fetch(self, args: dict, trace: list[TraceStep]) -> object:
        """Plan the data requirement, fetch exactly that, return plan + table.

        The plan is emitted into the trace as its own step so the decision is
        visible next to the data it produced, rather than only inside the prose.
        """
        from backend.agent import data_planner  # noqa: PLC0415

        task = args.get("task") or "unspecified task"
        tenors = [t for t in (args.get("tenors") or ["y2", "y10"])
                  if t in data_planner.TENOR_MONTHS] or ["y2", "y10"]

        catalogue = self.data.list_series()
        available = sorted({k for row in catalogue for k in row} |
                           set(data_planner.MANDATORY_FIELDS) | {"tenor"})

        plan = data_planner.plan(
            task, args.get("requested_fields"), args.get("requested_rows"),
            available_fields=available, knowledge=self.kb,
        )

        if plan.granted_rows <= 1:
            curve = self.data.get_yield_curve(None, "nominal")
            if "error" in curve:
                return curve
            rows = [{"tenor": t, "rate_percent": v,
                     "quote_basis": curve.get("quote_basis"),
                     "rate_kind": "nominal",
                     "observation_date": curve.get("curve_date")}
                    for t, v in (curve.get("points") or {}).items()]
            columns = [c for c in plan.granted_fields if c in
                       {"tenor", "rate_percent", "quote_basis", "rate_kind",
                        "observation_date"}]
            table = data_planner.build_table(
                rows, columns or ["tenor", "rate_percent", "quote_basis"],
                f"Nominal par curve — {curve.get('curve_date')}")
            table["provenance"] = self._provenance_of(curve)
        else:
            # One series per tenor, aligned on date so the table reads as a
            # curve history rather than as several unrelated columns.
            by_date: dict[str, dict[str, object]] = {}
            basis = None
            for tenor in tenors:
                for point in self.data.get_rate_history(tenor) or []:
                    if "error" in point:
                        continue
                    day = point["observation_date"]
                    by_date.setdefault(day, {"observation_date": day})[tenor] = \
                        point["rate_percent"]
            curve = self.data.get_yield_curve(None, "nominal")
            basis = curve.get("quote_basis") if isinstance(curve, dict) else None
            ordered = [by_date[d] for d in sorted(by_date, reverse=True)]
            ordered = ordered[:plan.granted_rows]
            for row in ordered:
                row["quote_basis"] = basis
            table = data_planner.build_table(
                ordered, ["observation_date", *tenors, "quote_basis"],
                f"Par yields — {', '.join(tenors)} (most recent {len(ordered)} rows)")
            table["provenance"] = self._provenance_of(curve)

        self._tables.append(table)
        self._data_plan = plan.as_dict()
        trace.append(TraceStep(
            "decision",
            f"Data requirement plan [{plan.profile}]: "
            f"{len(plan.granted_fields)} field(s), {plan.granted_rows} row(s)",
            plan.as_dict(),
        ))
        trace.append(TraceStep("tool_call", f"Fetched dataset: {table['title']}"))
        # The model gets the plan and a small sample. The full table goes to the
        # UI out of band - putting 250 rows in the prompt would cost a fortune
        # and teach the model to paste them back into the answer.
        return {"plan": plan.as_dict(),
                "table_preview": {"columns": table["columns"],
                                  "rows": table["rows"][:5],
                                  "total_rows": table["row_count"]},
                "note": "The full table is rendered in the UI. Summarise the plan "
                        "and the shape; do not re-print the rows."}

    def _dispatch(self, name: str, args: dict, trace: list[TraceStep]) -> object:
        if name == "plan_and_fetch_dataset":
            return self._plan_and_fetch(args, trace)
        if name == "retrieve_knowledge":
            hits = self.kb.retrieve(args["query"], domain=args.get("domain"))
            scope = f" [{args['domain']}]" if args.get("domain") else ""
            trace.append(TraceStep(
                "knowledge", f"Retrieved knowledge: '{args['query']}'{scope}",
                [f"{h['domain']}/{h['source']}/{h['heading']} (dist={h['distance']})" for h in hits],
            ))
            return hits
        if self.risk is not None and name in _RISK_DISPATCH:
            result = getattr(self.risk, _RISK_DISPATCH[name])(**args)
            trace.append(TraceStep("tool_call", f"Risk engine: {name}({args})"))
            return result
        if name == "list_series":
            result = self.data.list_series()
        elif name == "get_latest_rates":
            result = self.data.get_latest_rates()
        elif name == "get_yield_curve":
            result = self.data.get_yield_curve(args.get("curve_date"), args.get("kind", "nominal"))
        elif name == "get_rate_history":
            result = self.data.get_rate_history(args["tenor"], args.get("start"), args.get("end"))
        elif name == "get_curve_slope":
            result = self.data.get_curve_slope(args.get("short", "y2"), args.get("long", "y10"), args.get("curve_date"))
        else:
            return {"error": f"unknown tool {name}"}
        trace.append(TraceStep("tool_call", f"Fetched data: {name}({args})"))
        return result

    def answer(self, request: str, history: list | None = None) -> AgentResult:
        """Answer a request. Pass `history` (a prior AgentResult.messages) to
        continue a session — e.g. after the agent asked a clarifying question."""
        trace = [TraceStep("intent", "Received client request", request)]
        messages = list(history or []) + [{"role": "user", "content": request}]
        # Per-turn, not per-agent: a table fetched two questions ago must not
        # reappear under an answer that had nothing to do with it.
        self._tables: list = []
        self._data_plan: dict | None = None

        for _ in range(MAX_STEPS):
            resp = self.client.messages.create(
                model=MODEL,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=self.system_prompt,
                tools=self.tools,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": resp.content})

            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            text = "".join(b.text for b in resp.content if b.type == "text").strip()

            if not tool_uses:
                is_question = resp.stop_reason == "end_turn" and is_clarification(text)
                trace.append(TraceStep(
                    "clarification" if is_question else "answer",
                    "Asked for clarification" if is_question else "Composed answer",
                    text,
                ))
                return AgentResult(answer=text, trace=trace,
                                   awaiting_clarification=is_question, messages=messages,
                                   tables=self._tables, data_plan=self._data_plan)

            if text:
                trace.append(TraceStep("decision", "Reasoning", text))

            results = []
            for tu in tool_uses:
                out = self._dispatch(tu.name, tu.input or {}, trace)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(out, default=str),
                })
            messages.append({"role": "user", "content": results})

        trace.append(TraceStep("answer", "Stopped: step limit reached", None))
        return AgentResult(answer="(step limit reached)", trace=trace, messages=messages)


def trace_as_dicts(trace: list[TraceStep]) -> list[dict]:
    """JSON-serializable form of the decision trace, for the /chat contract."""
    return [{"kind": s.kind, "label": s.label, "detail": s.detail} for s in trace]


def extract_sources(trace: list[TraceStep]) -> list[str]:
    """Unique 'domain/source' knowledge docs the agent leaned on, in order."""
    seen: list[str] = []
    for s in trace:
        if s.kind == "knowledge" and isinstance(s.detail, list):
            for line in s.detail:
                doc = "/".join(line.split("/")[:2])  # domain/source
                if doc and doc not in seen:
                    seen.append(doc)
    return seen


def render_trace(trace: list[TraceStep]) -> str:
    lines = []
    for s in trace:
        lines.append(f"- [{s.kind}] {s.label}")
        if isinstance(s.detail, list):
            lines.extend(f"      - {d}" for d in s.detail)
        elif s.detail:
            snippet = str(s.detail).replace("\n", " ")
            lines.append(f"      {snippet[:200]}")
    return "\n".join(lines)
