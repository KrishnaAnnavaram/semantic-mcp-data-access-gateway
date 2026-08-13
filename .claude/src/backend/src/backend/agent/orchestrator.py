"""Front door for every question: triage cheaply, escalate only when needed.

Three things arrive at `/chat` and they cost wildly different amounts to answer:

    "hi"                          -> a sentence. No data, no tools, no domain.
    "what's the VaR"              -> underspecified. Which book? What horizon?
    "2s10s slope on 2026-08-11"   -> a real question for the quant agent.

Routing all three through Opus with seventeen MCP tools loaded means "hi" pays
for a tool-selection problem it does not have. The orchestrator triages with
Haiku first and only wakes the quant agent for the third case.

The second case is the one that was previously broken. The old loop had no way
to say "I need more information", so an underspecified question was answered by
guessing — silently picking a tenor, a date, a confidence level. Now it comes
back as a structured elicitation the UI can render as an actual question.

Routing is a **tool call**, not parsed prose. A model asked to reply with the
word "QUANT" will eventually reply "QUANT." or "Route: quant", and a string
comparison will send a risk question to the small-talk path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic

from backend.agent.quant_agent import AgentResult, QuantAgent, TraceStep

LOGGER = logging.getLogger("backend.orchestrator")

# Triage is a classification problem, not a reasoning one. Haiku is the right
# size for it and keeps "hi" from costing an Opus turn.
TRIAGE_MODEL = "claude-haiku-4-5-20251001"
TRIAGE_MAX_TOKENS = 1024

TRIAGE_SYSTEM = """\
You are the front door of a market-risk data gateway. Classify the user's \
message and route it. You never answer domain questions yourself.

Routes:

- `answer` — greetings, thanks, goodbyes, and questions about what this system \
is or can do. Reply yourself, warmly and briefly. Also use this to decline \
things clearly out of scope (weather, general coding, unrelated topics).

  **Never explain a finance or risk concept yourself.** "What is VaR", "explain \
DV01", "how does a par curve work" all go to `quant`, which has an authoritative \
knowledge base. Answering those from memory bypasses it and invents definitions \
that may not match this system's actual conventions.

- `clarify` — the user wants market-risk work, but a required detail is missing \
**and no sensible default exists**. Ask ONE short question and offer concrete \
options where you can.

  Clarify when the message omits:
    * which tenor, when a single rate is implied but none is named \
("how have rates moved lately")
    * confidence level or horizon for VaR/ES, when neither is stated and no \
portfolio context implies one
    * which portfolio, when more than one exists and none is named

  Do **not** clarify — route to `quant` — when a default is obvious:
    * **No date means the latest published data.** Never ask "which date"
      just because none was given.
    * A named tenor or spread is already specific: "the 10-year", "2s10s",
      "the 30-year real yield" need nothing more.
    * "the curve", "current", "today" all mean the latest curve.
    * A definition or explanation request needs no parameters at all.

  When in doubt between `clarify` and `quant`, choose `quant`. The quant agent \
can ask its own question once it has looked at the data, and a needless \
question is worse than a good default.

- `quant` — a well-specified market-risk question, **or any request to explain a \
finance concept**. Route it onward with no answer of your own.

What the system can do, for `answer` replies: Treasury nominal and real yield \
curves from 1990 to today; curve levels, history and slopes; portfolio pricing, \
DV01 and key-rate DV01; historical VaR and Expected Shortfall; hypothetical and \
historical-replay stress. It cannot do CVA, counterparty exposure or RWA — \
there is no counterparty data.

Be brief. A greeting deserves one or two sentences, not a brochure.
"""

ROUTE_TOOL: dict[str, Any] = {
    "name": "route",
    "description": "Classify the message and either answer it, ask for the one "
                   "missing detail, or hand it to the quant agent.",
    "input_schema": {
        "type": "object",
        "properties": {
            "route": {
                "type": "string",
                "enum": ["answer", "clarify", "quant"],
                "description": "Where this message goes.",
            },
            "reply": {
                "type": "string",
                "description": "route=answer only: the complete reply to send.",
            },
            "question": {
                "type": "string",
                "description": "route=clarify only: ONE concise question.",
            },
            "options": {
                "type": "array",
                "description": "route=clarify only: concrete choices, when they exist.",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "description": "Short button text."},
                        "value": {"type": "string",
                                  "description": "What to send back if chosen."},
                    },
                    "required": ["label", "value"],
                },
            },
            "reason": {
                "type": "string",
                "description": "One short phrase: why this route. For the trace.",
            },
        },
        "required": ["route"],
    },
}


@dataclass
class Elicitation:
    """A question back to the user, structured so a UI can render it properly."""

    question: str
    options: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"question": self.question, "options": self.options}


@dataclass
class OrchestratorResult:
    answer: str
    route: str
    trace: list[TraceStep] = field(default_factory=list)
    elicitation: Elicitation | None = None
    messages: list = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    @property
    def awaiting_clarification(self) -> bool:
        return self.elicitation is not None


class Orchestrator:
    """Triage in front of the quant agent.

    The quant agent is built lazily and reused: constructing it spawns the MCP
    child processes and opens a `mcp_reader` connection, which is far too
    expensive to pay for a message that turns out to be "thanks".
    """

    def __init__(self, quant_agent: QuantAgent | None = None,
                 quant_agent_factory: Callable[[], QuantAgent] | None = None) -> None:
        self.client = anthropic.Anthropic()
        self._quant = quant_agent
        self._factory = quant_agent_factory or QuantAgent

    @property
    def quant(self) -> QuantAgent:
        if self._quant is None:
            LOGGER.info("first quant question this process — starting the quant agent")
            self._quant = self._factory()
        return self._quant

    def summarise_session(self, messages: list[dict]) -> str:
        """Name a conversation from what it turned out to be about.

        The opening question makes a poor title: it is often the vaguest thing
        the user says all session, and is frequently replaced by a clarification
        one turn later. Naming from the whole exchange gives "10Y VaR and 1994
        replay" instead of "hi can you help".
        """
        transcript = "\n".join(
            f"{m.get('role', '?')}: {str(m.get('content', ''))[:400]}"
            for m in messages[-12:]
            if isinstance(m.get("content"), str)
        )
        if not transcript.strip():
            return "New chat"

        response = self.client.messages.create(
            model=TRIAGE_MODEL,
            max_tokens=64,
            system="Title this conversation in 2 to 6 words. Name the subject, not "
                   "the act of asking: '10Y VaR and 1994 replay', not 'question "
                   "about VaR'. No quotes, no trailing period, no preamble.",
            messages=[{"role": "user", "content": transcript}],
        )
        title = "".join(b.text for b in response.content if b.type == "text").strip()
        title = title.strip('"“”').rstrip(".").strip()
        return title[:48] or "New chat"

    def _triage(self, query: str, history: list | None) -> dict[str, Any]:
        """Classify with Haiku. Returns the `route` tool's arguments."""
        # Only the last few turns matter for routing, and sending the whole
        # transcript to the cheap model would undo the point of using it.
        recent = [m for m in (history or [])[-4:] if isinstance(m.get("content"), str)]
        messages = recent + [{"role": "user", "content": query}]

        response = self.client.messages.create(
            model=TRIAGE_MODEL,
            max_tokens=TRIAGE_MAX_TOKENS,
            system=TRIAGE_SYSTEM,
            tools=[ROUTE_TOOL],
            tool_choice={"type": "tool", "name": "route"},
            messages=messages,
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "route":
                return dict(block.input or {})
        # tool_choice makes this all but unreachable; if the model somehow
        # returns prose, escalate rather than guess — a missed quant question is
        # a worse failure than an unnecessary Opus turn.
        LOGGER.warning("triage returned no tool call; escalating to the quant agent")
        return {"route": "quant", "reason": "triage produced no routing decision"}

    def handle(self, query: str, history: list | None = None) -> OrchestratorResult:
        trace = [TraceStep("intent", "Received request", query)]
        decision = self._triage(query, history)
        route = decision.get("route", "quant")
        reason = decision.get("reason") or ""
        trace.append(TraceStep("decision", f"Triage → {route}", reason or None))

        if route == "answer":
            reply = (decision.get("reply") or "").strip() or \
                "I answer questions about U.S. Treasury yield curves and the market-risk " \
                "metrics computed from them. Ask me about a rate, a curve, or a portfolio."
            trace.append(TraceStep("answer", f"Answered directly ({TRIAGE_MODEL})", reply))
            messages = list(history or []) + [
                {"role": "user", "content": query},
                {"role": "assistant", "content": reply},
            ]
            return OrchestratorResult(answer=reply, route=route, trace=trace,
                                      messages=messages)

        if route == "clarify":
            question = (decision.get("question") or "").strip() or \
                "Could you say a little more about what you need?"
            options = [
                {"label": str(o.get("label", "")), "value": str(o.get("value", ""))}
                for o in (decision.get("options") or [])
                if o.get("label") and o.get("value")
            ]
            trace.append(TraceStep("clarification", "Asked for a missing detail", question))
            # The question and its answer both stay in history, so the next turn
            # carries the context the user just supplied.
            messages = list(history or []) + [
                {"role": "user", "content": query},
                {"role": "assistant", "content": question},
            ]
            return OrchestratorResult(answer=question, route=route, trace=trace,
                                      elicitation=Elicitation(question, options),
                                      messages=messages)

        # route == "quant"
        result: AgentResult = self.quant.answer(query, history=history)
        trace.extend(result.trace[1:])  # drop its duplicate "Received request"
        elicitation = None
        if result.awaiting_clarification:
            # The quant agent asked something the triage model could not have
            # known to ask — it only surfaced once tools had been consulted.
            #
            # No trace step is added here on purpose: the quant agent already
            # recorded its own "clarification" step, and `trace.extend` above
            # merged it in. Appending another produced the same question twice
            # in the trace panel.
            elicitation = Elicitation(result.answer.strip(), [])
        return OrchestratorResult(answer=result.answer, route=route, trace=trace,
                                  elicitation=elicitation, messages=result.messages)
