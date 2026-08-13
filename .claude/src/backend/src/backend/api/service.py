"""Agent HTTP service (Layer 2 keystone).

Exposes the QuantAgent over the REST contract the chatbot (Layer 1) already
expects:

    POST /chat  { "query": "...", "session_id": "..." }
      -> { "answer": "...", "sources": [...], "trace": [...],
           "awaiting_clarification": false }
    GET  /health -> { "status": "ok" }

Run it:
    ANTHROPIC_API_KEY=...  uvicorn agent_service:app --port 8000   # from src/
or  python src/agent_service.py                                    # convenience
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Load .env before anything reads the environment. Without this the service
# starts happily and only fails at the first /chat, because the Anthropic client
# resolves its key at construction — a confusing way to discover a missing key.
from treasury_db.db import load_dotenv

load_dotenv()

from backend.agent.orchestrator import Orchestrator  # noqa: E402
from backend.agent.quant_agent import extract_sources, trace_as_dicts  # noqa: E402

app = FastAPI(title="semantic-mcp-data-access-gateway", version="0.2.0")

_orchestrator: Orchestrator | None = None
_sessions: dict[str, list] = {}  # session_id -> prior conversation (in-memory)


def get_orchestrator() -> Orchestrator:
    """Build the orchestrator once. It builds the quant agent lazily in turn, so
    a process that only ever sees small talk never starts the MCP servers."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


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


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "api_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY"))}


@app.post("/summarise", response_model=SummaryResponse)
def summarise(req: SummaryRequest) -> SummaryResponse:
    """Name a conversation from what it turned out to be about.

    The first question is a poor title -- it is often the vaguest thing the user
    ever says, and gets replaced by a clarification a turn later."""
    try:
        title = get_orchestrator().summarise_session(req.messages)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"summary failed: {exc}") from exc
    return SummaryResponse(title=title)


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    orchestrator = get_orchestrator()
    history = _sessions.get(req.session_id) if req.session_id else None
    try:
        result = orchestrator.handle(req.query, history=history)
    except Exception as exc:  # surface a clean error to the chatbot client
        raise HTTPException(status_code=502, detail=f"agent error: {exc}") from exc
    if req.session_id:
        _sessions[req.session_id] = result.messages  # persist for the next turn
    return ChatResponse(
        answer=result.answer,
        sources=extract_sources(result.trace),
        trace=trace_as_dicts(result.trace),
        awaiting_clarification=result.awaiting_clarification,
        elicitation=(ElicitationPayload(**result.elicitation.as_dict())
                     if result.elicitation else None),
        route=result.route,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("AGENT_PORT", "8000")))
