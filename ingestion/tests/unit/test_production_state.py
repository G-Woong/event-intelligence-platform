"""F-1: ProductionSourceState — 전 source 상태 보유 + UNKNOWN 0 + 매핑(네트워크 0)."""
from __future__ import annotations

from datetime import datetime, timezone

from ingestion.orchestration.production_state import (
    EXTERNAL_RATE_LIMITED,
    NEEDS_OPERATOR_REVIEW,
    POLICY_BLOCKED_NO_BYPASS,
    POLICY_EXCLUDED,
    PRODUCTION_READY,
    PRODUCTION_READY_DEGRADED,
    PRODUCTION_STATES,
    UNKNOWN,
    VENDOR_CONTRACT_REQUIRED,
    decide_production_strategy,
    derive_production_state,
    summarize_states,
)
from ingestion.orchestration.source_profile import SourceProfile, load_source_profiles
from ingestion.orchestration.source_strategy_memory import (
    SourceStrategyMemory,
    load_strategy_memory,
)

_PROFILES = "ingestion/configs/source_profiles.yaml"
_MEMORY = "ingestion/configs/source_strategy_memory.yaml"


def _profile(sid, **kw):
    base = dict(source_id=sid, enabled=True, source_group="news", purpose="news",
                live_eligible="true", requires_api_key=False, preferred_strategy="strategy_loop_fetch",
                min_interval_seconds=1800)
    base.update(kw)
    return SourceProfile(**base)


def _mem(sid, final_status, *, successful=None, root_after=()):
    return SourceStrategyMemory(
        source_id=sid, previous_status="NEEDS_PARSER_UNRESOLVED", final_status=final_status,
        successful_strategy=successful, root_cause_after=tuple(root_after))


def test_every_source_has_state_no_unknown():
    profiles = load_source_profiles(_PROFILES)
    memory = load_strategy_memory(_MEMORY)
    states = [derive_production_state(p, memory=memory, api_key_ready=False) for p in profiles]
    assert len(states) == len(profiles)
    summ = summarize_states(states)
    assert summ["unknown"] == 0
    assert summ["source_without_state"] == 0
    for s in states:
        assert s.current_status in PRODUCTION_STATES
        assert s.current_status != UNKNOWN


def test_excluded_source_is_policy_excluded():
    p = _profile("reddit", enabled=False, skip_reason="disabled_by_policy")
    s = derive_production_state(p, memory={})
    assert s.current_status == POLICY_EXCLUDED
    assert s.production_ready is False and s.known_dead_end is True


def test_memory_data_alive_becomes_production_ready():
    p = _profile("tmdb", source_group="domain", requires_api_key=True, skip_reason="requires_api_key")
    mem = {"tmdb": _mem("tmdb", "OFFICIAL_RECORD_ALIVE", successful="adapter:tmdb")}
    s = derive_production_state(p, memory=mem, api_key_ready=False)
    # memory가 skip_reason보다 우선 — 살아난 source는 READY
    assert s.current_status == PRODUCTION_READY
    assert s.production_ready is True
    assert s.best_strategy == "adapter:tmdb"


def test_memory_degraded_alive_is_degraded():
    p = _profile("product_hunt", source_group="community")
    mem = {"product_hunt": _mem("product_hunt", "COMMUNITY_SIGNAL_ALIVE",
                                successful="adapter:product_hunt", root_after=["NO_STABLE_URL"])}
    s = derive_production_state(p, memory=mem)
    assert s.current_status == PRODUCTION_READY_DEGRADED
    assert s.production_ready is True


def test_memory_vendor_contract_required():
    p = _profile("eia", source_group="official", requires_api_key=True, skip_reason="requires_api_key")
    mem = {"eia": _mem("eia", "REQUIRES_VENDOR_SPECIFIC_API_CONTRACT")}
    s = derive_production_state(p, memory=mem)
    assert s.current_status == VENDOR_CONTRACT_REQUIRED
    assert s.production_ready is False


def test_api_key_required_missing_is_operator_review():
    p = _profile("polygon", source_group="market", requires_api_key=True, skip_reason="requires_api_key",
                 live_eligible="false")
    s = derive_production_state(p, memory={}, api_key_ready=False)
    assert s.current_status == NEEDS_OPERATOR_REVIEW
    assert s.terminal_reason == "api_key_missing"


def test_api_key_required_present_is_ready():
    p = _profile("polygon", source_group="market", requires_api_key=True, skip_reason="requires_api_key",
                 live_eligible="false")
    s = derive_production_state(p, memory={}, api_key_ready=True)
    assert s.current_status == PRODUCTION_READY and s.production_ready is True


def test_robots_block_is_policy_blocked():
    p = _profile("dcinside", source_group="community", live_eligible="false",
                 skip_reason="robots_or_policy_block")
    s = derive_production_state(p, memory={})
    assert s.current_status == POLICY_BLOCKED_NO_BYPASS
    assert s.known_dead_end is True


def test_health_overrides_static_state():
    from ingestion.core.source_health import SourceHealthState
    p = _profile("bbc")
    health = SourceHealthState(source_id="bbc", state="QUARANTINED_RETRYABLE",
                              next_retry_at="2099-01-01T00:00:00Z", reason="consecutive_failures:3")
    s = derive_production_state(p, memory={}, health=health)
    assert s.current_status == "QUARANTINED"
    assert s.quarantine_until == "2099-01-01T00:00:00Z"


def test_dead_end_strategy_decision_skips():
    p = _profile("its", source_group="domain")
    mem = {"its": _mem("its", "NOT_SERVICE_USEFUL")}
    s = derive_production_state(p, memory=mem)
    decision = decide_production_strategy("its", p, mem, s)
    assert decision.skip is True and decision.dead_end is True


def test_rate_limited_is_not_dead_end():
    # rate-limited는 dead-end가 아니라 조건부 skip(쿨다운 후 재시도)
    p = _profile("gdelt", source_group="official")
    mem = {"gdelt": _mem("gdelt", "EXTERNAL_RATE_LIMITED_WITH_RETRY_POLICY")}
    s = derive_production_state(p, memory=mem)
    assert s.known_dead_end is False
    decision = decide_production_strategy("gdelt", p, mem, s)
    assert decision.dead_end is False and decision.skip is True


def test_ready_source_strategy_reused():
    p = _profile("tmdb", source_group="domain")
    mem = {"tmdb": _mem("tmdb", "OFFICIAL_RECORD_ALIVE", successful="adapter:tmdb")}
    s = derive_production_state(p, memory=mem, api_key_ready=True)
    decision = decide_production_strategy("tmdb", p, mem, s)
    assert decision.skip is False
    assert decision.strategy == "adapter:tmdb"


def _rl_mem(sid, *, cooldown_policy=None, evidence=None, preferred=None):
    return SourceStrategyMemory(
        source_id=sid, previous_status="EXTERNAL_RATE_LIMITED",
        final_status="EXTERNAL_RATE_LIMITED_PENDING_RESUME",
        preferred_next_strategy=preferred, cooldown_policy=cooldown_policy, evidence=evidence)


def test_derive_sets_cooldown_until_from_cooldown_policy():
    # R-GdeltMainLoopResume: rate-limited memory의 resume deadline이 state.cooldown_until로 노출.
    p = _profile("gdelt", source_group="official")
    mem = {"gdelt": _rl_mem("gdelt", cooldown_policy="respect_cooldown_until:2026-06-16T11:25:27Z")}
    s = derive_production_state(p, memory=mem)
    assert s.current_status == EXTERNAL_RATE_LIMITED
    assert s.cooldown_until == "2026-06-16T11:25:27Z"


def test_derive_sets_cooldown_until_from_evidence_next_resume_at():
    p = _profile("gdelt", source_group="official")
    mem = {"gdelt": _rl_mem("gdelt", cooldown_policy="respect_cooldown",
                            evidence="attempts=broad;next_resume_at=2026-06-16T11:25:27Z;host=gdelt")}
    s = derive_production_state(p, memory=mem)
    assert s.cooldown_until == "2026-06-16T11:25:27Z"


def test_rate_limited_reprobes_after_cooldown_elapsed():
    # cooldown 만료(now > deadline) → not_ready skip 면제, 학습 전략으로 재probe.
    p = _profile("gdelt", source_group="official")
    mem = {"gdelt": _rl_mem("gdelt", cooldown_policy="respect_cooldown_until:2026-06-16T11:25:27Z",
                            preferred="host_rate_limit_spaced_probe")}
    s = derive_production_state(p, memory=mem)
    now = datetime(2026, 6, 22, 0, 0, 0, tzinfo=timezone.utc)
    d = decide_production_strategy("gdelt", p, mem, s, now=now)
    assert d.skip is False and d.dead_end is False
    assert d.strategy == "host_rate_limit_spaced_probe"


def test_rate_limited_still_cooling_keeps_skip():
    # cooldown 미경과(now < deadline) → 여전히 skip(우회 없음).
    p = _profile("gdelt", source_group="official")
    mem = {"gdelt": _rl_mem("gdelt", cooldown_policy="respect_cooldown_until:2099-01-01T00:00:00Z")}
    s = derive_production_state(p, memory=mem)
    now = datetime(2026, 6, 22, 0, 0, 0, tzinfo=timezone.utc)
    d = decide_production_strategy("gdelt", p, mem, s, now=now)
    assert d.skip is True and d.dead_end is False


def test_state_roundtrip_serialization(tmp_path):
    from ingestion.orchestration.production_state import (
        load_production_state,
        save_production_state,
    )
    p = _profile("bbc")
    s = derive_production_state(p, memory={})
    path = tmp_path / "state.json"
    save_production_state([s], path, run_id="r1")
    loaded = load_production_state(path)
    assert "bbc" in loaded
    assert loaded["bbc"].current_status == s.current_status
