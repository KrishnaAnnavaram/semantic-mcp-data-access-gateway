"""Telling a question apart from an answer that ends by offering a next step.

Both end with '?'. Only one of them means the agent is stuck. Getting this wrong
is not cosmetic: `awaiting_clarification` travels out over `/chat`, and the UI
draws a "pick one" prompt underneath whatever it is told is a pending question.

The cases below are the real ones observed against the running service, kept
verbatim so a future change has to confront the actual text rather than a
tidied-up paraphrase.
"""

from __future__ import annotations

import pytest

from backend.agent.quant_agent import is_clarification

# Observed: a genuine clarification. The whole turn is the question.
GENUINE = ("Would you like to stress test with a historical replay (past market "
           "moves) or a hypothetical scenario (you define the shifts)?")

# Observed: a complete 2,302-character DV01 answer whose last line offers a next
# step. Before the fix this was classified as a pending clarification purely
# because of the final character.
ANSWER_THEN_OFFER = """## DV01 in one line

**DV01 is the change in value for a 1 basis-point parallel move in rates.**

| Method | How |
|---|---|
| Analytic | Modified Duration x PV x 0.0001 |
| Full revaluation | Reprice on a bumped curve |

Want me to run DV01 on the demo book - with the key-rate breakdown?"""

# Observed: the same intent as above, phrased without a question mark. This one
# was always classified correctly, which is what made the bug visible.
ANSWER_THEN_STATEMENT = (
    "Next steps on this book: `compute_dv01` (with key-rate breakdown at "
    "2/5/10/20/30Y), historical-simulation VaR/ES, or a parallel-shift stress. "
    "Say which and I'll run it."
)


def test_a_bare_question_is_a_clarification():
    assert is_clarification(GENUINE) is True


def test_a_complete_answer_that_ends_by_offering_a_next_step_is_not():
    """The regression. Structure and length both say this answered something."""
    assert is_clarification(ANSWER_THEN_OFFER) is False


def test_the_same_offer_without_a_question_mark_is_also_not():
    assert is_clarification(ANSWER_THEN_STATEMENT) is False


def test_the_two_phrasings_of_one_intent_agree():
    """The bug in one line: identical meaning must not classify differently."""
    assert is_clarification(ANSWER_THEN_OFFER) is is_clarification(ANSWER_THEN_STATEMENT)


def test_text_not_ending_in_a_question_is_never_a_clarification():
    assert is_clarification("The 2s10s slope is +48.0 bp as of 2026-08-11.") is False


def test_trailing_whitespace_does_not_change_the_verdict():
    assert is_clarification(GENUINE + "   \n") is True


@pytest.mark.parametrize("marker", ["\n# Heading", "\n| a | b |", "\n- bullet",
                                    "\n1. first", "\n```code```"])
def test_markdown_structure_marks_a_turn_as_having_delivered_content(marker):
    """A question does not need a table, a heading or a code block."""
    assert is_clarification(f"Here is what I found.{marker}\n\nShall I continue?") is False


def test_a_long_unstructured_question_is_still_not_a_clarification():
    """Length alone is enough: a clarification is the agent saying it is stuck."""
    padded = "word " * 120 + "which tenor did you mean?"
    assert len(padded) > 400
    assert is_clarification(padded) is False


@pytest.mark.parametrize("empty", ["", "   ", None])
def test_empty_input_is_handled(empty):
    assert is_clarification(empty) is False
