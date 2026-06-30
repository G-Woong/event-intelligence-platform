"""ADR#93 §9 — real payload promotion workflow (live attempt 후보 → REAL operator payload 승격 절차·draft-only·코드가 event fabricate 0).

문제(ADR#92 실측·R-OperatorConfirmedEventScarcity): live attempt pack 은 operator 가 고를 수 있는 candidate event
shape 묶음을 주지만, "그 후보 하나를 어떤 순서·어떤 안전장치로 **REAL operator payload** 로 승격(promote)하는가" 의
절차가 한 곳에 명시되어 있지 않았다 — 승격은 operator 가 *발생을 확인하고* operator_confirmed/live_approved 를 직접
설정해 real path 에 저장해야만 live 가 되는, 사람이 책임지는 단계인데 그 경계가 흩어져 있었다.

이 모듈은 그 승격 절차를 묶는 **promotion workflow** 다(live attempt pack + authoring helper 위 thin 합성·재구현 0).
핵심 정직성(불변·draft-only):
  - **코드는 절대 operator_confirmed=true / live_approved=true 를 쓰지 않는다**: 승격 draft 는
    `generate_operator_fillable_payload_template` 로 만들어(operator_confirmed/live_approved 강제 False 상속) 그대로는
    gate 를 통과하지 못함을 `validate_operator_confirmed_event` 로 증명한다(draft 는 live-eligible 이 아니다).
  - **코드는 real payload 파일을 쓰지 않는다**(disk write 0·network 0·real payload disk read 0). real path 는
    gitignored 이며 operator 가 직접 저장해야 한다.
  - **코드는 사건 발생을 단정하지 않는다**: 승격 체크리스트는 *occurrence 확인을 FIRST* 로 강제한다 — operator 가
    실제 발생을 확인한 뒤에만 approval flag 를 설정한다.
  - same_event 단정 0 · merge 0 · 전송 0 · production gold 0 · secret/PII 0(`_assert_pii_safe` 재귀 가드).
  승격은 코드가 하는 게 아니라 operator 가 하는 일이다 — 이 모듈은 *그 절차를 보여줄* 뿐이다.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.live_attempt_pack_builder import (
    ATTEMPT_PACK_ID,
    PACK_NO_CANDIDATES,
    PACK_READY,
    PACK_REAL_PRESENT,
    build_live_attempt_pack,
)
from backend.app.tools.operator_payload_authoring_helper import (
    generate_operator_fillable_payload_template,
)
from backend.app.tools.operator_payload_sourcing_workflow import (
    live_command,
    validation_command,
)
from backend.app.tools.operator_regulatory_event_intake import (
    validate_operator_confirmed_event,
)
from backend.app.tools.operator_regulatory_event_payload import (
    EXAMPLE_PAYLOAD_PATH,
    REAL_PAYLOAD_PATH,
)
from backend.app.tools.regulatory_event_seed_bank import build_regulatory_event_seed_bank
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "real_payload_promotion_workflow"

# real_payload_promotion_status(operator-facing).
RPP_DRAFT_READY = "promotion_draft_ready_operator_must_confirm"   # real 없음 → 후보를 draft 로 승격(operator 확인 필요).
RPP_REAL_PRESENT = "real_payload_present_promotion_complete"      # real 있음 → 승격 완료(검증/승인으로 진행).
RPP_NO_CANDIDATE = "no_attempt_candidate_to_promote"             # 승격할 후보 없음.

# 기본 선택 후보 — occurrence-verifiability 가 가장 높은(유일 selectable) seed. 없으면 첫 후보로 폴백.
_DEFAULT_CANDIDATE_ID = "epa_final_rule_emissions"

# operator 가 **수동으로** 채워/설정해야 하는 confirmation 필드(코드가 대신 쓰지 않는다·§9 계약).
MANUAL_CONFIRMATION_FIELDS: tuple[str, ...] = (
    "operator_confirmed", "confirmed_by", "confirmed_at",
    "date_window_start", "date_window_end", "live_approved",
)

# live_attempt_pack_status → real_payload_promotion_status 매핑(분기 단일 출처).
_PROMOTION_STATUS_FROM_PACK: dict[str, str] = {
    PACK_READY: RPP_DRAFT_READY,
    PACK_REAL_PRESENT: RPP_REAL_PRESENT,
    PACK_NO_CANDIDATES: RPP_NO_CANDIDATE,
}


def live_preflight_command(path: str = REAL_PAYLOAD_PATH) -> str:
    """no-live preflight = real payload 구조 검증만(live_approved=false 유지·live 미실행). `validation_command` 의 alias —
    별도 live 실행 없이 payload 가 gate-ready 한지 점검하는 preflight 단계임을 이름으로 구분한다(재구현 0)."""
    return validation_command(path)


def _promotion_checklist(*, manual_live_cmd: str, real_path: str) -> list[str]:
    """승격 체크리스트(§9·순서 강제: occurrence 확인 FIRST → source/date/query 확인 → flag 설정 → live 실행)."""
    return [
        "1. Verify the event ACTUALLY occurred (occurrence verification FIRST) — code does not and will not "
        "confirm this for you.",
        "2. Confirm the source, the real occurrence date window, and the official_query/news_query match the "
        "actual event.",
        f"3. Only AFTER steps 1-2, set operator_confirmed=true and live_approved=true, fill confirmed_by/"
        f"confirmed_at, and save the payload to {real_path} (gitignored — never commit).",
        f"4. Run the bounded official×news live command (manual step): {manual_live_cmd}",
    ]


def _safety_notes(real_path: str) -> list[str]:
    """operator-facing 안전수칙(불변·계약·draft-only)."""
    return [
        "Code never sets operator_confirmed=true or live_approved=true — you set them yourself after verifying "
        "the event occurred.",
        "Code does not write the real payload and does not claim the event occurred; promotion is a draft-only "
        "procedure.",
        f"The real payload path {real_path} is gitignored — never commit it.",
        "Run the no-live preflight (the validation command) first; it validates structure with live_approved=false "
        "and does not run a live query.",
        "A live run happens ONLY when operator_confirmed=true AND live_approved=true; the draft fails this gate by "
        "construction.",
        "Promotion order is occurrence-verification FIRST — confirm the event actually happened before setting any "
        "approval flag.",
        "Do not put secrets/API keys/reviewer PII in the payload — such keys are rejected fail-closed on load.",
    ]


def _next_action(*, promotion_status: str, selected_id: Optional[str], real_path: str,
                 validation_cmd: str) -> str:
    """현재 승격 상태에서 operator 가 할 첫 행동 한 줄."""
    if promotion_status == RPP_DRAFT_READY:
        return (
            f"the selected attempt candidate {selected_id!r} is a DRAFT, not a confirmed event — verify the event "
            f"ACTUALLY occurred FIRST, then set operator_confirmed=true and live_approved=true, fill confirmed_by/"
            f"confirmed_at and the real occurrence window, save it to {real_path} (gitignored), run the no-live "
            f"preflight ({validation_cmd}), and only then run the manual live command — code does not confirm the "
            f"event, set live_approved, or write the real payload")
    if promotion_status == RPP_REAL_PRESENT:
        return (
            f"a real operator payload is already present at {real_path} — the promotion is complete; validate it "
            f"({validation_cmd}) and approve a bounded live run rather than promoting a new draft candidate")
    return (
        "no attempt candidate is available to promote — specify a named regulatory event "
        "(agency/entity + action + ISO date window) before promoting a payload")


def build_real_payload_promotion_workflow(
    *, selected_attempt_candidate_id: Optional[str] = None, operator_payload_status: Optional[str] = None,
) -> dict:
    """live attempt 후보 → REAL operator payload 승격 절차(draft + 체크리스트 + 검증/preflight/live 명령·안전수칙)를 한 번에 산출.

    operator_payload_status 는 주입(frontier-safe·real payload disk read 0) — present_valid 면 승격 완료(검증/승인으로
    진행), 아니면 draft 승격 ready. 후보는 live attempt pack 에서 가져오며 기본 선택은 occurrence-verifiability 가 가장
    높은 epa_final_rule_emissions(없으면 첫 후보). 승격 draft 는 `generate_operator_fillable_payload_template` 로 만들어
    operator_confirmed/live_approved 강제 False 를 상속하고, `validate_operator_confirmed_event` 로 그 draft 가 gate 를
    통과하지 못함(live-eligible 아님)을 증명한다. 코드는 confirmed/approved 를 쓰지 않으며 real payload 파일을 쓰지
    않는다(disk write 0·network 0). same_event 단정 0·merge 0·전송 0·secret/PII 0."""
    pack = build_live_attempt_pack(operator_payload_status=operator_payload_status)
    pack_status = pack.get("live_attempt_pack_status")
    available = list(pack.get("available_candidate_ids") or [])

    # 후보 선택: 명시 id(존재 시) > 기본 epa(존재 시) > 첫 후보 > 없음.
    if selected_attempt_candidate_id and selected_attempt_candidate_id in available:
        selected_id: Optional[str] = selected_attempt_candidate_id
    elif _DEFAULT_CANDIDATE_ID in available:
        selected_id = _DEFAULT_CANDIDATE_ID
    elif available:
        selected_id = available[0]
    else:
        selected_id = None

    promotion_status = _PROMOTION_STATUS_FROM_PACK.get(str(pack_status), RPP_DRAFT_READY)

    # 승격 draft 생성 + gate 실패 증명(코드가 confirmed/approved 를 쓰지 않음을 실값으로 입증).
    draft_confirmation_valid = False
    draft_live_eligible = False
    draft_blocked_reason = "no_attempt_candidate_to_promote"
    if selected_id is not None:
        bank = build_regulatory_event_seed_bank()
        seed = next((s for s in (bank.get("seed_bank") or []) if s.get("seed_id") == selected_id), None)
        if seed is None:
            selected_id = None
            promotion_status = RPP_NO_CANDIDATE
        else:
            draft = generate_operator_fillable_payload_template(seed)
            # CARDINAL — draft 는 operator_confirmed/live_approved 가 강제 False(helper 가 보장).
            assert draft.get("operator_confirmed") is False, "draft operator_confirmed must be False"
            assert draft.get("live_approved") is False, "draft live_approved must be False"
            cv = validate_operator_confirmed_event(draft)
            draft_confirmation_valid = bool(cv.get("confirmation_valid"))
            draft_live_eligible = bool(cv.get("live_allowed"))
            draft_blocked_reason = cv.get("confirmation_blocked_reason") or ""
            # CARDINAL — draft 는 live-eligible 이 아니다(gate 통과 불가 → live 트리거 0).
            assert draft_confirmation_valid is False, "draft must NOT be confirmation_valid (not live-eligible)"
            assert draft_live_eligible is False, "draft must NOT be live-allowed (not live-eligible)"
    else:
        promotion_status = RPP_NO_CANDIDATE

    validation_cmd = validation_command()
    manual_live_cmd = live_command()
    operator_verification_required = {
        "required": True,
        "draft_confirmation_valid": draft_confirmation_valid,   # False — draft 는 gate 통과 못함.
        "draft_live_eligible": draft_live_eligible,             # False — draft 로는 live 불가.
        "blocked_reason": draft_blocked_reason,                 # operator 가 채워야 할 결손(secret/PII 없음).
        "must_verify_occurrence_first": True,
    }

    out = {
        "operation_name": OPERATION_NAME,
        "real_payload_promotion_status": promotion_status,
        "selected_attempt_candidate_id": selected_id,
        "attempt_pack_id": ATTEMPT_PACK_ID,
        "available_candidate_ids": available,
        # operator 가 직접 해야 하는 일(코드가 대신 단정/기록하지 않는다).
        "operator_verification_required": operator_verification_required,
        "manual_confirmation_fields": list(MANUAL_CONFIRMATION_FIELDS),
        # paths(real↔example·real 은 gitignored·코드 자동 쓰기 0).
        "real_payload_path": REAL_PAYLOAD_PATH,
        "example_payload_path": EXAMPLE_PAYLOAD_PATH,
        # 승격 절차.
        "promotion_checklist": _promotion_checklist(manual_live_cmd=manual_live_cmd, real_path=REAL_PAYLOAD_PATH),
        "validation_command": validation_cmd,
        "live_preflight_command": live_preflight_command(),
        "manual_live_command": manual_live_cmd,
        "live_command_is_manual_step": True,
        "draft_can_trigger_live": draft_live_eligible,          # False.
        "safety_notes": _safety_notes(REAL_PAYLOAD_PATH),
        "next_action": _next_action(
            promotion_status=promotion_status, selected_id=selected_id, real_path=REAL_PAYLOAD_PATH,
            validation_cmd=validation_cmd),
        # ── 불변 경계(정직·constant·EVERY input) ──
        "code_sets_operator_confirmed_true": False,
        "code_sets_live_approved_true": False,
        "code_claims_event_occurred": False,
        "code_writes_real_payload": False,
        "draft_operator_confirmed": False,
        "draft_live_approved": False,
        "real_payload_path_gitignored": True,
        "same_event_asserted": False,
        "actual_sending_performed": False,
        "merge_allowed": False,
        "production_gold_count": 0,
    }
    _assert_pii_safe(out, _path="real_payload_promotion_workflow_output")
    return out


def sanitized_real_payload_promotion(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(체크리스트·명령·draft 본문 제외·status/next_action + 핵심 boolean 만)."""
    return {
        "real_payload_promotion_status": out["real_payload_promotion_status"],
        "selected_attempt_candidate_id": out["selected_attempt_candidate_id"],
        "code_sets_operator_confirmed_true": out["code_sets_operator_confirmed_true"],
        "code_sets_live_approved_true": out["code_sets_live_approved_true"],
        "code_writes_real_payload": out["code_writes_real_payload"],
        "draft_operator_confirmed": out["draft_operator_confirmed"],
        "draft_live_approved": out["draft_live_approved"],
        "real_payload_path_gitignored": out["real_payload_path_gitignored"],
        "production_gold_count": out["production_gold_count"],
        "real_payload_promotion_next_action": out["next_action"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#93 real payload promotion workflow (live attempt 후보 → REAL operator payload 승격 절차; "
                     "코드가 operator_confirmed/live_approved 쓰기 0·real payload 쓰기 0·event fabricate 0·network 0)."))
    parser.add_argument("--candidate-id", default=None,
                        help="승격할 attempt 후보 id(미지정 시 기본 epa_final_rule_emissions·없으면 첫 후보).")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(체크리스트/명령/draft 본문 제외).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_real_payload_promotion_workflow(selected_attempt_candidate_id=ns.candidate_id)
    if ns.json:
        print(json.dumps(sanitized_real_payload_promotion(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['real_payload_promotion_status']} "
          f"selected_candidate={out['selected_attempt_candidate_id']}")
    print(f"- paths: real={out['real_payload_path']} (gitignored={out['real_payload_path_gitignored']}) "
          f"example={out['example_payload_path']}")
    print(f"- draft: operator_confirmed={out['draft_operator_confirmed']} live_approved={out['draft_live_approved']} "
          f"can_trigger_live={out['draft_can_trigger_live']}")
    print(f"- manual_confirmation_fields: {', '.join(out['manual_confirmation_fields'])}")
    print("- promotion_checklist:")
    for step in out["promotion_checklist"]:
        print(f"    {step}")
    print(f"- validation_command: {out['validation_command']}")
    print(f"- live_preflight_command (no-live): {out['live_preflight_command']}")
    print(f"- manual_live_command (manual): {out['manual_live_command']}")
    print("- safety_notes:")
    for note in out["safety_notes"]:
        print(f"    - {note}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
