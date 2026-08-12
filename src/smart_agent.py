"""Smart server-side agent (Phase 4).

A Claude-driven reasoning loop that:
  1. receives a client request,
  2. understands intent (asks to clarify if genuinely ambiguous),
  3. retrieves relevant quant knowledge from the vector DB (domain-scoped),
  4. decides which risk data is actually required,
  5. calls the data tools (DataProvider) to fetch only that,
  6. composes an answer,
  7. and emits a structured decision trace at every step.

The agent talks only to the KnowledgeBase and the DataProvider interface, so
swapping ChromaDB -> pgvector, or the mock data -> a real MCP/DB-backed provider,
requires no change here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic

from data_provider import DataProvider, MockDataProvider
from knowledge_base import KnowledgeBase

MODEL = "claude-opus-5"
MAX_STEPS = 12
DOMAINS = ["market_risk", "xva", "regulatory_capital", "credit_risk"]

SYSTEM_PROMPT = """\
You are a server-side quantitative risk agent for a bank. You answer questions \
about market and counterparty risk — Value at Risk (VaR), Expected Shortfall, \
stress testing, sensitivities/Greeks, Credit Valuation Adjustment (CVA), \
counterparty exposure (EE/EPE/PFE), Risk-Weighted Assets (RWA), Basel capital \
ratios, and credit parameters (PD/LGD/EAD).

How to work:
- First understand what the user is actually asking for.
- If the request is genuinely ambiguous (missing which metric, portfolio, \
counterparty, confidence level, or horizon), ask ONE concise clarifying \
question instead of guessing.
- Before computing anything, call `retrieve_knowledge` to ground yourself in the \
correct definition and the exact data each metric requires. Pass a `domain` \
when you know which desk the question belongs to.
- Then decide which data you actually need and call only the relevant data \
tools. Do not fetch data a metric does not require.
- Show the calculation at a high level and state the result plainly, with units \
and the assumptions you used.
- Keep the final answer focused and concise.
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
        "name": "get_assets",
        "description": "List assets in the book (id, name, asset_class, currency).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_historical_prices",
        "description": "Historical price series for one asset, for return/VaR/ES calc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string"},
                "days": {"type": "integer", "description": "Trading days (default 250)."},
            },
            "required": ["asset_id"],
        },
    },
    {
        "name": "get_portfolio_positions",
        "description": "Current portfolio positions (asset_id, quantity, market_value).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_counterparty_exposure",
        "description": (
            "Counterparty exposure and credit inputs (exposure, EPE, spread, "
            "recovery, rating). Needed for CVA and RWA. Optional 'counterparty' filter."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"counterparty": {"type": "string"}},
        },
    },
]


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


class SmartAgent:
    def __init__(self, kb: KnowledgeBase | None = None, data: DataProvider | None = None):
        self.client = anthropic.Anthropic()
        self.kb = kb or KnowledgeBase()
        self.data = data or MockDataProvider()

    def _dispatch(self, name: str, args: dict, trace: list[TraceStep]) -> object:
        if name == "retrieve_knowledge":
            hits = self.kb.retrieve(args["query"], domain=args.get("domain"))
            scope = f" [{args['domain']}]" if args.get("domain") else ""
            trace.append(TraceStep(
                "knowledge", f"Retrieved knowledge: '{args['query']}'{scope}",
                [f"{h['domain']}/{h['source']}/{h['heading']} (dist={h['distance']})" for h in hits],
            ))
            return hits
        if name == "get_assets":
            result = self.data.get_assets()
        elif name == "get_historical_prices":
            result = self.data.get_historical_prices(args["asset_id"], args.get("days", 250))
        elif name == "get_portfolio_positions":
            result = self.data.get_portfolio_positions()
        elif name == "get_counterparty_exposure":
            result = self.data.get_counterparty_exposure(args.get("counterparty"))
        else:
            return {"error": f"unknown tool {name}"}
        trace.append(TraceStep("tool_call", f"Fetched data: {name}({args})"))
        return result

    def answer(self, request: str) -> AgentResult:
        trace = [TraceStep("intent", "Received client request", request)]
        messages = [{"role": "user", "content": request}]

        for _ in range(MAX_STEPS):
            resp = self.client.messages.create(
                model=MODEL,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": resp.content})

            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            text = "".join(b.text for b in resp.content if b.type == "text").strip()

            if not tool_uses:
                is_question = resp.stop_reason == "end_turn" and text.rstrip().endswith("?")
                trace.append(TraceStep(
                    "clarification" if is_question else "answer",
                    "Asked for clarification" if is_question else "Composed answer",
                    text,
                ))
                return AgentResult(answer=text, trace=trace, awaiting_clarification=is_question)

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
        return AgentResult(answer="(step limit reached)", trace=trace)


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
