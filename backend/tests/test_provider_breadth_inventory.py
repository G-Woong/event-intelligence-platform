"""ADR#81 — provider breadth inventory 테스트(§13: breadth 8~17·source role guard·secret-safe).

network 0 · merge 0 · LLM 0 · secret 값 0. synthetic sources/env_status_fn 주입으로 결정론(실 registry/.env 비의존),
+ 실 registry 1건으로 total/guard 회귀."""
from __future__ import annotations

import json

from backend.app.tools.provider_breadth_inventory import (
    CATALOG_ENRICHMENT_ONLY,
    COMMUNITY_REACTION_ONLY,
    FEED_ONLY_PUBLISHABLE,
    KO_OFFICIAL_NEWS,
    MARKET_SIGNAL_ONLY,
    OFFICIAL_SOURCE,
    QUERY_CAPABLE_PUBLISHABLE,
    SEARCH_URL_CANDIDATE,
    UNKNOWN_QUARANTINE,
    build_provider_breadth_inventory,
)


def _spec(sid: str, stype: str, *, role="primary", env_keys=None, expected=None, base_url="https://x.test"):
    return {
        "id": sid, "name": sid.upper(), "type": stype, "role": role,
        "env_keys": env_keys or [], "expected_fields": expected or ["title", "body", "published_at"],
        "base_url": base_url, "known_blockers": [],
    }


def _env_all_missing(keys):
    return {k: "missing" for k in keys}


def _env_present(present):
    def fn(keys):
        return {k: ("present" if k in present else "missing") for k in keys}
    return fn


# 9 카테고리를 대표하는 synthetic registry(한 카테고리당 ≥1).
_SYNTH = [
    _spec("guardian", "news", role="secondary", env_keys=["GUARDIAN_API_KEY"]),
    _spec("gdelt", "official"),                              # query-capable publishable(curated)
    _spec("bbc", "news"),                                    # feed-only publishable
    _spec("yna", "news"),                                    # KO publishable news(curated)
    _spec("opendart", "official"),                           # official source
    _spec("serper", "search", env_keys=["SERPER_API_KEY"]),  # search URL candidate
    _spec("reddit", "community", role="secondary"),          # community reaction-only
    _spec("finnhub", "market", role="secondary", env_keys=["FINNHUB_API_KEY"]),  # market signal-only
    _spec("tmdb", "domain", role="secondary", env_keys=["TMDB_API_KEY"]),        # catalog enrichment-only
    _spec("google_trending_now", "signal", role="supplementary"),  # trend → quarantine(fail-closed)
    _spec("_dummy", "news", role="supplementary"),          # test stub → quarantine
    _spec("weird_thing", "totally_unknown_type"),           # 미지 type → quarantine
]


def _cat(inv, sid):
    return next(r for r in inv["inventory"] if r["source_id"] == sid)["category"]


def _row(inv, sid):
    return next(r for r in inv["inventory"] if r["source_id"] == sid)


def test_inventory_generated_with_all_rows():
    """§13-8: provider inventory generated."""
    inv = build_provider_breadth_inventory(sources=_SYNTH, env_status_fn=_env_all_missing)
    assert inv["provider_breadth_inventory_ready"] is True
    assert inv["total_sources"] == len(_SYNTH)
    assert len(inv["inventory"]) == len(_SYNTH)
    # 카운트 합 == total(누락/이중계상 없음).
    assert sum(inv["category_counts"].values()) == inv["total_sources"]


def test_query_capable_publishable_separated():
    """§13-9: query-capable publishable 분리·anchor 가능."""
    inv = build_provider_breadth_inventory(sources=_SYNTH, env_status_fn=_env_all_missing)
    assert _cat(inv, "guardian") == QUERY_CAPABLE_PUBLISHABLE
    assert _cat(inv, "gdelt") == QUERY_CAPABLE_PUBLISHABLE
    assert _row(inv, "guardian")["anchor_eligible"] is True
    assert inv["query_capable_publishable_count"] >= 2


def test_feed_only_publishable_separated():
    """§13-10: feed-only publishable 분리(키워드 query 불가·breadth)."""
    inv = build_provider_breadth_inventory(sources=_SYNTH, env_status_fn=_env_all_missing)
    assert _cat(inv, "bbc") == FEED_ONLY_PUBLISHABLE
    assert _row(inv, "bbc")["anchor_eligible"] is True
    assert _row(inv, "bbc")["query_capability"] == "feed_only"


def test_official_source_separated():
    """§13-11: official source 분리."""
    inv = build_provider_breadth_inventory(sources=_SYNTH, env_status_fn=_env_all_missing)
    assert _cat(inv, "opendart") == OFFICIAL_SOURCE
    assert _row(inv, "opendart")["anchor_eligible"] is True


def test_search_url_candidate_not_truth():
    """§13-12: search URL candidate 는 truth 아님·anchor 금지. credential present 시 fetch-before-truth 행동 노출."""
    inv = build_provider_breadth_inventory(
        sources=_SYNTH, env_status_fn=_env_present({"SERPER_API_KEY"}))
    assert _cat(inv, "serper") == SEARCH_URL_CANDIDATE
    row = _row(inv, "serper")
    assert row["anchor_eligible"] is False           # search 는 anchor 불가(truth 아님).
    assert "fetch_and_validate_before_truth" in row["next_action"]


def test_community_reaction_only():
    """§13-13: community 는 reaction-only·anchor 금지."""
    inv = build_provider_breadth_inventory(sources=_SYNTH, env_status_fn=_env_all_missing)
    assert _cat(inv, "reddit") == COMMUNITY_REACTION_ONLY
    assert _row(inv, "reddit")["anchor_eligible"] is False
    assert "reaction_to" in _row(inv, "reddit")["next_action"]


def test_market_signal_only():
    """§13-14: market 은 signal-only·anchor 금지."""
    inv = build_provider_breadth_inventory(sources=_SYNTH, env_status_fn=_env_all_missing)
    assert _cat(inv, "finnhub") == MARKET_SIGNAL_ONLY
    assert _row(inv, "finnhub")["anchor_eligible"] is False


def test_catalog_enrichment_only():
    """§13-15: catalog/domain 은 enrichment-only·anchor 금지."""
    inv = build_provider_breadth_inventory(sources=_SYNTH, env_status_fn=_env_all_missing)
    assert _cat(inv, "tmdb") == CATALOG_ENRICHMENT_ONLY
    assert _row(inv, "tmdb")["anchor_eligible"] is False


def test_unknown_quarantine_fail_closed():
    """§13-16: signal/test-stub/미지 type → unknown_quarantine·fail-closed anchor 금지."""
    inv = build_provider_breadth_inventory(sources=_SYNTH, env_status_fn=_env_all_missing)
    assert _cat(inv, "google_trending_now") == UNKNOWN_QUARANTINE
    assert _cat(inv, "_dummy") == UNKNOWN_QUARANTINE
    assert _cat(inv, "weird_thing") == UNKNOWN_QUARANTINE
    for sid in ("google_trending_now", "_dummy", "weird_thing"):
        assert _row(inv, sid)["anchor_eligible"] is False


def test_ko_official_news_separated():
    """KO publishable news 분리·KO floor 기여·anchor 가능."""
    inv = build_provider_breadth_inventory(sources=_SYNTH, env_status_fn=_env_all_missing)
    assert _cat(inv, "yna") == KO_OFFICIAL_NEWS
    assert _row(inv, "yna")["anchor_eligible"] is True
    assert _row(inv, "yna")["ko_floor_usefulness"] == "high"


def test_source_role_guard_preserved():
    """§13-17: source role guard — non-anchor 카테고리는 anchor_eligible=False 강제."""
    inv = build_provider_breadth_inventory(sources=_SYNTH, env_status_fn=_env_all_missing)
    assert inv["source_role_guard_preserved"] is True
    assert inv["source_role_guard_registry_cross_checked"] is True
    non_anchor_cats = {
        SEARCH_URL_CANDIDATE, COMMUNITY_REACTION_ONLY, MARKET_SIGNAL_ONLY,
        CATALOG_ENRICHMENT_ONLY, UNKNOWN_QUARANTINE,
    }
    for r in inv["inventory"]:
        if r["category"] in non_anchor_cats:
            assert r["anchor_eligible"] is False


def test_source_role_guard_catches_override_registry_drift():
    """가드는 tautology 가 아니다: curated override 가 비-publishable(community) registry type 을 anchor 로 올리면
    registry-type 독립 교차검증이 fail-loud(guard_preserved=False)."""
    # 'guardian' 은 _QUERY_CAPABLE_PUBLISHABLE_IDS override → query_capable_publishable(anchor_eligible=True).
    # registry 가 그 소스를 community 로 강등한 drift 를 시뮬레이트 → registry type 교차검증이 잡아야 함.
    drift = [_spec("guardian", "community", role="secondary", env_keys=["GUARDIAN_API_KEY"])]
    inv = build_provider_breadth_inventory(sources=drift, env_status_fn=_env_all_missing)
    row = inv["inventory"][0]
    assert row["category"] == QUERY_CAPABLE_PUBLISHABLE      # override 가 여전히 anchor category 로 분류.
    assert row["anchor_eligible"] is True
    assert row["registry_type"] == "community"               # 그러나 registry type 은 비-publishable.
    assert inv["source_role_guard_registry_cross_checked"] is False
    assert inv["source_role_guard_preserved"] is False       # drift 를 fail-loud 로 포착(가드 비-tautology 증명).


def test_newsapi_gnews_curated_anchor_exception_allowed():
    """newsapi/gnews 는 registry type=search 이나 curated anchor 예외(news aggregator) → 교차검증 통과."""
    ex = [
        _spec("newsapi", "search", role="secondary", env_keys=["NEWSAPI_API_KEY"]),
        _spec("gnews", "search", role="secondary", env_keys=["GNEWS_API_KEY"]),
    ]
    inv = build_provider_breadth_inventory(sources=ex, env_status_fn=_env_all_missing)
    assert all(r["category"] == QUERY_CAPABLE_PUBLISHABLE for r in inv["inventory"])
    assert inv["source_role_guard_registry_cross_checked"] is True
    assert inv["source_role_guard_preserved"] is True


def test_credential_presence_secret_safe_no_values():
    """credential 은 present/missing boolean 만·값 노출 0. missing → set_env next_action."""
    inv = build_provider_breadth_inventory(
        sources=_SYNTH, env_status_fn=_env_present({"GUARDIAN_API_KEY"}))
    g = _row(inv, "guardian")
    assert g["credential_required"] is True
    assert g["credential_presence_secret_safe"] == {"GUARDIAN_API_KEY": "present"}
    # missing key → set_env 행동(이름만).
    f = _row(inv, "finnhub")
    assert f["credential_presence_secret_safe"] == {"FINNHUB_API_KEY": "missing"}
    assert "set_env:FINNHUB_API_KEY" in f["next_action"]
    # 전체 직렬화에 present/missing 외 값 토큰 없음(secret 미노출).
    blob = json.dumps(inv, ensure_ascii=False)
    assert inv["secret_values_exposed"] is False
    for tok in ("present", "missing"):
        assert tok in blob
    # env value 가 새지 않음 — credential dict 의 value 는 present/missing 만.
    for r in inv["inventory"]:
        for v in r["credential_presence_secret_safe"].values():
            assert v in ("present", "missing")


def test_no_merge_no_llm_no_db_invariants():
    inv = build_provider_breadth_inventory(sources=_SYNTH, env_status_fn=_env_all_missing)
    assert inv["merge_allowed"] is False
    assert inv["llm_invoked"] is False
    assert inv["embedding_invoked"] is False
    assert inv["db_write"] is False
    assert inv["public_truth_exposed"] is False
    assert inv["raw_source_body_exposed"] is False
    assert inv["breadth_is_acquisition_support_not_truth"] is True


def test_empty_sources_fail_closed_not_ready():
    """sources 비면 ready=False(추측 금지·fail-closed)."""
    inv = build_provider_breadth_inventory(sources=[], env_status_fn=_env_all_missing)
    assert inv["provider_breadth_inventory_ready"] is False
    assert inv["total_sources"] == 0
    assert inv["anchor_eligible_count"] == 0


def test_real_registry_total_and_guard():
    """실 source_registry.yaml 회귀: total 57 · guard preserved · 카운트 합 == total."""
    inv = build_provider_breadth_inventory()  # 실 registry 로드.
    assert inv["registry_loaded"] is True
    assert inv["total_sources"] == 57
    assert sum(inv["category_counts"].values()) == 57
    assert inv["source_role_guard_preserved"] is True
    # 실 registry 에서 알려진 분류 회귀(분석 §2 기준).
    assert _cat(inv, "guardian") == QUERY_CAPABLE_PUBLISHABLE
    assert _cat(inv, "nyt") == QUERY_CAPABLE_PUBLISHABLE
    assert _cat(inv, "newsapi") == QUERY_CAPABLE_PUBLISHABLE
    assert _cat(inv, "yna") == KO_OFFICIAL_NEWS
    assert _cat(inv, "naver_news_search") == KO_OFFICIAL_NEWS
    assert _cat(inv, "serper") == SEARCH_URL_CANDIDATE
    assert _cat(inv, "reddit") == COMMUNITY_REACTION_ONLY
    assert _cat(inv, "_dummy") == UNKNOWN_QUARANTINE
    assert _cat(inv, "google_trending_now") == UNKNOWN_QUARANTINE
