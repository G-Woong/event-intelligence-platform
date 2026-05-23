from __future__ import annotations

import logging
import os


_SECRET_KEYS = {"OPENAI_API_KEY", "LANGSMITH_API_KEY"}


class SecretMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for key in _SECRET_KEYS:
            val = os.getenv(key, "")
            if val and val in msg:
                record.msg = record.msg.replace(val, "***")
                record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.addFilter(SecretMaskingFilter())
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[handler],
    )
