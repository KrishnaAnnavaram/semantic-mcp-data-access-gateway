"""Client for talking to the smart agent (teammate #2's service).

The transport is intentionally isolated behind `AgentClient` / `ask_agent` so the REST
implementation used for the demo can be swapped for an MCP client later without touching
`app.py`. `MockAgentClient` lets the UI be built and demoed before the real agent endpoint
exists.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

import requests
from langsmith import traceable

from config import Settings, get_settings

logger = logging.getLogger(__name__)


class AgentClientError(Exception):
    """Raised when the smart agent cannot be reached or returns an invalid response."""


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    sources: list[str] = field(default_factory=list)
    latency_ms: float = 0.0


class AgentClient(Protocol):
    def ask(self, query: str, session_id: str) -> AnswerResult: ...


class RestAgentClient:
    """Calls the smart agent's `POST /chat` endpoint. See root CLAUDE.md for the contract."""

    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds

    def ask(self, query: str, session_id: str) -> AnswerResult:
        started = time.perf_counter()
        try:
            response = requests.post(
                f"{self._base_url}/chat",
                json={"query": query, "session_id": session_id},
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise AgentClientError(f"Could not reach smart agent at {self._base_url}: {exc}") from exc

        try:
            payload = response.json()
            answer = payload["answer"]
        except (ValueError, KeyError) as exc:
            raise AgentClientError(f"Smart agent returned an unexpected response: {exc}") from exc

        latency_ms = (time.perf_counter() - started) * 1000
        return AnswerResult(
            answer=answer,
            sources=payload.get("sources", []),
            latency_ms=latency_ms,
        )


class MockAgentClient:
    """Canned responses so the UI is runnable/demoable before the real agent exists."""

    def ask(self, query: str, session_id: str) -> AnswerResult:
        started = time.perf_counter()
        time.sleep(0.4)  # simulate network + reasoning latency
        latency_ms = (time.perf_counter() - started) * 1000
        return AnswerResult(
            answer=(
                f"(mock agent) I received your question: \"{query}\". "
                "Set AGENT_BACKEND=rest and AGENT_API_URL to talk to the real smart agent."
            ),
            sources=["mock://smart-agent"],
            latency_ms=latency_ms,
        )


def _build_client(settings: Settings) -> AgentClient:
    if settings.agent_backend == "rest":
        return RestAgentClient(settings.agent_api_url, settings.agent_timeout_seconds)
    if settings.agent_backend == "mock":
        return MockAgentClient()
    raise AgentClientError(
        f"Unknown AGENT_BACKEND '{settings.agent_backend}'; expected 'mock' or 'rest'."
    )


@traceable(name="ask_smart_agent", run_type="chain")
def ask_agent(query: str, session_id: str) -> AnswerResult:
    settings = get_settings()
    client = _build_client(settings)
    logger.info("Asking smart agent (backend=%s): %r", settings.agent_backend, query)
    result = client.ask(query, session_id)
    logger.info("Smart agent responded in %.0fms", result.latency_ms)
    return result
