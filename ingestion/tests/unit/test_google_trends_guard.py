from __future__ import annotations

import pytest

from ingestion.core.rate_limit_policy import (
    _call_cache,
    load_rate_limit_policy,
    record_rate_limited,
)
from ingestion.core.rate_limit_store import reset_store_for_tests


@pytest.fixture(autouse=True)
def _clean_store():
    reset_store_for_tests()
    _call_cache.clear()
    yield
    reset_store_for_tests()
    _call_cache.clear()


# ── 정책 하한 (12-6 강화값) ───────────────────────────────────────────────

@pytest.mark.parametrize("source_id", ["google_trends_explore", "google_trending_now"])
def test_trends_policy_floor(source_id):
    policy = load_rate_limit_policy(source_id)
    assert policy.min_interval_seconds >= 7200
    assert policy.cooldown_on_429_seconds >= 3600
    assert policy.cache_ttl_seconds >= 7200
    assert policy.max_retries_on_429 == 0


# ── 429 감지 → next_retry_at 영속 (Route 2 / CloudBrowserLikeStrategy) ────

def test_rendered_429_returns_rate_limited_and_persists(monkeypatch, tmp_path):
    from ingestion.core.rate_limit_store import get_store
    from ingestion.fetch_strategies.cloud_browser_like import CloudBrowserLikeStrategy
    from ingestion.tools import playwright_browser_tool

    monkeypatch.setattr(
        playwright_browser_tool, "fetch_with_playwright_sync",
        lambda url, strategy=None, screenshot_dir=None, dom_dir=None:
            "<html><body>429 Too Many Requests</body></html>",
    )
    result = CloudBrowserLikeStrategy().fetch(
        "https://trends.google.com/trending", "google_trends_explore",
        take_screenshot=False, save_dom=False,
    )
    # RATE_LIMITED가 UNKNOWN/FAILED/BLOCKED으로 떨어지지 않는다
    assert result.status == "RATE_LIMITED"
    # cooldown deadline이 store에 영속화된다
    assert get_store().get_next_retry_at("google_trends_explore:") is not None


def test_playwright_probe_429_path_persists(monkeypatch):
    """playwright_probe 429 경로가 record_rate_limited로 deadline을 영속화한다."""
    from ingestion.core.rate_limit_store import get_store
    from ingestion.probes import playwright_probe as pp

    async def _fake_open_page(url, **kwargs):
        return "<html>rate limit exceeded</html>"

    monkeypatch.setattr(pp, "open_page", _fake_open_page)
    result = pp.run_playwright_probe("google_trends_explore", query="ai")
    assert result.status == "RATE_LIMITED"
    assert result.next_retry_at is not None
    assert get_store().get_next_retry_at("google_trends_explore:ai") == result.next_retry_at


# ── cooldown 중 재호출 → 네트워크 미호출 ──────────────────────────────────

def test_cooldown_blocks_strategy_loop_without_network(monkeypatch):
    from ingestion.fetch_strategies.strategy_runner import run_fetch_strategy_loop

    record_rate_limited("google_trends_explore", cooldown_seconds=3600)

    import ingestion.agents.graph as graph
    monkeypatch.setattr(
        graph, "_fetch_with_strategy",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network must not be called")),
    )
    result = run_fetch_strategy_loop(
        "google_trends_explore", "https://trends.google.com"
    )
    assert result.status == "rate_limited"
    assert result.attempts == []


# ── status 매핑 보존 ──────────────────────────────────────────────────────

def test_rate_limited_is_a_valid_probe_status_not_unknown():
    from ingestion.fetch_strategies.collection_probe import _loop_status_to_probe_status
    from ingestion.probes.models import PROBE_STATUS

    assert "RATE_LIMITED" in PROBE_STATUS
    assert _loop_status_to_probe_status("rate_limited") == "RATE_LIMITED"
    # RATE_LIMITED_DEFERRED 같은 신규 literal은 추가하지 않는다 (PROBE_STATUS 강제)
    assert "RATE_LIMITED_DEFERRED" not in PROBE_STATUS
