from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ingestion.tools.playwright")

_MIN_DELAY_SEC = 2.0
_last_request_time: float = 0.0


async def _ensure_rate_limit() -> None:
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < _MIN_DELAY_SEC:
        await asyncio.sleep(_MIN_DELAY_SEC - elapsed)
    _last_request_time = time.monotonic()


async def open_page(
    url: str,
    *,
    wait_until: str = "domcontentloaded",
    timeout_ms: int = 30000,
    scroll: bool = False,
    wait_after_ms: int = 0,
    wait_selector: Optional[str] = None,
    screenshot_path: Optional[Path] = None,
    dom_snapshot_path: Optional[Path] = None,
) -> Optional[str]:
    await _ensure_rate_limit()
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("playwright not installed — run: python -m playwright install chromium")
        return None

    html: Optional[str] = None
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)

            if wait_after_ms > 0:
                await asyncio.sleep(wait_after_ms / 1000.0)

            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=10000)
                except Exception:
                    pass  # proceed with whatever content is available

            if scroll:
                await _scroll_page(page)

            html = await page.content()

            if screenshot_path:
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(screenshot_path), full_page=False)
                logger.debug("screenshot saved: %s", screenshot_path)

            if dom_snapshot_path:
                dom_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                dom_snapshot_path.write_text(html[:50000], encoding="utf-8")

            await browser.close()
    except Exception as exc:
        logger.warning("playwright open_page error: %s - %s", url, exc)
        if screenshot_path:
            await _save_error_screenshot(url, screenshot_path)
        html = None
    return html


async def _scroll_page(page, steps: int = 3, delay_ms: int = 500) -> None:
    for _ in range(steps):
        await page.evaluate("window.scrollBy(0, document.body.scrollHeight / 3)")
        await asyncio.sleep(delay_ms / 1000)


async def _save_error_screenshot(url: str, path: Path) -> None:
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=10000)
            path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(path))
            await browser.close()
    except Exception:
        pass


async def dom_snapshot(url: str, *, timeout_ms: int = 30000) -> Optional[str]:
    html = await open_page(url, timeout_ms=timeout_ms)
    return html


async def find_candidate_links(
    url: str,
    *,
    base_domain: str = "",
    limit: int = 20,
) -> list[str]:
    html = await open_page(url)
    if not html:
        return []
    try:
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin, urlparse

        soup = BeautifulSoup(html, "lxml")
        links = []
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            parsed = urlparse(href)
            if parsed.scheme in ("http", "https"):
                if not base_domain or base_domain in parsed.netloc:
                    links.append(href)
                    if len(links) >= limit:
                        break
        return list(dict.fromkeys(links))
    except Exception as exc:
        logger.warning("find_candidate_links error: %s", exc)
        return []


def fetch_with_playwright_sync(
    url: str,
    strategy: str = "playwright_basic",
    screenshot_dir: Optional[Path] = None,
    dom_dir: Optional[Path] = None,
) -> Optional[str]:
    scroll = strategy in ("playwright_scroll", "playwright_wait_network_idle", "playwright_click_more")
    wait_until = "networkidle" if strategy == "playwright_wait_network_idle" else "domcontentloaded"
    ss_path = (screenshot_dir / f"{strategy}.png") if screenshot_dir else None
    dom_path = (dom_dir / f"{strategy}.html") if dom_dir else None

    return asyncio.run(
        open_page(
            url,
            wait_until=wait_until,
            scroll=scroll,
            screenshot_path=ss_path,
            dom_snapshot_path=dom_path,
        )
    )
