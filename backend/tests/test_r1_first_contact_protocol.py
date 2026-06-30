"""ADR#92 §12 — R1 reviewer first-contact protocol tests.

검증: 8단계 모두 존재·어떤 단계도 발송 0·reviewer roster 미커밋·manual contact 는 수동 only·dropbox gitignored·
validation/intake command 존재·single/unsure 는 gold 아님·agreement gate 필수·gold 승격 gated.
"""
from __future__ import annotations

from backend.app.tools.r1_first_contact_protocol import (
    FC_DEFINED_AWAITING_FREEZE,
    FC_DEFINED_FREEZE_READY,
    STAGE_IDS,
    build_r1_first_contact_protocol,
    sanitized_r1_first_contact_protocol,
)

_STAGE_FIELDS = {
    "stage", "entry_condition", "allowed_action", "forbidden_action",
    "artifact_path", "privacy_rule", "next_command",
}


# ── 40. all stages present ──
def test_all_stages_present():
    out = build_r1_first_contact_protocol()
    assert out["stage_count"] == 8
    ids = [s["stage"] for s in out["protocol_stages"]]
    assert ids == list(STAGE_IDS)
    assert out["stage_order"] == list(STAGE_IDS)
    for s in out["protocol_stages"]:
        assert set(s.keys()) == _STAGE_FIELDS


# ── 41. no stage performs sending ──
def test_no_stage_performs_sending():
    out = build_r1_first_contact_protocol()
    assert out["actual_sending_performed"] is False
    contact = next(s for s in out["protocol_stages"] if s["stage"] == "stage_2_manual_contact")
    assert "no system sending" in contact["forbidden_action"].lower()


# ── 42. reviewer roster not committed ──
def test_reviewer_roster_not_committed():
    out = build_r1_first_contact_protocol()
    assert out["reviewer_roster_committed"] is False
    select = next(s for s in out["protocol_stages"] if s["stage"] == "stage_1_select_reviewer_outside_git")
    assert "do not commit the reviewer roster" in select["forbidden_action"].lower()
    assert "outside git" in select["allowed_action"].lower()


# ── 43. manual contact stage is manual only ──
def test_manual_contact_is_manual_only():
    out = build_r1_first_contact_protocol()
    contact = next(s for s in out["protocol_stages"] if s["stage"] == "stage_2_manual_contact")
    assert "manual" in contact["allowed_action"].lower()
    assert contact["next_command"] == ""


# ── 44. returned label dropbox path gitignored ──
def test_dropbox_path_gitignored():
    out = build_r1_first_contact_protocol()
    assert out["dropbox_gitignored"] is True
    ret = next(s for s in out["protocol_stages"] if s["stage"] == "stage_3_return_label_to_dropbox")
    assert "gitignored" in ret["privacy_rule"].lower()
    assert "outputs/reviewer_batch" in out["dropbox_path"]


# ── 45. validation command present ──
def test_validation_command_present():
    out = build_r1_first_contact_protocol()
    assert out["validation_command"].strip()
    validate = next(s for s in out["protocol_stages"] if s["stage"] == "stage_4_validate_returned_label")
    assert validate["next_command"] == out["validation_command"]


# ── 46. intake command present ──
def test_intake_command_present():
    out = build_r1_first_contact_protocol()
    assert "r1_gold_acquisition_plan" in out["intake_command"]
    intake = next(s for s in out["protocol_stages"] if s["stage"] == "stage_5_intake_to_r1_candidate")
    assert intake["next_command"] == out["intake_command"]


# ── 47./48. single / unsure label not gold ──
def test_single_and_unsure_not_gold():
    out = build_r1_first_contact_protocol()
    assert out["single_reviewer_label_is_gold"] is False
    assert out["unsure_label_is_gold"] is False
    intake = next(s for s in out["protocol_stages"] if s["stage"] == "stage_5_intake_to_r1_candidate")
    assert "single-reviewer" in intake["forbidden_action"].lower()
    assert "unsure" in intake["forbidden_action"].lower()


# ── 49. agreement gate required + gold promotion gated ──
def test_agreement_gate_required_and_gold_gated():
    out = build_r1_first_contact_protocol()
    assert out["agreement_required_for_gold"] is True
    assert out["gold_promotion_gated"] is True
    agree = next(s for s in out["protocol_stages"] if s["stage"] == "stage_6_agreement_check")
    assert "agreement" in agree["allowed_action"].lower()
    assert "no auto-majority" in agree["forbidden_action"].lower()
    promote = next(s for s in out["protocol_stages"] if s["stage"] == "stage_7_gold_promotion_gate")
    assert "explicit gate" in promote["allowed_action"].lower()


# ── status reflects freeze readiness ──
def test_status_awaiting_freeze_by_default():
    out = build_r1_first_contact_protocol()
    assert out["r1_first_contact_protocol_status"] == FC_DEFINED_AWAITING_FREEZE
    assert "no production-candidate freeze" in out["r1_first_contact_next_action"].lower()


def test_status_freeze_ready_when_flagged():
    out = build_r1_first_contact_protocol(freeze_ready=True)
    assert out["r1_first_contact_protocol_status"] == FC_DEFINED_FREEZE_READY


# ── invariants ──
def test_invariants():
    out = build_r1_first_contact_protocol()
    assert out["production_gold_count"] == 0
    assert out["merge_allowed"] is False
    assert out["same_event_asserted"] is False
    assert out["r2_r7_no_go"] is True


# ── sanitized projection (frontier 용) ──
def test_sanitized_projection_keys():
    out = build_r1_first_contact_protocol()
    s = sanitized_r1_first_contact_protocol(out)
    assert set(s.keys()) == {
        "r1_first_contact_protocol_status", "stage_count", "actual_sending_performed",
        "reviewer_roster_committed", "gold_promotion_gated", "r1_first_contact_next_action",
    }
