"""Process-wide synchronous Redis pool with fail-open circuit breaking."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

from agents.cache.config import RedisConfig

LOGGER = logging.getLogger("agents.cache.redis")
T = TypeVar("T")


class RedisUnavailable(RuntimeError):
    pass


class RedisConnection:
    """A shared redis-py client; failures become misses unless strict mode is on."""

    def __init__(self, config: RedisConfig, client: Any = None) -> None:
        self.config = config
        self._client = client
        self._pool = None
        self._state_lock = threading.Lock()
        self._offline_until = 0.0
        self._warned = False
        if client is None:
            self._build()
        if config.required:
            self.ping(raise_on_error=True)

    def _build(self) -> None:
        import redis

        common = {
            "decode_responses": True,
            "max_connections": self.config.max_connections,
            "socket_connect_timeout": self.config.socket_connect_timeout,
            "socket_timeout": self.config.socket_timeout,
            "health_check_interval": 30,
            # redis-py 8 defaults to RESP3. Protocol 2 keeps response shapes
            # stable across supported redis-py 7/8 while using Redis 8.8.
            "protocol": 2,
        }
        if self.config.url:
            self._pool = redis.ConnectionPool.from_url(self.config.url, **common)
        else:
            self._pool = redis.ConnectionPool(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password or None,
                **common,
            )
        self._client = redis.Redis(connection_pool=self._pool)

    @property
    def raw(self) -> Any:
        return self._client

    def call(
        self, operation: str, func: Callable[[Any], T], default: T, *, force: bool = False
    ) -> T:
        now = time.monotonic()
        if not force and now < self._offline_until:
            return default
        started = time.perf_counter()
        try:
            result = func(self._client)
        except Exception as exc:
            with self._state_lock:
                self._offline_until = time.monotonic() + 5.0
                first = not self._warned
                self._warned = True
            message = f"Redis {operation} unavailable; using uncached behavior: {exc}"
            if self.config.required:
                raise RedisUnavailable(message) from exc
            (LOGGER.warning if first else LOGGER.debug)(message)
            return default
        duration_ms = (time.perf_counter() - started) * 1000.0
        with self._state_lock:
            self._offline_until = 0.0
            self._warned = False
        if duration_ms > 100:
            LOGGER.debug("slow Redis operation %s: %.1fms", operation, duration_ms)
        return result

    def ping(self, *, raise_on_error: bool = False) -> bool:
        try:
            ok = bool(self._client.ping())
        except Exception as exc:
            if raise_on_error:
                raise RedisUnavailable(f"Redis is required but unreachable: {exc}") from exc
            return False
        if ok:
            with self._state_lock:
                self._offline_until = 0.0
                self._warned = False
        return ok

    def health(self) -> dict[str, Any]:
        connected = self.ping()
        out: dict[str, Any] = {
            "enabled": True,
            "required": self.config.required,
            "connected": connected,
            "exact_cache": True,
            "semantic_cache": self.config.semantic_enabled,
            "streams": True,
            "timeseries": True,
        }
        if not connected:
            out.update({"version": None, "json": False, "search": False, "timeseries": False})
            return out
        try:
            info = self._client.info("server")
            out["version"] = info.get("redis_version")
            stats = self._client.info("stats")
            out["expired_keys"] = int(stats.get("expired_keys") or 0)
            out["evicted_keys"] = int(stats.get("evicted_keys") or 0)
            modules = self._client.execute_command("MODULE", "LIST") or []
            module_names = set()
            for module in modules:
                if isinstance(module, list):
                    values = {
                        str(module[index]).lower(): module[index + 1]
                        for index in range(0, len(module) - 1, 2)
                    }
                    module_names.add(str(values.get("name") or "").lower())
                elif isinstance(module, dict):
                    module_names.add(str(module.get("name") or "").lower())
            out["json"] = "rejson" in module_names
            out["search"] = "search" in module_names
            out["timeseries"] = "timeseries" in module_names
            out["semantic_cache"] = bool(self.config.semantic_enabled and out["search"])
        except Exception as exc:  # noqa: BLE001 - feature detail is diagnostic
            out["feature_probe_error"] = str(exc)
        return out

    def close(self) -> None:
        try:
            if self._client is not None:
                self._client.close()
            if self._pool is not None:
                self._pool.disconnect()
        except Exception as exc:  # noqa: BLE001 - shutdown is best effort
            LOGGER.debug("closing Redis connection failed: %s", exc)
