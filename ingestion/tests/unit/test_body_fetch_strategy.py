"""Phase E-2: policy-safe body fetch — 길이만으로 present 판정하지 않고 우회하지 않는다.

network은 주입형 ``fetch_fn``/``extract_fn``/``robots_fn``으로 격리(테스트 0-network).
"""
from __future__ import annotations

from ingestion.orchestration.full_source_revival import fetch_article_body

_LONG = "기사 본문 " * 80  # 충분히 긴 본문(임계 초과)


def _fetch_ok(html):
    return lambda url: (200, html, None)


def test_no_url_is_skipped():
    r = fetch_article_body(None, source_id="s")
    assert r.attempted is False and r.status == "SKIPPED_NO_URL"


def test_robots_disallow_is_not_bypassed():
    r = fetch_article_body("https://x.com/a", source_id="s",
                           fetch_fn=_fetch_ok("<html>"), robots_fn=lambda u: False)
    assert r.status == "ROBOTS_BLOCKED" and r.attempted is False
    assert r.error_type == "robots_disallow"


def test_successful_body_extraction():
    r = fetch_article_body(
        "https://x.com/a", source_id="s",
        fetch_fn=_fetch_ok("<html>body</html>"),
        extract_fn=lambda html, url: (_LONG, "fake"),
        robots_fn=lambda u: True)
    assert r.status == "SUCCESS"
    assert r.body_state == "present"
    assert r.extractor_used == "fake"
    assert r.body_length >= 200


def test_excerpt_marker_not_promoted_to_present():
    body = "짧은 도입부. " * 30 + " Read the full story at Example."
    r = fetch_article_body(
        "https://x.com/a", source_id="s",
        fetch_fn=_fetch_ok("<html>"),
        extract_fn=lambda html, url: (body, "fake"),
        robots_fn=lambda u: True)
    # 길이가 임계를 넘어도 발췌 꼬리표 → present 아님
    assert r.excerpt_marker_detected is True
    assert r.status == "EXCERPT_ONLY"
    assert r.body_state == "snippet_only"


def test_empty_body_is_no_body():
    r = fetch_article_body(
        "https://x.com/a", source_id="s",
        fetch_fn=_fetch_ok("<html>"),
        extract_fn=lambda html, url: (None, "none"),
        robots_fn=lambda u: True)
    assert r.status == "NO_BODY"


def test_http_error_status():
    r = fetch_article_body(
        "https://x.com/a", source_id="s",
        fetch_fn=lambda url: (503, None, "server_error"),
        robots_fn=lambda u: True)
    assert r.status == "HTTP_ERROR"
    assert r.http_status == 503


def test_fetch_exception_is_isolated():
    def boom(url):
        raise RuntimeError("network down")

    r = fetch_article_body("https://x.com/a", source_id="s",
                           fetch_fn=boom, robots_fn=lambda u: True)
    assert r.status == "FETCH_ERROR"
    assert r.error_type == "RuntimeError"


def test_boilerplate_risk_detected():
    body = "Subscribe now. Sign in. Accept all cookies. " + ("내용 " * 60)
    r = fetch_article_body(
        "https://x.com/a", source_id="s",
        fetch_fn=_fetch_ok("<html>"),
        extract_fn=lambda html, url: (body, "fake"),
        robots_fn=lambda u: True)
    assert r.boilerplate_risk in ("medium", "high")
