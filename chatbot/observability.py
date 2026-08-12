"""LangSmith observability setup.

LangSmith's SDK reads its config (LANGCHAIN_TRACING_V2, LANGCHAIN_API_KEY, LANGCHAIN_PROJECT)
straight from the environment, so there is nothing to wire up beyond making sure those variables
are set before the traced calls happen and surfacing a clear warning if tracing was requested but
misconfigured.
"""

from __future__ import annotations

import logging

from config import get_settings

logger = logging.getLogger(__name__)


def configure_observability() -> None:
    settings = get_settings()

    if not settings.langsmith_tracing:
        logger.info("LangSmith tracing disabled (LANGCHAIN_TRACING_V2 is not 'true').")
        return

    if not settings.langsmith_api_key:
        logger.warning(
            "LANGCHAIN_TRACING_V2 is enabled but LANGCHAIN_API_KEY is not set; "
            "traces will fail to upload. Set it in .env."
        )
        return

    logger.info("LangSmith tracing enabled for project '%s'.", settings.langsmith_project)
