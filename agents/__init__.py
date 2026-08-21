"""The three runtime agents of the semantic MCP data-access gateway.

    ORCHESTRATOR  ──A2A──►  DOMAIN EXPERT  ──A2A──►  MCP AGENT
      routing                Qdrant + reasoning       tools + execution

Each is a real agent: a model, a job, a published Agent Card, an addressable A2A
endpoint, and a traced boundary. The order is the design. Data is never fetched
until a domain expert has said, on the record and with a citation from the
vector store, what the task actually requires — and never fetched on terms the
data layer has not agreed it can serve.

Every arrow above is an A2A task, not a method call. The protocol layer lives in
`agents/a2a/`; the agents themselves import none of it.

Entry point — the orchestrator's A2A endpoint, reached through the network:

    from agents import get_network
    outcome = get_network().handle("What is the DV01 of the demo book?")

`DomainExpertAgent` and `McpAgent` are deliberately **not** exported here. They
are reached by sending their agent a message, and a name exported from the
package is an invitation to skip that. Their modules are still importable for
what genuinely needs them — their own executor, and a unit test of a pure
function — which is the difference between a boundary and a wall.
"""

from agents.a2a.cards import agent_card, all_cards
from agents.a2a.identity import AgentId
from agents.a2a.runtime import AgentNetwork, get_network, reset_network
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
from agents.observability import langsmith_status, log_status, run_url, traced
from agents.orchestrator_agent import OrchestratorAgent
from agents.pipeline import AgentPipeline
from agents.planning import MAX_ROUNDS, DataPlanner

__all__ = [
    "MAX_ROUNDS",
    "AgentId",
    "AgentNetwork",
    "AgentOutcome",
    "AgentPipeline",
    "DataPlanner",
    "FieldNote",
    "Intent",
    "KnowledgeChunk",
    "Negotiation",
    "OrchestratorAgent",
    "Requirement",
    "ServeResponse",
    "ToolCatalogue",
    "ToolSpec",
    "agent_card",
    "all_cards",
    "get_network",
    "langsmith_status",
    "log_status",
    "reset_network",
    "run_url",
    "traced",
]
