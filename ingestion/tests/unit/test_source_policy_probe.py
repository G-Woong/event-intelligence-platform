"""G2-3: SourcePolicyProbe — robots allow/disallow path 판정 + AI 크롤러 차단 감지 + 마커.

네트워크 0: robots_get/page_get 주입형.
"""
from __future__ import annotations

from ingestion.orchestration.source_policy_probe import probe_source_policy

# dcinside gall robots를 단순화한 합성 텍스트(실제 구조 반영: AI 크롤러 site-wide 차단 + *는 일부만 차단)
_DC_ROBOTS = """
User-agent: ClaudeBot
Disallow: /
User-agent: anthropic-ai
Disallow: /
User-agent: GPTBot
Disallow: /
User-agent: *
Allow: /
Disallow: /kcaptcha/
Disallow: /board/lists/?id=stock_new
Disallow: /board/view/?id=stock_new
"""


def test_robots_allows_general_path_but_flags_ai_block():
    r = probe_source_policy(
        source_id="dcinside",
        tested_url="https://gall.dcinside.com/mgallery/board/lists/?id=stockus",
        robots_get=lambda u: _DC_ROBOTS,
    )
    assert r.robots_checked is True
    assert r.robots_allowed is True              # stockus는 *에게 허용
    assert r.ai_crawler_disallowed is True       # AI 크롤러는 site-wide 차단(증거)
    assert r.conclusion == "public_allowed"
    assert "AI crawlers" in (r.terms_notes or "")


def test_robots_disallows_specific_gallery():
    r = probe_source_policy(
        source_id="dcinside",
        tested_url="https://gall.dcinside.com/board/lists/?id=stock_new",
        robots_get=lambda u: _DC_ROBOTS,
    )
    assert r.robots_allowed is False
    assert r.conclusion == "robots_disallow_path"


def test_candidate_paths_split_allowed_blocked():
    r = probe_source_policy(
        source_id="dcinside",
        tested_url="https://gall.dcinside.com/",
        robots_get=lambda u: _DC_ROBOTS,
        candidate_paths=("/board/lists/?id=stockus", "/board/lists/?id=stock_new", "/kcaptcha/x"),
    )
    assert "/board/lists/?id=stockus" in r.allowed_public_paths
    assert "/board/lists/?id=stock_new" in r.blocked_paths
    assert "/kcaptcha/x" in r.blocked_paths


def test_page_marker_captcha_blocks():
    r = probe_source_policy(
        source_id="x", tested_url="https://x.test/a", robots_get=lambda u: "User-agent: *\nAllow: /",
        page_get=lambda u: (200, "<html>Just a moment... checking your browser (cf-chl)</html>"),
    )
    assert r.captcha_detected is True and r.conclusion == "captcha_blocked"


def test_429_sets_rate_limited():
    r = probe_source_policy(
        source_id="x", tested_url="https://x.test/a", robots_get=lambda u: "User-agent: *\nAllow: /",
        page_get=lambda u: (429, None),
    )
    assert r.rate_limit_detected is True and r.conclusion == "rate_limited"


def test_no_robots_when_fetch_fails():
    r = probe_source_policy(
        source_id="x", tested_url="https://x.test/a", robots_get=lambda u: None,
    )
    assert r.robots_checked is False and r.robots_allowed is None
    assert r.conclusion == "no_robots"


def test_empty_robots_allows_everything():
    # trends.google.com 처럼 directive 0개 → 차단 아님
    r = probe_source_policy(
        source_id="google_trends_explore",
        tested_url="https://trends.google.com/trends/explore?q=x",
        robots_get=lambda u: "# comment only\n",
    )
    assert r.robots_checked is True and r.robots_allowed is True
    assert r.ai_crawler_disallowed is False and r.conclusion == "public_allowed"
