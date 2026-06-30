"""ADR#92 §10 — news breadth trigger (live no-yield/overlap 실패 → source 확장 필요성 판정·GDELT 실행 0·truth 0).

문제(ADR#84~#86 실측·R-ProviderDateWindowFidelity): bounded live 가 news-side 에서 수율이 없을 때(news_no_records /
no_in_window_news / news_out_of_window), 다음에 *어느 source 를 어떻게 확장* 해야 하는지 판단이 흩어져 있었다.
Guardian/NYT 가 date window 를 못 지키거나(`under_control_experiment`) event 를 안 다루면 breadth 확장이 필요할 수
있으나, 무지성 확장은 source role guard 를 약화시킨다(aggregator 오염).

이 모듈은 그 판단을 묶는 **trigger** 다(taxonomy/overlap/window-honoring readiness 위 thin 합성·재구현 0):
  - taxonomy status + overlap blocked dimension + record counts → news_breadth_trigger_status 와 recommended_action.
  - GDELT 후보는 **계획만**(rate-fragile·aggregator attribution risk·not_wired) — 이 모듈은 GDELT 를 **실행하지 않는다**.
  - official-side gap(official_no_records)이면 news breadth 를 먼저 권하지 않는다(공식 query/window 부터 교정).
  - runtime 확장은 별도 ADR / explicit approval 이 필요하다(recommendation ≠ runtime).
  불변: network 0 · GDELT 실행 0 · merge 0 · same_event 단정 0 · source role guard 보존 · secret/PII 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.live_no_yield_taxonomy import (
    TX_FREEZE_UNSAFE,
    TX_NEWS_NO_RECORDS,
    TX_NEWS_OUT_OF_WINDOW,
    TX_NO_IN_WINDOW_NEWS,
    TX_NO_OVERLAP,
    TX_NOT_RUN,
    TX_OFFICIAL_NO_RECORDS,
    TX_OFFICIAL_OUT_OF_WINDOW,
)
from backend.app.tools.official_news_overlap_diagnostics import (
    DIM_ACTION,
    DIM_ENTITY,
    DIM_IN_WINDOW,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe
from backend.app.tools.window_honoring_source_readiness import (
    build_window_honoring_source_readiness,
)

OPERATION_NAME = "news_breadth_trigger"

# news_breadth_trigger_status(operator/engineer-facing).
NBT_NOT_TRIGGERED = "no_news_side_gap_not_triggered"
NBT_RECOMMEND_NEWS_BREADTH = "recommend_news_breadth_expansion"
NBT_RECOMMEND_PROVIDER_DATE = "recommend_provider_or_date_strategy"
NBT_OFFICIAL_FIRST = "official_side_gap_fix_official_first"
NBT_FREEZE_SAFETY = "recommend_freeze_safety_fix"
NBT_OVERLAP_REFINE = "recommend_query_overlap_refinement"


def _classify(status: str, dim: str, *, official_records_count: int, news_records_count: int) -> str:
    """taxonomy status(우선) + overlap dimension(보조) + counts → trigger status(결정론·official-side 우선)."""
    # ① official-side gap 우선 — news breadth 를 먼저 권하지 않는다(공식 query/window 부터).
    if status in (TX_OFFICIAL_NO_RECORDS, TX_OFFICIAL_OUT_OF_WINDOW):
        return NBT_OFFICIAL_FIRST
    if official_records_count <= 0 and news_records_count > 0:
        return NBT_OFFICIAL_FIRST
    # ② freeze unsafe — source 확장이 아니라 freeze artifact 안전부터 교정.
    if status == TX_FREEZE_UNSAFE:
        return NBT_FREEZE_SAFETY
    # ③ news no records — news breadth 확장 후보(GDELT 계획).
    if status == TX_NEWS_NO_RECORDS or (news_records_count <= 0 and official_records_count > 0):
        return NBT_RECOMMEND_NEWS_BREADTH
    # ④ in-window news gap — provider/date 전략(window-honoring source).
    if status in (TX_NO_IN_WINDOW_NEWS, TX_NEWS_OUT_OF_WINDOW) or dim == DIM_IN_WINDOW:
        return NBT_RECOMMEND_PROVIDER_DATE
    # ⑤ overlap gap — query 정밀화(named entity/action), breadth 아님.
    if status == TX_NO_OVERLAP or dim in (DIM_ENTITY, DIM_ACTION):
        return NBT_OVERLAP_REFINE
    return NBT_NOT_TRIGGERED


def _recommended_action(trigger_status: str) -> str:
    """trigger status → operator/engineer 가 할 다음 행동 한 줄(planning·runtime 아님)."""
    return {
        NBT_OFFICIAL_FIRST: (
            "the official side has no/out-of-window records — fix the Federal Register official_query and verify the "
            "publication_date window FIRST; do not expand news breadth before the official anchor is present"),
        NBT_FREEZE_SAFETY: (
            "a bridge candidate was found but freeze is unsafe — fix the freeze artifact safety "
            "(see first_freeze_package_hardening) before expanding sources"),
        NBT_RECOMMEND_NEWS_BREADTH: (
            "news returned no records for this event — consider news breadth expansion (GDELT is a PLANNING candidate "
            "only: rate-fragile aggregator, not wired this turn; a wired expansion needs a separate ADR + approval)"),
        NBT_RECOMMEND_PROVIDER_DATE: (
            "news returned out-of-window/no in-window records — Guardian/NYT date filtering is under a control "
            "experiment; prefer a window-honoring provider/date strategy (Federal Register honors publication_date)"),
        NBT_OVERLAP_REFINE: (
            "official and news did not overlap — refine the named entity/action in the queries (not breadth); name the "
            "specific respondent/target/product so official and news describe the same subject"),
        NBT_NOT_TRIGGERED: (
            "no news-side gap detected — no source breadth expansion is recommended at this time"),
    }[trigger_status]


def _next_adr_candidate(trigger_status: str) -> str:
    """확장이 필요할 때 어느 ADR 후보로 가는가(runtime 확장은 별도 ADR·explicit approval)."""
    if trigger_status == NBT_RECOMMEND_NEWS_BREADTH:
        return ("gdelt_news_breadth_adapter (separate ADR + explicit approval: bounded calls, rate budget, aggregator "
                "canonical attribution guard) — NOT this turn")
    if trigger_status == NBT_RECOMMEND_PROVIDER_DATE:
        return "federal_register live date-honoring verification (adapter already wired) — confirm window fidelity"
    return ""


def build_news_breadth_trigger(
    *, live_no_yield_taxonomy_status: Optional[str] = None, overlap_blocked_dimension: Optional[str] = None,
    official_records_count: int = 0, news_records_count: int = 0, in_window_news_count: int = 0,
    bridge_candidate_count: int = 0, provider_set: Optional[list[str]] = None,
) -> dict:
    """live no-yield/overlap 결과 → source 확장 필요성 판정(network 0·GDELT 실행 0·truth 0·source role guard 보존).

    GDELT 후보 행은 window-honoring source readiness(PURE)에서 가져오되 실행하지 않는다 — rate/attribution risk 를
    표면화하고 deferred/not_wired 임을 명시한다. runtime 확장은 recommendation 일 뿐 별도 ADR 가 필요하다."""
    status = str(live_no_yield_taxonomy_status or TX_NOT_RUN)
    dim = str(overlap_blocked_dimension or "")
    providers = list(provider_set or [])

    readiness = build_window_honoring_source_readiness()
    gdelt_row = next((r for r in readiness["candidates"] if r["source_id"] == "gdelt"), {})

    trigger_status = _classify(
        status, dim, official_records_count=int(official_records_count),
        news_records_count=int(news_records_count))

    # recommended_provider_expansion — trigger 별 후보(계획·문자열 리스트).
    expansion: list[str] = []
    if trigger_status == NBT_RECOMMEND_NEWS_BREADTH:
        expansion = [
            "gdelt — news breadth candidate (PLANNING ONLY: rate_limit_risk=high, aggregator canonical attribution "
            "risk=high, adapter_status=not_wired; needs a separate ADR + explicit approval)",
        ]
    elif trigger_status in (NBT_RECOMMEND_PROVIDER_DATE, NBT_OFFICIAL_FIRST):
        expansion = [
            "federal_register — window-honoring official source (key-free, publication_date[gte/lte]); verify live "
            "date fidelity before relying on the window",
        ]

    out = {
        "operation_name": OPERATION_NAME,
        "news_breadth_trigger_status": trigger_status,
        "input_taxonomy_status": status,
        "input_overlap_blocked_dimension": dim,
        "official_records_count": int(official_records_count),
        "news_records_count": int(news_records_count),
        "in_window_news_count": int(in_window_news_count),
        "bridge_candidate_count": int(bridge_candidate_count),
        "provider_set": providers,
        "recommended_action": _recommended_action(trigger_status),
        "recommended_provider_expansion": expansion,
        # GDELT 후보 — 실행하지 않고 risk 만 표면화(rate/attribution/aggregator).
        "gdelt_candidate_status": "deferred_not_wired_rate_fragile_aggregator",
        "source_role_risk": str(gdelt_row.get("cross_source_pairing_with_news") or "aggregator_contamination_risk"),
        "rate_limit_risk": str(gdelt_row.get("rate_limit_risk") or "high"),
        "attribution_risk": str(gdelt_row.get("canonical_attribution_risk") or "high"),
        "next_adr_candidate": _next_adr_candidate(trigger_status),
        "window_honoring_recommended_adapter": readiness.get("recommended_adapter"),
        # ── 불변 경계(정직·constant) ──
        "gdelt_executed": False,
        "network_invoked": False,
        "recommendation_is_planning_not_runtime": True,
        "runtime_expansion_requires_separate_adr": True,
        "source_role_guard_preserved": bool(readiness.get("source_role_guard_preserved", True)),
        "gdelt_result_is_truth": False,
        "same_event_asserted": False,
        "merge_allowed": False,
        "production_gold_count": 0,
    }
    _assert_pii_safe(out, _path="news_breadth_trigger_output")
    return out


def sanitized_news_breadth_trigger(out: dict) -> dict:
    """frontier 용 aggregate-only 투영(status + 권고 + risk·counts 제외)."""
    return {
        "news_breadth_trigger_status": out["news_breadth_trigger_status"],
        "recommended_provider_expansion": out["recommended_provider_expansion"],
        "gdelt_candidate_status": out["gdelt_candidate_status"],
        "rate_limit_risk": out["rate_limit_risk"],
        "attribution_risk": out["attribution_risk"],
        "gdelt_executed": out["gdelt_executed"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#92 news breadth trigger (live no-yield/overlap → source 확장 필요성 판정; GDELT 실행 0·"
                     "network 0·truth 0·source role guard 보존·runtime 확장은 별도 ADR)."))
    parser.add_argument("--taxonomy-status", default=None, help="live_no_yield_taxonomy_status 입력.")
    parser.add_argument("--blocked-dimension", default=None, help="overlap_blocked_dimension 입력.")
    parser.add_argument("--official-records", type=int, default=0)
    parser.add_argument("--news-records", type=int, default=0)
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_news_breadth_trigger(
        live_no_yield_taxonomy_status=ns.taxonomy_status, overlap_blocked_dimension=ns.blocked_dimension,
        official_records_count=ns.official_records, news_records_count=ns.news_records)
    if ns.json:
        print(json.dumps(sanitized_news_breadth_trigger(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['news_breadth_trigger_status']}")
    print(f"- recommended_action: {out['recommended_action']}")
    print(f"- recommended_provider_expansion: {out['recommended_provider_expansion']}")
    print(f"- gdelt_candidate_status={out['gdelt_candidate_status']} gdelt_executed={out['gdelt_executed']} "
          f"rate_limit_risk={out['rate_limit_risk']} attribution_risk={out['attribution_risk']}")
    print(f"- next_adr_candidate: {out['next_adr_candidate']}")
    print(f"- source_role_guard_preserved={out['source_role_guard_preserved']} "
          f"runtime_expansion_requires_separate_adr={out['runtime_expansion_requires_separate_adr']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
