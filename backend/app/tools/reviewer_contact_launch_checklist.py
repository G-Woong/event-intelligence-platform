"""ADR#89 — reviewer contact launch checklist (freeze→수동 접촉 직전·actual sending 0·dropbox readiness 링크).

ADR#88 `reviewer_contact_readiness` 가 freeze→contact-PRE package(instruction·label schema·expected files·validation
command·placement guide·operator checklist·manual contact steps)를 조립했다. ADR#89 는 그 위에 **launch checklist**
를 얹는다 — contact readiness(freeze 성공)와 returned label dropbox readiness 를 **조합** 해 *실제 사람이 접촉을
실행하기 직전* 점검표를 만들고, launch_ready 를 freeze 기준으로 게이트한다. 핵심: **launch_ready ≠ actual sending**
(`actual_sending_performed=False` 불변·시스템 자동 발송 0·reviewer roster/PII/actual email 은 committed artifact 0).

이 모듈은 freeze/contact/dropbox 를 **재계산하지 않는다** — 세 산출물을 launch checklist 형태로 합칠 뿐(단일 출처).

절대 불변(상속·상용 안전 계약):
  - **launch_ready 는 freeze 성공 시에만**(`reviewer_contact_ready` ∧ `label_dropbox_ready`). freeze 없으면 launch_ready=False.
  - **no sending**: 어떤 채널로도 자동 발송 0. reviewer 모집/접촉은 operator 수동(checklist 가 그 절차를 명시).
  - **must not include**: reviewer roster·raw PII·actual email·score·rationale·predicted_status·same_event truth·raw body.
  - merge 0 · production gold 0 유지(`_assert_pii_safe` 재귀 가드).
  test: handoff/contact_readiness/dropbox_readiness 주입 시 결정론(network 0).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.returned_label_dropbox_readiness import (
    build_returned_label_dropbox_readiness,
)
from backend.app.tools.reviewer_contact_readiness import build_reviewer_contact_readiness
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "reviewer_contact_launch_checklist"

LAUNCH_READY = "reviewer_contact_launch_ready"
LAUNCH_BLOCKED_NO_FREEZE = "blocked_no_production_candidate_freeze"

# §10 manual contact 절차(실제 사람이 수행·시스템 발송 0·score/rationale/raw body 미포함).
_MANUAL_CONTACT_STEPS = (
    "1. Select an approved reviewer outside git — do NOT commit a reviewer roster or email address.",
    "2. Manually send the sanitized official×news instruction + label schema (the system performs NO sending).",
    "3. Do NOT include model scores / rationale / predicted_status.",
    "4. Do NOT include raw source body.",
    "5. Ask each reviewer to return one JSONL label file to the gitignored returned-label dropbox.",
    "6. Run the validation_command before importing returned labels.",
    "7. Do NOT promote a single / unsure / synthetic label to production gold; require >=2-reviewer agreement.",
)


def build_reviewer_contact_launch_checklist(
    handoff: Optional[dict] = None, *, contact_readiness: Optional[dict] = None,
    dropbox_readiness: Optional[dict] = None, batch_id: str = "operator_regulatory_live",
) -> dict:
    """contact readiness(freeze→package) + returned label dropbox readiness → *수동 접촉 직전* launch checklist.

    contact_readiness 미주입 시 handoff 에서 파생(`build_reviewer_contact_readiness`). dropbox_readiness 미주입 시
    `build_returned_label_dropbox_readiness`. launch_ready 는 reviewer_contact_ready ∧ label_dropbox_ready 일 때만 True.
    actual_sending_performed=False 불변(시스템 발송 0)."""
    cr = contact_readiness or build_reviewer_contact_readiness(handoff or {})
    db = dropbox_readiness or build_returned_label_dropbox_readiness(batch_id=batch_id)

    contact_ready = bool(cr.get("reviewer_contact_ready"))
    dropbox_ready = bool(db.get("label_dropbox_ready"))
    launch_ready = bool(contact_ready and dropbox_ready)
    status = LAUNCH_READY if launch_ready else LAUNCH_BLOCKED_NO_FREEZE
    out = {
        "operation_name": OPERATION_NAME,
        "reviewer_contact_launch_status": status,
        "reviewer_contact_launch_ready": launch_ready,
        # §10 launch sub-readiness(freeze 없으면 대부분 False).
        "production_candidate_batch_ready": contact_ready,
        "reviewer_handoff_ready": contact_ready,
        "reviewer_contact_ready": contact_ready,
        "batch_id": str(cr.get("production_batch_id") or ""),
        "candidate_count": int(cr.get("candidate_count") or 0),
        "official_news_instruction_ready": bool(cr.get("instruction_ready")),
        "label_schema_ready": bool(cr.get("label_schema_ready")),
        "expected_returned_files_ready": bool(cr.get("expected_label_files_ready")),
        "validation_command_ready": bool(cr.get("validation_command_ready") and db.get("validation_command_ready")),
        "placement_guide_ready": bool(cr.get("placement_guide_ready")),
        "label_dropbox_ready": dropbox_ready,
        "manual_contact_steps_ready": True,
        "manual_contact_steps": list(_MANUAL_CONTACT_STEPS),
        # ── §10 boundary(정직·constant) — readiness ≠ sending·reviewer roster/PII 미커밋 ──
        "reviewer_roster_required_but_not_committed": True,
        "reviewer_roster_included": False,
        "actual_email_included": False,
        "actual_sending_performed": False,
        "score_hidden": True,
        "rationale_hidden": True,
        "predicted_status_hidden": True,
        "same_event_truth_hidden": True,
        "raw_body_hidden": True,
        # ── R1/merge 경계(passthrough·constant) ──
        "actual_returned_label_count": int(db.get("actual_returned_label_count") or 0),
        "production_gold_count": int(db.get("production_gold_count") or 0),
        "merge_allowed": False,
        "r2_r7_no_go": True,
        "blocked_reason": "" if launch_ready else (cr.get("blocked_reason") or LAUNCH_BLOCKED_NO_FREEZE),
        "next_action": (
            "operator: begin manual reviewer contact using the checklist (no system sending); collect returned JSONL "
            "labels into the gitignored dropbox and run the validation_command — production gold stays 0 until import"
            if launch_ready else
            "no live-derived production-candidate freeze yet — resolve the official×news acquisition blocker before "
            "reviewer contact (the checklist is not actual sending)"),
    }
    _assert_pii_safe(out, _path="reviewer_contact_launch_checklist_output")
    return out


def sanitized_launch_checklist(out: dict) -> dict:
    """snapshot/frontier 용 aggregate-only 투영(steps 본문 외 status/flag 만)."""
    return {
        "reviewer_contact_launch_status": out["reviewer_contact_launch_status"],
        "reviewer_contact_launch_ready": out["reviewer_contact_launch_ready"],
        "label_dropbox_ready": out["label_dropbox_ready"],
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
        description=("ADR#89 reviewer contact launch checklist (freeze→수동 접촉 직전; launch_ready ≠ actual sending·"
                     "전송 0·reviewer roster/PII 미커밋·score/rationale/raw body 미포함·merge 0). handoff JSON 입력."))
    parser.add_argument("--handoff-json", metavar="PATH", help="reviewer_handoff_bridge 출력 JSON(미지정 시 stdin).")
    parser.add_argument("--batch-id", default="operator_regulatory_live", help="dropbox batch id.")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if ns.handoff_json:
        with open(ns.handoff_json, encoding="utf-8") as f:
            handoff = json.load(f)
    else:
        data = sys.stdin.read().strip()
        handoff = json.loads(data) if data else {}
    out = build_reviewer_contact_launch_checklist(handoff or {}, batch_id=ns.batch_id)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} status={out['reviewer_contact_launch_status']}")
    print(f"- launch_ready={out['reviewer_contact_launch_ready']} candidate_count={out['candidate_count']} "
          f"actual_sending={out['actual_sending_performed']}")
    print(f"- ready_flags: instruction={out['official_news_instruction_ready']} schema={out['label_schema_ready']} "
          f"expected_files={out['expected_returned_files_ready']} validation={out['validation_command_ready']} "
          f"placement={out['placement_guide_ready']} dropbox={out['label_dropbox_ready']} "
          f"manual_steps={out['manual_contact_steps_ready']}")
    print(f"- roster: required_but_not_committed={out['reviewer_roster_required_but_not_committed']} "
          f"roster_included={out['reviewer_roster_included']} email_included={out['actual_email_included']}")
    print(f"- hidden: score={out['score_hidden']} rationale={out['rationale_hidden']} "
          f"predicted_status={out['predicted_status_hidden']} same_event={out['same_event_truth_hidden']} "
          f"raw_body={out['raw_body_hidden']}")
    print(f"- r1: production_gold={out['production_gold_count']} returned_labels={out['actual_returned_label_count']} "
          f"merge={out['merge_allowed']} r2_r7_no_go={out['r2_r7_no_go']}")
    print(f"- blocked_reason: {out['blocked_reason'] or '(none)'}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
