"""ADR#91 §9 — operator payload sourcing workflow (authoring helper 보다 한 단계 더 운영 친화적·코드가 event fabricate 0).

문제(ADR#90 실측·R-OperatorConfirmedEventScarcity 부분진전): authoring helper 는 curated seed → operator-fillable
템플릿 + missing_fields 를 주지만, operator 가 *지금 어디에 무엇을 어떤 순서로* 두고 어떤 명령으로 검증/실행해야
real payload 가 live 로 이어지는지 — 그 **end-to-end 운영 절차** 가 한 곳에 모여있지 않았다(템플릿·real path·검증
명령·live 명령·안전수칙이 흩어짐).

이 모듈은 그 절차를 묶는 **sourcing workflow** 다(authoring helper 위 thin 합성·재구현 0):
  - real payload 존재 상태(not_provided / present_valid / present_invalid_json / present_pii_or_secret)에 따라
    payload_sourcing_status 와 **행동 가능한 operator_action_checklist** 를 분기한다.
  - real path(`inputs/operator_events/...`·gitignored)·example path·검증 명령·**수동** live 명령·안전수칙을 한 번에 노출.
  - 코드가 confirmed=true / live_approved=true 를 **자동으로 쓰지 않으며**, real path 에 자동 기록하지 않고(disk write 0),
    생성 draft 는 live 를 트리거할 수 없다(gate 가 차단). same_event / event-occurred 단정 0.

frontier(read-API)에서 disk read 없이 쓰려면 `operator_payload_status` 를 주입한다(미주입 시에만 real path 를 읽어
상태를 감지 — CLI/operator 경로). 어느 경로든 network 0·secret/PII 미노출(`_assert_pii_safe` 재귀 가드).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.operator_payload_authoring_helper import build_operator_payload_authoring
from backend.app.tools.operator_regulatory_event_payload import (
    EXAMPLE_PAYLOAD_PATH,
    PAYLOAD_NOT_PROVIDED,
    PAYLOAD_PRESENT_INVALID_JSON,
    PAYLOAD_PRESENT_PII_OR_SECRET,
    PAYLOAD_PRESENT_VALID,
    REAL_PAYLOAD_PATH,
    load_operator_regulatory_event_payload,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "operator_payload_sourcing_workflow"

# venv python(Windows·repo 관례) — 명령 문자열 prefix(실행하지 않는다·문서화만).
_VENV_PY = r".\.venv\Scripts\python.exe"

# payload_sourcing_status(operator-facing·real payload 존재 상태에서 파생).
SOURCING_TEMPLATE_READY = "real_payload_absent_template_ready"          # real 없음 → 템플릿 채워 drop.
SOURCING_PRESENT_VALIDATE = "real_payload_present_validate_then_approve"  # real 있음·유효 JSON → 검증→승인.
SOURCING_PRESENT_INVALID_JSON = "real_payload_present_invalid_json"     # real 있음·JSON 파싱 실패.
SOURCING_PRESENT_PII_OR_SECRET = "real_payload_present_pii_or_secret_blocked"  # forbidden 키 → fail-closed.
SOURCING_NO_SEED = "no_authorable_regulatory_seed"                       # authoring 대상 seed 없음.

_STATUS_FROM_PAYLOAD: dict[str, str] = {
    PAYLOAD_NOT_PROVIDED: SOURCING_TEMPLATE_READY,
    PAYLOAD_PRESENT_VALID: SOURCING_PRESENT_VALIDATE,
    PAYLOAD_PRESENT_INVALID_JSON: SOURCING_PRESENT_INVALID_JSON,
    PAYLOAD_PRESENT_PII_OR_SECRET: SOURCING_PRESENT_PII_OR_SECRET,
}


def validation_command(path: str = REAL_PAYLOAD_PATH) -> str:
    """real payload 구조/확인 검증 명령(live_approved=false 유지 시 live 미실행·검증만)."""
    return (f"{_VENV_PY} -m backend.app.tools.operator_regulatory_event_payload "
            f"--event-json {path} --json")


def live_command(path: str = REAL_PAYLOAD_PATH) -> str:
    """bounded official×news live 실행 명령(**수동 단계**·operator_confirmed=true ∧ live_approved=true 일 때만 실제 호출)."""
    return (f"{_VENV_PY} -m backend.app.tools.operator_confirmed_live_runner "
            f"--event-json {path} --json")


def _safety_notes() -> list[str]:
    """operator-facing 안전수칙(불변·계약)."""
    return [
        "Code does not fabricate the event: operator_confirmed/live_approved stay false until you set them.",
        f"The real payload path {REAL_PAYLOAD_PATH} is gitignored — never commit it.",
        "Run the validation command with live_approved=false first; validation alone does not run a live query.",
        "A live query runs ONLY when operator_confirmed=true AND live_approved=true (the gate blocks otherwise).",
        "The curated seed is a collection SHAPE, not a confirmed event; you must confirm the event actually occurred.",
        "Do not put secrets/API keys/reviewer PII in the payload — such keys are rejected fail-closed on load.",
    ]


def _operator_action_checklist(*, sourcing_status: str, missing_fields: list[str],
                               real_path: str) -> list[str]:
    """real payload 상태별 행동 가능한 체크리스트(번호 단계·operator-facing)."""
    vcmd, lcmd = validation_command(real_path), live_command(real_path)
    if sourcing_status == SOURCING_TEMPLATE_READY:
        return [
            "1. Copy the payload_template below into a new JSON file.",
            f"2. Fill the {len(missing_fields)} missing field(s) listed in missing_required_fields.",
            f"3. Save the filled JSON to {real_path} (gitignored — never commit).",
            f"4. Validate the structure WITHOUT running live (keep live_approved=false): {vcmd}",
            "5. Only after confirming the event actually occurred, set operator_confirmed=true and live_approved=true.",
            f"6. Run the bounded official×news live (manual step): {lcmd}",
        ]
    if sourcing_status == SOURCING_PRESENT_VALIDATE:
        return [
            f"1. Validate the present payload: {vcmd}",
            "2. If confirmation_valid=false, fix operator_confirmed/confirmed_by/confirmed_at/agency_or_entity/window.",
            "3. Set live_approved=true only when you approve a bounded live run.",
            f"4. Run the bounded official×news live (manual step): {lcmd}",
        ]
    if sourcing_status == SOURCING_PRESENT_INVALID_JSON:
        return [
            f"1. The file at {real_path} is present but not parseable as a JSON object — fix the JSON.",
            f"2. Re-validate: {vcmd}",
        ]
    if sourcing_status == SOURCING_PRESENT_PII_OR_SECRET:
        return [
            f"1. The payload at {real_path} was rejected fail-closed: it contains forbidden secret/PII/score keys.",
            "2. Remove those keys (keep only the operator-payload fields), then re-validate.",
            f"3. Re-validate: {vcmd}",
        ]
    return ["1. No authorable regulatory seed is available — specify a named regulatory event "
            "(agency/entity + action + ISO date window) before authoring a payload."]


def _next_action(*, sourcing_status: str, real_path: str) -> str:
    """현재 상태에서 operator 가 할 첫 행동 한 줄."""
    if sourcing_status == SOURCING_TEMPLATE_READY:
        return (f"author the payload from the template, save it to {real_path} (gitignored), validate with "
                f"live_approved=false, then confirm + approve and run the live command — no real payload is present yet")
    if sourcing_status == SOURCING_PRESENT_VALIDATE:
        return f"a real payload is present — validate it ({validation_command(real_path)}) then approve and run live"
    if sourcing_status == SOURCING_PRESENT_INVALID_JSON:
        return f"the present payload is not valid JSON — fix {real_path} then re-validate"
    if sourcing_status == SOURCING_PRESENT_PII_OR_SECRET:
        return f"the present payload was rejected for forbidden keys — remove secret/PII/score keys from {real_path}"
    return ("no authorable regulatory seed — specify a named regulatory event "
            "(agency/entity + action + ISO date window)")


def build_operator_payload_sourcing_workflow(
    *, seed_id: Optional[str] = None, operator_payload_status: Optional[str] = None,
) -> dict:
    """real payload 상태 + authoring 템플릿 + 운영 절차(검증/live 명령·체크리스트·안전수칙)를 한 번에 산출.

    operator_payload_status 미주입 시 real path 를 읽어 상태를 감지한다(CLI/operator 경로·disk read·network 0). frontier
    (read-API)에서는 이미 알고 있는 status 를 주입해 disk read 0 으로 쓴다. 코드가 confirmed/live_approved 를 자동으로
    쓰지 않으며 real path 에 자동 기록하지 않는다(disk write 0). 생성 draft 는 live 를 트리거할 수 없다(gate 차단)."""
    if operator_payload_status is None:
        loaded = load_operator_regulatory_event_payload()
        operator_payload_status = loaded["operator_payload_status"]
    authoring = build_operator_payload_authoring(seed_id=seed_id)
    missing_fields = list(authoring.get("missing_fields") or [])
    real_present = operator_payload_status != PAYLOAD_NOT_PROVIDED

    if not authoring.get("payload_template_ready"):
        sourcing_status = SOURCING_NO_SEED
    else:
        sourcing_status = _STATUS_FROM_PAYLOAD.get(str(operator_payload_status), SOURCING_TEMPLATE_READY)

    checklist = _operator_action_checklist(
        sourcing_status=sourcing_status, missing_fields=missing_fields, real_path=REAL_PAYLOAD_PATH)
    nxt = _next_action(sourcing_status=sourcing_status, real_path=REAL_PAYLOAD_PATH)

    out = {
        "operation_name": OPERATION_NAME,
        "payload_sourcing_status": sourcing_status,
        "operator_payload_status": str(operator_payload_status),
        "real_payload_present": bool(real_present),
        # paths(real↔example·real 은 gitignored).
        "real_payload_path": REAL_PAYLOAD_PATH,
        "real_payload_path_gitignored": True,
        "example_payload_path": EXAMPLE_PAYLOAD_PATH,
        # authoring 템플릿 상태(draft·real path 와 다름·live 트리거 불가).
        "draft_template_status": authoring.get("authoring_status"),
        "draft_template_ready": bool(authoring.get("payload_template_ready")),
        "template_path_equals_real_payload_path": bool(authoring.get("template_path_equals_real_payload_path")),
        "missing_required_fields": missing_fields,
        "missing_required_field_count": len(missing_fields),
        # 운영 절차.
        "operator_action_checklist": checklist,
        "validation_command": validation_command(),
        "live_command": live_command(),
        "live_command_is_manual_step": True,
        "safety_notes": _safety_notes(),
        "next_action": nxt,
        # ── 불변 경계(정직·constant) ──
        "code_writes_operator_confirmed_true": False,
        "code_writes_live_approved_true": False,
        "code_writes_real_payload_path": False,
        "code_fabricated_confirmed_event": False,
        "draft_can_trigger_live": bool(authoring.get("can_trigger_live")),
        "operator_confirmed_in_draft": bool(authoring.get("operator_confirmed")),
        "live_approved_in_draft": bool(authoring.get("live_approved")),
        "same_event_asserted": False,
        "event_occurred_asserted_by_code": False,
        "actual_sending_performed": False,
        # operator 가 채울 안전 템플릿(secret/PII/score 없음·forbidden-key 가드 통과).
        "payload_template": authoring.get("payload_template"),
    }
    _assert_pii_safe(out, _path="operator_payload_sourcing_workflow_output")
    return out


def sanitized_operator_payload_sourcing(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(template 본문·전용 명령 필드[validation/live_command]·체크리스트 제외).

    status/flag + operator-facing next_action 만. next_action 은 산문이며 real path/명령을 *언급* 할 수 있으나(secret/PII
    0·정규화 경로 상수만), frontier 가 소비하는 read-API 상태(not_provided)에서는 템플릿 작성 안내 산문이다."""
    return {
        "payload_sourcing_status": out["payload_sourcing_status"],
        "operator_payload_status": out["operator_payload_status"],
        "real_payload_present": out["real_payload_present"],
        "draft_template_ready": out["draft_template_ready"],
        "missing_required_field_count": out["missing_required_field_count"],
        "draft_can_trigger_live": out["draft_can_trigger_live"],
        "payload_sourcing_next_action": out["next_action"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#91 operator payload sourcing workflow (real payload 상태 → authoring 템플릿 + 운영 절차; "
                     "코드가 event fabricate 0·real path 자동 쓰기 0·draft live 트리거 0·network 0·secret read 0)."))
    parser.add_argument("--seed-id", default=None, help="authoring 할 regulatory seed id(미지정 시 bank 의 selected).")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(template 본문 제외).")
    parser.add_argument("--print-template", action="store_true",
                        help="operator 가 채울 payload 템플릿 JSON 출력(stdout·디스크 미저장).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_operator_payload_sourcing_workflow(seed_id=ns.seed_id)
    if ns.print_template:
        print(json.dumps(out.get("payload_template"), ensure_ascii=False, indent=2))
        return 0
    if ns.json:
        print(json.dumps(sanitized_operator_payload_sourcing(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['payload_sourcing_status']} "
          f"real_payload_present={out['real_payload_present']}")
    print(f"- paths: real={out['real_payload_path']} (gitignored={out['real_payload_path_gitignored']}) "
          f"example={out['example_payload_path']}")
    print(f"- draft: status={out['draft_template_status']} can_trigger_live={out['draft_can_trigger_live']} "
          f"missing_fields={out['missing_required_field_count']}")
    print("- operator_action_checklist:")
    for step in out["operator_action_checklist"]:
        print(f"    {step}")
    print(f"- validation_command: {out['validation_command']}")
    print(f"- live_command (manual): {out['live_command']}")
    print("- safety_notes:")
    for note in out["safety_notes"]:
        print(f"    - {note}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
