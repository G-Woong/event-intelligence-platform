from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ingestion.core.source_health")

_DEFAULT_HEALTH_FILE = (
    Path(__file__).parent.parent / "outputs" / "state" / "source_health.json"
)

# Health states
HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
RATE_LIMITED_COOLDOWN = "RATE_LIMITED_COOLDOWN"
QUARANTINED_RETRYABLE = "QUARANTINED_RETRYABLE"
BLOCKED_TERMINAL = "BLOCKED_TERMINAL"
DEFERRED_SPECIAL_ROUND = "DEFERRED_SPECIAL_ROUND"

HEALTH_STATES: frozenset[str] = frozenset({
    HEALTHY, DEGRADED, RATE_LIMITED_COOLDOWN,
    QUARANTINED_RETRYABLE, BLOCKED_TERMINAL, DEFERRED_SPECIAL_ROUND,
})

# Probe error categories that mean a terminal blocker (no retry, ever)
_TERMINAL_BLOCKER_CATEGORIES = frozenset({
    "CAPTCHA_DETECTED", "LOGIN_WALL_DETECTED", "PAYWALL_DETECTED",
    "ROBOTS_BLOCKED", "LOGIN_WALL", "LICENSE_REQUIRED",
})

# Transient failure statuses that accumulate toward quarantine
_TRANSIENT_FAILURE_STATUSES = frozenset({
    "NETWORK_ERROR", "TIMEOUT",
})

_QUARANTINE_RECHECK_SECONDS = 6 * 3600  # 격리 후 재점검 가능 시각 (수동/미래 Celery용)


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


@dataclass
class SourceHealthState:
    source_id: str
    state: str = HEALTHY
    failure_count: int = 0
    last_status: Optional[str] = None
    last_error_category: Optional[str] = None
    last_checked_at: Optional[str] = None
    next_retry_at: Optional[str] = None
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "state": self.state,
            "failure_count": self.failure_count,
            "last_status": self.last_status,
            "last_error_category": self.last_error_category,
            "last_checked_at": self.last_checked_at,
            "next_retry_at": self.next_retry_at,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SourceHealthState":
        return cls(
            source_id=d.get("source_id", ""),
            state=d.get("state", HEALTHY),
            failure_count=int(d.get("failure_count", 0)),
            last_status=d.get("last_status"),
            last_error_category=d.get("last_error_category"),
            last_checked_at=d.get("last_checked_at"),
            next_retry_at=d.get("next_retry_at"),
            reason=d.get("reason", ""),
        )


def apply_probe_outcome(
    prev: Optional[SourceHealthState],
    *,
    source_id: str = "",
    status: str,
    error_category: Optional[str] = None,
    next_retry_at: Optional[str] = None,
    quarantine_threshold: int = 3,
) -> SourceHealthState:
    """Pure transition function: previous health + probe outcome → new health.

    - LIVE_SUCCESS / LIVE_PARTIAL → HEALTHY (failure_count reset)
    - RATE_LIMITED → RATE_LIMITED_COOLDOWN (+next_retry_at)
    - terminal blocker (CAPTCHA/LOGIN_WALL/PAYWALL/ROBOTS) → BLOCKED_TERMINAL immediately
    - NETWORK/TIMEOUT/5XX accumulate: < threshold → DEGRADED, >= threshold → QUARANTINED_RETRYABLE
    - DEFERRED → DEFERRED_SPECIAL_ROUND
    - other statuses → DEGRADED (single, non-accumulating beyond count)
    """
    sid = source_id or (prev.source_id if prev else "")
    now = _utc_now_iso()
    fc = prev.failure_count if prev else 0

    if status in ("LIVE_SUCCESS", "LIVE_PARTIAL"):
        return SourceHealthState(
            source_id=sid, state=HEALTHY, failure_count=0,
            last_status=status, last_error_category=None,
            last_checked_at=now, next_retry_at=None, reason="probe_success",
        )

    if status == "DEFERRED":
        return SourceHealthState(
            source_id=sid, state=DEFERRED_SPECIAL_ROUND, failure_count=fc,
            last_status=status, last_error_category=error_category,
            last_checked_at=now, next_retry_at=None,
            reason="deferred_to_special_round",
        )

    if status == "BLOCKED" or (error_category or "") in _TERMINAL_BLOCKER_CATEGORIES:
        return SourceHealthState(
            source_id=sid, state=BLOCKED_TERMINAL, failure_count=fc + 1,
            last_status=status, last_error_category=error_category,
            last_checked_at=now, next_retry_at=None,
            reason=f"terminal_blocker:{error_category or 'BLOCKED'}",
        )

    if status == "RATE_LIMITED":
        return SourceHealthState(
            source_id=sid, state=RATE_LIMITED_COOLDOWN, failure_count=fc,
            last_status=status, last_error_category=error_category,
            last_checked_at=now, next_retry_at=next_retry_at,
            reason="rate_limited_cooldown",
        )

    if status in _TRANSIENT_FAILURE_STATUSES or (error_category or "") in (
        "HTTP_5XX", "NETWORK_TIMEOUT", "NETWORK_CONNECTION_RESET",
    ):
        fc += 1
        if fc >= quarantine_threshold:
            recheck = datetime.now(timezone.utc) + timedelta(
                seconds=_QUARANTINE_RECHECK_SECONDS
            )
            return SourceHealthState(
                source_id=sid, state=QUARANTINED_RETRYABLE, failure_count=fc,
                last_status=status, last_error_category=error_category,
                last_checked_at=now,
                next_retry_at=recheck.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                reason=f"consecutive_failures:{fc}",
            )
        return SourceHealthState(
            source_id=sid, state=DEGRADED, failure_count=fc,
            last_status=status, last_error_category=error_category,
            last_checked_at=now, next_retry_at=None,
            reason=f"transient_failure:{fc}",
        )

    # Other non-success statuses (PARSE_ERROR, MISSING_KEY, UNKNOWN, ...) → DEGRADED
    return SourceHealthState(
        source_id=sid, state=DEGRADED, failure_count=fc + 1,
        last_status=status, last_error_category=error_category,
        last_checked_at=now, next_retry_at=None,
        reason=f"non_success_status:{status}",
    )


def should_skip(state: Optional[SourceHealthState]) -> tuple[bool, str]:
    """(skip?, reason). BLOCKED_TERMINAL always skips; cooldown/quarantine skip
    while next_retry_at is in the future; DEFERRED skips (special round only)."""
    if state is None:
        return False, ""
    if state.state == BLOCKED_TERMINAL:
        return True, f"blocked_terminal:{state.last_error_category or state.reason}"
    if state.state == DEFERRED_SPECIAL_ROUND:
        return True, "deferred_special_round"
    if state.state in (RATE_LIMITED_COOLDOWN, QUARANTINED_RETRYABLE):
        if not state.next_retry_at:
            return False, ""
        try:
            deadline = datetime.fromisoformat(state.next_retry_at.replace("Z", "+00:00"))
        except ValueError:
            return False, ""
        if deadline > datetime.now(timezone.utc):
            return True, f"{state.state.lower()}_until:{state.next_retry_at}"
    return False, ""


# ── stores ────────────────────────────────────────────────────────────────

class SourceHealthStore(ABC):
    @abstractmethod
    def get(self, source_id: str) -> Optional[SourceHealthState]: ...

    @abstractmethod
    def set(self, state: SourceHealthState) -> None: ...

    @abstractmethod
    def all_states(self) -> dict[str, SourceHealthState]: ...

    def list_due_for_retry(self) -> list[SourceHealthState]:
        """미래 Celery 스케줄러 진입점 — cooldown/quarantine deadline이 지난 소스 목록.
        이번 라운드에서는 소비자 없음."""
        due: list[SourceHealthState] = []
        now = datetime.now(timezone.utc)
        for st in self.all_states().values():
            if st.state not in (RATE_LIMITED_COOLDOWN, QUARANTINED_RETRYABLE):
                continue
            if not st.next_retry_at:
                due.append(st)
                continue
            try:
                deadline = datetime.fromisoformat(st.next_retry_at.replace("Z", "+00:00"))
            except ValueError:
                due.append(st)
                continue
            if deadline <= now:
                due.append(st)
        return due


class InMemorySourceHealthStore(SourceHealthStore):
    def __init__(self) -> None:
        self._states: dict[str, SourceHealthState] = {}

    def get(self, source_id: str) -> Optional[SourceHealthState]:
        return self._states.get(source_id)

    def set(self, state: SourceHealthState) -> None:
        self._states[state.source_id] = state

    def all_states(self) -> dict[str, SourceHealthState]:
        return dict(self._states)


class LocalFileSourceHealthStore(SourceHealthStore):
    """JSON file store. 수동 unquarantine은 파일 직접 편집으로 가능 (docs/76 절차)."""

    def __init__(self, file_path: Optional[Path] = None) -> None:
        self._path = Path(file_path) if file_path else _DEFAULT_HEALTH_FILE

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception as exc:
            logger.warning("source_health.json unreadable (%s) — starting empty", exc)
            return {}

    def _save(self, data: dict) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            try:
                os.replace(tmp_name, self._path)
            except PermissionError:
                time.sleep(0.1)
                os.replace(tmp_name, self._path)
        except Exception as exc:
            logger.warning("source_health.json save failed: %s", exc)

    def get(self, source_id: str) -> Optional[SourceHealthState]:
        entry = self._load().get(source_id)
        return SourceHealthState.from_dict(entry) if isinstance(entry, dict) else None

    def set(self, state: SourceHealthState) -> None:
        data = self._load()
        data[state.source_id] = state.to_dict()
        self._save(data)

    def all_states(self) -> dict[str, SourceHealthState]:
        return {
            sid: SourceHealthState.from_dict(entry)
            for sid, entry in self._load().items()
            if isinstance(entry, dict)
        }


_health_store_singleton: Optional[SourceHealthStore] = None


def get_health_store() -> SourceHealthStore:
    """Singleton health store (default: local_file)."""
    global _health_store_singleton
    if _health_store_singleton is None:
        _health_store_singleton = LocalFileSourceHealthStore()
    return _health_store_singleton


def reset_health_store_for_tests(store: Optional[SourceHealthStore] = None) -> None:
    global _health_store_singleton
    _health_store_singleton = store
