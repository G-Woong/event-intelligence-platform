"""E-3: browser/Selenium 전략의 no-bypass 정책 — paywall/login/captcha는 렌더 금지(network 0)."""
from __future__ import annotations

from ingestion.orchestration.body_fetch_strategy import fetch_body_with_ladder

_FULL = "본문내용 " * 200  # ~1000자 (>= CONFIDENT_FULL_MIN)


def _fetch(html):
    return lambda url: (200, html, None)


def _ok_robots(u):
    return True


def test_login_marker_skips_browser():
    called = []
    r = fetch_body_with_ladder(
        "https://x.test/a", source_id="x",
        fetch_fn=_fetch("<html>please log in to continue</html>"),
        extract_fn=lambda h, u: (None, "none"), bs4_fn=lambda h, u: (None, "none"),
        robots_fn=_ok_robots, allow_browser=True,
        browser_fn=lambda u: called.append(u) or ("<html/>", "ok"))
    assert r.login_marker is True and r.status == "LOGIN"
    assert called == []


def test_captcha_marker_skips_browser():
    called = []
    r = fetch_body_with_ladder(
        "https://x.test/a", source_id="x",
        fetch_fn=_fetch("<html>verify you are human recaptcha</html>"),
        extract_fn=lambda h, u: (None, "none"), bs4_fn=lambda h, u: (None, "none"),
        robots_fn=_ok_robots, allow_browser=True,
        browser_fn=lambda u: called.append(u) or ("<html/>", "ok"))
    assert r.captcha_marker is True and r.status == "CAPTCHA"
    assert called == []


def test_browser_not_invoked_when_static_sufficient():
    called = []
    r = fetch_body_with_ladder(
        "https://x.test/a", source_id="x",
        fetch_fn=_fetch("<html>full</html>"),
        extract_fn=lambda h, u: (_FULL, "trafilatura"),
        robots_fn=_ok_robots, allow_browser=True,
        browser_fn=lambda u: called.append(u) or ("<html/>", "ok"))
    assert r.status == "SUCCESS" and called == []  # 충분하면 렌더 불필요


def test_browser_disabled_flag_never_calls_browser():
    called = []
    r = fetch_body_with_ladder(
        "https://x.test/a", source_id="x",
        fetch_fn=_fetch("<html>thin</html>"),
        extract_fn=lambda h, u: (None, "none"), bs4_fn=lambda h, u: (None, "none"),
        robots_fn=_ok_robots, allow_browser=False,
        browser_fn=lambda u: called.append(u) or ("<html/>", "ok"))
    assert called == []  # allow_browser=False면 절대 호출 안 함


def test_browser_render_failure_is_tool_unavailable_not_crash():
    r = fetch_body_with_ladder(
        "https://x.test/a", source_id="x",
        fetch_fn=_fetch("<html>thin</html>"),
        extract_fn=lambda h, u: (None, "none"), bs4_fn=lambda h, u: (None, "none"),
        robots_fn=_ok_robots, allow_browser=True,
        browser_fn=lambda u: (_ for _ in ()).throw(RuntimeError("driver boom")))
    assert r.tool_unavailable is True  # 예외 격리 → 크래시 없이 도구 미가용 기록
