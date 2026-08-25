"""One configuration surface for Redis cache, telemetry, and coordination."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

LOGGER = logging.getLogger("agents.cache.config")


def _load_env() -> None:
    try:
        from treasury_db.db import load_dotenv

        load_dotenv()
    except Exception as exc:  # noqa: BLE001 - a .env file is optional
        LOGGER.debug("optional .env loader unavailable: %s", exc)


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _bool(name: str, default: bool) -> bool:
    raw = _env(name, "true" if default else "false").lower()
    return raw in {"1", "true", "yes", "on"}


def _int(name: str, default: int, *, minimum: int = 0) -> int:
    try:
        value = int(_env(name, str(default)))
    except ValueError:
        return default
    return value if value >= minimum else default


def _float(name: str, default: float, *, minimum: float = 0.0) -> float:
    try:
        value = float(_env(name, str(default)))
    except ValueError:
        return default
    return value if value >= minimum else default


@dataclass(frozen=True)
class RedisConfig:
    """Resolved Redis settings with useful local-development defaults.

    Redis is opt-in when no environment has been loaded, preserving the existing
    unit-test and library behavior. The shipped `.env.example` and Compose
    service enable it for the full local stack.
    """

    enabled: bool = False
    required: bool = False
    url: str = ""
    host: str = "127.0.0.1"
    port: int = 6379
    db: int = 0
    password: str = ""
    max_connections: int = 24
    socket_connect_timeout: float = 0.25
    socket_timeout: float = 1.0
    cache_prefix: str = "smcp"
    namespace_version: str = "v1"

    domain_retrieval_ttl: int = 900
    domain_derive_ttl: int = 86_400
    domain_revise_ttl: int = 43_200
    domain_validate_ttl: int = 3_600
    mcp_catalogue_ttl: int = 300
    mcp_assess_ttl: int = 21_600
    mcp_choices_ttl: int = 300
    semantic_ttl: int = 86_400
    run_summary_ttl: int = 604_800

    semantic_enabled: bool = True
    semantic_similarity_threshold: float = 0.93
    semantic_candidates: int = 8
    agent_stream_maxlen: int = 50_000
    question_frequency_max_entries: int = 10_000
    metrics_retention_seconds: int = 2_592_000

    lock_ttl_ms: int = 360_000
    lock_wait_seconds: float = 310.0
    lock_poll_initial_ms: int = 25
    lock_poll_max_ms: int = 500

    global_llm_rate_limit: int = 0
    domain_llm_rate_limit: int = 0
    mcp_llm_rate_limit: int = 0
    llm_rate_window_seconds: int = 60

    @property
    def namespace(self) -> str:
        return f"{self.cache_prefix}:{self.namespace_version}"

    @classmethod
    def from_env(cls) -> RedisConfig:
        _load_env()
        return cls(
            enabled=_bool("REDIS_ENABLED", False),
            required=_bool("REDIS_REQUIRED", False),
            url=_env("REDIS_URL"),
            host=_env("REDIS_HOST", "127.0.0.1"),
            port=_int("REDIS_PORT", 6379, minimum=1),
            db=_int("REDIS_DB", 0),
            password=_env("REDIS_PASSWORD"),
            max_connections=_int("REDIS_MAX_CONNECTIONS", 24, minimum=1),
            socket_connect_timeout=_float("REDIS_CONNECT_TIMEOUT_SECONDS", 0.25),
            socket_timeout=_float("REDIS_SOCKET_TIMEOUT_SECONDS", 1.0),
            cache_prefix=_env("REDIS_CACHE_PREFIX", "smcp") or "smcp",
            namespace_version=_env("REDIS_NAMESPACE_VERSION", "v1") or "v1",
            domain_retrieval_ttl=_int("REDIS_DOMAIN_RETRIEVAL_TTL", 900, minimum=1),
            domain_derive_ttl=_int("REDIS_DOMAIN_DERIVE_TTL", 86_400, minimum=1),
            domain_revise_ttl=_int("REDIS_DOMAIN_REVISE_TTL", 43_200, minimum=1),
            domain_validate_ttl=_int("REDIS_DOMAIN_VALIDATE_TTL", 3_600, minimum=1),
            mcp_catalogue_ttl=_int("REDIS_MCP_CATALOGUE_TTL", 300, minimum=1),
            mcp_assess_ttl=_int("REDIS_MCP_ASSESS_TTL", 21_600, minimum=1),
            mcp_choices_ttl=_int("REDIS_MCP_CHOICES_TTL", 300, minimum=1),
            semantic_ttl=_int("REDIS_SEMANTIC_CACHE_TTL", 86_400, minimum=1),
            run_summary_ttl=_int("REDIS_RUN_SUMMARY_TTL", 604_800, minimum=1),
            semantic_enabled=_bool("REDIS_SEMANTIC_CACHE_ENABLED", True),
            semantic_similarity_threshold=_float("REDIS_SEMANTIC_SIMILARITY_THRESHOLD", 0.93),
            semantic_candidates=_int("REDIS_SEMANTIC_CANDIDATES", 8, minimum=1),
            agent_stream_maxlen=_int("REDIS_AGENT_STREAM_MAXLEN", 50_000, minimum=100),
            question_frequency_max_entries=_int(
                "REDIS_QUESTION_FREQUENCY_MAX_ENTRIES", 10_000, minimum=100
            ),
            metrics_retention_seconds=_int(
                "REDIS_METRICS_RETENTION_SECONDS", 2_592_000, minimum=60
            ),
            lock_ttl_ms=_int("REDIS_LOCK_TTL_MS", 360_000, minimum=1_000),
            lock_wait_seconds=_float("REDIS_SINGLEFLIGHT_WAIT_SECONDS", 310.0),
            lock_poll_initial_ms=_int("REDIS_LOCK_POLL_INITIAL_MS", 25, minimum=1),
            lock_poll_max_ms=_int("REDIS_LOCK_POLL_MAX_MS", 500, minimum=1),
            global_llm_rate_limit=_int("REDIS_GLOBAL_LLM_RATE_LIMIT", 0),
            domain_llm_rate_limit=_int("REDIS_DOMAIN_LLM_RATE_LIMIT", 0),
            mcp_llm_rate_limit=_int("REDIS_MCP_LLM_RATE_LIMIT", 0),
            llm_rate_window_seconds=_int("REDIS_LLM_RATE_WINDOW_SECONDS", 60, minimum=1),
        )

    def redacted(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "required": self.required,
            "host": self.host if not self.url else "configured by REDIS_URL",
            "port": self.port,
            "db": self.db,
            "password_configured": bool(self.password),
            "namespace": self.namespace,
            "semantic_enabled": self.semantic_enabled,
        }
