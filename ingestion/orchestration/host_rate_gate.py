"""R-GdeltGovernorSplitBrain — host 단위 호출 간격의 단일 출처(single source of truth).

문제: gdelt 호스트(api.gdeltproject.org)는 서로 독립적인 오케스트레이션 루프 3곳에서 호출된다 —
  1) 메인 production loop(run_production_orchestration; governor=rate_limit_governor.json)
  2) final source closure(run_final_source_closure; governor=gdelt_rate_limit_state.json)
  3) last-chance resurrection(run_last_chance_source_resurrection)
각 루프는 자기 governor 파일에만 last_call/cooldown을 기록하므로, 두 루프가 동시에 가동되면
호스트가 제공자 최소 간격(GDELT "one request every 5 seconds") 안에서 교차 호출될 수 있다.

이 모듈은 **host 키로** 단일 상태 파일(host_rate_gate.json)을 공유해, *실제 HTTP 호출 직전*에
모든 경로가 같은 gate를 통과하게 한다. source-level RateLimitGovernor(소스별 cadence/cooldown,
메인 900s vs closure 10s)와는 분리된 **호스트 단위 floor**다 — governor를 대체하지 않고 그 위에
얹힌다(우회/병렬/tight-retry 추가 없음).

cross-process 좌표화: file-backed면 decide/record 시점에 파일을 다시 읽고(다른 프로세스의 최신
기록 가시화), record_call은 호출 직전 **즉시** atomic write로 영속한다(성공/실패와 무관). OS 파일
락 없이 read-modify-write 경합 창은 남지만(잔여 한계), 재읽기+즉시영속으로 창을 최소화한다.

stdlib + json. 신규 설치 0. secret 미사용/미출력.
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

# gdelt 호스트와 보수적 host-level 최소 간격(초). 제공자 문서 한도("5초당 1회")보다 보수적.
GDELT_HOST = "api.gdeltproject.org"
GDELT_HOST_MIN_SPACING_SECONDS = 10

# source_id → (host, host_min_spacing_seconds). 메인루프가 어떤 source를 host-gate 대상으로
# 볼지의 단일 출처. (closure/resurrection은 gdelt 전용 경로라 직접 host를 넘긴다.)
HOST_GATED_SOURCES: dict[str, tuple[str, int]] = {
    "gdelt": (GDELT_HOST, GDELT_HOST_MIN_SPACING_SECONDS),
}


@dataclass(frozen=True)
class HostGateDecision:
    host: str
    allowed: bool
    reason: Optional[str]
    last_call_at: Optional[str]
    next_allowed_at: Optional[str]
    min_spacing_seconds: int


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


class HostRateGate:
    """host별 last_call을 wall-clock으로 추적하는 cross-loop 단일 출처. 영속은 선택(JSON).

    RateLimitGovernor와의 차이: 키가 source_id가 아니라 **host**이고, file-backed면 decide/record
    시점에 파일을 재읽어 다른 프로세스의 기록을 본다(governor는 생성 시 1회만 읽음). record_call은
    즉시 영속(다른 루프가 바로 보게).
    """

    def __init__(self, *, state_path: str | Path | None = None) -> None:
        self._path = Path(state_path) if state_path else None
        # {host: {"last_call_at": iso}}
        self._state: dict[str, dict] = {}
        self._reload()

    # ── 영속/재읽기 ───────────────────────────────────────────────────────────
    def _reload(self) -> None:
        """file-backed면 파일을 다시 읽어 in-memory 상태를 최신화(cross-process 가시성)."""
        if not (self._path and self._path.exists()):
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._state = {k: v for k, v in raw.items() if isinstance(v, dict)}
        except (json.JSONDecodeError, OSError):
            # 파일 손상/경합 시 in-memory 유지(빈 dict로 덮어쓰지 않음)
            pass

    def _persist(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=1)
        try:
            os.replace(tmp, self._path)
        except PermissionError:
            _time.sleep(0.1)
            os.replace(tmp, self._path)

    # ── 조회 ──────────────────────────────────────────────────────────────────
    def decide(
        self,
        host: str,
        *,
        min_spacing_seconds: int,
        now: Optional[datetime] = None,
    ) -> HostGateDecision:
        """host 호출 허용 여부. 직전 호출 후 min_spacing 미경과면 불허(no-bypass)."""
        self._reload()
        now = now or datetime.now(timezone.utc)
        last_iso = self._state.get(host, {}).get("last_call_at")
        last = _parse_iso(last_iso)
        if last is not None:
            elapsed = (now - last).total_seconds()
            if elapsed < min_spacing_seconds:
                next_allowed = _iso(last + timedelta(seconds=min_spacing_seconds))
                return HostGateDecision(
                    host=host, allowed=False,
                    reason=f"host_min_spacing_not_elapsed:{int(elapsed)}<{min_spacing_seconds}",
                    last_call_at=last_iso, next_allowed_at=next_allowed,
                    min_spacing_seconds=min_spacing_seconds,
                )
        return HostGateDecision(
            host=host, allowed=True, reason=None, last_call_at=last_iso,
            next_allowed_at=None, min_spacing_seconds=min_spacing_seconds,
        )

    def last_call_at(self, host: str) -> Optional[str]:
        self._reload()
        return self._state.get(host, {}).get("last_call_at")

    # ── 갱신 ──────────────────────────────────────────────────────────────────
    def record_call(self, host: str, *, now: Optional[datetime] = None) -> str:
        """실제 호출 직전에 호출. last_call_at=now로 기록하고 **즉시** 영속(성공/실패 무관).

        반환: 기록한 last_call_at ISO.
        """
        self._reload()
        now = now or datetime.now(timezone.utc)
        ts = _iso(now)
        self._state.setdefault(host, {})["last_call_at"] = ts
        self._persist()
        return ts

    def save(self, path: str | Path | None = None) -> Optional[Path]:
        p = Path(path) if path else self._path
        if p is None:
            return None
        if path and Path(path) != self._path:
            self._path = Path(path)
        self._persist()
        return self._path

    def snapshot(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in self._state.items()}
