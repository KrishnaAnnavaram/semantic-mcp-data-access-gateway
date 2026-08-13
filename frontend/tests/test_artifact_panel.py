"""The artifact card and panel: what the user sees before they click.

The table never enters the transcript — a card stands for it. That card is the
only thing the user has to decide on, so its summary has to carry the shape and
the surprise without them opening anything.
"""

from __future__ import annotations

from app import artifact_summary

TABLE = {
    "title": "Par yields — y2, y10",
    "columns": ["observation_date", "y2", "y10", "quote_basis"],
    "rows": [["2026-08-11", 4.22, 4.70, "par_coupon_semiannual"]],
    "row_count": 250,
    "displayed": 250,
    "truncated": False,
}

# The domain expert's Requirement, as `/chat` serialises it. Key names matter:
# the panel once read the *old* planner's names (granted_rows, field_decisions,
# sources) and silently rendered an empty tab against this payload.
PLAN = {
    "rows": 250,
    "grounded": True,
    "row_quote": "Historical simulation reads a fixed lookback window of 250 trading days.",
    "fields": ["observation_date", "rate_percent", "quote_basis", "tenor"],
    "field_notes": [
        {"name": "observation_date", "verdict": "required", "reason": "..."},
        {"name": "cusip", "verdict": "unavailable", "reason": "..."},
        {"name": "issuer_name", "verdict": "unavailable", "reason": "..."},
        {"name": "settlement_date", "verdict": "unavailable", "reason": "..."},
    ],
    "citations": [{"domain": "market_risk", "source": "var",
                   "heading": "Observation window", "distance": 0.12}],
    "warnings": ["Requested 10,000 rows; the method consumes 250."],
}


def test_the_card_states_the_shape_of_the_data():
    assert "250 rows" in artifact_summary(TABLE, PLAN)
    assert "4 cols" in artifact_summary(TABLE, PLAN)


def test_the_card_says_whether_the_window_is_cited():
    """The most useful thing on the card: is this number auditable?"""
    assert "window cited" in artifact_summary(TABLE, PLAN)


def test_an_ungrounded_window_is_called_out_on_the_card():
    """A row count nobody can trace must not look like one that is traced."""
    summary = artifact_summary(TABLE, dict(PLAN, grounded=False))
    assert "window NOT cited" in summary


def test_the_card_counts_fields_that_do_not_exist():
    """Three unavailable fields is the thing most worth knowing up front."""
    assert "3 field(s) unavailable" in artifact_summary(TABLE, PLAN)


def test_no_window_is_claimed_when_the_corpus_stated_none():
    plan = dict(PLAN, rows=None)
    assert "window" not in artifact_summary(TABLE, plan)


def test_no_missing_fields_are_claimed_when_all_were_available():
    plan = dict(PLAN, field_notes=[
        {"name": "observation_date", "verdict": "required", "reason": "..."}])
    assert "unavailable" not in artifact_summary(TABLE, plan)


def test_a_table_without_a_plan_still_summarises():
    """Not every table comes from the planner; the card must not depend on one."""
    summary = artifact_summary(TABLE, None)
    assert "250 rows" in summary
    assert "window" not in summary


def test_an_empty_table_does_not_crash_the_card():
    assert artifact_summary({"row_count": 0, "columns": []}, None).startswith("0 rows")
