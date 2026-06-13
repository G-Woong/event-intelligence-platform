from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.core.source_health import (
    BLOCKED_TERMINAL,
    DEFERRED_SPECIAL_ROUND,
    DEGRADED,
    HEALTHY,
    QUARANTINED_RETRYABLE,
    RATE_LIMITED_COOLDOWN,
    InMemorySourceHealthStore,
    LocalFileSourceHealthStore,
    SourceHealthState,
    apply_probe_outcome,
    reset_health_store_for_tests,
    should_skip,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_health_store_for_tests()
    yield
    reset_health_store_for_tests()


# ── 전이 함수 ─────────────────────────────────────────────────────────────

def test_success_transitions_to_healthy_and_resets_failures():
    prev = SourceHealthState(source_id="s", state=DEGRADED, failure_count=2)
    new = apply_probe_outcome(prev, status="LIVE_SUCCESS")
    assert new.state == HEALTHY
    assert new.failure_count == 0
    assert new.next_retry_at is None


def test_partial_also_transitions_to_healthy():
    new = apply_probe_outcome(None, source_id="s", status="LIVE_PARTIAL")
    assert new.state == HEALTHY


def test_rate_limited_transitions_to_cooldown_with_next_retry():
    new = apply_probe_outcome(
        None, source_id="s", status="RATE_LIMITED",
        next_retry_at="2099-01-01T00:00:00Z",
    )
    assert new.state == RATE_LIMITED_COOLDOWN
    assert new.next_retry_at == "2099-01-01T00:00:00Z"


@pytest.mark.parametrize("category", [
    "CAPTCHA_DETECTED", "LOGIN_WALL_DETECTED", "PAYWALL_DETECTED", "ROBOTS_BLOCKED",
])
def test_blocker_transitions_to_terminal_immediately(category):
    new = apply_probe_outcome(None, source_id="s", status="BLOCKED", error_category=category)
    assert new.state == BLOCKED_TERMINAL


def test_deferred_transitions_to_special_round():
    new = apply_probe_outcome(None, source_id="s", status="DEFERRED")
    assert new.state == DEFERRED_SPECIAL_ROUND


def test_transient_failures_accumulate_to_quarantine():
    state = None
    for i in range(1, 3):
        state = apply_probe_outcome(state, source_id="s", status="NETWORK_ERROR")
        assert state.state == DEGRADED
        assert state.failure_count == i
    state = apply_probe_outcome(state, source_id="s", status="TIMEOUT")
    assert state.state == QUARANTINED_RETRYABLE
    assert state.failure_count == 3
    assert state.next_retry_at is not None  # 재점검 시각 부여


def test_recovery_after_quarantine():
    quarantined = SourceHealthState(
        source_id="s", state=QUARANTINED_RETRYABLE, failure_count=3
    )
    new = apply_probe_outcome(quarantined, status="LIVE_SUCCESS")
    assert new.state == HEALTHY
    assert new.failure_count == 0


def test_custom_quarantine_threshold():
    state = apply_probe_outcome(
        None, source_id="s", status="NETWORK_ERROR", quarantine_threshold=1
    )
    assert state.state == QUARANTINED_RETRYABLE


# ── should_skip ───────────────────────────────────────────────────────────

def test_should_skip_blocked_terminal():
    st = SourceHealthState(source_id="s", state=BLOCKED_TERMINAL,
                           last_error_category="CAPTCHA_DETECTED")
    skip, reason = should_skip(st)
    assert skip is True
    assert "CAPTCHA_DETECTED" in reason


def test_should_skip_future_cooldown_but_not_expired():
    future = SourceHealthState(source_id="s", state=RATE_LIMITED_COOLDOWN,
                               next_retry_at="2099-01-01T00:00:00Z")
    assert should_skip(future)[0] is True

    expired = SourceHealthState(source_id="s", state=RATE_LIMITED_COOLDOWN,
                                next_retry_at="2020-01-01T00:00:00Z")
    assert should_skip(expired)[0] is False


def test_should_skip_none_and_healthy():
    assert should_skip(None) == (False, "")
    assert should_skip(SourceHealthState(source_id="s", state=HEALTHY))[0] is False


# ── local file store ──────────────────────────────────────────────────────

def test_local_file_store_roundtrip(tmp_path: Path):
    path = tmp_path / "state" / "source_health.json"
    s1 = LocalFileSourceHealthStore(path)
    s1.set(SourceHealthState(source_id="gdelt", state=DEGRADED, failure_count=2,
                             last_status="TIMEOUT", reason="transient_failure:2"))
    s2 = LocalFileSourceHealthStore(path)  # 재기동 시뮬레이션
    loaded = s2.get("gdelt")
    assert loaded is not None
    assert loaded.state == DEGRADED
    assert loaded.failure_count == 2
    assert "gdelt" in s2.all_states()


def test_local_file_store_corrupted_starts_empty(tmp_path: Path):
    path = tmp_path / "source_health.json"
    path.write_text("not json", encoding="utf-8")
    store = LocalFileSourceHealthStore(path)
    assert store.get("anything") is None


def test_list_due_for_retry():
    store = InMemorySourceHealthStore()
    store.set(SourceHealthState(source_id="due", state=QUARANTINED_RETRYABLE,
                                next_retry_at="2020-01-01T00:00:00Z"))
    store.set(SourceHealthState(source_id="not_due", state=QUARANTINED_RETRYABLE,
                                next_retry_at="2099-01-01T00:00:00Z"))
    store.set(SourceHealthState(source_id="healthy", state=HEALTHY))
    due_ids = {s.source_id for s in store.list_due_for_retry()}
    assert due_ids == {"due"}


# ── collection_probe health gate 통합 ─────────────────────────────────────

def _gate_test_store(state: SourceHealthState) -> InMemorySourceHealthStore:
    store = InMemorySourceHealthStore()
    store.set(state)
    reset_health_store_for_tests(store)
    return store


def test_blocked_source_skipped_without_network(monkeypatch):
    """BLOCKED_TERMINAL 소스는 네트워크 호출 없이 BLOCKED 반환."""
    from ingestion.fetch_strategies import collection_probe as cp

    _gate_test_store(SourceHealthState(
        source_id="bbc", state=BLOCKED_TERMINAL, last_error_category="CAPTCHA_DETECTED"
    ))

    def _boom(*a, **k):
        raise AssertionError("network probe must not be called")

    monkeypatch.setattr(cp, "run_api_live_probe", _boom)
    result = cp.run_collection_probe("bbc")
    assert result.status == "BLOCKED"
    assert result.next_action.startswith("health_gate_skip:")


def test_force_bypasses_health_gate(monkeypatch):
    from ingestion.fetch_strategies import collection_probe as cp
    from ingestion.probes.models import ProbeResult

    _gate_test_store(SourceHealthState(
        source_id="bbc", state=BLOCKED_TERMINAL, last_error_category="CAPTCHA_DETECTED"
    ))

    called = {"n": 0}

    def _fake_probe(source_id, max_calls=1):
        called["n"] += 1
        return ProbeResult(source_id=source_id, method="api", status="LIVE_SUCCESS",
                           items_found=3)

    monkeypatch.setattr(cp, "run_api_live_probe", _fake_probe)
    result = cp.run_collection_probe("bbc", force=True)
    assert called["n"] == 1
    assert result.status == "LIVE_SUCCESS"


def test_success_updates_health_store(monkeypatch):
    from ingestion.fetch_strategies import collection_probe as cp
    from ingestion.probes.models import ProbeResult

    store = InMemorySourceHealthStore()
    reset_health_store_for_tests(store)

    monkeypatch.setattr(
        cp, "run_api_live_probe",
        lambda source_id, max_calls=1: ProbeResult(
            source_id=source_id, method="api", status="LIVE_SUCCESS", items_found=2
        ),
    )
    cp.run_collection_probe("bbc")
    state = store.get("bbc")
    assert state is not None
    assert state.state == HEALTHY


def test_cooldown_gate_returns_rate_limited_without_network(monkeypatch):
    from ingestion.fetch_strategies import collection_probe as cp

    _gate_test_store(SourceHealthState(
        source_id="gdelt", state=RATE_LIMITED_COOLDOWN,
        next_retry_at="2099-01-01T00:00:00Z",
    ))
    monkeypatch.setattr(
        cp, "run_api_live_probe",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")),
    )
    result = cp.run_collection_probe("gdelt")
    assert result.status == "RATE_LIMITED"
