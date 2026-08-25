"""Redis Streams, Time Series, counters, run summaries, and cache analytics."""

from __future__ import annotations

import json
import math
import threading
import time
from datetime import UTC, datetime
from typing import Any

from agents.cache.client import RedisConnection
from agents.cache.config import RedisConfig
from agents.cache.fingerprints import canonical_question, fingerprint
from agents.cache.keys import KeyBuilder
from agents.redaction import contains_sensitive_data, redact_sensitive


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stream_value(value: Any) -> str:
    value = redact_sensitive(value)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class RedisTelemetry:
    """Best-effort operational evidence. Failure never changes an answer."""

    def __init__(self, connection: RedisConnection, config: RedisConfig, keys: KeyBuilder) -> None:
        self.connection = connection
        self.config = config
        self.keys = keys
        self._run_lock = threading.Lock()
        self._indexes_ready = False

    def ensure_run_index(self) -> bool:
        if self._indexes_ready:
            return True

        def create(client):
            try:
                client.execute_command(
                    "FT.CREATE",
                    self.keys.run_index(),
                    "ON",
                    "JSON",
                    "PREFIX",
                    1,
                    self.keys.run_prefix(),
                    "SCHEMA",
                    "$.request_id",
                    "AS",
                    "request_id",
                    "TAG",
                    "$.canonical_question",
                    "AS",
                    "canonical_question",
                    "TEXT",
                    "$.route",
                    "AS",
                    "route",
                    "TAG",
                    "$.result_status",
                    "AS",
                    "result_status",
                    "TAG",
                    "$.domain_cache_status",
                    "AS",
                    "domain_cache_status",
                    "TAG",
                    "$.mcp_cache_status",
                    "AS",
                    "mcp_cache_status",
                    "TAG",
                    "$.total_latency_ms",
                    "AS",
                    "total_latency_ms",
                    "NUMERIC",
                    "$.actual_total_tokens",
                    "AS",
                    "actual_total_tokens",
                    "NUMERIC",
                    "$.estimated_tokens_saved",
                    "AS",
                    "estimated_tokens_saved",
                    "NUMERIC",
                    "$.negotiation_rounds",
                    "AS",
                    "negotiation_rounds",
                    "NUMERIC",
                    "$.created_at",
                    "AS",
                    "created_at",
                    "TAG",
                )
            except Exception as exc:
                if "Index already exists" not in str(exc):
                    raise
            return True

        ready = self.connection.call("create run-summary index", create, False)
        self._indexes_ready = bool(ready)
        return self._indexes_ready

    def record_operation(self, event: dict[str, Any]) -> None:
        clean = dict(redact_sensitive(event))
        clean.setdefault("timestamp", _now())
        clean.setdefault("request_id", "")
        clean.setdefault("context_id", "")
        clean.setdefault("task_id", "")
        clean.setdefault("negotiation_round", 0)
        clean.setdefault("phase", "")
        clean.setdefault("retries", 0)
        clean.setdefault("cache_status", "bypass")
        clean.setdefault("cache_type", "none")
        clean.setdefault("result_status", "completed")
        stream_fields = {key: _stream_value(value) for key, value in clean.items()}
        counter_changes = self._counter_changes(clean)

        def write(client):
            pipe = client.pipeline(transaction=False)
            pipe.xadd(
                self.keys.stream(),
                stream_fields,
                maxlen=self.config.agent_stream_maxlen,
                approximate=True,
            )
            for name, amount in counter_changes.items():
                pipe.hincrby(self.keys.counters(), name, int(amount))
            pipe.execute()
            return True

        self.connection.call("write agent event", write, False)
        self._record_timeseries(clean)
        self._update_run_from_event(clean)

    @staticmethod
    def _counter_changes(event: dict[str, Any]) -> dict[str, int]:
        changes: dict[str, int] = {}
        agent = str(event.get("agent") or "system")
        status = str(event.get("cache_status") or "")
        if status in {"exact_hit", "wait_hit"}:
            changes[f"{agent}.exact_hits"] = 1
        elif status == "semantic_hit":
            changes[f"{agent}.semantic_hits"] = 1
        elif status == "miss":
            changes[f"{agent}.misses"] = 1
        if event.get("llm_called"):
            changes["system.llm_invocations"] = 1
        if event.get("saved_llm_call"):
            changes["system.llm_calls_avoided"] = 1
        saved = int(float(event.get("estimated_tokens_saved") or 0))
        if saved:
            changes["system.estimated_tokens_saved"] = saved
        used = int(float(event.get("total_tokens") or 0))
        if used:
            changes["system.actual_tokens_used"] = used
        if event.get("failure_kind") == "semantic_safety_rejected":
            changes["system.semantic_safety_rejections"] = 1
        return changes

    def _record_timeseries(self, event: dict[str, Any]) -> None:
        agent = str(event.get("agent") or "system")
        operation = str(event.get("operation") or "unknown")
        model = str(event.get("model") or "none")
        values = {
            "latency_ms": event.get("duration_ms"),
            "redis_latency_ms": event.get("redis_latency_ms"),
            "prompt_tokens": event.get("prompt_tokens"),
            "reasoning_tokens": event.get("reasoning_tokens"),
            "completion_tokens": event.get("completion_tokens"),
            "total_tokens": event.get("total_tokens"),
            "cache_hit": 1
            if event.get("cache_status") in {"exact_hit", "semantic_hit", "wait_hit"}
            else 0,
            "cache_miss": 1 if event.get("cache_status") == "miss" else 0,
            "semantic_hit": 1 if event.get("cache_status") == "semantic_hit" else 0,
            "llm_invocation": 1 if event.get("llm_called") else 0,
            "estimated_tokens_saved": event.get("estimated_tokens_saved"),
            "estimated_latency_saved_ms": event.get("estimated_latency_saved_ms"),
        }
        samples: list[tuple[str, float]] = []
        for metric, raw in values.items():
            if raw is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            samples.append((metric, value))
        if not samples:
            return
        timestamp = int(time.time_ns() // 1_000_000)

        def add_all(client):
            pipe = client.pipeline(transaction=False)
            for metric, value in samples:
                pipe.execute_command(
                    "TS.ADD",
                    self.keys.timeseries(agent, operation, metric),
                    timestamp,
                    value,
                    "RETENTION",
                    self.config.metrics_retention_seconds * 1000,
                    "ON_DUPLICATE",
                    "LAST",
                    "LABELS",
                    "agent",
                    agent,
                    "operation",
                    operation,
                    "metric",
                    metric,
                    "model",
                    model,
                )
            pipe.execute()
            return True

        self.connection.call("record operation metrics", add_all, False)

    def record_question(
        self, *, agent: str, operation: str, question: str, question_fingerprint: str = ""
    ) -> None:
        canonical = canonical_question(str(redact_sensitive(question)))
        digest = question_fingerprint or fingerprint(canonical)
        now = _now()

        def write(client):
            pipe = client.pipeline(transaction=False)
            for scope in ("all", agent, f"{agent}:{operation}"):
                frequency_key = self.keys.question_frequency(scope)
                pipe.zincrby(frequency_key, 1, digest)
                # Keep the highest-frequency members. Metadata for a removed
                # member expires independently, so no orphan is permanent.
                pipe.zremrangebyrank(
                    frequency_key, 0, -(self.config.question_frequency_max_entries + 1)
                )
            pipe.execute()
            existing = client.json().get(self.keys.question_metadata(digest)) or {}
            client.json().set(
                self.keys.question_metadata(digest),
                "$",
                {
                    "fingerprint": digest,
                    "canonical_question": canonical,
                    "agent": agent,
                    "operation": operation,
                    "first_seen_at": existing.get("first_seen_at") or now,
                    "last_seen_at": now,
                },
            )
            client.expire(
                self.keys.question_metadata(digest), self.config.metrics_retention_seconds
            )
            return True

        self.connection.call("record repeated question", write, False)

    def record_negotiation(self, *, rounds: int, decision: str, request_id: str = "") -> None:
        event = {
            "event_type": "negotiation_completed",
            "agent": "system",
            "operation": "negotiation",
            "request_id": request_id,
            "cache_status": "bypass",
            "llm_called": False,
            "duration_ms": 0,
            "negotiation_round": rounds,
            "result_status": decision,
            "stalled": decision == "CANNOT_REACH_AGREEMENT",
        }
        self.record_operation(event)
        self._timeseries_value("system", "negotiation", "rounds", rounds, "none")
        self._timeseries_value(
            "system", "negotiation", "agreed", 1 if decision == "AGREED" else 0, "none"
        )
        if decision == "CANNOT_REACH_AGREEMENT":
            self._timeseries_value("system", "negotiation", "stalled", 1, "none")

    def _timeseries_value(
        self, agent: str, operation: str, metric: str, value: float, model: str
    ) -> None:
        key = self.keys.timeseries(agent, operation, metric)
        timestamp = int(time.time_ns() // 1_000_000)

        def add(client):
            return client.execute_command(
                "TS.ADD",
                key,
                timestamp,
                float(value),
                "RETENTION",
                self.config.metrics_retention_seconds * 1000,
                "ON_DUPLICATE",
                "LAST",
                "LABELS",
                "agent",
                agent,
                "operation",
                operation,
                "metric",
                metric,
                "model",
                model,
            )

        self.connection.call(f"record metric {metric}", add, None)

    def record_invalidation(self, count: int = 1) -> None:
        if count:
            self.connection.call(
                "count invalidation",
                lambda client: client.hincrby(
                    self.keys.counters(), "system.cache_invalidations", count
                ),
                0,
            )

    def record_expiration(self, count: int = 1) -> None:
        if count:
            self.connection.call(
                "count expiration",
                lambda client: client.hincrby(
                    self.keys.counters(), "system.cache_expirations", count
                ),
                0,
            )

    def complete_run(
        self,
        request_id: str,
        *,
        question: str,
        route: str,
        result_status: str,
        total_latency_ms: int,
        negotiation_rounds: int = 0,
    ) -> None:
        if not request_id:
            return
        clean_question = (
            "[sensitive query omitted]"
            if contains_sensitive_data(question)
            else canonical_question(str(redact_sensitive(question)))
        )
        self._merge_run(
            request_id,
            {
                "request_id": request_id,
                "canonical_question": clean_question,
                "question_fingerprint": fingerprint(clean_question),
                "route": route,
                "result_status": result_status,
                "total_latency_ms": max(0, int(total_latency_ms)),
                "negotiation_rounds": max(0, int(negotiation_rounds)),
                "completed_at": _now(),
            },
        )

    def _update_run_from_event(self, event: dict[str, Any]) -> None:
        request_id = str(event.get("request_id") or "")
        if not request_id:
            return
        agent = str(event.get("agent") or "")
        cache_status = str(event.get("cache_status") or "")
        usage = int(float(event.get("total_tokens") or 0))
        saved = int(float(event.get("estimated_tokens_saved") or 0))
        patch: dict[str, Any] = {
            "request_id": request_id,
            "actual_total_tokens_increment": usage,
            "estimated_tokens_saved_increment": saved,
            "llm_calls_increment": 1 if event.get("llm_called") else 0,
            "llm_calls_saved_increment": 1 if event.get("saved_llm_call") else 0,
        }
        if agent == "domain_expert" and cache_status:
            patch["domain_cache_status"] = cache_status
        elif agent == "mcp_agent" and cache_status:
            patch["mcp_cache_status"] = cache_status
        self._merge_run(request_id, patch)

    def _merge_run(self, request_id: str, patch: dict[str, Any]) -> None:
        self.ensure_run_index()
        key = self.keys.run(request_id)
        now = _now()

        def write(client):
            # A process-local lock avoids lost increments among this runtime's
            # worker threads. Cross-process events are still independently
            # durable in the Stream, which remains the analytics authority.
            with self._run_lock:
                current = client.json().get(key) or {
                    "request_id": request_id,
                    "canonical_question": "",
                    "question_fingerprint": "",
                    "route": "",
                    "result_status": "working",
                    "domain_cache_status": "",
                    "mcp_cache_status": "",
                    "total_latency_ms": 0,
                    "actual_total_tokens": 0,
                    "estimated_tokens_saved": 0,
                    "llm_calls": 0,
                    "llm_calls_saved": 0,
                    "negotiation_rounds": 0,
                    "created_at": now,
                }
                for source, target in (
                    ("actual_total_tokens_increment", "actual_total_tokens"),
                    ("estimated_tokens_saved_increment", "estimated_tokens_saved"),
                    ("llm_calls_increment", "llm_calls"),
                    ("llm_calls_saved_increment", "llm_calls_saved"),
                ):
                    current[target] = int(current.get(target) or 0) + int(patch.get(source) or 0)
                for name, value in patch.items():
                    if not name.endswith("_increment"):
                        current[name] = value
                client.json().set(key, "$", dict(redact_sensitive(current)))
                client.expire(key, self.config.run_summary_ttl)
            return True

        self.connection.call("update run summary", write, False)

    def counters(self) -> dict[str, int]:
        raw = self.connection.call(
            "read counters", lambda client: client.hgetall(self.keys.counters()), {}
        )
        return {str(key): int(value) for key, value in (raw or {}).items()}

    def top_questions(self, scope: str = "all", limit: int = 10) -> list[dict[str, Any]]:
        rows = self.connection.call(
            "read question frequencies",
            lambda client: client.zrevrange(
                self.keys.question_frequency(scope), 0, max(0, limit - 1), withscores=True
            ),
            [],
        )
        out = []
        for digest, score in rows or []:
            meta = (
                self.connection.call(
                    "read question metadata",
                    lambda client, d=digest: client.json().get(self.keys.question_metadata(str(d))),
                    {},
                )
                or {}
            )
            out.append({**meta, "count": int(score)})
        return out

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = (len(ordered) - 1) * percentile
        lower, upper = math.floor(index), math.ceil(index)
        if lower == upper:
            return round(ordered[lower], 3)
        weight = index - lower
        return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 3)

    def latency_percentiles(self, agent: str, operation: str) -> dict[str, float | None]:
        key = self.keys.timeseries(agent, operation, "latency_ms")
        rows = self.connection.call(
            "read latency series",
            lambda client: (
                client.execute_command("TS.RANGE", key, "-", "+") if client.exists(key) else []
            ),
            [],
        )
        values = [float(row[1]) for row in rows or [] if len(row) >= 2]
        return {
            name: self._percentile(values, percentile)
            for name, percentile in (("p50", 0.50), ("p95", 0.95), ("p99", 0.99))
        }

    def snapshot(self) -> dict[str, Any]:
        counters = self.counters()

        def hit_rate(agent: str) -> float | None:
            hits = counters.get(f"{agent}.exact_hits", 0) + counters.get(
                f"{agent}.semantic_hits", 0
            )
            attempts = hits + counters.get(f"{agent}.misses", 0)
            return round(hits / attempts, 4) if attempts else None

        return {
            "counters": counters,
            "hit_rates": {
                "domain_expert": hit_rate("domain_expert"),
                "mcp_agent": hit_rate("mcp_agent"),
            },
            "top_questions": self.top_questions(),
            "latency": {
                "domain_derive": self.latency_percentiles("domain_expert", "derive"),
                "domain_revise": self.latency_percentiles("domain_expert", "revise"),
                "mcp_assess": self.latency_percentiles("mcp_agent", "assess"),
            },
            "agent_event_count": self.connection.call(
                "read stream length", lambda client: client.xlen(self.keys.stream()), 0
            ),
        }
