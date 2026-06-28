"""ADR#83 — date-pinned operator event → exact live query target wiring (PURE build + isolated executor).

ADR#82 가 정직하게 남긴 fail-closed(`LIVE_QUERY_TARGET_WIRED=False`)의 근거: date-pin 은 operator 게이트일 뿐,
bounded live 의 base 경로(breadth→discrete→targeted→smoke)는 **curated seed 를 topic + 상대(real-today) 윈도우로**
쿼리한다. 그래서 "operator 가 핀한 event X 승인" 과 "실제로 쿼리되는 event Y(curated)" 가 **decoupled** 됐다
(Finding 1). 이 모듈은 그 decoupling 을 해소한다 — high-risk 한 query-target 배선을 **한 모듈에 격리**(§4 권고):
  - `build_live_query_target`(PURE·network 0): operator named_entity + event_phrase → 결정적 query_text,
    occurrence_date(D) → 절대 윈도우 [D, D+1](as_of_anchor=D+1·time_window=1d). 검증 실패는 fail-closed.
  - `execute_date_pinned_bounded_live_run`(isolated executor): target.wired 일 때만, **검증된 targeted-layer 패턴**
    (`smoke → run_r1_production_candidate_acquisition(acquire_fn=lambda:smoke)`)을 그대로 미러해 operator query 로
    live 후보를 얻고 freeze 를 시도한다. target 미wired/빈값이면 **curated fallback 으로 떨어지지 않고 fail-closed**.

절대 불변(상속·상용 안전 계약):
  - **date-pin ≠ 발생 증명·≠ same-event 증명**: occurrence_date 는 operator 주장이지 code 검증 사실이 아니다
    (event_occurrence_verified=False·same_event_asserted=False 불변). 같은 사건 여부는 MERGE_GATE 영역.
  - **curated fallback 둔갑 0**: 실행 query 는 항상 operator named_entity + event_phrase 로 구성(query_hint 는 기록만).
    target 미wired 시 live 실행 0(hard guard·fail-closed).
  - **merge 0 · LLM/embedding 0 · DB 0 · 전송 0 · secret read 0 · raw body 0 · public IU 0 · production gold 증가 0**.
  - **source role guard**: publishable×publishable(article/official)만 — community/market/catalog/search anchor 금지(소비처 강제).

`LIVE_QUERY_TARGET_WIRED=True` 는 이 모듈의 plumbing 이 **test-locked 된 뒤에만** 켠다(§6). True 여도 live 실행은
여전히 (operator event valid) ∧ (live_query 승인) ∧ (provider pool≥2·guardian anchor) 를 모두 요구 — flag 단독으로
live 하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from backend.app.tools.cross_source_live_overlap_smoke import (
    _DEFAULT_PROVIDER_B,
    _PROVIDER_A,
    run_cross_source_live_overlap_smoke,
)
from backend.app.tools.named_event_seed_bank import (
    _BROAD_SEED_DENYLIST,
    _ISO_DATE,
    _norm,
)
from backend.app.tools.r1_production_candidate_acquisition import (
    PROD_BATCH_ID,
    run_r1_production_candidate_acquisition,
)

OPERATION_NAME = "date_pinned_live_query_and_freeze_attempt"

# §6 — date-pinned operator event → 정확한 query plumbing 이 test-locked 된 뒤에만 True(이 모듈이 owner·ADR#83 에서 켬).
# False 이면 어떤 valid date-pin·승인이 있어도 live 불가(fail-closed). True 여도 live 실행은 여전히
# (operator event valid) ∧ (live_query 승인) ∧ (provider pool≥2·guardian anchor) 를 모두 요구한다 — flag 단독 live 0.
LIVE_QUERY_TARGET_WIRED = True

# ── fail-closed block reasons(§6 validation) ─────────────────────────────────────────────────────────────
BLOCK_MISSING_NAMED_ENTITY = "missing_named_entity"
BLOCK_PLACEHOLDER_ENTITY = "placeholder_named_entity"
BLOCK_BROAD_ENTITY = "broad_named_entity"
BLOCK_MISSING_EVENT_PHRASE = "missing_event_phrase"
BLOCK_BROAD_EVENT_PHRASE = "umbrella_event_phrase"
BLOCK_MISSING_OCCURRENCE_DATE = "missing_occurrence_date"
BLOCK_OCCURRENCE_NOT_ISO = "occurrence_date_not_iso_yyyy_mm_dd"
BLOCK_PROVIDER_POOL_EMPTY = "provider_pool_empty_or_no_guardian_anchor"
BLOCK_TARGET_NOT_WIRED = "live_query_target_not_wired"

# date-pin shape(발생/같은 사건과 무관) 을 깨는 reason 집합 — 이 중 하나라도 있으면 date_pinned=False.
_DATE_PIN_BREAKING = frozenset({
    BLOCK_MISSING_NAMED_ENTITY, BLOCK_PLACEHOLDER_ENTITY, BLOCK_BROAD_ENTITY,
    BLOCK_MISSING_EVENT_PHRASE, BLOCK_BROAD_EVENT_PHRASE,
    BLOCK_MISSING_OCCURRENCE_DATE, BLOCK_OCCURRENCE_NOT_ISO,
})

_PUBLISHABLE_ROLE_REQUIRED = "publishable"
_DEFAULT_TIME_WINDOW = "1d"


def _next_day_iso(iso_date: str) -> Optional[str]:
    """occurrence_date(D·ISO) → D+1 ISO(절대 윈도우 끝 anchor=run_provider_query today). 파싱 실패 None."""
    try:
        d = datetime.strptime(iso_date, "%Y-%m-%d").date()
        return (d + timedelta(days=1)).isoformat()
    except Exception:
        return None


def build_live_query_target(
    operator_event: Optional[dict], *,
    provider_pool: Optional[list[str]] = None,
    wired_flag: Optional[bool] = None,
) -> dict:
    """operator date-pinned event → sanitized live query target(PURE·network 0·same_event 단정 0·secret 0·body 0).

    query_text 는 named_entity + event_phrase 로 **결정적** 구성(operator query_hint 는 기록만·실행 query 는 항상
    entity+phrase 포함 → §6 'query must include named_entity and event_phrase' 보장·나쁜 hint 로 anchor 유실 방지).
    절대 윈도우: occurrence_date(D) → [D, D+1](start=D·end=D+1·as_of_anchor=D+1·time_window=1d) — 발표 당일+익일
    cross-source 보도를 bracket(scheduled 기관 이벤트는 D/D+1 에 다출처 수렴이 높음). provider_pool 은 bounded live
    pool(adapter_wired ∩ credential = 현재 guardian/nyt) — guardian 은 항상 provider_a anchor(smoke 고정). 검증 실패는
    fail-closed block_reasons. wired = (date-pin-breaking·pool·target_not_wired block 0) ∧ LIVE_QUERY_TARGET_WIRED ∧
    date_pinned ∧ query_text ∧ guardian∈providers ∧ second_provider 존재.

    date_pinned=True 여도 event_occurrence_verified/same_event_asserted=False(불변) — 날짜는 operator 주장이지
    code 가 검증한 발생/같은 사건이 아니다."""
    wired_flag = LIVE_QUERY_TARGET_WIRED if wired_flag is None else bool(wired_flag)
    ev = operator_event or {}
    named_entity = str(ev.get("named_entity") or "").strip()
    event_phrase = str(ev.get("event_phrase") or "").strip()
    occurrence_raw = str(ev.get("occurrence_date") or "").strip()
    query_hint = str(ev.get("query_hint") or "").strip()
    expected_sources = list(ev.get("expected_sources") or [])

    reasons: list[str] = []
    # named_entity — 비어있음/placeholder/broad 거부.
    if not named_entity:
        reasons.append(BLOCK_MISSING_NAMED_ENTITY)
    elif "<" in named_entity or "operator fills" in named_entity.lower():
        reasons.append(BLOCK_PLACEHOLDER_ENTITY)
    elif _norm(named_entity) in _BROAD_SEED_DENYLIST:
        reasons.append(BLOCK_BROAD_ENTITY)
    # event_phrase — 비어있음/umbrella 거부.
    if not event_phrase:
        reasons.append(BLOCK_MISSING_EVENT_PHRASE)
    elif _norm(event_phrase) in _BROAD_SEED_DENYLIST:
        reasons.append(BLOCK_BROAD_EVENT_PHRASE)
    # occurrence_date — 비어있음/비-ISO 거부.
    occurrence_is_iso = bool(occurrence_raw and _ISO_DATE.match(occurrence_raw))
    if not occurrence_raw:
        reasons.append(BLOCK_MISSING_OCCURRENCE_DATE)
    elif not occurrence_is_iso:
        reasons.append(BLOCK_OCCURRENCE_NOT_ISO)

    # provider pool — bounded live pool(기본 guardian/nyt). guardian 은 provider_a anchor(smoke 고정)이라 강제 보존.
    pool = list(provider_pool) if provider_pool is not None else [_PROVIDER_A, _DEFAULT_PROVIDER_B]
    if expected_sources:
        narrowed = {p for p in pool if p in set(expected_sources)}
        if _PROVIDER_A in pool:
            narrowed.add(_PROVIDER_A)   # guardian anchor 강제(expected 가 빼도 — pair 불가 방지).
        providers = sorted(narrowed)
    else:
        providers = sorted(set(pool))
    second_provider = next((p for p in providers if p != _PROVIDER_A), None)
    if _PROVIDER_A not in providers or second_provider is None:
        reasons.append(BLOCK_PROVIDER_POOL_EMPTY)

    date_pinned = not (set(reasons) & _DATE_PIN_BREAKING)

    # 절대 윈도우(date_pinned 일 때만).
    start_date = occurrence_raw if (date_pinned and occurrence_raw) else None
    as_of_anchor = _next_day_iso(occurrence_raw) if start_date else None
    if start_date and not as_of_anchor:
        # ISO 매치했으나 strptime 실패(이론상 불가) — fail-closed.
        reasons.append(BLOCK_OCCURRENCE_NOT_ISO)
        date_pinned = False
        start_date = None
    end_date = as_of_anchor

    # 실행 query_text — entity + phrase 결정적 구성(둘 다 있을 때만). query_hint 는 실행 query 에 넣지 않음(기록만).
    query_text = f"{named_entity} {event_phrase}".strip() if (named_entity and event_phrase) else ""

    if not wired_flag:
        reasons.append(BLOCK_TARGET_NOT_WIRED)

    wired = bool(
        not (set(reasons) & (_DATE_PIN_BREAKING | {BLOCK_PROVIDER_POOL_EMPTY, BLOCK_TARGET_NOT_WIRED}))
        and wired_flag and date_pinned and query_text
        and _PROVIDER_A in providers and second_provider is not None)

    return {
        "operation_name": OPERATION_NAME,
        "operator_event_provided": bool(operator_event),
        "named_entity": named_entity or None,
        "event_phrase": event_phrase or None,
        "occurrence_date": start_date,
        "occurrence_date_valid_iso": occurrence_is_iso,
        "date_pinned_named_event_valid": date_pinned,
        # date 가 있어도 발생/같은 사건은 operator·MERGE_GATE 영역(불변).
        "event_occurrence_verified": False,
        "same_event_asserted": False,
        # 실행 query target(sanitized·secret 0·raw body 0).
        "query_text": query_text or None,
        "operator_query_hint": query_hint or None,   # 기록만 — 실행 query 는 entity+phrase(anchor 유실 방지).
        "start_date": start_date,
        "end_date": end_date,
        "as_of_anchor": as_of_anchor,                # run_provider_query(today=) anchor → 절대 윈도우 [D, D+1].
        "time_window": _DEFAULT_TIME_WINDOW,
        "providers": providers,
        "provider_a": _PROVIDER_A if _PROVIDER_A in providers else None,
        "second_provider": second_provider,
        "source_role_required": _PUBLISHABLE_ROLE_REQUIRED,
        "raw_body_allowed": False,
        "live_query_target_wired": bool(wired_flag),
        "wired": wired,
        "block_reasons": list(dict.fromkeys(reasons)),
    }


def _smoke_executed(smoke: dict) -> bool:
    """smoke 가 실제 provider fetch 를 시도했는가(opt-in + credential present → provider_status 채워짐). gated 면 False."""
    return bool(smoke.get("provider_status_by_provider"))


def _smoke_live_call_count(smoke: dict) -> int:
    """실제 쿼리된 provider 수(0=gated·2=양 provider fetch). provider_status_by_provider 키 수."""
    return len(smoke.get("provider_status_by_provider") or {})


def execute_date_pinned_bounded_live_run(
    target: dict, *, directory: Optional[Any] = None, batch_id: str = PROD_BATCH_ID,
    as_of: Optional[str] = None,
    transport_a: Optional[Callable[[str], Optional[str]]] = None,
    transport_b: Optional[Callable[[str], Optional[str]]] = None,
    env_status_fn: Optional[Callable[[list[str]], dict[str, str]]] = None,
    env_probe_fn: Optional[Callable[[str], dict]] = None, host_gate: Any = None,
    readiness_fn: Optional[Callable[[], dict]] = None, gate_fn: Optional[Callable[..., dict]] = None,
    synthetic_batch_fn: Optional[Callable[..., dict]] = None,
    smoke_fn: Optional[Callable[..., dict]] = None,
    freeze_fn: Optional[Callable[..., dict]] = None,
) -> dict:
    """target(build_live_query_target) → bounded live run(operator query·절대 윈도우) + production candidate freeze.

    HARD GUARD(§6·§7): target.wired False 또는 query_text 빈값이면 live 실행 0 — curated fallback 으로 떨어지지
    않고 fail-closed(`live_query_target_not_wired`). wired 일 때만:
      ① smoke(provider_b=second·topic=target.query_text·today=target.as_of_anchor·1d·emit_band/recall) — operator
         event 를 실제 쿼리 대상으로(curated topic 아님). today 가 occurrence_date+1 → 절대 [D, D+1] 윈도우.
      ② run_r1_production_candidate_acquisition(acquire_fn=lambda:smoke) — live-derived publishable×publishable 만
         freeze(targeted-layer 와 동일·합성 둔갑 0). freeze 는 reviewer worklist 이지 same-event truth 가 아니다.
    merge 0·LLM 0·embedding 0·DB 0·전송 0·secret read 0·same_event 단정 0·raw body 0. test 는 transport_a/transport_b
    (fake)+env_probe_fn 주입 시 결정론(network 0·실 `.env` 미접촉·key 불요); smoke_fn/freeze_fn 주입 시 완전 분리."""
    if not target.get("wired") or not target.get("query_text"):
        return {
            "executed": False, "live_call_count": 0,
            "block_reason": BLOCK_TARGET_NOT_WIRED, "smoke": None, "pcand": None,
        }
    second = target.get("second_provider") or _DEFAULT_PROVIDER_B
    smoke = (smoke_fn or run_cross_source_live_overlap_smoke)(
        provider_b=second, topic=target["query_text"], topic_key="operator_date_pinned_event",
        time_window=target.get("time_window") or _DEFAULT_TIME_WINDOW, today=target.get("as_of_anchor"),
        live_query=True, enforce_window=True, transport_a=transport_a, transport_b=transport_b,
        env_status_fn=env_status_fn, env_probe_fn=env_probe_fn, host_gate=host_gate,
        emit_band_diagnostic=True, emit_recall_probe=True)
    pcand = (freeze_fn or run_r1_production_candidate_acquisition)(
        directory=directory, batch_id=batch_id, as_of=as_of, live_query=True,
        acquire_fn=lambda *, live_query: smoke,
        readiness_fn=readiness_fn, gate_fn=gate_fn, synthetic_batch_fn=synthetic_batch_fn)
    return {
        "executed": _smoke_executed(smoke),
        "live_call_count": _smoke_live_call_count(smoke),
        "block_reason": None,
        "smoke": smoke,
        "pcand": pcand,
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#83 date-pinned live query target builder (PURE·network 0; build_live_query_target 검증 + "
                     "절대 윈도우. live 실행은 r1_bounded_live_breadth_run --operator-* 경유·이 CLI 는 target 검사만)."))
    parser.add_argument("--named-entity", default="", help="operator named entity(예: 'US Federal Reserve').")
    parser.add_argument("--event-phrase", default="", help="operator event 행위(예: 'FOMC rate decision').")
    parser.add_argument("--occurrence-date", default="", help="실제 발생일 ISO YYYY-MM-DD(operator 확인).")
    parser.add_argument("--query-hint", default="", help="(optional) 실제 검색 문구 — 기록만·실행 query 는 entity+phrase.")
    parser.add_argument("--json", action="store_true", help="target JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    operator_event = None
    if ns.named_entity or ns.event_phrase or ns.occurrence_date:
        operator_event = {
            "named_entity": ns.named_entity, "event_phrase": ns.event_phrase,
            "occurrence_date": ns.occurrence_date, "query_hint": ns.query_hint,
        }
    target = build_live_query_target(operator_event)
    if ns.json:
        print(json.dumps(target, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {target['operation_name']}")
    print(f"- operator_event_provided={target['operator_event_provided']} "
          f"date_pinned_valid={target['date_pinned_named_event_valid']} wired={target['wired']}")
    print(f"- query_text={target['query_text']!r}")
    print(f"- window: start={target['start_date']} end={target['end_date']} "
          f"as_of_anchor={target['as_of_anchor']} time_window={target['time_window']}")
    print(f"- providers={target['providers']} second={target['second_provider']} "
          f"role_required={target['source_role_required']}")
    print(f"- event_occurrence_verified={target['event_occurrence_verified']} "
          f"same_event_asserted={target['same_event_asserted']}")
    print(f"- block_reasons={target['block_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
