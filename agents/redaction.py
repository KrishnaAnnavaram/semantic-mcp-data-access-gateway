"""Internal identifiers must never reach a user. Enforced, not requested.

Both reasoning agents are shown the tool catalogue — the domain expert to judge
what the source can hold, the MCP agent to choose what to call — so both *can*
copy an identifier into prose, and under some models both do. Observed on
glm-5.2, a scope refusal came back naming seven tools:

    "...I can still run compute_dv01, compute_var, run_stress and
     price_portfolio on the demo book."

Every fact in that sentence is true. It is still the wrong sentence, because
`compute_dv01` is a function in this repository, not a thing a market-risk
analyst asks for.

A prompt cannot guarantee this. The repository already draws the same line for
`awaiting_clarification` — decided structurally rather than inferred from
prose — and this is the same argument: a rule that must always hold belongs in
code, where it can be tested.

**Substitution, not deletion.** Removing the token would leave a hole in a
sentence the model built around it. `compute_dv01` becomes "DV01", so the
sentence still reads and still means what it meant.
"""

from __future__ import annotations

import re

__all__ = ["humanise", "scrub_identifiers"]

# Verb prefixes the tool namespace uses. Stripping one turns an action into the
# noun a person would actually say: `get_rate_history` -> "rate history".
_VERBS = ("get_", "list_", "compute_", "run_", "price_", "search_", "export_",
          "explain_", "brief_")

# Domain shorthand that must not be sentence-cased into nonsense. "Var" reads as
# a variable; "VaR" is value-at-risk.
_ACRONYMS = {
    "var": "VaR", "es": "ES", "dv01": "DV01", "csv": "CSV", "cusip": "CUSIP",
    "mcp": "MCP", "pv": "PV", "id": "ID", "2s10s": "2s10s",
}

# `tool` and `_tool` suffixes are an implementation detail of the risk server.
_SUFFIXES = ("_tool",)

# Where stripping the verb loses the meaning. "run price_portfolio" becoming
# "run portfolio" is grammatical and says nothing; these read as a person would
# say them. Everything not listed falls through to the mechanical rule.
_PHRASES = {
    "price_portfolio": "portfolio valuation",
    "run_stress": "a stress scenario",
    "list_portfolios": "the available portfolios",
    "list_scenarios": "the available scenarios",
    "list_series": "the series catalogue",
    "list_datasets": "the dataset catalogue",
    "explain_number": "provenance for a number",
    "search_series": "a series lookup",
    "get_portfolio": "the portfolio contents",
    "get_scenario": "a scenario definition",
    "brief_dataset_caveat": "a dataset caveat briefing",
    # Not tools — these are the keys of the structures the agents exchange, and
    # a model that has been shown a JSON payload will happily quote its field
    # names back at the user. A real decline read "...and available_calculations
    # is empty", which is both an internal identifier and, as it happens, false.
    "available_calculations": "the calculations this system can run",
    "retrieval_always_available": "the data it can retrieve",
    "unsupported_fields": "the fields it cannot supply",
    "unnecessary_fields": "the fields the tool does not read",
    "available_fields": "the fields it can supply",
    "candidate_fields": "the inputs the method asks for",
    "executable_tools": "the calculations this system can run",
    "temporal_constraints": "the period it covers",
    "curve_family": "the curve",
    "calculation_params": "the calculation's settings",
    "open_questions": "what is still undecided",
    "row_quote": "the quoted window",
    "data_key": "the dataset",
}

#: Field and structure names the agents pass between themselves. Scrubbed from
#: prose alongside tool names: both are this repository's vocabulary rather
#: than a market-risk one, and neither means anything to a reader.
CONTRACT_KEYS: tuple[str, ...] = (
    "available_calculations", "retrieval_always_available", "executable_tools",
    "unsupported_fields", "unnecessary_fields", "available_fields",
    "candidate_fields", "temporal_constraints", "calculation_params",
    "open_questions", "curve_family", "row_quote", "data_key",
    "how_to_read_this", "can_calculate", "max_rows_available",
    "counter_proposal", "answered_questions", "unanswerable_reason",
    "is_hypothesis", "blocked_by",
)


def humanise(name: str) -> str:
    """`compute_key_rate_dv01_tool` -> `key rate DV01`."""
    if name in _PHRASES:
        return _PHRASES[name]
    text = name.strip()
    for suffix in _SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    for verb in _VERBS:
        if text.startswith(verb):
            text = text[len(verb):]
            break
    words = [w for w in text.split("_") if w]
    return " ".join(_ACRONYMS.get(w.lower(), w) for w in words) or name


def scrub_identifiers(text: str | None, names: list[str] | tuple[str, ...]) -> str:
    """Replace bare tool identifiers in user-facing text with readable phrases.

    Only *bare* occurrences are touched. A name already inside backticks is
    deliberate — the decision trace and the data-plan panel quote identifiers on
    purpose, and those are developer surfaces, not prose. This mirrors the
    evaluator's own rule, so the two cannot disagree about what a leak is.

    Longest name first, so `compute_key_rate_dv01_tool` is not half-matched by
    `compute_key_rate_dv01`.
    """
    if not text:
        return text or ""
    for name in sorted(names, key=len, reverse=True):
        if not name:
            continue
        text = re.sub(rf"(?<![\w`]){re.escape(name)}(?![\w`])",
                      humanise(name), text)
    return text
