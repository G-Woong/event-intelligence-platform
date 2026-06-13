from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from ingestion.core.artifact_store import (
    _OUTPUTS_DIR,
    get_screenshot_path,
    new_run_id,
    url_hash,
)
from ingestion.core.error_taxonomy import ErrorType, classify_content_blocker
from ingestion.fetch_strategies.models import RenderedPageFetchResult

logger = logging.getLogger("ingestion.fetch_strategies.cloud_browser_like")


class CloudBrowserLikeStrategy:
    """JS render + screenshot + markdown + artifact save — one unified call.

    Mirrors the functionality offered by cloud browser APIs (render, screenshot,
    markdown extraction, rendered DOM) using our internal Playwright tooling.
    No external service dependency; no 'Scrapfly' or similar names in public API.
    """

    def fetch(
        self,
        url: str,
        source_id: str,
        strategy: str = "playwright_basic",
        *,
        run_id: Optional[str] = None,
        take_screenshot: bool = True,
        save_dom: bool = True,
    ) -> RenderedPageFetchResult:
        if run_id is None:
            run_id = new_run_id(0, source_id)
        uh = url_hash(url)

        ss_path: Optional[Path] = get_screenshot_path(run_id, source_id, uh) if take_screenshot else None
        dom_path: Optional[Path] = None
        if save_dom:
            dom_path = _OUTPUTS_DIR / "rendered_dom" / source_id / f"{run_id}_{uh}.html"
            dom_path.parent.mkdir(parents=True, exist_ok=True)

        t0 = time.monotonic()
        from ingestion.tools.playwright_browser_tool import fetch_with_playwright_sync

        html = fetch_with_playwright_sync(
            url,
            strategy=strategy,
            screenshot_dir=ss_path.parent if ss_path else None,
            dom_dir=dom_path.parent if dom_path else None,
        )
        timing = time.monotonic() - t0

        if not html:
            return RenderedPageFetchResult(
                url=url,
                strategy_used=strategy,
                status="NETWORK_ERROR",
                error_category=ErrorType.JS_RENDER_FAIL,
                timing=timing,
            )

        # 429 / rate-limited rendered page → RATE_LIMITED (not BLOCKED/UNKNOWN),
        # with the cooldown deadline persisted (12-6)
        from ingestion.probes.playwright_probe import _detect_429
        if _detect_429(html):
            from ingestion.core.rate_limit_policy import record_rate_limited
            next_retry_at = record_rate_limited(source_id)
            logger.info(
                "RATE_LIMITED detected for %s (rendered) — next_retry=%s",
                source_id, next_retry_at,
            )
            return RenderedPageFetchResult(
                url=url,
                strategy_used=strategy,
                html=html,
                status="RATE_LIMITED",
                error_category=ErrorType.RATE_LIMITED,
                timing=timing,
                screenshot_path=str(ss_path) if ss_path and ss_path.exists() else None,
            )

        blocker = classify_content_blocker(html.lower())
        if blocker:
            return RenderedPageFetchResult(
                url=url,
                strategy_used=strategy,
                html=html,
                status="BLOCKED",
                error_category=blocker,
                timing=timing,
                screenshot_path=str(ss_path) if ss_path and ss_path.exists() else None,
            )

        markdown: Optional[str] = None
        extracted_text: Optional[str] = None
        try:
            from ingestion.tools.markdown_extractor import extract_markdown
            md_result = extract_markdown(html, url)
            if md_result.success:
                markdown = md_result.body
                extracted_text = md_result.body
        except Exception as exc:
            logger.warning("markdown extraction failed for %s: %s", url, exc)

        rendered_dom_path_str: Optional[str] = None
        if dom_path and dom_path.exists():
            rendered_dom_path_str = str(dom_path)

        screenshot_path_str: Optional[str] = None
        if ss_path and ss_path.exists():
            screenshot_path_str = str(ss_path)

        return RenderedPageFetchResult(
            url=url,
            strategy_used=strategy,
            html=html,
            markdown=markdown,
            screenshot_path=screenshot_path_str,
            rendered_dom_path=rendered_dom_path_str,
            extracted_text=extracted_text,
            status="LIVE_SUCCESS",
            timing=timing,
        )
