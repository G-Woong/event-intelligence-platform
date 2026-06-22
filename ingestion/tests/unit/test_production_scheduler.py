"""F-2: Production scheduler — due/skip 통합 정책(네트워크 0, 주입형 now/governor)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.orchestration.production_scheduler import (
    MODE_PRODUCTION,
    MODE_VALIDATION,
    build_production_run_plan,
)
from ingestion.orchestration.production_state import derive_production_state
from ingestion.orchestration.rate_limit_governor import RateLimitGovernor
from ingestion.orchestration.source_profile import SourceProfile, load_source_profiles
from ingestion.orchestration.source_strategy_memory import (
    SourceStrategyMemory,
    load_strategy_memory,
)

_T0 = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)


def _profile(sid, **kw):
    base = dict(source_id=sid, enabled=True, source_group="news", purpose="news",
                live_eligible="true", requires_api_key=False,
                preferred_strategy="strategy_loop_fetch", min_interval_seconds=1800)
    base.update(kw)
    return SourceProfile(**base)


def _mem(sid, final_status, *, successful=None):
    return SourceStrategyMemory(source_id=sid, previous_status="x", final_status=final_status,
                               successful_strategy=successful)


def _states(profiles, memory, **kw):
    return {p.source_id: derive_production_state(p, memory=memory, **kw) for p in profiles}


def test_ready_source_is_due_in_validation_mode():
    profiles = [_profile("bbc")]
    states = _states(profiles, {})
    plan = build_production_run_plan(profiles, states=states, now=_T0, mode=MODE_VALIDATION)
    assert "bbc" in plan.due_sources


def test_excluded_source_skipped():
    profiles = [_profile("reddit", enabled=False, skip_reason="disabled_by_policy")]
    states = _states(profiles, {})
    plan = build_production_run_plan(profiles, states=states, now=_T0, mode=MODE_VALIDATION)
    assert "reddit" in plan.skipped_sources
    assert plan.skipped_reasons["reddit"].startswith("policy_excluded")


def test_dead_end_source_skipped():
    profiles = [_profile("its", source_group="domain")]
    mem = {"its": _mem("its", "NOT_SERVICE_USEFUL")}
    states = _states(profiles, mem)
    plan = build_production_run_plan(profiles, states=states, memory=mem, now=_T0, mode=MODE_VALIDATION)
    assert "its" in plan.skipped_sources
    assert plan.skip_category_counts.get("skipped_dead_end", 0) >= 1


def test_interval_not_due_skipped_in_production_mode():
    profiles = [_profile("bbc", min_interval_seconds=1800)]
    states = _states(profiles, {})
    last_run = {"bbc": _T0 - timedelta(seconds=600)}  # 10분 전 — interval 미경과
    plan = build_production_run_plan(profiles, states=states, last_run_at_by_source=last_run,
                                     now=_T0, mode=MODE_PRODUCTION)
    assert "bbc" in plan.skipped_sources
    assert plan.skipped_reasons["bbc"].startswith("not_due")


def test_interval_elapsed_is_due():
    profiles = [_profile("bbc", min_interval_seconds=1800)]
    states = _states(profiles, {})
    last_run = {"bbc": _T0 - timedelta(seconds=2000)}
    plan = build_production_run_plan(profiles, states=states, last_run_at_by_source=last_run,
                                     now=_T0, mode=MODE_PRODUCTION)
    assert "bbc" in plan.due_sources


def test_validation_mode_ignores_interval_but_respects_cooldown():
    profiles = [_profile("bbc")]
    states = _states(profiles, {})
    governor = RateLimitGovernor()
    governor.record_rate_limited("bbc", retry_after=3600, now=_T0)
    plan = build_production_run_plan(profiles, states=states, governor=governor,
                                     now=_T0 + timedelta(seconds=60), mode=MODE_VALIDATION)
    assert "bbc" in plan.skipped_sources
    assert plan.skip_category_counts.get("skipped_cooldown", 0) >= 1


def test_quarantine_source_skipped():
    profiles = [_profile("bbc")]
    base = derive_production_state(profiles[0], memory={})
    quarantined = type(base)(**{**base.to_dict(), "quarantine_until": "2099-01-01T00:00:00Z"})
    plan = build_production_run_plan(profiles, states={"bbc": quarantined}, now=_T0, mode=MODE_VALIDATION)
    assert "bbc" in plan.skipped_sources
    assert plan.skipped_reasons["bbc"].startswith("quarantine_until")


def test_successful_strategy_in_plan():
    profiles = [_profile("tmdb", source_group="domain")]
    mem = {"tmdb": _mem("tmdb", "OFFICIAL_RECORD_ALIVE", successful="adapter:tmdb")}
    states = _states(profiles, mem, api_key_ready=True)
    plan = build_production_run_plan(profiles, states=states, memory=mem, now=_T0, mode=MODE_VALIDATION)
    assert plan.strategy_by_source.get("tmdb") == "adapter:tmdb"


def test_max_sources_caps_due():
    profiles = [_profile(f"src{i}") for i in range(5)]
    states = _states(profiles, {})
    plan = build_production_run_plan(profiles, states=states, now=_T0, mode=MODE_VALIDATION,
                                     max_sources=2)
    assert len(plan.due_sources) == 2
    assert any(r.startswith("deferred") for r in plan.skipped_reasons.values())


def test_full_profile_coverage_every_source_classified():
    profiles = load_source_profiles("ingestion/configs/source_profiles.yaml")
    memory = load_strategy_memory("ingestion/configs/source_strategy_memory.yaml")
    states = _states(profiles, memory, api_key_ready=False)
    plan = build_production_run_plan(profiles, states=states, memory=memory, now=_T0,
                                     mode=MODE_VALIDATION)
    # 모든 source는 due 또는 skip 둘 중 하나로 분류(누락 0)
    classified = set(plan.due_sources) | set(plan.skipped_sources)
    assert classified == {p.source_id for p in profiles}


def _rl_mem(sid, cooldown_until, *, preferred="host_rate_limit_spaced_probe"):
    return SourceStrategyMemory(
        source_id=sid, previous_status="EXTERNAL_RATE_LIMITED",
        final_status="EXTERNAL_RATE_LIMITED_PENDING_RESUME",
        preferred_next_strategy=preferred,
        cooldown_policy="respect_cooldown_until:%s" % cooldown_until)


def test_rate_limited_due_in_main_plan_after_cooldown():
    # R-GdeltMainLoopResume: cooldown 만료 → 메인 플래너가 자동 재probe(due). 개별 spaced-probe 의존 제거.
    profiles = [_profile("gdelt", source_group="official")]
    mem = {"gdelt": _rl_mem("gdelt", "2026-06-16T11:25:27Z")}
    states = _states(profiles, mem)
    plan = build_production_run_plan(profiles, states=states, memory=mem,
                                     now=datetime(2026, 6, 22, tzinfo=timezone.utc),
                                     mode=MODE_VALIDATION)
    assert "gdelt" in plan.due_sources


def test_rate_limited_skipped_in_main_plan_while_cooling():
    profiles = [_profile("gdelt", source_group="official")]
    mem = {"gdelt": _rl_mem("gdelt", "2099-01-01T00:00:00Z")}
    states = _states(profiles, mem)
    plan = build_production_run_plan(profiles, states=states, memory=mem,
                                     now=datetime(2026, 6, 22, tzinfo=timezone.utc),
                                     mode=MODE_VALIDATION)
    assert "gdelt" in plan.skipped_sources
    assert plan.skip_category_counts.get("skipped_cooldown", 0) >= 1
