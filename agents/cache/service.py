"""Shared Redis intelligence without changing the A2A agent boundary."""

from __future__ import annotations

import json
import logging
import time
from array import array
from collections.abc import Callable
from typing import Any, TypeVar

from agents.cache.client import RedisConnection
from agents.cache.config import RedisConfig
from agents.cache.fingerprints import (
    fingerprint,
    is_semantic_cache_reuse_safe,
)
from agents.cache.keys import KeyBuilder
from agents.cache.locks import RedisSingleFlight
from agents.cache.policies import policy_for
from agents.cache.rate_limit import RedisRateLimiter
from agents.cache.serialization import (
    CacheRequest,
    InvalidCacheEntry,
    build_envelope,
    load_result,
    utc_now,
    validate_envelope,
)
from agents.cache.telemetry import RedisTelemetry
from agents.redaction import contains_sensitive_data, redact_sensitive

LOGGER = logging.getLogger("agents.cache")
T = TypeVar("T")


def _execution_metadata() -> dict[str, Any]:
    try:
        from agents.a2a.executors import active_execution

        context = active_execution()
    except Exception:  # noqa: BLE001 - telemetry must not affect the task
        context = None
    if context is None:
        return {
            "request_id": "",
            "context_id": "",
            "task_id": "",
            "phase": "",
            "negotiation_round": 0,
        }
    return {
        "request_id": context.user_request_id,
        "context_id": context.context_id,
        "task_id": context.task_id,
        "phase": context.skill,
        "negotiation_round": _negotiation_round(context.call_chain),
    }


def _negotiation_round(chain: tuple[str, ...]) -> int:
    # Chains are implementation evidence, not a stable schema. Count completed
    # assessment calls instead of parsing a particular rendered path.
    return sum("assess_data_requirement" in item for item in chain)


def _last_call_stats() -> dict[str, Any]:
    try:
        from agents.observability import last_call_stats

        return dict(last_call_stats())
    except Exception:  # noqa: BLE001 - older/custom providers have no hook
        return {}


def _clear_call_stats() -> None:
    try:
        from agents.observability import clear_call_stats

        clear_call_stats()
    except Exception:  # noqa: BLE001 - optional provider measurement hook
        return


def _embedding_values(raw: Any) -> list[float]:
    if hasattr(raw, "tolist"):
        raw = raw.tolist()
    if isinstance(raw, tuple):
        raw = list(raw)
    if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], (list, tuple)):
        raw = list(raw[0])
    if not isinstance(raw, list) or not raw:
        raise ValueError("embedding provider returned no vector")
    return [float(value) for value in raw]


class NoOpIntelligence:
    """The exact original behavior when Redis is disabled."""

    enabled = False

    def configure_embedder(
        self, embedder: Callable[[str], Any] | None, embedding_model: str = ""
    ) -> None:
        del embedder, embedding_model

    def cached(
        self,
        request: CacheRequest,
        compute: Callable[[], T],
        *,
        cache_if: Callable[[T], bool] | None = None,
    ) -> T:
        del request, cache_if
        return compute()

    def allow_llm(self, agent: str) -> bool:
        del agent
        return True

    def observed(
        self, agent: str, operation: str, compute: Callable[[], T], *, question: str = ""
    ) -> T:
        del agent, operation, question
        return compute()

    def record_llm_call(self, *, agent: str, model: str, stats: dict[str, Any]) -> None:
        del agent, model, stats

    def record_negotiation(self, *, rounds: int, decision: str, request_id: str = "") -> None:
        del rounds, decision, request_id

    def complete_run(self, request_id: str, **details: Any) -> None:
        del request_id, details

    def health(self, *, include_analytics: bool = False) -> dict[str, Any]:
        del include_analytics
        return {
            "enabled": False,
            "required": False,
            "connected": False,
            "mode": "no-op",
            "reason": "REDIS_ENABLED is false",
        }

    def clear(self, scope: str = "all") -> dict[str, Any]:
        return {"scope": scope, "deleted": 0, "enabled": False}

    def close(self) -> None:
        return None


class RedisIntelligence:
    """Validated L1/L2 cache plus coordination and operational evidence."""

    enabled = True

    def __init__(
        self,
        config: RedisConfig,
        connection: RedisConnection,
        *,
        embedder: Callable[[str], Any] | None = None,
        embedding_model: str = "",
    ) -> None:
        self.config = config
        self.connection = connection
        self.keys = KeyBuilder(config.namespace)
        self.locks = RedisSingleFlight(connection, config)
        self.telemetry = RedisTelemetry(connection, config, self.keys)
        self.rate_limiter = RedisRateLimiter(connection, config, self.keys)
        self.embedder = embedder
        self.embedding_model = embedding_model
        self._semantic_dimension = 0
        self._semantic_index_ready = False

    def configure_embedder(
        self, embedder: Callable[[str], Any] | None, embedding_model: str = ""
    ) -> None:
        if embedder is not None:
            self.embedder = embedder
            self.embedding_model = embedding_model or self.embedding_model

    def allow_llm(self, agent: str) -> bool:
        return self.rate_limiter.allow(agent)

    def observed(
        self, agent: str, operation: str, compute: Callable[[], T], *, question: str = ""
    ) -> T:
        """Record an intentionally uncached operation, such as MCP execution."""
        started = time.perf_counter()
        if question and not contains_sensitive_data(question):
            self.telemetry.record_question(agent=agent, operation=operation, question=question)
        try:
            result = compute()
        except Exception as exc:
            self.telemetry.record_operation(
                {
                    **_execution_metadata(),
                    "event_type": "operation_completed",
                    "agent": agent,
                    "operation": operation,
                    "cache_status": "bypass",
                    "cache_type": "none",
                    "llm_called": False,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                    "result_status": "failed",
                    "failure_kind": type(exc).__name__,
                }
            )
            raise
        status = "completed"
        if isinstance(result, dict):
            status = (
                "input_required"
                if result.get("pending_input")
                else "failed"
                if result.get("error")
                else "completed"
            )
        self.telemetry.record_operation(
            {
                **_execution_metadata(),
                "event_type": "operation_completed",
                "agent": agent,
                "operation": operation,
                "cache_status": "bypass",
                "cache_type": "none",
                "llm_called": False,
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "result_status": status,
            }
        )
        return result

    def record_llm_call(self, *, agent: str, model: str, stats: dict[str, Any]) -> None:
        """Record non-specialist model calls that are outside cache wrappers."""
        self.telemetry.record_operation(
            {
                **_execution_metadata(),
                "event_type": "llm_call_completed",
                "agent": agent,
                "operation": "structured_call",
                "cache_status": "bypass",
                "cache_type": "none",
                "llm_called": bool(stats.get("calls")),
                "duration_ms": stats.get("duration_ms", 0),
                "model": model,
                "failure_kind": stats.get("failure_kind", ""),
                **_usage(stats),
            }
        )

    def cached(
        self,
        request: CacheRequest,
        compute: Callable[[], T],
        *,
        cache_if: Callable[[T], bool] | None = None,
    ) -> T:
        policy = policy_for(request.agent, request.operation, self.config)
        if not policy.exact or contains_sensitive_data(
            {"identity": request.identity, "question": request.canonical_question}
        ):
            return compute()

        digest = fingerprint(
            {
                "identity": request.identity,
                "versions": request.versions,
                "model": request.model or {},
                "result_kind": request.result_kind,
            }
        )
        key = self.keys.exact(request.agent, request.operation, digest)
        self.telemetry.record_question(
            agent=request.agent,
            operation=request.operation,
            question=request.canonical_question or request.operation,
            question_fingerprint=fingerprint(request.canonical_question or request.identity),
        )

        hit = self._load_exact(key, request, digest)
        if hit is not None:
            value, envelope, redis_ms = hit
            self._record_cache_event(request, "exact_hit", envelope, redis_latency_ms=redis_ms)
            self._touch(key)
            return value

        semantic = self._load_semantic(request) if policy.semantic else None
        if semantic is not None:
            value, envelope, similarity, redis_ms, semantic_key = semantic
            self._touch_semantic(semantic_key)
            self._promote_semantic(key, digest, request, envelope, policy.ttl_seconds)
            self._record_cache_event(
                request, "semantic_hit", envelope, redis_latency_ms=redis_ms, similarity=similarity
            )
            return value

        lease = self.locks.acquire(self.keys.lock(key))
        # SET returning false can mean contention or an unavailable Redis. A
        # quick bounded ping distinguishes the two; an outage computes now
        # instead of pretending another owner exists and waiting for minutes.
        if not lease.owned and self.connection.ping():
            waited = self.locks.wait_for(lambda: self._load_exact(key, request, digest))
            if waited is not None:
                value, envelope, redis_ms = waited  # type: ignore[misc]
                self._record_cache_event(request, "wait_hit", envelope, redis_latency_ms=redis_ms)
                self._touch(key)
                return value

        started = time.perf_counter()
        try:
            if policy.expensive_llm:
                _clear_call_stats()
            value = compute()
            duration_ms = round((time.perf_counter() - started) * 1000)
            stats = _last_call_stats() if policy.expensive_llm else {}
            allowed = cache_if(value) if cache_if is not None else True
            if allowed and not contains_sensitive_data(value):
                try:
                    envelope = build_envelope(
                        request,
                        key_fingerprint=digest,
                        result=value,
                        usage=_usage(stats),
                        duration_ms=duration_ms,
                    )
                    self._store_exact(key, envelope, policy.ttl_seconds)
                    if policy.semantic:
                        self._store_semantic(request, envelope)
                except Exception as exc:  # noqa: BLE001 - cache serialization is fail-open
                    LOGGER.warning(
                        "could not serialize %s.%s for Redis: %s",
                        request.agent,
                        request.operation,
                        exc,
                    )
            self._record_compute_event(request, duration_ms, stats, cache_status="miss")
            return value
        finally:
            self.locks.release(lease)

    def _load_exact(
        self, key: str, request: CacheRequest, digest: str
    ) -> tuple[Any, dict[str, Any], int] | None:
        started = time.perf_counter()
        raw = self.connection.call("read exact cache", lambda client: client.json().get(key), None)
        redis_ms = round((time.perf_counter() - started) * 1000)
        if raw is None:
            self._count_expired(key)
            return None
        try:
            envelope = validate_envelope(raw, request, key_fingerprint=digest)
            value = load_result(request.result_kind, envelope["result"])
        except (InvalidCacheEntry, TypeError, ValueError) as exc:
            LOGGER.warning("discarded invalid Redis entry %s: %s", key, exc)
            self._delete(key)
            self.telemetry.record_invalidation()
            return None
        return value, envelope, redis_ms

    def _store_exact(self, key: str, envelope: dict[str, Any], ttl: int) -> None:
        expires_at = time.time() + ttl

        def write(client):
            pipe = client.pipeline(transaction=False)
            pipe.json().set(key, "$", dict(redact_sensitive(envelope)))
            pipe.expire(key, ttl)
            pipe.zadd(self.keys.expiry_index(), {key: expires_at})
            pipe.execute()
            return True

        self.connection.call("write exact cache", write, False)

    def _touch(self, key: str) -> None:
        def update(client):
            pipe = client.pipeline(transaction=False)
            pipe.json().numincrby(key, "$.provenance.hit_count", 1)
            pipe.json().set(key, "$.provenance.last_accessed_at", utc_now())
            pipe.execute()
            return True

        self.connection.call("update cache provenance", update, False)

    def _delete(self, key: str) -> None:
        def remove(client):
            pipe = client.pipeline(transaction=False)
            pipe.unlink(key)
            pipe.zrem(self.keys.expiry_index(), key)
            pipe.execute()
            return True

        self.connection.call("remove cache entry", remove, False)

    def _count_expired(self, key: str) -> None:
        score = self.connection.call(
            "check cache expiry", lambda client: client.zscore(self.keys.expiry_index(), key), None
        )
        if score is not None and float(score) <= time.time():
            self.connection.call(
                "remove expiry marker", lambda client: client.zrem(self.keys.expiry_index(), key), 0
            )
            self.telemetry.record_expiration()

    def _ensure_semantic_index(self, dimension: int) -> bool:
        if self._semantic_index_ready and self._semantic_dimension == dimension:
            return True

        def create(client):
            try:
                client.execute_command(
                    "FT.CREATE",
                    self.keys.semantic_index(),
                    "ON",
                    "JSON",
                    "PREFIX",
                    1,
                    self.keys.semantic_prefix(),
                    "SCHEMA",
                    "$.agent",
                    "AS",
                    "agent",
                    "TAG",
                    "$.operation",
                    "AS",
                    "operation",
                    "TAG",
                    "$.embedding_model",
                    "AS",
                    "embedding_model",
                    "TAG",
                    "$.embedding",
                    "AS",
                    "embedding",
                    "VECTOR",
                    "FLAT",
                    6,
                    "TYPE",
                    "FLOAT32",
                    "DIM",
                    dimension,
                    "DISTANCE_METRIC",
                    "COSINE",
                )
            except Exception as exc:
                if "Index already exists" not in str(exc):
                    raise
            return True

        ready = bool(self.connection.call("create semantic index", create, False))
        if ready:
            self._semantic_dimension = dimension
            self._semantic_index_ready = True
        return ready

    def _embed(self, text: str) -> list[float] | None:
        if self.embedder is None or not text:
            return None
        try:
            return _embedding_values(self.embedder(text))
        except Exception as exc:  # noqa: BLE001 - L2 failure is an L1 miss
            LOGGER.warning("semantic embedding unavailable: %s", exc)
            return None

    def _load_semantic(
        self,
        request: CacheRequest,
    ) -> tuple[Any, dict[str, Any], float, int, str] | None:
        if not request.semantic_signature or not request.canonical_question:
            return None
        embedding = self._embed(request.canonical_question)
        if not embedding or not self._ensure_semantic_index(len(embedding)):
            return None
        vector = array("f", embedding).tobytes()
        query = (
            f"(@agent:{{{request.agent}}} @operation:{{{request.operation}}})"
            f"=>[KNN {self.config.semantic_candidates} "
            "@embedding $query_vector AS vector_distance]"
        )
        started = time.perf_counter()
        rows = self.connection.call(
            "search semantic cache",
            lambda client: client.execute_command(
                "FT.SEARCH",
                self.keys.semantic_index(),
                query,
                "PARAMS",
                2,
                "query_vector",
                vector,
                "SORTBY",
                "vector_distance",
                "ASC",
                "RETURN",
                2,
                "$",
                "vector_distance",
                "DIALECT",
                2,
            ),
            [],
        )
        redis_ms = round((time.perf_counter() - started) * 1000)
        for document in self._semantic_documents(rows):
            envelope = document["envelope"]
            similarity = 1.0 - document["distance"]
            provenance = envelope.get("provenance") or {}
            candidate_model = {
                "provider": str(provenance.get("provider") or ""),
                "model": str(provenance.get("model") or ""),
            }
            model_matches = candidate_model == {
                "provider": str((request.model or {}).get("provider") or ""),
                "model": str((request.model or {}).get("model") or ""),
            }
            embedding_matches = document.get("embedding_model") == (
                self.embedding_model or "unknown"
            )
            safe, reason = is_semantic_cache_reuse_safe(
                request.semantic_signature,
                envelope.get("semantic_signature") or {},
                query_versions=request.versions,
                candidate_versions=envelope.get("versions") or {},
                similarity=similarity,
                threshold=self.config.semantic_similarity_threshold,
            )
            if not model_matches:
                safe, reason = False, "model_identity_mismatch"
            elif not embedding_matches:
                safe, reason = False, "embedding_model_mismatch"
            if not safe:
                if similarity >= self.config.semantic_similarity_threshold:
                    self.telemetry.record_operation(
                        {
                            **_execution_metadata(),
                            "event_type": "cache_rejected",
                            "agent": request.agent,
                            "operation": request.operation,
                            "cache_status": "bypass",
                            "cache_type": "semantic",
                            "llm_called": False,
                            "failure_kind": "semantic_safety_rejected",
                            "semantic_similarity": similarity,
                            "reason": reason,
                        }
                    )
                continue
            try:
                # The candidate fingerprint validates its own immutable entry;
                # structured safety above validates equivalence to this query.
                candidate_request = CacheRequest(
                    agent=request.agent,
                    operation=request.operation,
                    identity=envelope.get("identity") or {},
                    versions=request.versions,
                    result_kind=request.result_kind,
                )
                validate_envelope(
                    envelope,
                    candidate_request,
                    key_fingerprint=str(envelope.get("key_fingerprint") or ""),
                )
                value = load_result(request.result_kind, envelope["result"])
            except (InvalidCacheEntry, TypeError, ValueError):
                self._delete(document["key"])
                self.telemetry.record_invalidation()
                continue
            return value, envelope, similarity, redis_ms, document["key"]
        return None

    def _touch_semantic(self, key: str) -> None:
        def update(client):
            pipe = client.pipeline(transaction=False)
            pipe.json().numincrby(key, "$.envelope.provenance.hit_count", 1)
            pipe.json().set(key, "$.envelope.provenance.last_accessed_at", utc_now())
            pipe.execute()
            return True

        self.connection.call("update semantic provenance", update, False)

    @staticmethod
    def _semantic_documents(rows: Any) -> list[dict[str, Any]]:
        if not isinstance(rows, list) or len(rows) < 3:
            return []
        documents: list[dict[str, Any]] = []
        for index in range(1, len(rows), 2):
            if index + 1 >= len(rows):
                break
            key, fields = str(rows[index]), rows[index + 1]
            if not isinstance(fields, list):
                continue
            mapping = {str(fields[pos]): fields[pos + 1] for pos in range(0, len(fields) - 1, 2)}
            try:
                root = json.loads(mapping.get("$") or "{}")
                if isinstance(root, list):
                    root = root[0]
                envelope = root.get("envelope")
                if not isinstance(envelope, dict):
                    continue
                documents.append(
                    {
                        "key": key,
                        "envelope": envelope,
                        "embedding_model": str(root.get("embedding_model") or ""),
                        "distance": float(mapping["vector_distance"]),
                    }
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return documents

    def _store_semantic(self, request: CacheRequest, envelope: dict[str, Any]) -> None:
        if not request.semantic_signature or not request.canonical_question:
            return
        embedding = self._embed(request.canonical_question)
        if not embedding or not self._ensure_semantic_index(len(embedding)):
            return
        digest = fingerprint(
            {
                "question": request.canonical_question,
                "signature": request.semantic_signature,
                "versions": request.versions,
            }
        )
        key = self.keys.semantic(request.agent, request.operation, digest)
        semantic_envelope = dict(envelope)
        semantic_envelope["provenance"] = {
            **envelope.get("provenance", {}),
            "cache_type": "semantic",
        }
        document = {
            "agent": request.agent,
            "operation": request.operation,
            "embedding_model": self.embedding_model or "unknown",
            "embedding": embedding,
            "envelope": semantic_envelope,
        }
        self.connection.call(
            "write semantic cache",
            lambda client: (
                client.json().set(key, "$", dict(redact_sensitive(document))),
                client.expire(key, self.config.semantic_ttl),
            ),
            None,
        )

    def _promote_semantic(
        self, key: str, digest: str, request: CacheRequest, candidate: dict[str, Any], ttl: int
    ) -> None:
        promoted = dict(candidate)
        promoted.update(
            {
                "key_fingerprint": digest,
                "identity": request.identity,
                "canonical_question": request.canonical_question,
            }
        )
        promoted["provenance"] = {
            **candidate.get("provenance", {}),
            "cache_type": "semantic_promoted",
            "last_accessed_at": utc_now(),
        }
        self._store_exact(key, promoted, ttl)

    def _record_cache_event(
        self,
        request: CacheRequest,
        status: str,
        envelope: dict[str, Any],
        *,
        redis_latency_ms: int,
        similarity: float | None = None,
    ) -> None:
        provenance = envelope.get("provenance") or {}
        usage = provenance.get("historical_usage") or {}
        event = {
            **_execution_metadata(),
            "event_type": "cache_reuse",
            "agent": request.agent,
            "operation": request.operation,
            "cache_status": status,
            "cache_type": "semantic" if status == "semantic_hit" else "exact",
            "llm_called": False,
            "result_status": "completed",
            "saved_llm_call": policy_for(
                request.agent, request.operation, self.config
            ).expensive_llm,
            "estimated_tokens_saved": usage.get("total_tokens", 0),
            "estimated_latency_saved_ms": provenance.get("historical_uncached_duration_ms", 0),
            "redis_latency_ms": redis_latency_ms,
            "model": (request.model or {}).get("model", ""),
        }
        if similarity is not None:
            event["semantic_similarity"] = round(similarity, 8)
        self.telemetry.record_operation(event)

    def _record_compute_event(
        self, request: CacheRequest, duration_ms: int, stats: dict[str, Any], *, cache_status: str
    ) -> None:
        self.telemetry.record_operation(
            {
                **_execution_metadata(),
                "event_type": "operation_completed",
                "agent": request.agent,
                "operation": request.operation,
                "cache_status": cache_status,
                "cache_type": "exact",
                "duration_ms": duration_ms,
                "llm_called": bool(stats.get("calls")),
                "retries": max(0, int(stats.get("calls") or 0) - 1),
                "model": (request.model or {}).get("model", ""),
                "failure_kind": stats.get("failure_kind", ""),
                "result_status": "failed" if stats.get("failure_kind") else "completed",
                **_usage(stats),
            }
        )

    def record_negotiation(self, *, rounds: int, decision: str, request_id: str = "") -> None:
        self.telemetry.record_negotiation(rounds=rounds, decision=decision, request_id=request_id)

    def complete_run(self, request_id: str, **details: Any) -> None:
        self.telemetry.complete_run(request_id, **details)

    def health(self, *, include_analytics: bool = False) -> dict[str, Any]:
        health = self.connection.health()
        health.update(
            {
                "mode": "redis",
                "config": self.config.redacted(),
                "embedding_model": self.embedding_model or None,
            }
        )
        if include_analytics and health.get("connected"):
            health["analytics"] = self.telemetry.snapshot()
        return health

    def clear(self, scope: str = "all") -> dict[str, Any]:
        if scope not in {"all", "domain", "mcp", "semantic"}:
            raise ValueError("scope must be all, domain, mcp, or semantic")
        patterns = [self.keys.cache_pattern(scope)]
        if scope == "all":
            patterns.append(self.keys.cache_pattern("semantic"))
        deleted = 0
        for pattern in patterns:
            keys = self.connection.call(
                "scan cache entries",
                lambda client, p=pattern: list(client.scan_iter(match=p, count=500)),
                [],
            )
            for start in range(0, len(keys), 500):
                batch = keys[start : start + 500]
                if batch:
                    deleted += int(
                        self.connection.call(
                            "clear cache entries", lambda client, b=batch: client.unlink(*b), 0
                        )
                    )
        self.telemetry.record_invalidation(deleted)
        return {"scope": scope, "deleted": deleted, "enabled": True}

    def close(self) -> None:
        self.connection.close()


def _usage(stats: dict[str, Any]) -> dict[str, int]:
    usage = stats.get("usage") if isinstance(stats.get("usage"), dict) else stats
    out: dict[str, int] = {}
    for name in (
        "prompt_tokens",
        "reasoning_tokens",
        "completion_tokens",
        "total_tokens",
        "input_tokens",
        "output_tokens",
    ):
        try:
            value = int(usage.get(name) or 0)
        except (TypeError, ValueError):
            value = 0
        if value:
            out[name] = value
    if "total_tokens" not in out:
        total = out.get("prompt_tokens", out.get("input_tokens", 0)) + out.get(
            "completion_tokens", out.get("output_tokens", 0)
        )
        if total:
            out["total_tokens"] = total
    return out
