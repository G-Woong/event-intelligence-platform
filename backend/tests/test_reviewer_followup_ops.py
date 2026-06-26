"""ADR#69 — reviewer follow-up operations + label collection status cockpit 테스트(병합 0·LLM 0·DB 0·전송 0).

커버: follow-up status 7-state(not_launchable/no_labels/partial/invalid/conflict_pending/calibration_pending/
imported_ready)·expected vs actual coverage·reminder/escalation template(PII-safe·전송 0)·partial label status·
reviewer SLA/capacity·gold passthrough(production_gold_count 미증가)·no merge/LLM/DB·secret/PII 경계·정책 lock.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.app.services.identity_human_labeling import SOURCE_LIVE, SOURCE_SYNTHETIC
from backend.app.tools.near_match_reviewer_queue import build_near_match_reviewer_queue
from backend.app.tools.production_label_intake import run_production_label_intake
from backend.app.tools.reviewer_batch_launch import build_assignment_manifest
from backend.app.tools.reviewer_followup_ops import (
    _REMINDER_FORBIDDEN_KEYS,
    FOLLOWUP_CALIBRATION_PENDING,
    FOLLOWUP_CONFLICT_PENDING,
    FOLLOWUP_INVALID,
    FOLLOWUP_NO_LABELS,
    FOLLOWUP_NOT_LAUNCHABLE,
    FOLLOWUP_PARTIAL,
    FOLLOWUP_STATES,
    OPERATION_NAME,
    REMINDER_FIRST,
    REMINDER_MISSING,
    REVIEWER_FOLLOWUP_AGENT_CONTRACT,
    build_escalation_actions,
    build_reminder_templates,
    compute_coverage,
    run_reviewer_followup_ops,
)
from backend.app.tools.reviewer_label_operations import (
    LABEL_SOURCE_PRODUCTION,
    LABEL_SOURCE_SYNTHETIC,
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
        disc, packet_id="followup_test", reviewers=reviewers,
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
    kw.setdefault("packet_id", "followup_test")
    return run_reviewer_followup_ops(**kw)


# ── §10.1-7: follow-up status ───────────────────────────────────────────────────────────────────────────
def test_01_no_assignments_not_launchable():
    out = _run(queue={})
    assert out["followup_status"] == FOLLOWUP_NOT_LAUNCHABLE
    assert out["assignment_count"] == 0
    assert "not_launchable" in out["block_reasons"]


def test_02_assignments_no_labels():
    out = _run(queue=_queue())
    assert out["followup_status"] == FOLLOWUP_NO_LABELS
    assert out["submitted_label_count"] == 0
    assert out["expected_label_count"] > 0


def test_03_some_labels_missing_partial():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_partial_rows(m, 1), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["followup_status"] == FOLLOWUP_PARTIAL
    assert out["missing_label_count"] > 0
    assert out["submitted_label_count"] > 0


def test_04_invalid_label_file():
    q = _queue()
    m = _manifest(q)
    (ps, pid) = _assignments(m)[0]
    rows = [_row(ps, pid, "same_event", extra={"score": 0.9})]   # forbidden field.
    out = _run(queue=q, label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
    assert out["followup_status"] == FOLLOWUP_INVALID
    assert "invalid_labels" in out["block_reasons"]


def test_05_valid_labels_conflict_pending():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_conflict_rows(m), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["missing_label_count"] == 0           # full coverage
    assert out["followup_status"] == FOLLOWUP_CONFLICT_PENDING
    assert out["conflict_pair_count"] >= 1


def test_06_valid_labels_calibration_pending():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_submit_all(m, lambda ps, pid: "same_event"),
               label_source=LABEL_SOURCE_PRODUCTION)
    assert out["missing_label_count"] == 0
    assert out["conflict_pair_count"] == 0
    assert out["followup_status"] == FOLLOWUP_CALIBRATION_PENDING
    assert out["calibration_ready"] is False


def test_07_merge_allowed_false_in_all_states():
    q = _queue()
    m = _manifest(q)
    states = [
        _run(queue={}),
        _run(queue=q),
        _run(queue=q, label_rows=_partial_rows(m, 1), label_source=LABEL_SOURCE_PRODUCTION),
        _run(queue=q, label_rows=_conflict_rows(m), label_source=LABEL_SOURCE_PRODUCTION),
        _run(queue=q, label_rows=_submit_all(m, lambda ps, pid: "same_event"),
             label_source=LABEL_SOURCE_PRODUCTION),
    ]
    for out in states:
        assert out["merge_allowed"] is False
        assert out["merge_gate_ready"] is False
        assert out["followup_status"] in FOLLOWUP_STATES


# ── §10.8-18: expected vs actual ────────────────────────────────────────────────────────────────────────
def test_08_expected_label_count():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q)
    assert out["expected_label_count"] == m["assignments_count"]


def test_09_submitted_label_count():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_partial_rows(m, 1), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["submitted_label_count"] == len(_partial_rows(m, 1))


def test_10_missing_label_count():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_partial_rows(m, 1), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["missing_label_count"] == m["assignments_count"] - out["submitted_label_count"]


def test_11_pair_coverage_rate():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_partial_rows(m, 1), label_source=LABEL_SOURCE_PRODUCTION)
    pairs = len({pid for _, pid in _assignments(m)})
    assert out["pair_coverage_rate"] == round(1 / pairs, 4)


def test_12_reviewer_coverage_rate():
    q = _queue()
    m = _manifest(q)
    # 첫 pair 만 회수해도 그 pair 에 양 reviewer 가 참여 → reviewer_coverage 1.0.
    out = _run(queue=q, label_rows=_partial_rows(m, 1), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["reviewer_coverage_rate"] == 1.0


def test_13_missing_by_reviewer_pseudonym():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_partial_rows(m, 1), label_source=LABEL_SOURCE_PRODUCTION)
    mbr = out["missing_by_reviewer_pseudonym"]
    assert mbr
    for ps, pids in mbr.items():
        assert ps.startswith("rv_")             # pseudonym only
        assert all(isinstance(p, str) for p in pids)


def test_14_missing_by_pair_id():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_partial_rows(m, 1), label_source=LABEL_SOURCE_PRODUCTION)
    submitted_pair = sorted({pid for _, pid in _assignments(m)})[0]
    assert submitted_pair not in out["missing_by_pair_id"]   # 회수된 pair 는 missing 아님
    assert len(out["missing_by_pair_id"]) > 0


def test_15_duplicate_labels_counted():
    q = _queue()
    m = _manifest(q)
    (ps, pid) = _assignments(m)[0]
    out = _run(queue=q, label_rows=[_row(ps, pid, "same_event"), _row(ps, pid, "same_event")],
               label_source=LABEL_SOURCE_PRODUCTION)
    assert out["duplicate_label_count"] >= 1
    assert out["followup_status"] == FOLLOWUP_INVALID


def test_16_unknown_pair_id_counted():
    q = _queue()
    m = _manifest(q)
    ps = _assignments(m)[0][0]
    out = _run(queue=q, label_rows=[_row(ps, "no_such_pair", "same_event")],
               label_source=LABEL_SOURCE_PRODUCTION)
    assert out["unknown_pair_id_count"] >= 1
    assert out["followup_status"] == FOLLOWUP_INVALID


def test_17_forbidden_field_counted():
    q = _queue()
    m = _manifest(q)
    (ps, pid) = _assignments(m)[0]
    out = _run(queue=q, label_rows=[_row(ps, pid, "same_event", extra={"predicted_status": "likely_same"})],
               label_source=LABEL_SOURCE_PRODUCTION)
    assert out["forbidden_field_count"] >= 1
    assert "forbidden_field" in out["block_reasons"]


def test_18_model_label_rejected_counted():
    q = _queue()
    m = _manifest(q)
    (ps, pid) = _assignments(m)[0]
    out = _run(queue=q, label_rows=[_row(ps, pid, "same_event", extra={"reviewer_kind": "model"})],
               label_source=LABEL_SOURCE_PRODUCTION)
    assert out["model_label_rejected_count"] >= 1
    assert "non_human_label" in out["block_reasons"]


# ── §10.19-28: reminder / escalation ────────────────────────────────────────────────────────────────────
def test_19_no_labels_first_reminder():
    out = _run(queue=_queue())
    assert out["reminder_templates"]
    assert all(t["template_type"] == REMINDER_FIRST for t in out["reminder_templates"])
    assert any(a["action_type"] == "send_first_reminder" for a in out["escalation_actions"])


def test_20_partial_missing_reminder():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_partial_rows(m, 1), label_source=LABEL_SOURCE_PRODUCTION)
    assert any(t["template_type"] == REMINDER_MISSING for t in out["reminder_templates"])
    assert any(a["action_type"] == "send_missing_label_reminder" for a in out["escalation_actions"])


def test_21_invalid_correction_request():
    q = _queue()
    m = _manifest(q)
    (ps, pid) = _assignments(m)[0]
    out = _run(queue=q, label_rows=[_row(ps, pid, "same_event", extra={"model_score": 1})],
               label_source=LABEL_SOURCE_PRODUCTION)
    corr = [a for a in out["escalation_actions"] if a["action_type"] == "send_correction_request"]
    assert corr
    assert corr[0]["reason_codes"]               # reason code 존재
    assert out["invalid_by_file_basename"]       # basename → reason code


def test_22_conflict_adjudication_action():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_conflict_rows(m), label_source=LABEL_SOURCE_PRODUCTION)
    assert any(a["action_type"] == "assign_human_adjudicator" for a in out["escalation_actions"])
    assert out["adjudication_needed_count"] >= 1


def test_23_insufficient_capacity_escalation():
    # reviewers_per_pair=1 로 1인 배정 queue 빌드(>=2 distinct 요구 회피) → manifest capacity insufficient.
    q = _queue(reviewers=["solo"], rpp=1)
    out = _run(queue=q)
    assert out["reviewer_capacity_status"] != "ok"
    assert any(a["action_type"] == "assign_more_reviewers" for a in out["escalation_actions"])
    assert "insufficient_reviewer_capacity" in out["block_reasons"]


def test_24_calibration_pending_collect_more():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_submit_all(m, lambda ps, pid: "same_event"),
               label_source=LABEL_SOURCE_PRODUCTION)
    assert out["followup_status"] == FOLLOWUP_CALIBRATION_PENDING
    assert any(a["action_type"] == "collect_more_labels" for a in out["escalation_actions"])


def test_25_templates_contain_reviewer_pseudonym():
    out = _run(queue=_queue())
    for t in out["reminder_templates"]:
        assert t["reviewer_pseudonym"].startswith("rv_")
        assert t["reviewer_pseudonym"] in t["message"]


def test_26_templates_no_raw_pii():
    out = _run(queue=_queue())
    blob = json.dumps(out["reminder_templates"], ensure_ascii=False)
    assert _RAW_REVIEWER_MARKER not in blob       # raw reviewer id 미노출(pseudonym only)
    assert "@" not in blob                         # email 부재


def test_27_templates_no_score_rationale_predicted():
    out = _run(queue=_queue())
    blob = json.dumps(out["reminder_templates"], ensure_ascii=False)
    assert "score" not in blob.lower()
    assert "rationale" not in blob.lower()
    assert "predicted_status" not in blob.lower()
    for t in out["reminder_templates"]:
        assert not (set(t) & _REMINDER_FORBIDDEN_KEYS)


def test_28_templates_have_no_transport_side_channel():
    # 전송 0 — reminder/escalation artifact 는 데이터만(email/slack/webhook 전송 필드/호출 없음).
    # (agent_contract 는 "webhook 전송 금지"를 명시하므로 검사 범위에서 제외 — 금지 선언은 정당.)
    out = _run(queue=_queue())
    artifacts = json.dumps(
        {"reminders": out["reminder_templates"], "escalations": out["escalation_actions"],
         "operator_next_actions": out["operator_next_actions"]}, ensure_ascii=False).lower()
    for forbidden in ("smtp", "webhook", "slack_token", "sendgrid", "mailto:", "http://", "https://"):
        assert forbidden not in artifacts
    for a in out["escalation_actions"]:
        assert "action_type" in a                  # action 명세일 뿐(실행 아님)


# ── §10.29-34: PII / secret ─────────────────────────────────────────────────────────────────────────────
def test_29_raw_roster_not_committed_flag():
    out = _run(queue=_queue())
    assert out["reviewer_sla"]["raw_roster_committed"] is False
    assert out["raw_pii_exposed"] is False
    assert out["reviewer_ids_pseudonymous"] is True


def test_30_local_mapping_not_required():
    # 전체 출력에 raw reviewer id 없음 — pseudonym/basename/pair_id 만으로 운영 가능.
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_partial_rows(m, 1), label_source=LABEL_SOURCE_PRODUCTION)
    assert _RAW_REVIEWER_MARKER not in json.dumps(out, ensure_ascii=False)


def test_31_file_basename_only(tmp_path):
    q = _queue()
    m = _manifest(q)
    ps0 = sorted(m["pseudonymous_reviewers"])[0]
    pairs = sorted({pid for _, pid in _assignments(m)})
    _write_reviewer_file(tmp_path, "b1", ps0, [_row(ps0, pairs[0], "same_event")])
    out = _run(queue=q, intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    for f in out["actual_label_files"]:
        assert "/" not in f and "\\" not in f      # basename only


def test_32_absolute_path_sanitized(tmp_path):
    q = _queue()
    out = _run(queue=q, intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    disp = out["intake_directory"]
    assert "Users" not in disp and ":" not in disp  # 사용자명/드라이브 미노출(basename/relative)


def test_33_no_secret_no_external():
    q = _queue()
    m = _manifest(q)
    (ps, pid) = _assignments(m)[0]
    # secret-looking 값을 forbidden field 로 주입 → 거부되고 값은 출력에 없어야 한다.
    secret = "sk-this-must-never-appear"
    out = _run(queue=q, label_rows=[_row(ps, pid, "same_event", extra={"api_key": secret})],
               label_source=LABEL_SOURCE_PRODUCTION)
    assert secret not in json.dumps(out, ensure_ascii=False)
    assert out["llm_invoked"] is False and out["embedding_invoked"] is False and out["db_write"] is False


def test_34_forbidden_secret_rejected_value_absent():
    q = _queue()
    m = _manifest(q)
    (ps, pid) = _assignments(m)[0]
    out = _run(queue=q, label_rows=[_row(ps, pid, "same_event", extra={"secret": "topsecret-xyz"})],
               label_source=LABEL_SOURCE_PRODUCTION)
    assert out["followup_status"] == FOLLOWUP_INVALID
    assert "topsecret-xyz" not in json.dumps(out, ensure_ascii=False)


# ── §10.35-40: no merge / LLM / DB ──────────────────────────────────────────────────────────────────────
def test_35_no_public_intelligence_unit():
    assert _run(queue=_queue())["no_public_intelligence_unit"] is True


def test_36_no_db_write():
    assert _run(queue=_queue())["db_write"] is False


def test_37_no_llm_invoked():
    assert _run(queue=_queue())["llm_invoked"] is False


def test_38_no_embedding_invoked():
    assert _run(queue=_queue())["embedding_invoked"] is False


def test_39_production_gold_not_changed_by_followup():
    q = _queue()
    m = _manifest(q)
    rows = _submit_all(m, lambda ps, pid: "same_event")
    followup = _run(queue=q, label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
    intake = run_production_label_intake(
        queue=q, batch_id="b1", packet_id="followup_test", label_rows=rows,
        label_source=LABEL_SOURCE_PRODUCTION)
    # exact passthrough — follow-up 은 production_gold_count 를 재계산/증가시키지 않는다.
    assert followup["production_gold_count"] == intake["production_gold_count"]
    # no-labels follow-up 은 항상 0(정직).
    assert _run(queue=q)["production_gold_count"] == 0


def test_40_merge_gate_ready_not_forced_true():
    q = _queue()
    m = _manifest(q)
    for rows in (None, _partial_rows(m, 1), _submit_all(m, lambda ps, pid: "same_event")):
        out = _run(queue=q, label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
        assert out["merge_gate_ready"] is False


# ── filesystem 경로(실 reviewer 파일 회수 시뮬레이션) ───────────────────────────────────────────────────
def test_41_filesystem_partial_then_full(tmp_path):
    q = _queue()
    m = _manifest(q)
    pairs = sorted({pid for _, pid in _assignments(m)})
    ps_list = sorted(m["pseudonymous_reviewers"])
    # reviewer 0 가 첫 pair 만 제출 → partial.
    _write_reviewer_file(tmp_path, "b1", ps_list[0], [_row(ps_list[0], pairs[0], "same_event")])
    out = _run(queue=q, intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["followup_status"] == FOLLOWUP_PARTIAL
    assert out["submitted_label_count"] >= 1
    assert ps_list[0] not in out["missing_by_reviewer_pseudonym"] or pairs[0] not in out[
        "missing_by_reviewer_pseudonym"].get(ps_list[0], [])


def test_42_filesystem_malformed_invalid(tmp_path):
    q = _queue()
    m = _manifest(q)
    ps0 = sorted(m["pseudonymous_reviewers"])[0]
    p = Path(tmp_path) / f"b1__{ps0}__labels.jsonl"
    p.write_text('{"pair_id": "x", "broken": ', encoding="utf-8")   # malformed JSON
    out = _run(queue=q, intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["followup_status"] == FOLLOWUP_INVALID
    assert "malformed_label_file" in out["block_reasons"]
    assert any("malformed" in rc for rcs in out["invalid_by_file_basename"].values() for rc in rcs)


def test_43_filesystem_empty_dir_no_labels(tmp_path):
    out = _run(queue=_queue(), intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["followup_status"] == FOLLOWUP_NO_LABELS
    assert out["actual_label_files"] == []


# ── contract / policy lock ──────────────────────────────────────────────────────────────────────────────
def test_44_operation_name():
    assert _run(queue=_queue())["operation_name"] == OPERATION_NAME == "reviewer_followup_ops"


def test_45_followup_states_locked():
    assert FOLLOWUP_STATES == {
        "not_launchable", "no_labels", "partial_labels", "invalid_labels",
        "conflict_pending", "calibration_pending", "imported_ready_for_merge_gate_review"}


def test_46_agent_contract_cannot_merge_or_send():
    c = REVIEWER_FOLLOWUP_AGENT_CONTRACT
    joined = " ".join(c["cannot"])
    assert "merge 실행" in joined
    assert "actual email/slack/webhook 전송" in joined
    assert "reviewer raw PII 출력" in joined
    assert c["embedding_llm_adjudicator"]["status"].startswith("No-Go")


def test_47_agent_contract_can_plan_followup():
    c = REVIEWER_FOLLOWUP_AGENT_CONTRACT
    joined = " ".join(c["can"])
    assert "reviewer follow-up status 점검" in joined
    assert "calibration gap planning" in joined


def test_48_validation_command_surfaced():
    out = _run(queue=_queue())
    assert "reviewer_batch_launch" in out["validation_command"]
    assert "--validate" in out["validation_command"]


def test_49_intake_status_passthrough():
    q = _queue()
    out_none = _run(queue=q)
    assert out_none["intake_status"] == "awaiting_production_labels"


def test_50_invalid_precedence_over_partial():
    # invalid + missing 동시 → fail-loud(invalid_labels 우선).
    q = _queue()
    m = _manifest(q)
    (ps, pid) = _assignments(m)[0]
    rows = [_row(ps, pid, "same_event", extra={"score": 1})]   # 1개 invalid·나머지 다수 missing
    out = _run(queue=q, label_rows=rows, label_source=LABEL_SOURCE_PRODUCTION)
    assert out["followup_status"] == FOLLOWUP_INVALID


def test_51_coverage_pseudonym_space_unmatched():
    # raw(비-pseudonym) reviewer_id 제출은 expected 와 불일치 → unmatched(coverage 는 pseudonym 공간).
    q = _queue()
    m = _manifest(q)
    pid = sorted({p for _, p in _assignments(m)})[0]
    out = _run(queue=q, label_rows=[_row("raw_not_pseudonym", pid, "same_event")],
               label_source=LABEL_SOURCE_PRODUCTION)
    assert out["unmatched_submission_count"] >= 1
    assert "unmatched_submissions" in out["block_reasons"]
    assert "raw_not_pseudonym" not in json.dumps(out, ensure_ascii=False)   # raw 제출 id echo 0(회귀 락)


def test_52_compute_coverage_unit():
    q = _queue()
    m = _manifest(q)
    cov = compute_coverage(m, [])
    assert cov["expected_label_count"] == m["assignments_count"]
    assert cov["submitted_label_count"] == 0
    assert cov["missing_label_count"] == m["assignments_count"]


def test_53_reminder_builder_clean_and_guard_constant():
    # 정상 템플릿은 forbidden 키 0(구조적 allowlist) + 가드 상수가 핵심 누출 벡터를 포함.
    intake_plan = {"validation_command": "cmd", "expected_label_files": []}
    ok = build_reminder_templates(
        batch_id="b1", packet_id="p", intake_plan=intake_plan,
        missing_by_reviewer={"rv_x": ["pairA"]}, reviewers_submitted=set())
    assert ok and ok[0]["template_type"] == REMINDER_FIRST
    for t in ok:
        assert not (set(t) & _REMINDER_FORBIDDEN_KEYS)
    for k in ("score", "rationale", "predicted_status", "email", "name"):
        assert k in _REMINDER_FORBIDDEN_KEYS


def test_54_escalation_actions_unit():
    actions = build_escalation_actions(
        capacity_status="ok", missing_by_reviewer={"rv_a": ["p1"]}, reviewers_submitted=set(),
        invalid_by_file_basename={}, conflict_pair_count=0, calibration_gaps=[])
    assert any(a["action_type"] == "send_first_reminder" for a in actions)


def test_55_synthetic_partial_keeps_production_gold_zero():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q, label_rows=_partial_rows(m, 1, ds=SOURCE_SYNTHETIC),
               label_source=LABEL_SOURCE_SYNTHETIC)
    assert out["production_gold_count"] == 0
    assert out["followup_status"] == FOLLOWUP_PARTIAL


def test_56_expected_files_match_pseudonyms():
    q = _queue()
    m = _manifest(q)
    out = _run(queue=q)
    for ps in m["pseudonymous_reviewers"]:
        assert f"b1__{ps}__labels.jsonl" in out["expected_label_files"]


def test_57_calibration_delta_passthrough():
    q = _queue()
    out = _run(queue=q)
    assert "next_needed_for_merge_gate" in out["calibration_delta"]
    assert out["calibration_delta"]["merge_gate_ready"] is False


# ── 감사 fix-lock(adversarial MEDIUM basename PII·code-review MEDIUM multi-file 발산·LOW capacity noise) ──
def test_58_cross_file_duplicate_consistent(tmp_path):
    # cross-file duplicate: 같은 (pair,reviewer,round)가 두 파일에 → combined 검증이 잡고 basename 도 채워진다.
    q = _queue()
    m = _manifest(q)
    ps = sorted(m["pseudonymous_reviewers"])
    pid = sorted({p for _, p in _assignments(m)})[0]
    dup = _row(ps[0], pid, "same_event")
    _write_reviewer_file(tmp_path, "b1", ps[0], [dup])
    _write_reviewer_file(tmp_path, "b1", ps[1], [dup])   # 같은 ps[0] 행을 2nd 파일에 = cross-file 중복
    out = _run(queue=q, intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["followup_status"] == FOLLOWUP_INVALID
    assert out["duplicate_label_count"] >= 1                       # combined 단일 출처(per-file 이면 누락)
    assert out["invalid_by_file_basename"]                         # counts 와 정합
    assert any(a["action_type"] == "send_correction_request" for a in out["escalation_actions"])


def test_59_malformed_plus_violation_consistent(tmp_path):
    # malformed 파일 + 다른 파일의 forbidden field → intake 단락에도 followup 은 위반을 표면화(self-consistent).
    q = _queue()
    m = _manifest(q)
    ps = sorted(m["pseudonymous_reviewers"])
    pid = sorted({p for _, p in _assignments(m)})[0]
    (Path(tmp_path) / f"b1__{ps[0]}__labels.jsonl").write_text('{"broken": ', encoding="utf-8")
    _write_reviewer_file(tmp_path, "b1", ps[1], [_row(ps[1], pid, "same_event", extra={"model_score": 1})])
    out = _run(queue=q, intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    assert out["followup_status"] == FOLLOWUP_INVALID
    assert "malformed_label_file" in out["block_reasons"]
    assert out["forbidden_field_count"] >= 1                       # intake 단락과 무관하게 file B 위반 표면화
    flat = [rc for rcs in out["invalid_by_file_basename"].values() for rc in rcs]
    assert any("malformed" in rc for rc in flat) and "forbidden_field" in flat


def test_60_nonconforming_filename_masked(tmp_path):
    # 기대 가명 패턴 밖 파일명(실명)은 마스킹 → 출력 어디에도 실명 미노출.
    q = _queue()
    m = _manifest(q)
    pid = sorted({p for _, p in _assignments(m)})[0]
    ps0 = sorted(m["pseudonymous_reviewers"])[0]
    (Path(tmp_path) / "kim_cheolsu_realname.jsonl").write_text(
        json.dumps(_row(ps0, pid, "same_event")), encoding="utf-8")
    out = _run(queue=q, intake_directory=str(tmp_path), label_source=LABEL_SOURCE_PRODUCTION)
    assert "kim_cheolsu" not in json.dumps(out, ensure_ascii=False)   # 실명 파일명 미노출(PII 가드)
    assert out["nonconforming_filenames_count"] == 1
    assert "nonconforming_file_1" in out["actual_label_files"]


def test_61_not_launchable_no_capacity_escalation():
    # 후보 0(not_launchable)에서는 "reviewer 충원" escalation 미발행(실제 action=packet 재발행).
    out = _run(queue={})
    assert out["followup_status"] == FOLLOWUP_NOT_LAUNCHABLE
    assert not any(a["action_type"] == "assign_more_reviewers" for a in out["escalation_actions"])
    assert "insufficient_reviewer_capacity" not in out["block_reasons"]
