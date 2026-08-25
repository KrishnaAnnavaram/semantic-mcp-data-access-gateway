"""Redis-backed shared intelligence for the two specialist agents.

Redis remembers validated specialist work and records how that work behaved. It
does not hold source market data (PostgreSQL owns that) or authoritative domain
knowledge (Qdrant owns that), and it never changes the A2A route between agents.
"""

from agents.cache.config import RedisConfig
from agents.cache.factory import (
    build_intelligence,
    get_intelligence,
    reset_intelligence,
)
from agents.cache.service import NoOpIntelligence, RedisIntelligence

__all__ = [
    "NoOpIntelligence",
    "RedisConfig",
    "RedisIntelligence",
    "build_intelligence",
    "get_intelligence",
    "reset_intelligence",
]
