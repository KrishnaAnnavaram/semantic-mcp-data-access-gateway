"""Z.AI (GLM) behind the `ModelProvider` seam, over the OpenAI-compatible API.

**Structured output does not use `response_format`.** Measured against the live
endpoint, Z.AI accepts `response_format={"type": "json_schema", "strict": true}`,
answers HTTP 200, and then ignores the field names it was given::

    asked for : {"rows": int, "grounded": bool, "quote": str}
    received  : {"rows_required": 250, "quoted_sentence": "..."}

Valid JSON, so `json.loads` succeeds and nothing raises. Two fields renamed,
one dropped, and every `.get()` downstream quietly returns `None`. So this
provider obtains structure the way GLM actually honours it — a **forced
function call** — and then validates the arguments against the schema anyway.

The forced-tool path was measured returning an exact schema match on the same
prompt where `response_format` did not.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from llm.config import ModelConfig
from llm.contracts import (
    CallSite,
    ModelReply,
    ProviderError,
    SchemaViolation,
    ToolCall,
    ToolSpec,
)
from llm.validation import strictened, validate_against_schema

LOGGER = logging.getLogger("llm.zai")

# Z.AI error codes worth naming, so a failure reads as itself rather than as a
# generic 429. 1113 is "insufficient balance", which is not a rate limit.
_BALANCE_CODES = {"1113"}

# Chat-template sentinels observed leaking *inside* the function-arguments
# string on glm-4.5-air. Measured: a correct routing decision arrived as
#
#     {"route":"direct",...,"requested_rows":-1.0\n</tool_call>
#
# - the closing brace missing and the model's own stop token appended. The
# decision was right; only the serialisation was broken. Cutting at the
# sentinel and closing the structure is deterministic and cannot invent a
# value, and the schema validator still has the final say on the result.
_SENTINELS = ("</tool_call>", "<tool_call>", "</function_call>", "<|")


class ZaiProvider:
    """GLM models through Z.AI's OpenAI-compatible endpoint."""

    name = "zai"

    def __init__(self, config: ModelConfig) -> None:
        if not config.api_key:
            # Names the fix, both ways. `zai` is the project default, so this is
            # the first thing a teammate hits on a fresh checkout - and an error
            # that only says "auth failed" would send them looking in the wrong
            # place entirely.
            raise ProviderError(
                "ZAI_API_KEY is not set, and zai is this project's default "
                "model backend. Either add ZAI_API_KEY to .env (get one at "
                "https://z.ai), or set LLM_BACKEND=anthropic to run on Claude "
                "with your ANTHROPIC_API_KEY instead.", kind="auth")
        self.config = config
        self._client: Any = None

    # --- plumbing ---------------------------------------------------------
    def _api(self) -> Any:
        if self._client is None:
            from openai import OpenAI  # noqa: PLC0415

            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout_seconds,
                max_retries=self.config.max_transport_retries,
            )
        return self._client

    def model_for(self, call_site: CallSite) -> str:
        return self.config.model_for(call_site)

    def _create(self, **request: Any) -> Any:
        try:
            return self._api().chat.completions.create(**request)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"zai call failed: {exc}",
                                kind=_kind_of(exc)) from exc

    @staticmethod
    def _usage(response: Any) -> dict[str, int]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        out: dict[str, int] = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = getattr(usage, key, None)
            if value:
                out[key] = int(value)
        # GLM bills thinking against the same budget as the answer; surfacing it
        # is what makes an empty completion diagnosable rather than mysterious.
        details = getattr(usage, "completion_tokens_details", None)
        reasoning = getattr(details, "reasoning_tokens", None) if details else None
        if reasoning:
            out["reasoning_tokens"] = int(reasoning)
        return out

    # --- the three operations --------------------------------------------
    def structured_call(self, *, call_site: CallSite, system: str, prompt: str,
                        schema: dict[str, Any], max_tokens: int | None = None,
                        result_name: str = "emit_result") -> dict[str, Any]:
        model = self.model_for(call_site)
        schema = strictened(schema)
        budget = self.config.tokens_for(call_site, max_tokens)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        try:
            return self._forced_call(model, call_site, messages, schema,
                                     budget, result_name)
        except (SchemaViolation, ProviderError) as first:
            # Exactly one corrective retry, and only for the two *deterministic*
            # ways a model can break the output contract: a schema violation, or
            # answering in prose when the call was forced. Transport failures are
            # excluded - the SDK already retries those, and retrying an expensive
            # reasoning request on a timeout is how a retry storm starts.
            # `SchemaViolation` subclasses `ProviderError`, so it must be tested
            # for first - checking `.kind` alone would send every violation down
            # the re-raise branch and silently disable the retry.
            if not isinstance(first, SchemaViolation) and first.kind != "no_tool_call":
                raise
            LOGGER.warning("output contract broken on %s (%s); one corrective "
                           "retry | %s", model, call_site.value, first)
            messages = messages + [{
                "role": "user",
                "content": (
                    f"Your previous reply did not satisfy the output contract:\n\n"
                    f"{first}\n\nRespond by calling the {result_name} function "
                    f"and nothing else - no prose outside the call. Emit every "
                    f"required field, use the exact field names from the schema, "
                    f"respect each declared type, and use null (not a sentinel "
                    f"number such as -1) where a value is unknown."),
            }]
            try:
                return self._forced_call(model, call_site, messages, schema,
                                         budget, result_name)
            except SchemaViolation as second:
                raise SchemaViolation(
                    f"{second} (unchanged after one corrective retry)") from first
            except ProviderError as second:
                raise ProviderError(
                    f"{second} (unchanged after one corrective retry)",
                    kind=second.kind) from first

    def _forced_call(self, model: str, call_site: CallSite,
                     messages: list[dict[str, Any]], schema: dict[str, Any],
                     budget: int, result_name: str) -> dict[str, Any]:
        """One forced-function-call round: request, extract, parse, validate."""
        started = time.time()
        response = self._create(
            model=model,
            max_tokens=budget,
            messages=messages,
            tools=[{"type": "function", "function": {
                "name": result_name,
                "description": ("Emit the result. You MUST call this function "
                                "exactly once, with every required field."),
                "parameters": schema}}],
            tool_choice={"type": "function", "function": {"name": result_name}},
        )

        choice = (getattr(response, "choices", None) or [None])[0]
        if choice is None:
            raise ProviderError(f"{model} returned no choices", kind="empty")

        calls = getattr(choice.message, "tool_calls", None) or []
        if not calls:
            # The model answered in prose despite the call being forced. Say so
            # rather than trying to scrape JSON out of the text - a scraped
            # object is exactly the unvalidated shape this design rejects.
            text = (getattr(choice.message, "content", None) or "").strip()
            raise ProviderError(
                f"{model} did not produce the forced call {result_name!r}"
                + (f"; it replied with prose: {text[:160]!r}" if text else ""),
                kind="no_tool_call")

        raw = calls[0].function.arguments or ""
        try:
            payload = json.loads(sanitise_arguments(raw))
        except json.JSONDecodeError as exc:
            raise SchemaViolation(
                f"{model} produced malformed function arguments: {exc}") from exc

        LOGGER.debug("structured_call provider=%s model=%s call_site=%s "
                     "%.1fs usage=%s", self.name, model, call_site.value,
                     time.time() - started, self._usage(response))
        return validate_against_schema(payload, schema,
                                       context=f"{model} ({call_site.value})")

    def tool_turn(self, *, call_site: CallSite, system: str,
                  messages: list[Any], tools: list[ToolSpec],
                  max_tokens: int | None = None) -> ModelReply:
        model = self.model_for(call_site)
        started = time.time()
        response = self._create(
            model=model,
            max_tokens=self.config.tokens_for(call_site, max_tokens),
            messages=[{"role": "system", "content": system}, *messages],
            tools=[{"type": "function", "function": {
                "name": t.name, "description": t.description,
                "parameters": t.parameters}} for t in tools],
        )

        choice = (getattr(response, "choices", None) or [None])[0]
        if choice is None:
            raise ProviderError(f"{model} returned no choices", kind="empty")

        raw_calls = getattr(choice.message, "tool_calls", None) or []
        calls: list[ToolCall] = []
        for call in raw_calls:
            try:
                args = json.loads(sanitise_arguments(call.function.arguments or "{}"))
            except json.JSONDecodeError as exc:
                raise SchemaViolation(
                    f"{model} produced malformed arguments for "
                    f"{call.function.name}: {exc}") from exc
            calls.append(ToolCall(id=call.id, name=call.function.name,
                                  arguments=args))

        return ModelReply(
            text=(getattr(choice.message, "content", None) or "").strip(),
            tool_calls=calls,
            stop_reason=_stop_reason(getattr(choice, "finish_reason", None), calls),
            model=getattr(response, "model", model), provider=self.name,
            raw_message=choice.message, usage=self._usage(response),
            duration_seconds=time.time() - started,
        )

    def complete(self, *, call_site: CallSite, system: str | None,
                 messages: list[dict[str, str]],
                 max_tokens: int | None = None) -> ModelReply:
        model = self.model_for(call_site)
        payload = ([{"role": "system", "content": system}] if system else []) + messages
        started = time.time()
        response = self._create(
            model=model,
            max_tokens=self.config.tokens_for(call_site, max_tokens),
            messages=payload,
        )
        choice = (getattr(response, "choices", None) or [None])[0]
        if choice is None:
            raise ProviderError(f"{model} returned no choices", kind="empty")
        return ModelReply(
            text=(getattr(choice.message, "content", None) or "").strip(),
            stop_reason=_stop_reason(getattr(choice, "finish_reason", None), []),
            model=getattr(response, "model", model), provider=self.name,
            usage=self._usage(response), duration_seconds=time.time() - started,
        )

    # --- message shapes ---------------------------------------------------
    def assistant_message(self, reply: ModelReply) -> Any:
        return reply.raw_message

    def tool_result_message(self, results: list[tuple[str, str, bool]]) -> Any:
        # OpenAI-compatible APIs take one message *per* tool result, so this
        # returns a list and callers extend rather than append. The host loop
        # treats the return value as opaque and never inspects it.
        return [{"role": "tool", "tool_call_id": call_id, "content": text}
                for call_id, text, _ in results]


def sanitise_arguments(raw: str) -> str:
    """Recover the JSON object from a tool-argument string, without inventing.

    Two deterministic repairs, in order:

    1. Truncate at a leaked chat-template sentinel. Those tokens are never part
       of JSON, so anything from one onward is serving noise.
    2. Close brackets the model left open.

    Neither step can add a *value* — only structure. A repaired object that is
    still wrong is caught by schema validation, which remains the authority.
    """
    text = raw.strip()
    for sentinel in _SENTINELS:
        cut = text.find(sentinel)
        if cut != -1:
            text = text[:cut]
    return _close_unbalanced(text.rstrip().rstrip(","))


def _close_unbalanced(text: str) -> str:
    """Append the closers needed to balance `text`, respecting string literals."""
    stack: list[str] = []
    in_string = escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]" and stack:
            stack.pop()
    if in_string:
        text += '"'
    return text + "".join("}" if opener == "{" else "]" for opener in reversed(stack))


def _stop_reason(finish_reason: str | None, calls: list[ToolCall]) -> str:
    """Normalise OpenAI's `finish_reason` onto the neutral vocabulary.

    OpenAI-compatible providers have no typed refusal, so nothing here ever
    produces "refusal" - and the Anthropic-only refusal branch upstream simply
    never fires rather than misfiring.
    """
    if calls or finish_reason == "tool_calls":
        return "tool_calls"
    if finish_reason == "length":
        return "length"
    if finish_reason == "content_filter":
        return "refusal"
    return "end_turn"


def _kind_of(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    text = str(exc)
    if any(code in text for code in _BALANCE_CODES) or "balance" in text.lower():
        return "balance"
    if "timeout" in name:
        return "timeout"
    if "ratelimit" in name or "429" in text:
        return "rate_limit"
    if "authentication" in name or "401" in text:
        return "auth"
    if "connection" in name:
        return "transport"
    return "error"
