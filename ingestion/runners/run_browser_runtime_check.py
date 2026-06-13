from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

READY = "READY"
PARTIAL = "PARTIAL"
NOT_READY = "NOT_READY"


def _check_python() -> dict:
    v = sys.version_info
    return {
        "version": f"{v.major}.{v.minor}.{v.micro}",
        "ok": (v.major, v.minor) >= (3, 11),
    }


def _check_playwright() -> dict:
    result: dict = {"installed": False, "version": None, "chromium_installed": False}
    try:
        import playwright  # noqa: F401
        result["installed"] = True
        try:
            from importlib.metadata import version
            result["version"] = version("playwright")
        except Exception:
            result["version"] = "unknown"
    except ImportError:
        return result
    # Chromium 설치 확인 — 기본은 비기동 경로 확인 (브라우저를 띄우지 않음)
    try:
        from playwright._impl._driver import compute_driver_executable  # noqa: F401
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = p.chromium.executable_path
            result["chromium_installed"] = bool(exe) and Path(exe).exists()
    except Exception:
        result["chromium_installed"] = False
    return result


def _check_playwright_launch(screenshot_dir: Path) -> dict:
    """--launch 시에만 호출: headless 기동 + screenshot 저장."""
    result: dict = {"launched": False, "screenshot_saved": False, "error": None}
    try:
        from playwright.sync_api import sync_playwright
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        ss_path = screenshot_dir / "runtime_check_chromium.png"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content("<html><body><h1>runtime check</h1></body></html>")
            page.screenshot(path=str(ss_path))
            browser.close()
        result["launched"] = True
        result["screenshot_saved"] = ss_path.exists()
        result["screenshot_path"] = str(ss_path)
    except Exception as exc:
        result["error"] = type(exc).__name__
    return result


def _check_selenium() -> dict:
    try:
        from ingestion.fetch_strategies.selenium_strategy import selenium_env_status
        return selenium_env_status()
    except Exception as exc:
        return {"selenium_installed": False, "ready": False, "error": type(exc).__name__}


def run_runtime_check(launch: bool = False, screenshot_dir: Optional[Path] = None) -> dict:
    """Browser runtime readiness report. Contains no env values or secrets."""
    if screenshot_dir is None:
        screenshot_dir = _REPO_ROOT / "ingestion" / "outputs" / "screenshots" / "_runtime_check"

    python_check = _check_python()
    playwright_check = _check_playwright()
    selenium_check = _check_selenium()

    launch_check: Optional[dict] = None
    if launch and playwright_check["chromium_installed"]:
        launch_check = _check_playwright_launch(screenshot_dir)

    playwright_ready = playwright_check["installed"] and playwright_check["chromium_installed"]
    selenium_ready = bool(selenium_check.get("ready"))

    if playwright_ready and selenium_ready:
        overall = READY
    elif playwright_ready or selenium_ready:
        overall = PARTIAL
    else:
        overall = NOT_READY

    return {
        "overall": overall,
        "python": python_check,
        "playwright": playwright_check,
        "playwright_launch": launch_check,
        "selenium": selenium_check,
        "screenshot_capable": bool(
            (launch_check or {}).get("screenshot_saved")
        ) if launch else playwright_ready,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check browser runtime readiness (playwright/chromium/selenium)."
    )
    parser.add_argument("--launch", action="store_true",
                        help="Actually launch headless chromium and save a screenshot")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero when overall is not READY")
    args = parser.parse_args(argv)

    report = run_runtime_check(launch=args.launch)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"overall={report['overall']}")
        print(f"python {report['python']['version']} ok={report['python']['ok']}")
        pw = report["playwright"]
        print(f"playwright installed={pw['installed']} version={pw['version']} "
              f"chromium_installed={pw['chromium_installed']}")
        if report["playwright_launch"] is not None:
            lc = report["playwright_launch"]
            print(f"launch={lc['launched']} screenshot_saved={lc['screenshot_saved']}")
        se = report["selenium"]
        print(f"selenium installed={se.get('selenium_installed')} ready={se.get('ready')}")

    if args.strict and report["overall"] != READY:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
