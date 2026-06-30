"""ADR#95 §9(B) — evidence-assisted payload production kit (operator-confirmed-ready 묶음을 operator-actionable
EVIDENCE-REQUIREMENTS kit 로 변환·contract/planning only·network 0).

문제(ADR#94 실측 연속): `operator_confirmed_ready_package` 는 operator 가 외부에서 무엇을 검증해야 하는지 *체크리스트*
와 query 초안·real path·검증/live 명령을 한 묶음으로 준다. 그러나 operator 가 "candidate epa_final_rule_emissions 를
real payload 로 옮기기 위해 **정확히 어떤 official/news 증거를 어떤 acceptance 기준으로 모아야** 하는가"를 구조화한
**evidence-requirements kit** 은 없었다 — official record 가 만족해야 할 조건(provider/agency/document_type/overlap
tokens)과 news 보도가 만족해야 할 조건(provider/angle/action phrase)이 분리·명시돼 있지 않았다.

이 모듈은 그 kit 이다(ready package + regulatory seed bank 위 thin 합성·재구현 0). 핵심:
  - **이것은 payload 가 아니다**(kit_is_payload=False): operator 가 증거를 모아 외부 검증을 마친 뒤에야 real payload 를
    author/confirm 한다. kit 자체는 디스크에 쓰지 않고 사건이 일어났다고 단정하지 않는다(code_claims_event_occurred=False).
  - **live 를 트리거할 수 없다**(kit_can_trigger_live=False·network_invoked=False): acquisition_fn 을 받지 않고 live
    runner 를 호출하지 않는다. validate/live 명령은 **문자열로만** 노출(ready package 가 만든 명령 그대로·실행 0).
  - candidate identity·query 초안·date window·real path·명령은 `operator_confirmed_ready_package`(PURE)에서 상속하고,
    ready package 가 drop 한 evidence-shaping 필드(expected_overlap_tokens/expected_news_angle/document_type/risk/
    source_role_policy)는 `regulatory_event_seed_bank`(PURE)에서 복원한다(값 하드코딩 0).
  - official=authoritative evidence · news=public reporting · **NOT same role** · community/market **NOT anchor**.
  - same_event 단정 0 · merge 0 · 전송 0 · production gold 0 · secret/PII 0(`_assert_pii_safe` 재귀 가드).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.operator_confirmed_ready_package import (
    build_operator_confirmed_ready_package,
)
from backend.app.tools.regulatory_event_seed_bank import build_regulatory_event_seed_bank
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "evidence_assisted_payload_production_kit"
CONTRACT_VERSION = "evidence_assisted_payload_production_kit_v1"

# evidence_payload_kit_status(operator-facing).
KIT_READY = "evidence_payload_kit_ready"        # 후보 있음 → operator 가 아래 증거를 모아 외부 검증.
KIT_NO_CANDIDATE = "no_candidate_to_prepare"    # 준비할 후보 없음.


def _seed_for_candidate(candidate_id: Optional[str]) -> dict:
    """regulatory seed bank(PURE)에서 candidate_id 에 맞는 seed 를 읽어 ready package 가 drop 한 evidence-shaping
    필드(expected_overlap_tokens/expected_news_angle/document_type/risk/source_role_policy)를 복원한다(하드코딩 0).

    candidate_id 가 bank 에 있으면 그 seed, 없으면 selected(epa) seed, 둘 다 없으면 빈 dict."""
    bank = build_regulatory_event_seed_bank()
    seed_bank = bank.get("seed_bank") or []
    seed = None
    if candidate_id:
        seed = next((s for s in seed_bank if s.get("seed_id") == candidate_id), None)
    if seed is None:
        seed = bank.get("selected_seed_for_next_live_run")
    return seed if isinstance(seed, dict) else {}


def build_evidence_assisted_payload_production_kit(
    *, selected_candidate_id: Optional[str] = None, operator_payload_status: Optional[str] = None,
) -> dict:
    """operator-confirmed-ready 묶음을 operator-actionable EVIDENCE-REQUIREMENTS kit 으로 변환(network 0·disk write 0·
    live 실행 0).

    `operator_confirmed_ready_package`(PURE)에서 candidate identity·official/news query 초안·date window·real path·
    validate/live 명령을 상속하고, `regulatory_event_seed_bank`(PURE)에서 ready package 가 drop 한 evidence-shaping
    필드(overlap tokens·news angle·document_type·risk·source_role_policy)를 복원해 official_evidence_required /
    news_evidence_required(provider·query·acceptance_criteria)로 구조화한다. 이 kit 은 **payload 가 아니다**
    (kit_is_payload=False)·**live 를 트리거할 수 없다**(kit_can_trigger_live=False·network_invoked=False)·사건 발생을
    단정하지 않는다(code_claims_event_occurred=False). secret/PII 0(`_assert_pii_safe`)."""
    ready = build_operator_confirmed_ready_package(
        selected_candidate_id=selected_candidate_id, operator_payload_status=operator_payload_status)

    candidate_id = ready.get("candidate_id")
    status = KIT_READY if candidate_id else KIT_NO_CANDIDATE

    # ready package 가 drop 한 evidence-shaping 필드를 seed bank(PURE)에서 복원(값 하드코딩 0).
    seed = _seed_for_candidate(candidate_id)
    document_type = str(seed.get("document_type") or "")
    expected_overlap_tokens = [str(t) for t in (seed.get("expected_overlap_tokens") or [])]
    expected_news_angle = str(seed.get("expected_news_angle") or "")
    risk = str(seed.get("risk") or "")
    source_role_policy = str(seed.get("source_role_policy") or "")
    official_provider = str(seed.get("official_provider") or "") or "federal_register"
    news_providers = [str(p) for p in (seed.get("news_providers") or []) if str(p)]
    news_provider_label = "/".join(news_providers) if news_providers else "guardian/nyt"

    # ready package 상속(candidate identity·query 초안·window·명령·real path).
    agency_or_entity = ready.get("agency_or_entity")
    action_phrase = ready.get("action_phrase")
    official_query = ready.get("official_query_draft")
    news_query = ready.get("news_query_draft")
    date_window = dict(ready.get("date_window") or {})
    win_start = str(date_window.get("start") or "?")
    win_end = str(date_window.get("end") or "?")

    official_evidence_required = [{
        "provider": official_provider,
        "query": official_query,
        "agency": agency_or_entity,
        "document_type": document_type,
        "expected_overlap_tokens": expected_overlap_tokens,
        "acceptance_criteria": (
            f"Find a {official_provider} {document_type or 'document'} from {agency_or_entity or 'the agency'} "
            f"matching the query within {win_start}..{win_end}; its title/text should overlap the expected tokens "
            f"{expected_overlap_tokens}. This is authoritative evidence the action was published — it does NOT by "
            "itself confirm the event occurred or that any news article refers to the same event."),
    }]
    news_evidence_required = [{
        "provider": news_provider_label,
        "query": news_query,
        "expected_news_angle": expected_news_angle,
        "action_phrase": action_phrase,
        "divergence_risk": risk,
        "acceptance_criteria": (
            f"Find at least one {news_provider_label} article within {win_start}..{win_end} reporting the same action "
            f"({action_phrase or 'the action'}); expected angle: {expected_news_angle or 'public reporting'}. News is "
            "public reporting, NOT authoritative evidence, and must not be the sole anchor; community/market reaction "
            "must NOT be used as an event anchor."),
    }]

    # official=authoritative evidence · news=public reporting · NOT same role · community/market NOT anchor.
    source_role_requirements = {
        "official": "authoritative evidence",
        "news": "public reporting",
        "not_same_role": True,
        "community_or_market_not_anchor": True,
        "policy": source_role_policy,
    }

    operator_next_action = (
        "Collect the official_evidence_required and news_evidence_required above and verify each acceptance_criteria "
        "OFFLINE (no live run). Only after the official document AND same-window news are independently confirmed "
        "should the operator author/confirm the real payload, set operator_confirmed=true ∧ live_approved=true, and "
        "run the live command. This kit is NOT a payload, cannot trigger live, and does not confirm the event occurred.")

    out = {
        "operation_name": OPERATION_NAME,
        "contract_version": CONTRACT_VERSION,
        "evidence_payload_kit_status": status,
        "selected_candidate_id": candidate_id,
        # ── 구조화 evidence requirements(official record + news 보도·acceptance 기준 분리) ──
        "official_evidence_required": official_evidence_required,
        "official_evidence_required_count": len(official_evidence_required),
        "news_evidence_required": news_evidence_required,
        "news_evidence_required_count": len(news_evidence_required),
        # ── operator 가 확정해야 하는 identity/window/angle(seed/ready 복원·발생 단정 0) ──
        "agency_or_entity_required": agency_or_entity,
        "action_phrase_required": action_phrase,
        "date_window_required": date_window,
        "expected_news_angle_required": expected_news_angle,
        "source_role_requirements": source_role_requirements,
        # ── paths/commands(reuse·string only·실행 0) ──
        "real_payload_path": ready.get("real_payload_path"),
        "validation_command": ready.get("validate_payload_command"),
        "live_command": ready.get("live_run_command"),
        "operator_next_action": operator_next_action,
        # ── 불변(정직·constant·THIS IS NOT A PAYLOAD·live 트리거 불가) ──
        "kit_is_payload": False,
        "kit_can_trigger_live": False,
        "operator_confirmed": False,
        "live_approved": False,
        "same_event_asserted": False,
        "code_claims_event_occurred": False,
        "network_invoked": False,
        "production_gold_count": 0,
    }
    _assert_pii_safe(out, _path="evidence_payload_kit_output")
    return out


def sanitized_evidence_assisted_payload_production_kit(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(evidence 본문·query 초안·명령·acceptance 기준 제외·status/count/
    honesty flag 만)."""
    return {
        "evidence_payload_kit_status": out["evidence_payload_kit_status"],
        "contract_version": out["contract_version"],
        "selected_candidate_id": out["selected_candidate_id"],
        "official_evidence_required_count": out["official_evidence_required_count"],
        "news_evidence_required_count": out["news_evidence_required_count"],
        "kit_is_payload": out["kit_is_payload"],
        "kit_can_trigger_live": out["kit_can_trigger_live"],
        "operator_confirmed": out["operator_confirmed"],
        "live_approved": out["live_approved"],
        "same_event_asserted": out["same_event_asserted"],
        "code_claims_event_occurred": out["code_claims_event_occurred"],
        "network_invoked": out["network_invoked"],
        "production_gold_count": out["production_gold_count"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#95 §9(B) evidence-assisted payload production kit (operator-actionable EVIDENCE-REQUIREMENTS "
                     "kit; NOT a payload·live 트리거 0·event 발생 단정 0·network 0)."))
    parser.add_argument("--candidate-id", default=None,
                        help="준비할 후보 id(미지정 시 기본 epa_final_rule_emissions).")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(evidence 본문/명령 제외).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_evidence_assisted_payload_production_kit(selected_candidate_id=ns.candidate_id)
    if ns.json:
        print(json.dumps(sanitized_evidence_assisted_payload_production_kit(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['evidence_payload_kit_status']}")
    print(f"- candidate: {out['selected_candidate_id']} agency_or_entity={out['agency_or_entity_required']!r}")
    print(f"- official_evidence_required ({out['official_evidence_required_count']}):")
    for ev in out["official_evidence_required"]:
        print(f"    provider={ev['provider']} query={ev['query']!r} document_type={ev['document_type']!r}")
        print(f"    acceptance: {ev['acceptance_criteria']}")
    print(f"- news_evidence_required ({out['news_evidence_required_count']}):")
    for ev in out["news_evidence_required"]:
        print(f"    provider={ev['provider']} query={ev['query']!r} angle={ev['expected_news_angle']!r}")
        print(f"    acceptance: {ev['acceptance_criteria']}")
    print(f"- source_role_requirements: {out['source_role_requirements']}")
    print(f"- date_window_required: {out['date_window_required']}")
    print(f"- real_payload_path: {out['real_payload_path']} (this kit is NOT a real payload)")
    print(f"- validation_command: {out['validation_command']}")
    print(f"- live_command: {out['live_command']}")
    print(f"- invariants: kit_is_payload={out['kit_is_payload']} kit_can_trigger_live={out['kit_can_trigger_live']} "
          f"operator_confirmed={out['operator_confirmed']} live_approved={out['live_approved']} "
          f"same_event_asserted={out['same_event_asserted']} "
          f"code_claims_event_occurred={out['code_claims_event_occurred']} network_invoked={out['network_invoked']}")
    print(f"- operator_next_action: {out['operator_next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
