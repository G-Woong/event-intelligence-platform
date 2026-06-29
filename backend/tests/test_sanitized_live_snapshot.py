"""ADR#84 — sanitized live snapshot tests (reproducibility without leakage; gitignored outputs).

정책을 테스트로 잠근다: named_entity/event_phrase 는 hash 만(원문 미노출)·per-pair score/raw body/secret/PII/
same_event 미포함·live attempt 없으면 not_written_no_live_run·write 는 지정 dir(outputs gitignored)에만.
"""
from __future__ import annotations

import json

import pytest

from backend.app.tools.sanitized_live_snapshot import (
    SNAPSHOT_NOT_WRITTEN_NO_LIVE_RUN,
    SNAPSHOT_WRITTEN,
    build_sanitized_live_snapshot,
    write_sanitized_live_snapshot,
)

_ENTITY = "U.S. Supreme Court"
_PHRASE = "Supreme Court ruling allowing turn-back of asylum seekers under metering policy"

TARGET = {
    "named_entity": _ENTITY,
    "event_phrase": _PHRASE,
    "occurrence_date": "2026-06-25",
    "start_date": "2026-06-25",
    "end_date": "2026-06-26",
    "time_window": "1d",
    "providers": ["guardian", "nyt"],
    "query_text": f"{_ENTITY} {_PHRASE}",
}

EXECUTOR_OUT_LIVE = {
    "executed": True,
    "live_call_count": 2,
    "block_reason": None,
    "smoke": {
        "provider_status_by_provider": {"guardian": "ok", "nyt": "ok"},
        "records_count_by_provider": {"guardian": 10, "nyt": 10},
        "cross_source_pair_count": 100,
        "block_reasons": ["no_title_overlap"],
        "band_diagnostic": {"max_cross_source_title_jaccard": 0.0625},
        "recall_probe_diagnostic": {"max_recall_probe_score": 0.0625, "pairs_newly_routed_by_probe": 0},
    },
    "pcand": {
        "production_candidate_status": "blocked_no_publishable_pairs",
        "production_frozen_pair_count": 0,
        "candidate_provenance": "none",
        "next_actions": ["re-run bounded with narrower same-event-targeted topics"],
    },
}

EXECUTOR_OUT_NO_LIVE = {
    "executed": False, "live_call_count": 0,
    "block_reason": "live_query_target_not_wired", "smoke": None, "pcand": None,
}

_FORBIDDEN = ("score", "rationale", "predicted_status", "same_event", "raw_body", "body",
              "reviewer_name", "email", "secret", "api_key")


def test_build_hashes_entity_and_phrase_no_plaintext():
    s = build_sanitized_live_snapshot(TARGET, EXECUTOR_OUT_LIVE, run_id="r1",
                                      live_run_status="live_no_routing_candidates")
    assert s["named_entity_redacted_or_hash"].startswith("sha256:")
    assert s["event_phrase_redacted_or_hash"].startswith("sha256:")
    # 원문(named_entity/event_phrase)이 직렬화 어디에도 없음.
    blob = json.dumps(s, ensure_ascii=False)
    assert _ENTITY not in blob
    assert "asylum seekers under metering" not in blob
    assert "named_entity" not in s and "event_phrase" not in s


def test_build_carries_sanitized_aggregates_only():
    s = build_sanitized_live_snapshot(TARGET, EXECUTOR_OUT_LIVE, run_id="r1",
                                      live_run_status="live_no_routing_candidates")
    assert s["live_query_executed"] is True
    assert s["live_call_count"] == 2
    assert s["comparison_pair_count"] == 100
    assert s["max_baseline_jaccard"] == 0.0625
    assert s["max_recall_probe_score"] == 0.0625
    assert s["live_pairs_newly_routed_by_probe"] == 0
    assert s["production_candidate_status"] == "blocked_no_publishable_pairs"
    assert s["live_run_status"] == "live_no_routing_candidates"
    assert s["date_window_enforced"] is True
    assert s["providers"] == ["guardian", "nyt"]


def test_date_window_enforced_reflects_param_not_constant():
    # adversarial MEDIUM-2: 상수 True 둔갑 금지 — 실제 executor enforce_window 인자를 사실대로 반영.
    on = build_sanitized_live_snapshot(TARGET, EXECUTOR_OUT_LIVE, run_id="r1", date_window_enforced=True)
    off = build_sanitized_live_snapshot(TARGET, EXECUTOR_OUT_LIVE, run_id="r1", date_window_enforced=False)
    assert on["date_window_enforced"] is True
    assert off["date_window_enforced"] is False


def test_build_no_forbidden_or_per_pair_score():
    s = build_sanitized_live_snapshot(TARGET, EXECUTOR_OUT_LIVE, run_id="r1")
    for f in _FORBIDDEN:
        assert f not in s, f"forbidden key {f}"
    # aggregate(max_*)만 — per-pair score 리스트는 없음(top_lift_samples 등 미포함).
    assert "top_lift_samples" not in s
    assert "top_below_floor_samples" not in s
    assert "recall_probe_diagnostic" not in s


def test_build_no_live_run_marks_not_executed():
    s = build_sanitized_live_snapshot(TARGET, EXECUTOR_OUT_NO_LIVE, run_id="r0")
    assert s["live_query_executed"] is False
    assert s["comparison_pair_count"] == 0


def test_write_persists_only_when_executed(tmp_path):
    s = build_sanitized_live_snapshot(TARGET, EXECUTOR_OUT_LIVE, run_id="adr84_test")
    w = write_sanitized_live_snapshot(s, directory=str(tmp_path))
    assert w["snapshot_status"] == SNAPSHOT_WRITTEN
    written = tmp_path / "adr84_test.json"
    assert written.exists()
    content = json.loads(written.read_text(encoding="utf-8"))
    assert content["run_id"] == "adr84_test"
    assert content["named_entity_redacted_or_hash"].startswith("sha256:")
    assert _ENTITY not in written.read_text(encoding="utf-8")


def test_write_skips_when_no_live_run(tmp_path):
    s = build_sanitized_live_snapshot(TARGET, EXECUTOR_OUT_NO_LIVE, run_id="adr84_nolive")
    w = write_sanitized_live_snapshot(s, directory=str(tmp_path))
    assert w["snapshot_status"] == SNAPSHOT_NOT_WRITTEN_NO_LIVE_RUN
    assert w["snapshot_path"] == ""
    assert not (tmp_path / "adr84_nolive.json").exists()


# ── ADR#85: control experiment(fidelity) 결과를 snapshot 에 aggregate-only 로 첨부(제목 전문·score 미노출) ──────────
_FIDELITY = {
    "operation_name": "provider_date_window_fidelity",
    "provider": "guardian",
    "live_query_executed": True,
    "provider_date_window_status": "returns_out_of_window",
    "mechanism_primary_hypothesis": "order_by_newest_dominance",
    "mechanism_confidence": "medium",
    "date_param_effect": "weak",
    "order_by_newest_effect": "strong",
    "query_relevance_effect": "weak",
    "in_window_coverage_effect": "zero_in_returned",
    "in_window_records_found": 1,
    "out_of_window_records_dropped": 2,
    "no_in_window_records": False,
    "control_experiment_variants_count": 5,
    "variant_results": [
        {"variant": "original", "result_class": "out_of_window_only", "title_or_label": "LEAK ME"},
        {"variant": "relevance_order", "result_class": "in_window_related", "title_or_label": "LEAK ME TOO"},
    ],
}


def test_control_experiment_block_is_aggregate_only_no_titles():
    s = build_sanitized_live_snapshot(
        TARGET, EXECUTOR_OUT_LIVE, run_id="adr85", live_run_status="live_no_routing_candidates",
        fidelity_result=_FIDELITY)
    ce = s["control_experiment"]
    assert ce is not None
    assert ce["mechanism_primary_hypothesis"] == "order_by_newest_dominance"
    assert ce["mechanism_confidence"] == "medium"
    assert ce["mechanism_confidence"] != "high"          # 단일 bounded run 은 절대 high 금지.
    assert ce["out_of_window_records_dropped"] == 2
    # variant→result_class 만 보존(제목 전문 미노출).
    assert ce["variant_result_classes"] == {
        "original": "out_of_window_only", "relevance_order": "in_window_related"}
    # 제목 전문이 snapshot 어디에도 새지 않는다.
    assert "LEAK ME" not in json.dumps(s, ensure_ascii=False)


def test_control_experiment_none_when_no_fidelity():
    s = build_sanitized_live_snapshot(TARGET, EXECUTOR_OUT_LIVE, run_id="adr85b")
    assert s["control_experiment"] is None   # fidelity 미주입 → 첨부 없음(정직).


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
