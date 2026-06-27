"""ADR#71 — reviewer pilot execution ledger + returned-labels monitor 테스트(병합 0·LLM 0·DB 0·전송 0).

커버: execution ledger(not_started/awaiting_operator_contact/contacted_waiting_return)·contact evidence PII-safe
검증(allowlist/enum/email-like/free-text 거부)·contacted 둔갑 금지(prepared≠contacted·evidence 없으면 0)·
declined/unavailable 분리·returned-label monitor(partial/invalid/conflict/calibration)·gold exact passthrough
(execution wrapper 만으로 production_gold_count 미증가)·operator SLA/checklist·overdue(as_of 기준)·ops UI execution
contract(internal_only/no_public_truth)·no merge/LLM/DB·전체 출력 forbidden-key 0·handoff decorate 발산 0·정책 lock.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.services.identity_human_labeling import SOURCE_LIVE, SOURCE_SYNTHETIC
from backend.app.tools.near_match_reviewer_queue import build_near_match_reviewer_queue
from backend.app.tools.reviewer_batch_launch import build_assignment_manifest
from backend.app.tools.reviewer_label_operations import (
    LABEL_SOURCE_PRODUCTION,
    LABEL_SOURCE_SYNTHETIC,
)
from backend.app.tools.reviewer_pilot_execution import (
    CONTACT_METHOD_LABELS,
    CONTACT_STATUSES,
    EXEC_AWAITING_CONTACT,
    EXEC_CALIBRATION,
    EXEC_CONFLICT,
    EXEC_CONTACTED_WAITING,
    EXEC_INVALID,
    EXEC_NOT_STARTED,
    EXEC_PARTIAL,
    EXECUTION_STATES,
    OPERATION_NAME,
    REVIEWER_PILOT_EXECUTION_AGENT_CONTRACT,
    _execution_status,
    run_reviewer_pilot_execution,
    validate_contact_evidence,
)
from backend.app.tools.reviewer_pilot_handoff import (
    _HANDOFF_FORBIDDEN_KEYS,
    PILOT_NOT_READY,
    PILOT_STATES,
    run_reviewer_pilot_handoff,
)
from backend.app.tools.source_overlap_discovery import (
    build_captured_overlap_fixture,
    discover_overlap,
)


# ── helpers ────────────────────────────────────────────────────────────────────────────────────────────
def _queue(*, reviewers=None, hard_neg=False, rpp=2):
    disc = discover_overlap(build_captured_overlap_fixture())
    return build_near_match_reviewer_queue(
        disc, packet_id="pilot_exec_test", reviewers=reviewers,
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


def _evidence(manifest, *, status="contacted", method="manual_email", due=None,
              pseudonyms=None, note=None):
    ps_list = pseudonyms if pseudonyms is not None else sorted(manifest["pseudonymous_reviewers"])
    out = []
    for ps in ps_list:
        rec = {"reviewer_pseudonym": ps, "contact_method_label": method, "contact_status": status}
        if due is not None:
            rec["due_hint"] = due
        if note is not None:
            rec["operator_note_code"] = note
        out.append(rec)
    return out


def _run(queue=None, **kw):
    if queue is None:
        queue = _queue()
    kw.setdefault("batch_id", "b1")
    kw.setdefault("packet_id", "pilot_exec_test")
    return run_reviewer_pilot_execution(queue=queue, **kw)


def _forbidden_keys_in(obj):
    found = set()
    if isinstance(obj, dict):
        found |= set(obj) & _HANDOFF_FORBIDDEN_KEYS
        for v in obj.values():
            found |= _forbidden_keys_in(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _forbidden_keys_in(v)
    return found


# ── §11.1-8: execution ledger / contact evidence ────────────────────────────────────────────────────────
def test_01_no_bundle_not_started():
    out = _run(queue={})
    assert out["pilot_status"] == PILOT_NOT_READY
    assert out["execution_status"] == EXEC_NOT_STARTED
    assert out["pilot_executed"] is False
    assert out["real_reviewers_contacted"] == 0


def test_02_bundle_ready_no_contact_awaiting():
    out = _run()
    assert out["execution_status"] == EXEC_AWAITING_CONTACT
    assert out["contact_evidence_present"] is False
    assert out["pilot_executed"] is False


def test_03_prepared_only_not_contacted():
    m = _manifest(_queue())
    out = _run(contact_evidence=_evidence(m, status="prepared"))
    # prepared 는 contacted 아님 — 여전히 awaiting_operator_contact·contacted 0.
    assert out["execution_status"] == EXEC_AWAITING_CONTACT
    assert out["real_reviewers_contacted"] == 0
    assert out["reviewers_prepared"] == 2
    assert out["pilot_executed"] is False


def test_04_contacted_increments():
    m = _manifest(_queue())
    out = _run(contact_evidence=_evidence(m, status="contacted"))
    assert out["execution_status"] == EXEC_CONTACTED_WAITING
    assert out["real_reviewers_contacted"] == 2
    assert out["pilot_executed"] is True
    assert sorted(out["reviewer_contacted_by_pseudonym"]) == sorted(m["pseudonymous_reviewers"])


def test_05_declined_separated_from_contacted():
    m = _manifest(_queue())
    ps = sorted(m["pseudonymous_reviewers"])
    ev = [{"reviewer_pseudonym": ps[0], "contact_method_label": "manual_email", "contact_status": "contacted"},
          {"reviewer_pseudonym": ps[1], "contact_method_label": "manual_slack", "contact_status": "declined"}]
    out = _run(contact_evidence=ev)
    assert out["real_reviewers_contacted"] == 1
    assert out["reviewers_declined"] == 1
    # 접촉 시도(declined 포함)가 있으므로 awaiting 에서 벗어난다.
    assert out["execution_status"] == EXEC_CONTACTED_WAITING


def test_06_unavailable_only_not_contacted_waiting():
    # adversarial F1: unavailable-only(contacted=0)는 "회수 대기"로 둔갑 금지 — awaiting_operator_contact(대체 재배포).
    m = _manifest(_queue())
    out = _run(contact_evidence=_evidence(m, status="unavailable"))
    assert out["reviewers_unavailable"] == 2
    assert out["real_reviewers_contacted"] == 0
    assert out["pilot_executed"] is False
    assert out["execution_status"] == EXEC_AWAITING_CONTACT


def test_06b_declined_only_not_contacted_waiting():
    # adversarial F1: declined-only 도 미접촉 — awaiting_operator_contact(영영 안 올 라벨을 기다리라고 오도 금지).
    m = _manifest(_queue())
    out = _run(contact_evidence=_evidence(m, status="declined"))
    assert out["reviewers_declined"] == 2
    assert out["real_reviewers_contacted"] == 0
    assert out["execution_status"] == EXEC_AWAITING_CONTACT


def test_07_raw_pii_key_rejected():
    m = _manifest(_queue())
    for bad in ("reviewer_name", "name", "email", "phone"):
        ev = _evidence(m, status="contacted")
        ev[0][bad] = "leak"
        with pytest.raises(ValueError):
            _run(contact_evidence=ev)


def test_08_score_rationale_predicted_key_rejected():
    m = _manifest(_queue())
    for bad in ("score", "model_score", "rationale", "predicted_status"):
        ev = _evidence(m, status="contacted")
        ev[0][bad] = "leak"
        with pytest.raises(ValueError):
            _run(contact_evidence=ev)


# ── §11.9-16: returned labels monitor ───────────────────────────────────────────────────────────────────
def test_09_contacted_no_labels_waiting():
    m = _manifest(_queue())
    out = _run(contact_evidence=_evidence(m, status="contacted"))
    assert out["execution_status"] == EXEC_CONTACTED_WAITING
    assert out["returned_label_count"] == 0


def test_10_no_evidence_no_labels_awaiting():
    out = _run()
    assert out["execution_status"] == EXEC_AWAITING_CONTACT
    assert out["returned_label_count"] == 0
    assert out["production_gold_count"] == 0


def test_11_partial_returned():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_partial_rows(m, 1), label_source=LABEL_SOURCE_PRODUCTION,
               contact_evidence=_evidence(m, status="contacted"))
    assert out["execution_status"] == EXEC_PARTIAL
    assert 0 < out["returned_label_count"] < out["expected_label_count"]


def test_12_invalid_returned():
    q = _queue()
    m = _manifest(q)
    rows = _submit_all(m, lambda ps, pid: "same_event")
    rows[0]["score"] = 0.9   # forbidden field → invalid.
    out = _run(queue=q, label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION,
               contact_evidence=_evidence(m, status="contacted"))
    assert out["execution_status"] == EXEC_INVALID
    assert out["invalid_label_count"] > 0


def test_13_conflict_pending():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_conflict_rows(m), label_source=LABEL_SOURCE_PRODUCTION,
               contact_evidence=_evidence(m, status="contacted"))
    assert out["execution_status"] == EXEC_CONFLICT
    assert out["conflict_pair_count"] > 0


def test_14_calibration_pending():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_submit_all(m, lambda ps, pid: "same_event"),
               label_source=LABEL_SOURCE_PRODUCTION, contact_evidence=_evidence(m, status="contacted"))
    # 전원 합의·완전 회수이나 gold floor(live 200) 미충족 → calibration_pending.
    assert out["execution_status"] == EXEC_CALIBRATION
    assert out["calibration_ready"] is False
    assert out["merge_gate_ready"] is False


def test_15_returned_labels_exact_passthrough():
    q = _queue()
    m = _manifest(q)
    rows = _submit_all(m, lambda ps, pid: "same_event")
    direct = run_reviewer_pilot_handoff(
        queue=q, batch_id="b1", packet_id="pilot_exec_test",
        label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
    out = _run(queue=q, label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
    # execution wrapper 는 handoff 결과를 그대로 passthrough(발산 0).
    for k in ("returned_label_count", "expected_label_count", "missing_label_count",
              "invalid_label_count", "conflict_pair_count", "production_gold_count",
              "synthetic_gold_count", "calibration_ready", "merge_gate_ready"):
        assert out[k] == direct[k], k


def test_16_execution_wrapper_does_not_modify_production_gold():
    q = _queue()
    m = _manifest(q)
    rows = _submit_all(m, lambda ps, pid: "same_event")
    # contact evidence 유무와 무관하게 production_gold_count 동일(execution 만으로 미증가).
    with_ev = _run(queue=q, label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION,
                   contact_evidence=_evidence(m, status="contacted"))
    without_ev = _run(queue=q, label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
    assert with_ev["production_gold_count"] == without_ev["production_gold_count"]


def test_17_synthetic_labels_no_production_gold():
    q = _queue()
    m = _manifest(q)
    rows = _submit_all(m, lambda ps, pid: "same_event", ds=SOURCE_SYNTHETIC)
    direct = run_reviewer_pilot_handoff(
        queue=q, batch_id="b1", packet_id="pilot_exec_test",
        label_rows=rows, label_source=LABEL_SOURCE_SYNTHETIC)
    out = _run(queue=q, label_rows=rows, label_source=LABEL_SOURCE_SYNTHETIC,
               contact_evidence=_evidence(m, status="contacted"))
    assert out["production_gold_count"] == 0
    # synthetic same_event 합의 → synthetic gold 산출(>0)·production 은 0(exact passthrough·둔갑 0).
    assert out["synthetic_gold_count"] == direct["synthetic_gold_count"] > 0


def test_18_labels_override_contact_dimension():
    # contacted + partial labels → contact 축이 아니라 returned label 상태(partial)를 따른다.
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_partial_rows(m, 1), label_source=LABEL_SOURCE_PRODUCTION,
               contact_evidence=_evidence(m, status="contacted"))
    assert out["execution_status"] == EXEC_PARTIAL


# ── §11.17-24: SLA / checklist ──────────────────────────────────────────────────────────────────────────
def test_19_checklist_one_per_reviewer():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, contact_evidence=_evidence(m, status="contacted"))
    pseudonyms = {c["reviewer_pseudonym"] for c in out["operator_action_checklist"]}
    assert pseudonyms == set(m["pseudonymous_reviewers"])


def test_20_checklist_pseudonym_only_no_pii():
    out = _run(contact_evidence=_evidence(_manifest(_queue()), status="contacted"))
    assert _forbidden_keys_in(out["operator_action_checklist"]) == set()


def test_21_due_hint_preserved_per_reviewer():
    m = _manifest(_queue())
    out = _run(contact_evidence=_evidence(m, status="contacted", due="2026-06-30"))
    assert all(c["due_hint"] == "2026-06-30" for c in out["operator_action_checklist"])


def test_22_overdue_computed_when_as_of_past_due():
    m = _manifest(_queue())
    out = _run(contact_evidence=_evidence(m, status="contacted", due="2026-06-30"), as_of="2026-07-05")
    assert out["overdue_count"] == 2
    assert all(c["overdue"] for c in out["operator_action_checklist"])


def test_23_overdue_false_without_as_of():
    m = _manifest(_queue())
    out = _run(contact_evidence=_evidence(m, status="contacted", due="2026-06-30"))
    assert out["overdue_count"] == 0
    assert not any(c["overdue"] for c in out["operator_action_checklist"])


def test_24_missing_reviewer_next_action():
    # 미접촉 + 미회수 → send_manual_handoff.
    out = _run()
    assert all(c["next_action"] == "send_manual_handoff" for c in out["operator_action_checklist"])


def test_25_sla_status_fields():
    m = _manifest(_queue())
    out = _run(contact_evidence=_evidence(m, status="contacted"))
    sla = out["sla_status"]
    assert sla["reviewers_total"] == 2
    assert sla["reviewers_contacted"] == 2
    assert sla["raw_roster_committed"] is False
    assert sla["actual_sending_performed"] is False


def test_26_overdue_count_matches_checklist():
    m = _manifest(_queue())
    out = _run(contact_evidence=_evidence(m, status="contacted", due="2026-06-30"), as_of="2026-07-05")
    assert out["overdue_count"] == sum(1 for c in out["operator_action_checklist"] if c["overdue"])


# ── §11.25-29: PII / secret boundary ────────────────────────────────────────────────────────────────────
def test_27_email_like_pseudonym_rejected():
    with pytest.raises(ValueError):
        validate_contact_evidence(
            [{"reviewer_pseudonym": "hong@corp.com", "contact_method_label": "manual_email",
              "contact_status": "contacted"}], batch_id="b1")


def test_28_unknown_key_rejected_allowlist():
    with pytest.raises(ValueError):
        validate_contact_evidence(
            [{"reviewer_pseudonym": "rv1", "contact_method_label": "manual_email",
              "contact_status": "contacted", "full_name": "Hong Gildong"}], batch_id="b1")


def test_29_free_text_note_rejected():
    with pytest.raises(ValueError):
        validate_contact_evidence(
            [{"reviewer_pseudonym": "rv1", "contact_method_label": "manual_email",
              "contact_status": "contacted", "operator_note_code": "called Hong at home number"}],
            batch_id="b1")


def test_30_whole_output_no_forbidden_keys():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_submit_all(m, lambda ps, pid: "same_event"),
               label_source=LABEL_SOURCE_PRODUCTION, contact_evidence=_evidence(m, status="contacted"))
    assert _forbidden_keys_in(out) == set()
    assert out["raw_pii_exposed"] is False
    assert out["reviewer_ids_pseudonymous"] is True


# ── §11.30-38: ops UI execution contract ────────────────────────────────────────────────────────────────
def test_31_ops_ui_contract_name():
    out = _run(contact_evidence=_evidence(_manifest(_queue()), status="contacted"))
    assert out["ops_ui_contract"]["contract"] == "InternalOpsPilotExecutionStatus"


def test_32_ops_ui_has_execution_status():
    m = _manifest(_queue())
    out = _run(contact_evidence=_evidence(m, status="contacted"))
    c = out["ops_ui_contract"]
    assert c["execution_status"] == out["execution_status"]
    assert c["contact_evidence_present"] is True
    assert c["real_reviewers_contacted"] == 2


def test_33_ops_ui_internal_only_no_public_truth():
    out = _run()
    flags = out["ops_ui_contract"]["flags"]
    assert flags["internal_only"] is True
    assert flags["no_public_truth"] is True


def test_34_ops_ui_no_merge_no_public_iu():
    out = _run()
    flags = out["ops_ui_contract"]["flags"]
    assert flags["no_merge"] is True
    assert flags["no_public_iu"] is True


def test_35_ops_ui_no_llm_no_db():
    out = _run()
    flags = out["ops_ui_contract"]["flags"]
    assert flags["no_llm"] is True
    assert flags["no_db_write"] is True


def test_36_ops_ui_pii_safe_provenance_caveat():
    out = _run()
    c = out["ops_ui_contract"]
    assert c["flags"]["pii_safe"] is True
    # gold provenance 미검증 caveat 동반(미검증 gold 가 truth 로 박제되지 않게).
    assert c["production_gold_provenance_verified"] is False
    assert c["flags"]["gold_provenance_verified"] is False


def test_37_ops_ui_does_not_expose_same_event_truth():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_submit_all(m, lambda ps, pid: "same_event"),
               label_source=LABEL_SOURCE_PRODUCTION)
    c = out["ops_ui_contract"]
    # contract 는 workflow state 만 — same_event/label/verdict truth 키 0.
    assert "label" not in c
    assert "same_event" not in c
    assert "verdict" not in c


# ── §11.39-44: no merge / LLM / DB ──────────────────────────────────────────────────────────────────────
def test_38_merge_allowed_false():
    out = _run()
    assert out["merge_allowed"] is False
    assert out["no_merge_without_gold"] is True


def test_39_no_public_intelligence_unit():
    assert _run()["no_public_intelligence_unit"] is True


def test_40_no_db_write():
    assert _run()["db_write"] is False


def test_41_no_llm_no_embedding():
    out = _run()
    assert out["llm_invoked"] is False
    assert out["embedding_invoked"] is False


def test_42_merge_gate_ready_not_forced():
    out = _run(contact_evidence=_evidence(_manifest(_queue()), status="contacted"))
    assert out["merge_gate_ready"] is False


def test_43_actual_sending_never_performed():
    m = _manifest(_queue())
    out = _run(contact_evidence=_evidence(m, status="contacted"))
    assert out["actual_sending_performed"] is False
    assert out["sla_status"]["actual_sending_performed"] is False


def test_44_labeler_hidden_flags():
    out = _run()
    assert out["score_hidden_from_labeler"] is True
    assert out["rationale_hidden_from_labeler"] is True
    assert out["predicted_status_hidden"] is True


# ── §11.45-: contract / policy lock + regression ────────────────────────────────────────────────────────
def test_45_operation_name():
    assert _run()["operation_name"] == OPERATION_NAME == "reviewer_pilot_execution"


def test_46_execution_states_count():
    assert len(EXECUTION_STATES) == 8


def test_47_agent_contract_cannot():
    cannot = REVIEWER_PILOT_EXECUTION_AGENT_CONTRACT["cannot"]
    joined = " ".join(cannot)
    assert "merge 실행" in cannot
    assert "actual email/slack/webhook 전송" in cannot
    assert "contact evidence 임의 생성" in cannot
    assert "reviewer raw PII 출력" in joined


def test_48_agent_contract_embedding_no_go():
    interface = REVIEWER_PILOT_EXECUTION_AGENT_CONTRACT["embedding_llm_adjudicator"]
    assert "status" in interface
    assert "No-Go" in interface["status"]


def test_49_invalid_label_source_rejected():
    with pytest.raises(ValueError):
        _run(label_source="bogus")


def test_50_contact_evidence_not_list_rejected():
    with pytest.raises(ValueError):
        _run(contact_evidence={"reviewer_pseudonym": "rv1"})


def test_51_bad_method_enum_rejected():
    with pytest.raises(ValueError):
        validate_contact_evidence(
            [{"reviewer_pseudonym": "rv1", "contact_method_label": "auto_blast",
              "contact_status": "contacted"}], batch_id="b1")


def test_52_bad_status_enum_rejected():
    with pytest.raises(ValueError):
        validate_contact_evidence(
            [{"reviewer_pseudonym": "rv1", "contact_method_label": "manual_email",
              "contact_status": "sent"}], batch_id="b1")


def test_53_block_reasons_reflect_execution_status():
    out = _run()
    assert "awaiting_operator_contact" in out["block_reasons"]


def test_54_enum_constants_locked():
    assert CONTACT_METHOD_LABELS == {"manual_email", "manual_slack", "manual_dm", "manual_other"}
    assert CONTACT_STATUSES == {"prepared", "contacted", "declined", "unavailable"}


def test_55_handoff_decorate_independent():
    # ADR#70 handoff 가 execution wrapper 없이도 독립 작동(decorate 가 깨뜨리지 않음).
    q = _queue()
    direct = run_reviewer_pilot_handoff(queue=q, batch_id="b1", packet_id="pilot_exec_test")
    assert direct["pilot_status"] in {"ready_to_contact", "awaiting_reviewer_return", "not_ready"}
    assert direct["merge_allowed"] is False


def test_56_filesystem_intake_basename_only(tmp_path):
    q = _queue()
    m = _manifest(q)
    d = Path(tmp_path) / "intake"
    d.mkdir()
    rows = _submit_all(m, lambda ps, pid: "same_event")
    by_ps: dict = {}
    for r in rows:
        by_ps.setdefault(r["reviewer_id"], []).append(r)
    for ps, rws in by_ps.items():
        (d / f"b1__{ps}__labels.jsonl").write_text(
            "\n".join(json.dumps(x) for x in rws), encoding="utf-8")
    out = _run(queue=q, intake_directory=str(d), label_source=LABEL_SOURCE_PRODUCTION,
               contact_evidence=_evidence(m, status="contacted"))
    assert _forbidden_keys_in(out) == set()
    # 절대경로 사용자명 미노출(_display_path 경유).
    assert "Users" not in json.dumps(out["returned_label_files"])


def test_57_evidence_none_means_zero_contact():
    out = _run(contact_evidence=None)
    assert out["contact_evidence_present"] is False
    assert out["real_reviewers_contacted"] == 0
    assert out["execution_status"] == EXEC_AWAITING_CONTACT


# ── 감사 fix-lock(adversarial F1-F3·code-review CR#1-#3) ────────────────────────────────────────────────
def test_58_due_hint_value_pii_rejected():
    # adversarial F2: due_hint 값에 raw PII/자유 텍스트 → 출력 누출 전 fail-loud(키-allowlist 위 값-레벨 가드).
    for bad in ("hong@corp.com", "010-1234-5678 Hong", "call him at home"):
        with pytest.raises(ValueError):
            validate_contact_evidence(
                [{"reviewer_pseudonym": "rv1", "contact_method_label": "manual_email",
                  "contact_status": "contacted", "due_hint": bad}], batch_id="b1")


def test_59_pseudonym_name_rejected():
    # adversarial F2: 공백 포함 raw 이름 거부(pseudonym charset).
    with pytest.raises(ValueError):
        validate_contact_evidence(
            [{"reviewer_pseudonym": "Hong Gildong", "contact_method_label": "manual_email",
              "contact_status": "contacted"}], batch_id="b1")


def test_60_pseudonym_phone_rejected():
    # adversarial F2: 전부 숫자/대시(전화번호) raw PII 거부.
    with pytest.raises(ValueError):
        validate_contact_evidence(
            [{"reviewer_pseudonym": "010-1234-5678", "contact_method_label": "manual_email",
              "contact_status": "contacted"}], batch_id="b1")


def test_61_ghost_pseudonym_not_counted():
    # adversarial F3: roster 밖 유령 pseudonym 은 contacted 부풀리기 0·정합성 신호 표면화.
    q = _queue()
    m = _manifest(q)
    ps = sorted(m["pseudonymous_reviewers"])
    ev = [{"reviewer_pseudonym": ps[0], "contact_method_label": "manual_email", "contact_status": "contacted"},
          {"reviewer_pseudonym": "rv_ghost99", "contact_method_label": "manual_email", "contact_status": "contacted"}]
    out = _run(queue=q, contact_evidence=ev)
    assert out["real_reviewers_contacted"] == 1
    assert out["real_reviewers_contacted"] <= out["sla_status"]["reviewers_total"]
    assert out["evidence_for_unknown_pseudonym_count"] == 1


def test_62_cross_batch_evidence_rejected():
    # code-review CR#3: rec batch_id 가 run batch_id 와 다르면 cross-batch 오염 거부.
    with pytest.raises(ValueError):
        validate_contact_evidence(
            [{"batch_id": "OTHER", "reviewer_pseudonym": "rv1", "contact_method_label": "manual_email",
              "contact_status": "contacted"}], batch_id="b1")


def test_63_pilot_to_exec_mapping_complete():
    # adversarial F4: not_ready 외 어떤 pilot_status 도 not_started 로 조용히 둔갑하지 않음(.get 폴백 가드).
    for ps in PILOT_STATES:
        for active in (True, False):
            es = _execution_status(ps, any_active_contact=active)
            assert es in EXECUTION_STATES
            if ps == PILOT_NOT_READY:
                assert es == EXEC_NOT_STARTED
            else:
                assert es != EXEC_NOT_STARTED


def test_64_unhashable_enum_value_value_error():
    # code-review CR#1: unhashable(list/dict) enum 값에 TypeError 아닌 ValueError(fail-loud 계약 유지).
    with pytest.raises(ValueError):
        validate_contact_evidence(
            [{"reviewer_pseudonym": "rv1", "contact_method_label": ["manual_email"],
              "contact_status": "contacted"}], batch_id="b1")
    with pytest.raises(ValueError):
        validate_contact_evidence(
            [{"reviewer_pseudonym": "rv1", "contact_method_label": "manual_email",
              "contact_status": {"x": 1}}], batch_id="b1")


def test_65_non_ascii_note_rejected():
    # code-review CR#2: operator_note_code 비-ASCII(한글 이름 등) 거부(isalnum Unicode 우회 차단).
    with pytest.raises(ValueError):
        validate_contact_evidence(
            [{"reviewer_pseudonym": "rv1", "contact_method_label": "manual_email",
              "contact_status": "contacted", "operator_note_code": "홍길동연락처"}], batch_id="b1")
