"""Client for talking to the quant agent (teammate #2's service).

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
    """Raised when the quant agent cannot be reached or returns an invalid response."""


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    sources: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    # Set when the agent needs a detail before it can answer. Rendering this as
    # a question with real choices is the difference between the agent asking
    # and the agent guessing.
    elicitation: dict | None = None
    route: str = "quant"
    # Tabular results as {title, columns, rows, ...}. Kept structured rather
    # than folded into `answer`, so the UI can put them in a real table widget.
    tables: list[dict] = field(default_factory=list)
    # Which fields and how many rows the task needed, and what decided that.
    data_plan: dict | None = None
    # The domain expert <-> MCP agent exchange that settled the plan.
    negotiation: dict | None = None

    @property
    def awaiting_clarification(self) -> bool:
        return self.elicitation is not None


class AgentClient(Protocol):
    def ask(self, query: str, session_id: str) -> AnswerResult: ...
    def summarise(self, messages: list[dict]) -> str | None: ...


class RestAgentClient:
    """Calls the quant agent's `POST /chat` endpoint. See root CLAUDE.md for the contract."""

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
            raise AgentClientError(f"Could not reach quant agent at {self._base_url}: {exc}") from exc

        try:
            payload = response.json()
            answer = payload["answer"]
        except (ValueError, KeyError) as exc:
            raise AgentClientError(f"Quant agent returned an unexpected response: {exc}") from exc

        latency_ms = (time.perf_counter() - started) * 1000
        return AnswerResult(
            answer=answer,
            sources=payload.get("sources", []),
            latency_ms=latency_ms,
            elicitation=payload.get("elicitation"),
            route=payload.get("route", "quant"),
            tables=payload.get("tables") or [],
            data_plan=payload.get("data_plan"),
            negotiation=payload.get("negotiation"),
        )

    def summarise(self, messages: list[dict]) -> str | None:
        """Ask the backend to name this conversation. Best-effort: a failed
        title is cosmetic, so it must never break the chat."""
        try:
            response = requests.post(
                f"{self._base_url}/summarise",
                json={"messages": messages},
                timeout=min(self._timeout_seconds, 30),
            )
            response.raise_for_status()
            return response.json().get("title") or None
        except (requests.RequestException, ValueError) as exc:
            logger.debug("session summary unavailable: %s", exc)
            return None


class MockAgentClient:
    """Canned responses so the UI is runnable/demoable before the real agent exists."""

    def ask(self, query: str, session_id: str) -> AnswerResult:
        started = time.perf_counter()
        time.sleep(0.4)  # simulate network + reasoning latency
        latency_ms = (time.perf_counter() - started) * 1000
        return AnswerResult(
            answer=(
                f"(mock agent) I received your question: \"{query}\". "
                "Set AGENT_BACKEND=rest and AGENT_API_URL to talk to the real quant agent."
            ),
            sources=["mock://quant-agent"],
            latency_ms=latency_ms,
        )

    def summarise(self, messages: list[dict]) -> str | None:
        return None


def _build_client(settings: Settings) -> AgentClient:
    if settings.agent_backend == "rest":
        return RestAgentClient(settings.agent_api_url, settings.agent_timeout_seconds)
    if settings.agent_backend == "mock":
        return MockAgentClient()
    raise AgentClientError(
        f"Unknown AGENT_BACKEND '{settings.agent_backend}'; expected 'mock' or 'rest'."
    )


@traceable(name="frontend_chat_request", run_type="chain")
def ask_agent(query: str, session_id: str) -> AnswerResult:
    settings = get_settings()
    client = _build_client(settings)
    logger.info("Asking quant agent (backend=%s): %r", settings.agent_backend, query)
    result = client.ask(query, session_id)
    logger.info("Quant agent responded in %.0fms (route=%s)", result.latency_ms, result.route)
    return result


def summarise_session(messages: list[dict]) -> str | None:
    """Best-effort conversation title. Never raises — a title is cosmetic."""
    try:
        return _build_client(get_settings()).summarise(messages)
    except Exception as exc:  # noqa: BLE001
        logger.debug("session summary skipped: %s", exc)
        return None
