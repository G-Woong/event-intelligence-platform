from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("crawling.tools.screenshot_logger")

_OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"


def screenshot_path_for(
    source_id: str,
    attempt_no: int,
    strategy: str,
) -> Path:
    return _OUTPUTS_DIR / "screenshots" / source_id / f"attempt{attempt_no}_{strategy}.png"


def dom_snapshot_path_for(
    source_id: str,
    attempt_no: int,
    strategy: str,
) -> Path:
    return _OUTPUTS_DIR / "dom_snapshots" / source_id / f"attempt{attempt_no}_{strategy}.html"


def save_dom_snapshot(
    html: str,
    source_id: str,
    attempt_no: int,
    strategy: str,
    max_chars: int = 50000,
) -> Optional[Path]:
    path = dom_snapshot_path_for(source_id, attempt_no, strategy)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html[:max_chars], encoding="utf-8")
        logger.debug("dom_snapshot saved: %s", path)
        return path
    except Exception as exc:
        logger.warning("dom_snapshot save failed: %s", exc)
        return None
