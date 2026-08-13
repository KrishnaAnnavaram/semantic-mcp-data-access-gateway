"""Environment-driven configuration for the chatbot UI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    agent_backend: str
    agent_api_url: str
    agent_timeout_seconds: float
    langsmith_tracing: bool
    langsmith_project: str
    langsmith_api_key: str | None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        agent_backend=os.getenv("AGENT_BACKEND", "mock").strip().lower(),
        agent_api_url=os.getenv("AGENT_API_URL", "http://localhost:8000").rstrip("/"),
        agent_timeout_seconds=float(os.getenv("AGENT_TIMEOUT_SECONDS", "30")),
        langsmith_tracing=os.getenv("LANGCHAIN_TRACING_V2", "false").strip().lower() == "true",
        langsmith_project=os.getenv("LANGCHAIN_PROJECT", "semantic-mcp-data-access-gateway"),
        langsmith_api_key=os.getenv("LANGCHAIN_API_KEY") or None,
    )
