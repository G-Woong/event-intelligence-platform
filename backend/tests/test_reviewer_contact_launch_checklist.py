"""ADR#89 §19(37~45) — reviewer contact launch checklist(freeze→수동 접촉 직전·launch_ready ≠ sending·roster/PII 미커밋).
contact_readiness/dropbox_readiness 주입으로 결정론 검증(network 0)."""
from __future__ import annotations

from backend.app.tools.reviewer_contact_launch_checklist import (
    LAUNCH_BLOCKED_NO_FREEZE,
    LAUNCH_READY,
    build_reviewer_contact_launch_checklist,
    sanitized_launch_checklist,
)
from backend.app.tools.reviewer_handoff_bridge import build_reviewer_handoff_bridge

_READY_CONTACT = {
    "reviewer_contact_ready": True, "instruction_ready": True, "label_schema_ready": True,
    "expected_label_files_ready": True, "validation_command_ready": True, "placement_guide_ready": True,
    "production_batch_id": "oxn_b1", "candidate_count": 2, "blocked_reason": "",
}
_READY_DROPBOX = {
    "label_dropbox_ready": True, "validation_command_ready": True,
    "actual_returned_label_count": 0, "production_gold_count": 0,
}
_NO_FREEZE_CONTACT = {
    "reviewer_contact_ready": False, "blocked_reason": "blocked_no_production_candidate_freeze",
}


# ── §19-37: freeze success → contact checklist ready ───────────────────────────────────────────────────────
def test_37_freeze_success_launch_ready():
    out = build_reviewer_contact_launch_checklist(
        contact_readiness=_READY_CONTACT, dropbox_readiness=_READY_DROPBOX)
    assert out["reviewer_contact_launch_status"] == LAUNCH_READY
    assert out["reviewer_contact_launch_ready"] is True
    assert out["label_dropbox_ready"] is True
    assert out["blocked_reason"] == ""


# ── §19-38: freeze failure → checklist false ───────────────────────────────────────────────────────────────
def test_38_freeze_failure_launch_not_ready():
    out = build_reviewer_contact_launch_checklist(
        contact_readiness=_NO_FREEZE_CONTACT, dropbox_readiness=_READY_DROPBOX)
    assert out["reviewer_contact_launch_status"] == LAUNCH_BLOCKED_NO_FREEZE
    assert out["reviewer_contact_launch_ready"] is False
    assert out["blocked_reason"] == "blocked_no_production_candidate_freeze"


# ── 추가: dropbox not ready 도 launch 차단(둘 다 필요) ──────────────────────────────────────────────────────
def test_dropbox_not_ready_blocks_launch():
    out = build_reviewer_contact_launch_checklist(
        contact_readiness=_READY_CONTACT, dropbox_readiness={"label_dropbox_ready": False})
    assert out["reviewer_contact_launch_ready"] is False


# ── §19-39: manual contact steps ready ─────────────────────────────────────────────────────────────────────
def test_39_manual_contact_steps_ready():
    out = build_reviewer_contact_launch_checklist(
        contact_readiness=_READY_CONTACT, dropbox_readiness=_READY_DROPBOX)
    assert out["manual_contact_steps_ready"] is True
    assert len(out["manual_contact_steps"]) >= 5


# ── §19-40: reviewer roster required but not committed ─────────────────────────────────────────────────────
def test_40_reviewer_roster_required_not_committed():
    out = build_reviewer_contact_launch_checklist(
        contact_readiness=_READY_CONTACT, dropbox_readiness=_READY_DROPBOX)
    assert out["reviewer_roster_required_but_not_committed"] is True
    assert out["reviewer_roster_included"] is False


# ── §19-41: no actual email address in committed artifact ──────────────────────────────────────────────────
def test_41_no_actual_email():
    out = build_reviewer_contact_launch_checklist(
        contact_readiness=_READY_CONTACT, dropbox_readiness=_READY_DROPBOX)
    assert out["actual_email_included"] is False


# ── §19-42: no PII (recursive guard passes — output construction itself enforces) ──────────────────────────
def test_42_no_pii_guard_passes():
    # build_* 가 _assert_pii_safe 를 통과해야 반환됨(forbidden 키 있으면 ValueError). 반환되면 통과.
    out = build_reviewer_contact_launch_checklist(
        contact_readiness=_READY_CONTACT, dropbox_readiness=_READY_DROPBOX)
    assert "score" not in out and "rationale" not in out and "email" not in out


# ── §19-43: no same_event truth ────────────────────────────────────────────────────────────────────────────
def test_43_no_same_event_truth():
    out = build_reviewer_contact_launch_checklist(
        contact_readiness=_READY_CONTACT, dropbox_readiness=_READY_DROPBOX)
    assert out["same_event_truth_hidden"] is True


# ── §19-44: no score/rationale/predicted_status ────────────────────────────────────────────────────────────
def test_44_no_score_rationale_predicted():
    out = build_reviewer_contact_launch_checklist(
        contact_readiness=_READY_CONTACT, dropbox_readiness=_READY_DROPBOX)
    assert out["score_hidden"] is True
    assert out["rationale_hidden"] is True
    assert out["predicted_status_hidden"] is True
    assert out["raw_body_hidden"] is True


# ── §19-45: actual sending false ───────────────────────────────────────────────────────────────────────────
def test_45_actual_sending_false():
    ready = build_reviewer_contact_launch_checklist(
        contact_readiness=_READY_CONTACT, dropbox_readiness=_READY_DROPBOX)
    blocked = build_reviewer_contact_launch_checklist(
        contact_readiness=_NO_FREEZE_CONTACT, dropbox_readiness=_READY_DROPBOX)
    assert ready["actual_sending_performed"] is False
    assert blocked["actual_sending_performed"] is False


# ── 추가: 빈 handoff(freeze 없음) → launch 차단·sending 0(real handoff 경로) ────────────────────────────────
def test_empty_handoff_blocks_launch():
    out = build_reviewer_contact_launch_checklist({})
    assert out["reviewer_contact_launch_ready"] is False
    assert out["actual_sending_performed"] is False
    assert out["production_gold_count"] == 0


# ── 추가: real handoff(freeze ready) 통합 — handoff bridge → contact readiness → launch checklist ───────────
def test_real_handoff_integration_launch_ready():
    pcand = {
        "production_candidate_batch_ready": True, "production_batch_id": "oxn_b1",
        "production_frozen_pair_count": 2, "candidate_provenance": "live_official_news",
        "production_gold_count": 0, "current_r1_gap": 200,
    }
    handoff = build_reviewer_handoff_bridge(pcand)
    assert handoff["reviewer_handoff_ready"] is True
    out = build_reviewer_contact_launch_checklist(handoff)   # dropbox readiness 는 실제 synthetic dry-run.
    assert out["reviewer_contact_launch_ready"] is True
    assert out["actual_sending_performed"] is False
    assert out["production_gold_count"] == 0


# ── 추가: sanitized 투영 ────────────────────────────────────────────────────────────────────────────────────
def test_sanitized_projection():
    out = build_reviewer_contact_launch_checklist(
        contact_readiness=_READY_CONTACT, dropbox_readiness=_READY_DROPBOX)
    s = sanitized_launch_checklist(out)
    assert set(s) == {"reviewer_contact_launch_status", "reviewer_contact_launch_ready", "label_dropbox_ready",
                      "actual_sending_performed", "blocked_reason", "next_action"}
