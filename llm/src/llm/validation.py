"""Strict structural validation. Parsing is not validation.

`json.loads` succeeding proves the model emitted *well-formed* JSON. It proves
nothing about whether the model answered the question that was asked. Measured
against Z.AI's hosted GLM, a request for::

    {"rows": int, "grounded": bool, "quote": str}

came back as::

    {"rows_required": 250, "quoted_sentence": "..."}

HTTP 200, valid JSON, two fields renamed and one dropped. Downstream every
`.get()` misses, the values become `None`, and the system reports that the
corpus is silent while the model had in fact found and quoted the answer. No
exception is raised anywhere. That is the failure this module exists to stop.

So the pipeline is::

    tool call -> arguments -> json.loads -> SCHEMA + TYPE VALIDATION -> grounding

Structural validation and grounding validation are deliberately separate steps.
A structurally perfect object can still be factually ungrounded, and a
grounded value can still arrive in the wrong shape. Collapsing the two into one
weak check loses both guarantees.
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from jsonschema.validators import extend

from llm.contracts import SchemaViolation

__all__ = ["validate_against_schema", "strictened", "normalise_nullables"]

# Strings a model emits when it means JSON `null` but cannot produce it.
# Deliberately narrow: an empty string is *not* here, because "" is a legitimate
# value for several fields in this project (an absent counter-proposal, say) and
# collapsing it into None would erase a real distinction.
_NULL_WORDS = {"null", "none", "nil", "n/a", "na", "undefined", "nan"}


def _permits_null(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    declared = schema.get("type")
    if isinstance(declared, list):
        return "null" in declared
    if declared == "null":
        return True
    for key in ("anyOf", "oneOf"):
        for option in schema.get(key) or []:
            if _permits_null(option):
                return True
    return False


def normalise_nullables(payload: Any, schema: dict[str, Any]) -> Any:
    """Turn the *word* "null" into actual `None`, but only where null is allowed.

    Measured on glm-5.2: `unsupported_calculation`, declared `["string","null"]`,
    came back as the four-character string `"null"` on every attempt. It is a
    valid string, so strict validation passes it, and then it is *truthy* -
    which silently inverted the discussion's convergence test and meant the two
    agents could never agree on any question.

    That is the same failure as emitting `-1.0` for an absent integer: the model
    knows the answer is "nothing" and cannot say so in JSON. Correcting it here,
    at the seam, keeps every consumer from having to know the quirk.

    **Scoped to fields whose schema actually permits null.** A string field that
    does not allow null keeps the word verbatim - it might legitimately be about
    the concept.
    """
    if isinstance(payload, dict):
        properties = schema.get("properties") or {}
        out = {}
        for key, value in payload.items():
            sub = properties.get(key, {})
            if (isinstance(value, str) and value.strip().lower() in _NULL_WORDS
                    and _permits_null(sub)):
                out[key] = None
            else:
                out[key] = normalise_nullables(value, sub) if isinstance(
                    value, (dict, list)) else value
        return out
    if isinstance(payload, list):
        items = schema.get("items") or {}
        return [normalise_nullables(entry, items) for entry in payload]
    return payload


def _is_strict_integer(_checker: object, instance: object) -> bool:
    """`integer` means a Python `int`, not "a float that happens to be whole".

    JSON Schema accepts `10000.0` as an integer because its fractional part is
    zero. That is correct by the specification and wrong for this system: the
    value continues into the application as a Python `float`, and a row count of
    `0.0` is not the `None` the model meant to send.

    Measured on glm-4.5-air against the orchestrator's schema, a nullable
    integer came back as `0.0`, as `10000.0`, and once as a 1,000-digit integer.
    The first two are the dangerous ones precisely because the specification
    lets them through. `bool` is excluded too - `True` is an `int` in Python and
    is never a row count.
    """
    return isinstance(instance, int) and not isinstance(instance, bool)


def _is_strict_number(_checker: object, instance: object) -> bool:
    """`number` still accepts both, minus `bool`."""
    return isinstance(instance, (int, float)) and not isinstance(instance, bool)


_STRICT_TYPES = Draft202012Validator.TYPE_CHECKER.redefine_many({
    "integer": _is_strict_integer,
    "number": _is_strict_number,
})

StrictValidator = extend(Draft202012Validator, type_checker=_STRICT_TYPES)


def strictened(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `schema` that rejects unexpected properties.

    A schema silent on `additionalProperties` accepts anything extra, which is
    exactly how a renamed field slips through: `rows_required` is simply an
    additional property, and the *missing* `rows` is the only signal — one that
    disappears the moment a field is optional.

    Applied recursively, and only where the schema has not already made the
    decision itself.
    """
    if not isinstance(schema, dict):
        return schema

    out = dict(schema)
    if out.get("type") == "object" or "properties" in out:
        out.setdefault("additionalProperties", False)
        props = out.get("properties")
        if isinstance(props, dict):
            out["properties"] = {k: strictened(v) for k, v in props.items()}
    items = out.get("items")
    if isinstance(items, dict):
        out["items"] = strictened(items)
    for key in ("anyOf", "oneOf", "allOf"):
        if isinstance(out.get(key), list):
            out[key] = [strictened(s) for s in out[key]]
    return out


def validate_against_schema(payload: Any, schema: dict[str, Any], *,
                            context: str = "structured output") -> dict[str, Any]:
    """Validate `payload` against `schema`, or raise `SchemaViolation`.

    Every error is collected rather than only the first, because a model that
    got one field wrong has usually got several wrong, and a caller debugging a
    provider swap needs the whole picture in one message.
    """
    if not isinstance(payload, dict):
        raise SchemaViolation(
            f"{context}: expected a JSON object, got {type(payload).__name__}")

    # Repair the word "null" into real None *before* validating, so a field the
    # schema allows to be null is judged on what the model meant rather than on
    # how it failed to spell it. Structure only - no value is invented.
    payload = normalise_nullables(payload, schema)

    validator = StrictValidator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    if not errors:
        return payload

    raise SchemaViolation(f"{context}: {_describe(errors)}")


def _describe(errors: list[ValidationError]) -> str:
    parts = []
    for err in errors[:8]:
        where = ".".join(str(p) for p in err.absolute_path) or "(root)"
        parts.append(f"{where}: {err.message}")
    if len(errors) > 8:
        parts.append(f"... and {len(errors) - 8} more")
    return "; ".join(parts)
