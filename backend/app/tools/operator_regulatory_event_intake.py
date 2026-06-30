"""ADR#88 — operator-confirmed regulatory event intake (code_proposed → operator_confirmed gate · live 차단 · merge 0).

ADR#87 이 만든 것: regulatory-class **code_proposed** seed bank + official×news live acquisition engine
(`run_official_news_live_acquisition`) + freeze 경로(결정론 검증). 그러나 그 engine 은 seed 의 *shape* 만 검증할 뿐
**operator 가 실제 발생한 regulatory event 를 확인했는지** 를 묻지 않는다 — code_proposed seed("operator fills"
template·발생 미확인)가 그대로 live 로 갈 자리가 남는다(§2: operator 확인 없는 seed 로 live 후 confirmed 둔갑 금지).

이 모듈은 그 **operator gate** 다(engine 재구현 0·wrapper). engine(`run_official_news_live_acquisition`)은 무수정으로
ADR#87 byte-identical 보존하고, 이 gate 가:
  - §8 operator-confirmed event payload(named agency/entity·specific action·ISO date window·official_query≠news_query·
    expected_news_angle·live_approved)를 **결정론으로 검증**(placeholder/generic/broad reject·same_event 단정 reject),
  - confirmation_valid ∧ live_approved 일 때만 operator-confirmed seed 를 build(provenance=operator_confirmed_event)해
    engine 을 호출하고, 아니면 live 를 **호출하지 않고** blocked 를 정직히 산출한다(§9 2-state 추가):
      · blocked_operator_not_confirmed(operator_confirmed≠true)
      · blocked_invalid_confirmation(필드 무효/placeholder/broad/same_event 단정/shape 무효).

절대 불변(상속·상용 안전 계약):
  - **code_proposed ≠ operator_confirmed**: provenance 로 분리(code_proposed_regulatory_shape vs operator_confirmed_event).
    code_proposed seed 는 이 gate 를 통과하지 못하면 live 로 못 간다(operator 확인 없이 live 금지).
  - **operator confirmation ≠ truth**: operator_confirmed=True 는 "operator 가 live-run 을 승인" 일 뿐 *그 사건이
    일어났다/official 과 news 가 같은 사건이다* 가 아니다(same_event_asserted=False·event_occurrence_verified_by_code=
    False·R-OperatorConfirmationAsTruthLeakage). bridge candidate/freeze 는 여전히 reviewer worklist(gold 0).
  - **merge 0 · LLM/embedding 0 · DB 0 · 전송 0 · secret read 0 · raw body 0 · public IU 0 · score 0**.
  test: payload 주입 + acquisition_fn(fake) 주입 시 결정론(network 0·실 `.env` 미접촉).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any, Callable, Optional

# named_event_seed_bank 단일 출처(ISO date·정규화 재사용·재구현 0).
from backend.app.tools.named_event_seed_bank import _ISO_DATE, _norm
from backend.app.tools.official_news_live_acquisition import (
    run_official_news_live_acquisition,
)
from backend.app.tools.regulatory_event_seed_bank import (
    _BROAD_DENYLIST,
    _is_placeholder,
    build_regulatory_event_seed_bank,
    validate_regulatory_seed,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "operator_regulatory_event_intake"

# ── seed provenance(§7.5 code_proposed vs operator_confirmed 분리) ─────────────────────────────────────────
PROVENANCE_CODE_PROPOSED = "code_proposed_regulatory_shape"
PROVENANCE_OPERATOR_CONFIRMED = "operator_confirmed_event"

# ── operator_event_status(intake 축·5-state·official_news_live_status 와 직교) ────────────────────────────
OPERATOR_EVENT_NOT_PROVIDED = "not_provided"               # payload 없음(이번 턴 기본·정직).
OPERATOR_EVENT_NOT_CONFIRMED = "operator_not_confirmed"    # operator_confirmed≠true.
OPERATOR_EVENT_INVALID_CONFIRMATION = "invalid_confirmation"   # 필드 무효/placeholder/broad/same_event 단정.
OPERATOR_EVENT_CONFIRMED_NOT_APPROVED = "confirmed_not_approved"   # 확인 유효하나 live_approved=false.
OPERATOR_EVENT_CONFIRMED_LIVE = "confirmed_live_executed"  # 확인 유효 ∧ live_approved → engine 호출.
OPERATOR_EVENT_STATES = frozenset({
    OPERATOR_EVENT_NOT_PROVIDED, OPERATOR_EVENT_NOT_CONFIRMED, OPERATOR_EVENT_INVALID_CONFIRMATION,
    OPERATOR_EVENT_CONFIRMED_NOT_APPROVED, OPERATOR_EVENT_CONFIRMED_LIVE,
})

# ── official_news_live_status §9 operator gate 추가 어휘(ADR#87 9-state 앞단·둔갑 0) ──────────────────────
ONL_BLOCKED_OPERATOR_NOT_CONFIRMED = "blocked_operator_not_confirmed"
ONL_BLOCKED_INVALID_CONFIRMATION = "blocked_invalid_confirmation"
ONL_BLOCKED_NO_OPT_IN = "blocked_no_live_opt_in"   # ADR#87 와 동일 토큰(confirmed 이나 미승인).

# ── §8 required fields ─────────────────────────────────────────────────────────────────────────────────────
OPERATOR_EVENT_REQUIRED_FIELDS: tuple[str, ...] = (
    "seed_id", "operator_confirmed", "confirmed_by", "confirmed_at",
    "agency_or_entity", "action_phrase", "date_window_start", "date_window_end",
    "official_query", "news_query", "expected_news_angle", "live_approved",
)

# operator-특화 generic 어휘(agency/action 이 named 아님·broad denylist 와 합집합).
_GENERIC_OPERATOR_TERMS: frozenset[str] = frozenset({
    "agency", "regulator", "government", "the government", "federal agency", "an agency", "the agency",
    "regulatory action", "enforcement action", "agency action", "rulemaking",
})
_OPERATOR_BROAD_DENYLIST = _BROAD_DENYLIST | _GENERIC_OPERATOR_TERMS


def _is_iso_date_or_datetime(text: Optional[str]) -> bool:
    """confirmed_at 이 ISO date(YYYY-MM-DD) 또는 ISO datetime 인가(§8). 빈값/형식불명=False."""
    t = (text or "").strip()
    if not t:
        return False
    if _ISO_DATE.match(t):
        return True
    try:
        datetime.fromisoformat(t.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _is_broad(value: str) -> bool:
    """정규화 후 operator broad/generic denylist 단독 매치인가(named 아님)."""
    n = _norm(value)
    return bool(n) and n in _OPERATOR_BROAD_DENYLIST


def validate_operator_confirmed_event(payload: dict) -> dict:
    """§8 operator-confirmed regulatory event payload → 결정론 검증(placeholder/generic/broad/same_event 단정 reject).

    confirmation_valid=True 는 'operator 가 이 regulatory event 로 bounded live-run 을 승인했다' 는 운영 게이트일 뿐
    *그 사건이 일어났다/official 과 news 가 같은 사건이다* 가 아니다(same_event_asserted=False·event_occurrence_
    verified_by_code=False). bank/network 불필요(순수)."""
    reasons: list[str] = []

    operator_confirmed = bool(payload.get("operator_confirmed") is True)
    confirmed_by = str(payload.get("confirmed_by") or "").strip()
    confirmed_at = str(payload.get("confirmed_at") or "").strip()
    agency_or_entity = str(payload.get("agency_or_entity") or "").strip()
    action_phrase = str(payload.get("action_phrase") or "").strip()
    start = str(payload.get("date_window_start") or "").strip()
    end = str(payload.get("date_window_end") or "").strip()
    official_query = str(payload.get("official_query") or "").strip()
    news_query = str(payload.get("news_query") or "").strip()
    expected_news_angle = str(payload.get("expected_news_angle") or "").strip()
    live_approved_present = "live_approved" in payload
    live_approved = bool(payload.get("live_approved") is True)

    # ① operator_confirmed(live 실행의 전제).
    if not operator_confirmed:
        reasons.append("operator_not_confirmed")
    # ② confirmed_by(non-empty).
    if not confirmed_by:
        reasons.append("missing_confirmed_by")
    # ③ confirmed_at(ISO date/datetime).
    if not confirmed_at:
        reasons.append("missing_confirmed_at")
    elif not _is_iso_date_or_datetime(confirmed_at):
        reasons.append("confirmed_at_not_iso")
    # ④ agency_or_entity(named·placeholder 아님·generic 아님).
    if not agency_or_entity:
        reasons.append("missing_agency_or_entity")
    elif _is_placeholder(agency_or_entity):
        reasons.append("placeholder_agency_or_entity")
    elif _is_broad(agency_or_entity):
        reasons.append("generic_agency_or_entity")
    # ⑤ action_phrase(specific·generic 아님).
    if not action_phrase:
        reasons.append("missing_action_phrase")
    elif _is_broad(action_phrase):
        reasons.append("generic_action_phrase")
    # ⑥ date window(ISO start+end·start≤end).
    if not (start and end):
        reasons.append("missing_date_window")
    elif not (_ISO_DATE.match(start) and _ISO_DATE.match(end)):
        reasons.append("date_window_not_iso")
    elif start > end:
        reasons.append("date_window_start_after_end")
    # ⑦ official_query / news_query(non-empty·분리 허용).
    if not official_query:
        reasons.append("missing_official_query")
    if not news_query:
        reasons.append("missing_news_query")
    # ⑧ expected_news_angle(non-empty).
    if not expected_news_angle:
        reasons.append("missing_expected_news_angle")
    # ⑨ live_approved(키 존재 — 누락 reject).
    if not live_approved_present:
        reasons.append("missing_live_approved")
    # ⑩ same_event 단정 금지(operator 가 같은 사건이라고 단정하면 reject — bridge/reviewer 가 판정).
    if bool(payload.get("same_event_asserted")) or bool(payload.get("same_event")):
        reasons.append("operator_asserted_same_event")
    # ⑪ broad/generic query(official_query/news_query 단독 broad reject).
    if official_query and _is_broad(official_query):
        reasons.append("broad_official_query")
    if news_query and _is_broad(news_query):
        reasons.append("broad_news_query")

    # confirmation_valid: 모든 §8 검증 통과(operator_confirmed 포함). live_allowed 는 추가로 live_approved 필요.
    confirmation_valid = not reasons
    live_allowed = confirmation_valid and live_approved
    return {
        "operator_confirmed": operator_confirmed,
        "confirmation_valid": confirmation_valid,
        "live_approved": live_approved,
        "live_allowed": live_allowed,
        "rejection_reasons": reasons,
        "confirmation_blocked_reason": ",".join(reasons) if reasons else "",
        "seed_provenance": PROVENANCE_OPERATOR_CONFIRMED if confirmation_valid else PROVENANCE_CODE_PROPOSED,
        # 불변 — 확인은 운영 게이트일 뿐 truth 아님.
        "same_event_asserted": False,
        "event_occurrence_verified_by_code": False,
        "reviewer_routing_only": True,
    }


def build_confirmed_seed_from_event(payload: dict, *, bank_seed: Optional[dict] = None) -> dict:
    """operator-confirmed payload → official_news_live_acquisition engine 이 소비하는 seed(provenance=operator_confirmed_
    event). regulatory_domain/official_provider/news_providers/document_type 는 payload 우선·없으면 bank_seed(같은
    seed_id 의 code_proposed template) 기본값. agency_or_entity → entity(validate_regulatory_seed 가 agency∨entity)."""
    bs = bank_seed or {}
    news_providers = payload.get("news_providers") or bs.get("news_providers") or ["guardian", "nyt"]
    return {
        "seed_id": payload.get("seed_id"),
        "regulatory_domain": payload.get("regulatory_domain") or bs.get("regulatory_domain") or "",
        "official_provider": payload.get("official_provider") or bs.get("official_provider") or "federal_register",
        "news_providers": list(news_providers),
        "agency": "",
        "entity": str(payload.get("agency_or_entity") or ""),
        "action_phrase": str(payload.get("action_phrase") or ""),
        "document_type": payload.get("document_type") or bs.get("document_type") or "Notice",
        "date_window_start": str(payload.get("date_window_start") or ""),
        "date_window_end": str(payload.get("date_window_end") or ""),
        "official_query": str(payload.get("official_query") or ""),
        "news_query": str(payload.get("news_query") or ""),
        "expected_overlap_tokens": list(bs.get("expected_overlap_tokens") or []),
        "expected_news_angle": str(payload.get("expected_news_angle") or ""),
        "source_role_policy": (
            "official=authoritative evidence · news=public reporting · NOT same role · bridge=reviewer-routing only"),
        "risk": bs.get("risk") or "operator-confirmed event (occurrence asserted by operator, not code-verified)",
        "live_run_allowed_if_approved": True,
        # ── provenance 분리(§7.5) — operator_confirmed 이나 발생/같은 사건 단정 아님 ──
        "provenance": PROVENANCE_OPERATOR_CONFIRMED,
        "operator_confirmed": True,
        "confirmed_by": str(payload.get("confirmed_by") or ""),
        "confirmed_at": str(payload.get("confirmed_at") or ""),
        "event_occurrence_verified": False,
        "operator_must_confirm_actual_event": False,
        "same_event_asserted": False,
    }


# status → operator 한 줄 next action(internal ops UI·secret 0·PII 0).
_NEXT_ACTION = {
    OPERATOR_EVENT_NOT_PROVIDED: (
        "operator must provide a confirmed regulatory event (seed_id, operator_confirmed=true, confirmed_by, "
        "confirmed_at ISO, a named agency/entity, a specific action, an ISO date window, official_query, news_query, "
        "expected_news_angle, live_approved) — code-proposed seeds cannot go live without operator confirmation"),
    OPERATOR_EVENT_NOT_CONFIRMED: (
        "set operator_confirmed=true only after confirming the event actually occurred (this is an operator "
        "live-run approval, not a same-event assertion)"),
    OPERATOR_EVENT_INVALID_CONFIRMATION: (
        "fix the operator confirmation before a live run (a named non-placeholder agency/entity, a specific "
        "non-generic action, an ISO date window, non-broad queries, and no operator same_event assertion)"),
    OPERATOR_EVENT_CONFIRMED_NOT_APPROVED: (
        "approve the bounded official×news live run (live_approved=true) — the operator event is confirmed and valid "
        "(host/rate honored · raw body 0 · secret 0)"),
    OPERATOR_EVENT_CONFIRMED_LIVE: (
        "operator: review the official×news live acquisition result; if a production candidate froze, distribute the "
        "reviewer worklist (production gold stays 0 until returned labels)"),
}


def run_operator_regulatory_event_intake(
    payload: Optional[dict] = None, *, bank: Optional[dict] = None,
    acquisition_fn: Optional[Callable[..., dict]] = None, today: Optional[str] = None,
    **acquisition_kwargs: Any,
) -> dict:
    """§8 operator-confirmed regulatory event intake gate(code_proposed → operator_confirmed·live 차단·merge 0).

    payload=None(이번 턴 기본) → operator_event_status=not_provided·live 미호출(blocked_operator_not_confirmed).
    payload 주입 시 §8 검증 → operator_confirmed≠true=blocked_operator_not_confirmed · 무효=blocked_invalid_confirmation
    · 유효하나 미승인=blocked_no_live_opt_in · 유효 ∧ live_approved → operator-confirmed seed build 후 engine 호출.
    engine(`run_official_news_live_acquisition`)은 무수정(ADR#87 보존). merge 0·LLM/embedding 0·DB 0·전송 0·secret 0."""
    acquisition_fn = acquisition_fn or run_official_news_live_acquisition
    if bank is None:
        bank = build_regulatory_event_seed_bank()

    cv: Optional[dict] = None
    acq: Optional[dict] = None
    confirmed_seed: Optional[dict] = None
    seed_id = (payload or {}).get("seed_id")
    live_approved = bool((payload or {}).get("live_approved") is True)

    if payload is None:
        status = OPERATOR_EVENT_NOT_PROVIDED
        official_news_live_status = ONL_BLOCKED_OPERATOR_NOT_CONFIRMED
        seed_provenance = PROVENANCE_CODE_PROPOSED
        confirmation_valid = False
        operator_confirmed = False
        confirmation_blocked_reason = "operator_event_not_provided"
    else:
        cv = validate_operator_confirmed_event(payload)
        operator_confirmed = bool(cv["operator_confirmed"])
        confirmation_valid = bool(cv["confirmation_valid"])
        confirmation_blocked_reason = cv["confirmation_blocked_reason"]
        seed_provenance = cv["seed_provenance"]

        # confirmed seed shape 교차 검증(regulatory_domain ∈ allowed 등 — operator 필드 검증과 직교).
        bank_seed = None
        for s in (bank.get("seed_bank") or []):
            if s.get("seed_id") == seed_id:
                bank_seed = s
                break
        if confirmation_valid:
            confirmed_seed = build_confirmed_seed_from_event(payload, bank_seed=bank_seed)
            shape = validate_regulatory_seed(confirmed_seed)
            if not shape["accepted"]:
                confirmation_valid = False
                confirmation_blocked_reason = ",".join(
                    ["shape:" + r for r in shape["rejection_reasons"]]) or "invalid_regulatory_shape"
                seed_provenance = PROVENANCE_CODE_PROPOSED

        if not operator_confirmed:
            status = OPERATOR_EVENT_NOT_CONFIRMED
            official_news_live_status = ONL_BLOCKED_OPERATOR_NOT_CONFIRMED
        elif not confirmation_valid:
            status = OPERATOR_EVENT_INVALID_CONFIRMATION
            official_news_live_status = ONL_BLOCKED_INVALID_CONFIRMATION
        elif not live_approved:
            status = OPERATOR_EVENT_CONFIRMED_NOT_APPROVED
            official_news_live_status = ONL_BLOCKED_NO_OPT_IN
        else:
            # confirmation 유효 ∧ live_approved → engine 호출(operator-confirmed seed·live_approved=True).
            acq = acquisition_fn(confirmed_seed, live_approved=True, today=today, **acquisition_kwargs)
            status = OPERATOR_EVENT_CONFIRMED_LIVE
            official_news_live_status = acq.get("official_news_live_status") or "not_run"

    live_allowed = bool(confirmation_valid and live_approved)
    blocked_reason = "" if status == OPERATOR_EVENT_CONFIRMED_LIVE else (
        confirmation_blocked_reason or official_news_live_status)
    next_action = _NEXT_ACTION.get(status, "investigate operator regulatory event intake")

    out = {
        "operation_name": OPERATION_NAME,
        "operator_event_provided": payload is not None,
        "operator_event_status": status,
        "operator_confirmed": operator_confirmed,
        "confirmation_valid": confirmation_valid,
        "confirmation_blocked_reason": confirmation_blocked_reason,
        "confirmation_rejection_reasons": list((cv or {}).get("rejection_reasons") or []),
        "seed_provenance": seed_provenance,
        "selected_seed_id": seed_id,
        "live_query_approved": live_approved,
        "live_allowed": live_allowed,
        "official_news_live_status": official_news_live_status,
        # ── code_proposed vs operator_confirmed 분리 증명(§7.5) ──
        "code_proposed_seed_provenance": PROVENANCE_CODE_PROPOSED,
        "operator_confirmed_seed_provenance": PROVENANCE_OPERATOR_CONFIRMED,
        "code_proposed_treated_as_confirmed": False,
        # ── aggregate passthrough(score/title/url 미노출) ── raw engine 결과(acq)는 **재임베드하지 않는다**:
        # acq.federal_register_live_result/official_news_bridge_result 가 record-level title/canonical_url 을 비-forbidden
        # 키명으로 보유할 수 있어 _assert_pii_safe(정확명) 가 못 잡으므로(adversarial NIT-1) 아래 count/status 만 노출한다.
        "live_query_executed": bool((acq or {}).get("live_query_executed")),
        "official_records_count": int((acq or {}).get("official_records_count") or 0),
        "news_records_count": int((acq or {}).get("news_records_count") or 0),
        "bridge_candidate_count": int((acq or {}).get("bridge_candidate_count") or 0),
        "freeze_eligible_count": int((acq or {}).get("freeze_eligible_count") or 0),
        "production_candidate_status": (acq or {}).get("production_candidate_status") or "blocked",
        "production_candidate_batch_ready": bool((acq or {}).get("production_candidate_batch_ready")),
        "production_frozen_pair_count": int((acq or {}).get("production_frozen_pair_count") or 0),
        "candidate_provenance": (acq or {}).get("candidate_provenance") or "none",
        "reviewer_handoff_ready": bool((acq or {}).get("reviewer_handoff_ready")),
        "production_gold_count": int((acq or {}).get("production_gold_count") or 0),
        "current_r1_gap": int((acq or {}).get("current_r1_gap") or 0),
        # ── 불변 경계(정직·constant + 파생) ──
        "same_event_asserted": False,
        "operator_confirmation_as_same_event_truth": False,   # 확인은 운영 게이트일 뿐 truth 아님.
        "event_occurrence_verified_by_code": False,
        "actual_sending_performed": False,
        "merge_allowed": bool((acq or {}).get("merge_allowed")),
        "llm_invoked": bool((acq or {}).get("llm_invoked")),
        "embedding_invoked": bool((acq or {}).get("embedding_invoked")),
        "db_write": bool((acq or {}).get("db_write")),
        "public_iu_allowed": False,
        "r2_r7_no_go": True,
        "blocked_reason": blocked_reason,
        "next_action": next_action,
    }
    # 전체 출력 재귀 forbidden-key 가드(score/rationale/predicted_status/raw PII/secret 어떤 depth 도 0·드리프트 fail-loud).
    _assert_pii_safe(out, _path="operator_regulatory_event_intake_output")
    return out


def sanitized_operator_intake(out: dict) -> dict:
    """snapshot/frontier 용 aggregate-only 투영(payload 본문·acq 전체 제외·status/count/flag 만)."""
    return {
        "operator_event_status": out["operator_event_status"],
        "operator_confirmed": out["operator_confirmed"],
        "confirmation_valid": out["confirmation_valid"],
        "confirmation_blocked_reason": out["confirmation_blocked_reason"],
        "seed_provenance": out["seed_provenance"],
        "selected_seed_id": out["selected_seed_id"],
        "live_allowed": out["live_allowed"],
        "official_news_live_status": out["official_news_live_status"],
        "production_candidate_status": out["production_candidate_status"],
        "reviewer_handoff_ready": out["reviewer_handoff_ready"],
        "blocked_reason": out["blocked_reason"],
        "next_action": out["next_action"],
    }


def _load_payload(path: Optional[str]) -> Optional[dict]:
    """operator event payload 를 gitignored JSON 파일에서 읽음(없으면 None — 이번 턴 기본). 코드가 생성하지 않는다."""
    if not path:
        return None
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return None
    data = p.read_text(encoding="utf-8").strip()
    return json.loads(data) if data else None


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#88 operator-confirmed regulatory event intake gate (code_proposed → operator_confirmed; "
                     "operator 확인 없이 live 차단·merge 0·LLM 0·DB 0·전송 0·secret read 0)."))
    parser.add_argument("--event-json", metavar="PATH", default=None,
                        help="operator-confirmed event payload JSON 파일(gitignored·미지정 시 not_provided). 코드 생성 0.")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    payload = _load_payload(ns.event_json)
    out = run_operator_regulatory_event_intake(payload)
    agg = sanitized_operator_intake(out)
    if ns.json:
        print(json.dumps(agg, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} provided={out['operator_event_provided']} "
          f"seed={out['selected_seed_id']}")
    print(f"- operator_event: status={out['operator_event_status']} confirmed={out['operator_confirmed']} "
          f"confirmation_valid={out['confirmation_valid']} provenance={out['seed_provenance']}")
    print(f"- live: approved={out['live_query_approved']} allowed={out['live_allowed']} "
          f"official_news_live_status={out['official_news_live_status']}")
    print(f"- production_candidate: status={out['production_candidate_status']} "
          f"frozen={out['production_frozen_pair_count']} handoff_ready={out['reviewer_handoff_ready']}")
    print(f"- r1: production_gold={out['production_gold_count']} gap={out['current_r1_gap']} "
          f"r2_r7_no_go={out['r2_r7_no_go']}")
    print(f"- gates: merge={out['merge_allowed']} llm={out['llm_invoked']} db_write={out['db_write']} "
          f"sending={out['actual_sending_performed']} same_event={out['same_event_asserted']}")
    print(f"- blocked_reason: {out['blocked_reason'] or '(none)'}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
