"""Structured, recoverable failures for the risk engine.

The data server already answers a bad request with a JSON `ToolError` rather
than prose, because the reader is a model that has to correct itself without a
human. The engine follows the same convention for the same reason - and for one
more that is specific to a calculation service.

**A quant tool that cannot compute something truthfully must say which thing.**
"insufficient history" and "the covariance matrix is not positive
semidefinite" are both refusals, but they call for opposite corrections: widen
the window, or repair the matrix. Collapsing them into `ValueError("bad
input")` throws away the only part of the message that was useful.

The three legacy exception types - `CurveError`, `PricingError`, `RiskError` -
predate this module and keep their identity, because callers and tests catch
them by name. `EngineError` is a sibling, not a replacement; where a new
failure is naturally one of the old kinds, the constructors below return a
subclass that is *both*, so `except RiskError` still works and the error code
still travels.
"""

from __future__ import annotations

import json
from typing import Any, Literal

RiskErrorCode = Literal[
    "UNSUPPORTED_INSTRUMENT",
    "UNSUPPORTED_DAY_COUNT",
    "UNSUPPORTED_COUPON_FREQUENCY",
    "NO_REMAINING_CASH_FLOWS",
    "INVALID_CURVE",
    "MISSING_CURVE_TENOR",
    "INVALID_STRESS_VECTOR",
    "UNKNOWN_SCENARIO_TEMPLATE",
    "INSUFFICIENT_HISTORY",
    "INVALID_CONFIDENCE_LEVEL",
    "INVALID_HORIZON",
    "INVALID_COVARIANCE_MATRIX",
    "MONTE_CARLO_FAILURE",
    "NO_REVERSE_STRESS_SOLUTION",
    "SOLVER_DID_NOT_CONVERGE",
    "INSUFFICIENT_BACKTEST_DATA",
    "MISSING_PNL_SERIES",
    "INVALID_VAR_FORECAST",
    "INVALID_LIMIT",
    "UNSUPPORTED_REGULATORY_SCOPE",
    "MISSING_REQUIRED_MARKET_DATA",
    "UNSUPPORTED_CRISIS_SCENARIO",
    "INCONSISTENT_PORTFOLIOS",
]

RiskErrorCategory = Literal[
    "USER_INPUT", "DATA_AVAILABILITY", "NUMERICAL", "MODEL_SCOPE"
]


class EngineError(ValueError):
    """A calculation that cannot be performed truthfully, with a code.

    `str(self)` is JSON, matching the data server's `DomainError`. The SDK puts
    that string in the text block the model reads, so it has to be the
    instruction rather than a log line.
    """

    def __init__(
        self,
        code: RiskErrorCode,
        message: str,
        *,
        category: RiskErrorCategory = "USER_INPUT",
        retryable: bool = False,
        field_errors: dict[str, str] | None = None,
        suggested_action: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "error_code": code,
            "category": category,
            "retryable": retryable,
            "message": message,
        }
        if field_errors:
            payload["field_errors"] = field_errors
        if suggested_action:
            payload["suggested_action"] = suggested_action
        if details:
            payload["details"] = details
        super().__init__(json.dumps(payload, sort_keys=True, default=str))
        self.code = code
        self.category = category
        self.retryable = retryable
        self.plain_message = message
        self.details = details or {}


def unsupported_scope(code: RiskErrorCode, message: str, action: str) -> EngineError:
    """A refusal on grounds of model scope, not of the caller's arithmetic.

    Kept distinct because the correction is different in kind: no retry, no
    different argument, and no approximation. The capability is absent.
    """
    return EngineError(code, message, category="MODEL_SCOPE", suggested_action=action)
