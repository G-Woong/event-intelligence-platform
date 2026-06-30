"""ADR#94 — operator-confirmed ready package (operator 가 외부에서 검증 후 REAL payload 로 옮길 PRE-payload 묶음·contract/planning only·network 0).

문제(ADR#93 실측·R-OperatorConfirmedEventScarcity 연속): promotion workflow 와 live command pack 은 각각 *승격 절차*
와 *실행 명령*을 주지만, operator 가 "이 후보를 가지고 **무엇을 외부에서 직접 검증**하면 real payload 로 옮길 준비가
되는가"를 한눈에 담은 **operator-facing PRE-payload 묶음**이 한 곳에 없었다 — 후보 요약·official/news query 초안·
검증 체크리스트·real path·검증/live 명령이 흩어져 있었다.

이 모듈은 그 묶음이다(promotion workflow + live command pack + regulatory seed bank 위 thin 합성·재구현 0). 핵심:
  - **이것은 REAL payload 가 아니다**: 코드는 이 묶음을 디스크에 쓰지 않고(code_writes_real_payload=False),
    사건이 일어났다고 단정하지 않으며(code_claims_event_occurred=False·event_occurrence_verified_by_code=False),
    operator_confirmed/live_approved 를 강제 False 로 둔다 — operator 가 외부 검증 후 직접 채워야 live 가 된다.
  - **live 를 트리거할 수 없다**: 이 모듈은 acquisition_fn 을 받지 않고 live runner 를 호출하지 않는다(network_invoked
    =False). live/validate 명령은 **문자열로만** 노출한다(실행 0).
  - query 초안·후보 요약·date window 는 regulatory seed bank(PURE)에서 읽는다(하드코딩 0·수집 의도일 뿐 발생 단정 0).
  - same_event 단정 0 · merge 0 · 전송 0 · production gold 0 · secret/PII 0(`_assert_pii_safe` 재귀 가드).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.operator_live_command_pack import build_operator_live_command_pack
from backend.app.tools.operator_regulatory_event_payload import REAL_PAYLOAD_PATH
from backend.app.tools.real_payload_promotion_workflow import (
    RPP_DRAFT_READY,
    RPP_NO_CANDIDATE,
    RPP_REAL_PRESENT,
    build_real_payload_promotion_workflow,
)
from backend.app.tools.regulatory_event_seed_bank import build_regulatory_event_seed_bank
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "operator_confirmed_ready_package"

# operator_confirmed_ready_package_status(operator-facing).
OCRP_READY = "operator_confirmed_ready_package_ready"         # 후보 있음 → operator 가 검증 후 promote.
OCRP_REAL_PRESENT = "real_payload_present_already_promoted"   # real payload 이미 존재 → 검증/승인으로.
OCRP_NO_CANDIDATE = "no_candidate_to_prepare"                 # 준비할 후보 없음.

# promotion status → ready package status(분기 단일 출처).
_STATUS_FROM_PROMOTION: dict[str, str] = {
    RPP_DRAFT_READY: OCRP_READY,
    RPP_REAL_PRESENT: OCRP_REAL_PRESENT,
    RPP_NO_CANDIDATE: OCRP_NO_CANDIDATE,
}

# operator 가 **외부에서 직접** 검증/설정해야 하는 것(코드가 대신 단정/설정하지 않는다·truthy operator-facing 문자열).
_VERIFY_OCCURRENCE = (
    "Verify the event ACTUALLY occurred (occurrence verification FIRST) — code does not and will not confirm this.")
_VERIFY_OFFICIAL_SOURCE = (
    "Verify the official source (Federal Register / agency record) actually published this regulatory action in the "
    "stated window.")
_VERIFY_NEWS_COVERAGE = (
    "Verify at least one news provider (guardian/nyt) reported the same event in the same window.")
_SET_OPERATOR_CONFIRMED = (
    "Set operator_confirmed=true ONLY after verifying the event occurred (this is a live-run approval, not a "
    "same-event assertion).")
_SET_LIVE_APPROVED = (
    "Set live_approved=true to approve a bounded official×news live run.")


def _seed_for_candidate(candidate_id: Optional[str]) -> dict:
    """regulatory seed bank(PURE)에서 candidate_id 에 맞는 seed shape 를 읽는다(query/window draft 용·값 하드코딩 0).

    candidate_id 가 bank 에 있으면 그 seed, 없으면 bank 의 selected(epa) seed, 둘 다 없으면 빈 dict."""
    bank = build_regulatory_event_seed_bank()
    seed_bank = bank.get("seed_bank") or []
    seed = None
    if candidate_id:
        seed = next((s for s in seed_bank if s.get("seed_id") == candidate_id), None)
    if seed is None:
        seed = bank.get("selected_seed_for_next_live_run")
    return seed if isinstance(seed, dict) else {}


def build_operator_confirmed_ready_package(
    *, selected_candidate_id: Optional[str] = None, operator_payload_status: Optional[str] = None,
) -> dict:
    """operator 가 외부 검증 후 REAL payload 로 옮길 PRE-payload 묶음을 산출(network 0·disk write 0·live 실행 0).

    promotion workflow(승격 절차·코드가 confirm/approve/write 0)와 live command pack(validate/live 명령·provider 미리보기)
    을 합성하고, regulatory seed bank 에서 후보 요약·official/news query 초안·date window 를 읽는다. 이 묶음은 **REAL
    payload 가 아니다** — 코드는 디스크에 쓰지 않고(code_writes_real_payload=False), 사건 발생을 단정하지 않으며
    (code_claims_event_occurred=False), operator_confirmed/live_approved 를 강제 False 로 둔다. live runner 를 호출하지
    않고 acquisition_fn 을 받지 않는다(live 트리거 불가·network_invoked=False). secret/PII 0(`_assert_pii_safe`)."""
    promotion = build_real_payload_promotion_workflow(
        selected_attempt_candidate_id=selected_candidate_id, operator_payload_status=operator_payload_status)
    command_pack = build_operator_live_command_pack(operator_payload_status=operator_payload_status)

    candidate_id = promotion.get("selected_attempt_candidate_id")
    status = _STATUS_FROM_PROMOTION.get(str(promotion.get("real_payload_promotion_status")), OCRP_READY)

    # 후보 요약·query 초안은 seed bank(PURE)에서 — agency 우선·없으면 entity(authoring helper 와 동형·하드코딩 0).
    seed = _seed_for_candidate(candidate_id)
    agency_or_entity = str(seed.get("agency") or "").strip() or str(seed.get("entity") or "").strip()
    action_phrase = str(seed.get("action_phrase") or "")
    official_query_draft = str(seed.get("official_query") or "")
    news_query_draft = str(seed.get("news_query") or "")
    start = str(seed.get("date_window_start") or "")
    end = str(seed.get("date_window_end") or "")
    date_window = {"start": start, "end": end}

    candidate_summary = (
        f"{candidate_id or 'no_candidate'}: {agency_or_entity or 'UNSPECIFIED'} — "
        f"{action_phrase or 'UNSPECIFIED'} (code-proposed window {start or '?'}..{end or '?'}); occurrence NOT "
        "verified by code — the operator must confirm this event actually occurred before promotion.")

    out = {
        "operation_name": OPERATION_NAME,
        "operator_confirmed_ready_package_status": status,
        # ── 후보 identity + drafts(seed shape·수집 의도일 뿐 발생/같은 사건 단정 0) ──
        "candidate_id": candidate_id,
        "candidate_summary": candidate_summary,
        "agency_or_entity": agency_or_entity,
        "action_phrase": action_phrase,
        "official_query_draft": official_query_draft,
        "news_query_draft": news_query_draft,
        "date_window": date_window,
        # ── operator 가 외부에서 직접 검증/설정(코드가 대신 단정/설정 0) ──
        "operator_must_verify_occurrence": _VERIFY_OCCURRENCE,
        "operator_must_verify_official_source": _VERIFY_OFFICIAL_SOURCE,
        "operator_must_verify_news_coverage": _VERIFY_NEWS_COVERAGE,
        "operator_must_set_operator_confirmed": _SET_OPERATOR_CONFIRMED,
        "operator_must_set_live_approved": _SET_LIVE_APPROVED,
        "manual_confirmation_fields": list(promotion.get("manual_confirmation_fields") or []),
        # ── paths/commands(reuse·string only·실행 0) ──
        "real_payload_path": REAL_PAYLOAD_PATH,
        "validation_command": promotion.get("validation_command"),
        "live_command": promotion.get("manual_live_command"),
        "validate_payload_command": command_pack.get("validate_payload_command"),
        "live_run_command": command_pack.get("live_run_command"),
        # ── bounded provider 미리보기(reuse from command pack·live 실행 *전* 공개) ──
        "expected_provider_calls": command_pack.get("expected_provider_calls"),
        "provider_list": list(command_pack.get("provider_list") or []),
        "next_action": promotion.get("next_action"),
        # ── 불변(정직·constant·THIS IS NOT A REAL PAYLOAD) ──
        "operator_confirmed": False,
        "live_approved": False,
        "same_event_asserted": False,
        "event_occurrence_verified_by_code": False,
        "code_writes_real_payload": False,
        "code_claims_event_occurred": False,
        "network_invoked": False,
        "production_gold_count": 0,
    }
    _assert_pii_safe(out, _path="operator_confirmed_ready_package_output")
    return out


def sanitized_operator_confirmed_ready_package(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(명령·query 초안·요약 제외·status/provider/honesty flag 만)."""
    return {
        "operator_confirmed_ready_package_status": out["operator_confirmed_ready_package_status"],
        "candidate_id": out["candidate_id"],
        "expected_provider_calls": out["expected_provider_calls"],
        "provider_list": list(out["provider_list"]),
        "operator_confirmed": out["operator_confirmed"],
        "live_approved": out["live_approved"],
        "same_event_asserted": out["same_event_asserted"],
        "event_occurrence_verified_by_code": out["event_occurrence_verified_by_code"],
        "code_writes_real_payload": out["code_writes_real_payload"],
        "network_invoked": out["network_invoked"],
        "production_gold_count": out["production_gold_count"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#94 operator-confirmed ready package (operator 가 외부 검증 후 REAL payload 로 옮길 PRE-payload "
                     "묶음; 코드가 confirm/approve/write 0·event fabricate 0·live 실행 0·network 0)."))
    parser.add_argument("--candidate-id", default=None,
                        help="준비할 후보 id(미지정 시 promotion 기본 epa_final_rule_emissions).")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(명령/query 초안 제외).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_operator_confirmed_ready_package(selected_candidate_id=ns.candidate_id)
    if ns.json:
        print(json.dumps(sanitized_operator_confirmed_ready_package(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['operator_confirmed_ready_package_status']}")
    print(f"- candidate: id={out['candidate_id']} agency_or_entity={out['agency_or_entity']!r}")
    print(f"- candidate_summary: {out['candidate_summary']}")
    print(f"- official_query_draft: {out['official_query_draft']!r}")
    print(f"- news_query_draft: {out['news_query_draft']!r}")
    print(f"- date_window: {out['date_window']}")
    print("- operator must verify (external):")
    print(f"    occurrence: {out['operator_must_verify_occurrence']}")
    print(f"    official_source: {out['operator_must_verify_official_source']}")
    print(f"    news_coverage: {out['operator_must_verify_news_coverage']}")
    print(f"- real_payload_path: {out['real_payload_path']} (this package is NOT a real payload)")
    print(f"- validation_command: {out['validation_command']}")
    print(f"- live_command (manual): {out['live_command']}")
    print(f"- providers: expected_calls={out['expected_provider_calls']} list={out['provider_list']}")
    print(f"- invariants: operator_confirmed={out['operator_confirmed']} live_approved={out['live_approved']} "
          f"code_writes_real_payload={out['code_writes_real_payload']} "
          f"code_claims_event_occurred={out['code_claims_event_occurred']} network_invoked={out['network_invoked']}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
