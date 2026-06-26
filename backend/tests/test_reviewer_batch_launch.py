"""ADR#67 — reviewer batch launch pack + intake validation loop 테스트(병합 0·LLM 0·embedding 0·DB 0).

정책을 잠근다(§11 1-46): batch launch pack(packet/template/instruction/manifest/batch_id/validation command/
no-labels)·reviewer-facing secrecy(score/predicted_status/raw body/secret 0·reviewer_id pseudonym)·assignment
policy(pair 당 2명·capacity·hard negative/top-k·pseudonym·raw roster 미commit)·label template/intake(forbidden
field/malformed/duplicate/unknown pair_id/non-human 거부)·agreement/calibration(single/unanimous/conflict/
adjudicated·synthetic≠production·calibration/merge_gate False without floors·korean floor)·no-merge/no-LLM/no-DB.
회귀(47-80)는 전 suite 가 담당. 추가: labeler vocab 정규화·production label path·required-keys drift lock.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.services.identity_eval_dataset import LABEL_AMBIGUOUS, LABEL_INSUFFICIENT
from backend.app.services.identity_human_labeling import (
    _REVIEWER_REQUIRED_KEYS,
    REVIEWER_ALLOWED_KEYS,
    SOURCE_LIVE,
    SOURCE_SYNTHETIC,
    _validate_reviewer_row,
)
from backend.app.tools.near_match_reviewer_queue import build_near_match_reviewer_queue
from backend.app.tools.reviewer_batch_launch import (
    _INTAKE_REQUIRED_KEYS,
    INTAKE_AWAITING,
    INTAKE_IMPORTED,
    INTAKE_INVALID,
    INTAKE_PRESENT,
    LABELER_LABELS,
    build_assignment_manifest,
    build_intake_plan,
    build_label_template,
    build_reviewer_instruction,
    normalize_label,
    run_reviewer_batch_launch,
    validate_label_intake,
)
from backend.app.tools.reviewer_label_operations import (
    LABEL_SOURCE_PRODUCTION,
    LABEL_SOURCE_SYNTHETIC,
    LABEL_SOURCE_TEST,
)
from backend.app.tools.source_overlap_discovery import (
    build_captured_overlap_fixture,
    discover_overlap,
)

_MODULE = Path(__file__).resolve().parents[1] / "app" / "tools" / "reviewer_batch_launch.py"


# ── helpers ───────────────────────────────────────────────────────────────────────────────────────────
def _queue(**kw):
    disc = discover_overlap(build_captured_overlap_fixture())
    return build_near_match_reviewer_queue(disc, packet_id="t_batch_pkt", **kw)


def _pids(queue, n=2):
    return list(queue.get("queue_pair_ids") or [])[:n]


def _row(pid, rid, label, *, extra=None, lang="en", ds=SOURCE_LIVE, rnd=1):
    """labeler-vocab label row(intake 필수 키 전부). label ∈ LABELER_LABELS."""
    r = {
        "pair_id": pid, "reviewer_id": rid, "review_round": rnd, "label": label,
        "label_confidence": "high", "reviewed_at": "2026-06-26T00:00:00+00:00", "language": lang,
        "source_type_left": "article", "source_type_right": "article",
        "title_left": "headline left", "title_right": "headline right",
        "observed_at_left": "2026-06-22", "observed_at_right": "2026-06-22",
        "dataset_source": ds,
    }
    if extra:
        r.update(extra)
    return r


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return path


def _launch(**kw):
    return run_reviewer_batch_launch(queue=_queue(), batch_id="b1", packet_id="t_batch_pkt", **kw)


# ── §11 1-8: batch launch ──────────────────────────────────────────────────────────────────────────────
def test_01_packet_exported():
    assert _launch()["packet_exported"] is True


def test_02_label_template_exported():
    out = _launch()
    assert out["label_template_exported"] is True


def test_03_reviewer_instruction_exported():
    assert _launch()["reviewer_instruction_exported"] is True


def test_04_assignment_manifest_exported():
    assert _launch()["assignment_manifest_exported"] is True


def test_05_output_has_batch_id():
    assert _launch()["batch_id"] == "b1"


def test_06_output_has_packet_id():
    assert _launch()["packet_id"] == "t_batch_pkt"


def test_07_output_has_validation_command():
    cmd = _launch()["validation_command"]
    assert "--validate" in cmd and "reviewer_batch_launch" in cmd


def test_08_no_label_file_awaiting():
    out = _launch()
    assert out["intake_status"] == INTAKE_AWAITING
    assert "awaiting_labels" in out["block_reasons"]
    assert out["label_import_attempted"] is False


# ── §11 9-15: reviewer-facing secrecy ──────────────────────────────────────────────────────────────────
def test_09_template_no_semantic_score():
    for r in build_label_template(_queue()):
        assert "semantic_score" not in r and "score" not in r and "model_score" not in r


def test_10_template_no_predicted_status():
    for r in build_label_template(_queue()):
        assert "predicted_status" not in r and "sampling_bucket" not in r


def test_11_template_no_model_rationale():
    for r in build_label_template(_queue()):
        assert "model_rationale" not in r and "reasons_internal" not in r


def test_12_template_no_raw_body():
    for r in build_label_template(_queue()):
        assert "raw_body" not in r and "body" not in r and "content" not in r


def test_13_template_no_secret_api_key():
    for r in build_label_template(_queue()):
        assert "api_key" not in r and "secret" not in r and "provider_secret" not in r


def test_14_instruction_no_hidden_score_rank():
    ins = build_reviewer_instruction()
    assert ins["model_score_shown"] is False
    assert ins["predicted_status_shown"] is False
    assert ins["hidden_candidate_rank_shown"] is False
    # 숫자 score 값이 instruction 최상위 어디에도 없어야(model score 누출 0·CR-3 vacuous 수정).
    assert not any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in ins.values())


def test_15_reviewer_id_pseudonymous_in_template():
    for r in build_label_template(_queue()):
        assert r["reviewer_id"].startswith("rv_")
        assert "reviewer_pool_slot" not in r["reviewer_id"]


# ── §11 16-22: assignment policy ───────────────────────────────────────────────────────────────────────
def test_16_each_pair_two_reviewers():
    m = build_assignment_manifest(_queue(), batch_id="b")
    assert m["reviewer_count_assigned"] >= 2
    assert m["duplicate_assignment_coverage"] == 1.0


def test_17_insufficient_capacity_reported():
    q = _queue()
    rid0 = q["packet_rows"][0]["reviewer_id"]
    q1 = dict(q)
    q1["packet_rows"] = [r for r in q["packet_rows"] if r["reviewer_id"] == rid0]
    m = build_assignment_manifest(q1, batch_id="b")
    assert m["capacity_status"] == "insufficient_reviewer_capacity"
    assert m["reviewer_count_assigned"] == 1


def test_18_hard_negatives_included():
    q = _queue(include_synthetic_hard_negatives=True)
    m = build_assignment_manifest(q, batch_id="b")
    assert m["hard_negative_count"] >= 1


def test_19_top_k_candidates_included():
    m = build_assignment_manifest(_queue(), batch_id="b")
    assert m["top_k_candidate_count"] >= 1


def test_20_assignments_balanced():
    m = build_assignment_manifest(_queue(), batch_id="b")
    # 모든 pair 가 동일 reviewer 수(round-robin)로 균형.
    assert m["assignments_count"] == m["pairs_count"] * m["reviewer_count_required"]


def test_21_pseudonymous_reviewer_ids():
    m = build_assignment_manifest(_queue(), batch_id="b")
    assert all(a["reviewer_pseudonym"].startswith("rv_") for a in m["assignments"])
    assert all(p.startswith("rv_") for p in m["pseudonymous_reviewers"])


def test_22_raw_roster_not_committed():
    m = build_assignment_manifest(_queue(), batch_id="b")
    assert m["raw_reviewer_pii_committed"] is False
    blob = json.dumps(m)
    assert "reviewer_pool_slot" not in blob   # raw queue reviewer id 미노출.


# ── §11 23-30: label template / intake ─────────────────────────────────────────────────────────────────
def test_23_template_fields_allowed_only():
    for r in build_label_template(_queue()):
        assert set(r) <= REVIEWER_ALLOWED_KEYS


def test_24_forbidden_field_in_label_rejected():
    q = _queue()
    pid = _pids(q)[0]
    rows = [_row(pid, "rev_a", "same_event", extra={"semantic_score": 0.9})]
    rep = validate_label_intake(rows, known_pair_ids=set(q["queue_pair_ids"]))
    assert rep["schema_valid"] is False
    assert "semantic_score" in rep["forbidden_fields_found"]


def test_25_missing_label_file_awaiting(tmp_path):
    out = _launch(label_path=tmp_path / "nope.jsonl")
    assert out["intake_status"] == INTAKE_AWAITING
    assert "label_file_missing" in out["block_reasons"]


def test_26_malformed_label_invalid():
    q = _queue()
    pid = _pids(q)[0]
    rows = [_row(pid, "rev_a", "not_a_label")]
    out = run_reviewer_batch_launch(queue=q, batch_id="b", label_rows=rows)
    assert out["intake_status"] == INTAKE_INVALID
    assert "invalid_labels" in out["block_reasons"]


def test_27_valid_label_imported():
    q = _queue()
    p0, p1 = _pids(q)
    rows = [_row(p0, "rev_a", "same_event"), _row(p0, "rev_b", "same_event")]
    out = run_reviewer_batch_launch(queue=q, batch_id="b", label_rows=rows,
                                    label_source=LABEL_SOURCE_SYNTHETIC)
    assert out["intake_status"] == INTAKE_IMPORTED
    assert out["label_import_attempted"] is True


def test_28_duplicate_labels_handled():
    q = _queue()
    pid = _pids(q)[0]
    rows = [_row(pid, "rev_a", "same_event"), _row(pid, "rev_a", "same_event")]
    rep = validate_label_intake(rows, known_pair_ids=set(q["queue_pair_ids"]))
    assert rep["schema_valid"] is False
    assert any(e["reason"] == "duplicate_label" for e in rep["errors"])


def test_29_unknown_pair_id_rejected():
    q = _queue()
    rows = [_row("pair:does_not_exist", "rev_a", "same_event")]
    rep = validate_label_intake(rows, known_pair_ids=set(q["queue_pair_ids"]))
    assert rep["schema_valid"] is False
    assert "pair:does_not_exist" in rep["unknown_pair_ids"]


def test_30_non_human_label_rejected():
    q = _queue()
    pid = _pids(q)[0]
    rows = [_row(pid, "model_x", "same_event", extra={"reviewer_kind": "model"})]
    rep = validate_label_intake(rows, known_pair_ids=set(q["queue_pair_ids"]))
    assert rep["schema_valid"] is False
    assert any(e["reason"] == "model_label_rejected" for e in rep["errors"])


# ── §11 31-39: agreement / calibration ─────────────────────────────────────────────────────────────────
def test_31_single_reviewer_insufficient():
    q = _queue()
    pid = _pids(q)[0]
    out = run_reviewer_batch_launch(queue=q, batch_id="b",
                                    label_rows=[_row(pid, "rev_a", "same_event")])
    assert out["production_gold_count"] == 0
    assert out["synthetic_gold_count"] == 0   # 1명 → gold 아님.


def test_32_two_unanimous_gold_candidate():
    q = _queue()
    pid = _pids(q)[0]
    out = run_reviewer_batch_launch(queue=q, batch_id="b",
                                    label_rows=[_row(pid, "rev_a", "same_event"),
                                                _row(pid, "rev_b", "same_event")],
                                    label_source=LABEL_SOURCE_SYNTHETIC)
    assert out["synthetic_gold_count"] >= 1


def test_33_conflict_pending():
    q = _queue()
    pid = _pids(q)[0]
    out = run_reviewer_batch_launch(queue=q, batch_id="b",
                                    label_rows=[_row(pid, "rev_a", "same_event"),
                                                _row(pid, "rev_b", "different_event")])
    assert out["conflict_count"] >= 1


def test_34_adjudicated_gold_candidate():
    q = _queue()
    pid = _pids(q)[0]
    out = run_reviewer_batch_launch(
        queue=q, batch_id="b",
        label_rows=[_row(pid, "rev_a", "same_event"), _row(pid, "rev_b", "different_event")],
        adjudications={pid: {"label": "same_event", "adjudicator_kind": "human", "adjudicated_by": "lead"}},
        label_source=LABEL_SOURCE_SYNTHETIC)
    assert out["synthetic_gold_count"] >= 1
    assert out["conflict_count"] == 0   # adjudication 으로 해소.


def test_35_synthetic_stays_synthetic():
    q = _queue()
    pid = _pids(q)[0]
    out = run_reviewer_batch_launch(queue=q, batch_id="b",
                                    label_rows=[_row(pid, "rev_a", "same_event", ds=SOURCE_SYNTHETIC),
                                                _row(pid, "rev_b", "same_event", ds=SOURCE_SYNTHETIC)],
                                    label_source=LABEL_SOURCE_SYNTHETIC)
    assert out["production_gold_count"] == 0
    assert out["synthetic_gold_count"] >= 1


def test_36_production_gold_zero_without_real():
    assert _launch()["production_gold_count"] == 0


def test_37_calibration_ready_false_without_floors():
    q = _queue()
    p0, p1 = _pids(q)
    out = run_reviewer_batch_launch(queue=q, batch_id="b",
                                    label_rows=[_row(p0, "rev_a", "same_event"),
                                                _row(p0, "rev_b", "same_event")],
                                    label_source=LABEL_SOURCE_PRODUCTION)
    assert out["calibration_ready"] is False   # floor 200 미충족.


def test_38_merge_gate_ready_false():
    assert _launch()["merge_gate_ready"] is False


def test_39_korean_calibration_target_present():
    out = _launch()
    assert out["korean_calibration_target"] == 50
    # language_distribution 보존(calibration 용).
    assert isinstance(out["language_distribution"], dict)


# ── §11 40-46: no merge / no LLM / no DB / secret ──────────────────────────────────────────────────────
def test_40_merge_allowed_false():
    assert _launch()["merge_allowed"] is False


def test_41_no_public_iu():
    assert _launch()["no_public_intelligence_unit"] is True


def test_42_db_write_false():
    assert _launch()["db_write"] is False


def test_43_llm_not_invoked():
    assert _launch()["llm_invoked"] is False


def test_44_embedding_not_invoked():
    assert _launch()["embedding_invoked"] is False


def test_45_env_not_read():
    src = _MODULE.read_text(encoding="utf-8")
    assert "os.environ" not in src
    assert "os.getenv" not in src
    assert "dotenv" not in src
    assert "load_env" not in src


def test_46_secret_absent():
    out = _launch()
    assert out["secret_absent"] is True
    assert out["raw_body_absent"] is True


# ── 추가: labeler vocab 정규화·production path·drift lock·회귀 cross-check ──────────────────────────────
def test_47_intake_required_keys_lock():
    # _INTAKE_REQUIRED_KEYS 가 frozen _REVIEWER_REQUIRED_KEYS 와 drift 하면 즉시 실패.
    assert _INTAKE_REQUIRED_KEYS == _REVIEWER_REQUIRED_KEYS


def test_48_labeler_vocab_normalization():
    assert normalize_label("unsure") == LABEL_INSUFFICIENT
    assert normalize_label("needs_review") == LABEL_AMBIGUOUS
    assert normalize_label("same_event") == "same_event"
    assert normalize_label("different_event") == "different_event"
    with pytest.raises(ValueError):
        normalize_label("ambiguous")   # canonical token 은 labeler 어휘 아님(정규화 입력 거부).


def test_49_unsure_needs_review_not_gold():
    q = _queue()
    pid = _pids(q)[0]
    # 2명 만장일치 'needs_review'(→ambiguous) — gold 아님(same/different 만 승격).
    out = run_reviewer_batch_launch(queue=q, batch_id="b",
                                    label_rows=[_row(pid, "rev_a", "needs_review"),
                                                _row(pid, "rev_b", "needs_review")],
                                    label_source=LABEL_SOURCE_PRODUCTION, dataset_source=SOURCE_LIVE)
    assert out["production_gold_count"] == 0
    assert out["synthetic_gold_count"] == 0


def test_50_production_label_path_counts_gold():
    q = _queue()
    pid = _pids(q)[0]
    # label_source=production + live_derived + 2 만장일치 human → production gold 1(단 calibration False).
    out = run_reviewer_batch_launch(queue=q, batch_id="b",
                                    label_rows=[_row(pid, "rev_a", "same_event", ds=SOURCE_LIVE),
                                                _row(pid, "rev_b", "same_event", ds=SOURCE_LIVE)],
                                    label_source=LABEL_SOURCE_PRODUCTION, dataset_source=SOURCE_LIVE)
    assert out["production_gold_count"] == 1
    assert out["calibration_ready"] is False
    assert out["merge_gate_ready"] is False
    assert out["merge_allowed"] is False


def test_51_test_fixture_not_production_gold():
    q = _queue()
    pid = _pids(q)[0]
    out = run_reviewer_batch_launch(queue=q, batch_id="b",
                                    label_rows=[_row(pid, "rev_a", "same_event"),
                                                _row(pid, "rev_b", "same_event")],
                                    label_source=LABEL_SOURCE_TEST)
    assert out["production_gold_count"] == 0


def test_52_order_invariance():
    q = _queue()
    pid = _pids(q)[0]
    rows = [_row(pid, "rev_a", "same_event"), _row(pid, "rev_b", "same_event")]
    a = run_reviewer_batch_launch(queue=q, batch_id="b", label_rows=rows,
                                  label_source=LABEL_SOURCE_PRODUCTION, dataset_source=SOURCE_LIVE)
    b = run_reviewer_batch_launch(queue=q, batch_id="b", label_rows=list(reversed(rows)),
                                  label_source=LABEL_SOURCE_PRODUCTION, dataset_source=SOURCE_LIVE)
    assert a["production_gold_count"] == b["production_gold_count"]
    assert a["synthetic_gold_count"] == b["synthetic_gold_count"]


def test_53_label_file_path_imported(tmp_path):
    q = _queue()
    p0 = _pids(q)[0]
    path = _write_jsonl(tmp_path / "labels.jsonl",
                        [_row(p0, "rev_a", "same_event"), _row(p0, "rev_b", "same_event")])
    out = run_reviewer_batch_launch(queue=q, batch_id="b", label_path=path,
                                    label_source=LABEL_SOURCE_SYNTHETIC)
    assert out["intake_status"] == INTAKE_IMPORTED
    assert out["label_file_present"] is True
    assert out["synthetic_gold_count"] >= 1


def test_54_intake_plan_paths():
    plan = build_intake_plan("batch_x", pseudonyms=["rv_aaa", "rv_bbb"])
    assert plan["intake_directory"].endswith("batch_x/intake")
    assert all(f.startswith("batch_x__") and f.endswith("labels.jsonl")
               for f in plan["expected_label_files"])


def test_55_adr66_ops_intact():
    # ADR#66 run_reviewer_label_operations 가 batch launch 와 독립적으로 유지(회귀).
    from backend.app.tools.reviewer_label_operations import run_reviewer_label_operations
    out = run_reviewer_label_operations(queue=_queue(), label_source=LABEL_SOURCE_SYNTHETIC)
    assert out["merge_allowed"] is False
    assert out["production_gold_count"] == 0


def test_56_adr60_checklist_in_output():
    out = _launch()
    cl = out["operating_checklist"]
    assert cl["hidden_prediction_verified"] is True
    assert cl["raw_body_absent_verified"] is True


def test_57_labeler_labels_are_four():
    assert LABELER_LABELS == frozenset({"same_event", "different_event", "unsure", "needs_review"})


# ── 감사 fix-lock(adversarial B-1/B-2/B-3 + code-review CR-1/CR-4) ──────────────────────────────────────
def test_58_non_decisive_gold_count_accurate():
    q = _queue()
    pid = _pids(q)[0]
    out = run_reviewer_batch_launch(queue=q, batch_id="b",
                                    label_rows=[_row(pid, "rev_a", "needs_review"),
                                                _row(pid, "rev_b", "needs_review")],
                                    label_source=LABEL_SOURCE_PRODUCTION, dataset_source=SOURCE_LIVE)
    assert out["production_gold_count"] == 0
    assert out["synthetic_gold_count"] == 0
    assert out["non_decisive_gold_count"] >= 1   # unanimous ambiguous = resolved gold·decisive 아님.


def test_59_empty_label_rows_labels_present():
    out = run_reviewer_batch_launch(queue=_queue(), batch_id="b", label_rows=[])
    assert out["intake_status"] == INTAKE_PRESENT   # 행 있으나 유효 라벨 0.
    assert "no_labels" in out["block_reasons"]
    assert out["label_import_attempted"] is True


def test_60_run_propagates_forbidden_block_reason():
    q = _queue()
    pid = _pids(q)[0]
    out = run_reviewer_batch_launch(queue=q, batch_id="b",
                                    label_rows=[_row(pid, "rev_a", "same_event",
                                                     extra={"semantic_score": 0.9})])
    assert out["intake_status"] == INTAKE_INVALID
    assert "forbidden_field_in_label" in out["block_reasons"]


def test_61_run_propagates_model_and_unknown_block_reasons():
    q = _queue()
    pid = _pids(q)[0]
    m = run_reviewer_batch_launch(queue=q, batch_id="b",
                                  label_rows=[_row(pid, "mdl", "same_event",
                                                   extra={"reviewer_kind": "model"})])
    assert "model_label_rejected" in m["block_reasons"]
    u = run_reviewer_batch_launch(queue=q, batch_id="b",
                                  label_rows=[_row("pair:nope", "rev_a", "same_event")])
    assert "unknown_pair_id" in u["block_reasons"]


def test_62_agreement_rate_in_output():
    q = _queue()
    pid = _pids(q)[0]
    out = run_reviewer_batch_launch(queue=q, batch_id="b",
                                    label_rows=[_row(pid, "rev_a", "same_event"),
                                                _row(pid, "rev_b", "same_event")],
                                    label_source=LABEL_SOURCE_PRODUCTION, dataset_source=SOURCE_LIVE)
    assert out["agreement_rate"] == 1.0   # 2인 만장일치.


def test_63_invalid_reviewed_at_rejected():
    q = _queue()
    pid = _pids(q)[0]
    rep = validate_label_intake([_row(pid, "rev_a", "same_event", extra={"reviewed_at": "garbage"})],
                                known_pair_ids=set(q["queue_pair_ids"]))
    assert rep["schema_valid"] is False
    assert any(e["reason"] == "invalid_reviewed_at" for e in rep["errors"])


def test_64_invalid_dataset_source_and_risk_tags_rejected():
    q = _queue()
    pid = _pids(q)[0]
    r1 = validate_label_intake([_row(pid, "rev_a", "same_event", extra={"dataset_source": "bogus"})],
                               known_pair_ids=set(q["queue_pair_ids"]))
    assert r1["schema_valid"] is False
    assert any(e["reason"] == "invalid_dataset_source" for e in r1["errors"])
    r2 = validate_label_intake([_row(pid, "rev_a", "same_event", extra={"risk_tags": [1, 2]})],
                               known_pair_ids=set(q["queue_pair_ids"]))
    assert r2["schema_valid"] is False
    assert any(e["reason"] == "invalid_risk_tags" for e in r2["errors"])


def test_65_intake_validation_equivalent_to_frozen():
    # bad reviewed_at: intake 와 frozen `_validate_reviewer_row` 둘 다 거부(검증 동등성·키만 잠그지 않음).
    q = _queue()
    pid = _pids(q)[0]
    bad = _row(pid, "rev_a", "same_event", extra={"reviewed_at": "not-a-date"})
    rep = validate_label_intake([bad], known_pair_ids={pid})
    assert rep["schema_valid"] is False
    with pytest.raises(ValueError):
        _validate_reviewer_row(dict(bad), seen=set())   # canonical same_event→frozen 도 reviewed_at 거부.


def test_66_no_raw_reviewer_pii_in_output():
    q = _queue()
    pid = _pids(q)[0]
    out = run_reviewer_batch_launch(queue=q, batch_id="b",
                                    label_rows=[_row(pid, "secret_reviewer_alice", "same_event"),
                                                _row(pid, "secret_reviewer_bob", "same_event")],
                                    label_source=LABEL_SOURCE_PRODUCTION, dataset_source=SOURCE_LIVE)
    blob = json.dumps(out, default=str)
    assert "secret_reviewer_alice" not in blob   # raw reviewer_id 미노출(normalized_rows 제거).
    assert "normalized_rows" not in (out.get("intake_report") or {})
    assert out["production_gold_provenance_verified"] is False   # 선언 기반 표면화(B-1).


def test_67_adjudication_labeler_vocab_no_crash():
    q = _queue()
    pid = _pids(q)[0]
    # 사람 lead 가 labeler vocab(needs_review)로 adjudication → 크래시 없이 정규화(CR-1).
    out = run_reviewer_batch_launch(
        queue=q, batch_id="b",
        label_rows=[_row(pid, "rev_a", "same_event"), _row(pid, "rev_b", "different_event")],
        adjudications={pid: {"label": "needs_review", "adjudicator_kind": "human", "adjudicated_by": "lead"}},
        label_source=LABEL_SOURCE_PRODUCTION, dataset_source=SOURCE_LIVE)
    assert out["intake_status"] == INTAKE_IMPORTED
    assert out["conflict_count"] == 0            # adjudication 으로 해소.
    assert out["production_gold_count"] == 0     # needs_review→ambiguous=decisive 아님.
