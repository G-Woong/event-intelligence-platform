"""url_resolver(09 §2-4, 기법 4) 단위 테스트 — 전부 MockTransport, 실제 네트워크 없음."""
import httpx
import pytest

from ingestion.tools import url_resolver
from ingestion.tools.url_resolver import resolve


@pytest.fixture(autouse=True)
def _clear_cache():
    url_resolver.clear_cache()
    yield
    url_resolver.clear_cache()


def _client(handler, max_hops=5):
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        max_redirects=max_hops,
    )


def test_resolve_follows_3_hop_redirect_chain():
    # proxy → hop1 → hop2 → 최종 원본
    chain = {
        "https://news.google.com/rss/articles/ABC": "https://hop1.example/a",
        "https://hop1.example/a": "https://hop2.example/b",
        "https://hop2.example/b": "https://apnews.com/article/final",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        nxt = chain.get(str(request.url))
        if nxt:
            return httpx.Response(302, headers={"Location": nxt})
        return httpx.Response(200)

    with _client(handler) as c:
        out = resolve("https://news.google.com/rss/articles/ABC", client=c)
    assert out == "https://apnews.com/article/final", \
        "redirect 체인 끝의 원본 apnews.com URL로 해석되어야 한다"


def test_resolve_returns_original_on_network_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    url = "https://news.google.com/rss/articles/XYZ"
    with _client(handler) as c:
        out = resolve(url, client=c)
    assert out == url, "해석 실패 시 수집을 죽이지 말고 원본 URL을 그대로 반환해야 한다"


def test_resolve_returns_original_on_too_many_redirects():
    # 무한 루프: 항상 자기 자신으로 redirect → TooManyRedirects → 원본 반환
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://loop.example/next"})

    url = "https://loop.example/start"
    with _client(handler, max_hops=3) as c:
        out = resolve(url, max_hops=3, client=c)
    assert out == url, "max_hops 초과(무한 redirect) 시 원본 URL을 반환해야 한다"


def test_resolve_google_news_opaque_url_unchanged():
    # 신형 Google News URL: redirect 없이 200 (JS 디코드) → 원본에 도달 못함 = 입력 그대로
    gn = "https://news.google.com/rss/articles/CBMiOPAQUE?oc=5"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    with _client(handler) as c:
        out = resolve(gn, client=c)
    assert out == gn, \
        "Google News 신형 URL은 HTTP redirect가 없어(외부 제한) 입력 URL 그대로 반환된다"


def test_resolve_head_blocked_falls_back_to_get():
    target = "https://apnews.com/article/via-get"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(405)  # HEAD 차단
        # GET: 최종 원본으로 redirect
        if "proxy" in str(request.url):
            return httpx.Response(302, headers={"Location": target})
        return httpx.Response(200)

    with _client(handler) as c:
        out = resolve("https://proxy.example/x", client=c)
    assert out == target, "HEAD 차단(405) 시 GET 폴백으로 원본을 해석해야 한다"


def test_resolve_caches_by_url(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200)

    url = "https://example.com/cacheme"
    with _client(handler) as c:
        first = resolve(url, client=c)
        second = resolve(url, client=c)
    assert first == second
    assert calls["n"] == 1, "동일 URL은 캐시되어 재요청하지 않아야 한다"


# ── 브라우저 승격 경로 (Playwright 1-hop) ─────────────────────────────────────

def test_needs_browser_resolution():
    assert url_resolver.needs_browser_resolution("https://news.google.com/rss/articles/CBMx")
    assert not url_resolver.needs_browser_resolution("https://apnews.com/article/x")
    assert not url_resolver.needs_browser_resolution("")


def test_canonical_from_html_og_url():
    html = '<meta property="og:url" content="https://apnews.com/article/abc">'
    assert url_resolver.canonical_from_html(html) == "https://apnews.com/article/abc"


def test_canonical_from_html_canonical_link_when_og_is_google():
    # og:url이 news.google.com이면 건너뛰고 canonical(apnews)을 잡아야 한다
    html = (
        '<meta property="og:url" content="https://news.google.com">'
        '<link rel="canonical" href="https://apnews.com/article/def">'
    )
    assert url_resolver.canonical_from_html(html) == "https://apnews.com/article/def"


def test_canonical_from_html_anchor_fallback():
    html = '<a href="https://apnews.com/article/ghi">read</a>'
    assert url_resolver.canonical_from_html(html) == "https://apnews.com/article/ghi"


def test_canonical_from_html_none_when_no_apnews():
    html = '<meta property="og:url" content="https://news.google.com"><a href="/x">y</a>'
    assert url_resolver.canonical_from_html(html) is None


def test_resolve_via_browser_returns_apnews(monkeypatch):
    async def _fake(url, timeout_ms, max_wait_ms):
        return "https://apnews.com/article/resolved-by-browser"

    monkeypatch.setattr(url_resolver, "_resolve_via_browser_async", _fake)
    out = url_resolver.resolve_via_browser("https://news.google.com/rss/articles/CBMx")
    assert out == "https://apnews.com/article/resolved-by-browser"


def test_resolve_via_browser_failsafe_on_error(monkeypatch):
    async def _boom(url, timeout_ms, max_wait_ms):
        raise RuntimeError("playwright down")

    monkeypatch.setattr(url_resolver, "_resolve_via_browser_async", _boom)
    gn = "https://news.google.com/rss/articles/CBMy"
    out = url_resolver.resolve_via_browser(gn)
    assert out == gn, "브라우저 해석 실패 시 수집을 죽이지 말고 원본 URL을 반환해야 한다"
