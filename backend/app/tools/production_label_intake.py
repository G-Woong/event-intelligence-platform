"""ADR#68 — first production labels import pilot + intake/gold/calibration dry-run (병합 0·LLM 0·embedding 0·DB 0).

ADR#67 이 만든 것: reviewer batch launch pack(instruction·label template·assignment manifest·intake plan·
validation command·no-labels report)과 in-memory/단일파일 intake validation dry-run. 그러나 그 pack 은
**아직 실제 운영 루프에 연결되지 않았다** — 실 reviewer 가 작성한 label 파일이 intake_directory 에 들어왔을 때
production label import → validation → agreement → gold 승격 → calibration delta 를 닫는 경로가 없다.

이 모듈은 **재구현이 아니라 first production label intake orchestrator** 다. 무거운 일은 전부 기존 단일 출처가 한다:
  - reviewer queue(score/bias 0): `near_match_reviewer_queue.build_near_match_reviewer_queue`
  - assignment manifest / intake plan(directory·expected files·validation command): `reviewer_batch_launch`
  - label intake dry-run(forbidden/PII/pair_id/duplicate/model-label·canonical 정규화): `reviewer_batch_launch.validate_label_intake`
  - resolve(agreement/conflict/gold)·calibration preflight: `reviewer_label_operations.{resolve_label_operations,build_calibration_preflight}`
  - decisive-gold 필터·PII strip·JSONL read·adjudication 정규화: `reviewer_batch_launch` 의 단일-출처 primitive 재사용

이 모듈이 **새로** 더하는 것(기존에 없던 운영 결손):
  - **filesystem 다중파일 intake**: intake_directory 의 reviewer 별 `*.jsonl` 을 스캔·집계(ADR#67 은 단일 파일/in-memory).
  - **awaiting_production_labels(정직)**: label 파일이 없으면 실패가 아니라 awaiting + **operator no_labels_report**
    (expected file path·validation command·reviewer count·instruction summary·next action checklist).
  - **production provenance gate**: production gold 는 label_source==production AND dataset_source==live_derived 의
    **decisive(same/different)** gold 만. synthetic/test/model label 은 production denominator 에서 분리(둔갑 차단).
  - **calibration delta(§8)**: import 전/후 production_gold·positive·negative·korean·agreement·conflict 변화와
    precision/FPR/korean denominator readiness·MERGE_GATE 까지 무엇이 더 필요한지(next_needed_for_merge_gate).

절대 불변(상속·상용 안전 계약):
  - **no merge / no auto-merge**: gold 는 metric/문서 전용. merge_allowed=False·no_merge_without_gold 불변.
  - **production_gold_count 0 정직**: 실 production human label(live_derived)이 없으면 0(synthetic/test=simulated only).
    production_gold_count 무결성은 **선언 기반**(provenance 미검증·B-1) — readiness 근거로 인용 금지.
  - **single reviewer ≠ gold**·**conflict ≠ 자동 다수결 gold**·**model/self/LLM label ≠ gold**(human only).
  - **reviewer raw PII 0**: 출력 표면(report·CLI)에는 pseudonym 만. raw reviewer_id/rationale 미노출. label 파일·
    roster·local mapping 은 commit 금지(intake_directory 는 outputs/ 하위·gitignore).
  - **secret 0 / raw body 0 / DB 0 / LLM·embedding 실호출 0 / public IU 0**.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from backend.app.services.identity_eval_dataset import LABEL_DIFFERENT, LABEL_SAME
from backend.app.services.identity_human_labeling import (
    DEFAULT_REVIEWERS_PER_PAIR,
    SOURCE_SYNTHETIC,
)
from backend.app.tools.near_match_reviewer_queue import (
    EMBEDDING_LLM_ADJUDICATOR_INTERFACE,
    build_near_match_reviewer_queue,
)
from backend.app.tools.reviewer_batch_launch import (
    _normalize_adjudications,
    _public_intake_report,
    _read_jsonl,
    _rows_to_labels,
    build_assignment_manifest,
    build_intake_plan,
    build_reviewer_instruction,
    validate_label_intake,
)
from backend.app.tools.reviewer_label_operations import (
    GOLD_MERGE_MIN_KOREAN_GOLD,
    GOLD_MERGE_MIN_LIVE_GOLD,
    LABEL_SOURCE_PRODUCTION,
    LABEL_SOURCE_SYNTHETIC,
    LABEL_SOURCES,
    build_calibration_preflight,
    resolve_label_operations,
)

OPERATION_NAME = "production_label_intake"

# ── §4 intake state machine ───────────────────────────────────────────────────────────────────────────
# awaiting_production_labels: label 파일 없음(또는 유효 라벨 0) — 실패 아님(정직). invalid_labels: 파일 있으나
# schema/forbidden/PII/pair_id 위반(fail-loud). imported: 유효 import·충돌 0·calibration ready(이번 턴 미도달).
# conflict_pending: import 됐으나 미해결 conflict 잔여. calibration_pending: import·충돌 0 이나 floor 미충족.
INTAKE_AWAITING_PRODUCTION = "awaiting_production_labels"
INTAKE_INVALID = "invalid_labels"
INTAKE_IMPORTED = "imported"
INTAKE_CONFLICT_PENDING = "conflict_pending"
INTAKE_CALIBRATION_PENDING = "calibration_pending"
INTAKE_STATES = frozenset({
    INTAKE_AWAITING_PRODUCTION, INTAKE_INVALID, INTAKE_IMPORTED,
    INTAKE_CONFLICT_PENDING, INTAKE_CALIBRATION_PENDING,
})

# synthetic hard-negative trap namespace(near_match_reviewer_queue 가 `hn_syn:{pid}` 로 발행) — 행 dataset_source 가
# live_derived 로 (오)태깅돼도 이 prefix 의 pair 는 **production gold 에서 구조적 배제**(선언 기반 provenance 의 알려진
# 합성 namespace 를 structural 가드로 격상·adversarial MEDIUM-2). 드리프트는 lock 테스트가 잡음.
_SYNTHETIC_PAIR_PREFIX = "hn_syn:"

# §6 failure classification(reason 별 fail-loud 분류). raw_pii_exposure 는 forbidden_field 의 부분집합(allowlist 가
# author/email/body 를 구조적 차단)이라 별도 row reason 은 없고, forbidden_field 로 흡수된다(참조용 상수).
FAILURE_CLASSES = frozenset({
    "malformed_label_file", "forbidden_field", "unknown_pair_id", "duplicate_label",
    "non_human_label", "raw_pii_exposure", "insufficient_reviewers", "non_decisive_only",
    "conflict_pending", "calibration_floor_not_met",
})

# §9 Agent / Intelligence Unit contract — Agent 는 production label intake 를 **계획**할 수 있으나 label 조작·merge 불가.
PRODUCTION_INTAKE_AGENT_CONTRACT = {
    "can": [
        "production label intake status 점검", "reviewer follow-up reminder 계획",
        "missing label file next action 도출", "invalid label correction 요청 작성",
        "agreement/conflict/adjudication workflow 계획", "gold calibration readiness 계획",
        "hard negative balancing 계획", "korean calibration 계획", "next reviewer action 도출",
    ],
    "cannot": [
        "reviewer label 조작", "label file 임의 생성해 production label 로 사용", "score 를 truth 로 사용",
        "same-event 확정", "merge 실행", "public Intelligence Unit 생성",
        "community reaction 을 event anchor 로 사용", "market/catalog 를 event anchor 로 사용",
        "secret 읽기/출력", "reviewer raw PII 출력",
    ],
    "embedding_llm_adjudicator": EMBEDDING_LLM_ADJUDICATOR_INTERFACE,   # No-Go for merge(이번 턴 호출 0).
}

# block_reason → next_action(운영자/리뷰어 actionable).
_NEXT_ACTION = {
    "no_packet": "cross-source 후보 0 — targeted same-event acquisition(source pair/topic/time window) 후 재시도",
    "insufficient_reviewers": "reviewer roster < 2 — pair 당 2명 합의 불가. reviewer 충원 후 batch 재발행",
    "no_production_labels": (
        "intake_directory 에 production label 파일 없음(또는 유효 라벨 0) — batch pack 배포→실 human label(JSONL) 회수"),
    "malformed_label_file": "label JSONL JSON/schema 오류 — 행 형식(allowlist 키·labeler 어휘) 점검 후 재배치",
    "invalid_labels": "label schema 오류 — validation_command 의 errors 로 행 수정 후 재intake",
    "forbidden_field": "label 에 score/rationale/raw body/secret/PII 누출 — 해당 필드 제거(reviewer-facing 만)",
    "non_human_label": "model/self/LLM label 은 gold 불가(human only) — reviewer_kind=human 사람 라벨만",
    "unknown_pair_id": "label 의 pair_id 가 batch manifest 에 없음 — 배포된 packet 의 pair_id 만 라벨링",
    "duplicate_label": "(pair,reviewer,round) 중복 라벨 — 행 중복 제거 후 재intake",
    "non_decisive_only": "유효 라벨이 unsure/needs_review 뿐 — same/different decisive 라벨이 있어야 gold 승격",
    "conflict_pending": "reviewer 불일치 conflict — human adjudication(lead 판정)으로 해소 후 gold 후보",
    "calibration_floor_not_met": (
        "production gold denominator 미충족 — 실 reviewer label 충원(live 200·KO 50)으로 floor 도달"),
    "insufficient_gold_for_calibration": (
        f"production gold < live floor({GOLD_MERGE_MIN_LIVE_GOLD}) — 실 reviewer label 충원 필요"),
    "merge_gate_not_ready": "MERGE_GATE(precision≥0.98·FPR≤0.01·hard_neg_fp=0·KO≥0.98) 미충족 — calibration 후 재평가",
}


# ── §5: operator no-labels report(awaiting_production_labels 일 때 actionable next action) ──────────────
def build_no_labels_report(intake_plan: dict, manifest: dict, instruction: dict, intake_dir: str) -> dict:
    """label 파일 없음(또는 유효 라벨 0) → operator/reviewer 가 무엇을 해야 하는지 구조화 보고(정직·actionable).

    no-labels 는 시스템 실패가 아니다. expected file path·validation command·reviewer count·instruction
    summary(모델 점수 0)·next action checklist 를 담아 reviewer follow-up 루프가 끊기지 않게 한다."""
    return {
        "status": INTAKE_AWAITING_PRODUCTION,
        "intake_directory": intake_dir,
        "expected_label_files": intake_plan["expected_label_files"],
        "expected_label_file_count": len(intake_plan["expected_label_files"]),
        "validation_command": intake_plan["validation_command"],
        "reviewer_count_required": manifest["reviewer_count_required"],
        "reviewer_count_assigned": manifest["reviewer_count_assigned"],
        "pairs_expected": manifest["pairs_count"],
        # instruction summary — labeler 어휘·목적만(모델 점수/rationale/predicted_status 0·§6 누출 차단).
        "reviewer_instruction_summary": {
            "purpose": instruction["purpose"],
            "label_vocabulary": instruction["label_vocabulary"],
            "model_score_shown": instruction["model_score_shown"],
            "predicted_status_shown": instruction["predicted_status_shown"],
        },
        "operator_next_actions": [
            "reviewer 에게 batch pack(instruction·label template·assignment manifest) 배포",
            "reviewer 가 label template 의 label/label_confidence/reviewed_at 작성(labeler 어휘)",
            f"작성한 label JSONL 을 intake_directory 에 배치: {intake_dir}",
            f"expected files: {intake_plan['expected_label_files']}",
            f"validation_command 실행: {intake_plan['validation_command']}",
            f"pair 당 최소 {DEFAULT_REVIEWERS_PER_PAIR}명 reviewer 확보(합의 필요)",
            "intake_directory 는 `outputs/reviewer_batch/`(gitignore) 하위 유지 — 실 reviewer 라벨 PII 커밋 금지(MEDIUM-3)",
        ],
    }


# ── 출력 표면용 경로 표시(절대경로 OS 사용자명 미노출·adversarial MEDIUM-1) ──────────────────────────────
def _display_path(p: Any) -> str:
    """report/no_labels_report 노출용 경로 — 상대경로는 그대로, 절대경로는 repo 상대화(불가 시 basename).

    기본 intake_directory(`outputs/reviewer_batch/...`)는 상대경로라 안전. caller 가 절대경로(override)를 주면
    repo 밖이면 basename 만(예: tmp_path → 'intake') → 출력에 `C:\\Users\\<user>\\...` 사용자명 미노출."""
    pth = Path(p)
    if not pth.is_absolute():
        return str(p).replace("\\", "/")
    try:
        return pth.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return pth.name


# ── filesystem 다중파일 스캔(intake_directory 의 reviewer 별 *.jsonl 집계·malformed fail-loud) ───────────
def _scan_intake_dir(intake_dir: Any) -> tuple[list[dict], list[str], list[dict]]:
    """intake_directory 의 `*.jsonl` 을 스캔 → (rows, label_files_found, malformed_files).

    파일명은 **basename 만**(절대경로/사용자명 PII 미노출). JSON 파싱 오류 파일은 malformed_files 로 분리하고
    그 행은 집계하지 않는다(부분 import 금지·fail-loud). 디렉토리 부재 = 빈 결과(awaiting)."""
    rows: list[dict] = []
    files_found: list[str] = []
    malformed: list[dict] = []
    d = Path(intake_dir)
    if not d.exists() or not d.is_dir():
        return rows, files_found, malformed
    for fp in sorted(d.glob("*.jsonl")):
        files_found.append(fp.name)
        try:
            rows.extend(_read_jsonl(fp))
        except ValueError as exc:
            # 메시지는 라인 번호/JSON 오류만(값 미포함 — secret/PII 비노출).
            malformed.append({"file": fp.name, "error": str(exc)[:200]})
    return rows, files_found, malformed


# ── §8: calibration delta(import 전/후·MERGE_GATE 까지 무엇이 더 필요한가) ─────────────────────────────
def _default_baseline() -> dict:
    """delta baseline 기본 — production gold 는 항상 0 이었으므로 0/None(정직). 미래 run 은 직전 snapshot 전달."""
    return {
        "production_gold_count": 0, "positive_gold_count": 0, "negative_gold_count": 0,
        "korean_gold_count": 0, "agreement_rate": None, "conflict_count": 0,
    }


def build_calibration_delta(
    *, production_gold_count: int, positive_gold_count: int, negative_gold_count: int,
    korean_gold_count: int, agreement_rate: Optional[float], conflict_count: int,
    precision_denominator_ready: bool, fpr_denominator_ready: bool,
    korean_calibration_ready: bool, merge_gate_ready: bool,
    baseline: Optional[dict] = None,
) -> dict:
    """import 전/후 gold·positive·negative·korean·agreement·conflict delta + denominator readiness + MERGE_GATE
    gap. floor 미충족이면 merge_gate_ready False·korean 미충족이면 korean_calibration_ready False(threshold 확정 금지)."""
    b = baseline or _default_baseline()

    def _num_delta(after: Optional[float], before: Optional[float]) -> Optional[float]:
        if after is None or before is None:
            return None
        return round(after - before, 4)

    def _int_delta(after: int, before: Optional[int]) -> Optional[int]:
        # baseline 정수 필드가 None 으로 전달돼도 crash 없이 None(adversarial LOW-3).
        return None if before is None else after - before

    next_needed: list[str] = []
    if production_gold_count < GOLD_MERGE_MIN_LIVE_GOLD:
        next_needed.append(
            f"+{GOLD_MERGE_MIN_LIVE_GOLD - production_gold_count} live production gold "
            f"(now {production_gold_count}/{GOLD_MERGE_MIN_LIVE_GOLD})")
    if korean_gold_count < GOLD_MERGE_MIN_KOREAN_GOLD:
        next_needed.append(
            f"+{GOLD_MERGE_MIN_KOREAN_GOLD - korean_gold_count} korean gold "
            f"(now {korean_gold_count}/{GOLD_MERGE_MIN_KOREAN_GOLD})")
    if negative_gold_count == 0:
        next_needed.append("≥1 different_event(negative) gold for FPR denominator")
    if not merge_gate_ready:
        next_needed.append("MERGE_GATE precision≥0.98/FPR≤0.01/hard_neg_fp=0/KO≥0.98")
    # partial baseline dict(키 누락)도 graceful — `.get` 으로 missing→0/None(KeyError 없음·code-review CR-C).
    return {
        "before_production_gold_count": b.get("production_gold_count", 0),
        "after_production_gold_count": production_gold_count,
        "gold_delta": _int_delta(production_gold_count, b.get("production_gold_count", 0)),
        "positive_delta": _int_delta(positive_gold_count, b.get("positive_gold_count", 0)),
        "negative_delta": _int_delta(negative_gold_count, b.get("negative_gold_count", 0)),
        "korean_delta": _int_delta(korean_gold_count, b.get("korean_gold_count", 0)),
        "agreement_delta": _num_delta(agreement_rate, b.get("agreement_rate")),
        "conflict_delta": _int_delta(conflict_count, b.get("conflict_count", 0)),
        "precision_denominator_ready": precision_denominator_ready,
        "fpr_denominator_ready": fpr_denominator_ready,
        "korean_calibration_ready": korean_calibration_ready,
        "merge_gate_ready": merge_gate_ready,
        "next_needed_for_merge_gate": next_needed,
    }


# ── §4: 통합 production label intake entrypoint ────────────────────────────────────────────────────────
def run_production_label_intake(
    *, queue: Optional[dict] = None, discovery: Optional[dict] = None,
    batch_id: str = "prod_intake_001", packet_id: str = "prod_intake_pkt",
    intake_directory: Optional[Any] = None, label_rows: Optional[list[dict]] = None,
    label_source: str = LABEL_SOURCE_PRODUCTION,
    adjudications: Optional[dict] = None, reviewers: Optional[list[str]] = None,
    top_k_sourced: bool = True, include_synthetic_hard_negatives: bool = False,
    calibration_baseline: Optional[dict] = None,
) -> dict:
    """reviewer batch launch output 기준 first production label intake(병합 0·LLM 0·embedding 0·DB 0).

    intake_directory(filesystem) 의 reviewer 별 `*.jsonl` 을 스캔하거나 label_rows(in-memory·테스트) 로 라벨 주입.
    파일 없음 → awaiting_production_labels(+ no_labels_report). 파일 있음 → import dry-run(invalid 면 fail-loud) →
    valid 면 agreement/gold/calibration preflight + delta. production gold 는 label_source==production &
    live_derived decisive(same/different) 일 때만 카운트. 어떤 경로도 merge/LLM/embedding/DB 를 건드리지 않는다."""
    if label_source not in LABEL_SOURCES:
        raise ValueError(f"invalid label_source {label_source!r} (allowed: {sorted(LABEL_SOURCES)})")
    if queue is None and discovery is not None:
        queue = build_near_match_reviewer_queue(
            discovery, packet_id=packet_id, reviewers=reviewers,
            include_synthetic_hard_negatives=include_synthetic_hard_negatives)
    queue = queue or {}
    block_reasons: list[str] = []

    # launch pack 재사용(ADR#67) — manifest(pairs/reviewer capacity/hard negative)·intake plan(dir/files/command).
    instruction = build_reviewer_instruction()
    manifest = build_assignment_manifest(queue, batch_id=batch_id)
    intake_plan = build_intake_plan(batch_id, pseudonyms=manifest["pseudonymous_reviewers"])
    intake_dir = str(intake_directory) if intake_directory is not None else intake_plan["intake_directory"]
    intake_dir_display = _display_path(intake_dir)   # 출력 표면용(절대경로 사용자명 미노출·MEDIUM-1).
    known_pair_ids = set(queue.get("queue_pair_ids") or [])
    pairs_expected = manifest["pairs_count"]
    if manifest["capacity_status"] != "ok":
        block_reasons.append("insufficient_reviewers")

    # 라벨 수집: in-memory(테스트) 우선, 없으면 filesystem 스캔.
    if label_rows is not None:
        raw_rows: list[dict] = list(label_rows)
        label_files_found = ["(in-memory)"]
        malformed_files: list[dict] = []
    else:
        raw_rows, label_files_found, malformed_files = _scan_intake_dir(intake_dir)

    # 정직 기본값(라벨 없음/무효 → 0/False/None).
    intake_report: Optional[dict] = None
    no_labels_report: Optional[dict] = None
    production_gold_count = synthetic_gold_count = non_decisive_gold_count = 0
    positive_gold_count = negative_gold_count = korean_gold_count = conflict_count = 0
    duplicate_label_count = unknown_pair_id_count = forbidden_field_count = model_label_rejected_count = 0
    pairs_labeled = reviewer_count_observed = 0
    agreement_rate: Optional[float] = None
    conflict_rate: Optional[float] = None
    precision_denominator_ready = fpr_denominator_ready = False
    korean_calibration_ready = calibration_ready = merge_gate_ready = False

    has_files = bool(label_files_found) or bool(malformed_files)
    label_import_attempted = (label_rows is not None) or has_files

    if not label_import_attempted:
        # §5 no-labels — 실패 아님(정직). production gold 0 유지.
        intake_status = INTAKE_AWAITING_PRODUCTION
        block_reasons.append("no_production_labels")
        no_labels_report = build_no_labels_report(intake_plan, manifest, instruction, intake_dir_display)
    elif malformed_files:
        # JSON 깨진 파일 — fail-loud(부분 import 금지).
        intake_status = INTAKE_INVALID
        block_reasons.append("malformed_label_file")
    else:
        intake_report = validate_label_intake(
            raw_rows, known_pair_ids=known_pair_ids, label_source=label_source)
        reasons = [e["reason"] for e in intake_report["errors"]]
        duplicate_label_count = reasons.count("duplicate_label")
        unknown_pair_id_count = len(intake_report["unknown_pair_ids"])
        forbidden_field_count = reasons.count("forbidden_field")
        model_label_rejected_count = reasons.count("model_label_rejected")
        if not intake_report["schema_valid"]:
            intake_status = INTAKE_INVALID
            block_reasons.append("invalid_labels")
            rs = set(reasons)
            for reason, br in (("forbidden_field", "forbidden_field"),
                               ("model_label_rejected", "non_human_label"),
                               ("unknown_pair_id", "unknown_pair_id"),
                               ("duplicate_label", "duplicate_label")):
                if reason in rs:
                    block_reasons.append(br)
        elif not intake_report["normalized_rows"]:
            # 파일은 있으나 유효 라벨 0(빈 파일) — awaiting(정직).
            intake_status = INTAKE_AWAITING_PRODUCTION
            block_reasons.append("no_production_labels")
            no_labels_report = build_no_labels_report(intake_plan, manifest, instruction, intake_dir_display)
        else:
            normalized = intake_report["normalized_rows"]
            reviewer_count_observed = intake_report["reviewer_count"]
            pairs_labeled = len({r["pair_id"] for r in normalized})
            # ADR#66/#67 building block 직접 재사용(resolve + decisive 필터 + calibration).
            labels = _rows_to_labels(normalized)
            try:
                resolve = resolve_label_operations(
                    labels, adjudications=_normalize_adjudications(adjudications), label_source=label_source)
            except ValueError:
                # model/self adjudicator 등 invalid adjudication → crash 대신 graceful block(non_human_label·LOW-4).
                # reviewer label 의 model_kind 는 validate_label_intake 가 이미 거부(여기 도달 시 adjudication 측 위반).
                intake_status = INTAKE_INVALID
                block_reasons.extend(["invalid_labels", "non_human_label"])
                resolve = None
            if resolve is not None:
                # **production gold = production AND live_derived AND decisive(same/different)**.
                # synthetic trap namespace(`hn_syn:`)는 행이 live 로 (오)태깅돼도 production 에서 배제(MEDIUM-2).
                prod_decisive = [g for g in resolve["production_gold"]
                                 if g.label in (LABEL_SAME, LABEL_DIFFERENT)
                                 and not g.pair_id.startswith(_SYNTHETIC_PAIR_PREFIX)]
                syn_namespace = [g for g in resolve["production_gold"]
                                 if g.label in (LABEL_SAME, LABEL_DIFFERENT)
                                 and g.pair_id.startswith(_SYNTHETIC_PAIR_PREFIX)]
                syn_decisive = [g for g in resolve["synthetic_gold"]
                                if g.label in (LABEL_SAME, LABEL_DIFFERENT)] + syn_namespace
                production_gold_count = len(prod_decisive)
                synthetic_gold_count = len(syn_decisive)
                non_decisive_gold_count = (
                    len(resolve["production_gold"]) + len(resolve["synthetic_gold"])
                    - production_gold_count - synthetic_gold_count)
                conflict_count = resolve["conflict_count"]
                agreement_rate = (resolve.get("agreement") or {}).get("agreement_rate")
                # calibration preflight 은 decisive production gold 로만(ambiguous padding 으로 floor 부풀리기 차단).
                resolve_decisive = dict(resolve)
                resolve_decisive["production_gold"] = prod_decisive
                resolve_decisive["production_gold_count"] = production_gold_count
                preflight = build_calibration_preflight(
                    resolve_decisive, hard_negative_count=manifest["hard_negative_count"],
                    top_k_sourced=top_k_sourced)
                positive_gold_count = preflight["positive_gold_count"]
                negative_gold_count = preflight["negative_gold_count"]
                korean_gold_count = preflight["korean_gold_count"]
                conflict_rate = preflight["conflict_rate"]
                precision_denominator_ready = preflight["precision_denominator_ready"]
                fpr_denominator_ready = preflight["fpr_denominator_ready"]
                korean_calibration_ready = preflight["korean_calibration_ready"]
                calibration_ready = preflight["calibration_ready"]
                merge_gate_ready = preflight["merge_gate_ready"]

                if label_source != LABEL_SOURCE_PRODUCTION:
                    block_reasons.append("no_production_labels")
                # status precedence: conflict > calibration floor > imported.
                if conflict_count > 0:
                    intake_status = INTAKE_CONFLICT_PENDING
                    block_reasons.append("conflict_pending")
                elif not calibration_ready:
                    intake_status = INTAKE_CALIBRATION_PENDING
                    block_reasons.append("calibration_floor_not_met")
                else:
                    intake_status = INTAKE_IMPORTED
                # 유효 라벨은 있으나 decisive gold 0(전부 unsure/needs_review) — non_decisive_only(정직).
                if (production_gold_count + synthetic_gold_count) == 0 and non_decisive_gold_count > 0:
                    block_reasons.append("non_decisive_only")
                if production_gold_count < GOLD_MERGE_MIN_LIVE_GOLD:
                    block_reasons.append("insufficient_gold_for_calibration")
                if not merge_gate_ready:
                    block_reasons.append("merge_gate_not_ready")

    pair_coverage_rate = round(pairs_labeled / pairs_expected, 4) if pairs_expected else None
    calibration_delta = build_calibration_delta(
        production_gold_count=production_gold_count, positive_gold_count=positive_gold_count,
        negative_gold_count=negative_gold_count, korean_gold_count=korean_gold_count,
        agreement_rate=agreement_rate, conflict_count=conflict_count,
        precision_denominator_ready=precision_denominator_ready,
        fpr_denominator_ready=fpr_denominator_ready,
        korean_calibration_ready=korean_calibration_ready, merge_gate_ready=merge_gate_ready,
        baseline=calibration_baseline)
    next_actions = [_NEXT_ACTION.get(br, f"investigate: {br}")
                    for br in dict.fromkeys(block_reasons)]

    return {
        "operation_name": OPERATION_NAME,
        "batch_id": batch_id,
        "packet_id": packet_id,
        "packet_source": "near_match_reviewer_queue(semantic scorer top-k)" if top_k_sourced else "discovery",
        "intake_directory": intake_dir_display,   # 절대경로 사용자명 미노출(MEDIUM-1).
        "expected_label_files": intake_plan["expected_label_files"],
        "label_files_found": label_files_found,
        "label_import_attempted": label_import_attempted,
        "intake_status": intake_status,
        "no_labels_report": no_labels_report,
        "validation_command": intake_plan["validation_command"],
        "reviewer_count_required": manifest["reviewer_count_required"],
        "reviewer_count_observed": reviewer_count_observed,
        "pairs_expected": pairs_expected,
        "pairs_labeled": pairs_labeled,
        "pair_coverage_rate": pair_coverage_rate,
        "duplicate_label_count": duplicate_label_count,
        "unknown_pair_id_count": unknown_pair_id_count,
        "forbidden_field_count": forbidden_field_count,
        "model_label_rejected_count": model_label_rejected_count,
        "raw_pii_exposed": False,           # 출력 표면에 raw reviewer_id/rationale 미노출(intake_report stripped).
        "reviewer_ids_pseudonymous": True,
        "production_gold_count": production_gold_count,
        "synthetic_gold_count": synthetic_gold_count,
        "non_decisive_gold_count": non_decisive_gold_count,
        # production_gold_count 무결성은 **선언 기반**(label_source/dataset_source 평문 태그·provenance 미검증).
        # 실 live provenance 바인딩(R-IdentityHumanLabeling) 전까지 readiness 근거로 인용 금지(adversarial B-1).
        "production_gold_provenance_verified": False,
        "positive_gold_count": positive_gold_count,
        "negative_gold_count": negative_gold_count,
        "agreement_rate": agreement_rate,
        "conflict_rate": conflict_rate,
        "korean_gold_count": korean_gold_count,
        "korean_calibration_target": GOLD_MERGE_MIN_KOREAN_GOLD,
        "hard_negative_count": manifest["hard_negative_count"],
        "calibration_ready": calibration_ready,
        "merge_gate_ready": merge_gate_ready,
        "calibration_delta": calibration_delta,
        "merge_allowed": False,
        "no_merge_without_gold": True,
        "no_public_intelligence_unit": True,
        "db_write": False,
        "llm_invoked": False,
        "embedding_invoked": False,
        "intake_report": _public_intake_report(intake_report),   # raw 행 제거(PII·adversarial B-3).
        "agent_contract": PRODUCTION_INTAKE_AGENT_CONTRACT,
        "block_reasons": list(dict.fromkeys(block_reasons)),
        "next_actions": next_actions,
    }


# ── CLI(기본 captured fixture·network 0·DB 0·라벨 없음=awaiting_production_labels 정직; synthetic 데모 opt-in) ──
def _demo_synthetic_label_rows(queue: dict) -> list[dict]:
    """경로 검증용 synthetic label rows(2인 만장일치 1·conflict 1) — labeler 어휘·**synthetic_fixture**(production gold 0)."""
    pairs = list(queue.get("queue_pair_ids") or [])[:2]
    if len(pairs) < 2:
        return []

    def _row(pid: str, rid: str, label: str) -> dict:
        return {
            "pair_id": pid, "reviewer_id": rid, "review_round": 1, "label": label,
            "label_confidence": "medium", "reviewed_at": "2026-06-26T00:00:00+00:00", "language": "en",
            "source_type_left": "article", "source_type_right": "article",
            "title_left": "demo headline left", "title_right": "demo headline right",
            "observed_at_left": "2026-06-22", "observed_at_right": "2026-06-22",
            "dataset_source": SOURCE_SYNTHETIC,
        }
    return [
        _row(pairs[0], "reviewer_a", "different_event"),
        _row(pairs[0], "reviewer_b", "different_event"),   # 만장일치 → simulated gold(production 아님)
        _row(pairs[1], "reviewer_a", "same_event"),
        _row(pairs[1], "reviewer_b", "needs_review"),      # conflict → adjudication queue
    ]


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="first production labels import pilot + intake/gold/calibration dry-run (ADR#68·병합 0·LLM 0·DB 0).")
    parser.add_argument("--intake-dir", metavar="DIR",
                        help="production label intake directory(reviewer 별 *.jsonl 스캔). 미지정 시 batch 기본 경로.")
    parser.add_argument("--batch-id", default="prod_intake_cli", help="batch id.")
    parser.add_argument("--synthetic-labels", action="store_true",
                        help="synthetic label rows 데모(경로 검증·production gold 0·synthetic_fixture).")
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
        disc, packet_id="prod_intake_cli",
        include_synthetic_hard_negatives=ns.synthetic_hard_negatives)

    labels = _demo_synthetic_label_rows(queue) if ns.synthetic_labels else None
    out = run_production_label_intake(
        queue=queue, batch_id=ns.batch_id, packet_id="prod_intake_cli",
        intake_directory=ns.intake_dir, label_rows=labels,
        label_source=LABEL_SOURCE_SYNTHETIC if ns.synthetic_labels else LABEL_SOURCE_PRODUCTION,
        top_k_sourced=False)

    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} batch_id={out['batch_id']} status={out['intake_status']}")
    print(f"- intake_dir: {out['intake_directory']}")
    print(f"- files_found: {out['label_files_found']} import_attempted={out['label_import_attempted']}")
    print(f"- coverage: pairs_labeled={out['pairs_labeled']}/{out['pairs_expected']} "
          f"rate={out['pair_coverage_rate']} reviewers={out['reviewer_count_observed']}/{out['reviewer_count_required']}")
    print(f"- rejections: duplicate={out['duplicate_label_count']} unknown_pair={out['unknown_pair_id_count']} "
          f"forbidden={out['forbidden_field_count']} model_label={out['model_label_rejected_count']}")
    print(f"- gold: production={out['production_gold_count']} synthetic={out['synthetic_gold_count']} "
          f"non_decisive={out['non_decisive_gold_count']} pos={out['positive_gold_count']} neg={out['negative_gold_count']} "
          f"ko={out['korean_gold_count']}")
    print(f"- calibration: ready={out['calibration_ready']} merge_gate_ready={out['merge_gate_ready']} "
          f"gold_delta={out['calibration_delta']['gold_delta']} "
          f"next_needed={out['calibration_delta']['next_needed_for_merge_gate']}")
    print(f"- gates: merge_allowed={out['merge_allowed']} db_write={out['db_write']} "
          f"llm_invoked={out['llm_invoked']} embedding_invoked={out['embedding_invoked']} "
          f"provenance_verified={out['production_gold_provenance_verified']}")
    if out["no_labels_report"]:
        print(f"- no_labels next: {out['no_labels_report']['operator_next_actions'][0]}")
    print(f"- block_reasons: {out['block_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
