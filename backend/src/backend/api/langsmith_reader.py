"""Reading a LangSmith trace back, on the server, with the payloads removed.

The gateway has always *written* traces. Reading one meant leaving the
application, so a demo of what the agents did involved a second browser tab and
an account. This module closes that loop from the backend, and the reason it is
a backend module rather than a frontend call is the first rule below.

**The API key never reaches the browser.** There is no `VITE_LANGSMITH_*`
variable and there must never be one: a key in a Vite build is a key in the
bundle, readable by anyone who opens the page. The browser holds a trace id -
which is not a credential - and asks this service, which holds the key and
decides what may travel back.

**Only the shape of the trace travels.** Run names, types, timings, status,
model and token counts. Never `inputs` or `outputs`: those hold the prompts, the
retrieved chunks and the model's own working, which is exactly the private
reasoning the execution view is not allowed to show. Dropping them here rather
than in the client is what makes that a property of the system instead of a
convention the UI is trusted to follow.

**It always answers.** LangSmith disabled, unreachable, still ingesting, or a
trace id that does not exist are four different facts, and all four come back as
`available: false` with the reason named. None of them is an error in this
gateway, and reporting them as one would make a healthy system look broken
whenever a SaaS was slow.
"""

from __future__ import annotations

import logging
import os
from typing import Any

LOGGER = logging.getLogger("backend.langsmith_reader")

#: How many runs one trace may return. A fully negotiated turn is a few dozen
#: spans; the cap is there so a pathological trace cannot become a large
#: response, and it is reported when it bites rather than silently truncating.
MAX_RUNS = 500

#: Run fields that may travel. Everything absent from this set is dropped,
#: including `inputs`, `outputs`, `error` details, `extra.metadata` and
#: `events` - an allow-list rather than a block-list, because a block-list is
#: wrong the first time the SDK adds a field.
_SAFE_FIELDS = ("id", "parent_run_id", "name", "run_type", "start_time",
                "end_time", "status", "trace_id")


def _read_timeout() -> float:
    try:
        return float(os.environ.get("LANGSMITH_READ_TIMEOUT_SECONDS", "8"))
    except ValueError:
        return 8.0


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    return {"available": False, "reason": reason, "runs": [], **extra}


def _iso(value: Any) -> str:
    if value is None:
        return ""
    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


def _latency_ms(run: Any) -> int | None:
    start, end = getattr(run, "start_time", None), getattr(run, "end_time", None)
    if start is None or end is None:
        return None
    try:
        return int((end - start).total_seconds() * 1000)
    except Exception:  # noqa: BLE001 - a missing latency is cosmetic
        return None


def _tokens(run: Any) -> dict[str, Any]:
    """Token counts, when LangSmith recorded them.

    Reported only where they exist. A span with no usage is shown without
    counts rather than with zeros: zero tokens and "not measured" are different
    facts, and a dashboard that adds them up gets the second one wrong.
    """
    out: dict[str, Any] = {}
    for attribute, key in (("prompt_tokens", "input_tokens"),
                           ("completion_tokens", "output_tokens"),
                           ("total_tokens", "total_tokens")):
        value = getattr(run, attribute, None)
        if isinstance(value, int) and value >= 0:
            out[key] = value
    return out


def _model_of(run: Any) -> str:
    """The model a span ran on, from the conventional metadata keys."""
    extra = getattr(run, "extra", None)
    metadata = extra.get("metadata") if isinstance(extra, dict) else None
    if not isinstance(metadata, dict):
        return ""
    for key in ("ls_model_name", "model_name", "model"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _sanitise(run: Any) -> dict[str, Any]:
    payload = {field: getattr(run, field, None) for field in _SAFE_FIELDS}
    return {
        "id": str(payload["id"] or ""),
        "parent_id": (str(payload["parent_run_id"])
                      if payload["parent_run_id"] else ""),
        "trace_id": str(payload["trace_id"] or ""),
        "name": str(payload["name"] or ""),
        "run_type": str(payload["run_type"] or ""),
        "start_time": _iso(payload["start_time"]),
        "end_time": _iso(payload["end_time"]),
        "latency_ms": _latency_ms(run),
        # `status` is absent on a run still being written; "running" is what
        # that means and is more useful than an empty cell.
        "status": str(payload["status"] or "running"),
        # An error is reported as a boolean, never as its message. An exception
        # string carries hosts, ports and internal identifiers, and this
        # response is rendered in a browser.
        "error": bool(getattr(run, "error", None)),
        "model": _model_of(run),
        **_tokens(run),
    }


def fetch_trace(trace_id: str) -> dict[str, Any]:
    """One turn's LangSmith runs, flattened, sanitised and ready to nest."""
    if not trace_id:
        return _unavailable("no trace id was supplied")
    try:
        from agents.observability import project_name, tracing_enabled  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"the observability layer is unavailable: {exc}")

    if not tracing_enabled():
        return _unavailable(
            "LangSmith tracing is not enabled on this gateway, so there is no "
            "trace to read. The gateway's own execution trace is still "
            "available and is what the Trace view shows by default.")

    try:
        from langsmith import Client  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"the langsmith client is not installed: {exc}")

    project = project_name()
    try:
        client = Client(timeout_ms=(int(_read_timeout() * 1000),
                                    int(_read_timeout() * 1000)))
        runs = list(client.list_runs(project_name=project, trace_id=trace_id,
                                     limit=MAX_RUNS))
    except Exception as exc:  # noqa: BLE001 - never a 5xx from this gateway
        LOGGER.info("could not read LangSmith trace %s: %s", trace_id, exc)
        return _unavailable(
            "LangSmith could not be read just now. This does not affect the "
            "answer or the gateway's own trace.",
            detail=type(exc).__name__, project=project)

    if not runs:
        # The commonest case by far, and worth its own sentence: LangSmith
        # ingests asynchronously, so a trace requested the instant its turn
        # finished is often not queryable yet. Telling the reader to try again
        # is actionable; "unavailable" is not.
        return _unavailable(
            "No runs are recorded against this trace yet. LangSmith ingests "
            "asynchronously, so a trace is often queryable a few seconds after "
            "the turn finishes.", project=project, trace_id=trace_id)

    sanitised = [_sanitise(run) for run in runs]
    sanitised.sort(key=lambda r: r["start_time"] or "")
    started = min((r["start_time"] for r in sanitised if r["start_time"]),
                  default="")
    ended = max((r["end_time"] for r in sanitised if r["end_time"]), default="")
    return {
        "available": True,
        "trace_id": trace_id,
        "project": project,
        "runs": sanitised,
        "run_count": len(sanitised),
        "truncated": len(sanitised) >= MAX_RUNS,
        "started_at": started,
        "ended_at": ended,
    }
