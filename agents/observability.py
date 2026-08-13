"""LangSmith instrumentation. Every agent boundary is a run.

A trace of one request should show the shape of the system, not one opaque span
per HTTP call:

    orchestrator_agent
      ├─ orchestrator.classify            (llm, Haiku)
      ├─ domain_expert_agent
      │    ├─ knowledge_retrieval         (retriever, Qdrant)
      │    ├─ domain_expert.derive        (llm, Opus)
      │    └─ discussion
      │         ├─ round_1.mcp_agent.assess    (llm, Opus)
      │         └─ round_1.domain_expert.revise(llm, Opus)
      ├─ mcp_agent.execute                (tool)
      └─ orchestrator.reflect             (llm, Haiku)

That nesting is what makes the system *evaluable*: an evaluator can score the
domain expert's requirement on its own, separately from the answer eventually
written from it.

Two rules this module enforces:

**Tracing must never change behaviour.** A missing key, an unreachable endpoint
or a payload that will not serialise must not take a request down. Everything
degrades to simply running the function.

**Configuration is read from the environment, once.** LangSmith's SDK reads
`LANGSMITH_*` / `LANGCHAIN_*` itself; this module only reports what it found, so
there is no second copy to drift.
"""

from __future__ import annotations

import functools
import logging
import os
from typing import Any, Callable, TypeVar

LOGGER = logging.getLogger("agents.observability")

DEFAULT_PROJECT = "semantic-mcp-data-access-gateway"

F = TypeVar("F", bound=Callable[..., Any])


def _load_env() -> None:
    try:
        from treasury_db.db import load_dotenv  # noqa: PLC0415

        load_dotenv()
    except Exception:  # noqa: BLE001 - .env is optional
        pass


def tracing_enabled() -> bool:
    """True only when a flag *and* a key are present.

    Both spellings are accepted: LangSmith renamed these variables and both are
    still in circulation, so a correctly configured project should work without
    the user having to know which era their tutorial came from.
    """
    _load_env()
    flag = (os.environ.get("LANGSMITH_TRACING")
            or os.environ.get("LANGCHAIN_TRACING_V2") or "").strip().lower() == "true"
    keyed = bool(os.environ.get("LANGSMITH_API_KEY")
                 or os.environ.get("LANGCHAIN_API_KEY"))
    return flag and keyed


def project_name() -> str:
    _load_env()
    return (os.environ.get("LANGSMITH_PROJECT")
            or os.environ.get("LANGCHAIN_PROJECT") or DEFAULT_PROJECT)


def langsmith_status() -> dict[str, Any]:
    """What tracing will actually do — reported, not assumed.

    A silently disabled tracer is the usual reason an evaluation run comes back
    empty, so the reason is spelled out rather than left to be inferred.
    """
    _load_env()
    flag = (os.environ.get("LANGSMITH_TRACING")
            or os.environ.get("LANGCHAIN_TRACING_V2") or "").strip().lower() == "true"
    keyed = bool(os.environ.get("LANGSMITH_API_KEY")
                 or os.environ.get("LANGCHAIN_API_KEY"))
    if flag and keyed:
        reason = "runs are being sent to LangSmith"
    elif flag:
        reason = "LANGSMITH_TRACING is true but no API key is set"
    elif keyed:
        reason = "an API key is set but LANGSMITH_TRACING is not 'true'"
    else:
        reason = "set LANGSMITH_TRACING=true and LANGSMITH_API_KEY to enable"
    return {"enabled": flag and keyed, "project": project_name(), "reason": reason}


def traced(name: str, run_type: str = "chain", **kwargs: Any) -> Callable[[F], F]:
    """Mark an agent boundary as a LangSmith run, without ever failing the call."""

    def decorate(func: F) -> F:
        try:
            from langsmith import traceable  # noqa: PLC0415

            instrumented = traceable(name=name, run_type=run_type, **kwargs)(func)
        except Exception as exc:  # noqa: BLE001 - langsmith absent/misconfigured
            LOGGER.debug("tracing unavailable for %s: %s", name, exc)
            return func

        @functools.wraps(func)
        def wrapper(*args: Any, **inner: Any) -> Any:
            try:
                return instrumented(*args, **inner)
            except Exception:
                raise  # the traced function's own error - never swallowed

        return wrapper  # type: ignore[return-value]

    return decorate


def run_url() -> str | None:
    """Deep link to the current run, for surfacing in the decision trace."""
    if not tracing_enabled():
        return None
    try:
        from langsmith.run_helpers import get_current_run_tree  # noqa: PLC0415

        tree = get_current_run_tree()
        return tree.get_url() if tree is not None else None
    except Exception:  # noqa: BLE001 - a missing link is cosmetic
        return None


def log_status(logger: logging.Logger | None = None) -> None:
    status = langsmith_status()
    (logger or LOGGER).info("LangSmith: %s (project=%s) - %s",
                            "ENABLED" if status["enabled"] else "disabled",
                            status["project"], status["reason"])


_CLIENT = None


def anthropic_client():
    """One Anthropic client for every agent.

    Shared so connection pooling and retry settings are configured in exactly
    one place; the per-agent difference is the *model*, not the transport.
    """
    global _CLIENT  # noqa: PLW0603 - deliberate process-wide singleton
    if _CLIENT is None:
        _load_env()
        import anthropic  # noqa: PLC0415

        _CLIENT = anthropic.Anthropic()
    return _CLIENT


def structured_call(*, model: str, system: str, prompt: str, schema: dict[str, Any],
                    max_tokens: int = 4000, effort: str = "high") -> dict[str, Any] | None:
    """One JSON-schema-constrained model call, shared by all three agents.

    Returns `None` rather than raising: an agent that cannot get a structured
    answer has to degrade visibly (say so, hand back control) rather than take
    the whole request down.
    """
    import json  # noqa: PLC0415

    # Adaptive thinking and `effort` are frontier-model features. Haiku rejects
    # both with a 400, and the orchestrator deliberately runs on Haiku - so the
    # request is shaped to the model rather than the model chosen to fit one
    # request shape.
    request: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
        "messages": [{"role": "user", "content": prompt}],
    }
    if not model.startswith("claude-haiku"):
        request["thinking"] = {"type": "adaptive"}
        request["output_config"]["effort"] = effort

    try:
        response = anthropic_client().messages.create(**request)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("structured call to %s failed: %s", model, exc)
        return None

    if getattr(response, "stop_reason", None) == "refusal":
        LOGGER.warning("model %s refused the request", model)
        return None
    text = "".join(b.text for b in response.content
                   if getattr(b, "type", None) == "text")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        LOGGER.warning("model %s returned unparseable JSON", model)
        return None
