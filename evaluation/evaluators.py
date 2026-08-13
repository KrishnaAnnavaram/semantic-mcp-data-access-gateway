"""Scorers. Each one checks a property this system claims to have.

The claims worth testing are not "is the answer good" — a model can be graded on
that anywhere. They are the specific promises this architecture makes:

* the row count comes from the corpus, with a quote that is really in it;
* a field the source does not hold is refused, never filled;
* an expensive path is not entered for a greeting;
* the answer does not assert more than the material supports.

Every evaluator returns a 0/1 score plus a comment saying *why*, because a
failing suite is only useful if it says what broke.
"""

from __future__ import annotations

import re
from typing import Any

# Internal identifiers that must never reach a user as if they were speech.
TOOL_NAMES = {
    "get_yield_curve", "get_rate_history", "get_curve_slope", "list_series",
    "list_portfolios", "get_portfolio", "price_portfolio", "compute_dv01",
    "compute_var", "run_stress", "list_scenarios", "explain_number",
    "retrieve_knowledge", "plan_and_fetch_dataset", "get_latest_rates",
}


def _result(key: str, passed: bool, comment: str) -> dict[str, Any]:
    return {"key": key, "score": 1.0 if passed else 0.0, "comment": comment}


def routing_correct(outcome: dict, expected: dict) -> dict[str, Any]:
    """The orchestrator sent the question down the right path."""
    want, got = expected.get("expect_route"), outcome.get("route")
    return _result("routing_correct", want == got,
                   f"expected {want!r}, got {got!r}")


def cheap_path_stays_cheap(outcome: dict, expected: dict) -> dict[str, Any]:
    """A direct or clarifying turn must not have run a vector search.

    The whole point of a small routing model is that greetings cost almost
    nothing. If retrieval happened anyway, the saving is gone.
    """
    if expected.get("expect_route") not in {"direct", "clarify"}:
        return _result("cheap_path_stays_cheap", True, "not applicable")
    citations = outcome.get("citations") or []
    return _result("cheap_path_stays_cheap", not citations,
                   f"{len(citations)} chunk(s) retrieved on a {outcome.get('route')} turn")


def rows_are_grounded(outcome: dict, expected: dict) -> dict[str, Any]:
    """Where the corpus states a window, the requirement must cite it."""
    if not expected.get("expect_grounded"):
        return _result("rows_are_grounded", True, "not applicable")
    plan = outcome.get("data_plan") or {}
    grounded, quote = plan.get("grounded"), plan.get("row_quote")
    return _result("rows_are_grounded", bool(grounded and quote),
                   f"grounded={grounded}, quote={'yes' if quote else 'none'}")


def no_ungrounded_numbers(outcome: dict, _expected: dict) -> dict[str, Any]:
    """The central invariant: a stated row count must have a citation.

    Applies to every data request, including ones where no window is expected —
    inventing a number is a defect whether or not the corpus happened to have one.
    """
    plan = outcome.get("data_plan") or {}
    if not plan or plan.get("rows") is None:
        return _result("no_ungrounded_numbers", True,
                       "no row count asserted")
    return _result("no_ungrounded_numbers", bool(plan.get("grounded")),
                   f"rows={plan.get('rows')} grounded={plan.get('grounded')}")


def expected_row_count(outcome: dict, expected: dict) -> dict[str, Any]:
    """The window matches what the corpus actually says."""
    want = expected.get("expect_rows")
    if want is None:
        return _result("expected_row_count", True, "not applicable")
    got = (outcome.get("data_plan") or {}).get("rows")
    return _result("expected_row_count", want == got, f"expected {want}, got {got}")


def impossible_fields_refused(outcome: dict, expected: dict) -> dict[str, Any]:
    """A field the source does not hold is named as unavailable, never returned."""
    impossible = expected.get("impossible_fields") or []
    if not impossible:
        return _result("impossible_fields_refused", True, "not applicable")
    plan = outcome.get("data_plan") or {}
    granted = {f.lower() for f in plan.get("fields") or []}
    flagged = {n.get("name", "").lower() for n in plan.get("field_notes") or []
               if n.get("verdict") == "unavailable"}
    leaked = [f for f in impossible if f.lower() in granted]
    unflagged = [f for f in impossible if f.lower() not in flagged]
    passed = not leaked and not unflagged
    return _result("impossible_fields_refused", passed,
                   f"leaked into results: {leaked or 'none'}; "
                   f"not flagged unavailable: {unflagged or 'none'}")


def citations_present(outcome: dict, expected: dict) -> dict[str, Any]:
    """A data request must show which knowledge it reasoned from."""
    if not expected.get("expect_citations"):
        return _result("citations_present", True, "not applicable")
    citations = outcome.get("citations") or outcome.get("sources") or []
    return _result("citations_present", len(citations) > 0,
                   f"{len(citations)} citation(s)")


def no_tool_names_leaked(outcome: dict, _expected: dict) -> dict[str, Any]:
    """Nothing shown to the user may be an internal identifier.

    Observed defect: an elicitation option whose value was `list_portfolios`
    landed in the transcript as if the user had typed it.
    """
    elicitation = outcome.get("elicitation") or {}
    offenders = []
    for option in elicitation.get("options") or []:
        for part in (option.get("label", ""), option.get("value", "")):
            if part.strip() in TOOL_NAMES:
                offenders.append(part.strip())
    answer_hits = [name for name in TOOL_NAMES
                   if re.search(rf"(?<![\w`]){re.escape(name)}(?![\w`])",
                                outcome.get("answer") or "")]
    passed = not offenders and not answer_hits
    return _result("no_tool_names_leaked", passed,
                   f"in options: {offenders or 'none'}; bare in answer: {answer_hits or 'none'}")


def answer_is_brief(outcome: dict, expected: dict) -> dict[str, Any]:
    """A turn that produced a table explains, it does not restate the table."""
    limit = expected.get("max_sentences")
    if not limit:
        return _result("answer_is_brief", True, "not applicable")
    answer = outcome.get("answer") or ""
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer.strip()) if s]
    return _result("answer_is_brief", len(sentences) <= limit,
                   f"{len(sentences)} sentence(s), limit {limit}")


def discussion_converged(outcome: dict, expected: dict) -> dict[str, Any]:
    """The two agents reached agreement rather than running out of rounds."""
    if expected.get("expect_route") != "data_request":
        return _result("discussion_converged", True, "not applicable")
    plan = outcome.get("data_plan") or {}
    if plan and plan.get("answerable") is False:
        # Nothing to negotiate. The domain expert established the task cannot be
        # served from this source, and the pipeline stops before the discussion
        # by design - demanding a transcript here would penalise a correct refusal.
        return _result("discussion_converged", True,
                       "not applicable - task correctly declined as unanswerable")
    negotiation = outcome.get("negotiation") or {}
    if not negotiation:
        return _result("discussion_converged", False, "no discussion recorded")
    return _result("discussion_converged", bool(negotiation.get("converged")),
                   f"{negotiation.get('rounds_used')} round(s), "
                   f"converged={negotiation.get('converged')}")


def clarification_offers_choices(outcome: dict, expected: dict) -> dict[str, Any]:
    """A question the user cannot act on is barely better than a guess."""
    if expected.get("expect_route") != "clarify":
        return _result("clarification_offers_choices", True, "not applicable")
    options = (outcome.get("elicitation") or {}).get("options") or []
    return _result("clarification_offers_choices", len(options) >= 2,
                   f"{len(options)} option(s) offered")


ALL_EVALUATORS = [
    routing_correct,
    cheap_path_stays_cheap,
    rows_are_grounded,
    no_ungrounded_numbers,
    expected_row_count,
    impossible_fields_refused,
    citations_present,
    no_tool_names_leaked,
    answer_is_brief,
    discussion_converged,
    clarification_offers_choices,
]
