"""ADR#89 §19(46~54) — returned label dropbox readiness(수신 경로/schema/validation·실 label 0·production gold 0).
fake scan_fn / label_readiness 주입으로 결정론 검증(network 0·디스크 쓰기 0)."""
from __future__ import annotations

from pathlib import Path

from backend.app.tools.returned_label_dropbox_readiness import (
    DROPBOX_BLOCKED_SCHEMA,
    DROPBOX_READY,
    build_returned_label_dropbox_readiness,
    sanitized_dropbox_readiness,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _empty_scan(directory):
    return {"directory": str(directory), "directory_exists": False,
            "contact_evidence_files": [], "returned_label_files": []}


def _scan_with_files(n):
    def _scan(directory):
        return {"directory": str(directory), "directory_exists": True,
                "contact_evidence_files": [],
                "returned_label_files": [f"file_{i}.jsonl" for i in range(n)]}
    return _scan


# ── §19-46: dropbox path declared ──────────────────────────────────────────────────────────────────────────
def test_46_dropbox_path_declared():
    out = build_returned_label_dropbox_readiness(scan_fn=_empty_scan)
    assert out["dropbox_path"]
    assert "outputs/reviewer_batch" in out["dropbox_path"].replace("\\", "/")


# ── ADR#90 — batch_id 출력 필드(launch checklist batch 정합 lock 의 입력·직접 검증) ──────────────────────────
def test_adr90_batch_id_field_exposed():
    out = build_returned_label_dropbox_readiness(scan_fn=_empty_scan, batch_id="my_batch_xyz")
    assert out["batch_id"] == "my_batch_xyz"
    # dropbox_path 도 그 batch 를 경로에 반영(batch-specific).
    assert "my_batch_xyz" in out["dropbox_path"].replace("\\", "/")


# ── §19-47: dropbox path gitignored ────────────────────────────────────────────────────────────────────────
def test_47_dropbox_gitignored():
    gitignore = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "outputs/reviewer_batch/" in gitignore
    out = build_returned_label_dropbox_readiness(scan_fn=_empty_scan)
    assert out["dropbox_gitignored"] is True


# ── §19-48: expected file pattern defined ──────────────────────────────────────────────────────────────────
def test_48_expected_file_pattern_defined():
    out = build_returned_label_dropbox_readiness(scan_fn=_empty_scan)
    assert out["returned_label_glob"] == "*.jsonl"
    assert isinstance(out["expected_returned_files_example"], list)
    assert out["schema_version"]


# ── §19-49: validation command defined ─────────────────────────────────────────────────────────────────────
def test_49_validation_command_defined():
    out = build_returned_label_dropbox_readiness(scan_fn=_empty_scan)
    assert out["validation_command"]
    assert out["validation_command_ready"] is True


# ── §19-50: actual_returned_label_count=0 if no real files ─────────────────────────────────────────────────
def test_50_actual_count_zero_when_no_files():
    out = build_returned_label_dropbox_readiness(scan_fn=_empty_scan)
    assert out["actual_returned_label_count"] == 0
    # 실 파일이 있으면 카운트는 반영되지만 gold 는 여전히 0.
    out2 = build_returned_label_dropbox_readiness(scan_fn=_scan_with_files(3))
    assert out2["actual_returned_label_count"] == 3
    assert out2["production_gold_count"] == 0


# ── §19-51: synthetic fixture not counted as gold ──────────────────────────────────────────────────────────
def test_51_synthetic_not_counted():
    out = build_returned_label_dropbox_readiness(scan_fn=_empty_scan)
    assert out["synthetic_fixture_counted_as_gold"] is False
    assert out["label_fabricated"] is False


# ── §19-52: single reviewer label not gold ─────────────────────────────────────────────────────────────────
def test_52_single_reviewer_not_gold():
    out = build_returned_label_dropbox_readiness(scan_fn=_empty_scan)
    assert out["single_reviewer_label_is_gold"] is False
    assert out["agreement_required_for_gold"] is True


# ── §19-53: unsure/needs_more_context not gold ─────────────────────────────────────────────────────────────
def test_53_unsure_not_gold():
    out = build_returned_label_dropbox_readiness(scan_fn=_empty_scan)
    assert out["unsure_label_is_gold"] is False
    assert "needs_more_context" in out["accepted_labels"]


# ── §19-54: production_gold_count remains 0 ────────────────────────────────────────────────────────────────
def test_54_production_gold_zero():
    out = build_returned_label_dropbox_readiness(scan_fn=_empty_scan)
    assert out["production_gold_count"] == 0
    assert out["merge_allowed"] is False
    assert out["r2_r7_no_go"] is True


# ── 추가: schema ready(synthetic dry-run) → label_dropbox_ready True ────────────────────────────────────────
def test_schema_ready_makes_dropbox_ready():
    out = build_returned_label_dropbox_readiness(scan_fn=_empty_scan)
    assert out["returned_label_dropbox_status"] == DROPBOX_READY
    assert out["label_dropbox_ready"] is True
    assert out["blocked_reason"] == ""


# ── 추가: schema not ready(주입) → label_dropbox_ready False·blocked ────────────────────────────────────────
def test_schema_not_ready_blocks():
    bad = {"label_intake_readiness_status": "official_news_label_schema_invalid", "production_gold_count": 0}
    out = build_returned_label_dropbox_readiness(scan_fn=_empty_scan, label_readiness=bad)
    assert out["returned_label_dropbox_status"] == DROPBOX_BLOCKED_SCHEMA
    assert out["label_dropbox_ready"] is False
    assert out["blocked_reason"] == "official_news_label_schema_not_ready"


# ── 추가: sanitized 투영(status/count 만) ──────────────────────────────────────────────────────────────────
def test_sanitized_projection():
    out = build_returned_label_dropbox_readiness(scan_fn=_empty_scan)
    s = sanitized_dropbox_readiness(out)
    assert set(s) == {"returned_label_dropbox_status", "label_dropbox_ready", "actual_returned_label_count",
                      "production_gold_count", "blocked_reason", "next_action"}
