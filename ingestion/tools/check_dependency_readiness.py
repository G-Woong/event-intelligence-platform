from __future__ import annotations

"""수집 파이프라인 런타임 의존성 점검 (09 §1). 키 값 미출력 — NAME/존재 여부만.

종료 코드: 전부 READY=0, 하나라도 MISSING이 있으면 1 (DEGRADED는 비차단).
점검 항목:
  [1] import 가능성 (playwright/selenium/trafilatura/readability/bs4/lxml/
      feedparser/yaml/httpx/langgraph)
  [2] playwright chromium 바이너리 launch 가능 여부
  [3] selenium 환경 (기존 selenium_env_status() 재사용 — 새로 만들지 않음)
  [4] outputs/state 쓰기 권한 (tmp write→delete)
  [5] (정보성) INGESTION_RATE_LIMIT_BACKEND 값 + rate_limit_cache.json 존재
"""

import argparse
import importlib
import os
import sys
from pathlib import Path

# 점검 대상 import 모듈명 (import 이름 기준 — readability-lxml의 import 이름은 readability)
_REQUIRED_MODULES = [
    "playwright",
    "selenium",
    "trafilatura",
    "readability",
    "bs4",
    "lxml",
    "feedparser",
    "yaml",
    "httpx",
    "langgraph",
]


def _find_repo_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in (p.parent, p.parent.parent, p.parent.parent.parent):
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            return candidate
    return Path.cwd()


def check_imports(modules: list[str]) -> list[dict]:
    """각 모듈 import 시도 → READY/MISSING. 값/경로 노출 없음."""
    results: list[dict] = []
    for name in modules:
        try:
            importlib.import_module(name)
            results.append({"component": f"import:{name}", "status": "READY", "fix": ""})
        except Exception as exc:  # ImportError 외 (lxml_html_clean 누락 등) 포함
            results.append({
                "component": f"import:{name}",
                "status": "MISSING",
                "fix": f"uv pip install {name}  ({type(exc).__name__})",
            })
    return results


def check_playwright_chromium(timeout_s: int = 15) -> dict:
    """chromium 바이너리 launch→close 시도. 실패 시 설치 명령 안내."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {
            "component": "playwright_chromium",
            "status": "MISSING",
            "fix": f"uv pip install playwright  ({type(exc).__name__})",
        }
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return {"component": "playwright_chromium", "status": "READY", "fix": ""}
    except Exception as exc:
        msg = str(exc)
        if "Executable doesn't exist" in msg or "playwright install" in msg:
            fix = "python -m playwright install chromium"
        else:
            fix = f"chromium launch failed ({type(exc).__name__})"
        return {"component": "playwright_chromium", "status": "MISSING", "fix": fix}


def check_selenium() -> dict:
    """기존 selenium_env_status() 재사용. chrome binary 없으면 DEGRADED(비차단)."""
    try:
        from ingestion.fetch_strategies.selenium_strategy import selenium_env_status
    except Exception as exc:
        return {
            "component": "selenium_env",
            "status": "MISSING",
            "fix": f"selenium import 실패 ({type(exc).__name__})",
        }
    st = selenium_env_status()
    if st.get("ready"):
        return {"component": "selenium_env", "status": "READY", "fix": ""}
    # selenium 자체는 설치됐으나 chrome binary 미발견 등 — playwright가 주 경로라 비차단
    return {
        "component": "selenium_env",
        "status": "DEGRADED",
        "fix": "install Chrome/Chromium binary (selenium은 보조 경로 — 비차단)",
    }


def check_state_writable(repo_root: Path | None = None) -> dict:
    """outputs/state 디렉토리에 임시 파일 write→delete 권한 확인."""
    root = repo_root or _find_repo_root()
    state_dir = root / "ingestion" / "outputs" / "state"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        probe = state_dir / ".readiness_write_probe.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return {"component": "state_writable", "status": "READY", "fix": ""}
    except Exception as exc:
        return {
            "component": "state_writable",
            "status": "MISSING",
            "fix": f"outputs/state 쓰기 불가 ({type(exc).__name__})",
        }


def check_rate_limit_backend(repo_root: Path | None = None) -> dict:
    """(정보성) rate limit backend 설정값 + cache 파일 존재. 항상 READY."""
    root = repo_root or _find_repo_root()
    backend = os.environ.get("INGESTION_RATE_LIMIT_BACKEND", "(default)")
    cache_exists = (root / "ingestion" / "outputs" / "state" / "rate_limit_cache.json").exists()
    return {
        "component": "rate_limit_backend",
        "status": "READY",
        "fix": f"backend={backend}, rate_limit_cache.json={'present' if cache_exists else 'absent'}",
    }


def run_all_checks(repo_root: Path | None = None) -> list[dict]:
    rows: list[dict] = []
    rows.extend(check_imports(_REQUIRED_MODULES))
    rows.append(check_playwright_chromium())
    rows.append(check_selenium())
    rows.append(check_state_writable(repo_root))
    rows.append(check_rate_limit_backend(repo_root))
    return rows


def _safe_print(line: str) -> None:
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode("ascii", errors="replace").decode("ascii"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="수집 파이프라인 런타임 의존성 점검 (키 값 미출력)."
    )
    parser.add_argument(
        "--skip-browser",
        action="store_true",
        help="chromium launch 점검 생략 (import만 확인)",
    )
    args = parser.parse_args()

    rows: list[dict] = []
    rows.extend(check_imports(_REQUIRED_MODULES))
    if args.skip_browser:
        rows.append({"component": "playwright_chromium", "status": "SKIPPED", "fix": "--skip-browser"})
    else:
        rows.append(check_playwright_chromium())
    rows.append(check_selenium())
    rows.append(check_state_writable())
    rows.append(check_rate_limit_backend())

    width = max(len(r["component"]) for r in rows)
    _safe_print(f"{'COMPONENT':<{width}}  STATUS    FIX")
    _safe_print(f"{'-' * width}  --------  ---")
    for r in rows:
        _safe_print(f"{r['component']:<{width}}  {r['status']:<8}  {r['fix']}")

    missing = [r for r in rows if r["status"] == "MISSING"]
    degraded = [r for r in rows if r["status"] == "DEGRADED"]
    _safe_print("")
    _safe_print(
        f"summary: {sum(1 for r in rows if r['status'] == 'READY')} READY / "
        f"{len(degraded)} DEGRADED / {len(missing)} MISSING"
    )
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
