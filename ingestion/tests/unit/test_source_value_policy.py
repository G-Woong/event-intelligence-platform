"""G-8: source value policy — its/dcinside/google_trends disable 결정(네트워크 0)."""
from __future__ import annotations

from ingestion.orchestration.source_value_policy import (
    DISABLE_NOT_SERVICE_USEFUL,
    NEEDS_API_INTEGRATION,
    POLICY_EXCLUDED,
    decide_source_value,
    is_disabled_decision,
)


def test_its_disabled_not_service_useful():
    d = decide_source_value("its")
    assert d.decision == DISABLE_NOT_SERVICE_USEFUL
    assert d.profile_patch["enabled"] is False
    assert d.profile_patch["skip_reason"] == "not_service_useful"
    assert is_disabled_decision(d)


def test_dcinside_policy_excluded():
    d = decide_source_value("dcinside")
    assert d.decision == POLICY_EXCLUDED
    assert d.profile_patch["enabled"] is False
    assert "robots" in d.profile_patch["skip_reason"]


def test_google_trends_needs_api_integration():
    d = decide_source_value("google_trends_explore")
    assert d.decision == NEEDS_API_INTEGRATION
    assert d.profile_patch["enabled"] is False
    assert d.profile_patch["skip_reason"] == "needs_api_integration"


def test_unknown_source_no_decision():
    assert decide_source_value("bbc") is None
    assert is_disabled_decision(None) is False


def test_rationale_present():
    for sid in ("its", "dcinside", "google_trends_explore"):
        assert decide_source_value(sid).rationale
