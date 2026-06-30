"""ADR#90 §14 — community interaction future gate 테스트(requirements 정의·runtime 0·댓글 응답 생성 0·anchor 0)."""
from __future__ import annotations

from backend.app.tools.community_interaction_future_gate import (
    COMMUNITY_GATE_REQUIREMENTS,
    build_community_interaction_future_gate,
)


def test_requirements_defined():
    c = build_community_interaction_future_gate()
    assert c["requirement_count"] == len(COMMUNITY_GATE_REQUIREMENTS) >= 8
    for r in ("verified_event", "public_iu_gate_passed", "moderation_policy", "privacy_user_data_policy",
              "reply_provenance", "rate_limit", "audit_log"):
        assert r in c["requirements"]


def test_runtime_disabled():
    c = build_community_interaction_future_gate()
    assert c["runtime_enabled"] is False
    assert c["user_comment_runtime_open"] is False
    assert c["community_interaction_gate_status"] == "community_interaction_requirements_unmet"


def test_no_comment_reply_generation():
    c = build_community_interaction_future_gate()
    assert c["comment_reply_generation"] is False
    assert c["comment_auto_reply_enabled"] is False
    assert c["llm_invoked"] is False


def test_community_not_evidence_anchor():
    c = build_community_interaction_future_gate()
    assert c["community_is_evidence_anchor"] is False


def test_all_met_still_runtime_disabled():
    # 모든 requirement 가 충족돼도(가정) 현 단계 runtime 은 여전히 disabled(public-IU/MERGE_GATE No-Go).
    passed = {r: True for r in COMMUNITY_GATE_REQUIREMENTS}
    c = build_community_interaction_future_gate(passed=passed)
    assert c["all_requirements_met"] is True
    assert c["runtime_enabled"] is False
    assert c["comment_reply_generation"] is False
    assert c["community_interaction_gate_status"] == "community_interaction_runtime_disabled"


def test_partial_requirements_tracked():
    c = build_community_interaction_future_gate(passed={"verified_event": True, "rate_limit": True})
    assert set(c["requirements_met"]) == {"verified_event", "rate_limit"}
    assert "public_iu_gate_passed" in c["requirements_unmet"]
    assert c["all_requirements_met"] is False
