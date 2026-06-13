from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from ingestion.core.error_taxonomy import BLOCKED_ERRORS, ErrorType
from ingestion.core.retry_policy import STRATEGY_SEQUENCE, RetryPolicy
from ingestion.fetch_strategies.models import FetchAttempt
from ingestion.fetch_strategies.strategy_runner import _default_policy, run_fetch_strategy_loop
from ingestion.fetch_strategies.strategy_selection import select_next_strategy


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)


@pytest.fixture(autouse=True)
def _clean_rate_limit_state():
    from ingestion.core.rate_limit_policy import _call_cache
    from ingestion.core.rate_limit_store import reset_store_for_tests
    reset_store_for_tests()
    _call_cache.clear()
    yield
    reset_store_for_tests()
    _call_cache.clear()


# ── terminal blocker: 추가 시도 없음 ──────────────────────────────────────

def test_captcha_terminates_loop_with_no_further_attempts():
    with patch(
        "ingestion.agents.graph._fetch_with_strategy",
        side_effect=Exception("captcha challenge detected"),
    ):
        result = run_fetch_strategy_loop("bbc", "https://bbc.com")
    assert result.status == "blocked"
    assert len(result.attempts) == 1  # 첫 시도에서 즉시 종료
    assert result.final_error_type == ErrorType.CAPTCHA_DETECTED


def test_login_wall_terminates_loop():
    with patch(
        "ingestion.agents.graph._fetch_with_strategy",
        side_effect=Exception("please login to continue"),
    ):
        result = run_fetch_strategy_loop("bbc", "https://bbc.com")
    assert result.status == "blocked"
    assert result.final_error_type == ErrorType.LOGIN_WALL_DETECTED


@pytest.mark.parametrize("blocker", sorted(BLOCKED_ERRORS, key=lambda e: e.value))
def test_all_blockers_stop_strategy_selection(blocker):
    """CAPTCHA/LOGIN/PAYWALL/ROBOTS — select_next_strategy가 즉시 None (우회 시도 금지)."""
    attempts = [FetchAttempt(strategy="httpx_direct", success=False, error_type=blocker)]
    assert select_next_strategy({}, attempts, blocker) is None


def test_turnstile_page_classified_as_captcha():
    """Cloudflare Turnstile/challenge 페이지 → CAPTCHA_DETECTED (terminal)."""
    from ingestion.core.error_taxonomy import classify_content_blocker
    html = '<html><body class="cf-challenge">verify you are human</body></html>'
    assert classify_content_blocker(html.lower()) == ErrorType.CAPTCHA_DETECTED


# ── attempt history ───────────────────────────────────────────────────────

def test_attempt_history_records_strategy_names():
    with patch(
        "ingestion.agents.graph._fetch_with_strategy",
        side_effect=Exception("boom unknown"),
    ):
        result = run_fetch_strategy_loop("bbc", "https://bbc.com")
    strategies = [a.strategy for a in result.attempts]
    assert strategies == STRATEGY_SEQUENCE[: len(strategies)]
    assert all(not a.success for a in result.attempts)


# ── budget ────────────────────────────────────────────────────────────────

def test_default_budget_is_3_attempts():
    with patch(
        "ingestion.agents.graph._fetch_with_strategy",
        side_effect=Exception("boom unknown"),
    ):
        result = run_fetch_strategy_loop("bbc", "https://bbc.com")
    assert result.status == "exhausted"
    assert len(result.attempts) == 3


def test_per_source_budget_krx_kind_8_dcinside_6():
    policy = _default_policy()
    assert policy.budget_for("krx_kind") == 8
    assert policy.budget_for("dcinside") == 6
    assert policy.budget_for("bbc") == 3  # 전역 기본 유지


def test_krx_kind_loop_reaches_8_attempts():
    with patch(
        "ingestion.agents.graph._fetch_with_strategy",
        side_effect=Exception("boom unknown"),
    ):
        result = run_fetch_strategy_loop("krx_kind", "https://kind.krx.co.kr")
    assert result.status == "exhausted"
    assert len(result.attempts) == 8


# ── EXTRACTION_EMPTY → playwright_basic 점프 ──────────────────────────────

def test_extraction_empty_on_httpx_jumps_to_playwright_basic():
    calls: list[str] = []

    def _empty_fetch(url, strategy, run_id, source_id, uh):
        calls.append(strategy)
        return None, None, None  # empty html → EXTRACTION_EMPTY

    with patch("ingestion.agents.graph._fetch_with_strategy", side_effect=_empty_fetch):
        run_fetch_strategy_loop("dcinside", "https://gall.dcinside.com")
    assert calls[0] == "httpx_direct"
    assert calls[1] == "playwright_basic"  # httpx_mobile_ua 등을 건너뛰고 점프


# ── selenium gate ─────────────────────────────────────────────────────────

def _exhausted_playwright_attempts() -> list[FetchAttempt]:
    return [
        FetchAttempt(strategy=s, success=False, error_type=ErrorType.JS_RENDER_FAIL)
        for s in (
            "playwright_basic", "playwright_scroll",
            "playwright_wait_network_idle", "playwright_click_more",
        )
    ]


def test_selenium_only_selected_when_env_ready(monkeypatch):
    from ingestion.fetch_strategies import selenium_strategy

    policy = RetryPolicy(max_strategies_per_url=20)
    attempts = _exhausted_playwright_attempts()

    monkeypatch.setattr(selenium_strategy, "selenium_env_status", lambda: {"ready": True})
    assert select_next_strategy({}, attempts, ErrorType.JS_RENDER_FAIL, policy) == \
        "selenium_rendered_dom"

    monkeypatch.setattr(selenium_strategy, "selenium_env_status", lambda: {"ready": False})
    assert select_next_strategy({}, attempts, ErrorType.JS_RENDER_FAIL, policy) is None


# ── RSS는 playwright 미진입 ───────────────────────────────────────────────

def test_rss_source_never_enters_playwright():
    policy = RetryPolicy(max_strategies_per_url=20)
    attempts = [
        FetchAttempt(strategy="dom_heuristic", success=False,
                     error_type=ErrorType.DOM_PARSE_ERROR)
    ]
    # 다음 순서는 playwright_basic이지만 RSS 소스라 None
    assert select_next_strategy(
        {"type": "rss"}, attempts, ErrorType.DOM_PARSE_ERROR, policy
    ) is None
    assert select_next_strategy(
        {"endpoint": "https://example.com/feed.xml"}, attempts,
        ErrorType.DOM_PARSE_ERROR, policy,
    ) is None
