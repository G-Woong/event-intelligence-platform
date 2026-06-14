"""Phase F-3 RateLimitGovernor — source별 호출 간격/쿨다운 자동 관리.

설계 08(retry/rate-limit/quarantine)의 운영 루프 내장 버전. 핵심:
  - source별 마지막 호출 시각을 추적해 min_interval 미만이면 호출을 막는다.
  - 429/RateLimit/GDELT Note payload를 감지하면 retry_after(있으면) 또는 보수적
    쿨다운을 설정한다.
  - 쿨다운/간격 위반 source는 다음 plan에서 자동 skip된다(무한 retry 금지).

기존 ``ingestion/core/rate_limit_store``는 age_seconds에 monotonic clock을 써서
프로세스 재시작/결정적 테스트에 부적합하다. 이 governor는 wall-clock ISO 상태를
주입형 ``now``로 다루어 재현 가능하고 영속화 가능하게 한다. error 신호 감지는
``ingestion.core.error_taxonomy``를 재사용한다(중복 구현 금지).

stdlib + json. 신규 설치 0.
"""
from __future__ import annotations

import json
import os
import tempfile
import time as _time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from ingestion.core.error_taxonomy import classify_http_error, is_rate_limited_text

# group별 보수적 min_interval/쿨다운 기본값(초). profile.min_interval_seconds가 우선.
_DEFAULT_COOLDOWN_SECONDS = {
    "near_real_time": 900,
    "short": 1800,
    "medium": 3600,
    "daily": 21600,
}
_CONSERVATIVE_COOLDOWN_SECONDS = 3600  # retry_after 없을 때 기본 쿨다운
_MAX_COOLDOWN_SECONDS = 86400          # 쿨다운 상한(무한 대기 방지/명시)


@dataclass(frozen=True)
class RateLimitDecision:
    source_id: str
    allowed: bool
    reason: Optional[str]
    cooldown_until: Optional[str]
    min_interval_seconds: int


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def detect_rate_limit_signal(
    *,
    http_status: Optional[int] = None,
    payload_text: Optional[str] = None,
) -> bool:
    """429 / rate-limit 텍스트 / GDELT Note 등 외부 rate-limit 신호 감지.

    error_taxonomy를 재사용한다. payload는 일부만 검사(긴 본문 비용 절감).
    """
    if http_status is not None:
        try:
            if classify_http_error(int(http_status)).name == "RATE_LIMITED":
                return True
        except Exception:
            if int(http_status) == 429:
                return True
    if payload_text:
        if is_rate_limited_text(payload_text[:4000]):
            return True
        low = payload_text[:4000].lower()
        # GDELT는 200 OK + 본문에 limit note를 싣는다
        if "your query" in low and ("too" in low or "limit" in low):
            return True
    return False


def _extract_retry_after_seconds(retry_after: Optional[object]) -> Optional[int]:
    """Retry-After 헤더(초 정수 또는 HTTP-date) → 초. 파싱 불가 시 None."""
    if retry_after is None:
        return None
    if isinstance(retry_after, (int, float)):
        return max(0, int(retry_after))
    s = str(retry_after).strip()
    if s.isdigit():
        return int(s)
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt is not None:
            delta = (dt.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()
            return max(0, int(delta))
    except (TypeError, ValueError):
        pass
    return None


class RateLimitGovernor:
    """source별 last_call/cooldown을 wall-clock으로 추적. 영속화는 선택(JSON)."""

    def __init__(self, *, state_path: str | Path | None = None) -> None:
        self._path = Path(state_path) if state_path else None
        # {source_id: {"last_call_at": iso, "cooldown_until": iso, "reason": str}}
        self._state: dict[str, dict] = {}
        if self._path and self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._state = {k: v for k, v in raw.items() if isinstance(v, dict)}
            except (json.JSONDecodeError, OSError):
                self._state = {}

    # ── 조회 ────────────────────────────────────────────────────────────────
    def decide(
        self,
        source_id: str,
        *,
        min_interval_seconds: int,
        now: Optional[datetime] = None,
    ) -> RateLimitDecision:
        """호출 허용 여부. 쿨다운 중이거나 min_interval 미경과면 불허(skip 사유 포함)."""
        now = now or datetime.now(timezone.utc)
        entry = self._state.get(source_id, {})
        cooldown_until = entry.get("cooldown_until")
        cd = _parse_iso(cooldown_until)
        if cd is not None and cd > now:
            return RateLimitDecision(
                source_id=source_id, allowed=False,
                reason=f"cooldown_active:{entry.get('reason') or 'rate_limited'}",
                cooldown_until=cooldown_until, min_interval_seconds=min_interval_seconds,
            )
        last = _parse_iso(entry.get("last_call_at"))
        if last is not None:
            elapsed = (now - last).total_seconds()
            if elapsed < min_interval_seconds:
                return RateLimitDecision(
                    source_id=source_id, allowed=False,
                    reason=f"min_interval_not_elapsed:{int(elapsed)}<{min_interval_seconds}",
                    cooldown_until=None, min_interval_seconds=min_interval_seconds,
                )
        return RateLimitDecision(
            source_id=source_id, allowed=True, reason=None,
            cooldown_until=None, min_interval_seconds=min_interval_seconds,
        )

    # ── 갱신 ────────────────────────────────────────────────────────────────
    def record_call(self, source_id: str, *, now: Optional[datetime] = None) -> None:
        now = now or datetime.now(timezone.utc)
        entry = self._state.setdefault(source_id, {})
        entry["last_call_at"] = _iso(now)

    def record_rate_limited(
        self,
        source_id: str,
        *,
        retry_after: Optional[object] = None,
        freshness_bucket: str = "short",
        reason: str = "rate_limited",
        now: Optional[datetime] = None,
    ) -> str:
        """rate-limit 발생 기록 → cooldown_until 설정. retry_after 우선, 없으면 보수적 기본.

        반환: cooldown_until ISO. 무한 retry 방지를 위해 상한(_MAX_COOLDOWN_SECONDS)을 둔다.
        """
        now = now or datetime.now(timezone.utc)
        secs = _extract_retry_after_seconds(retry_after)
        if secs is None:
            secs = _DEFAULT_COOLDOWN_SECONDS.get(freshness_bucket, _CONSERVATIVE_COOLDOWN_SECONDS)
        secs = max(1, min(int(secs), _MAX_COOLDOWN_SECONDS))
        cooldown_until = _iso(now + timedelta(seconds=secs))
        entry = self._state.setdefault(source_id, {})
        entry["last_call_at"] = _iso(now)
        entry["cooldown_until"] = cooldown_until
        entry["reason"] = reason
        return cooldown_until

    def cooldown_until(self, source_id: str) -> Optional[str]:
        return self._state.get(source_id, {}).get("cooldown_until")

    def clear_cooldown(self, source_id: str) -> None:
        entry = self._state.get(source_id)
        if entry:
            entry.pop("cooldown_until", None)
            entry.pop("reason", None)

    # ── 영속화 ──────────────────────────────────────────────────────────────
    def save(self, path: str | Path | None = None) -> Optional[Path]:
        p = Path(path) if path else self._path
        if p is None:
            return None
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=1)
        try:
            os.replace(tmp, p)
        except PermissionError:
            _time.sleep(0.1)
            os.replace(tmp, p)
        return p

    def snapshot(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in self._state.items()}
