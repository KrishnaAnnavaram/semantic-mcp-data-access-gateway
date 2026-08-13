"""Domain errors, written for a model to recover from.

MCP distinguishes two failure kinds and the distinction matters here:

* **Protocol errors** - malformed arguments, unknown tool. The model is unlikely
  to recover from these, so they stay JSON-RPC errors and the SDK raises them.
* **Tool execution errors** - a well-formed request that cannot be satisfied.
  The spec says clients SHOULD feed these back to the model so it can correct
  itself, which means the message is not a log line. It is an instruction.

So every error below names the fix. "No data for 2026-07-04" is a dead end;
"2026-07-04 is a holiday, nearest available are 2026-07-02 and 2026-07-07" lets
the model retry successfully without a human.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ErrorCode = Literal[
    "UNKNOWN_SERIES",
    "AMBIGUOUS_SERIES",
    "UNKNOWN_DATASET",
    "UNKNOWN_PORTFOLIO",
    "UNKNOWN_SCENARIO",
    "DATE_NO_DATA",
    "DATE_OUT_OF_RANGE",
    "INVALID_DATE_RANGE",
    "ROW_LIMIT_EXCEEDED",
    "INVALID_CURSOR",
    "INSUFFICIENT_HISTORY",
    "CURVE_INCOMPLETE",
    "MISSING_OBSERVATIONS",
]

ErrorCategory = Literal["USER_INPUT", "DATA_AVAILABILITY", "LIMIT", "INTEGRITY"]


class ToolError(BaseModel):
    """Structured, recoverable failure returned with `is_error=True`."""

    error_code: ErrorCode
    category: ErrorCategory
    retryable: bool
    message: str
    field_errors: dict[str, str] | None = None
    suggested_action: str | None = None
    candidates: list[dict[str, Any]] | None = Field(
        default=None,
        description="Concrete alternatives the caller can retry with, when known.",
    )


class DomainError(Exception):
    """Raised inside a tool; the SDK turns it into an `is_error` tool result.

    `str(self)` is the ToolError as JSON, because that string becomes the text
    block the model reads. A prose message would tell the model something went
    wrong; the JSON tells it what to do instead - which error code, which field
    was at fault, and which concrete alternatives exist.

    Note the SDK prefixes the text with "Error executing tool <name>: ". The
    JSON begins after the first "{".
    """

    def __init__(self, error: ToolError) -> None:
        super().__init__(error.model_dump_json(exclude_none=True))
        self.error = error


def unknown_series(code: str, candidates: list[dict[str, Any]] | None = None) -> DomainError:
    return DomainError(ToolError(
        error_code="UNKNOWN_SERIES",
        category="USER_INPUT",
        retryable=False,
        message=f"No series with code {code!r}.",
        field_errors={"series_codes": f"{code!r} is not a known series code."},
        suggested_action="Call search_series or list_series to obtain valid codes.",
        candidates=candidates,
    ))


def ambiguous_series(query: str, candidates: list[dict[str, Any]]) -> DomainError:
    """The '30 year' problem: nominal or real? Never guess between them."""
    return DomainError(ToolError(
        error_code="AMBIGUOUS_SERIES",
        category="USER_INPUT",
        retryable=False,
        message=(
            f"{query!r} matches more than one series and the difference is "
            "material - nominal and real yields are not interchangeable."
        ),
        suggested_action="Re-request naming an exact series_code from candidates.",
        candidates=candidates,
    ))


def date_no_data(
    observation_date: str, curve_family: str, nearest: list[dict[str, Any]]
) -> DomainError:
    return DomainError(ToolError(
        error_code="DATE_NO_DATA",
        category="DATA_AVAILABILITY",
        retryable=True,
        message=(
            f"No {curve_family} curve was published on {observation_date}. "
            "Treasury does not publish on weekends, federal holidays or Good Friday."
        ),
        field_errors={"observation_date": "No exact observation on this date."},
        suggested_action=(
            "Retry with one of the nearest available dates, or set "
            "date_policy='previous' or 'next' to accept a shift explicitly."
        ),
        candidates=nearest,
    ))


def date_out_of_range(field: str, value: str, first: str, last: str) -> DomainError:
    return DomainError(ToolError(
        error_code="DATE_OUT_OF_RANGE",
        category="DATA_AVAILABILITY",
        retryable=False,
        message=f"{value} lies outside the available history ({first} to {last}).",
        field_errors={field: f"Must fall between {first} and {last}."},
        suggested_action=f"Choose a date between {first} and {last}.",
    ))


def row_limit_exceeded(requested: int, limit: int, hint: str) -> DomainError:
    """Deliberately an error, not an elicitation.

    Asking the user "this is big, continue?" is the wrong response to a
    resource limit - it turns a mechanical constraint into a conversation. The
    caller should narrow the request or paginate. Elicitation is reserved for
    genuine semantic ambiguity, where no amount of retrying will resolve it.
    """
    return DomainError(ToolError(
        error_code="ROW_LIMIT_EXCEEDED",
        category="LIMIT",
        retryable=False,
        message=f"Request would return {requested:,} rows; the limit is {limit:,}.",
        suggested_action=hint,
    ))


def invalid_cursor(reason: str) -> DomainError:
    return DomainError(ToolError(
        error_code="INVALID_CURSOR",
        category="USER_INPUT",
        retryable=False,
        message=f"Pagination cursor rejected: {reason}.",
        suggested_action="Restart the query without a cursor.",
    ))


def invalid_date_range(start: str, end: str) -> DomainError:
    return DomainError(ToolError(
        error_code="INVALID_DATE_RANGE",
        category="USER_INPUT",
        retryable=False,
        message=f"start_date {start} is after end_date {end}.",
        field_errors={"start_date": "Must be on or before end_date."},
        suggested_action="Swap the dates.",
    ))


def insufficient_history(requested: int, available: int, first: str) -> DomainError:
    return DomainError(ToolError(
        error_code="INSUFFICIENT_HISTORY",
        category="DATA_AVAILABILITY",
        retryable=False,
        message=(
            f"{requested} trading days requested but only {available} are "
            f"available on the intersection of the requested tenors "
            f"(history begins {first})."
        ),
        suggested_action=(
            f"Request at most {available} trading days, or drop the tenors whose "
            "history starts later."
        ),
    ))


def missing_observations(
    excluded: int, requested: int, detail: list[dict[str, Any]]
) -> DomainError:
    """The honest default when a curve is incomplete across the window.

    The alternative - silently dropping incomplete dates - changes a VaR number
    without failing. The 30-year has a genuine 994-business-day hole from 2002
    to 2006; a window spanning it must either be refused or have the exclusion
    stated out loud. Callers who accept the loss can pass
    missing_policy='intersection', which reports excluded_dates in the result.
    """
    return DomainError(ToolError(
        error_code="MISSING_OBSERVATIONS",
        category="DATA_AVAILABILITY",
        retryable=True,
        message=(
            f"{excluded} of {requested} dates lack an observation for every "
            "requested tenor. Returning a partial history would change any risk "
            "number computed from it without signalling that anything was lost."
        ),
        suggested_action=(
            "Either narrow the tenor set, move the window, or pass "
            "missing_policy='intersection' to accept the gaps - the result will "
            "then report excluded_dates."
        ),
        candidates=detail[:10] or None,
    ))


def unknown_entity(kind: str, value: str, candidates: list[dict[str, Any]]) -> DomainError:
    code_map: dict[str, ErrorCode] = {
        "dataset": "UNKNOWN_DATASET",
        "portfolio": "UNKNOWN_PORTFOLIO",
        "scenario": "UNKNOWN_SCENARIO",
    }
    return DomainError(ToolError(
        error_code=code_map[kind],
        category="USER_INPUT",
        retryable=False,
        message=f"No {kind} with id {value!r}.",
        suggested_action=f"Call list_{kind}s for valid identifiers.",
        candidates=candidates,
    ))
