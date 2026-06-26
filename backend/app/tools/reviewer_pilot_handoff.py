"""ADR#70 — actual reviewer pilot handoff bundle + returned-label gate (병합 0·LLM 0·embedding 0·DB 0·전송 0).

ADR#69 가 만든 것: `reviewer_followup_ops` — assignment(expected) vs 회수(actual) coverage·7-state
`followup_status`·reminder/escalation·SLA cockpit. 그러나 그것은 **운영 상태 cockpit**이지 **실 reviewer pilot
을 시작 가능한 handoff package**가 아니다 — 운영자가 실제 reviewer 에게 **무엇을 건네야** 첫 라벨 회수가
시작되는지(instruction·reviewer 별 assignment summary·label template schema·expected filename·validation
command 를 하나로 묶은 bundle)와, "아직 접촉 전(ready_to_contact)"인지 "회수 대기(awaiting_reviewer_return)"인지가
분리돼 있지 않다. 그리고 returned label 이 들어오면 intake→followup→agreement/gold/calibration delta 를
**end-to-end** 로 닫는 단일 entrypoint 와, 미래 internal ops UI 가 읽을 status contract 가 없다.

이 모듈은 **재구현이 아니라 pilot handoff orchestrator** 다. 무거운 일은 전부 기존 단일 출처가 한다:
  - follow-up status/coverage/counts/reminder/escalation/SLA·intake passthrough(gold/calibration/conflict):
    `reviewer_followup_ops.run_reviewer_followup_ops`(단일 호출·decorate).
  - reviewer instruction(score/rationale/predicted_status 구조적 0): `reviewer_batch_launch.build_reviewer_instruction`.
  - label template(pseudonym·allowlist fail-loud): `reviewer_batch_launch.build_label_template`.
  - assignment manifest(pseudonym·capacity)·intake plan(dir/files/command): `reviewer_batch_launch`.

이 모듈이 **새로** 더하는 것(기존에 없던 운영 결손):
  - **actual reviewer pilot handoff bundle(§A·옵션A)**: instruction + reviewer 별 assignment summary +
    label template schema + expected filename + intake dir + validation command + allowed labels + due_hint 를
    **PII-safe(pseudonym only)** 하나의 bundle 로. 실제 email/slack/webhook 전송 0(operator 수동).
  - **returned-label gate(§B·옵션B)**: returned label 이 있으면 followup→intake 를 그대로 태워 end-to-end
    상태를 산출하고, 없으면 ready_to_contact/awaiting_reviewer_return 를 **정직**하게 산출.
  - **8-state pilot_status(§C·옵션C)**: followup 7-state 를 pilot 운영 상태로 매핑하되 no_labels 를
    ready_to_contact(intake dir 미설정=접촉 전) vs awaiting_reviewer_return(설정·빈=회수 대기)로 분할.
  - **correction/adjudication/calibration handoff template(§7)**: invalid→reason code correction, conflict→
    human-lead adjudication(자동 다수결 금지), calibration→gold/KO/negative gap. 전송 0.
  - **ops UI seed contract(§D·옵션D)**: 미래 internal ops dashboard 가 읽을 OpsReviewBatchStatus(workflow state
    이지 public truth 아님·no_merge/no_public_iu/pii_safe/no_llm/no_db_write 플래그).

절대 불변(상속·상용 안전 계약):
  - **no merge / no auto-merge**: merge_allowed=False·no_merge_without_gold 불변. handoff 는 merge 를 만들지 않는다.
  - **production_gold_count 0 정직·exact passthrough**: gold/calibration/merge_gate_ready 는 전부
    `reviewer_followup_ops`(→`production_label_intake`) 결과를 **그대로 전달**. handoff 만으로 증가 0.
  - **single reviewer ≠ gold**·**conflict ≠ 자동 다수결 gold**·**model/self/LLM label ≠ gold**(intake 가 강제).
  - **reviewer raw PII 0**: bundle·template·correction 표면에는 pseudonym·basename·pair_id 만. raw name/email/
    phone·local roster mapping 은 출력·커밋 금지(intake_directory 는 `outputs/reviewer_batch/` gitignore).
  - **labeler 숨김**: score/rationale/predicted_status 는 labeler-facing bundle 에 0(instruction 구조 플래그에서
    파생·하드코딩 아님) + bundle 전체 forbidden-key 재귀 가드.
  - **실제 전송 0**: bundle/reminder/correction/adjudication 은 **명세**일 뿐 — email/slack/webhook/sms 호출 0.
  - **secret 0 / raw body 0 / DB 0 / LLM·embedding 실호출 0 / public IU 0**.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from backend.app.services.identity_human_labeling import LABEL_CONFIDENCES
from backend.app.tools.near_match_reviewer_queue import (
    EMBEDDING_LLM_ADJUDICATOR_INTERFACE,
    build_near_match_reviewer_queue,
)
from backend.app.tools.production_label_intake import _display_path
from backend.app.tools.reviewer_batch_launch import (
    LABELER_LABELS,
    build_assignment_manifest,
    build_intake_plan,
    build_label_template,
    build_reviewer_instruction,
)
from backend.app.tools.reviewer_followup_ops import (
    FOLLOWUP_CALIBRATION_PENDING,
    FOLLOWUP_CONFLICT_PENDING,
    FOLLOWUP_IMPORTED_READY,
    FOLLOWUP_INVALID,
    FOLLOWUP_NO_LABELS,
    FOLLOWUP_NOT_LAUNCHABLE,
    FOLLOWUP_PARTIAL,
    run_reviewer_followup_ops,
)
from backend.app.tools.reviewer_label_operations import (
    LABEL_SOURCE_PRODUCTION,
    LABEL_SOURCE_SYNTHETIC,
    LABEL_SOURCES,
)

OPERATION_NAME = "reviewer_pilot_handoff"

# ── §5 pilot status(8-state) ───────────────────────────────────────────────────────────────────────────
# not_ready: handoff bundle 미완성(또는 not_launchable=후보 0). ready_to_contact: bundle 완성·intake dir 미설정
# (접촉 전 — operator 가 reviewer 에게 bundle 을 건네야 함). awaiting_reviewer_return: bundle 완성·intake dir
# 설정(존재)·회수 0(회수 대기). partial_returned: 일부 회수·일부 missing. invalid_returned: malformed/forbidden/
# unknown/model 라벨(fail-loud). conflict_pending: 유효·완전 회수이나 reviewer 불일치. calibration_pending: 유효·
# 완전·충돌 0 이나 gold floor 미충족. imported_ready_for_merge_gate_review: 유효·완전·충돌 0·floor 충족(merge 허용 아님).
PILOT_NOT_READY = "not_ready"
PILOT_READY_TO_CONTACT = "ready_to_contact"
PILOT_AWAITING_RETURN = "awaiting_reviewer_return"
PILOT_PARTIAL_RETURNED = "partial_returned"
PILOT_INVALID_RETURNED = "invalid_returned"
PILOT_CONFLICT_PENDING = "conflict_pending"
PILOT_CALIBRATION_PENDING = "calibration_pending"
PILOT_IMPORTED_READY = "imported_ready_for_merge_gate_review"
PILOT_STATES = frozenset({
    PILOT_NOT_READY, PILOT_READY_TO_CONTACT, PILOT_AWAITING_RETURN, PILOT_PARTIAL_RETURNED,
    PILOT_INVALID_RETURNED, PILOT_CONFLICT_PENDING, PILOT_CALIBRATION_PENDING, PILOT_IMPORTED_READY,
})

# followup_status(라벨 회수 후) → pilot_status. no_labels/not_launchable 는 별도 처리(아래 _pilot_status).
_FOLLOWUP_TO_PILOT = {
    FOLLOWUP_PARTIAL: PILOT_PARTIAL_RETURNED,
    FOLLOWUP_INVALID: PILOT_INVALID_RETURNED,
    FOLLOWUP_CONFLICT_PENDING: PILOT_CONFLICT_PENDING,
    FOLLOWUP_CALIBRATION_PENDING: PILOT_CALIBRATION_PENDING,
    FOLLOWUP_IMPORTED_READY: PILOT_IMPORTED_READY,
}

# correction/adjudication template 종류.
CORRECTION_REQUEST = "label_correction_request"   # invalid label 파일 정정 요청(reason code only).
ADJUDICATION_HANDOFF = "conflict_adjudication_handoff"  # reviewer 불일치 → human lead 판정 이관.

# §6 handoff bundle·correction 에 **포함 금지**(PII/secret/bias 누출 차단) — 재귀 구조 가드(build 후 재검사).
# reviewer_followup_ops._REMINDER_FORBIDDEN_KEYS 와 동일 벡터(+ provider_secret) — drift 는 lock 테스트가 잡음.
_HANDOFF_FORBIDDEN_KEYS = frozenset({
    "reviewer_name", "name", "email", "phone", "score", "model_score", "rationale",
    "predicted_status", "raw_body", "body", "secret", "api_key", "provider_secret",
    "hidden_rank", "source_hidden_rank",
})

# §9 Agent / Intelligence Unit contract — Agent 는 pilot handoff/returned-label status 를 **계획**할 수 있으나
# label 조작·label file 임의 생성·merge·전송·PII 출력 불가.
REVIEWER_PILOT_AGENT_CONTRACT = {
    "can": [
        "reviewer pilot handoff readiness 점검", "returned label status 점검", "missing label follow-up 계획",
        "invalid label correction request 작성", "conflict adjudication handoff 계획",
        "calibration gap planning", "korean label collection plan", "internal ops UI status 요약",
        "next reviewer/operator action 도출",
    ],
    "cannot": [
        "reviewer label 조작", "label file 임의 생성해 production label 로 사용", "score 를 truth 로 사용",
        "same-event 확정", "merge 실행", "public Intelligence Unit 생성",
        "community reaction 을 event anchor 로 사용", "market/catalog 를 event anchor 로 사용",
        "secret 읽기/출력", "reviewer raw PII 출력", "actual email/slack/webhook 전송",
    ],
    "embedding_llm_adjudicator": EMBEDDING_LLM_ADJUDICATOR_INTERFACE,   # No-Go for merge(이번 턴 호출 0).
}

# pilot_status → operator 한 줄 next_action(ops UI 가 읽는 단일 요약).
_PILOT_NEXT_ACTION = {
    PILOT_NOT_READY: "cross-source 후보/assignment 0 — targeted same-event acquisition 후 packet 재발행(handoff 대상 없음)",
    PILOT_READY_TO_CONTACT: "handoff bundle 완성 — operator 가 reviewer 에게 instruction·template·assignment 배포(수동)",
    PILOT_AWAITING_RETURN: "intake 경로 설정됨(reviewer 접촉은 미검증) — 미접촉이면 먼저 bundle 배포·intake_directory 에 reviewer label JSONL 회수 후 returned-label gate 재실행",
    PILOT_PARTIAL_RETURNED: "부분 회수 — missing reviewer 에게 missing-label reminder(수동) 후 재회수",
    PILOT_INVALID_RETURNED: "invalid 회수 — reason code 로 correction request(값 미노출) 후 재배치·재검증",
    PILOT_CONFLICT_PENDING: "reviewer 불일치 — human lead adjudication 배정(자동 다수결 금지) 후 gold 재평가",
    PILOT_CALIBRATION_PENDING: "gold/Korean/hard-negative denominator 충원 — 실 reviewer label 회수 지속(merge 금지)",
    PILOT_IMPORTED_READY: "MERGE_GATE review 준비(병합 자동 실행 아님 — adversarial 승인 필요)",
}


# ── §A: pilot handoff bundle(PII-safe·전송 0) ──────────────────────────────────────────────────────────
def _assignment_summary_by_reviewer(manifest: dict, batch_id: str) -> dict:
    """manifest assignment → reviewer pseudonym 별 {pair_ids, pair_count, expected_label_filename}.

    raw reviewer id/name/email 0 — pseudonym·pair_id·파일명만(operator 가 pseudonym→실명은 local 매핑으로 처리)."""
    by_reviewer: dict[str, dict] = {}
    for a in manifest.get("assignments") or []:
        ps = a["reviewer_pseudonym"]
        entry = by_reviewer.setdefault(ps, {
            "reviewer_pseudonym": ps,
            "pair_ids": [],
            "expected_label_filename": f"{batch_id}__{ps}__labels.jsonl",
        })
        if a["pair_id"] not in entry["pair_ids"]:
            entry["pair_ids"].append(a["pair_id"])
    for entry in by_reviewer.values():
        entry["pair_ids"] = sorted(entry["pair_ids"])
        entry["pair_count"] = len(entry["pair_ids"])
    return {ps: by_reviewer[ps] for ps in sorted(by_reviewer)}


def _label_template_schema(template: list[dict]) -> dict:
    """label template → labeler 가 채울 schema(컬럼·허용값). 실제 행 dump 0(컬럼 이름·허용 어휘만·minimal).

    reviewer fill 칸(label/label_confidence/reviewed_at)과 고정 메타 컬럼을 분리해 노출. score/rationale/
    predicted_status 컬럼은 build_label_template 가 이미 allowlist 로 구조 차단(여기 도달 0)."""
    columns = sorted({k for row in template for k in row.keys()})
    fill_columns = ["label", "label_confidence", "reviewed_at"]
    return {
        "fill_columns": fill_columns,                       # reviewer 가 직접 채우는 칸.
        "fixed_columns": [c for c in columns if c not in fill_columns],  # packet 이 채워 배포(pseudonym·title·meta).
        "allowed_labels": sorted(LABELER_LABELS),
        "allowed_label_confidences": sorted(LABEL_CONFIDENCES),
        "reviewed_at_format": "ISO8601(예: 2026-06-26T00:00:00+00:00)",
    }


def build_pilot_handoff_bundle(
    *, batch_id: str, packet_id: str, instruction: dict, manifest: dict,
    intake_plan: dict, template: list[dict], intake_dir_display: str,
    due_hint: Optional[str] = None,
) -> dict:
    """§6 actual reviewer pilot handoff bundle — operator 가 그대로 reviewer 에게 배포(수동). **실제 전송 0**.

    포함(§6): reviewer instruction·reviewer 별 assignment summary·expected label filename·label template schema·
    intake directory·validation command·allowed labels·due_hint·pseudonym. **금지**(§6): raw name/email/phone·
    score·rationale·predicted_status·hidden rank·raw body·secret — instruction 구조 플래그에서 숨김 파생 +
    build 후 `_assert_pii_safe` 재귀 가드."""
    bundle = {
        "batch_id": batch_id,
        "packet_id": packet_id,
        "reviewer_instruction": dict(instruction),          # score/rationale/predicted_status 구조적 False(아래 파생).
        "assignment_summary_by_reviewer": _assignment_summary_by_reviewer(manifest, batch_id),
        "reviewer_pseudonyms": list(manifest.get("pseudonymous_reviewers") or []),
        "expected_label_files": list(intake_plan["expected_label_files"]),
        "label_template_schema": _label_template_schema(template),
        "label_template_row_count": len(template),
        "intake_directory": intake_dir_display,
        "validation_command": intake_plan["validation_command"],
        "allowed_labels": sorted(LABELER_LABELS),
        "due_hint_optional": due_hint,
        "delivery_note": "operator 가 instruction·label template·assignment summary 를 reviewer 에게 직접 배포(수동). 자동 전송 0.",
    }
    _assert_pii_safe(bundle)
    return bundle


def _assert_pii_safe(obj: Any, *, _path: str = "bundle") -> None:
    """bundle/template artifact 의 어떤 dict 도 forbidden 키(PII/secret/score/rationale/predicted_status)를
    노출하지 않음을 **재귀 구조 가드**로 보장(선언 상수 아님). 드리프트는 lock 테스트가 잡음."""
    if isinstance(obj, dict):
        leaked = set(obj) & _HANDOFF_FORBIDDEN_KEYS
        if leaked:
            raise ValueError(f"pilot handoff artifact leaks forbidden keys (PII/bias 차단) at {_path}: {sorted(leaked)}")
        for k, v in obj.items():
            _assert_pii_safe(v, _path=f"{_path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _assert_pii_safe(v, _path=f"{_path}[{i}]")


def _bundle_ready(*, instruction: dict, manifest: dict, intake_plan: dict, template: list[dict]) -> dict:
    """handoff bundle 완성도(각 artifact 존재) — not_ready 판정의 단일 출처. assignment 0(후보 0)이면 미완성."""
    reviewer_instruction_present = bool(instruction) and "label_vocabulary" in instruction
    assignment_manifest_present = bool(manifest.get("assignments"))
    label_template_present = bool(template)
    validation_command_present = bool(intake_plan.get("validation_command"))
    intake_directory_present = bool(intake_plan.get("intake_directory"))
    handoff_bundle_ready = all([
        reviewer_instruction_present, assignment_manifest_present, label_template_present,
        validation_command_present, intake_directory_present,
    ])
    return {
        "reviewer_instruction_present": reviewer_instruction_present,
        "assignment_manifest_present": assignment_manifest_present,
        "label_template_present": label_template_present,
        "validation_command_present": validation_command_present,
        "intake_directory_present": intake_directory_present,
        "handoff_bundle_ready": handoff_bundle_ready,
    }


# ── §5: pilot_status(followup 7-state + intake dir 존재 → 8-state) ──────────────────────────────────────
def _intake_dir_established(intake_dir: Any, label_rows: Optional[list[dict]]) -> bool:
    """intake 회수 경로가 **설정**됐는가(=intake dir 디스크 존재 또는 in-memory 라벨 채널). **주의**: 이는
    "회수 경로 설정 여부"의 프록시일 뿐 **reviewer 가 실제 접촉됐는지를 검증하지 않는다**(adversarial MEDIUM).
    `actual_sending_performed=False`·`reviewer_contact_required` 가 "접촉 미검증"을 함께 노출한다."""
    return label_rows is not None or (intake_dir is not None and Path(intake_dir).exists())


def _pilot_status(
    followup_status: str, *, bundle_ready: bool, dir_established: bool,
) -> str:
    """followup_status → pilot_status. bundle 미완성/not_launchable → not_ready. no_labels 는 intake dir 미설정
    (filesystem·미존재)이면 ready_to_contact(접촉 전), 그 외(설정·빈, 또는 in-memory 빈)면 awaiting_reviewer_return.
    **dir_established=회수 경로 설정 프록시이지 reviewer 접촉 검증 아님**(`_intake_dir_established` 참고)."""
    if not bundle_ready or followup_status == FOLLOWUP_NOT_LAUNCHABLE:
        return PILOT_NOT_READY
    if followup_status == FOLLOWUP_NO_LABELS:
        return PILOT_AWAITING_RETURN if dir_established else PILOT_READY_TO_CONTACT
    return _FOLLOWUP_TO_PILOT.get(followup_status, PILOT_NOT_READY)


# ── §7: correction / adjudication / calibration handoff template(전송 0) ────────────────────────────────
def build_correction_templates(
    *, batch_id: str, packet_id: str, intake_plan: dict,
    invalid_by_file_basename: dict[str, list[str]],
) -> list[dict]:
    """invalid label 파일별 correction request(reason code only·원본 값 미노출). **실제 전송 0**.

    basename 은 followup 이 이미 가명/마스킹(`nonconforming_file_N`)한 값 — raw 실명 0. reason code 만(score
    값·rationale 텍스트·secret 미포함). operator 가 복사해 reviewer 에게 수동 정정 요청."""
    templates: list[dict] = []
    for basename in sorted(invalid_by_file_basename):
        reason_codes = sorted(invalid_by_file_basename[basename])
        templates.append({
            "template_type": CORRECTION_REQUEST,
            "batch_id": batch_id,
            "packet_id": packet_id,
            "file_basename": basename,                  # 가명/마스킹된 basename(PII 아님).
            "reason_codes": reason_codes,               # reason code 만(원본 값 미노출).
            "allowed_labels": sorted(LABELER_LABELS),
            "validation_command": intake_plan["validation_command"],
            "message": (
                f"[batch {batch_id}] 파일 {basename}: 검증 실패({'/'.join(reason_codes)}). 허용 라벨"
                f"({'/'.join(sorted(LABELER_LABELS))})·허용 키만으로 정정 후 재배치. score/rationale/예측 미포함(직접 판단)."),
        })
    _assert_pii_safe(templates)
    return templates


def build_adjudication_handoff(
    *, batch_id: str, conflict_pair_count: int, adjudication_needed_count: int,
) -> dict:
    """conflict(reviewer 불일치) → human lead adjudication 이관 명세. **자동 다수결 금지**·전송 0.

    raw label 값/score 미포함 — conflict pair 수와 사람 판정 필요분만(누가 무엇을 판정할지는 operator-local)."""
    needed = conflict_pair_count > 0
    return {
        "template_type": ADJUDICATION_HANDOFF,
        "batch_id": batch_id,
        "adjudication_needed": needed,
        "conflict_pair_count": conflict_pair_count,
        "adjudication_needed_count": adjudication_needed_count,
        "adjudication_method": "human_lead_adjudication",
        "no_auto_majority": True,                       # conflict 를 자동 다수결로 gold 처리 금지.
        "message": (
            f"[batch {batch_id}] reviewer 불일치 conflict {conflict_pair_count}건 — human lead 가 각 pair 를 직접 "
            f"판정(자동 다수결 금지). 판정 후 gold 후보 재평가." if needed
            else "미해결 conflict 없음(adjudication 불필요)."),
    }


def build_calibration_gap(calibration_delta: dict) -> dict:
    """intake calibration_delta → merge_gate 까지 필요한 gold/Korean/hard-negative/negative gap(정량).

    calibration_delta 는 intake exact passthrough — handoff 는 재계산 0(필요분만 표면화)."""
    return {
        "merge_gate_ready": calibration_delta.get("merge_gate_ready", False),
        "production_gold_now": calibration_delta.get("after_production_gold_count", 0),
        "korean_calibration_ready": calibration_delta.get("korean_calibration_ready", False),
        "precision_denominator_ready": calibration_delta.get("precision_denominator_ready", False),
        "fpr_denominator_ready": calibration_delta.get("fpr_denominator_ready", False),
        "next_needed_for_merge_gate": list(calibration_delta.get("next_needed_for_merge_gate") or []),
    }


# ── §8: ops UI seed contract(internal ops dashboard 가 읽는 status — public truth 아님) ─────────────────
def build_ops_ui_contract(
    *, batch_id: str, pilot_status: str, followup_status: str, intake_status: str,
    expected_label_count: int, returned_label_count: int, missing_label_count: int,
    invalid_label_count: int, invalid_file_count: int, conflict_pair_count: int,
    production_gold_count: int, synthetic_gold_count: int,
    production_gold_provenance_verified: bool,
    calibration_ready: bool, merge_gate_ready: bool, next_action: str,
) -> dict:
    """§8 OpsReviewBatchStatus — 미래 internal ops dashboard 가 읽을 workflow state contract. **public IU 아님**.

    flags 가 명시: no_merge/no_public_iu/pii_safe/no_llm/no_db_write/**gold_provenance_verified**. 이 contract 는
    unverified truth 를 노출하지 않고 운영 워크플로 상태만 시각화한다(R-OpsUIPrematureTruth 가드). **provenance
    caveat 동반**(adversarial MEDIUM): production_gold_count 를 노출하면서 `production_gold_provenance_verified`
    (현재 항상 False·선언 기반)와 `synthetic_gold_count` 를 함께 실어, dashboard 가 미검증 gold 를 검증된 truth 로
    렌더하지 못하게 한다(이 누락이 forward-looking seed 에 박제되는 것 차단)."""
    return {
        "contract": "OpsReviewBatchStatus",
        "batch_id": batch_id,
        "pilot_status": pilot_status,
        "followup_status": followup_status,
        "intake_status": intake_status,
        "expected_label_count": expected_label_count,
        "returned_label_count": returned_label_count,
        "missing_label_count": missing_label_count,
        "invalid_label_count": invalid_label_count,
        # malformed/invalid **파일** 수(code-review LOW): malformed JSONL 은 0행 파싱→invalid_label_count(행 단위)=0
        # 이지만 invalid_returned 상태일 수 있어 self-contradictory metric 차단(file 단위 카운트 동반).
        "invalid_file_count": invalid_file_count,
        "conflict_pair_count": conflict_pair_count,
        "production_gold_count": production_gold_count,
        "synthetic_gold_count": synthetic_gold_count,
        # production gold 무결성은 **선언 기반**(provenance 미검증·R-IdentityHumanLabeling) — readiness 근거 인용 금지.
        "production_gold_provenance_verified": production_gold_provenance_verified,
        "calibration_ready": calibration_ready,
        "merge_gate_ready": merge_gate_ready,
        "next_action": next_action,
        "flags": {
            "no_merge": True,
            "no_public_iu": True,
            "pii_safe": True,
            "no_llm": True,
            "no_db_write": True,
            # gold provenance 미검증을 contract 표면에 명시(internal workflow state ≠ verified public truth).
            "gold_provenance_verified": production_gold_provenance_verified,
        },
    }


# ── §4: 통합 reviewer pilot handoff entrypoint ─────────────────────────────────────────────────────────
def run_reviewer_pilot_handoff(
    *, queue: Optional[dict] = None, discovery: Optional[dict] = None,
    batch_id: str = "reviewer_pilot_001", packet_id: str = "reviewer_pilot_pkt",
    intake_directory: Optional[Any] = None, label_rows: Optional[list[dict]] = None,
    label_source: str = LABEL_SOURCE_PRODUCTION, adjudications: Optional[dict] = None,
    reviewers: Optional[list[str]] = None, top_k_sourced: bool = True,
    include_synthetic_hard_negatives: bool = False, due_hint: Optional[str] = None,
    calibration_baseline: Optional[dict] = None,
) -> dict:
    """actual reviewer pilot handoff bundle + returned-label gate(병합 0·LLM 0·embedding 0·DB 0·전송 0).

    `run_reviewer_followup_ops` 를 단일 출처로 1회 호출해 followup_status/coverage/counts/gold/calibration/
    conflict 를 받고(그대로 passthrough — handoff 만으로 production_gold_count 증가 0), 그 위에 pilot handoff
    bundle·8-state pilot_status·correction/adjudication/calibration handoff·ops UI contract 를 더한다.
    returned label 없음 = 실패 아님(ready_to_contact/awaiting_reviewer_return). 어떤 경로도 merge/LLM/embedding/
    DB/전송을 건드리지 않는다."""
    if label_source not in LABEL_SOURCES:
        raise ValueError(f"invalid label_source {label_source!r} (allowed: {sorted(LABEL_SOURCES)})")
    # queue 를 한 번만 build 해 followup 과 bundle builder 가 동일 입력을 보게 한다(발산 0).
    if queue is None and discovery is not None:
        queue = build_near_match_reviewer_queue(
            discovery, packet_id=packet_id, reviewers=reviewers,
            include_synthetic_hard_negatives=include_synthetic_hard_negatives)
    queue = queue or {}

    # 1) followup(단일 출처) — status/coverage/counts/reminder/escalation/SLA·intake passthrough(gold/calibration/conflict).
    fu = run_reviewer_followup_ops(
        queue=queue, batch_id=batch_id, packet_id=packet_id,
        intake_directory=intake_directory, label_rows=label_rows, label_source=label_source,
        adjudications=adjudications, top_k_sourced=top_k_sourced, due_hint=due_hint,
        calibration_baseline=calibration_baseline)

    # 2) handoff bundle artifacts(pure builder·동일 queue/batch_id → followup 내부와 동일·발산 0).
    instruction = build_reviewer_instruction()
    manifest = build_assignment_manifest(queue, batch_id=batch_id)
    intake_plan = build_intake_plan(batch_id, pseudonyms=manifest["pseudonymous_reviewers"])
    template = build_label_template(queue)
    intake_dir = str(intake_directory) if intake_directory is not None else intake_plan["intake_directory"]
    intake_dir_display = _display_path(intake_dir)

    readiness = _bundle_ready(
        instruction=instruction, manifest=manifest, intake_plan=intake_plan, template=template)
    handoff_bundle = build_pilot_handoff_bundle(
        batch_id=batch_id, packet_id=packet_id, instruction=instruction, manifest=manifest,
        intake_plan=intake_plan, template=template, intake_dir_display=intake_dir_display, due_hint=due_hint)

    # 3) pilot_status(followup + intake dir 존재). returned/missing/invalid 카운트는 followup passthrough.
    returned_label_count = fu["submitted_label_count"]
    dir_established = _intake_dir_established(
        (None if label_rows is not None else intake_dir), label_rows)
    pilot_status = _pilot_status(
        fu["followup_status"], bundle_ready=readiness["handoff_bundle_ready"],
        dir_established=dir_established)

    # 4) §7 correction/adjudication/calibration handoff(전송 0). reminder 는 followup passthrough.
    correction_templates = build_correction_templates(
        batch_id=batch_id, packet_id=packet_id, intake_plan=intake_plan,
        invalid_by_file_basename=fu["invalid_by_file_basename"])
    adjudication_handoff = build_adjudication_handoff(
        batch_id=batch_id, conflict_pair_count=fu["conflict_pair_count"],
        adjudication_needed_count=fu["adjudication_needed_count"])
    calibration_gap = build_calibration_gap(fu["calibration_delta"])

    # 5) operator next actions(followup checklist + pilot 한 줄). reviewer_contact_required: 회수 전 단계.
    pilot_next_action = _PILOT_NEXT_ACTION.get(pilot_status, "")
    operator_next_actions = ([pilot_next_action] if pilot_next_action else []) + list(fu["operator_next_actions"])
    reviewer_contact_required = pilot_status in (PILOT_READY_TO_CONTACT, PILOT_AWAITING_RETURN)

    # 6) §8 ops UI seed contract(internal dashboard 가 읽는 workflow state).
    ops_ui_contract = build_ops_ui_contract(
        batch_id=batch_id, pilot_status=pilot_status, followup_status=fu["followup_status"],
        intake_status=fu["intake_status"], expected_label_count=fu["expected_label_count"],
        returned_label_count=returned_label_count, missing_label_count=fu["missing_label_count"],
        invalid_label_count=fu["invalid_label_count"],
        invalid_file_count=len(fu["invalid_by_file_basename"]), conflict_pair_count=fu["conflict_pair_count"],
        production_gold_count=fu["production_gold_count"], synthetic_gold_count=fu["synthetic_gold_count"],
        production_gold_provenance_verified=fu["production_gold_provenance_verified"],
        calibration_ready=fu["calibration_ready"],
        merge_gate_ready=fu["merge_gate_ready"], next_action=pilot_next_action)

    # labeler 숨김 플래그는 instruction 구조 플래그에서 **파생**(하드코딩 아님·adversarial 가드).
    score_hidden = not instruction.get("model_score_shown", False)
    rationale_hidden = not instruction.get("model_rationale_shown", False)
    predicted_hidden = not instruction.get("predicted_status_shown", False)

    block_reasons = list(fu["block_reasons"])
    result = {
        "operation_name": OPERATION_NAME,
        "batch_id": batch_id,
        "packet_id": packet_id,
        "pilot_status": pilot_status,
        "followup_status": fu["followup_status"],
        "intake_status": fu["intake_status"],
        # **번들 생성 ≠ pilot 실행**(adversarial overclaim 가드): 이 모듈은 handoff package 를 만들 뿐 실 reviewer 를
        # 접촉하거나 라벨을 회수하지 않는다. real_labels_returned 는 followup 회수분 passthrough(실 reviewer 회수 시만 >0).
        "pilot_executed": False,
        "real_reviewers_contacted": 0,
        "real_labels_returned": returned_label_count,
        "intake_directory_established": dir_established,   # 회수 경로 설정 프록시(reviewer 접촉 검증 아님).
        # §A handoff bundle readiness.
        "handoff_bundle_ready": readiness["handoff_bundle_ready"],
        "reviewer_instruction_present": readiness["reviewer_instruction_present"],
        "assignment_manifest_present": readiness["assignment_manifest_present"],
        "label_template_present": readiness["label_template_present"],
        "validation_command_present": readiness["validation_command_present"],
        "handoff_bundle": handoff_bundle,
        # §B returned-label gate(followup passthrough).
        "intake_directory": intake_dir_display,
        "expected_label_files": fu["expected_label_files"],
        "returned_label_files": fu["actual_label_files"],
        "nonconforming_filenames_count": fu["nonconforming_filenames_count"],
        "expected_label_count": fu["expected_label_count"],
        "returned_label_count": returned_label_count,
        "missing_label_count": fu["missing_label_count"],
        "invalid_label_count": fu["invalid_label_count"],
        "conflict_pair_count": fu["conflict_pair_count"],
        "calibration_gap": calibration_gap,
        "reviewer_contact_required": reviewer_contact_required,
        "actual_sending_performed": False,        # email/slack/webhook/sms 호출 0(템플릿/명세만).
        # §7 template/handoff(전송 0). reminder 는 followup passthrough.
        "reminder_templates": fu["reminder_templates"],
        "correction_templates": correction_templates,
        "adjudication_handoff": adjudication_handoff,
        "operator_next_actions": operator_next_actions,
        # §8 ops UI seed contract(internal dashboard·public truth 아님).
        "ops_ui_contract": ops_ui_contract,
        # PII/labeler 숨김(구조적 파생·재귀 가드).
        "raw_pii_exposed": False,
        "reviewer_ids_pseudonymous": True,
        "score_hidden_from_labeler": score_hidden,
        "rationale_hidden_from_labeler": rationale_hidden,
        "predicted_status_hidden": predicted_hidden,
        # gold/calibration 은 followup→intake exact passthrough — handoff 만으로 production_gold_count 증가 0.
        "production_gold_count": fu["production_gold_count"],
        "synthetic_gold_count": fu["synthetic_gold_count"],
        "production_gold_provenance_verified": fu["production_gold_provenance_verified"],
        "calibration_ready": fu["calibration_ready"],
        "merge_gate_ready": fu["merge_gate_ready"],
        "calibration_delta": fu["calibration_delta"],
        "merge_allowed": False,
        "no_merge_without_gold": True,
        "no_public_intelligence_unit": True,
        "db_write": False,
        "llm_invoked": False,
        "embedding_invoked": False,
        "agent_contract": REVIEWER_PILOT_AGENT_CONTRACT,
        "block_reasons": block_reasons,
        "next_actions": list(fu["next_actions"]),
    }
    # 전체 출력 재귀 forbidden-key 가드(adversarial LOW-MEDIUM): bundle/correction 뿐 아니라 **최상위 반환 dict
    # 전부**가 score/rationale/predicted_status/raw PII 키를 노출하지 않음을 보장(미래 편집 드리프트 fail-loud).
    _assert_pii_safe(result, _path="pilot_handoff_output")
    return result


# ── CLI(기본 captured fixture·network 0·DB 0·전송 0; synthetic partial 데모 opt-in) ────────────────────
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="actual reviewer pilot handoff bundle + returned-label gate (ADR#70·병합 0·LLM 0·DB 0·전송 0).")
    parser.add_argument("--intake-dir", metavar="DIR",
                        help="returned label intake directory(reviewer 별 *.jsonl 스캔). 미지정 시 batch 기본 경로.")
    parser.add_argument("--batch-id", default="reviewer_pilot_cli", help="batch id.")
    parser.add_argument("--synthetic-labels", action="store_true",
                        help="synthetic partial 회수 데모(첫 pair 만 회수·production gold 0·synthetic_fixture).")
    parser.add_argument("--synthetic-hard-negatives", action="store_true",
                        help="trap-zone synthetic hard negative 포함(calibration 연습).")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    from backend.app.tools.reviewer_followup_ops import _demo_followup_label_rows
    from backend.app.tools.source_overlap_discovery import (
        build_captured_overlap_fixture,
        discover_overlap,
    )
    disc = discover_overlap(build_captured_overlap_fixture())
    queue = build_near_match_reviewer_queue(
        disc, packet_id="reviewer_pilot_cli",
        include_synthetic_hard_negatives=ns.synthetic_hard_negatives)

    labels = None
    if ns.synthetic_labels:
        labels = _demo_followup_label_rows(build_assignment_manifest(queue, batch_id=ns.batch_id))
    out = run_reviewer_pilot_handoff(
        queue=queue, batch_id=ns.batch_id, packet_id="reviewer_pilot_cli",
        intake_directory=ns.intake_dir, label_rows=labels,
        label_source=LABEL_SOURCE_SYNTHETIC if ns.synthetic_labels else LABEL_SOURCE_PRODUCTION,
        top_k_sourced=False)

    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} batch_id={out['batch_id']} "
          f"pilot_status={out['pilot_status']} followup_status={out['followup_status']}")
    print(f"- bundle_ready: {out['handoff_bundle_ready']} instruction={out['reviewer_instruction_present']} "
          f"manifest={out['assignment_manifest_present']} template={out['label_template_present']} "
          f"validation_cmd={out['validation_command_present']}")
    print(f"- intake_dir: {out['intake_directory']}")
    print(f"- returns: returned={out['returned_label_count']}/{out['expected_label_count']} "
          f"missing={out['missing_label_count']} invalid={out['invalid_label_count']} "
          f"conflict={out['conflict_pair_count']} contact_required={out['reviewer_contact_required']}")
    print(f"- templates: reminders={len(out['reminder_templates'])} corrections={len(out['correction_templates'])} "
          f"adjudication_needed={out['adjudication_handoff']['adjudication_needed']}")
    print(f"- calibration_gap: {out['calibration_gap']['next_needed_for_merge_gate']}")
    print(f"- gold: production={out['production_gold_count']} synthetic={out['synthetic_gold_count']} "
          f"calibration_ready={out['calibration_ready']} merge_gate_ready={out['merge_gate_ready']}")
    print(f"- gates: merge_allowed={out['merge_allowed']} actual_sending={out['actual_sending_performed']} "
          f"db_write={out['db_write']} llm_invoked={out['llm_invoked']} embedding_invoked={out['embedding_invoked']} "
          f"raw_pii_exposed={out['raw_pii_exposed']}")
    print(f"- ops_ui: pilot_status={out['ops_ui_contract']['pilot_status']} "
          f"next_action={out['ops_ui_contract']['next_action']}")
    if out["operator_next_actions"]:
        print(f"- next: {out['operator_next_actions'][0]}")
    print(f"- block_reasons: {out['block_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
