"""Redis 8.8 native window counters for cross-request LLM guardrails."""

from __future__ import annotations

from agents.cache.client import RedisConnection
from agents.cache.config import RedisConfig
from agents.cache.keys import KeyBuilder

_TAKE_LIMITS = """
local global_incremented = 0
local global_limit = tonumber(ARGV[1])
local agent_limit = tonumber(ARGV[2])
local window = tonumber(ARGV[3])

if global_limit > 0 then
  local result = redis.call(
    'INCREX', KEYS[1], 'BYINT', 1, 'UBOUND', global_limit,
    'EX', window, 'ENX')
  if tonumber(result[2]) == 0 then
    return {0, 'global'}
  end
  global_incremented = 1
end

if agent_limit > 0 then
  local result = redis.call(
    'INCREX', KEYS[2], 'BYINT', 1, 'UBOUND', agent_limit,
    'EX', window, 'ENX')
  if tonumber(result[2]) == 0 then
    if global_incremented == 1 then
      redis.call('DECR', KEYS[1])
    end
    return {0, 'agent'}
  end
end

return {1, 'allowed'}
"""


class RedisRateLimiter:
    def __init__(self, connection: RedisConnection, config: RedisConfig, keys: KeyBuilder) -> None:
        self.connection = connection
        self.config = config
        self.keys = keys

    def _limit_for(self, scope: str) -> int:
        if scope == "global":
            return self.config.global_llm_rate_limit
        if scope == "domain_expert":
            return self.config.domain_llm_rate_limit
        if scope == "mcp_agent":
            return self.config.mcp_llm_rate_limit
        return 0

    def allow(self, agent: str) -> bool:
        """Apply global and specialist limits; zero means deliberately disabled."""
        global_limit = self._limit_for("global")
        agent_limit = self._limit_for(agent)
        if global_limit <= 0 and agent_limit <= 0:
            return True
        reply = self.connection.call(
            "take LLM rate limits",
            lambda client: client.eval(
                _TAKE_LIMITS,
                2,
                self.keys.rate_limit("global"),
                self.keys.rate_limit(agent),
                global_limit,
                agent_limit,
                self.config.llm_rate_window_seconds,
            ),
            None,
        )
        # Fail open when Redis is unavailable. The script atomically rolls the
        # global increment back if a specialist-specific limit rejects.
        return reply is None or bool(int(reply[0]))
