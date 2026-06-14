"""Phase C SourceProfile 로드 + SourceSchedule 변환 단위 테스트 (docs 02, 03)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ingestion.orchestration.cycle_planner import select_due_sources
from ingestion.orchestration.source_profile import (
    SourceProfile,
    load_source_profiles,
    profiles_to_schedules,
)

UTC = timezone.utc


def _write_yaml(tmp_path, body: str):
    p = tmp_path / "source_profiles.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_load_two_profiles(tmp_path):
    p = _write_yaml(tmp_path, """
version: 1
profiles:
  gdelt:
    purpose: news
    min_interval_seconds: 900
  hacker_news:
    purpose: community
    is_community: true
    confirmation_policy: unconfirmed_until_corroborated
""")
    profiles = load_source_profiles(p)
    assert [x.source_id for x in profiles] == ["gdelt", "hacker_news"]
    assert profiles[0].min_interval_seconds == 900
    assert profiles[1].is_community is True
    assert profiles[1].confirmation_policy == "unconfirmed_until_corroborated"


def test_unknown_field_raises(tmp_path):
    p = _write_yaml(tmp_path, """
profiles:
  gdelt:
    bogus_field: 1
""")
    with pytest.raises(ValueError):
        load_source_profiles(p)


def test_missing_file_returns_empty(tmp_path):
    assert load_source_profiles(tmp_path / "nope.yaml") == []


def test_empty_profile_uses_defaults(tmp_path):
    p = _write_yaml(tmp_path, "profiles:\n  gdelt:\n")
    profiles = load_source_profiles(p)
    assert profiles[0].source_id == "gdelt"
    assert profiles[0].enabled is True
    assert profiles[0].requires_api_key is False


def test_profiles_to_schedules_reflects_interval_and_order():
    profiles = [
        SourceProfile("a", min_interval_seconds=300),
        SourceProfile("b", min_interval_seconds=600),
    ]
    schedules = profiles_to_schedules(profiles)
    assert [s.source_id for s in schedules] == ["a", "b"]
    assert schedules[0].min_interval_seconds == 300
    assert schedules[1].min_interval_seconds == 600


def test_disabled_profile_not_due():
    now = datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC)
    profiles = [
        SourceProfile("a", min_interval_seconds=300, enabled=True),
        SourceProfile("b", min_interval_seconds=300, enabled=False),
    ]
    schedules = profiles_to_schedules(profiles)
    assert select_due_sources(schedules, now) == ["a"]


def test_last_run_reflected_in_schedule_due():
    now = datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC)
    profiles = [SourceProfile("a", min_interval_seconds=300)]
    # last_run 방금 → not due
    schedules = profiles_to_schedules(profiles, {"a": now})
    assert select_due_sources(schedules, now) == []
    # last_run 10분 전 → due
    schedules2 = profiles_to_schedules(profiles, {"a": now - timedelta(seconds=600)})
    assert select_due_sources(schedules2, now) == ["a"]


def test_real_source_profiles_yaml_loads():
    """레포의 실제 source_profiles.yaml이 로드되고 community 정책이 일관된다."""
    profiles = load_source_profiles()  # 기본 경로
    assert len(profiles) >= 8
    by_id = {p.source_id: p for p in profiles}
    assert "gdelt" in by_id and "yna" in by_id
    for p in profiles:
        if p.is_community:
            assert p.confirmation_policy == "unconfirmed_until_corroborated"
