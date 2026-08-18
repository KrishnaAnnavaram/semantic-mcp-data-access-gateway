"""The HTTP service in front of the three-agent pipeline.

This is the only thing the UI talks to, and the only caller of `agents/`:

    POST /chat  { "query": "...", "session_id": "..." }
      -> { "answer", "sources", "trace", "awaiting_clarification",
           "tables", "data_plan", "negotiation", "catalogue", "calculation" }
    POST /summarise { "messages": [...] } -> { "title": "..." }
    GET  /health -> { "status", "llm_backend", "models", "data_backend" }

The service owns session memory; the pipeline is stateless. Run it:

    python -m backend.api.service      # :8000

The model backend defaults to `zai` (glm-5.2 at every call site); set
LLM_BACKEND=anthropic to run on Claude. `/health` reports which one is live.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Load .env before anything reads the environment. Without this the service
# starts happily and only fails at the first /chat, because the Anthropic client
# resolves its key at construction — a confusing way to discover a missing key.
from treasury_db.db import load_dotenv

load_dotenv()


app = FastAPI(title="semantic-mcp-data-access-gateway", version="0.2.0")

# session_id -> {"turns": [...], "clarified": bool}. In-memory, so it resets on
# restart; `clarified` records whether the last turn asked a question, which is
# what stops the agent asking a second one and looping the user.
_sessions: dict[str, dict] = {}


_pipeline = None


def get_pipeline():
    """The three-agent pipeline, built once.

    Orchestrator -> domain expert (Qdrant) <-> MCP agent. Built lazily so the
    service can start and report health before Qdrant or the MCP children are
    reachable; a failure here should surface on a request, not at import.
    """
    global _pipeline  # noqa: PLW0603
    if _pipeline is None:
        from agents import AgentPipeline, log_status  # noqa: PLC0415

        from backend.knowledge.knowledge_base import KnowledgeBase  # noqa: PLC0415
        from backend.providers.base import make_data_provider  # noqa: PLC0415

        log_status()
        _pipeline = AgentPipeline(KnowledgeBase(), make_data_provider())
    return _pipeline


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
    return status


@app.post("/summarise", response_model=SummaryResponse)
def summarise(req: SummaryRequest) -> SummaryResponse:
    """Name a conversation from what it turned out to be about.

    The first question is a poor title -- it is often the vaguest thing the user
    ever says, and gets replaced by a clarification a turn later."""
    try:
        title = get_pipeline().orchestrator.summarise_session(req.messages)
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
    )


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """One turn through the three-agent pipeline.

    Orchestrator classifies, and for a data request the domain expert derives a
    requirement from Qdrant, negotiates it with the MCP agent, and only then is
    anything fetched. The negotiation transcript travels back so the UI can show
    that the reduction was argued, not assumed.
    """
    pipeline = get_pipeline()
    session = _sessions.get(req.session_id) or {} if req.session_id else {}
    history = session.get("turns")
    try:
        outcome = pipeline.handle(req.query, history=history,
                                  already_clarified=session.get("clarified", False))
    except Exception as exc:  # surface a clean error to the chatbot client
        raise HTTPException(status_code=502, detail=f"agent error: {exc}") from exc

    if req.session_id:
        # The pipeline is stateless; the service owns session memory. Keep the
        # turn pair so a follow-up ("and the 30 year?") still has context.
        turns = list(history or [])
        turns += [{"role": "user", "content": req.query},
                  {"role": "assistant", "content": outcome.answer}]
        # Remember that this turn asked a question, so the next one cannot.
        _sessions[req.session_id] = {"turns": turns[-12:],
                                     "clarified": outcome.route == "clarify"}

    return _response_for(outcome)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("AGENT_PORT", "8000")))
