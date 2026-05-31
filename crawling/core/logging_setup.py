from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional


_SECRET_KEYS = {"OPENAI_API_KEY", "LANGSMITH_API_KEY"}


class SecretMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for key in _SECRET_KEYS:
            val = os.getenv(key, "")
            if val and val in msg:
                record.msg = str(record.msg).replace(val, "***")
                record.args = ()
        return True


class JsonlHandler(logging.Handler):
    def __init__(self, log_path: Path) -> None:
        super().__init__()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = log_path

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": self.formatter.formatTime(record) if self.formatter else "",
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
            }
            if hasattr(record, "extra"):
                entry.update(record.extra)  # type: ignore[arg-type]
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception:
            self.handleError(record)


def configure_crawling_logging(
    log_dir: Path,
    source_id: str = "",
    level: str = "INFO",
) -> None:
    root = logging.getLogger("crawling")
    if root.handlers:
        return

    _level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(_level)

    mask_filter = SecretMaskingFilter()

    console = logging.StreamHandler()
    console.setLevel(_level)
    console.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(name)s] %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    console.addFilter(mask_filter)
    root.addHandler(console)

    for sub in ("runs", "attempts", "errors"):
        fname = f"{source_id}_{sub}.jsonl" if source_id else f"{sub}.jsonl"
        handler = JsonlHandler(log_dir / sub / fname)
        handler.setLevel(_level)
        handler.addFilter(mask_filter)
        root.addHandler(handler)


def get_crawling_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"crawling.{name}")
