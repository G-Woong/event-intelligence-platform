"""E-3: 본문 fetch strategy ladder(trafilatura→readability→bs4→browser) — network 0(주입형 fn)."""
from __future__ import annotations

from ingestion.orchestration.body_fetch_strategy import fetch_body_with_ladder

_FULL = "본문내용 " * 200  # ~1000자 (>= CONFIDENT_FULL_MIN)  # >= FULL_BODY_MIN


def _fetch_ok(html):
    return lambda url: (200, html, None)


def _allow_robots(url):
    return True


def test_no_url_skips():
    r = fetch_body_with_ladder(None, source_id="x")
    assert r.status == "SKIPPED_NO_URL" and r.attempted is False


def test_robots_block_no_fetch():
    r = fetch_body_with_ladder("https://x.test/a", source_id="x",
                               robots_fn=lambda u: False)
    assert r.status == "ROBOTS_BLOCKED" and r.attempted is False


def test_trafilatura_first_then_no_bs4():
    calls = []

    def extract(html, url):
        calls.append("extract")
        return _FULL, "trafilatura"

    def bs4(html, url):
        calls.append("bs4")
        return None, "none"

    r = fetch_body_with_ladder("https://x.test/a", source_id="x",
                               fetch_fn=_fetch_ok("<html>body</html>"),
                               extract_fn=extract, bs4_fn=bs4, robots_fn=_allow_robots)
    assert r.status == "SUCCESS" and r.extractor_used == "trafilatura"
    assert "bs4" not in calls  # 1차 성공 시 bs4 미호출


def test_bs4_fallback_when_trafilatura_empty():
    r = fetch_body_with_ladder("https://x.test/a", source_id="x",
                               fetch_fn=_fetch_ok("<html>x</html>"),
                               extract_fn=lambda h, u: (None, "none"),
                               bs4_fn=lambda h, u: (_FULL, "bs4_paragraphs"),
                               robots_fn=_allow_robots)
    assert r.status == "SUCCESS" and r.extractor_used == "bs4_paragraphs"


def test_paywall_marker_blocks_browser_no_bypass():
    browser_called = []
    html = "<html>To continue reading subscribe to continue</html>"
    r = fetch_body_with_ladder("https://x.test/a", source_id="x",
                               fetch_fn=_fetch_ok(html),
                               extract_fn=lambda h, u: (None, "none"),
                               bs4_fn=lambda h, u: (None, "none"),
                               robots_fn=_allow_robots, allow_browser=True,
                               browser_fn=lambda u: browser_called.append(u) or ("<html/>", "ok"))
    assert r.paywall_marker is True
    assert r.status == "PAYWALL"
    assert browser_called == []  # 마커 감지 시 브라우저 우회 시도 금지


def test_browser_render_when_static_insufficient_no_marker():
    r = fetch_body_with_ladder("https://x.test/a", source_id="x",
                               fetch_fn=_fetch_ok("<html>thin</html>"),
                               extract_fn=lambda h, u: (None, "none") if "thin" in h else (_FULL, "trafilatura"),
                               bs4_fn=lambda h, u: (None, "none"),
                               robots_fn=_allow_robots, allow_browser=True,
                               browser_fn=lambda u: ("<html>rendered full</html>", "ok"))
    assert r.browser_used is True and r.status == "SUCCESS"
    assert r.extractor_used.startswith("browser+")


def test_browser_unavailable_marks_tool_unavailable():
    r = fetch_body_with_ladder("https://x.test/a", source_id="x",
                               fetch_fn=_fetch_ok("<html>thin</html>"),
                               extract_fn=lambda h, u: (None, "none"),
                               bs4_fn=lambda h, u: (None, "none"),
                               robots_fn=_allow_robots, allow_browser=True,
                               browser_available=True,
                               browser_fn=lambda u: (None, "NOT_READY"))
    assert r.tool_unavailable is True


def test_http_error_reported():
    r = fetch_body_with_ladder("https://x.test/a", source_id="x",
                               fetch_fn=lambda u: (403, None, "HTTP 403"),
                               robots_fn=_allow_robots)
    assert r.status == "HTTP_ERROR" and r.http_status == 403


def test_stored_html_skips_fetch():
    fetched = []
    r = fetch_body_with_ladder("https://x.test/a", source_id="zdnet_korea",
                               html="<html>" + _FULL + "</html>",
                               fetch_fn=lambda u: fetched.append(u) or (200, "x", None),
                               extract_fn=lambda h, u: (_FULL, "trafilatura"),
                               robots_fn=_allow_robots)
    assert r.status == "SUCCESS"
    assert fetched == []  # html 직접 주입 → httpx fetch 건너뜀
    assert "stored_html" in r.strategies_tried


def test_promo_block_unrelated_to_title_not_success():
    # 기사(title)와 무관한 짧은 프로모션 본문(<600자, title 토큰 겹침 없음)은 SUCCESS 둔갑 금지.
    promo = ("Where do the sharpest minds on Wall Street believe the market is headed? "
             "The CNBC Pro exclusive Market Strategist Survey is a roundup of year-end "
             "targets for the S&P 500 from top Wall Street strategists. " * 2)
    r = fetch_body_with_ladder("https://x.test/elon-musk-spacex.html", source_id="cnbc",
                               title="Elon Musk drifted from Larry Page but SpaceX Google closer",
                               fetch_fn=_fetch_ok("<html>x</html>"),
                               extract_fn=lambda h, u: (promo, "trafilatura"),
                               robots_fn=_allow_robots)
    assert r.status != "SUCCESS"  # title 무관 프로모션 → full 둔갑 안 함


def test_short_body_with_title_overlap_is_success():
    # 짧아도 title content 토큰이 본문에 등장하면 실본문으로 인정.
    body = "Elon Musk and SpaceX announced a new rocket launch from the Texas facility today. " * 3
    r = fetch_body_with_ladder("https://x.test/a", source_id="x",
                               title="Elon Musk SpaceX rocket launch Texas",
                               fetch_fn=_fetch_ok("<html>x</html>"),
                               extract_fn=lambda h, u: (body, "trafilatura"),
                               robots_fn=_allow_robots)
    assert r.status == "SUCCESS"


def test_excerpt_only_downgraded_not_present():
    short = "단어 " * 20  # PARTIAL_MIN 초과, FULL_BODY_MIN 미만 → partial/snippet
    r = fetch_body_with_ladder("https://x.test/a", source_id="x",
                               fetch_fn=_fetch_ok("<html>x</html>"),
                               extract_fn=lambda h, u: (short, "trafilatura"),
                               robots_fn=_allow_robots)
    assert r.status in ("PARTIAL", "EXCERPT_ONLY", "NO_BODY")
    assert r.status != "SUCCESS"  # 길이 미달은 present로 둔갑하지 않음
