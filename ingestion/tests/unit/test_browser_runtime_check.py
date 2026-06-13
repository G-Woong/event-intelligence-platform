from __future__ import annotations

import json
import os

from ingestion.runners import run_browser_runtime_check as rc


def test_report_structure():
    report = rc.run_runtime_check(launch=False)
    assert report["overall"] in ("READY", "PARTIAL", "NOT_READY")
    assert "python" in report
    assert "playwright" in report
    assert "selenium" in report
    assert "screenshot_capable" in report
    assert report["playwright_launch"] is None  # --launch 없으면 비기동


def test_playwright_missing_means_not_ready_or_partial(monkeypatch):
    monkeypatch.setattr(
        rc, "_check_playwright",
        lambda: {"installed": False, "version": None, "chromium_installed": False},
    )
    monkeypatch.setattr(
        rc, "_check_selenium",
        lambda: {"selenium_installed": False, "ready": False},
    )
    report = rc.run_runtime_check(launch=False)
    assert report["overall"] == "NOT_READY"


def test_partial_when_only_selenium_ready(monkeypatch):
    monkeypatch.setattr(
        rc, "_check_playwright",
        lambda: {"installed": False, "version": None, "chromium_installed": False},
    )
    monkeypatch.setattr(
        rc, "_check_selenium",
        lambda: {"selenium_installed": True, "ready": True},
    )
    report = rc.run_runtime_check(launch=False)
    assert report["overall"] == "PARTIAL"


def test_report_contains_no_env_values():
    """리포트 직렬화 결과에 환경변수 값이 섞이지 않는다."""
    report = rc.run_runtime_check(launch=False)
    serialized = json.dumps(report)
    for key in ("OPENAI_API_KEY", "LANGSMITH_API_KEY", "NAVER_CLIENT_SECRET"):
        val = os.environ.get(key, "")
        if val and len(val) >= 8:
            assert (val in serialized) is False


def test_main_not_ready_is_safe_without_strict(monkeypatch, capsys):
    monkeypatch.setattr(
        rc, "run_runtime_check",
        lambda launch=False: {
            "overall": "NOT_READY",
            "python": {"version": "3.11.9", "ok": True},
            "playwright": {"installed": False, "version": None, "chromium_installed": False},
            "playwright_launch": None,
            "selenium": {"selenium_installed": False, "ready": False},
            "screenshot_capable": False,
        },
    )
    assert rc.main([]) == 0          # NOT_READY여도 안전 반환
    assert rc.main(["--strict"]) == 1  # --strict일 때만 exit≠0
