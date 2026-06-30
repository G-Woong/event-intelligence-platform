"""ADR#88 — official×news label intake readiness (synthetic dry-run · NO fabricated gold · production gold 0).

목표(§12): 라벨을 **날조하지 않으면서** 미래에 reviewer 가 돌려줄 official×news returned-label schema 가 수용
가능한지 확인한다. 두 축:
  1. **gold-bearing core schema 수용 증명**: synthetic official×news fixture(source_type official/article·
     dataset_source=synthetic·marked_synthetic)를 기존 `run_production_label_intake`(label_source=synthetic)에 태워
     schema 가 official×news 행을 수용하는지(schema_valid) 확인하되 **production_gold_count 는 0** 으로 유지한다
     (synthetic ≠ production·단일 reviewer ≠ gold·unsure ≠ gold).
  2. **§12 returned-label annotation schema 검증**: batch_id·pair_id·label·reviewer_id_or_anonymous_code +
     optional(evidence_notes·role_confusion_flag·uncertain_flag)을 `validate_official_news_label_record` 로 검증.
     annotation 필드는 gold-bearing core schema 와 분리(점수 아님·gold 오염 0).

절대 불변(상속·상용 안전 계약):
  - **synthetic ≠ production gold**: fixture 는 marked_synthetic·label_source=synthetic — production_gold_count 0 유지
    (R-SyntheticLabelFixtureLeakage·실 returned label 전까지 0).
  - **single reviewer ≠ gold · unsure/needs_review ≠ gold**: dry-run 으로 그 규칙을 *증명* 한다(둔갑 0).
  - **label 날조 0**: 실 reviewer label 을 만들지 않는다(synthetic fixture 만·production 경로 미오염).
  - **merge 0 · LLM/embedding 0 · DB 0 · 전송 0 · secret 0 · raw body 0 · score 0**.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Callable, Optional

from backend.app.services.identity_human_labeling import SOURCE_SYNTHETIC
from backend.app.tools.production_label_intake import run_production_label_intake
from backend.app.tools.reviewer_batch_launch import LABELER_LABELS
from backend.app.tools.reviewer_label_operations import LABEL_SOURCE_SYNTHETIC
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "official_news_label_intake_readiness"

LABEL_INTAKE_READINESS_READY = "official_news_label_intake_dry_run_ready"
LABEL_INTAKE_READINESS_SCHEMA_INVALID = "official_news_label_schema_invalid"

# §12 accepted returned-label 어휘 — 단일 출처(LABELER_LABELS) + §12 alias(needs_more_context→needs_review).
_NEEDS_MORE_CONTEXT = "needs_more_context"
_ACCEPTED_RETURNED_LABELS = frozenset(LABELER_LABELS) | {_NEEDS_MORE_CONTEXT}
_LABEL_ALIAS = {_NEEDS_MORE_CONTEXT: "needs_review"}

# §12 returned-label minimal record 필드(annotation layer·gold-bearing core 와 분리).
_RECORD_REQUIRED_FIELDS = ("batch_id", "pair_id", "label", "reviewer_id_or_anonymous_code")
_RECORD_OPTIONAL_FIELDS = ("evidence_notes", "role_confusion_flag", "uncertain_flag")
# annotation record 에 절대 실리면 안 되는 필드(점수/판정 누출 방어 — _assert_pii_safe 와 별개의 record-level 검사).
_RECORD_FORBIDDEN_FIELDS = frozenset({
    "score", "model_score", "rationale", "predicted_status", "raw_body", "body", "secret", "same_event_truth",
})


def canonical_returned_label(label: str) -> str:
    """§12 alias(needs_more_context)를 canonical(needs_review)로 정규화. 그 외는 passthrough."""
    return _LABEL_ALIAS.get(label, label)


def validate_official_news_label_record(record: dict) -> dict:
    """§12 official×news returned-label minimal record 검증(annotation layer·gold 미부여·점수 누출 차단).

    required: batch_id·pair_id·label(∈accepted)·reviewer_id_or_anonymous_code. optional: evidence_notes(str)·
    role_confusion_flag(bool)·uncertain_flag(bool). score/rationale/predicted_status/raw body/same_event truth 누출
    시 reject. 단일 record 검증일 뿐 gold 가 아니다(production_gold_count 미증가)."""
    reasons: list[str] = []
    if not isinstance(record, dict):
        return {"valid": False, "rejection_reasons": ["not_a_dict"], "canonical_label": None}

    for f in _RECORD_REQUIRED_FIELDS:
        if not str(record.get(f) or "").strip():
            reasons.append(f"missing_{f}")
    label = str(record.get("label") or "").strip()
    if label and label not in _ACCEPTED_RETURNED_LABELS:
        reasons.append("invalid_label")
    # optional 필드 타입 검사(있을 때만).
    if "evidence_notes" in record and not isinstance(record["evidence_notes"], str):
        reasons.append("invalid_evidence_notes")
    if "role_confusion_flag" in record and not isinstance(record["role_confusion_flag"], bool):
        reasons.append("invalid_role_confusion_flag")
    if "uncertain_flag" in record and not isinstance(record["uncertain_flag"], bool):
        reasons.append("invalid_uncertain_flag")
    # forbidden 필드(점수/판정/raw body/same_event truth) 누출 차단.
    leaked = sorted(set(record) & _RECORD_FORBIDDEN_FIELDS)
    if leaked:
        reasons.append("forbidden_field")
    # 허용된 키 외 미지 키는 경고하지 않되(유연), forbidden 만 차단(annotation layer 는 reviewer-facing).
    valid = not reasons
    return {
        "valid": valid,
        "rejection_reasons": reasons,
        "canonical_label": canonical_returned_label(label) if (valid and label) else None,
        "is_gold": False,   # 단일 record 는 절대 gold 아님(consensus 필요).
    }


def _synthetic_official_news_queue(pair_ids: list[str], reviewers: list[str]) -> dict:
    """synthetic official×news queue(source_type official/article) — run_production_label_intake 의 pair_id membership
    검증을 통과시키는 최소 queue. packet_rows 는 assignment manifest 용(pair_id/reviewer_id)."""
    packet_rows: list[dict] = []
    for pid in pair_ids:
        for rid in reviewers:
            packet_rows.append({
                "pair_id": pid, "reviewer_id": rid, "review_round": 1, "language": "en",
                "source_type_left": "official", "source_type_right": "article",
                "title_left": "EPA final rule on greenhouse gas emissions standards",
                "title_right": "EPA tightens emissions rule; industry and states react",
                "observed_at_left": "2026-06-25", "observed_at_right": "2026-06-25",
            })
    return {
        "queue_pair_ids": list(pair_ids),
        "packet_rows": packet_rows,
        "near_positive_count": len(pair_ids),
        "hard_negative_discovery_count": 0,
        "hard_negative_synthetic_count": 0,
    }


def build_synthetic_official_news_label_fixture(
    pair_id: str, reviewers: list[str], label: str = "same_event",
) -> list[dict]:
    """synthetic official×news label rows(full reviewer schema·source_type official/article·dataset_source=synthetic).

    marked_synthetic = dataset_source==SOURCE_SYNTHETIC(production gold denominator 에서 구조적 배제). 실 reviewer
    label 이 아니다(경로 검증 전용)."""
    return [
        {
            "pair_id": pair_id, "reviewer_id": rid, "review_round": 1, "label": label,
            "label_confidence": "medium", "reviewed_at": "2026-06-26T00:00:00+00:00", "language": "en",
            "source_type_left": "official", "source_type_right": "article",
            "title_left": "EPA final rule on greenhouse gas emissions standards",
            "title_right": "EPA tightens emissions rule; industry and states react",
            "observed_at_left": "2026-06-25", "observed_at_right": "2026-06-25",
            "dataset_source": SOURCE_SYNTHETIC,
        }
        for rid in reviewers
    ]


def _intake(
    *, pair_id: str, reviewers: list[str], label: str, intake_fn: Callable[..., dict], batch_id: str,
) -> dict:
    """synthetic official×news fixture → run_production_label_intake(label_source=synthetic). production gold 0 검증용."""
    queue = _synthetic_official_news_queue([pair_id], reviewers)
    rows = build_synthetic_official_news_label_fixture(pair_id, reviewers, label=label)
    return intake_fn(
        queue=queue, batch_id=batch_id, packet_id=f"{batch_id}_pkt", label_rows=rows,
        label_source=LABEL_SOURCE_SYNTHETIC, top_k_sourced=False)


def run_official_news_label_intake_readiness(
    *, intake_fn: Optional[Callable[..., dict]] = None, batch_id: str = "official_news_label_dryrun",
) -> dict:
    """§12 official×news label intake readiness dry-run(synthetic·production gold 0·single/unsure ≠ gold 증명).

    3 sub-scenario 를 synthetic 으로 태워 schema 수용 + gold 규칙을 증명한다:
      · multi_unanimous(2 reviewer 만장일치 same_event) → schema_valid·synthetic_gold>0·production_gold 0.
      · single_reviewer(1 reviewer) → gold 아님(production·synthetic 모두 0).
      · unsure(2 reviewer unsure) → non_decisive·gold 0.
    label 날조 0(synthetic fixture 만). annotation record(§12) 도 검증한다."""
    intake_fn = intake_fn or run_production_label_intake

    multi = _intake(pair_id="oxn_0001", reviewers=["reviewer_a", "reviewer_b"], label="same_event",
                    intake_fn=intake_fn, batch_id=batch_id)
    single = _intake(pair_id="oxn_0002", reviewers=["reviewer_a"], label="same_event",
                     intake_fn=intake_fn, batch_id=batch_id + "_single")
    unsure = _intake(pair_id="oxn_0003", reviewers=["reviewer_a", "reviewer_b"], label="unsure",
                     intake_fn=intake_fn, batch_id=batch_id + "_unsure")

    # schema 수용 = multi intake_report(공개본)의 schema_valid. intake_report 부재면 **fail-closed False**(True default
    # vacuous-pass 제거·code-review NIT). label_rows 를 항상 넘기므로 정상 경로에서 intake_report 는 항상 dict.
    schema_valid = bool((multi.get("intake_report") or {}).get("schema_valid"))

    production_gold_count = int(multi.get("production_gold_count") or 0)
    synthetic_gold_count = int(multi.get("synthetic_gold_count") or 0)
    single_reviewer_not_gold = (
        int(single.get("production_gold_count") or 0) == 0 and int(single.get("synthetic_gold_count") or 0) == 0)
    unsure_not_gold = int(unsure.get("production_gold_count") or 0) == 0

    # §12 annotation record 검증(accepted·invalid·role_confusion·forbidden).
    sample_records = [
        {"batch_id": batch_id, "pair_id": "oxn_0001", "label": "same_event",
         "reviewer_id_or_anonymous_code": "rv_a", "evidence_notes": "same dated EPA action",
         "role_confusion_flag": False, "uncertain_flag": False},
        {"batch_id": batch_id, "pair_id": "oxn_0001", "label": _NEEDS_MORE_CONTEXT,
         "reviewer_id_or_anonymous_code": "rv_b", "role_confusion_flag": True},
    ]
    record_validations = [validate_official_news_label_record(r) for r in sample_records]
    annotation_schema_valid = all(v["valid"] for v in record_validations)

    status = (LABEL_INTAKE_READINESS_READY if (schema_valid and annotation_schema_valid)
              else LABEL_INTAKE_READINESS_SCHEMA_INVALID)

    out = {
        "operation_name": OPERATION_NAME,
        "label_intake_readiness_status": status,
        "schema_accepts_official_news": schema_valid,
        "marked_synthetic": True,
        "not_production_gold": True,
        "actual_label_fabricated": False,   # synthetic fixture 만·실 reviewer label 0.
        "production_gold_count": production_gold_count,        # 0(synthetic).
        "synthetic_gold_count": synthetic_gold_count,
        "single_reviewer_not_gold": single_reviewer_not_gold,
        "unsure_not_gold": unsure_not_gold,
        "accepted_labels": sorted(_ACCEPTED_RETURNED_LABELS),
        "optional_annotation_fields": list(_RECORD_OPTIONAL_FIELDS),
        "annotation_records_validated": len(record_validations),
        "annotation_schema_valid": annotation_schema_valid,
        "multi_intake_status": multi.get("intake_status"),
        # ── 불변 경계(정직·constant) ──
        "production_gold_provenance_verified": False,
        "merge_allowed": False,
        "actual_sending_performed": False,
        "r2_r7_no_go": True,
        "blocked_reason": "" if status == LABEL_INTAKE_READINESS_READY else "official_news_label_schema_invalid",
        "next_action": (
            "official×news returned-label schema is acceptable (synthetic dry-run) — production gold stays 0 until "
            "real reviewers return labels and agreement criteria are met"
            if status == LABEL_INTAKE_READINESS_READY
            else "fix the official×news label schema before accepting returned labels"),
    }
    _assert_pii_safe(out, _path="official_news_label_intake_readiness_output")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#88 official×news label intake readiness dry-run (synthetic·production gold 0·single/unsure "
                     "≠ gold·label 날조 0·merge 0·LLM 0·DB 0)."))
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = run_official_news_label_intake_readiness()
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} status={out['label_intake_readiness_status']}")
    print(f"- schema_accepts_official_news={out['schema_accepts_official_news']} "
          f"marked_synthetic={out['marked_synthetic']} actual_label_fabricated={out['actual_label_fabricated']}")
    print(f"- gold: production={out['production_gold_count']} synthetic={out['synthetic_gold_count']} "
          f"single_reviewer_not_gold={out['single_reviewer_not_gold']} unsure_not_gold={out['unsure_not_gold']}")
    print(f"- accepted_labels={out['accepted_labels']}")
    print(f"- annotation: validated={out['annotation_records_validated']} schema_valid={out['annotation_schema_valid']} "
          f"optional={out['optional_annotation_fields']}")
    print(f"- gates: merge={out['merge_allowed']} provenance_verified={out['production_gold_provenance_verified']} "
          f"r2_r7_no_go={out['r2_r7_no_go']}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
