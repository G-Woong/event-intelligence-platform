"""redirect/proxy URL → 원본 canonical URL 해석 (09 §2-4, 기법 4).

2단 사다리(안정성 서열 적용):
1. **HTTP resolve()** — httpx redirect 추적. 일반 단축/프록시/301-302 URL의 최종 도착지.
2. **resolve_via_browser()** — Playwright headless 1-hop. Google News RSS 신형 URL처럼 HTTP
   redirect가 아니라 클라이언트 JS로 원본에 도달하는 경우 실제 브라우저로 navigation을 따라간다.

설계 원칙:
- **실패해도 수집을 죽이지 않는다**: 어떤 예외든 원본 URL을 그대로 반환한다.
- **무한 redirect 방지**: max_hops(httpx max_redirects) / 브라우저 max_wait·timeout 상한.
- **동의/CAPTCHA/로그인 페이지는 우회하지 않는다**: 감지 시 원본 반환 + BLOCKED_BY_PROVIDER 로그.
- **동일 URL 캐시**: in-process dict로 같은 URL 재요청 방지.

Google News RSS 신형 기사 URL(`news.google.com/rss/articles/CBM...`)은 HTTP HEAD/GET으로는
news.google.com에 머문다(canonical 자기참조, og:url=news.google.com, 본문에 원본 URL 없음 —
data-n-a-id/data-n-a-sg 토큰을 JS가 런타임에 복호). 따라서 HTTP resolve()로는 원본에 도달하지
못하고, resolve_via_browser()로 승격해야 apnews.com 원본 기사 URL을 얻는다(2026-06-13 실측 3/3).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_GOOGLE_NEWS_HOST = "news.google.com"
# 동의/차단 페이지 호스트 — 감지 시 우회하지 않고 원본 반환
_BLOCK_HOSTS = ("consent.google.com", "google.com/sorry")

# 같은 URL은 한 번만 해석 (프로세스 수명 동안 유효)
_cache: dict[str, str] = {}


def clear_cache() -> None:
    """테스트/장기 실행에서 캐시를 비운다."""
    _cache.clear()


def resolve(
    url: str,
    max_hops: int = 5,
    timeout: float = 10.0,
    client: Optional[httpx.Client] = None,
) -> str:
    """url의 redirect 체인을 따라가 최종 URL을 반환. 실패 시 원본 반환.

    Args:
        url: 해석할 URL.
        max_hops: 허용 최대 redirect 수 (초과 시 원본 반환).
        timeout: 요청 타임아웃(초).
        client: 주입용 httpx.Client (테스트의 MockTransport용). None이면 내부 생성.
    """
    if not url:
        return url
    if url in _cache:
        return _cache[url]

    owns_client = client is None
    resolved = url
    c: Optional[httpx.Client] = None
    try:
        c = client or httpx.Client(
            timeout=timeout, follow_redirects=True, max_redirects=max_hops
        )
        resp = c.head(url, headers={"User-Agent": _UA})
        # 일부 서버는 HEAD를 막는다(405/501/403) → GET으로 1회 폴백
        if resp.status_code in (403, 405, 501):
            resp = c.get(url, headers={"User-Agent": _UA})
        resolved = str(resp.url)
    except Exception as exc:  # TooManyRedirects/timeout/network 등 전부 무해 처리
        logger.warning("url resolve failed (원본 반환) for %s: %s", url[:80], exc)
        resolved = url
    finally:
        if owns_client and c is not None:
            c.close()

    _cache[url] = resolved
    return resolved


def needs_browser_resolution(url: str) -> bool:
    """HTTP resolve로 원본에 도달 못하는(=브라우저 승격 필요) URL인지."""
    return bool(url) and _GOOGLE_NEWS_HOST in url


def canonical_from_html(html: str, want_host: str = "apnews.com") -> Optional[str]:
    """렌더된 HTML에서 want_host(예: apnews.com)의 원본 URL을 추출.

    우선순위: og:url → rel=canonical → anchor[href*=want_host]. want_host를 가리키지 않으면
    None. (page.url로 못 잡았을 때의 폴백 + saved-HTML 단위 테스트 대상 — 순수 함수.)
    """
    if not html:
        return None
    for pat in (
        r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:url["\']',
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
    ):
        m = re.search(pat, html, re.IGNORECASE)
        if m and want_host in m.group(1):
            return m.group(1)
    m = re.search(r'href=["\'](https?://[^"\']*' + re.escape(want_host) + r'[^"\']*)["\']', html, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


async def _resolve_via_browser_async(url: str, timeout_ms: int, max_wait_ms: int) -> str:
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page(user_agent=_UA)
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # JS가 원본으로 navigation할 때까지 폴링 (news.google.com을 벗어날 때까지)
            import asyncio
            waited = 0
            step = 500
            while waited < max_wait_ms:
                cur = page.url
                if any(b in cur for b in _BLOCK_HOSTS):
                    logger.warning("BLOCKED_BY_PROVIDER (동의/차단 페이지) for %s → 원본 반환", url[:80])
                    return url
                if _GOOGLE_NEWS_HOST not in cur:
                    return cur  # 원본 도착
                await asyncio.sleep(step / 1000.0)
                waited += step
            final = page.url
            if _GOOGLE_NEWS_HOST not in final:
                return final
            # page.url이 아직 google이면 HTML 파싱 폴백
            html = await page.content()
            found = canonical_from_html(html)
            return found or url
        finally:
            await browser.close()


def resolve_via_browser(url: str, timeout_ms: int = 30000, max_wait_ms: int = 10000) -> str:
    """Playwright headless로 JS navigation을 따라가 원본 URL을 얻는다. 실패 시 원본 반환.

    Google News RSS 신형 URL 전용 승격 경로. 동의/CAPTCHA/차단 페이지는 우회하지 않고 원본 반환.
    Playwright/chromium 미설치·timeout·예외는 전부 무해 처리(원본 반환).
    """
    if not url:
        return url
    cache_key = "browser::" + url
    if cache_key in _cache:
        return _cache[cache_key]
    resolved = url
    try:
        import asyncio
        resolved = asyncio.run(_resolve_via_browser_async(url, timeout_ms, max_wait_ms))
    except Exception as exc:
        logger.warning("browser resolve failed (원본 반환) for %s: %s", url[:80], exc)
        resolved = url
    _cache[cache_key] = resolved
    return resolved
