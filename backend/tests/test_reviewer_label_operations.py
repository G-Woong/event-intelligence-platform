"""ADR#66 — reviewer label operations + gold calibration preflight 테스트(병합 0·LLM 0·embedding 0·DB 0).

정책을 잠근다(§10 1-41): packet export/labeler-hidden·label import allowlist(forbidden field fail-loud)·
reviewer_id pseudonymization·gold 승격(single/unanimous/conflict/adjudicated)·production vs synthetic 분리·
agreement/calibration preflight·no-merge/no-LLM/no-DB·optional real label path. 회귀(42-74)는 전 suite 가 담당.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.identity_human_labeling import (
    SOURCE_LIVE,
    SOURCE_SYNTHETIC,
    ReviewerLabel,
)
from backend.app.tools.near_match_reviewer_queue import build_near_match_reviewer_queue
from backend.app.tools.reviewer_label_operations import (
    FORBIDDEN_LABEL_FIELDS,
    LABEL_SOURCE_PRODUCTION,
    LABEL_SOURCE_SYNTHETIC,
    LABEL_SOURCE_TEST,
    build_calibration_preflight,
    export_reviewer_packet,
    import_reviewer_labels,
    pseudonymize_reviewer_id,
    resolve_label_operations,
    run_reviewer_label_operations,
)
from backend.app.tools.semantic_candidate_scorer import run_semantic_candidate_scoring
from backend.app.tools.source_overlap_discovery import (
    build_captured_overlap_fixture,
    discover_overlap,
)

_MODULE = Path(__file__).resolve().parents[1] / "app" / "tools" / "reviewer_label_operations.py"


# ── helpers ───────────────────────────────────────────────────────────────────────────────────────────
def _queue():
    disc = discover_overlap(build_captured_overlap_fixture())
    return build_near_match_reviewer_queue(disc, packet_id="t_pkt")


def _lab(pid, rid, label, *, ds=SOURCE_LIVE, lang="en", rnd=1, conf="high"):
    return ReviewerLabel(
        pair_id=pid, reviewer_id=rid, review_round=rnd, label=label, label_confidence=conf,
        reviewed_at="2026-06-22T00:00:00+00:00", language=lang,
        source_type_left="article", source_type_right="article",
        title_left="headline left", title_right="headline right",
        observed_at_left="2026-06-22", observed_at_right="2026-06-22", dataset_source=ds)


def _row(pid, rid, label, *, extra=None, lang="en"):
    r = {
        "pair_id": pid, "reviewer_id": rid, "review_round": 1, "label": label,
        "label_confidence": "high", "reviewed_at": "2026-06-22T00:00:00+00:00", "language": lang,
        "source_type_left": "article", "source_type_right": "article",
        "title_left": "a", "title_right": "b",
        "observed_at_left": "2026-06-22", "observed_at_right": "2026-06-22",
    }
    if extra:
        r.update(extra)
    return r


def _write_jsonl(path, rows):
    import json
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return path


# ── §10 1-10: label export/import contract ─────────────────────────────────────────────────────────────
def test_01_scored_packet_exportable():
    out = export_reviewer_packet(_queue())
    assert out["packet_exportable"] is True
    assert out["packet_assignment_count"] > 0


def test_02_labeler_view_no_score():
    out = export_reviewer_packet(_queue())
    assert "score" not in out["labeler_view_sample_keys"]
    assert out["score_hidden_from_labeler"] is True


def test_03_labeler_view_no_rationale():
    out = export_reviewer_packet(_queue())
    assert "rationale" not in out["labeler_view_sample_keys"]
    assert out["rationale_hidden_from_labeler"] is True


def test_04_labeler_view_no_predicted_status():
    out = export_reviewer_packet(_queue())
    assert "predicted_status" not in out["labeler_view_sample_keys"]
    assert "sampling_bucket" not in out["labeler_view_sample_keys"]
    assert out["labeler_prediction_hidden"] is True


def test_05_import_accepts_allowed_fields(tmp_path):
    f = _write_jsonl(tmp_path / "ok.jsonl", [_row("p1", "ra", "same_event"), _row("p1", "rb", "same_event")])
    info = import_reviewer_labels(f, label_source=LABEL_SOURCE_PRODUCTION)
    assert info["label_schema_valid"] is True
    assert len(info["labels"]) == 2


def test_06_import_rejects_semantic_score(tmp_path):
    f = _write_jsonl(tmp_path / "s.jsonl", [_row("p1", "ra", "same_event", extra={"semantic_score": 0.9})])
    info = import_reviewer_labels(f, label_source=LABEL_SOURCE_PRODUCTION)
    assert info["label_schema_valid"] is False
    assert info["block_reason"] == "forbidden_field_in_label"


def test_07_import_rejects_model_rationale(tmp_path):
    f = _write_jsonl(tmp_path / "m.jsonl", [_row("p1", "ra", "same_event", extra={"model_rationale": "x"})])
    info = import_reviewer_labels(f, label_source=LABEL_SOURCE_PRODUCTION)
    assert info["label_schema_valid"] is False
    assert info["block_reason"] == "forbidden_field_in_label"


def test_08_import_rejects_raw_body(tmp_path):
    f = _write_jsonl(tmp_path / "b.jsonl", [_row("p1", "ra", "same_event", extra={"raw_body": "full text"})])
    info = import_reviewer_labels(f, label_source=LABEL_SOURCE_PRODUCTION)
    assert info["label_schema_valid"] is False
    assert info["block_reason"] == "forbidden_field_in_label"


def test_09_import_rejects_secret_api_key(tmp_path):
    f = _write_jsonl(tmp_path / "k.jsonl", [_row("p1", "ra", "same_event", extra={"api_key": "sk-xxx"})])
    info = import_reviewer_labels(f, label_source=LABEL_SOURCE_PRODUCTION)
    assert info["label_schema_valid"] is False
    assert info["block_reason"] == "forbidden_field_in_label"


def test_10_reviewer_id_not_raw_in_report():
    labs = [_lab("p1", "alice_secret_id", "same_event"), _lab("p1", "bob_secret_id", "same_event")]
    out = run_reviewer_label_operations(
        queue=_queue(), reviewer_labels=labs, label_source=LABEL_SOURCE_PRODUCTION)
    flat = repr(out)
    assert "alice_secret_id" not in flat and "bob_secret_id" not in flat
    assert all(p.startswith("rv_") for p in out["pseudonymous_reviewers"])
    assert pseudonymize_reviewer_id("alice_secret_id") in out["pseudonymous_reviewers"]


# ── §10 11-18: gold promotion ──────────────────────────────────────────────────────────────────────────
def test_11_single_reviewer_insufficient():
    r = resolve_label_operations([_lab("p1", "ra", "same_event")], label_source=LABEL_SOURCE_PRODUCTION)
    assert r["single_reviewer_count"] == 1
    assert r["production_gold_count"] == 0
    assert r["gold_ready"] is False


def test_12_unanimous_same_event_positive_gold():
    labs = [_lab("p1", "ra", "same_event"), _lab("p1", "rb", "same_event")]
    r = resolve_label_operations(labs, label_source=LABEL_SOURCE_PRODUCTION)
    assert r["unanimous_count"] == 1
    assert r["production_gold_count"] == 1
    assert r["production_gold"][0].label == "same_event"


def test_13_unanimous_different_event_negative_gold():
    labs = [_lab("p1", "ra", "different_event"), _lab("p1", "rb", "different_event")]
    r = resolve_label_operations(labs, label_source=LABEL_SOURCE_PRODUCTION)
    assert r["production_gold_count"] == 1
    assert r["production_gold"][0].label == "different_event"


def test_14_conflict_to_queue():
    labs = [_lab("p1", "ra", "same_event"), _lab("p1", "rb", "different_event")]
    r = resolve_label_operations(labs, label_source=LABEL_SOURCE_PRODUCTION)
    assert r["conflict_count"] == 1
    assert r["production_gold_count"] == 0
    assert any(q["pair_id"] == "p1" and q["needs_human_adjudication"] for q in r["conflict_adjudication_queue"])


def test_15_conflict_plus_human_adjudication_gold():
    labs = [_lab("p1", "ra", "same_event"), _lab("p1", "rb", "different_event")]
    adj = {"p1": {"label": "same_event", "adjudicated_by": "lead_h", "adjudicator_kind": "human"}}
    r = resolve_label_operations(labs, adjudications=adj, label_source=LABEL_SOURCE_PRODUCTION)
    assert r["adjudicated_count"] == 1
    assert r["production_gold_count"] == 1
    assert r["conflict_count"] == 0


def test_16_unsure_single_not_gold():
    # ambiguous(=unsure) single reviewer → insufficient → gold 아님.
    r = resolve_label_operations([_lab("p1", "ra", "ambiguous")], label_source=LABEL_SOURCE_PRODUCTION)
    assert r["production_gold_count"] == 0
    assert r["single_reviewer_count"] == 1


def test_17_synthetic_labels_not_production_gold():
    labs = [_lab("p1", "ra", "same_event", ds=SOURCE_SYNTHETIC),
            _lab("p1", "rb", "same_event", ds=SOURCE_SYNTHETIC)]
    r = resolve_label_operations(labs, label_source=LABEL_SOURCE_SYNTHETIC)
    assert r["production_gold_count"] == 0
    assert r["synthetic_gold_count"] == 1
    assert r["gold_ready"] is False


def test_18_production_gold_only_if_policy_met():
    # production label_source 라도 dataset_source 가 synthetic 이면 production gold 아님.
    labs = [_lab("p1", "ra", "same_event", ds=SOURCE_SYNTHETIC),
            _lab("p1", "rb", "same_event", ds=SOURCE_SYNTHETIC)]
    r = resolve_label_operations(labs, label_source=LABEL_SOURCE_PRODUCTION)
    assert r["production_gold_count"] == 0
    assert r["synthetic_gold_count"] == 1


# ── §10 19-27: agreement/calibration ────────────────────────────────────────────────────────────────────
def test_19_reviewer_count_reported():
    labs = [_lab("p1", "ra", "same_event"), _lab("p1", "rb", "same_event")]
    r = resolve_label_operations(labs, label_source=LABEL_SOURCE_PRODUCTION)
    assert r["reviewer_count"] == 2


def test_20_agreement_rate_reported():
    labs = [_lab("p1", "ra", "same_event"), _lab("p1", "rb", "same_event")]
    r = resolve_label_operations(labs, label_source=LABEL_SOURCE_PRODUCTION)
    assert r["agreement"]["agreement_rate"] == 1.0


def test_21_conflict_rate_reported():
    labs = [_lab("p1", "ra", "same_event"), _lab("p1", "rb", "different_event"),
            _lab("p2", "ra", "same_event"), _lab("p2", "rb", "same_event")]
    r = resolve_label_operations(labs, label_source=LABEL_SOURCE_PRODUCTION)
    pf = build_calibration_preflight(r)
    assert pf["conflict_rate"] == 0.5   # 1 conflict / 2 multi-reviewer pairs


def test_22_positive_negative_balance_reported():
    labs = [_lab("p1", "ra", "same_event"), _lab("p1", "rb", "same_event"),
            _lab("p2", "ra", "different_event"), _lab("p2", "rb", "different_event")]
    r = resolve_label_operations(labs, label_source=LABEL_SOURCE_PRODUCTION)
    pf = build_calibration_preflight(r)
    assert pf["positive_negative_balance"]["positive"] == 1
    assert pf["positive_negative_balance"]["negative"] == 1


def test_23_hard_negative_coverage_reported():
    r = resolve_label_operations([], label_source=LABEL_SOURCE_PRODUCTION)
    pf = build_calibration_preflight(r, hard_negative_count=3)
    assert pf["hard_negative_coverage"]["count"] == 3
    assert pf["hard_negative_coverage"]["sufficient"] is False


def test_24_production_gold_zero_without_real_labels():
    out = run_reviewer_label_operations(queue=_queue())
    assert out["production_gold_count"] == 0
    assert out["gold_ready"] is False
    assert "no_labels" in out["block_reasons"]


def test_25_calibration_not_ready_without_gold():
    r = resolve_label_operations([], label_source=LABEL_SOURCE_PRODUCTION)
    pf = build_calibration_preflight(r)
    assert pf["calibration_ready"] is False


def test_26_merge_gate_not_ready_without_thresholds():
    labs = [_lab("p1", "ra", "same_event"), _lab("p1", "rb", "same_event")]
    r = resolve_label_operations(labs, label_source=LABEL_SOURCE_PRODUCTION)
    pf = build_calibration_preflight(r)
    assert pf["merge_gate_ready"] is False   # 표본 floor(200) 미충족


def test_27_precision_fpr_denominator_readiness_reported():
    r = resolve_label_operations([], label_source=LABEL_SOURCE_PRODUCTION)
    pf = build_calibration_preflight(r)
    assert pf["precision_denominator_ready"] is False
    assert pf["fpr_denominator_ready"] is False
    assert "min_live_gold" in pf


# ── §10 28-34: optional real label path ─────────────────────────────────────────────────────────────────
def test_28_missing_label_file_no_labels():
    info = import_reviewer_labels(None, label_source=LABEL_SOURCE_PRODUCTION)
    assert info["block_reason"] == "no_labels"
    assert info["label_file_present"] is False


def test_29_malformed_label_file_rejected(tmp_path):
    f = tmp_path / "bad.jsonl"
    f.write_text("{not valid json\n", encoding="utf-8")
    info = import_reviewer_labels(f, label_source=LABEL_SOURCE_PRODUCTION)
    assert info["label_schema_valid"] is False
    assert info["block_reason"] == "malformed_label_file"


def test_30_forbidden_field_file_rejected(tmp_path):
    f = _write_jsonl(tmp_path / "f.jsonl", [_row("p1", "ra", "same_event", extra={"predicted_status": "likely_same"})])
    info = import_reviewer_labels(f, label_source=LABEL_SOURCE_PRODUCTION)
    assert info["block_reason"] == "forbidden_field_in_label"


def test_31_valid_label_file_imported(tmp_path):
    f = _write_jsonl(tmp_path / "v.jsonl",
                     [_row("p1", "ra", "same_event"), _row("p1", "rb", "same_event")])
    out = run_reviewer_label_operations(
        queue=_queue(), label_path=f, label_source=LABEL_SOURCE_PRODUCTION)
    assert out["label_file_present"] is True
    assert out["label_count"] == 2
    assert out["production_gold_count"] == 1


def test_32_label_source_separation_preserved(tmp_path):
    f = _write_jsonl(tmp_path / "t.jsonl",
                     [_row("p1", "ra", "same_event"), _row("p1", "rb", "same_event")])
    # test_fixture → 절대 production gold 아님(경로 검증만).
    out = run_reviewer_label_operations(queue=_queue(), label_path=f, label_source=LABEL_SOURCE_TEST)
    assert out["label_source"] == LABEL_SOURCE_TEST
    assert out["production_gold_count"] == 0


def test_33_dataset_source_preserved():
    labs = [_lab("p1", "ra", "same_event", ds=SOURCE_LIVE), _lab("p1", "rb", "same_event", ds=SOURCE_LIVE)]
    r = resolve_label_operations(labs, label_source=LABEL_SOURCE_PRODUCTION)
    assert r["production_gold"][0].dataset_source == SOURCE_LIVE


def test_34_language_preserved_for_korean():
    labs = [_lab("p1", "ra", "same_event", lang="ko"), _lab("p1", "rb", "same_event", lang="ko")]
    r = resolve_label_operations(labs, label_source=LABEL_SOURCE_PRODUCTION)
    pf = build_calibration_preflight(r)
    assert pf["language_distribution"].get("ko") == 1
    assert pf["korean_gold_count"] == 1


# ── §10 35-41: no merge / no LLM / no DB / secret boundary ───────────────────────────────────────────────
def test_35_merge_allowed_false():
    out = run_reviewer_label_operations(queue=_queue())
    assert out["merge_allowed"] is False
    assert out["no_merge_without_gold"] is True


def test_36_no_public_intelligence_unit():
    out = run_reviewer_label_operations(queue=_queue())
    assert out["no_public_intelligence_unit"] is True


def test_37_no_db_write():
    out = run_reviewer_label_operations(queue=_queue())
    assert out["db_write"] is False


def test_38_no_llm_invoked():
    out = run_reviewer_label_operations(queue=_queue())
    assert out["llm_invoked"] is False


def test_39_no_embedding_invoked():
    out = run_reviewer_label_operations(queue=_queue())
    assert out["embedding_invoked"] is False


def test_40_no_env_or_secret_access_in_source():
    # 구조적: 모듈이 .env/os.environ/getenv/dotenv 를 읽지 않는다(secret 경계).
    src = _MODULE.read_text(encoding="utf-8")
    for needle in ("os.environ", "getenv", "dotenv", "open(", ".env"):
        assert needle not in src, f"module must not access env/secret: {needle}"


def test_41_output_json_serializable_no_secret_leak():
    import json
    labs = [_lab("p1", "ra", "same_event"), _lab("p1", "rb", "same_event")]
    out = run_reviewer_label_operations(
        queue=_queue(), reviewer_labels=labs, label_source=LABEL_SOURCE_PRODUCTION)
    blob = json.dumps(out, default=str)
    for forbidden in FORBIDDEN_LABEL_FIELDS:
        # forbidden field 가 output 키로 새지 않음(값은 애초에 없음).
        assert f'"{forbidden}"' not in blob


# ── 회귀 cross-check(42-43; 44-74 는 전 suite) ──────────────────────────────────────────────────────────
def test_42_adr65_scorer_still_imports():
    # 모듈 top-level import 가 collection 단계에서 scorer 임포트 가능성을 잠근다(새 모듈과 공존).
    assert callable(run_semantic_candidate_scoring)


def test_43_queue_build_unchanged_by_new_module():
    q = _queue()
    assert q["no_merge_without_gold"] is True
    assert q["llm_invoked"] is False


# ── 추가 잠금: validation/guard ────────────────────────────────────────────────────────────────────────
def test_44_invalid_label_source_rejected():
    with pytest.raises(ValueError):
        import_reviewer_labels(None, label_source="bogus_source")


def test_45_empty_queue_blocks_no_packet():
    out = run_reviewer_label_operations(queue={})
    assert "no_packet" in out["block_reasons"]
    assert out["packet_exportable"] is False


def test_46_pseudonym_deterministic_and_unlinkable_surface():
    a = pseudonymize_reviewer_id("xyz@example.com")
    assert a == pseudonymize_reviewer_id("xyz@example.com")
    assert "xyz@example.com" not in a and a.startswith("rv_")


# ── HIGH 감사 fix-lock: human-only gold 불변(in-memory·file 양 경로) ──────────────────────────────────────
def _model_lab(pid, rid, label, *, kind="model"):
    return ReviewerLabel(
        pair_id=pid, reviewer_id=rid, review_round=1, label=label, label_confidence="high",
        reviewed_at="2026-06-22T00:00:00+00:00", language="en",
        source_type_left="article", source_type_right="article",
        title_left="a", title_right="b",
        observed_at_left="2026-06-22", observed_at_right="2026-06-22",
        reviewer_kind=kind, dataset_source=SOURCE_LIVE)


def test_47_resolve_rejects_model_kind_label():
    # cardinal: model/self/LLM label 은 gold 불가 — resolve chokepoint 가 fail-loud.
    labs = [_model_lab("p1", "m1", "same_event"), _model_lab("p1", "m2", "same_event")]
    with pytest.raises(ValueError, match="human only"):
        resolve_label_operations(labs, label_source=LABEL_SOURCE_PRODUCTION)


def test_48_run_in_memory_model_label_not_gold():
    # in-memory 경로(파일 가드 우회)에서도 model label 2개 만장일치가 production gold 로 승격 안 됨.
    labs = [_model_lab("p1", "m1", "same_event"), _model_lab("p1", "m2", "same_event")]
    out = run_reviewer_label_operations(
        queue=_queue(), reviewer_labels=labs, label_source=LABEL_SOURCE_PRODUCTION)
    assert out["production_gold_count"] == 0
    assert out["gold_ready"] is False
    assert "model_label_rejected" in out["block_reasons"]
    assert out["label_schema_valid"] is False


def test_49_file_model_label_classified(tmp_path):
    # 파일 경로 model label → load fail-loud → model_label_rejected 로 분류(진단 정직).
    f = _write_jsonl(tmp_path / "m.jsonl",
                     [_row("p1", "m1", "same_event", extra={"reviewer_kind": "model"})])
    info = import_reviewer_labels(f, label_source=LABEL_SOURCE_PRODUCTION)
    assert info["label_schema_valid"] is False
    assert info["block_reason"] == "model_label_rejected"
