"""The model-provider seam: one interface, many engines.

    Agent / MCP host
         │
         ▼
    ModelProvider          structured_call · tool_turn · complete
         ├── AnthropicProvider     output_config.format.json_schema
         └── ZaiProvider           forced function call (OpenAI-compatible)

Chosen by `LLM_BACKEND`, exactly as `DATA_BACKEND` chooses a `DataProvider` and
`QDRANT_URL` chooses a `VectorStore`. **Swapping the engine must require no
change in an agent.**

This is the lowest layer in the repository — it imports none of the others, so
the MCP host can keep running standalone without the backend, Qdrant or the UI.

For a structured answer the guarantee is never the vendor's word:

    schema -> provider mechanism -> arguments -> json.loads
           -> STRICT SCHEMA + TYPE VALIDATION -> caller
           -> (grounding validation, which lives with the agent)

Structural validity and semantic grounding are separate checks on purpose. A
structurally perfect object can still be ungrounded, and the system rejects it.
"""

from llm.base import ModelProvider
from llm.config import ANTHROPIC, ZAI, ModelConfig, load_config
from llm.contracts import (
    CallSite,
    ModelReply,
    ProviderError,
    SchemaViolation,
    ToolCall,
    ToolSpec,
)
from llm.factory import (
    build_provider,
    make_model_provider,
    provider_status,
    reset_provider,
)
from llm.validation import strictened, validate_against_schema

__all__ = [
    "ANTHROPIC",
    "ZAI",
    "CallSite",
    "ModelConfig",
    "ModelProvider",
    "ModelReply",
    "ProviderError",
    "SchemaViolation",
    "ToolCall",
    "ToolSpec",
    "build_provider",
    "load_config",
    "make_model_provider",
    "provider_status",
    "reset_provider",
    "strictened",
    "validate_against_schema",
]
