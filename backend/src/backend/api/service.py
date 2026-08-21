"""The HTTP service in front of the three-agent A2A network.

This is the only thing the UI talks to, and the only thing that talks to the
orchestrator on the user's behalf:

    POST /chat  { "query": "...", "session_id": "..." }
      -> { "answer", "sources", "trace", "awaiting_clarification",
           "tables", "data_plan", "negotiation", "catalogue", "calculation" }
    POST /summarise { "messages": [...] } -> { "title": "..." }
    GET  /health -> { "status", "llm_backend", "models", "data_backend", "a2a" }

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

The model backend defaults to `zai` (glm-5.2 at every call site); set
LLM_BACKEND=anthropic to run on Claude. `/health` reports which one is live.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from a2a.utils.constants import PROTOCOL_VERSION_CURRENT
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
        from backend.providers.base import make_data_provider  # noqa: PLC0415

        log_status()
        _network = build_network(KnowledgeBase(), make_data_provider())
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
    # The turn's agent-to-agent ledger: who called whom, at what depth, with
    # which task id, how long it took and how much of the budget it spent.
    # Additive and optional - the frontend needs no change to keep working, and
    # gains the ability to show a handoff timeline when someone wants one.
    # Without it, following a request across agents means reading server logs.
    handoffs: dict | None = None


@app.get("/health")
def health() -> dict:
    """Liveness, plus which engines are actually answering.

    The model backend is reported here rather than only logged. `log_status()`
    writes it at INFO, but uvicorn's logging configuration swallows that, so a
    running service had no way of being *asked* which vendor it was using — and
    "which model answered this" is exactly the question worth being able to
    settle without reading source or restarting anything.

    `redacted()` reports whether a key is present, never the key.
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
        handoffs=outcome.handoffs,
    )


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
    session = _sessions.get(req.session_id) or {} if req.session_id else {}
    history = session.get("turns")
    try:
        outcome = network.handle(req.query, history=history,
                                 already_clarified=session.get("clarified", False),
                                 session_id=req.session_id,
                                 waiting=session.get("waiting"))
    except Exception as exc:  # surface a clean error to the chatbot client
        raise HTTPException(status_code=502, detail=f"agent error: {exc}") from exc

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
        }

    return _response_for(outcome)


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
