"""Agent HTTP service (Layer 2 keystone).

Exposes the SmartAgent over the REST contract the chatbot (Layer 1) already
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

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from smart_agent import SmartAgent, extract_sources, trace_as_dicts

app = FastAPI(title="Smart MCP Agent", version="0.1.0")

_agent: SmartAgent | None = None
_sessions: dict[str, list] = {}  # session_id -> prior conversation (in-memory)


def get_agent() -> SmartAgent:
    """Lazily build the agent once (loads the vector DB, wires the data provider)."""
    global _agent
    if _agent is None:
        _agent = SmartAgent()
    return _agent


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    session_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = []
    trace: list[dict] = []
    awaiting_clarification: bool = False


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "api_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY"))}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    agent = get_agent()
    history = _sessions.get(req.session_id) if req.session_id else None
    try:
        result = agent.answer(req.query, history=history)
    except Exception as exc:  # surface a clean error to the chatbot client
        raise HTTPException(status_code=502, detail=f"agent error: {exc}") from exc
    if req.session_id:
        _sessions[req.session_id] = result.messages  # persist for the next turn
    return ChatResponse(
        answer=result.answer,
        sources=extract_sources(result.trace),
        trace=trace_as_dicts(result.trace),
        awaiting_clarification=result.awaiting_clarification,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("AGENT_PORT", "8000")))
