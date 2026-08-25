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

__all__ = [
    "CONTRACT_KEYS",
    "MCP_IMPLEMENTATION_NAMES",
    "contains_sensitive_data",
    "humanise",
    "redact_sensitive",
    "scrub_identifiers",
]

# Cache and telemetry redaction is separate from user-facing identifier
# scrubbing, but belongs at the same enforced boundary. These names are narrow
# on purpose: `prompt_tokens` is useful runtime telemetry and is not a secret,
# while `access_token` is a credential and must never be persisted.
_SECRET_KEYS = re.compile(
    r"^(?:zai_api_key|anthropic_api_key|redis_password|postgres_password|"
    r"mcp_reader_password|password|api_key|authorization|authorization_header|"
    r"access_token|refresh_token|client_secret|database_url|redis_url)$",
    re.IGNORECASE,
)
_SECRET_TEXT = (
    re.compile(
        r"(?i)\b(zai_api_key|anthropic_api_key|redis_password|postgres_password|"
        r"mcp_reader_password|password|api_key|authorization|access_token|"
        r"refresh_token|client_secret)\b\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"(?i)\b(?:postgres(?:ql)?|redis)://[^\s]+"),
    re.compile(r"\b(?:sk|lsv2)_[A-Za-z0-9_-]{12,}\b"),
)

# Verb prefixes the tool namespace uses. Stripping one turns an action into the
# noun a person would actually say: `get_rate_history` -> "rate history".
_VERBS = ("get_", "list_", "compute_", "run_", "price_", "search_", "export_",
          "explain_", "brief_", "find_", "compare_", "evaluate_", "analyze_",
          "backtest_")

# Domain shorthand that must not be sentence-cased into nonsense. "Var" reads as
# a variable; "VaR" is value-at-risk.
_ACRONYMS = {
    "var": "VaR", "es": "ES", "dv01": "DV01", "csv": "CSV", "cusip": "CUSIP",
    "mcp": "MCP", "pv": "PV", "id": "ID", "2s10s": "2s10s",
    # Added with the expanded capability set. Without these the mechanical rule
    # produces "frtb girr" and "monte carlo risk", which look like typos in an
    # otherwise careful answer.
    "girr": "GIRR", "frtb": "FRTB", "ytm": "YTM", "pnl": "P&L",
    "krd": "KRD", "bp": "bp",
}

# `tool` and `_tool` suffixes are an implementation detail of the risk server.
_SUFFIXES = ("_tool",)

# Where stripping the verb loses the meaning. "run price_portfolio" becoming
# "run portfolio" is grammatical and says nothing; these read as a person would
# say them. Everything not listed falls through to the mechanical rule.
_PHRASES = {
    # Parameters a plan can state. A warning about one of these is written
    # into the reply, so the name a user reads must be the English one.
    "shock_bp": "rate shock",
    "severity_bp": "scenario severity",
    "tenor_months": "curve tenor",
    "pivot_tenor_months": "twist pivot tenor",
    "target_losses": "list of target losses",
    "amber_utilisation_percent": "warning threshold",
    "scenario_count": "simulation count",
    "top_n": "number of entries to rank",
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
    # The expanded capability set. Each maps to how a market-risk analyst would
    # actually say it, not to the function name. The legitimate domain phrase
    # ("Monte Carlo VaR", "reverse stress") must survive - it is the identifier
    # that must not.
    "compute_bond_analytics": "bond analytics",
    "compute_carry_roll": "carry and roll-down",
    "compute_curve_analytics": "curve analytics",
    "compute_rate_volatility": "rate volatility",
    "compute_rate_sensitivities": "rate sensitivities",
    "compute_risk_contributions": "risk contributions",
    "compute_concentration": "risk concentration",
    "run_rate_stress": "a rate stress scenario",
    "run_key_rate_stress": "a key-rate stress",
    "run_shock_ladder": "a shock ladder",
    "run_stress_matrix": "the standard stress pack",
    "compute_stress_contributions": "stress contributions",
    "run_historical_stress": "a historical replay",
    "find_worst_historical_stresses": "the worst historical scenarios",
    "run_reverse_stress": "reverse stress",
    "compute_stress_thresholds": "stress thresholds",
    "find_limit_breach_stress": "the limit-breach stress",
    "compute_parametric_risk": "parametric VaR",
    "compute_monte_carlo_risk": "Monte Carlo VaR",
    "compare_risk_methods": "a comparison of risk methods",
    "backtest_var": "VaR backtesting",
    "compute_pnl_attribution": "P&L attribution",
    "evaluate_risk_limits": "risk limit utilisation",
    "compare_portfolio_risk": "a portfolio comparison",
    "analyze_hypothetical_trade": "hypothetical trade analysis",
    "compute_frtb_girr": "the FRTB GIRR charge",
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
#: The risk server's own tool names. The agents are shown *capability* names
#: (`compute_monte_carlo_risk`), never these, so in normal operation none of
#: them can appear in prose. They are scrubbed anyway: the cost is one regex per
#: name and the alternative is discovering the exception in a user's answer.
#:
#: `humanise` already strips the `_tool` suffix, so `compute_frtb_girr_tool`
#: and `compute_frtb_girr` collapse to the same readable phrase.
MCP_IMPLEMENTATION_NAMES: tuple[str, ...] = (
    "price_portfolio_tool", "compute_dv01_tool", "compute_key_rate_dv01_tool",
    "run_stress_tool", "compute_historical_risk_tool",
    "compute_bond_analytics_tool", "compute_carry_roll_tool",
    "compute_curve_analytics_tool", "compute_rate_volatility_tool",
    "compute_rate_sensitivities_tool", "compute_risk_contributions_tool",
    "run_rate_stress_tool", "run_key_rate_stress_tool",
    "run_curve_twist_stress_tool", "run_curve_curvature_stress_tool",
    "run_shock_ladder_tool", "run_stress_matrix_tool",
    "compare_stress_scenarios_tool", "compute_stress_contributions_tool",
    "explain_stress_loss_tool", "compute_stress_thresholds_tool",
    "run_concentration_stress_tool", "run_scenario_severity_pack_tool",
    "run_historical_stress_tool", "run_historical_crisis_stress_tool",
    "find_worst_historical_stresses_tool", "run_reverse_stress_tool",
    "find_limit_breach_stress_tool", "compute_parametric_risk_tool",
    "compute_monte_carlo_risk_tool", "run_extreme_tail_simulation_tool",
    "run_volatility_regime_stress_tool", "run_rate_correlation_stress_tool",
    "compare_risk_methods_tool", "backtest_var_tool",
    "compute_pnl_attribution_tool", "compute_concentration_tool",
    "evaluate_risk_limits_tool", "compare_portfolio_risk_tool",
    "analyze_hypothetical_trade_tool", "analyze_rate_hedge_tool",
    "compute_frtb_girr_tool",
    # Data-server tools that appear in workflow plumbing.
    "get_curve_history_matrix", "get_curve", "get_rate_history",
)

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
    """`compute_key_rate_dv01_tool` -> `key rate DV01`.

    The `_tool` suffix is stripped *before* the phrase lookup, so the engine's
    implementation name and the agent-facing capability name collapse to the
    same readable phrase. Without that, `compute_monte_carlo_risk` reads as
    "Monte Carlo VaR" while `compute_monte_carlo_risk_tool` falls through to the
    mechanical rule and reads as "monte carlo risk" - two spellings of the same
    thing, one of which looks like a typo.
    """
    text = name.strip()
    for suffix in _SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    if text in _PHRASES:
        return _PHRASES[text]
    if name in _PHRASES:
        return _PHRASES[name]
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


def contains_sensitive_data(value: object) -> bool:
    """Whether persisting `value` would risk storing a credential."""
    if isinstance(value, dict):
        return any(_SECRET_KEYS.match(str(key)) or contains_sensitive_data(item)
                   for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(contains_sensitive_data(item) for item in value)
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in _SECRET_TEXT)
    return False


def redact_sensitive(value: object) -> object:
    """Recursively redact credentials before any cache/log write.

    The shape is preserved so structured telemetry stays useful. Secret-bearing
    keys remain present with a redacted value, which also makes a test able to
    prove redaction happened instead of silently dropping evidence of the field.
    """
    if isinstance(value, dict):
        return {
            str(key): ("[REDACTED]" if _SECRET_KEYS.match(str(key))
                       else redact_sensitive(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact_sensitive(item) for item in value]
    if not isinstance(value, str):
        return value
    text = value
    # Remove a complete bearer credential before the generic key=value rule;
    # otherwise that rule consumes only the word "Bearer" and leaves its token.
    text = _SECRET_TEXT[1].sub("Bearer [REDACTED]", text)
    text = _SECRET_TEXT[0].sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _SECRET_TEXT[2].sub("[REDACTED_CONNECTION_URL]", text)
    text = _SECRET_TEXT[3].sub("[REDACTED_TOKEN]", text)
    return text
