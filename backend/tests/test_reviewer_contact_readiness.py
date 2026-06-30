"""ADR#88 — reviewer_contact_readiness tests (§19 42~54 · freeze→contact-PRE · 전송 0 · network 0)."""
from __future__ import annotations

from backend.app.tools.reviewer_contact_readiness import (
    CONTACT_READINESS_BLOCKED_NO_FREEZE,
    CONTACT_READINESS_READY,
    build_official_news_label_schema,
    build_reviewer_contact_readiness,
    sanitized_contact_readiness,
)
from backend.app.tools.reviewer_handoff_bridge import build_reviewer_handoff_bridge


def _frozen_pcand() -> dict:
    """freeze 성공 pcand 대역(run_r1_production_candidate_acquisition 출력 형태·live_derived)."""
    return {
        "production_candidate_batch_ready": True,
        "production_batch_id": "prod_batch_x",
        "production_batch_signature": "sig123",
        "production_frozen_pair_count": 1,
        "candidate_provenance": "live_derived",
        "reviewer_instruction_ready": True,
        "expected_label_files": [
            "prod_batch_x__rv_a__labels.jsonl", "prod_batch_x__rv_b__labels.jsonl"],
        "validation_command": (
            ".\\.venv\\Scripts\\python.exe -m backend.app.tools.reviewer_batch_launch "
            "--validate outputs/reviewer_batch/prod_batch_x/intake --batch-id prod_batch_x"),
        "intake_directory": "outputs/reviewer_batch/prod_batch_x/intake",
        "operator_launch_checklist": ["recruit >=2 reviewers", "distribute pack"],
        "production_gold_count": 0,
        "current_r1_gap": 200,
    }


def _ready_contact() -> dict:
    return build_reviewer_contact_readiness(build_reviewer_handoff_bridge(_frozen_pcand()))


def _blocked_contact() -> dict:
    # freeze 없음(빈 pcand) → handoff not ready → contact not ready.
    return build_reviewer_contact_readiness(
        build_reviewer_handoff_bridge({}, live_run_status="no_official_news_overlap"))


# ── §19-42: freeze success → contact readiness package ready ─────────────────────────────────────────────
def test_42_freeze_success_package_ready():
    out = _ready_contact()
    assert out["reviewer_contact_readiness_status"] == CONTACT_READINESS_READY
    assert out["reviewer_contact_ready"] is True
    pkg = out["contact_readiness_package"]
    assert pkg is not None
    assert pkg["batch_id"] == "prod_batch_x"
    assert pkg["candidate_count"] == 1
    assert "manual_contact_steps" in pkg and pkg["manual_contact_steps"]


# ── §19-43: freeze failure → contact readiness false ────────────────────────────────────────────────────
def test_43_freeze_failure_not_ready():
    out = _blocked_contact()
    assert out["reviewer_contact_readiness_status"] == CONTACT_READINESS_BLOCKED_NO_FREEZE
    assert out["reviewer_contact_ready"] is False
    assert out["contact_readiness_package"] is None
    assert out["blocked_reason"] == "no_official_news_overlap"


# ── §19-44~49: readiness sub-flags ──────────────────────────────────────────────────────────────────────
def test_44_instruction_ready():
    out = _ready_contact()
    assert out["instruction_ready"] is True
    instr = out["contact_readiness_package"]["official_news_label_instructions"]
    # official=evidence / news=reporting role 명시(news×news 와 다름).
    assert "authoritative evidence" in instr["official_source_role"].lower()
    assert "public reporting" in instr["news_source_role"].lower()


def test_45_label_schema_ready():
    out = _ready_contact()
    assert out["label_schema_ready"] is True
    schema = out["contact_readiness_package"]["label_schema"]
    assert "same_event" in schema["accepted_labels"]
    assert "different_event" in schema["accepted_labels"]
    # role_fields 가 official×news 를 구분.
    assert schema["role_fields"] == ["source_type_left", "source_type_right"]


def test_46_expected_label_files_ready():
    out = _ready_contact()
    assert out["expected_label_files_ready"] is True
    assert out["contact_readiness_package"]["expected_returned_file_names"] == [
        "prod_batch_x__rv_a__labels.jsonl", "prod_batch_x__rv_b__labels.jsonl"]


def test_47_validation_command_ready():
    out = _ready_contact()
    assert out["validation_command_ready"] is True
    assert "--validate" in out["contact_readiness_package"]["validation_command"]


def test_48_placement_guide_ready():
    out = _ready_contact()
    assert out["placement_guide_ready"] is True
    assert out["contact_readiness_package"]["placement_guide"]


def test_49_operator_checklist_ready():
    out = _ready_contact()
    assert out["operator_checklist_ready"] is True
    assert out["contact_readiness_package"]["operator_checklist"]


# ── §19-50: no reviewer roster ──────────────────────────────────────────────────────────────────────────
def test_50_no_reviewer_roster():
    out = _ready_contact()
    assert out["reviewer_roster_included"] is False
    assert out["actual_email_included"] is False


# ── §19-51: no raw PII (recursive guard would have raised) ──────────────────────────────────────────────
def test_51_no_raw_pii():
    out = _ready_contact()
    assert out["pii_safe"] is True
    # 출력 어디에도 forbidden 정확명(email/phone/name/rationale/score) 키 없음 — _assert_pii_safe 통과가 증명.


# ── §19-52: no same_event truth ─────────────────────────────────────────────────────────────────────────
def test_52_no_same_event_truth():
    out = _ready_contact()
    assert out["same_event_truth_hidden"] is True
    instr = out["contact_readiness_package"]["official_news_label_instructions"]
    assert instr["same_event_truth_asserted"] is False


# ── §19-53: no score/rationale/predicted_status ─────────────────────────────────────────────────────────
def test_53_no_score_rationale_predicted_status():
    out = _ready_contact()
    assert out["score_hidden"] is True
    assert out["rationale_hidden"] is True
    assert out["predicted_status_hidden"] is True
    assert out["raw_body_hidden"] is True


# ── §19-54: actual sending false ────────────────────────────────────────────────────────────────────────
def test_54_actual_sending_false():
    assert _ready_contact()["actual_sending_performed"] is False
    assert _blocked_contact()["actual_sending_performed"] is False


# ── invariants: gold 0 · merge 0 · sanitized projection ─────────────────────────────────────────────────
def test_55_invariants_and_sanitized():
    out = _ready_contact()
    assert out["production_gold_count"] == 0   # freeze ≠ gold.
    assert out["merge_allowed"] is False
    assert out["r2_r7_no_go"] is True
    agg = sanitized_contact_readiness(out)
    assert "contact_readiness_package" not in agg
    assert agg["reviewer_contact_ready"] is True
    assert agg["actual_sending_performed"] is False


# ── label schema single-source accepted labels ─────────────────────────────────────────────────────────
def test_56_label_schema_single_source():
    schema = build_official_news_label_schema()
    for lab in ("same_event", "different_event", "unsure", "needs_review"):
        assert lab in schema["accepted_labels"]
    assert "role_confusion_flag" in schema["optional_annotation_fields"]
    assert "JSONL" in schema["file_format"]
