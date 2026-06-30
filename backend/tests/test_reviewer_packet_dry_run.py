"""ADR#95 §14/§21 (#42-48) — reviewer packet dry-run tests.

정책을 테스트로 잠근다: 진짜 freeze 없음 + synthetic=False → BLOCKED_NO_FREEZE(production packet 없음) · 기본
(synthetic=True) → SYNTHETIC dry-run(synthetic_or_fake True·is_production False) · UNSAFE artifact 는 hardening 이
거부(BLOCKED_UNSAFE·packet None·forbidden 값 미누출) 또는 _assert_pii_safe 가 fail-loud · safe 합성/production packet
은 수용 · actual_sending 항상 False · reviewer roster 미커밋·PII 0 · production_gold_count 0 · forbidden_fields_hidden
True · sanitized 에 status 포함 · 기본 build 는 _assert_pii_safe 통과.
"""
from __future__ import annotations

import pytest

from backend.app.tools.reviewer_packet_dry_run import (
    CONTRACT_VERSION,
    OPERATION_NAME,
    PACKET_BLOCKED_NO_FREEZE,
    PACKET_BLOCKED_UNSAFE,
    PACKET_PRODUCTION_READY,
    PACKET_SYNTHETIC_DRY_RUN,
    build_reviewer_packet_dry_run,
    sanitized_reviewer_packet_dry_run,
)
from backend.app.tools.reviewer_pilot_handoff import _HANDOFF_FORBIDDEN_KEYS, _assert_pii_safe

_REQUIRED_KEYS = {
    "operation_name", "contract_version", "reviewer_packet_dry_run_status", "synthetic_or_fake",
    "is_production", "batch_id", "candidate_count", "official_news_role_explanation", "label_instruction",
    "expected_return_file_pattern", "dropbox_path", "validation_command", "intake_command",
    "forbidden_fields_hidden", "packet", "blocked_reason", "next_action", "actual_sending_performed",
    "reviewer_roster_committed", "score_hidden", "rationale_hidden", "predicted_status_hidden",
    "same_event_truth_hidden", "raw_body_hidden", "reviewer_pii_hidden", "merge_allowed",
    "production_gold_count", "network_invoked",
}


def _safe_pair() -> dict:
    """hardening 통과 reviewer worklist record pair(official/news 는 allowlist 키만)."""
    return {
        "pair_id": "synthetic_packet_0001",
        "official_record": {
            "record_type": "official_document",
            "source_id": "synthetic_official_source",
            "canonical_url": "https://example.org/synthetic/official/packet",
            "published_at_or_observed_at": "2026-06-25",
            "title_or_label": "SYNTHETIC official record for reviewer packet dry-run",
        },
        "news_record": {
            "record_type": "news_article",
            "source_id": "synthetic_news_source",
            "canonical_url": "https://example.com/synthetic/news/packet",
            "published_at_or_observed_at": "2026-06-25",
            "title_or_label": "SYNTHETIC news article for reviewer packet dry-run",
        },
        "shared_tokens": ["synthetic", "packet"],
        "date_proximity_days": 0,
    }


def _frozen_production_candidate() -> dict:
    """live-derived production-candidate freeze 성공 형태(safe record pair 동봉)."""
    return {
        "production_candidate_batch_ready": True,
        "production_batch_id": "reviewer_prod_cand_777",
        "production_batch_signature": "sha256:deadbeefcafe0777",
        "production_frozen_pair_count": 2,
        "candidate_provenance": "live_derived",
        "expected_label_files": ["reviewer_prod_cand_777__rev_00001__labels.jsonl"],
        "validation_command": ".\\.venv\\Scripts\\python.exe -m backend.app.tools.reviewer_batch_launch --validate x",
        "intake_directory": "outputs/reviewer_batch/reviewer_prod_cand_777/intake",
        "operator_launch_checklist": {"steps": ["distribute", "collect"], "dry_run": False},
        "reviewer_instruction_ready": True,
        "production_gold_count": 0,
        "current_r1_gap": 200,
        "record_pair": _safe_pair(),
    }


# ── #42 no real freeze + synthetic disabled → blocked, no production packet ──
def test_no_candidate_synthetic_false_blocks_no_freeze():
    out = build_reviewer_packet_dry_run(production_candidate=None, synthetic=False)
    assert out["reviewer_packet_dry_run_status"] == PACKET_BLOCKED_NO_FREEZE
    assert out["packet"] is None
    assert out["is_production"] is False
    assert out["synthetic_or_fake"] is False


def test_non_frozen_candidate_synthetic_false_blocks():
    # batch_ready 선언만(batch_id/pairs 미충족)으로는 freeze 아님 → synthetic 비활성 시 BLOCKED.
    half = {"production_candidate_batch_ready": True, "production_batch_id": "", "production_frozen_pair_count": 0}
    out = build_reviewer_packet_dry_run(production_candidate=half, synthetic=False)
    assert out["reviewer_packet_dry_run_status"] == PACKET_BLOCKED_NO_FREEZE
    assert out["packet"] is None


# ── #43 default (synthetic=True) → synthetic dry-run packet ──
def test_default_is_synthetic_dry_run():
    out = build_reviewer_packet_dry_run()
    assert out["reviewer_packet_dry_run_status"] == PACKET_SYNTHETIC_DRY_RUN
    assert out["synthetic_or_fake"] is True
    assert out["is_production"] is False
    assert out["operation_name"] == OPERATION_NAME
    assert out["contract_version"] == CONTRACT_VERSION


# ── #44 a safe synthetic packet is accepted (shape present) ──
def test_safe_synthetic_packet_accepted():
    out = build_reviewer_packet_dry_run(synthetic=True)
    pkt = out["packet"]
    assert pkt is not None
    assert pkt["synthetic_or_fake"] is True
    assert pkt["candidate_count"] == 1
    assert pkt["reviewers_per_pair_minimum"] == 2
    assert out["official_news_role_explanation"] and out["label_instruction"]
    assert out["dropbox_path"] and out["validation_command"] and out["intake_command"]
    assert out["expected_return_file_pattern"].endswith("__labels.jsonl")


# ── #44b a real frozen candidate (safe pair) → production packet accepted ──
def test_frozen_candidate_production_packet():
    out = build_reviewer_packet_dry_run(production_candidate=_frozen_production_candidate(), synthetic=False)
    assert out["reviewer_packet_dry_run_status"] == PACKET_PRODUCTION_READY
    assert out["is_production"] is True
    assert out["synthetic_or_fake"] is False
    assert out["batch_id"] == "reviewer_prod_cand_777"
    assert out["candidate_count"] == 2
    assert out["packet"] is not None
    assert out["validation_command"]
    assert out["intake_command"]


# ── #45 UNSAFE artifact (forbidden key in record pair) → rejected by hardening, no leak ──
def test_unsafe_record_pair_rejected_by_hardening_no_leak():
    cand = _frozen_production_candidate()
    poisoned = _safe_pair()
    poisoned["official_record"]["score"] = 0.99   # forbidden key → hardening unsafe.
    cand["record_pair"] = poisoned
    out = build_reviewer_packet_dry_run(production_candidate=cand, synthetic=False)
    assert out["reviewer_packet_dry_run_status"] == PACKET_BLOCKED_UNSAFE
    assert out["packet"] is None
    assert out["is_production"] is False
    # 출력은 forbidden EXACT key 를 노출하지 않는다(score_hidden 선언 키는 forbidden 아님) AND 그 값(0.99)도 echo 0.
    for f in _HANDOFF_FORBIDDEN_KEYS:
        assert f not in out
    assert "0.99" not in repr(out)
    _assert_pii_safe(out, _path="unsafe_block")   # 재귀 가드도 통과(packet None·forbidden key 0).


# ── #45b _assert_pii_safe backstop: poisoned operator_launch_checklist (no record pair) → fail-loud ──
def test_poisoned_checklist_raises_pii_safe():
    cand = _frozen_production_candidate()
    cand.pop("record_pair", None)   # record pair 없음 → hardening skip, handoff bridge 경로로.
    cand["operator_launch_checklist"] = {"reviewer_name": "should not pass"}
    with pytest.raises(ValueError):
        build_reviewer_packet_dry_run(production_candidate=cand, synthetic=False)


# ── #46 actual sending never performed (every branch) ──
def test_actual_sending_not_performed():
    assert build_reviewer_packet_dry_run()["actual_sending_performed"] is False
    assert build_reviewer_packet_dry_run(synthetic=False)["actual_sending_performed"] is False
    assert build_reviewer_packet_dry_run(
        production_candidate=_frozen_production_candidate())["actual_sending_performed"] is False


# ── #46b reviewer roster not committed AND no reviewer name/email anywhere ──
def test_reviewer_roster_not_committed_and_no_pii():
    for out in (
        build_reviewer_packet_dry_run(),
        build_reviewer_packet_dry_run(production_candidate=_frozen_production_candidate()),
    ):
        assert out["reviewer_roster_committed"] is False
        assert out["reviewer_pii_hidden"] is True
        blob = repr(out)
        assert "@" not in blob            # email 0.
        assert "reviewer_name" not in blob


# ── #47 production gold count stays 0 (no gold increase) ──
def test_production_gold_count_zero():
    assert build_reviewer_packet_dry_run()["production_gold_count"] == 0
    assert build_reviewer_packet_dry_run(synthetic=False)["production_gold_count"] == 0
    assert build_reviewer_packet_dry_run(
        production_candidate=_frozen_production_candidate())["production_gold_count"] == 0


# ── #47b merge / network never enabled ──
def test_no_merge_no_network():
    out = build_reviewer_packet_dry_run()
    assert out["merge_allowed"] is False
    assert out["network_invoked"] is False


# ── #48 forbidden_fields_hidden True and no forbidden EXACT key in output or packet ──
def test_forbidden_fields_hidden_and_no_forbidden_keys():
    for out in (
        build_reviewer_packet_dry_run(),
        build_reviewer_packet_dry_run(production_candidate=_frozen_production_candidate()),
        build_reviewer_packet_dry_run(production_candidate=None, synthetic=False),
    ):
        assert out["forbidden_fields_hidden"] is True
        for f in _HANDOFF_FORBIDDEN_KEYS:
            assert f not in out
            assert f not in (out.get("packet") or {})


# ── required output keys present ──
def test_required_output_keys_present():
    assert _REQUIRED_KEYS <= set(build_reviewer_packet_dry_run())


# ── sanitized projection carries the status (and aggregate flags only) ──
def test_sanitized_has_status():
    out = build_reviewer_packet_dry_run()
    s = sanitized_reviewer_packet_dry_run(out)
    assert s["reviewer_packet_dry_run_status"] == PACKET_SYNTHETIC_DRY_RUN
    assert "packet" not in s
    assert "validation_command" not in s
    assert s["production_gold_count"] == 0


# ── _assert_pii_safe passes on the default build (recursive guard, no raise) ──
def test_assert_pii_safe_passes_on_default():
    out = build_reviewer_packet_dry_run()
    _assert_pii_safe(out, _path="test_reviewer_packet_dry_run")   # must not raise.


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
