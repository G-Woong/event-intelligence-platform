"""G-6: news body rescue ladder — 최선 본문 판정(네트워크 0, 주입형 fn)."""
from __future__ import annotations

from ingestion.orchestration.body_rescue_ladder import rescue_news_body

_FULL = "본문내용 " * 200  # >= CONFIDENT_FULL_MIN


def _fetch(html):
    return lambda url: (200, html, None)


def _ok_robots(u):
    return True


def test_full_body_is_article_alive():
    r = rescue_news_body([("https://x.test/a", "Title A")], source_id="cnbc",
                         fetch_fn=_fetch("<html>x</html>"),
                         extract_fn=lambda h, u: (_FULL, "trafilatura"), robots_fn=_ok_robots)
    assert r.best_status == "SUCCESS" and r.readiness_verdict == "ARTICLE_BODY_ALIVE"


def test_no_body_verdict():
    r = rescue_news_body([("https://x.test/a", "Title")], source_id="cnbc",
                         fetch_fn=_fetch("<html>x</html>"),
                         extract_fn=lambda h, u: (None, "none"),
                         bs4_fn=lambda h, u: (None, "none"), robots_fn=_ok_robots)
    assert r.readiness_verdict == "NO_BODY"


def test_paywall_marker_blocks_no_bypass():
    called = []
    r = rescue_news_body([("https://x.test/a", "Title")], source_id="cnbc",
                         fetch_fn=_fetch("<html>subscribe to continue reading</html>"),
                         extract_fn=lambda h, u: (None, "none"),
                         bs4_fn=lambda h, u: (None, "none"), robots_fn=_ok_robots,
                         allow_browser=True, browser_fn=lambda u: called.append(u) or ("<html/>", "ok"))
    assert r.paywall_marker is True
    assert r.readiness_verdict == "PAYWALL_BLOCKED_NO_BYPASS"
    assert called == []  # 마커 시 브라우저 우회 금지


def test_picks_best_across_candidates():
    # 첫 후보 no body, 둘째 full → best=SUCCESS
    def extract(h, u):
        return (_FULL, "trafilatura") if "good" in h else (None, "none")

    def fetch(url):
        return (200, "<html>good</html>" if url.endswith("2") else "<html>bad</html>", None)
    r = rescue_news_body([("https://x.test/1", "A"), ("https://x.test/2", "B")],
                         source_id="cnbc", fetch_fn=fetch, extract_fn=extract,
                         bs4_fn=lambda h, u: (None, "none"), robots_fn=_ok_robots)
    assert r.best_status == "SUCCESS"


def test_no_url_candidates():
    r = rescue_news_body([(None, "no url")], source_id="cnbc")
    assert r.readiness_verdict == "NO_BODY" and r.attempted_urls == 0
