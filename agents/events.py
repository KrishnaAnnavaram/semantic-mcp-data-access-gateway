"""The execution event stream: what the system is doing, while it does it.

A turn in this gateway takes minutes, not milliseconds - a bounded negotiation
is several reasoning calls, and each of those is tens of seconds. For that whole
time the browser used to see one spinner, which is indistinguishable from a
hang. This module is the channel that makes the wait legible: every agent
boundary, every model call, every retrieval and every MCP tool publishes one
small, sanitised fact about itself, and the service relays those to the UI over
SSE as they happen.

    publisher (worker thread, A2A loop, FastAPI thread)
        |  emit(...)
        v
    EventBus  -- bounded per-run history --> late subscriber replays
        |
        +- asyncio.Queue on the subscriber's own loop (SSE)
        +- latency_report(): the same events, summed by component

Four rules this module holds to.

**Observability must never change behaviour.** Every function here is
fail-open: a full queue, a dead loop, a value that will not serialise, or no
subscriber at all must all degrade to doing nothing. `emit` cannot raise.

**No private reasoning, ever.** Events carry what an operator can act on -
agent, stage, tool, status, duration, counts. Model prompts, completions, chain
of thought, rate values, credentials and connection strings are not published,
and `safe_metadata` drops any key that looks like a secret rather than trusting
call sites to remember.

**One id correlates everything.** `request_id` is the `TurnLedger`'s
`user_request_id`, which is also what the A2A handoff ledger reports and what
the frontend chose before it sent the question. So the live stream, the handoff
trail, the latency table and the graph are all views of the same turn rather
than four observability systems that have to be reconciled.

**Timing is measured, never modelled.** Durations come from `perf_counter`
around real work. An event with no duration reports none; nothing here
interpolates a plausible number.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterator

LOGGER = logging.getLogger("agents.events")

#: How many turns keep their event history. A run is worthless once its answer
#: has been read; an unbounded dictionary keyed by request id is a slow leak.
RUN_CAPACITY = 64

#: How many events one turn may keep. A fully negotiated risk turn publishes
#: roughly sixty; the ceiling is there so a pathological loop cannot grow the
#: buffer without bound, and the overflow count is reported rather than hidden.
EVENTS_PER_RUN = 600

#: Metadata keys never published, matched as substrings, case-insensitively.
#: Cheaper than asking every call site to remember, and it fails safe: a field
#: named `..._token` added later is dropped before anyone notices it exists.
_SECRETISH = ("key", "token", "secret", "password", "credential", "auth",
              "dsn", "conn", "cookie")

#: Metadata strings longer than this are truncated. A trace line is not a
#: payload channel, and a 40 KB error string in an SSE frame is a denial of
#: service on the reader's browser rather than information.
_MAX_STR = 240


class EventType:
    """The vocabulary. One normalised model, not several per-layer formats."""

    REQUEST_RECEIVED = "REQUEST_RECEIVED"
    ORCHESTRATOR_STARTED = "ORCHESTRATOR_STARTED"
    ORCHESTRATOR_DECISION = "ORCHESTRATOR_DECISION"
    DOMAIN_VALIDATION_STARTED = "DOMAIN_VALIDATION_STARTED"
    DOMAIN_VALIDATION_COMPLETED = "DOMAIN_VALIDATION_COMPLETED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    RETRIEVAL_STARTED = "RETRIEVAL_STARTED"
    RETRIEVAL_COMPLETED = "RETRIEVAL_COMPLETED"
    AGENT_HANDOFF = "AGENT_HANDOFF"
    AGENT_HANDOFF_COMPLETED = "AGENT_HANDOFF_COMPLETED"
    NEGOTIATION_ROUND = "NEGOTIATION_ROUND"
    MCP_AGENT_STARTED = "MCP_AGENT_STARTED"
    MCP_TOOL_STARTED = "MCP_TOOL_STARTED"
    MCP_TOOL_COMPLETED = "MCP_TOOL_COMPLETED"
    MCP_TOOL_FAILED = "MCP_TOOL_FAILED"
    DB_QUERY_STARTED = "DB_QUERY_STARTED"
    DB_QUERY_COMPLETED = "DB_QUERY_COMPLETED"
    MODEL_CALL_STARTED = "MODEL_CALL_STARTED"
    MODEL_CALL_COMPLETED = "MODEL_CALL_COMPLETED"
    MODEL_CALL_FAILED = "MODEL_CALL_FAILED"
    RESPONSE_SYNTHESIS_STARTED = "RESPONSE_SYNTHESIS_STARTED"
    RESPONSE_SYNTHESIS_COMPLETED = "RESPONSE_SYNTHESIS_COMPLETED"
    REQUEST_COMPLETED = "REQUEST_COMPLETED"
    REQUEST_FAILED = "REQUEST_FAILED"


#: Which latency component an event type belongs to. Anything unmapped is not
#: counted - a component total assembled from events nobody classified would be
#: a number with no defined meaning.
_COMPONENT_OF = {
    EventType.MODEL_CALL_COMPLETED: "llm",
    EventType.MODEL_CALL_FAILED: "llm",
    EventType.RETRIEVAL_COMPLETED: "qdrant",
    EventType.MCP_TOOL_COMPLETED: "mcp_tool",
    EventType.MCP_TOOL_FAILED: "mcp_tool",
    EventType.DB_QUERY_COMPLETED: "postgres",
    EventType.AGENT_HANDOFF_COMPLETED: "a2a_handoff",
    EventType.DOMAIN_VALIDATION_COMPLETED: "preflight",
}

#: Components whose durations *contain* other components' durations. Reported
#: separately and never summed with the rest: an A2A call to the domain expert
#: contains its own model calls, its retrievals and every nested MCP call, so
#: adding it to those would attribute the same second three times and produce a
#: table whose percentages exceed 100.
NESTED_COMPONENTS = frozenset({"a2a_handoff"})


@dataclass(frozen=True)
class ExecutionEvent:
    """One operationally useful fact about a turn in progress."""

    request_id: str
    sequence: int
    event_type: str
    agent: str
    title: str
    summary: str = ""
    status: str = "running"          # running | completed | failed | skipped | info
    #: Wall-clock, for display. `elapsed_ms` is what a timeline is built from,
    #: because it is measured from one monotonic origin and cannot go backwards.
    timestamp: float = 0.0
    elapsed_ms: int = 0
    duration_ms: int | None = None
    span_id: str = ""
    parent_span_id: str = ""
    trace_id: str = ""
    tool_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id, "sequence": self.sequence,
            "event_type": self.event_type, "agent": self.agent,
            "title": self.title, "summary": self.summary, "status": self.status,
            "timestamp": self.timestamp, "elapsed_ms": self.elapsed_ms,
            "duration_ms": self.duration_ms, "span_id": self.span_id,
            "parent_span_id": self.parent_span_id, "trace_id": self.trace_id,
            "tool_name": self.tool_name, "metadata": self.metadata,
        }


def _safe(value: Any, depth: int = 0) -> Any:
    """Reduce a value to something small, serialisable and non-secret."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= _MAX_STR else value[:_MAX_STR] + "..."
    if depth >= 2:
        return None
    if isinstance(value, (list, tuple, set)):
        items = []
        for item in list(value)[:12]:
            try:
                clean = _safe(item, depth + 1)
            except Exception:  # noqa: BLE001 - one bad item, not a lost list
                continue
            if clean is not None:
                items.append(clean)
        return items
    if isinstance(value, dict):
        return safe_metadata(value, depth + 1)
    return _safe(str(value), depth)


def safe_metadata(raw: Any, depth: int = 0) -> dict[str, Any]:
    """Sanitised metadata: no secrets, no payloads, no unbounded strings.

    Each value is converted independently, because a single value that cannot
    be described - an object whose `__repr__` raises, a lazy proxy that touches
    a closed resource - must cost that one field and not the whole event. An
    all-or-nothing conversion drops the progress line entirely, which is the
    opposite of what a panel built to show what is happening should do when
    something unusual happens.
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in list(raw.items())[:20]:
        try:
            name = str(key)
            if any(marker in name.lower() for marker in _SECRETISH):
                continue
            clean = _safe(value, depth)
        except Exception:  # noqa: BLE001 - drop the field, keep the event
            continue
        if clean is None or clean == [] or clean == {}:
            continue
        out[name] = clean
    return out


@dataclass
class _Run:
    """One turn's event history, and the origin its timeline is measured from."""

    request_id: str
    started_monotonic: float = field(default_factory=time.perf_counter)
    started_wall: float = field(default_factory=time.time)
    sequence: int = 0
    events: deque = field(default_factory=lambda: deque(maxlen=EVENTS_PER_RUN))
    finished: bool = False
    dropped: int = 0


class EventBus:
    """Process-local publish/subscribe for execution events.

    Publishers are on three different threads and two different event loops (the
    A2A loop, uvicorn's loop, and the worker threads the executors use), while
    subscribers are SSE responses on uvicorn's loop. So the shared state is
    guarded by a plain lock and delivery to a subscriber is marshalled onto
    *that subscriber's* loop with `call_soon_threadsafe`. No publisher ever waits
    on a subscriber, which is what keeps observability off the answer's path.
    """

    def __init__(self, run_capacity: int = RUN_CAPACITY) -> None:
        self._runs: dict[str, _Run] = {}
        self._subscribers: dict[str, list[tuple[Any, Any]]] = {}
        self._lock = threading.Lock()
        self._run_capacity = run_capacity

    # -- runs ----------------------------------------------------------------

    def open_run(self, request_id: str) -> str:
        """Start (or re-open) a turn's timeline. Idempotent by request id."""
        rid = request_id or uuid.uuid4().hex[:12]
        with self._lock:
            if rid not in self._runs:
                self._runs[rid] = _Run(request_id=rid)
                self._evict()
        return rid

    def close_run(self, request_id: str) -> None:
        """Mark a turn finished so subscribers can stop waiting.

        The history survives: the trace, latency and graph views are read after
        the answer arrives, which is precisely when the turn is over.
        """
        with self._lock:
            run = self._runs.get(request_id)
            if run is not None:
                run.finished = True
            subscribers = list(self._subscribers.get(request_id) or [])
        for loop, queue in subscribers:
            self._deliver(loop, queue, None)

    def is_finished(self, request_id: str) -> bool:
        with self._lock:
            run = self._runs.get(request_id)
            return run is None or run.finished

    def history(self, request_id: str) -> list[ExecutionEvent]:
        with self._lock:
            run = self._runs.get(request_id)
            return list(run.events) if run else []

    def elapsed_ms(self, request_id: str) -> int:
        with self._lock:
            run = self._runs.get(request_id)
            if run is None:
                return 0
            return int((time.perf_counter() - run.started_monotonic) * 1000)

    def _evict(self) -> None:
        while len(self._runs) > self._run_capacity:
            self._runs.pop(next(iter(self._runs)))

    # -- publishing ----------------------------------------------------------

    def publish(self, request_id: str, event_type: str, *, agent: str = "system",
                title: str = "", summary: str = "", status: str = "running",
                duration_ms: int | None = None, tool_name: str = "",
                span_id: str = "", parent_span_id: str = "", trace_id: str = "",
                metadata: dict[str, Any] | None = None):
        """Record one event and fan it out. Never raises, never blocks."""
        try:
            with self._lock:
                run = self._runs.get(request_id)
                if run is None:
                    # A publisher that beats the run open - or a turn nobody is
                    # watching - still gets a timeline rather than being lost.
                    run = _Run(request_id=request_id)
                    self._runs[request_id] = run
                    self._evict()
                run.sequence += 1
                if len(run.events) == run.events.maxlen:
                    run.dropped += 1
                now = time.perf_counter()
                event = ExecutionEvent(
                    request_id=request_id, sequence=run.sequence,
                    event_type=event_type, agent=agent or "system",
                    title=title or event_type, summary=summary, status=status,
                    timestamp=run.started_wall + (now - run.started_monotonic),
                    elapsed_ms=int((now - run.started_monotonic) * 1000),
                    duration_ms=(int(duration_ms)
                                 if duration_ms is not None else None),
                    span_id=span_id, parent_span_id=parent_span_id,
                    trace_id=trace_id, tool_name=tool_name,
                    metadata=safe_metadata(metadata or {}))
                run.events.append(event)
                subscribers = list(self._subscribers.get(request_id) or [])
        except Exception as exc:  # noqa: BLE001 - observability is never fatal
            LOGGER.debug("could not record event %s: %s", event_type, exc)
            return None
        for loop, queue in subscribers:
            self._deliver(loop, queue, event)
        return event

    @staticmethod
    def _deliver(loop: Any, queue: Any, event) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception:  # noqa: BLE001 - a gone loop or a full queue drops
            pass

    # -- subscribing ---------------------------------------------------------

    @contextlib.contextmanager
    def subscribe(self, request_id: str) -> Iterator[Any]:
        """An asyncio queue fed with this turn's events, on the caller's loop.

        Must be entered from the loop that will consume it - the SSE handler -
        because that is the loop delivery is marshalled onto.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=2048)
        entry = (loop, queue)
        with self._lock:
            self._subscribers.setdefault(request_id, []).append(entry)
        try:
            yield queue
        finally:
            with self._lock:
                subscribers = self._subscribers.get(request_id) or []
                if entry in subscribers:
                    subscribers.remove(entry)
                if not subscribers:
                    self._subscribers.pop(request_id, None)


_BUS = EventBus()


def bus() -> EventBus:
    return _BUS


#: The turn every publisher on this execution context belongs to. Set once at
#: the user boundary; `contextvars` carries it across `asyncio.to_thread`,
#: `run_coroutine_threadsafe` and the in-process ASGI hop, which is every
#: crossing a publisher in this system sits behind.
_REQUEST_ID: contextvars.ContextVar = contextvars.ContextVar(
    "execution_request_id", default="")


def set_request_id(request_id: str) -> Any:
    return _REQUEST_ID.set(request_id or "")


def reset_request_id(token: Any) -> None:
    with contextlib.suppress(Exception):
        _REQUEST_ID.reset(token)


def current_request_id() -> str:
    """The turn this code runs for, from the context or from the A2A task.

    Two sources rather than one because context propagation is the *usual* path
    and the A2A execution context is the *provable* one: an executor publishes
    the task it is running before handing work to a worker thread, and that
    record already carries the turn id. If either knows which turn this is, the
    event is attributed correctly instead of dropped.
    """
    rid = _REQUEST_ID.get("")
    if rid:
        return rid
    try:
        from agents.a2a.executors import active_execution  # noqa: PLC0415

        context = active_execution()
        return context.user_request_id if context is not None else ""
    except Exception:  # noqa: BLE001 - resolution is best effort
        return ""


def emit(event_type: str, *, agent: str = "system", title: str = "",
         summary: str = "", status: str = "running",
         duration_ms: int | None = None, tool_name: str = "",
         request_id: str = "", **metadata: Any):
    """Publish one event for the current turn. Fail-open in every direction."""
    rid = request_id or current_request_id()
    if not rid:
        return None
    return _BUS.publish(rid, event_type, agent=agent, title=title,
                        summary=summary, status=status, duration_ms=duration_ms,
                        tool_name=tool_name, metadata=metadata)


@contextlib.contextmanager
def stage(started: str, completed: str, *, agent: str, title: str,
          failed: str = "", tool_name: str = "", request_id: str = "",
          **metadata: Any) -> Iterator[dict]:
    """Publish a start event, time the block, publish its completion.

    Yields a dict the block may add to; whatever it holds at exit becomes the
    completion event's metadata. Re-raises whatever the block raised - this
    times work, it does not swallow its failures.
    """
    extra: dict[str, Any] = {}
    emit(started, agent=agent, title=title, status="running",
         tool_name=tool_name, request_id=request_id, **metadata)
    began = time.perf_counter()
    try:
        yield extra
    except Exception as exc:
        emit(failed or completed, agent=agent, title=title, status="failed",
             summary=type(exc).__name__, tool_name=tool_name,
             request_id=request_id,
             duration_ms=int((time.perf_counter() - began) * 1000),
             **{**metadata, **extra})
        raise
    emit(completed, agent=agent, title=title, status="completed",
         tool_name=tool_name, request_id=request_id,
         duration_ms=int((time.perf_counter() - began) * 1000),
         **{**metadata, **extra})


# -- latency ------------------------------------------------------------------


def _component_for(event: ExecutionEvent):
    """Which latency bucket an event's measured duration belongs to.

    Model time is split by *call site* rather than lumped together, because
    "the LLM took 90 seconds" is not an actionable finding and "the domain
    expert's derive took 62 s of it" is.
    """
    base = _COMPONENT_OF.get(event.event_type)
    if base is None or event.duration_ms is None:
        return None
    if base != "llm":
        return base
    site = str(event.metadata.get("call_site") or event.agent or "llm")
    return f"llm:{site}"


def latency_report(request_id: str, total_ms: int | None = None) -> dict:
    """Sum this turn's measured durations by component.

    Built only from events that carry a real measured duration. A stage nobody
    instrumented is absent rather than estimated, and `unattributed_ms` names
    what the components do not account for instead of quietly distributing it -
    an honest gap is more useful than a table that adds up because it was made
    to.
    """
    events = _BUS.history(request_id)
    total = total_ms if total_ms is not None else _BUS.elapsed_ms(request_id)
    buckets: dict[str, list[int]] = {}
    for event in events:
        component = _component_for(event)
        if component is None:
            continue
        buckets.setdefault(component, []).append(int(event.duration_ms or 0))

    rows: list[dict[str, Any]] = []
    for component, durations in sorted(buckets.items()):
        summed = sum(durations)
        nested = component in NESTED_COMPONENTS
        rows.append({
            "component": component,
            "calls": len(durations),
            "total_ms": summed,
            "avg_ms": round(summed / len(durations)) if durations else 0,
            "max_ms": max(durations) if durations else 0,
            "pct": (round(100.0 * summed / total, 1)
                    if total and not nested else None),
            "nested": nested,
        })
    rows.sort(key=lambda r: (r["nested"], -r["total_ms"]))
    attributed = sum(r["total_ms"] for r in rows if not r["nested"])
    return {
        "request_id": request_id,
        "total_ms": total,
        "components": rows,
        "attributed_ms": attributed,
        # Serialisation, the FastAPI hop, session bookkeeping, and any stage
        # with no instrumentation. Named rather than hidden. Floored at zero:
        # a negative value would mean work overlapped inside the turn, and that
        # shows honestly as attributed_ms exceeding total_ms instead.
        "unattributed_ms": max(0, total - attributed),
        "events": len(events),
    }


def timeline(request_id: str) -> list[dict]:
    """This turn's events as plain dicts, oldest first."""
    return [event.as_dict() for event in _BUS.history(request_id)]
