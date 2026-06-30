"""ADR#93 §20 #34-#41 — freeze→R1 executable checklist tests.

검증: no freeze → 차단(checklist 미준비) · safe freeze → FR1_READY · batch_id 가 dropbox/validation/intake 전반 일관 ·
validation/intake 명령 shape · agreement_check == intake(intake run 안에서 합의 수행) · actual sending 0 ·
real returned label 없으면 production_gold_count 불변(0) · freeze 가 다른 배치 id 면 mismatch 차단.
"""
from __future__ import annotations

from backend.app.tools.first_freeze_package_hardening import FH_SAFE
from backend.app.tools.freeze_to_r1_executable_checklist import (
    FR1_BLOCKED_BATCH_MISMATCH,
    FR1_BLOCKED_NO_FREEZE,
    FR1_BLOCKED_UNSAFE_ARTIFACT,
    FR1_READY,
    build_freeze_to_r1_executable_checklist,
    sanitized_freeze_to_r1_executable_checklist,
)
from backend.app.tools.r1_label_return_operational_bridge import DEFAULT_BATCH_ID

_REQUIRED_KEYS = {
    "operation_name", "freeze_to_r1_status", "batch_id", "freeze_batch_id", "batch_id_mismatch",
    "candidate_count", "freeze_package_hardening_status", "freeze_artifact_safe",
    "reviewer_contact_checklist_ready", "manual_contact_steps", "dropbox_path",
    "expected_returned_file_pattern", "label_validation_command", "label_intake_command",
    "agreement_check_command", "agreement_performed_by_intake_run", "gold_promotion_gate_status",
    "actual_sending_performed", "production_gold_count", "next_action",
}


def _safe_pair() -> dict:
    """hardening 통과 freeze artifact(official/news record 는 source_role+canonical_url+published_at+title 만)."""
    return {
        "pair_id": "oxn_0001",
        "official_record": {
            "record_type": "official_document",
            "source_id": "federal_register",
            "canonical_url": "https://www.federalregister.gov/documents/2026/06/25/epa-rule",
            "published_at_or_observed_at": "2026-06-25",
            "title_or_label": "EPA final rule on greenhouse gas emissions standards",
        },
        "news_record": {
            "record_type": "news_article",
            "source_id": "guardian",
            "canonical_url": "https://www.theguardian.com/environment/2026/jun/25/epa-emissions",
            "published_at_or_observed_at": "2026-06-25",
            "title_or_label": "EPA tightens vehicle emissions standards",
        },
        "shared_tokens": ["epa", "emissions"],
        "date_proximity_days": 0,
    }


# ── 34. no freeze → checklist blocked ──
def test_no_freeze_blocks_checklist():
    out = build_freeze_to_r1_executable_checklist(freeze_artifact=None)
    assert out["freeze_to_r1_status"] == FR1_BLOCKED_NO_FREEZE
    assert out["reviewer_contact_checklist_ready"] is False
    assert out["freeze_artifact_safe"] is False
    assert out["candidate_count"] == 0
    assert "no production-candidate freeze" in out["next_action"].lower()


# ── 35. safe freeze → checklist ready ──
def test_safe_freeze_makes_checklist_ready():
    out = build_freeze_to_r1_executable_checklist(freeze_artifact=_safe_pair())
    assert out["freeze_to_r1_status"] == FR1_READY
    assert out["freeze_package_hardening_status"] == FH_SAFE
    assert out["freeze_artifact_safe"] is True
    assert out["reviewer_contact_checklist_ready"] is True
    assert out["candidate_count"] == 1
    assert out["batch_id_mismatch"] is False
    assert out["manual_contact_steps"]  # non-empty contact steps present.


# ── 36. batch_id consistent across checklist / dropbox / intake fields ──
def test_batch_id_consistent_across_fields():
    out = build_freeze_to_r1_executable_checklist(freeze_artifact=_safe_pair())
    assert out["batch_id"] == DEFAULT_BATCH_ID
    assert DEFAULT_BATCH_ID in out["dropbox_path"]
    assert DEFAULT_BATCH_ID in out["label_validation_command"]
    assert DEFAULT_BATCH_ID in out["label_intake_command"]
    # intake command points at the same dropbox directory the labels are returned to.
    assert out["dropbox_path"] in out["label_intake_command"]


# ── 37. label_validation_command present + correct shape ──
def test_label_validation_command_shape():
    out = build_freeze_to_r1_executable_checklist(freeze_artifact=_safe_pair())
    cmd = out["label_validation_command"]
    assert cmd.strip()
    assert "backend.app.tools.reviewer_batch_launch" in cmd
    assert "--validate" in cmd
    assert f"--batch-id {DEFAULT_BATCH_ID}" in cmd


# ── 38. label_intake_command present + correct shape ──
def test_label_intake_command_shape():
    out = build_freeze_to_r1_executable_checklist(freeze_artifact=_safe_pair())
    cmd = out["label_intake_command"]
    assert cmd.strip()
    assert "backend.app.tools.r1_gold_acquisition_plan" in cmd
    assert f"--batch-id {DEFAULT_BATCH_ID}" in cmd
    assert "--input-dir" in cmd
    assert "--json" in cmd


# ── 39. agreement_check_command == intake command + performed inside the intake run ──
def test_agreement_check_command_is_intake_run():
    out = build_freeze_to_r1_executable_checklist(freeze_artifact=_safe_pair())
    assert out["agreement_check_command"] == out["label_intake_command"]
    assert out["agreement_performed_by_intake_run"] is True


# ── 40. actual sending never performed ──
def test_actual_sending_not_performed():
    assert build_freeze_to_r1_executable_checklist(freeze_artifact=_safe_pair())["actual_sending_performed"] is False
    assert build_freeze_to_r1_executable_checklist(freeze_artifact=None)["actual_sending_performed"] is False


# ── 41. production_gold_count unchanged (0) without real returned labels ──
def test_production_gold_count_zero_without_labels():
    out = build_freeze_to_r1_executable_checklist(freeze_artifact=_safe_pair())
    assert out["production_gold_count"] == 0
    assert out["actual_returned_label_count"] == 0
    assert out["gold_promotion_gate_status"] == "awaiting_returned_labels"


# ── batch mismatch: freeze carries a different batch id → blocked ──
def test_freeze_batch_mismatch_blocks():
    art = _safe_pair()
    art["batch_id"] = "reviewer_prod_cand_001"   # FREEZE side PROD_BATCH_ID != contact DEFAULT_BATCH_ID.
    out = build_freeze_to_r1_executable_checklist(freeze_artifact=art)
    assert out["batch_id_mismatch"] is True
    assert out["freeze_batch_id"] == "reviewer_prod_cand_001"
    assert out["freeze_to_r1_status"] == FR1_BLOCKED_BATCH_MISMATCH
    assert out["reviewer_contact_checklist_ready"] is False
    # contact lane is still threaded on DEFAULT_BATCH_ID (not the freeze batch).
    assert out["batch_id"] == DEFAULT_BATCH_ID
    assert DEFAULT_BATCH_ID in out["label_intake_command"]


def test_matching_batch_id_is_not_mismatch():
    art = _safe_pair()
    art["batch_id"] = DEFAULT_BATCH_ID
    out = build_freeze_to_r1_executable_checklist(freeze_artifact=art)
    assert out["batch_id_mismatch"] is False
    assert out["freeze_to_r1_status"] == FR1_READY


# ── unsafe artifact (forbidden key leaked) → blocked ──
def test_unsafe_artifact_blocks():
    art = _safe_pair()
    art["official_record"]["score"] = 0.97   # forbidden key → hardening unsafe.
    out = build_freeze_to_r1_executable_checklist(freeze_artifact=art)
    assert out["freeze_artifact_safe"] is False
    assert out["freeze_to_r1_status"] == FR1_BLOCKED_UNSAFE_ARTIFACT
    assert out["reviewer_contact_checklist_ready"] is False


# ── unsafe takes priority over batch mismatch ──
def test_unsafe_priority_over_batch_mismatch():
    art = _safe_pair()
    art["batch_id"] = "reviewer_prod_cand_001"
    art["news_record"]["rationale"] = "same event"   # forbidden → unsafe.
    out = build_freeze_to_r1_executable_checklist(freeze_artifact=art)
    assert out["freeze_to_r1_status"] == FR1_BLOCKED_UNSAFE_ARTIFACT


# ── production_gold_count is bridge passthrough, not local: gold count args don't inflate it ──
def test_gold_count_args_do_not_inflate_production_gold():
    # before==after keeps hardening safe; production_gold_count still comes from the (empty) bridge dropbox.
    out = build_freeze_to_r1_executable_checklist(
        freeze_artifact=_safe_pair(), production_gold_count_before=3, production_gold_count_after=3)
    assert out["freeze_artifact_safe"] is True
    assert out["production_gold_count"] == 0


# ── honesty invariants (hardcoded constants) ──
def test_honesty_invariants():
    out = build_freeze_to_r1_executable_checklist(freeze_artifact=_safe_pair())
    assert out["actual_sending_performed"] is False
    assert out["reviewer_roster_committed"] is False
    assert out["single_reviewer_label_is_gold"] is False
    assert out["unsure_label_is_gold"] is False
    assert out["agreement_required_for_gold"] is True
    assert out["gold_promotion_gated"] is True
    assert out["same_event_asserted"] is False
    assert out["merge_allowed"] is False


# ── all required output keys present ──
def test_required_output_keys_present():
    out = build_freeze_to_r1_executable_checklist(freeze_artifact=_safe_pair())
    assert _REQUIRED_KEYS <= set(out)


# ── sanitized projection: status/flags/count/next_action only, no command strings ──
def test_sanitized_projection_keys():
    out = build_freeze_to_r1_executable_checklist(freeze_artifact=_safe_pair())
    s = sanitized_freeze_to_r1_executable_checklist(out)
    assert set(s.keys()) == {
        "freeze_to_r1_status", "freeze_artifact_safe", "reviewer_contact_checklist_ready",
        "batch_id_mismatch", "actual_sending_performed", "agreement_required_for_gold",
        "gold_promotion_gated", "merge_allowed", "same_event_asserted",
        "production_gold_count", "next_action",
    }
    # no command strings / raw records leak into the sanitized projection.
    assert "label_intake_command" not in s
    assert "label_validation_command" not in s
    assert "manual_contact_steps" not in s
    assert "dropbox_path" not in s
