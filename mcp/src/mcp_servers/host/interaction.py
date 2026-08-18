"""The client half of the three client-directed primitives.

A server that asks is useless without a client that answers. This module is
what makes elicitation, roots and sampling real rather than declared: three
callbacks, plus the retry loop that carries their answers back.

## How the answers travel

On protocol revision 2026-07-28 a server does not send a mid-call request. It
returns an ``InputRequiredResult`` carrying ``input_requests``, and the client
answers by **retrying the original call** with ``input_responses`` and the
echoed ``request_state``. That loop is `run_input_required_driver` in the SDK —
used here rather than hand-rolled, because the retry has to preserve request
state exactly and re-dispatch only what is still outstanding.

The same three callbacks serve both transports. On an older negotiated version
the SDK routes legacy server-to-client RPCs through them instead, so nothing
here has to know which revision is in play.

## Why each answer is what it is

**Roots** are a permission boundary, so the default is one directory this
project owns (`data/exports`), not the repository root and never the filesystem.
A root is a grant; granting more than the task needs is the whole failure mode.

**Elicitation** defaults to *declining* when nobody is watching. That looks
unhelpful and is deliberate: the question exists precisely because the server
cannot pick correctly, so a headless client inventing an answer would
manufacture exactly the wrong-curve error the question was raised to prevent. A
decline is labelled and recoverable; a guess is neither.

**Sampling** borrows this host's model, because the data server has none and
should not have one — an LLM credential inside it would be a second privilege
boundary to defend, sitting next to the database credential. When no API key is
configured the callback returns an empty draft tagged with the reason rather
than a plausible sentence, so a missing key can never be mistaken for a briefing.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from mcp.client._input_required import run_input_required_driver
from mcp.client.session import ClientRequestContext, ClientSession
from mcp.types import (
    CreateMessageResult,
    ElicitResult,
    InputRequiredResult,
    ListRootsResult,
    Root,
    TextContent,
)

from mcp_servers.paths import REPO_ROOT

LOGGER = logging.getLogger("host.interaction")

def _configured_sampling_model() -> str:
    """The model this host lends to servers that ask for one.

    Resolved from the model layer rather than pinned here, so the sampling model
    is chosen by `LLM_BACKEND` + `SAMPLING_MODEL` alongside every other call
    site. This is only a *label* for the policy — the actual call goes through
    the provider, which reads the same configuration.
    """
    try:
        from llm import CallSite, load_config  # noqa: PLC0415

        return load_config().model_for(CallSite.SAMPLING)
    except Exception:  # noqa: BLE001 - a policy label must never break a host
        return "unconfigured"


SAMPLING_MODEL = _configured_sampling_model()

ElicitationMode = Literal["decline", "prompt", "preset"]


@dataclass
class InteractionPolicy:
    """What this host is willing to answer, decided once and stated explicitly.

    Everything a server can ask for is a grant. Collecting the grants in one
    object means a reader can see the host's entire exposure without reading
    three callbacks.
    """

    roots: list[Path] = field(default_factory=list)
    elicitation: ElicitationMode = "decline"
    #: Answers for `elicitation="preset"`, keyed by elicitation schema field.
    #: Used by the demo and the verifier, where a human cannot be asked but the
    #: intended answer is known in advance and recorded in the source.
    preset_answers: dict[str, Any] = field(default_factory=dict)
    sampling_model: str = field(default_factory=_configured_sampling_model)
    max_rounds: int = 8

    @classmethod
    def default(cls, **overrides: Any) -> "InteractionPolicy":
        """The standard policy: one owned export directory, decline questions.

        `MCP_CLIENT_ROOTS` overrides the root list (os.pathsep-separated). Each
        entry must already exist or be creatable; a root that cannot be resolved
        is dropped with a warning rather than silently offered.
        """
        raw = os.environ.get("MCP_CLIENT_ROOTS", "")
        if raw.strip():
            candidates = [Path(p) for p in raw.split(os.pathsep) if p.strip()]
        else:
            candidates = [REPO_ROOT / "data" / "exports"]
        roots: list[Path] = []
        for path in candidates:
            try:
                path.mkdir(parents=True, exist_ok=True)
                roots.append(path.resolve())
            except OSError as exc:
                LOGGER.warning("dropping unusable root %s: %s", path, exc)
        return cls(roots=roots, **overrides)


# --- roots ------------------------------------------------------------------


def make_roots_callback(policy: InteractionPolicy):
    async def list_roots(context: ClientRequestContext) -> ListRootsResult:
        roots = [
            Root(uri=p.as_uri(), name=p.name or str(p))  # type: ignore[arg-type]
            for p in policy.roots
        ]
        LOGGER.info("declared %d root(s): %s", len(roots), ", ".join(str(p) for p in policy.roots))
        return ListRootsResult(roots=roots)

    return list_roots


# --- elicitation ------------------------------------------------------------


def make_elicitation_callback(policy: InteractionPolicy):
    async def elicit(context: ClientRequestContext, params: Any) -> ElicitResult:
        message = getattr(params, "message", "") or ""
        schema = getattr(params, "requested_schema", {}) or {}
        fields = list((schema.get("properties") or {}).keys())

        if policy.elicitation == "preset":
            answer = {k: v for k, v in policy.preset_answers.items() if k in fields}
            if answer:
                LOGGER.info("elicitation answered from preset: %s", answer)
                return ElicitResult(action="accept", content=answer)
            LOGGER.warning("no preset answer for fields %s; declining", fields)
            return ElicitResult(action="decline")

        if policy.elicitation == "prompt" and sys.stdin is not None and sys.stdin.isatty():
            return _ask_on_terminal(message, schema, fields)

        # Headless and no preset. Declining is the honest answer: the server
        # asked because it cannot choose, so neither can we.
        LOGGER.info("declining elicitation (no interactive client): %s", message[:120])
        return ElicitResult(action="decline")

    return elicit


def _ask_on_terminal(message: str, schema: dict, fields: list[str]) -> ElicitResult:
    """Ask a real human, one field at a time. Empty input declines."""
    props = schema.get("properties") or {}
    print(f"\n  ? {message}", file=sys.stderr)
    answer: dict[str, Any] = {}
    for name in fields:
        spec = props.get(name) or {}
        options = spec.get("enum")
        hint = f" [{'/'.join(map(str, options))}]" if options else ""
        try:
            raw = input(f"    {name}{hint}: ").strip()
        except (EOFError, KeyboardInterrupt):
            return ElicitResult(action="cancel")
        if not raw:
            return ElicitResult(action="decline")
        if options and raw not in [str(o) for o in options]:
            print(f"    not one of {options}; declining", file=sys.stderr)
            return ElicitResult(action="decline")
        answer[name] = raw
    return ElicitResult(action="accept", content=answer)


# --- sampling ---------------------------------------------------------------


def make_sampling_callback(policy: InteractionPolicy):
    """Lend this host's model to a server that has none.

    SEP-2577 deprecated the *client capability declaration* around sampling, and
    the recommended replacement is exactly this: the host integrates the LLM
    provider API directly. That is what happens here — the server still asks
    over the protocol, and the host answers with a real model call rather than
    by proxying to some model the protocol knows about.

    *Which* model is a `ModelProvider` decision, not this callback's. The
    server never learns the vendor, and neither does this function.
    """

    async def sample(context: ClientRequestContext, params: Any) -> CreateMessageResult:
        text, model, stop = _sampling_completion(params, policy)
        return CreateMessageResult(
            role="assistant",
            content=TextContent(type="text", text=text),
            model=model,
            stop_reason=stop,
        )

    return sample


def _sampling_completion(params: Any, policy: InteractionPolicy
                         ) -> tuple[str, str, str | None]:
    """Run the sampling request through the configured model provider.

    Returns ``(text, model_label, stop_reason)``. Failures return empty text and
    a model label that names the cause, because a server that receives prose has
    no way to tell a real draft from an apology — but it can read a label. The
    tool's own fallback then prints the verbatim caveat instead, which is the
    load-bearing half.
    """
    messages = []
    for msg in getattr(params, "messages", None) or []:
        content = getattr(msg, "content", None)
        piece = getattr(content, "text", None)
        if piece:
            messages.append({"role": getattr(msg, "role", "user"), "content": piece})
    if not messages:
        return "", "unavailable:no-messages", "error"

    # The server sets the ceiling and the provider honours it, raising it only to
    # the configured floor. That floor matters here: a reasoning model bills its
    # thinking against the same budget, so a 400-token ceiling can return an
    # empty completion rather than a short one.
    requested = int(getattr(params, "max_tokens", 0) or 0) or None
    system = getattr(params, "system_prompt", None)

    try:
        from llm import CallSite, make_model_provider  # noqa: PLC0415

        provider = make_model_provider()
        reply = provider.complete(call_site=CallSite.SAMPLING, system=system,
                                  messages=messages, max_tokens=requested)
    except Exception as exc:  # noqa: BLE001 - reported to the server as a label
        LOGGER.warning("sampling call failed: %s", exc)
        return "", f"unavailable:{type(exc).__name__}", "error"

    if reply.refused:
        return "", f"{reply.model}:refused", "refusal"
    LOGGER.info("sampling drafted by provider=%s model=%s usage=%s",
                reply.provider, reply.model, reply.usage or "-")
    return reply.text, reply.model or policy.sampling_model, reply.stop_reason


# --- the retry loop ---------------------------------------------------------


async def call_with_input_required(
    session: ClientSession,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    max_rounds: int = 8,
) -> Any:
    """Call a tool, answering any `input_requests` and retrying until terminal.

    `allow_input_required=True` is what opts this client into MRTR at all;
    without it the SDK raises rather than handing back an `InputRequiredResult`,
    on the reasonable grounds that a client which cannot answer should not
    pretend to have called the tool.
    """

    async def retry(responses: Any, state: str | None) -> Any:
        return await session.call_tool(
            tool_name, arguments,
            input_responses=responses, request_state=state,
            allow_input_required=True,
        )

    first = await retry(None, None)
    if not isinstance(first, InputRequiredResult):
        return first

    async def dispatch(key: str, request: Any) -> Any:
        ctx = ClientRequestContext(
            session=session, request_id=key,
            meta=request.params.meta if getattr(request, "params", None) else None,
        )
        LOGGER.info("answering %s for %s", getattr(request, "method", "?"), tool_name)
        return await session.dispatch_input_request(ctx, request)

    return await run_input_required_driver(
        first, dispatch=dispatch, retry=retry, max_rounds=max_rounds)
