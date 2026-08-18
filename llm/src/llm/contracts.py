"""Provider-neutral types. Nothing here names a vendor.

Every agent and the MCP host speak in these terms. The translation to
Anthropic's `tool_use` blocks or OpenAI's `tool_calls` happens *inside* a
provider and never leaks upward — that is the whole point of the seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CallSite(str, Enum):
    """Where in the system a model call originates.

    The model is chosen per call site, not per provider. Routing a greeting and
    grounding a market-risk requirement are different problems, and paying
    frontier rates for the first is why a split exists at all.
    """

    ORCHESTRATOR = "orchestrator"
    DOMAIN_EXPERT = "domain_expert"
    MCP_AGENT = "mcp_agent"
    HOST_AGENT = "host_agent"
    SAMPLING = "sampling"


@dataclass(frozen=True)
class ToolSpec:
    """One callable tool, in provider-neutral form."""

    name: str
    description: str
    parameters: dict[str, Any]      # JSON Schema for the arguments


@dataclass(frozen=True)
class ToolCall:
    """A model's request to call a tool, normalised across providers."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ModelReply:
    """One turn back from a model, whichever provider produced it."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    #: Provider-neutral stop signal: "end_turn" | "tool_calls" | "refusal"
    #: | "length" | "error". Anthropic's typed refusal and OpenAI's
    #: finish_reason both normalise into this.
    stop_reason: str = "end_turn"
    model: str = ""
    provider: str = ""
    #: Raw provider turn, kept so a tool-calling loop can echo the assistant
    #: message back verbatim on the next request without the loop knowing the
    #: provider's message shape.
    raw_message: Any = None
    usage: dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0

    @property
    def refused(self) -> bool:
        return self.stop_reason == "refusal"


class ProviderError(RuntimeError):
    """A model call failed in a way the caller must see rather than absorb.

    Providers raise this instead of returning a plausible-looking empty result:
    a fabricated value is worse than a visible failure, which is the rule the
    whole system is built on.
    """

    def __init__(self, message: str, *, kind: str = "error") -> None:
        super().__init__(message)
        #: "timeout" | "auth" | "rate_limit" | "balance" | "transport"
        #: | "empty" | "no_tool_call" | "malformed_arguments" | "schema"
        #: | "refusal" | "error"
        self.kind = kind


class SchemaViolation(ProviderError):
    """The model returned syntactically valid data that is structurally wrong.

    This is the failure this class exists to name. `json.loads` succeeding does
    not mean the model answered the question asked: a renamed field, a float
    where an integer was required, or a missing key all parse cleanly and then
    silently become `None` three layers downstream.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, kind="schema")
