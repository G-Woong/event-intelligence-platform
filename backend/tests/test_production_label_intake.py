"""ADR#68 — first production labels import pilot + intake/gold/calibration dry-run 테스트(병합 0·LLM 0·embedding 0·DB 0).

정책을 잠근다(§10 1-39): no-labels(awaiting_production_labels·정직·operator next action)·labels-present
validation(valid import·malformed/forbidden/raw_body/secret/score/unknown pair_id/duplicate/non-human 거부·
reviewer PII 미노출)·gold policy(single≠gold·2인 same→positive·different→negative·conflict→conflict_pending·
adjudicated→gold·unsure/needs_review≠gold·synthetic/model≠production·decisive only)·calibration delta(before/after·
positive/negative/korean delta·precision/FPR denominator readiness·merge_gate False without floors·next_needed)·
no-merge/no-LLM/no-DB/secret. filesystem 다중파일 스캔(basename only·malformed fail-loud·empty→awaiting).
회귀(40-74·ADR#42~#67 유지)는 전 suite 가 담당.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.app.services.identity_human_labeling import SOURCE_LIVE, SOURCE_SYNTHETIC
from backend.app.tools.near_match_reviewer_queue import build_near_match_reviewer_queue
from backend.app.tools.production_label_intake import (
    FAILURE_CLASSES,
    INTAKE_AWAITING_PRODUCTION,
    INTAKE_CALIBRATION_PENDING,
    INTAKE_CONFLICT_PENDING,
    INTAKE_INVALID,
    INTAKE_STATES,
    OPERATION_NAME,
    build_calibration_delta,
    build_no_labels_report,
    run_production_label_intake,
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

_MODULE = Path(__file__).resolve().parents[1] / "app" / "tools" / "production_label_intake.py"


# ── helpers ───────────────────────────────────────────────────────────────────────────────────────────
def _queue(**kw):
    disc = discover_overlap(build_captured_overlap_fixture())
    return build_near_match_reviewer_queue(disc, packet_id="t_intake_pkt", **kw)


def _pids(queue, n=2):
    return list(queue.get("queue_pair_ids") or [])[:n]


def _row(pid, rid, label, *, extra=None, lang="en", ds=SOURCE_LIVE, rnd=1):
    """labeler-vocab label row(intake 필수 키 전부). label ∈ {same_event,different_event,unsure,needs_review}."""
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


def _run(**kw):
    return run_production_label_intake(queue=_queue(), batch_id="b1", packet_id="t_intake_pkt", **kw)


def _two_same(pid, *, lang="en", ds=SOURCE_LIVE):
    return [_row(pid, "rev_a", "same_event", lang=lang, ds=ds),
            _row(pid, "rev_b", "same_event", lang=lang, ds=ds)]


def _two_diff(pid, *, lang="en", ds=SOURCE_LIVE):
    return [_row(pid, "rev_a", "different_event", lang=lang, ds=ds),
            _row(pid, "rev_b", "different_event", lang=lang, ds=ds)]


# ── §10 1-6: no-labels intake ──────────────────────────────────────────────────────────────────────────
def test_01_no_labels_awaiting_production(tmp_path):
    out = _run(intake_directory=tmp_path / "empty")
    assert out["intake_status"] == INTAKE_AWAITING_PRODUCTION
    assert out["operation_name"] == OPERATION_NAME


def test_02_no_labels_production_gold_zero(tmp_path):
    out = _run(intake_directory=tmp_path / "empty")
    assert out["production_gold_count"] == 0


def test_03_no_labels_calibration_false(tmp_path):
    assert _run(intake_directory=tmp_path / "empty")["calibration_ready"] is False


def test_04_no_labels_merge_gate_false(tmp_path):
    assert _run(intake_directory=tmp_path / "empty")["merge_gate_ready"] is False


def test_05_no_labels_actionable_next_actions(tmp_path):
    out = _run(intake_directory=tmp_path / "empty")
    assert "no_production_labels" in out["block_reasons"]
    rep = out["no_labels_report"]
    assert rep is not None and len(rep["operator_next_actions"]) >= 5


def test_06_no_labels_validation_command_emitted(tmp_path):
    out = _run(intake_directory=tmp_path / "empty")
    assert "--validate" in out["validation_command"]
    assert out["label_import_attempted"] is False


# ── §10 7-16: labels-present validation ──────────────────────────────────────────────────────────────
def test_07_valid_production_file_imports(tmp_path):
    q = _queue()
    pid = _pids(q)[0]
    d = tmp_path / "intake"
    d.mkdir()
    _write_jsonl(d / "b1__rv_x__labels.jsonl", _two_same(pid))
    out = run_production_label_intake(queue=q, batch_id="b1", intake_directory=d,
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["intake_status"] in (INTAKE_CALIBRATION_PENDING,)   # imported·충돌0·floor 미달.
    assert out["production_gold_count"] == 1
    assert out["label_files_found"] == ["b1__rv_x__labels.jsonl"]


def test_08_malformed_file_rejected(tmp_path):
    d = tmp_path / "intake"
    d.mkdir()
    (d / "bad.jsonl").write_text("{not valid json\n", encoding="utf-8")
    out = _run(intake_directory=d)
    assert out["intake_status"] == INTAKE_INVALID
    assert "malformed_label_file" in out["block_reasons"]


def test_09_forbidden_field_rejected():
    q = _queue()
    pid = _pids(q)[0]
    rows = _two_same(pid)
    rows[0]["semantic_score"] = 0.9
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=rows,
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["intake_status"] == INTAKE_INVALID
    assert "forbidden_field" in out["block_reasons"]
    assert out["forbidden_field_count"] >= 1


def test_10_raw_body_rejected():
    q = _queue()
    pid = _pids(q)[0]
    rows = _two_same(pid)
    rows[0]["raw_body"] = "full article text"
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=rows,
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["intake_status"] == INTAKE_INVALID
    assert "forbidden_field" in out["block_reasons"]


def test_11_api_key_secret_rejected():
    q = _queue()
    pid = _pids(q)[0]
    rows = _two_same(pid)
    rows[0]["api_key"] = "sk-should-never-be-here"
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=rows,
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["intake_status"] == INTAKE_INVALID
    assert "forbidden_field" in out["block_reasons"]
    # secret 값은 출력 표면 미노출(거부된 필드명만 진단으로 surfaced·값은 normalized 전 차단).
    assert "sk-should-never-be-here" not in json.dumps(out)


def test_12_model_rationale_score_rejected():
    q = _queue()
    pid = _pids(q)[0]
    rows = _two_same(pid)
    rows[0]["model_rationale"] = "model said same"
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=rows,
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["intake_status"] == INTAKE_INVALID


def test_13_unknown_pair_id_rejected():
    q = _queue()
    out = run_production_label_intake(queue=q, batch_id="b1",
                                      label_rows=_two_same("pair:nonexistent_999"),
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["intake_status"] == INTAKE_INVALID
    assert out["unknown_pair_id_count"] >= 1
    assert "unknown_pair_id" in out["block_reasons"]


def test_14_duplicate_label_handled():
    q = _queue()
    pid = _pids(q)[0]
    rows = [_row(pid, "rev_a", "same_event"), _row(pid, "rev_a", "same_event")]   # 같은 (pair,reviewer,round).
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=rows,
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["duplicate_label_count"] >= 1


def test_15_non_human_label_rejected():
    q = _queue()
    pid = _pids(q)[0]
    rows = _two_same(pid)
    rows[0]["reviewer_kind"] = "model"
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=rows,
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["intake_status"] == INTAKE_INVALID
    assert out["model_label_rejected_count"] >= 1
    assert "non_human_label" in out["block_reasons"]


def test_16_reviewer_id_pii_not_printed():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(
        queue=q, batch_id="b1",
        label_rows=[_row(pid, "alice@example.com", "same_event"),
                    _row(pid, "bob@example.com", "same_event")],
        label_source=LABEL_SOURCE_PRODUCTION)
    blob = json.dumps(out, ensure_ascii=False, default=str)
    assert "alice@example.com" not in blob and "bob@example.com" not in blob
    assert out["raw_pii_exposed"] is False
    assert out["reviewer_ids_pseudonymous"] is True


# ── §10 17-25: gold policy ───────────────────────────────────────────────────────────────────────────
def test_17_single_reviewer_insufficient():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(queue=q, batch_id="b1",
                                      label_rows=[_row(pid, "rev_a", "same_event")],
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["production_gold_count"] == 0   # 1명 = insufficient(gold 아님).


def test_18_two_human_same_positive_gold():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=_two_same(pid),
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["production_gold_count"] == 1
    assert out["positive_gold_count"] == 1


def test_19_two_human_different_negative_gold():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=_two_diff(pid),
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["production_gold_count"] == 1
    assert out["negative_gold_count"] == 1


def test_20_conflict_pending():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(
        queue=q, batch_id="b1",
        label_rows=[_row(pid, "rev_a", "same_event"), _row(pid, "rev_b", "different_event")],
        label_source=LABEL_SOURCE_PRODUCTION)
    assert out["intake_status"] == INTAKE_CONFLICT_PENDING
    assert "conflict_pending" in out["block_reasons"]


def test_21_adjudicated_conflict_gold_candidate():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(
        queue=q, batch_id="b1",
        label_rows=[_row(pid, "rev_a", "same_event"), _row(pid, "rev_b", "different_event")],
        adjudications={pid: {"label": "same_event", "adjudicator_kind": "human", "adjudicated_by": "lead"}},
        label_source=LABEL_SOURCE_PRODUCTION)
    assert out["production_gold_count"] == 1
    assert out["conflict_rate"] == 0.0 or out["block_reasons"].count("conflict_pending") == 0


def test_22_unsure_needs_review_not_gold():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(
        queue=q, batch_id="b1",
        label_rows=[_row(pid, "rev_a", "needs_review"), _row(pid, "rev_b", "needs_review")],
        label_source=LABEL_SOURCE_PRODUCTION)
    assert out["production_gold_count"] == 0
    assert out["non_decisive_gold_count"] >= 1
    assert "non_decisive_only" in out["block_reasons"]


def test_23_synthetic_not_production_gold():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(
        queue=q, batch_id="b1", label_rows=_two_same(pid, ds=SOURCE_SYNTHETIC),
        label_source=LABEL_SOURCE_SYNTHETIC)
    assert out["production_gold_count"] == 0
    assert out["synthetic_gold_count"] == 1


def test_24_test_fixture_not_production_gold():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(
        queue=q, batch_id="b1", label_rows=_two_same(pid, ds=SOURCE_SYNTHETIC),
        label_source=LABEL_SOURCE_TEST)
    assert out["production_gold_count"] == 0


def test_25_production_tag_but_synthetic_dataset_not_gold():
    # label_source=production 이나 행 dataset_source=synthetic → live 아님 → production gold 아님(provenance 분리).
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(
        queue=q, batch_id="b1", label_rows=_two_same(pid, ds=SOURCE_SYNTHETIC),
        label_source=LABEL_SOURCE_PRODUCTION)
    assert out["production_gold_count"] == 0


# ── §10 26-32: calibration delta ─────────────────────────────────────────────────────────────────────
def test_26_gold_delta_reported():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=_two_same(pid),
                                      label_source=LABEL_SOURCE_PRODUCTION)
    d = out["calibration_delta"]
    assert d["before_production_gold_count"] == 0 and d["after_production_gold_count"] == 1
    assert d["gold_delta"] == 1


def test_27_positive_negative_delta_reported():
    q = _queue()
    pids = _pids(q, 2)
    rows = _two_same(pids[0]) + _two_diff(pids[1])
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=rows,
                                      label_source=LABEL_SOURCE_PRODUCTION)
    d = out["calibration_delta"]
    assert d["positive_delta"] == 1 and d["negative_delta"] == 1


def test_28_korean_delta_reported():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=_two_same(pid, lang="ko"),
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["korean_gold_count"] == 1
    assert out["calibration_delta"]["korean_delta"] == 1


def test_29_precision_denominator_not_ready():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=_two_same(pid),
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["calibration_delta"]["precision_denominator_ready"] is False


def test_30_fpr_denominator_not_ready():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=_two_diff(pid),
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["calibration_delta"]["fpr_denominator_ready"] is False


def test_31_merge_gate_false_without_floors():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=_two_same(pid),
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["merge_gate_ready"] is False
    assert out["calibration_delta"]["merge_gate_ready"] is False


def test_32_next_needed_for_merge_gate_emitted():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=_two_same(pid),
                                      label_source=LABEL_SOURCE_PRODUCTION)
    nn = out["calibration_delta"]["next_needed_for_merge_gate"]
    assert any("live production gold" in s for s in nn)
    assert any("korean gold" in s for s in nn)


# ── §10 33-39: no merge / no LLM / no DB / secret ────────────────────────────────────────────────────
def test_33_merge_allowed_false():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=_two_same(pid),
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["merge_allowed"] is False and out["no_merge_without_gold"] is True


def test_34_no_public_intelligence_unit(tmp_path):
    assert _run(intake_directory=tmp_path / "e")["no_public_intelligence_unit"] is True


def test_35_no_db_write(tmp_path):
    assert _run(intake_directory=tmp_path / "e")["db_write"] is False


def test_36_no_llm_invoked(tmp_path):
    assert _run(intake_directory=tmp_path / "e")["llm_invoked"] is False


def test_37_no_embedding_invoked(tmp_path):
    assert _run(intake_directory=tmp_path / "e")["embedding_invoked"] is False


def test_38_module_does_not_read_env():
    src = _MODULE.read_text(encoding="utf-8")
    for token in ("os.environ", "getenv", "load_dotenv", "dotenv", "open(\".env"):
        assert token not in src


def test_39_production_gold_provenance_not_asserted():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=_two_same(pid),
                                      label_source=LABEL_SOURCE_PRODUCTION)
    # gold 가 카운트돼도 provenance 는 선언 기반 — readiness 근거 인용 금지(B-1).
    assert out["production_gold_provenance_verified"] is False


# ── filesystem 다중파일 스캔 ─────────────────────────────────────────────────────────────────────────
def test_40_filesystem_multi_file_aggregated(tmp_path):
    q = _queue()
    pids = _pids(q, 2)
    d = tmp_path / "intake"
    d.mkdir()
    _write_jsonl(d / "b1__rv_a__labels.jsonl", [_row(pids[0], "rev_a", "same_event"),
                                                _row(pids[1], "rev_a", "different_event")])
    _write_jsonl(d / "b1__rv_b__labels.jsonl", [_row(pids[0], "rev_b", "same_event"),
                                                _row(pids[1], "rev_b", "different_event")])
    out = run_production_label_intake(queue=q, batch_id="b1", intake_directory=d,
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["pairs_labeled"] == 2
    assert out["production_gold_count"] == 2
    assert len(out["label_files_found"]) == 2


def test_41_label_files_found_basename_only(tmp_path):
    q = _queue()
    pid = _pids(q)[0]
    d = tmp_path / "intake"
    d.mkdir()
    _write_jsonl(d / "b1__rv_a__labels.jsonl", _two_same(pid))
    out = run_production_label_intake(queue=q, batch_id="b1", intake_directory=d,
                                      label_source=LABEL_SOURCE_PRODUCTION)
    # basename 만(절대경로/사용자명 미노출·MEDIUM-1). 절대경로 override → intake_directory=basename.
    assert out["label_files_found"] == ["b1__rv_a__labels.jsonl"]
    assert out["intake_directory"] == "intake"
    # escape-aware: 절대경로의 어떤 상위 컴포넌트(드라이브/사용자명)도 intake_directory 에 미노출.
    assert ":" not in out["intake_directory"]
    for part in tmp_path.parts:
        if part not in ("intake", "\\", "/"):
            assert part not in out["intake_directory"]


def test_42_empty_dir_awaiting(tmp_path):
    d = tmp_path / "intake"
    d.mkdir()
    out = _run(intake_directory=d)
    assert out["intake_status"] == INTAKE_AWAITING_PRODUCTION
    assert out["label_files_found"] == []


def test_43_nonexistent_dir_awaiting(tmp_path):
    out = _run(intake_directory=tmp_path / "does_not_exist")
    assert out["intake_status"] == INTAKE_AWAITING_PRODUCTION
    assert out["label_import_attempted"] is False


def test_44_pair_coverage_rate(tmp_path):
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=_two_same(pid),
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["pairs_labeled"] == 1
    assert out["pairs_expected"] >= 1
    assert out["pair_coverage_rate"] == round(1 / out["pairs_expected"], 4)


# ── contract / drift locks ───────────────────────────────────────────────────────────────────────────
def test_45_intake_states_are_five():
    assert len(INTAKE_STATES) == 5
    assert INTAKE_AWAITING_PRODUCTION in INTAKE_STATES


def test_46_agent_contract_cannot_merge():
    out = _run(intake_directory=Path("nope"))
    assert "merge 실행" in out["agent_contract"]["cannot"]
    assert any("label 조작" in c for c in out["agent_contract"]["cannot"])


def test_47_agent_contract_embedding_no_go():
    out = _run(intake_directory=Path("nope"))
    assert "No-Go" in out["agent_contract"]["embedding_llm_adjudicator"]["status"]


def test_48_failure_classes_cover_reasons():
    for cls in ("malformed_label_file", "forbidden_field", "unknown_pair_id", "duplicate_label",
                "non_human_label", "conflict_pending", "calibration_floor_not_met"):
        assert cls in FAILURE_CLASSES


def test_49_calibration_delta_pure_function():
    d = build_calibration_delta(
        production_gold_count=3, positive_gold_count=2, negative_gold_count=1, korean_gold_count=0,
        agreement_rate=1.0, conflict_count=0, precision_denominator_ready=False,
        fpr_denominator_ready=False, korean_calibration_ready=False, merge_gate_ready=False)
    assert d["gold_delta"] == 3 and d["positive_delta"] == 2 and d["negative_delta"] == 1
    assert any("korean gold" in s for s in d["next_needed_for_merge_gate"])


def test_50_no_labels_report_pure_function():
    q = _queue()
    from backend.app.tools.reviewer_batch_launch import (
        build_assignment_manifest,
        build_intake_plan,
        build_reviewer_instruction,
    )
    manifest = build_assignment_manifest(q, batch_id="b1")
    plan = build_intake_plan("b1", pseudonyms=manifest["pseudonymous_reviewers"])
    rep = build_no_labels_report(plan, manifest, build_reviewer_instruction(), plan["intake_directory"])
    assert rep["status"] == INTAKE_AWAITING_PRODUCTION
    # instruction summary 에 모델 점수/predicted_status 미노출.
    assert rep["reviewer_instruction_summary"]["model_score_shown"] is False
    assert rep["reviewer_instruction_summary"]["predicted_status_shown"] is False


def test_51_agreement_rate_reported_on_import():
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=_two_same(pid),
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["agreement_rate"] is not None


def test_52_decisive_only_mixed_batch():
    # 만장일치 needs_review(non-decisive) + 만장일치 same_event(decisive) → production gold 1·non_decisive ≥1.
    q = _queue()
    pids = _pids(q, 2)
    rows = (_two_same(pids[0])
            + [_row(pids[1], "rev_a", "needs_review"), _row(pids[1], "rev_b", "needs_review")])
    out = run_production_label_intake(queue=q, batch_id="b1", label_rows=rows,
                                      label_source=LABEL_SOURCE_PRODUCTION)
    assert out["production_gold_count"] == 1
    assert out["non_decisive_gold_count"] >= 1


# ── 감사 fix-lock(adversarial MEDIUM-1/2·LOW-3/4·MEDIUM-3) ────────────────────────────────────────────
def test_53_synthetic_namespace_excluded_from_production_gold():
    # hn_syn: trap pair 가 행 dataset_source=live + label_source=production 으로 (오)태깅돼도 production gold 아님(MEDIUM-2).
    disc = discover_overlap(build_captured_overlap_fixture())
    q = build_near_match_reviewer_queue(disc, packet_id="t", include_synthetic_hard_negatives=True)
    hn = [p for p in (q.get("queue_pair_ids") or []) if p.startswith("hn_syn:")][0]
    out = run_production_label_intake(
        queue=q, batch_id="b1", label_rows=_two_same(hn, ds=SOURCE_LIVE),
        label_source=LABEL_SOURCE_PRODUCTION)
    assert out["production_gold_count"] == 0          # synthetic namespace → production 배제.
    assert out["synthetic_gold_count"] >= 1           # synthetic 으로 재분류(정직).


def test_54_calibration_delta_none_baseline_no_crash():
    # baseline 정수 필드 None 이어도 crash 없이 None delta(LOW-3).
    d = build_calibration_delta(
        production_gold_count=2, positive_gold_count=1, negative_gold_count=1, korean_gold_count=0,
        agreement_rate=None, conflict_count=0, precision_denominator_ready=False,
        fpr_denominator_ready=False, korean_calibration_ready=False, merge_gate_ready=False,
        baseline={"production_gold_count": None, "positive_gold_count": None, "negative_gold_count": None,
                  "korean_gold_count": None, "agreement_rate": None, "conflict_count": None})
    assert d["gold_delta"] is None and d["agreement_delta"] is None


def test_55_model_adjudicator_graceful_not_crash():
    # model adjudicator adjudication → crash 대신 graceful invalid(non_human_label·LOW-4).
    q = _queue()
    pid = _pids(q)[0]
    out = run_production_label_intake(
        queue=q, batch_id="b1",
        label_rows=[_row(pid, "rev_a", "same_event"), _row(pid, "rev_b", "different_event")],
        adjudications={pid: {"label": "same_event", "adjudicator_kind": "model", "adjudicated_by": "bot"}},
        label_source=LABEL_SOURCE_PRODUCTION)
    assert out["intake_status"] == INTAKE_INVALID
    assert "non_human_label" in out["block_reasons"]
    assert out["production_gold_count"] == 0


def test_56_default_relative_path_no_abs_leak():
    # 기본(상대) intake_directory 는 정보 보존(outputs/reviewer_batch/)·절대경로/드라이브 콜론 0(MEDIUM-1).
    out = run_production_label_intake(queue=_queue(), batch_id="b9", packet_id="t")
    assert out["intake_directory"].startswith("outputs/reviewer_batch/")
    assert ":" not in out["intake_directory"]


def test_57_no_labels_report_gitignore_note(tmp_path):
    out = _run(intake_directory=tmp_path / "empty")
    actions = out["no_labels_report"]["operator_next_actions"]
    # MEDIUM-3 note 자체를 잠금(validation_command action 의 경로 문자열로 우연 통과 방지).
    assert any("gitignore" in a and "커밋 금지" in a for a in actions)
