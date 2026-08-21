"""Each agent as an addressable A2A service.

One ASGI application per agent, each serving exactly two things:

    <mount>/.well-known/agent-card.json   the card — identity, skills, capabilities
    <mount>/                             JSON-RPC — message/send, tasks/get, tasks/cancel

and one root application that mounts all three, so a single ASGI app answers for
the whole network:

    /a2a/orchestrator     /a2a/domain-expert     /a2a/mcp-agent

That root app is what the in-process transport dials, and the same three
sub-applications are what the FastAPI service mounts, so an agent is reachable
over a socket and in-process at the *same* URL. There is one address per agent,
not one per deployment mode.

Why Starlette apps rather than a separate FastAPI service per agent: three
processes to run, three ports to configure and three health checks to watch
would be distributed infrastructure with nothing distributed about it. The
addressing is real and the protocol is real; the topology is honest about being
local. Moving one agent onto its own host later means serving its app from a
different process and setting `A2A_<AGENT>_URL` — no code changes here.
"""

from __future__ import annotations

import logging

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from starlette.applications import Starlette
from starlette.routing import Mount

from agents.a2a.cards import agent_card
from agents.a2a.identity import MOUNT_PATHS, AgentId

LOGGER = logging.getLogger("agents.a2a.server")


def build_agent_app(agent: AgentId, executor) -> Starlette:
    """The ASGI application for one agent.

    The task store is in-memory on purpose. A task here lives for one user turn,
    or until the user answers a question; nothing in this system needs a task to
    survive a restart, and a database-backed store would be persistence for
    persistence's sake. Swapping it for `DatabaseTaskStore` is a one-line change
    the day that stops being true.
    """
    card = agent_card(agent)
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = Starlette(routes=[
        *create_agent_card_routes(card),
        *create_jsonrpc_routes(handler, "/"),
    ])
    # Kept so a caller holding the app can read the card without a request, and
    # so the service can drain in-flight tasks on shutdown.
    app.state.agent_card = card
    app.state.request_handler = handler
    app.state.agent_id = agent
    LOGGER.debug("built A2A app for %s with %d skill(s)",
                 agent.value, len(card.skills))
    return app


def build_network_app(apps: dict[AgentId, Starlette]) -> Starlette:
    """One ASGI app answering for every agent, at each agent's own mount path."""
    return Starlette(routes=[
        Mount(MOUNT_PATHS[agent], app=app) for agent, app in apps.items()
    ])


class LazyAgentApp:
    """An agent's address, live from startup; the agent itself, built on demand.

    The network is expensive to build — an embedded vector store, two MCP child
    processes — and building it at import would mean the service could not start
    and report health until every dependency it might eventually need was up.
    But an address that only appears after the first `/chat` is not an address:
    discovery is the one thing a caller does *before* it has any work to send,
    and a card that 404s until someone else has used the system is useless.

    So the mount is registered at import and the agent is resolved on the first
    request that reaches it. The resolution happens on a worker thread because
    it is synchronous and slow, and this runs on the server's event loop.
    """

    def __init__(self, agent: AgentId, resolve) -> None:
        self.agent = agent
        self._resolve = resolve
        self._app = None

    async def __call__(self, scope, receive, send) -> None:
        import asyncio  # noqa: PLC0415

        if self._app is None:
            self._app = await asyncio.to_thread(self._resolve, self.agent)
            LOGGER.info("A2A endpoint for %s resolved on first request",
                        self.agent.value)
        await self._app(scope, receive, send)
