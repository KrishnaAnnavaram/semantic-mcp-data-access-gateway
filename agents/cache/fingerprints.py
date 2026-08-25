"""Canonical, bounded identities for exact and semantically equivalent work."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from typing import Any

from agents.cache.versions import SEMANTIC_POLICY_VERSION

_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9%._:/-]+")
_SENSITIVE_LIST_KEYS = frozenset(
    {
        "fields",
        "tenors",
        "candidate_fields",
        "available_fields",
        "unsupported_fields",
        "unnecessary_fields",
        "available_tools",
        "requested_fields",
        "tools",
        "limitations",
        "assumptions",
    }
)
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twenty": 20,
    "thirty": 30,
}
_MONTHS = (
    "january|february|march|april|may|june|july|august|september|"
    "october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)


def canonical_question(text: str) -> str:
    """Lowercase and normalize typography without rewriting meaning."""
    value = (text or "").strip().lower()
    value = value.replace("–", "-").replace("—", "-").replace("’", "'")
    value = _PUNCT.sub(" ", value)
    return _SPACE.sub(" ", value).strip()[:2_000]


def canonicalize(value: Any, *, key: str = "") -> Any:
    """A JSON-safe form where only analytically unordered lists are sorted."""
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    elif hasattr(value, "as_dict") and callable(value.as_dict):
        value = value.as_dict()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(k): canonicalize(v, key=str(k))
            for k, v in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [canonicalize(item, key=key) for item in value]
        if key in _SENSITIVE_LIST_KEYS or isinstance(value, (set, frozenset)):
            return sorted(items, key=_canonical_json)
        return items
    if isinstance(value, float):
        return round(value, 12)
    if isinstance(value, str):
        return _SPACE.sub(" ", value.strip())
    if value is None or isinstance(value, (bool, int)):
        return value
    return str(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def fingerprint(value: Any) -> str:
    payload = _canonical_json(canonicalize(value)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def combine_versions(*versions: str) -> str:
    clean = [str(version) for version in versions if version]
    return fingerprint(clean) if clean else ""


def catalogue_fingerprint(catalogue: Any, *, backend: str = "") -> str:
    return fingerprint({"backend": backend, "catalogue": canonicalize(catalogue)})


def model_identity(call_site: Any) -> dict[str, str]:
    """Configured provider/model without constructing a credentialed client."""
    try:
        from llm import provider_status

        status = provider_status()
        site = getattr(call_site, "value", str(call_site))
        return {
            "provider": str(status.get("backend") or "unknown"),
            "model": str((status.get("models") or {}).get(site) or "unknown"),
        }
    except Exception:  # noqa: BLE001 - a missing identity disables stale reuse
        return {"provider": "unknown", "model": "unknown"}


def _word_or_number(value: str) -> int | None:
    value = value.lower()
    if value.isdigit():
        return int(value)
    return _NUMBER_WORDS.get(value)


def analytical_signature(
    question: str,
    *,
    task: str = "",
    requested_fields: list[str] | None = None,
    requested_rows: int | None = None,
    prior_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract only dimensions whose equality can authorize semantic reuse.

    It is intentionally conservative. Vector similarity proposes a candidate;
    every material analytical dimension below must then be identical.
    """
    text = canonical_question(f"{question} {task}")
    prior = canonicalize(prior_plan or {})
    prior_params = prior.get("calculation_params", {}) if isinstance(prior, dict) else {}
    prior_calculation = str(prior.get("calculation") or "") if isinstance(prior, dict) else ""

    metric = ""
    if "expected shortfall" in text or re.search(r"\bes\b", text):
        metric = "expected_shortfall"
    elif "value at risk" in text or re.search(r"\bvar\b", text):
        metric = "historical_var" if "historical" in text else "var"
    elif "dv01" in text or "pv01" in text:
        metric = "dv01"
    elif "2s10s" in text or "curve slope" in text or "steepness" in text:
        metric = "curve_slope"
    elif "stress" in text or "shock" in text:
        metric = "stress"
    elif "curve" in text or "treasury rate" in text or "yield" in text:
        metric = "curve_data"
    elif prior_calculation:
        if "var" in prior_calculation or "risk" in prior_calculation:
            metric = "var"
        elif "dv01" in prior_calculation or "sensitiv" in prior_calculation:
            metric = "dv01"
        elif "stress" in prior_calculation:
            metric = "stress"

    method = ""
    if "monte carlo" in text or "simulation" in text:
        method = "monte_carlo"
    elif "parametric" in text or "delta normal" in text or "variance covariance" in text:
        method = "parametric"
    elif "historical simulation" in text or (
        "historical" in text and metric in {"var", "historical_var", "expected_shortfall"}
    ):
        method = "historical_simulation"
    elif "compare" in text and metric in {"var", "historical_var", "expected_shortfall"}:
        method = "compare_methods"
    elif prior_calculation:
        method = prior_calculation

    confidence = None
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*%", text)
    if match:
        confidence = round(float(match.group(1)) / 100.0, 8)

    horizon = None
    match = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty)"
        r"\s*[- ]?day\b",
        text,
    )
    if match:
        horizon = _word_or_number(match.group(1))

    lookback = None
    match = re.search(
        r"\b(?:last|past|most recent)?\s*(\d+)\s+(?:trading\s+)?days?"
        r"\s+(?:of\s+)?(?:history|lookback)",
        text,
    )
    if match:
        lookback = int(match.group(1))

    tenors: set[str] = set()
    slope = re.search(r"\b(\d{1,2})s(\d{1,2})s\b", text)
    if slope:
        tenors.update({f"y{slope.group(1)}", f"y{slope.group(2)}"})
    for amount, unit in re.findall(r"\b(\d+(?:\.\d+)?)\s*[- ]?(month|year)s?\b", text):
        value = float(amount)
        if unit == "year" and value.is_integer():
            tenors.add(f"y{int(value)}")
        elif unit == "month":
            tenors.add(f"m{str(value).rstrip('0').rstrip('.')}")
    if not tenors and isinstance(prior, dict):
        tenors.update(str(value) for value in prior.get("tenors") or [])

    if re.search(r"\b(?:tips|real yield|real rate|inflation[- ]linked)\b", text):
        curve_family = "real"
    elif re.search(r"\bnominal\b", text):
        curve_family = "nominal"
    else:
        curve_family = str(prior.get("curve_family") or "unspecified")

    iso_dates = sorted(set(re.findall(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b", text)))
    years = sorted(set(re.findall(r"\b(?:19|20)\d{2}\b", text)))
    named_dates = sorted(
        set(re.findall(rf"\b(?:{_MONTHS})\s+(?:\d{{1,2}}\s+)?(?:19|20)\d{{2}}\b", text))
    )
    temporal_values = sorted(set(iso_dates + named_dates + years))
    prior_temporal = prior.get("temporal") or {} if isinstance(prior, dict) else {}
    if not temporal_values and isinstance(prior_temporal, dict):
        temporal_values = sorted(
            str(prior_temporal[name])
            for name in ("as_of_date", "start_date", "end_date")
            if prior_temporal.get(name)
        )
    temporal_mode = "historical" if temporal_values else "latest"

    if lookback is None and isinstance(prior_temporal, dict):
        lookback = prior_temporal.get("lookback_days")

    scenario = ""
    for name in (
        "parallel_up",
        "parallel_down",
        "bear_steepener",
        "bull_steepener",
        "bear_flattener",
        "bull_flattener",
        "belly_selloff",
        "belly_rally",
        "wings_selloff",
        "wings_rally",
        "twist",
    ):
        if name.replace("_", " ") in text:
            scenario = name
            break
    scenario = scenario or str(prior_params.get("scenario") or "")

    shock = re.search(r"(?<!\d)([-+]?\d+(?:\.\d+)?)\s*(?:bp|basis point)", text)
    shock_bp = (
        float(shock.group(1))
        if shock
        else prior_params.get("shock_bp", prior_params.get("severity_bp"))
    )
    numbers = sorted(set(re.findall(r"(?<![a-z])[-+]?\d+(?:\.\d+)?", text)))
    portfolio = str(prior_params.get("portfolio_id") or prior.get("portfolio", ""))
    portfolio_match = re.search(r"\b(?:portfolio|book)\s+(?:id\s+)?([a-z0-9_-]+)\b", text)
    if portfolio_match:
        portfolio = portfolio_match.group(1)

    return {
        "policy_version": SEMANTIC_POLICY_VERSION,
        "metric": metric,
        "method": method,
        "confidence_level": confidence
        if confidence is not None
        else prior_params.get("confidence_level"),
        "horizon_days": horizon if horizon is not None else prior_params.get("horizon_days"),
        "lookback_days": lookback,
        "curve_family": curve_family,
        "tenors": sorted(tenors),
        "temporal_mode": temporal_mode,
        "temporal_values": temporal_values,
        "requested_fields": sorted(set(requested_fields or prior.get("fields") or [])),
        "requested_rows": requested_rows if requested_rows is not None else prior.get("rows"),
        "portfolio": portfolio,
        "scenario": scenario,
        "shock_bp": shock_bp,
        "numbers": numbers,
        "calculation_params": prior_params,
    }


def is_semantic_cache_reuse_safe(
    query_signature: Mapping[str, Any],
    candidate_signature: Mapping[str, Any],
    *,
    query_versions: Mapping[str, Any],
    candidate_versions: Mapping[str, Any],
    similarity: float,
    threshold: float,
) -> tuple[bool, str]:
    """Authorize reuse only after vector and structured equivalence both pass."""
    if similarity < threshold:
        return False, "below_similarity_threshold"
    if not query_signature.get("metric"):
        return False, "missing_metric_signature"
    if canonicalize(query_versions) != canonicalize(candidate_versions):
        return False, "version_mismatch"
    material = (
        "policy_version",
        "metric",
        "method",
        "confidence_level",
        "horizon_days",
        "lookback_days",
        "curve_family",
        "tenors",
        "temporal_mode",
        "temporal_values",
        "requested_fields",
        "requested_rows",
        "portfolio",
        "scenario",
        "shock_bp",
        "numbers",
        "calculation_params",
    )
    for name in material:
        if canonicalize(query_signature.get(name), key=name) != canonicalize(
            candidate_signature.get(name), key=name
        ):
            return False, f"analytical_mismatch:{name}"
    return True, "equivalent"
