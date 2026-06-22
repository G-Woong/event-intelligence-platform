"""소스 콘텐츠 타입 분류 — 카탈로그형은 metadata_complete(본문 실패 아님), 산문형만 body_expected."""
from __future__ import annotations

from ingestion.orchestration.source_content_type import (
    CLASS_BODY_EXPECTED,
    CLASS_METADATA_COMPLETE,
    CLASS_URL_CANDIDATE,
    body_expected,
    body_ladder_eligible,
    classify,
    content_type,
    is_metadata_complete,
)


def test_catalog_sources_are_metadata_complete_not_body_failure():
    # 영화/도서/공연/관광/박스오피스/게임 메타 API — 별도 산문 본문 없음 → 실패로 치지 않음
    for sid in ("aladin", "tmdb", "kofic", "kopis", "tour", "igdb"):
        assert content_type(sid, "official") == "catalog_metadata"
        assert body_expected(sid, "official") is False
        assert is_metadata_complete(sid, "official") is True
        assert classify(sid, "official") == CLASS_METADATA_COMPLETE
        assert body_ladder_eligible(sid, "official") is False


def test_document_and_detail_and_article_are_body_expected():
    assert content_type("opendart", "official") == "document"
    assert content_type("culture_info", "official") == "detail"
    assert content_type("nyt", "news") == "article"
    for sid, grp in (("opendart", "official"), ("culture_info", "official"), ("nyt", "news")):
        assert body_expected(sid, grp) is True
        assert classify(sid, grp) == CLASS_BODY_EXPECTED
        assert body_ladder_eligible(sid, grp) is True


def test_search_is_url_candidate():
    for sid in ("exa", "serper", "tavily", "newsapi"):
        assert content_type(sid, "search") == "search"
        assert classify(sid, "search") == CLASS_URL_CANDIDATE
        assert body_expected(sid, "search") is False
        assert body_ladder_eligible(sid, "search") is False


def test_structured_is_not_body_expected():
    for sid in ("twelve_data", "alpha_vantage", "finnhub"):
        assert is_metadata_complete(sid, "market") is True
        assert body_expected(sid, "market") is False


def test_official_default_is_document_but_catalog_overrides():
    # 오버라이드에 없는 official 기본은 document(산문 본문 기대), catalog set은 오버라이드로 metadata
    assert content_type("federal_register", "official") == "document"
    assert content_type("aladin", "official") == "catalog_metadata"   # 오버라이드 우선
