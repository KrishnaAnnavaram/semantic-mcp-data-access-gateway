"""Provider selection, in one place.

Mirrors `make_data_provider()` and `make_vector_store()`. Adding a third
provider means implementing the Protocol and adding one line here; nothing in
any agent changes.
"""

from __future__ import annotations

import logging
from typing import Any

from llm.base import ModelProvider
from llm.config import ANTHROPIC, ZAI, ModelConfig, load_config

LOGGER = logging.getLogger("llm.factory")

_PROVIDER: ModelProvider | None = None


def build_provider(config: ModelConfig | None = None) -> ModelProvider:
    """Construct a provider from config, without caching it."""
    config = config or load_config()
    if config.backend == ZAI:
        from llm.zai_provider import ZaiProvider  # noqa: PLC0415

        return ZaiProvider(config)
    if config.backend == ANTHROPIC:
        from llm.anthropic_provider import AnthropicProvider  # noqa: PLC0415

        return AnthropicProvider(config)
    raise ValueError(f"unknown LLM_BACKEND: {config.backend!r}")


def make_model_provider() -> ModelProvider:
    """The process-wide provider.

    Shared so connection pooling, timeouts and retry settings are configured in
    exactly one place; the per-agent difference is the *call site*, not the
    transport.
    """
    global _PROVIDER  # noqa: PLW0603 - deliberate process-wide singleton
    if _PROVIDER is None:
        _PROVIDER = build_provider()
        LOGGER.info("model provider: %s", _PROVIDER.name)
    return _PROVIDER


def reset_provider() -> None:
    """Drop the cached provider. For tests that vary the environment."""
    global _PROVIDER  # noqa: PLW0603
    _PROVIDER = None


def provider_status() -> dict[str, Any]:
    """What the model layer resolved to. Safe to log — no secrets."""
    try:
        return load_config().redacted()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
