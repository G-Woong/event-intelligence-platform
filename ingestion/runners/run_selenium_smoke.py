"""Selenium smoke test runner.

Usage:
    python -m ingestion.runners.run_selenium_smoke
    python -m ingestion.runners.run_selenium_smoke --url https://example.com --screenshot
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("ingestion.runners.run_selenium_smoke")

_OUTPUT_DIR = Path(__file__).parent.parent / "outputs" / "selenium_smoke"


def main() -> int:
    parser = argparse.ArgumentParser(description="Selenium smoke test")
    parser.add_argument("--url", default="https://example.com", help="URL to fetch")
    parser.add_argument("--screenshot", action="store_true", help="Save screenshot")
    args = parser.parse_args()

    from ingestion.fetch_strategies.selenium_strategy import SeleniumRenderStrategy, selenium_env_status

    env = selenium_env_status()
    logger.info("selenium_env_status: %s", {k: v for k, v in env.items() if k != "ready"})

    if not env["ready"]:
        reason = "Chrome/Chromium binary not found" if env.get("selenium_installed") else "selenium not installed"
        result = {
            "status": "NOT_READY",
            "reason": reason,
            "env": env,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        logger.warning("Selenium NOT_READY: %s", reason)
        return 0  # NOT_READY is expected, not an error

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ss_path = (_OUTPUT_DIR / "smoke_screenshot.png") if args.screenshot else None

    strategy = SeleniumRenderStrategy(headless=True)
    fetch_result = strategy.fetch(args.url, screenshot_path=ss_path)

    result: dict = {
        "status": fetch_result.status,
        "error_category": fetch_result.error_category or None,
        "url": args.url,
        "html_length": len(fetch_result.html) if fetch_result.html else 0,
        "screenshot_saved": fetch_result.screenshot_saved,
        "screenshot_path": str(ss_path) if ss_path else None,
    }

    if fetch_result.status == "ok":
        result["status"] = "LIVE_SUCCESS"
        logger.info("LIVE_SUCCESS — html_length=%d", result["html_length"])
    else:
        logger.warning("Selenium fetch result: %s (%s)", fetch_result.status, fetch_result.error_category)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
