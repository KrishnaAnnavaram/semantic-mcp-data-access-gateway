"""Redis policy tests; integration cases run against an explicitly supplied Redis 8."""

from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import replace

import pytest

from agents.cache import RedisConfig, build_intelligence
from agents.cache.fingerprints import (
    analytical_signature,
    fingerprint,
    is_semantic_cache_reuse_safe,
)
from agents.cache.policies import execution_cacheability
from agents.cache.serialization import CacheRequest
from agents.contracts import KnowledgeChunk, Requirement, TemporalScope
from agents.redaction import contains_sensitive_data, redact_sensitive


def test_fingerprints_are_deterministic_but_versions_are_material():
    left = fingerprint({"fields": ["rate_percent", "observation_date"], "rows": 250})
    right = fingerprint({"rows": 250, "fields": ["observation_date", "rate_percent"]})
    changed = fingerprint({"rows": 250, "fields": ["observation_date"], "knowledge_version": "new"})
    assert left == right
    assert changed != left


@pytest.mark.parametrize(
    ("question", "candidate", "reason"),
    [
        (
            "calculate 99% one-day VaR",
            "calculate 95% one-day VaR",
            "analytical_mismatch:confidence_level",
        ),
        (
            "calculate 99% one-day VaR",
            "calculate 99% ten-day VaR",
            "analytical_mismatch:horizon_days",
        ),
        (
            "show nominal 10 year yield",
            "show real 10 year yield",
            "analytical_mismatch:curve_family",
        ),
        ("show the yield in 2008", "show the latest yield", "analytical_mismatch:temporal_mode"),
    ],
)
def test_semantic_similarity_never_overrides_analytical_dimensions(
    question,
    candidate,
    reason,
):
    safe, actual = is_semantic_cache_reuse_safe(
        analytical_signature(question),
        analytical_signature(candidate),
        query_versions={"knowledge": "v1"},
        candidate_versions={"knowledge": "v1"},
        similarity=0.999,
        threshold=0.93,
    )
    assert safe is False
    assert actual == reason


def test_execution_cache_is_explicitly_deferred_without_snapshot_identity():
    current = Requirement(task="latest", answerable=True)
    historical = Requirement(
        task="historical", answerable=True, temporal=TemporalScope(as_of_date="2008-09-15")
    )
    assert execution_cacheability(current) == (False, "latest_or_current_data")
    assert execution_cacheability(historical) == (
        False,
        "historical_snapshot_identity_not_exposed_by_provider",
    )


def test_secret_detection_and_redaction_cover_credentials_and_urls():
    value = {
        "api_key": "sk_example_123456789012",
        "message": "Authorization: Bearer token-value redis://user:pw@redis:6379/0",
    }
    assert contains_sensitive_data(value)
    redacted = redact_sensitive(value)
    assert redacted["api_key"] == "[REDACTED]"
    assert "token-value" not in redacted["message"]
    assert "user:pw" not in redacted["message"]


def test_disabled_redis_is_a_true_noop():
    intelligence = build_intelligence(config=RedisConfig(enabled=False))
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return {"value": calls}

    request = CacheRequest("mcp_agent", "choices", {"provider": "test"}, {"schema": "v1"}, "json")
    assert intelligence.cached(request, compute) == {"value": 1}
    assert intelligence.cached(request, compute) == {"value": 2}
    assert intelligence.health()["mode"] == "no-op"


def test_unreachable_optional_redis_fails_open_without_waiting_for_a_lock():
    config = replace(
        RedisConfig(enabled=True, url="redis://127.0.0.1:6398/0"),
        socket_connect_timeout=0.05,
        socket_timeout=0.05,
        lock_wait_seconds=2.0,
    )
    intelligence = build_intelligence(config=config)
    started = time.perf_counter()
    result = intelligence.cached(
        _choices_request(identity="offline"), lambda: _choice_payload("offline")
    )
    elapsed = time.perf_counter() - started
    intelligence.close()
    assert result["portfolios"][0]["id"] == "offline"
    assert elapsed < 1.0


@pytest.fixture
def redis_intelligence():
    url = os.environ.get("REDIS_INTEGRATION_URL")
    if not url:
        pytest.skip("set REDIS_INTEGRATION_URL to run Redis 8 integration tests")
    import redis
    from redis.exceptions import ResponseError

    namespace = f"pytest-{uuid.uuid4().hex[:12]}"
    config = replace(
        RedisConfig(enabled=True, url=url),
        cache_prefix=namespace,
        lock_wait_seconds=3.0,
        lock_ttl_ms=10_000,
        mcp_choices_ttl=1,
        global_llm_rate_limit=2,
        llm_rate_window_seconds=30,
    )
    raw = redis.Redis.from_url(url, decode_responses=True, protocol=2)
    intelligence = build_intelligence(
        config=config,
        client=raw,
        embedder=lambda _text: [1.0, 0.0, 0.0],
        embedding_model="test-bge-compatible-3d",
    )
    yield intelligence
    for index in (intelligence.keys.semantic_index(), intelligence.keys.run_index()):
        try:
            raw.execute_command("FT.DROPINDEX", index)
        except ResponseError:  # the test may not have created that index
            continue
    keys = list(raw.scan_iter(match=f"{config.namespace}:*", count=500))
    if keys:
        raw.unlink(*keys)
    intelligence.close()


def _choices_request(*, version: str = "v1", identity: str = "same"):
    return CacheRequest(
        agent="mcp_agent",
        operation="choices",
        identity={"provider": identity},
        versions={"schema": version},
        result_kind="choices",
        canonical_question="show available choices",
    )


def _choice_payload(value: object) -> dict:
    return {
        "portfolios": [{"id": value}],
        "scenarios": [],
        "curve_families": ["nominal", "real"],
        "tenors": ["y2", "y10"],
        "availability_warnings": [],
    }


def test_actual_redis_exact_cache_schema_invalidation_and_telemetry(
    redis_intelligence,
):
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return _choice_payload("P1")

    request = _choices_request()
    assert redis_intelligence.cached(request, compute)["portfolios"][0]["id"] == "P1"
    assert redis_intelligence.cached(request, compute)["portfolios"][0]["id"] == "P1"
    assert calls == 1
    counters = redis_intelligence.telemetry.counters()
    assert counters["mcp_agent.misses"] == 1
    assert counters["mcp_agent.exact_hits"] == 1
    assert redis_intelligence.connection.raw.xlen(redis_intelligence.keys.stream()) == 2

    # A value with the right key but wrong JSON contract is discarded rather
    # than leaking through as a partially rebuilt result.
    keys = list(
        redis_intelligence.connection.raw.scan_iter(
            match=f"{redis_intelligence.config.namespace}:cache:mcp_agent:choices:*"
        )
    )
    assert len(keys) == 1
    redis_intelligence.connection.raw.json().set(keys[0], "$.result", "corrupt")
    redis_intelligence.cached(request, compute)
    assert calls == 2
    assert redis_intelligence.telemetry.counters()["system.cache_invalidations"] == 1

    # A schema/version change is a new identity, never a stale hit.
    redis_intelligence.cached(_choices_request(version="v2"), compute)
    assert calls == 3


def test_actual_redis_ttl_expiration_becomes_a_miss(redis_intelligence):
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return _choice_payload(calls)

    request = _choices_request(identity="expires")
    assert redis_intelligence.cached(request, compute)["portfolios"][0]["id"] == 1
    time.sleep(1.2)
    assert redis_intelligence.cached(request, compute)["portfolios"][0]["id"] == 2
    assert redis_intelligence.telemetry.counters()["system.cache_expirations"] >= 1


def test_actual_redis_singleflight_has_one_owner(redis_intelligence):
    request = _choices_request(identity="singleflight")
    calls = 0
    barrier = threading.Barrier(3)
    results = []

    def worker():
        nonlocal calls
        barrier.wait()

        def compute():
            nonlocal calls
            calls += 1
            time.sleep(0.15)
            return _choice_payload("OWNER")

        results.append(redis_intelligence.cached(request, compute))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)
    assert not any(thread.is_alive() for thread in threads)
    assert calls == 1
    assert [row["portfolios"][0]["id"] for row in results] == ["OWNER", "OWNER"]


def test_actual_redis_semantic_hit_requires_safe_signature(redis_intelligence):
    versions = {"knowledge": "k1", "prompt": "p1", "schema": "s1"}
    calls = 0
    value = (
        Requirement(task="VaR", answerable=True),
        [KnowledgeChunk("market_risk", "var", "Window", "grounded text", 0.1)],
    )

    def compute():
        nonlocal calls
        calls += 1
        return value

    def request(question: str):
        return CacheRequest(
            "domain_expert",
            "derive",
            {"question": question},
            versions,
            "requirement_with_chunks",
            question,
            analytical_signature(question),
            {"provider": "test", "model": "test"},
        )

    redis_intelligence.cached(request("calculate 99% one-day VaR"), compute)
    redis_intelligence.cached(request("give me one-day VaR at 99%"), compute)
    assert calls == 1

    # The vector is deliberately identical; only the structured safety gate
    # prevents the analytically different confidence level from being reused.
    redis_intelligence.cached(request("calculate 95% one-day VaR"), compute)
    assert calls == 2
    counters = redis_intelligence.telemetry.counters()
    assert counters["domain_expert.semantic_hits"] == 1
    assert counters["system.semantic_safety_rejections"] >= 1


def test_actual_redis_native_rate_limit_and_health(redis_intelligence):
    assert redis_intelligence.allow_llm("orchestrator") is True
    assert redis_intelligence.allow_llm("orchestrator") is True
    assert redis_intelligence.allow_llm("orchestrator") is False
    health = redis_intelligence.health()
    assert health["version"].startswith("8.8.")
    assert health["json"] and health["search"] and health["timeseries"]


def test_actual_redis_timeseries_and_searchable_run_summary(redis_intelligence):
    redis_intelligence.telemetry.record_operation(
        {
            "event_type": "operation_completed",
            "request_id": "run-redis-test",
            "agent": "domain_expert",
            "operation": "derive",
            "cache_status": "miss",
            "cache_type": "exact",
            "duration_ms": 42,
            "llm_called": True,
            "prompt_tokens": 100,
            "completion_tokens": 25,
            "total_tokens": 125,
            "result_status": "completed",
        }
    )
    redis_intelligence.complete_run(
        "run-redis-test",
        question="calculate one-day VaR",
        route="data_request",
        result_status="AGREED",
        total_latency_ms=123,
        negotiation_rounds=1,
    )

    raw = redis_intelligence.connection.raw
    summary = raw.json().get(redis_intelligence.keys.run("run-redis-test"))
    assert summary["route"] == "data_request"
    assert summary["actual_total_tokens"] == 125
    search = raw.execute_command(
        "FT.SEARCH",
        redis_intelligence.keys.run_index(),
        "@request_id:{run\\-redis\\-test}",
        "NOCONTENT",
    )
    assert int(search[0]) == 1
    samples = raw.execute_command(
        "TS.RANGE",
        redis_intelligence.keys.timeseries("domain_expert", "derive", "latency_ms"),
        "-",
        "+",
    )
    assert any(float(sample[1]) == 42 for sample in samples)
