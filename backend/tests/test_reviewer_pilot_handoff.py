"""ADR#70 — actual reviewer pilot handoff bundle + returned-label gate 테스트(병합 0·LLM 0·DB 0·전송 0).

커버: pilot handoff readiness(not_ready/ready_to_contact/awaiting_reviewer_return)·returned-label gate(no/partial/
invalid/conflict/calibration/imported)·8-state pilot_status·correction/adjudication/calibration handoff(전송 0)·
ops UI seed contract·PII/secret 경계·labeler 숨김·gold exact passthrough(production_gold_count 미증가·handoff 만)·
no merge/LLM/DB·followup/intake 발산 0·정책 lock.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.app.services.identity_human_labeling import SOURCE_LIVE, SOURCE_SYNTHETIC
from backend.app.tools.near_match_reviewer_queue import build_near_match_reviewer_queue
from backend.app.tools.production_label_intake import run_production_label_intake
from backend.app.tools.reviewer_batch_launch import build_assignment_manifest
from backend.app.tools.reviewer_followup_ops import run_reviewer_followup_ops
from backend.app.tools.reviewer_label_operations import (
    LABEL_SOURCE_PRODUCTION,
    LABEL_SOURCE_SYNTHETIC,
)
from backend.app.tools.reviewer_pilot_handoff import (
    _HANDOFF_FORBIDDEN_KEYS,
    ADJUDICATION_HANDOFF,
    CORRECTION_REQUEST,
    OPERATION_NAME,
    PILOT_AWAITING_RETURN,
    PILOT_CALIBRATION_PENDING,
    PILOT_CONFLICT_PENDING,
    PILOT_IMPORTED_READY,
    PILOT_INVALID_RETURNED,
    PILOT_NOT_READY,
    PILOT_PARTIAL_RETURNED,
    PILOT_READY_TO_CONTACT,
    PILOT_STATES,
    REVIEWER_PILOT_AGENT_CONTRACT,
    build_adjudication_handoff,
    build_correction_templates,
    run_reviewer_pilot_handoff,
)
from backend.app.tools.source_overlap_discovery import (
    build_captured_overlap_fixture,
    discover_overlap,
)

_RAW_REVIEWER_MARKER = "reviewer_pool_slot"   # 기본 placeholder raw id — 출력 표면에 절대 노출 금지.


# ── helpers ────────────────────────────────────────────────────────────────────────────────────────────
def _queue(*, reviewers=None, hard_neg=False, rpp=2):
    disc = discover_overlap(build_captured_overlap_fixture())
    return build_near_match_reviewer_queue(
        disc, packet_id="pilot_test", reviewers=reviewers,
        include_synthetic_hard_negatives=hard_neg, reviewers_per_pair=rpp)


def _manifest(queue, batch_id="b1"):
    return build_assignment_manifest(queue, batch_id=batch_id)


def _row(ps, pid, label, *, ds=SOURCE_LIVE, lang="en", conf="medium", rnd=1, extra=None):
    row = {
        "pair_id": pid, "reviewer_id": ps, "review_round": rnd, "label": label,
        "label_confidence": conf, "reviewed_at": "2026-06-26T00:00:00+00:00", "language": lang,
        "source_type_left": "article", "source_type_right": "article",
        "title_left": "headline left", "title_right": "headline right",
        "observed_at_left": "2026-06-22", "observed_at_right": "2026-06-22",
        "dataset_source": ds,
    }
    if extra:
        row.update(extra)
    return row


def _assignments(manifest):
    return [(a["reviewer_pseudonym"], a["pair_id"]) for a in manifest["assignments"]]


def _submit_all(manifest, label_fn, *, ds=SOURCE_LIVE):
    return [_row(ps, pid, label_fn(ps, pid), ds=ds) for ps, pid in _assignments(manifest)]


def _partial_rows(manifest, n_pairs=1, *, ds=SOURCE_LIVE, label="same_event"):
    pairs = sorted({pid for _, pid in _assignments(manifest)})
    target = set(pairs[:n_pairs])
    return [_row(ps, pid, label, ds=ds) for ps, pid in _assignments(manifest) if pid in target]


def _conflict_rows(manifest):
    assigns = _assignments(manifest)
    pairs = sorted({pid for _, pid in assigns})
    p0 = pairs[0]
    p0_ps = sorted(ps for ps, pid in assigns if pid == p0)
    assert len(p0_ps) >= 2
    rows = []
    for ps, pid in assigns:
        if pid == p0 and ps == p0_ps[1]:
            rows.append(_row(ps, pid, "different_event"))
        else:
            rows.append(_row(ps, pid, "same_event"))
    return rows


def _write_reviewer_file(d, batch_id, ps, rows):
    p = Path(d) / f"{batch_id}__{ps}__labels.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


def _run(**kw):
    kw.setdefault("batch_id", "b1")
    kw.setdefault("packet_id", "pilot_test")
    return run_reviewer_pilot_handoff(**kw)


def _forbidden_keys_in(obj):
    """재귀로 forbidden 키 노출 여부 수집(테스트용)."""
    found = set()
    if isinstance(obj, dict):
        found |= set(obj) & _HANDOFF_FORBIDDEN_KEYS
        for v in obj.values():
            found |= _forbidden_keys_in(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _forbidden_keys_in(v)
    return found


# ── §10.1-8: pilot handoff readiness ────────────────────────────────────────────────────────────────────
def test_01_missing_artifacts_not_ready():
    out = _run(queue={})
    assert out["pilot_status"] == PILOT_NOT_READY
    assert out["handoff_bundle_ready"] is False


def test_02_complete_bundle_ready():
    out = _run(queue=_queue(), intake_directory="outputs/reviewer_batch/__nope__/intake")
    assert out["handoff_bundle_ready"] is True
    assert out["reviewer_instruction_present"] is True
    assert out["assignment_manifest_present"] is True
    assert out["label_template_present"] is True
    assert out["validation_command_present"] is True


def test_03_no_returns_ready_to_contact(tmp_path):
    # bundle 완성 + intake dir 미존재(접촉 전) → ready_to_contact.
    missing = Path(tmp_path) / "not_created_yet"
    out = _run(queue=_queue(), intake_directory=str(missing), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["pilot_status"] == PILOT_READY_TO_CONTACT
    assert out["reviewer_contact_required"] is True


def test_04_existing_empty_dir_awaiting_return(tmp_path):
    # bundle 완성 + intake dir 존재·빈(회수 대기) → awaiting_reviewer_return.
    out = _run(queue=_queue(), intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["pilot_status"] == PILOT_AWAITING_RETURN
    assert out["reviewer_contact_required"] is True


def test_05_reviewer_instruction_present_in_bundle():
    out = _run(queue=_queue())
    instr = out["handoff_bundle"]["reviewer_instruction"]
    assert "label_vocabulary" in instr
    assert instr["model_score_shown"] is False           # score/예측 숨김(구조).


def test_06_assignment_summary_present():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q)
    summary = out["handoff_bundle"]["assignment_summary_by_reviewer"]
    assert set(summary) == set(m["pseudonymous_reviewers"])
    for ps, entry in summary.items():
        assert entry["expected_label_filename"] == f"b1__{ps}__labels.jsonl"
        assert entry["pair_count"] == len(entry["pair_ids"])


def test_07_label_template_schema_present():
    out = _run(queue=_queue())
    sch = out["handoff_bundle"]["label_template_schema"]
    assert sch["fill_columns"] == ["label", "label_confidence", "reviewed_at"]
    assert "same_event" in sch["allowed_labels"]
    assert out["handoff_bundle"]["label_template_row_count"] > 0


def test_08_validation_command_and_intake_dir_present():
    out = _run(queue=_queue())
    assert "reviewer_batch_launch" in out["handoff_bundle"]["validation_command"]
    assert out["handoff_bundle"]["intake_directory"]
    assert out["expected_label_files"]


# ── §10.9-15: returned-label gate ───────────────────────────────────────────────────────────────────────
def test_09_no_returns_reminder_templates(tmp_path):
    out = _run(queue=_queue(), intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["reminder_templates"]                     # followup passthrough
    assert out["returned_label_count"] == 0


def test_10_partial_returned(tmp_path):
    q = _queue()
    m = _manifest(q)
    pairs = sorted({pid for _, pid in _assignments(m)})
    ps0 = sorted(m["pseudonymous_reviewers"])[0]
    _write_reviewer_file(tmp_path, "b1", ps0, [_row(ps0, pairs[0], "same_event")])
    out = _run(queue=q, intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["pilot_status"] == PILOT_PARTIAL_RETURNED
    assert 0 < out["returned_label_count"] < out["expected_label_count"]
    assert out["missing_label_count"] > 0


def test_11_invalid_returned():
    q = _queue()
    m = _manifest(q)
    (ps, pid) = _assignments(m)[0]
    out = _run(queue=q, label_rows=[_row(ps, pid, "same_event", extra={"score": 0.9})],
               label_source=LABEL_SOURCE_PRODUCTION)
    assert out["pilot_status"] == PILOT_INVALID_RETURNED
    assert out["correction_templates"]
    assert out["invalid_label_count"] >= 1


def test_12_conflict_pending():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_conflict_rows(m), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["pilot_status"] == PILOT_CONFLICT_PENDING
    assert out["conflict_pair_count"] >= 1
    assert out["adjudication_handoff"]["adjudication_needed"] is True


def test_13_calibration_pending():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_submit_all(m, lambda ps, pid: "same_event"),
               label_source=LABEL_SOURCE_PRODUCTION)
    assert out["pilot_status"] == PILOT_CALIBRATION_PENDING
    assert out["calibration_ready"] is False
    assert out["calibration_gap"]["next_needed_for_merge_gate"]


def test_14_valid_exact_intake_passthrough():
    # returned-label gate 가 followup→intake 와 정확히 동일 상태를 산출(발산 0).
    q = _queue()
    m = _manifest(q)
    rows = _submit_all(m, lambda ps, pid: "same_event")
    pilot = _run(queue=q, label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
    fu = run_reviewer_followup_ops(queue=q, batch_id="b1", packet_id="pilot_test",
                                   label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
    intake = run_production_label_intake(queue=q, batch_id="b1", packet_id="pilot_test",
                                         label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
    assert pilot["followup_status"] == fu["followup_status"]
    assert pilot["intake_status"] == intake["intake_status"]
    assert pilot["calibration_delta"] == intake["calibration_delta"]


def test_15_production_gold_not_modified_by_handoff():
    q = _queue()
    m = _manifest(q)
    rows = _submit_all(m, lambda ps, pid: "same_event")
    pilot = _run(queue=q, label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
    intake = run_production_label_intake(queue=q, batch_id="b1", packet_id="pilot_test",
                                         label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
    assert pilot["production_gold_count"] == intake["production_gold_count"]   # exact passthrough
    # no-returns handoff 은 항상 0(정직).
    assert _run(queue=q)["production_gold_count"] == 0


# ── §10.16-24: safety ───────────────────────────────────────────────────────────────────────────────────
def test_16_actual_sending_false_always():
    q = _queue()
    m = _manifest(q)
    for rows in (None, _partial_rows(m, 1), _conflict_rows(m), _submit_all(m, lambda ps, pid: "same_event")):
        out = _run(queue=q, label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
        assert out["actual_sending_performed"] is False


def test_17_no_raw_reviewer_pii_in_output(tmp_path):
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_partial_rows(m, 1), label_source=LABEL_SOURCE_PRODUCTION)
    assert _RAW_REVIEWER_MARKER not in json.dumps(out, ensure_ascii=False)
    assert out["raw_pii_exposed"] is False


def test_18_reviewer_ids_pseudonymous():
    out = _run(queue=_queue())
    assert out["reviewer_ids_pseudonymous"] is True
    for ps in out["handoff_bundle"]["reviewer_pseudonyms"]:
        assert ps.startswith("rv_")


def test_19_no_forbidden_keys_in_bundle():
    # bundle 전체(instruction·assignment·template schema) 어디에도 forbidden 키(score/rationale/predicted_status/
    # email/secret 등) 노출 0 — 재귀 구조 가드(build 시 _assert_pii_safe + 여기 재검).
    out = _run(queue=_queue())
    assert _forbidden_keys_in(out["handoff_bundle"]) == set()
    assert out["score_hidden_from_labeler"] is True
    assert out["rationale_hidden_from_labeler"] is True
    assert out["predicted_status_hidden"] is True


def test_20_no_score_value_in_handoff_artifacts():
    # bundle/correction/adjudication artifact 에 score/rationale/predicted_status 키 노출 0.
    # (instruction 의 model_score_shown/predicted_status_shown=False 는 "숨김" 선언이라 허용 — substring 아닌
    #  forbidden 키 정확 일치로 검사하고, 숨김 플래그가 실제 False 임을 구조적으로 확인.)
    out = _run(queue=_queue())
    artifacts = {"bundle": out["handoff_bundle"], "corrections": out["correction_templates"],
                 "adjudication": out["adjudication_handoff"]}
    assert _forbidden_keys_in(artifacts) == set()     # score/rationale/predicted_status 키 부재
    instr = out["handoff_bundle"]["reviewer_instruction"]
    assert instr["model_score_shown"] is False
    assert instr["model_rationale_shown"] is False
    assert instr["predicted_status_shown"] is False
    assert instr["hidden_candidate_rank_shown"] is False


def test_21_no_raw_body_in_output():
    q = _queue()
    m = _manifest(q)
    (ps, pid) = _assignments(m)[0]
    out = _run(queue=q, label_rows=[_row(ps, pid, "same_event", extra={"body": "raw article text leak"})],
               label_source=LABEL_SOURCE_PRODUCTION)
    assert out["pilot_status"] == PILOT_INVALID_RETURNED   # body 는 forbidden field → invalid
    assert "raw article text leak" not in json.dumps(out, ensure_ascii=False)


def test_22_secret_value_absent():
    q = _queue()
    m = _manifest(q)
    (ps, pid) = _assignments(m)[0]
    secret = "sk-pilot-must-never-appear"
    out = _run(queue=q, label_rows=[_row(ps, pid, "same_event", extra={"api_key": secret})],
               label_source=LABEL_SOURCE_PRODUCTION)
    assert secret not in json.dumps(out, ensure_ascii=False)


def test_23_absolute_path_sanitized(tmp_path):
    out = _run(queue=_queue(), intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    disp = out["intake_directory"]
    assert "Users" not in disp and ":" not in disp


def test_24_no_external_calls():
    out = _run(queue=_queue())
    assert out["llm_invoked"] is False
    assert out["embedding_invoked"] is False
    assert out["db_write"] is False


# ── §10.25-30: templates ────────────────────────────────────────────────────────────────────────────────
def test_25_reminder_template_generated(tmp_path):
    out = _run(queue=_queue(), intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["reminder_templates"]


def test_26_correction_template_generated():
    q = _queue()
    m = _manifest(q)
    (ps, pid) = _assignments(m)[0]
    out = _run(queue=q, label_rows=[_row(ps, pid, "same_event", extra={"model_score": 1})],
               label_source=LABEL_SOURCE_PRODUCTION)
    corr = out["correction_templates"]
    assert corr and corr[0]["template_type"] == CORRECTION_REQUEST
    assert corr[0]["reason_codes"]                    # reason code only


def test_27_adjudication_handoff_generated():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_conflict_rows(m), label_source=LABEL_SOURCE_PRODUCTION)
    adj = out["adjudication_handoff"]
    assert adj["template_type"] == ADJUDICATION_HANDOFF
    assert adj["no_auto_majority"] is True
    assert adj["adjudication_method"] == "human_lead_adjudication"


def test_28_calibration_gap_next_action():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_submit_all(m, lambda ps, pid: "same_event"),
               label_source=LABEL_SOURCE_PRODUCTION)
    gap = out["calibration_gap"]
    assert gap["next_needed_for_merge_gate"]
    assert gap["merge_gate_ready"] is False


def test_29_correction_reason_codes_only():
    # correction template 은 reason code 만(원본 invalid 값/score 텍스트 미포함).
    q = _queue()
    m = _manifest(q)
    (ps, pid) = _assignments(m)[0]
    out = _run(queue=q, label_rows=[_row(ps, pid, "same_event", extra={"score": 0.77})],
               label_source=LABEL_SOURCE_PRODUCTION)
    blob = json.dumps(out["correction_templates"], ensure_ascii=False)
    assert "0.77" not in blob                          # 원본 score 값 미노출
    assert _forbidden_keys_in(out["correction_templates"]) == set()


def test_30_templates_no_transport_side_channel():
    # 전송 0 — bundle/reminder/correction/adjudication artifact 는 데이터만(전송 호출/URL/토큰 없음).
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_conflict_rows(m), label_source=LABEL_SOURCE_PRODUCTION)
    artifacts = json.dumps({
        "bundle": out["handoff_bundle"], "reminders": out["reminder_templates"],
        "corrections": out["correction_templates"], "adjudication": out["adjudication_handoff"],
        "ops_ui": out["ops_ui_contract"]}, ensure_ascii=False).lower()
    for forbidden in ("smtp", "webhook", "slack_token", "sendgrid", "mailto:", "http://", "https://"):
        assert forbidden not in artifacts


# ── §10.31-36: ops UI seed contract ─────────────────────────────────────────────────────────────────────
def test_31_ops_ui_contract_emitted():
    out = _run(queue=_queue())
    c = out["ops_ui_contract"]
    assert c["contract"] == "OpsReviewBatchStatus"
    assert c["batch_id"] == "b1"
    assert c["pilot_status"] == out["pilot_status"]
    assert "next_action" in c


def test_32_ops_ui_no_public_iu_flag():
    assert _run(queue=_queue())["ops_ui_contract"]["flags"]["no_public_iu"] is True


def test_33_ops_ui_no_merge_flag():
    assert _run(queue=_queue())["ops_ui_contract"]["flags"]["no_merge"] is True


def test_34_ops_ui_no_llm_flag():
    assert _run(queue=_queue())["ops_ui_contract"]["flags"]["no_llm"] is True


def test_35_ops_ui_no_db_write_flag():
    assert _run(queue=_queue())["ops_ui_contract"]["flags"]["no_db_write"] is True


def test_36_ops_ui_pii_safe_flag():
    assert _run(queue=_queue())["ops_ui_contract"]["flags"]["pii_safe"] is True


# ── §10.37-42: no merge / LLM / DB ──────────────────────────────────────────────────────────────────────
def test_37_merge_allowed_false_all_states(tmp_path):
    q = _queue()
    m = _manifest(q)
    outs = [
        _run(queue={}),
        _run(queue=q, intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION),
        _run(queue=q, label_rows=_partial_rows(m, 1), label_source=LABEL_SOURCE_PRODUCTION),
        _run(queue=q, label_rows=_conflict_rows(m), label_source=LABEL_SOURCE_PRODUCTION),
        _run(queue=q, label_rows=_submit_all(m, lambda ps, pid: "same_event"),
             label_source=LABEL_SOURCE_PRODUCTION),
    ]
    for out in outs:
        assert out["merge_allowed"] is False
        assert out["merge_gate_ready"] is False
        assert out["no_merge_without_gold"] is True
        assert out["pilot_status"] in PILOT_STATES


def test_38_no_public_intelligence_unit():
    assert _run(queue=_queue())["no_public_intelligence_unit"] is True


def test_39_no_db_write():
    assert _run(queue=_queue())["db_write"] is False


def test_40_no_llm_invoked():
    assert _run(queue=_queue())["llm_invoked"] is False


def test_41_no_embedding_invoked():
    assert _run(queue=_queue())["embedding_invoked"] is False


def test_42_synthetic_keeps_production_gold_zero():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_submit_all(m, lambda ps, pid: "same_event", ds=SOURCE_SYNTHETIC),
               label_source=LABEL_SOURCE_SYNTHETIC)
    assert out["production_gold_count"] == 0
    assert out["merge_allowed"] is False


# ── contract / policy lock ──────────────────────────────────────────────────────────────────────────────
def test_43_operation_name():
    assert _run(queue=_queue())["operation_name"] == OPERATION_NAME == "reviewer_pilot_handoff"


def test_44_pilot_states_locked():
    assert PILOT_STATES == {
        "not_ready", "ready_to_contact", "awaiting_reviewer_return", "partial_returned",
        "invalid_returned", "conflict_pending", "calibration_pending",
        "imported_ready_for_merge_gate_review"}


def test_45_agent_contract_cannot_merge_send_or_fabricate():
    c = REVIEWER_PILOT_AGENT_CONTRACT
    joined = " ".join(c["cannot"])
    assert "merge 실행" in joined
    assert "label file 임의 생성해 production label 로 사용" in joined
    assert "actual email/slack/webhook 전송" in joined
    assert "reviewer raw PII 출력" in joined
    assert c["embedding_llm_adjudicator"]["status"].startswith("No-Go")


def test_46_agent_contract_can_plan_handoff():
    c = REVIEWER_PILOT_AGENT_CONTRACT
    joined = " ".join(c["can"])
    assert "reviewer pilot handoff readiness 점검" in joined
    assert "internal ops UI status 요약" in joined


def test_47_followup_status_consistency():
    # pilot 은 followup 을 단일 출처로 — followup_status 가 그대로 노출(재계산 0).
    q = _queue()
    m = _manifest(q)
    rows = _partial_rows(m, 1)
    pilot = _run(queue=q, label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
    fu = run_reviewer_followup_ops(queue=q, batch_id="b1", packet_id="pilot_test",
                                   label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
    assert pilot["followup_status"] == fu["followup_status"]
    assert pilot["missing_label_count"] == fu["missing_label_count"]
    assert pilot["reminder_templates"] == fu["reminder_templates"]


def test_48_imported_ready_not_merge_allowed():
    # imported_ready_for_merge_gate_review 라도 merge 는 절대 허용 아님(상태≠허가).
    # calibration floor 가 매우 높아 실제 도달은 불가하나, 매핑/불변을 단위로 검증.
    from backend.app.tools.reviewer_followup_ops import FOLLOWUP_IMPORTED_READY
    from backend.app.tools.reviewer_pilot_handoff import _FOLLOWUP_TO_PILOT
    assert _FOLLOWUP_TO_PILOT[FOLLOWUP_IMPORTED_READY] == PILOT_IMPORTED_READY


def test_49_correction_builder_unit():
    corr = build_correction_templates(
        batch_id="b1", packet_id="p",
        intake_plan={"validation_command": "cmd", "expected_label_files": []},
        invalid_by_file_basename={"nonconforming_file_1": ["forbidden_field", "duplicate_label"]})
    assert corr and corr[0]["reason_codes"] == ["duplicate_label", "forbidden_field"]
    assert corr[0]["file_basename"] == "nonconforming_file_1"


def test_50_adjudication_builder_no_conflict():
    adj = build_adjudication_handoff(batch_id="b1", conflict_pair_count=0, adjudication_needed_count=0)
    assert adj["adjudication_needed"] is False
    assert adj["no_auto_majority"] is True


def test_51_ready_to_contact_vs_awaiting_distinct(tmp_path):
    # 동일 queue, intake dir 존재 여부만 다름 → ready_to_contact vs awaiting_reviewer_return 분기.
    q = _queue()
    missing = Path(tmp_path) / "x"
    ready = _run(queue=q, intake_directory=str(missing), label_source=LABEL_SOURCE_PRODUCTION)
    awaiting = _run(queue=q, intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    assert ready["pilot_status"] == PILOT_READY_TO_CONTACT
    assert awaiting["pilot_status"] == PILOT_AWAITING_RETURN


def test_52_nonconforming_filename_masked_passthrough(tmp_path):
    # followup 의 가명 마스킹이 pilot 출력까지 보존(실명 파일명 미노출).
    q = _queue()
    m = _manifest(q)
    pid = sorted({p for _, p in _assignments(m)})[0]
    ps0 = sorted(m["pseudonymous_reviewers"])[0]
    (Path(tmp_path) / "realname_leak.jsonl").write_text(
        json.dumps(_row(ps0, pid, "same_event")), encoding="utf-8")
    out = _run(queue=q, intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    assert "realname_leak" not in json.dumps(out, ensure_ascii=False)
    assert out["nonconforming_filenames_count"] == 1


# ── 감사 fix-lock(adversarial MEDIUM ops_ui provenance·MEDIUM dir≠contact·LOW-MEDIUM whole-output guard·naming) ──
def test_53_ops_ui_contract_carries_gold_provenance():
    # ops_ui_contract 가 production_gold_count 를 노출하면서 provenance caveat 를 함께 실어야 한다(미검증 gold→
    # 검증된 truth 오인 차단). synthetic_gold_count 도 포함(합성/실 구분 신호).
    out = _run(queue=_queue())
    c = out["ops_ui_contract"]
    assert "production_gold_provenance_verified" in c
    assert c["production_gold_provenance_verified"] is False        # 선언 기반·미검증
    assert "synthetic_gold_count" in c
    assert c["flags"]["gold_provenance_verified"] is False


def test_54_pilot_executed_honesty_fields():
    # 번들 생성 ≠ pilot 실행 — 명시 필드로 못박는다(overclaim 가드).
    q = _queue()
    m = _manifest(q)
    out_none = _run(queue=q)
    assert out_none["pilot_executed"] is False
    assert out_none["real_reviewers_contacted"] == 0
    assert out_none["real_labels_returned"] == 0
    # 실 회수가 있어도 pilot_executed 는 False(handoff 모듈은 실행자가 아님)·real_labels_returned 만 passthrough.
    rows = _partial_rows(m, 1)
    out = _run(queue=q, label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
    assert out["pilot_executed"] is False
    assert out["real_labels_returned"] == out["returned_label_count"] == len(rows)


def test_55_whole_output_no_forbidden_keys(tmp_path):
    # 최상위 반환 dict 전체(bundle/templates/ops_ui/calibration/agent_contract 포함) 어디에도 forbidden 키 0.
    q = _queue()
    m = _manifest(q)
    for rows in (None, _partial_rows(m, 1), _conflict_rows(m),
                 _submit_all(m, lambda ps, pid: "same_event")):
        out = _run(queue=q, label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
        assert _forbidden_keys_in(out) == set()


def test_56_intake_directory_established_reflects_dir(tmp_path):
    # intake_directory_established=회수 경로 설정 프록시(reviewer 접촉 검증 아님) — dir 존재 여부를 반영.
    q = _queue()
    missing = Path(tmp_path) / "nope"
    ready = _run(queue=q, intake_directory=str(missing), label_source=LABEL_SOURCE_PRODUCTION)
    awaiting = _run(queue=q, intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    assert ready["intake_directory_established"] is False
    assert awaiting["intake_directory_established"] is True
    # 접촉 미검증 신호가 두 상태 모두에서 노출(dir 존재가 접촉으로 둔갑하지 않음).
    assert ready["actual_sending_performed"] is False
    assert awaiting["actual_sending_performed"] is False


def test_57_ops_ui_invalid_file_count_no_self_contradiction(tmp_path):
    # malformed JSONL 은 0행 파싱→invalid_label_count(행 단위)=0 이지만 invalid_returned 상태 → ops_ui_contract 가
    # invalid_file_count(파일 단위)로 모순을 해소(code-review LOW).
    q = _queue()
    m = _manifest(q)
    ps0 = sorted(m["pseudonymous_reviewers"])[0]
    (Path(tmp_path) / f"b1__{ps0}__labels.jsonl").write_text('{"broken": ', encoding="utf-8")
    out = _run(queue=q, intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["pilot_status"] == PILOT_INVALID_RETURNED
    c = out["ops_ui_contract"]
    assert c["invalid_label_count"] == 0          # 행 단위(malformed=0행)
    assert c["invalid_file_count"] >= 1           # 파일 단위 → invalid_returned 와 정합
