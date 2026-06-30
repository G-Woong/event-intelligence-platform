"""ADR#94 §13 — first live freeze->R1 dry-run harness tests.

검증: 기본 후보는 synthetic/fake 로 표식(synthetic_or_fake True) · 합성은 production gold 아님(is_production_gold False·
production_gold_count 0) · unsafe 합성(forbidden/extra 키 or canonical 누락)은 거부(synthetic_artifact_rejected) ·
safe 합성은 freeze->R1 체크리스트를 생성(freeze_to_r1_status ready·command_ready True) · batch_id 정합 · actual sending 0 ·
reviewer roster 미커밋 · real returned label 미집계.
"""
from __future__ import annotations

from backend.app.tools.first_live_freeze_r1_dry_run_harness import (
    DRY_RUN_READY,
    DRY_RUN_REJECTED,
    build_first_live_freeze_r1_dry_run_harness,
    sanitized_first_live_freeze_r1_dry_run_harness,
)
from backend.app.tools.freeze_to_r1_executable_checklist import FR1_READY
from backend.app.tools.r1_label_return_operational_bridge import DEFAULT_BATCH_ID

_REQUIRED_KEYS = {
    "freeze_r1_dry_run_status", "synthetic_or_fake", "freeze_candidate_present", "freeze_artifact_safe",
    "freeze_to_r1_status", "batch_id_consistent", "label_dropbox_ready", "validation_command_ready",
    "intake_command_ready", "agreement_command_ready", "production_gold_count", "is_production_gold",
    "actual_sending_performed", "reviewer_roster_committed", "real_label_counted", "merge_allowed",
    "network_invoked",
}


def _safe_pair() -> dict:
    """hardening 통과 합성 freeze artifact(official/news record 는 allowlist 키만)."""
    return {
        "pair_id": "synthetic_dry_run_0002",
        "official_record": {
            "record_type": "official_document",
            "source_id": "synthetic_official_source",
            "canonical_url": "https://example.org/synthetic/official/dry-run",
            "published_at_or_observed_at": "2026-06-25",
            "title_or_label": "SYNTHETIC official record for freeze->R1 dry-run",
        },
        "news_record": {
            "record_type": "news_article",
            "source_id": "synthetic_news_source",
            "canonical_url": "https://example.com/synthetic/news/dry-run",
            "published_at_or_observed_at": "2026-06-25",
            "title_or_label": "SYNTHETIC news article for freeze->R1 dry-run",
        },
        "shared_tokens": ["synthetic", "dry", "run"],
        "date_proximity_days": 0,
    }


# ── default fake candidate is marked synthetic ──
def test_default_candidate_marked_synthetic():
    out = build_first_live_freeze_r1_dry_run_harness()
    assert out["synthetic_or_fake"] is True
    assert out["freeze_candidate_present"] is True
    assert out["freeze_r1_dry_run_status"] == DRY_RUN_READY


# ── fake candidate is NOT production gold ──
def test_fake_candidate_not_production_gold():
    out = build_first_live_freeze_r1_dry_run_harness()
    assert out["is_production_gold"] is False
    assert out["production_gold_count"] == 0


# ── UNSAFE artifact (forbidden key) → rejected, no checklist ──
def test_unsafe_forbidden_key_rejected():
    art = _safe_pair()
    art["official_record"]["score"] = 0.97   # forbidden key → hardening unsafe.
    out = build_first_live_freeze_r1_dry_run_harness(synthetic_pair=art)
    assert out["freeze_artifact_safe"] is False
    assert out["freeze_r1_dry_run_status"] == DRY_RUN_REJECTED
    assert out["validation_command_ready"] is False
    assert out["intake_command_ready"] is False


# ── UNSAFE artifact (record missing canonical_url) → rejected ──
def test_unsafe_missing_canonical_rejected():
    art = _safe_pair()
    art["news_record"]["canonical_url"] = ""   # missing canonical → hardening unsafe.
    out = build_first_live_freeze_r1_dry_run_harness(synthetic_pair=art)
    assert out["freeze_artifact_safe"] is False
    assert out["freeze_r1_dry_run_status"] == DRY_RUN_REJECTED


# ── SAFE artifact → checklist produced (status ready + command_ready bools True) ──
def test_safe_artifact_produces_checklist():
    out = build_first_live_freeze_r1_dry_run_harness(synthetic_pair=_safe_pair())
    assert out["freeze_artifact_safe"] is True
    assert out["freeze_r1_dry_run_status"] == DRY_RUN_READY
    assert out["freeze_to_r1_status"] == FR1_READY
    assert out["label_dropbox_ready"] is True
    assert out["validation_command_ready"] is True
    assert out["intake_command_ready"] is True
    assert out["agreement_command_ready"] is True


# ── batch_id consistent with the default contact batch ──
def test_batch_id_consistent_with_default_batch():
    out = build_first_live_freeze_r1_dry_run_harness()
    assert out["batch_id"] == DEFAULT_BATCH_ID
    assert out["batch_id_consistent"] is True


# ── production_gold_count unchanged (0) for the synthetic dry-run ──
def test_production_gold_count_zero():
    assert build_first_live_freeze_r1_dry_run_harness()["production_gold_count"] == 0
    assert build_first_live_freeze_r1_dry_run_harness(synthetic_pair=_safe_pair())["production_gold_count"] == 0


# ── no actual sending performed ──
def test_actual_sending_not_performed():
    assert build_first_live_freeze_r1_dry_run_harness()["actual_sending_performed"] is False
    art = _safe_pair()
    art["official_record"]["score"] = 0.5   # unsafe path also never sends.
    assert build_first_live_freeze_r1_dry_run_harness(synthetic_pair=art)["actual_sending_performed"] is False


# ── no reviewer roster committed ──
def test_reviewer_roster_not_committed():
    assert build_first_live_freeze_r1_dry_run_harness()["reviewer_roster_committed"] is False


# ── no real returned label counted ──
def test_real_label_not_counted():
    assert build_first_live_freeze_r1_dry_run_harness()["real_label_counted"] is False


# ── module asserts no merge / no network ──
def test_no_merge_no_network():
    out = build_first_live_freeze_r1_dry_run_harness()
    assert out["merge_allowed"] is False
    assert out["network_invoked"] is False


# ── all required output keys present ──
def test_required_output_keys_present():
    assert _REQUIRED_KEYS <= set(build_first_live_freeze_r1_dry_run_harness())


# ── sanitized projection: status/flags/count/next_action only ──
def test_sanitized_projection_keys():
    out = build_first_live_freeze_r1_dry_run_harness()
    s = sanitized_first_live_freeze_r1_dry_run_harness(out)
    assert set(s.keys()) == {
        "freeze_r1_dry_run_status", "synthetic_or_fake", "freeze_artifact_safe", "freeze_to_r1_status",
        "batch_id_consistent", "is_production_gold", "actual_sending_performed", "real_label_counted",
        "merge_allowed", "production_gold_count", "next_action",
    }
    assert s["synthetic_or_fake"] is True
    assert s["is_production_gold"] is False
