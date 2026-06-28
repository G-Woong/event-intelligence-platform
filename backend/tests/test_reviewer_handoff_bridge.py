"""ADR#84 — reviewer handoff bridge tests (freeze → contact-PRE package; 전송 0·PII/secret/score 0).

정책을 테스트로 잠근다: freeze 있을 때만 handoff_ready·freeze 없으면 ready=False + blocker·actual_sending 항상 False·
freeze_is_reviewer_worklist_only=True·gold 미증가·forbidden key(score/rationale/predicted/PII/body/secret) 0.
"""
from __future__ import annotations

import pytest

from backend.app.tools.reviewer_handoff_bridge import (
    HANDOFF_BLOCKED_NO_FREEZE,
    build_reviewer_handoff_bridge,
)

_FORBIDDEN = ("score", "rationale", "predicted_status", "same_event", "raw_body", "body",
              "reviewer_name", "reviewer_email", "email", "phone", "secret", "api_key")


def _frozen_pcand():
    """live-derived production-candidate freeze 성공 형태(run_r1_production_candidate_acquisition 미러·sanitized)."""
    return {
        "production_candidate_batch_ready": True,
        "production_batch_id": "reviewer_prod_cand_001",
        "production_batch_signature": "sha256:deadbeefcafe0001",
        "production_frozen_pair_count": 3,
        "candidate_provenance": "live_derived",
        "expected_label_files": [
            "reviewer_prod_cand_001__rev_00001__labels.jsonl",
            "reviewer_prod_cand_001__rev_00002__labels.jsonl",
        ],
        "validation_command": ".\\.venv\\Scripts\\python.exe -m backend.app.tools.reviewer_batch_launch --validate ...",
        "intake_directory": "outputs/reviewer_batch/reviewer_prod_cand_001/intake",
        "operator_launch_checklist": {"steps": ["distribute", "collect"], "dry_run": False},
        "reviewer_instruction_ready": True,
        "production_gold_count": 0,
        "current_r1_gap": 200,
        "production_candidate_status": "production_batch_frozen",
    }


def _blocked_pcand():
    return {
        "production_candidate_batch_ready": False,
        "production_candidate_status": "blocked_no_publishable_pairs",
        "production_gold_count": 0,
        "current_r1_gap": 200,
    }


def test_no_freeze_blocks_handoff_with_blocker():
    out = build_reviewer_handoff_bridge(_blocked_pcand())
    assert out["reviewer_handoff_ready"] is False
    assert out["handoff_package"] is None
    assert out["blocked_reason"] == "blocked_no_publishable_pairs"
    assert out["actual_sending_performed"] is False


def test_empty_pcand_blocks_with_no_freeze_reason():
    out = build_reviewer_handoff_bridge({})
    assert out["reviewer_handoff_ready"] is False
    assert out["blocked_reason"] == HANDOFF_BLOCKED_NO_FREEZE


def test_live_run_status_overrides_blocked_reason():
    # §5 live status 가 더 구체적이면 그것을 blocked_reason 으로(operator 안내 정확).
    out = build_reviewer_handoff_bridge(_blocked_pcand(), live_run_status="live_no_routing_candidates")
    assert out["reviewer_handoff_ready"] is False
    assert out["blocked_reason"] == "live_no_routing_candidates"


def test_freeze_makes_handoff_ready_with_package():
    out = build_reviewer_handoff_bridge(_frozen_pcand())
    assert out["reviewer_handoff_ready"] is True
    pkg = out["handoff_package"]
    assert pkg is not None
    assert pkg["batch_id"] == "reviewer_prod_cand_001"
    assert pkg["frozen_pair_count"] == 3
    assert pkg["candidate_provenance"] == "live_derived"
    assert len(pkg["expected_label_files"]) == 2
    assert pkg["validation_command"]
    assert pkg["placement_guide"]
    assert pkg["reviewers_per_pair_minimum"] == 2
    assert out["expected_label_files_ready"] is True
    assert out["validation_command_ready"] is True
    assert out["placement_guide_ready"] is True


def test_freeze_does_not_send_or_increase_gold():
    out = build_reviewer_handoff_bridge(_frozen_pcand())
    assert out["actual_sending_performed"] is False        # 자동 전송 0(operator 수동 배포).
    assert out["freeze_is_reviewer_worklist_only"] is True  # freeze ≠ truth ≠ gold.
    assert out["production_gold_count"] == 0                # gold 미증가.
    assert out["merge_allowed"] is False


def test_ready_fails_closed_without_batch_id_or_pairs():
    # production_candidate_batch_ready=True 선언만으로 ready 둔갑 금지 — batch_id ∧ frozen_pair_count>0 필요.
    no_id = {**_frozen_pcand(), "production_batch_id": ""}
    assert build_reviewer_handoff_bridge(no_id)["reviewer_handoff_ready"] is False
    no_pairs = {**_frozen_pcand(), "production_frozen_pair_count": 0}
    assert build_reviewer_handoff_bridge(no_pairs)["reviewer_handoff_ready"] is False


def test_output_has_no_forbidden_fields_ready_and_blocked():
    for pcand in (_frozen_pcand(), _blocked_pcand()):
        out = build_reviewer_handoff_bridge(pcand)
        blob = repr(out)
        for f in _FORBIDDEN:
            assert f not in out, f"forbidden top-level key {f}"
        # 중첩(handoff_package)에도 forbidden EXACT key 없음(_assert_pii_safe 가 build 시 이미 강제).
        pkg = out.get("handoff_package") or {}
        for f in _FORBIDDEN:
            assert f not in pkg
        # reviewer raw PII(email)은 직렬화 어디에도 없음(boundary flag 키는 *_exposed 형태라 exact-key 가드가 담당).
        assert "@" not in blob


def test_pii_in_checklist_is_rejected_fail_loud():
    # operator_launch_checklist 에 forbidden key 가 끼면 _assert_pii_safe 가 build 시 fail-loud(드리프트 차단).
    poisoned = {**_frozen_pcand(), "operator_launch_checklist": {"reviewer_name": "should not pass"}}
    with pytest.raises(ValueError):
        build_reviewer_handoff_bridge(poisoned)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
