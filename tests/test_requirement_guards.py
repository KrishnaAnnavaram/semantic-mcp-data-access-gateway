"""The guards that decide whether a request is servable at all.

The domain expert says what a task needs; these are the rules that stop its
answer being self-contradictory. They are here rather than in the prompt because
a prompt is a request and this is a guarantee — and because the failure they
prevent was real, observed, and silent from the user's side: a request for six
fields of which three exist was declined in full, and the user got nothing.
"""

from __future__ import annotations

import pytest

from agents.contracts import KnowledgeChunk, ToolCatalogue, ToolSpec
from agents.domain_expert_agent import DomainExpertAgent

CHUNK = KnowledgeChunk(
    "market_risk", "var.md", "Observation window",
    "Historical simulation reads a fixed lookback window of 250 trading days.",
    0.1)

CATALOGUE = ToolCatalogue(
    tools=[ToolSpec("get_rate_history", "history", "data", executable=False),
           ToolSpec("compute_var", "VaR and ES", "risk", executable=True)],
    fields=["observation_date", "rate_percent", "quote_basis", "tenor",
            "rate_kind", "data_key", "series_code"],
    tenors=["y2", "y10", "y30"], can_calculate=True)


@pytest.fixture
def expert():
    return DomainExpertAgent(knowledge=None)


def payload(**overrides):
    """What the model returned for the six-field VaR request, verbatim in shape."""
    base = {
        "task_understood": "10-day 99% historical VaR on the book",
        "answerable": False,
        "unanswerable_reason": ("The request needs instrument-level identifiers "
                                "(cusip, issuer_name, settlement_date) that a "
                                "Treasury par yield curve does not contain."),
        "fields": ["observation_date", "rate_percent", "quote_basis"],
        "field_notes": [
            {"name": "cusip", "verdict": "unavailable", "reason": "not published"},
            {"name": "issuer_name", "verdict": "unavailable", "reason": "not published"},
            {"name": "settlement_date", "verdict": "unavailable", "reason": "not published"},
        ],
        "rows": 250,
        "row_quote": "Historical simulation reads a fixed lookback window of 250 trading days.",
        "row_reason": "The corpus states the window.",
        "tenors": ["y2", "y10"],
        "calculation": "compute_var",
        "curve_family": "nominal",
        "calculation_params": {"confidence_level": 0.99, "horizon_days": 10},
    }
    base.update(overrides)
    return base


# --- the reported defect ----------------------------------------------------


def test_a_partially_servable_request_is_not_declined(expert):
    """The pasted query: three fields exist, three do not, the VaR is computable."""
    requirement = expert._build(
        payload(), [CHUNK], CATALOGUE, requested_rows=10_000,
        requested_fields=["observation_date", "rate_percent", "quote_basis",
                          "cusip", "issuer_name", "settlement_date"])

    assert requirement.answerable is True, "a servable request was declined in full"
    assert requirement.unanswerable_reason is None
    # What exists is served...
    assert requirement.fields == ["observation_date", "rate_percent", "quote_basis"]
    assert requirement.rows == 250
    assert requirement.calculation == "compute_var"
    # ...and what does not is named, not substituted.
    unavailable = {n.name for n in requirement.field_notes if n.verdict == "unavailable"}
    assert unavailable == {"cusip", "issuer_name", "settlement_date"}
    # The correction is on the record, not silent.
    override = [w for w in requirement.warnings if "declared this task unanswerable" in w]
    assert override, requirement.warnings
    assert "cusip" in override[0]


def test_a_genuinely_out_of_scope_task_is_still_declined(expert):
    """CVA needs counterparty data. Nothing here can serve it, and it stays declined."""
    requirement = expert._build(
        payload(answerable=False, calculation=None, fields=[], field_notes=[],
                unanswerable_reason="CVA needs counterparty exposure data."),
        [CHUNK], CATALOGUE, requested_rows=None, requested_fields=[])

    assert requirement.answerable is False
    assert "counterparty" in requirement.unanswerable_reason
    assert not any("declared this task unanswerable" in w for w in requirement.warnings)


def test_a_request_for_only_missing_fields_is_still_declined(expert):
    """'Give me the CUSIP and issuer for every bond' names nothing this source has."""
    requirement = expert._build(
        payload(answerable=False, calculation=None,
                unanswerable_reason="A par yield curve holds no instrument records."),
        [CHUNK], CATALOGUE, requested_rows=None,
        requested_fields=["cusip", "issuer_name"])

    assert requirement.answerable is False
    assert "instrument records" in requirement.unanswerable_reason


def test_a_servable_calculation_alone_overturns_a_refusal(expert):
    """Even with no recognisable field names, a computable metric is servable."""
    requirement = expert._build(
        payload(answerable=False), [CHUNK], CATALOGUE,
        requested_rows=None, requested_fields=[])

    assert requirement.answerable is True
    assert any("the calculation it needs" in w for w in requirement.warnings)


def test_an_answerable_verdict_is_never_second_guessed(expert):
    """The guard only ever overturns a refusal; it does not manufacture one."""
    requirement = expert._build(
        payload(answerable=True, unanswerable_reason=None), [CHUNK], CATALOGUE,
        requested_rows=None, requested_fields=["cusip"])

    assert requirement.answerable is True
    assert not any("declared this task unanswerable" in w for w in requirement.warnings)


# --- which curve --------------------------------------------------------------


def test_the_curve_family_travels_with_the_tenors(expert):
    for family in ("nominal", "real", "ambiguous"):
        built = expert._build(payload(curve_family=family), [CHUNK], CATALOGUE,
                              None, [])
        assert built.curve_family == family
        assert built.as_dict()["curve_family"] == family


def test_an_unreadable_curve_family_falls_back_to_nominal(expert):
    """The standard Treasury par curve, and what every earlier version served."""
    for bad in ("", None, "tips", "NOMINAL "):
        built = expert._build(payload(curve_family=bad), [CHUNK], CATALOGUE, None, [])
        assert built.curve_family == "nominal"


# --- calculation parameters ---------------------------------------------------


def test_stated_parameters_reach_the_requirement(expert):
    """A 10-day 99% VaR must be computed at 10 days, not merely called one."""
    built = expert._build(payload(), [CHUNK], CATALOGUE, None, [])
    assert built.calculation_params == {"confidence_level": 0.99, "horizon_days": 10}
    assert built.as_dict()["calculation_params"]["horizon_days"] == 10


def test_unstated_parameters_leave_the_data_layers_default_alone(expert):
    built = expert._build(
        payload(calculation_params={"confidence_level": None, "horizon_days": None}),
        [CHUNK], CATALOGUE, None, [])
    assert built.calculation_params == {}


@pytest.mark.parametrize("bad,keep", [
    ({"confidence_level": 99, "horizon_days": 10}, {"horizon_days": 10}),
    ({"confidence_level": 0.99, "horizon_days": 0}, {"confidence_level": 0.99}),
    ({"confidence_level": 0.99, "horizon_days": 5000}, {"confidence_level": 0.99}),
    ({"confidence_level": 1.0, "horizon_days": 2}, {"horizon_days": 2}),
])
def test_a_parameter_outside_its_range_is_dropped_not_clamped(expert, bad, keep):
    """99 meaning 99% rewritten to 0.99 would be a guess about the defining number."""
    built = expert._build(payload(calculation_params=bad), [CHUNK], CATALOGUE, None, [])
    assert built.calculation_params == keep
    assert any("dropped" in w for w in built.warnings), built.warnings
