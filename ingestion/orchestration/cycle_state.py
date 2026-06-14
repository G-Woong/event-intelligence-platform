from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ingestion.orchestration.cycle_state")

# Phase C: 소스별 last_run_at을 local_file(JSON)로 영속. Redis/DB 없음.
# 형태: {"sources": {"<source_id>": {"last_run_at": "<ISO8601>"}}}

_DEFAULT_STATE_PATH = (
    Path(__file__).parent.parent / "outputs" / "state" / "orchestration_cycle_state.json"
)


def _parse_iso(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_last_run_state(path: str | Path | None = None) -> dict[str, datetime]:
    """source_id → last_run_at(datetime) 매핑. 파일 없거나 깨졌으면 빈 dict.

    깨진 JSON/잘못된 타임스탬프는 수집을 막지 않도록 빈 상태로 안전 처리한다(로그 경고).
    """
    p = Path(path) if path else _DEFAULT_STATE_PATH
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("cycle_state unreadable (%s) — starting empty", exc)
        return {}
    if not isinstance(raw, dict):
        return {}
    sources = raw.get("sources", {})
    if not isinstance(sources, dict):
        return {}
    out: dict[str, datetime] = {}
    for sid, entry in sources.items():
        if isinstance(entry, dict):
            dt = _parse_iso(entry.get("last_run_at"))
            if dt is not None:
                out[str(sid)] = dt
    return out


def save_last_run_state(
    path: str | Path | None,
    state: dict[str, datetime],
) -> None:
    """state(dict[source_id, datetime])를 atomic하게 JSON 파일로 기록."""
    p = Path(path) if path else _DEFAULT_STATE_PATH
    payload = {
        "sources": {
            sid: {"last_run_at": dt.isoformat()} for sid, dt in state.items()
        }
    }
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        try:
            os.replace(tmp_name, p)
        except PermissionError:
            time.sleep(0.1)
            os.replace(tmp_name, p)
    except Exception as exc:
        logger.warning("cycle_state save failed: %s", exc)


def record_last_run(
    path: str | Path | None,
    source_id: str,
    timestamp: Optional[datetime] = None,
) -> None:
    """단일 소스의 last_run_at을 갱신(load→update→save). timestamp 기본 = now(UTC)."""
    ts = timestamp or datetime.now(timezone.utc)
    state = load_last_run_state(path)
    state[source_id] = ts
    save_last_run_state(path, state)
