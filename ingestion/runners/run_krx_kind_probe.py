"""KRX KIND 전용 XHR/네트워크 probe 러너.

공개 페이지에서 발생하는 XHR/fetch 요청만 관찰합니다.
로그인/CAPTCHA/우회 없음.

Usage:
    python -m ingestion.runners.run_krx_kind_probe
    python -m ingestion.runners.run_krx_kind_probe --max-items 10
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("ingestion.runners.run_krx_kind_probe")

_SITE_ID = "krx_kind"
_KRX_URL = "https://kind.krx.co.kr/disclosure/todaydisclosure.do"
_OUTPUT_DIR = Path(__file__).parent.parent / "outputs" / "krx_kind"
_REQUIRED_FIELDS = {"corp_name", "report_title", "disclosed_at", "detail_url", "market_type"}
_MIN_FIELDS_SUCCESS = 3


async def _run_probe(max_items: int) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"status": "NOT_READY", "reason": "playwright not installed"}

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ss_path = _OUTPUT_DIR / "krx_kind_screenshot.png"
    dom_path = _OUTPUT_DIR / "krx_kind_rendered.html"

    network_entries: list[dict] = []
    html: str = ""

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )

            async def _on_response(response) -> None:
                try:
                    url = response.url
                    method = response.request.method
                    status = response.status
                    ct = response.headers.get("content-type", "").lower()
                    if any(x in ct for x in ("json", "xml", "text/plain")) or method == "POST":
                        entry: dict = {
                            "url": url,
                            "method": method,
                            "status": status,
                            "content_type": ct,
                        }
                        if "json" in ct:
                            try:
                                body = await response.body()
                                if len(body) <= 8192:
                                    entry["json_body"] = json.loads(body)
                            except Exception:
                                pass
                        network_entries.append(entry)
                except Exception:
                    pass

            page.on("response", _on_response)

            logger.info("Navigating to %s", _KRX_URL)
            try:
                await page.goto(_KRX_URL, wait_until="networkidle", timeout=45000)
            except Exception as nav_err:
                logger.warning("Navigation error: %s", nav_err)
                try:
                    await page.goto(_KRX_URL, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass

            await asyncio.sleep(3.0)  # Allow XHR to complete

            html = await page.content()
            await page.screenshot(path=str(ss_path), full_page=False)
            dom_path.write_text(html[:100000], encoding="utf-8", errors="replace")

            await browser.close()
    except Exception as exc:
        logger.error("Playwright error: %s", exc)
        return {
            "status": "NETWORK_ERROR",
            "reason": str(exc),
            "network_log": network_entries,
        }

    # Analyse network log for XHR endpoints
    xhr_candidates = [
        e for e in network_entries
        if e.get("method") == "POST" or "json" in e.get("content_type", "")
    ]
    logger.info("Network entries captured: %d, XHR/JSON candidates: %d", len(network_entries), len(xhr_candidates))

    # Selector-based extraction
    items = _extract_disclosure_items(html, max_items)
    logger.info("Table items extracted: %d", len(items))

    html_lower = html.lower()
    html_len = len(html)
    logger.info("Rendered HTML length: %d bytes", html_len)

    # Detect server error in rendered page
    is_error_page = any(s in html_lower for s in [
        "오류", "error", "service unavailable", "503", "502", "내부 서버 오류"
    ]) and html_len < 5000

    result: dict = {
        "site_id": _SITE_ID,
        "url": _KRX_URL,
        "html_length": html_len,
        "items_found": len(items),
        "items": items[:max_items],
        "xhr_candidates": len(xhr_candidates),
        "network_log": network_entries[:20],
        "screenshot_path": str(ss_path),
        "dom_path": str(dom_path),
    }

    if items and _count_valid_fields(items) >= _MIN_FIELDS_SUCCESS:
        result["status"] = "LIVE_SUCCESS"
        result["next_action"] = "integrate_into_pipeline"
        # Check if XHR endpoint found — could separate into API-like source
        if xhr_candidates:
            result["api_endpoint_hint"] = [e["url"] for e in xhr_candidates[:3]]
            result["next_action"] = "evaluate_api_like_source_separation"
    elif is_error_page:
        result["status"] = "DEFERRED_SERVER_ERROR"
        result["deferred_reason"] = (
            f"KRX KIND returns {html_len}B error page; "
            "XHR log captured for manual review; "
            "next: try mobile UA or official data portal API"
        )
        result["next_action"] = "retry_with_mobile_ua_or_data_portal_api"
    elif items:
        result["status"] = "LIVE_PARTIAL"
        result["next_action"] = "improve_selectors"
    else:
        result["status"] = "PARSE_ERROR"
        result["deferred_reason"] = (
            f"HTML {html_len}B but no table items matched; "
            f"XHR candidates: {len(xhr_candidates)}; "
            "JS table may not render in Playwright headless"
        )
        result["next_action"] = "check_js_table_rendering_or_use_xhr_endpoint"

    # Persist result
    out_file = _OUTPUT_DIR / "krx_kind_probe_result.json"
    out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Result saved to %s", out_file)

    return result


def _extract_disclosure_items(html: str, max_items: int) -> list[dict]:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        selectors = [
            "table.list tbody tr",
            ".tblList tbody tr",
            "table tbody tr",
        ]
        for sel in selectors:
            rows = soup.select(sel)
            if not rows:
                continue
            items = []
            for row in rows[:max_items]:
                cells = row.find_all(["td", "th"])
                if not cells:
                    continue
                item: dict = {}
                texts = [c.get_text(strip=True) for c in cells]
                hrefs = [c.find("a") for c in cells]
                if len(texts) >= 2:
                    item["corp_name"] = texts[0] if texts[0] else ""
                    item["report_title"] = texts[1] if len(texts) > 1 else ""
                    item["disclosed_at"] = texts[2] if len(texts) > 2 else ""
                    item["market_type"] = texts[3] if len(texts) > 3 else ""
                    for a in hrefs:
                        if a and a.get("href"):
                            href = a["href"]
                            if not href.startswith("http"):
                                href = "https://kind.krx.co.kr" + href
                            item["detail_url"] = href
                            break
                    if any(v for v in item.values()):
                        items.append(item)
            if items:
                return items
    except Exception as exc:
        logger.warning("disclosure extraction error: %s", exc)
    return []


def _count_valid_fields(items: list[dict]) -> int:
    if not items:
        return 0
    first = items[0]
    return sum(1 for f in _REQUIRED_FIELDS if first.get(f))


def main() -> int:
    parser = argparse.ArgumentParser(description="KRX KIND 공시 probe")
    parser.add_argument("--max-items", type=int, default=10)
    args = parser.parse_args()

    result = asyncio.run(_run_probe(args.max_items))
    print(json.dumps(result, indent=2, ensure_ascii=False))

    status = result.get("status", "UNKNOWN")
    logger.info("Final status: %s", status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
