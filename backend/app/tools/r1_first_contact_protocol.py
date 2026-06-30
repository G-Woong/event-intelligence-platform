"""ADR#92 §12 — R1 reviewer first-contact protocol (freeze→contact→label→gold 운영을 product-quality 로 명확화·전송 0).

문제(ADR#88~#91): freeze→reviewer contact/dropbox/intake/gold 의 각 조각은 준비됐으나, 실제 reviewer 와 *접촉 전후*
무엇을 어떤 순서로 하고 무엇이 금지인지 — 그 **end-to-end protocol** 이 한 곳에 product-quality 로 정리돼 있지 않았다.

이 모듈은 8단계 first-contact protocol 을 정의한다(community_posting_roadmap 의 tuple-of-dicts + STAGE_ORDER +
`_assert_pii_safe` 메커니즘 재사용·§12 필드셋: entry_condition/allowed_action/forbidden_action/artifact_path/
privacy_rule/next_command). 명령/경로는 단일 출처 재사용(intake_command·build_intake_plan).

절대 불변(§12·상속): reviewer roster 는 git 미커밋 · actual sending 0(어떤 단계도 발송하지 않음) · returned label 은
gitignored dropbox 로 회수 · single reviewer/unsure 는 gold 아님 · agreement 필수 · gold 승격은 explicit gate ·
production_gold_count 는 실 returned human labels + 2-reviewer 합의 전까지 0 · merge 0 · secret/PII 0. PURE(network 0).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.r1_label_return_operational_bridge import DEFAULT_BATCH_ID, intake_command
from backend.app.tools.reviewer_batch_launch import build_intake_plan
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "r1_first_contact_protocol"

# r1_first_contact_protocol_status.
FC_DEFINED_AWAITING_FREEZE = "protocol_defined_awaiting_freeze"
FC_DEFINED_FREEZE_READY = "protocol_defined_freeze_ready"

# 8단계 id(순서는 STAGE_ORDER·forward link 는 위치).
STAGE_IDS: tuple[str, ...] = (
    "stage_0_freeze_ready",
    "stage_1_select_reviewer_outside_git",
    "stage_2_manual_contact",
    "stage_3_return_label_to_dropbox",
    "stage_4_validate_returned_label",
    "stage_5_intake_to_r1_candidate",
    "stage_6_agreement_check",
    "stage_7_gold_promotion_gate",
)
STAGE_ORDER: tuple[str, ...] = STAGE_IDS


def _build_stages(*, batch_id: str, dropbox_path: str, validate_cmd: str, intake_cmd: str) -> list[dict]:
    """8단계 first-contact protocol stage dict 리스트(§12 6필드 + stage id). 명령/경로는 단일 출처 재사용."""
    roster_note = "local reviewer roster (NOT in git — operator-managed pseudonym→person mapping)"
    return [
        {
            "stage": "stage_0_freeze_ready",
            "entry_condition": "a production-candidate freeze succeeded and the worklist passed "
                               "first_freeze_package_hardening (freeze_artifact_safe=true)",
            "allowed_action": "review the hardened reviewer worklist (titles, canonical, date, role) before contact",
            "forbidden_action": "do not treat the freeze as truth/gold, do not assert same_event, do not merge",
            "artifact_path": f"outputs/reviewer_batch/{batch_id} (frozen worklist · gitignored)",
            "privacy_rule": "worklist carries titles for judgment but no score/rationale/predicted_status/raw body/PII",
            "next_command": validate_cmd,
        },
        {
            "stage": "stage_1_select_reviewer_outside_git",
            "entry_condition": "freeze worklist is reviewer-safe (stage_0 done)",
            "allowed_action": "select >=2 pseudonymous reviewers per pair from a roster kept OUTSIDE git",
            "forbidden_action": "do not commit the reviewer roster or any reviewer real name/email/phone to git",
            "artifact_path": roster_note,
            "privacy_rule": "roster stays local; only pseudonyms appear in any committed/handoff artifact",
            "next_command": "",
        },
        {
            "stage": "stage_2_manual_contact",
            "entry_condition": "reviewers selected (stage_1 done)",
            "allowed_action": "manually contact reviewers and hand them the worklist + instruction (operator-managed)",
            "forbidden_action": "no system sending — code does not send email/slack/webhook; contact is manual only",
            "artifact_path": "(manual contact — no artifact written by code)",
            "privacy_rule": "actual_sending_performed=false; contact happens outside the system",
            "next_command": "",
        },
        {
            "stage": "stage_3_return_label_to_dropbox",
            "entry_condition": "reviewers contacted (stage_2 done)",
            "allowed_action": "reviewers return label JSONL; operator places each file in the gitignored dropbox",
            "forbidden_action": "do not commit returned label files (they may contain reviewer_id/rationale PII)",
            "artifact_path": f"{dropbox_path} (gitignored)",
            "privacy_rule": "dropbox is gitignored (outputs/reviewer_batch/.../intake); returned labels never committed",
            "next_command": "",
        },
        {
            "stage": "stage_4_validate_returned_label",
            "entry_condition": "returned label files placed in the dropbox (stage_3 done)",
            "allowed_action": "validate the returned label schema/pair coverage before importing",
            "forbidden_action": "do not import malformed/invalid labels; do not fabricate missing labels",
            "artifact_path": f"{dropbox_path} (gitignored)",
            "privacy_rule": "validation reads only schema/coverage, not reviewer identity",
            "next_command": validate_cmd,
        },
        {
            "stage": "stage_5_intake_to_r1_candidate",
            "entry_condition": "returned labels validated (stage_4 done)",
            "allowed_action": "import validated labels and attempt R1 production-gold promotion",
            "forbidden_action": "single-reviewer or unsure/needs_more_context labels never count as gold",
            "artifact_path": f"{dropbox_path} (gitignored)",
            "privacy_rule": "import counts only decisive 2-reviewer agreement; no PII surfaced",
            "next_command": intake_cmd,
        },
        {
            "stage": "stage_6_agreement_check",
            "entry_condition": "labels imported (stage_5 done)",
            "allowed_action": "require >=2-reviewer agreement (unanimous=agreed, conflict=human adjudication)",
            "forbidden_action": "no auto-majority; a single label or an unresolved conflict is not gold",
            "artifact_path": f"{dropbox_path} (gitignored)",
            "privacy_rule": "adjudication is human-only; reviewer identity stays pseudonymous",
            "next_command": "",
        },
        {
            "stage": "stage_7_gold_promotion_gate",
            "entry_condition": "2-reviewer agreement reached (stage_6 done)",
            "allowed_action": "promote agreed decisive labels to production gold under an explicit gate",
            "forbidden_action": "production_gold_count stays 0 until real returned human labels pass agreement; "
                                "no merge before MERGE_GATE",
            "artifact_path": f"{dropbox_path} (gitignored)",
            "privacy_rule": "gold provenance is declaration-checked; synthetic (hn_syn:) excluded",
            "next_command": intake_cmd,
        },
    ]


def build_r1_first_contact_protocol(
    *, batch_id: str = DEFAULT_BATCH_ID, freeze_ready: bool = False,
) -> dict:
    """8단계 reviewer first-contact protocol(PURE·network 0·전송 0·gold 0). 명령/경로는 단일 출처 재사용.

    freeze_ready 는 stage_0 entry(freeze 성공+hardening) 충족 여부 — 미충족(현 상태)이면 awaiting_freeze. 어떤 단계도
    발송하지 않으며(actual_sending_performed=False) reviewer roster 를 git 에 커밋하지 않는다. build_intake_plan 은
    pure(스캔 0) — dropbox 경로/validation command 만 가져온다."""
    plan = build_intake_plan(batch_id, pseudonyms=["reviewer_a", "reviewer_b"])
    dropbox_path = str(plan["intake_directory"])
    validate_cmd = str(plan["validation_command"])
    intake_cmd = intake_command(batch_id=batch_id, intake_dir=dropbox_path)

    stages = _build_stages(
        batch_id=batch_id, dropbox_path=dropbox_path, validate_cmd=validate_cmd, intake_cmd=intake_cmd)
    status = FC_DEFINED_FREEZE_READY if freeze_ready else FC_DEFINED_AWAITING_FREEZE
    if freeze_ready:
        next_action = ("freeze is ready — select >=2 pseudonymous reviewers (roster outside git), manually contact "
                       "them, and collect returned labels into the gitignored dropbox (no system sending)")
    else:
        next_action = ("no production-candidate freeze yet — acquire in-window official×news pairs, freeze, and harden "
                       "the worklist (first_freeze_package_hardening) before first contact")

    out = {
        "operation_name": OPERATION_NAME,
        "r1_first_contact_protocol_status": status,
        "protocol_stages": stages,
        "stage_order": list(STAGE_ORDER),
        "stage_count": len(stages),
        "batch_id": batch_id,
        "dropbox_path": dropbox_path,
        "dropbox_gitignored": True,
        "validation_command": validate_cmd,
        "intake_command": intake_cmd,
        "r1_first_contact_next_action": next_action,
        # ── 불변 경계(§12·정직·constant) ──
        "reviewer_roster_committed": False,
        "actual_sending_performed": False,
        "single_reviewer_label_is_gold": False,
        "unsure_label_is_gold": False,
        "agreement_required_for_gold": True,
        "gold_promotion_gated": True,
        "production_gold_count": 0,
        "merge_allowed": False,
        "same_event_asserted": False,
        "r2_r7_no_go": True,
    }
    _assert_pii_safe(out, _path="r1_first_contact_protocol_output")
    return out


def sanitized_r1_first_contact_protocol(out: dict) -> dict:
    """frontier 용 aggregate-only 투영(stage 본문·명령 제외·status/count/flag 만)."""
    return {
        "r1_first_contact_protocol_status": out["r1_first_contact_protocol_status"],
        "stage_count": out["stage_count"],
        "actual_sending_performed": out["actual_sending_performed"],
        "reviewer_roster_committed": out["reviewer_roster_committed"],
        "gold_promotion_gated": out["gold_promotion_gated"],
        "r1_first_contact_next_action": out["r1_first_contact_next_action"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#92 R1 reviewer first-contact protocol (8단계 freeze→contact→label→gold; 전송 0·roster 미커밋·"
                     "single/unsure 는 gold 아님·agreement 필수·gold 승격 gated·network 0)."))
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID, help="returned-label dropbox batch id.")
    parser.add_argument("--freeze-ready", action="store_true", help="stage_0 freeze entry 충족 표시.")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(stage 본문 제외).")
    parser.add_argument("--print-stages", action="store_true", help="stage 리스트 JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_r1_first_contact_protocol(batch_id=ns.batch_id, freeze_ready=ns.freeze_ready)
    if ns.print_stages:
        print(json.dumps(out["protocol_stages"], ensure_ascii=False, indent=2))
        return 0
    if ns.json:
        print(json.dumps(sanitized_r1_first_contact_protocol(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['r1_first_contact_protocol_status']} "
          f"stages={out['stage_count']}")
    for s in out["protocol_stages"]:
        print(f"    {s['stage']:<36} next_command={'(manual)' if not s['next_command'] else 'cmd'}")
    print(f"- dropbox_path: {out['dropbox_path']} (gitignored={out['dropbox_gitignored']})")
    print(f"- validation_command: {out['validation_command']}")
    print(f"- intake_command: {out['intake_command']}")
    print(f"- actual_sending_performed={out['actual_sending_performed']} "
          f"reviewer_roster_committed={out['reviewer_roster_committed']} "
          f"gold_promotion_gated={out['gold_promotion_gated']}")
    print(f"- next_action: {out['r1_first_contact_next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
