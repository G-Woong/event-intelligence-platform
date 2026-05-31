from __future__ import annotations

import logging
import time
from typing import Optional

from crawling.core.fetch_result import FetchResult

logger = logging.getLogger("crawling.tools.html_fetch")

_UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


def fetch_html(
    url: str,
    strategy: str = "httpx_direct",
    timeout: float = 15.0,
) -> FetchResult:
    try:
        import httpx
    except ImportError:
        return FetchResult.failure(url, strategy, "httpx not installed")

    ua = _UA_DESKTOP
    if strategy == "httpx_mobile_ua":
        ua = _UA_MOBILE
    elif strategy == "httpx_random_ua":
        import random
        ua = random.choice([_UA_DESKTOP, _UA_MOBILE])

    headers = {"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"}
    start = time.monotonic()
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            resp = client.get(url, headers=headers)
        elapsed = time.monotonic() - start
        html = resp.text
        logger.debug("fetch_html: %s status=%d len=%d", url, resp.status_code, len(html))
        return FetchResult(
            url=url,
            strategy=strategy,
            success=resp.status_code < 400,
            status_code=resp.status_code,
            html=html,
            headers=dict(resp.headers),
            elapsed_sec=elapsed,
            error_message=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
        )
    except Exception as exc:
        elapsed = time.monotonic() - start
        logger.warning("fetch_html error: %s - %s", url, exc)
        return FetchResult.failure(url, strategy, str(exc))
