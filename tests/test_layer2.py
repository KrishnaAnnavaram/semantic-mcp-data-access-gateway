"""Layer 2 tests — data provider, trace helpers, and the /chat service.

Fast and offline: no ANTHROPIC_API_KEY, no network, no vector download. The live
LLM loop is intentionally not exercised here.
"""

import json

from data_provider import MockDataProvider
from smart_agent import TraceStep, extract_sources, trace_as_dicts


# --- Treasury-shaped mock data provider ---------------------------------------

def test_latest_curve_matches_published_base():
    d = MockDataProvider()
    curve = d.get_yield_curve()["points"]
    assert curve["y2"] == 4.22
    assert curve["y10"] == 4.70
    assert curve["y30"] == 5.24


def test_2s10s_slope():
    d = MockDataProvider()
    slope = d.get_curve_slope(short="y2", long="y10")
    assert slope["slope_bps"] == 48.0  # (4.70 - 4.22) * 100


def test_rate_history_shape():
    d = MockDataProvider()
    hist = d.get_rate_history("y10")
    assert len(hist) == 252
    assert hist[-1]["observation_date"] == "2026-08-11"
    assert all("rate_percent" in row for row in hist)


def test_series_catalogue():
    d = MockDataProvider()
    series = d.list_series()
    assert len(series) == 19  # 14 nominal + 5 real
    assert {s["rate_kind"] for s in series} == {"nominal", "real"}


def test_unknown_tenor_is_handled():
    d = MockDataProvider()
    assert d.get_rate_history("zz9") == []
    assert "error" in d.get_curve_slope(short="zz9", long="y10")


# --- decision-trace helpers ---------------------------------------------------

def test_extract_sources_dedupes_domain_source():
    trace = [
        TraceStep("knowledge", "q", [
            "market_risk/yield_curve/Definition (dist=0.2)",
            "market_risk/yield_curve/Key measures (dist=0.3)",
            "credit_risk/pd_lgd_ead/Definition (dist=0.4)",
        ]),
    ]
    assert extract_sources(trace) == ["market_risk/yield_curve", "credit_risk/pd_lgd_ead"]


def test_trace_as_dicts_is_json_serializable():
    trace = [TraceStep("intent", "got it", "hello"), TraceStep("answer", "done", None)]
    dicts = trace_as_dicts(trace)
    json.dumps(dicts)  # must not raise
    assert dicts[0] == {"kind": "intent", "label": "got it", "detail": "hello"}


# --- /chat service (no LLM call) ----------------------------------------------

def test_service_health_and_validation():
    from fastapi.testclient import TestClient

    import agent_service

    client = TestClient(agent_service.app)
    assert client.get("/health").status_code == 200
    # empty query fails validation before any agent/LLM work happens
    assert client.post("/chat", json={"query": ""}).status_code == 422
