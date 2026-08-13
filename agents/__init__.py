"""The three runtime agents of the semantic MCP data-access gateway.

    ORCHESTRATOR (Haiku)  →  DOMAIN EXPERT (Opus)  ⇄  MCP AGENT (Opus)
         routing               Qdrant + reasoning       tools + execution

Each is a real agent: a model, a job, and a traced boundary. The order is the
design. Data is never fetched until a domain expert has said, on the record and
with a citation from the vector store, what the task actually requires — and
never fetched on terms the data layer has not agreed it can serve.

Entry point:

    from agents import AgentPipeline
    outcome = AgentPipeline(knowledge, data_provider).handle("...")
"""

from agents.contracts import (
    AgentOutcome,
    FieldNote,
    Intent,
    KnowledgeChunk,
    Negotiation,
    Requirement,
    ServeResponse,
    ToolCatalogue,
    ToolSpec,
)
from agents.domain_expert_agent import DomainExpertAgent
from agents.mcp_agent import McpAgent
from agents.observability import langsmith_status, log_status, run_url, traced
from agents.orchestrator_agent import OrchestratorAgent
from agents.pipeline import MAX_ROUNDS, AgentPipeline

__all__ = [
    "MAX_ROUNDS",
    "AgentOutcome",
    "AgentPipeline",
    "DomainExpertAgent",
    "FieldNote",
    "Intent",
    "KnowledgeChunk",
    "McpAgent",
    "Negotiation",
    "OrchestratorAgent",
    "Requirement",
    "ServeResponse",
    "ToolCatalogue",
    "ToolSpec",
    "langsmith_status",
    "log_status",
    "run_url",
    "traced",
]
