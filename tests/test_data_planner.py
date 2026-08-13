"""Data-requirement planning: the reduction must be correct *and* explainable.

A planner that quietly returns fewer rows is indistinguishable from a bug. So
these tests check both halves: that the right amount of data is chosen, and that
every departure from what was asked for carries a reason the caller can read.
"""

from __future__ import annotations

import pytest

from backend.agent import data_planner as dp

AVAILABLE = ["observation_date", "rate_percent", "quote_basis", "tenor",
             "rate_kind", "data_key", "series_code"]


def make_plan(task, fields=None, rows=None):
    return dp.plan(task, fields, rows, available_fields=AVAILABLE, knowledge=None)


# --- classification ---------------------------------------------------------


@pytest.mark.parametrize("task,expected", [
    ("10-day 99% historical VaR on the book", "historical_var"),
    ("expected shortfall at 97.5%", "historical_var"),
    ("compute DV01 and key rate sensitivities", "sensitivity"),
    ("show me the yield curve for today", "curve_snapshot"),
    ("run the 2008 stress scenario", "stress_replay"),
    ("how has the 10 year moved over time", "trend"),
])
def test_tasks_are_classified_by_what_they_are_for(task, expected):
    assert dp.classify(task).name == expected


def test_an_unrecognised_task_falls_back_to_the_least_presumptuous_profile():
    """Guessing a 250-day window for an unknown task would be worse than a snapshot."""
    assert dp.classify("something entirely unrelated").name == "curve_snapshot"


# --- row decisions ----------------------------------------------------------


def test_a_ten_thousand_row_request_for_var_is_reduced_to_the_method_window():
    """The demo case. 250 is methodology, not preference."""
    plan = make_plan("10-day 99% historical VaR", rows=10_000)
    assert plan.granted_rows == 250
    assert plan.requested_rows == 10_000


def test_the_reduction_is_always_explained():
    plan = make_plan("historical VaR", rows=10_000)
    assert plan.warnings, "a silent reduction is indistinguishable from a bug"
    assert "10,000" in plan.warnings[0] and "250" in plan.warnings[0]
    assert plan.row_reason.strip()


def test_asking_for_fewer_rows_than_the_method_needs_does_not_shrink_the_window():
    """The one case where honouring the request produces a wrong number.

    A short lookback does not approximate a 250-day VaR; it computes a
    different one. So the plan refuses and says why.
    """
    plan = make_plan("historical VaR", rows=30)
    assert plan.granted_rows == 250
    assert any("changes the number" in w for w in plan.warnings)


def test_a_sensitivity_needs_one_curve_not_a_history():
    plan = make_plan("compute DV01 on the book", rows=5_000)
    assert plan.granted_rows == 1
    assert "not a history" in plan.row_reason or "single curve" in plan.row_reason


def test_a_stress_replay_needs_exactly_two_dates():
    assert make_plan("replay the 2008 stress scenario").granted_rows == 2


def test_no_warning_when_the_request_already_matches_the_method():
    assert make_plan("historical VaR", rows=250).warnings == []


# --- field decisions --------------------------------------------------------


def test_fields_the_dataset_does_not_publish_are_reported_never_invented():
    """Nothing is substituted for a column that does not exist."""
    plan = make_plan("historical VaR", fields=["cusip", "issuer_name"])
    verdicts = {d.name: d.verdict for d in plan.field_decisions}
    assert verdicts["cusip"] == "unavailable"
    assert verdicts["issuer_name"] == "unavailable"
    assert "cusip" not in plan.granted_fields


def test_a_real_but_unnecessary_field_is_dropped_with_a_reason():
    plan = make_plan("compute DV01", fields=["data_key"])
    dropped = [d for d in plan.field_decisions if d.name == "data_key"]
    assert dropped and dropped[0].verdict == "dropped"
    assert dropped[0].reason.strip()


def test_quote_basis_is_never_dropped_whatever_was_asked_for():
    """A rate without its basis is a number nobody can safely combine."""
    for task in ("historical VaR", "compute DV01", "show the curve", "stress replay"):
        assert "quote_basis" in make_plan(task).granted_fields


def test_every_decision_carries_a_reason():
    plan = make_plan("historical VaR", fields=["cusip", "data_key", "rate_percent"])
    assert all(d.reason.strip() for d in plan.field_decisions)


def test_granted_fields_never_include_something_unavailable():
    plan = make_plan("historical VaR", fields=["not_a_column"])
    assert set(plan.granted_fields) <= set(AVAILABLE) | set(dp.MANDATORY_FIELDS)


# --- knowledge grounding ----------------------------------------------------


def test_the_plan_cites_the_knowledge_it_was_grounded_in():
    class FakeKB:
        def retrieve(self, query, domain=None):
            return [{"domain": "market_risk", "source": "var",
                     "heading": "Data required", "distance": 0.21}]

    plan = dp.plan("historical VaR", None, 10_000,
                   available_fields=AVAILABLE, knowledge=FakeKB())
    assert plan.sources and plan.sources[0]["source"] == "var"


def test_a_knowledge_failure_still_yields_a_usable_plan():
    """Citations improve a plan; their absence must not withhold one."""
    class BrokenKB:
        def retrieve(self, query, domain=None):
            raise RuntimeError("vector store down")

    plan = dp.plan("historical VaR", None, 10_000,
                   available_fields=AVAILABLE, knowledge=BrokenKB())
    assert plan.granted_rows == 250
    assert plan.sources == []


def test_the_plan_serialises_for_the_wire():
    import json
    json.dumps(make_plan("historical VaR", ["cusip"], 10_000).as_dict())


# --- table shaping ----------------------------------------------------------


def test_a_table_is_columns_and_rows_not_a_formatted_string():
    """The UI needs a real widget; a markdown blob cannot be sorted or scrolled."""
    table = dp.build_table([{"a": 1, "b": 2}, {"a": 3, "b": 4}], ["a", "b"], "T")
    assert table["columns"] == ["a", "b"]
    assert table["rows"] == [[1, 2], [3, 4]]


def test_dates_are_serialised_for_json():
    import datetime as dt
    table = dp.build_table([{"d": dt.date(2026, 8, 11)}], ["d"], "T")
    assert table["rows"] == [["2026-08-11"]]


def test_a_large_result_is_capped_for_display_but_reports_the_true_count():
    rows = [{"a": i} for i in range(dp.MAX_DISPLAY_ROWS + 250)]
    table = dp.build_table(rows, ["a"], "T")
    assert table["displayed"] == dp.MAX_DISPLAY_ROWS
    assert table["row_count"] == len(rows)
    assert table["truncated"] is True


def test_a_missing_column_becomes_an_empty_cell_not_an_error():
    table = dp.build_table([{"a": 1}], ["a", "b"], "T")
    assert table["rows"] == [[1, None]]
