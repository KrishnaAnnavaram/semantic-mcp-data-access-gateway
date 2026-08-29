"""The HTTP service in front of the three-agent A2A network.

This is the only thing the UI talks to, and the only thing that talks to the
orchestrator on the user's behalf:

    POST /chat  { "query": "...", "session_id": "..." }
      -> { "answer", "sources", "trace", "awaiting_clarification",
           "tables", "data_plan", "negotiation", "catalogue", "calculation",
           "langsmith_url", "langsmith_trace_id", "langsmith_project", "handoffs" }
    POST /summarise { "messages": [...] } -> { "title": "..." }
    GET  /health -> { "status", "llm_backend", "models", "data_backend",
                      "langsmith", "a2a" }

`/chat` does not call an agent's method. It sends an A2A message to the
orchestrator, which is the only agent whose card admits the user boundary at
all — the domain expert and the MCP agent refuse a request from it by name. The
client contract is unchanged; what changed is what happens on the other side of
it.

    POST /chat ──A2A(handle_user_turn)──► orchestrator ──A2A──► specialists

The three agents are also mounted here as independently addressable services:

    /a2a/orchestrator/.well-known/agent-card.json    and JSON-RPC at /a2a/orchestrator/
    /a2a/domain-expert/...
    /a2a/mcp-agent/...

Mounting them is what makes "each agent is individually addressable" true rather
than claimed, and it is how the cards are discovered. It is *not* a second route
to the data: the specialists' caller allow-lists mean a browser that POSTs
directly to `/a2a/mcp-agent/` is rejected, not served.

The service owns session memory; the agents are stateless between turns. It also
owns the return leg of elicitation: when a specialist stops a task waiting for a
human, the task id is held against the session so the user's next message
resumes that task instead of starting new work.

Run it:

    python -m backend.api.service      # :8000

The model backend defaults to `zai` (glm-5.3 at every call site); set
LLM_BACKEND=anthropic to run on Claude. `/health` reports which one is live.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from a2a.utils.constants import PROTOCOL_VERSION_CURRENT
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Load .env before anything reads the environment. Without this the service
# starts happily and only fails at the first /chat, because the Anthropic client
# resolves its key at construction — a confusing way to discover a missing key.
from treasury_db.db import load_dotenv

load_dotenv()


app = FastAPI(title="semantic-mcp-data-access-gateway", version="0.2.0")

# The React frontend is a separate origin (Vite dev server, or a built static
# host later), so the browser enforces CORS even though the socket is reachable.
# `CORS_ALLOWED_ORIGINS` is a comma-separated override for non-default hosts;
# the Vite defaults cover local dev out of the box.
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_allowed_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", _default_origins).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# session_id -> {"turns": [...], "clarified": bool, "waiting": {...} | None}.
# In-memory, so it resets on restart. `clarified` records whether the last turn
# asked a question, which is what stops the agent asking a second one and
# looping the user; `waiting` records a specialist A2A task left in
# `input-required`, so the user's answer resumes that task rather than being
# read as a fresh question.
_sessions: dict[str, dict] = {}


_network = None


def get_network():
    """The three-agent A2A network, built once.

    Built lazily so the service can start and report health before Qdrant or the
    MCP children are reachable; a failure here should surface on a request, not
    at import.
    """
    global _network  # noqa: PLW0603
    if _network is None:
        from agents import get_network as build_network  # noqa: PLC0415
        from agents import log_status  # noqa: PLC0415
        from backend.knowledge.knowledge_base import KnowledgeBase  # noqa: PLC0415
        from backend.knowledge.market_risk_kb import (  # noqa: PLC0415
            MarketRiskKnowledgeBase,
        )
        from backend.providers.base import make_data_provider  # noqa: PLC0415

        log_status()
        _network = build_network(
            KnowledgeBase(), make_data_provider(),
            market_risk_knowledge=MarketRiskKnowledgeBase())
    return _network


def mount_a2a_agents(fastapi_app: FastAPI) -> None:
    """Expose each agent at its own path on this service, from startup.

    Each agent is a separate ASGI application with its own card and its own
    JSON-RPC endpoint; mounting them here means one process to run and one port
    to configure while every agent still has a real, distinct address. Moving
    one onto its own host is then a matter of serving its app elsewhere and
    setting `A2A_<AGENT>_URL` — no code in the agents changes.

    The mount is registered now and the agent behind it is built on the first
    request, so a card can be fetched from a freshly started service without a
    `/chat` having to happen first.
    """
    from agents.a2a.identity import MOUNT_PATHS  # noqa: PLC0415
    from agents.a2a.server import LazyAgentApp  # noqa: PLC0415

    mounted = {r.path for r in fastapi_app.routes if hasattr(r, "path")}
    for agent, path in MOUNT_PATHS.items():
        if path not in mounted:
            fastapi_app.mount(
                path, LazyAgentApp(agent, lambda a: get_network().apps[a]),
                name=f"a2a-{agent.value}")


mount_a2a_agents(app)


class SummaryRequest(BaseModel):
    messages: list[dict] = Field(..., min_length=1)


class SummaryResponse(BaseModel):
    title: str


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    session_id: str | None = None
    # The client chooses this before it asks, and opens `/chat/stream/{id}`
    # first, so it is already watching by the time the orchestrator starts
    # thinking. Optional: a client that does not want the live view omits it
    # and the server generates one, exactly as before.
    request_id: str | None = Field(default=None, max_length=48)


class ElicitationOption(BaseModel):
    label: str
    value: str


class ElicitationPayload(BaseModel):
    """A question back to the user, structured so the UI can render choices.

    Sent instead of a guessed answer whenever a required detail is missing.
    The client answers by POSTing again with the same session_id."""

    question: str
    options: list[ElicitationOption] = []


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = []
    trace: list[dict] = []
    awaiting_clarification: bool = False
    elicitation: ElicitationPayload | None = None
    route: str = "quant"
    # Tabular results travel as columns + rows, never as a markdown string: the
    # client renders them in a real table widget, and a pre-formatted blob
    # cannot be sorted, scrolled or exported.
    tables: list[dict] = []
    # The domain expert's requirement: fields, rows, the verbatim quote it was
    # grounded in, and the knowledge chunks behind it.
    data_plan: dict | None = None
    # The discussion between the domain expert and the MCP agent, so the UI can
    # show that the requirement was argued rather than assumed.
    negotiation: dict | None = None
    # What the MCP agent advertised it could do at the time of the request.
    catalogue: dict | None = None
    calculation: dict | None = None
    langsmith_url: str | None = None
    # The id of this turn's LangSmith trace, and the project it lives in. Carried
    # beside the URL so the frontend can label a message with its trace even when
    # the deep link is not opened, and so a message keeps its *own* trace rather
    # than sharing one global "latest" link. Both null when tracing is off.
    langsmith_trace_id: str | None = None
    langsmith_project: str | None = None
    # The turn's agent-to-agent ledger: who called whom, at what depth, with
    # which task id, how long it took and how much of the budget it spent.
    # Additive and optional - the frontend needs no change to keep working, and
    # gains the ability to show a handoff timeline when someone wants one.
    # Without it, following a request across agents means reading server logs.
    handoffs: dict | None = None
    # The turn's correlation id: the same value as `handoffs.user_request_id`,
    # as the live stream's `request_id`, and as the key `/trace/{id}` and
    # `/latency/{id}` are addressed by. One id, four views.
    request_id: str | None = None
    # The reply as sections - executive answer, scope, metrics, table, chart,
    # interpretation, methodology, assumptions, caveats, sources - adapted to
    # what kind of question this was. `answer` is unchanged, so a client that
    # ignores this renders exactly what it rendered before.
    structured: dict | None = None
    # Where this turn's time went, summed from measured durations only.
    latency: dict | None = None


@app.get("/health")
def health(analytics: bool = False) -> dict:
    """Liveness, plus which engines are actually answering.

    The model backend is reported here rather than only logged. `log_status()`
    writes it at INFO, but uvicorn's logging configuration swallows that, so a
    running service had no way of being *asked* which vendor it was using — and
    "which model answered this" is exactly the question worth being able to
    settle without reading source or restarting anything.

    `redacted()` reports whether a key is present, never the key.

    Redis analytics (top questions, latency percentiles, a stream length scan)
    cost more than a liveness probe should pay on every call, so they are
    opt-in via `?analytics=true` rather than gathered on the default path that
    a monitor or load balancer polls every few seconds.
    """
    status: dict[str, Any] = {"status": "ok"}
    try:
        from llm import provider_status  # noqa: PLC0415

        models = provider_status()
        status["llm_backend"] = models.get("backend")
        status["models"] = models.get("models")
        status["api_key_configured"] = models.get("api_key_configured")
    except Exception as exc:  # noqa: BLE001 - health must answer even when broken
        status["llm_backend"] = "unavailable"
        status["model_layer_error"] = str(exc)
        status["api_key_configured"] = False
    status["data_backend"] = os.environ.get("DATA_BACKEND", "mock")
    # LangSmith observability status. Reported so the UI header can show whether
    # tracing is on without guessing from the frontend's own mode, and so an
    # operator can settle "why are my traces missing" from one endpoint. This is
    # *configured*, not *verified*: it reads the environment and makes no network
    # call, because `/health` must answer whether or not LangSmith is reachable —
    # and LangSmith being down must never make this service report unhealthy. The
    # API key is never included; only whether one is present.
    try:
        from agents.observability import langsmith_status  # noqa: PLC0415

        status["langsmith"] = langsmith_status()
    except Exception as exc:  # noqa: BLE001 - health must answer even when broken
        status["langsmith"] = {"enabled": False, "error": str(exc),
                               "reason": "observability layer unavailable"}
    try:
        from agents.cache import get_intelligence  # noqa: PLC0415

        status["redis"] = get_intelligence().health(include_analytics=analytics)
    except Exception as exc:  # noqa: BLE001 - health still reports the failure
        status["redis"] = {"enabled": True, "connected": False,
                           "error": str(exc)}
    # Configuration only — deliberately not a probe. `/health` must answer
    # before Qdrant or the MCP children are up, and building the network to
    # report on it would make the liveness check the thing most likely to fail.
    try:
        from agents.a2a.elicitation import max_clarification_retries  # noqa: PLC0415
        from agents.a2a.guardrails import (  # noqa: PLC0415
            max_chain, max_handoffs, max_reentry, turn_timeout_s)
        from agents.planning import MAX_NEGOTIATION_ROUNDS  # noqa: PLC0415
        from agents.a2a.identity import AgentId, card_url, transport_mode  # noqa: PLC0415

        from agents.a2a.identity import MOUNT_PATHS  # noqa: PLC0415

        status["a2a"] = {
            "transport": transport_mode(),
            "protocol_version": PROTOCOL_VERSION_CURRENT,
            # Both forms, because they answer different questions. `path` is
            # where this service serves the agent and is what a reader should
            # append to the host they just called; `configured_url` is what the
            # agents themselves dial, which differs the moment one is moved.
            "agents": {agent.value: {
                "path": MOUNT_PATHS[agent],
                "card": f"{MOUNT_PATHS[agent]}/.well-known/agent-card.json",
                "configured_url": card_url(agent),
            } for agent in AgentId},
            # Five distinct bounds, because they stop five distinct
            # runaways. A single number cannot: a chain of eight steps
            # that never revisits an agent is healthy, while the same
            # agent asked the same thing four times is a cycle.
            "limits": {"max_chain": max_chain(),
                       "max_reentry": max_reentry(),
                       "max_handoffs": max_handoffs(),
                       "max_negotiation_rounds": MAX_NEGOTIATION_ROUNDS,
                       "max_clarifications": max_clarification_retries(),
                       "turn_timeout_seconds": turn_timeout_s()},
            "network_built": _network is not None,
        }
    except Exception as exc:  # noqa: BLE001 - health must answer even when broken
        status["a2a"] = {"error": str(exc)}
    return status


@app.post("/summarise", response_model=SummaryResponse)
def summarise(req: SummaryRequest) -> SummaryResponse:
    """Name a conversation from what it turned out to be about.

    The first question is a poor title -- it is often the vaguest thing the user
    ever says, and gets replaced by a clarification a turn later."""
    try:
        title = get_network().summarise(req.messages)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"summary failed: {exc}") from exc
    return SummaryResponse(title=title)


def _response_for(outcome) -> ChatResponse:
    """Shape an `AgentOutcome` into the `/chat` contract.

    `awaiting_clarification` follows the **route**, never the prose. The old
    single-agent loop had to infer it from the text and got it wrong in both
    directions - a finished answer ending "Want me to run DV01?" was reported as
    a pending question, and the UI drew a "pick one" prompt underneath it. Here
    the orchestrator has already decided, so there is nothing left to infer.
    """
    requirement = outcome.requirement
    clarifying = outcome.route == "clarify"
    return ChatResponse(
        answer=outcome.answer,
        sources=[c.get("label", "") for c in outcome.citations],
        trace=outcome.trace,
        awaiting_clarification=clarifying,
        elicitation=(ElicitationPayload(
            question=outcome.intent.question or outcome.answer,
            options=outcome.intent.options)
            if clarifying and outcome.intent else None),
        route=outcome.route,
        tables=outcome.tables,
        data_plan=requirement.as_dict() if requirement else None,
        negotiation=outcome.negotiation.as_dict() if outcome.negotiation else None,
        catalogue=outcome.catalogue.as_dict() if outcome.catalogue else None,
        calculation=outcome.calculation,
        langsmith_url=outcome.langsmith_url,
        langsmith_trace_id=outcome.langsmith_trace_id,
        # Only meaningful alongside a real trace; null when tracing is off keeps
        # the client from labelling a message with a project it never traced to.
        langsmith_project=(_langsmith_project() if outcome.langsmith_url else None),
        handoffs=outcome.handoffs,
        request_id=outcome.request_id or None,
        structured=outcome.structured,
        latency=outcome.latency,
    )


def _langsmith_project() -> str | None:
    """The configured LangSmith project, or None if tracing is unavailable.

    Never raises: the project name is cosmetic, and a broken observability
    import must not turn a successful turn into a 502.
    """
    try:
        from agents.observability import project_name  # noqa: PLC0415

        return project_name()
    except Exception:  # noqa: BLE001 - cosmetic
        return None


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """One turn, sent to the orchestrator over A2A.

    The orchestrator classifies, and for a data request the domain expert
    derives a requirement from Qdrant and negotiates it with the MCP agent —
    each of those an A2A task in its own right — and only then is anything
    fetched. The negotiation transcript travels back as an artifact so the UI
    can show that the reduction was argued, not assumed.

    When the previous turn left a specialist task waiting on a human, this
    message is that answer: it is relayed back into the same task rather than
    classified as a new question.
    """
    network = get_network()
    started = time.perf_counter()
    session = _sessions.get(req.session_id) or {} if req.session_id else {}
    history = session.get("turns")
    try:
        outcome = network.handle(req.query, history=history,
                                 already_clarified=session.get("clarified", False),
                                 session_id=req.session_id,
                                 waiting=session.get("waiting"),
                                 pending_clarification=session.get("clarification"),
                                 request_id=req.request_id or "")
    except Exception as exc:  # surface a clean error to the chatbot client
        raise HTTPException(status_code=502, detail=f"agent error: {exc}") from exc

    try:
        request_id = str((outcome.handoffs or {}).get("user_request_id") or "")
        decision = (outcome.negotiation.decision
                    if outcome.negotiation is not None else None)
        result_status = decision or (
            "input_required" if outcome.route == "clarify" else "completed")
        network.intelligence.complete_run(
            request_id, question=req.query, route=outcome.route,
            result_status=result_status,
            total_latency_ms=round((time.perf_counter() - started) * 1000),
            negotiation_rounds=(outcome.negotiation.rounds_used
                                if outcome.negotiation is not None else 0))
    except Exception:  # noqa: BLE001 - analytics never changes the response
        pass

    if req.session_id:
        # The agents are stateless between turns; the service owns session
        # memory. Keep the turn pair so a follow-up ("and the 30 year?") still
        # has context.
        turns = list(history or [])
        turns += [{"role": "user", "content": req.query},
                  {"role": "assistant", "content": outcome.answer}]
        _sessions[req.session_id] = {
            "turns": turns[-12:],
            # Remember that this turn asked a question, so the next one cannot.
            "clarified": outcome.route == "clarify",
            # And remember which specialist task, if any, that question came
            # from — that is the correlation the resumed A2A task needs.
            "waiting": outcome.waiting,
            # A pre-flight clarification has no task to resume — nothing had
            # started — so what has to survive is the *question it interrupted*.
            # Holding it here is what lets the next turn read "last 30 days" as
            # the answer it is rather than as a new request with no subject.
            "clarification": outcome.clarification,
        }

    return _response_for(outcome)


@app.get("/chat/stream/{request_id}")
async def chat_stream(request_id: str) -> StreamingResponse:
    """The turn's execution events, as they happen (SSE).

    **Why SSE and not WebSockets.** The traffic is one-directional: the server
    reports progress and the browser reports nothing back. A WebSocket would
    add a second protocol, a second failure mode, a handshake to get through
    whatever proxy sits in front of this, and its own reconnect logic — to carry
    a stream of small JSON objects in one direction. SSE is a plain GET over the
    same HTTP stack `/chat` already uses, it survives the same CORS
    configuration, `EventSource` reconnects on its own, and the whole client is
    thirty lines. The moment the browser needs to *send* something mid-turn —
    cancel this run, answer a question inline — a WebSocket earns its keep; it
    does not before then.

    **This is a view, not a channel the answer depends on.** The turn runs on
    `POST /chat` exactly as it always has. If nobody subscribes, if the
    subscriber disconnects, or if this endpoint is never called, the answer is
    identical — the publisher never waits for a reader. The client opens this
    first, then posts, and the bounded per-run history covers the race.

    The stream ends when the turn does. A subscriber to a turn that has already
    finished gets its replayed history and an immediate close, which is what
    makes a reconnect after a dropped connection cheap rather than a hang.
    """
    from agents.events import bus  # noqa: PLC0415

    event_bus = bus()
    # Claim the run before anything is read from it.
    #
    # This is load-bearing, and getting it wrong made the whole live view
    # silently deliver nothing. The client subscribes BEFORE it posts, so at
    # this moment the turn does not exist yet — and to `is_finished()` a run it
    # has never heard of is indistinguishable from one that has ended, so the
    # stream closed immediately and every event of the turn arrived to nobody.
    #
    # `open_run` is idempotent by request id: it registers the turn if this is
    # the first mention of it and leaves an existing one (including a finished
    # one being re-read) exactly as it stands. It also starts the timeline at
    # the moment the browser began waiting, which is the honest origin for a
    # number labelled "elapsed".
    event_bus.open_run(request_id)

    async def publish():
        # **Subscribe before replaying, not after.** The obvious order — replay
        # the history, then start listening — has a window between the two, and
        # anything published inside it belongs to neither: too late for the
        # replay, too early for the subscription. On a turn whose first events
        # land within milliseconds of the connection that is not a rare race,
        # it is the common case.
        #
        # Subscribing first cannot lose an event; it can only deliver one
        # twice, and `seen` already discards the duplicate because sequence
        # numbers are monotonic per turn. Trading a silent loss for a cheap
        # comparison is the right way round.
        idle = 0
        # A turn that never arrives must not hold the connection forever — a
        # mistyped or abandoned request id would otherwise pin a response for
        # the life of the process. Generous on purpose: the bound has to exceed
        # the turn deadline (900s) or it would cut off turns that are running
        # normally, which is the failure this whole channel exists to prevent.
        max_idle = int(1200 / 15)
        with event_bus.subscribe(request_id) as queue:
            seen = 0
            for event in event_bus.history(request_id):
                seen = event.sequence
                yield _sse("event", event.as_dict())
            if event_bus.is_finished(request_id):
                yield _sse("done", {"request_id": request_id, "replayed": True})
                return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    # A comment frame. Idle proxies close a connection that has
                    # been silent for long enough, and a single reasoning call
                    # can legitimately be silent for a minute.
                    yield ": keep-alive\n\n"
                    idle += 1
                    if event_bus.is_finished(request_id) or idle >= max_idle:
                        break
                    continue
                idle = 0
                if event is None:
                    break
                if event.sequence <= seen:
                    continue        # already replayed above
                seen = event.sequence
                yield _sse("event", event.as_dict())
        yield _sse("done", {"request_id": request_id})

    return StreamingResponse(
        publish(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 # Nginx buffers proxied responses by default, which turns a
                 # live stream into one delivery at the end — the exact failure
                 # this endpoint exists to remove.
                 "X-Accel-Buffering": "no"})


def _sse(event: str, payload: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


@app.get("/trace/{request_id}")
def request_trace(request_id: str) -> dict:
    """This turn's own execution trace and latency breakdown.

    Served from the events the gateway recorded itself, so it answers whether
    or not LangSmith is configured, reachable, or has finished ingesting. That
    is deliberate: observability must never be a dependency of being able to
    explain what happened, and a trace view that goes blank when a SaaS is slow
    is a trace view nobody trusts in the moment they need it.
    """
    from agents.events import bus, latency_report, timeline  # noqa: PLC0415

    events = timeline(request_id)
    return {
        "request_id": request_id,
        "available": bool(events),
        "finished": bus().is_finished(request_id),
        "events": events,
        "latency": latency_report(request_id),
    }


@app.get("/langsmith/trace/{trace_id}")
def langsmith_trace(trace_id: str) -> dict:
    """The LangSmith span tree for one turn, fetched and sanitised server-side.

    The API key never leaves this process. The browser asks this service for a
    trace id it already holds; this service is what holds the credential and
    what decides which fields may travel.

    Always answers. LangSmith being disabled, unreachable, or still ingesting
    are three different facts and all three come back as `available: false` with
    the reason named — never as a 5xx, because a missing trace must not look
    like a broken gateway.
    """
    from backend.api.langsmith_reader import fetch_trace  # noqa: PLC0415

    return fetch_trace(trace_id)


if __name__ == "__main__":
    import logging

    import uvicorn

    # Without a root handler, uvicorn's logging configuration swallows every
    # INFO line this application writes - including the A2A handoff log, which
    # is the only way to follow one request across three agents while it is
    # happening. `A2A_LOG_LEVEL=DEBUG` turns up the detail.
    logging.basicConfig(
        level=os.environ.get("A2A_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)-7s %(name)-24s %(message)s",
    )
    # httpx logs one line per in-process A2A call at INFO, which doubles the
    # volume of the handoff log without adding to it.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("AGENT_PORT", "8000")))
