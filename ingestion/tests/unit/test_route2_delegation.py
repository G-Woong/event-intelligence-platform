"""Route 2 위임 + search_url + 본문 cascade + raw_signal sample 단위 테스트 (docs/07)."""
from __future__ import annotations

from unittest.mock import MagicMock


def test_route2_delegates_to_playwright_probe_for_spec_sites(monkeypatch):
    from ingestion.fetch_strategies import collection_probe as cp
    from ingestion.probes.models import ProbeResult
    captured = {}

    def fake_probe(site_id, query=None, region=None, max_items=10):
        captured.update(site_id=site_id, query=query, max_items=max_items)
        return ProbeResult(source_id=site_id, method="playwright",
                           status="LIVE_SUCCESS", items_found=7)

    monkeypatch.setattr("ingestion.probes.playwright_probe.run_playwright_probe", fake_probe)
    result = cp.run_collection_probe("signal_bz", query="삼성", max_items=10, force=True)
    assert captured["site_id"] == "signal_bz" and captured["query"] == "삼성"
    assert captured["max_items"] == 10
    assert result.items_found == 7
    assert result.strategy_used == "playwright_site_spec"


def test_route2_429_next_retry_flows_to_health(monkeypatch):
    """위임 결과의 next_retry_at이 health update path(_update_health)로 전달된다."""
    from ingestion.fetch_strategies import collection_probe as cp
    from ingestion.probes.models import ProbeResult
    captured = {}

    def fake_probe(site_id, query=None, region=None, max_items=10):
        return ProbeResult(source_id=site_id, method="playwright",
                           status="RATE_LIMITED", items_found=0,
                           next_retry_at="2026-06-13T12:00:00Z")

    def fake_apply(prev, source_id, status, error_category, next_retry_at):
        captured["next_retry_at"] = next_retry_at
        return prev

    monkeypatch.setattr("ingestion.probes.playwright_probe.run_playwright_probe", fake_probe)
    monkeypatch.setattr("ingestion.core.source_health.apply_probe_outcome", fake_apply)
    monkeypatch.setattr("ingestion.core.source_health.get_health_store",
                        lambda: MagicMock())
    cp.run_collection_probe("signal_bz", force=True)
    assert captured["next_retry_at"] == "2026-06-13T12:00:00Z"


def test_route2_falls_back_to_cloud_browser_without_spec(monkeypatch):
    """site spec 없는 playwright 소스는 기존 CloudBrowserLike 경로를 유지한다."""
    from ingestion.fetch_strategies import collection_probe as cp
    from ingestion.fetch_strategies.models import RenderedPageFetchResult

    monkeypatch.setattr("ingestion.probes.site_specs.load_site_specs",
                        lambda config_path=None: {})
    monkeypatch.setattr(cp, "_SERVICE_CONFIGS",
                        {"dcinside": {"endpoint": "https://gall.dcinside.com"}})

    rendered = RenderedPageFetchResult(
        url="https://gall.dcinside.com", strategy_used="playwright_basic",
        html="<html>x</html>", markdown="x", status="LIVE_SUCCESS",
    )
    mock_strategy = MagicMock()
    mock_strategy.return_value.fetch.return_value = rendered
    monkeypatch.setattr(
        "ingestion.fetch_strategies.cloud_browser_like.CloudBrowserLikeStrategy",
        mock_strategy,
    )
    result = cp.run_collection_probe("dcinside", force=True)
    assert result.strategy_used == "playwright_basic"
    assert result.extraction is not None
    assert result.extraction.rendered_page is not None


def test_search_url_used_when_query_present(monkeypatch):
    from ingestion.probes import playwright_probe as pp
    captured: dict = {"urls": []}

    async def fake_open_page(url, **kwargs):
        captured["urls"].append(url)
        return "<html><body><p>검색 결과 페이지</p></body></html>"

    monkeypatch.setattr(pp, "open_page", fake_open_page)
    pp.run_playwright_probe("dcinside", query="삼성전자", max_items=5)
    assert any("search.dcinside.com" in u for u in captured["urls"])


def test_start_url_used_without_query(monkeypatch):
    from ingestion.probes import playwright_probe as pp
    captured: dict = {"urls": []}

    async def fake_open_page(url, **kwargs):
        captured["urls"].append(url)
        return "<html><body><p>갤러리 목록</p></body></html>"

    monkeypatch.setattr(pp, "open_page", fake_open_page)
    pp.run_playwright_probe("dcinside", max_items=5)
    assert any("gall.dcinside.com" in u for u in captured["urls"])
    assert not any("search.dcinside.com" in u for u in captured["urls"])


def test_signal_bz_items_have_rank(monkeypatch):
    from ingestion.probes import playwright_probe as pp
    html = '<html><body>' + "".join(
        f'<div class="rank-tex">키워드{i}</div>' for i in range(5)) + '</body></html>'

    async def fake_open_page(url, **kwargs):
        return html

    monkeypatch.setattr(pp, "open_page", fake_open_page)
    result = pp.run_playwright_probe("signal_bz", max_items=5)
    assert result.items_found == 5
    # raw_signal 파일에 rank 필드가 들어가는지 확인
    import json
    from pathlib import Path
    sig_path = result.artifact_paths.get("raw_signal")
    assert sig_path
    items = json.loads(Path(sig_path).read_text(encoding="utf-8"))
    assert items[0]["rank"] == 1 and items[4]["rank"] == 5


def test_body_cascade_falls_back(monkeypatch):
    from ingestion.fetch_strategies.article_body_extractor import extract_article_body
    import ingestion.fetch_strategies.article_body_extractor as abe
    monkeypatch.setattr(abe, "_try_trafilatura", lambda h, u: None)
    html = ("<html><body><article><h1>제목</h1>"
            + "<p>본문 문단입니다. " * 30 + "</p></article></body></html>")
    out = extract_article_body(html, "https://x.test/1")
    assert out and out["method"] in ("readability", "dom_heuristic")
    assert len(out["body"]) >= 200


def test_body_cascade_trafilatura_first():
    from ingestion.fetch_strategies.article_body_extractor import extract_article_body
    html = ("<html><body><article><h1>뉴스 제목</h1>"
            + "<p>이것은 실제 기사 본문 문단입니다. 사건이 발생했습니다. " * 20
            + "</p></article></body></html>")
    out = extract_article_body(html, "https://x.test/news")
    assert out and out["method"] == "trafilatura"
    assert len(out["body"]) >= 200


def test_body_cascade_blocked_or_empty_returns_none(monkeypatch):
    from ingestion.fetch_strategies.article_body_extractor import extract_article_body
    assert extract_article_body("", "https://x") is None
    assert extract_article_body("<html><body><p>x</p></body></html>", "https://x") is None


def test_body_site_selector_avoids_boilerplate():
    """site 지정 본문 selector가 cascade보다 우선되어 공통 안내 박스를 회피한다."""
    from ingestion.fetch_strategies.article_body_extractor import extract_article_body
    html = ('<html><body>'
            '<div class="notice">자동 짤방 이미지 개선 안내문구 ' + '안내 ' * 60 + '</div>'
            '<div class="write_div">실제 게시글 본문입니다. ' + '내용 ' * 40 + '</div>'
            '</body></html>')
    out = extract_article_body(html, "https://dc.test/1", body_selectors=[".write_div"])
    assert out and out["method"] == "site_selector"
    assert "실제 게시글 본문" in out["body"]
    assert "자동 짤방" not in out["body"]


def test_body_site_selector_missing_falls_through_to_cascade():
    from ingestion.fetch_strategies.article_body_extractor import extract_article_body
    html = ("<html><body><article><h1>제목</h1>"
            + "<p>일반 기사 본문 문단입니다. " * 25 + "</p></article></body></html>")
    out = extract_article_body(html, "https://x.test/1", body_selectors=[".nonexistent_body"])
    assert out and out["method"] == "trafilatura"


def test_collect_samples_reads_raw_signal_json(tmp_path):
    import json
    p = tmp_path / "sig.json"
    p.write_text(json.dumps([{"keyword": "실검1", "url": "https://a"}]), encoding="utf-8")
    from ingestion.runners._audit_common import extract_sample_items
    samples = extract_sample_items("signal_bz", str(p))
    assert samples and samples[0]["title"] == "실검1"
