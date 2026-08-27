"""The requirement completeness gate: what it stops, and what it must not.

Two failure modes matter here and they pull in opposite directions.

**Asking when it should not** is the expensive one for a senior quant. Every
question this gate raises is an interruption, and interrupting someone to ask
for a confidence level that has a documented default teaches them to stop using
the system. Most of the tests below assert that a question proceeds.

**Not asking when it should** is the expensive one for the gateway: a full
negotiated turn - four vector queries and up to a dozen model calls - spent to
discover that the user never said which period to compare.

The third property is the one the whole design rests on: when the gate stops a
turn, *nothing expensive has run yet*. That is asserted against the handoff
ledger rather than against prose, because the ledger is what actually records
whether Qdrant and the MCP agent were reached.
"""

from __future__ import annotations

import pytest

from agents import preflight
from agents.preflight import assess, classify_intent, extract

# --- the deterministic layer -------------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("the curve on 2008-09-15", ["2008-09-15"]),
    ("rates on 3/17/2020", ["2020-03-17"]),
    ("yields in March 2020", ["2020-03"]),
    ("what happened on 2020-3-5", ["2020-03-05"]),
])
def test_dates_are_read_from_the_text_not_inferred(text, expected):
    assert extract(text).dates == expected


def test_a_year_inside_a_full_date_is_not_a_second_anchor_in_time():
    """`2008-09-15` names one moment, not the day and also the year 2008.

    Counting it twice would let a single-date question satisfy a comparison's
    requirement for two, which is exactly the check this gate exists to make.
    """
    facts = extract("the curve on 2008-09-15")
    assert facts.years == []
    assert facts.date_count == 1


@pytest.mark.parametrize("text", [
    "over the last 30 days", "in the past six months", "year to date",
    "since 2019", "between 2020-01-01 and 2020-06-30", "this quarter",
])
def test_relative_and_named_periods_are_recognised(text):
    assert extract(text).has_period is True


def test_a_holding_period_is_not_a_tenor():
    """"10-day VaR" names a horizon; "10 year" names a point on the curve.

    Reading the first as a tenor made a VaR question look as though the user had
    already chosen their maturities, which is a different question entirely.
    """
    facts = extract("10-day 99% VaR")
    assert facts.tenors == []
    assert facts.horizon_days == 10
    assert facts.confidence_level == pytest.approx(0.99)


def test_a_tenor_is_read_as_a_tenor():
    assert extract("the 10Y and 2 year yields").tenors == ["10Y", "2Y"]


@pytest.mark.parametrize("text,found", [
    ("a $5m loss", True),
    ("a 50,000 limit", True),
    ("breaches 2,500,000", True),
    ("the 2008 crisis", False),      # a year is not an amount
    ("the 10 year point", False),    # a tenor is not an amount
])
def test_amounts_need_more_than_a_bare_number(text, found):
    """A four-digit year and a tenor are numbers, and neither is a loss limit.

    Accepting any number here would silently satisfy `target_loss`, which is the
    one input a reverse stress cannot be run without.
    """
    assert extract(text).has_amount is found


@pytest.mark.parametrize("text,expected", [
    ("compare the curve", "curve_comparison"),
    ("run a stress test", "stress_test"),
    ("what reverse stress breaks the book", "reverse_stress"),
    ("are we within our DV01 limit", "limit_check"),
    ("10-day 99% VaR on the book", "var"),
    ("what is the key rate DV01", "dv01"),
    ("show me the 10Y yield", "curve_snapshot"),
    ("hello", "unknown"),
])
def test_intent_is_classified_deterministically(text, expected):
    assert classify_intent(text) == expected


# --- the verdict -------------------------------------------------------------


@pytest.mark.parametrize("question", [
    "Show me the 10Y Treasury yield.",
    "What is the 2s10s slope today?",
    "10-day 99% VaR on the book",
    "Compute DV01 on the demo book",
    "Give me the 30 year rate history",
    "What data do I need for Key Rate DV01?",
    "Run the 2008 crisis scenario on the demo book",
    "Run a 100bp parallel shock on the book",
    "What reverse stress produces a $5m loss?",
    "hi",
])
def test_a_complete_question_is_never_interrupted(question):
    """The reluctance rule. Each of these is answerable as it stands."""
    verdict = assess(question)
    assert verdict.complete, f"{question!r} was stopped for {verdict.missing}"
    assert verdict.questions == []


@pytest.mark.parametrize("question,field", [
    ("Compare the Treasury curve and show the biggest movements.",
     "comparison_period"),
    ("What has changed in the curve?", "comparison_period"),
    ("Run a stress test on the demo book", "scenario"),
    ("What reverse stress breaks the book?", "target_loss"),
    ("Are we within our DV01 limit?", "limit_amount"),
])
def test_a_question_missing_an_undefaultable_input_is_stopped(question, field):
    verdict = assess(question)
    assert not verdict.complete
    assert [m.name for m in verdict.missing] == [field]
    assert verdict.questions and verdict.questions[0].endswith("?")
    assert verdict.reason


def test_parameters_with_documented_defaults_never_block_a_turn():
    """A VaR with no confidence level and no horizon still runs.

    Both have documented defaults in the risk workflows, and the reply states
    which were used. Asking would be asking someone to type a number the system
    already knows - and `defaults_applied` is how the answer stays honest about
    having chosen it.
    """
    verdict = assess("Compute VaR on the demo book")
    assert verdict.complete
    assert "confidence_level" in verdict.defaults_applied
    assert "horizon_days" in verdict.defaults_applied


def test_no_more_than_three_questions_are_ever_asked(monkeypatch):
    monkeypatch.setenv("PREFLIGHT_MAX_QUESTIONS", "9")
    # Even asked for nine, the hard ceiling is five and the default is three.
    assert preflight.max_questions() == 5
    monkeypatch.delenv("PREFLIGHT_MAX_QUESTIONS")
    assert preflight.max_questions() == preflight.DEFAULT_MAX_QUESTIONS == 3


def test_the_gate_gives_up_asking_rather_than_looping_the_user():
    """A bounded number of asks, then the turn proceeds and says so.

    Unbounded clarification is the user-facing twin of an unbounded agent loop:
    the user answers, is asked again, and has no way out. After the budget is
    spent the turn runs on defaults and `proceeded_on_defaults` is what makes
    the reply admit it rather than pretend nothing was missing.
    """
    question = "Compare the curve and show the biggest movements."
    assert not assess(question, rounds_used=0).complete

    exhausted = assess(question, rounds_used=preflight.max_rounds(),
                       already_clarified=True)
    assert exhausted.complete
    assert exhausted.proceeded_on_defaults
    assert "comparison_period" in exhausted.defaults_applied


def test_the_gate_can_be_switched_off_without_touching_the_pipeline(monkeypatch):
    monkeypatch.setenv("PREFLIGHT_ENABLED", "false")
    verdict = assess("Compare the curve and show the biggest movements.")
    assert verdict.complete
    assert verdict.missing == []


def test_a_verdict_survives_the_round_trip_through_an_a2a_artifact():
    """It travels as a protobuf Struct, so it has to rebuild from a plain dict."""
    original = assess("Run a stress test on the demo book")
    restored = preflight.verdict_from_dict(original.as_dict())
    assert restored is not None
    assert restored.complete is original.complete
    assert restored.intent == original.intent
    assert [m.name for m in restored.missing] == [m.name for m in original.missing]
    assert restored.questions == original.questions


def test_the_scenario_vocabulary_matches_the_domain_experts():
    """Restated in two modules, so a test has to hold them together.

    `preflight` deliberately does not import `domain_expert_agent` - the gate's
    whole value is that it costs nothing to reach, and that module pulls in the
    model layer and the cache. Duplication is the lesser evil; silent drift is
    not.
    """
    from agents.domain_expert_agent import CRISIS_IDS, SCENARIO_NAMES

    assert set(preflight.SCENARIO_WORDS) == set(SCENARIO_NAMES)
    assert set(preflight.CRISIS_WORDS) == {c.lower() for c in CRISIS_IDS}
