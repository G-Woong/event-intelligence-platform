"""ADR#88 — official_news_label_intake_readiness tests (§19 55~62 · synthetic dry-run · gold 0 · network 0)."""
from __future__ import annotations

from backend.app.services.identity_human_labeling import SOURCE_SYNTHETIC
from backend.app.tools.official_news_label_intake_readiness import (
    LABEL_INTAKE_READINESS_READY,
    build_synthetic_official_news_label_fixture,
    canonical_returned_label,
    run_official_news_label_intake_readiness,
    validate_official_news_label_record,
)


# ── §19-55: synthetic official×news label fixture marked synthetic ──────────────────────────────────────
def test_55_fixture_marked_synthetic():
    rows = build_synthetic_official_news_label_fixture("oxn_0001", ["reviewer_a", "reviewer_b"])
    assert len(rows) == 2
    for r in rows:
        assert r["dataset_source"] == SOURCE_SYNTHETIC          # marked synthetic.
        assert r["source_type_left"] == "official"             # official×news role.
        assert r["source_type_right"] == "article"


# ── §19-56 & §19-62: synthetic fixture does not increase production gold (remains 0) ────────────────────
def test_56_62_synthetic_does_not_increase_production_gold():
    out = run_official_news_label_intake_readiness()
    assert out["production_gold_count"] == 0
    assert out["not_production_gold"] is True
    assert out["marked_synthetic"] is True
    # 2-reviewer 만장일치 same_event 는 synthetic gold(production 아님).
    assert out["synthetic_gold_count"] >= 1


# ── §19-57: single reviewer label not gold ─────────────────────────────────────────────────────────────
def test_57_single_reviewer_not_gold():
    out = run_official_news_label_intake_readiness()
    assert out["single_reviewer_not_gold"] is True


# ── §19-58: unsure not gold ─────────────────────────────────────────────────────────────────────────────
def test_58_unsure_not_gold():
    out = run_official_news_label_intake_readiness()
    assert out["unsure_not_gold"] is True


# ── §19-59: accepted labels validated ──────────────────────────────────────────────────────────────────
def test_59_accepted_labels_validated():
    for lab in ("same_event", "different_event", "unsure", "needs_review", "needs_more_context"):
        v = validate_official_news_label_record({
            "batch_id": "b", "pair_id": "oxn_0001", "label": lab, "reviewer_id_or_anonymous_code": "rv_a"})
        assert v["valid"] is True, lab
    # alias canonicalization.
    assert canonical_returned_label("needs_more_context") == "needs_review"
    assert canonical_returned_label("same_event") == "same_event"


# ── §19-60: invalid label rejected ─────────────────────────────────────────────────────────────────────
def test_60_invalid_label_rejected():
    v = validate_official_news_label_record({
        "batch_id": "b", "pair_id": "oxn_0001", "label": "totally_made_up",
        "reviewer_id_or_anonymous_code": "rv_a"})
    assert v["valid"] is False
    assert "invalid_label" in v["rejection_reasons"]
    # missing required.
    v2 = validate_official_news_label_record({"pair_id": "oxn_0001", "label": "same_event"})
    assert v2["valid"] is False
    assert "missing_batch_id" in v2["rejection_reasons"]
    assert "missing_reviewer_id_or_anonymous_code" in v2["rejection_reasons"]


# ── §19-61: role_confusion flag accepted ───────────────────────────────────────────────────────────────
def test_61_role_confusion_flag_accepted():
    v = validate_official_news_label_record({
        "batch_id": "b", "pair_id": "oxn_0001", "label": "different_event",
        "reviewer_id_or_anonymous_code": "rv_a", "role_confusion_flag": True,
        "uncertain_flag": True, "evidence_notes": "official is a different docket than the news"})
    assert v["valid"] is True
    # invalid flag type rejected.
    v2 = validate_official_news_label_record({
        "batch_id": "b", "pair_id": "oxn_0001", "label": "same_event",
        "reviewer_id_or_anonymous_code": "rv_a", "role_confusion_flag": "yes"})
    assert v2["valid"] is False
    assert "invalid_role_confusion_flag" in v2["rejection_reasons"]


# ── forbidden field (score/rationale/predicted_status) in returned label rejected ──────────────────────
def test_62b_forbidden_field_in_record_rejected():
    for forb in ("score", "rationale", "predicted_status", "raw_body", "same_event_truth"):
        v = validate_official_news_label_record({
            "batch_id": "b", "pair_id": "oxn_0001", "label": "same_event",
            "reviewer_id_or_anonymous_code": "rv_a", forb: 0.99})
        assert v["valid"] is False, forb
        assert "forbidden_field" in v["rejection_reasons"], forb


# ── readiness status + schema acceptance + invariants ──────────────────────────────────────────────────
def test_63_readiness_status_and_invariants():
    out = run_official_news_label_intake_readiness()
    assert out["label_intake_readiness_status"] == LABEL_INTAKE_READINESS_READY
    assert out["schema_accepts_official_news"] is True
    assert out["annotation_schema_valid"] is True
    assert out["actual_label_fabricated"] is False
    assert out["merge_allowed"] is False
    assert out["production_gold_provenance_verified"] is False
    assert out["r2_r7_no_go"] is True
