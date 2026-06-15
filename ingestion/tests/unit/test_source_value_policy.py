"""G-8: source value policy — its/dcinside/google_trends disable 결정(네트워크 0)."""
from __future__ import annotations

from ingestion.orchestration.source_value_policy import (
    DISABLE_NOT_SERVICE_USEFUL,
    REQUIRES_OFFICIAL_API_OR_CONTRACT,
    decide_source_value,
    is_disabled_decision,
)


def test_its_disabled_not_service_useful():
    d = decide_source_value("its")
    assert d.decision == DISABLE_NOT_SERVICE_USEFUL
    assert d.profile_patch["enabled"] is False
    assert d.profile_patch["skip_reason"] == "not_service_useful"
    assert is_disabled_decision(d)


def test_dcinside_rescued_no_disable_decision():
    # Phase G-2: dcinside는 robots 허용 갤러리 static fetch로 복구됨 → disable 결정 없음(keep_active)
    assert decide_source_value("dcinside") is None


def test_google_trends_requires_official_api_or_contract():
    # Phase G-2: needs_api_integration(모호) → 검증된 blocker(공식 API 없음+anti-abuse 429)로 격상
    d = decide_source_value("google_trends_explore")
    assert d.decision == REQUIRES_OFFICIAL_API_OR_CONTRACT
    assert d.profile_patch["enabled"] is False
    assert d.profile_patch["skip_reason"] == "requires_official_api_or_contract"


def test_unknown_source_no_decision():
    assert decide_source_value("bbc") is None
    assert is_disabled_decision(None) is False


def test_rationale_present():
    for sid in ("its", "google_trends_explore"):
        assert decide_source_value(sid).rationale
