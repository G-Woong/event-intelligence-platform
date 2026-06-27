"""ADR#71 — reviewer pilot execution ledger + first returned-labels monitor (병합 0·LLM 0·embedding 0·DB 0·전송 0).

ADR#70 가 만든 것: `reviewer_pilot_handoff` — operator 가 실 reviewer 에게 바로 배포 가능한 handoff bundle 과
returned label 회수 시 end-to-end gate·8-state `pilot_status`(ready_to_contact/awaiting_reviewer_return 분할)·
ops UI seed contract. 그러나 그것은 **pilot handoff readiness**(배포 가능 상태)이지 **pilot execution 추적**이 아니다 —
operator 가 실제로 reviewer 에게 bundle 을 건넸는지(contact), 어떤 pseudonym 이 어떤 batch 를 받았는지, 첫 returned
label file 이 들어왔는지를 PII-safe ledger 로 관리하는 층이 없다. ADR#70 의 `pilot_executed`/`real_reviewers_contacted`
는 contact evidence 입력 통로가 없어 **하드코딩 False/0** 이다(`reviewer_pilot_handoff.py` 결과 dict). 즉 "번들이
있다"가 "pilot 이 실행됐다"로 둔갑할 자리가 남아 있다(R-ReviewerPilotExecution·R-OpsUIPrematureTruth).

이 모듈은 **재구현이 아니라 pilot execution 추적 wrapper** 다. 무거운 일은 전부 기존 단일 출처가 한다:
  - pilot handoff bundle·returned-label gate·8-state pilot_status·correction/adjudication/calibration handoff·
    gold/calibration **exact passthrough**: `reviewer_pilot_handoff.run_reviewer_pilot_handoff`(단일 호출·decorate).
    그 자신이 `reviewer_followup_ops`→`production_label_intake` 를 1회 태우므로 본 wrapper 도 intake/followup/handoff
    를 **재호출하지 않는다**(단일 출처 체인 — 발산 0).
  - PII 재귀 가드(forbidden-key 벡터): `reviewer_pilot_handoff._assert_pii_safe`/`_HANDOFF_FORBIDDEN_KEYS`(재사용).

이 모듈이 **새로** 더하는 것(기존에 없던 운영 결손):
  - **contact evidence ledger(§A·옵션A)**: operator 가 *이미 수동으로 수행한* 접촉을 기록할 PII-safe schema
    (pseudonym·contact_method_label·contact_status·contacted_at·due_hint·operator_note_code). **allowlist
    fail-loud**(raw name/email/phone/score/rationale/predicted_status 등 비허용 키·email-like pseudonym 거부)·
    재귀 forbidden-key 가드. evidence 가 없으면 contacted 0(둔갑 금지). 실제 email/slack/webhook 전송 0.
  - **execution_status(§B·옵션B·8-state)**: handoff bundle/pilot_status + contact evidence 를 결합해 운영 실행
    상태를 산출. no-labels 일 때 contact evidence 유무로 `awaiting_operator_contact`(미접촉) vs
    `contacted_waiting_return`(접촉·회수 대기)를 분리(pilot_status 의 "회수 경로" 축과 직교하는 **contact 축**).
    returned labels 가 있으면 pilot_status(partial/invalid/conflict/calibration/ready)를 그대로 승계.
  - **operator SLA/checklist(§C·옵션C)**: reviewer pseudonym 별 assigned/contact_status/returned_file_status/
    missing/due_hint/overdue/next_action(전송 0·overdue 는 operator 가 준 `as_of` 기준만·wall-clock 미커플링).
  - **ops UI execution contract(§D·옵션D)**: `InternalOpsPilotExecutionStatus`(execution_status·contact_evidence_
    present·real_reviewers_contacted 등 + `internal_only`/`no_public_truth` 플래그)·docs/schema 중심. public UI 0.

절대 불변(상속·상용 안전 계약):
  - **no merge / no auto-merge**: merge_allowed=False·no_merge_without_gold 불변. execution 추적은 merge 를 만들지 않는다.
  - **production_gold_count 0 정직·exact passthrough**: gold/calibration/merge_gate_ready 는 전부
    `reviewer_pilot_handoff`(→followup→intake) 결과를 **그대로 전달**. execution wrapper 만으로 증가 0.
  - **contacted 둔갑 금지**: `real_reviewers_contacted` 는 contact_status=contacted evidence 수만. evidence 0 → 0.
    `prepared` 는 contacted 아님. operator evidence 없이 contacted 증가 0(R-ContactEvidenceIntegrity 가드).
  - **reviewer raw PII 0**: contact evidence·checklist·ops contract 표면에는 pseudonym·basename·pair_id 만.
    raw name/email/phone·local roster mapping 은 출력·커밋 금지(evidence 파일은 `outputs/reviewer_batch/` gitignore).
  - **labeler 숨김**: score/rationale/predicted_status 는 labeler-facing/contact artifact 에 0(handoff 파생 + 전체 재귀 가드).
  - **실제 전송 0**: contact evidence 는 *기록*일 뿐 — email/slack/webhook/sms 호출 0(operator 수동).
  - **secret 0 / raw body 0 / DB 0 / LLM·embedding 실호출 0 / public IU 0**.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from typing import Any, Optional

from backend.app.tools.near_match_reviewer_queue import (
    EMBEDDING_LLM_ADJUDICATOR_INTERFACE,
    build_near_match_reviewer_queue,
)
from backend.app.tools.reviewer_label_operations import (
    LABEL_SOURCE_PRODUCTION,
    LABEL_SOURCE_SYNTHETIC,
    LABEL_SOURCES,
)
from backend.app.tools.reviewer_pilot_handoff import (
    PILOT_AWAITING_RETURN,
    PILOT_CALIBRATION_PENDING,
    PILOT_CONFLICT_PENDING,
    PILOT_IMPORTED_READY,
    PILOT_INVALID_RETURNED,
    PILOT_NOT_READY,
    PILOT_PARTIAL_RETURNED,
    PILOT_READY_TO_CONTACT,
    _assert_pii_safe,
    run_reviewer_pilot_handoff,
)

OPERATION_NAME = "reviewer_pilot_execution"

# ── §A contact evidence schema(PII-safe·allowlist) ─────────────────────────────────────────────────────
# operator 가 *이미 수동으로 수행한* 접촉을 기록(시스템 전송 아님). 허용 키만(allowlist fail-loud) — raw
# name/email/phone/score/rationale/predicted_status 등은 키 자체가 비허용이라 구조적 거부.
CONTACT_EVIDENCE_ALLOWED_KEYS = frozenset({
    "batch_id", "reviewer_pseudonym", "contact_method_label", "contact_status",
    "contacted_at", "due_hint", "operator_note_code",
})
CONTACT_EVIDENCE_REQUIRED_KEYS = frozenset({"reviewer_pseudonym", "contact_method_label", "contact_status"})
# 실제 전송이 아니라 *어떤 수동 경로로 접촉했는지* 라벨(자유 텍스트·주소 금지).
CONTACT_METHOD_LABELS = frozenset({"manual_email", "manual_slack", "manual_dm", "manual_other"})
# prepared=준비만(접촉 아님)·contacted=접촉함·declined=거절·unavailable=불가. prepared≠contacted(둔갑 금지).
CONTACT_STATUSES = frozenset({"prepared", "contacted", "declined", "unavailable"})
# 동일 pseudonym 다중 evidence 시 가장 진전된 상태 채택(접촉이 준비를 이긴다).
_CONTACT_STATUS_PRECEDENCE = {"prepared": 0, "declined": 1, "unavailable": 2, "contacted": 3}
# reviewer_pseudonym·operator_note_code 는 **ASCII 코드 charset**만(공백=이름·'@'=email·'.'=도메인·한글 자유텍스트 거부).
# raw PII(이름/이메일/전화)가 value-레벨로 새는 것을 키-allowlist 위에 추가 차단(adversarial F2·code-review).
_PSEUDONYM_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
_NOTE_CODE_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")

# ── §B execution status(8-state) ───────────────────────────────────────────────────────────────────────
# not_started: handoff bundle 미완성(pilot_status=not_ready). awaiting_operator_contact: bundle 완성이나 contact
# evidence 0(미접촉). contacted_waiting_return: 접촉 기록 있음·회수 0(회수 대기). 이하 5개는 returned label 상태를
# pilot_status 에서 승계(partial/invalid/conflict/calibration/labels_returned_ready). ready≠merge 허용.
EXEC_NOT_STARTED = "not_started"
EXEC_AWAITING_CONTACT = "awaiting_operator_contact"
EXEC_CONTACTED_WAITING = "contacted_waiting_return"
EXEC_PARTIAL = "partial_returned"
EXEC_INVALID = "invalid_returned"
EXEC_CONFLICT = "conflict_pending"
EXEC_CALIBRATION = "calibration_pending"
EXEC_LABELS_READY = "labels_returned_ready_for_merge_gate_review"
EXECUTION_STATES = frozenset({
    EXEC_NOT_STARTED, EXEC_AWAITING_CONTACT, EXEC_CONTACTED_WAITING, EXEC_PARTIAL,
    EXEC_INVALID, EXEC_CONFLICT, EXEC_CALIBRATION, EXEC_LABELS_READY,
})

# returned label 이 도착한 뒤 pilot_status → execution_status 승계(contact 축은 더 이상 분기 안 함 — 라벨 자체가
# 접촉의 사후 증거). no_labels(ready_to_contact/awaiting_reviewer_return)만 contact evidence 로 분기(_execution_status).
_PILOT_TO_EXEC = {
    PILOT_PARTIAL_RETURNED: EXEC_PARTIAL,
    PILOT_INVALID_RETURNED: EXEC_INVALID,
    PILOT_CONFLICT_PENDING: EXEC_CONFLICT,
    PILOT_CALIBRATION_PENDING: EXEC_CALIBRATION,
    PILOT_IMPORTED_READY: EXEC_LABELS_READY,
}

# execution_status → operator 한 줄 next_action(ops UI 가 읽는 단일 요약·전송 지시 아님).
_EXEC_NEXT_ACTION = {
    EXEC_NOT_STARTED: "handoff 대상 0(cross-source 후보/assignment 없음) — targeted same-event acquisition 후 packet 재발행",
    EXEC_AWAITING_CONTACT: "operator 가 reviewer 에게 handoff bundle 배포(수동) 후 contact evidence(contact_status=contacted) 기록 — 실 전송/연락은 operator 수동(시스템 전송 0)",
    EXEC_CONTACTED_WAITING: "접촉 기록됨·회수 대기 — intake_directory 에 reviewer label JSONL 회수 후 returned-label gate 재실행(미회수·overdue 시 reminder 수동)",
    EXEC_PARTIAL: "부분 회수 — missing reviewer 에게 missing-label reminder(수동) 후 재회수",
    EXEC_INVALID: "invalid 회수 — reason code 로 correction request(값 미노출) 후 재배치·재검증",
    EXEC_CONFLICT: "reviewer 불일치 — human lead adjudication 배정(자동 다수결 금지) 후 gold 재평가",
    EXEC_CALIBRATION: "gold/Korean/hard-negative denominator 충원 — 실 reviewer label 회수 지속(merge 금지)",
    EXEC_LABELS_READY: "MERGE_GATE review 준비(병합 자동 실행 아님 — adversarial 승인 필요)",
}

# execution_status → block_reason(merge 가 막힌 이유·actionable).
_EXEC_BLOCK_REASON = {
    EXEC_NOT_STARTED: "pilot_not_started",
    EXEC_AWAITING_CONTACT: "awaiting_operator_contact",
    EXEC_CONTACTED_WAITING: "contacted_waiting_return",
    EXEC_PARTIAL: "partial_returned",
    EXEC_INVALID: "invalid_returned",
    EXEC_CONFLICT: "conflict_pending",
    EXEC_CALIBRATION: "calibration_floor_not_met",
    EXEC_LABELS_READY: "awaiting_merge_gate_review",
}

# §10 Agent / Intelligence Unit contract — Agent 는 pilot execution status/returned-label gate 를 **계획**할 수
# 있으나 label·contact evidence 조작·merge·전송·PII 출력 불가.
REVIEWER_PILOT_EXECUTION_AGENT_CONTRACT = {
    "can": [
        "pilot execution status 점검", "contact evidence status 점검", "returned labels status 점검",
        "missing label follow-up 계획", "invalid label correction request 작성",
        "conflict adjudication handoff 계획", "calibration gap planning", "korean label collection plan",
        "internal ops UI execution status 요약", "next reviewer/operator action 도출",
    ],
    "cannot": [
        "reviewer label 조작", "contact evidence 임의 생성", "label file 임의 생성해 production label 로 사용",
        "score 를 truth 로 사용", "same-event 확정", "merge 실행", "public Intelligence Unit 생성",
        "community reaction 을 event anchor 로 사용", "market/catalog 를 event anchor 로 사용",
        "secret 읽기/출력", "reviewer raw PII 출력", "actual email/slack/webhook 전송",
    ],
    "embedding_llm_adjudicator": EMBEDDING_LLM_ADJUDICATOR_INTERFACE,   # No-Go for merge(이번 턴 호출 0).
}


# ── §A: contact evidence 검증(PII-safe·allowlist·전송 0) ────────────────────────────────────────────────
def validate_contact_evidence(
    contact_evidence: Optional[list[dict]], *, batch_id: str,
) -> list[dict]:
    """operator contact evidence 를 PII-safe 하게 검증·정규화. **allowlist + 값-레벨 fail-loud** + 재귀
    forbidden-key 가드. None → [](evidence 없음=접촉 0). 실제 전송이 아니라 *operator 가 수동으로 수행한 접촉의 기록*.

    방어(키 + 값 둘 다 — adversarial F2/F3·code-review): raw name/email/phone/score/rationale/predicted_status 는
    키 자체가 비허용(allowlist). **값-레벨**: reviewer_pseudonym=ASCII 코드 charset(공백/이름·@/email·전화 거부)·
    due_hint/contacted_at=ISO date-like 강제(자유 텍스트/PII 차단)·operator_note_code=ASCII 코드·enum 은 isinstance
    후 멤버십(unhashable 입력에 TypeError 대신 ValueError)·**batch_id 교차검증**(cross-batch evidence 오염 거부)."""
    if contact_evidence is None:
        return []
    if not isinstance(contact_evidence, list):
        raise ValueError("contact_evidence must be a list of evidence dicts (or None).")
    validated: list[dict] = []
    for i, rec in enumerate(contact_evidence):
        if not isinstance(rec, dict):
            raise ValueError(f"contact_evidence[{i}] must be a dict.")
        keys = set(rec)
        unknown = keys - CONTACT_EVIDENCE_ALLOWED_KEYS
        if unknown:   # raw PII/score/secret 등 비허용 키 — fail-loud(allowlist).
            raise ValueError(
                f"contact_evidence[{i}] has non-allowlisted keys (PII/secret 차단): {sorted(unknown)}; "
                f"allowed: {sorted(CONTACT_EVIDENCE_ALLOWED_KEYS)}")
        missing = CONTACT_EVIDENCE_REQUIRED_KEYS - keys
        if missing:
            raise ValueError(f"contact_evidence[{i}] missing required keys: {sorted(missing)}")
        # batch_id 교차검증(cross-batch evidence 오염 차단·CR#3) — 있으면 이 run 의 batch_id 와 일치해야.
        rec_batch = rec.get("batch_id")
        if rec_batch is not None and rec_batch != batch_id:
            raise ValueError(
                f"contact_evidence[{i}] batch_id {rec_batch!r} != run batch_id {batch_id!r} (cross-batch 오염).")
        ps = rec["reviewer_pseudonym"]
        if not isinstance(ps, str) or not _PSEUDONYM_RE.fullmatch(ps):
            raise ValueError(
                f"contact_evidence[{i}] reviewer_pseudonym must be a pseudonymous code [A-Za-z0-9_-] "
                f"(no spaces/@/. — raw name/email/PII 거부).")
        if ps.replace("-", "").isdigit():   # 전부 숫자/대시 → 전화번호 형태 raw PII 거부.
            raise ValueError(f"contact_evidence[{i}] reviewer_pseudonym looks like a raw phone number — pseudonym only.")
        method = rec["contact_method_label"]
        if not isinstance(method, str) or method not in CONTACT_METHOD_LABELS:
            raise ValueError(
                f"contact_evidence[{i}] invalid contact_method_label {method!r} "
                f"(allowed: {sorted(CONTACT_METHOD_LABELS)}).")
        status = rec["contact_status"]
        if not isinstance(status, str) or status not in CONTACT_STATUSES:
            raise ValueError(
                f"contact_evidence[{i}] invalid contact_status {status!r} (allowed: {sorted(CONTACT_STATUSES)}).")
        # due_hint/contacted_at 는 **값-레벨** ISO date-like 강제(자유 텍스트/PII 가 출력으로 새는 것 차단·F2).
        for date_field in ("due_hint", "contacted_at"):
            val = rec.get(date_field)
            if val is not None and _parse_iso_date(val) is None:
                raise ValueError(
                    f"contact_evidence[{i}] {date_field} must be ISO date/datetime (no free text/PII): {val!r}")
        note = rec.get("operator_note_code")
        if note is not None and (not isinstance(note, str) or not _NOTE_CODE_RE.fullmatch(note)):
            # note 는 *ASCII 코드*(예: reassigned·ooo)여야 하며 자유 텍스트/비-ASCII(한글 등) 금지(raw PII 유입 차단).
            raise ValueError(
                f"contact_evidence[{i}] operator_note_code must be a short ASCII code [A-Za-z0-9_-] (no free text/PII).")
        validated.append({k: rec[k] for k in sorted(keys)})
    # 재귀 forbidden-key 가드(방어 심화) — allowlist 가 이미 차단하나 드리프트는 lock 테스트가 잡음.
    _assert_pii_safe(validated, _path="contact_evidence")
    return validated


def _tally_contacts(evidence: list[dict], *, roster: set) -> dict:
    """contact evidence → pseudonym 별 effective status(precedence)·집계. real_reviewers_contacted 는
    **roster(배정 reviewer) ∩ contact_status=contacted** 만(둔갑·부풀리기 금지·F3). declined/unavailable 은 별도
    분리(§5). 동일 pseudonym 다중 evidence 는 가장 진전된 상태의 record 채택(due_hint/contacted_at 도 그 record).
    roster 밖 evidence(유령 pseudonym)는 공식 카운트에서 제외하고 `evidence_for_unknown_pseudonym_count` 로 표면화.

    **any_active_contact 는 contacted>0 만**(declined/unavailable-only=미접촉이므로 contacted_waiting_return 둔갑
    금지·adversarial F1) — declined/unavailable-only 는 awaiting_operator_contact(대체 reviewer 재배포)로 정직 산출."""
    record_by_pseudonym: dict[str, dict] = {}
    for rec in evidence:
        ps, status = rec["reviewer_pseudonym"], rec["contact_status"]
        cur = record_by_pseudonym.get(ps)
        if cur is None or _CONTACT_STATUS_PRECEDENCE[status] > _CONTACT_STATUS_PRECEDENCE[cur["contact_status"]]:
            record_by_pseudonym[ps] = rec
    by_pseudonym = {ps: r["contact_status"] for ps, r in record_by_pseudonym.items()}
    # 공식 카운트는 roster ∩ evidence 만(배정 안 된 유령 pseudonym 은 contacted 로 카운트 0).
    on_roster = {ps: s for ps, s in by_pseudonym.items() if ps in roster}
    contacted = sorted(ps for ps, s in on_roster.items() if s == "contacted")
    declined = sorted(ps for ps, s in on_roster.items() if s == "declined")
    unavailable = sorted(ps for ps, s in on_roster.items() if s == "unavailable")
    prepared = sorted(ps for ps, s in on_roster.items() if s == "prepared")
    unknown = sorted(ps for ps in by_pseudonym if ps not in roster)
    return {
        "by_pseudonym": by_pseudonym,
        "record_by_pseudonym": record_by_pseudonym,
        "contacted_pseudonyms": contacted,
        "real_reviewers_contacted": len(contacted),
        "reviewers_declined": len(declined),
        "reviewers_unavailable": len(unavailable),
        "reviewers_prepared": len(prepared),
        "evidence_for_unknown_pseudonym_count": len(unknown),
        # contacted(roster 내)가 하나라도 있을 때만 awaiting 에서 벗어난다(declined/unavailable-only 는 미접촉).
        "any_active_contact": bool(contacted),
    }


# ── §B: execution status(pilot_status + contact evidence) ──────────────────────────────────────────────
def _execution_status(pilot_status: str, *, any_active_contact: bool) -> str:
    """pilot_status(8-state) + contact evidence → execution_status(8-state). bundle 없으면 not_started. no_labels
    (ready_to_contact/awaiting_reviewer_return)는 contact evidence 로 awaiting_operator_contact(미접촉) vs
    contacted_waiting_return(접촉·회수 대기) 분기. returned label 상태는 pilot_status 를 그대로 승계."""
    if pilot_status == PILOT_NOT_READY:
        return EXEC_NOT_STARTED
    if pilot_status in (PILOT_READY_TO_CONTACT, PILOT_AWAITING_RETURN):
        return EXEC_CONTACTED_WAITING if any_active_contact else EXEC_AWAITING_CONTACT
    return _PILOT_TO_EXEC.get(pilot_status, EXEC_NOT_STARTED)


# ── §C: operator SLA/checklist(전송 0·overdue 는 as_of 기준만) ──────────────────────────────────────────
def _parse_iso_date(value: Any) -> Optional[date]:
    """ISO date(또는 datetime 앞 10자) → date. 파싱 실패/None → None(overdue 미산정·정직 unknown)."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _reviewer_next_action(contact_status: str, returned_file_status: str, *, overdue: bool) -> str:
    """reviewer pseudonym 별 다음 수동 action(§7 vocab). 전송 지시 아님 — operator 수동."""
    if returned_file_status == "returned":
        return "wait_for_return"        # 이 reviewer 회수 완료 — batch/downstream 대기.
    if returned_file_status == "partial":
        return "send_manual_reminder"
    if contact_status in ("not_contacted", "prepared"):
        return "send_manual_handoff"    # 아직 실 접촉 전 — bundle 배포부터.
    if contact_status in ("declined", "unavailable"):
        return "send_manual_handoff"    # reviewer 이탈(거절/불가) — 대체 reviewer 에게 재배포(handoff).
    if overdue:
        return "send_manual_reminder"   # 접촉했으나 due 초과 — 재촉.
    return "wait_for_return"            # 접촉·회수 대기.


def build_operator_checklist(
    *, assignment_summary: dict, missing_by_pseudonym: dict[str, int],
    contact_record_by_pseudonym: dict[str, dict], due_hint: Optional[str], as_of: Optional[str],
) -> tuple[list[dict], int]:
    """reviewer pseudonym 별 operator checklist(§7) + overdue_count. raw PII 0(pseudonym·pair count 만).

    returned_file_status: missing==0→returned·missing>=assigned→missing·그 외→partial. per-reviewer due 는 그
    reviewer 의 contact evidence due_hint(접촉 시점 부여)·없으면 top-level due_hint fallback. overdue 는 operator 가
    준 `as_of`(ISO)와 due 가 모두 파싱되고 회수 미완일 때만 True(wall-clock 미커플링·미제공 시 False)."""
    as_of_d = _parse_iso_date(as_of)
    checklist: list[dict] = []
    overdue_count = 0
    for ps in sorted(assignment_summary):
        assigned = assignment_summary[ps].get("pair_count", 0)
        missing = missing_by_pseudonym.get(ps, 0)
        if missing <= 0:
            returned_file_status = "returned"
        elif missing >= assigned:
            returned_file_status = "missing"
        else:
            returned_file_status = "partial"
        rec = contact_record_by_pseudonym.get(ps)
        contact_status = rec["contact_status"] if rec else "not_contacted"
        reviewer_due = (rec.get("due_hint") if rec else None) or due_hint
        due_d = _parse_iso_date(reviewer_due)
        overdue = bool(
            as_of_d is not None and due_d is not None
            and returned_file_status != "returned" and as_of_d > due_d)
        if overdue:
            overdue_count += 1
        checklist.append({
            "reviewer_pseudonym": ps,
            "assigned_pair_count": assigned,
            "contact_status": contact_status,
            "returned_file_status": returned_file_status,
            "missing_label_count": missing,
            "due_hint": reviewer_due,
            "overdue": overdue,
            "next_action": _reviewer_next_action(contact_status, returned_file_status, overdue=overdue),
        })
    return checklist, overdue_count


# ── §D: ops UI execution contract(internal ops dashboard 가 읽는 status — public truth 아님) ─────────────
def build_ops_ui_execution_contract(
    *, batch_id: str, pilot_status: str, execution_status: str, contact_evidence_present: bool,
    real_reviewers_contacted: int, returned_label_count: int, missing_label_count: int,
    invalid_label_count: int, invalid_file_count: int, conflict_pair_count: int,
    production_gold_count: int, synthetic_gold_count: int, production_gold_provenance_verified: bool,
    calibration_ready: bool, merge_gate_ready: bool, overdue_count: int, next_action: str,
) -> dict:
    """§9 InternalOpsPilotExecutionStatus — 미래 internal ops dashboard 가 읽을 **execution** workflow state.
    **public IU 아님**. flags 가 명시: internal_only/no_public_truth/no_merge/no_public_iu/pii_safe/no_llm/
    no_db_write/gold_provenance_verified. execution_status·contact_evidence_present·real_reviewers_contacted 를
    노출하되 same_event truth·verified gold 를 렌더하지 못하게 한다(R-OpsUIPrematureTruth 가드). provenance
    caveat(`production_gold_provenance_verified`·현재 False) 동반 — 미검증 gold 가 truth 로 박제되는 것 차단."""
    return {
        "contract": "InternalOpsPilotExecutionStatus",
        "batch_id": batch_id,
        "pilot_status": pilot_status,
        "execution_status": execution_status,
        "contact_evidence_present": contact_evidence_present,
        "real_reviewers_contacted": real_reviewers_contacted,
        "returned_label_count": returned_label_count,
        "missing_label_count": missing_label_count,
        "invalid_label_count": invalid_label_count,
        "invalid_file_count": invalid_file_count,
        "conflict_pair_count": conflict_pair_count,
        "overdue_count": overdue_count,
        "production_gold_count": production_gold_count,
        "synthetic_gold_count": synthetic_gold_count,
        # production gold 무결성은 **선언 기반**(provenance 미검증·R-IdentityHumanLabeling) — readiness 근거 인용 금지.
        "production_gold_provenance_verified": production_gold_provenance_verified,
        "calibration_ready": calibration_ready,
        "merge_gate_ready": merge_gate_ready,
        "next_action": next_action,
        "flags": {
            "internal_only": True,        # internal ops dashboard 전용(public surface 0).
            "no_public_truth": True,      # workflow state ≠ verified public truth.
            "no_merge": True,
            "no_public_iu": True,
            "pii_safe": True,
            "no_llm": True,
            "no_db_write": True,
            "gold_provenance_verified": production_gold_provenance_verified,
        },
    }


# ── §4: 통합 reviewer pilot execution entrypoint ───────────────────────────────────────────────────────
def run_reviewer_pilot_execution(
    *, queue: Optional[dict] = None, discovery: Optional[dict] = None,
    batch_id: str = "reviewer_pilot_exec_001", packet_id: str = "reviewer_pilot_exec_pkt",
    intake_directory: Optional[Any] = None, label_rows: Optional[list[dict]] = None,
    label_source: str = LABEL_SOURCE_PRODUCTION, adjudications: Optional[dict] = None,
    reviewers: Optional[list[str]] = None, top_k_sourced: bool = True,
    include_synthetic_hard_negatives: bool = False, due_hint: Optional[str] = None,
    calibration_baseline: Optional[dict] = None,
    contact_evidence: Optional[list[dict]] = None, as_of: Optional[str] = None,
) -> dict:
    """reviewer pilot execution ledger + returned-labels monitor(병합 0·LLM 0·embedding 0·DB 0·전송 0).

    `run_reviewer_pilot_handoff` 를 단일 출처로 1회 호출해 handoff bundle·pilot_status·returned-label gate·gold/
    calibration 을 받고(그대로 passthrough — execution wrapper 만으로 production_gold_count 증가 0), 그 위에 PII-safe
    contact evidence ledger·8-state execution_status·operator SLA/checklist·ops UI execution contract 를 더한다.
    contact evidence 없음·returned labels 없음 = 실패 아님(awaiting_operator_contact/contacted_waiting_return).
    어떤 경로도 merge/LLM/embedding/DB/전송을 건드리지 않는다."""
    if label_source not in LABEL_SOURCES:
        raise ValueError(f"invalid label_source {label_source!r} (allowed: {sorted(LABEL_SOURCES)})")
    evidence = validate_contact_evidence(contact_evidence, batch_id=batch_id)

    # queue 를 한 번만 build 해 handoff 와 동일 입력을 보게 한다(발산 0).
    if queue is None and discovery is not None:
        queue = build_near_match_reviewer_queue(
            discovery, packet_id=packet_id, reviewers=reviewers,
            include_synthetic_hard_negatives=include_synthetic_hard_negatives)
    queue = queue or {}

    # 1) handoff(단일 출처) — bundle·pilot_status·returned-label gate·gold/calibration passthrough.
    handoff = run_reviewer_pilot_handoff(
        queue=queue, batch_id=batch_id, packet_id=packet_id,
        intake_directory=intake_directory, label_rows=label_rows, label_source=label_source,
        adjudications=adjudications, top_k_sourced=top_k_sourced, due_hint=due_hint,
        calibration_baseline=calibration_baseline)

    # 2) contact evidence 집계(둔갑 금지·roster ∩ contacted 만 카운트·F1/F3). roster=배정 reviewer pseudonym.
    assignment_summary = handoff["handoff_bundle"]["assignment_summary_by_reviewer"]
    tally = _tally_contacts(evidence, roster=set(assignment_summary))
    pilot_status = handoff["pilot_status"]
    execution_status = _execution_status(pilot_status, any_active_contact=tally["any_active_contact"])
    pilot_executed = tally["real_reviewers_contacted"] > 0

    # 3) operator SLA/checklist(reviewer 별 — assignment summary + reminder(missing) passthrough).
    missing_by_pseudonym = {
        t["reviewer_pseudonym"]: t["missing_pair_count"] for t in handoff["reminder_templates"]}
    checklist, overdue_count = build_operator_checklist(
        assignment_summary=assignment_summary, missing_by_pseudonym=missing_by_pseudonym,
        contact_record_by_pseudonym=tally["record_by_pseudonym"], due_hint=due_hint, as_of=as_of)

    reviewers_total = len(assignment_summary)
    reviewers_awaiting_contact = sum(
        1 for ps in assignment_summary
        if tally["by_pseudonym"].get(ps, "not_contacted") in ("not_contacted", "prepared"))
    sla_status = {
        "reviewers_total": reviewers_total,
        "reviewers_contacted": tally["real_reviewers_contacted"],
        "reviewers_declined": tally["reviewers_declined"],
        "reviewers_unavailable": tally["reviewers_unavailable"],
        "reviewers_prepared": tally["reviewers_prepared"],
        "reviewers_awaiting_contact": reviewers_awaiting_contact,
        "evidence_for_unknown_pseudonym_count": tally["evidence_for_unknown_pseudonym_count"],
        "expected_label_count": handoff["expected_label_count"],
        "returned_label_count": handoff["returned_label_count"],
        "missing_label_count": handoff["missing_label_count"],
        "overdue_count": overdue_count,
        "as_of": as_of,
        "due_hint_optional": due_hint,
        "pair_coverage_target": 1.0,
        "raw_roster_committed": False,
        "actual_sending_performed": False,
    }

    # 4) ops UI execution contract(internal dashboard·public truth 아님). invalid_file_count 는 handoff ops UI
    # contract 가 이미 산출(malformed 파일 단위·행 단위 invalid_label_count 와 self-contradiction 차단·passthrough).
    invalid_file_count = handoff["ops_ui_contract"]["invalid_file_count"]
    exec_next_action = _EXEC_NEXT_ACTION.get(execution_status, "")
    ops_ui_contract = build_ops_ui_execution_contract(
        batch_id=batch_id, pilot_status=pilot_status, execution_status=execution_status,
        contact_evidence_present=bool(evidence), real_reviewers_contacted=tally["real_reviewers_contacted"],
        returned_label_count=handoff["returned_label_count"], missing_label_count=handoff["missing_label_count"],
        invalid_label_count=handoff["invalid_label_count"], invalid_file_count=invalid_file_count,
        conflict_pair_count=handoff["conflict_pair_count"],
        production_gold_count=handoff["production_gold_count"], synthetic_gold_count=handoff["synthetic_gold_count"],
        production_gold_provenance_verified=handoff["production_gold_provenance_verified"],
        calibration_ready=handoff["calibration_ready"], merge_gate_ready=handoff["merge_gate_ready"],
        overdue_count=overdue_count, next_action=exec_next_action)

    # 5) block_reasons / next_actions(execution-level + handoff passthrough·dedup).
    block_reasons = list(dict.fromkeys([_EXEC_BLOCK_REASON.get(execution_status, execution_status)]
                                       + list(handoff["block_reasons"])))
    next_actions = ([exec_next_action] if exec_next_action else []) + list(handoff["operator_next_actions"])

    result = {
        "operation_name": OPERATION_NAME,
        "batch_id": batch_id,
        "packet_id": packet_id,
        "pilot_status": pilot_status,
        "execution_status": execution_status,
        # **번들/회수경로 ≠ pilot 실행**: pilot_executed/real_reviewers_contacted 는 contact evidence(contacted)
        # 가 있을 때만 증가(operator evidence 없이 둔갑 0·R-ContactEvidenceIntegrity).
        "pilot_executed": pilot_executed,
        "contact_evidence_present": bool(evidence),
        "real_reviewers_contacted": tally["real_reviewers_contacted"],
        "reviewer_contacted_by_pseudonym": tally["contacted_pseudonyms"],
        "reviewers_declined": tally["reviewers_declined"],
        "reviewers_unavailable": tally["reviewers_unavailable"],
        "reviewers_prepared": tally["reviewers_prepared"],
        # roster(배정) 밖 pseudonym evidence — 공식 contacted 카운트 제외·정합성 신호(F3).
        "evidence_for_unknown_pseudonym_count": tally["evidence_for_unknown_pseudonym_count"],
        # §B returned-label monitor(handoff passthrough).
        "returned_label_files": handoff["returned_label_files"],
        "real_labels_returned": handoff["returned_label_count"],
        "expected_label_count": handoff["expected_label_count"],
        "returned_label_count": handoff["returned_label_count"],
        "missing_label_count": handoff["missing_label_count"],
        "invalid_label_count": handoff["invalid_label_count"],
        "conflict_pair_count": handoff["conflict_pair_count"],
        "calibration_gap": handoff["calibration_gap"],
        # §C operator SLA/checklist.
        "operator_action_checklist": checklist,
        "sla_status": sla_status,
        "overdue_count": overdue_count,
        # handoff bundle·template/handoff(전송 0). reminder/correction/adjudication 은 handoff passthrough.
        "handoff_bundle_ready": handoff["handoff_bundle_ready"],
        "handoff_bundle": handoff["handoff_bundle"],
        "reminder_templates": handoff["reminder_templates"],
        "correction_templates": handoff["correction_templates"],
        "adjudication_handoff": handoff["adjudication_handoff"],
        # §D ops UI execution contract(internal dashboard·public truth 아님).
        "ops_ui_contract": ops_ui_contract,
        # 실제 접촉/전송 정직.
        "actual_sending_performed": False,        # email/slack/webhook/sms 호출 0(evidence 는 기록일 뿐).
        # PII/labeler 숨김(구조적 파생·재귀 가드).
        "raw_pii_exposed": False,
        "reviewer_ids_pseudonymous": True,
        "score_hidden_from_labeler": handoff["score_hidden_from_labeler"],
        "rationale_hidden_from_labeler": handoff["rationale_hidden_from_labeler"],
        "predicted_status_hidden": handoff["predicted_status_hidden"],
        # gold/calibration 은 handoff→followup→intake exact passthrough — execution wrapper 만으로 증가 0.
        "production_gold_count": handoff["production_gold_count"],
        "synthetic_gold_count": handoff["synthetic_gold_count"],
        "production_gold_provenance_verified": handoff["production_gold_provenance_verified"],
        "calibration_ready": handoff["calibration_ready"],
        "merge_gate_ready": handoff["merge_gate_ready"],
        "calibration_delta": handoff["calibration_delta"],
        "merge_allowed": False,
        "no_merge_without_gold": True,
        "no_public_intelligence_unit": True,
        "db_write": False,
        "llm_invoked": False,
        "embedding_invoked": False,
        "agent_contract": REVIEWER_PILOT_EXECUTION_AGENT_CONTRACT,
        "block_reasons": block_reasons,
        "next_actions": next_actions,
    }
    # 전체 출력 재귀 forbidden-key 가드(adversarial): contact evidence·checklist·ops contract·handoff bundle 등
    # 어떤 depth 의 dict 도 score/rationale/predicted_status/raw PII 키를 노출하지 않음을 보장(미래 드리프트 fail-loud).
    _assert_pii_safe(result, _path="pilot_execution_output")
    return result


# ── CLI(기본 captured fixture·network 0·DB 0·전송 0; synthetic contact/labels 데모 opt-in) ──────────────
def _demo_contact_evidence(manifest: dict, *, batch_id: str, status: str = "contacted") -> list[dict]:
    """경로 검증용 synthetic contact evidence(manifest pseudonym·manual_other·기록일 뿐·전송 0)."""
    pseudonyms = sorted(manifest.get("pseudonymous_reviewers") or [])
    return [{
        "batch_id": batch_id, "reviewer_pseudonym": ps, "contact_method_label": "manual_other",
        "contact_status": status, "contacted_at": "2026-06-27T00:00:00+00:00", "due_hint": "2026-06-30",
        "operator_note_code": "demo_contact",
    } for ps in pseudonyms]


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="reviewer pilot execution ledger + returned-labels monitor (ADR#71·병합 0·LLM 0·DB 0·전송 0).")
    parser.add_argument("--intake-dir", metavar="DIR",
                        help="returned label intake directory(reviewer 별 *.jsonl 스캔). 미지정 시 batch 기본 경로.")
    parser.add_argument("--batch-id", default="reviewer_pilot_exec_cli", help="batch id.")
    parser.add_argument("--synthetic-contact", action="store_true",
                        help="synthetic contact evidence 데모(manifest pseudonym contacted·기록일 뿐·전송 0).")
    parser.add_argument("--synthetic-labels", action="store_true",
                        help="synthetic partial 회수 데모(첫 pair 만 회수·production gold 0·synthetic_fixture).")
    parser.add_argument("--synthetic-hard-negatives", action="store_true",
                        help="trap-zone synthetic hard negative 포함(calibration 연습).")
    parser.add_argument("--as-of", metavar="ISO_DATE", help="overdue 산정 기준일(ISO·예: 2026-07-01). 미지정 시 overdue 0.")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    from backend.app.tools.reviewer_batch_launch import build_assignment_manifest
    from backend.app.tools.reviewer_followup_ops import _demo_followup_label_rows
    from backend.app.tools.source_overlap_discovery import (
        build_captured_overlap_fixture,
        discover_overlap,
    )
    disc = discover_overlap(build_captured_overlap_fixture())
    queue = build_near_match_reviewer_queue(
        disc, packet_id="reviewer_pilot_exec_cli",
        include_synthetic_hard_negatives=ns.synthetic_hard_negatives)
    manifest = build_assignment_manifest(queue, batch_id=ns.batch_id)

    labels = _demo_followup_label_rows(manifest) if ns.synthetic_labels else None
    evidence = _demo_contact_evidence(manifest, batch_id=ns.batch_id) if ns.synthetic_contact else None
    out = run_reviewer_pilot_execution(
        queue=queue, batch_id=ns.batch_id, packet_id="reviewer_pilot_exec_cli",
        intake_directory=ns.intake_dir, label_rows=labels,
        label_source=LABEL_SOURCE_SYNTHETIC if ns.synthetic_labels else LABEL_SOURCE_PRODUCTION,
        contact_evidence=evidence, as_of=ns.as_of, top_k_sourced=False)

    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} batch_id={out['batch_id']} "
          f"execution_status={out['execution_status']} pilot_status={out['pilot_status']}")
    print(f"- contact: present={out['contact_evidence_present']} contacted={out['real_reviewers_contacted']} "
          f"declined={out['reviewers_declined']} unavailable={out['reviewers_unavailable']} "
          f"prepared={out['reviewers_prepared']} pilot_executed={out['pilot_executed']}")
    print(f"- returns: returned={out['returned_label_count']}/{out['expected_label_count']} "
          f"missing={out['missing_label_count']} invalid={out['invalid_label_count']} "
          f"conflict={out['conflict_pair_count']}")
    print(f"- sla: reviewers={out['sla_status']['reviewers_total']} "
          f"awaiting_contact={out['sla_status']['reviewers_awaiting_contact']} overdue={out['overdue_count']}")
    print(f"- gold: production={out['production_gold_count']} synthetic={out['synthetic_gold_count']} "
          f"calibration_ready={out['calibration_ready']} merge_gate_ready={out['merge_gate_ready']}")
    print(f"- gates: merge_allowed={out['merge_allowed']} actual_sending={out['actual_sending_performed']} "
          f"db_write={out['db_write']} llm_invoked={out['llm_invoked']} embedding_invoked={out['embedding_invoked']} "
          f"raw_pii_exposed={out['raw_pii_exposed']}")
    print(f"- ops_ui: contract={out['ops_ui_contract']['contract']} "
          f"internal_only={out['ops_ui_contract']['flags']['internal_only']} "
          f"no_public_truth={out['ops_ui_contract']['flags']['no_public_truth']}")
    if out["next_actions"]:
        print(f"- next: {out['next_actions'][0]}")
    print(f"- block_reasons: {out['block_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
