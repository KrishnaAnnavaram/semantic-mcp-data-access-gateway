"""Tier 4 — every data tool, exercised. Needs PostgreSQL.

One happy path and one edge per tool. The edges matter more: a tool that returns
plausible data for a bad request is worse than one that fails, because the
number reaches an answer either way.

The three client-directed tools (`search_series`, `export_curve_csv`,
`brief_dataset_caveat`) are absent by design — a resolver needs a request
context this in-process path does not create, so they are covered end-to-end by
`tools/verify_mcp.py` with real child processes.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("db")


def _structured(result):
    data = getattr(result, "structured_content", None)
    assert data is not None, "tool returned no structured content"
    return data


# --- catalogue --------------------------------------------------------------


def test_list_datasets_returns_the_five_datasets_with_caveats(call_tool):
    body = _structured(call_tool("list_datasets", {}))
    datasets = body["datasets"]
    assert len(datasets) >= 5
    assert all((d.get("caveat") or "").strip() for d in datasets), \
        "a dataset without a caveat is a trap nobody is warned about"


def test_list_series_paginates_and_carries_a_cursor(call_tool):
    body = _structured(call_tool("list_series", {"page_size": 5}))
    assert len(body["series"]) == 5
    assert body.get("next_cursor"), "more series exist, so a cursor is owed"


def test_list_series_cursor_advances_without_repeating(call_tool):
    first = _structured(call_tool("list_series", {"page_size": 5}))
    second = _structured(call_tool("list_series", {"page_size": 5,
                                                   "cursor": first["next_cursor"]}))
    assert not ({s["series_code"] for s in first["series"]}
                & {s["series_code"] for s in second["series"]})


def test_list_series_rejects_an_oversized_page(failing_tool):
    err = failing_tool("list_series", {"page_size": 100_000})
    assert err.get("error_code") == "ROW_LIMIT_EXCEEDED"


def test_list_series_filters_by_dataset(call_tool):
    body = _structured(call_tool("list_series", {"data_key": "daily_treasury_bill_rates",
                                                 "page_size": 50}))
    assert body["series"]
    assert {s["data_key"] for s in body["series"]} == {"daily_treasury_bill_rates"}


def test_get_series_coverage_reports_bounds(call_tool):
    body = _structured(call_tool("get_series_coverage", {"series_codes": ["BC_10YEAR"]}))
    series = body["series"][0]
    assert series["first_observation"] < series["last_observation"]
    assert series["observation_count"] > 0


def test_get_series_coverage_rejects_an_unknown_code_with_candidates(failing_tool):
    err = failing_tool("get_series_coverage", {"series_codes": ["BC_10Y"]})
    assert err.get("error_code") == "UNKNOWN_SERIES"
    assert err.get("candidates"), "the model must be able to retry without a human"


def test_get_series_coverage_refuses_an_oversized_batch(failing_tool):
    err = failing_tool("get_series_coverage", {"series_codes": [f"S{i}" for i in range(64)]})
    assert err.get("error_code") == "ROW_LIMIT_EXCEEDED"


# --- curve ------------------------------------------------------------------


def test_get_curve_returns_a_fully_described_curve(call_tool):
    body = _structured(call_tool("get_curve", {"curve_family": "nominal"}))
    assert body["points"]
    for point in body["points"]:
        assert point["quote_basis"] and point["rate_kind"]
    assert body["envelope"]["data_classification"] == "REAL_MARKET_DATA"


def test_get_curve_defaults_to_refusing_a_shifted_date(failing_tool):
    """4 July 2026 is a holiday; `exact` must not silently return the 3rd."""
    err = failing_tool("get_curve", {"curve_family": "nominal",
                                     "observation_date": "2026-07-04"})
    assert err.get("error_code") == "DATE_NO_DATA"
    assert err.get("candidates")


def test_get_curve_shifts_only_when_asked_and_says_so(call_tool):
    body = _structured(call_tool("get_curve", {"curve_family": "nominal",
                                               "observation_date": "2026-07-04",
                                               "date_policy": "previous"}))
    assert body["date_was_shifted"] is True
    assert body["observation_date"] != "2026-07-04"
    assert body["envelope"]["warnings"], "a shift must be stated, not just performed"


def test_get_curve_rejects_a_date_outside_published_history(failing_tool):
    err = failing_tool("get_curve", {"curve_family": "nominal",
                                     "observation_date": "1970-01-01"})
    assert err.get("error_code") == "DATE_OUT_OF_RANGE"


def test_the_real_curve_is_available_and_distinct(call_tool):
    real = _structured(call_tool("get_curve", {"curve_family": "real"}))
    assert {p["rate_kind"] for p in real["points"]} == {"real"}


# --- history ----------------------------------------------------------------


def test_get_rate_history_returns_ordered_observations(call_tool):
    body = _structured(call_tool("get_rate_history", {
        "series_codes": ["BC_10YEAR"], "start_date": "2026-01-02",
        "end_date": "2026-03-31", "page_size": 100}))
    dates = [i["observation_date"] for i in body["items"]]
    assert dates == sorted(dates)
    assert body["returned"] == len(body["items"])


def test_get_rate_history_rejects_a_reversed_range(failing_tool):
    err = failing_tool("get_rate_history", {
        "series_codes": ["BC_10YEAR"], "start_date": "2026-08-01",
        "end_date": "2026-01-01"})
    assert err.get("error_code") == "INVALID_DATE_RANGE"


def test_get_rate_history_refuses_too_many_series(failing_tool):
    err = failing_tool("get_rate_history", {
        "series_codes": [f"S{i}" for i in range(40)],
        "start_date": "2026-01-01", "end_date": "2026-02-01"})
    assert err.get("error_code") == "ROW_LIMIT_EXCEEDED"


# --- bulk matrix ------------------------------------------------------------


def test_curve_history_matrix_keeps_the_numbers_out_of_the_model_view(call_tool):
    """The summary goes to the model; the matrix rides `_meta` to the risk engine."""
    # 60 is the documented floor; anything smaller is refused as ROW_LIMIT_EXCEEDED.
    result = call_tool("get_curve_history_matrix", {
        "curve_family": "nominal", "trading_days": 60,
        "tenors_months": [24, 120, 360]})
    summary = _structured(result)
    meta = dict(getattr(result, "meta", None) or {})
    payload = meta.get(summary["meta_key"])
    assert payload, "the bulk matrix must travel in _meta"
    assert len(payload["rates_percent"]) == summary["trading_days_returned"]
    assert len(payload["rates_percent"][0]) == 3
    assert payload["quote_basis"], "even the bulk channel carries its basis"


def test_curve_history_matrix_refuses_a_window_with_gaps_by_default(failing_tool):
    """Silently dropping dates changes any risk number computed from the window."""
    err = failing_tool("get_curve_history_matrix", {
        "curve_family": "nominal", "as_of_date": "2005-06-30",
        "trading_days": 250, "tenors_months": [24, 120, 360]})
    assert err.get("error_code") == "MISSING_OBSERVATIONS"


def test_curve_history_matrix_reports_exclusions_when_gaps_are_accepted(call_tool):
    body = _structured(call_tool("get_curve_history_matrix", {
        "curve_family": "nominal", "as_of_date": "2005-06-30",
        "trading_days": 250, "tenors_months": [24, 120, 360],
        "missing_policy": "intersection"}))
    assert body["excluded_dates"] > 0
    assert body["excluded_date_sample"], "an exclusion nobody can see is a silent drop"


def test_curve_history_matrix_rejects_an_absurd_window(failing_tool):
    err = failing_tool("get_curve_history_matrix", {
        "curve_family": "nominal", "trading_days": 99_999})
    assert err.get("error_code") == "ROW_LIMIT_EXCEEDED"


# --- provenance -------------------------------------------------------------


def test_explain_number_traces_a_value_to_a_checksummed_file(call_tool):
    body = _structured(call_tool("explain_number", {
        "series_code": "BC_10YEAR", "observation_date": "2026-08-11"}))
    assert body["provenance"]["source_sha256"]
    assert body["provenance"]["source_file"].endswith(".xml")
    assert "chain" in body["lineage"]


def test_explain_number_refuses_a_date_with_no_observation(failing_tool):
    err = failing_tool("explain_number", {"series_code": "BC_10YEAR",
                                          "observation_date": "2026-07-04"})
    assert err.get("error_code") in {"DATE_NO_DATA", "DATE_OUT_OF_RANGE"}


# --- demo book (synthetic) --------------------------------------------------


def test_list_portfolios_labels_everything_synthetic(call_tool):
    body = _structured(call_tool("list_portfolios", {}))
    assert body["portfolios"]
    assert body["envelope"]["data_classification"] == "SYNTHETIC_DEMO"


def test_get_portfolio_returns_priceable_economics(call_tool):
    portfolio_id = _structured(call_tool("list_portfolios", {}))["portfolios"][0]["portfolio_id"]
    body = _structured(call_tool("get_portfolio", {"portfolio_id": portfolio_id}))
    assert body["envelope"]["data_classification"] == "SYNTHETIC_DEMO"
    for position in body["positions"]:
        instrument = position["instrument"]
        assert instrument["maturity_date"] and instrument["coupon_rate_pct"] is not None


def test_get_portfolio_refuses_an_unknown_id_with_candidates(failing_tool):
    err = failing_tool("get_portfolio", {"portfolio_id": "NOT_A_BOOK"})
    assert err.get("error_code") == "UNKNOWN_PORTFOLIO"
    assert err.get("candidates")


def test_list_scenarios_declares_each_scenario_type(call_tool):
    body = _structured(call_tool("list_scenarios", {}))
    assert body["scenarios"]
    assert {s["scenario_type"] for s in body["scenarios"]} <= {
        "TENOR_VECTOR_BP", "HISTORICAL_REPLAY"}


def test_get_scenario_returns_a_usable_shock_definition(call_tool):
    scenario_id = _structured(call_tool("list_scenarios", {}))["scenarios"][0]["scenario_id"]
    body = _structured(call_tool("get_scenario", {"scenario_id": scenario_id}))
    assert body["shock_definition"]


def test_get_scenario_refuses_an_unknown_id(failing_tool):
    err = failing_tool("get_scenario", {"scenario_id": "NOPE"})
    assert err.get("error_code") == "UNKNOWN_SCENARIO"
