"""ADR#93 §15 — next provider expansion pack (no-yield 원인 → 다음에 추가할 provider 권고 카드·PLANNING ONLY·실행 0).

문제(ADR#84~#92 실측): bounded live 가 수율 0 일 때 taxonomy 가 *왜* 0 인지는 분류하지만(live_no_yield_taxonomy),
"그래서 **다음에 어느 provider 를 어떤 risk 로** 추가/교정해야 하는가"를 per-provider 카드로 묶은 단일 출처가 없었다.
news_breadth_trigger(ADR#92 §10)가 runtime 확장 trigger 의 단일 출처이고, 이 모듈은 그것을 **재구현하지 않고
인용(cite)** 하는 per-provider expansion **카드 덱**이다 — taxonomy 키(no_yield_reason)를 받아 headline provider 와
provider 카드(GDELT / AP·Reuters-like / official-agency PR / SEC·EDGAR / Federal Register)를 risk 필드와 함께 낸다.

설계 계약(상속·재확인):
  - **PLANNING ONLY**: runtime_enabled=False. 권고는 계획일 뿐 runtime 확장은 별도 ADR + explicit approval 이 필요하다.
  - **GDELT 실행 0**: gdelt_executed=False. 이 모듈은 어떤 provider 도 호출하지 않는다(network_invoked=False).
  - **GDELT/SEC/FR risk fact 재선언 0**: window_honoring_source_readiness(PURE) + provider_breadth_inventory(PURE,
    network 0·secret-safe)에서 그대로 끌어온다. AP·Reuters-like / official-agency PR 만 기존 행이 없어 inline 신규
    선언(adapter_status=not_wired).
  - **official-side 우선**: official_no_records 면 news breadth 를 먼저 권하지 않는다(공식 query/window 부터 교정).
  - **KO lane 분리**: KO 권고는 EN 과 절대 병합하지 않고 별도 행(ko_lane_recommendation·ko_lane_separate=True).
  - 불변: aggregator_truth=False · source_role guard 보존 · merge 0 · same_event 단정 0 · secret 값 0(present/missing only).

friendly token → TX 매핑(아래 _FRIENDLY_TO_TX): 호출측이 짧은 별칭을 넘겨도 canonical TX 키로 해소한다. 4개 중
news_no_records / no_in_window_news / official_no_records 는 TX 값과 **동일** 하고, "freeze_unsafe" 만 TX 값이 아니라
TX_FREEZE_UNSAFE(=="bridge_candidate_found_but_freeze_unsafe")의 **별칭** 이다. TX 값 자체도 그대로 받는다(둘 다 허용).
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
from backend.app.tools.provider_breadth_inventory import (
    _KO_PUBLISHABLE_NEWS_IDS,
    build_provider_breadth_inventory,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe
from backend.app.tools.window_honoring_source_readiness import (
    build_window_honoring_source_readiness,
)

OPERATION_NAME = "next_provider_expansion_pack"

# next_provider_expansion_status(operator/engineer-facing) — news_breadth_trigger NBT_* 어휘를 인용·미러.
NPE_NEWS_BREADTH = "recommend_news_breadth_provider"
NPE_PROVIDER_DATE = "recommend_provider_or_date_strategy"
NPE_OFFICIAL_FIRST = "recommend_official_side_fix_first"
NPE_OVERLAP_REFINE = "recommend_overlap_refinement_no_new_provider"
NPE_NOT_TRIGGERED = "no_expansion_recommended"

# ── friendly token → canonical TX 키(별칭+TX 값 둘 다 허용·문서화) ────────────────────────────────────────
# 주의: "freeze_unsafe" 는 TX 값이 아니라 TX_FREEZE_UNSAFE 의 짧은 별칭. 나머지 셋은 TX 값과 동일.
_FRIENDLY_TO_TX: dict[str, str] = {
    "news_no_records": TX_NEWS_NO_RECORDS,            # == TX 값.
    "no_in_window_news": TX_NO_IN_WINDOW_NEWS,        # == TX 값.
    "official_no_records": TX_OFFICIAL_NO_RECORDS,    # == TX 값.
    "freeze_unsafe": TX_FREEZE_UNSAFE,                # 별칭 → "bridge_candidate_found_but_freeze_unsafe".
}

# 입력으로 직접 받을 수 있는 canonical TX 값(별칭 외 — 이 값들은 그대로 통과).
_KNOWN_TX: frozenset[str] = frozenset({
    TX_NEWS_NO_RECORDS, TX_NO_IN_WINDOW_NEWS, TX_OFFICIAL_NO_RECORDS, TX_FREEZE_UNSAFE,
    TX_NEWS_OUT_OF_WINDOW, TX_OFFICIAL_OUT_OF_WINDOW, TX_NO_OVERLAP, TX_NOT_RUN,
})

# resolved TX 키 → expansion status(thin 매핑 — news_breadth_trigger._classify 의 counts/dimension 로직 재구현 0).
_TX_TO_STATUS: dict[str, str] = {
    TX_NEWS_NO_RECORDS: NPE_NEWS_BREADTH,
    TX_NO_IN_WINDOW_NEWS: NPE_PROVIDER_DATE,
    TX_NEWS_OUT_OF_WINDOW: NPE_PROVIDER_DATE,
    TX_OFFICIAL_NO_RECORDS: NPE_OFFICIAL_FIRST,
    TX_OFFICIAL_OUT_OF_WINDOW: NPE_OFFICIAL_FIRST,
    TX_FREEZE_UNSAFE: NPE_OVERLAP_REFINE,
    TX_NO_OVERLAP: NPE_OVERLAP_REFINE,
    TX_NOT_RUN: NPE_NOT_TRIGGERED,
}

# status → headline provider(top-level 권고 1순위). OVERLAP_REFINE/NOT_TRIGGERED 는 신규 provider 없음(None).
_STATUS_TO_HEADLINE_SID: dict[str, Optional[str]] = {
    NPE_NEWS_BREADTH: "gdelt",
    NPE_PROVIDER_DATE: "federal_register",
    NPE_OFFICIAL_FIRST: "sec_edgar",
    NPE_OVERLAP_REFINE: None,
    NPE_NOT_TRIGGERED: None,
}

_WHY_RECOMMENDED: dict[str, str] = {
    NPE_NEWS_BREADTH: (
        "news returned no records for this event — news breadth expansion is the next lever. GDELT is a PLANNING-ONLY "
        "candidate (rate_limit_risk=high, aggregator canonical attribution risk=high, adapter not wired; needs a "
        "separate ADR + explicit approval). An AP/Reuters-like wire service is the cleaner-attribution alternative "
        "(also not wired). GDELT is NOT executed by this pack."),
    NPE_PROVIDER_DATE: (
        "news returned out-of-window / no in-window records — Guardian/NYT date filtering is under a control "
        "experiment. Prefer a window-honoring provider/date strategy: Federal Register honors publication_date[gte/lte] "
        "(key-free, official), but its date fidelity is documented_unverified — verify with a bounded live smoke "
        "before relying on the window."),
    NPE_OFFICIAL_FIRST: (
        "the official side returned no/out-of-window records — do NOT blame news first. Fix the Federal Register "
        "official query/window first (confirm the event actually has an official document); if expanding the official "
        "side, consider SEC/EDGAR full-text or an official agency PR feed. News breadth expansion is not the fix here."),
    NPE_OVERLAP_REFINE: (
        "a bridge candidate was found but freeze is unsafe / official and news did not overlap — refine the query "
        "overlap (named entity/action) and tighten the date window so BOTH records fall in-window. No new provider "
        "is needed."),
    NPE_NOT_TRIGGERED: (
        "no no-yield reason was provided (or it did not map to a known taxonomy key) — no provider expansion is "
        "recommended at this time."),
}

_NEXT_ADR_CANDIDATE: dict[str, str] = {
    NPE_NEWS_BREADTH: (
        "gdelt_news_breadth_adapter OR ap_reuters_like wire adapter (separate ADR + explicit approval: bounded calls, "
        "rate budget, canonical attribution guard) — NOT this turn"),
    NPE_PROVIDER_DATE: (
        "federal_register live date-honoring verification (adapter already wired) — confirm window fidelity before "
        "relying on it"),
    NPE_OFFICIAL_FIRST: (
        "official-side query/window fix first; a SEC/EDGAR or official-agency-PR adapter is a separate ADR — NOT this turn"),
    NPE_OVERLAP_REFINE: "",
    NPE_NOT_TRIGGERED: "",
}


def _resolve_taxonomy_key(no_yield_reason: Optional[str]) -> str:
    """no_yield_reason(TX 값 또는 friendly 별칭) → canonical TX 키. 미지/None 은 not_run 으로 fail-closed."""
    if no_yield_reason is None:
        return TX_NOT_RUN
    s = str(no_yield_reason).strip()
    if s in _KNOWN_TX:                       # canonical TX 값은 그대로 통과.
        return s
    if s in _FRIENDLY_TO_TX:                 # friendly 별칭은 매핑(freeze_unsafe → TX_FREEZE_UNSAFE).
        return _FRIENDLY_TO_TX[s]
    return TX_NOT_RUN


def _credential_requirement(inv_row: dict, read_row: dict, inline_default: str) -> str:
    """secret-safe credential 요건(값 0). inventory credential_required(bool) → key_required/key_free; 없으면 readiness
    key_free, 그것도 없으면 inline 기본. **실제 secret 값/이름은 노출하지 않는다**(present/missing 계약)."""
    if inv_row:
        return "key_required" if inv_row.get("credential_required") else "key_free"
    if read_row:
        return "key_free" if read_row.get("key_free") else "key_required"
    return inline_default


def _canonical_url_risk(inv_row: dict, inline_default: str) -> str:
    """canonical URL 부재 risk(provider_breadth_inventory.canonical_url_available 인용)."""
    if not inv_row:
        return inline_default
    return "low" if inv_row.get("canonical_url_available") else "high"


def _body_availability_risk(inv_row: dict, inline_default: str) -> str:
    """body 확보 risk(inventory.body_available 인용). 우리 정책은 title+canonical only 라 body 미보유는 매칭이
    title/snippet 에 의존함을 뜻한다(키 이름은 body_availability_risk — 'body' 단일 키는 PII 가드에 걸림)."""
    if not inv_row:
        return inline_default
    return "low" if inv_row.get("body_available") else "title_only_no_body"


def _build_provider_cards(readiness: dict, inv_index: dict) -> list[dict]:
    """per-provider expansion 카드 덱(GDELT/AP·Reuters-like/official-agency PR/SEC·EDGAR/Federal Register).

    GDELT/SEC/FR 의 role·date_filter·rate·attribution·cost·adapter_status 는 window_honoring_source_readiness 행에서
    인용(재선언 0); canonical_url/body risk·credential 은 provider_breadth_inventory 행에서 인용. AP·Reuters-like /
    official-agency PR 는 기존 행이 없어 inline 신규 선언(adapter_status=not_wired)."""
    def read_row(sid: str) -> dict:
        return next((r for r in readiness["candidates"] if r["source_id"] == sid), {})

    gd, se, fr = read_row("gdelt"), read_row("sec_edgar"), read_row("federal_register")
    gd_inv = inv_index.get("gdelt", {})
    se_inv = inv_index.get("sec_edgar", {})
    fr_inv = inv_index.get("federal_register", {})

    return [
        {
            "source_id": "gdelt",
            "source_role": gd.get("source_role", "news"),
            "date_filter_capability": gd.get("date_filter_capability", "startdatetime_enddatetime"),
            "rate_limit_risk": gd.get("rate_limit_risk", "high"),
            "attribution_risk": gd.get("canonical_attribution_risk", "high"),
            "canonical_url_risk": _canonical_url_risk(gd_inv, "low"),
            "body_availability_risk": _body_availability_risk(gd_inv, "title_only_no_body"),
            "credential_requirement": _credential_requirement(gd_inv, gd, "key_free"),
            "implementation_cost": gd.get("implementation_cost", "medium"),
            "adapter_status": gd.get("adapter_status", "not_wired"),
            "why": (
                "GDELT — news breadth candidate, PLANNING ONLY: rate-fragile (min_interval 60s, 429 storm) and "
                "aggregator canonical attribution risk (Guardian/NYT re-ingest → same-source contamination). Not "
                "wired; a wired expansion needs a separate ADR + explicit approval. GDELT is NOT executed here."),
        },
        {
            "source_id": "ap_reuters_like",
            "source_role": "news",
            "date_filter_capability": "wire_timestamp_filter_documented_unverified",
            "rate_limit_risk": "medium",
            "attribution_risk": "low",
            "canonical_url_risk": "low",
            "body_availability_risk": "license_gated",
            "credential_requirement": "key_required",
            "implementation_cost": "high",
            "adapter_status": "not_wired",
            "why": (
                "AP/Reuters-like primary wire service — cleaner canonical attribution than an aggregator (low "
                "attribution risk), but commercial licensing (key_required, high implementation cost). A breadth "
                "candidate with better provenance than GDELT; not wired."),
        },
        {
            "source_id": "official_agency_pr",
            "source_role": "official",
            "date_filter_capability": "feed_recency_or_listing_date_documented_unverified",
            "rate_limit_risk": "low",
            "attribution_risk": "low",
            "canonical_url_risk": "low",
            "body_availability_risk": "low",
            "credential_requirement": "key_free",
            "implementation_cost": "medium",
            "adapter_status": "not_wired",
            "why": (
                "Official agency PR / newsroom feeds (first-party) — low attribution risk and key-free, but "
                "heterogeneous per-agency adapters (medium cost). For official_no_records, broadens official-side "
                "coverage beyond Federal Register; not wired."),
        },
        {
            "source_id": "sec_edgar",
            "source_role": se.get("source_role", "official"),
            "date_filter_capability": se.get("date_filter_capability", "dateRange_startdt_enddt"),
            "rate_limit_risk": se.get("rate_limit_risk", "medium"),
            "attribution_risk": se.get("canonical_attribution_risk", "low"),
            "canonical_url_risk": _canonical_url_risk(se_inv, "low"),
            "body_availability_risk": _body_availability_risk(se_inv, "low"),
            "credential_requirement": _credential_requirement(se_inv, se, "key_free"),
            "implementation_cost": se.get("implementation_cost", "medium"),
            "adapter_status": se.get("adapter_status", "not_wired"),
            "why": (
                "SEC/EDGAR full-text search — official filings domain (startdt/enddt date range), low attribution "
                "risk, key-free (10 req/s + User-Agent). Domain mismatch with general news; relevant when a "
                "corporate/disclosure event is pinned. Not wired."),
        },
        {
            "source_id": "federal_register",
            "source_role": fr.get("source_role", "official"),
            "date_filter_capability": fr.get("date_filter_capability", "explicit_publication_date_gte_lte"),
            "rate_limit_risk": fr.get("rate_limit_risk", "low"),
            "attribution_risk": fr.get("canonical_attribution_risk", "low"),
            "canonical_url_risk": _canonical_url_risk(fr_inv, "low"),
            "body_availability_risk": _body_availability_risk(fr_inv, "low"),
            "credential_requirement": _credential_requirement(fr_inv, fr, "key_free"),
            "implementation_cost": fr.get("implementation_cost", "low"),
            "adapter_status": fr.get("adapter_status", "wired"),
            "why": (
                "Federal Register — window-honoring official source (key-free, publication_date[gte/lte]), low "
                "rate/attribution risk, adapter wired (ADR#86). BUT date fidelity is documented_unverified — verify "
                "with a bounded live smoke before relying on the window. For no_in_window_news, the date strategy of "
                "choice."),
        },
    ]


def _build_ko_lane() -> dict:
    """KO lane 권고(EN 과 절대 병합 0·별도 행). KO publishable news 는 KO floor 기여·anchor 가능하나 EN 카드와 섞지
    않는다(naver_news_search 만 credential 필요·나머지 RSS/HTML key-free). KO floor(0/50)는 미해결."""
    return {
        "lane": "korean",
        "separate_from_en_lane": True,
        "source_role": "news_ko",
        "recommended_ko_sources": sorted(_KO_PUBLISHABLE_NEWS_IDS),
        "credential_requirement": "naver_news_search=key_required; rss_html_feeds=key_free",
        "adapter_status": "naver_news_search_not_wired; rss_html_feeds_live",
        "ko_floor_status": "unsolved_0_of_50",
        "why": (
            "KO lane is evaluated SEPARATELY from the EN lane (never merged). KO publishable news "
            "(zdnet_korea/etnews/yna/hankyung/maekyung/naver_news_search) can contribute the KO floor; NAVER search "
            "needs credentials while the RSS/HTML feeds are key-free. Tokenization risk is handled by "
            "ko_source_readiness. The KO floor (0/50) is still unsolved."),
    }


def build_next_provider_expansion_pack(
    *, no_yield_reason: Optional[str] = None, news_records_count: int = 0,
    official_records_count: int = 0, in_window_news_count: int = 0,
) -> dict:
    """no-yield 원인 → 다음 provider 권고 카드(PLANNING ONLY·network 0·GDELT 실행 0·secret 값 0·KO lane 분리).

    no_yield_reason(TX 값 또는 friendly 별칭)을 canonical TX 키로 해소해 expansion status 를 정하고, headline provider
    와 provider 카드 덱을 risk 필드와 함께 낸다. GDELT/SEC/FR risk fact 는 readiness/inventory(PURE)에서 인용하고
    news_breadth_trigger(ADR#92 §10)의 runtime trigger 를 인용한다(_classify 재구현 0). counts 는 맥락(입력 echo)일
    뿐 권고는 taxonomy 키 기준이다(runtime 확장은 별도 ADR)."""
    resolved = _resolve_taxonomy_key(no_yield_reason)
    status = _TX_TO_STATUS.get(resolved, NPE_NOT_TRIGGERED)

    readiness = build_window_honoring_source_readiness()
    inventory = build_provider_breadth_inventory()
    inv_index = {r["source_id"]: r for r in inventory.get("inventory", [])}

    provider_cards = _build_provider_cards(readiness, inv_index)
    card_index = {c["source_id"]: c for c in provider_cards}

    headline_sid = _STATUS_TO_HEADLINE_SID.get(status)
    headline = card_index.get(headline_sid, {}) if headline_sid else {}
    if headline_sid:
        recommended_provider = headline_sid
    elif status == NPE_OVERLAP_REFINE:
        recommended_provider = "none_refine_overlap_window"
    else:
        recommended_provider = "none"

    out = {
        "operation_name": OPERATION_NAME,
        "next_provider_expansion_status": status,
        "input_no_yield_reason": None if no_yield_reason is None else str(no_yield_reason),
        "resolved_taxonomy_key": resolved,
        "recommended_provider": recommended_provider,
        "why_recommended": _WHY_RECOMMENDED[status],
        # headline provider 의 risk 투영(신규 provider 없으면 n/a).
        "source_role": headline.get("source_role", "n/a"),
        "date_filter_capability": headline.get("date_filter_capability", "n/a"),
        "credential_requirement": headline.get("credential_requirement", "n/a"),
        "rate_limit_risk": headline.get("rate_limit_risk", "n/a"),
        "attribution_risk": headline.get("attribution_risk", "n/a"),
        "canonical_url_risk": headline.get("canonical_url_risk", "n/a"),
        "body_availability_risk": headline.get("body_availability_risk", "n/a"),
        "implementation_cost": headline.get("implementation_cost", "n/a"),
        "next_adr_candidate": _NEXT_ADR_CANDIDATE[status],
        "ko_lane_recommendation": _build_ko_lane(),
        "provider_cards": provider_cards,
        # 맥락(입력 echo) — 권고는 taxonomy 키 기준·counts 로 재분류하지 않음(_classify 재구현 0).
        "news_records_count": int(news_records_count),
        "official_records_count": int(official_records_count),
        "in_window_news_count": int(in_window_news_count),
        # 인용(cite, not re-implement): runtime 확장 trigger 의 단일 출처.
        "cites_upstream_trigger": "news_breadth_trigger",
        # ── 정직 불변(하드코딩) ──
        "runtime_enabled": False,
        "gdelt_executed": False,
        "network_invoked": False,
        "recommendation_is_planning_not_runtime": True,
        "runtime_expansion_requires_separate_adr": True,
        "aggregator_truth": False,
        "source_role_guard_preserved": True,
        "ko_lane_separate": True,
        "merge_allowed": False,
        "same_event_asserted": False,
        "production_gold_count": 0,
        "secret_values_exposed": False,
    }
    _assert_pii_safe(out, _path="next_provider_expansion_pack_output")
    return out


def sanitized_next_provider_expansion_pack(out: dict) -> dict:
    """frontier 용 aggregate-only 투영(status + headline 권고 + risk + 핵심 불변)."""
    return {
        "next_provider_expansion_status": out["next_provider_expansion_status"],
        "resolved_taxonomy_key": out["resolved_taxonomy_key"],
        "recommended_provider": out["recommended_provider"],
        "rate_limit_risk": out["rate_limit_risk"],
        "attribution_risk": out["attribution_risk"],
        "ko_lane_separate": out["ko_lane_separate"],
        "runtime_enabled": out["runtime_enabled"],
        "gdelt_executed": out["gdelt_executed"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#93 next provider expansion pack (no-yield 원인 → 다음 provider 권고 카드·PLANNING ONLY·"
                     "GDELT 실행 0·network 0·secret 값 0·KO lane 분리·runtime 확장은 별도 ADR)."))
    parser.add_argument("--reason", default=None,
                        help="no_yield_reason — TX 값 또는 friendly 별칭(news_no_records/no_in_window_news/"
                             "official_no_records/freeze_unsafe).")
    parser.add_argument("--news-records", type=int, default=0)
    parser.add_argument("--official-records", type=int, default=0)
    parser.add_argument("--in-window-news", type=int, default=0)
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_next_provider_expansion_pack(
        no_yield_reason=ns.reason, news_records_count=ns.news_records,
        official_records_count=ns.official_records, in_window_news_count=ns.in_window_news)
    if ns.json:
        print(json.dumps(sanitized_next_provider_expansion_pack(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['next_provider_expansion_status']}")
    print(f"- input_no_yield_reason={out['input_no_yield_reason']} resolved_taxonomy_key={out['resolved_taxonomy_key']}")
    print(f"- recommended_provider={out['recommended_provider']} source_role={out['source_role']} "
          f"rate_limit_risk={out['rate_limit_risk']} attribution_risk={out['attribution_risk']}")
    print(f"- why_recommended: {out['why_recommended']}")
    print(f"- next_adr_candidate: {out['next_adr_candidate']}")
    for c in out["provider_cards"]:
        print(f"    {c['source_id']:<18} role={c['source_role']:<8} rate={c['rate_limit_risk']:<7} "
              f"attrib={c['attribution_risk']:<7} cred={c['credential_requirement']:<12} adapter={c['adapter_status']}")
    print(f"- ko_lane(separate={out['ko_lane_separate']}): {out['ko_lane_recommendation']['recommended_ko_sources']} "
          f"floor={out['ko_lane_recommendation']['ko_floor_status']}")
    print(f"- runtime_enabled={out['runtime_enabled']} gdelt_executed={out['gdelt_executed']} "
          f"network_invoked={out['network_invoked']} aggregator_truth={out['aggregator_truth']} "
          f"runtime_expansion_requires_separate_adr={out['runtime_expansion_requires_separate_adr']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
