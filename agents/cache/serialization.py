"""Validated serialization for Redis JSON cache entries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agents.a2a.envelope import (
    catalogue_from_dict,
    requirement_from_dict,
    serve_response_from_dict,
    validation_from_dict,
)
from agents.cache.versions import CACHE_ENVELOPE_SCHEMA_VERSION
from agents.contracts import KnowledgeChunk


class InvalidCacheEntry(ValueError):
    """A Redis object no longer satisfies the current application contract."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class CacheRequest:
    agent: str
    operation: str
    identity: dict[str, Any]
    versions: dict[str, str]
    result_kind: str
    canonical_question: str = ""
    semantic_signature: dict[str, Any] | None = None
    model: dict[str, str] | None = None


def build_envelope(
    request: CacheRequest,
    *,
    key_fingerprint: str,
    result: Any,
    usage: dict[str, int] | None,
    duration_ms: int,
    cache_type: str = "exact",
) -> dict[str, Any]:
    now = utc_now()
    dumped = dump_result(request.result_kind, result)
    # Validate before persistence as well as after retrieval. Redis must never
    # become the place an invalid in-memory result first looks legitimate.
    load_result(request.result_kind, dumped)
    return {
        "schema_version": CACHE_ENVELOPE_SCHEMA_VERSION,
        "key_fingerprint": key_fingerprint,
        "agent": request.agent,
        "operation": request.operation,
        "result_kind": request.result_kind,
        "identity": request.identity,
        "versions": request.versions,
        "canonical_question": request.canonical_question,
        "semantic_signature": request.semantic_signature or {},
        "result": dumped,
        "provenance": {
            "cache_type": cache_type,
            "source_operation": request.operation,
            "agent": request.agent,
            "provider": (request.model or {}).get("provider", ""),
            "model": (request.model or {}).get("model", ""),
            "created_at": now,
            "last_accessed_at": now,
            "hit_count": 0,
            "historical_usage": dict(usage or {}),
            "historical_uncached_duration_ms": max(0, int(duration_ms)),
        },
    }


def validate_envelope(raw: Any, request: CacheRequest, *, key_fingerprint: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise InvalidCacheEntry("cache root is not an object")
    required = {
        "schema_version",
        "key_fingerprint",
        "agent",
        "operation",
        "result_kind",
        "identity",
        "versions",
        "result",
        "provenance",
    }
    missing = sorted(required - set(raw))
    if missing:
        raise InvalidCacheEntry(f"cache envelope misses {missing}")
    expected = {
        "schema_version": CACHE_ENVELOPE_SCHEMA_VERSION,
        "key_fingerprint": key_fingerprint,
        "agent": request.agent,
        "operation": request.operation,
        "result_kind": request.result_kind,
        "versions": request.versions,
    }
    for field, value in expected.items():
        if raw.get(field) != value:
            raise InvalidCacheEntry(f"cache envelope {field} does not match")
    if not isinstance(raw.get("identity"), dict):
        raise InvalidCacheEntry("cache identity is not an object")
    if raw.get("identity") != request.identity:
        raise InvalidCacheEntry("cache envelope identity does not match")
    if not isinstance(raw.get("provenance"), dict):
        raise InvalidCacheEntry("cache provenance is not an object")
    return raw


def _require_object(value: Any, required: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidCacheEntry(f"{name} is not an object")
    missing = sorted(required - set(value))
    if missing:
        raise InvalidCacheEntry(f"{name} misses {missing}")
    return value


def _require_list(data: dict[str, Any], fields: tuple[str, ...], name: str) -> None:
    wrong = [field for field in fields if not isinstance(data.get(field), list)]
    if wrong:
        raise InvalidCacheEntry(f"{name} list field(s) have the wrong type: {wrong}")


def _require_strings(data: dict[str, Any], fields: tuple[str, ...], name: str) -> None:
    wrong = [field for field in fields if not isinstance(data.get(field), str)]
    if wrong:
        raise InvalidCacheEntry(f"{name} string field(s) have the wrong type: {wrong}")


_REQUIREMENT_FIELDS = {
    "task",
    "answerable",
    "fields",
    "field_notes",
    "rows",
    "row_reason",
    "row_quote",
    "grounded",
    "tenors",
    "curve_family",
    "temporal",
    "decision",
    "is_hypothesis",
    "candidate_fields",
    "open_questions",
    "assumptions",
    "limitations",
    "calculation",
    "calculation_params",
    "unanswerable_reason",
    "blocked_by",
    "citations",
    "warnings",
}
_SERVE_FIELDS = {
    "feasible",
    "available_fields",
    "unsupported_fields",
    "unnecessary_fields",
    "unsupported_calculation",
    "available_tools",
    "max_rows_available",
    "temporal_constraints",
    "constraints",
    "counter_proposal",
    "answered_questions",
    "open_questions",
    "notes",
}
_CATALOGUE_FIELDS = {"tools", "fields", "tenors", "can_calculate", "notes"}
_VALIDATION_FIELDS = {"verdict", "checks", "mismatches", "warnings", "interpretation"}


def _dump_chunk(chunk: KnowledgeChunk) -> dict[str, Any]:
    return {
        "domain": chunk.domain,
        "source": chunk.source,
        "heading": chunk.heading,
        "text": chunk.text,
        "distance": chunk.distance,
        "collection": chunk.collection,
        "chunk_id": chunk.chunk_id,
        "score": chunk.score,
        "document_path": chunk.document_path,
        "line_start": chunk.line_start,
        "line_end": chunk.line_end,
        "retrieval_query": chunk.retrieval_query,
    }


def _load_chunks(value: Any) -> list[KnowledgeChunk]:
    if not isinstance(value, list):
        raise InvalidCacheEntry("knowledge chunks are not a list")
    chunks: list[KnowledgeChunk] = []
    for raw in value:
        data = _require_object(
            raw,
            {"domain", "source", "heading", "text", "distance", "collection"},
            "knowledge chunk",
        )
        if not isinstance(data["text"], str) or not isinstance(data["distance"], (int, float)):
            raise InvalidCacheEntry("knowledge chunk text/distance has the wrong type")
        chunks.append(
            KnowledgeChunk(
                domain=str(data["domain"]),
                source=str(data["source"]),
                heading=str(data["heading"]),
                text=data["text"],
                distance=float(data["distance"]),
                collection=str(data["collection"]),
                chunk_id=str(data.get("chunk_id") or ""),
                score=(
                    float(data["score"]) if isinstance(data.get("score"), (int, float)) else None
                ),
                document_path=str(data.get("document_path") or ""),
                line_start=data.get("line_start"),
                line_end=data.get("line_end"),
                retrieval_query=str(data.get("retrieval_query") or ""),
            )
        )
    return chunks


def dump_result(kind: str, value: Any) -> Any:
    if kind == "requirement_with_chunks":
        requirement, chunks = value
        return {
            "requirement": requirement.as_dict(),
            "chunks": [_dump_chunk(chunk) for chunk in chunks],
        }
    if kind == "knowledge_chunks":
        return [_dump_chunk(chunk) for chunk in value]
    if kind in {"requirement", "serve_response", "tool_catalogue", "result_validation"}:
        return value.as_dict()
    if kind in {"choices", "json"} and isinstance(value, dict):
        return value
    raise InvalidCacheEntry(f"unsupported result kind {kind!r}")


def load_result(kind: str, value: Any) -> Any:
    if kind == "requirement_with_chunks":
        root = _require_object(value, {"requirement", "chunks"}, kind)
        requirement = load_result("requirement", root["requirement"])
        return requirement, _load_chunks(root["chunks"])
    if kind == "knowledge_chunks":
        return _load_chunks(value)
    if kind == "requirement":
        data = _require_object(value, _REQUIREMENT_FIELDS, kind)
        if not isinstance(data["answerable"], bool):
            raise InvalidCacheEntry("requirement answerable is not boolean")
        _require_list(
            data,
            (
                "fields",
                "field_notes",
                "tenors",
                "candidate_fields",
                "open_questions",
                "assumptions",
                "limitations",
                "citations",
                "warnings",
            ),
            kind,
        )
        _require_strings(data, ("task", "row_reason", "curve_family", "blocked_by"), kind)
        if data["rows"] is not None and (
            isinstance(data["rows"], bool) or not isinstance(data["rows"], int)
        ):
            raise InvalidCacheEntry("requirement rows is not an integer or null")
        if not isinstance(data["grounded"], bool):
            raise InvalidCacheEntry("requirement grounded is not boolean")
        if not isinstance(data["temporal"], dict):
            raise InvalidCacheEntry("requirement temporal is not an object")
        if not isinstance(data["calculation_params"], dict):
            raise InvalidCacheEntry("requirement calculation_params is not an object")
        if data["decision"] not in {
            None,
            "AGREED",
            "NEEDS_USER_INPUT",
            "UNSUPPORTED",
            "CANNOT_REACH_AGREEMENT",
        }:
            raise InvalidCacheEntry("requirement decision is unreadable")
        if not all(isinstance(note, dict) for note in data["field_notes"]):
            raise InvalidCacheEntry("requirement field notes are not objects")
        restored = requirement_from_dict(data)
        if restored is None:
            raise InvalidCacheEntry("requirement could not be rebuilt")
        return restored
    if kind == "serve_response":
        data = _require_object(value, _SERVE_FIELDS, kind)
        if not isinstance(data["feasible"], bool):
            raise InvalidCacheEntry("serve response feasible is not boolean")
        _require_list(
            data,
            (
                "available_fields",
                "unsupported_fields",
                "unnecessary_fields",
                "available_tools",
                "temporal_constraints",
                "constraints",
                "answered_questions",
                "open_questions",
                "notes",
            ),
            kind,
        )
        _require_strings(data, ("counter_proposal",), kind)
        if data["max_rows_available"] is not None and (
            isinstance(data["max_rows_available"], bool)
            or not isinstance(data["max_rows_available"], int)
        ):
            raise InvalidCacheEntry("serve response max rows is invalid")
        return serve_response_from_dict(data)
    if kind == "tool_catalogue":
        data = _require_object(value, _CATALOGUE_FIELDS, kind)
        if not isinstance(data["can_calculate"], bool):
            raise InvalidCacheEntry("catalogue can_calculate is not boolean")
        _require_list(data, ("tools", "fields", "tenors", "notes"), kind)
        if not all(isinstance(tool, dict) for tool in data["tools"]):
            raise InvalidCacheEntry("catalogue tools are not objects")
        restored = catalogue_from_dict(data)
        if restored is None:
            raise InvalidCacheEntry("catalogue could not be rebuilt")
        return restored
    if kind == "result_validation":
        data = _require_object(value, _VALIDATION_FIELDS, kind)
        if data["verdict"] not in {"VALID", "VALID_WITH_WARNINGS", "INVALID"}:
            raise InvalidCacheEntry("validation verdict is unreadable")
        _require_list(data, ("checks", "mismatches", "warnings"), kind)
        _require_strings(data, ("interpretation",), kind)
        restored = validation_from_dict(data)
        if restored is None or restored.verdict == "INVALID" and data.get("verdict") != "INVALID":
            raise InvalidCacheEntry("validation verdict is unreadable")
        return restored
    if kind == "choices":
        data = _require_object(value, {"portfolios", "scenarios", "curve_families", "tenors"}, kind)
        _require_list(data, ("portfolios", "scenarios", "curve_families", "tenors"), kind)
        if data.get("availability_warnings") is not None and not isinstance(
            data["availability_warnings"], list
        ):
            raise InvalidCacheEntry("choices availability warnings are not a list")
        return data
    if kind == "json":
        if not isinstance(value, dict):
            raise InvalidCacheEntry(f"{kind} is not an object")
        return value
    raise InvalidCacheEntry(f"unsupported result kind {kind!r}")


def result_loader(kind: str) -> Callable[[Any], Any]:
    return lambda value: load_result(kind, value)
