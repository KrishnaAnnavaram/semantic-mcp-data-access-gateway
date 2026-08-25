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

import contextlib
import functools
import logging
import os
import threading
from typing import Any, Callable, Iterator, TypeVar

LOGGER = logging.getLogger("agents.observability")

DEFAULT_PROJECT = "semantic-mcp-data-access-gateway"

#: LangSmith's public SaaS ingest endpoint. Reported (never a secret) so a
#: reader of `/health` can tell a default deployment from an EU or self-hosted
#: one without guessing.
DEFAULT_ENDPOINT = "https://api.smith.langchain.com"

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


def endpoint() -> str:
    """The LangSmith ingest endpoint runs are sent to.

    Reported, not secret. A custom value is how an EU or self-hosted LangSmith
    is reached, and knowing which one is in effect is the difference between "my
    traces are missing" and "my traces are in the other region".
    """
    _load_env()
    return (os.environ.get("LANGSMITH_ENDPOINT")
            or os.environ.get("LANGCHAIN_ENDPOINT") or DEFAULT_ENDPOINT)


def workspace_id() -> str | None:
    """The workspace a multi-workspace key is scoped to, if one is set."""
    _load_env()
    return (os.environ.get("LANGSMITH_WORKSPACE_ID")
            or os.environ.get("LANGCHAIN_WORKSPACE_ID") or None)


def langsmith_status() -> dict[str, Any]:
    """What tracing will actually do — reported, not assumed.

    A silently disabled tracer is the usual reason an evaluation run comes back
    empty, so the reason is spelled out rather than left to be inferred.

    The distinction that matters: *configured* (a flag and a key are present, so
    runs will be attempted) is not *verified* (LangSmith has actually accepted a
    run). This object reports the first — it reads the environment and never
    makes a network call, because `/health` must answer whether or not LangSmith
    is reachable. The key itself never appears; only whether one is present.
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
    return {
        "enabled": flag and keyed,
        "project": project_name(),
        # `configured` is a synonym for `enabled` kept explicit: it names the
        # thing this object actually reports, so a reader is not tempted to read
        # `enabled` as "verified working".
        "configured": flag and keyed,
        "api_key_configured": keyed,
        "tracing_flag": flag,
        "endpoint": endpoint(),
        "workspace_configured": workspace_id() is not None,
        "reason": reason,
    }


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


def run_id() -> str | None:
    """The id of the current run's *trace* (its root), for correlation.

    This is the id a user can paste into LangSmith to find the exact request,
    and the one the frontend stores per message. It is the trace id, not the
    span id, so every span in the turn resolves to the same value.
    """
    if not tracing_enabled():
        return None
    try:
        from langsmith.run_helpers import get_current_run_tree  # noqa: PLC0415

        tree = get_current_run_tree()
        if tree is None:
            return None
        # `trace_id` is the root of the whole turn; `id` would be this span.
        return str(getattr(tree, "trace_id", None) or getattr(tree, "id", None) or "") or None
    except Exception:  # noqa: BLE001 - a missing id is cosmetic
        return None


#: The A2A message-metadata key under which the LangSmith trace-continuation
#: headers travel. One key, so a reader of a captured message can tell the
#: tracing baggage from the domain metadata beside it.
TRACE_HEADER_KEY = "langsmith_trace"


def current_trace_headers() -> dict[str, str] | None:
    """The headers that let another execution continue *this* trace.

    This is the whole of distributed tracing across A2A. Captured on the worker
    thread where the parent run is active, carried in A2A message metadata, and
    handed to `continue_trace` on the far side so the specialist's spans nest
    under the same root instead of starting a second disconnected trace.

    Returns `None` when tracing is off or there is no active run — in which case
    the far side simply starts fresh, exactly as it does today. Never raises.
    """
    if not tracing_enabled():
        return None
    try:
        from langsmith.run_helpers import get_current_run_tree  # noqa: PLC0415

        tree = get_current_run_tree()
        if tree is None:
            return None
        headers = tree.to_headers()
        # Only the two continuation headers, as plain strings — nothing that
        # could carry a secret, and nothing a protobuf Struct cannot hold.
        return {k: str(v) for k, v in headers.items()
                if k in ("langsmith-trace", "baggage") and v}
    except Exception:  # noqa: BLE001 - propagation is best effort
        return None


@contextlib.contextmanager
def continue_trace(headers: dict[str, str] | None) -> Iterator[None]:
    """Re-establish a parent trace from headers captured across an A2A hop.

    Wrap the specialist's work in this on the *receiving* side. Because the
    executor hands its work to a worker thread with `asyncio.to_thread`, and
    that copies the current context, entering this context manager before the
    hand-off is what makes the copied context carry the parent — so the traced
    functions on the worker thread nest under the caller's run.

    A no-op when there are no headers or tracing is off, and it never raises:
    tracing must not be able to fail a request.
    """
    if not headers or not tracing_enabled():
        yield
        return
    try:
        from langsmith.run_helpers import tracing_context  # noqa: PLC0415

        with tracing_context(parent=headers):
            yield
    except Exception as exc:  # noqa: BLE001 - a broken parent must not fail work
        LOGGER.debug("could not continue trace from headers: %s", exc)
        yield


@contextlib.contextmanager
def span(name: str, run_type: str = "tool", **metadata: Any) -> Iterator[None]:
    """An ad-hoc child span with a runtime name, for MCP and DB operations.

    The `@traced` decorator needs a static name; a per-tool span
    (`mcp.call:get_curve`, `postgres.query`) needs a dynamic one, so this wraps
    LangSmith's `trace` context manager. Nests under whatever run is active, so
    called from inside a traced agent method it lands in the right place.

    Fail-open in every direction: tracing off, langsmith absent, or `trace`
    raising all degrade to running the block untraced. It never suppresses an
    exception from *inside* the block — that is the caller's own error.
    """
    if not tracing_enabled():
        yield
        return
    try:
        from langsmith import trace as _ls_trace  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - langsmith absent
        yield
        return
    clean = {k: v for k, v in metadata.items() if v is not None}
    try:
        cm = _ls_trace(name=name, run_type=run_type, metadata=clean or None)
    except Exception as exc:  # noqa: BLE001 - could not open a span
        LOGGER.debug("could not open span %s: %s", name, exc)
        yield
        return
    with cm:
        yield


def set_run_metadata(**metadata: Any) -> None:
    """Attach metadata to the current run, for dashboards and filtering.

    Fail-open and best effort: unknown keys, a missing run tree, or a langsmith
    that will not accept the update all degrade to doing nothing. Values should
    be small scalars — this is for grouping and filtering (route, model,
    session), never for payloads.
    """
    if not tracing_enabled() or not metadata:
        return
    try:
        from langsmith.run_helpers import get_current_run_tree  # noqa: PLC0415

        tree = get_current_run_tree()
        if tree is None:
            return
        extra = tree.extra if isinstance(getattr(tree, "extra", None), dict) else {}
        existing = extra.get("metadata") if isinstance(extra.get("metadata"), dict) else {}
        existing.update({k: v for k, v in metadata.items() if v is not None})
        extra["metadata"] = existing
        tree.extra = extra
    except Exception as exc:  # noqa: BLE001 - metadata is never load-bearing
        LOGGER.debug("could not set run metadata: %s", exc)


def set_run_tags(*tags: str) -> None:
    """Add tags to the current run. Fail-open, like `set_run_metadata`."""
    clean = [t for t in tags if t]
    if not tracing_enabled() or not clean:
        return
    try:
        from langsmith.run_helpers import get_current_run_tree  # noqa: PLC0415

        tree = get_current_run_tree()
        if tree is None:
            return
        current = list(getattr(tree, "tags", None) or [])
        for tag in clean:
            if tag not in current:
                current.append(tag)
        tree.tags = current
    except Exception as exc:  # noqa: BLE001 - tags are never load-bearing
        LOGGER.debug("could not set run tags: %s", exc)


_APP_METADATA: dict[str, Any] | None = None


def app_metadata() -> dict[str, Any]:
    """Process-wide facts worth stamping on every trace, resolved once.

    Environment, application name and version, the git commit, and which model
    backend and data backend are live. All safe to expose; none is a secret. A
    dashboard filters on these — "P95 latency on this commit", "error rate under
    the zai backend" — so they are attached to the root of every turn.
    """
    global _APP_METADATA  # noqa: PLW0603 - resolved once, then cached
    if _APP_METADATA is not None:
        return dict(_APP_METADATA)
    _load_env()
    meta: dict[str, Any] = {
        "application": "smcp-gateway",
        "environment": os.environ.get("SMCP_ENV") or os.environ.get("ENVIRONMENT") or "local",
        "app_version": os.environ.get("APP_VERSION") or _read_version(),
        "git_commit": os.environ.get("GIT_COMMIT") or _read_git_commit(),
        "llm_backend": os.environ.get("LLM_BACKEND") or "zai",
        "data_backend": os.environ.get("DATA_BACKEND") or "mock",
    }
    _APP_METADATA = {k: v for k, v in meta.items() if v}
    return dict(_APP_METADATA)


def _repo_root():
    """Walk up for a repository marker. Never counts directory levels.

    Resolved locally rather than importing `backend.paths`: `agents` sits below
    `backend` in the dependency order, and an upward import to read a version
    string would invert it. Same marker discipline as `paths.py`.
    """
    from pathlib import Path  # noqa: PLC0415

    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists() or (candidate / "docker-compose.yml").exists():
            return candidate
    return None


def _read_version() -> str:
    try:
        root = _repo_root()
        if root is None:
            return ""
        for line in (root / "pyproject.toml").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:  # noqa: BLE001 - version is cosmetic
        pass
    return ""


def _read_git_commit() -> str:
    """The short commit, read from `.git` without shelling out at request time."""
    try:
        root = _repo_root()
        if root is None:
            return ""
        git = root / ".git"
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(" ", 1)[1].strip()
            return (git / ref).read_text(encoding="utf-8").strip()[:12]
        return head[:12]
    except Exception:  # noqa: BLE001 - commit is cosmetic
        return ""


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


def last_call_stats() -> dict[str, Any]:
    """Measured usage for the latest structured call on this worker thread."""
    value = getattr(_FAILURE, "stats", {})
    return dict(value) if isinstance(value, dict) else {}


def clear_call_stats() -> None:
    """Clear provider-call evidence before a potentially cached operation."""
    _FAILURE.kind = ""
    _FAILURE.stats = {}


def _record_non_specialist_call(site: str, model: str,
                                stats: dict[str, Any]) -> None:
    if site in {"domain_expert", "mcp_agent"}:
        return
    try:
        from agents.cache import get_intelligence

        get_intelligence().record_llm_call(agent=site, model=model, stats=stats)
    except Exception as exc:  # noqa: BLE001 - analytics is never on the answer path
        LOGGER.debug("could not record Redis LLM analytics: %s", exc)


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
    import time as _time  # noqa: PLC0415

    from llm import ProviderError, SchemaViolation  # noqa: PLC0415

    _FAILURE.kind = ""
    _FAILURE.stats = {}
    site = getattr(call_site, "value", str(call_site))
    try:
        from agents.cache import get_intelligence  # noqa: PLC0415

        if not get_intelligence().allow_llm(site):
            LOGGER.warning("structured call rate-limited | call_site=%s", site)
            _FAILURE.kind = "rate_limit"
            _FAILURE.stats = {"calls": 0, "failure_kind": "rate_limit"}
            _record_non_specialist_call(site, "", _FAILURE.stats)
            set_run_metadata(call_site=site, failure_kind="rate_limit")
            set_run_tags(f"call_site:{site}", "rate_limited")
            return None
    except Exception as exc:  # noqa: BLE001 - Redis guardrail is fail-open
        LOGGER.debug("Redis LLM rate limiter unavailable: %s", exc)

    provider = model_provider()
    model = provider.model_for(call_site)
    _FAILURE.kind = ""
    # LangSmith model attribution: `ls_provider` and `ls_model_name` are the
    # conventional keys a run carries so the UI groups by model and can price a
    # call. Attached to the enclosing llm span (this call runs inside one), so it
    # costs nothing when tracing is off. `structured_call` returns the payload
    # only — the provider's token usage is not surfaced through this seam — so
    # token counts are deliberately not invented here; duration is recorded
    # because it is measured honestly.
    set_run_metadata(ls_provider=provider.name, ls_model_name=model,
                     call_site=site)
    started = _time.perf_counter()
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
        _FAILURE.stats = _provider_stats(provider, started, "schema")
        _record_non_specialist_call(site, model, _FAILURE.stats)
        return None
    except ProviderError as exc:
        LOGGER.warning("structured call failed | provider=%s model=%s "
                       "call_site=%s kind=%s | %s", provider.name, model,
                       getattr(call_site, "value", call_site), exc.kind, exc)
        _FAILURE.kind = exc.kind or "provider"
        _FAILURE.stats = _provider_stats(provider, started, _FAILURE.kind)
        _record_non_specialist_call(site, model, _FAILURE.stats)
        return None
    except Exception as exc:  # noqa: BLE001 - never take a request down
        LOGGER.warning("structured call errored | provider=%s model=%s | %s",
                       provider.name, model, exc)
        _FAILURE.kind = "unknown"
        _FAILURE.stats = _provider_stats(provider, started, "unknown")
        _record_non_specialist_call(site, model, _FAILURE.stats)
        return None

    set_run_metadata(model_call_seconds=round(_time.perf_counter() - started, 3))
    _FAILURE.stats = _provider_stats(provider, started, "")
    _record_non_specialist_call(site, model, _FAILURE.stats)
    LOGGER.debug("structured call ok | provider=%s model=%s call_site=%s",
                 provider.name, model, getattr(call_site, "value", call_site))
    return payload


def _provider_stats(provider: Any, started: float,
                    failure_kind: str) -> dict[str, Any]:
    """Read an optional provider-neutral measurement hook without requiring it."""
    try:
        hook = getattr(provider, "last_call_stats", None)
        stats = dict(hook()) if callable(hook) else {}
    except Exception:  # noqa: BLE001 - observability cannot change behavior
        stats = {}
    stats.setdefault("calls", 1)
    stats.setdefault("duration_ms", round(
        (__import__("time").perf_counter() - started) * 1000))
    if failure_kind:
        stats["failure_kind"] = failure_kind
    return stats
