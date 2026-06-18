from __future__ import annotations

"""run_orchestration_source_validation 분류기 단위테스트 (네트워크 0).

호출 없이 결정 가능한 final_action 분류만 검증한다. green(LIVE_TO_BACKEND_OK)은 이 도구가
만들지 않으므로 여기서도 생성되지 않는다.
"""

from ingestion.orchestration.api_readiness import ApiKeyReadiness
from ingestion.tools.run_orchestration_source_validation import (
    ACTION_CALLABLE,
    ACTION_HELD,
    ACTION_NEEDS_KEY,
    ACTION_QUARANTINED,
    ACTION_RATE_LIMITED,
    ACTION_SKIPPED,
    classify,
    summarize,
)


def _entry(sid="s", status="PRODUCTION_READY", **kw):
    base = {"source_id": sid, "current_status": status, "source_group": "news", "excluded": False}
    base.update(kw)
    return base


def _readiness(status="ready", present=True, missing=()):
    return ApiKeyReadiness(
        source_id="s", required_keys=(), keys_present=present, missing_keys=tuple(missing),
        alias_warning=(), readiness_status=status, safe_to_live_smoke=present,
    )


def test_excluded_is_skipped():
    v = classify(_entry(excluded=True, status="POLICY_EXCLUDED", terminal_reason="login_wall_no_bypass"), None)
    assert v.final_action == ACTION_SKIPPED
    assert v.call_allowed_by_policy is False
    assert "login_wall" in v.reason


def test_policy_excluded_status_is_skipped():
    v = classify(_entry(status="POLICY_EXCLUDED"), _readiness())
    assert v.final_action == ACTION_SKIPPED


def test_external_rate_limited_is_scheduled():
    v = classify(_entry(status="EXTERNAL_RATE_LIMITED", terminal_reason="PROVIDER_429_THROTTLE"), _readiness())
    assert v.final_action == ACTION_RATE_LIMITED
    assert v.call_allowed_by_policy is False


def test_cooldown_is_scheduled():
    v = classify(_entry(status="PRODUCTION_READY", cooldown_until="2026-06-18T00:00:00Z"), _readiness())
    assert v.final_action == ACTION_RATE_LIMITED


def test_community_preview_is_held():
    v = classify(_entry(status="PRODUCTION_READY_COMMUNITY_PREVIEW"), _readiness())
    assert v.final_action == ACTION_HELD
    assert v.call_allowed_by_policy is True


def test_quarantined_is_failed():
    v = classify(_entry(status="QUARANTINED", terminal_reason="consecutive_failures"), _readiness())
    assert v.final_action == ACTION_QUARANTINED


def test_missing_key_is_needs_key_names_only():
    v = classify(_entry(status="PRODUCTION_READY"), _readiness(status="missing", present=False, missing=("FINNHUB_API_KEY",)))
    assert v.final_action == ACTION_NEEDS_KEY
    assert "FINNHUB_API_KEY" in v.reason  # 키 이름만, 값 아님


def test_unknown_readiness_is_needs_key():
    v = classify(_entry(status="PRODUCTION_READY"), _readiness(status="unknown", present=False))
    assert v.final_action == ACTION_NEEDS_KEY


def test_ready_production_is_callable_not_probed():
    v = classify(_entry(status="PRODUCTION_READY"), _readiness(status="ready", present=True))
    assert v.final_action == ACTION_CALLABLE  # green 아님 — 정직한 미probe 버킷
    assert v.call_allowed_by_policy is True


def test_not_required_keyless_is_callable():
    v = classify(_entry(status="PRODUCTION_READY"), _readiness(status="not_required", present=True))
    assert v.final_action == ACTION_CALLABLE


def test_summarize_counts():
    verdicts = [
        classify(_entry(status="POLICY_EXCLUDED"), None),
        classify(_entry(status="PRODUCTION_READY"), _readiness()),
        classify(_entry(status="PRODUCTION_READY"), _readiness()),
    ]
    s = summarize(verdicts)
    assert s[ACTION_SKIPPED] == 1
    assert s[ACTION_CALLABLE] == 2


def test_no_green_action_ever_produced():
    # 헌법: 이 도구는 호출 없이 success(LIVE_TO_BACKEND_OK)를 만들지 않는다.
    for status in ("PRODUCTION_READY", "POLICY_EXCLUDED", "EXTERNAL_RATE_LIMITED",
                   "PRODUCTION_READY_COMMUNITY_PREVIEW", "QUARANTINED"):
        v = classify(_entry(status=status), _readiness())
        assert v.final_action != "LIVE_TO_BACKEND_OK"
        assert v.final_action != "DUPLICATE_COLLAPSED"
