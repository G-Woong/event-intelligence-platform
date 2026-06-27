"""ADR#72 — actual reviewer input gate + internal ops bridge 테스트(병합 0·LLM 0·DB 0·전송 0·입력 날조 0).

커버: actual input 스캔(생성 0·basename only)·5-state actual_input_status(no_actual_input/contact_evidence_only/
returned_labels_present/invalid_returned_labels/labels_imported)·external_input_required 정직·contact evidence 파일
로드(JSON 배열·malformed fail-loud)·returned label 디렉터리 intake 체인·production_gold exact passthrough(게이트만으로
미증가)·internal ops bridge readiness·no public truth/PII/score/merge·전체 출력 forbidden-key 0·입력 파일 날조 0.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.services.identity_human_labeling import SOURCE_LIVE
from backend.app.tools.near_match_reviewer_queue import build_near_match_reviewer_queue
from backend.app.tools.reviewer_actual_input_gate import (
    ACTUAL_INPUT_STATES,
    INPUT_CONTACT_ONLY,
    INPUT_INVALID_RETURNED,
    INPUT_LABELS_IMPORTED,
    INPUT_NO_ACTUAL,
    INPUT_RETURNED_PRESENT,
    OPERATION_NAME,
    _actual_input_status,
    run_actual_input_gate,
    scan_actual_reviewer_input,
)
from backend.app.tools.reviewer_batch_launch import build_assignment_manifest
from backend.app.tools.reviewer_label_operations import LABEL_SOURCE_PRODUCTION
from backend.app.tools.reviewer_pilot_execution import (
    EXEC_AWAITING_CONTACT,
    EXEC_CONFLICT,
    EXEC_CONTACTED_WAITING,
    EXEC_NOT_STARTED,
    EXEC_PARTIAL,
    EXECUTION_STATES,
    run_reviewer_pilot_execution,
)
from backend.app.tools.reviewer_pilot_handoff import _HANDOFF_FORBIDDEN_KEYS
from backend.app.tools.source_overlap_discovery import (
    build_captured_overlap_fixture,
    discover_overlap,
)


# ── helpers ────────────────────────────────────────────────────────────────────────────────────────────
def _queue(*, reviewers=None, rpp=2):
    disc = discover_overlap(build_captured_overlap_fixture())
    return build_near_match_reviewer_queue(
        disc, packet_id="input_gate_test", reviewers=reviewers, reviewers_per_pair=rpp)


def _manifest(queue, batch_id="b1"):
    return build_assignment_manifest(queue, batch_id=batch_id)


def _row(ps, pid, label, *, ds=SOURCE_LIVE):
    return {
        "pair_id": pid, "reviewer_id": ps, "review_round": 1, "label": label,
        "label_confidence": "medium", "reviewed_at": "2026-06-26T00:00:00+00:00", "language": "en",
        "source_type_left": "article", "source_type_right": "article",
        "title_left": "headline left", "title_right": "headline right",
        "observed_at_left": "2026-06-22", "observed_at_right": "2026-06-22",
        "dataset_source": ds,
    }


def _assignments(manifest):
    return [(a["reviewer_pseudonym"], a["pair_id"]) for a in manifest["assignments"]]


def _submit_all(manifest, label_fn):
    return [_row(ps, pid, label_fn(ps, pid)) for ps, pid in _assignments(manifest)]


def _partial_rows(manifest, n_pairs=1, *, label="same_event"):
    pairs = sorted({pid for _, pid in _assignments(manifest)})
    target = set(pairs[:n_pairs])
    return [_row(ps, pid, label) for ps, pid in _assignments(manifest) if pid in target]


def _conflict_rows(manifest):
    assigns = _assignments(manifest)
    pairs = sorted({pid for _, pid in assigns})
    p0 = pairs[0]
    p0_ps = sorted(ps for ps, pid in assigns if pid == p0)
    assert len(p0_ps) >= 2
    rows = []
    for ps, pid in assigns:
        rows.append(_row(ps, pid, "different_event" if (pid == p0 and ps == p0_ps[1]) else "same_event"))
    return rows


def _evidence(manifest, *, status="contacted", method="manual_email"):
    return [
        {"reviewer_pseudonym": ps, "contact_method_label": method, "contact_status": status}
        for ps in sorted(manifest["pseudonymous_reviewers"])
    ]


def _write_labels_dir(directory, rows, *, batch_id="b1"):
    by_ps: dict = {}
    for r in rows:
        by_ps.setdefault(r["reviewer_id"], []).append(r)
    for ps, rws in by_ps.items():
        (Path(directory) / f"{batch_id}__{ps}__labels.jsonl").write_text(
            "\n".join(json.dumps(x) for x in rws), encoding="utf-8")


def _write_contact_file(directory, evidence, *, name="contact_evidence.json"):
    (Path(directory) / name).write_text(json.dumps(evidence), encoding="utf-8")


def _forbidden_keys_in(obj) -> set:
    found: set = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in _HANDOFF_FORBIDDEN_KEYS:
                    found.add(k)
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(obj)
    return found


# ── 1) actual input 탐지 / external_input_required ──────────────────────────────────────────────────────
def test_01_no_actual_input_external_required(tmp_path):
    out = run_actual_input_gate(directory=str(tmp_path / "missing"), batch_id="b1")
    assert out["operation_name"] == OPERATION_NAME
    assert out["actual_input_status"] == INPUT_NO_ACTUAL
    assert out["actual_contact_evidence_found"] is False
    assert out["actual_returned_labels_found"] is False
    assert out["external_input_required"] is True
    assert out["execution_status"] == EXEC_NOT_STARTED   # queue 없음 → handoff 대상 0.
    assert "external_reviewer_input_required" in out["block_reasons"]


def test_02_scan_missing_dir(tmp_path):
    scan = scan_actual_reviewer_input(str(tmp_path / "nope"))
    assert scan["directory_exists"] is False
    assert scan["contact_evidence_files"] == []
    assert scan["returned_label_files"] == []


def test_03_scan_detects_basenames_only(tmp_path):
    d = tmp_path / "batch"
    d.mkdir()
    _write_contact_file(d, [])
    (d / "b1__rev__labels.jsonl").write_text("", encoding="utf-8")
    scan = scan_actual_reviewer_input(str(d))
    assert scan["directory_exists"] is True
    assert scan["contact_evidence_files"] == ["contact_evidence.json"]
    assert scan["returned_label_files"] == ["b1__rev__labels.jsonl"]
    # basename only — 절대경로/사용자명 누출 0.
    assert "Users" not in json.dumps(scan["contact_evidence_files"] + scan["returned_label_files"])


def test_04_actual_input_status_state_machine():
    f = _actual_input_status
    assert f(contact_found=False, labels_found=False, returned_label_count=0, production_gold_count=0) == INPUT_NO_ACTUAL
    assert f(contact_found=True, labels_found=False, returned_label_count=0, production_gold_count=0) == INPUT_CONTACT_ONLY
    assert f(contact_found=False, labels_found=True, returned_label_count=0, production_gold_count=0) == INPUT_INVALID_RETURNED
    assert f(contact_found=False, labels_found=True, returned_label_count=4, production_gold_count=0) == INPUT_RETURNED_PRESENT
    assert f(contact_found=True, labels_found=True, returned_label_count=10, production_gold_count=6) == INPUT_LABELS_IMPORTED
    assert ACTUAL_INPUT_STATES == {
        INPUT_NO_ACTUAL, INPUT_CONTACT_ONLY, INPUT_RETURNED_PRESENT,
        INPUT_INVALID_RETURNED, INPUT_LABELS_IMPORTED}


# ── 2) contact evidence (파일 기반) ────────────────────────────────────────────────────────────────────
def test_05_contact_evidence_only(tmp_path):
    q = _queue()
    m = _manifest(q)
    d = tmp_path / "batch"
    d.mkdir()
    _write_contact_file(d, _evidence(m, status="contacted"))
    out = run_actual_input_gate(directory=str(d), queue=q, batch_id="b1")
    assert out["actual_contact_evidence_found"] is True
    assert out["actual_returned_labels_found"] is False
    assert out["actual_input_status"] == INPUT_CONTACT_ONLY
    assert out["execution_status"] == EXEC_CONTACTED_WAITING
    assert out["real_reviewers_contacted"] > 0


def test_06_prepared_only_awaiting(tmp_path):
    q = _queue()
    m = _manifest(q)
    d = tmp_path / "batch"
    d.mkdir()
    _write_contact_file(d, _evidence(m, status="prepared"))   # prepared ≠ contacted.
    out = run_actual_input_gate(directory=str(d), queue=q, batch_id="b1")
    assert out["actual_input_status"] == INPUT_CONTACT_ONLY
    assert out["execution_status"] == EXEC_AWAITING_CONTACT
    assert out["real_reviewers_contacted"] == 0
    assert out["pilot_executed"] is False


def test_07_invalid_contact_evidence_rejected(tmp_path):
    d = tmp_path / "batch"
    d.mkdir()
    # 비-allowlist 키(raw_email) — validate_contact_evidence 가 fail-loud.
    _write_contact_file(d, [{
        "reviewer_pseudonym": "rev", "contact_method_label": "manual_email",
        "contact_status": "contacted", "raw_email": "x@y.com"}])
    with pytest.raises(ValueError):
        run_actual_input_gate(directory=str(d), queue=_queue(), batch_id="b1")


def test_14_malformed_contact_json_failloud(tmp_path):
    d = tmp_path / "batch"
    d.mkdir()
    (d / "contact_evidence.json").write_text(json.dumps({"not": "array"}), encoding="utf-8")
    with pytest.raises(ValueError):
        run_actual_input_gate(directory=str(d), queue=_queue(), batch_id="b1")


# ── 3) returned label (디렉터리 intake 체인) ────────────────────────────────────────────────────────────
def test_08_returned_labels_present(tmp_path):
    q = _queue()
    m = _manifest(q)
    d = tmp_path / "batch"
    d.mkdir()
    _write_labels_dir(d, _submit_all(m, lambda ps, pid: "same_event"), batch_id="b1")
    out = run_actual_input_gate(directory=str(d), queue=q, batch_id="b1", label_source=LABEL_SOURCE_PRODUCTION)
    assert out["actual_returned_labels_found"] is True
    assert out["returned_label_count"] > 0
    assert out["actual_input_status"] in {INPUT_RETURNED_PRESENT, INPUT_LABELS_IMPORTED}


def test_09_invalid_returned_labels(tmp_path):
    q = _queue()
    d = tmp_path / "batch"
    d.mkdir()
    (d / "b1__nobody__labels.jsonl").write_text("", encoding="utf-8")   # 파일은 있으나 유효 row 0.
    out = run_actual_input_gate(directory=str(d), queue=q, batch_id="b1")
    assert out["actual_returned_labels_found"] is True
    assert out["returned_label_count"] == 0
    assert out["actual_input_status"] == INPUT_INVALID_RETURNED


def test_10_partial_returned(tmp_path):
    q = _queue()
    m = _manifest(q)
    d = tmp_path / "batch"
    d.mkdir()
    _write_labels_dir(d, _partial_rows(m, n_pairs=1), batch_id="b1")
    out = run_actual_input_gate(directory=str(d), queue=q, batch_id="b1")
    assert out["execution_status"] == EXEC_PARTIAL
    assert out["missing_label_count"] > 0


def test_11_conflict_pending(tmp_path):
    q = _queue()
    m = _manifest(q)
    d = tmp_path / "batch"
    d.mkdir()
    _write_labels_dir(d, _conflict_rows(m), batch_id="b1")
    out = run_actual_input_gate(directory=str(d), queue=q, batch_id="b1")
    assert out["execution_status"] == EXEC_CONFLICT
    assert out["conflict_pair_count"] > 0


def test_12_full_submission_returned(tmp_path):
    q = _queue()
    m = _manifest(q)
    d = tmp_path / "batch"
    d.mkdir()
    _write_labels_dir(d, _submit_all(m, lambda ps, pid: "same_event"), batch_id="b1")
    out = run_actual_input_gate(directory=str(d), queue=q, batch_id="b1")
    assert out["returned_label_count"] == out["expected_label_count"]
    assert out["execution_status"] in EXECUTION_STATES
    assert out["merge_gate_ready"] is False   # calibration floor 미충족 → 자동 merge 금지.


# ── 4) gold exact passthrough(게이트만으로 미증가) ──────────────────────────────────────────────────────
def test_13_production_gold_exact_passthrough(tmp_path):
    q = _queue()
    m = _manifest(q)
    d = tmp_path / "batch"
    d.mkdir()
    _write_labels_dir(d, _submit_all(m, lambda ps, pid: "same_event"), batch_id="b1")
    gate = run_actual_input_gate(directory=str(d), queue=q, batch_id="b1", label_source=LABEL_SOURCE_PRODUCTION)
    direct = run_reviewer_pilot_execution(
        queue=q, batch_id="b1", intake_directory=str(d), label_source=LABEL_SOURCE_PRODUCTION)
    for k in ("returned_label_count", "expected_label_count", "missing_label_count",
              "invalid_label_count", "conflict_pair_count", "production_gold_count",
              "synthetic_gold_count", "calibration_ready", "merge_gate_ready"):
        assert gate[k] == direct[k], k


# ── 5) internal ops bridge readiness / no public truth ─────────────────────────────────────────────────
def test_15_bridge_readiness():
    out = run_actual_input_gate(queue=_queue(), batch_id="b1")
    assert out["internal_ops_contract_ready"] is True
    assert out["backend_internal_ops_api_ready"] is True
    assert out["frontend_internal_ops_seed_ready"] is True
    assert out["internal_ops_contract"]["contract"] == "InternalOpsPilotExecutionStatus"


def test_16_no_go_flags():
    out = run_actual_input_gate(queue=_queue(), batch_id="b1")
    assert out["public_truth_exposed"] is False
    assert out["same_event_truth_exposed"] is False
    assert out["merge_allowed"] is False
    assert out["no_public_intelligence_unit"] is True
    assert out["db_write"] is False
    assert out["llm_invoked"] is False
    assert out["embedding_invoked"] is False


def test_17_labeler_hidden_flags():
    out = run_actual_input_gate(queue=_queue(), batch_id="b1")
    assert out["score_exposed"] is False
    assert out["rationale_exposed"] is False
    assert out["predicted_status_exposed"] is False
    assert out["raw_pii_exposed"] is False
    assert out["reviewer_ids_pseudonymous"] is True


def test_18_ops_ui_flags():
    flags = run_actual_input_gate(queue=_queue(), batch_id="b1")["ops_ui_flags"]
    for k in ("internal_only", "no_public_truth", "no_merge", "no_public_iu", "pii_safe", "no_llm", "no_db_write"):
        assert flags[k] is True, k
    assert flags["gold_provenance_verified"] is False


# ── 6) PII / forbidden-key / 입력 날조 0 ────────────────────────────────────────────────────────────────
def test_19_no_forbidden_keys(tmp_path):
    q = _queue()
    m = _manifest(q)
    d = tmp_path / "batch"
    d.mkdir()
    _write_contact_file(d, _evidence(m, status="contacted"))
    _write_labels_dir(d, _submit_all(m, lambda ps, pid: "same_event"), batch_id="b1")
    out = run_actual_input_gate(directory=str(d), queue=q, batch_id="b1")
    assert _forbidden_keys_in(out) == set()


def test_20_returned_files_basename_only(tmp_path):
    q = _queue()
    m = _manifest(q)
    d = tmp_path / "batch"
    d.mkdir()
    _write_labels_dir(d, _submit_all(m, lambda ps, pid: "same_event"), batch_id="b1")
    out = run_actual_input_gate(directory=str(d), queue=q, batch_id="b1")
    blob = json.dumps(out["returned_label_files"]) + json.dumps(out["input_directory"])
    assert "Users" not in blob   # 절대경로 사용자명 미노출.


def test_21_operation_name_and_states():
    out = run_actual_input_gate(queue=_queue(), batch_id="b1")
    assert out["operation_name"] == OPERATION_NAME
    assert out["actual_input_status"] in ACTUAL_INPUT_STATES
    assert out["execution_status"] in EXECUTION_STATES


def test_22_gate_does_not_fabricate_input(tmp_path):
    d = tmp_path / "empty_batch"
    d.mkdir()
    out = run_actual_input_gate(directory=str(d), queue=_queue(), batch_id="b1")
    # 게이트는 입력 파일을 *스캔만* — 어떤 파일도 생성하지 않는다(날조 0).
    assert list(d.iterdir()) == []
    assert out["actual_input_status"] == INPUT_NO_ACTUAL
    assert out["actual_contact_evidence_found"] is False


# ── 감사 fix-lock(adversarial HIGH·code-review M1: 경로 발산) ────────────────────────────────────────────
def test_23_gate_passes_scanned_dir_to_ledger(tmp_path, monkeypatch):
    # HIGH 회귀: 게이트가 스캔한 dir 을 그대로 ledger 에 전달(None→/intake fallback 발산 차단·scan==intake 수렴).
    import backend.app.tools.reviewer_actual_input_gate as gate_mod
    captured: dict = {}
    real = gate_mod.run_reviewer_pilot_execution

    def spy(**kw):
        captured["intake_directory"] = kw.get("intake_directory")
        return real(**kw)

    monkeypatch.setattr(gate_mod, "run_reviewer_pilot_execution", spy)
    d = tmp_path / "batch"
    d.mkdir()   # 라벨 없음(빈 dir) — None 이 아니라 스캔 경로 그대로 전달돼야.
    run_actual_input_gate(directory=str(d), queue=_queue(), batch_id="b1")
    assert captured["intake_directory"] == str(d)


def test_24_returned_count_consistent_with_found(tmp_path):
    # HIGH 회귀: returned_label_count>0 이면 actual_returned_labels_found=True(no_actual_input+returned>0 자기모순 금지).
    q = _queue()
    m = _manifest(q)
    d = tmp_path / "batch"
    d.mkdir()
    _write_labels_dir(d, _submit_all(m, lambda ps, pid: "same_event"), batch_id="b1")
    out = run_actual_input_gate(directory=str(d), queue=q, batch_id="b1")
    assert (out["returned_label_count"] > 0) == out["actual_returned_labels_found"]
    assert out["returned_label_count"] > 0


def test_25_redacted_filename_masked(tmp_path):
    # LOW 회귀: operator 가 파일명에 raw PII(이메일)를 넣어도 출력 basename 마스킹(노출 0).
    q = _queue()
    d = tmp_path / "batch"
    d.mkdir()
    (d / "b1__rev@example.com__labels.jsonl").write_text("", encoding="utf-8")
    out = run_actual_input_gate(directory=str(d), queue=q, batch_id="b1")
    blob = json.dumps(out["returned_label_files"])
    assert "@" not in blob
    assert "<redacted_filename>" in out["returned_label_files"]
