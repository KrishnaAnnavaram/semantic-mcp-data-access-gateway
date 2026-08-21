"""The A2A network: three hosted agents, one loop, one way in.

    FastAPI /chat ──► AgentNetwork.handle ──A2A──► orchestrator
                                                       │
                                       ┌───────────A2A─┴──A2A────────┐
                                       ▼                             ▼
                                 domain-expert ──────A2A──────► mcp-agent

`AgentNetwork` owns everything that has to exist once per process: the three
agent objects, the three executors, the three ASGI apps, the A2A clients that
dial them, and the event loop all of that runs on. It is also the only door
into the system — `handle` and `summarise` are the user boundary, and they reach
the orchestrator over A2A like any other caller would.

**One loop, on a daemon thread.** The same shape the MCP bridge already uses,
and for the same reason: `DataProvider` and the agents are synchronous and are
called from FastAPI request handlers running in a thread pool, while A2A is
asyncio. A loop per call would rebuild three clients per question.

**Domain work runs on worker threads, not on that loop.** Each executor hands
its agent's work to a thread (see `executors.py`), which is what makes the
nested call work: while the domain expert is thinking on a worker thread, the
loop is free to serve the MCP agent call that thinking is about to make. The
loop's default executor is sized here rather than left at asyncio's default,
because one user turn can hold three worker threads at once and the default pool
is shared with everything else the loop does.
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.utils.constants import TransportProtocol
from starlette.applications import Starlette

from agents.a2a.cards import agent_card
from agents.a2a.client import AgentLink
from agents.a2a.envelope import ARTIFACT_OUTCOME, ARTIFACT_TITLE, SkillResult
from agents.a2a.executors import (
    DomainExpertExecutor,
    McpAgentExecutor,
    OrchestratorExecutor,
)
from agents.a2a.guardrails import LedgerRegistry, TurnLedger
from agents.a2a.identity import INPROCESS_BASE_URL, AgentId, base_url, transport_mode
from agents.a2a.server import build_agent_app, build_network_app
from agents.contracts import AgentOutcome

LOGGER = logging.getLogger("agents.a2a.runtime")

#: One user turn can hold three worker threads (orchestrator, domain expert, MCP
#: agent) plus whatever the data layer is doing. Sized for concurrent turns
#: rather than for one.
WORKER_THREADS = 32
STARTUP_TIMEOUT_S = 30.0


class _LoopThread:
    """An event loop that outlives any single request."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._loop.set_default_executor(
            ThreadPoolExecutor(max_workers=WORKER_THREADS,
                               thread_name_prefix="a2a-work"))
        self._ready = threading.Event()
        self._stop: asyncio.Event | None = None
        self._thread = threading.Thread(target=self._run, name="a2a-loop",
                                        daemon=True)
        self._thread.start()
        if not self._ready.wait(STARTUP_TIMEOUT_S):
            raise RuntimeError("the A2A event loop did not start")

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self) -> None:
        self._stop = asyncio.Event()
        self._ready.set()
        await self._stop.wait()

    def run(self, coro, timeout: float | None = None) -> Any:
        """Run a coroutine on the loop from a synchronous caller and wait."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def shutdown(self) -> None:
        if self._stop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._stop.set)
            self._thread.join(timeout=5)


class AgentNetwork:
    """The three agents, hosted and wired to each other over A2A."""

    def __init__(self, knowledge: Any = None, data_provider: Any = None) -> None:
        from agents.domain_expert_agent import DomainExpertAgent  # noqa: PLC0415
        from agents.mcp_agent import McpAgent  # noqa: PLC0415
        from agents.orchestrator_agent import OrchestratorAgent  # noqa: PLC0415

        self.ledgers = LedgerRegistry()
        self._closed = False
        self._loop_thread = _LoopThread()

        # The agents themselves, constructed once. The two specialists are
        # underscored deliberately: the only supported way to reach one is an
        # A2A message to its endpoint, and a public attribute is an invitation
        # to skip that. The orchestrator stays public because its own workflow
        # legitimately holds it — the orchestrator *is* the caller there.
        self.orchestrator_agent = OrchestratorAgent()
        self._domain_expert_agent = DomainExpertAgent(knowledge)
        self._mcp_agent = McpAgent(data_provider)

        self._executors = {
            AgentId.ORCHESTRATOR: OrchestratorExecutor(
                self.ledgers, self.orchestrator_agent, self),
            AgentId.DOMAIN_EXPERT: DomainExpertExecutor(
                self.ledgers, self._domain_expert_agent, self),
            AgentId.MCP: McpAgentExecutor(self.ledgers, self._mcp_agent),
        }
        self.apps: dict[AgentId, Starlette] = {
            agent: build_agent_app(agent, executor)
            for agent, executor in self._executors.items()
        }
        self.network_app = build_network_app(self.apps)

        self._links: dict[AgentId, AgentLink] = self._loop_thread.run(
            self._build_links(), STARTUP_TIMEOUT_S)
        atexit.register(self.shutdown)
        LOGGER.info("A2A network up (%s transport): %s", transport_mode(),
                    ", ".join(f"{a.value} at {base_url(a)}" for a in AgentId))

    # -- wiring --------------------------------------------------------------

    async def _build_links(self) -> dict[AgentId, AgentLink]:
        """One A2A client per agent, built on the loop that will use them.

        In-process, every client dials the same network app through httpx's ASGI
        transport: real JSON-RPC, real serialisation, real task lifecycle, no
        socket. Over `A2A_TRANSPORT=http` the identical client code dials the
        configured URLs instead, which is the property that makes moving an
        agent to its own host a configuration change.
        """
        mode = transport_mode()
        links: dict[AgentId, AgentLink] = {}
        for agent in AgentId:
            if mode == "inprocess":
                http = httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=self.network_app),
                    base_url=INPROCESS_BASE_URL, timeout=None)
            else:
                http = httpx.AsyncClient(base_url=base_url(agent), timeout=None)
            factory = ClientFactory(ClientConfig(
                # Not streaming: the cards do not advertise it, and a client
                # that subscribes to a stream no server produces waits forever.
                streaming=False, httpx_client=http,
                supported_protocol_bindings=[TransportProtocol.JSONRPC]))
            links[agent] = AgentLink(agent, factory.create(agent_card(agent)))
        return links

    def link(self, agent: AgentId) -> AgentLink:
        return self._links[agent]

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop_thread.loop

    # -- the user boundary ---------------------------------------------------
    #
    # Everything below is the FastAPI service acting for a human. It is the only
    # caller the orchestrator's card admits, and the specialists admit nobody
    # from here at all.

    CALLER = OrchestratorExecutor.USER_BOUNDARY

    def handle(self, question: str, history: list[dict] | None = None,
               already_clarified: bool = False, session_id: str | None = None,
               waiting: dict[str, Any] | None = None) -> AgentOutcome:
        """One user turn, through the orchestrator's A2A endpoint.

        `waiting` is a specialist task left in `input-required` by the previous
        turn. Its presence routes this turn to `relay_user_input`, so the user's
        answer resumes that task instead of starting an unrelated workflow.
        """
        skill = "relay_user_input" if waiting else "handle_user_turn"
        payload: dict[str, Any] = {
            "query": question,
            "history": history or [],
            "already_clarified": bool(already_clarified),
        }
        if waiting:
            payload["waiting"] = waiting
        result, ledger = self._ask(skill, payload, session_id)
        outcome = _outcome_from(result)
        # Attached here rather than carried in the artifact: this is the same
        # ledger every agent in the turn shared, with native integers and the
        # final state of the last hop already recorded.
        outcome.handoffs = ledger.as_dict()
        return outcome

    def summarise(self, messages: list[dict]) -> str | None:
        result, _ledger = self._ask("summarise_session", {"messages": messages}, None)
        if not result.completed:
            raise RuntimeError(
                (result.error or {}).get("message") or
                f"the orchestrator could not name this conversation ({result.state})")
        return (result.artifact(ARTIFACT_TITLE) or {}).get("title") or None

    def _ask(self, skill: str, payload: dict[str, Any],
             session_id: str | None) -> tuple[SkillResult, TurnLedger]:
        """Open the turn's budget, spend the first hop on it, and hand both back.

        The ledger is opened *here*, at the user boundary, and every agent the
        turn reaches finds the same one. That is what makes the handoff limit a
        limit on the turn rather than on each agent's own idea of the turn.

        The context id is the conversation. Every task the turn spawns — across
        all three agents — carries it, which is what makes a whole multi-agent
        turn recoverable from a task listing.
        """
        ledger = self.ledgers.open(session_id or "")
        try:
            result = self._loop_thread.run(
                self.link(AgentId.ORCHESTRATOR).call(
                    skill=skill, payload=payload, requesting_agent=self.CALLER,
                    ledger=ledger, intent="user turn",
                    context_id=session_id or ledger.user_request_id),
                # The bridge must outlast the deadline it is waiting on, or it
                # reports a timeout for work the inner layer would have ended
                # with a usable message a moment later.
                ledger.turn_timeout_s + 60)
            return result, ledger
        finally:
            self.ledgers.close(ledger)

    # -- lifecycle -----------------------------------------------------------

    def shutdown(self) -> None:
        """Close the clients and stop the loop. Safe to call more than once.

        Called explicitly by tests and again by `atexit`; the second call must
        not try to await a coroutine on a loop that has already stopped, which
        is how a clean shutdown turns into a "coroutine was never awaited"
        warning at interpreter exit.
        """
        if self._closed:
            return
        self._closed = True
        for link in self._links.values():
            try:
                self._loop_thread.run(link.aclose(), 5)
            except Exception as exc:  # noqa: BLE001 - shutdown is best effort
                LOGGER.debug("closing link %s failed: %s", link.agent.value, exc)
        self._links.clear()
        # Drain each agent's in-flight tasks before the loop stops. Without it a
        # task abandoned by a cancelled call is still pending when the loop is
        # torn down, and asyncio complains at interpreter exit about a coroutine
        # nobody awaited — noise that looks like a leak and hides real ones.
        for app in self.apps.values():
            handler = getattr(app.state, "request_handler", None)
            if handler is None or not hasattr(handler, "aclose"):
                continue
            try:
                self._loop_thread.run(handler.aclose(), 5)
            except Exception as exc:  # noqa: BLE001 - must not block exit
                LOGGER.debug("draining in-flight tasks failed: %s", exc)
        self._loop_thread.shutdown()


def _outcome_from(result: SkillResult) -> AgentOutcome:
    """Rebuild the orchestrator's outcome, or state plainly that it failed.

    A transport fault reaching the browser as a stack trace was never acceptable;
    reaching it as an empty answer would be worse, because an empty answer looks
    like the system had nothing to say rather than that it broke.
    """
    from agents.a2a.envelope import outcome_from_dict  # noqa: PLC0415

    payload = result.artifact(ARTIFACT_OUTCOME)
    if result.completed and isinstance(payload, dict):
        return outcome_from_dict(payload)

    detail = (result.error or {}).get("message") or result.narrative
    LOGGER.error("orchestrator turn did not complete (%s): %s", result.state, detail)
    return AgentOutcome(
        answer=("The gateway could not complete this request: "
                f"{detail or result.state}."),
        route="direct",
        trace=[{"kind": "answer", "label": "Failed", "detail": detail or result.state}],
    )


_NETWORK: AgentNetwork | None = None
_NETWORK_LOCK = threading.Lock()


def get_network(knowledge: Any = None, data_provider: Any = None) -> AgentNetwork:
    """The process-wide network, built once.

    A singleton for the same reason the MCP bridge is one: the expensive
    resources behind it (child processes, a capped database connection pool, an
    embedded vector store) are process-wide, and a second network would hold a
    second copy of all of them.
    """
    global _NETWORK  # noqa: PLW0603 - deliberate process-wide singleton
    with _NETWORK_LOCK:
        if _NETWORK is None:
            if knowledge is None or data_provider is None:
                from backend.knowledge.knowledge_base import KnowledgeBase  # noqa: PLC0415
                from backend.providers.base import make_data_provider  # noqa: PLC0415

                knowledge = knowledge or KnowledgeBase()
                data_provider = data_provider if data_provider is not None \
                    else make_data_provider()
            _NETWORK = AgentNetwork(knowledge, data_provider)
        return _NETWORK


def reset_network() -> None:
    """Drop the singleton. For tests that need a network with different wiring."""
    global _NETWORK  # noqa: PLW0603
    with _NETWORK_LOCK:
        if _NETWORK is not None:
            _NETWORK.shutdown()
        _NETWORK = None
