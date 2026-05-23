from __future__ import annotations

import logging
import os

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


def setup_langsmith() -> None:
    flag = (settings.LANGSMITH_TRACING or "").lower()
    if flag not in ("1", "true", "yes"):
        logger.info("LangSmith tracing disabled (LANGSMITH_TRACING unset/false)")
        return

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    if settings.LANGSMITH_ENDPOINT:
        os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    if settings.LANGSMITH_API_KEY:
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
    if settings.LANGSMITH_PROJECT:
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT

    logger.info("LangSmith tracing enabled project=%s", settings.LANGSMITH_PROJECT or "<default>")
