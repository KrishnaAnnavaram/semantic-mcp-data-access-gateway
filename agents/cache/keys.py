"""Central construction of namespaced, bounded Redis keys."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyBuilder:
    namespace: str

    def exact(self, agent: str, operation: str, digest: str) -> str:
        return f"{self.namespace}:cache:{agent}:{operation}:{digest}"

    def semantic(self, agent: str, operation: str, digest: str) -> str:
        return f"{self.namespace}:semantic:{agent}:{operation}:{digest}"

    def semantic_prefix(self, agent: str = "domain_expert", operation: str = "derive") -> str:
        return f"{self.namespace}:semantic:{agent}:{operation}:"

    def semantic_index(self) -> str:
        return f"{self.namespace}:idx:semantic"

    def run(self, request_id: str) -> str:
        return f"{self.namespace}:run:{request_id}"

    def run_prefix(self) -> str:
        return f"{self.namespace}:run:"

    def run_index(self) -> str:
        return f"{self.namespace}:idx:runs"

    def lock(self, cache_key: str) -> str:
        # The cache key is already bounded and contains only a SHA-256 digest.
        return f"{self.namespace}:lock:{cache_key.rsplit(':', 1)[-1]}"

    def stream(self) -> str:
        return f"{self.namespace}:stream:agent-events"

    def counters(self) -> str:
        return f"{self.namespace}:stats:counters"

    def question_frequency(self, scope: str = "all") -> str:
        return f"{self.namespace}:stats:question-frequency:{scope}"

    def question_metadata(self, digest: str) -> str:
        return f"{self.namespace}:stats:question:{digest}"

    def expiry_index(self) -> str:
        return f"{self.namespace}:stats:cache-expiry"

    def timeseries(self, agent: str, operation: str, metric: str) -> str:
        return f"{self.namespace}:ts:{agent}:{operation}:{metric}"

    def rate_limit(self, scope: str) -> str:
        return f"{self.namespace}:rate:llm:{scope}"

    def cache_pattern(self, scope: str = "all") -> str:
        if scope == "domain":
            return f"{self.namespace}:cache:domain_expert:*"
        if scope == "mcp":
            return f"{self.namespace}:cache:mcp_agent:*"
        if scope == "semantic":
            return f"{self.namespace}:semantic:*"
        return f"{self.namespace}:cache:*"
