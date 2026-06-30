"""ADR#95 §10 (option C) — operator verification worksheet (HUMAN-fills·외부 검증 구조·코드가 confirm/approve 0·network 0).

문제(ADR#94 연속·R-OperatorConfirmedEventScarcity): operator_confirmed_ready_package 는 "operator 가 외부에서 무엇을
검증하면 real payload 로 옮길 준비가 되는가"를 묶어 주지만, **official source 검증**과 **news coverage 검증**이 한 줄
지시문으로 뭉쳐 있어 *각각을 따로 기록*할 구조가 없다 — operator 가 official 기록과 news 보도를 같은 칸에 섞어 "확인함"
처리하면 same-day unrelated 보도가 official 검증으로 둔갑할 수 있다(ADR#84 date-window fidelity gap 의 사람 측 재현).

이 모듈은 그 구조다 — 사람이 채우는 **검증 worksheet**. 핵심:
  - **official-source 검증과 news-coverage 검증을 구조적으로 분리**(official_source_check ≠ news_coverage_check).
    각 check 는 {item(무엇을), instruction(어떻게), record_slot(operator 가 채울 빈칸), confirmed=False} 의 dict.
  - **worksheet 완료 ≠ 확정**: worksheet 가 모두 채워져도 코드는 operator_confirmed/live_approved 를 **절대** True 로
    두지 않는다(code_sets_operator_confirmed_true=False·code_sets_live_approved_true=False). 완료는
    worksheet_status=WORKSHEET_COMPLETE 일 뿐 *그 사건이 일어났다/같은 사건이다* 가 아니다(same_event_asserted=False).
  - **payload 아님·live 트리거 0**: 이 worksheet 는 real payload 가 아니고(worksheet_is_payload=False),
    acquisition_fn 을 받지 않으며 live runner 를 호출하지 않는다(network_invoked=False).
  - candidate 필드(agency/action/official_query/news_query/date_window)는 regulatory seed bank(PURE)에서 읽고,
    operator 가 최종 채워야 하는 12개 필드는 operator_regulatory_event_intake.OPERATOR_EVENT_REQUIRED_FIELDS 단일 출처.
  - secret/PII 0(`_assert_pii_safe` 재귀 가드) · merge 0 · LLM/embedding 0 · DB 0 · 전송 0 · production gold 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.operator_regulatory_event_intake import OPERATOR_EVENT_REQUIRED_FIELDS
from backend.app.tools.regulatory_event_seed_bank import build_regulatory_event_seed_bank
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "operator_verification_worksheet"
CONTRACT_VERSION = "operator_verification_worksheet_v1"

# worksheet_status(2-state) — 완료조차 확정이 아님(이름이 그 사실을 못 박는다).
WORKSHEET_INCOMPLETE = "worksheet_incomplete_operator_must_verify"
WORKSHEET_COMPLETE = "worksheet_complete_still_not_confirmation"

# 기본 candidate(seed bank 의 selected epa seed) — operator 가 --candidate-id 로 다른 seed 선택 가능.
_DEFAULT_CANDIDATE_ID = "epa_final_rule_emissions"


def _seed_for_candidate(candidate_id: Optional[str]) -> dict:
    """regulatory seed bank(PURE)에서 candidate_id 에 맞는 seed shape 를 읽는다(query/window 표시용·값 하드코딩 0).

    candidate_id 가 bank 에 있으면 그 seed, 없으면 epa_final_rule_emissions, 그래도 없으면 selected/빈 dict."""
    bank = build_regulatory_event_seed_bank()
    seed_bank = bank.get("seed_bank") or []
    seed = None
    if candidate_id:
        seed = next((s for s in seed_bank if s.get("seed_id") == candidate_id), None)
    if seed is None:
        seed = next((s for s in seed_bank if s.get("seed_id") == _DEFAULT_CANDIDATE_ID), None)
    if seed is None:
        seed = bank.get("selected_seed_for_next_live_run")
    return seed if isinstance(seed, dict) else {}


def _build_check(item: str, instruction: str, provided: Optional[dict]) -> dict:
    """단일 검증 항목을 {item, instruction, record_slot, confirmed} dict 로. record_slot 은 operator 가 채울 빈칸.

    caller 가 채운 dict(provided)를 주면 record_slot/confirmed 를 **알려진 필드만** 반영한다(임의 키 echo 0 — PII 가드).
    record_slot/confirmed 가 없으면 빈칸 템플릿(record_slot=""·confirmed=False)."""
    record_slot = ""
    confirmed = False
    if isinstance(provided, dict):
        record_slot = str(provided.get("record_slot") or "")
        confirmed = provided.get("confirmed") is True
    return {
        "item": item,
        "instruction": instruction,
        "record_slot": record_slot,
        "confirmed": confirmed,
    }


def _is_satisfied(check: dict) -> bool:
    """check 가 충족됐는가 — confirmed==True **그리고** record_slot 이 비어있지 않을 때만(빈칸 confirm 둔갑 차단)."""
    return check.get("confirmed") is True and bool(str(check.get("record_slot") or "").strip())


def build_operator_verification_worksheet(
    *, candidate_id: Optional[str] = None, official_check: Optional[dict] = None,
    news_coverage_check: Optional[dict] = None, date_window_check: Optional[dict] = None,
) -> dict:
    """ADR#95 §10 operator 가 외부에서 사건 발생을 검증하는 worksheet(official↔news 분리·완료해도 확정 아님·network 0).

    official-source 검증과 news-coverage 검증을 구조적으로 분리한 check dict 들과, 추가 식별/날짜/role check, operator 가
    최종 채워야 하는 12개 confirmation 필드(OPERATOR_EVENT_REQUIRED_FIELDS), 미해결 질문을 묶는다. caller 가
    official_check/news_coverage_check/date_window_check 를 주면 그 check 는 **confirmed==True ∧ record_slot 비어있지
    않을 때만** 충족으로 본다. 셋 모두 충족 → completion_status=complete·worksheet_status=WORKSHEET_COMPLETE. 그래도
    코드는 operator_confirmed/live_approved 를 절대 True 로 두지 않는다(완료 ≠ 확정). payload 아님·live 트리거 0·secret/PII 0."""
    seed = _seed_for_candidate(candidate_id)
    agency = str(seed.get("agency") or "").strip()
    action_phrase = str(seed.get("action_phrase") or "").strip()
    official_query = str(seed.get("official_query") or "").strip()
    news_query = str(seed.get("news_query") or "").strip()
    start = str(seed.get("date_window_start") or "").strip()
    end = str(seed.get("date_window_end") or "").strip()
    resolved_candidate_id = str(seed.get("seed_id") or candidate_id or _DEFAULT_CANDIDATE_ID)

    # ── official-source 검증과 news-coverage 검증은 **다른 check**(같은 칸에 섞기 금지) ──
    official_source_check_out = _build_check(
        item="OFFICIAL SOURCE: an authoritative official record published this regulatory action.",
        instruction=(
            f"Search the official record (Federal Register / agency site) for {official_query!r}. Record the official "
            f"document number / citation showing {agency or 'the agency'} issued '{action_phrase or 'the action'}'. "
            "Do NOT let a news article stand in for the official record."),
        provided=official_check)
    news_coverage_check_out = _build_check(
        item="NEWS COVERAGE: at least one independent news provider reported the same event.",
        instruction=(
            f"Search news providers (guardian / nyt) for {news_query!r}. Record one article URL + headline that reports "
            "the SAME event — not merely same-day unrelated news."),
        provided=news_coverage_check)
    date_window_check_out = _build_check(
        item=f"DATE WINDOW: the occurrence date falls inside [{start or '?'}, {end or '?'}].",
        instruction=(
            f"Confirm the event occurrence date falls within [{start or '?'}, {end or '?'}]. Record the occurrence date "
            "taken from the OFFICIAL source, not an article publication date."),
        provided=date_window_check)

    # ── 추가 식별/URL/timestamp/role check(worksheet 항목이되 completion 게이트는 official+news+date 만) ──
    agency_entity_check = _build_check(
        item=f"AGENCY / ENTITY: the acting agency/entity is {agency or 'the named agency/entity'}.",
        instruction="Record the exact agency/entity name as it appears in the official record.", provided=None)
    action_phrase_check = _build_check(
        item=f"ACTION PHRASE: the action matches '{action_phrase or 'the named action'}'.",
        instruction="Record the official action title/phrase verbatim from the official record.", provided=None)
    canonical_url_check = _build_check(
        item="CANONICAL URL: a stable canonical official-source URL exists for this action.",
        instruction="Paste the stable canonical URL of the official document (not a search-results page).", provided=None)
    published_at_check = _build_check(
        item="PUBLISHED-AT: the official publication/effective timestamp is recorded.",
        instruction="Record the official published/effective date (ISO YYYY-MM-DD) from the source record.", provided=None)
    source_role_check = _build_check(
        item="SOURCE ROLE: official source and news coverage are kept as separate roles.",
        instruction=(
            "Confirm the official record is treated as authoritative evidence and news as public reporting — they are "
            "NOT merged into one same-role same-event claim."),
        provided=None)

    # completion 게이트: official + news + date_window **셋 모두** 충족일 때만 complete(나머지 check 는 기록용).
    all_satisfied = (
        _is_satisfied(official_source_check_out)
        and _is_satisfied(news_coverage_check_out)
        and _is_satisfied(date_window_check_out))
    completion_status = "complete" if all_satisfied else "incomplete"
    worksheet_status = WORKSHEET_COMPLETE if all_satisfied else WORKSHEET_INCOMPLETE

    # operator 가 외부 검증 후에도 남는 정직한 미해결 질문(non-empty) — 완료가 발생/같은 사건을 단정하지 않음을 못 박는다.
    unresolved_questions = [
        ("Did the event ACTUALLY occur? Worksheet completion records verification steps but does not assert occurrence — "
         "the operator must verify it externally."),
        "Are the official record and the news coverage about the SAME event, or merely same-day but unrelated items?",
        "Does the occurrence date fall strictly inside the stated window, or is only an article publication date inside it?",
        "Is the news coverage independent reporting, or a syndication/aggregation of a single wire item?",
    ]

    out = {
        # ── lead ──
        "operation_name": OPERATION_NAME,
        "contract_version": CONTRACT_VERSION,
        "worksheet_status": worksheet_status,
        # ── candidate identity ──
        "candidate_id": resolved_candidate_id,
        # ── §10 checks(official ↔ news 구조 분리) ──
        "official_source_check": official_source_check_out,
        "news_coverage_check": news_coverage_check_out,
        "date_window_check": date_window_check_out,
        "agency_entity_check": agency_entity_check,
        "action_phrase_check": action_phrase_check,
        "canonical_url_check": canonical_url_check,
        "published_at_check": published_at_check,
        "source_role_check": source_role_check,
        # ── operator 가 최종 채워야 하는 12개 confirmation 필드(단일 출처) + 미해결 질문 ──
        "operator_confirmation_fields": list(OPERATOR_EVENT_REQUIRED_FIELDS),
        "unresolved_questions": unresolved_questions,
        "completion_status": completion_status,
        # ── 불변(정직·constant·완료해도 확정 아님·코드가 confirm/approve 0) ──
        "worksheet_is_payload": False,
        "worksheet_complete_auto_confirms": False,
        "code_sets_operator_confirmed_true": False,
        "code_sets_live_approved_true": False,
        "operator_confirmed": False,
        "live_approved": False,
        "same_event_asserted": False,
        "network_invoked": False,
        "production_gold_count": 0,
    }
    _assert_pii_safe(out, _path="operator_verification_worksheet_output")
    return out


def sanitized_operator_verification_worksheet(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(check 본문 제외·status/완료/불변 flag·count 만)."""
    return {
        "contract_version": out["contract_version"],
        "worksheet_status": out["worksheet_status"],
        "candidate_id": out["candidate_id"],
        "completion_status": out["completion_status"],
        "operator_confirmation_field_count": len(out["operator_confirmation_fields"]),
        "unresolved_question_count": len(out["unresolved_questions"]),
        "worksheet_is_payload": out["worksheet_is_payload"],
        "worksheet_complete_auto_confirms": out["worksheet_complete_auto_confirms"],
        "code_sets_operator_confirmed_true": out["code_sets_operator_confirmed_true"],
        "code_sets_live_approved_true": out["code_sets_live_approved_true"],
        "operator_confirmed": out["operator_confirmed"],
        "live_approved": out["live_approved"],
        "same_event_asserted": out["same_event_asserted"],
        "network_invoked": out["network_invoked"],
        "production_gold_count": out["production_gold_count"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#95 §10 operator verification worksheet (HUMAN-fills; official↔news 검증 분리·완료해도 확정 "
                     "아님·코드가 operator_confirmed/live_approved 0·payload 아님·network 0)."))
    parser.add_argument("--candidate-id", default=None,
                        help="검증할 후보 seed id(미지정 시 기본 epa_final_rule_emissions).")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(check 본문 제외).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_operator_verification_worksheet(candidate_id=ns.candidate_id)
    if ns.json:
        print(json.dumps(sanitized_operator_verification_worksheet(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} ({out['contract_version']}) status={out['worksheet_status']}")
    print(f"- candidate_id: {out['candidate_id']} completion_status={out['completion_status']}")
    print("- checks (operator fills record_slot; official ↔ news kept separate):")
    for key in ("official_source_check", "news_coverage_check", "date_window_check", "agency_entity_check",
                "action_phrase_check", "canonical_url_check", "published_at_check", "source_role_check"):
        c = out[key]
        print(f"    {key:<22} confirmed={c['confirmed']!s:<5} item={c['item']}")
    print(f"- operator_confirmation_fields ({len(out['operator_confirmation_fields'])}): "
          f"{out['operator_confirmation_fields']}")
    print(f"- unresolved_questions ({len(out['unresolved_questions'])}):")
    for q in out["unresolved_questions"]:
        print(f"    - {q}")
    print(f"- invariants: worksheet_is_payload={out['worksheet_is_payload']} "
          f"worksheet_complete_auto_confirms={out['worksheet_complete_auto_confirms']} "
          f"operator_confirmed={out['operator_confirmed']} live_approved={out['live_approved']} "
          f"code_sets_operator_confirmed_true={out['code_sets_operator_confirmed_true']} "
          f"code_sets_live_approved_true={out['code_sets_live_approved_true']} "
          f"same_event_asserted={out['same_event_asserted']} network_invoked={out['network_invoked']} "
          f"production_gold_count={out['production_gold_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
