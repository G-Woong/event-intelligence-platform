"""ADR#91 §12 — r1_label_return_operational_bridge 테스트(intake_command 신규·승격 상태·gold 0 유지·synthetic/single/unsure 미승격).

dropbox_readiness/gold_plan 주입으로 승격 분기를 결정론 검증. 실 합성 경로(미주입)는 outputs/reviewer_batch 부재라 awaiting 으로 수렴."""
from __future__ import annotations

from backend.app.tools.r1_gold_acquisition_plan import (
    R1_BLOCKED_NO_LABELS,
    R1_COLLECTING,
    R1_SATISFIED,
)
from backend.app.tools.r1_label_return_operational_bridge import (
    GP_AWAITING_LABELS,
    GP_FLOOR_SATISFIED,
    GP_LABELS_NO_GOLD,
    RETURN_AWAITING,
    RETURN_COLLECTING,
    RETURN_ELIGIBLE,
    build_r1_label_return_operational_bridge,
    sanitized_r1_label_return,
)


def _dropbox(actual: int = 0, **over) -> dict:
    d = {
        "dropbox_path": "outputs/reviewer_batch/operator_regulatory_live",
        "dropbox_gitignored": True,
        "returned_label_glob": "*.jsonl",
        "expected_returned_files_example": ["operator_regulatory_live__rv01__labels.jsonl"],
        "actual_returned_label_count": actual,
        "validation_command": ".venv/Scripts/python.exe -m backend.app.tools.reviewer_batch_launch --validate ...",
        "synthetic_fixture_counted_as_gold": False,
        "single_reviewer_label_is_gold": False,
        "unsure_label_is_gold": False,
        "agreement_required_for_gold": True,
    }
    d.update(over)
    return d


def _gold(prod: int = 0, r1_status: str = R1_BLOCKED_NO_LABELS, gap: int = 200, block_reasons=None) -> dict:
    return {
        "production_gold_count": prod,
        "r1_status": r1_status,
        "label_collection_gap": gap,
        "block_reasons": list(block_reasons or ["r1_blocked_no_actual_returned_labels"]),
    }


# ── no labels → awaiting · production gold 0 · blocker no_returned_labels ─────────────────────────────────────
def test_no_labels_awaiting():
    out = build_r1_label_return_operational_bridge(dropbox_readiness=_dropbox(0), gold_plan=_gold())
    assert out["r1_label_return_status"] == RETURN_AWAITING
    assert out["gold_promotion_status"] == GP_AWAITING_LABELS
    assert out["actual_returned_label_count"] == 0
    assert out["production_gold_count"] == 0
    assert "no_returned_labels" in out["gold_promotion_blockers"]


# ── §19-53: emits validation command ────────────────────────────────────────────────────────────────────────
def test_53_emits_validation_command():
    out = build_r1_label_return_operational_bridge(dropbox_readiness=_dropbox(0), gold_plan=_gold())
    assert out["validation_command"]
    assert "reviewer_batch_launch" in out["validation_command"]


# ── §19-54: emits intake command(신규 표면) ──────────────────────────────────────────────────────────────────
def test_54_emits_intake_command():
    out = build_r1_label_return_operational_bridge(dropbox_readiness=_dropbox(0), gold_plan=_gold())
    assert out["intake_command"]
    assert "r1_gold_acquisition_plan" in out["intake_command"]
    assert "--input-dir" in out["intake_command"]
    assert "outputs/reviewer_batch/operator_regulatory_live" in out["intake_command"]


# ── §19-49: actual_returned_label_count = 실 파일 count passthrough ───────────────────────────────────────────
def test_49_actual_count_passthrough():
    out = build_r1_label_return_operational_bridge(
        dropbox_readiness=_dropbox(3), gold_plan=_gold(prod=0, r1_status=R1_COLLECTING))
    assert out["actual_returned_label_count"] == 3
    # 실 파일이 있어도 decisive 합의 gold 없으면 production gold 0.
    assert out["production_gold_count"] == 0


# ── §19-50: synthetic fixture not counted as gold(passthrough) ───────────────────────────────────────────────
def test_50_synthetic_not_counted():
    out = build_r1_label_return_operational_bridge(
        dropbox_readiness=_dropbox(2, synthetic_fixture_counted_as_gold=False), gold_plan=_gold(prod=0))
    assert out["synthetic_fixture_counted_as_gold"] is False
    assert out["production_gold_count"] == 0


# ── §19-51: single reviewer label not gold ──────────────────────────────────────────────────────────────────
def test_51_single_reviewer_not_gold():
    out = build_r1_label_return_operational_bridge(dropbox_readiness=_dropbox(0), gold_plan=_gold())
    assert out["single_reviewer_label_is_gold"] is False


# ── §19-52: unsure/needs_more_context not gold ──────────────────────────────────────────────────────────────
def test_52_unsure_not_gold():
    out = build_r1_label_return_operational_bridge(dropbox_readiness=_dropbox(0), gold_plan=_gold())
    assert out["unsure_label_is_gold"] is False


# ── §19-55: no gold without agreement ───────────────────────────────────────────────────────────────────────
def test_55_no_gold_without_agreement():
    out = build_r1_label_return_operational_bridge(
        dropbox_readiness=_dropbox(5), gold_plan=_gold(prod=0, r1_status=R1_COLLECTING))
    assert out["agreement_required_for_gold"] is True
    assert out["production_gold_count"] == 0
    assert out["gold_promotion_status"] == GP_LABELS_NO_GOLD
    assert "no_decisive_two_reviewer_gold" in out["gold_promotion_blockers"]


# ── decisive multi-reviewer agreement → eligible but still gate-controlled(merge 0) ──────────────────────────
def test_floor_satisfied_eligible_but_gate_controlled():
    out = build_r1_label_return_operational_bridge(
        dropbox_readiness=_dropbox(220), gold_plan=_gold(prod=200, r1_status=R1_SATISFIED, gap=0))
    assert out["r1_label_return_status"] == RETURN_ELIGIBLE
    assert out["gold_promotion_status"] == GP_FLOOR_SATISFIED
    # eligible 이어도 자동 merge 0(gate-controlled).
    assert out["merge_allowed"] is False
    assert out["r2_r7_no_go"] is True


# ── labels present no gold → collecting ──────────────────────────────────────────────────────────────────────
def test_labels_present_no_gold_collecting():
    out = build_r1_label_return_operational_bridge(
        dropbox_readiness=_dropbox(4), gold_plan=_gold(prod=0, r1_status=R1_COLLECTING))
    assert out["r1_label_return_status"] == RETURN_COLLECTING
    assert out["gold_promotion_status"] == GP_LABELS_NO_GOLD


# ── 실 합성 경로(미주입) → outputs/reviewer_batch 부재라 awaiting · gold 0 ─────────────────────────────────────
def test_real_composition_awaiting_when_absent():
    out = build_r1_label_return_operational_bridge()
    assert out["actual_returned_label_count"] == 0
    assert out["gold_promotion_status"] == GP_AWAITING_LABELS
    assert out["production_gold_count"] == 0
    assert out["merge_allowed"] is False


# ── sanitized 투영(명령 제외·status/count 만) ────────────────────────────────────────────────────────────────
def test_sanitized_projection():
    out = build_r1_label_return_operational_bridge(dropbox_readiness=_dropbox(0), gold_plan=_gold())
    s = sanitized_r1_label_return(out)
    assert set(s) == {"r1_label_return_status", "gold_promotion_status", "actual_returned_label_count",
                      "production_gold_count", "r1_label_return_next_action"}
    assert "intake_command" not in s
