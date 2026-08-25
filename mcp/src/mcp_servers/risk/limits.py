"""Limit utilisation.  `explicit_threshold_utilisation_v1`

Arithmetic so simple it barely needs a module, wrapped in the one discipline
that makes it safe: **this engine holds no risk policy and will not invent
one.**

Every limit is an explicit typed input - the metric, the amount, and the amber
threshold. There is no default limit anywhere, no "typical" DV01 cap, no
house view about what a reasonable VaR is. The reason is not caution. A
threshold that appears in a report without a stated source becomes policy by
accident: it is quoted, then relied on, and by the time anyone asks where it
came from the answer is "the system". A limit is a decision somebody made, and
this module's job is to compare against it, not to supply it.

The one number with a default is `amber_utilisation_percent`, at 80%. That is a
convention rather than a rule, it is per-limit and overridable, and it is
returned in every result so it is never implicit.

## Status boundaries, stated exactly

    utilisation < amber              -> GREEN
    amber <= utilisation < 100       -> AMBER
    utilisation >= 100               -> RED

Both boundaries are closed from below, so a metric exactly at the amber
threshold is AMBER and a metric exactly at the limit is RED. "At the limit" is a
breach: a limit is the largest permitted value, and a book sitting precisely on
it has no headroom left, which is the thing the status is meant to convey.

Utilisation uses the **absolute** value of the metric against a positive limit.
A DV01 limit constrains the size of the exposure, and a large short position is
not compliant because its DV01 is negative.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .errors import EngineError

LimitStatus = Literal["GREEN", "AMBER", "RED"]

DEFAULT_AMBER_UTILISATION_PERCENT = 80.0


@dataclass(frozen=True)
class LimitDefinition:
    metric: str
    limit_amount: float
    current_value: float
    unit: str = "USD"
    amber_utilisation_percent: float = DEFAULT_AMBER_UTILISATION_PERCENT
    description: str | None = None


@dataclass(frozen=True)
class LimitEvaluation:
    metric: str
    unit: str
    current_value: float
    absolute_value: float
    limit_amount: float
    utilisation_percent: float
    remaining_headroom: float
    amber_utilisation_percent: float
    amber_amount: float
    status: LimitStatus
    breached: bool
    description: str | None


@dataclass(frozen=True)
class LimitReport:
    evaluations: tuple[LimitEvaluation, ...]
    breach_count: int
    amber_count: int
    worst_utilisation_percent: float
    worst_metric: str | None
    all_within_limits: bool
    method: str = "explicit_threshold_utilisation_v1"
    threshold_policy: str = (
        "GREEN below the amber threshold; AMBER from the amber threshold up to "
        "but not including 100% utilisation; RED at or above 100%. Utilisation "
        "is the absolute value of the metric over the limit. Every limit and "
        "every amber threshold is a caller-supplied input - this engine holds "
        "no risk policy of its own."
    )


def evaluate_limit(definition: LimitDefinition) -> LimitEvaluation:
    if definition.limit_amount <= 0:
        raise EngineError(
            "INVALID_LIMIT",
            f"the limit for {definition.metric!r} is {definition.limit_amount}. A "
            "limit must be a positive amount: zero would make every book "
            "infinitely over its limit, and a negative one has no meaning.",
            category="USER_INPUT",
            field_errors={"limit_amount": "Must be greater than zero."},
            suggested_action="Supply the limit as a positive amount in its own unit.")
    if not 0 < definition.amber_utilisation_percent < 100:
        raise EngineError(
            "INVALID_LIMIT",
            f"the amber threshold for {definition.metric!r} is "
            f"{definition.amber_utilisation_percent}%. It must lie strictly "
            "between 0 and 100 - at 0 every book is amber, at 100 amber and red "
            "coincide and the warning band disappears.",
            category="USER_INPUT",
            field_errors={"amber_utilisation_percent": "Must be in (0, 100)."},
            suggested_action="Use a value such as 80.")

    absolute = abs(definition.current_value)
    utilisation = absolute / definition.limit_amount * 100.0
    if utilisation >= 100.0:
        status: LimitStatus = "RED"
    elif utilisation >= definition.amber_utilisation_percent:
        status = "AMBER"
    else:
        status = "GREEN"
    return LimitEvaluation(
        metric=definition.metric, unit=definition.unit,
        current_value=definition.current_value, absolute_value=absolute,
        limit_amount=definition.limit_amount, utilisation_percent=utilisation,
        remaining_headroom=definition.limit_amount - absolute,
        amber_utilisation_percent=definition.amber_utilisation_percent,
        amber_amount=definition.limit_amount * definition.amber_utilisation_percent / 100.0,
        status=status, breached=status == "RED",
        description=definition.description,
    )


def evaluate_limits(definitions: Sequence[LimitDefinition]) -> LimitReport:
    if not definitions:
        raise EngineError(
            "INVALID_LIMIT",
            "no limits were supplied. This engine has no default limit set and "
            "will not assume one.",
            category="USER_INPUT",
            suggested_action=(
                "Pass the limits that apply to this book, each with its metric, "
                "amount and unit."))
    evaluations = tuple(evaluate_limit(d) for d in definitions)
    worst = max(evaluations, key=lambda e: e.utilisation_percent)
    return LimitReport(
        evaluations=evaluations,
        breach_count=sum(1 for e in evaluations if e.status == "RED"),
        amber_count=sum(1 for e in evaluations if e.status == "AMBER"),
        worst_utilisation_percent=worst.utilisation_percent,
        worst_metric=worst.metric,
        all_within_limits=all(e.status != "RED" for e in evaluations),
    )
