"""ADR#81 — provider breadth inventory (acquisition support only · merge 0 · LLM 0 · DB 0 · secret value 0).

문제(ADR#80 실측): live recall lift 0 의 한 원인은 *acquisition breadth 협소*였다 — live run 이 Guardian×NYT 둘만
호출했기 때문이지 wiring 이 좁아서가 아니다(분석 §2-A). source_registry.yaml 에는 이미 57 소스가 와이어링돼 있다.
이 모듈은 그 57 소스를 **source role guard 를 보존한 채** acquisition 능력으로 분류해 operator/Agent 가 breadth
확장의 다음 행동을 볼 수 있게 한다. **truth 가 아니라 acquisition support** — breadth 는 candidate 를 늘릴 뿐,
같은 사건/병합/공개를 단정하지 않는다.

무엇을 하는가:
  - source_registry.yaml(단일 출처)을 읽어 각 소스를 §5 의 9 카테고리로 분류한다.
  - anchor-eligible(query_capable_publishable·feed_only_publishable·ko_official_news·official_source) 과
    non-anchor(search_url_candidate·community_reaction_only·market_signal_only·catalog_enrichment_only·
    unknown_quarantine)를 **분리**한다 — community/market/catalog/search 는 event anchor 가 될 수 없다.
  - credential presence 는 secret-safe(env var 이름·present/missing boolean 만·값 0) 로 실측한다.
  - per-source row 와 카테고리 카운트, breadth 다음 행동을 산출한다.

절대 불변(상속·재확인):
  - **source role guard**: non-anchor 카테고리는 anchor_eligible=False 가 강제된다(약화 금지·§2-Q12).
  - **search URL candidate 는 fetch/검증 전 truth 아님**(§2-Q13) · community=reaction_only · market=signal_only ·
    catalog=enrichment_only.
  - merge 0 · LLM/embedding 0 · DB write 0 · public IU 0 · raw body 미저장(title+canonical only).
  - secret 값은 출력·로그 0(env var 이름·present/missing boolean 만).

registry 에는 'query-capable/anchor-eligibility' 단일 flag 가 없으므로(분석 §2-Q1·Q5) 아래 curated 집합이
anchor-eligibility 를 **registry type 과 교차해** 선언한다(provider_readiness._PROVIDER_CATALOG 와 동일한 근거·
하드코딩 readiness 아님 — credential/rate 는 동적 실측).
"""
from __future__ import annotations

import argparse
import sys
from typing import Callable, Optional

# ── §5 9-카테고리 ──────────────────────────────────────────────────────────────────────────────────────
QUERY_CAPABLE_PUBLISHABLE = "query_capable_publishable"
FEED_ONLY_PUBLISHABLE = "feed_only_publishable"
OFFICIAL_SOURCE = "official_source"
SEARCH_URL_CANDIDATE = "search_url_candidate"
KO_OFFICIAL_NEWS = "ko_official_news"
COMMUNITY_REACTION_ONLY = "community_reaction_only"
MARKET_SIGNAL_ONLY = "market_signal_only"
CATALOG_ENRICHMENT_ONLY = "catalog_enrichment_only"
UNKNOWN_QUARANTINE = "unknown_quarantine"

ALL_CATEGORIES: tuple[str, ...] = (
    QUERY_CAPABLE_PUBLISHABLE, FEED_ONLY_PUBLISHABLE, OFFICIAL_SOURCE, SEARCH_URL_CANDIDATE,
    KO_OFFICIAL_NEWS, COMMUNITY_REACTION_ONLY, MARKET_SIGNAL_ONLY, CATALOG_ENRICHMENT_ONLY,
    UNKNOWN_QUARANTINE,
)

# anchor-eligible(event anchor candidate 가 될 수 있는 publishable role). 나머지는 source role guard 로 anchor 금지.
_ANCHOR_ELIGIBLE_CATEGORIES = frozenset({
    QUERY_CAPABLE_PUBLISHABLE, FEED_ONLY_PUBLISHABLE, KO_OFFICIAL_NEWS, OFFICIAL_SOURCE,
})

# anchor 가능한 **registry type**(source role guard 의 독립 출처 — category 파생이 아님). anchor-eligible 한 모든
# 소스는 이 type 이거나 아래 curated 예외여야 한다. category 만 대조하면 tautology(category↔anchor_eligible 동일
# 식 파생) — registry type 과 교차해야 override/registry drift(예: registry 가 anchor 소스를 community 로 강등)를 잡는다.
_ANCHOR_CAPABLE_REGISTRY_TYPES = frozenset({"news", "official"})
# registry type 이 news/official 이 아니나 anchor 로 promote 되는 curated 예외(문서화된 사유). newsapi/gnews 는
# registry type=search 이나 article metadata 를 돌려주는 news aggregator → query_capable_publishable(SERP 와 구분).
_CURATED_ANCHOR_EXCEPTIONS = frozenset({"newsapi", "gnews"})

# ── curated anchor-eligibility 집합(registry 에 query-capable flag 부재 — §2-Q1/Q5; type 과 교차) ──────────
# query-capable + publishable(키워드+시간창 query 로 same-event news 후보 생성 가능; serper/tavily/exa 같은 SERP 와
# 구분 — 이들은 article metadata 가 아니라 URL+snippet 이라 search_url_candidate). gdelt/sec_edgar/federal_register
# 는 key-free, guardian/nyt/newsapi/gnews 는 key-required(.env.example placeholder 존재).
_QUERY_CAPABLE_PUBLISHABLE_IDS = frozenset({
    "guardian", "nyt", "newsapi", "gnews", "gdelt", "sec_edgar", "federal_register",
})
# KO publishable news(anchor 가능·KO floor 기여). naver_news_search 는 키워드 query·NAVER 키 필요(ko_source_readiness
# 가 정밀 credential 처리). 나머지는 RSS/HTML feed(이미 LIVE_SUCCESS·key-free).
_KO_PUBLISHABLE_NEWS_IDS = frozenset({
    "zdnet_korea", "etnews", "yna", "hankyung", "maekyung", "naver_news_search",
})
# SERP-style search(URL+snippet — fetch/검증 전 truth 아님·anchor 금지). newsapi/gnews 는 registry type=search 이나
# article metadata 를 돌려주는 news aggregator 라 query_capable_publishable 로 분류(위 집합) — SERP 와 구분.
_SEARCH_SERP_IDS = frozenset({
    "serper", "tavily", "exa", "google_programmable_search",
})

# query 능력 표기(분류용·동적 readiness 아님). 미기재는 카테고리 기본값으로 채움.
_QUERY_CAPABILITY: dict[str, str] = {
    "guardian": "topic+time_window", "nyt": "topic+time_window",
    "newsapi": "topic+time_window", "gnews": "topic+time_window",
    "gdelt": "topic+time_window", "federal_register": "topic+time_window",
    "sec_edgar": "full_text_search", "naver_news_search": "topic",
    "serper": "topic", "tavily": "topic", "exa": "topic",
    "google_programmable_search": "topic",
}

_RAW_BODY_POLICY = "title_canonical_only_no_body"


def _default_env_status(keys: list[str]) -> dict[str, str]:
    """secret-safe credential presence — env_loader.env_status 재사용(값 0·alias 해소). 실패 시 fail-closed missing."""
    if not keys:
        return {}
    try:
        from ingestion.core.env_loader import env_status
        return env_status(list(keys))
    except Exception:
        return {k: "missing" for k in keys}


def _rate_limit_policy(source_id: str) -> dict:
    """effective rate-limit policy(default+per_source). load 실패 시 보수 기본값(죽지 않음)."""
    try:
        from ingestion.core.rate_limit_policy import load_rate_limit_policy
        pol = load_rate_limit_policy(source_id)
        return {
            "min_interval_seconds": pol.min_interval_seconds,
            "cooldown_on_429_seconds": pol.cooldown_on_429_seconds,
            "max_retries_on_429": pol.max_retries_on_429,
        }
    except Exception:
        return {"min_interval_seconds": 0, "cooldown_on_429_seconds": 60, "max_retries_on_429": 1}


def _classify(source_id: str, source_type: str) -> str:
    """단일 소스 → §5 9-카테고리(curated anchor-eligibility ∩ registry type·우선순위·fail-closed).

    우선순위: 명시 query-capable publishable > KO publishable news > SERP search > registry type 기본.
    type=signal(트렌드/attention)·_dummy(test stub)·미지 type 은 anchor 8-bucket 에 안 맞으면 fail-closed quarantine."""
    if source_id in _QUERY_CAPABLE_PUBLISHABLE_IDS:
        return QUERY_CAPABLE_PUBLISHABLE
    if source_id in _KO_PUBLISHABLE_NEWS_IDS:
        return KO_OFFICIAL_NEWS
    if source_id in _SEARCH_SERP_IDS:
        return SEARCH_URL_CANDIDATE
    if source_type == "news":
        if source_id == "_dummy":
            return UNKNOWN_QUARANTINE                       # test stub — anchor 금지(fail-closed).
        return FEED_ONLY_PUBLISHABLE
    if source_type == "official":
        return OFFICIAL_SOURCE
    if source_type == "community":
        return COMMUNITY_REACTION_ONLY
    if source_type == "market":
        return MARKET_SIGNAL_ONLY
    if source_type == "domain":
        return CATALOG_ENRICHMENT_ONLY
    if source_type == "search":
        return SEARCH_URL_CANDIDATE                         # 잔여 search → URL candidate(truth 아님).
    if source_type == "signal":
        # 트렌드/attention 신호(Google Trends·Signal.bz) — reaction/signal 레이어이지 event anchor 아님.
        # 명명된 8-bucket(community 는 community-authored content) 에 부합하지 않아 fail-closed quarantine.
        return UNKNOWN_QUARANTINE
    return UNKNOWN_QUARANTINE                               # 미지 type → fail closed.


_GUARD_ROLE = {
    QUERY_CAPABLE_PUBLISHABLE: "news", FEED_ONLY_PUBLISHABLE: "news",
    KO_OFFICIAL_NEWS: "news_ko", OFFICIAL_SOURCE: "official",
    SEARCH_URL_CANDIDATE: "search", COMMUNITY_REACTION_ONLY: "community",
    MARKET_SIGNAL_ONLY: "market", CATALOG_ENRICHMENT_ONLY: "catalog",
    UNKNOWN_QUARANTINE: "unknown",
}

_OVERLAP_USEFULNESS = {
    QUERY_CAPABLE_PUBLISHABLE: "high", FEED_ONLY_PUBLISHABLE: "medium_breadth",
    KO_OFFICIAL_NEWS: "high_ko", OFFICIAL_SOURCE: "medium",
    SEARCH_URL_CANDIDATE: "low_url_only", COMMUNITY_REACTION_ONLY: "none_non_anchor",
    MARKET_SIGNAL_ONLY: "none_non_anchor", CATALOG_ENRICHMENT_ONLY: "none_non_anchor",
    UNKNOWN_QUARANTINE: "none_non_anchor",
}


def _next_action(category: str, *, credential_required: bool, missing: list[str]) -> str:
    """per-source 다음 행동(secret 값 0·env var 이름만)."""
    if credential_required and missing:
        return f"set_env:{','.join(missing)} (.env 값 설정·secret 커밋 금지)"
    if category == QUERY_CAPABLE_PUBLISHABLE:
        return "wire_into_targeted_acquisition_pool (anchor 후보·named seed 와 결합)"
    if category == FEED_ONLY_PUBLISHABLE:
        return "include_as_breadth_pool (키워드 query 불가·same-date breadth 기여)"
    if category == KO_OFFICIAL_NEWS:
        return "wire_ko_publishable_into_comparison_pool (KO floor 기여·anchor 가능)"
    if category == OFFICIAL_SOURCE:
        return "use_official_doc_as_anchor_or_enrichment (publishable doc 만 anchor)"
    if category == SEARCH_URL_CANDIDATE:
        return "fetch_and_validate_before_truth (anchor 금지·URL candidate only)"
    if category == COMMUNITY_REACTION_ONLY:
        return "attach_as_reaction_to_verified_event_only (anchor 금지)"
    if category == MARKET_SIGNAL_ONLY:
        return "attach_as_market_signal_for_only (anchor 금지)"
    if category == CATALOG_ENRICHMENT_ONLY:
        return "use_for_entity_enrichment_only (anchor 금지)"
    return "quarantine_no_anchor (fail-closed·trend/stub/unknown)"


def _row(spec_dict: dict, *, env_status_fn: Callable[[list[str]], dict[str, str]]) -> dict:
    """단일 source row(§5 필수 필드). credential 은 secret-safe 실측·값 0."""
    sid = spec_dict["id"]
    stype = spec_dict.get("type", "unknown")
    category = _classify(sid, stype)
    anchor_eligible = category in _ANCHOR_ELIGIBLE_CATEGORIES
    env_keys = list(spec_dict.get("env_keys") or [])
    credential_required = bool(env_keys)
    env_present = env_status_fn(env_keys) if env_keys else {}
    missing = [k for k in env_keys if env_present.get(k) != "present"]
    expected = list(spec_dict.get("expected_fields") or [])
    return {
        "source_id": sid,
        "source_name": spec_dict.get("name", sid),
        "category": category,
        "source_role": _GUARD_ROLE[category],
        "registry_type": stype,
        "registry_role": spec_dict.get("role"),
        "anchor_eligible": anchor_eligible,
        "query_capability": _QUERY_CAPABILITY.get(
            sid, "feed_only" if category in (FEED_ONLY_PUBLISHABLE, KO_OFFICIAL_NEWS) else "n/a"),
        "credential_required": credential_required,
        "credential_presence_secret_safe": env_present,      # {VAR: present|missing} — 이름+boolean 만(값 0).
        "rate_limit_policy": _rate_limit_policy(sid),
        "canonical_url_available": bool(spec_dict.get("base_url")),
        "title_available": "title" in expected,
        "published_at_available": "published_at" in expected,
        "body_available": "body" in expected,                # source 능력(우리는 raw body 미저장·title+canonical only).
        "raw_body_policy": _RAW_BODY_POLICY,
        "legal_tos_caution": _legal_caution(category, spec_dict),
        "expected_overlap_usefulness": _OVERLAP_USEFULNESS[category],
        "r1_candidate_usefulness": (
            "high" if category == QUERY_CAPABLE_PUBLISHABLE
            else "medium" if anchor_eligible else "none"),
        "ko_floor_usefulness": (
            "high" if category == KO_OFFICIAL_NEWS
            else "reaction_only_no_floor" if (sid in ("naver_blog_search", "dcinside", "fmkorea"))
            else "none"),
        "next_action": _next_action(category, credential_required=credential_required, missing=missing),
    }


def _legal_caution(category: str, spec_dict: dict) -> str:
    blockers = list(spec_dict.get("known_blockers") or [])
    base = {
        SEARCH_URL_CANDIDATE: "tos_review_required_no_full_text_storage",
        COMMUNITY_REACTION_ONLY: "tos_review_required_reaction_layer_pii_caution",
        MARKET_SIGNAL_ONLY: "api_tos_attribution",
        CATALOG_ENRICHMENT_ONLY: "api_tos_attribution",
    }.get(category, "standard_attribution")
    return f"{base}{(' | blockers=' + ','.join(blockers)) if blockers else ''}"


def build_provider_breadth_inventory(
    *, sources: Optional[list[dict]] = None,
    env_status_fn: Optional[Callable[[list[str]], dict[str, str]]] = None,
) -> dict:
    """source_registry.yaml(단일 출처) → 9-카테고리 sanitized 인벤토리 + 카운트 + breadth 다음 행동.

    network 0 · merge 0 · LLM 0 · DB 0 · secret 값 0(present/missing boolean 만). test 는 sources/env_status_fn
    주입으로 실 registry/.env 비의존 결정론. registry load 실패해도 죽지 않고 fail-closed(empty inventory + reason)."""
    env_fn = env_status_fn or _default_env_status
    registry_loaded = True
    load_error: Optional[str] = None
    if sources is None:
        try:
            from ingestion.core.source_registry import load_registry
            sources = [s.to_dict() for s in load_registry().all()]
        except Exception as exc:                              # noqa: BLE001 — fail-closed(추측 금지).
            registry_loaded = False
            load_error = f"registry_load_failed:{type(exc).__name__}"
            sources = []

    rows = [_row(s, env_status_fn=env_fn) for s in sources]
    rows.sort(key=lambda r: (ALL_CATEGORIES.index(r["category"]), r["source_id"]))

    category_counts = {cat: sum(1 for r in rows if r["category"] == cat) for cat in ALL_CATEGORIES}
    anchor_rows = [r for r in rows if r["anchor_eligible"]]
    non_anchor_rows = [r for r in rows if not r["anchor_eligible"]]
    # source role guard 불변(2겹·tautology 회피):
    #  ① non-anchor 카테고리는 anchor_eligible=False(category 일관성).
    #  ② anchor-eligible 한 모든 소스는 registry type 이 news/official 이거나 curated 예외 — **registry type 독립
    #     교차검증**(category 파생이 아닌 source-of-truth 대조)이라 override/registry drift(anchor 소스의 community/
    #     market 강등·비-publishable 의 anchor 승격)를 fail-loud 로 잡는다.
    guard_category_consistent = all(
        (not r["anchor_eligible"]) for r in rows if r["category"] not in _ANCHOR_ELIGIBLE_CATEGORIES)
    guard_registry_consistent = all(
        (r["registry_type"] in _ANCHOR_CAPABLE_REGISTRY_TYPES
         or r["source_id"] in _CURATED_ANCHOR_EXCEPTIONS)
        for r in rows if r["anchor_eligible"])
    guard_preserved = guard_category_consistent and guard_registry_consistent

    next_actions = sorted({r["next_action"] for r in anchor_rows})
    return {
        "operation": "provider_breadth_inventory",
        "registry_loaded": registry_loaded,
        "registry_load_error": load_error,
        "total_sources": len(rows),
        "inventory": rows,
        "category_counts": category_counts,
        "query_capable_publishable_count": category_counts[QUERY_CAPABLE_PUBLISHABLE],
        "feed_only_publishable_count": category_counts[FEED_ONLY_PUBLISHABLE],
        "official_source_count": category_counts[OFFICIAL_SOURCE],
        "search_url_candidate_count": category_counts[SEARCH_URL_CANDIDATE],
        "ko_official_news_count": category_counts[KO_OFFICIAL_NEWS],
        "community_reaction_only_count": category_counts[COMMUNITY_REACTION_ONLY],
        "market_signal_only_count": category_counts[MARKET_SIGNAL_ONLY],
        "catalog_enrichment_only_count": category_counts[CATALOG_ENRICHMENT_ONLY],
        "unknown_quarantine_count": category_counts[UNKNOWN_QUARANTINE],
        "anchor_eligible_count": len(anchor_rows),
        "non_anchor_count": len(non_anchor_rows),
        "anchor_eligible_source_ids": sorted(r["source_id"] for r in anchor_rows),
        "provider_breadth_next_actions": next_actions,
        "provider_breadth_inventory_ready": registry_loaded and len(rows) > 0,
        # ── 불변 경계(source role guard·breadth=support not truth) ──
        "source_role_guard_preserved": guard_preserved,
        "source_role_guard_registry_cross_checked": guard_registry_consistent,  # registry type 독립 교차검증(tautology 아님).
        "breadth_is_acquisition_support_not_truth": True,
        "raw_body_policy": _RAW_BODY_POLICY,
        "merge_allowed": False,
        "llm_invoked": False,
        "embedding_invoked": False,
        "db_write": False,
        "public_truth_exposed": False,
        "raw_source_body_exposed": False,
        "secret_values_exposed": False,
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#81 provider breadth inventory (acquisition support only·merge 0·LLM 0·DB 0·secret 값 0; "
                     "source role guard 보존·9-카테고리 분류·network 0)."))
    parser.add_argument("--json", action="store_true", help="full inventory JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    inv = build_provider_breadth_inventory()
    if ns.json:
        import json
        print(json.dumps(inv, ensure_ascii=False, indent=2))
        return 0
    print(f"- provider breadth inventory (ADR#81) total={inv['total_sources']} "
          f"guard_preserved={inv['source_role_guard_preserved']}")
    for cat in ALL_CATEGORIES:
        print(f"    {cat:<28} {inv['category_counts'][cat]}")
    print(f"- anchor_eligible={inv['anchor_eligible_count']} non_anchor={inv['non_anchor_count']}")
    print(f"- next_actions={inv['provider_breadth_next_actions']}")
    print(f"- merge_allowed={inv['merge_allowed']} llm_invoked={inv['llm_invoked']} "
          f"secret_values_exposed={inv['secret_values_exposed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
