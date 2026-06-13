from __future__ import annotations

from typing import Optional

from ingestion.core.error_taxonomy import BLOCKED_ERRORS, ErrorType
from ingestion.core.retry_policy import STRATEGY_SEQUENCE, RetryPolicy

_PLAYWRIGHT_STRATEGIES = frozenset({
    "playwright_basic",
    "playwright_scroll",
    "playwright_wait_network_idle",
    "playwright_click_more",
})

_JS_RENDER_STRATEGIES = frozenset({
    "playwright_basic",
    "playwright_scroll",
    "playwright_wait_network_idle",
    "playwright_click_more",
    "selenium_rendered_dom",
})


def select_next_strategy(
    source_spec: dict,
    previous_attempts: list,  # list[FetchAttempt]
    failure_category: ErrorType,
    policy: Optional[RetryPolicy] = None,
) -> Optional[str]:
    """Source-aware next strategy selection.

    Rules:
    - BLOCKED_ERRORS → None (stop immediately)
    - RATE_LIMITED → caller handles cooldown+retry; do not advance strategy
    - EXTRACTION_EMPTY on httpx → jump to playwright_basic (JS render needed)
    - JS_RENDER_FAIL on playwright → try next playwright; after all playwright exhausted → selenium_rendered_dom if ready
    - RSS/feed/XML → skip playwright variants
    - Budget: max_strategies_per_url from policy
    """
    if failure_category in BLOCKED_ERRORS:
        return None

    if failure_category == ErrorType.RATE_LIMITED:
        # Caller (strategy_runner) handles cooldown; no strategy advance
        return None

    if policy is None:
        policy = RetryPolicy()

    if len(previous_attempts) >= policy.max_strategies_per_url:
        return None

    current = previous_attempts[-1].strategy if previous_attempts else None
    is_rss_source = _is_rss_or_feed(source_spec)

    if current is None:
        return STRATEGY_SEQUENCE[0]

    # EXTRACTION_EMPTY on httpx-family → jump directly to playwright_basic
    if failure_category == ErrorType.EXTRACTION_EMPTY and current in (
        "httpx_direct", "httpx_mobile_ua", "httpx_random_ua"
    ):
        return "playwright_basic"

    next_s = policy.next_strategy(current)
    if next_s is None:
        # Exhausted STRATEGY_SEQUENCE — try selenium if it's in the JS render catalog
        preferred = source_spec.get("preferred_browser")
        if "selenium_rendered_dom" in _JS_RENDER_STRATEGIES and (
            preferred == "selenium" or _all_playwright_failed(previous_attempts)
        ):
            from ingestion.fetch_strategies.selenium_strategy import selenium_env_status
            if selenium_env_status()["ready"]:
                return "selenium_rendered_dom"
        return None

    if is_rss_source and next_s in _PLAYWRIGHT_STRATEGIES:
        return None

    return next_s


def _all_playwright_failed(attempts: list) -> bool:
    """Return True if all playwright strategies attempted and failed."""
    failed_playwright = {a.strategy for a in attempts if not a.success and a.strategy in _PLAYWRIGHT_STRATEGIES}
    return _PLAYWRIGHT_STRATEGIES.issubset(failed_playwright)


def _is_rss_or_feed(source_spec: dict) -> bool:
    source_type = source_spec.get("type", "")
    if source_type in ("rss", "feed", "xml"):
        return True
    endpoint = source_spec.get("endpoint", source_spec.get("base_url", ""))
    lower = endpoint.lower()
    if "rss" in lower or "feed" in lower or lower.endswith(".xml"):
        return True
    if source_spec.get("response_format") == "xml":
        return True
    return False
