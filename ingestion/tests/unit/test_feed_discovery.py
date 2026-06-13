"""feed_discovery (기법 2·3·6) + 기법 10 공유화 단위 테스트 — 네트워크 없음."""


# ── 기법 2: RSS/Atom autodiscovery ───────────────────────────────────────────

def test_discover_feeds_from_link_tags():
    from ingestion.tools.feed_discovery import discover_feeds
    html = (
        '<html><head>'
        '<link rel="alternate" type="application/rss+xml" href="/feed.xml">'
        '<link rel="alternate" type="application/atom+xml" href="https://x.test/atom">'
        '<link rel="stylesheet" href="/style.css">'
        '</head></html>'
    )
    feeds = discover_feeds(html, "https://x.test/news")
    assert "https://x.test/feed.xml" in feeds
    assert "https://x.test/atom" in feeds
    assert all("style.css" not in f for f in feeds)


def test_discover_feeds_falls_back_to_common_paths():
    from ingestion.tools.feed_discovery import discover_feeds
    feeds = discover_feeds("<html><head></head></html>", "https://news.test/section")
    assert "https://news.test/rss" in feeds
    assert "https://news.test/feed" in feeds


def test_discover_feeds_dedupes():
    from ingestion.tools.feed_discovery import discover_feeds
    html = (
        '<head>'
        '<link rel="alternate" type="application/rss+xml" href="https://x.test/f">'
        '<link rel="alternate" type="application/rss+xml" href="https://x.test/f">'
        '</head>'
    )
    feeds = discover_feeds(html, "https://x.test/")
    assert feeds.count("https://x.test/f") == 1


# ── 기법 3: Google News RSS 프록시 ───────────────────────────────────────────

def test_google_news_proxy_url_rules():
    from ingestion.tools.feed_discovery import google_news_proxy_url
    url = google_news_proxy_url("apnews.com")
    assert url.startswith("https://news.google.com/rss/search?q=")
    assert "site%3Aapnews.com" in url
    assert "hl=en-US" in url and "gl=US" in url


def test_google_news_proxy_strips_www():
    from ingestion.tools.feed_discovery import google_news_proxy_url
    url = google_news_proxy_url("www.bbc.com", lang="ko-KR", country="KR")
    assert "site%3Abbc.com" in url
    assert "gl=KR" in url


# ── 기법 6: sitemap 발견 (공통 경로는 네트워크 없이 항상 포함) ────────────────

def test_discover_sitemaps_includes_common_paths(monkeypatch):
    import httpx
    from ingestion.tools import feed_discovery

    class _Boom:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, *a, **k): raise RuntimeError("no network")

    monkeypatch.setattr(httpx, "Client", lambda **k: _Boom(**k))
    sm = feed_discovery.discover_sitemaps("https://ec.europa.eu/commission/presscorner")
    assert "https://ec.europa.eu/sitemap.xml" in sm
    assert "https://ec.europa.eu/news-sitemap.xml" in sm


# ── 기법 10: rate-limit 신호 단일 출처 ───────────────────────────────────────

def test_rate_limited_signals_shared_source():
    from ingestion.core.error_taxonomy import is_rate_limited_text, RATE_LIMITED_SIGNALS
    assert is_rate_limited_text("HTTP 429 Too Many Requests")
    assert is_rate_limited_text("Please limit requests to one every 5 seconds")
    assert not is_rate_limited_text("normal article body text")
    assert "too many requests" in RATE_LIMITED_SIGNALS


def test_playwright_probe_detect_429_uses_shared_signals():
    """playwright_probe._detect_429이 error_taxonomy 공유 함수를 사용한다."""
    from ingestion.probes.playwright_probe import _detect_429
    assert _detect_429("<html>rate limit exceeded</html>")
    assert not _detect_429("<html><body>real content here</body></html>")
