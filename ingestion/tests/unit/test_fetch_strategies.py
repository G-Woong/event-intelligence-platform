from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ingestion.fetch_strategies.models import (
    ArtifactPaths,
    CollectionProbeResult,
    ExtractionBundle,
    FetchAttempt,
    RenderedPageFetchResult,
    StrategyLoopResult,
)


# ── model field checks ────────────────────────────────────────────────────

def test_collection_probe_result_defaults():
    r = CollectionProbeResult(source_id="bbc", status="LIVE_SUCCESS")
    assert r.items_found == 0
    assert r.attempts == []
    assert r.artifact_paths.raw_html is None


def test_artifact_paths_to_dict_excludes_none():
    ap = ArtifactPaths(raw_html="/tmp/foo.html")
    d = ap.to_dict()
    assert "raw_html" in d
    assert "screenshot" not in d


def test_rendered_page_fetch_result_fields():
    r = RenderedPageFetchResult(
        url="https://example.com",
        strategy_used="playwright_basic",
        html="<html>ok</html>",
        markdown="# ok",
        status="LIVE_SUCCESS",
        timing=1.5,
    )
    assert r.status == "LIVE_SUCCESS"
    assert r.markdown == "# ok"
    assert r.timing == 1.5


def test_strategy_loop_result_defaults():
    r = StrategyLoopResult(source_id="test", url="https://x.com", status="exhausted")
    assert r.attempts == []
    assert r.final_html is None


# ── run_collection_probe routing ──────────────────────────────────────────

def test_run_collection_probe_routes_to_api_probe():
    """Sources with probe spec go through run_api_live_probe."""
    from ingestion.fetch_strategies.collection_probe import run_collection_probe
    from ingestion.probes.models import ProbeResult

    mock_probe = ProbeResult(
        source_id="federal_register",
        method="api",
        status="LIVE_SUCCESS",
        items_found=3,
        meaningful_fields=["results"],
        artifact_paths={},
        next_action="integrate_into_pipeline",
    )
    with patch("ingestion.fetch_strategies.collection_probe.run_api_live_probe", return_value=mock_probe) as mock_fn:
        result = run_collection_probe("federal_register")
    mock_fn.assert_called_once_with("federal_register", max_calls=1)
    assert result.status == "LIVE_SUCCESS"
    assert result.strategy_used == "api"
    assert result.items_found == 3


def test_run_collection_probe_missing_key():
    from ingestion.fetch_strategies.collection_probe import run_collection_probe
    from ingestion.probes.models import ProbeResult

    mock_probe = ProbeResult(
        source_id="naver_news_search",
        method="api",
        status="MISSING_KEY",
        items_found=0,
        next_action="add_key_to_.env",
        artifact_paths={},
    )
    with patch("ingestion.fetch_strategies.collection_probe.run_api_live_probe", return_value=mock_probe):
        result = run_collection_probe("naver_news_search")
    assert result.status == "MISSING_KEY"
    assert result.items_found == 0


def test_run_collection_probe_playwright_first_delegates_to_playwright_probe():
    """site spec 보유 playwright 소스는 run_playwright_probe로 위임된다 (Route 2 구조 수정).

    이전엔 CloudBrowserLikeStrategy(렌더 힌트/selector 추출 없음)로 떨어졌으나,
    site spec(deferred=false)을 가진 소스는 이제 run_playwright_probe 단일 경로를 탄다.
    """
    from ingestion.fetch_strategies.collection_probe import (
        _PLAYWRIGHT_FIRST_SOURCES,
        run_collection_probe,
    )
    from ingestion.probes.models import ProbeResult

    assert "dcinside" in _PLAYWRIGHT_FIRST_SOURCES

    fake = ProbeResult(
        source_id="dcinside", method="playwright", status="LIVE_SUCCESS",
        items_found=5, artifact_paths={"raw_signal": "/tmp/x.json"},
    )
    with patch("ingestion.probes.playwright_probe.run_playwright_probe", return_value=fake):
        result = run_collection_probe("dcinside", force=True)

    assert result.status == "LIVE_SUCCESS"
    assert result.strategy_used == "playwright_site_spec"
    assert result.items_found == 5
    assert result.probe_result is fake


def test_run_collection_probe_unknown_source_returns_unknown():
    from ingestion.fetch_strategies.collection_probe import run_collection_probe
    result = run_collection_probe("nonexistent_source_xyz_abc")
    assert result.status == "UNKNOWN"


# ── CloudBrowserLikeStrategy result standard fields ───────────────────────

def test_cloud_browser_like_success_has_required_fields():
    from ingestion.fetch_strategies.cloud_browser_like import CloudBrowserLikeStrategy

    html = "<html><body><h1>Test</h1><p>Hello world article content here.</p></body></html>"
    with patch(
        "ingestion.tools.playwright_browser_tool.fetch_with_playwright_sync",
        return_value=html,
    ):
        strategy = CloudBrowserLikeStrategy()
        result = strategy.fetch("https://example.com", "test_source")

    assert result.url == "https://example.com"
    assert result.strategy_used == "playwright_basic"
    assert result.html is not None
    assert result.status == "LIVE_SUCCESS"
    assert result.timing >= 0.0
    assert hasattr(result, "markdown")
    assert hasattr(result, "screenshot_path")
    assert hasattr(result, "rendered_dom_path")
    assert hasattr(result, "extracted_text")


def test_cloud_browser_like_no_html_returns_network_error():
    from ingestion.core.error_taxonomy import ErrorType
    from ingestion.fetch_strategies.cloud_browser_like import CloudBrowserLikeStrategy

    with patch(
        "ingestion.tools.playwright_browser_tool.fetch_with_playwright_sync",
        return_value=None,
    ):
        strategy = CloudBrowserLikeStrategy()
        result = strategy.fetch("https://example.com", "test_source")

    assert result.status == "NETWORK_ERROR"
    assert result.error_category == ErrorType.JS_RENDER_FAIL


def test_cloud_browser_like_captcha_detected():
    from ingestion.core.error_taxonomy import ErrorType
    from ingestion.fetch_strategies.cloud_browser_like import CloudBrowserLikeStrategy

    captcha_html = "<html><body>just a moment...</body></html>"
    with patch(
        "ingestion.tools.playwright_browser_tool.fetch_with_playwright_sync",
        return_value=captcha_html,
    ):
        strategy = CloudBrowserLikeStrategy()
        result = strategy.fetch("https://example.com", "test_source")

    assert result.status == "BLOCKED"
    assert result.error_category == ErrorType.CAPTCHA_DETECTED


# ── write_collection_artifacts path propagation ───────────────────────────

def test_write_collection_artifacts_propagates_probe_paths():
    from ingestion.fetch_strategies.artifact_writer import write_collection_artifacts

    existing_paths = ArtifactPaths(
        raw_payload="/outputs/raw_payload/bbc/run1.json",
        extracted_payload="/outputs/extracted_payload/bbc/run1.json",
    )
    result = CollectionProbeResult(
        source_id="bbc",
        status="LIVE_SUCCESS",
        artifact_paths=existing_paths,
    )
    paths = write_collection_artifacts(result)
    assert paths.raw_payload == "/outputs/raw_payload/bbc/run1.json"
    assert paths.extracted_payload == "/outputs/extracted_payload/bbc/run1.json"


def test_write_collection_artifacts_saves_html_for_rendered_page(tmp_path):
    from ingestion.fetch_strategies.artifact_writer import write_collection_artifacts
    import ingestion.core.artifact_store as store_mod

    rendered = RenderedPageFetchResult(
        url="https://example.com",
        strategy_used="playwright_basic",
        html="<html>content</html>",
        markdown="# content",
        status="LIVE_SUCCESS",
    )
    bundle = ExtractionBundle(rendered_page=rendered, markdown="# content")
    result = CollectionProbeResult(
        source_id="test_src",
        status="LIVE_SUCCESS",
        extraction=bundle,
    )

    # Redirect output to tmp_path
    original_dir = store_mod._OUTPUTS_DIR
    store_mod._OUTPUTS_DIR = tmp_path
    try:
        paths = write_collection_artifacts(result)
    finally:
        store_mod._OUTPUTS_DIR = original_dir

    assert paths.raw_html is not None
    assert Path(paths.raw_html).name.endswith(".html")


# ── markdown_extractor ────────────────────────────────────────────────────

def test_extract_markdown_returns_extraction_result():
    from ingestion.tools.markdown_extractor import extract_markdown

    html = "<html><body><h1>Breaking News</h1><p>A major event happened today in the city.</p></body></html>"
    result = extract_markdown(html, "https://example.com/article")
    assert result.strategy == "trafilatura_markdown"
    assert result.url == "https://example.com/article"
    # success depends on trafilatura finding content in minimal html
    # body should be either present or failure is reported
    if result.success:
        assert result.body is not None
        assert len(result.body) > 0


def test_extract_markdown_empty_html_returns_failure():
    from ingestion.tools.markdown_extractor import extract_markdown

    result = extract_markdown("", "https://example.com")
    assert not result.success
    assert result.error_message is not None


def test_extract_markdown_body_is_string_when_success():
    from ingestion.tools.markdown_extractor import extract_markdown

    html = """<html><body>
    <article>
    <h1>Test Article</h1>
    <p>This is a longer article with enough content for trafilatura to extract.
    It contains multiple sentences to meet the minimum length requirement for extraction.</p>
    </article>
    </body></html>"""
    result = extract_markdown(html, "https://example.com/test")
    if result.success:
        assert isinstance(result.body, str)


# ── Fix 1: rate_limited → RATE_LIMITED mapping ────────────────────────────

def test_loop_status_rate_limited_maps_to_probe_rate_limited():
    from ingestion.fetch_strategies.collection_probe import _loop_status_to_probe_status
    assert _loop_status_to_probe_status("rate_limited") == "RATE_LIMITED"


def test_loop_status_cached_maps_to_live_success():
    from ingestion.fetch_strategies.collection_probe import _loop_status_to_probe_status
    assert _loop_status_to_probe_status("cached") == "LIVE_SUCCESS"


def test_loop_status_unknown_string_maps_to_unknown():
    from ingestion.fetch_strategies.collection_probe import _loop_status_to_probe_status
    assert _loop_status_to_probe_status("some_future_status") == "UNKNOWN"


# ── Fix 4: selenium Windows chrome detection ──────────────────────────────

def test_find_chrome_binary_returns_bool():
    from ingestion.fetch_strategies.selenium_strategy import _find_chrome_binary
    result = _find_chrome_binary()
    assert isinstance(result, bool)


def test_selenium_env_status_returns_expected_keys():
    from ingestion.fetch_strategies.selenium_strategy import selenium_env_status
    s = selenium_env_status()
    assert "selenium_installed" in s
    assert "chromedriver_found" in s
    assert "chrome_binary_found" in s
    assert "ready" in s


def test_find_chrome_binary_detects_windows_path(monkeypatch, tmp_path):
    """If a Windows-style chrome.exe path exists, _find_chrome_binary returns True."""
    import sys, os
    if sys.platform != "win32":
        return  # skip on non-Windows

    from ingestion.fetch_strategies import selenium_strategy as sel_mod
    import shutil

    fake_chrome = tmp_path / "chrome.exe"
    fake_chrome.write_text("fake")

    monkeypatch.setattr(shutil, "which", lambda name: None)  # PATH misses
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "pf86"))
    # Place chrome.exe at expected LOCALAPPDATA path
    app_dir = tmp_path / "Google" / "Chrome" / "Application"
    app_dir.mkdir(parents=True)
    (app_dir / "chrome.exe").write_text("fake")

    result = sel_mod._find_chrome_binary()
    assert result is True


# ── Fix 5: _JS_RENDER_STRATEGIES used in select_next_strategy ────────────

def test_js_render_strategies_includes_selenium():
    from ingestion.fetch_strategies.strategy_selection import _JS_RENDER_STRATEGIES
    assert "selenium_rendered_dom" in _JS_RENDER_STRATEGIES


def test_strategy_loop_result_docstring_has_rate_limited():
    from ingestion.fetch_strategies.models import StrategyLoopResult
    doc = StrategyLoopResult.__dataclass_fields__["status"].metadata
    # The status field comment is in the class docstring
    import inspect
    src = inspect.getsource(StrategyLoopResult)
    assert "rate_limited" in src
