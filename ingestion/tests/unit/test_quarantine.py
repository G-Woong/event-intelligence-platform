"""F-4: Failure Quarantine 정책 — 반복 실패 격리/정책 종결 분리(네트워크 0)."""
from __future__ import annotations

from datetime import datetime, timezone

from ingestion.orchestration.quarantine import (
    QuarantineDecision,
    evaluate_quarantine,
    is_quarantine_active,
)

_T0 = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)


def test_policy_terminal_is_not_quarantine():
    d = evaluate_quarantine("reuters", error_category="PAYWALL_DETECTED", now=_T0)
    assert d.quarantined is False
    assert d.reason.startswith("policy_terminal")
    assert d.recovery_strategy is None


def test_captcha_is_policy_terminal():
    d = evaluate_quarantine("x", error_category="CAPTCHA_DETECTED", now=_T0)
    assert d.quarantined is False and d.reason.startswith("policy_terminal")


def test_repeated_external_api_error_quarantines():
    d = evaluate_quarantine(
        "nyt", last_status="EXTERNAL_API_ERROR", error_category="EXTERNAL_API_ERROR",
        consecutive_failure_count=3, now=_T0)
    assert d.quarantined is True
    assert d.quarantine_until is not None
    assert d.recovery_strategy == "recovery_probe_after_cooldown"


def test_transient_failure_below_threshold_no_quarantine():
    d = evaluate_quarantine(
        "bbc", error_category="NETWORK_ERROR", consecutive_failure_count=1, now=_T0)
    assert d.quarantined is False
    assert d.recovery_strategy == "retry_next_cycle"


def test_body_fetch_failure_tries_alt_strategy_first():
    d = evaluate_quarantine(
        "ap_news", last_status="NO_BODY", error_category="NO_BODY",
        body_fetch_failures=1, alternative_strategy_available=True, now=_T0)
    assert d.quarantined is False
    assert d.recovery_strategy == "try_alternative_body_strategy"


def test_body_fetch_failure_repeated_quarantines():
    d = evaluate_quarantine(
        "ap_news", last_status="BODY_FETCH_FAILED", error_category="BODY_FETCH_FAILED",
        body_fetch_failures=3, now=_T0)
    assert d.quarantined is True
    assert d.recovery_strategy == "recheck_with_browser_after_cooldown"


def test_not_service_useful_not_quarantine():
    d = evaluate_quarantine("its", last_status="NOT_SERVICE_USEFUL", now=_T0)
    assert d.quarantined is False and d.reason == "not_service_useful"


def test_vendor_contract_requires_operator():
    d = evaluate_quarantine("eia", last_status="REQUIRES_VENDOR_SPECIFIC_API_CONTRACT", now=_T0)
    assert d.quarantined is False
    assert d.recovery_strategy == "operator_configure_endpoint"


def test_is_quarantine_active_future_true():
    d = evaluate_quarantine(
        "nyt", error_category="EXTERNAL_API_ERROR", consecutive_failure_count=5, now=_T0)
    assert is_quarantine_active(d.quarantine_until, now=_T0) is True


def test_is_quarantine_active_past_false():
    from datetime import timedelta
    d = evaluate_quarantine(
        "nyt", error_category="EXTERNAL_API_ERROR", consecutive_failure_count=5, now=_T0)
    # 격리 만료 이후 시점
    assert is_quarantine_active(d.quarantine_until, now=_T0 + timedelta(days=2)) is False


def test_is_quarantine_active_none_false():
    assert is_quarantine_active(None) is False
