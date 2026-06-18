from __future__ import annotations

"""source_role 파생 taxonomy 단위테스트 (네트워크 0).

실제 source_profiles.yaml 57소스를 로드해 각 source 가 정확히 하나의 primary role 로
파생되는지, role 별 anchor 가 맞는지, community/search 가 직접 publish 금지인지 검증한다.
"""

import pytest

from ingestion.orchestration.source_profile import load_source_profiles
from ingestion.orchestration.source_role import (
    ALL_ROLES,
    ARTICLE_BODY,
    COMMUNITY_EARLY_SIGNAL,
    ENRICHMENT_ONLY,
    EXPANSION_SEARCH,
    OFFICIAL_RECORD,
    PERIODIC_EVENT_QUEUE,
    STRUCTURED_SIGNAL,
    derive_source_role,
    roles_by_source,
)
from ingestion.orchestration.source_profile import SourceProfile


@pytest.fixture(scope="module")
def role_map():
    profiles = load_source_profiles()
    assert len(profiles) >= 50, "source_profiles.yaml 로드 실패"
    return roles_by_source(profiles)


def test_every_source_gets_exactly_one_known_primary_role(role_map):
    for sid, view in role_map.items():
        assert view.primary_role in ALL_ROLES, f"{sid}: unknown role {view.primary_role}"
        assert view.primary_role in view.roles
        for r in view.roles:
            assert r in ALL_ROLES


# role 별 anchor (실제 profile 기준)
_ARTICLE_ANCHORS = ["bbc", "ap_news", "techcrunch", "yna", "hankyung", "aljazeera"]
_EXPANSION_ANCHORS = ["serper", "tavily", "exa", "gnews", "newsapi", "naver_news_search"]
_OFFICIAL_ANCHORS = ["sec_edgar", "gdelt", "federal_register", "opendart", "eu_press_corner"]
_STRUCTURED_ANCHORS = ["coinbase_market", "binance_market", "finnhub", "polygon"]
_COMMUNITY_ANCHORS = ["hacker_news", "dcinside", "youtube", "product_hunt", "naver_blog_search"]
_ENRICHMENT_ANCHORS = ["google_trending_now", "signal_bz", "kma", "tmdb", "kofic"]


@pytest.mark.parametrize("sid", _ARTICLE_ANCHORS)
def test_news_is_article_body(role_map, sid):
    v = role_map[sid]
    assert v.primary_role == ARTICLE_BODY
    assert PERIODIC_EVENT_QUEUE in v.roles  # news 는 주기 큐에도 들어간다


@pytest.mark.parametrize("sid", _EXPANSION_ANCHORS)
def test_search_is_expansion(role_map, sid):
    assert role_map[sid].primary_role == EXPANSION_SEARCH


@pytest.mark.parametrize("sid", _OFFICIAL_ANCHORS)
def test_official_is_official_record(role_map, sid):
    v = role_map[sid]
    assert v.primary_role == OFFICIAL_RECORD
    assert PERIODIC_EVENT_QUEUE in v.roles


@pytest.mark.parametrize("sid", _STRUCTURED_ANCHORS)
def test_market_is_structured_signal(role_map, sid):
    assert role_map[sid].primary_role == STRUCTURED_SIGNAL


@pytest.mark.parametrize("sid", _COMMUNITY_ANCHORS)
def test_community_is_early_signal(role_map, sid):
    assert role_map[sid].primary_role == COMMUNITY_EARLY_SIGNAL


@pytest.mark.parametrize("sid", _ENRICHMENT_ANCHORS)
def test_trend_domain_is_enrichment(role_map, sid):
    assert role_map[sid].primary_role == ENRICHMENT_ONLY


def test_community_never_direct_publish(role_map):
    for sid, view in role_map.items():
        if view.primary_role == COMMUNITY_EARLY_SIGNAL:
            assert "never_direct_publish" in view.publication_policy, sid


def test_search_never_direct_publish_expansion_only(role_map):
    for sid, view in role_map.items():
        if view.primary_role == EXPANSION_SEARCH:
            assert "never_direct_publish" in view.publication_policy, sid


def test_is_community_overrides_search_group():
    # naver_blog_search: source_group=search 이지만 is_community=true → community 우선.
    p = SourceProfile(source_id="naver_blog_search", source_group="search",
                      is_community=True, confirmation_policy="unconfirmed_until_corroborated")
    assert derive_source_role(p).primary_role == COMMUNITY_EARLY_SIGNAL


def test_unknown_group_defaults_to_enrichment_no_publish():
    p = SourceProfile(source_id="mystery", source_group=None)
    v = derive_source_role(p)
    assert v.primary_role == ENRICHMENT_ONLY
    assert "no_direct_publish" in v.publication_policy
