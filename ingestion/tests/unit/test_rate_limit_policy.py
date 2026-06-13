from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ingestion.core.rate_limit_policy import (
    RateLimitPolicy,
    cache_key,
    is_cached,
    load_rate_limit_policy,
    record_call,
    _call_cache,
)


# ── default policy load ───────────────────────────────────────────────────

def test_load_default_policy_returns_dataclass():
    policy = load_rate_limit_policy("unknown_source_xyz")
    assert isinstance(policy, RateLimitPolicy)
    assert policy.max_calls_per_run >= 1
    assert policy.cooldown_on_429_seconds >= 0


def test_gdelt_policy_has_longer_cooldown():
    policy = load_rate_limit_policy("gdelt")
    assert policy.cooldown_on_429_seconds >= 60
    assert policy.min_interval_seconds >= 1


def test_gdelt_has_cache_ttl():
    policy = load_rate_limit_policy("gdelt")
    assert policy.cache_ttl_seconds > 0


def test_unknown_source_gets_default_cooldown():
    default = load_rate_limit_policy("nonexistent_source")
    gdelt = load_rate_limit_policy("gdelt")
    assert gdelt.cooldown_on_429_seconds >= default.cooldown_on_429_seconds


# ── default + per_source merge ─────────────────────────────────────────────

def test_per_source_overrides_default():
    """gdelt should override default min_interval_seconds."""
    default = load_rate_limit_policy("default_fallback_xyz")
    gdelt = load_rate_limit_policy("gdelt")
    assert gdelt.min_interval_seconds > default.min_interval_seconds


def test_yaml_fallback_on_missing_file():
    """If YAML file not found, returns default RateLimitPolicy without raising."""
    with patch("ingestion.core.rate_limit_policy._POLICY_PATH", Path("/nonexistent/path.yaml")):
        policy = load_rate_limit_policy("gdelt")
    assert isinstance(policy, RateLimitPolicy)


# ── 429 → ErrorType.RATE_LIMITED ─────────────────────────────────────────

def test_classify_http_429_returns_rate_limited():
    from ingestion.core.error_taxonomy import ErrorType, classify_http_error
    assert classify_http_error(429) == ErrorType.RATE_LIMITED


def test_classify_http_429_distinct_from_4xx():
    from ingestion.core.error_taxonomy import ErrorType, classify_http_error
    assert classify_http_error(403) == ErrorType.HTTP_4XX
    assert classify_http_error(429) != ErrorType.HTTP_4XX


def test_probe_status_rate_limited_maps_correctly():
    from ingestion.core.error_taxonomy import ErrorType
    from ingestion.fetch_strategies.failure_classifier import _PROBE_STATUS_TO_ERROR_TYPE
    assert _PROBE_STATUS_TO_ERROR_TYPE["RATE_LIMITED"] == ErrorType.RATE_LIMITED


# ── in-process TTL cache ───────────────────────────────────────────────────

def test_not_cached_before_first_call():
    # Use a source with no cache_ttl so it's effectively disabled
    assert not is_cached("bbc", "q=test_unique_xyz_abc")


def test_record_and_check_cache_within_ttl():
    """After recording a call, is_cached returns True within TTL window."""
    source = "gdelt"
    query = "test_cache_check_query_unique"
    _call_cache.clear()
    record_call(source, query)
    assert is_cached(source, query)


def test_cache_expires_after_ttl(monkeypatch):
    """Simulate TTL expiry by adjusting monotonic time."""
    source = "gdelt"
    query = "test_cache_expiry_unique"
    _call_cache.clear()
    record_call(source, query)

    # Monkey-patch time.monotonic to be far in the future
    original_monotonic = time.monotonic
    far_future = original_monotonic() + 9999
    monkeypatch.setattr(time, "monotonic", lambda: far_future)
    assert not is_cached(source, query)


def test_zero_ttl_never_cached():
    """Sources with cache_ttl_seconds=0 are never considered cached."""
    # bbc has no per_source override, default ttl=0
    record_call("bbc", "some_query")
    assert not is_cached("bbc", "some_query")


# ── max_retries_on_429 ────────────────────────────────────────────────────

def test_gdelt_max_retries_on_429():
    policy = load_rate_limit_policy("gdelt")
    assert policy.max_retries_on_429 >= 1


def test_default_max_retries_on_429():
    policy = load_rate_limit_policy("some_unknown_source")
    assert policy.max_retries_on_429 >= 1


# ── Fix 3: google_trends per_source policy ────────────────────────────────

def test_google_trends_explore_has_long_interval():
    policy = load_rate_limit_policy("google_trends_explore")
    assert policy.min_interval_seconds >= 1800


def test_google_trending_now_has_long_interval():
    policy = load_rate_limit_policy("google_trending_now")
    assert policy.min_interval_seconds >= 1800


def test_google_trends_explore_has_cache_ttl():
    policy = load_rate_limit_policy("google_trends_explore")
    assert policy.cache_ttl_seconds >= 1800


def test_google_trends_explore_zero_retries_on_429():
    policy = load_rate_limit_policy("google_trends_explore")
    assert policy.max_retries_on_429 == 0


# ── Fix 2: TTL cache wiring in strategy_runner ────────────────────────────

def test_cached_source_skips_live_fetch():
    """run_fetch_strategy_loop returns 'cached' status when is_cached=True."""
    from ingestion.fetch_strategies.strategy_runner import run_fetch_strategy_loop
    from ingestion.core.rate_limit_policy import _call_cache
    import time

    _call_cache["google_trends_explore:test_q"] = time.monotonic()
    result = run_fetch_strategy_loop("google_trends_explore", "https://trends.google.com", query="test_q")
    assert result.status == "cached"
    assert result.attempts == []


def test_non_cached_source_proceeds_to_fetch():
    """Source without cache TTL never returns 'cached'."""
    from ingestion.fetch_strategies.strategy_runner import run_fetch_strategy_loop
    from ingestion.core.rate_limit_policy import _call_cache
    from unittest.mock import patch

    # bbc has no cache_ttl (default=0), so is_cached always False
    _call_cache.pop("bbc:", None)
    with patch("ingestion.agents.graph._fetch_with_strategy", return_value=("<html>ok</html>", None, None)):
        result = run_fetch_strategy_loop("bbc", "https://bbc.com")
    assert result.status != "cached"


# ── 429 detection helper (playwright_probe) ───────────────────────────────────

def test_detect_429_on_too_many_requests_string():
    from ingestion.probes.playwright_probe import _detect_429
    assert _detect_429("429 too many requests") is True


def test_detect_429_on_rate_limit_exceeded():
    from ingestion.probes.playwright_probe import _detect_429
    assert _detect_429("rate limit exceeded") is True


def test_detect_429_false_on_normal_html():
    from ingestion.probes.playwright_probe import _detect_429
    assert _detect_429("<html><body>hello world</body></html>") is False


def test_detect_429_case_insensitive():
    from ingestion.probes.playwright_probe import _detect_429
    # _detect_429 accepts raw HTML (performs its own .lower() internally)
    assert _detect_429("TOO MANY REQUESTS") is True


# ── network capture log parsing ──────────────────────────────────────────────

def test_network_log_entry_structure():
    """Network log entries must have url/method/status/content_type keys."""
    entry = {"url": "https://example.com/api", "method": "POST", "status": 200, "content_type": "application/json"}
    assert "url" in entry
    assert "method" in entry
    assert "status" in entry


def test_probe_result_network_log_serialisable():
    import json
    from ingestion.probes.models import ProbeResult
    entries = [{"url": "https://kind.krx.co.kr/api/list", "method": "POST", "status": 200, "content_type": "application/json"}]
    r = ProbeResult(source_id="krx_kind", method="playwright", status="LIVE_PARTIAL", network_log=entries)
    d = r.to_dict()
    text = json.dumps(d)
    assert "krx_kind" in text
    assert "network_log" in text
