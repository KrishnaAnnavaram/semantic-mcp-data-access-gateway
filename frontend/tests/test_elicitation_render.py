"""The elicitation widget must add a next step, not repeat the question.

The backend puts the same sentence in `answer` and in `elicitation.question`,
and the transcript already shows `answer`. Before this rule the UI drew both,
so a clarifying question appeared twice in a row — once as a statement, once as
a question — which reads as the agent repeating itself.
"""

from __future__ import annotations

from app import question_needs_repeating

QUESTION = ("Would you like to stress test with a historical replay (past market "
            "moves) or a hypothetical scenario (you define the shifts)?")


def test_question_already_in_the_transcript_is_not_repeated():
    """The real case: backend echoes the same text into both fields."""
    messages = [
        {"role": "user", "content": "i want to perform stress testing"},
        {"role": "assistant", "content": QUESTION},
    ]
    assert question_needs_repeating(QUESTION, messages) is False


def test_surrounding_whitespace_does_not_defeat_the_match():
    messages = [{"role": "assistant", "content": f"  {QUESTION}  "}]
    assert question_needs_repeating(QUESTION, messages) is False


def test_a_genuinely_different_question_is_still_shown():
    """Not 'never draw it' — only 'do not draw it twice'.

    A backend that sends a question the transcript does not contain is carrying
    information the user would otherwise never see.
    """
    messages = [{"role": "assistant", "content": "Here is the curve for 2026-08-11."}]
    assert question_needs_repeating(QUESTION, messages) is True


def test_the_comparison_uses_the_last_assistant_turn_not_the_last_message():
    """A trailing user turn must not hide an already-shown question."""
    messages = [
        {"role": "assistant", "content": QUESTION},
        {"role": "user", "content": "hmm"},
    ]
    assert question_needs_repeating(QUESTION, messages) is False


def test_an_empty_question_is_never_drawn():
    assert question_needs_repeating("", [{"role": "assistant", "content": "x"}]) is False


def test_an_empty_transcript_still_shows_the_question():
    """First turn of a fresh chat: nothing has been shown, so show it."""
    assert question_needs_repeating(QUESTION, []) is True
