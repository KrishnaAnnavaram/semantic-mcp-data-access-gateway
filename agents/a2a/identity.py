"""Who the agents are on the A2A network, and how they are addressed.

Explicit configuration, not service discovery. Three agents live in one
repository and one process; a registry, a broker or a discovery daemon would be
infrastructure with nothing to discover. What this module holds is the
*addressing* half of A2A — an id, a mount path, and a base URL — so that moving
one agent onto its own host later is an environment variable rather than a
refactor.

    AgentId.ORCHESTRATOR   /a2a/orchestrator
    AgentId.DOMAIN_EXPERT  /a2a/domain-expert
    AgentId.MCP            /a2a/mcp-agent

Each mount serves two things: the Agent Card at
``<mount>/.well-known/agent-card.json`` and the JSON-RPC endpoint at ``<mount>/``.

**Transport.** ``A2A_TRANSPORT=inprocess`` (default) dials the mounted ASGI app
directly through httpx's ASGI transport: real JSON-RPC, real serialisation, real
task lifecycle, no second port to run. ``A2A_TRANSPORT=http`` dials
``A2A_BASE_URL`` (or a per-agent override) over the network instead. The client
code is identical either way, which is the point of putting the choice here.
"""

from __future__ import annotations

import os
from enum import Enum

#: Bumped when the shape of what agents send each other changes, not when an
#: agent's reasoning changes. It travels in the Agent Card's `version`.
AGENT_VERSION = "1.0.0"

PROVIDER_ORGANISATION = "semantic-mcp-data-access-gateway"
PROVIDER_URL = "https://github.com/KrishnaAnnavaram/semantic-mcp-data-access-gateway"


class AgentId(str, Enum):
    """The three agents. There is no fourth, and adding one is a design change."""

    ORCHESTRATOR = "orchestrator"
    DOMAIN_EXPERT = "domain-expert"
    MCP = "mcp-agent"


#: Mount path per agent, relative to the backend service root.
MOUNT_PATHS: dict[AgentId, str] = {
    AgentId.ORCHESTRATOR: "/a2a/orchestrator",
    AgentId.DOMAIN_EXPERT: "/a2a/domain-expert",
    AgentId.MCP: "/a2a/mcp-agent",
}

#: The synthetic host used by the in-process transport. It is never resolved by
#: DNS — httpx's ASGI transport short-circuits before that — but a base URL is
#: still required to build absolute request URLs, and a `.local` name makes it
#: obvious in a log line that no socket was involved.
INPROCESS_BASE_URL = "http://agents.a2a.local"


def transport_mode() -> str:
    """`inprocess` (default) or `http`."""
    mode = os.environ.get("A2A_TRANSPORT", "inprocess").strip().lower()
    return mode if mode in {"inprocess", "http"} else "inprocess"


def base_url(agent: AgentId) -> str:
    """Where this agent answers, without the trailing slash.

    Per-agent overrides come first (`A2A_ORCHESTRATOR_URL` and friends), so one
    agent can be moved to another host without moving the other two.
    """
    override = os.environ.get(f"A2A_{agent.name}_URL", "").strip()
    if override:
        return override.rstrip("/")
    root = os.environ.get("A2A_BASE_URL", "").strip() or INPROCESS_BASE_URL
    return f"{root.rstrip('/')}{MOUNT_PATHS[agent]}"


def card_url(agent: AgentId) -> str:
    return f"{base_url(agent)}/.well-known/agent-card.json"
