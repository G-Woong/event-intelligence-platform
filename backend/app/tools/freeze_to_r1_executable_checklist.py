"""ADR#93 §12 — freeze→R1 executable checklist (production-candidate freeze 이후 contact→label→gold 경로를 *실행 가능한* CLI 명령 체크리스트로·전송 0·gold 0).

문제(ADR#88~#92): freeze→contact/dropbox/intake/gold 의 각 조각과 8단계 protocol(산문)은 준비됐으나, freeze 가
성공한 *바로 그 순간* operator 가 "어떤 명령을 순서대로 치면 reviewer contact→returned label→R1 gold 인가"를 한
화면에서 **실행 가능한 명령 문자열**로 받지 못한다. 이 모듈은 그 간극을 잇는다 — freeze artifact 를 받아 hardening
후, returned-label operational bridge 가 단일 출처로 만든 명령(validation / intake / agreement=intake)과 dropbox·
manual contact step·gold gate 를 하나의 체크리스트로 묶는다(명령/배치 id 재저작 0).

배치 정합(§12): contact lane 은 `DEFAULT_BATCH_ID`(operator_regulatory_live) 단일 배치로 thread 한다. freeze 쪽이
다른 배치 id(예: reviewer_prod_cand_001)를 artifact 에 실어오면 `batch_id_mismatch=True` + FR1_BLOCKED_BATCH_MISMATCH
로 차단한다(reviewer 가 *틀린 배치의 dropbox* 로 라벨을 반환하는 것을 막음 — reviewer_contact_launch_checklist 의
LAUNCH_BLOCKED_BATCH_MISMATCH 미러).

절대 불변(§12·상속·constant): actual sending 0 · reviewer roster 미커밋 · single/unsure 는 gold 아님 · agreement 필수 ·
gold 승격 gated · production_gold_count 는 bridge exact passthrough(실 returned human label + 2-reviewer 합의 전까지 0) ·
merge 0 · same_event 단정 0 · network 0 · 디스크 쓰기 0. 명령 문자열/배치 id 는 기존 단일 출처 재사용(재저작 0)."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.first_freeze_package_hardening import (
    build_first_freeze_package_hardening,
)
from backend.app.tools.r1_label_return_operational_bridge import (
    DEFAULT_BATCH_ID,
    build_r1_label_return_operational_bridge,
)
from backend.app.tools.reviewer_contact_launch_checklist import (
    build_reviewer_contact_launch_checklist,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "freeze_to_r1_executable_checklist"

# freeze_to_r1_status.
FR1_READY = "freeze_to_r1_checklist_ready"
FR1_BLOCKED_NO_FREEZE = "blocked_no_production_candidate_freeze"
FR1_BLOCKED_UNSAFE_ARTIFACT = "blocked_freeze_artifact_unsafe"
FR1_BLOCKED_BATCH_MISMATCH = "blocked_freeze_batch_mismatch"


def _next_action(
    *, status: str, dropbox_path: str, batch_id: str, freeze_batch_id: str, blocked_reason: str,
) -> str:
    """freeze_to_r1_status → operator 한 줄 next_action(실행 가능한 다음 한 걸음)."""
    if status == FR1_READY:
        return (
            "freeze is reviewer-safe — execute the checklist: (1) manually contact >=2 pseudonymous reviewers with the "
            f"worklist (no system sending), (2) collect returned JSONL labels into {dropbox_path} (gitignored), "
            "(3) run label_validation_command, then label_intake_command (agreement runs inside that intake) to attempt "
            "R1 gold promotion — production gold stays 0 until real returned labels pass >=2-reviewer agreement")
    if status == FR1_BLOCKED_BATCH_MISMATCH:
        return (
            f"freeze artifact batch_id ({freeze_batch_id}) != contact/dropbox/intake batch ({batch_id}) — re-freeze "
            "into the contact batch (or thread the frozen batch through the dropbox) so reviewers return labels to the "
            "correct gitignored dropbox before contact")
    if status == FR1_BLOCKED_UNSAFE_ARTIFACT:
        return f"freeze artifact is not reviewer-safe — fix it before reviewer contact: {blocked_reason}"
    return (
        "no production-candidate freeze yet — acquire in-window official×news publishable pairs and freeze a production "
        "candidate, then build the executable checklist (this module does not send or create gold)")


def build_freeze_to_r1_executable_checklist(
    *, freeze_artifact: Optional[dict] = None, batch_id: str = DEFAULT_BATCH_ID,
    production_gold_count_before: int = 0, production_gold_count_after: int = 0,
) -> dict:
    """production-candidate freeze → reviewer contact→label→R1 gold 의 *실행 가능한* operator 체크리스트(PURE·전송 0·gold 0).

    freeze_artifact = {pair_id, official_record, news_record, shared_tokens, date_proximity_days}
    (iter_freeze_eligible_record_pairs 형태). None 이면 FR1_BLOCKED_NO_FREEZE(정직 — 아직 freeze 0). 제공 시
    `build_first_freeze_package_hardening` 으로 reviewer-facing 안전성을 검사하고(unsafe → FR1_BLOCKED_UNSAFE_ARTIFACT),
    artifact 가 다른 배치 id 를 실어오면 FR1_BLOCKED_BATCH_MISMATCH 로 차단한다. 명령 3종(validation/intake/agreement)·
    dropbox·expected pattern·gold_promotion_status·production_gold_count 은 `build_r1_label_return_operational_bridge`
    단일 호출에서 그대로 가져온다(재저작 0·production_gold_count 는 exact passthrough). manual contact step 은
    `build_reviewer_contact_launch_checklist` 에서 읽는다. 어떤 경로도 발송/merge/gold 생성/디스크 쓰기를 하지 않는다."""
    # 1) returned-label operational bridge(단일 출처) — 명령/경로/패턴/gold passthrough. network 0·디스크 쓰기 0.
    bridge = build_r1_label_return_operational_bridge(batch_id=batch_id)
    label_intake_command = str(bridge["intake_command"])
    label_validation_command = str(bridge["validation_command"])
    dropbox_path = str(bridge["dropbox_path"])
    expected_returned_file_pattern = str(bridge["expected_file_pattern"])
    gold_promotion_gate_status = str(bridge["gold_promotion_status"])
    production_gold_count = int(bridge["production_gold_count"])   # exact passthrough(실 라벨 전까지 0).
    actual_returned_label_count = int(bridge["actual_returned_label_count"])

    # 2) manual contact steps(단일 출처 — 사적 _MANUAL_CONTACT_STEPS 미임포트).
    launch = build_reviewer_contact_launch_checklist(batch_id=batch_id)
    manual_contact_steps = list(launch["manual_contact_steps"])

    # 3) freeze artifact hardening(reviewer-facing 안전성). artifact None 이면 FH_NO_ARTIFACT·safe=False.
    hardening = build_first_freeze_package_hardening(
        artifact=freeze_artifact,
        production_gold_count_before=production_gold_count_before,
        production_gold_count_after=production_gold_count_after)
    freeze_package_hardening_status = str(hardening["freeze_package_hardening_status"])
    freeze_artifact_safe = bool(hardening["freeze_artifact_safe"])

    # 4) 배치 정합 — freeze 가 다른 배치 id 를 실어오면 mismatch(한쪽[freeze]이 unknown[빈값]이면 단정 불가 → mismatch 아님).
    freeze_batch_id = str(freeze_artifact.get("batch_id") or "") if isinstance(freeze_artifact, dict) else ""
    batch_id_mismatch = bool(freeze_batch_id) and freeze_batch_id != str(batch_id)

    candidate_count = 1 if isinstance(freeze_artifact, dict) else 0

    # 5) status — no freeze > unsafe > batch mismatch > ready(차단이 ready 를 가린다).
    if freeze_artifact is None:
        status = FR1_BLOCKED_NO_FREEZE
    elif not freeze_artifact_safe:
        status = FR1_BLOCKED_UNSAFE_ARTIFACT
    elif batch_id_mismatch:
        status = FR1_BLOCKED_BATCH_MISMATCH
    else:
        status = FR1_READY
    reviewer_contact_checklist_ready = status == FR1_READY

    next_action = _next_action(
        status=status, dropbox_path=dropbox_path, batch_id=str(batch_id),
        freeze_batch_id=freeze_batch_id, blocked_reason=str(hardening.get("blocked_reason") or ""))

    out = {
        "operation_name": OPERATION_NAME,
        "freeze_to_r1_status": status,
        # ── 배치 정합(contact/dropbox/intake 는 단일 batch_id 로 thread). ──
        "batch_id": str(batch_id),
        "freeze_batch_id": freeze_batch_id,
        "batch_id_mismatch": batch_id_mismatch,
        "candidate_count": candidate_count,
        # ── freeze artifact hardening. ──
        "freeze_package_hardening_status": freeze_package_hardening_status,
        "freeze_artifact_safe": freeze_artifact_safe,
        "reviewer_contact_checklist_ready": reviewer_contact_checklist_ready,
        # ── 실행 가능한 체크리스트(manual contact + dropbox + 3 commands + gold gate). ──
        "manual_contact_steps": manual_contact_steps,
        "dropbox_path": dropbox_path,
        "expected_returned_file_pattern": expected_returned_file_pattern,
        "label_validation_command": label_validation_command,
        "label_intake_command": label_intake_command,
        # agreement 는 별도 CLI 가 없다 — intake run 안에서 >=2-reviewer 합의가 수행된다(새 명령 발명 0).
        "agreement_check_command": label_intake_command,
        "agreement_performed_by_intake_run": True,
        "gold_promotion_gate_status": gold_promotion_gate_status,
        "actual_returned_label_count": actual_returned_label_count,
        "production_gold_count": production_gold_count,   # bridge exact passthrough(실 라벨 전까지 0).
        # ── 정직 불변(hardcode·constant) ──
        "actual_sending_performed": False,
        "reviewer_roster_committed": False,
        "single_reviewer_label_is_gold": False,
        "unsure_label_is_gold": False,
        "agreement_required_for_gold": True,
        "gold_promotion_gated": True,
        "same_event_asserted": False,
        "merge_allowed": False,
        "next_action": next_action,
    }
    _assert_pii_safe(out, _path="freeze_to_r1_executable_checklist_output")
    return out


def sanitized_freeze_to_r1_executable_checklist(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(명령 문자열·raw record 제외·status/flag/count/next_action 만)."""
    return {
        "freeze_to_r1_status": out["freeze_to_r1_status"],
        "freeze_artifact_safe": out["freeze_artifact_safe"],
        "reviewer_contact_checklist_ready": out["reviewer_contact_checklist_ready"],
        "batch_id_mismatch": out["batch_id_mismatch"],
        "actual_sending_performed": out["actual_sending_performed"],
        "agreement_required_for_gold": out["agreement_required_for_gold"],
        "gold_promotion_gated": out["gold_promotion_gated"],
        "merge_allowed": out["merge_allowed"],
        "same_event_asserted": out["same_event_asserted"],
        "production_gold_count": out["production_gold_count"],
        "next_action": out["next_action"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#93 freeze→R1 executable checklist (production-candidate freeze 이후 contact→label→gold 를 "
                     "실행 가능한 CLI 명령으로; 전송 0·reviewer roster 미커밋·single/unsure 는 gold 아님·agreement 필수·"
                     "gold 승격 gated·production_gold_count exact passthrough·merge 0·network 0). artifact 미제공 시 "
                     "blocked_no_freeze(정직)."))
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID, help="contact/dropbox/intake batch id.")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(명령 문자열 제외).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    # CLI 는 freeze artifact 를 받지 않는다(no freeze → blocked·현 상태 정직 probe).
    out = build_freeze_to_r1_executable_checklist(batch_id=ns.batch_id)
    if ns.json:
        print(json.dumps(sanitized_freeze_to_r1_executable_checklist(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['freeze_to_r1_status']} "
          f"checklist_ready={out['reviewer_contact_checklist_ready']}")
    print(f"- freeze: hardening={out['freeze_package_hardening_status']} safe={out['freeze_artifact_safe']} "
          f"candidate_count={out['candidate_count']} batch_id_mismatch={out['batch_id_mismatch']}")
    print(f"- batch: contact={out['batch_id']} freeze={out['freeze_batch_id'] or '(none)'}")
    print(f"- dropbox_path: {out['dropbox_path']} (pattern={out['expected_returned_file_pattern']})")
    print(f"- label_validation_command: {out['label_validation_command']}")
    print(f"- label_intake_command: {out['label_intake_command']}")
    print(f"- agreement_check_command: {out['agreement_check_command']} "
          f"(performed_by_intake_run={out['agreement_performed_by_intake_run']})")
    print(f"- gold: promotion_gate={out['gold_promotion_gate_status']} production_gold_count={out['production_gold_count']} "
          f"returned_labels={out['actual_returned_label_count']}")
    print(f"- gates: actual_sending={out['actual_sending_performed']} reviewer_roster_committed={out['reviewer_roster_committed']} "
          f"agreement_required={out['agreement_required_for_gold']} gold_gated={out['gold_promotion_gated']} "
          f"merge={out['merge_allowed']} same_event={out['same_event_asserted']}")
    for i, step in enumerate(out["manual_contact_steps"], 1):
        print(f"    contact_step[{i}] {step}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
