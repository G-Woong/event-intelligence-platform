"""Phase B cycle planner due 판정 단위 테스트 (docs 07, 11)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.orchestration.cycle_planner import (
    SourceSchedule,
    is_due,
    select_due_sources,
)

UTC = timezone.utc


def test_due_when_never_run():
    assert is_due(datetime.now(UTC), None, 300) is True


def test_not_due_within_interval():
    now = datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC)
    last = now - timedelta(seconds=100)
    assert is_due(now, last, 300) is False


def test_due_exactly_at_interval():
    now = datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC)
    last = now - timedelta(seconds=300)
    assert is_due(now, last, 300) is True


def test_due_after_interval():
    now = datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC)
    last = now - timedelta(seconds=600)
    assert is_due(now, last, 300) is True


def test_naive_last_run_treated_as_utc():
    now = datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC)
    naive_last = datetime(2026, 6, 14, 11, 0, 0)  # naive, 1시간 전
    assert is_due(now, naive_last, 300) is True


def test_select_only_due_and_enabled_preserves_order():
    now = datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC)
    schedules = [
        SourceSchedule("a", 300, last_run_at=None),                          # due(never)
        SourceSchedule("b", 300, last_run_at=now - timedelta(seconds=100)),  # not due
        SourceSchedule("c", 300, last_run_at=now - timedelta(seconds=600)),  # due
        SourceSchedule("d", 300, last_run_at=None, enabled=False),           # disabled
    ]
    assert select_due_sources(schedules, now) == ["a", "c"]


def test_disabled_source_never_due():
    now = datetime.now(UTC)
    schedules = [SourceSchedule("x", 0, last_run_at=None, enabled=False)]
    assert select_due_sources(schedules, now) == []


def test_empty_schedules_returns_empty():
    assert select_due_sources([], datetime.now(UTC)) == []
