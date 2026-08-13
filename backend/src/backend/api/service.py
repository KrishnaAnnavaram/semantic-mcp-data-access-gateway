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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("AGENT_PORT", "8000")))
