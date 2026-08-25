"""Owned Redis single-flight locks for expensive cache misses."""

from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass

from agents.cache.client import RedisConnection
from agents.cache.config import RedisConfig

_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


@dataclass(frozen=True)
class LockLease:
    key: str
    token: str
    owned: bool


class RedisSingleFlight:
    def __init__(self, connection: RedisConnection, config: RedisConfig) -> None:
        self.connection = connection
        self.config = config

    def acquire(self, key: str) -> LockLease:
        token = uuid.uuid4().hex
        owned = self.connection.call(
            "single-flight acquire",
            lambda client: bool(client.set(key, token, nx=True, px=self.config.lock_ttl_ms)),
            False,
        )
        return LockLease(key=key, token=token, owned=owned)

    def release(self, lease: LockLease) -> None:
        if not lease.owned:
            return
        self.connection.call(
            "single-flight release",
            lambda client: client.eval(_RELEASE, 1, lease.key, lease.token),
            0,
        )

    def wait_for(self, loader) -> object | None:
        """Wait boundedly for the lock owner to populate the cache."""
        deadline = time.monotonic() + self.config.lock_wait_seconds
        delay = self.config.lock_poll_initial_ms / 1000.0
        ceiling = self.config.lock_poll_max_ms / 1000.0
        while time.monotonic() < deadline:
            value = loader()
            if value is not None:
                return value
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(remaining, delay + random.random() * delay * 0.2))
            delay = min(ceiling, delay * 1.7)
        return None
