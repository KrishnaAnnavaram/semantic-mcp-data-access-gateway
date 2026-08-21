"""Orchestrator-mediated elicitation: the specialist asks, the orchestrator speaks.

MCP's elicitation exists because some choices cannot be made by a server. The
query `'30 year'` matches `BC_30YEAR` and `TC_30YEAR` — a nominal par yield and
a real yield, different quantities that must never share a curve — and no amount
of server-side cleverness picks correctly, because the information needed is in
the caller's head.

What changed is *who that caller is*. Previously the MCP host answered the
question itself: declining when headless, or prompting on the terminal when a
human happened to be sitting at one. Both bypass the orchestrator, and the
terminal prompt is a second channel to the user that the system cannot see.

Now the question travels as an A2A task state instead:

    MCP data server ── elicitation ──► MCP host ── relay ──► MCP AGENT
                                                                │
                                          A2A task: input-required
                                                                ▼
                                                        ORCHESTRATOR
                                                                │
                                              /chat: question + options
                                                                ▼
                                                              USER

and the answer travels back down the same path, into the *same* A2A task.

This module owns only the translation between the two vocabularies: the record
the MCP layer produces, the A2A-facing payload, and the deterministic matching
of a user's reply back onto the field the server asked about. Matching is
deliberately not a model call — the allowed answers are an enum the server
supplied, and asking a model to choose from a list it was given is a way to
occasionally get something that is not on the list.
"""

from __future__ import annotations

import os
import re
from typing import Any

#: Marks a data part as the question rather than a result. `read_task` looks for
#: it on a task's status message.
INPUT_REQUEST_KIND = "input_request"

#: How many times a question may be *re-asked* after the first attempt. Three
#: chances in total, which is enough for a typo and a misread and still bounded.
#: A question that cannot be answered in three tries is not going to be, and an
#: unbounded clarification loop is the same defect as an unbounded agent loop —
#: it just wears the user down instead of the budget.
DEFAULT_MAX_CLARIFICATION_RETRIES = 3

#: Words that end the exchange rather than answer it. Deliberately a short,
#: explicit list: a user who says "cancel" means cancel, and a user who says
#: something the list does not contain has *not* cancelled — inferring refusal
#: from vagueness would terminate exactly the conversations the retry exists for.
_REFUSALS = (
    "cancel", "cancelled", "canceled", "stop", "abort", "quit", "exit",
    "never mind", "nevermind", "forget it", "drop it", "leave it",
    "no thanks", "no thank you", "not now",
)


def max_clarification_retries() -> int:
    """How many re-asks are allowed, from configuration."""
    try:
        value = int(os.environ.get("A2A_MAX_CLARIFICATIONS", "").strip()
                    or DEFAULT_MAX_CLARIFICATION_RETRIES)
    except ValueError:
        return DEFAULT_MAX_CLARIFICATION_RETRIES
    return value if value >= 0 else DEFAULT_MAX_CLARIFICATION_RETRIES


def is_refusal(text: str) -> bool:
    """Did the user end the exchange rather than answer it?

    Checked *before* the answer is matched, because "cancel" is not a nominal
    curve and should not be run through an enum matcher. Matched on word
    boundaries so a real answer containing one of these as a substring is not
    read as a refusal.
    """
    haystack = (text or "").strip().lower()
    if not haystack:
        return False
    return any(re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", haystack)
               for word in _REFUSALS)


def input_request_payload(pending: dict[str, Any]) -> dict[str, Any]:
    """The MCP layer's pending-input record, in A2A-facing form.

    `pending` is what `mcp_servers.host.interaction.ElicitationRelay` records:
    the tool that asked, the server's own wording, and the schema of the answer
    it wants. Nothing is invented here — the question the user eventually sees
    is written by the orchestrator from these facts.
    """
    schema = pending.get("schema") or {}
    properties = schema.get("properties") or {}
    fields = list(pending.get("fields") or properties.keys())
    choices: list[dict[str, str]] = []
    for name in fields:
        spec = properties.get(name) or {}
        for option in spec.get("enum") or []:
            choices.append({"field": name, "value": str(option),
                            "description": str(spec.get("description") or "")})
    return {
        "kind": INPUT_REQUEST_KIND,
        "source": "mcp",
        "tool": pending.get("tool") or "",
        "question": pending.get("message") or "",
        "required_information": fields,
        "schema": schema,
        "choices": choices,
        # Zero on the first ask; incremented each time the question is put again
        # because the previous reply did not answer it.
        "attempt": 0,
        "retries_remaining": max_clarification_retries(),
    }


def retry_payload(payload: dict[str, Any], unmatched_reply: str) -> dict[str, Any]:
    """The same question, put again, carrying why it is being put again.

    A re-ask that repeats the original wording verbatim reads like the system
    did not hear the user. Recording the reply that failed to match lets the
    orchestrator say what it needs *and* acknowledge what it got — without
    inventing anything, since both halves are facts.
    """
    attempt = int(payload.get("attempt") or 0) + 1
    retried = dict(payload)
    retried["attempt"] = attempt
    retried["retries_remaining"] = max(0, max_clarification_retries() - attempt)
    retried["unmatched_reply"] = (unmatched_reply or "").strip()[:200]
    return retried


def question_for_user(payload: dict[str, Any]) -> str:
    """The question the orchestrator puts to the user, first time or re-asked."""
    question = payload.get("question") or (
        "The data layer needs a decision it cannot make.")
    attempt = int(payload.get("attempt") or 0)
    if attempt <= 0:
        return question

    allowed = [c.get("value", "") for c in payload.get("choices") or []]
    fields = ", ".join(payload.get("required_information") or []) or "that detail"
    reply = payload.get("unmatched_reply") or ""
    said = f' You said "{reply}", which does not settle it.' if reply else ""
    choices = f" Please answer with one of: {', '.join(allowed)}." if allowed else ""
    return (f"I still need {fields} before I can continue.{said}{choices}")


def user_options(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Clickable options whose text carries the exact token the server needs.

    The frontend sends an option's `value` as the user's next message, so the
    token has to survive the round trip through free text. Embedding it in a
    sentence keeps the message natural without making the answer a guess.
    """
    options: list[dict[str, str]] = []
    for choice in payload.get("choices") or []:
        value = choice.get("value") or ""
        if not value:
            continue
        options.append({"label": value,
                        "value": f"Use the {value} series for this."})
    return options[:4]


def match_answer(text: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Map what the user said onto the fields the server asked about.

    Returns `None` when a required field cannot be filled. That is the honest
    outcome: the elicitation exists precisely because guessing is the error, so
    an unmatched reply is relayed back as a decline rather than as a plausible
    choice.
    """
    schema = payload.get("schema") or {}
    properties = schema.get("properties") or {}
    fields = list(payload.get("required_information") or properties.keys())
    if not fields:
        return None

    answer: dict[str, Any] = {}
    haystack = (text or "").strip()
    for name in fields:
        spec = properties.get(name) or {}
        allowed = [str(o) for o in spec.get("enum") or []]
        if allowed:
            hit = _first_token(haystack, allowed)
            if hit is None:
                return None
            answer[name] = hit
        elif haystack:
            answer[name] = haystack
        else:
            return None
    return answer


#: Fields whose value changes the *analysis*, not merely which rows are read.
#: A curve family decides whether a figure is a nominal or a real yield — two
#: different quantities that must never share a curve. A confidence level or a
#: horizon defines what a VaR number even means. Answering one of these is not
#: filling in a blank; it is changing the question, and the plan that was agreed
#: for the old question no longer describes the new one.
DOMAIN_MATERIAL_FIELDS = frozenset({
    "rate_kind", "curve_family", "confidence_level", "horizon_days",
    "trading_days", "lookback_days", "method", "methodology",
})


def is_domain_material(answers: dict[str, Any] | None,
                       payload: dict[str, Any] | None = None,
                       has_methodology: bool = False) -> bool:
    """Does this answer change the analysis, or only which rows are read?

    Two conditions, and both are needed.

    The field must be one whose value defines the quantity — a curve family, a
    confidence level, a horizon. And there must be **a methodology for it to be
    material to**: an agreed calculation whose inputs it feeds.

    Without the second condition this fires far too widely. "Show me the 30-year
    history" followed by "the real one" is a *row selection*: no method was
    agreed, nothing is invalidated, and sending the domain expert away to
    re-derive a plan would be ceremony that costs a model call and loses the
    task the user is waiting on. The same answer given while a VaR is being
    planned changes what the VaR measures, and continuing on the nominal plan
    would produce a correct number answering a question nobody asked.

    Deliberately a field-name test rather than a model call: the fields are a
    short, closed set the servers themselves declare, and asking a model whether
    something is material would introduce judgement where a lookup suffices.
    """
    if not has_methodology:
        return False
    names = set(answers or {})
    if payload:
        names |= set(payload.get("required_information") or [])
    return bool(names & DOMAIN_MATERIAL_FIELDS)


def _first_token(text: str, allowed: list[str]) -> str | None:
    """The single allowed value the text names, or None if it names none or two.

    Longest first, so 'real yield' does not match a shorter option that happens
    to be a prefix. Two different allowed values in one reply is an ambiguous
    answer to a question asked to remove ambiguity, so it is refused.
    """
    found = [value for value in sorted(allowed, key=len, reverse=True)
             if re.search(rf"(?<![\w-]){re.escape(value)}(?![\w-])", text,
                          flags=re.IGNORECASE)]
    return found[0] if len(found) == 1 else None
