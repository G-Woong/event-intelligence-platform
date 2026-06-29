"""ADR#85 — window-honoring source readiness (date-fidelity 후보 평가 · merge 0 · LLM 0 · DB 0 · secret 값 0).

ADR#84/#85 가 드러낸 blocker: Guardian/NYT 는 from-date/to-date 가 URL 에 정확히 들어가도 응답이 window 를
제약하지 못할 수 있다(메커니즘은 control experiment 가 분해 중). 이 모듈은 그 hedge 로 **window-honoring 가능성이
높은 source 후보**를 source role guard 를 보존한 채 평가한다 — date_filter 능력·의미론·confidence·rate risk·
canonical attribution risk·adapter status·구현비용·news 와의 cross-source pairing 정책·다음 행동.

**truth 가 아니라 acquisition support**: 후보 평가는 어떤 source 도 같은 사건/병합/공개로 단정하지 않는다.
이 턴은 adapter 를 **배선하지 않는다**(adapter_wired_this_turn=False) — Federal Register 를 ADR#86 adapter 로
권고하고 정밀 spec 은 docs 가 남긴다. official×news cross-source pairing 은 role-bridge 정책이 필요해 ADR#86 영역.
GDELT 는 rate-fragile(rate_limit_policy min_interval 60s·실측 429 storm) + aggregator canonical attribution
위험으로 보류. 모든 후보는 publishable role(official/news)만 — community/market/catalog/search anchor 0(guard 보존)."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Callable, Optional

OPERATION_NAME = "window_honoring_source_readiness"

# anchor 가능한 publishable role(provider_breadth_inventory 와 동일 근거 — community/market/catalog/search 제외).
_ANCHOR_ROLES = frozenset({"official", "news"})

# ── curated window-honoring 후보 지식(API capability — 하드코딩 readiness 아님; credential 은 동적·여기선 전부 key-free).
# date_filter_confidence: 요청 date window 가 응답을 실제 제약한다는 데 대한 *문서·구조 근거* 신뢰도(절대 단정 아님).
_CANDIDATES: dict[str, dict] = {
    "federal_register": {
        "source_role": "official", "key_free": True, "query_capability": "topic+publication_date",
        "date_filter_capability": "explicit_publication_date_gte_lte",
        "date_filter_semantics": "conditions[publication_date][gte]/[lte] (official documented range filter)",
        # **documented_unverified**(adversarial MEDIUM-3): 문서·구조 근거는 강하나 실 호출로 미검증 — 바로 이번 턴이
        # "문서상 정확한 date param 도 응답을 제약 못 한다"(Guardian/NYT)를 발견했으므로 official source 도 'high' 단정 금지.
        "date_filter_confidence": "documented_unverified",
        "rate_limit_risk": "low",                  # public·no key·관대.
        "canonical_attribution_risk": "low",       # 1차 공식 출처(자기 문서).
        "cross_source_pairing_with_news": "role_bridge_required",   # official×news → ADR#86 정책.
        "implementation_cost": "low",
        "recommended_for_adr86_adapter": True,
        "next_action": ("ADR#86 wired: run_provider_query federal_register adapter (key-free · "
                        "conditions[term]+publication_date[gte/lte] · enforce_window) + official_news_role_bridge "
                        "built; next: live date-honoring verification + in-window official×news freeze "
                        "(out-of-window cannot freeze · documented_unverified → live_verified/live_weak after smoke)"),
        "risk": ("regulatory documents(rules/notices) 반환 — general news 가 아니므로 news 와 cross-source near-match "
                 "전에 official×article pairing 정책 필요(role guard 약화 금지)"),
    },
    "gdelt": {
        "source_role": "news", "key_free": True, "query_capability": "topic+datetime",
        "date_filter_capability": "startdatetime_enddatetime",
        "date_filter_semantics": "startdatetime/enddatetime (YYYYMMDDHHMMSS) + sort=DateAsc/DateDesc/Relevance",
        "date_filter_confidence": "medium",        # 범위 파라미터 있으나 coverage/behavior 편차.
        "rate_limit_risk": "high",                 # rate_limit_policy: min_interval 60s·실측 429 storm.
        "canonical_attribution_risk": "high",      # aggregator — Guardian/NYT 자기기사 재유입(same-source 오염) 위험.
        "cross_source_pairing_with_news": "aggregator_contamination_risk",
        "implementation_cost": "medium",
        "recommended_for_adr86_adapter": False,
        "next_action": ("defer: rate-fragile(min_interval 60s·429 storm) + aggregator canonical attribution 을 "
                        "해소해야 배선 가능(bounded 통제 호출만)"),
        "risk": "aggregator 가 Guardian/NYT 기사를 다른 host 로 재유입 → same-source 오염; rate budget 협소",
    },
    "sec_edgar": {
        "source_role": "official", "key_free": True, "query_capability": "full_text_search+date",
        "date_filter_capability": "dateRange_startdt_enddt",
        "date_filter_semantics": "EDGAR full-text search startdt/enddt (filings 도메인)",
        "date_filter_confidence": "documented_unverified",   # 명시 범위나 실 호출 미검증(adversarial MEDIUM-3).
        "rate_limit_risk": "medium",               # 10 req/s + User-Agent 필수.
        "canonical_attribution_risk": "low",
        "cross_source_pairing_with_news": "role_bridge_required",
        "implementation_cost": "medium",
        "recommended_for_adr86_adapter": False,
        "next_action": ("defer: corporate filings 도메인 — SCOTUS 류 news event class 와 불일치; 기업/공시 event 가 "
                        "pin 되면 ADR#86+ 고려"),
        "risk": "filings 도메인이 general news event 와 불일치; 적용 범위 협소",
    },
}

# 이미 배선된 news provider(맥락 행) — date fidelity 는 ADR#85 control experiment 가 측정 중(단정 금지).
_WIRED_CONTEXT: dict[str, dict] = {
    "guardian": {"date_filter_confidence": "under_control_experiment",
                 "note": "wired·ADR#85 control experiment 가 from-date/to-date 실효를 측정 중"},
    "nyt": {"date_filter_confidence": "under_control_experiment",
            "note": "wired·ADR#85 control experiment 가 begin_date/end_date 실효를 측정 중"},
}


def _wired_providers() -> frozenset[str]:
    # ADR#86: ALL_ADAPTER_PROVIDERS(news + official) 기준 — run_provider_query 가 dispatch 가능한 전체. FR 이
    # official adapter 로 배선되면 여기 포함되어 adapter_status="wired" 로 반영(news-pairing set 과 별개).
    try:
        from backend.app.tools.provider_query_adapters import ALL_ADAPTER_PROVIDERS
        return frozenset(ALL_ADAPTER_PROVIDERS)
    except Exception:
        try:   # fallback: 구 심볼(ADR#85 호환).
            from backend.app.tools.provider_query_adapters import ADAPTER_WIRED_PROVIDERS
            return frozenset(ADAPTER_WIRED_PROVIDERS)
        except Exception:
            return frozenset()


def _candidate_row(sid: str, spec: dict, *, wired: frozenset[str]) -> dict:
    adapter_wired = sid in wired
    return {
        "source_id": sid,
        "source_role": spec["source_role"],
        "anchor_eligible": spec["source_role"] in _ANCHOR_ROLES,
        "key_free": spec["key_free"],
        "query_capability": spec["query_capability"],
        "date_filter_capability": spec["date_filter_capability"],
        "date_filter_semantics": spec["date_filter_semantics"],
        "date_filter_confidence": spec["date_filter_confidence"],
        "rate_limit_risk": spec["rate_limit_risk"],
        "canonical_attribution_risk": spec["canonical_attribution_risk"],
        "cross_source_pairing_with_news": spec["cross_source_pairing_with_news"],
        "adapter_status": "wired" if adapter_wired else "not_wired",
        "implementation_cost": spec["implementation_cost"],
        "recommended_for_adr86_adapter": spec["recommended_for_adr86_adapter"],
        "next_action": spec["next_action"],
        "risk": spec["risk"],
    }


def build_window_honoring_source_readiness(
    *, env_status_fn: Optional[Callable[[list[str]], dict[str, str]]] = None,
) -> dict:
    """window-honoring source 후보 평가(PURE·network 0·merge 0·LLM 0·DB 0·secret 값 0).

    env_status_fn 은 향후 key-required 후보 확장을 위한 hook(현재 후보는 전부 key-free 라 미사용). 후보 행 +
    권고 adapter(Federal Register) + role guard 보존 + 이 턴 adapter 미배선(ADR#86 spec) 을 산출한다."""
    wired = _wired_providers()
    rows = [_candidate_row(sid, spec, wired=wired) for sid, spec in _CANDIDATES.items()]
    # 맥락(이미 배선된 guardian/nyt) 행 — date fidelity 는 control experiment 측정 중.
    context_rows = [
        {"source_id": sid, "source_role": "news", "adapter_status": "wired",
         "date_filter_confidence": meta["date_filter_confidence"], "note": meta["note"]}
        for sid, meta in _WIRED_CONTEXT.items()
    ]

    recommended = [r for r in rows if r["recommended_for_adr86_adapter"]]
    recommended_id = recommended[0]["source_id"] if recommended else None
    # ADR#86: 권고 adapter 가 실제 wired 됐는가(FR 이 ALL_ADAPTER_PROVIDERS 에 들어오면 True). 단 wired ≠ live date
    # honoring 검증 — date_filter_confidence 는 여전히 documented_unverified(live smoke 가 별도로 verify).
    recommended_now_wired = bool(recommended_id and recommended_id in wired)
    # source role guard: 모든 후보 role 이 anchor publishable(official/news)인지 — 비-publishable anchor 승격 0.
    guard_preserved = all(r["source_role"] in _ANCHOR_ROLES for r in rows)

    return {
        "operation_name": OPERATION_NAME,
        "candidates": rows,
        "candidate_count": len(rows),
        "wired_context": context_rows,
        "recommended_adapter": recommended_id,
        "recommended_reason": (
            "Federal Register: key-free·official·명시 publication_date[gte/lte] 범위 필터·rate/attribution risk low — "
            "window-honoring 후보 중 가장 깨끗. ADR#86 에서 run_provider_query adapter 배선 + official×news role-bridge "
            "구축 완료(adapter_wired). 단 date_filter_confidence 는 여전히 documented_unverified — wired ≠ live "
            "date-honoring 검증이므로 bounded live smoke 가 live_verified/live_weak 로 별도 확정해야 함."
            if recommended_id == "federal_register" else "no recommended candidate"),
        # ADR#86: 권고 adapter(FR)가 이번 턴 실제 배선됨(ALL_ADAPTER_PROVIDERS 포함). ADR#85 의 spec-only 에서 전환.
        "adapter_wired_this_turn": recommended_now_wired,
        "next_adapter_for_adr86": recommended_id,
        "window_honoring_source_readiness_ready": True,
        # ── 불변 경계(source role guard·support not truth) ──
        "source_role_guard_preserved": guard_preserved,
        "readiness_is_acquisition_support_not_truth": True,
        "search_url_candidate_as_truth": False,
        "merge_allowed": False,
        "llm_invoked": False,
        "embedding_invoked": False,
        "db_write": False,
        "secret_values_exposed": False,
        "raw_source_body_exposed": False,
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#85 window-honoring source readiness (merge 0·LLM 0·DB 0·secret 값 0; date-fidelity 후보 "
                     "평가·role guard 보존·network 0·이 턴 adapter 미배선)."))
    parser.add_argument("--json", action="store_true", help="full readiness JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_window_honoring_source_readiness()
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} candidates={out['candidate_count']} "
          f"recommended={out['recommended_adapter']} guard_preserved={out['source_role_guard_preserved']}")
    for r in out["candidates"]:
        print(f"    {r['source_id']:<18} role={r['source_role']:<9} date_conf={r['date_filter_confidence']:<22} "
              f"rate={r['rate_limit_risk']:<7} attrib={r['canonical_attribution_risk']:<7} "
              f"adapter={r['adapter_status']} rec={r['recommended_for_adr86_adapter']}")
    print(f"- adapter_wired_this_turn={out['adapter_wired_this_turn']} next_for_adr86={out['next_adapter_for_adr86']}")
    print(f"- merge={out['merge_allowed']} llm={out['llm_invoked']} db_write={out['db_write']} "
          f"secret_exposed={out['secret_values_exposed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
