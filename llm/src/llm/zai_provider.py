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
import re
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

#: The same defect one level out: not a sentinel leaking *into* the arguments,
#: but the whole forced call rendered as chat-template text in the **content**
#: channel, with no `tool_calls` on the message at all. Measured verbatim on
#: glm-5.2 at the orchestrator call site:
#:
#:     emit_result<arg_key>route</arg_key><arg_value>data_request</arg_value>
#:     <arg_key>reasoning</arg_key><arg_value>Compute request names a clear…
#:
#: The routing decision was correct and complete. Only the encoding was wrong,
#: and the provider threw the whole thing away and bought a corrective round.
#:
#: Recovering it is the same deal `sanitise_arguments` already makes: structure
#: only, no value invented, and the strict validator still decides. What it
#: cannot do is rescue genuine prose — a model that answered in sentences
#: produces no pairs here, and falls through to the retry exactly as before.
_ARG_PAIR = re.compile(
    r"<arg_key>(?P<key>.*?)</arg_key>\s*<arg_value>(?P<value>.*?)</arg_value>",
    re.DOTALL)


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
        except SchemaViolation as first:
            return self._corrective_retry(model, call_site, messages, schema,
                                          budget, result_name, first)
        except ProviderError as first:
            if first.kind == "budget_exhausted":
                # Retrying this unchanged burns the same budget again. Retrying
                # it *without reasoning* cannot, and that is a measurement
                # rather than a hope: the same call that spent 6,254 tokens
                # thinking returns the same validated object in 1,220 with
                # thinking off. GLM expands its reasoning to fill whatever
                # ceiling it is given — 5,241 tokens under 12,000, 9,576 under
                # 20,000 — so raising the ceiling relocates the truncation
                # instead of removing it, and charges more for the privilege.
                #
                # Nothing is loosened by the escalation: the reasoning was
                # never the deliverable here, the schema-checked object is,
                # and it is still schema-checked.
                LOGGER.warning(
                    "output budget exhausted on %s (%s); one retry with "
                    "reasoning disabled | %s", model, call_site.value, first)
                return self._forced_call(model, call_site, messages, schema,
                                         budget, result_name, thinking=False)
            if first.kind != "no_tool_call":
                # Transport failures are excluded: the SDK already retries
                # those, and retrying an expensive reasoning request on a
                # timeout is how a retry storm starts.
                raise
            return self._corrective_retry(model, call_site, messages, schema,
                                          budget, result_name, first)

    def _corrective_retry(self, model: str, call_site: CallSite,
                          messages: list[dict[str, Any]], schema: dict[str, Any],
                          budget: int, result_name: str,
                          first: ProviderError) -> dict[str, Any]:
        """One corrective round, for the deterministic contract breaks only.

        A schema violation and prose-instead-of-a-call are both things the model
        can be *told* about and fix. Quoting the failure back is what makes the
        retry worth its cost; repeating the original request unchanged would
        mostly reproduce the original answer.

        **It is a repair, not a re-derivation.** The model's own broken object
        goes back with the complaint, so the round is spent fixing a
        serialisation fault rather than thinking the whole answer out again —
        and these faults are serialisation faults. The measured cases were a
        correct routing decision truncated at a leaked stop token, and a
        correct answer whose nullable enum arrived as the string `"null"`: the
        reasoning was right both times and only the encoding was wrong. Asking
        for the analysis again is paying twice for work already done.

        Nothing is loosened. The repaired object is validated by the same
        strict validator, which remains the only authority on whether it is
        acceptable.
        """
        LOGGER.warning("output contract broken on %s (%s); one corrective "
                       "retry | %s", model, call_site.value, first)
        emitted = (getattr(first, "payload_text", "") or "")[:4_000]
        quoted = (f"This is exactly what you emitted, verbatim:\n\n{emitted}\n\n"
                  f"Return the SAME analysis. Change only what the contract "
                  f"requires - do not reconsider the answer itself.\n\n"
                  if emitted.strip() else "")
        messages = messages + [{
            "role": "user",
            "content": (
                f"Your previous reply did not satisfy the output contract:\n\n"
                f"{first}\n\n{quoted}Respond by calling the {result_name} function "
                f"and nothing else - no prose outside the call. Emit every "
                f"required field, use the exact field names from the schema, "
                f"respect each declared type, and use JSON null - the bare "
                f"literal, never the string \"null\" - where a value is "
                f"unknown. Do not use a sentinel number such as -1."),
        }]
        try:
            return self._forced_call(model, call_site, messages, schema,
                                     budget, result_name)
        except SchemaViolation as second:
            raise SchemaViolation(
                f"{second} (unchanged after one corrective retry)") from first
        except ProviderError as second:
            if second.kind == "budget_exhausted":
                return self._forced_call(model, call_site, messages, schema,
                                         budget, result_name, thinking=False)
            raise ProviderError(
                f"{second} (unchanged after one corrective retry)",
                kind=second.kind) from first

    def _forced_call(self, model: str, call_site: CallSite,
                     messages: list[dict[str, Any]], schema: dict[str, Any],
                     budget: int, result_name: str,
                     thinking: bool = True) -> dict[str, Any]:
        """One forced-function-call round: request, extract, parse, validate."""
        started = time.time()
        response = self._create(
            model=model,
            max_tokens=budget,
            # GLM bills thinking against the output budget, and it expands to
            # fill whatever it is given — measured 5,241 reasoning tokens under
            # a 12,000 ceiling and 9,576 under 20,000, on the same prompt. So
            # raising the ceiling does not remove the truncation, it relocates
            # it and charges more for the privilege. `thinking=False` is the
            # escalation for a call that has already been truncated once.
            **({} if thinking else
               {"extra_body": {"thinking": {"type": "disabled"}}}),
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
        raw = calls[0].function.arguments or "" if calls else ""
        if not calls:
            text = (getattr(choice.message, "content", None) or "").strip()
            usage = self._usage(response)
            # Did it make the call and merely fail to *emit* it? A leaked chat
            # template carries the whole answer, so recovering it costs nothing
            # and saves a full corrective round. Genuine prose yields nothing
            # here and falls straight through to the paths below.
            recovered = _recover_templated_call(text)
            if recovered is None:
                if getattr(choice, "finish_reason", None) == "length":
                    # Not a refusal and not a broken contract: the completion
                    # was cut off mid-thought. Worth its own message, because
                    # the two look identical from here and have opposite fixes
                    # — one is "raise the budget", the other is "fix the
                    # prompt" — and a reasoning model spends the budget on
                    # thinking before it writes anything, so this is the
                    # *likely* cause, not the exotic one. Retrying it unchanged
                    # only burns it again.
                    raise ProviderError(
                        f"{model} ran out of output budget before it could call "
                        f"{result_name!r} ({budget} max_tokens, "
                        f"{usage.get('reasoning_tokens', 0)} of "
                        f"{usage.get('completion_tokens', 0)} spent on reasoning). "
                        f"Raise the floor for this call site in llm/config.py.",
                        kind="budget_exhausted")
                # The model answered in prose despite the call being forced. Say
                # so rather than trying to scrape JSON out of the text - a
                # scraped object is exactly the unvalidated shape this design
                # rejects. The prose travels on the error so the corrective
                # round can quote it back and ask only for a re-encoding.
                raise ProviderError(
                    f"{model} did not produce the forced call {result_name!r}"
                    + (f"; it replied with prose: {text[:160]!r}" if text else ""),
                    kind="no_tool_call", payload_text=text)
            LOGGER.warning(
                "%s (%s) wrote its forced call as chat-template text instead of "
                "emitting it; %d field(s) recovered deterministically rather "
                "than re-asked", model, call_site.value, text.count("<arg_key>"))
            raw = recovered

        try:
            payload = _unstring_nulls(json.loads(sanitise_arguments(raw)))
        except json.JSONDecodeError as exc:
            raise SchemaViolation(
                f"{model} produced malformed function arguments: {exc}",
                payload_text=raw) from exc

        LOGGER.debug("structured_call provider=%s model=%s call_site=%s "
                     "%.1fs usage=%s", self.name, model, call_site.value,
                     time.time() - started, self._usage(response))
        try:
            return validate_against_schema(payload, schema,
                                           context=f"{model} ({call_site.value})")
        except SchemaViolation as exc:
            # Keep what it emitted. The correction round quotes this back so the
            # model repairs its own object rather than reasoning the whole
            # answer out a second time.
            exc.payload_text = raw
            raise

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


def _recover_templated_call(text: str) -> str | None:
    """A forced call written as chat-template text, turned back into arguments.

    Returns a JSON object string, or `None` when there is nothing to recover —
    which is every case of the model genuinely answering in prose, so the
    corrective round still happens exactly where it should.

    The template is flat text and carries no types, so each value is read as
    JSON where it parses as JSON and kept as a string where it does not. That
    is the only reading available: `250` in a template is not "the string
    250", it is a template with no way to say `250`. It is also the whole
    extent of the interpretation — no field is added, renamed or defaulted, and
    the strict validator downstream is still the only thing that decides
    whether the result is acceptable.
    """
    if not text or "<arg_key>" not in text:
        return None
    pairs = _ARG_PAIR.findall(text)
    if not pairs:
        return None
    recovered: dict[str, Any] = {}
    for key, value in pairs:
        name = key.strip()
        if not name:
            continue
        body = value.strip()
        try:
            recovered[name] = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            recovered[name] = body
    return json.dumps(recovered) if recovered else None


#: What a model writes when it means JSON `null` and produces a string instead.
#: Deliberately short and exact — `"none"` is a real answer to "which scenario?"
#: only in the sense that nobody would phrase it that way, whereas coercing
#: anything vaguer (`"n/a"`, `"unknown"`) would start discarding real answers.
_STRING_NULLS = frozenset({"null", "none", "nil"})


def _unstring_nulls(value: Any) -> Any:
    """Turn the *string* `"null"` into JSON `null`, recursively.

    glm-5.2 returns `"decision": "null"` where the schema declares a nullable
    enum, and no amount of corrective prompting fixed it — the retry came back
    identical. That is a model quirk about JSON encoding, not a disagreement
    about the answer: it meant null and typed it.

    Normalising it here is deliberate placement. The provider is where a
    vendor's habits are absorbed, so the agents above never learn that one
    backend spells null differently. It cannot invent a value or change a real
    one; the schema check downstream is still the authority on whether the
    result is acceptable.
    """
    if isinstance(value, dict):
        return {k: _unstring_nulls(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unstring_nulls(v) for v in value]
    if isinstance(value, str) and value.strip().lower() in _STRING_NULLS:
        return None
    return value


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
