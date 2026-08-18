"""Anthropic behind the `ModelProvider` seam.

This preserves exactly what the repository did before the seam existed, so
`LLM_BACKEND=anthropic` is a genuine fallback rather than a decorative one.

Two Anthropic-specific behaviours are kept here and nowhere else:

**Adaptive thinking and `effort` are frontier-model features.** Haiku rejects
both with a 400, and the orchestrator deliberately runs on Haiku — so the
request is shaped to the model rather than the model chosen to fit one request
shape.

**A typed refusal exists.** `stop_reason == "refusal"` is real on Anthropic and
absent on OpenAI-compatible providers, so it is normalised into the neutral
`ModelReply.stop_reason` here rather than checked upstream.
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

LOGGER = logging.getLogger("llm.anthropic")

# Call sites cheap enough that thinking would be waste, not depth.
_LOW_EFFORT = {CallSite.ORCHESTRATOR, CallSite.SAMPLING}


class AnthropicProvider:
    """Anthropic Messages API."""

    name = "anthropic"

    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        self._client: Any = None

    # --- plumbing ---------------------------------------------------------
    def _api(self) -> Any:
        if self._client is None:
            import anthropic  # noqa: PLC0415

            kwargs: dict[str, Any] = {"timeout": self.config.timeout_seconds}
            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def model_for(self, call_site: CallSite) -> str:
        return self.config.model_for(call_site)

    def _thinking(self, model: str, call_site: CallSite) -> dict[str, Any]:
        """Adaptive thinking, except where the model or the task rejects it."""
        if model.startswith("claude-haiku"):
            return {}
        effort = "low" if call_site in _LOW_EFFORT else "high"
        return {"thinking": {"type": "adaptive"}, "output_config": {"effort": effort}}

    @staticmethod
    def _text(response: Any) -> str:
        return "".join(b.text for b in (getattr(response, "content", None) or [])
                       if getattr(b, "type", None) == "text")

    @staticmethod
    def _usage(response: Any) -> dict[str, int]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        return {k: int(v) for k, v in
                (("input_tokens", getattr(usage, "input_tokens", 0)),
                 ("output_tokens", getattr(usage, "output_tokens", 0))) if v}

    # --- the three operations --------------------------------------------
    def structured_call(self, *, call_site: CallSite, system: str, prompt: str,
                        schema: dict[str, Any], max_tokens: int | None = None,
                        result_name: str = "emit_result") -> dict[str, Any]:
        model = self.model_for(call_site)
        schema = strictened(schema)
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": self.config.tokens_for(call_site, max_tokens),
            "system": system,
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
            "messages": [{"role": "user", "content": prompt}],
        }
        extra = self._thinking(model, call_site)
        if extra:
            request["thinking"] = extra["thinking"]
            request["output_config"]["effort"] = extra["output_config"]["effort"]

        started = time.time()
        try:
            response = self._api().messages.create(**request)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"anthropic call failed: {exc}",
                                kind=_kind_of(exc)) from exc

        if getattr(response, "stop_reason", None) == "refusal":
            raise ProviderError(f"{model} refused the request", kind="refusal")

        text = self._text(response).strip()
        if not text:
            raise ProviderError(f"{model} returned no content", kind="empty")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SchemaViolation(
                f"{model} returned unparseable JSON: {exc}") from exc

        LOGGER.debug("structured_call provider=%s model=%s call_site=%s %.1fs",
                     self.name, model, call_site.value, time.time() - started)
        # Even Anthropic's constrained decoding is verified rather than trusted:
        # the guarantee the system relies on is the validator, not the vendor.
        return validate_against_schema(payload, schema,
                                       context=f"{model} ({call_site.value})")

    def tool_turn(self, *, call_site: CallSite, system: str,
                  messages: list[Any], tools: list[ToolSpec],
                  max_tokens: int | None = None) -> ModelReply:
        model = self.model_for(call_site)
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": self.config.tokens_for(call_site, max_tokens),
            "system": system,
            "tools": [{"name": t.name, "description": t.description,
                       "input_schema": t.parameters} for t in tools],
            "messages": messages,
        }
        request.update(self._thinking(model, call_site))

        started = time.time()
        try:
            # Streaming, because adaptive thinking plus a high ceiling is exactly
            # the shape that trips the SDK's non-streaming timeout guard.
            with self._api().messages.stream(**request) as stream:
                response = stream.get_final_message()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"anthropic tool turn failed: {exc}",
                                kind=_kind_of(exc)) from exc

        blocks = getattr(response, "content", None) or []
        calls = [ToolCall(id=b.id, name=b.name, arguments=dict(b.input or {}))
                 for b in blocks if getattr(b, "type", None) == "tool_use"]
        stop = getattr(response, "stop_reason", "end_turn")
        return ModelReply(
            text="".join(b.text for b in blocks
                         if getattr(b, "type", None) == "text").strip(),
            tool_calls=calls,
            stop_reason=("refusal" if stop == "refusal"
                         else "tool_calls" if calls else "end_turn"),
            model=model, provider=self.name, raw_message=blocks,
            usage=self._usage(response), duration_seconds=time.time() - started,
        )

    def complete(self, *, call_site: CallSite, system: str | None,
                 messages: list[dict[str, str]],
                 max_tokens: int | None = None) -> ModelReply:
        model = self.model_for(call_site)
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": self.config.tokens_for(call_site, max_tokens),
            "messages": messages,
        }
        request.update(self._thinking(model, call_site))
        if system:
            request["system"] = system

        started = time.time()
        try:
            response = self._api().messages.create(**request)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"anthropic completion failed: {exc}",
                                kind=_kind_of(exc)) from exc

        stop = getattr(response, "stop_reason", "end_turn")
        return ModelReply(
            text=self._text(response), stop_reason=(
                "refusal" if stop == "refusal" else "end_turn"),
            model=getattr(response, "model", model), provider=self.name,
            usage=self._usage(response), duration_seconds=time.time() - started,
        )

    # --- message shapes ---------------------------------------------------
    def assistant_message(self, reply: ModelReply) -> Any:
        return {"role": "assistant", "content": reply.raw_message}

    def tool_result_message(self, results: list[tuple[str, str, bool]]) -> Any:
        return {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": call_id,
             "content": text, "is_error": is_error}
            for call_id, text, is_error in results]}


def _kind_of(exc: Exception) -> str:
    """Map an SDK exception onto the neutral error vocabulary."""
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "ratelimit" in name:
        return "rate_limit"
    if "authentication" in name or "permission" in name:
        return "auth"
    if "connection" in name or "apiconnection" in name:
        return "transport"
    return "error"
