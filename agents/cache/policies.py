"""Central cacheability and freshness policy; agents contain no TTL constants."""

from __future__ import annotations

from dataclasses import dataclass

from agents.cache.config import RedisConfig


@dataclass(frozen=True)
class OperationPolicy:
    exact: bool
    semantic: bool
    ttl_seconds: int
    expensive_llm: bool = False
    cache_failures: bool = False


def policy_for(agent: str, operation: str, config: RedisConfig) -> OperationPolicy:
    matrix = {
        ("domain_expert", "retrieve"): OperationPolicy(True, False, config.domain_retrieval_ttl),
        ("domain_expert", "retrieve_reference"): OperationPolicy(
            True, False, config.domain_retrieval_ttl
        ),
        ("domain_expert", "derive"): OperationPolicy(
            True, config.semantic_enabled, config.domain_derive_ttl, True
        ),
        ("domain_expert", "revise"): OperationPolicy(True, False, config.domain_revise_ttl, True),
        ("domain_expert", "validate_result"): OperationPolicy(
            True, False, config.domain_validate_ttl, True
        ),
        ("mcp_agent", "catalogue"): OperationPolicy(True, False, config.mcp_catalogue_ttl),
        ("mcp_agent", "assess"): OperationPolicy(True, False, config.mcp_assess_ttl, True),
        ("mcp_agent", "choices"): OperationPolicy(True, False, config.mcp_choices_ttl),
        # Execution is deliberately absent. A historical result is cacheable
        # only when every provider exposes an immutable snapshot identity. The
        # current seam does not, so "latest" and "2008" both execute normally.
    }
    return matrix.get((agent, operation), OperationPolicy(False, False, 0))


def execution_cacheability(requirement: object) -> tuple[bool, str]:
    """State the execution policy explicitly even though execution is uncached."""
    temporal = getattr(requirement, "temporal", None)
    if temporal is None or not getattr(temporal, "is_historical", False):
        return False, "latest_or_current_data"
    return False, "historical_snapshot_identity_not_exposed_by_provider"
