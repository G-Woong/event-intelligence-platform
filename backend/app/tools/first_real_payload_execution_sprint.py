"""ADR#94 — first real payload execution sprint (real payload 있으면 단 한 번 gated live·없으면 PRE-payload 묶음으로 안내·contract/planning only·network 0 except the one gated live call).

문제(ADR#93 실측·R-OperatorConfirmedEventScarcity 연속): operator 가 real payload 를 drop 했을 때 *첫 real payload 를
실제로 실행* 하는 단일 진입점 — present/valid 판정 → (valid ∧ approved ∧ executor 주입)이면 **operator_confirmed_live_
runner 경유로 단 한 번** live → 결과를 aggregate 로 표면화, 없으면 operator_confirmed_ready_package 로 안내 — 가 한 곳에
없었다(payload 경계·gate·runner·PRE-payload 묶음이 흩어짐).

이 모듈은 그 sprint 다(operator_confirmed_live_runner + operator_confirmed_ready_package + live command pack 위 thin 합성·
재구현 0). 핵심 정직성(fail-closed·network 0 except the one gated live call):
  - real payload 없음 → live 0·PRE-payload 묶음(Module D)으로 안내(missing_payload).
  - real payload 무효(bad JSON / forbidden 키) → live 0(payload_invalid).
  - valid ∧ live_approved ∧ acquisition_fn 주입 → **단 한 번** `run_operator_confirmed_live`(operator_confirmed_live_
    runner 경유만·ungated fidelity probe 로 라우팅 0). live_query_executed/production_gold_count 는 그 결과에서 취한다.
  - valid 이나 (미승인 ∨ executor 없음) → live 0(payload_present_not_executed).
  - raw payload 본문/secret/score/PII 미노출(`_assert_pii_safe` 재귀 가드) · actual sending 0 · merge 0 · production gold 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Callable, Optional

from backend.app.tools.operator_confirmed_ready_package import (
    build_operator_confirmed_ready_package,
)
from backend.app.tools.operator_live_command_pack import build_operator_live_command_pack
from backend.app.tools.operator_regulatory_event_intake import OPERATOR_EVENT_REQUIRED_FIELDS
from backend.app.tools.operator_regulatory_event_payload import (
    PAYLOAD_NOT_PROVIDED,
    PAYLOAD_PRESENT_VALID,
    REAL_PAYLOAD_PATH,
)
from backend.app.tools.r1_label_return_operational_bridge import DEFAULT_BATCH_ID
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "first_real_payload_execution_sprint"

# first_real_payload_sprint_status(operator-facing).
SPRINT_AWAITING_PAYLOAD = "awaiting_operator_payload"            # real payload 없음 → PRE-payload 묶음으로 안내.
SPRINT_PAYLOAD_INVALID = "payload_invalid"                       # real payload 있으나 무효 → live 0.
SPRINT_PAYLOAD_NOT_EXECUTED = "payload_present_not_executed"     # valid 이나 미승인/executor 없음 → live 0.
SPRINT_LIVE_EXECUTED = "operator_confirmed_live_executed"        # valid ∧ approved ∧ executor → 단 한 번 live.

# bounded live policy(live runner 가 강제하는 경계·readiness 표면·실행 0). 명령은 문자열로만 노출된다.
_BOUNDED_LIVE_POLICY: dict[str, object] = {
    "bounded": True,
    "host_gate_honored": True,
    "rate_limit_honored": True,
    "raw_text_persisted": False,
    "secret_read": False,
    "routes_only_through_operator_confirmed_live_runner": True,
    "routes_through_ungated_fidelity_probe": False,
}

# operator 가 live 전 외부에서 직접 검증/설정해야 하는 것(코드가 대신 단정/설정 0).
_OPERATOR_VERIFICATION_REQUIRED: dict[str, object] = {
    "required": True,
    "must_verify_occurrence": True,
    "must_verify_official_source": True,
    "must_verify_news_coverage": True,
    "must_set_operator_confirmed": True,
    "must_set_live_approved": True,
}


def build_first_real_payload_execution_sprint(
    *, real_payload_path: Optional[str] = None, operator_payload_status: Optional[str] = None,
    live_approved: Optional[bool] = None, acquisition_fn: Optional[Callable[..., dict]] = None,
    selected_candidate_id: Optional[str] = None, batch_id: Optional[str] = None,
) -> dict:
    """첫 real payload 실행 sprint(fail-closed·network 0 except the one gated live call).

    present/valid 판정은 주입 operator_payload_status 로(파일시스템 미접근·결정론). valid ∧ live_approved ∧ acquisition_fn
    주입일 때만 `run_operator_confirmed_live`(operator_confirmed_live_runner 경유)를 **단 한 번** 호출하고, 그 외에는 live 를
    호출하지 않는다. real payload 없으면 operator_confirmed_ready_package(PRE-payload 묶음)로 안내한다. raw payload 본문/
    secret/score/PII 는 출력에 재임베드하지 않는다(status/count/aggregate 만·`_assert_pii_safe` 재귀 가드)."""
    # present/valid 판정(주입 status 기반·파일시스템 미접근·결정론).
    real_payload_present = operator_payload_status not in (None, "", PAYLOAD_NOT_PROVIDED)
    real_payload_valid = operator_payload_status == PAYLOAD_PRESENT_VALID

    # validate/dry/live 명령 + provider 미리보기(string only·network 0·모든 분기 동일 표면). task: operator_payload_status 만 전달.
    command_pack = build_operator_live_command_pack(operator_payload_status=operator_payload_status)

    # 분기 기본값(fail-closed·live 0).
    sprint_status = SPRINT_AWAITING_PAYLOAD
    live_query_executed = False
    production_gold_count = 0
    network_invoked = False
    blocked_reason = "missing_payload"
    operator_event_status = "not_provided"
    live_no_yield_taxonomy_status = "missing_payload"
    production_candidate_status = "blocked"
    reviewer_handoff_ready = False
    ready_package: Optional[dict] = None
    next_action = ""

    if not real_payload_present:
        # ① real payload 없음 → live 0·PRE-payload 묶음(Module D)으로 안내.
        sprint_status = SPRINT_AWAITING_PAYLOAD
        blocked_reason = "missing_payload"
        ready_package = build_operator_confirmed_ready_package(
            selected_candidate_id=selected_candidate_id, operator_payload_status=operator_payload_status)
        next_action = (
            "no real operator payload — verify and author a real payload (the operator_confirmed_ready_package shows "
            "the candidate, the official/news query drafts, the verification checklist, and the gitignored path to "
            "drop it), then validate it and approve a bounded live run")
    elif not real_payload_valid:
        # ② real payload 있으나 무효(bad JSON / forbidden 키) → live 0.
        sprint_status = SPRINT_PAYLOAD_INVALID
        blocked_reason = "payload_present_invalid"
        live_no_yield_taxonomy_status = "invalid_payload"
        next_action = (
            "the real payload is present but not valid — fix it (valid JSON, all required fields, and no "
            "secret/PII keys), then re-validate before approving a bounded live run")
    elif live_approved is True and acquisition_fn is not None:
        # ③ valid ∧ approved ∧ executor 주입 → 단 한 번 gated live(operator_confirmed_live_runner 경유만).
        # operator_confirmed_live_runner 는 여기서만 lazy import — read 경로(분기 ①②④·acquisition_fn=None)는 real-path
        # 리더를 import조차 안 함(ADR#91/#93 import-isolation 불변 유지). DEFAULT_BATCH_ID 는 local-mirror에서 동일 값.
        from backend.app.tools.operator_confirmed_live_runner import (
            run_operator_confirmed_live,
        )

        exec_path = real_payload_path or REAL_PAYLOAD_PATH
        result = run_operator_confirmed_live(
            exec_path, acquisition_fn=acquisition_fn, batch_id=batch_id or DEFAULT_BATCH_ID)
        sprint_status = SPRINT_LIVE_EXECUTED
        live_query_executed = bool(result.get("live_query_executed"))
        production_gold_count = int(result.get("production_gold_count") or 0)
        network_invoked = True
        blocked_reason = result.get("blocked_reason") or ""
        operator_event_status = result.get("operator_event_status") or "not_provided"
        live_no_yield_taxonomy_status = result.get("live_no_yield_taxonomy_status") or "unknown"
        production_candidate_status = result.get("production_candidate_status") or "blocked"
        reviewer_handoff_ready = bool(result.get("reviewer_handoff_ready"))
        next_action = result.get("next_action") or ""
    else:
        # ④ valid 이나 (미승인 ∨ executor 없음) → live 0.
        sprint_status = SPRINT_PAYLOAD_NOT_EXECUTED
        blocked_reason = "approved_but_no_executor" if live_approved is True else "not_approved"
        live_no_yield_taxonomy_status = "payload_not_approved"
        next_action = (
            "the real payload is present and valid but no live run was executed — approve a bounded live run "
            "(live_approved=true) and provide an acquisition runner to execute it")

    out = {
        "operation_name": OPERATION_NAME,
        "first_real_payload_sprint_status": sprint_status,
        # ── present/valid 판정(주입 status 기반·결정론) ──
        "real_payload_present": real_payload_present,
        "real_payload_valid": real_payload_valid,
        "selected_candidate_id": selected_candidate_id,
        "operator_verification_required": dict(_OPERATOR_VERIFICATION_REQUIRED),
        "payload_required_fields": list(OPERATOR_EVENT_REQUIRED_FIELDS),
        "real_payload_path": REAL_PAYLOAD_PATH,
        # ── commands/providers(reuse·string only·실행 0) ──
        "validate_payload_command": command_pack.get("validate_payload_command"),
        "dry_run_command": command_pack.get("dry_run_command"),
        "live_run_command": command_pack.get("live_run_command"),
        "expected_provider_calls": command_pack.get("expected_provider_calls"),
        "provider_list": list(command_pack.get("provider_list") or []),
        "bounded_live_policy": dict(_BOUNDED_LIVE_POLICY),
        # ── live 결과/진단(분기별·aggregate·raw payload 0) ──
        "live_query_executed": live_query_executed,
        "operator_event_status": operator_event_status,
        "live_no_yield_taxonomy_status": live_no_yield_taxonomy_status,
        "production_candidate_status": production_candidate_status,
        "reviewer_handoff_ready": reviewer_handoff_ready,
        "operator_confirmed_ready_package": ready_package,
        "blocked_reason": blocked_reason,
        "next_action": next_action,
        # ── 불변(정직·constant) ──
        "routes_through_ungated_fidelity_probe": False,
        "raw_payload_text_exposed": False,
        "secret_values_exposed": False,
        "actual_sending_performed": False,
        "merge_allowed": False,
        "production_gold_count": production_gold_count,
        "network_invoked": network_invoked,
    }
    _assert_pii_safe(out, _path="first_real_payload_execution_sprint_output")
    return out


def sanitized_first_real_payload_execution_sprint(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(명령·required fields·ready package 본문 제외·status/count/flag 만)."""
    return {
        "first_real_payload_sprint_status": out["first_real_payload_sprint_status"],
        "real_payload_present": out["real_payload_present"],
        "real_payload_valid": out["real_payload_valid"],
        "selected_candidate_id": out["selected_candidate_id"],
        "expected_provider_calls": out["expected_provider_calls"],
        "provider_list": list(out["provider_list"]),
        "live_query_executed": out["live_query_executed"],
        "production_candidate_status": out["production_candidate_status"],
        "routes_through_ungated_fidelity_probe": out["routes_through_ungated_fidelity_probe"],
        "actual_sending_performed": out["actual_sending_performed"],
        "merge_allowed": out["merge_allowed"],
        "production_gold_count": out["production_gold_count"],
        "network_invoked": out["network_invoked"],
        "blocked_reason": out["blocked_reason"],
        "next_action": out["next_action"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#94 first real payload execution sprint (real payload 있으면 단 한 번 gated live·없으면 "
                     "PRE-payload 묶음으로 안내; operator_confirmed_live_runner 경유만·ungated fidelity probe 0·"
                     "actual sending 0·merge 0·secret read 0·network 0 except the one gated live call)."))
    parser.add_argument("--candidate-id", default=None,
                        help="real payload 없을 때 안내할 후보 id(미지정 시 promotion 기본 epa).")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(명령/ready package 본문 제외).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    # CLI: operator_payload_status 미주입(이번 턴 real payload 없음) → awaiting_operator_payload(live 0).
    out = build_first_real_payload_execution_sprint(selected_candidate_id=ns.candidate_id)
    if ns.json:
        print(json.dumps(sanitized_first_real_payload_execution_sprint(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['first_real_payload_sprint_status']}")
    print(f"- payload: present={out['real_payload_present']} valid={out['real_payload_valid']} "
          f"live_executed={out['live_query_executed']}")
    print(f"- providers: expected_calls={out['expected_provider_calls']} list={out['provider_list']}")
    print(f"- validate_payload_command: {out['validate_payload_command']}")
    print(f"- dry_run_command: {out['dry_run_command']}")
    print(f"- live_run_command: {out['live_run_command']}")
    print(f"- bounded_live_policy: {out['bounded_live_policy']}")
    print(f"- r1: production_gold={out['production_gold_count']} merge={out['merge_allowed']} "
          f"sending={out['actual_sending_performed']} "
          f"routes_through_ungated_fidelity_probe={out['routes_through_ungated_fidelity_probe']} "
          f"network_invoked={out['network_invoked']}")
    print(f"- blocked_reason: {out['blocked_reason'] or '(none)'}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
