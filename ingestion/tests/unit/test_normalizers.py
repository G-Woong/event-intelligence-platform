from __future__ import annotations

import pytest

from ingestion.probes.normalizers import (
    normalize_api_result,
    normalize_doc_items,
    normalize_signal_items,
)


# ── normalize_api_result ───────────────────────────────────────────────────

def test_normalize_api_result_naver_news():
    parsed = {"items": [{"title": "t1"}, {"title": "t2"}], "total": 2, "display": 2}
    result = normalize_api_result("naver_news_search", parsed)
    assert "items" in result
    assert "total" in result
    assert len(result["items"]) == 2


def test_normalize_api_result_youtube():
    parsed = {"items": [{"id": "abc"}], "pageInfo": {"totalResults": 1}}
    result = normalize_api_result("youtube", parsed)
    assert "items" in result
    assert "pageInfo" in result


def test_normalize_api_result_gdelt():
    parsed = {"articles": [{"url": "http://example.com", "title": "Test"}]}
    result = normalize_api_result("gdelt", parsed)
    assert "articles" in result
    assert result["articles"][0]["title"] == "Test"


def test_normalize_api_result_unknown_service():
    parsed = {"foo": 1, "bar": 2, "baz": 3}
    result = normalize_api_result("unknown_svc", parsed)
    # Should return first 5 keys
    assert "foo" in result or "bar" in result or "baz" in result


def test_normalize_api_result_non_dict():
    result = normalize_api_result("hacker_news", [1, 2, 3])
    assert isinstance(result, dict)
    assert "length" in result or "raw_type" in result


def test_normalize_api_result_empty_dict():
    result = normalize_api_result("gdelt", {})
    assert isinstance(result, dict)


# ── normalize_signal_items ─────────────────────────────────────────────────

def test_normalize_signal_items_strings():
    items = ["삼성전자", "애플", "엔비디아"]
    result = normalize_signal_items("signal_bz", items)
    assert len(result) == 3
    assert result[0]["source"] == "signal_bz"
    assert result[0]["keyword"] == "삼성전자"
    assert result[0]["rank"] == 1
    assert result[1]["rank"] == 2
    assert result[0]["official"] is False
    assert result[0]["evidence_level"] == "low"
    assert result[0]["signal_type"] == "trending_keyword"
    assert result[0]["collection_method"] == "playwright"


def test_normalize_signal_items_dicts():
    items = [
        {"keyword": "GPT-5", "rank": 1, "official": True, "evidence_level": "medium"},
    ]
    result = normalize_signal_items("google_trending_now", items)
    assert result[0]["keyword"] == "GPT-5"
    assert result[0]["official"] is True
    assert result[0]["evidence_level"] == "medium"


def test_normalize_signal_items_observed_at_present():
    items = ["test_keyword"]
    result = normalize_signal_items("signal_bz", items)
    assert result[0]["observed_at"]  # non-empty ISO string


def test_normalize_signal_items_empty():
    result = normalize_signal_items("signal_bz", [])
    assert result == []


def test_normalize_signal_items_schema_keys():
    required_keys = {
        "source", "signal_type", "official", "evidence_level",
        "rank", "keyword", "observed_at", "source_url", "collection_method",
    }
    items = ["키워드"]
    result = normalize_signal_items("signal_bz", items)
    assert required_keys <= set(result[0].keys())


# ── normalize_doc_items ────────────────────────────────────────────────────

def test_normalize_doc_items_basic():
    items = [
        {"title": "제목1", "body": "본문1", "url": "https://example.com/1", "time": "2026-06-03", "score": 42},
    ]
    result = normalize_doc_items("dcinside", items)
    assert len(result) == 1
    assert result[0]["source"] == "dcinside"
    assert result[0]["title"] == "제목1"
    assert result[0]["body"] == "본문1"
    assert result[0]["score"] == 42


def test_normalize_doc_items_published_at_fallback():
    items = [{"title": "t", "body": "b", "url": "u", "published_at": "2026-01-01"}]
    result = normalize_doc_items("fmkorea", items)
    assert result[0]["time"] == "2026-01-01"


def test_normalize_doc_items_skips_non_dicts():
    items = ["string_item", {"title": "ok", "body": "", "url": ""}]
    result = normalize_doc_items("dcinside", items)
    assert len(result) == 1


def test_normalize_doc_items_empty():
    result = normalize_doc_items("fmkorea", [])
    assert result == []


def test_normalize_doc_items_schema_keys():
    required_keys = {"source", "title", "body", "url", "time", "score"}
    items = [{"title": "t", "body": "b", "url": "u"}]
    result = normalize_doc_items("dcinside", items)
    assert required_keys <= set(result[0].keys())
