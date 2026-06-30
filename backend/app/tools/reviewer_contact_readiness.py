"""ADR#88 — reviewer contact readiness gate (freeze → contact-PRE readiness package · NO actual sending · merge 0).

ADR#84 reviewer_handoff_bridge 가 freeze→contact-PRE handoff package(label schema·expected files·validation
command·placement guide·operator checklist)를 조립했다. ADR#88 은 그 위에 **reviewer contact readiness gate** 를
얹는다 — freeze 가 성공했을 때만 operator 가 *실제 접촉 직전* 점검할 readiness package(official×news label
instruction·label schema·expected returned file names·validation command·placement guide·operator checklist·manual
contact steps)를 구성하고, **모든 hidden 보장(score/rationale/predicted_status/same_event truth/raw body/PII)을
구조적 플래그로 강제** 한다. 핵심: **readiness ≠ actual sending** — `actual_sending_performed=False` 불변(operator
가 수동 배포·시스템 자동 발송 0).

이 모듈은 freeze/handoff 를 **재계산하지 않는다** — handoff bridge 산출물을 contact-readiness 형태로 재패키징하고
official×news 전용 instruction 을 첨부할 뿐(단일 출처 보존).

절대 불변(상속·상용 안전 계약):
  - **no sending**: 어떤 채널로도 자동 발송 0(`actual_sending_performed=False`). reviewer 모집/접촉은 operator 수동.
  - **freeze ≠ truth ≠ gold**: readiness package 는 pre-contact worklist 이지 same_event 확정·production gold 가 아니다
    (production_gold_count 불변·R2~R7 No-Go).
  - **must not include**: reviewer roster·raw PII·actual email(미승인)·score·rationale·predicted_status·same_event
    truth·raw source body·secret. 출력은 `_assert_pii_safe`(정확명 forbidden-key 재귀 차단) 통과.
  test: handoff dict 주입 시 결정론(network 0).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.official_news_live_acquisition import (
    build_official_news_reviewer_instruction,
)
from backend.app.tools.reviewer_batch_launch import LABELER_LABELS
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "reviewer_contact_readiness"

CONTACT_READINESS_READY = "contact_readiness_ready"
CONTACT_READINESS_BLOCKED_NO_FREEZE = "blocked_no_production_candidate_freeze"

# §12 official×news returned label 의 optional annotation 필드(gold-bearing core schema 와 분리·점수 아님).
_OPTIONAL_ANNOTATION_FIELDS = ("evidence_notes", "role_confusion_flag", "uncertain_flag")

_MANUAL_CONTACT_STEPS = (
    "operator manually recruits/contacts >=2 pseudonymous reviewers per pair — the system performs NO sending",
    "operator distributes the official×news reviewer instruction (official=authoritative evidence, news=public "
    "reporting) and the label schema",
    "operator shares each frozen pair's title + canonical_url per side (no score / rationale / predicted_status / "
    "same_event truth / raw body)",
    "each reviewer returns one JSONL label file named per expected_returned_file_names into the intake_directory "
    "(gitignored under outputs/reviewer_batch/ — never committed)",
    "operator runs the validation_command before importing; production gold stays 0 until returned labels are "
    "validated and agreement criteria are met",
)


def build_official_news_label_schema(*, instruction: Optional[dict] = None) -> dict:
    """§11/§12 official×news returned label schema(reviewer 가 채울 구조·gold-bearing core + optional annotation 분리).

    accepted_labels 는 단일 출처(reviewer_batch_launch.LABELER_LABELS)에서 — same_event/different_event/unsure/
    needs_review. core 필드는 frozen reviewer schema 와 정렬되며 score/rationale/predicted_status 는 구조적으로 없다.
    role_fields(source_type_left/right)가 official×news 를 news×news 와 구분한다(official/article)."""
    instr = instruction or build_official_news_reviewer_instruction()
    vocab = instr.get("label_vocabulary") or sorted(LABELER_LABELS)
    return {
        "core_required_fields": [
            "pair_id", "reviewer_id_or_anonymous_code", "label", "label_confidence", "reviewed_at",
            "source_type_left", "source_type_right", "title_left", "title_right",
            "observed_at_left", "observed_at_right",
        ],
        "role_fields": ["source_type_left", "source_type_right"],   # official / article — official×news 구분.
        "accepted_labels": list(vocab),
        "optional_annotation_fields": list(_OPTIONAL_ANNOTATION_FIELDS),
        "forbidden_fields": "no score / rationale / predicted_status / raw source body / secret / reviewer PII",
        "file_format": "JSONL — one label per line, one file per pseudonymous reviewer",
        "gold_rule": "single reviewer != gold · unsure/needs_review != gold · production gold 0 until returned labels",
    }


def build_reviewer_contact_readiness(
    handoff: dict, *, official_news_instruction: Optional[dict] = None,
) -> dict:
    """reviewer_handoff_bridge 출력(handoff) → §11 contact readiness gate(freeze 성공 시 package·전송 0·hidden 강제).

    handoff = `build_reviewer_handoff_bridge` 출력. reviewer_handoff_ready(이미 batch_id·frozen pair fail-closed)일
    때만 contact-PRE readiness package 를 조립하고 hidden 플래그를 구조적으로 True; 아니면 reviewer_contact_ready=False
    + blocked_reason 표면화. 어떤 경우도 전송·merge·gold 증가 0(actual_sending_performed=False)."""
    ready = bool(handoff.get("reviewer_handoff_ready"))
    package = handoff.get("handoff_package") or {}
    instruction = official_news_instruction or build_official_news_reviewer_instruction()

    contact_package: Optional[dict] = None
    if ready:
        label_schema = build_official_news_label_schema(instruction=instruction)
        contact_package = {
            "batch_id": str(package.get("batch_id") or ""),
            "candidate_count": int(package.get("frozen_pair_count") or 0),
            "official_news_label_instructions": instruction,
            "label_schema": label_schema,
            "expected_returned_file_names": list(package.get("expected_label_files") or []),
            "validation_command": str(package.get("validation_command") or ""),
            "placement_guide": str(package.get("placement_guide") or ""),
            "operator_checklist": package.get("operator_launch_checklist"),
            "manual_contact_steps": list(_MANUAL_CONTACT_STEPS),
            "reviewers_per_pair_minimum": int(package.get("reviewers_per_pair_minimum") or 2),
        }
        status = CONTACT_READINESS_READY
        blocked_reason = ""
        next_action = (
            "operator: manually distribute the official×news reviewer worklist to >=2 pseudonymous reviewers per "
            "pair and collect returned label JSONL (no system sending); production gold stays 0 until import")
    else:
        status = CONTACT_READINESS_BLOCKED_NO_FREEZE
        blocked_reason = str(handoff.get("blocked_reason") or CONTACT_READINESS_BLOCKED_NO_FREEZE)
        next_action = (
            "resolve the candidate blocker before reviewer contact — no live-derived production-candidate batch was "
            "frozen, so there is no official×news worklist to hand off yet")

    result = {
        "operation_name": OPERATION_NAME,
        "reviewer_contact_readiness_status": status,
        "reviewer_contact_ready": ready,
        # §11 readiness sub-flags(freeze 없으면 전부 False).
        "instruction_ready": ready,
        "label_schema_ready": ready,
        "expected_label_files_ready": ready and bool(package.get("expected_label_files")),
        "validation_command_ready": ready and bool(package.get("validation_command")),
        "placement_guide_ready": ready and bool(package.get("placement_guide")),
        "operator_checklist_ready": ready and bool(package.get("operator_launch_checklist")),
        "contact_readiness_package": contact_package,
        "candidate_count": int(package.get("frozen_pair_count") or 0),
        "production_batch_id": str(package.get("batch_id") or "") if ready else "",
        # ── §11 hidden 보장(구조적·constant) + readiness ≠ sending ──
        "actual_sending_performed": False,
        "pii_safe": True,
        "score_hidden": True,
        "rationale_hidden": True,
        "predicted_status_hidden": True,
        "same_event_truth_hidden": True,
        "raw_body_hidden": True,
        "reviewer_roster_included": False,
        "actual_email_included": False,
        # ── 경계(정직·constant) ──
        "freeze_is_reviewer_worklist_only": True,
        "production_gold_count": int(handoff.get("production_gold_count") or 0),
        "current_r1_gap": int(handoff.get("current_r1_gap") or 0),
        "merge_allowed": False,
        "r2_r7_no_go": True,
        "blocked_reason": blocked_reason,
        "next_action": next_action,
    }
    # 전체 출력 재귀 forbidden-key 가드(score/rationale/predicted_status/raw PII/secret 어떤 depth 도 0·드리프트 fail-loud).
    _assert_pii_safe(result, _path="reviewer_contact_readiness_output")
    return result


def sanitized_contact_readiness(out: dict) -> dict:
    """snapshot/frontier 용 aggregate-only 투영(package 본문/instruction 제외·status/flag/count 만)."""
    return {
        "reviewer_contact_readiness_status": out["reviewer_contact_readiness_status"],
        "reviewer_contact_ready": out["reviewer_contact_ready"],
        "candidate_count": out["candidate_count"],
        "actual_sending_performed": out["actual_sending_performed"],
        "blocked_reason": out["blocked_reason"],
        "next_action": out["next_action"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#88 reviewer contact readiness gate (freeze → contact-PRE package; readiness ≠ actual "
                     "sending·전송 0·score/rationale/predicted_status/same_event/raw body/PII hidden·merge 0). "
                     "handoff bridge 출력 JSON 을 stdin/파일로 받아 readiness 를 산출."))
    parser.add_argument("--handoff-json", metavar="PATH", help="reviewer_handoff_bridge 출력 JSON(미지정 시 stdin).")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if ns.handoff_json:
        with open(ns.handoff_json, encoding="utf-8") as f:
            handoff = json.load(f)
    else:
        data = sys.stdin.read().strip()
        handoff = json.loads(data) if data else {}
    out = build_reviewer_contact_readiness(handoff or {})
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} status={out['reviewer_contact_readiness_status']}")
    print(f"- contact_ready={out['reviewer_contact_ready']} candidate_count={out['candidate_count']} "
          f"actual_sending={out['actual_sending_performed']}")
    print(f"- ready_flags: instruction={out['instruction_ready']} label_schema={out['label_schema_ready']} "
          f"expected_files={out['expected_label_files_ready']} validation={out['validation_command_ready']} "
          f"placement={out['placement_guide_ready']} checklist={out['operator_checklist_ready']}")
    print(f"- hidden: score={out['score_hidden']} rationale={out['rationale_hidden']} "
          f"predicted_status={out['predicted_status_hidden']} same_event_truth={out['same_event_truth_hidden']} "
          f"raw_body={out['raw_body_hidden']}")
    print(f"- r1: production_gold={out['production_gold_count']} gap={out['current_r1_gap']} "
          f"merge_allowed={out['merge_allowed']} r2_r7_no_go={out['r2_r7_no_go']}")
    print(f"- blocked_reason: {out['blocked_reason'] or '(none)'}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
