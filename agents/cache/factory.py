"""Process-wide construction of optional Redis intelligence."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from agents.cache.client import RedisConnection
from agents.cache.config import RedisConfig
from agents.cache.service import NoOpIntelligence, RedisIntelligence

_LOCK = threading.Lock()
_INTELLIGENCE: RedisIntelligence | NoOpIntelligence | None = None


def build_intelligence(
    *,
    config: RedisConfig | None = None,
    client: Any = None,
    embedder: Callable[[str], Any] | None = None,
    embedding_model: str = "",
) -> RedisIntelligence | NoOpIntelligence:
    resolved = config or RedisConfig.from_env()
    if not resolved.enabled:
        return NoOpIntelligence()
    connection = RedisConnection(resolved, client=client)
    return RedisIntelligence(
        resolved, connection, embedder=embedder, embedding_model=embedding_model
    )


def get_intelligence(
    *, embedder: Callable[[str], Any] | None = None, embedding_model: str = ""
) -> RedisIntelligence | NoOpIntelligence:
    global _INTELLIGENCE
    with _LOCK:
        if _INTELLIGENCE is None:
            _INTELLIGENCE = build_intelligence(embedder=embedder, embedding_model=embedding_model)
        else:
            _INTELLIGENCE.configure_embedder(embedder, embedding_model)
        return _INTELLIGENCE


def reset_intelligence() -> None:
    """Release the singleton; intended for process shutdown and tests."""
    global _INTELLIGENCE
    with _LOCK:
        if _INTELLIGENCE is not None:
            _INTELLIGENCE.close()
        _INTELLIGENCE = None
