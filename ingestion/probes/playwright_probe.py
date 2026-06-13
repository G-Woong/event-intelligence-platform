from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus, urljoin

_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from ingestion.core.artifact_store import (
    get_screenshot_path,
    new_run_id,
    save_raw_signal,
    save_rendered_dom,
    url_hash,
)
from ingestion.core.error_taxonomy import classify_content_blocker
from ingestion.core.rate_limit_policy import load_rate_limit_policy
from ingestion.probes.models import ProbeResult
from ingestion.probes.normalizers import normalize_doc_items, normalize_signal_items
from ingestion.probes.site_specs import load_site_specs
from ingestion.tools.playwright_browser_tool import open_page

logger = logging.getLogger("ingestion.probes.playwright_probe")

_CLICK_DELAY_SEC = 2.0
_MAX_CLICK_LINKS = 3


def _detect_429(html: str) -> bool:
    """Return True if rendered HTML indicates a 429 / rate-limited page (case-insensitive).

    기법 10 (docs/09 §2): rate-limit 신호 목록은 error_taxonomy 단일 출처를 쓴다.
    """
    from ingestion.core.error_taxonomy import is_rate_limited_text
    return is_rate_limited_text(html)


def _select_rate_limit_backend(backend: Optional[str]) -> None:
    """Force a durable rate-limit backend before the store singleton is built.

    Standalone probe runs default to the in-memory store, so a 429 cooldown
    recorded during RATE_LIMITED detection lives only in-process and is lost on
    exit — the next process sees an open gate and can hammer the provider again.
    Operational 429 verification MUST pass backend='local_file' so the cooldown
    deadline is persisted to rate_limit_cache.json and survives restarts.
    No-op when backend is None (dev runs keep the memory default).
    """
    if not backend:
        return
    import os
    from ingestion.core.rate_limit_store import reset_store_for_tests

    os.environ["INGESTION_RATE_LIMIT_BACKEND"] = backend
    reset_store_for_tests()  # drop any singleton built under the old backend


def run_playwright_probe(
    site_id: str,
    query: Optional[str] = None,
    region: Optional[str] = None,
    max_items: int = 10,
) -> ProbeResult:
    """Synchronous wrapper around the async probe."""
    return asyncio.run(
        _async_probe(site_id, query=query, region=region, max_items=max_items)
    )


async def _async_probe(
    site_id: str,
    query: Optional[str] = None,
    region: Optional[str] = None,
    max_items: int = 10,
) -> ProbeResult:
    site_specs = load_site_specs()
    spec = site_specs.get(site_id)

    if not spec:
        return ProbeResult(
            source_id=site_id,
            method="playwright",
            query=query,
            region=region,
            status="UNKNOWN",
            error_category="UNKNOWN",
            next_action="site_not_in_playwright_probe_sites.yaml",
        )

    if spec.deferred:
        return ProbeResult(
            source_id=site_id,
            method="playwright",
            query=query,
            region=region,
            status="DEFERRED",
            error_category="DEFERRED",
            next_action="implement_in_next_round",
        )

    # Build URL from template — query가 있고 search_url이 정의된 사이트는 검색 진입
    url = spec.start_url
    if query and getattr(spec, "search_url", ""):
        url = spec.search_url
    if region:
        url = url.replace("{region}", region)
    elif "{region}" in url:
        url = url.replace("{region}", "KR")
    if query:
        url = url.replace("{query}", quote_plus(query))
    elif "{query}" in url:
        url = url.replace("{query}", "samsung")

    run_id = new_run_id(0, site_id)
    uh = url_hash(url)
    ss_path = get_screenshot_path(run_id, site_id, uh)
    artifact_paths: dict = {}

    scroll = spec.search_strategy in ("page_load_scroll", "page_load_wait_js")
    wait_until = "networkidle" if spec.search_strategy != "page_load_only" else "domcontentloaded"
    wait_selector = (spec.selectors or {}).get("wait_for") if spec.selectors else None
    wait_after_ms = getattr(spec, "wait_after_ms", 0) or 0
    html = await open_page(
        url,
        wait_until=wait_until,
        timeout_ms=45000,
        scroll=scroll,
        wait_after_ms=wait_after_ms,
        wait_selector=wait_selector,
        screenshot_path=ss_path,
    )

    artifact_paths["screenshot"] = str(ss_path)

    if not html:
        return ProbeResult(
            source_id=site_id,
            method="playwright",
            query=query,
            region=region,
            status="NETWORK_ERROR",
            error_category="NETWORK_ERROR",
            next_action="check_connectivity",
            artifact_paths=artifact_paths,
        )

    # Save rendered DOM
    try:
        dom_path = save_rendered_dom(run_id, site_id, uh, html)
        artifact_paths["rendered_dom"] = str(dom_path)
    except Exception as exc:
        logger.warning("rendered_dom save failed for %s: %s", site_id, exc)

    html_lower = html.lower()

    # Check for 429 / rate-limited response BEFORE bot-protection check
    if _detect_429(html):
        rl_policy = load_rate_limit_policy(site_id)
        cooldown = rl_policy.cooldown_on_429_seconds
        next_retry_at = None
        if cooldown > 0:
            # Persist the cooldown deadline so it survives process restarts (12-6)
            from ingestion.core.rate_limit_policy import record_rate_limited
            next_retry_at = record_rate_limited(
                site_id, query or "", cooldown_seconds=cooldown
            )
        logger.info("RATE_LIMITED detected for %s — cooldown=%ds next_retry=%s", site_id, cooldown, next_retry_at)
        return ProbeResult(
            source_id=site_id,
            method="playwright",
            query=query,
            region=region,
            status="RATE_LIMITED",
            error_category="RATE_LIMITED",
            next_action=f"retry_after_cooldown_{cooldown}s",
            artifact_paths=artifact_paths,
            cooldown_seconds=cooldown,
            next_retry_at=next_retry_at,
            retry_after_reason="429_detected_in_rendered_html",
        )

    # Check for bot-protection challenge
    blocker = classify_content_blocker(html_lower)
    if blocker is not None:
        return ProbeResult(
            source_id=site_id,
            method="playwright",
            query=query,
            region=region,
            status="BLOCKED",
            error_category=blocker.value,
            next_action="site_challenge_detected_no_bypass",
            artifact_paths=artifact_paths,
        )

    # Extract list items using YAML-configured selectors
    items: list[dict] = _extract_list_items(html, url, spec.selectors.get("list", []), max_items)
    items_found = len(items)

    # Save raw signal
    if items:
        try:
            signal_payload = json.dumps(items, ensure_ascii=False)
            sig_path = save_raw_signal(run_id, site_id, uh, signal_payload)
            artifact_paths["raw_signal"] = str(sig_path)
        except Exception as exc:
            logger.warning("raw_signal save failed for %s: %s", site_id, exc)

    # Click-through body extraction for community sites
    items_extracted = 0
    click_selectors = spec.selectors.get("click_target", [])
    if click_selectors and items:
        links = _extract_links(html, url, click_selectors, _MAX_CLICK_LINKS)
        for detail_url in links:
            await asyncio.sleep(_CLICK_DELAY_SEC)
            detail_uh = url_hash(detail_url)
            detail_ss = get_screenshot_path(run_id, site_id, detail_uh)
            detail_html = await open_page(detail_url, screenshot_path=detail_ss)
            if not detail_html:
                continue
            if classify_content_blocker(detail_html.lower()) is not None:
                break
            try:
                from ingestion.fetch_strategies.article_body_extractor import extract_article_body
                body_selectors = spec.selectors.get("body", []) if spec.selectors else []
                body = extract_article_body(detail_html, detail_url, body_selectors=body_selectors)
                if body and body.get("body"):
                    items_extracted += 1
                    from ingestion.core.artifact_store import save_extracted_payload
                    ep = save_extracted_payload(run_id, site_id, detail_uh, {
                        "url": detail_url,
                        "title": body.get("title"),
                        "body": body["body"][:5000],
                        "method": body.get("method"),
                    })
                    artifact_paths[f"extracted_body_{items_extracted}"] = str(ep)
            except Exception as exc:
                logger.warning("body extraction failed for %s: %s", detail_url, exc)

    if items_found > 0:
        probe_status = "LIVE_SUCCESS"
    elif len(html) > 500:
        probe_status = "LIVE_PARTIAL"
    else:
        probe_status = "PARSE_ERROR"

    return ProbeResult(
        source_id=site_id,
        method="playwright",
        query=query,
        region=region,
        status=probe_status,
        items_found=items_found,
        items_extracted=items_extracted,
        meaningful_fields=["keyword", "url"] if items else [],
        artifact_paths=artifact_paths,
        error_category=None if probe_status in ("LIVE_SUCCESS", "LIVE_PARTIAL") else probe_status,
        next_action="integrate_into_pipeline" if probe_status == "LIVE_SUCCESS" else "check_selectors",
    )


def _extract_list_items(html: str, base_url: str, selectors, max_items: int) -> list[dict]:
    if not selectors:
        return []
    sel_list = selectors if isinstance(selectors, list) else [selectors]
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for sel in sel_list:
            found = soup.select(sel)
            if not found:
                continue
            items: list[dict] = []
            for i, el in enumerate(found[:max_items]):
                text = el.get_text(strip=True)
                href = el.get("href", "")
                if href and not href.startswith("http"):
                    href = urljoin(base_url, href)
                if text:
                    items.append({"keyword": text, "url": href, "rank": i + 1})
            if items:
                return items
    except Exception as exc:
        logger.warning("list extraction failed: %s", exc)
    return []


def _extract_links(html: str, base_url: str, selectors, limit: int) -> list[str]:
    sel_list = selectors if isinstance(selectors, list) else [selectors]
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for sel in sel_list:
            found = soup.select(sel)
            links: list[str] = []
            for el in found[:limit]:
                href = el.get("href", "")
                if not href:
                    href = el.find("a", href=True)
                    href = href["href"] if href else ""
                if href:
                    if not href.startswith("http"):
                        href = urljoin(base_url, href)
                    links.append(href)
            if links:
                return links
    except Exception as exc:
        logger.warning("link extraction failed: %s", exc)
    return []


def main(argv: Optional[list] = None) -> int:
    """Operational standalone runner. For RATE_LIMITED verification pass
    --rate-limit-backend local_file so the 429 cooldown is persisted durably."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Standalone Playwright probe (operational 429-verification path)."
    )
    parser.add_argument("--site", required=True, help="site_id in playwright_probe_sites.yaml")
    parser.add_argument("--query", default=None)
    parser.add_argument("--region", default=None)
    parser.add_argument("--max-items", type=int, default=10)
    parser.add_argument(
        "--rate-limit-backend",
        default=None,
        help="local_file persists cooldown across restarts — required when verifying RATE_LIMITED.",
    )
    args = parser.parse_args(argv)

    _select_rate_limit_backend(args.rate_limit_backend)
    result = run_playwright_probe(
        args.site, query=args.query, region=args.region, max_items=args.max_items
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
