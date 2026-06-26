"""ADR#69 — reviewer follow-up operations + label collection status cockpit (병합 0·LLM 0·embedding 0·DB 0·전송 0).

ADR#68 이 만든 것: `production_label_intake` — intake_directory 의 reviewer 별 `*.jsonl` 을 스캔해 validate→
agreement→gold→calibration delta 를 닫고, label 파일이 없으면 `awaiting_production_labels`(정직)로 보고. 그러나
그것은 **intake readiness** 이지 **reviewer follow-up 운영층**이 아니다 — 누가 어떤 pair 를 맡았고, 어떤 label
파일이 아직 missing 인지, 어떤 reviewer 에게 reminder 를 보내야 하는지, 어떤 상태에서 escalation 해야 하는지를
PII-safe 하게 추적하는 운영 cockpit 이 없다.

이 모듈은 **재구현이 아니라 follow-up orchestrator** 다. 무거운 일은 전부 기존 단일 출처가 한다:
  - intake validate→gold→calibration→5-state `intake_status`(단일 출처): `production_label_intake.run_production_label_intake`
  - reviewer assignment(pair 당 ≥2·pseudonym only)·expected label files·validation command: `reviewer_batch_launch`
  - per-file label 검증(forbidden/PII/pair_id/duplicate/model·schema): `reviewer_batch_launch.validate_label_intake`
  - reviewer queue(score/bias 0): `near_match_reviewer_queue.build_near_match_reviewer_queue`

이 모듈이 **새로** 더하는 것(기존에 없던 운영 결손):
  - **follow-up status cockpit(§A)**: assignment(expected) vs 회수(actual) 비교로 reviewer pseudonym/pair 별
    submitted/missing/invalid 를 산출하고 7-state `followup_status` 로 운영 상태를 분류.
  - **reminder/escalation template(§B·PII-safe)**: missing/partial/invalid/conflict/calibration/capacity 조건별
    **메시지 템플릿과 operator action** 만 생성(실제 email/slack/webhook 전송 0). pseudonym·basename·pair_id·
    validation command·allowed labels 만(raw name/email/phone·score·rationale·predicted_status 0).
  - **partial label status(§C)**: 라벨이 일부만 회수돼도 expected/submitted/missing·pair·reviewer coverage 를
    정량화(실 운영에서 라벨은 한 번에 다 오지 않는다 — partial 은 실패가 아니라 운영 상태).
  - **reviewer SLA/capacity(§D)**: required/assigned·capacity_status·coverage target·escalation threshold 산출
    (raw roster 미커밋·pseudonym only).

절대 불변(상속·상용 안전 계약):
  - **no merge / no auto-merge**: merge_allowed=False·no_merge_without_gold 불변. follow-up 은 merge 를 만들지 않는다.
  - **production_gold_count 0 정직·exact passthrough**: gold/calibration/merge_gate_ready 는 전부
    `production_label_intake` 결과를 **그대로 전달**한다. follow-up 만으로 production_gold_count 를 **증가시키지 않는다**.
  - **single reviewer ≠ gold**·**conflict ≠ 자동 다수결 gold**·**model/self/LLM label ≠ gold**(intake 가 강제).
  - **reviewer raw PII 0**: cockpit·reminder·escalation 표면에는 pseudonym·file basename·pair_id 만. raw
    name/email/phone·local roster mapping 은 출력·커밋 금지(intake_directory 는 `outputs/reviewer_batch/` gitignore).
  - **실제 전송 0**: reminder/escalation 은 **템플릿/action 명세**일 뿐 — email/slack/webhook 호출 0(operator 수동).
  - **secret 0 / raw body 0 / DB 0 / LLM·embedding 실호출 0 / public IU 0**.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from backend.app.services.identity_human_labeling import (
    DEFAULT_REVIEWERS_PER_PAIR,
    SOURCE_SYNTHETIC,
)
from backend.app.tools.near_match_reviewer_queue import (
    EMBEDDING_LLM_ADJUDICATOR_INTERFACE,
    build_near_match_reviewer_queue,
)
from backend.app.tools.production_label_intake import (
    INTAKE_INVALID,
    _display_path,
    run_production_label_intake,
)
from backend.app.tools.reviewer_batch_launch import (
    LABELER_LABELS,
    _read_jsonl,
    build_assignment_manifest,
    build_intake_plan,
    validate_label_intake,
)
from backend.app.tools.reviewer_label_operations import (
    GOLD_MERGE_MIN_KOREAN_GOLD,
    GOLD_MERGE_MIN_LIVE_GOLD,
    LABEL_SOURCE_PRODUCTION,
    LABEL_SOURCE_SYNTHETIC,
    LABEL_SOURCES,
)

OPERATION_NAME = "reviewer_followup_ops"

# ── §5 follow-up state machine(7-state) ───────────────────────────────────────────────────────────────
# not_launchable: assignment 0(packet 없음 — 후속할 대상 자체 없음). no_labels: assignment 있으나 회수 라벨 0.
# partial_labels: 일부 회수·일부 missing(정직·실패 아님). invalid_labels: malformed/forbidden/unknown/model 라벨
# 파일 존재(fail-loud). conflict_pending: 유효·완전 회수이나 reviewer 불일치. calibration_pending: 유효·완전·
# 충돌 0 이나 gold floor 미충족. imported_ready_for_merge_gate_review: 유효·완전·충돌 0·floor 충족(merge 허용 아님).
FOLLOWUP_NOT_LAUNCHABLE = "not_launchable"
FOLLOWUP_NO_LABELS = "no_labels"
FOLLOWUP_PARTIAL = "partial_labels"
FOLLOWUP_INVALID = "invalid_labels"
FOLLOWUP_CONFLICT_PENDING = "conflict_pending"
FOLLOWUP_CALIBRATION_PENDING = "calibration_pending"
FOLLOWUP_IMPORTED_READY = "imported_ready_for_merge_gate_review"
FOLLOWUP_STATES = frozenset({
    FOLLOWUP_NOT_LAUNCHABLE, FOLLOWUP_NO_LABELS, FOLLOWUP_PARTIAL, FOLLOWUP_INVALID,
    FOLLOWUP_CONFLICT_PENDING, FOLLOWUP_CALIBRATION_PENDING, FOLLOWUP_IMPORTED_READY,
})

# reminder template 종류.
REMINDER_FIRST = "first_reminder"            # 미제출 reviewer(no_labels/부분 배치의 전혀 안 한 reviewer).
REMINDER_MISSING = "missing_label_reminder"  # 일부 제출했으나 잔여 missing 이 있는 reviewer(partial).

# §6 reminder 에 **포함 금지**(PII/secret/bias 누출 차단) — 구조적 가드(build 후 재검사).
_REMINDER_FORBIDDEN_KEYS = frozenset({
    "reviewer_name", "name", "email", "phone", "score", "model_score", "rationale",
    "predicted_status", "raw_body", "body", "secret", "api_key", "hidden_rank", "source_hidden_rank",
})

# §9 Agent / Intelligence Unit contract — Agent 는 follow-up 을 **계획**할 수 있으나 label 조작·merge·전송 불가.
REVIEWER_FOLLOWUP_AGENT_CONTRACT = {
    "can": [
        "reviewer follow-up status 점검", "missing label reminder 계획", "invalid label correction 요청 작성",
        "conflict/adjudication follow-up 계획", "reviewer capacity planning",
        "calibration gap planning", "korean label collection plan", "next reviewer/operator action 도출",
    ],
    "cannot": [
        "reviewer label 조작", "label file 임의 생성해 production label 로 사용", "score 를 truth 로 사용",
        "same-event 확정", "merge 실행", "public Intelligence Unit 생성",
        "community reaction 을 event anchor 로 사용", "market/catalog 를 event anchor 로 사용",
        "secret 읽기/출력", "reviewer raw PII 출력", "actual email/slack/webhook 전송",
    ],
    "embedding_llm_adjudicator": EMBEDDING_LLM_ADJUDICATOR_INTERFACE,   # No-Go for merge(이번 턴 호출 0).
}

# block_reason → next_action(운영자/리뷰어 actionable).
_NEXT_ACTION = {
    "not_launchable": "cross-source 후보/assignment 0 — targeted same-event acquisition 후 packet 재발행(후속 대상 없음)",
    "insufficient_reviewer_capacity": "reviewer roster < 2 — pair 당 2명 합의 불가. reviewer 충원 후 batch 재발행",
    "no_labels": "회수된 label 0 — batch pack 배포 후 reviewer 에게 first reminder 발송(intake_directory 회수)",
    "partial_labels": "일부 reviewer/pair missing — missing_by_reviewer_pseudonym 기준 missing-label reminder 발송",
    "invalid_labels": "malformed/forbidden/unknown/model label 파일 — reason code 로 correction request(값 미노출)",
    "forbidden_field": "label 에 score/rationale/raw body/secret/PII 누출 — 해당 필드 제거(reviewer-facing 만)",
    "non_human_label": "model/self/LLM label 은 gold 불가(human only) — reviewer_kind=human 사람 라벨만",
    "unknown_pair_id": "label 의 pair_id 가 batch manifest 에 없음 — 배포된 packet 의 pair_id 만 라벨링",
    "duplicate_label": "(pair,reviewer,round) 중복 라벨 — 행 중복 제거 후 재제출",
    "malformed_label_file": "label JSONL JSON 오류 — 행 형식 점검 후 재배치(부분 import 금지)",
    "conflict_pending": "reviewer 불일치 conflict — human lead adjudication 으로 해소 후 gold 후보",
    "calibration_floor_not_met": (
        f"production gold denominator 미충족 — 실 reviewer label 충원(live {GOLD_MERGE_MIN_LIVE_GOLD}·"
        f"KO {GOLD_MERGE_MIN_KOREAN_GOLD})으로 floor 도달"),
    "unmatched_submissions": "manifest 에 없는 (reviewer,pair) 제출 — 배포된 assignment 의 pair_id/pseudonym 만 라벨링",
}


# ── §A: assignment(expected) vs 회수(actual) coverage(pseudonym 공간·재pseudonymize 0) ──────────────────
def compute_coverage(manifest: dict, raw_rows: list[dict]) -> dict:
    """manifest assignment(expected (pseudonym,pair) 튜플) vs 회수 행(actual) → coverage.

    회수 행의 `reviewer_id` 는 template 이 이미 pseudonymize 한 값이라 manifest pseudonym 과 같은 공간 — **재
    pseudonymize 0**. 매칭은 lenient(파싱된 (reviewer_id,pair_id) 존재 = 제출 시도) — 유효성은 §C 가 별도 산출.
    missing = expected − submitted. unmatched = 배포 밖(잘못된 pair/pseudonym) 제출."""
    expected = {(a["reviewer_pseudonym"], a["pair_id"]) for a in manifest.get("assignments") or []}
    expected_pairs = {pid for _, pid in expected}
    expected_pseudonyms = set(manifest.get("pseudonymous_reviewers") or [])

    submitted: set[tuple] = set()
    for r in raw_rows:
        rid, pid = r.get("reviewer_id"), r.get("pair_id")
        if isinstance(rid, str) and rid.strip() and isinstance(pid, str) and pid.strip():
            submitted.add((rid, pid))

    matched = submitted & expected
    missing = expected - submitted
    unmatched = submitted - expected

    missing_by_reviewer: dict[str, list[str]] = {}
    missing_by_pair: dict[str, list[str]] = {}
    for ps, pid in sorted(missing):
        missing_by_reviewer.setdefault(ps, []).append(pid)
        missing_by_pair.setdefault(pid, []).append(ps)

    pairs_with_label = len({pid for _, pid in matched})
    reviewers_submitted = {ps for ps, _ in matched}
    return {
        "expected_label_count": len(expected),
        "submitted_label_count": len(matched),
        "missing_label_count": len(missing),
        "unmatched_submission_count": len(unmatched),
        "pair_coverage_rate": round(pairs_with_label / len(expected_pairs), 4) if expected_pairs else None,
        "reviewer_coverage_rate": (
            round(len(reviewers_submitted) / len(expected_pseudonyms), 4) if expected_pseudonyms else None),
        "missing_by_reviewer_pseudonym": missing_by_reviewer,
        "missing_by_pair_id": missing_by_pair,
        "reviewers_submitted": sorted(reviewers_submitted),
    }


# ── §C: per-file 검증 attribution(basename → reason code·malformed·valid count — 값 미노출) ──────────────
def _attribute_files(
    intake_dir: Any, *, known_pair_ids: set, label_source: str, expected_files: set,
) -> tuple[list[dict], dict, int]:
    """intake_directory 의 `*.jsonl` 을 스캔 → **하나의 combined validation**(= intake 와 동일 입력)으로 검증하고
    error 를 row index 로 파일에 귀속 → ([{file, malformed, error_reasons, rows}], combined_report, nonconforming_count).

    **단일 검증 출처(중요·adversarial+code-review MEDIUM)**: rejection 카운트·invalid_by_file_basename·INVALID
    sub-reason 을 전부 이 combined_report 한 곳에서 파생해 self-consistent 보장(파일별 따로 검증하면 cross-file
    duplicate 누락·malformed 단락 시 카운트/basename 불일치). 행 순서는 sorted glob(= intake `_scan_intake_dir`).
    **basename PII 가드(adversarial MEDIUM)**: 기대 가명 파일명(`{batch_id}__{pseudonym}__labels.jsonl`) 밖의
    파일명은 `nonconforming_file_N` 으로 마스킹(운영자가 실명 파일로 저장해도 reviewer raw PII 0 보장)."""
    scanned: list[dict] = []
    nonconforming = 0
    d = Path(intake_dir)
    if d.exists() and d.is_dir():
        for fp in sorted(d.glob("*.jsonl")):
            if fp.name in expected_files:
                safe = fp.name
            else:
                nonconforming += 1
                safe = f"nonconforming_file_{nonconforming}"   # 실명 파일명 미노출(PII).
            try:
                rows = _read_jsonl(fp)
            except ValueError:
                scanned.append({"file": safe, "malformed": True, "rows": []})
                continue
            scanned.append({"file": safe, "malformed": False, "rows": rows})

    combined: list[dict] = []
    row_file: list[str] = []
    for s in scanned:
        for r in s["rows"]:
            combined.append(r)
            row_file.append(s["file"])
    report = validate_label_intake(combined, known_pair_ids=known_pair_ids, label_source=label_source)
    per_file: dict[str, set] = {s["file"]: set() for s in scanned}
    for e in report["errors"]:
        i = e["row"]
        if 0 <= i < len(row_file):
            per_file[row_file[i]].add(e["reason"])
    entries = [{"file": s["file"], "malformed": s["malformed"],
                "error_reasons": sorted(per_file.get(s["file"], ())), "rows": s["rows"]}
               for s in scanned]
    return entries, report, nonconforming


# ── §B: reminder template(PII-safe·전송 0) ─────────────────────────────────────────────────────────────
def build_reminder_templates(
    *, batch_id: str, packet_id: str, intake_plan: dict,
    missing_by_reviewer: dict[str, list[str]], reviewers_submitted: set,
    due_hint: Optional[str] = None,
) -> list[dict]:
    """missing 이 있는 reviewer pseudonym 별 reminder 템플릿(operator 가 복사해 수동 발송). **실제 전송 0**.

    포함: batch/packet/pseudonym/missing pair count·ids/expected filename/validation command/allowed labels/
    due_hint/instruction reference. **금지**(§6): raw name/email/phone·score·rationale·predicted_status·raw
    body·secret·hidden rank — 구조적 allowlist + build 후 `_REMINDER_FORBIDDEN_KEYS` 재검사."""
    templates: list[dict] = []
    for ps in sorted(missing_by_reviewer):
        missing_pids = missing_by_reviewer[ps]
        ttype = REMINDER_MISSING if ps in reviewers_submitted else REMINDER_FIRST
        allowed = sorted(LABELER_LABELS)
        templates.append({
            "template_type": ttype,
            "batch_id": batch_id,
            "packet_id": packet_id,
            "reviewer_pseudonym": ps,
            "missing_pair_count": len(missing_pids),
            "missing_pair_ids": list(missing_pids),     # pair_id 는 안전한 식별자(PII 아님).
            "expected_label_filename": f"{batch_id}__{ps}__labels.jsonl",
            "validation_command": intake_plan["validation_command"],
            "allowed_labels": allowed,
            "due_hint_optional": due_hint,
            "instruction_reference": "reviewer_instruction(label_vocabulary·criteria) — batch pack 동봉",
            # message: pseudonym·batch·파일명·라벨 어휘·개수만. 모델 판정/예측 미제공(직접 판단·bias 0).
            "message": (
                f"[batch {batch_id}] reviewer {ps}: 미회수 {len(missing_pids)}건 라벨 요청. "
                f"파일 {batch_id}__{ps}__labels.jsonl 에 허용 라벨({'/'.join(allowed)}) 로 작성 후 "
                f"검증 명령 실행. 모델 판정·예측 미제공(직접 판단)."),
        })
    # 구조적 재검사: 어떤 템플릿도 forbidden 키를 노출하지 않는다(드리프트는 lock 테스트가 잡음).
    for t in templates:
        leaked = set(t) & _REMINDER_FORBIDDEN_KEYS
        if leaked:
            raise ValueError(f"reminder template leaks forbidden keys (PII/bias 차단): {sorted(leaked)}")
    return templates


# ── §B: escalation action(조건별 operator action — 전송 0) ─────────────────────────────────────────────
def build_escalation_actions(
    *, capacity_status: str, missing_by_reviewer: dict[str, list[str]], reviewers_submitted: set,
    invalid_by_file_basename: dict[str, list[str]], conflict_pair_count: int,
    calibration_gaps: list[str],
) -> list[dict]:
    """§6 조건별 escalation action(operator 가 수동 수행). **email/slack/webhook 전송 0** — action 명세만."""
    actions: list[dict] = []
    if capacity_status != "ok":
        actions.append({
            "action_type": "assign_more_reviewers", "reason": "insufficient_reviewer_capacity",
            "detail": f"pair 당 {DEFAULT_REVIEWERS_PER_PAIR}명 합의 필요 — reviewer 충원 후 batch 재발행"})
    first = sorted(ps for ps in missing_by_reviewer if ps not in reviewers_submitted)
    miss = sorted(ps for ps in missing_by_reviewer if ps in reviewers_submitted)
    if first:
        actions.append({
            "action_type": "send_first_reminder", "reason": "no_labels", "targets": first,
            "detail": "batch pack 배포·첫 라벨 회수 reminder(전혀 미제출 reviewer)"})
    if miss:
        actions.append({
            "action_type": "send_missing_label_reminder", "reason": "partial_labels", "targets": miss,
            "detail": "부분 제출 reviewer 에 잔여 missing pair reminder"})
    if invalid_by_file_basename:
        reason_codes = sorted({rc for rcs in invalid_by_file_basename.values() for rc in rcs})
        actions.append({
            "action_type": "send_correction_request", "reason": "invalid_labels",
            "targets": sorted(invalid_by_file_basename),     # file basename(pseudonym 내포·PII 아님).
            "reason_codes": reason_codes,                    # reason code 만(값 미노출).
            "detail": "schema/forbidden/unknown/model/malformed — reason code 로 정정 요청(원본 값 미노출)"})
    if conflict_pair_count > 0:
        actions.append({
            "action_type": "assign_human_adjudicator", "reason": "conflict_pending",
            "conflict_pair_count": conflict_pair_count,
            "detail": "reviewer 불일치 — human lead adjudication 으로 해소(자동 다수결 금지)"})
    if calibration_gaps:
        actions.append({
            "action_type": "collect_more_labels", "reason": "calibration_pending",
            "gaps": list(calibration_gaps),
            "detail": "gold/Korean/hard-negative denominator 충원 — 실 reviewer label 회수 지속"})
    return actions


# ── §4: 통합 reviewer follow-up entrypoint ────────────────────────────────────────────────────────────
def run_reviewer_followup_ops(
    *, queue: Optional[dict] = None, discovery: Optional[dict] = None,
    batch_id: str = "reviewer_followup_001", packet_id: str = "reviewer_followup_pkt",
    intake_directory: Optional[Any] = None, label_rows: Optional[list[dict]] = None,
    label_source: str = LABEL_SOURCE_PRODUCTION, adjudications: Optional[dict] = None,
    reviewers: Optional[list[str]] = None, top_k_sourced: bool = True,
    include_synthetic_hard_negatives: bool = False, due_hint: Optional[str] = None,
    calibration_baseline: Optional[dict] = None,
) -> dict:
    """reviewer batch/intake output 기준 follow-up 운영 상태 cockpit(병합 0·LLM 0·embedding 0·DB 0·전송 0).

    `run_production_label_intake` 를 단일 출처로 호출해 intake_status/gold/calibration/conflict 를 받고(그대로
    passthrough — follow-up 만으로 production_gold_count 증가 0), 그 위에 assignment vs 회수 coverage·reminder/
    escalation template·SLA 를 더한다. label 없음 = 실패 아님(no_labels 운영 상태). 어떤 경로도 merge/LLM/
    embedding/DB/전송을 건드리지 않는다."""
    if label_source not in LABEL_SOURCES:
        raise ValueError(f"invalid label_source {label_source!r} (allowed: {sorted(LABEL_SOURCES)})")
    if queue is None and discovery is not None:
        queue = build_near_match_reviewer_queue(
            discovery, packet_id=packet_id, reviewers=reviewers,
            include_synthetic_hard_negatives=include_synthetic_hard_negatives)
    queue = queue or {}

    # launch pack 재사용(ADR#67) — assignment manifest(pseudonym·capacity)·intake plan(dir/files/command).
    manifest = build_assignment_manifest(queue, batch_id=batch_id)
    intake_plan = build_intake_plan(batch_id, pseudonyms=manifest["pseudonymous_reviewers"])
    intake_dir = str(intake_directory) if intake_directory is not None else intake_plan["intake_directory"]
    intake_dir_display = _display_path(intake_dir)
    known_pair_ids = set(queue.get("queue_pair_ids") or [])

    # intake(단일 출처) — gold/calibration/conflict/validity/status. malformed 검출 위해 file 경로는 intake 가 스캔.
    intake = run_production_label_intake(
        queue=queue, batch_id=batch_id, packet_id=packet_id,
        intake_directory=(None if label_rows is not None else intake_dir),
        label_rows=label_rows, label_source=label_source, adjudications=adjudications,
        top_k_sourced=top_k_sourced, calibration_baseline=calibration_baseline)

    # per-file attribution + **단일 combined validation**(coverage 행 + rejection 카운트 + correction reason code).
    # in-memory(테스트)는 단일 가상 파일 + combined report. filesystem 은 `_attribute_files`(가명 마스킹 포함).
    expected_files = set(intake_plan["expected_label_files"])
    nonconforming_filenames_count = 0
    if label_rows is not None:
        report = validate_label_intake(list(label_rows), known_pair_ids=known_pair_ids, label_source=label_source)
        file_entries = [{
            "file": "(in-memory)", "malformed": False,
            "error_reasons": sorted({e["reason"] for e in report["errors"]}), "rows": list(label_rows)}]
    else:
        file_entries, report, nonconforming_filenames_count = _attribute_files(
            intake_dir, known_pair_ids=known_pair_ids, label_source=label_source, expected_files=expected_files)

    raw_rows = [r for e in file_entries for r in e["rows"]]
    actual_label_files = [e["file"] for e in file_entries]
    malformed_files = [e["file"] for e in file_entries if e["malformed"]]
    invalid_by_file_basename: dict[str, list[str]] = {}
    for e in file_entries:
        if e["malformed"]:
            invalid_by_file_basename[e["file"]] = ["malformed_label_file"]
        elif e["error_reasons"]:
            invalid_by_file_basename[e["file"]] = e["error_reasons"]

    coverage = compute_coverage(manifest, raw_rows)
    reviewers_submitted = set(coverage["reviewers_submitted"])

    # rejection 카운트·valid/invalid 는 **followup 자체 combined report 단일 출처**(per-file basename·INVALID
    # sub-reason 과 정합·intake 의 malformed 단락과 무관하게 self-consistent·adversarial+code-review MEDIUM).
    reasons = [e["reason"] for e in report["errors"]]
    duplicate_label_count = reasons.count("duplicate_label")
    unknown_pair_id_count = len(report["unknown_pair_ids"])
    forbidden_field_count = reasons.count("forbidden_field")
    model_label_rejected_count = reasons.count("model_label_rejected")
    valid_label_count = report["valid_label_count"]
    invalid_label_count = len(report["errors"])

    # gold/calibration/conflict/status 만 intake passthrough(재계산 0). production_gold_count 는 follow-up 이 절대 증가 안 함.
    intake_status = intake["intake_status"]
    production_gold_count = intake["production_gold_count"]
    synthetic_gold_count = intake["synthetic_gold_count"]
    calibration_ready = intake["calibration_ready"]
    merge_gate_ready = intake["merge_gate_ready"]
    conflict_pair_count = intake.get("conflict_count", 0)
    calibration_gaps = list(intake["calibration_delta"]["next_needed_for_merge_gate"])

    # §5 followup_status precedence: not_launchable > invalid(fail-loud) > no_labels > partial >
    # conflict > calibration_floor > imported_ready. invalid 를 partial 보다 우선(혼란 숨김 금지).
    assignments_count = manifest["assignments_count"]
    block_reasons: list[str] = []
    if assignments_count == 0:
        followup_status = FOLLOWUP_NOT_LAUNCHABLE
        block_reasons.append("not_launchable")
    elif intake_status == INTAKE_INVALID:
        followup_status = FOLLOWUP_INVALID
        block_reasons.append("invalid_labels")
        if forbidden_field_count > 0:
            block_reasons.append("forbidden_field")
        if model_label_rejected_count > 0:
            block_reasons.append("non_human_label")
        if unknown_pair_id_count > 0:
            block_reasons.append("unknown_pair_id")
        if duplicate_label_count > 0:
            block_reasons.append("duplicate_label")
        if malformed_files:
            block_reasons.append("malformed_label_file")
    elif coverage["submitted_label_count"] == 0:
        followup_status = FOLLOWUP_NO_LABELS
        block_reasons.append("no_labels")
    elif coverage["missing_label_count"] > 0:
        followup_status = FOLLOWUP_PARTIAL
        block_reasons.append("partial_labels")
    elif conflict_pair_count > 0:
        followup_status = FOLLOWUP_CONFLICT_PENDING
        block_reasons.append("conflict_pending")
    elif not calibration_ready:
        followup_status = FOLLOWUP_CALIBRATION_PENDING
        block_reasons.append("calibration_floor_not_met")
    else:
        followup_status = FOLLOWUP_IMPORTED_READY

    # capacity insufficient 는 **assignment 가 있을 때만** 표면화(not_launchable=후보 0 이면 실제 action 은
    # "packet 재발행"이지 "reviewer 충원"이 아님·code-review LOW). escalation 도 동일 가드.
    capacity_actionable = manifest["capacity_status"] != "ok" and assignments_count > 0
    if capacity_actionable:
        block_reasons.append("insufficient_reviewer_capacity")
    if coverage["unmatched_submission_count"] > 0:
        block_reasons.append("unmatched_submissions")

    # §B reminder/escalation(전송 0). reminder 는 missing reviewer 별, escalation 은 조건별.
    reminder_templates = build_reminder_templates(
        batch_id=batch_id, packet_id=packet_id, intake_plan=intake_plan,
        missing_by_reviewer=coverage["missing_by_reviewer_pseudonym"],
        reviewers_submitted=reviewers_submitted, due_hint=due_hint)
    escalation_actions = build_escalation_actions(
        capacity_status=(manifest["capacity_status"] if capacity_actionable else "ok"),
        missing_by_reviewer=coverage["missing_by_reviewer_pseudonym"],
        reviewers_submitted=reviewers_submitted,
        invalid_by_file_basename=invalid_by_file_basename,
        conflict_pair_count=conflict_pair_count,
        calibration_gaps=(calibration_gaps if followup_status == FOLLOWUP_CALIBRATION_PENDING else []))

    # §D reviewer SLA/capacity(raw roster 미커밋·pseudonym only).
    reviewer_sla = {
        "reviewer_count_required": manifest["reviewer_count_required"],
        "reviewer_count_assigned": manifest["reviewer_count_assigned"],
        "reviewer_capacity_status": manifest["capacity_status"],
        "pair_coverage_target": 1.0,
        "reviewer_coverage_target": 1.0,
        "due_hint_optional": due_hint,
        "escalate_now": bool(coverage["missing_label_count"] > 0 or manifest["capacity_status"] != "ok"),
        "escalation_threshold_missing_gt": 0,
        "raw_roster_committed": False,
    }

    block_reasons = list(dict.fromkeys(block_reasons))
    next_actions = [_NEXT_ACTION.get(br, f"investigate: {br}") for br in block_reasons]
    operator_next_actions = _operator_checklist(
        followup_status, intake_plan=intake_plan, intake_dir_display=intake_dir_display,
        missing_by_reviewer=coverage["missing_by_reviewer_pseudonym"])

    return {
        "operation_name": OPERATION_NAME,
        "batch_id": batch_id,
        "packet_id": packet_id,
        "intake_directory": intake_dir_display,    # 절대경로 사용자명 미노출(ADR#68 _display_path).
        "expected_label_files": intake_plan["expected_label_files"],
        "actual_label_files": actual_label_files,
        "nonconforming_filenames_count": nonconforming_filenames_count,   # 기대 가명 패턴 밖 파일(마스킹됨·PII 가드).
        "intake_status": intake_status,
        "followup_status": followup_status,
        "reviewer_count_required": manifest["reviewer_count_required"],
        "reviewer_count_assigned": manifest["reviewer_count_assigned"],
        "reviewer_capacity_status": manifest["capacity_status"],
        "pair_count": manifest["pairs_count"],
        "assignment_count": assignments_count,
        "expected_label_count": coverage["expected_label_count"],
        "submitted_label_count": coverage["submitted_label_count"],
        "missing_label_count": coverage["missing_label_count"],
        "valid_label_count": valid_label_count,
        "invalid_label_count": invalid_label_count,
        "duplicate_label_count": duplicate_label_count,
        "unknown_pair_id_count": unknown_pair_id_count,
        "forbidden_field_count": forbidden_field_count,
        "model_label_rejected_count": model_label_rejected_count,
        "unmatched_submission_count": coverage["unmatched_submission_count"],
        "pair_coverage_rate": coverage["pair_coverage_rate"],
        "reviewer_coverage_rate": coverage["reviewer_coverage_rate"],
        "missing_by_reviewer_pseudonym": coverage["missing_by_reviewer_pseudonym"],
        "missing_by_pair_id": coverage["missing_by_pair_id"],
        "invalid_by_file_basename": invalid_by_file_basename,
        "conflict_pair_count": conflict_pair_count,
        "adjudication_needed_count": conflict_pair_count,   # 미해결 conflict pair = 사람 adjudication 필요분.
        "reminder_templates": reminder_templates,
        "escalation_actions": escalation_actions,
        "operator_next_actions": operator_next_actions,
        "validation_command": intake_plan["validation_command"],
        "reviewer_sla": reviewer_sla,
        # coverage=가명 공간(raw reviewer_id echo 0)·reminder=allowlist·**비-가명 파일명 마스킹**(nonconforming_file_N)
        # 의 구조적 다중 방어로 보장(선언 상수 아님·adversarial MEDIUM 해소).
        "raw_pii_exposed": False,
        "reviewer_ids_pseudonymous": True,
        # gold/calibration 은 intake exact passthrough — follow-up 만으로 production_gold_count 증가 0.
        "production_gold_count": production_gold_count,
        "synthetic_gold_count": synthetic_gold_count,
        "production_gold_provenance_verified": intake["production_gold_provenance_verified"],
        "calibration_ready": calibration_ready,
        "merge_gate_ready": merge_gate_ready,
        "calibration_delta": intake["calibration_delta"],
        "merge_allowed": False,
        "no_merge_without_gold": True,
        "no_public_intelligence_unit": True,
        "db_write": False,
        "llm_invoked": False,
        "embedding_invoked": False,
        "agent_contract": REVIEWER_FOLLOWUP_AGENT_CONTRACT,
        "block_reasons": block_reasons,
        "next_actions": next_actions,
    }


def _operator_checklist(
    followup_status: str, *, intake_plan: dict, intake_dir_display: str,
    missing_by_reviewer: dict[str, list[str]],
) -> list[str]:
    """followup_status 별 operator 체크리스트(상위 action 우선·actionable). 전송 지시 아님 — 수동 운영 안내."""
    missing_reviewers = sorted(missing_by_reviewer)
    base = {
        FOLLOWUP_NOT_LAUNCHABLE: [
            "cross-source 후보/assignment 0 — targeted same-event acquisition 후 packet 재발행",
            "reviewer roster ≥2 확보(pair 당 합의 필요)",
        ],
        FOLLOWUP_NO_LABELS: [
            "batch pack(instruction·label template·assignment manifest) reviewer 에게 배포",
            f"reviewer 작성 label JSONL 을 intake_directory 에 회수: {intake_dir_display}",
            f"미제출 reviewer 에게 first reminder 발송(수동): {missing_reviewers}",
            f"검증 명령 실행: {intake_plan['validation_command']}",
        ],
        FOLLOWUP_PARTIAL: [
            f"부분 회수 — missing reviewer 에게 missing-label reminder(수동): {missing_reviewers}",
            f"expected files 대조: {intake_plan['expected_label_files']}",
            f"검증 명령 실행: {intake_plan['validation_command']}",
        ],
        FOLLOWUP_INVALID: [
            "invalid_by_file_basename 의 reason code 로 reviewer 에게 correction request(값 미노출)",
            "정정된 label 파일 재배치 후 재검증",
        ],
        FOLLOWUP_CONFLICT_PENDING: [
            "conflict pair 에 human lead adjudication 배정(자동 다수결 금지)",
            "adjudication 후 gold 후보 재평가",
        ],
        FOLLOWUP_CALIBRATION_PENDING: [
            "gold/Korean/hard-negative denominator 충원 — 실 reviewer label 회수 지속",
            "calibration floor 도달 전 merge 금지(merge_allowed=False 불변)",
        ],
        FOLLOWUP_IMPORTED_READY: [
            "MERGE_GATE review 준비(병합 자동 실행 아님 — adversarial 승인 필요)",
        ],
    }
    return base.get(followup_status, [])


# ── CLI(기본 captured fixture·network 0·DB 0·전송 0; synthetic partial 데모 opt-in) ────────────────────
def _demo_row(ps: str, pid: str, label: str) -> dict:
    """경로 검증용 synthetic 제출 행(manifest pseudonym·labeler 어휘·**synthetic_fixture**·production gold 0)."""
    return {
        "pair_id": pid, "reviewer_id": ps, "review_round": 1, "label": label,
        "label_confidence": "medium", "reviewed_at": "2026-06-26T00:00:00+00:00", "language": "en",
        "source_type_left": "article", "source_type_right": "article",
        "title_left": "demo headline left", "title_right": "demo headline right",
        "observed_at_left": "2026-06-22", "observed_at_right": "2026-06-22",
        "dataset_source": SOURCE_SYNTHETIC,
    }


def _demo_followup_label_rows(manifest: dict) -> list[dict]:
    """첫 pair 만 2인 회수(나머지 missing → partial_labels 데모) — synthetic_fixture(production gold 0)."""
    assigns = manifest.get("assignments") or []
    pairs = sorted({a["pair_id"] for a in assigns})
    if not pairs:
        return []
    target = pairs[0]
    return [_demo_row(a["reviewer_pseudonym"], a["pair_id"], "same_event")
            for a in assigns if a["pair_id"] == target]


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="reviewer follow-up operations + label collection status cockpit (ADR#69·병합 0·LLM 0·DB 0·전송 0).")
    parser.add_argument("--intake-dir", metavar="DIR",
                        help="production label intake directory(reviewer 별 *.jsonl 스캔). 미지정 시 batch 기본 경로.")
    parser.add_argument("--batch-id", default="reviewer_followup_cli", help="batch id.")
    parser.add_argument("--synthetic-labels", action="store_true",
                        help="synthetic partial 회수 데모(첫 pair 만 회수·production gold 0·synthetic_fixture).")
    parser.add_argument("--synthetic-hard-negatives", action="store_true",
                        help="trap-zone synthetic hard negative 포함(calibration 연습).")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    from backend.app.tools.source_overlap_discovery import (
        build_captured_overlap_fixture,
        discover_overlap,
    )
    disc = discover_overlap(build_captured_overlap_fixture())
    queue = build_near_match_reviewer_queue(
        disc, packet_id="reviewer_followup_cli",
        include_synthetic_hard_negatives=ns.synthetic_hard_negatives)

    labels = None
    if ns.synthetic_labels:
        labels = _demo_followup_label_rows(build_assignment_manifest(queue, batch_id=ns.batch_id))
    out = run_reviewer_followup_ops(
        queue=queue, batch_id=ns.batch_id, packet_id="reviewer_followup_cli",
        intake_directory=ns.intake_dir, label_rows=labels,
        label_source=LABEL_SOURCE_SYNTHETIC if ns.synthetic_labels else LABEL_SOURCE_PRODUCTION,
        top_k_sourced=False)

    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} batch_id={out['batch_id']} "
          f"followup_status={out['followup_status']} intake_status={out['intake_status']}")
    print(f"- intake_dir: {out['intake_directory']}")
    print(f"- coverage: submitted={out['submitted_label_count']}/{out['expected_label_count']} "
          f"missing={out['missing_label_count']} pair_rate={out['pair_coverage_rate']} "
          f"reviewer_rate={out['reviewer_coverage_rate']}")
    print(f"- capacity: assigned={out['reviewer_count_assigned']}/{out['reviewer_count_required']} "
          f"status={out['reviewer_capacity_status']} pairs={out['pair_count']} assignments={out['assignment_count']}")
    print(f"- validity: valid={out['valid_label_count']} invalid={out['invalid_label_count']} "
          f"duplicate={out['duplicate_label_count']} unknown_pair={out['unknown_pair_id_count']} "
          f"forbidden={out['forbidden_field_count']} model={out['model_label_rejected_count']}")
    print(f"- conflict: pairs={out['conflict_pair_count']} adjudication_needed={out['adjudication_needed_count']}")
    print(f"- reminders: {len(out['reminder_templates'])} escalations: "
          f"{[a['action_type'] for a in out['escalation_actions']]}")
    print(f"- gold: production={out['production_gold_count']} synthetic={out['synthetic_gold_count']} "
          f"calibration_ready={out['calibration_ready']} merge_gate_ready={out['merge_gate_ready']}")
    print(f"- gates: merge_allowed={out['merge_allowed']} db_write={out['db_write']} "
          f"llm_invoked={out['llm_invoked']} embedding_invoked={out['embedding_invoked']} "
          f"raw_pii_exposed={out['raw_pii_exposed']}")
    if out["operator_next_actions"]:
        print(f"- next: {out['operator_next_actions'][0]}")
    print(f"- block_reasons: {out['block_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
