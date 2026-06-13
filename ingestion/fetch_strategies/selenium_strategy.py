from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class SeleniumFetchResult:
    status: str  # "ok" | "NOT_READY" | "JS_RENDER_FAIL"
    html: Optional[str] = None
    error_category: str = ""
    screenshot_saved: bool = False


@dataclass
class SeleniumRenderStrategy:
    """Selenium-based rendering fallback for when Playwright fingerprint is detected.

    Gracefully returns NOT_READY if Chrome/Chromium binary is absent rather than raising.
    Selenium Manager (bundled since 4.x) auto-downloads chromedriver — no manual PATH setup.
    To activate: ensure Chrome or Chromium is installed (any standard location).
    See docs/ingestion/54_selenium_installation_and_runtime_check.md for setup.
    """

    driver_path: Optional[str] = None
    headless: bool = True
    timeout_sec: int = 30

    def fetch(self, url: str, screenshot_path: Optional[Path] = None) -> SeleniumFetchResult:
        env = selenium_env_status()
        if not env["ready"]:
            cat = "BROWSER_NOT_FOUND" if env.get("selenium_installed") else "CONFIG_ERROR"
            return SeleniumFetchResult(status="NOT_READY", error_category=cat)
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service

            opts = Options()
            if self.headless:
                opts.add_argument("--headless=new")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")

            # driver_path=None → Selenium Manager auto-downloads chromedriver
            svc = Service(executable_path=self.driver_path) if self.driver_path else Service()
            driver = webdriver.Chrome(service=svc, options=opts)
            try:
                driver.set_page_load_timeout(self.timeout_sec)
                driver.get(url)
                html = driver.page_source
                screenshot_saved = False
                if screenshot_path is not None:
                    Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                    driver.save_screenshot(str(screenshot_path))
                    screenshot_saved = True
                return SeleniumFetchResult(status="ok", html=html, screenshot_saved=screenshot_saved)
            finally:
                driver.quit()
        except Exception:
            return SeleniumFetchResult(status="JS_RENDER_FAIL", error_category="JS_RENDER_FAIL")


def selenium_env_status() -> dict:
    """Check Selenium environment readiness without launching a browser.

    Readiness rule (Selenium 4.x): chrome_binary_found is sufficient.
    Selenium Manager downloads chromedriver automatically — chromedriver on PATH not required.
    """
    status: dict = {
        "selenium_installed": False,
        "selenium_version": None,
        "selenium_manager": True,  # Selenium 4.x always ships Selenium Manager
        "chromedriver_found": False,
        "chrome_binary_found": False,
        "ready": False,
    }
    try:
        import selenium
        status["selenium_installed"] = True
        status["selenium_version"] = getattr(selenium, "__version__", "unknown")
    except ImportError:
        return status

    status["chromedriver_found"] = shutil.which("chromedriver") is not None
    status["chrome_binary_found"] = _find_chrome_binary()
    # Selenium Manager can supply chromedriver when chrome binary exists
    status["ready"] = status["selenium_installed"] and status["chrome_binary_found"]
    return status


def _find_chrome_binary() -> bool:
    """Locate Chrome/Chromium binary via PATH and Windows standard install paths."""
    if any(shutil.which(name) for name in ("google-chrome", "chromium-browser", "chromium", "chrome")):
        return True
    import os
    import sys
    if sys.platform != "win32":
        return False
    _WIN_CHROME_PATHS = [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
    ]
    return any(os.path.isfile(p) for p in _WIN_CHROME_PATHS if p)
