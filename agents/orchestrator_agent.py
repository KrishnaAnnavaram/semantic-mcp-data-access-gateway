"""Agent 1 — the orchestrator. Reads the question, decides where it goes.

Runs on a **small, fast model** on purpose. Its job is routing and reflection,
not analysis, and routing is a cheap decision made on every single turn. Sending
"hi" to Opus would cost the same as sending a portfolio stress test to it.

Two responsibilities, at the two ends of a request:

**On the way in — classify.**
    normal question  ─► answer it here and stop
    request for data ─► extract what was asked for, hand to the domain expert

The split matters because the expensive path is expensive: the domain expert
does a vector search and two or three Opus calls. A greeting must never enter it.

**On the way out — reflect.** The orchestrator sees the requirement, the
discussion and the data, and writes the reply. It is the only agent that speaks
to the user, so honesty rules live here: what was returned, what was refused and
why, and whether the number rests on the knowledge base or on nothing.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.contracts import Intent
from agents.observability import structured_call, traced

LOGGER = logging.getLogger("agents.orchestrator")

# Low-cost model: this runs on every turn, including the ones that are just
# "hi". Routing does not need frontier reasoning.
MODEL = "claude-haiku-4-5"

CLASSIFY_SYSTEM = """\
You are the front door of a U.S. Treasury market-risk data gateway. You route \
requests; you do not analyse data.

Decide between three routes:

- "direct" — greetings, small talk, questions about your own capabilities, and \
conceptual questions you can answer in two or three sentences without reading \
any data. Write the reply yourself in `direct_answer`.
- "clarify" — the user wants data, but a detail is missing that would change \
the whole result: which metric, which portfolio, which tenor or date, what \
confidence level or horizon, or which of two readings they meant. Ask ONE \
question in `question` and give 2-4 concrete `options` the user can click. \
Each option needs a `label` (what the user reads) and a `value` (what gets sent \
as their next message - natural language, NEVER an internal tool name).
- "data_request" — anything that needs actual numbers and is specific enough to \
act on: rates, curves, history, tables, extracts, risk metrics, portfolio \
figures. Also choose this when the user names fields, columns or a row count.

The test depends on what is being asked for:

**Asking you to COMPUTE something** needs a target to compute it ON - a \
portfolio, a book, a named scenario. Metric alone is not enough:
  "calculate VaR"                -> on what? -> clarify
  "run a stress test"            -> which scenario, which book? -> clarify
  "compute DV01 on the demo book"-> target named -> data_request

**Asking for DATA** needs only a subject - a metric whose inputs are known, a \
curve, a tenor:
  "data for a 97.5% expected shortfall calculation" -> data_request
  "the data to compute DV01 on the demo book"       -> data_request
  "10 year history", "the nominal curve"            -> data_request

No subject at all -> "clarify":
  "show me the data" / "give me a table" -> of what?
  "I need yields"                        -> nominal or real? which tenor?

Subject named -> "data_request", even if some parameter is still open. \
Downstream a domain expert reads the knowledge base and fills in methodology \
defaults, so you do NOT need confidence levels, horizons or dates:
  "the 2s10s slope today"
  "data for a 97.5% expected shortfall calculation"   (metric named)
  "the data to compute DV01 on the demo book"         (metric + book named)
  "10-day 99% VaR on the book"
  "the nominal curve", "10 year history"

Out-of-scope requests are "data_request", NOT "clarify". If a user asks for CVA, \
counterparty exposure, RWA or PD/LGD/EAD, send it down the data path - the \
domain expert will explain from the knowledge base why it cannot be computed \
here. Asking them to clarify a question you cannot answer either way wastes \
their turn.

Two different doubts, two different defaults:
- Unsure whether it is IN SCOPE -> "data_request". The domain expert declines \
with citations, which is more useful than a question you cannot resolve either.
- Unsure WHAT IT IS ABOUT, or a compute request with no target -> "clarify". \
Fetching the wrong book's numbers is worse than one short question.

So "calculate VaR", "price the book", "run the stress" are ALWAYS clarify: they \
name an action with nothing to perform it on.

But a request that names WHAT DATA it wants is always "data_request", even if \
that data does not exist here - "give me the CUSIP and issuer for every bond in \
the 10-year sector" names its subject precisely. Send it down; the domain expert \
will explain from the corpus why a par yield curve holds no instrument records.

When the route is "data_request":
- `task` = what the data is FOR, in the user's own words (e.g. "10-day 99% \
historical VaR on the book", "2s10s slope today"). This drives everything \
downstream, so keep the user's intent, not your paraphrase of it.
- `requested_fields` = any field/column names they named. Empty list if none.
- `requested_rows` = a row count if they named one, else null.

Be decisive. If in doubt between the two, choose "data_request" — asking the \
data layer costs a little; inventing an answer costs correctness.
"""

CLASSIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": ["direct", "clarify", "data_request"]},
        "reasoning": {"type": "string",
                      "description": "One line on why this route."},
        "task": {"type": "string",
                 "description": "What the data is for. Empty when route is direct."},
        "direct_answer": {"type": "string",
                          "description": "The reply. Empty unless route is direct."},
        "question": {"type": "string",
                     "description": "One clarifying question. Empty unless route is clarify."},
        "options": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "value": {"type": "string",
                              "description": "Natural language sent as the user's "
                                             "next message. Never a tool name."},
                },
                "required": ["label", "value"],
                "additionalProperties": False,
            },
        },
        "requested_fields": {"type": "array", "items": {"type": "string"}},
        "requested_rows": {"type": ["integer", "null"]},
    },
    "required": ["route", "reasoning", "task", "direct_answer", "question",
                 "options", "requested_fields", "requested_rows"],
    "additionalProperties": False,
}

REFLECT_SYSTEM = """\
You are the voice of a market-risk data gateway, writing the final reply.

You are given: the user's question, what a domain expert decided the task needs \
(and the knowledge it cited), the discussion between the domain expert and the \
data layer, and what was actually returned.

Write a SHORT reply — at most three sentences. No headings, no bullet lists, no \
tables. The table and the full reasoning are already on screen in a panel.

Lead with the single most useful fact. Usually that is the row count against \
what the user asked for, or the figure they wanted.

Honesty rules you must not break:
- If fields were unavailable, say they are not published by this source and that \
nothing was substituted. Never imply data exists that does not.
- If the row count could NOT be grounded in the knowledge base, say the corpus \
does not state a window - do not present a number as authoritative.
- Portfolio data is SYNTHETIC_DEMO; market data is real. Keep both labels true.
- If you state a rate, a curve or a risk figure, give its observation date. A \
rate without a date is not an answer - it is a number that was true once.
- Never state a figure that is not in the material you were given.
- Never name an internal tool, function or column identifier (get_curve_slope, \
compute_var, plan_and_fetch_dataset...). The user did not ask which function \
ran. Say "the curve slope", not "get_curve_slope". Real data field names the \
user themselves asked for (cusip, observation_date) are fine.
"""

REFLECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reply": {"type": "string", "description": "At most three sentences."},
    },
    "required": ["reply"],
    "additionalProperties": False,
}


class OrchestratorAgent:
    """Routes the question in, and writes the reply out."""

    def __init__(self, model: str = MODEL) -> None:
        self.model = model

    @traced("orchestrator.classify", run_type="llm")
    def classify(self, question: str, history: list[dict] | None = None,
                 already_clarified: bool = False) -> Intent:
        """Normal question, or a request for data?

        `already_clarified` says the previous turn was itself a clarifying
        question. Asking a second one loops the user: they answer "a named
        scenario on my portfolio" and are asked "which named scenario?", having
        supplied the only detail they had. One question is a good trade; two in
        a row means the first one failed and the answer is to proceed on a
        default and say which was used.
        """
        recent = ""
        if history:
            # Two turns is enough to resolve "and the 30 year?" without paying
            # for the whole transcript on a routing decision.
            tail = history[-4:]
            recent = "\n".join(
                f"{m.get('role')}: {str(m.get('content'))[:300]}" for m in tail)
            recent = f"\nRecent conversation:\n{recent}\n"

        guard = ""
        if already_clarified:
            guard = ("\nIMPORTANT: the previous turn was ALREADY a clarifying "
                     "question and this message is the user's answer to it. You "
                     "must NOT choose 'clarify' again. Route to 'data_request' "
                     "and let the domain expert proceed on a sensible default; "
                     "it will state which default it used.\n")

        payload = structured_call(
            model=self.model, system=CLASSIFY_SYSTEM,
            prompt=f"{recent}{guard}\nUser question:\n{question}",
            schema=CLASSIFY_SCHEMA, max_tokens=1200, effort="low",
        )
        if payload is None:
            # Routing failed. Send it down the data path: the domain expert can
            # still decline, whereas a fabricated direct answer cannot be caught.
            LOGGER.warning("classification failed; defaulting to data_request")
            return Intent(route="data_request",
                          reasoning="Routing model unavailable; defaulted to the "
                                    "data path so nothing is answered from memory.",
                          task=question)

        return Intent(
            route=payload.get("route", "data_request"),  # type: ignore[arg-type]
            reasoning=payload.get("reasoning", ""),
            task=payload.get("task") or question,
            direct_answer=payload.get("direct_answer", ""),
            requested_fields=payload.get("requested_fields") or [],
            requested_rows=payload.get("requested_rows"),
            question=payload.get("question", ""),
            options=[o for o in (payload.get("options") or [])
                     if o.get("label") and o.get("value")],
        )

    @traced("orchestrator.reflect", run_type="llm")
    def reflect(self, question: str, requirement, negotiation, result) -> str:
        """Write the user-facing reply from what the other two agents produced."""
        unavailable = [n.name for n in requirement.field_notes
                       if n.verdict == "unavailable"] if requirement else []
        summary = {
            "question": question,
            "task": requirement.task if requirement else "",
            "rows_returned": result.get("rows_delivered") if result else None,
            "rows_requested_by_user": result.get("rows_requested_by_user") if result else None,
            "row_grounded": requirement.grounded if requirement else False,
            "row_reason": requirement.row_reason if requirement else "",
            "row_quote": requirement.row_quote if requirement else None,
            "fields_returned": requirement.fields if requirement else [],
            "fields_unavailable": unavailable,
            "warnings": (requirement.warnings if requirement else []),
            "discussion_rounds": negotiation.rounds_used if negotiation else 0,
            "discussion_outcome": negotiation.outcome if negotiation else "",
            "calculation": (result or {}).get("calculation"),
            "table_title": ((result or {}).get("table") or {}).get("title"),
        }
        payload = structured_call(
            model=self.model, system=REFLECT_SYSTEM,
            prompt=f"Material to write from (JSON):\n{summary}",
            schema=REFLECT_SCHEMA, max_tokens=1200, effort="low",
        )
        if payload and payload.get("reply"):
            return payload["reply"].strip()
        return self._fallback_reply(requirement, result)

    @staticmethod
    def _fallback_reply(requirement, result) -> str:
        """A truthful sentence when the reflection model is unavailable.

        Assembled from facts already established rather than generated, so a
        model outage degrades the prose, never the accuracy.
        """
        rows = (result or {}).get("rows_delivered", 0)
        asked = (result or {}).get("rows_requested_by_user")
        parts = [f"Returned {rows:,} rows."]
        if asked and asked != rows:
            parts.append(f"You asked for {asked:,}.")
        if requirement and not requirement.grounded:
            parts.append("The knowledge base does not state an observation window "
                         "for this task, so the row count is a sample, not a "
                         "methodology figure.")
        missing = [n.name for n in (requirement.field_notes if requirement else [])
                   if n.verdict == "unavailable"]
        if missing:
            parts.append(f"Not published by this source: {', '.join(missing)}.")
        return " ".join(parts)
