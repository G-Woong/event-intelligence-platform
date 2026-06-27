"""ADR#67 — reviewer batch launch pack + intake validation loop (병합 0·LLM 0·embedding 0·DB 0).

ADR#66 이 만든 것: scored reviewer queue → packet export → label import → agreement/conflict/adjudication →
gold 승격 → MERGE_GATE calibration preflight 의 운영 **함수**. 그러나 그 함수들은 **사람이 바로 라벨링을
시작할 수 있는 운영 패키지**가 아니다 — reviewer instruction·label template·assignment manifest·intake
directory·validation command·no-labels report 가 하나의 launch pack 으로 묶여있지 않다.

이 모듈은 **재구현이 아니라 launch-readiness orchestrator** 다. 무거운 일은 전부 기존 단일 출처가 한다:
  - reviewer queue(score/bias 0): `near_match_reviewer_queue.build_near_match_reviewer_queue`
  - packet export(labeler-facing score-free): `reviewer_label_operations.export_reviewer_packet`
  - reviewer instruction/정책/구조적 hidden-verify: `targeted_same_event_acquisition.build_reviewer_operating_checklist`
  - label import/agreement/gold/calibration: `reviewer_label_operations.run_reviewer_label_operations`
  - reviewer_id pseudonymization: `reviewer_label_operations.pseudonymize_reviewer_id`

이 모듈이 **새로** 더하는 것(기존에 없던 운영 결손):
  - **batch launch pack**: instruction + label template + assignment manifest + intake plan(directory/expected
    files/validation command)을 하나의 batch_id 로 묶어 export.
  - **assignment manifest**: pair 당 ≥2 reviewer(capacity 충분 시)·pseudonym only·top-k + hard negative balance.
  - **intake validation loop**: label file 들어오기 전에도 forbidden field/malformed/label_source/reviewer_kind/
    pair_id/duplicate 를 dry-run 검사. label 없음 = 실패가 아니라 `awaiting_labels`(정직).
  - **labeler vocabulary 정규화**: §6 labeler 용어(unsure/needs_review)를 frozen GOLD_LABELS(insufficient/
    ambiguous)로 정규화 — frozen `load_reviewer_labels` 계약을 건드리지 않고 reviewer 친화 어휘를 수용.

절대 불변(상속·상용 안전 계약):
  - **no merge / no auto-merge**: gold 는 metric/문서 전용. merge_allowed=False·no_merge_without_gold 불변.
  - **production_gold_count 0 정직**: 실 production human label(live_derived)이 없으면 0(synthetic/test=simulated only).
  - **single reviewer ≠ gold**·**conflict ≠ 자동 다수결 gold**·**model/self/LLM label ≠ gold**(human only).
  - **labeler 숨김**: score/rationale/predicted_status 는 labeler-facing artifact 에 0(구조적 검증).
  - **reviewer raw PII 0**: assignment manifest·template 은 pseudonym 만. raw roster 는 commit 금지.
  - **secret 0 / raw body 0 / DB 0 / LLM·embedding 실호출 0 / public IU 0**.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from backend.app.services.identity_eval_dataset import (
    _MAX_TITLE_LEN,
    LABEL_AMBIGUOUS,
    LABEL_DIFFERENT,
    LABEL_INSUFFICIENT,
    LABEL_SAME,
    LANGUAGES,
    SOURCE_TYPES,
)
from backend.app.services.identity_human_labeling import (
    DATASET_SOURCES,
    DEFAULT_REVIEWERS_PER_PAIR,
    LABEL_CONFIDENCES,
    REVIEWER_ALLOWED_KEYS,
    REVIEWER_HUMAN,
    REVIEWER_KINDS,
    SOURCE_LIVE,
    SOURCE_SYNTHETIC,
    ReviewerLabel,
    _validate_reviewed_at,
)
from backend.app.tools.near_match_reviewer_queue import (
    EMBEDDING_LLM_ADJUDICATOR_INTERFACE,
    build_near_match_reviewer_queue,
)
from backend.app.tools.reviewer_label_operations import (
    FORBIDDEN_LABEL_FIELDS,
    GOLD_MERGE_MIN_KOREAN_GOLD,
    GOLD_MERGE_MIN_LIVE_GOLD,
    LABEL_SOURCE_PRODUCTION,
    LABEL_SOURCE_SYNTHETIC,
    LABEL_SOURCES,
    build_calibration_preflight,
    export_reviewer_packet,
    pseudonymize_reviewer_id,
    resolve_label_operations,
)
from backend.app.tools.targeted_same_event_acquisition import (
    build_reviewer_operating_checklist,
)

OPERATION_NAME = "reviewer_batch_launch"

# ── intake state machine(§4 contract 4-state; conflict_pending/calibration_pending 는 imported 의 파생). ──
INTAKE_AWAITING = "awaiting_labels"
INTAKE_PRESENT = "labels_present"
INTAKE_INVALID = "invalid_labels"
INTAKE_IMPORTED = "imported"
INTAKE_STATES = frozenset({INTAKE_AWAITING, INTAKE_PRESENT, INTAKE_INVALID, INTAKE_IMPORTED})

# ── labeler vocabulary(§5/§6) → frozen GOLD_LABELS 정규화 ─────────────────────────────────────────────
# §6 reviewer 는 같은-사건 4-라벨로 판단: same_event/different_event/unsure/needs_review. frozen
# `_validate_reviewer_row` 는 GOLD_LABELS(same_event/different_event/ambiguous/insufficient)만 허용하므로,
# labeler 용어를 canonical 로 정규화한다(unsure=정보 부족→insufficient, needs_review=추가 판단 필요→ambiguous).
# 둘 다 gold 비대상(resolve 는 만장일치 same/different 만 승격) — "unsure/needs_review only → not gold" 보장.
LABELER_SAME = "same_event"
LABELER_DIFFERENT = "different_event"
LABELER_UNSURE = "unsure"
LABELER_NEEDS_REVIEW = "needs_review"
LABELER_LABELS = frozenset({LABELER_SAME, LABELER_DIFFERENT, LABELER_UNSURE, LABELER_NEEDS_REVIEW})
_LABELER_TO_GOLD = {
    LABELER_SAME: LABEL_SAME,
    LABELER_DIFFERENT: LABEL_DIFFERENT,
    LABELER_UNSURE: LABEL_INSUFFICIENT,
    LABELER_NEEDS_REVIEW: LABEL_AMBIGUOUS,
}

# ReviewerLabel 필수 키 — identity_human_labeling._REVIEWER_REQUIRED_KEYS 를 mirror(drift 는 lock 테스트가 잡음).
_INTAKE_REQUIRED_KEYS = frozenset({
    "pair_id", "reviewer_id", "review_round", "label", "label_confidence", "reviewed_at",
    "language", "source_type_left", "source_type_right",
    "title_left", "title_right", "observed_at_left", "observed_at_right",
})
# model/self/LLM reviewer_kind(human 외) — public REVIEWER_KINDS 에서 파생(private import 회피).
_MODEL_KINDS = frozenset(REVIEWER_KINDS) - {REVIEWER_HUMAN}
# _MAX_TITLE_LEN 은 frozen identity_eval_dataset 에서 import(literal drift 회피·adversarial B-4).

# §6 reviewer instruction — 같은-사건 판정 기준·금지·권장(모델 점수/rationale/predicted_status/숨은 rank 0).
REVIEWER_INSTRUCTION = {
    "purpose": "두 기사가 같은 실제 사건을 다루는지 판단한다(제목/메타데이터만·raw body 없음).",
    "criteria": {
        "same_event": "같은 시점/장소/행위자/사건 결과를 공유한다.",
        "different_event": "같은 주제라도 구체 사건이 다르다.",
        "unsure": "정보 부족으로 판단 불가(canonical: insufficient).",
        "needs_review": "사람이 추가 판단/조정이 필요(canonical: ambiguous).",
    },
    "forbidden": [
        "모델 점수 추측",
        "source 신뢰도만으로 same_event 결정",
        "같은 주제라는 이유만으로 same_event 결정",
        "headline 단어가 다르다는 이유만으로 무조건 different_event",
        "community reaction 을 event anchor 로 사용",
        "market/catalog 를 event anchor 로 사용",
    ],
    "recommended": [
        "title/canonical_url/published/source 를 함께 본다.",
        "불확실하면 unsure/needs_review 로 남긴다(추측 금지).",
        "rationale 은 짧고 구체적으로 작성한다.",
    ],
    "label_vocabulary": sorted(LABELER_LABELS),
    "canonical_mapping": dict(sorted(_LABELER_TO_GOLD.items())),
    # §6 instruction must not include — 구조적으로 False 명시(누출 0).
    "model_score_shown": False,
    "model_rationale_shown": False,
    "predicted_status_shown": False,
    "hidden_candidate_rank_shown": False,
}

# §10 Agent contract — Agent 는 batch launch/intake 를 **계획**할 수 있으나 label 조작·merge 는 불가.
BATCH_LAUNCH_AGENT_CONTRACT = {
    "can": [
        "reviewer batch launch 계획", "reviewer assignment 계획", "label intake status 점검",
        "agreement/adjudication workflow 계획", "gold calibration readiness 계획",
        "hard negative balancing 계획", "korean calibration 계획", "next reviewer action 도출",
    ],
    "cannot": [
        "reviewer label 조작", "score 를 truth 로 사용", "same-event 확정", "merge 실행",
        "public Intelligence Unit 생성", "community reaction 을 event anchor 로 사용",
        "market/catalog 를 event anchor 로 사용", "secret 읽기/출력", "reviewer raw PII 출력",
    ],
    "embedding_llm_adjudicator": EMBEDDING_LLM_ADJUDICATOR_INTERFACE,   # No-Go for merge(이번 턴 호출 0).
}

# block_reason → next_action.
_NEXT_ACTION = {
    "no_packet": "cross-source 후보 0 — targeted same-event acquisition(source pair/topic/time window) 후 재시도",
    "insufficient_reviewer_capacity": (
        "reviewer roster < 2 — pair 당 2명 합의 불가. reviewer 충원 후 assignment 재생성"),
    "awaiting_labels": "batch pack(instruction/template/manifest)을 reviewer 에게 배포 → 실 human label 수집",
    "no_labels": "label 파일/행 없음 — packet 배포 후 reviewer label(JSONL) 수집해 intake 로 재검증",
    "label_file_missing": "label_path 가 가리키는 파일이 없음 — intake_directory/expected_label_files 확인",
    "invalid_labels": "label schema 오류 — validation_command 의 errors 로 행 수정 후 재intake",
    "forbidden_field_in_label": "label 에 score/rationale/raw body/secret 누출 — 해당 필드 제거(reviewer-facing 만)",
    "model_label_rejected": "model/self/LLM label 은 gold 불가(human only) — reviewer_kind=human 사람 라벨만",
    "unknown_pair_id": "label 의 pair_id 가 packet 에 없음 — 배포된 batch packet 의 pair_id 만 라벨링",
    "no_production_labels": "label_source 가 production 아님(synthetic/test) — production gold 0 유지(경로 검증만)",
    "insufficient_gold_for_calibration": "production gold < live floor — 실 reviewer label 충원 필요",
    "merge_gate_not_ready": "MERGE_GATE(precision≥0.98·FPR≤0.01·hard_neg_fp=0·KO≥0.98) 미충족 — calibration 후 재평가",
}


# ── §6: reviewer instruction(구조적 + ADR#60 operating checklist 조합) ─────────────────────────────────
def build_reviewer_instruction() -> dict:
    """§6 reviewer instruction(같은-사건 4-라벨 기준·금지·권장). 모델 점수/rationale/predicted_status/숨은 rank 0."""
    return dict(REVIEWER_INSTRUCTION)


# ── §A: label template(reviewer 가 label 만 채우는 빈 worksheet·score/bucket/predicted 0) ──────────────
def build_label_template(queue: dict, *, dataset_source: str = SOURCE_LIVE) -> list[dict]:
    """packet rows → reviewer label template(REVIEWER_ALLOWED_KEYS 만). reviewer_id 는 pseudonym(raw PII 0).

    label/label_confidence/reviewed_at 은 reviewer fill 칸(빈 문자열). template 자체는 load_reviewer_labels 통과
    대상이 아니다(빈 label) — reviewer 가 채운 뒤 intake validation 으로 검증한다."""
    rows: list[dict] = []
    for r in queue.get("packet_rows") or []:
        row: dict[str, Any] = {
            "pair_id": r["pair_id"],
            "reviewer_id": pseudonymize_reviewer_id(r["reviewer_id"]),   # pseudonym only.
            "review_round": r["review_round"],
            "label": "",                  # reviewer fills (LABELER_LABELS).
            "label_confidence": "",       # reviewer fills (LABEL_CONFIDENCES).
            "reviewed_at": "",            # reviewer fills (ISO8601).
            "language": r["language"],
            "source_type_left": r["source_type_left"],
            "source_type_right": r["source_type_right"],
            "title_left": r["title_left"],
            "title_right": r["title_right"],
            "observed_at_left": r["observed_at_left"],
            "observed_at_right": r["observed_at_right"],
            "dataset_source": dataset_source,
        }
        if r.get("canonical_url_left"):
            row["canonical_url_left"] = r["canonical_url_left"]
        if r.get("canonical_url_right"):
            row["canonical_url_right"] = r["canonical_url_right"]
        rows.append(row)
    # 이중 방어: template 키가 allowlist 밖(score/predicted_status 등)이면 fail-loud.
    for row in rows:
        extra = set(row) - REVIEWER_ALLOWED_KEYS
        if extra:
            raise ValueError(f"label template leaks disallowed keys (forbidden field 차단): {sorted(extra)}")
    return rows


# ── §B/§7: assignment manifest(pair 당 ≥2 reviewer·pseudonym only·top-k + hard negative balance) ───────
def build_assignment_manifest(queue: dict, *, batch_id: str) -> dict:
    """packet 의 (pair, reviewer) 배정 → assignment manifest. reviewer_id 는 pseudonym only(raw PII commit 금지).

    reviewer 집합은 queue['packet_rows'] 의 배정에서 파생한다(reviewer override 는 queue build 단계에서 결정).
    capacity(distinct reviewer) < 2 → insufficient_reviewer_capacity(pair 당 2명 합의 불가). top-k positive 와
    hard negative 를 함께 포함(R-GoldSamplingBias). due_hint 는 optional(운영자 설정)."""
    packet_rows = queue.get("packet_rows") or []
    distinct_reviewers = sorted({r["reviewer_id"] for r in packet_rows})
    pseudonyms = {rid: pseudonymize_reviewer_id(rid) for rid in distinct_reviewers}
    assignments: list[dict] = []
    per_pair: dict[str, set] = {}
    for r in packet_rows:
        pid, rid = r["pair_id"], r["reviewer_id"]
        per_pair.setdefault(pid, set()).add(rid)
        ps = pseudonyms[rid]
        assignments.append({
            "assignment_id": f"{batch_id}__{pid}__{ps}",
            "batch_id": batch_id,
            "reviewer_pseudonym": ps,
            "pair_id": pid,
            "assignment_status": r.get("assignment_status", "assigned"),
            "due_hint_optional": None,
        })
    pairs = sorted(per_pair)
    dup_covered = sum(1 for p in pairs if len(per_pair[p]) >= DEFAULT_REVIEWERS_PER_PAIR)
    capacity = len(distinct_reviewers)
    capacity_status = "ok" if capacity >= DEFAULT_REVIEWERS_PER_PAIR else "insufficient_reviewer_capacity"
    hard_neg = (queue.get("hard_negative_discovery_count", 0)
                + queue.get("hard_negative_synthetic_count", 0))
    return {
        "batch_id": batch_id,
        "assignments": assignments,
        "assignments_count": len(assignments),
        "pairs_count": len(pairs),
        "reviewer_count_required": DEFAULT_REVIEWERS_PER_PAIR,
        "reviewer_count_assigned": capacity,
        "capacity_status": capacity_status,
        "duplicate_assignment_coverage": round(dup_covered / len(pairs), 4) if pairs else None,
        "duplicate_covered_pairs": dup_covered,
        "hard_negative_count": hard_neg,
        "top_k_candidate_count": queue.get("near_positive_count", 0),
        "pseudonymous_reviewers": sorted(pseudonyms.values()),
        "raw_reviewer_pii_committed": False,    # raw roster/매핑은 operator-local·commit 금지.
    }


# ── §C/§8: intake plan(directory / expected files / validation command) ───────────────────────────────
def build_intake_plan(batch_id: str, *, pseudonyms: list[str], intake_dir: Optional[str] = None) -> dict:
    """intake directory 구조·expected label filenames·validation command(운영자가 칠 명령) 정의.

    경로는 outputs/ 하위(commit 제외)다. reviewer 별 expected file = batch_id__<pseudonym>__labels.jsonl.
    `intake_dir` 미지정 시 canonical(`outputs/reviewer_batch/<batch_id>/intake`); 지정 시 그 경로로
    validation command/placement 를 정렬한다(게이트 스캔 경로와 단일 경로 수렴 — ADR#75 pilot batch freeze)."""
    intake_dir = intake_dir if intake_dir is not None else f"outputs/reviewer_batch/{batch_id}/intake"
    expected = [f"{batch_id}__{ps}__labels.jsonl" for ps in sorted(pseudonyms)]
    validation_command = (
        ".\\.venv\\Scripts\\python.exe -m backend.app.tools.reviewer_batch_launch "
        f"--validate {intake_dir} --batch-id {batch_id}")
    return {
        "intake_directory": intake_dir,
        "expected_label_files": expected,
        "validation_command": validation_command,
    }


# ── §C/§8: label vocabulary 정규화 + intake validation(import 前 dry-run) ──────────────────────────────
def normalize_label(raw: str) -> str:
    """labeler 어휘(same_event/different_event/unsure/needs_review) → canonical GOLD_LABELS. 미지 라벨은 거부."""
    if raw not in _LABELER_TO_GOLD:
        raise ValueError(f"invalid labeler label {raw!r} (allowed: {sorted(LABELER_LABELS)})")
    return _LABELER_TO_GOLD[raw]


def validate_label_intake(
    rows: list[dict], *, known_pair_ids: Optional[set] = None,
    label_source: str = LABEL_SOURCE_SYNTHETIC,
) -> dict:
    """label rows → §8 intake dry-run report(import 前 검증). forbidden field/malformed/label_source/
    reviewer_kind/pair_id/duplicate 를 검사하고 통과 행은 canonical label 로 정규화한다(파일 미작성).

    frozen 계약 재사용: allowlist=REVIEWER_ALLOWED_KEYS·label∈LABELER_LABELS·enum(LANGUAGES/SOURCE_TYPES/
    LABEL_CONFIDENCES)·reviewer_kind=human·title≤512. 어떤 행도 model/self label 이면 거부(gold 불가)."""
    if label_source not in LABEL_SOURCES:
        raise ValueError(f"invalid label_source {label_source!r} (allowed: {sorted(LABEL_SOURCES)})")
    errors: list[dict] = []
    normalized: list[dict] = []
    seen: set[tuple] = set()
    per_pair: dict[str, int] = {}
    reviewer_ids: set[str] = set()
    forbidden_found: set[str] = set()
    unknown_pairs: set[str] = set()

    def _err(i: int, reason: str, **extra: Any) -> None:
        errors.append({"row": i, "reason": reason, **extra})

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            _err(i, "not_a_dict")
            continue
        keys = set(row)
        extra = keys - REVIEWER_ALLOWED_KEYS
        if extra:
            forb = extra & FORBIDDEN_LABEL_FIELDS
            forbidden_found |= forb
            _err(i, "forbidden_field" if forb else "disallowed_keys", keys=sorted(extra))
            continue
        missing = _INTAKE_REQUIRED_KEYS - keys
        if missing:
            _err(i, "missing_keys", keys=sorted(missing))
            continue
        rk = row.get("reviewer_kind", REVIEWER_HUMAN)
        if rk in _MODEL_KINDS:
            _err(i, "model_label_rejected", reviewer_kind=rk)
            continue
        if rk != REVIEWER_HUMAN:
            _err(i, "invalid_reviewer_kind", reviewer_kind=rk)
            continue
        if not isinstance(row["reviewer_id"], str) or not row["reviewer_id"].strip():
            _err(i, "invalid_reviewer_id")
            continue
        pid = row["pair_id"]
        if known_pair_ids is not None and pid not in known_pair_ids:
            unknown_pairs.add(pid)
            _err(i, "unknown_pair_id", pair_id=pid)
            continue
        if row["label"] not in LABELER_LABELS:
            _err(i, "invalid_label", label=row["label"])
            continue
        if row["label_confidence"] not in LABEL_CONFIDENCES:
            _err(i, "invalid_label_confidence", label_confidence=row["label_confidence"])
            continue
        if row["language"] not in LANGUAGES:
            _err(i, "invalid_language", language=row["language"])
            continue
        if row["source_type_left"] not in SOURCE_TYPES or row["source_type_right"] not in SOURCE_TYPES:
            _err(i, "invalid_source_type")
            continue
        if any(not isinstance(row[s], str) or len(row[s]) > _MAX_TITLE_LEN
               for s in ("title_left", "title_right")):
            _err(i, "invalid_title")
            continue
        # frozen `_validate_reviewer_row` 와 동등성 유지(in-memory 구성이 검사를 빠뜨리지 않게):
        # reviewed_at(ISO8601)·dataset_source∈DATASET_SOURCES·risk_tags=list[str] (adversarial B-2).
        try:
            _validate_reviewed_at(row["reviewed_at"])
        except ValueError:
            _err(i, "invalid_reviewed_at")
            continue
        if row.get("dataset_source", SOURCE_LIVE) not in DATASET_SOURCES:
            _err(i, "invalid_dataset_source", dataset_source=row.get("dataset_source"))
            continue
        rt = row.get("risk_tags", [])
        if not isinstance(rt, list) or any(not isinstance(t, str) for t in rt):
            _err(i, "invalid_risk_tags")
            continue
        rnd = row["review_round"]
        if not isinstance(rnd, int) or isinstance(rnd, bool) or rnd < 1:
            _err(i, "invalid_review_round", review_round=rnd)
            continue
        # duplicate key 의 reviewer_id 는 pseudonym 으로(raw PII 미노출·adversarial B-3).
        key = (pid, row["reviewer_id"], rnd)
        if key in seen:
            _err(i, "duplicate_label", key=[pid, pseudonymize_reviewer_id(row["reviewer_id"]), rnd])
            continue
        seen.add(key)
        reviewer_ids.add(row["reviewer_id"])
        per_pair[pid] = per_pair.get(pid, 0) + 1
        norm = dict(row)
        norm["label"] = normalize_label(row["label"])
        normalized.append(norm)

    schema_valid = not errors
    return {
        "label_count": len(rows),
        "valid_label_count": len(normalized),
        "reviewer_count": len(reviewer_ids),
        "per_pair_reviewer_count": dict(sorted(per_pair.items())),
        "multi_reviewer_pairs": sum(1 for c in per_pair.values() if c >= DEFAULT_REVIEWERS_PER_PAIR),
        "forbidden_fields_found": sorted(forbidden_found),
        "unknown_pair_ids": sorted(unknown_pairs),
        "errors": errors,
        "schema_valid": schema_valid,
        "label_source": label_source,
        # 통과 행만(정규화 완료). schema invalid 면 빈 리스트(부분 import 금지).
        "normalized_rows": normalized if schema_valid else [],
    }


def _rows_to_labels(rows: list[dict]) -> list[ReviewerLabel]:
    """검증·정규화된 intake row → ReviewerLabel(in-memory). reviewer_kind=human 기본(model 은 intake 에서 이미 거부)."""
    out: list[ReviewerLabel] = []
    for row in rows:
        out.append(ReviewerLabel(
            pair_id=row["pair_id"], reviewer_id=row["reviewer_id"], review_round=row["review_round"],
            label=row["label"], label_confidence=row["label_confidence"], reviewed_at=row["reviewed_at"],
            language=row["language"], source_type_left=row["source_type_left"],
            source_type_right=row["source_type_right"], title_left=row["title_left"],
            title_right=row["title_right"], observed_at_left=row["observed_at_left"],
            observed_at_right=row["observed_at_right"], reviewer_kind=row.get("reviewer_kind", REVIEWER_HUMAN),
            canonical_url_left=row.get("canonical_url_left"), canonical_url_right=row.get("canonical_url_right"),
            rationale=row.get("rationale"), risk_tags=tuple(row.get("risk_tags", [])),
            dataset_source=row.get("dataset_source", SOURCE_LIVE)))
    return out


def _read_jsonl(path: Any) -> list[dict]:
    """label JSONL → list[dict](주석/빈 줄 무시). 행 JSON 오류는 fail-loud."""
    rows: list[dict] = []
    text = Path(path).read_text(encoding="utf-8")
    for ln, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except ValueError as exc:
            raise ValueError(f"label line {ln} invalid JSON: {exc}") from exc
    return rows


def _public_intake_report(report: Optional[dict]) -> Optional[dict]:
    """intake report 의 공개용 사본 — raw 행(reviewer_id/rationale 자유텍스트 보존)인 `normalized_rows` 제거.

    `normalized_rows` 는 `_rows_to_labels` 내부 소비용(raw reviewer_id 필요·agreement 집계)이라 report 에는 보존하되,
    노출 표면(run output·CLI --json)에는 싣지 않는다(raw PII 미노출·adversarial B-3)."""
    if report is None:
        return None
    return {k: v for k, v in report.items() if k != "normalized_rows"}


def _normalize_adjudications(adjudications: Optional[dict]) -> Optional[dict]:
    """adjudication 의 label 도 labeler vocab→canonical 정규화(reviewer row 와 대칭). 사람 lead 가 unsure/
    needs_review 로 판정해도 frozen `_validate_adjudication`(GOLD_LABELS only) 크래시 없이 처리(code-review CR-1).

    canonical 토큰은 `_LABELER_TO_GOLD.get(lab, lab)` 가 그대로 통과(passthrough)."""
    if not adjudications:
        return adjudications
    out: dict[str, Any] = {}
    for pid, entry in adjudications.items():
        if isinstance(entry, dict) and "label" in entry:
            e = dict(entry)
            e["label"] = _LABELER_TO_GOLD.get(entry["label"], entry["label"])
            out[pid] = e
        else:
            out[pid] = entry
    return out


# ── §4: 통합 batch launch entrypoint ──────────────────────────────────────────────────────────────────
def run_reviewer_batch_launch(
    *, queue: Optional[dict] = None, discovery: Optional[dict] = None,
    batch_id: str = "reviewer_batch_001", packet_id: str = "reviewer_batch_pkt",
    reviewers: Optional[list[str]] = None, label_path: Optional[Any] = None,
    label_rows: Optional[list[dict]] = None, label_source: str = LABEL_SOURCE_SYNTHETIC,
    dataset_source: str = SOURCE_LIVE, adjudications: Optional[dict] = None,
    include_synthetic_hard_negatives: bool = False, top_k_sourced: bool = True,
) -> dict:
    """scored reviewer queue → batch launch pack + intake validation(병합 0·LLM 0·embedding 0·DB 0).

    queue(=build_near_match_reviewer_queue 출력) 또는 discovery 로 build. label_rows(in-memory) 또는 label_path
    (파일)로 라벨 intake — 둘 다 없으면 awaiting_labels(정직). production gold 는 label_source==production &
    live_derived 일 때만 카운트. 어떤 경로도 merge/LLM/embedding/DB 를 건드리지 않는다."""
    if label_source not in LABEL_SOURCES:
        raise ValueError(f"invalid label_source {label_source!r}")
    if queue is None and discovery is not None:
        queue = build_near_match_reviewer_queue(
            discovery, packet_id=packet_id, reviewers=reviewers,
            include_synthetic_hard_negatives=include_synthetic_hard_negatives)
    queue = queue or {}
    block_reasons: list[str] = []

    # 1) packet export(reuse ADR#66 — labeler-facing score-free·leaked 재검사).
    export = export_reviewer_packet(queue)
    packet_exported = export["packet_exportable"]
    if not packet_exported:
        block_reasons.append("no_packet")

    # 2) launch pack artifacts.
    instruction = build_reviewer_instruction()
    template = build_label_template(queue, dataset_source=dataset_source)
    manifest = build_assignment_manifest(queue, batch_id=batch_id)
    intake_plan = build_intake_plan(batch_id, pseudonyms=manifest["pseudonymous_reviewers"])
    # ADR#60 operating checklist(구조적 hidden_prediction/raw_body absent verify)는 packet 있을 때만.
    checklist = (build_reviewer_operating_checklist(queue, dataset_source=dataset_source, packet_id=packet_id)
                 if packet_exported else {})
    if manifest["capacity_status"] != "ok":
        block_reasons.append("insufficient_reviewer_capacity")

    # 3) intake(label rows/file → dry-run validation → 통과 시 resolution).
    known_pair_ids = set(queue.get("queue_pair_ids") or [])
    raw_rows: Optional[list[dict]] = None
    label_file_present = False
    if label_rows is not None:
        raw_rows = list(label_rows)
    elif label_path is not None:
        p = Path(label_path)
        if not p.exists():
            block_reasons.append("label_file_missing")
        else:
            label_file_present = True
            raw_rows = _read_jsonl(p)

    label_import_attempted = (label_rows is not None) or (label_path is not None)
    intake_report: Optional[dict] = None
    # gold/calibration 기본값(라벨 없음/무효 → 0/False·None — 정직).
    production_gold_count = synthetic_gold_count = conflict_count = non_decisive_gold_count = 0
    calibration_ready = merge_gate_ready = False
    agreement_rate: Optional[float] = None
    if raw_rows is None:
        intake_status = INTAKE_AWAITING
        if "label_file_missing" not in block_reasons:
            block_reasons.append("awaiting_labels")
    else:
        intake_report = validate_label_intake(
            raw_rows, known_pair_ids=known_pair_ids, label_source=label_source)
        if not intake_report["schema_valid"]:
            intake_status = INTAKE_INVALID
            block_reasons.append("invalid_labels")
            reasons = {e["reason"] for e in intake_report["errors"]}
            for br in ("forbidden_field", "model_label_rejected", "unknown_pair_id"):
                if br in reasons:
                    block_reasons.append("forbidden_field_in_label" if br == "forbidden_field" else br)
        elif not intake_report["normalized_rows"]:
            intake_status = INTAKE_PRESENT       # 파일은 있으나 유효 라벨 0(빈 파일).
            block_reasons.append("no_labels")
        else:
            # ADR#66 building block 직접 재사용(resolve + calibration). run_ 을 거치지 않아 packet 재export 없음.
            labels = _rows_to_labels(intake_report["normalized_rows"])
            resolve = resolve_label_operations(
                labels, adjudications=_normalize_adjudications(adjudications), label_source=label_source)
            # **decisive gold = same/different 만**. unsure→insufficient·needs_review→ambiguous 는 resolved 이지만
            # gold 아님(§6 "unsure/needs_review only → not gold"·gold 부풀리기 금지).
            prod_decisive = [g for g in resolve["production_gold"]
                             if g.label in (LABEL_SAME, LABEL_DIFFERENT)]
            syn_decisive = [g for g in resolve["synthetic_gold"]
                            if g.label in (LABEL_SAME, LABEL_DIFFERENT)]
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
            calibration_ready = preflight["calibration_ready"]
            merge_gate_ready = preflight["merge_gate_ready"]
            intake_status = INTAKE_IMPORTED
            if label_source != LABEL_SOURCE_PRODUCTION:
                block_reasons.append("no_production_labels")
            if production_gold_count < GOLD_MERGE_MIN_LIVE_GOLD:
                block_reasons.append("insufficient_gold_for_calibration")
            if not merge_gate_ready:
                block_reasons.append("merge_gate_not_ready")

    lang_dist: dict[str, int] = {}
    for r in template:
        lang_dist[r["language"]] = lang_dist.get(r["language"], 0) + 1

    next_actions = [_NEXT_ACTION.get(br, f"investigate: {br}")
                    for br in dict.fromkeys(block_reasons)]

    return {
        "operation_name": OPERATION_NAME,
        "batch_id": batch_id,
        "packet_id": packet_id,
        "packet_source": "near_match_reviewer_queue(semantic scorer top-k)" if top_k_sourced else "discovery",
        "packet_exported": packet_exported,
        "label_template_exported": bool(template),
        "assignment_manifest_exported": bool(manifest["assignments"]),
        "reviewer_instruction_exported": True,
        "intake_directory": intake_plan["intake_directory"],
        "expected_label_files": intake_plan["expected_label_files"],
        "validation_command": intake_plan["validation_command"],
        "label_import_attempted": label_import_attempted,
        "label_file_present": label_file_present,
        "intake_status": intake_status,
        "reviewer_count_required": manifest["reviewer_count_required"],
        "reviewer_count_assigned": manifest["reviewer_count_assigned"],
        "pairs_count": manifest["pairs_count"],
        "assignments_count": manifest["assignments_count"],
        "duplicate_assignment_coverage": manifest["duplicate_assignment_coverage"],
        "hard_negative_count": manifest["hard_negative_count"],
        "top_k_candidate_count": manifest["top_k_candidate_count"],
        "language_distribution": dict(sorted(lang_dist.items())),
        "korean_calibration_target": GOLD_MERGE_MIN_KOREAN_GOLD,
        # labeler-facing secrecy(ADR#66 export 구조 검증 — 하드코딩 아닌 leaked 재검사 통과).
        "score_hidden_from_labeler": export["score_hidden_from_labeler"],
        "rationale_hidden_from_labeler": export["rationale_hidden_from_labeler"],
        "predicted_status_hidden": export["labeler_prediction_hidden"],
        "raw_body_absent": export["raw_body_absent"],
        "secret_absent": export["secret_absent"],
        "production_gold_count": production_gold_count,
        "synthetic_gold_count": synthetic_gold_count,
        "non_decisive_gold_count": non_decisive_gold_count,   # unanimous ambiguous/insufficient(gold 아님·정직).
        # production_gold_count 무결성은 **선언 기반**(label_source/dataset_source 평문 태그·provenance 미검증)
        # — 실 live provenance 바인딩(R-IdentityHumanLabeling) 전까지 readiness 근거로 인용 금지(adversarial B-1).
        "production_gold_provenance_verified": False,
        "conflict_count": conflict_count,
        "agreement_rate": agreement_rate,
        "calibration_ready": calibration_ready,
        "merge_gate_ready": merge_gate_ready,
        "merge_allowed": False,
        "no_merge_without_gold": True,
        "no_public_intelligence_unit": True,
        "db_write": False,
        "llm_invoked": False,
        "embedding_invoked": False,
        "reviewer_instruction": instruction,
        "assignment_manifest": manifest,
        "operating_checklist": checklist,
        "intake_report": _public_intake_report(intake_report),   # raw 행 제거(PII·adversarial B-3).
        "agent_contract": BATCH_LAUNCH_AGENT_CONTRACT,
        "block_reasons": list(dict.fromkeys(block_reasons)),
        "next_actions": next_actions,
    }


# ── CLI(기본 captured fixture·network 0·DB 0·라벨 없음=awaiting_labels 정직; synthetic 라벨 데모 opt-in) ──
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
        description="reviewer batch launch pack + intake validation loop (ADR#67·병합 0·LLM 0·DB 0).")
    parser.add_argument("--validate", metavar="INTAKE_DIR",
                        help="intake_directory 의 label 파일을 dry-run 검증(import 前).")
    parser.add_argument("--batch-id", default="reviewer_batch_cli", help="batch id.")
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
        disc, packet_id="reviewer_batch_cli",
        include_synthetic_hard_negatives=ns.synthetic_hard_negatives)

    # --validate: intake_directory 의 expected label 파일들을 모아 dry-run 검증.
    # 독립 --validate 는 **schema-only**(known_pair_ids=None) — pair_id membership 는 batch 의 queue 를 아는
    # `run_reviewer_batch_launch(label_path=…)` full run 에서 검증(fixture pair_id 하드와이어 회피·CR-2).
    if ns.validate:
        rows: list[dict] = []
        vdir = Path(ns.validate)
        if vdir.exists():
            for fp in sorted(vdir.glob("*.jsonl")):
                rows.extend(_read_jsonl(fp))
        report = validate_label_intake(rows, known_pair_ids=None, label_source=LABEL_SOURCE_SYNTHETIC)
        public = _public_intake_report(report)
        if ns.json:
            print(json.dumps(public, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"- intake validate dir={ns.validate} batch_id={ns.batch_id} "
                  f"files={'present' if vdir.exists() else 'missing'} (schema-only·pair_id 는 full run 에서)")
            print(f"- labels={report['label_count']} valid={report['valid_label_count']} "
                  f"reviewers={report['reviewer_count']} schema_valid={report['schema_valid']}")
            print(f"- forbidden_fields={report['forbidden_fields_found']} errors={len(report['errors'])}")
        return 0

    labels = _demo_synthetic_label_rows(queue) if ns.synthetic_labels else None
    out = run_reviewer_batch_launch(
        queue=queue, batch_id=ns.batch_id, packet_id="reviewer_batch_cli",
        label_rows=labels, label_source=LABEL_SOURCE_SYNTHETIC,
        dataset_source=SOURCE_SYNTHETIC, top_k_sourced=False)

    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} batch_id={out['batch_id']} "
          f"packet_exported={out['packet_exported']}")
    print(f"- pack: instruction={out['reviewer_instruction_exported']} template={out['label_template_exported']} "
          f"manifest={out['assignment_manifest_exported']}")
    print(f"- assignment: pairs={out['pairs_count']} assignments={out['assignments_count']} "
          f"reviewers={out['reviewer_count_assigned']}/{out['reviewer_count_required']} "
          f"dup_coverage={out['duplicate_assignment_coverage']} capacity={out['assignment_manifest']['capacity_status']}")
    print(f"- intake: status={out['intake_status']} import_attempted={out['label_import_attempted']} "
          f"hard_neg={out['hard_negative_count']} top_k={out['top_k_candidate_count']}")
    print(f"- gold: production={out['production_gold_count']} synthetic={out['synthetic_gold_count']} "
          f"conflict={out['conflict_count']} calibration_ready={out['calibration_ready']} "
          f"merge_gate_ready={out['merge_gate_ready']}")
    print(f"- gates: merge_allowed={out['merge_allowed']} db_write={out['db_write']} "
          f"llm_invoked={out['llm_invoked']} embedding_invoked={out['embedding_invoked']}")
    print(f"- intake_dir: {out['intake_directory']}")
    print(f"- validation_command: {out['validation_command']}")
    print(f"- block_reasons: {out['block_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
