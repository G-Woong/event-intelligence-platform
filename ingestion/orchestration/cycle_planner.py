from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence

# Phase B 최소 due 판정. cron/Celery/Redis 없이 순수 함수로만 "지금 수집할 시간이
# 된 소스인가"를 판단한다. 소스 44개 전체 등록/주기 정책은 Phase C(SourceProfile).


@dataclass
class SourceSchedule:
    """한 소스의 수집 주기 정의.

    last_run_at은 호출자가 관리한다(Phase B는 순수 판정만 제공). 영속(JSONL/state)과
    last_run_at 자동 갱신은 Phase C에서 source_profiles.yaml과 함께 도입한다.
    """
    source_id: str
    min_interval_seconds: int
    last_run_at: Optional[datetime] = None
    freshness_bucket: str = ""   # near_real_time|hourly|daily 등 (Phase C에서 활용)
    enabled: bool = True


def _as_utc(dt: datetime) -> datetime:
    """naive datetime은 UTC로 간주한다(timezone-aware 비교 보장)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def is_due(
    now: datetime,
    last_run_at: Optional[datetime],
    min_interval_seconds: int,
) -> bool:
    """수집할 시간이 됐는지 판정.

    - last_run_at is None → True (한 번도 안 돌았으면 즉시 due)
    - now - last_run_at >= min_interval_seconds → True
    - 그 외 → False

    now/last_run_at가 naive면 UTC로 간주한다.
    """
    if last_run_at is None:
        return True
    elapsed = (_as_utc(now) - _as_utc(last_run_at)).total_seconds()
    return elapsed >= min_interval_seconds


def select_due_sources(
    schedules: Sequence[SourceSchedule],
    now: datetime,
) -> list[str]:
    """enabled이며 due인 소스 id 목록(입력 순서 보존)."""
    return [
        s.source_id
        for s in schedules
        if s.enabled and is_due(now, s.last_run_at, s.min_interval_seconds)
    ]
