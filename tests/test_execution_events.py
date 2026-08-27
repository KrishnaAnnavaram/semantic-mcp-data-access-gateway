"""The execution event stream: correlation, sanitisation, and never breaking a turn.

Three properties, in the order they matter.

**Observability cannot change behaviour.** A publisher with no subscriber, a
dead loop, an unserialisable value or a missing run must all be no-ops. If any
of these can raise, the panel that was added to make failures visible becomes a
cause of them.

**Nothing private is published.** The events carry stages and durations. A
secret-looking key, a bulk payload or a model prompt must not survive
`safe_metadata`, and that has to be enforced at the source rather than by the
UI choosing not to render it.

**One id ties the views together.** The stream, the handoff ledger and the
latency report are three views of one turn, and they are only that if they carry
the same `request_id`.
"""

from __future__ import annotations

import threading

import pytest

from agents import events
from agents.events import EventBus, EventType, latency_report, safe_metadata


@pytest.fixture
def bus() -> EventBus:
    return EventBus(run_capacity=4)


# --- publishing --------------------------------------------------------------


def test_events_are_recorded_in_order_with_a_monotonic_sequence(bus):
    bus.open_run("r1")
    for i in range(5):
        bus.publish("r1", EventType.MODEL_CALL_COMPLETED, title=f"call {i}")
    history = bus.history("r1")
    assert [e.sequence for e in history] == [1, 2, 3, 4, 5]
    assert [e.title for e in history] == [f"call {i}" for i in range(5)]


def test_publishing_to_an_unopened_run_still_records_it():
    """A publisher that beats the run open must not lose its event.

    The turn's first events can be emitted before anything calls `open_run`, and
    a dropped `REQUEST_RECEIVED` is the one line that tells a reader when the
    clock started.
    """
    bus = EventBus()
    bus.publish("never-opened", EventType.REQUEST_RECEIVED, title="hello")
    assert len(bus.history("never-opened")) == 1


def test_publishing_never_raises_whatever_it_is_handed(bus):
    bus.open_run("r1")

    class Hostile:
        def __repr__(self):
            raise RuntimeError("this object refuses to be described")

    # Must not raise. An observability call on the answer path that can throw is
    # a defect regardless of how unlikely the input is.
    bus.publish("r1", EventType.MODEL_CALL_COMPLETED, title="x",
                metadata={"bad": Hostile(), "fine": 1})
    recorded = bus.history("r1")[-1]
    assert recorded.metadata.get("fine") == 1


def test_a_run_is_evicted_once_the_capacity_is_exceeded(bus):
    for i in range(6):
        bus.open_run(f"r{i}")
        bus.publish(f"r{i}", EventType.REQUEST_RECEIVED, title="x")
    # Four retained, oldest first out: a per-request dictionary that grows
    # forever is a slow leak in a long-lived service.
    assert bus.history("r0") == []
    assert bus.history("r5") != []


def test_events_per_run_are_bounded(bus):
    bus.open_run("r1")
    for i in range(events.EVENTS_PER_RUN + 50):
        bus.publish("r1", EventType.MODEL_CALL_COMPLETED, title=str(i))
    assert len(bus.history("r1")) == events.EVENTS_PER_RUN


def test_publishing_is_thread_safe(bus):
    """Publishers are on three threads and two loops; the store is shared."""
    bus.open_run("r1")

    def publish_many():
        for i in range(50):
            bus.publish("r1", EventType.MCP_TOOL_COMPLETED, title=str(i))

    workers = [threading.Thread(target=publish_many) for _ in range(4)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    history = bus.history("r1")
    assert len(history) == 200
    # No sequence handed out twice, which is what the UI dedupes on.
    assert len({e.sequence for e in history}) == 200


# --- sanitisation ------------------------------------------------------------


@pytest.mark.parametrize("key", [
    "api_key", "LANGSMITH_API_KEY", "token", "password", "secret",
    "credential", "authorization", "database_dsn", "connection_string",
    "cookie",
])
def test_secret_looking_keys_never_reach_an_event(key):
    """An allow-nothing rule at the source, not a convention in the renderer."""
    assert safe_metadata({key: "hunter2", "safe": 1}) == {"safe": 1}


def test_long_strings_are_truncated():
    cleaned = safe_metadata({"message": "x" * 5000})
    assert len(cleaned["message"]) <= events._MAX_STR + 3


def test_nested_payloads_are_bounded_rather_than_carried():
    deep = {"a": {"b": {"c": {"d": "too deep to be a trace line"}}}}
    cleaned = safe_metadata(deep)
    # Two levels survive; the payload underneath does not. An event is a
    # progress line, not a channel for a result set.
    assert cleaned == {"a": {"b": {}}} or cleaned == {}


def test_lists_are_capped():
    assert len(safe_metadata({"tools": list(range(100))})["tools"]) <= 12


# --- subscribing -------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_subscriber_receives_events_published_from_another_thread(bus):
    bus.open_run("r1")
    with bus.subscribe("r1") as queue:
        threading.Thread(
            target=lambda: bus.publish("r1", EventType.MCP_TOOL_COMPLETED,
                                       title="get_curve")).start()
        event = await queue.get()
    assert event.title == "get_curve"


@pytest.mark.asyncio
async def test_closing_a_run_releases_its_subscribers(bus):
    """A subscriber told nothing more is coming can stop waiting.

    Without this the SSE response holds the connection open for its whole idle
    timeout on a turn that has already answered.
    """
    bus.open_run("r1")
    with bus.subscribe("r1") as queue:
        bus.close_run("r1")
        assert await queue.get() is None
    assert bus.is_finished("r1")


def test_a_subscriber_that_disappears_does_not_break_publishing(bus):
    bus.open_run("r1")

    class DeadLoop:
        def call_soon_threadsafe(self, *_args, **_kwargs):
            raise RuntimeError("event loop is closed")

    bus._subscribers["r1"] = [(DeadLoop(), object())]
    # The publish must succeed and the event must still be in the history; a
    # browser tab that closed mid-turn cannot be allowed to fail the turn.
    bus.publish("r1", EventType.REQUEST_COMPLETED, title="done")
    assert bus.history("r1")[-1].title == "done"


# --- latency -----------------------------------------------------------------


def _seed_latency(bus, request_id="r1"):
    bus.open_run(request_id)
    bus.publish(request_id, EventType.MODEL_CALL_COMPLETED, agent="orchestrator",
                duration_ms=1800, metadata={"call_site": "orchestrator"})
    bus.publish(request_id, EventType.MODEL_CALL_COMPLETED, agent="domain_expert",
                duration_ms=61200, metadata={"call_site": "domain_expert"})
    bus.publish(request_id, EventType.RETRIEVAL_COMPLETED, agent="domain-expert",
                duration_ms=740)
    bus.publish(request_id, EventType.MCP_TOOL_COMPLETED, agent="mcp-agent",
                duration_ms=440, tool_name="get_yield_curve")
    bus.publish(request_id, EventType.AGENT_HANDOFF_COMPLETED,
                agent="domain-expert", duration_ms=64000)


def test_latency_is_split_by_call_site_not_lumped_into_one_llm_total(monkeypatch):
    bus = EventBus()
    monkeypatch.setattr(events, "_BUS", bus)
    _seed_latency(bus)
    report = latency_report("r1", total_ms=70000)
    components = {row["component"]: row for row in report["components"]}

    # "The LLM took 63 seconds" is not actionable. "The domain expert's
    # reasoning took 61 of them" is where an optimisation would go.
    assert components["llm:domain_expert"]["total_ms"] == 61200
    assert components["llm:orchestrator"]["total_ms"] == 1800
    assert components["qdrant"]["total_ms"] == 740
    assert components["mcp_tool"]["total_ms"] == 440


def test_nested_spans_are_reported_but_never_given_a_percentage(monkeypatch):
    """An A2A handoff contains the spans beneath it.

    Summing it with its own children attributes the same seconds twice and
    produces a table whose percentages exceed 100 - which is not a rounding
    problem, it is a table that means nothing.
    """
    bus = EventBus()
    monkeypatch.setattr(events, "_BUS", bus)
    _seed_latency(bus)
    report = latency_report("r1", total_ms=70000)
    handoff = next(r for r in report["components"] if r["component"] == "a2a_handoff")

    assert handoff["nested"] is True
    assert handoff["pct"] is None
    assert handoff["total_ms"] not in (report["attributed_ms"],)
    assert report["attributed_ms"] == 1800 + 61200 + 740 + 440
    assert sum(r["pct"] for r in report["components"] if r["pct"] is not None) <= 100


def test_unmeasured_time_is_named_rather_than_distributed(monkeypatch):
    bus = EventBus()
    monkeypatch.setattr(events, "_BUS", bus)
    _seed_latency(bus)
    report = latency_report("r1", total_ms=70000)
    assert report["unattributed_ms"] == 70000 - report["attributed_ms"]


def test_a_span_with_no_measured_duration_is_not_counted(monkeypatch):
    bus = EventBus()
    monkeypatch.setattr(events, "_BUS", bus)
    bus.open_run("r1")
    bus.publish("r1", EventType.MODEL_CALL_STARTED, agent="orchestrator")
    report = latency_report("r1", total_ms=1000)
    # A start event carries no duration, so it contributes nothing. Estimating
    # one would put a fabricated number in a latency report.
    assert report["components"] == []
    assert report["attributed_ms"] == 0


# --- correlation -------------------------------------------------------------


def test_emit_without_a_request_id_is_a_no_op(monkeypatch):
    bus = EventBus()
    monkeypatch.setattr(events, "_BUS", bus)
    monkeypatch.setattr(events, "current_request_id", lambda: "")
    assert events.emit(EventType.REQUEST_RECEIVED, title="orphan") is None


def test_the_request_id_propagates_from_the_context(monkeypatch):
    bus = EventBus()
    monkeypatch.setattr(events, "_BUS", bus)
    token = events.set_request_id("ctx-123")
    try:
        events.emit(EventType.REQUEST_RECEIVED, title="from the context")
    finally:
        events.reset_request_id(token)
    assert [e.title for e in bus.history("ctx-123")] == ["from the context"]


def test_stage_publishes_a_start_a_finish_and_a_measured_duration(monkeypatch):
    bus = EventBus()
    monkeypatch.setattr(events, "_BUS", bus)
    token = events.set_request_id("r1")
    try:
        with events.stage(EventType.RETRIEVAL_STARTED,
                          EventType.RETRIEVAL_COMPLETED,
                          agent="domain-expert", title="search") as extra:
            extra["chunks"] = 6
    finally:
        events.reset_request_id(token)

    started, finished = bus.history("r1")
    assert started.event_type == EventType.RETRIEVAL_STARTED
    assert started.duration_ms is None
    assert finished.event_type == EventType.RETRIEVAL_COMPLETED
    assert finished.status == "completed"
    assert finished.duration_ms is not None and finished.duration_ms >= 0
    assert finished.metadata["chunks"] == 6


def test_stage_reports_a_failure_and_re_raises_it(monkeypatch):
    """This times work; it does not swallow the work's failures."""
    bus = EventBus()
    monkeypatch.setattr(events, "_BUS", bus)
    token = events.set_request_id("r1")
    try:
        with pytest.raises(ValueError):
            with events.stage(EventType.MCP_TOOL_STARTED,
                              EventType.MCP_TOOL_COMPLETED,
                              failed=EventType.MCP_TOOL_FAILED,
                              agent="mcp-agent", title="get_curve"):
                raise ValueError("the server refused")
    finally:
        events.reset_request_id(token)

    failure = bus.history("r1")[-1]
    assert failure.event_type == EventType.MCP_TOOL_FAILED
    assert failure.status == "failed"
    # The exception TYPE, never its message: an exception string carries hosts,
    # ports and internal identifiers, and this is rendered in a browser.
    assert failure.summary == "ValueError"
    assert "the server refused" not in str(failure.as_dict())


# --- the SSE endpoint ---------------------------------------------------------


def test_an_unknown_run_is_not_the_same_thing_as_a_finished_one():
    """The defect that made the whole live view deliver nothing.

    The client subscribes BEFORE it posts, so at subscribe time the turn does
    not exist. `is_finished()` answers True for a run it has never heard of -
    which is the right answer for "should a reader stop waiting on a turn that
    is over" and the wrong one for "has this turn started". The endpoint claims
    the run first, and that is what this pins.
    """
    bus = EventBus()
    assert bus.is_finished("never-mentioned") is True     # unknown
    bus.open_run("never-mentioned")
    assert bus.is_finished("never-mentioned") is False    # claimed, not over
    bus.close_run("never-mentioned")
    assert bus.is_finished("never-mentioned") is True     # genuinely over


def test_claiming_a_run_twice_does_not_restart_its_timeline():
    """`open_run` is idempotent, which is what lets the endpoint call it safely.

    The SSE handler and the turn itself both claim the run. If the second claim
    reset the origin, every elapsed time in the timeline would jump backwards
    the moment the turn started.
    """
    bus = EventBus()
    bus.open_run("r1")
    bus.publish("r1", EventType.REQUEST_RECEIVED, title="first")
    bus.open_run("r1")
    bus.publish("r1", EventType.ORCHESTRATOR_STARTED, title="second")
    history = bus.history("r1")
    assert [e.title for e in history] == ["first", "second"]
    assert history[1].elapsed_ms >= history[0].elapsed_ms


@pytest.mark.asyncio
async def test_the_stream_endpoint_delivers_events_published_after_subscribing():
    """The endpoint's own generator, driven in the order the browser uses it.

    Subscribe, then publish, then read - because that sequence is the one that
    was broken, and a test that published first would have passed throughout.

    The generator is driven directly rather than through `TestClient.stream`:
    the test client runs the app on a portal thread and its line iterator does
    not interleave with a publisher on a third thread, so the transport hangs
    while the logic under test is fine. Driving the generator keeps the subject
    the endpoint's own claim/replay/subscribe/terminate behaviour.
    """
    import json

    from backend.api.service import chat_stream

    request_id = "sse-endpoint-1"
    response = await chat_stream(request_id)
    frames = response.body_iterator

    # Claiming the run is what the endpoint must do BEFORE deciding whether the
    # turn is over. Without it, a not-yet-started turn reads as finished.
    assert events.bus().is_finished(request_id) is False

    events.bus().publish(request_id, EventType.ORCHESTRATOR_STARTED,
                         agent="orchestrator", title="Analysing")
    first = await frames.__anext__()
    assert "Analysing" in first
    # Published only now, i.e. AFTER the generator has started and while it is
    # suspended. This is the window the old ordering dropped events in: replay
    # had finished and the subscription had not yet been registered.

    events.bus().publish(request_id, EventType.REQUEST_COMPLETED,
                         agent="system", title="Completed", status="completed")
    second = await frames.__anext__()
    assert "Completed" in second

    events.bus().close_run(request_id)
    last = await frames.__anext__()
    assert last.startswith("event: done")
    assert json.loads(last.split("data: ", 1)[1])["request_id"] == request_id


@pytest.mark.asyncio
async def test_a_finished_turn_replays_its_history_and_closes_at_once():
    """Reconnecting after the answer must not wait for a turn that is over."""
    request_id = "sse-endpoint-2"
    events.bus().open_run(request_id)
    events.bus().publish(request_id, EventType.REQUEST_RECEIVED, title="one")
    events.bus().close_run(request_id)

    from backend.api.service import chat_stream

    response = await chat_stream(request_id)
    frames = [frame async for frame in response.body_iterator]

    assert len(frames) == 2                   # the replayed event, then done
    assert "one" in frames[0]
    assert frames[1].startswith("event: done")
    assert '"replayed": true' in frames[1]
