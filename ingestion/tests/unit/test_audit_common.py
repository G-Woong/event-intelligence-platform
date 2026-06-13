"""_audit_common(docs/85 Step 2) 단위 테스트 — 전부 네트워크 없음."""
from __future__ import annotations

import json

import pytest

from ingestion.runners._audit_common import (
    AUDIT_EXCLUDED_IDS,
    evaluate_event_seed_fields,
    extract_sample_items,
    gate_check,
    load_audit_sources,
    relevance_label,
    relevance_score,
    seed_ready_label,
)


# ── seed 필드 평가 경계 ──────────────────────────────────────────────────────

def test_seed_fields_three_or_more_is_ready():
    count, fields = evaluate_event_seed_fields({
        "title": "삼성전자 발표", "url": "https://x.test/1", "source_id": "yna",
    })
    assert count == 3
    assert set(fields) == {"title", "url", "source_id"}
    assert seed_ready_label(count) == "yes"


def test_seed_fields_two_is_partial():
    count, _ = evaluate_event_seed_fields({"title": "t", "source_id": "bbc"})
    assert count == 2
    assert seed_ready_label(count) == "partial"


def test_seed_fields_empty_strings_not_counted():
    count, fields = evaluate_event_seed_fields({
        "title": "  ", "url": "", "snippet": None, "source_id": "bbc",
    })
    assert count == 1
    assert fields == ["source_id"]
    assert seed_ready_label(count) == "no"


def test_seed_fields_published_at_counts_as_timestamp():
    count, fields = evaluate_event_seed_fields({
        "title": "t", "published_at": "2026-06-13T00:00:00Z", "source_id": "gdelt",
    })
    assert "timestamp" in fields
    assert count == 3


# ── relevance ────────────────────────────────────────────────────────────────

def test_relevance_english_tokens():
    score = relevance_score("AI semiconductor", "AI chip makers expand semiconductor capacity")
    assert score == 1.0
    assert relevance_label(score) == "high"


def test_relevance_korean_2gram():
    score = relevance_score("삼성전자", "삼성전자, 신규 반도체 공장 착공", "")
    assert score == 1.0


def test_relevance_partial_korean():
    # "주식 급등" → 주식/급등 2-gram, snippet에 '주식'만 존재
    score = relevance_score("주식 급등", "코스피 주식 시장 동향", "")
    assert 0.0 < score < 1.0


def test_relevance_no_match_is_low():
    score = relevance_score("climate disaster", "박스오피스 1위 영화", "")
    assert score == 0.0
    assert relevance_label(score) == "low"


def test_relevance_empty_query():
    assert relevance_score("", "anything") == 0.0


# ── 소스 필터 ────────────────────────────────────────────────────────────────

def test_load_audit_sources_excludes_forbidden():
    sources = load_audit_sources()
    ids = {s["id"] for s in sources}
    assert ids.isdisjoint(AUDIT_EXCLUDED_IDS)
    assert "_dummy" not in ids
    assert "bbc" in ids
    assert "gdelt" in ids


def test_load_audit_sources_layer_filter():
    sources = load_audit_sources(layers=["market_signal"])
    assert sources, "market_signal 소스가 있어야 함"
    assert all(s["layer"] == "market_signal" for s in sources)
    ids = {s["id"] for s in sources}
    assert "finnhub" in ids
    assert "bbc" not in ids


# ── JSON sample 추출 (소스별 fake payload) ───────────────────────────────────

def _write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return str(p)


def test_extract_samples_serper(tmp_path):
    path = _write(tmp_path, "serper.json", {
        "organic": [
            {"title": "Result A", "link": "https://a.test", "snippet": "about A"},
            {"title": "Result B", "link": "https://b.test", "snippet": "about B"},
        ]
    })
    samples = extract_sample_items("serper", path)
    assert len(samples) == 2
    assert samples[0]["title"] == "Result A"
    assert samples[0]["url"] == "https://a.test"
    assert samples[0]["snippet"] == "about A"


def test_extract_samples_naver_strips_tags(tmp_path):
    path = _write(tmp_path, "naver.json", {
        "items": [{
            "title": "<b>삼성전자</b> 실적 발표",
            "link": "https://n.news.naver.com/1",
            "description": "설명 <b>강조</b> 텍스트",
            "pubDate": "Fri, 13 Jun 2026 09:00:00 +0900",
        }]
    })
    samples = extract_sample_items("naver_news_search", path)
    assert samples[0]["title"] == "삼성전자 실적 발표"
    assert samples[0]["snippet"] == "설명 강조 텍스트"
    assert samples[0]["published_at"].startswith("Fri, 13 Jun 2026")


def test_extract_samples_guardian_nested_path(tmp_path):
    path = _write(tmp_path, "guardian.json", {
        "response": {"results": [{
            "webTitle": "Guardian headline",
            "webUrl": "https://www.theguardian.com/x",
            "sectionName": "World",
            "webPublicationDate": "2026-06-13T01:00:00Z",
        }]}
    })
    samples = extract_sample_items("guardian", path)
    assert samples[0]["title"] == "Guardian headline"
    assert samples[0]["url"].startswith("https://www.theguardian.com")


def test_extract_samples_nyt_headline_main(tmp_path):
    path = _write(tmp_path, "nyt.json", {
        "response": {"docs": [{
            "headline": {"main": "NYT headline"},
            "web_url": "https://www.nytimes.com/x",
            "abstract": "abstract text",
            "pub_date": "2026-06-13T00:00:00+0000",
        }]}
    })
    samples = extract_sample_items("nyt", path)
    assert samples[0]["title"] == "NYT headline"
    assert samples[0]["published_at"] == "2026-06-13T00:00:00+0000"


def test_extract_samples_youtube_video_url(tmp_path):
    path = _write(tmp_path, "yt.json", {
        "items": [{
            "id": {"videoId": "abc123"},
            "snippet": {"title": "Video title", "description": "desc",
                        "publishedAt": "2026-06-12T00:00:00Z"},
        }]
    })
    samples = extract_sample_items("youtube", path)
    assert samples[0]["url"] == "https://www.youtube.com/watch?v=abc123"
    assert samples[0]["title"] == "Video title"


def test_extract_samples_gdelt(tmp_path):
    path = _write(tmp_path, "gdelt.json", {
        "articles": [{"title": "GDELT art", "url": "https://g.test",
                      "domain": "g.test", "seendate": "20260613T010000Z"}]
    })
    samples = extract_sample_items("gdelt", path)
    assert samples[0]["title"] == "GDELT art"
    assert samples[0]["published_at"] == "20260613T010000Z"


def test_extract_samples_generic_fallback(tmp_path):
    # 매핑 없는 소스 — generic list/title 키 추론
    path = _write(tmp_path, "unknown.json", {
        "results": [{"title": "Generic", "url": "https://u.test",
                     "description": "d", "date": "2026-06-13"}]
    })
    samples = extract_sample_items("some_unmapped_source", path)
    assert samples[0]["title"] == "Generic"
    assert samples[0]["url"] == "https://u.test"


def test_extract_samples_flat_dict_returns_empty(tmp_path):
    # finnhub quote — list 없음 → 빈 샘플 (정직한 결과)
    path = _write(tmp_path, "finnhub.json", {"c": 1.0, "h": 2.0, "l": 0.5, "o": 1.2, "pc": 1.1})
    assert extract_sample_items("finnhub", path) == []


def test_extract_samples_xml_rss(tmp_path):
    p = tmp_path / "feed.xml"
    p.write_text(
        "<?xml version='1.0'?><rss><channel>"
        "<item><title>RSS one</title><link>https://r.test/1</link>"
        "<description>first</description><pubDate>Fri, 13 Jun 2026 00:00:00 GMT</pubDate></item>"
        "<item><title>RSS two</title><link>https://r.test/2</link></item>"
        "</channel></rss>",
        encoding="utf-8",
    )
    samples = extract_sample_items("yna", str(p))
    assert len(samples) == 2
    assert samples[0]["title"] == "RSS one"
    assert samples[0]["url"] == "https://r.test/1"
    assert samples[0]["published_at"].endswith("GMT")


def test_extract_samples_missing_file():
    assert extract_sample_items("bbc", None) == []
    assert extract_sample_items("bbc", "Z:/does/not/exist.json") == []


# ── 절단 규칙 ────────────────────────────────────────────────────────────────

def test_truncation_rules(tmp_path):
    long_title = "T" * 500
    long_snippet = "S" * 500
    path = _write(tmp_path, "long.json", {
        "organic": [{"title": long_title, "link": "https://a.test", "snippet": long_snippet}]
    })
    samples = extract_sample_items("serper", path)
    assert len(samples[0]["title"]) == 120
    assert len(samples[0]["snippet"]) == 200


# ── gate_check (store 주입, 네트워크 없음) ──────────────────────────────────

def test_gate_check_health_skip(monkeypatch):
    from ingestion.core.source_health import (
        BLOCKED_TERMINAL,
        InMemorySourceHealthStore,
        SourceHealthState,
        reset_health_store_for_tests,
    )
    store = InMemorySourceHealthStore()
    store.set(SourceHealthState(source_id="bbc", state=BLOCKED_TERMINAL))
    reset_health_store_for_tests(store)
    try:
        assert gate_check("bbc") == "health_skip"
    finally:
        reset_health_store_for_tests(None)


def test_gate_check_cooldown_then_cache(monkeypatch):
    from ingestion.core.source_health import (
        InMemorySourceHealthStore, reset_health_store_for_tests,
    )
    reset_health_store_for_tests(InMemorySourceHealthStore())
    import ingestion.runners._audit_common as ac

    monkeypatch.setattr("ingestion.core.rate_limit_policy.in_cooldown",
                        lambda sid, q="": (True, "2099-01-01T00:00:00Z"))
    try:
        assert ac.gate_check("gdelt") == "cooldown_skip"
    finally:
        reset_health_store_for_tests(None)


def test_gate_check_cache_skip(monkeypatch):
    from ingestion.core.source_health import (
        InMemorySourceHealthStore, reset_health_store_for_tests,
    )
    reset_health_store_for_tests(InMemorySourceHealthStore())
    import ingestion.runners._audit_common as ac

    monkeypatch.setattr("ingestion.core.rate_limit_policy.in_cooldown",
                        lambda sid, q="": (False, None))
    monkeypatch.setattr("ingestion.core.rate_limit_policy.is_cached",
                        lambda sid, q="": True)
    try:
        assert ac.gate_check("gdelt", query="삼성") == "cache_skip"
    finally:
        reset_health_store_for_tests(None)


def test_gate_check_clear_returns_none(monkeypatch):
    from ingestion.core.source_health import (
        InMemorySourceHealthStore, reset_health_store_for_tests,
    )
    reset_health_store_for_tests(InMemorySourceHealthStore())
    monkeypatch.setattr("ingestion.core.rate_limit_policy.in_cooldown",
                        lambda sid, q="": (False, None))
    monkeypatch.setattr("ingestion.core.rate_limit_policy.is_cached",
                        lambda sid, q="": False)
    try:
        assert gate_check("hacker_news") is None
    finally:
        reset_health_store_for_tests(None)
