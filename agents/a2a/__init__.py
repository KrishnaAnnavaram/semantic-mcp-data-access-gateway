"""A2A — how the three runtime agents reach each other.

This package is the protocol boundary and nothing else. The agents' behaviour
lives one directory up, in modules that import none of this; everything here is
addressing, serialisation, hosting, calling and the bounds on all four.

    agent domain logic          orchestrator_agent / domain_expert_agent / mcp_agent
            ▲
    A2A adapter                 executors.py · ports.py · elicitation.py
            ▲
    A2A protocol + transport    cards.py · envelope.py · client.py · server.py
                                identity.py · guardrails.py · runtime.py

**A2A is not a replacement for MCP.** A2A carries agent-to-agent traffic: a
request for a capability another agent advertises, and the task that answers it.
MCP carries tools, resources and data — the Treasury database and the risk
engine, behind a privilege boundary no agent crosses. Both are load-bearing.

Design, guardrails and the elicitation relay: `docs/a2a.md`.
"""

from agents.a2a.cards import agent_card, all_cards, skill_ids
from agents.a2a.client import AgentLink, dispatch
from agents.a2a.envelope import SkillRequest, SkillResult
from agents.a2a.guardrails import HandoffRefused, LedgerRegistry, TurnLedger
from agents.a2a.identity import MOUNT_PATHS, AgentId, base_url, card_url, transport_mode
from agents.a2a.runtime import AgentNetwork, get_network, reset_network
from agents.a2a.server import build_agent_app, build_network_app

__all__ = [
    "MOUNT_PATHS",
    "AgentId",
    "AgentLink",
    "AgentNetwork",
    "HandoffRefused",
    "LedgerRegistry",
    "SkillRequest",
    "SkillResult",
    "TurnLedger",
    "agent_card",
    "all_cards",
    "base_url",
    "build_agent_app",
    "build_network_app",
    "card_url",
    "dispatch",
    "get_network",
    "reset_network",
    "skill_ids",
    "transport_mode",
]
