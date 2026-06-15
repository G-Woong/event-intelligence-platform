"""G-4: vendor 공식 API route — 정규화 + key-free evidence URL + 키 미누출(네트워크 0, 주입형)."""
from __future__ import annotations

import json

from ingestion.orchestration.vendor_api_routes import (
    fetch_bok_ecos,
    fetch_eia,
    fetch_gdelt,
    fetch_kma,
    fetch_nyt,
    fetch_vendor,
    has_vendor_route,
)

_ENV = {"BOK_ECOS_API_KEY": "SECRETKEY", "EIA_API_KEY": "SECRETKEY",
        "KMA_API_KEY": "SECRETKEY", "NYT_API_KEY": "SECRETKEY"}


def _no_key_leak(records):
    blob = json.dumps([dict(r) for r in records], ensure_ascii=False).lower()
    assert "secretkey" not in blob
    assert "servicekey" not in blob and "api_key=" not in blob and "api-key" not in blob


def test_bok_ecos_normalizes_rows():
    def http(url, params=None):
        return 200, {"StatisticSearch": {"row": [
            {"STAT_NAME": "기준금리", "ITEM_NAME1": "한국은행 기준금리", "UNIT_NAME": "%",
             "TIME": "202501", "DATA_VALUE": "3.0"}]}}, None
    r = fetch_bok_ecos(env=_ENV, http_get=http)
    assert r.success and r.record_type == "structured_signal" and r.item_count == 1
    rec = r.records[0]
    assert rec["published_at_or_observed_at"] == "2025-01"
    assert rec["source_url_or_evidence"].startswith("https://ecos.bok.or.kr")
    _no_key_leak(r.records)


def test_eia_drops_api_key_from_evidence():
    def http(url, params=None):
        return 200, {"response": {"data": [
            {"period": "2026-03", "series-description": "NG price", "value": 5.1, "units": "$"}]}}, None
    r = fetch_eia(env=_ENV, http_get=http)
    assert r.success and r.records[0]["published_at_or_observed_at"] == "2026-03"
    _no_key_leak(r.records)


def test_kma_result_code_00_ok():
    def http(url, params=None):
        return 200, {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                                  "body": {"items": {"item": [
                                      {"category": "T1H", "obsrValue": "21", "nx": 60, "ny": 127}]}}}}, None
    r = fetch_kma(env=_ENV, http_get=http)
    assert r.success and r.item_count == 1
    assert r.records[0]["body_state_or_signal"] == "weather_observation"
    _no_key_leak(r.records)


def test_kma_result_code_error_fails():
    def http(url, params=None):
        return 200, {"response": {"header": {"resultCode": "10", "resultMsg": "INVALID_REQUEST"}}}, None
    r = fetch_kma(env=_ENV, http_get=http)
    assert r.success is False and "result_code_10" in r.error


def test_nyt_article_search_uses_web_url():
    def http(url, params=None):
        return 200, {"response": {"docs": [
            {"headline": {"main": "Big Story"}, "web_url": "https://nytimes.com/2026/a.html",
             "pub_date": "2026-06-15T10:00:00Z", "abstract": "x"}]}}, None
    r = fetch_nyt(env=_ENV, http_get=http)
    assert r.success and r.record_type == "article_candidate"
    rec = r.records[0]
    assert rec["source_url_or_evidence"] == "https://nytimes.com/2026/a.html"
    assert rec["body_state_or_signal"] == "snippet_only"  # 공식 API는 abstract만(전문 아님)
    _no_key_leak(r.records)


def test_nyt_skips_docs_without_url():
    def http(url, params=None):
        return 200, {"response": {"docs": [{"headline": {"main": "no url"}, "web_url": None}]}}, None
    r = fetch_nyt(env=_ENV, http_get=http)
    assert r.success is False  # url 없는 doc만 → 레코드 0


def test_gdelt_no_key_needed():
    def http(url, params=None):
        return 200, {"articles": [
            {"title": "T", "url": "https://x.test/a", "seendate": "20260615T100000Z"}]}, None
    r = fetch_gdelt(http_get=http)
    assert r.success and r.record_type == "official_record"


def test_gdelt_429_reported_not_bypassed():
    def http(url, params=None):
        return 429, None, "Please limit requests to one every 5 seconds"
    r = fetch_gdelt(http_get=http)
    assert r.success is False and r.error == "provider_rate_limited"


def test_key_missing_returns_failure(monkeypatch):
    # os.environ에 실제 키가 있을 수 있으므로 격리(존재 여부만, 값은 안 읽음)
    for n in ("BOK_ECOS_API_KEY", "ECOS_API_KEY"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr("ingestion.orchestration.vendor_api_routes.load_env", lambda *a, **k: {})
    r = fetch_bok_ecos(env={}, http_get=lambda u, p=None: (200, {}, None))
    assert r.success is False and r.error == "key_missing"


def test_has_vendor_route_and_dispatch():
    assert has_vendor_route("bok_ecos") and has_vendor_route("gdelt")
    assert not has_vendor_route("bbc")
    assert fetch_vendor("bbc") is None
