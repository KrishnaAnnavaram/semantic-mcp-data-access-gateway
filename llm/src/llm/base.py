"""The `ModelProvider` seam.

Three operations cover every model call in this repository:

    structured_call   a schema-constrained answer          (all three agents)
    tool_turn         one turn of a tool-calling loop      (the MCP host agent)
    complete          plain prose                          (MCP sampling)

Agents depend on this interface and never on a vendor. Whether a structured
answer is obtained through Anthropic's `output_config.format.json_schema` or
through an OpenAI-compatible forced function call is a *provider* decision, and
one the agents are deliberately not told about.

Message shapes differ between providers, so the two message-building helpers
(`assistant_message`, `tool_result_message`) also live behind the seam. That is
what lets the host's tool-calling loop hold no provider-specific structure at
all — it passes back whatever the provider handed it.

**The interface is synchronous.** So is `DataProvider`, and so is every current
call site; making it async would force an await through three agents and the
FastAPI handlers for no gain, since each call is a single blocking HTTP request
either way.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from llm.contracts import CallSite, ModelReply, ToolSpec


@runtime_checkable
class ModelProvider(Protocol):
    """What every provider must offer. Implementations translate; callers don't."""

    #: Short provider name, for logs and traces: "anthropic" | "zai".
    name: str

    def model_for(self, call_site: CallSite) -> str:
        """Which concrete model this provider uses for that call site."""
        ...

    def structured_call(self, *, call_site: CallSite, system: str, prompt: str,
                        schema: dict[str, Any], max_tokens: int | None = None,
                        result_name: str = "emit_result") -> dict[str, Any]:
        """A schema-valid object, or raise.

        Returns only after the payload has passed strict schema and type
        validation. Never returns a partially-correct object, and never returns
        a plausible substitute for one — the caller must be able to trust the
        shape without re-checking it.
        """
        ...

    def tool_turn(self, *, call_site: CallSite, system: str,
                  messages: list[Any], tools: list[ToolSpec],
                  max_tokens: int | None = None) -> ModelReply:
        """One turn of a tool-calling loop, normalised into `ModelReply`."""
        ...

    def complete(self, *, call_site: CallSite, system: str | None,
                 messages: list[dict[str, str]],
                 max_tokens: int | None = None) -> ModelReply:
        """Plain prose. Used by MCP sampling, which needs no schema."""
        ...

    def assistant_message(self, reply: ModelReply) -> Any:
        """The assistant turn, in this provider's own message shape."""
        ...

    def tool_result_message(
        self, results: list[tuple[str, str, bool]]) -> Any:
        """Tool results as one message. Each entry is (tool_call_id, text, is_error)."""
        ...
