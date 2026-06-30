"""ADR#95 §12 (option E) — first-payload candidate evidence-TO-VERIFY binder (검증 대상 묶음·확정 아님·payload 아님·network 0).

문제(ADR#94 연속·R-OperatorConfirmedEventScarcity): operator_confirmed_ready_package 는 후보를 promote 하기 위한
PRE-payload 묶음을 주지만, "이 후보(epa_final_rule_emissions)를 real payload 로 옮기기 전에 **무엇을 증거로 직접
검증해야 하고, 어떤 질문이 아직 미해결인가**"를 official/news 로 **분리**해 담은 binder 가 한 곳에 없었다.

이 모듈이 그 binder 다(regulatory seed bank PURE 위 thin 합성·재구현 0). 핵심 정직성:
  - **이 binder 는 확정이 아니다**(binder_is_confirmation=False): 사건이 일어났다고 단정하지 않는다
    (binder_claims_event_occurred=False·event_occurrence_verified=False).
  - **이 binder 는 payload 가 아니다**(binder_is_payload=False)·**live 를 트리거할 수 없다**
    (binder_can_trigger_live=False·acquisition_fn 0·live runner 호출 0·network_invoked=False).
  - query 는 **초안**일 뿐 truth 가 아니다(query_drafts_are_not_truth=True) — seed bank 의 official_query/news_query
    를 검증 대상으로 노출하되 official(=evidence)·news(=reporting) role 을 분리한다(같은 role 로 섞지 않음).
  - date window 는 code-proposed·UNVERIFIED 이며 operator 가 실제 발생일을 확인해야 한다.
  - **미해결 질문을 반드시 표면화**(unresolved_questions 비어 있지 않음)하고 expected_failure_modes 로
    수집 단계 실패(out-of-window·overlap 0·title 발산)를 미리 드러낸다.

절대 불변: same_event 단정 0 · merge 0 · LLM/embedding 0 · DB 0 · 전송 0 · secret/PII 0(`_assert_pii_safe` 재귀 가드) ·
production gold 증가 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.regulatory_event_seed_bank import build_regulatory_event_seed_bank
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "first_payload_candidate_evidence_binder"
CONTRACT_VERSION = "first_payload_candidate_evidence_binder_v1"

# first_payload_evidence_binder_status.
BINDER_READY = "evidence_binder_ready"          # 후보 seed 있음 → operator 가 검증할 evidence binder 산출.
BINDER_NO_CANDIDATE = "no_candidate_to_bind"    # 일치하는 후보 seed 없음(잘못된 candidate id).

# 기본 후보(ADR#95 §12 option E) — operator 가 다른 id 를 주지 않으면 EPA final rule.
DEFAULT_CANDIDATE_ID = "epa_final_rule_emissions"


def _find_seed(candidate_id: str) -> Optional[dict]:
    """regulatory seed bank(PURE)에서 candidate_id 에 해당하는 seed 를 읽는다(값 하드코딩 0·없으면 None)."""
    bank = build_regulatory_event_seed_bank()
    seed_bank = bank.get("seed_bank") or []
    seed = next((s for s in seed_bank if s.get("seed_id") == candidate_id), None)
    return seed if isinstance(seed, dict) else None


def build_first_payload_candidate_evidence_binder(
    *, selected_candidate_id: Optional[str] = None,
) -> dict:
    """first-payload 후보의 evidence-TO-VERIFY binder 를 산출(network 0·disk write 0·live 트리거 0).

    seed bank 에서 후보 요약·official/news query 초안·date window·risk 를 읽어 official(=evidence)·news(=reporting)
    검증 대상을 **분리**해 담고, 미해결 질문·예상 실패 모드·다음 query 조정안을 표면화한다. 이 binder 는 **확정도
    payload 도 아니다** — 사건 발생을 단정하지 않고(binder_claims_event_occurred=False), live 를 트리거할 수 없으며
    (binder_can_trigger_live=False·network_invoked=False), query 는 초안일 뿐 truth 가 아니다. secret/PII 0
    (`_assert_pii_safe`)."""
    candidate_id = (selected_candidate_id or DEFAULT_CANDIDATE_ID)
    seed = _find_seed(candidate_id)
    has_candidate = seed is not None
    seed = seed or {}

    # seed 값 추출(없으면 빈 값·collection shape 일 뿐 발생/같은 사건 단정 0).
    agency = str(seed.get("agency") or "")
    entity = str(seed.get("entity") or "")
    action_phrase = str(seed.get("action_phrase") or "")
    document_type = str(seed.get("document_type") or "")
    official_provider = str(seed.get("official_provider") or "")
    news_providers = list(seed.get("news_providers") or [])
    official_query = str(seed.get("official_query") or "")
    news_query = str(seed.get("news_query") or "")
    expected_overlap_tokens = list(seed.get("expected_overlap_tokens") or [])
    expected_news_angle = str(seed.get("expected_news_angle") or "")
    risk = str(seed.get("risk") or "")
    start = str(seed.get("date_window_start") or "")
    end = str(seed.get("date_window_end") or "")
    source_role_policy = str(seed.get("source_role_policy") or "")

    status = BINDER_READY if has_candidate else BINDER_NO_CANDIDATE

    if has_candidate:
        candidate_summary = (
            f"{candidate_id}: {agency or 'UNSPECIFIED'} — {action_phrase or 'UNSPECIFIED'} "
            f"(code-proposed window {start or '?'}..{end or '?'}); this is an evidence-TO-VERIFY binder, NOT a "
            "confirmation — code has NOT verified the event occurred.")
    else:
        candidate_summary = (
            f"{candidate_id}: no matching candidate seed in the regulatory event seed bank — nothing to bind.")

    # ── official(=evidence) 검증 대상: FR 공식 record(query 는 초안·truth 아님) ──
    official_evidence_to_verify = {
        "provider": official_provider,
        "official_query_draft": official_query,
        "agency": agency,
        "document_type": document_type,
        "expected_overlap_tokens": expected_overlap_tokens,
        "what_to_confirm": (
            "Confirm the Federal Register actually published this regulatory document (agency + document_type) "
            "within the date window — code has NOT verified this; the query is a DRAFT, not truth."),
    }

    # ── news(=reporting) 검증 대상: publishable news 보도(official 과 같은 role 로 섞지 않음) ──
    news_evidence_to_verify = {
        "providers": news_providers,
        "news_query_draft": news_query,
        "expected_news_angle": expected_news_angle,
        "action_phrase": action_phrase,
        "what_to_confirm": (
            "Confirm at least one news provider (guardian/nyt) reported the SAME event in the SAME window with "
            "overlapping entity tokens — code has NOT verified this; the query is a DRAFT, not truth."),
    }

    date_window_to_verify = {
        "start": start,
        "end": end,
        "note": "code-proposed unverified, operator must confirm actual date",
    }

    agency_entity_to_verify = {
        "code_proposed_agency": agency,
        "code_proposed_entity": entity,
        "what_to_confirm": (
            "Confirm the actual agency and named entity in the official/news records match these code-proposed "
            "values (operator must verify)."),
    }

    action_phrase_to_verify = {
        "code_proposed_action_phrase": action_phrase,
        "what_to_confirm": (
            "Confirm the actual regulatory action matches this phrase — official and news titles may diverge."),
    }

    # canonical_url / published_at 은 seed 에 없다 — operator 가 실제 record 에서 채워야 한다(code 보유 0).
    canonical_url_to_verify = {
        "value": None,
        "what_to_confirm": (
            "Operator must capture the actual canonical URL of the official document and of the news article — "
            "code has none."),
    }
    published_at_to_verify = {
        "value": None,
        "what_to_confirm": (
            "Operator must capture the actual published_at timestamps and confirm both fall inside the date "
            "window — code has none."),
    }

    expected_failure_modes = [
        {"mode": "official_out_of_window",
         "detail": "the Federal Register document is published outside the requested date window"},
        {"mode": "news_out_of_window",
         "detail": "the news article is published outside the requested date window"},
        {"mode": "no_entity_overlap",
         "detail": "news and official records share no entity/overlap tokens (different subject)"},
        {"mode": "title_token_divergence",
         "detail": risk or "news framing and official rule text may use divergent title tokens"},
    ]

    next_query_adjustments = [
        "If official_out_of_window: re-pin the Federal Register window to the operator-confirmed effective date "
        "(replace the code-proposed window).",
        "If no_entity_overlap: add an overlap token from expected_overlap_tokens (e.g. 'standards') to the news "
        "query to tighten same-subject matching.",
        "If title_token_divergence: query the news angle phrase instead of the dry official rule text.",
        "If zero in-window official records: widen the window by +/-1 day around the confirmed date before "
        "broadening the query.",
    ]

    unresolved_questions = [
        "Did this regulatory event actually occur, and on what EXACT date? (code has NOT verified — the date "
        "window is code-proposed, UNVERIFIED).",
        "Does the Federal Register actually carry this document (agency + document_type) within the window?",
        "Did guardian or nyt report the same event in the same window?",
        "What is the canonical URL and published_at of each actual record? (operator must capture — code has none).",
        "Do the official and news records refer to the SAME event? (same_event is NOT asserted by code).",
    ]
    if not has_candidate:
        unresolved_questions = [
            f"No seed matched candidate id {candidate_id!r} — which candidate should be bound?",
        ] + unresolved_questions

    out = {
        "operation_name": OPERATION_NAME,
        "contract_version": CONTRACT_VERSION,
        "first_payload_evidence_binder_status": status,
        # ── 후보 identity + evidence-TO-VERIFY(official/news 분리·query 는 초안·truth 아님) ──
        "candidate_id": candidate_id,
        "candidate_summary": candidate_summary,
        "official_evidence_to_verify": official_evidence_to_verify,
        "news_evidence_to_verify": news_evidence_to_verify,
        "date_window_to_verify": date_window_to_verify,
        "agency_entity_to_verify": agency_entity_to_verify,
        "action_phrase_to_verify": action_phrase_to_verify,
        "canonical_url_to_verify": canonical_url_to_verify,
        "published_at_to_verify": published_at_to_verify,
        "source_role_notes": source_role_policy,
        "expected_failure_modes": expected_failure_modes,
        "next_query_adjustments": next_query_adjustments,
        "unresolved_questions": unresolved_questions,
        # ── 불변(정직·constant·THIS IS NOT A CONFIRMATION / NOT A PAYLOAD) ──
        "binder_is_confirmation": False,
        "binder_is_payload": False,
        "binder_can_trigger_live": False,
        "binder_claims_event_occurred": False,
        "query_drafts_are_not_truth": True,
        "same_event_asserted": False,
        "event_occurrence_verified": False,
        "network_invoked": False,
        "production_gold_count": 0,
    }
    _assert_pii_safe(out, _path="first_payload_evidence_binder_output")
    return out


def sanitized_first_payload_candidate_evidence_binder(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(query 초안·요약·검증 텍스트 제외·status/count/honesty flag 만)."""
    return {
        "operation_name": out["operation_name"],
        "contract_version": out["contract_version"],
        "first_payload_evidence_binder_status": out["first_payload_evidence_binder_status"],
        "candidate_id": out["candidate_id"],
        "official_provider": out["official_evidence_to_verify"]["provider"],
        "news_providers": list(out["news_evidence_to_verify"]["providers"]),
        "expected_failure_mode_count": len(out["expected_failure_modes"]),
        "next_query_adjustment_count": len(out["next_query_adjustments"]),
        "unresolved_question_count": len(out["unresolved_questions"]),
        "binder_is_confirmation": out["binder_is_confirmation"],
        "binder_is_payload": out["binder_is_payload"],
        "binder_can_trigger_live": out["binder_can_trigger_live"],
        "binder_claims_event_occurred": out["binder_claims_event_occurred"],
        "query_drafts_are_not_truth": out["query_drafts_are_not_truth"],
        "same_event_asserted": out["same_event_asserted"],
        "event_occurrence_verified": out["event_occurrence_verified"],
        "network_invoked": out["network_invoked"],
        "production_gold_count": out["production_gold_count"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#95 §12 first-payload candidate evidence-TO-VERIFY binder (확정 아님·payload 아님·live "
                     "트리거 0·query 초안일 뿐 truth 아님·network 0)."))
    parser.add_argument("--candidate-id", default=None,
                        help="bind 할 후보 id(미지정 시 기본 epa_final_rule_emissions).")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(query 초안/검증 텍스트 제외).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_first_payload_candidate_evidence_binder(selected_candidate_id=ns.candidate_id)
    if ns.json:
        print(json.dumps(sanitized_first_payload_candidate_evidence_binder(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} ({out['contract_version']}) "
          f"status={out['first_payload_evidence_binder_status']}")
    print(f"- candidate: {out['candidate_id']}")
    print(f"- candidate_summary: {out['candidate_summary']}")
    print(f"- official_evidence_to_verify: provider={out['official_evidence_to_verify']['provider']!r} "
          f"query_draft={out['official_evidence_to_verify']['official_query_draft']!r}")
    print(f"- news_evidence_to_verify: providers={out['news_evidence_to_verify']['providers']} "
          f"query_draft={out['news_evidence_to_verify']['news_query_draft']!r}")
    print(f"- date_window_to_verify: {out['date_window_to_verify']}")
    print(f"- source_role_notes: {out['source_role_notes']}")
    print("- expected_failure_modes:")
    for fm in out["expected_failure_modes"]:
        print(f"    {fm['mode']}: {fm['detail']}")
    print("- unresolved_questions:")
    for q in out["unresolved_questions"]:
        print(f"    - {q}")
    print(f"- invariants: binder_is_confirmation={out['binder_is_confirmation']} "
          f"binder_is_payload={out['binder_is_payload']} binder_can_trigger_live={out['binder_can_trigger_live']} "
          f"binder_claims_event_occurred={out['binder_claims_event_occurred']} "
          f"query_drafts_are_not_truth={out['query_drafts_are_not_truth']} "
          f"network_invoked={out['network_invoked']} production_gold_count={out['production_gold_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
