"""F-3: RateLimitGovernor — min_interval/쿨다운/신호 감지(네트워크 0, 주입형 now)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.orchestration.rate_limit_governor import (
    RateLimitGovernor,
    detect_rate_limit_signal,
)

_T0 = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)


def test_first_call_allowed():
    g = RateLimitGovernor()
    d = g.decide("bbc", min_interval_seconds=1800, now=_T0)
    assert d.allowed is True and d.reason is None


def test_min_interval_not_elapsed_blocks():
    g = RateLimitGovernor()
    g.record_call("bbc", now=_T0)
    d = g.decide("bbc", min_interval_seconds=1800, now=_T0 + timedelta(seconds=600))
    assert d.allowed is False
    assert d.reason.startswith("min_interval_not_elapsed")


def test_min_interval_elapsed_allows():
    g = RateLimitGovernor()
    g.record_call("bbc", now=_T0)
    d = g.decide("bbc", min_interval_seconds=1800, now=_T0 + timedelta(seconds=1801))
    assert d.allowed is True


def test_rate_limited_payload_creates_cooldown():
    g = RateLimitGovernor()
    until = g.record_rate_limited("gdelt", freshness_bucket="near_real_time", now=_T0)
    assert until is not None
    d = g.decide("gdelt", min_interval_seconds=900, now=_T0 + timedelta(seconds=60))
    assert d.allowed is False
    assert d.reason.startswith("cooldown_active")


def test_retry_after_seconds_respected():
    g = RateLimitGovernor()
    g.record_rate_limited("x", retry_after=120, now=_T0)
    # 119초 후엔 여전히 쿨다운, 121초 후엔 해제
    assert g.decide("x", min_interval_seconds=1, now=_T0 + timedelta(seconds=119)).allowed is False
    assert g.decide("x", min_interval_seconds=1, now=_T0 + timedelta(seconds=121)).allowed is True


def test_no_retry_after_uses_conservative_default():
    g = RateLimitGovernor()
    until = g.record_rate_limited("y", retry_after=None, freshness_bucket="short", now=_T0)
    # short 기본 쿨다운(1800s) 적용 → 1700초 후엔 여전히 막힘
    assert g.decide("y", min_interval_seconds=1, now=_T0 + timedelta(seconds=1700)).allowed is False


def test_cooldown_has_upper_bound_no_infinite():
    g = RateLimitGovernor()
    # 비정상적으로 큰 retry_after도 상한(86400s)으로 클램프
    until = g.record_rate_limited("z", retry_after=10_000_000, now=_T0)
    deadline = datetime.fromisoformat(until.replace("Z", "+00:00"))
    assert (deadline - _T0).total_seconds() <= 86400


def test_detect_rate_limit_signal_http_429():
    assert detect_rate_limit_signal(http_status=429) is True
    assert detect_rate_limit_signal(http_status=200) is False


def test_detect_rate_limit_signal_text():
    assert detect_rate_limit_signal(payload_text="Error: rate limit exceeded, try later") is True


def test_detect_gdelt_note():
    assert detect_rate_limit_signal(payload_text="Your query was too broad; please limit it.") is True


def test_persistence_roundtrip(tmp_path):
    p = tmp_path / "gov.json"
    g = RateLimitGovernor(state_path=p)
    g.record_rate_limited("a", retry_after=300, now=_T0)
    g.save()
    g2 = RateLimitGovernor(state_path=p)
    assert g2.decide("a", min_interval_seconds=1, now=_T0 + timedelta(seconds=10)).allowed is False


def test_clear_cooldown():
    g = RateLimitGovernor()
    g.record_rate_limited("a", retry_after=300, now=_T0)
    g.clear_cooldown("a")
    assert g.decide("a", min_interval_seconds=1, now=_T0 + timedelta(seconds=10)).allowed is True
