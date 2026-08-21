"""LangSmith instrumentation. Every agent boundary is a run.

A trace of one request should show the shape of the system, not one opaque span
per HTTP call:

    orchestrator_agent
      ├─ orchestrator.classify            (llm, routing model)
      ├─ domain_expert_agent
      │    ├─ knowledge_retrieval         (retriever, Qdrant)
      │    ├─ domain_expert.derive        (llm, reasoning model)
      │    └─ discussion
      │         ├─ round_1.mcp_agent.assess    (llm, reasoning model)
      │         └─ round_1.domain_expert.revise(llm, reasoning model)
      ├─ mcp_agent.execute                (tool)
      └─ orchestrator.reflect             (llm, routing model)

Which concrete model serves each call site is `LLM_BACKEND` configuration, not
something an agent or this module decides. `log_status()` reports the resolved
allocation at startup, with the key redacted to a present/absent flag.

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
import threading
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
    log = logger or LOGGER
    status = langsmith_status()
    log.info("LangSmith: %s (project=%s) - %s",
             "ENABLED" if status["enabled"] else "disabled",
             status["project"], status["reason"])

    # Which engine is answering, and with what per call site. No secret is
    # printed - `redacted()` reports only whether a key is present.
    try:
        from llm import provider_status  # noqa: PLC0415

        model_status = provider_status()
        log.info("Models: backend=%s key=%s %s",
                 model_status.get("backend"),
                 "set" if model_status.get("api_key_configured") else "MISSING",
                 model_status.get("models"))
    except Exception as exc:  # noqa: BLE001 - status must never break startup
        log.warning("model provider status unavailable: %s", exc)


_PROVIDER = None


def model_provider():
    """The process-wide `ModelProvider`.

    Which vendor answers is decided by `LLM_BACKEND`, exactly as `DATA_BACKEND`
    decides which `DataProvider` answers. Agents never see the difference.
    """
    global _PROVIDER  # noqa: PLW0603 - deliberate process-wide singleton
    if _PROVIDER is None:
        _load_env()
        from llm import make_model_provider  # noqa: PLC0415

        _PROVIDER = make_model_provider()
    return _PROVIDER


#: Why the last structured call failed, per thread. Thread-local because the
#: A2A executors run agent work on worker threads and two turns must never read
#: each other's failure. Cleared at the start of every call, so a stale kind can
#: never describe a later success.
_FAILURE = threading.local()


def last_failure_kind() -> str:
    """The kind of the most recent structured-call failure on this thread."""
    return getattr(_FAILURE, "kind", "") or ""


#: Failures no retry can fix. The account is empty or the key is wrong; the
#: same request in ten seconds gets the same answer, so inviting one is worse
#: than useless — it sends the user in a circle instead of to the fix.
TERMINAL_FAILURES = frozenset({"balance", "auth"})


def structured_call(*, call_site, system: str, prompt: str, schema: dict[str, Any],
                    max_tokens: int | None = None,
                    result_name: str = "emit_result") -> dict[str, Any] | None:
    """One schema-validated model call, shared by all three agents.

    The *call site* is the argument, not the model: which model serves it is
    configuration, and routing a greeting is not the same problem as grounding
    a market-risk requirement.

    Returns `None` rather than raising: an agent that cannot get a structured
    answer has to degrade visibly (say so, hand back control) rather than take
    the whole request down. Crucially, `None` is now also what a *structurally
    wrong* answer produces — a renamed field or a float where an integer was
    required no longer flows on as a half-populated dict whose missing keys
    quietly become `None` three layers later.

    The *reason* it failed is recorded in `last_failure_kind()` rather than
    thrown away with the exception. `None` alone cannot distinguish a blip from
    a wall, and the difference is the whole content of what the user should be
    told: a schema violation is worth retrying and an exhausted account is not.
    Telling someone "asking again usually works" when the provider has answered
    `Insufficient balance` is advice that cannot come true.
    """
    from llm import ProviderError, SchemaViolation  # noqa: PLC0415

    provider = model_provider()
    model = provider.model_for(call_site)
    _FAILURE.kind = ""
    try:
        payload = provider.structured_call(
            call_site=call_site, system=system, prompt=prompt, schema=schema,
            max_tokens=max_tokens, result_name=result_name)
    except SchemaViolation as exc:
        # Loud on purpose. This is the failure that used to be invisible.
        LOGGER.error("structured call rejected | provider=%s model=%s "
                     "call_site=%s | %s", provider.name, model,
                     getattr(call_site, "value", call_site), exc)
        _FAILURE.kind = "schema"
        return None
    except ProviderError as exc:
        LOGGER.warning("structured call failed | provider=%s model=%s "
                       "call_site=%s kind=%s | %s", provider.name, model,
                       getattr(call_site, "value", call_site), exc.kind, exc)
        _FAILURE.kind = exc.kind or "provider"
        return None
    except Exception as exc:  # noqa: BLE001 - never take a request down
        LOGGER.warning("structured call errored | provider=%s model=%s | %s",
                       provider.name, model, exc)
        _FAILURE.kind = "unknown"
        return None

    LOGGER.debug("structured call ok | provider=%s model=%s call_site=%s",
                 provider.name, model, getattr(call_site, "value", call_site))
    return payload
